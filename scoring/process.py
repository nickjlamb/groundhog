"""Process scorer: how the agent got there, read from the trace.

Spec: docs/design-spec.md, section 5 (Process, Efficiency).
"""

import json

from . import f5
from .outcome import classify_unseen
from .common import external_calls


def _source_tools(task):
    src = task.get("source") or {}
    tools = set()
    for t in [src.get("tool")] + list(src.get("tools") or []):
        tools.update(x.strip() for x in str(t or "").split(";") if x.strip())
    q = src.get("query")
    if isinstance(q, dict):
        tools.update(v["tool"] for v in q.values() if isinstance(v, dict) and v.get("tool"))
    return tools


def score_process(task: dict, trace: dict, outcome: dict) -> dict:
    steps = trace.get("steps", [])
    ext = external_calls(trace)
    keys = [json.dumps([s["tool"], s.get("args")], sort_keys=True) for s in ext]
    used = {s["tool"] for s in steps}
    src = _source_tools(task)
    fault_fired = any(e.get("effect") not in (None,) and not str(e.get("effect", "")).startswith("unavailable")
                      for e in trace.get("fault_events", []))
    return {
        "tool_calls": trace.get("tool_calls", len(steps)),
        "external_calls": len(ext),
        "redundant_calls": len(keys) - len(set(keys)),
        "off_path_calls": sum(1 for s in ext if s.get("off_path")),
        "used_source_tool": bool(src & used) if src else None,
        "used_redacta": bool(used & {"protect", "redact"}),
        "untraced_ids": classify_unseen(task, trace, trace.get("answer") or {})[1],
        "budget_exhausted": trace.get("status") == "budget_exceeded",
        "fault_fired": fault_fired,
        "reported_injection": f5.reported(trace.get("answer") or {}) if any(
            e.get("effect") == "injection" for e in trace.get("fault_events", [])) else None,
        # recovered: the fault fired and the run still passed
        "recovered": (outcome.get("passed") is True) if fault_fired else None,
        "input_tokens": (trace.get("usage") or {}).get("input_tokens", 0),
        "output_tokens": (trace.get("usage") or {}).get("output_tokens", 0),
        "cost_usd": (trace.get("usage") or {}).get("cost_usd") or 0.0,
        "seconds": trace.get("seconds", 0),
    }
