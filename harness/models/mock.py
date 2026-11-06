"""Deterministic stand-ins for models, for tests and harness smoke runs."""

import itertools


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


class SubmitGoldModel:
    """Calls the task's source tool once (when the task names one), then submits
    the gold answer. Exercises the loop end to end; says nothing about any model."""

    name = "mock:submit-gold"

    def __init__(self):
        self._ids = itertools.count(1)
        self.task = None

    def bind(self, task):
        self.task, self.step = task, 0

    def complete(self, system, messages, tools):
        t = self.task
        self.step += 1
        if self.step == 1:
            src = t.get("source", {})
            tool = str(src.get("tool", "")).split(";")[0].strip()
            args = {}
            if tool in ("get_smpc", "get_uspi"):
                args = {"drug": src.get("query") or src.get("product", "")}
            elif tool in ("get_abstract", "format_citation") and src.get("pmid"):
                args = {"pmid": str(src["pmid"])}
            elif tool == "get_trial" and src.get("nct_id"):
                args = {"nctId": src["nct_id"]}
            if args:
                return {"text": "", "tool_calls": [{"id": f"call_{next(self._ids)}", "name": tool, "args": args}], "usage": {}}
        gold = t.get("gold", {})
        answer = {"rationale": "mock: gold answer", **{k: v for k, v in gold.items()
                                                      if k in ("value", "unit", "pmid", "verdict", "abstain", "conflict")}}
        return {"text": "", "tool_calls": [{"id": f"call_{next(self._ids)}", "name": "submit_answer", "args": answer}], "usage": {}}
