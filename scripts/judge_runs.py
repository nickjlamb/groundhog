"""Run the calibrated judge over full-run traces. Resumable: verdicts are cached
in <out>/judge_cache.jsonl and only missing items are judged.

    python scripts/judge_runs.py runs/full/<model> [...] [--out runs/scores]

Judges (1) the outcome of every comparison-task run and (2) every judge-type
rubric criterion of every submitted run. Runs without an answer are not judged.
"""

import argparse
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.runner import load_env  # noqa: E402
from scoring.judge import Judge      # noqa: E402
from harness.taskset import by_id, task_for_condition  # noqa: E402

TASKS = by_id()        # includes held-out tasks when GROUNDHOG_PRIVATE is set


def item_key(episode, item):
    return f"{Path(episode).parent.name}/{Path(episode).name}#{item}"


def load_cache(path):
    cache = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                cache[r["key"]] = r
    return cache


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--out", default=str(ROOT / "runs" / "scores"))
    args = ap.parse_args()
    load_env()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    cache_path = out / "judge_cache.jsonl"
    cache = load_cache(cache_path)
    todo = []
    for run in args.runs:
        for f in sorted(glob.glob(str(Path(run) / "*__*.json"))):
            trace = json.load(open(f))
            if trace.get("status") != "submitted":
                continue
            task = task_for_condition(TASKS[trace["task_id"]], trace.get("condition", "F0"))
            if task.get("answer_type") == "comparison":
                todo.append((f, "outcome", task, None, trace["answer"] or {}))
            for c in task.get("rubric") or []:
                if c.get("check") == "judge":
                    todo.append((f, c["id"], task, c, trace["answer"] or {}))
    todo = [t for t in todo if item_key(t[0], t[1]) not in cache]
    print(f"{len(todo)} items to judge ({len(cache)} cached)", flush=True)
    judge = Judge()
    with open(cache_path, "a") as fh:
        for i, (f, item, task, crit, answer) in enumerate(todo, 1):
            res = judge.comparison(task, answer) if crit is None else judge.criterion(task, crit, answer)
            rec = {"key": item_key(f, item), "verdict": res["verdict"], "reason": res["reason"],
                   "judge": judge.model_name, "cost_usd": (res.get("usage") or {}).get("cost_usd", 0)}
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n"); fh.flush()
            if i % 25 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)}", flush=True)
    print("JUDGING DONE")


if __name__ == "__main__":
    main()
