"""Item analysis: which tasks separate the models and which sit at ceiling or floor.

    python scripts/item_analysis.py   (reads runs/scores/*.episodes.jsonl from the full run)

For each task, the pass rate per model over all its scored runs (clean + fault).
spread = best model's rate - worst model's rate. A task is
  ceiling        every model >= 0.9
  floor          every model <= 0.2
  discriminating spread >= 0.3
  weak           otherwise (some signal, little separation)
"""
import collections
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MODELS = {"anthropic_claude-sonnet-5-5": "Claude", "perplexity_google_gemini-3.1-pro-preview": "Gemini Pro",
          "perplexity_google_gemini-3.5-flash": "Gemini Flash"}
sys.path.insert(0, str(ROOT))
from harness.taskset import by_id  # noqa: E402
TASKS = by_id()


def main():
    rate = collections.defaultdict(dict)
    for run, name in MODELS.items():
        per = collections.defaultdict(list)
        for line in open(ROOT / "runs/scores" / f"{run}.episodes.jsonl"):
            r = json.loads(line)
            if r["passed"] is not None:
                per[r["task"]].append(r["passed"])
        for t, v in per.items():
            rate[t][name] = sum(v) / len(v)
    rows = []
    for t in sorted(rate):
        v = rate[t]
        spread = max(v.values()) - min(v.values())
        kind = ("ceiling" if min(v.values()) >= 0.9 else "floor" if max(v.values()) <= 0.2
                else "discriminating" if spread >= 0.3 else "weak")
        rows.append((t, TASKS[t]["category"], TASKS[t]["fault"], v, spread, kind))
    counts = collections.Counter(r[5] for r in rows)
    out = ["# Item analysis (Groundhog v1, three models)", "",
           f"Pass rate per task over all scored runs (clean + fault, 10 per model). "
           f"Ceiling: every model >= 0.9. Floor: every model <= 0.2. Discriminating: best minus worst >= 0.3.", "",
           "| Kind | Tasks |", "|---|---|"]
    for k in ("ceiling", "discriminating", "weak", "floor"):
        out.append(f"| {k} | {counts.get(k, 0)} |")
    out += ["", "## By category", "", "| Category | Tasks | Ceiling | Discriminating | Weak | Floor |", "|---|---|---|---|---|---|"]
    for cat in sorted({r[1] for r in rows}):
        c = collections.Counter(r[5] for r in rows if r[1] == cat)
        out.append(f"| {cat} | {sum(c.values())} | {c['ceiling']} | {c['discriminating']} | {c['weak']} | {c['floor']} |")
    out += ["", "## Tasks that are not at ceiling", "", "| Task | Category | Fault | Claude | Gemini Pro | Gemini Flash | Spread | Kind |",
            "|---|---|---|---|---|---|---|---|"]
    for t, cat, fault, v, spread, kind in sorted(rows, key=lambda r: (-r[4], r[0])):
        if kind == "ceiling":
            continue
        out.append(f"| {t} | {cat} | {fault} | {v.get('Claude', 0):.1f} | {v.get('Gemini Pro', 0):.1f} | "
                   f"{v.get('Gemini Flash', 0):.1f} | {spread:.1f} | {kind} |")
    out += ["", "Ceiling tasks: " + ", ".join(r[0] for r in rows if r[5] == "ceiling")]
    (ROOT / "analysis" / "item_analysis.md").write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
