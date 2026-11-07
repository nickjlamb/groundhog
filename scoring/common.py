"""Helpers shared by the scorers."""

import json
import re

_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}\b)")
_NUM = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")


def norm_text(s) -> str:
    s = str(s or "").replace("−", "-").replace("–", "-").replace("—", "-")
    return _THOUSANDS.sub("", s)


def numbers(s) -> list[str]:
    """Numbers in a string, with thousands separators removed ('7,064' -> '7064')."""
    return _NUM.findall(norm_text(s))


def seen_text(task: dict, trace: dict) -> str:
    """Everything the agent was shown: the prompt plus every tool result."""
    parts = [task.get("prompt", "")]
    for s in trace.get("steps", []):
        parts.append(json.dumps(s.get("result"), ensure_ascii=False))
    return norm_text(" ".join(parts))


def answer_text(answer: dict) -> str:
    return norm_text(" ".join(str(answer.get(k, "")) for k in ("value", "unit", "pmid", "verdict", "rationale")))


def external_calls(trace: dict) -> list[dict]:
    return [s for s in trace.get("steps", []) if s.get("external")]
