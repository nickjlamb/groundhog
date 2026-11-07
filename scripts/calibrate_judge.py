"""Compare the judge with Nick's grading of review/judge_calibration.xlsx.

    python scripts/calibrate_judge.py [--model perplexity:openai/gpt-5.4]

Writes review/judge_calibration_results.json and prints agreement and Cohen's kappa.
"""

import argparse
import json
import sys
from pathlib import Path

import yaml
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.runner import load_env  # noqa: E402
from scoring.judge import JUDGE_MODEL, Judge  # noqa: E402


def kappa(pairs):
    n = len(pairs)
    po = sum(a == b for a, b in pairs) / n
    pa = sum(a for a, _ in pairs) / n
    pb = sum(b for _, b in pairs) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=JUDGE_MODEL)
    args = ap.parse_args()
    load_env()
    key = {k["id"]: k for k in json.loads((ROOT / "review/judge_calibration_key.json").read_text())}
    ws = load_workbook(ROOT / "review/judge_calibration.xlsx")["Grade these"]
    human = {r[0]: r[6] for r in ws.iter_rows(min_row=2, values_only=True) if r[0]}
    judge = Judge(args.model)
    rows = []
    for jid, k in sorted(key.items()):
        if human.get(jid) not in ("Yes", "No"):
            continue
        task = yaml.safe_load((ROOT / "tasks" / f"{k['task']}.yaml").read_text())
        trace = json.loads(Path(k["episode"]).read_text()) if Path(k["episode"]).is_absolute() else \
            json.loads((ROOT / k["episode"]).read_text())
        answer = trace.get("answer") or {}
        if k["kind"] == "comparison outcome":
            out = judge.comparison(task, answer)
        else:
            crit = next(c for c in task["rubric"] if c["id"] == k["criterion_id"])
            out = judge.criterion(task, crit, answer)
        rows.append({"id": jid, "kind": k["kind"], "task": k["task"], "human": human[jid] == "Yes",
                     "judge": out["verdict"], "reason": out["reason"]})
        print(f"{jid} {k['task']:12} human={human[jid]:3} judge={'Yes' if out['verdict'] else 'No' if out['verdict'] is not None else '??'}"
              + ("" if out["verdict"] == (human[jid] == "Yes") else "   <-- DISAGREE"), flush=True)
    pairs = [(r["human"], r["judge"]) for r in rows if r["judge"] is not None]
    agree = sum(a == b for a, b in pairs)
    print(f"\nagreement {agree}/{len(pairs)} = {agree / len(pairs):.0%}; Cohen's kappa {kappa(pairs):.2f}")
    for kind in sorted({r["kind"] for r in rows}):
        p = [(r["human"], r["judge"]) for r in rows if r["kind"] == kind and r["judge"] is not None]
        print(f"  {kind}: {sum(a == b for a, b in p)}/{len(p)}")
    (ROOT / "review/judge_calibration_results.json").write_text(
        json.dumps({"model": args.model, "agreement": agree / len(pairs), "kappa": kappa(pairs), "items": rows},
                   indent=1, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
