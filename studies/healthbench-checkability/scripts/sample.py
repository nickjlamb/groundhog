"""Part B: draw a stratified sample of example-specific rubric criteria.

Strata: the five HealthBench axes x positive/negative points, 30 per stratum
(300 in all), drawn with a fixed seed. Each criterion is identified by
prompt_id plus its index in that conversation's rubric list, so labels can be
published without republishing HealthBench text.

Usage:  python scripts/sample.py
Writes: results/sample.csv (IDs only, committed)
        data/sample_with_text.csv (with criterion text, git-ignored)
"""

import csv
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
EVAL = HERE / "data" / "2025-05-07-06-14-12_oss_eval.jsonl"
SEED = 20261105
PER_STRATUM = 30
AXES = ["accuracy", "completeness", "context_awareness", "communication_quality", "instruction_following"]


def main() -> None:
    strata = defaultdict(list)
    with EVAL.open() as f:
        for line in f:
            ex = json.loads(line)
            for i, r in enumerate(ex["rubrics"]):
                if "level:example" not in r["tags"]:
                    continue
                axis = next(t.split(":", 1)[1] for t in r["tags"] if t.startswith("axis:"))
                sign = "pos" if r["points"] > 0 else "neg"
                strata[(axis, sign)].append({
                    "criterion_id": f"{ex['prompt_id']}#{i}",
                    "prompt_id": ex["prompt_id"],
                    "index": i,
                    "axis": axis,
                    "sign": sign,
                    "points": r["points"],
                    "has_ideal": bool(ex.get("ideal_completions_data")),
                    "criterion": r["criterion"],
                })

    rng = random.Random(SEED)
    sample = []
    for axis in AXES:
        for sign in ("pos", "neg"):
            pool = strata[(axis, sign)]
            sample.extend(rng.sample(pool, PER_STRATUM))
            print(f"{axis:22} {sign}: pool {len(pool):6}, sampled {PER_STRATUM}")

    id_fields = ["criterion_id", "prompt_id", "index", "axis", "sign", "points", "has_ideal"]
    with (HERE / "results" / "sample.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=id_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(sample)
    with (HERE / "data" / "sample_with_text.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=id_fields + ["criterion"])
        w.writeheader()
        w.writerows(sample)
    print(f"{len(sample)} criteria; with an ideal response: {sum(s['has_ideal'] for s in sample)}")


if __name__ == "__main__":
    main()
