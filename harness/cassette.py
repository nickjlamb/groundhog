"""Frozen tool responses, one cassette per task (design spec section 2).

Entries are keyed by tool name plus canonicalised arguments, so trivial
differences (key order, case, extra whitespace, paging arguments on label
tools) still hit the recording. An entry may carry a variant: "current" for
the live response, "stale" for a superseded version used by fault F4.
"""

import datetime
import json
from pathlib import Path

from .tools import PAGED

ROOT = Path(__file__).resolve().parent.parent / "cassettes"
PAGING_ARGS = ("max_chars", "offset")


def _norm(value):
    if isinstance(value, str):
        return " ".join(value.lower().split())
    if isinstance(value, list):
        return [_norm(v) for v in value]
    if isinstance(value, dict):
        return {k: _norm(v) for k, v in sorted(value.items()) if v is not None}
    return value


def canonical_key(tool: str, args: dict) -> str:
    args = dict(args or {})
    if tool in PAGED:
        for k in PAGING_ARGS:
            args.pop(k, None)
    return tool + " " + json.dumps(_norm(args), sort_keys=True, ensure_ascii=False)


class Cassette:
    def __init__(self, task_id: str, root: Path = ROOT):
        self.task_id = task_id
        self.path = Path(root) / f"{task_id}.json"
        if self.path.exists():
            self.data = json.loads(self.path.read_text())
        else:
            self.data = {"task_id": task_id, "entries": []}

    def lookup(self, tool: str, args: dict, variant: str = "current"):
        key = canonical_key(tool, args)
        for e in self.data["entries"]:
            if e["key"] == key and e.get("variant", "current") == variant:
                return e["response"]
        return None

    def has_variant(self, variant: str, tool: str | None = None) -> bool:
        return any(e.get("variant", "current") == variant and (tool is None or e["tool"] == tool)
                   for e in self.data["entries"])

    def add(self, tool: str, args: dict, response, recorded_by: str, variant: str = "current"):
        key = canonical_key(tool, args)
        self.data["entries"] = [e for e in self.data["entries"]
                                if not (e["key"] == key and e.get("variant", "current") == variant)]
        self.data["entries"].append({
            "key": key, "tool": tool, "args": args, "variant": variant, "response": response,
            "recorded_by": recorded_by,
            "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        })

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data["entries"].sort(key=lambda e: (e["key"], e.get("variant", "current")))
        self.path.write_text(json.dumps(self.data, indent=1, ensure_ascii=False) + "\n")
