"""Part C: run the frozen locators on physician-written ideal responses.

Expectation: an ideal response meets every positive criterion and none of the
negative ones. A locator "agrees" when its verdict matches that expectation.
Disagreements are then read by hand to decide whether the locator or the
expectation was wrong (see results/part_c_review.csv).

Usage:  python scripts/run_locators.py
Writes: results/part_c_runs.csv
"""

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))
from locators import LOCATORS, met  # noqa: E402


def main() -> None:
    labels = {int(r["row"]): r for r in csv.DictReader(open(HERE / "results" / "part_b_labels.csv"))}
    wanted = {labels[n]["criterion_id"].split("#")[0] for n in LOCATORS}
    ideal = {}
    with open(HERE / "data" / "2025-05-07-06-14-12_oss_eval.jsonl") as f:
        for line in f:
            ex = json.loads(line)
            if ex["prompt_id"] in wanted and ex.get("ideal_completions_data"):
                ideal[ex["prompt_id"]] = ex["ideal_completions_data"]["ideal_completion"]

    out = []
    for n, loc in sorted(LOCATORS.items()):
        lab = labels[n]
        pid = lab["criterion_id"].split("#")[0]
        if pid not in ideal:
            out.append({"row": n, "criterion_id": lab["criterion_id"], "sign": lab["sign"],
                        "met": "", "expected": "", "agrees": "no ideal response"})
            continue
        m = met(loc, ideal[pid])
        expected = lab["sign"] == "pos"
        out.append({"row": n, "criterion_id": lab["criterion_id"], "sign": lab["sign"],
                    "met": m, "expected": expected, "agrees": m == expected})

    with open(HERE / "results" / "part_c_runs.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    run = [o for o in out if o["agrees"] in (True, False)]
    for sign in ("pos", "neg"):
        s = [o for o in run if o["sign"] == sign]
        print(f"{sign}: {sum(o['agrees'] for o in s)}/{len(s)} agree with expectation")
    print(f"all: {sum(o['agrees'] for o in run)}/{len(run)}; disagreements: {[o['row'] for o in run if not o['agrees']]}")


if __name__ == "__main__":
    main()
