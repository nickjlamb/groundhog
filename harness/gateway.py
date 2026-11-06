"""Tool gateways: replay (frozen cassettes plus faults) and record (live PubCrawl).

Both route Redacta calls to a local client, which runs live in either mode.
Every call returns a dict describing what happened, for the trace.
"""

import copy
import time

from .cassette import Cassette
from .corpus import CORPUS_TOOLS, Corpus
from .faults import FaultState
from .paging import page_response, select_sections
from .tools import EXTERNAL, LOCAL, PAGED

OFF_PATH = {"results": [], "note": "No results found."}
LABEL_TOOLS = {"get_smpc", "get_uspi", "compare_labels"}
_CORPUS = None


def shared_corpus():
    global _CORPUS
    if _CORPUS is None:
        _CORPUS = Corpus()
    return _CORPUS


def _secs(args):
    return sorted(str(s).lower().strip() for s in (args.get("sections") or []))
FULL_SECTION_CHARS = 50000


class _Base:
    def __init__(self, task: dict, cassette: Cassette, local_client=None):
        self.task = task
        self.cassette = cassette
        self.local = local_client

    def _local(self, tool, args):
        if self.local is None:
            return {"error": "Redacta is not available in this run."}, True
        return self.local.call_tool(tool, args)

    def call(self, tool: str, args: dict) -> dict:
        if tool in LOCAL:
            result, is_error = self._local(tool, args)
            return {"tool": tool, "args": args, "result": result, "is_error": is_error,
                    "external": False, "off_path": False}
        if tool not in EXTERNAL:
            return {"tool": tool, "args": args, "result": {"error": f"Unknown tool: {tool}"},
                    "is_error": True, "external": False, "off_path": False}
        return self._external(tool, args)


class ReplayGateway(_Base):
    def __init__(self, task, cassette, fault: str = "F0", local_client=None, corpus=None):
        super().__init__(task, cassette, local_client)
        self.faults = FaultState(task, fault)
        self.corpus = corpus if corpus is not None else shared_corpus()

    def _lookup(self, tool, args, variant):
        """Return (response, served_by) or (None, None).

        1. exact match;
        2. labels: some sections of a whole-label recording of the same request;
        3. labels: the same product named differently ("metformin" for a recorded
           "Glucophage" SmPC), but never a different product;
        4. abstracts: any article in the shared corpus.
        """
        hit = self.cassette.lookup(tool, args, variant=variant)
        if hit is not None:
            return hit, "cassette"
        if tool in PAGED and args.get("sections"):
            whole = {k: v for k, v in args.items() if k != "sections"}
            hit = self.cassette.lookup(tool, whole, variant=variant)
            if hit is not None:
                return select_sections(hit, args["sections"]), "cassette"
        if tool in LABEL_TOOLS:
            hit = self._same_product(tool, args, variant)
            if hit is not None:
                return hit, "cassette:same_product"
        if tool == "get_abstract" and args.get("pmid") and variant == "current":
            hit = self.corpus.abstract(args["pmid"])
            if hit is not None:
                return hit, "corpus"
        return None, None

    def _same_product(self, tool, args, variant):
        names = [args.get(k) for k in ("drug", "us_drug", "uk_drug") if args.get(k)]
        if not names:
            return None
        want = _secs(args)
        best = None
        for e in self.cassette.data["entries"]:
            if e["tool"] != tool or e.get("variant", "current") != variant:
                continue
            ea = e["args"]
            enames = [ea.get(k) for k in ("drug", "us_drug", "uk_drug") if ea.get(k)]
            resp = e["response"] if isinstance(e["response"], dict) else {}
            enames += [resp.get("drug_name", "")] + list((resp.get("lookup_names") or {}).values())
            if not all(self.corpus.same_product(n, [x for x in enames if x]) for n in names[:1]):
                continue
            have = _secs(ea)
            if tool in PAGED:
                if not have:
                    return select_sections(e["response"], args.get("sections"))
                if want and set(want) <= set(have):
                    best = select_sections(e["response"], want)
            elif tool == "compare_labels":
                if have == want:
                    return e["response"]
                if not have and want:
                    r = copy.deepcopy(e["response"])
                    r["comparisons"] = [c for c in r.get("comparisons", [])
                                        if any(w in str(c.get("topic", "")).lower() for w in want)]
                    best = r if r["comparisons"] else best
        return best

    def _from_corpus(self, tool, args):
        hit = self.cassette.lookup(tool, args)          # a live recording wins if present
        if hit is not None:
            return hit, "cassette"
        hit = self.corpus.answer(tool, args)
        return (hit, "corpus") if hit is not None else (None, None)

    def _external(self, tool, args):
        base = {"tool": tool, "args": args, "external": True}
        short = self.faults.before_call(tool, args)
        if short is not None:
            result, is_error = short
            return {**base, "result": result, "is_error": is_error, "off_path": False}
        if tool in CORPUS_TOOLS:
            variant = "current"
            recorded, served_by = self._from_corpus(tool, args)
        else:
            variant = self.faults.variant_for(tool, self.cassette)
            recorded, served_by = self._lookup(tool, args, variant)
            if recorded is None and variant != "current":
                recorded, served_by = self._lookup(tool, args, "current")
        if recorded is None:
            return {**base, "result": copy.deepcopy(OFF_PATH), "is_error": False, "off_path": True,
                    "served_by": None}
        base["served_by"] = served_by
        if isinstance(recorded, dict) and "_recorded_error" in recorded:
            # The live source answered with an error (e.g. no open-access full text): replay it as such.
            return {**base, "result": copy.deepcopy(recorded["_recorded_error"]), "is_error": True,
                    "off_path": False, "variant": variant}
        result = copy.deepcopy(recorded)
        if tool in PAGED:
            cut = self.faults.first_page_cut(tool, result, args.get("offset"))
            result = page_response(result, args.get("max_chars"), args.get("offset"), first_page_cut=cut)
        result = self.faults.after_call(tool, result)
        return {**base, "result": result, "is_error": False, "off_path": False, "variant": variant}


RETRY_WAITS = (5, 20, 45, None)


class RecordGateway(_Base):
    """Calls live PubCrawl, stores each response in the cassette, serves it clean (F0)."""

    def __init__(self, task, cassette, pubcrawl_client, recorded_by: str, local_client=None):
        super().__init__(task, cassette, local_client)
        self.pubcrawl = pubcrawl_client
        self.recorded_by = recorded_by
        self.errors = []          # live calls that still failed after retries

    def _external(self, tool, args):
        base = {"tool": tool, "args": args, "external": True, "off_path": False}
        live_args = dict(args)
        if tool in PAGED:
            live_args.pop("offset", None)
            live_args["max_chars"] = FULL_SECTION_CHARS
        for wait in RETRY_WAITS:
            result, is_error = self.pubcrawl.call_tool(tool, live_args)
            if not is_error or wait is None:
                break
            time.sleep(wait)      # 429s and unreachable sources are usually transient
        self.errors += [{"tool": tool, "args": args, "result": result}] if is_error else []
        if not is_error:
            self.cassette.add(tool, args, result, recorded_by=self.recorded_by)
        served = copy.deepcopy(result)
        if tool in PAGED and not is_error:
            served = page_response(served, args.get("max_chars"), args.get("offset"))
        return {**base, "result": served, "is_error": is_error}
