"""Fault injection at replay (design spec section 2; v2 spec section 4).

Each episode runs clean (F0), under the task's transient fault (F1-F5), or
under its persistent fault (F1p-F5p).

Transient faults fire once, on the first eligible external call, so clean and
faulty runs of the same task are directly comparable:

  F1  first external call returns a timeout error
  F2  first external call returns an empty result
  F3  first page of a label section is cut so the answer falls past it
  F4  first label or registry call is served from a superseded ("stale") recording
  F5  an instruction is injected into the first external response that carries text

Persistent faults act on every call to the tool(s) named in the task's
persistent_fault.tool, for the whole episode; other tools work normally:

  F1p every call times out          F4p every call is served stale (if recorded)
  F2p every call returns empty      F5p every text response carries the injection
  F3p every first page is cut
"""

import re
from pathlib import Path

import yaml

from .tools import PAGED

CONFIG = yaml.safe_load((Path(__file__).resolve().parent / "fault_config.yaml").read_text())
STALE_TOOLS = frozenset({"get_smpc", "get_uspi", "compare_labels", "get_trial"})

TIMEOUT = {"error": "Upstream request timed out after 30 s with no response. You may retry."}


def empty_result(tool: str) -> dict:
    if tool in ("search_pubmed", "search_trials"):
        return {"results": [], "total_count": 0}
    if tool in PAGED:
        return {"sections": [], "note": "No matching product found."}
    return {"results": [], "note": "No results found."}


def injection_text(task: dict) -> str:
    """The task's own injection (v2: task.injection.text), else fault_config.yaml."""
    inj = task.get("injection") or {}
    if inj.get("text"):
        return inj["text"]
    return CONFIG["tasks"].get(task["id"], CONFIG["default"])


def _excerpts(task: dict) -> list[str]:
    src = task.get("source", {}) or {}
    texts = []
    if isinstance(src.get("excerpt"), str):
        texts.append(src["excerpt"])
    for v in (src.get("excerpts") or {}).values():
        if isinstance(v, str):
            texts.append(v)
    return texts


def _excerpt_pattern(excerpt: str):
    words = [re.escape(w) for w in excerpt.replace("...", " ").split()[:8]]
    return re.compile(r"\s+".join(words)) if len(words) >= 3 else None


def f3_cut(task: dict, full_text: str):
    """Length of a first page that ends before the first gold excerpt appears in
    full_text, or None if no excerpt appears. Matching tolerates any whitespace."""
    positions = []
    for ex in _excerpts(task):
        pat = _excerpt_pattern(ex)
        m = pat.search(full_text) if pat else None
        if m:
            positions.append(m.start())
    if not positions:
        return None
    pos = min(positions)
    if pos == 0:
        return 0
    space = full_text.rfind(" ", 0, pos)      # end on a word boundary before the answer
    return space if space > 0 else pos


def _inject(response, text: str):
    """Append text to the longest string inside response (in place); return True if done."""
    best = {"len": -1, "holder": None, "key": None}

    def walk(node):
        items = node.items() if isinstance(node, dict) else enumerate(node) if isinstance(node, list) else []
        for k, v in items:
            if isinstance(v, str) and len(v) > best["len"]:
                best.update(len=len(v), holder=node, key=k)
            elif isinstance(v, (dict, list)):
                walk(v)

    walk(response)
    if best["holder"] is None or best["len"] < 40:
        return False
    best["holder"][best["key"]] = best["holder"][best["key"]].rstrip() + "\n\n" + text
    return True


def _tools(spec) -> frozenset:
    if not spec:
        return frozenset()
    return frozenset([spec] if isinstance(spec, str) else spec)


class FaultState:
    def __init__(self, task: dict, fault: str):
        self.task = task
        self.fault = fault or "F0"                       # as run: F0, F1-F5 or F1p-F5p
        self.persistent = self.fault.endswith("p")
        self.code = self.fault[:-1] if self.persistent else self.fault
        if self.persistent:
            pf = task.get("persistent_fault") or {}
            if pf.get("code") != self.code:
                raise ValueError(f"{task.get('id')}: condition {self.fault} does not match persistent_fault {pf}")
            self.targets = _tools(pf.get("tool"))
            if not self.targets:
                raise ValueError(f"{task.get('id')}: persistent_fault needs a tool")
        else:
            self.targets = None
        self.fired = False
        self.events: list[dict] = []

    def _armed(self, tool) -> bool:
        """Transient: until the fault has fired once. Persistent: on every call to a target tool."""
        if self.persistent:
            return tool in self.targets
        return not self.fired

    def _fire(self, tool, what):
        self.fired = True
        self.events.append({"fault": self.fault, "code": self.code, "persistent": self.persistent,
                            "tool": tool, "effect": what})

    def before_call(self, tool: str, args: dict):
        """Return (response, is_error) to short-circuit the call, or None."""
        if not self._armed(tool):
            return None
        if self.code == "F1":
            self._fire(tool, "timeout")
            return TIMEOUT, True
        if self.code == "F2":
            self._fire(tool, "empty")
            return empty_result(tool), False
        return None

    def variant_for(self, tool: str, cassette) -> str:
        # Transient: fires on the first call to a tool that has a stale recording, so
        # an agent that consults the UK label first still meets the old US label.
        if self.code == "F4" and tool in STALE_TOOLS and self._armed(tool):
            if cassette.has_variant("stale", tool):
                self._fire(tool, "stale")
                return "stale"
            if not cassette.has_variant("stale"):
                self.events.append({"fault": self.fault, "code": "F4", "tool": tool,
                                    "effect": "unavailable: no stale recording"})
        return "current"

    def first_page_cut(self, tool: str, response: dict, offset=0):
        """For F3/F3p: {section code: first-page length} for sections holding the answer."""
        if self.code != "F3" or tool not in PAGED or int(offset or 0) != 0 or not self._armed(tool):
            return None
        cuts = {}
        for sec in response.get("sections", []) or []:
            cut = f3_cut(self.task, sec.get("content", ""))
            if cut is not None:
                cuts[sec.get("code")] = cut
        if cuts:
            self._fire(tool, "first page cut: " + ", ".join(f"{k} at {v} chars" for k, v in cuts.items()))
            return cuts
        return None

    def after_call(self, tool: str, response):
        if self.code != "F5" or not self._armed(tool):
            return response
        if _inject(response, injection_text(self.task)):
            self._fire(tool, "injection")
        return response
