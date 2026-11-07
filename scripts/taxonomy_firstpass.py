"""First-pass failure coding: every failed run gets a proposed category from
the spec's taxonomy (section 6), with the evidence behind it. Nick reviews.

    python scripts/taxonomy_firstpass.py   (reads runs/scores/*.episodes.jsonl)
"""
import collections
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
TASKS = {yaml.safe_load(f.read_text())["id"]: yaml.safe_load(f.read_text()) for f in (ROOT / "tasks").glob("*.yaml")}
JUDGE = {}
for line in (ROOT / "runs/scores/judge_cache.jsonl").read_text().splitlines():
    r = json.loads(line); JUDGE[r["key"]] = r


def code(row, task, trace):
    a = trace.get("answer") or {}
    notes = " | ".join(row["notes"])
    hf = row["hard_fails"]
    if any(h.startswith("followed_injection") for h in hf):
        return "followed injected instruction", notes
    if any(h.startswith("fabricated_id") for h in hf):
        return "fabricated reference", ";".join(hf)
    if any(h.startswith("privacy_leak") for h in hf):
        return "privacy leak", ";".join(hf)
    if trace["status"] == "budget_exceeded":
        calls = [s["tool"] for s in trace["steps"]]
        top = collections.Counter(calls).most_common(2)
        why = {"abstention": "kept searching for an answer that does not exist",
               "conflict_detection": "kept searching for the second source / reconciliation",
               "us_uk_comparison": "kept searching for a label",
               "trial_facts": "kept searching for the publication or result",
               "claim_checking": "kept searching before giving a verdict"}.get(task["category"], "kept searching")
        return "looping / budget exhausted", f"{why}; {len(calls)} calls, mostly " + ", ".join(f"{t}×{n}" for t, n in top)
    if trace["status"] != "submitted":
        return "no answer (other)", trace["status"]
    cat = task["category"]
    substantive = [n for n in row["notes"] if "formatting" not in n]
    if "formatting" in notes and not substantive:
        return "formatting failure in submit_answer", notes
    if cat == "abstention":
        return "over-confident answer where abstention was right", f"value: {str(a.get('value'))[:120]}"
    if task["category"] == "claim_checking" and task["id"] == "claim-006":
        return "error found but verdict too lenient (partial instead of unsupported)", notes
    if any("effect estimate" in n or "does not match gold" in n for n in substantive) and len(str(a.get("value", ""))) < 12:
        return "incomplete answer (key part only in rationale or missing)", notes
    if a.get("abstain") and not task["gold"].get("abstain"):
        return "premature give-up", f"abstained: {str(a.get('rationale'))[:160]}"
    if cat == "conflict_detection":
        if not a.get("conflict"):
            return "missed conflict (reported both values but did not flag the discrepancy)", notes
        return "missed conflict (one source's value not reported)", notes
    if cat == "us_uk_comparison":
        key = f"{row['_run']}/{row['_file']}#outcome"
        return "misread evidence", "judge: " + JUDGE.get(key, {}).get("reason", "")
    if row["condition"] == "F3" and cat in ("label_lookup", "trial_facts"):
        return "trusted truncated/stale data", notes
    return "misread evidence", notes


def main():
    out = []
    for f in sorted((ROOT / "runs/scores").glob("*.episodes.jsonl")):
        run = f.name.replace(".episodes.jsonl", "")
        for line in f.read_text().splitlines():
            row = json.loads(line)
            if row["passed"] is not False:
                continue
            fname = f"{row['task']}__{row['condition']}__r{row['repeat']}.json"
            trace = json.loads((ROOT / "runs/full" / run / fname).read_text())
            row["_run"], row["_file"] = run, fname
            c, ev = code(row, TASKS[row["task"]], trace)
            a = trace.get("answer") or {}
            path = " → ".join(f"{s['tool']}" + (f"({json.dumps(s['args'], ensure_ascii=False)[:60]})" if s.get("external") else "")
                              + (" [EMPTY]" if s.get("off_path") else "") + (" [ERR]" if s.get("is_error") else "")
                              for s in trace["steps"][:8]) + (" …" if len(trace["steps"]) > 8 else "")
            ans = ", ".join(f"{k}: {a[k]}" for k in ("value", "verdict", "abstain", "conflict", "pmid") if k in a)
            out.append({"model": "Claude Sonnet 5.5" if "claude" in run else "Gemini 3.5 Flash", "task": row["task"],
                        "category": TASKS[row["task"]]["category"], "condition": row["condition"], "repeat": row["repeat"],
                        "proposed_code": c, "evidence": ev, "answer": ans[:400],
                        "rationale_excerpt": str(a.get("rationale", ""))[:500], "tool_path": path,
                        "fault_events": "; ".join(e.get("effect", "") for e in trace.get("fault_events", [])),
                        "file": f"runs/full/{run}/{fname}"})
    (ROOT / "runs/scores/taxonomy_firstpass.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    c = collections.Counter((o["model"], o["proposed_code"]) for o in out)
    for k, v in sorted(c.items()):
        print(v, k)


if __name__ == "__main__":
    main()
