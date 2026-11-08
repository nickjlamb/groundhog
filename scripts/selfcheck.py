"""Gold answers must pass their own scorers.

    python scripts/selfcheck.py runs/scores/<run>.episodes.jsonl

Reads the scored episodes of a mock:submit-gold run and fails if any episode
that was scored (not awaiting the judge) did not pass, or has a hard fail.
A failure means a scorer and a gold answer disagree: fix one of them.
"""
import json
import sys

rows = [json.loads(line) for path in sys.argv[1:] for line in open(path)]
scored = [r for r in rows if r["passed"] is not None]
bad = [r for r in scored if not r["passed"] or r["hard_fails"]]
for r in bad:
    print(f"FAIL {r['task']} {r['condition']}: {r['hard_fails'] or r['notes']}")
print(f"selfcheck: {len(scored) - len(bad)}/{len(scored)} gold episodes pass "
      f"({len(rows) - len(scored)} awaiting the judge)")
sys.exit(1 if bad or not scored else 0)
