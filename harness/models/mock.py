"""Deterministic stand-ins for models, for tests and harness smoke runs."""

import itertools
import re


class ScriptedModel:
    """Plays back a fixed list of turns. Each turn is a list of (tool, args) pairs,
    or a string for a text-only turn."""

    name = "mock:scripted"

    def __init__(self, turns):
        self.turns = list(turns)
        self.i = 0
        self._ids = itertools.count(1)

    def complete(self, system, messages, tools):
        turn = self.turns[self.i] if self.i < len(self.turns) else "done"
        self.i += 1
        if isinstance(turn, str):
            return {"text": turn, "tool_calls": [], "usage": {}}
        return {"text": "", "tool_calls": [{"id": f"call_{next(self._ids)}", "name": n, "args": a} for n, a in turn],
                "usage": {"input_tokens": 10, "output_tokens": 5}}


# Gold paths that cannot be read off a task's source block.
GOLD_PATH_OVERRIDES = {
    "cmp-006": [("compare_labels", {"drug": "apixaban", "us_drug": "Eliquis", "uk_drug": "Eliquis"}),
                ("get_uspi", {"drug": "Eliquis"}), ("get_smpc", {"drug": "Eliquis 5 mg film-coated tablets"})],
    "cmp-007": [("get_uspi", {"drug": "Enhertu"}), ("get_smpc", {"drug": "Enhertu 100 mg powder for concentrate"})],
    "trial-004": [("get_trial", {"nctId": "NCT03529110"}), ("get_abstract", {"pmid": "35320644"})],   # no PMC full text for this article
    "conflict-001": [("get_abstract", {"pmid": "19717844"}), ("get_smpc", {"drug": "Pradaxa 150 mg hard capsules"}),
                     ("get_abstract", {"pmid": "21047252"})],
    "abstain-005": [("search_pubmed", {"query": "empagliflozin takotsubo randomized"}),
                    ("search_pubmed", {"query": '(SGLT2 OR empagliflozin OR dapagliflozin) AND (takotsubo OR "stress cardiomyopathy")'})],
}

LABEL_TOOLS = ("get_smpc", "get_uspi")
CITATION_STYLES = ("apa", "vancouver", "harvard", "bibtex")   # record every style an agent may pick


def _call_for(tool, spec, src):
    """Args for one source tool. Labels are fetched whole so any section request
    can be replayed from the recording."""
    spec = spec if isinstance(spec, dict) else {}
    if tool in LABEL_TOOLS:
        drug = spec.get("drug") or (src.get("query") if isinstance(src.get("query"), str) else None) or src.get("product", "")
        return {"drug": re.sub(r"\s*\(.*?\)", "", drug).strip()}
    if tool == "compare_labels":
        return {k: v for k, v in spec.items() if k in ("drug", "us_drug", "uk_drug", "sections")}
    if tool == "format_citation" and src.get("pmid"):
        return [{"pmid": str(src["pmid"]), "style": s} for s in CITATION_STYLES] + [{"pmid": str(src["pmid"])}]
    if tool == "get_abstract" and src.get("pmid"):
        return {"pmid": str(src["pmid"])}
    if tool == "get_full_text" and (src.get("pmcid") or src.get("pmid")):
        return {"pmcid": src["pmcid"]} if src.get("pmcid") else {"pmid": str(src["pmid"])}
    if tool == "get_trial" and src.get("nct_id"):
        return {"nctId": src["nct_id"]}
    return None


def _expand(tool, args):
    if not args:
        return []
    return [(tool, a) for a in (args if isinstance(args, list) else [args])]


def gold_calls(task):
    """The tool calls on a task's gold evidence path, as (tool, args) pairs."""
    if task.get("id") in GOLD_PATH_OVERRIDES:
        return list(GOLD_PATH_OVERRIDES[task["id"]])
    src = task.get("source", {}) or {}
    query = src.get("query")
    calls = []
    if isinstance(query, dict) and all(isinstance(v, dict) and "tool" in v for v in query.values()):
        for spec in query.values():
            calls += _expand(spec["tool"], _call_for(spec["tool"], spec, src))
        return calls
    for tool in [x.strip() for x in str(src.get("tool", "")).split(";") if x.strip()]:
        calls += _expand(tool, _call_for(tool, query, src))
    return calls


class SubmitGoldModel:
    """Makes the calls on the task's gold evidence path, then submits the gold
    answer. Exercises the loop end to end; says nothing about any model."""

    name = "mock:submit-gold"

    def __init__(self):
        self._ids = itertools.count(1)
        self.task = None

    def bind(self, task):
        self.task, self.step = task, 0

    def _call(self, name, args):
        return {"id": f"call_{next(self._ids)}", "name": name, "args": args}

    def complete(self, system, messages, tools):
        t = self.task
        self.step += 1
        if self.step == 1:
            calls = gold_calls(t)
            if calls:
                return {"text": "", "tool_calls": [self._call(n, a) for n, a in calls], "usage": {}}
        gold = t.get("gold", {})
        answer = {"rationale": "mock: gold answer", **{k: v for k, v in gold.items()
                                                      if k in ("value", "unit", "pmid", "verdict", "abstain", "conflict")}}
        return {"text": "", "tool_calls": [self._call("submit_answer", answer)], "usage": {}}
