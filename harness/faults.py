"""Fault injection at replay (design spec section 2, faults F0-F5).

Each episode runs clean (F0) or under the task's single assigned fault.
Faults act on the first eligible external call, so clean and faulty runs of
the same task are directly comparable.

  F1  first external call returns a timeout error
  F2  first external call returns an empty result
  F3  first page of a label section is cut so the answer falls past it
  F4  first label or registry call is served from a superseded ("stale") recording
  F5  an instruction is injected into the first external response that carries text
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


class FaultState:
    def __init__(self, task: dict, fault: str):
        self.task = task
        self.fault = fault or "F0"
        self.fired = False
        self.events: list[dict] = []

    def _fire(self, tool, what):
        self.fired = True
        self.events.append({"fault": self.fault, "tool": tool, "effect": what})

    def before_call(self, tool: str, args: dict):
        """Return (response, is_error) to short-circuit the call, or None."""
        if self.fired:
            return None
        if self.fault == "F1":
            self._fire(tool, "timeout")
            return TIMEOUT, True
        if self.fault == "F2":
            self._fire(tool, "empty")
            return empty_result(tool), False
        return None

    def variant_for(self, tool: str, cassette) -> str:
        if self.fault == "F4" and not self.fired and tool in STALE_TOOLS:
            if cassette.has_variant("stale"):
                self._fire(tool, "stale")
                return "stale"
            self.events.append({"fault": "F4", "tool": tool, "effect": "unavailable: no stale recording"})
        return "current"

    def first_page_cut(self, tool: str, response: dict, offset=0):
        """For F3: {section code: first-page length} for sections holding the answer."""
        if self.fault != "F3" or self.fired or tool not in PAGED or int(offset or 0) != 0:
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
        if self.fault != "F5" or self.fired:
            return response
        text = CONFIG["tasks"].get(self.task["id"], CONFIG["default"])
        if _inject(response, text):
            self._fire(tool, "injection")
        return response
