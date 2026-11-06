"""Tool gateways: replay (frozen cassettes plus faults) and record (live PubCrawl).

Both route Redacta calls to a local client, which runs live in either mode.
Every call returns a dict describing what happened, for the trace.
"""

import copy
import time

from .cassette import Cassette
from .faults import FaultState
from .paging import page_response, select_sections
from .tools import EXTERNAL, LOCAL, PAGED

OFF_PATH = {"results": [], "note": "No results found."}
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
    def __init__(self, task, cassette, fault: str = "F0", local_client=None):
        super().__init__(task, cassette, local_client)
        self.faults = FaultState(task, fault)

    def _lookup(self, tool, args, variant):
        """Exact match first; for labels, a request for some sections can be served
        from a recording of the whole label for the same product."""
        hit = self.cassette.lookup(tool, args, variant=variant)
        if hit is not None or tool not in PAGED or not args.get("sections"):
            return hit
        whole = {k: v for k, v in args.items() if k != "sections"}
        hit = self.cassette.lookup(tool, whole, variant=variant)
        return select_sections(hit, args["sections"]) if hit is not None else None

    def _external(self, tool, args):
        base = {"tool": tool, "args": args, "external": True}
        short = self.faults.before_call(tool, args)
        if short is not None:
            result, is_error = short
            return {**base, "result": result, "is_error": is_error, "off_path": False}
        variant = self.faults.variant_for(tool, self.cassette)
        recorded = self._lookup(tool, args, variant)
        if recorded is None and variant != "current":
            recorded = self._lookup(tool, args, "current")
        if recorded is None:
            return {**base, "result": copy.deepcopy(OFF_PATH), "is_error": False, "off_path": True}
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
