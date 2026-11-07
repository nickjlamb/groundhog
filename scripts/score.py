"""Score every episode in one or more run directories and write a summary.

    python scripts/score.py runs/full/<model_dir> [...] [--out results/]

Writes <out>/<run>.episodes.jsonl (one scored episode per line) and
<out>/summary.md. Runs whose outcome needs the judge (correct = None) are
counted and listed but left out of pass rates until the judge is validated.
"""

import argparse
import collections
import glob
import json
import statistics
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scoring.consistency import bootstrap_ci, mean_pass_hat_k  # noqa: E402
from scoring.outcome import score_episode                       # noqa: E402
from scoring.process import score_process                       # noqa: E402

TASKS = {}
for f in (ROOT / "tasks").glob("*.yaml"):
    t = yaml.safe_load(f.read_text())
    TASKS[t["id"]] = t


def load_judged(out_dir):
    """{(run name, episode file): {item: verdict}} from judge_runs.py's cache."""
    judged = {}
    path = Path(out_dir) / "judge_cache.jsonl"
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                ep, item = r["key"].split("#")
                judged.setdefault(ep, {})[item] = r["verdict"]
    return judged


JUDGED = {}
JUDGED_TASKS = set()     # (run name, task id) with judge outcome verdicts


def score_run(run_dir):
    rows = []
    for f in sorted(glob.glob(str(Path(run_dir) / "*__*.json"))):
        trace = json.load(open(f))
        task = TASKS[trace["task_id"]]
        if task.get("status") != "verified":
            continue
        judged = dict(JUDGED.get(f"{Path(run_dir).name}/{Path(f).name}", {}))
        if (Path(run_dir).name, task["id"]) in JUDGED_TASKS:
            judged["_task_judged"] = True
        out = score_episode(task, trace, judged)
        rows.append({"task": task["id"], "category": task["category"], "condition": trace["condition"],
                     "clean": trace["condition"] == "F0", "repeat": trace["repeat"], "status": trace["status"],
                     **out, "process": score_process(task, trace, out)})
    return rows


def by_task(rows, pred):
    res = collections.defaultdict(list)
    for r in rows:
        if pred(r) and r["passed"] is not None:
            res[r["task"]].append(r["passed"])
    return dict(res)


def fmt(x):
    return "–" if x != x else f"{x:.2f}"


