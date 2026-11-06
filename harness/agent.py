"""One episode: a model works one task through the gateway until submit_answer
or the tool budget runs out (design spec section 4).

Messages use a neutral format that model adapters translate:
  {"role": "user", "content": str}
  {"role": "assistant", "text": str, "tool_calls": [{"id", "name", "args"}]}
  {"role": "tool", "tool_call_id": str, "name": str, "content": str, "is_error": bool}
"""

import json
import time
from pathlib import Path

from .tools import load_tools

MAX_TOOL_CALLS = 15
SYSTEM_PROMPT = (Path(__file__).resolve().parent / "prompts" / "system.md").read_text()
NUDGE = "Please give your final answer by calling submit_answer."


def run_episode(task: dict, model, gateway, max_tool_calls: int = MAX_TOOL_CALLS,
                max_turns: int = 40, system: str = SYSTEM_PROMPT) -> dict:
    tools = load_tools()
    messages = [{"role": "user", "content": task["prompt"]}]
    steps, usage = [], {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
    answer, status, calls, nudged = None, None, 0, False
    t0 = time.monotonic()

    for _turn in range(max_turns):
        reply = model.complete(system=system, messages=messages, tools=tools)
        for k in usage:
            usage[k] += type(usage[k])(reply.get("usage", {}).get(k, 0) or 0)
        tool_calls = reply.get("tool_calls") or []
        messages.append({"role": "assistant", "text": reply.get("text", ""), "tool_calls": tool_calls})
        if not tool_calls:
            if nudged:
                status = "no_submit"
                break
            nudged = True
            messages.append({"role": "user", "content": NUDGE})
            continue
        for tc in tool_calls:
            if tc["name"] == "submit_answer":
                answer, status = tc.get("args", {}), "submitted"
                break
            calls += 1
            if calls > max_tool_calls:
                status = "budget_exceeded"
                break
            step = gateway.call(tc["name"], tc.get("args", {}) or {})
            step["call_index"] = calls
            steps.append(step)
            messages.append({"role": "tool", "tool_call_id": tc["id"], "name": tc["name"],
                             "content": json.dumps(step["result"], ensure_ascii=False),
                             "is_error": step["is_error"]})
        if status:
            break
    else:
        status = "turn_limit"

    faults = getattr(gateway, "faults", None)
    return {
        "task_id": task["id"],
        "fault": faults.fault if faults else "F0",
        "fault_events": faults.events if faults else [],
        "model": getattr(model, "name", "unknown"),
        "status": status,
        "answer": answer,
        "tool_calls": calls,
        "steps": steps,
        "usage": usage,
        "seconds": round(time.monotonic() - t0, 2),
        "messages": messages,
    }
