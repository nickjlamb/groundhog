"""Part A: physician-vs-physician agreement on HealthBench's consensus criteria.

Reproduces the physician baseline in HealthBench Table 5 (Arora et al. 2025,
arXiv:2505.08775): each physician's grades are scored against the other
physicians' grades on the same meta-examples (never against their own),
macro F1 is computed per physician per criterion, and each theme reports the
average weighted by the number of meta-examples per physician. Our figures
come within 0.02 of the paper's on every theme; the paper does not give enough
detail to close the remaining gap.

Usage:  python scripts/agreement.py
Writes: results/agreement.json
"""

import itertools
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
META = HERE / "data" / "2025-05-07-06-14-12_oss_meta_eval.jsonl"

THEMES = {  # category prefix -> theme name used in the paper's Table 5
    "emergency_referrals": "Emergency referrals",
    "communication": "Expertise-tailored communication",
    "hedging": "Responding under uncertainty",
    "complex_responses": "Response depth",
    "health_data_tasks": "Health data tasks",
    "global_health": "Global health",
    "context_seeking": "Context seeking",
}
PAPER_TABLE_5 = {  # physician weighted average, GPT-4.1
    "Emergency referrals": (0.647, 0.662),
    "Expertise-tailored communication": (0.618, 0.610),
    "Responding under uncertainty": (0.640, 0.679),
    "Response depth": (0.569, 0.572),
    "Health data tasks": (0.730, 0.683),
    "Global health": (0.648, 0.706),
    "Context seeking": (0.646, 0.706),
}


def theme_of(category: str) -> str:
    name = category.removeprefix("cluster:")
    for prefix, theme in THEMES.items():
        if name.startswith(prefix):
            return theme
    raise ValueError(f"unknown category {category}")


def macro_f1(pairs: list[tuple[bool, bool]]) -> float:
    """pairs are (prediction, reference); mean of F1 for met and not-met."""
    scores = []
    for cls in (True, False):
        tp = sum(p == cls and r == cls for p, r in pairs)
        fp = sum(p == cls and r != cls for p, r in pairs)
        fn = sum(p != cls and r == cls for p, r in pairs)
        scores.append(2 * tp / (2 * tp + fp + fn) if tp else 0.0)
    return sum(scores) / 2


def main() -> None:
    # (criterion, physician) -> list of (this physician's grade, another physician's grade)
    pairs = defaultdict(list)
    # (criterion, physician) -> meta-examples graded (the paper's weight)
    counts = defaultdict(int)
    all_pairs = []
    n_rows = 0
    with META.open() as f:
        for line in f:
            row = json.loads(line)
            n_rows += 1
            crit = row["category"]
            ids, labels = row["anonymized_physician_ids"], row["binary_labels"]
            for i, (pid, lab) in enumerate(zip(ids, labels)):
                others = [l for j, (q, l) in enumerate(zip(ids, labels)) if j != i and q != pid]
                if not others:
                    continue
                counts[(crit, pid)] += 1
                pairs[(crit, pid)].extend((lab, o) for o in others)
            all_pairs.extend(itertools.combinations(labels, 2))

    by_theme = defaultdict(lambda: [0.0, 0, set()])
    for (crit, pid), n in counts.items():
        acc = by_theme[theme_of(crit)]
        acc[0] += macro_f1(pairs[(crit, pid)]) * n
        acc[1] += n
        acc[2].add(pid)

    results = {}
    for theme, (paper_phys, paper_gpt) in PAPER_TABLE_5.items():
        total, n, pids = by_theme[theme]
        results[theme] = {
            "physician_mf1": round(total / n, 3),
            "paper_physician_mf1": paper_phys,
            "paper_gpt41_mf1": paper_gpt,
            "physicians": len(pids),
        }

    # Chance-corrected agreement over all physician pairs, all criteria
    agree = sum(a == b for a, b in all_pairs) / len(all_pairs)
    p_met = sum(a + b for a, b in all_pairs) / (2 * len(all_pairs))
    p_chance = p_met ** 2 + (1 - p_met) ** 2
    kappa = (agree - p_chance) / (1 - p_chance)

    out = {
        "meta_examples": n_rows,
        "physician_pairs": len(all_pairs),
        "raw_agreement": round(agree, 3),
        "met_rate": round(p_met, 3),
        "cohens_kappa_pooled": round(kappa, 3),
        "themes": results,
    }
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "agreement.json").write_text(json.dumps(out, indent=2) + "\n")
    print(f"{n_rows} meta-examples, {len(all_pairs)} physician pairs")
    print(f"raw agreement {agree:.3f}, met rate {p_met:.3f}, pooled kappa {kappa:.3f}")
    print(f"{'theme':34} {'ours':>6} {'paper':>6} {'GPT-4.1':>8}")
    for theme, r in results.items():
        print(f"{theme:34} {r['physician_mf1']:6.3f} {r['paper_physician_mf1']:6.3f} {r['paper_gpt41_mf1']:8.3f}")


if __name__ == "__main__":
    main()
