"""Model judge for the outcomes and rubric criteria that code cannot check.

The judge is a third model family (OpenAI GPT via Perplexity), so it is not
grading its own family's answers. It returns a yes/no verdict through a tool
call, which keeps the output structured. It is used only after
scripts/calibrate_judge.py has checked it against Nick's grading.
"""

import json

from harness.models import make_model

JUDGE_MODEL = "perplexity:openai/gpt-5.4"

SYSTEM = """You grade answers written by a medical-information assistant. A medical writer
has written the reference answer; treat it as correct. Judge the substance only:
ignore wording, length, formatting, and which field of the answer a fact appears
in. Do not give credit for facts the reference does not support, and do not
penalise extra correct detail. Record your verdict with the record_verdict tool."""

VERDICT_TOOL = {
    "name": "record_verdict",
    "description": "Record the grading decision.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["yes", "no"]},
            "reason": {"type": "string", "description": "One or two sentences."},
        },
        "required": ["verdict", "reason"],
    },
}


def answer_block(answer: dict) -> str:
    head = ", ".join(f"{k}: {answer[k]}" for k in ("value", "unit", "pmid", "verdict", "abstain", "conflict")
                     if k in answer and answer[k] not in ("", None))
    return (head + "\n\n" if head else "") + "Rationale: " + str(answer.get("rationale", ""))


def comparison_reference(task: dict) -> str:
    g = task["gold"]
    ref = (f"US: {g.get('us')}\nUK: {g.get('uk')}\nDo the labels differ materially: "
           f"{'yes' if g.get('differs') else 'no'}\n\n{str(g.get('detail', '')).strip()}")
    if g.get("accept_if"):
        ref += f"\n\nAccept if: {g['accept_if']}"
    return ref


def comparison_prompt(task: dict, answer: dict) -> str:
    return (f"QUESTION ASKED\n{task['prompt'].strip()}\n\nREFERENCE ANSWER\n{comparison_reference(task)}\n\n"
            f"ANSWER TO GRADE\n{answer_block(answer)}\n\n"
            "Is the answer correct for the US label, correct for the UK label, and right about whether "
            "the two labels differ materially? Answer yes only if all three are right.")


def criterion_prompt(task: dict, criterion: dict, answer: dict) -> str:
    gold = {k: v for k, v in task["gold"].items() if k != "identifiers"}
    if criterion["points"] < 0:
        ask = ("This criterion describes an ERROR. Answer yes if the answer makes this error, "
               "no if it does not.")
    else:
        ask = "Answer yes if the answer meets this criterion, no if it does not."
    return (f"QUESTION ASKED\n{task['prompt'].strip()}\n\nREFERENCE ANSWER\n"
            f"{json.dumps(gold, ensure_ascii=False, default=str)}\n\nANSWER TO GRADE\n{answer_block(answer)}\n\n"
            f"CRITERION\n{criterion['criterion']}\n\n{ask}")


class Judge:
    def __init__(self, model: str = JUDGE_MODEL):
        self.model_name = model
        self.model = make_model(model)

    def ask(self, prompt: str) -> dict:
        for _ in range(2):
            out = self.model.complete(SYSTEM, [{"role": "user", "content": prompt}], [VERDICT_TOOL])
            for c in out.get("tool_calls", []):
                if c["name"] == "record_verdict" and c["args"].get("verdict") in ("yes", "no"):
                    return {"verdict": c["args"]["verdict"] == "yes", "reason": c["args"].get("reason", ""),
                            "usage": out.get("usage", {})}
        return {"verdict": None, "reason": "judge gave no verdict", "usage": {}}

    def comparison(self, task, answer):
        return self.ask(comparison_prompt(task, answer))

    def criterion(self, task, criterion, answer):
        return self.ask(criterion_prompt(task, criterion, answer))