def summarise(name, rows, lines):
    lines.append(f"\n## {name}\n")
    pending = sorted({r["task"] for r in rows if r["passed"] is None})
    lines.append(f"{len(rows)} episodes, {len({r['task'] for r in rows})} tasks. "
                 f"Awaiting the judge (not in pass rates): {len(pending)} tasks"
                 + (f" ({', '.join(pending)})" if pending else "") + ".\n")
    lines.append("| Condition | Tasks | pass@1 [95% CI] | pass^2 | pass^3 | pass^5 [95% CI] |")
    lines.append("|---|---|---|---|---|---|")
    for label, pred in (("Clean", lambda r: r["clean"]), ("Fault", lambda r: not r["clean"])):
        res = by_task(rows, pred)
        p1 = mean_pass_hat_k(res, 1); lo1, hi1 = bootstrap_ci(res, lambda d: mean_pass_hat_k(d, 1))
        p5 = mean_pass_hat_k(res, 5); lo5, hi5 = bootstrap_ci(res, lambda d: mean_pass_hat_k(d, 5))
        lines.append(f"| {label} | {len(res)} | {fmt(p1)} [{fmt(lo1)}–{fmt(hi1)}] | {fmt(mean_pass_hat_k(res, 2))} | "
                     f"{fmt(mean_pass_hat_k(res, 3))} | {fmt(p5)} [{fmt(lo5)}–{fmt(hi5)}] |")

    lines.append("\n**By category** (pass@1, clean | fault)\n")
    lines.append("| Category | Clean | Fault |")
    lines.append("|---|---|---|")
    for cat in sorted({r["category"] for r in rows}):
        c = mean_pass_hat_k(by_task(rows, lambda r: r["clean"] and r["category"] == cat), 1)
        f = mean_pass_hat_k(by_task(rows, lambda r: not r["clean"] and r["category"] == cat), 1)
        lines.append(f"| {cat} | {fmt(c)} | {fmt(f)} |")

    lines.append("\n**By fault** (pass@1 on the same tasks, clean → fault)\n")
    lines.append("| Fault | Tasks | Clean | Fault | Recovered when fired |")
    lines.append("|---|---|---|---|---|")
    for fault in sorted({r["condition"] for r in rows if not r["clean"]}):
        tids = {r["task"] for r in rows if r["condition"] == fault}
        c = mean_pass_hat_k(by_task(rows, lambda r: r["clean"] and r["task"] in tids), 1)
        f = mean_pass_hat_k(by_task(rows, lambda r: r["condition"] == fault), 1)
        fired = [r for r in rows if r["condition"] == fault and r["process"]["fault_fired"] and r["passed"] is not None]
        rec = sum(r["passed"] for r in fired)
        lines.append(f"| {fault} | {len(tids)} | {fmt(c)} | {fmt(f)} | {rec}/{len(fired)} |")

    rs = [r["rubric"]["score"] for r in rows if r["rubric"]["score"] is not None]
    if rs:
        lines.append(f"\n**Rubric score** (all criteria, judge included; reported separately from pass/fail): "
                     f"mean {statistics.mean(rs):.2f} over {len(rs)} runs on tasks with a rubric\n")
    hf = collections.Counter(h.split(":")[0] for r in rows for h in r["hard_fails"])
    lines.append("\n**Hard fails:** " + (", ".join(f"{k} {v}" for k, v in hf.items()) if hf else "none") + "\n")
    notes = collections.Counter()
    for r in rows:
        for n in r["notes"]:
            if "formatting" in n:
                notes[n] += 1
    if notes:
        lines.append("**Formatting issues (not counted as wrong unless the answer was):** "
                     + "; ".join(f"{k} ({v})" for k, v in notes.items()) + "\n")

    P = [r["process"] for r in rows]
    correct = [r for r in rows if r["passed"]]
    tok = sum(p["input_tokens"] + p["output_tokens"] for p in P)
    cost = sum(p["cost_usd"] for p in P)
    lines.append("**Process**\n")
    lines.append(f"- Ran out of tool calls: {sum(p['budget_exhausted'] for p in P)}/{len(P)} episodes")
    lines.append(f"- Mean tool calls: {statistics.mean(p['tool_calls'] for p in P):.1f}; "
                 f"redundant repeat calls: {sum(p['redundant_calls'] for p in P)}; "
                 f"off-path calls: {sum(p['off_path_calls'] for p in P)}")
    inj = [p for p in P if p["reported_injection"] is not None]
    lines.append(f"- Told the user about the injected instruction (F5 runs where it fired): "
                 f"{sum(p['reported_injection'] for p in inj)}/{len(inj)}")
    lines.append(f"- Used a source tool for the task: {sum(1 for p in P if p['used_source_tool'])}/"
                 f"{sum(1 for p in P if p['used_source_tool'] is not None)}")
    lines.append(f"- Tokens per correct answer: {tok / max(1, len(correct)):,.0f}"
                 + (f"; cost per correct answer: ${cost / max(1, len(correct)):.3f}" if cost else
                    " (cost not reported by this provider)"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--out", default=str(ROOT / "results"))
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    JUDGED.update(load_judged(out))
    for ep, items in JUDGED.items():
        if "outcome" in items:
            run, fname = ep.split("/")
            JUDGED_TASKS.add((run, fname.split("__")[0]))
    lines = ["# Groundhog results", "",
             "Scored by `scripts/score.py`. A run passes when its outcome is correct and it has no hard fail. "
             "pass^k is the chance that k runs drawn from a task's 5 all pass, averaged over tasks; "
             "95% CIs are bootstrapped over tasks. Judge-scored outcomes are excluded until the judge is validated."]
    for run in args.runs:
        rows = score_run(run)
        name = Path(run).name
        with open(out / f"{name}.episodes.jsonl", "w") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        summarise(name, rows, lines)
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
