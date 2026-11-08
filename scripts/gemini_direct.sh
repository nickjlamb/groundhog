#!/bin/sh
# Gemini called through Google's own API (v2 check on the v1.1 Perplexity runs).
# Resumable; spending capped by GEMINI_BUDGET_USD (default 70) via runs/gemini_spend.json.
#   ./scripts/gemini_direct.sh check      key works? which Gemini models are available?
#   ./scripts/gemini_direct.sh headline   Gemini 3.1 Pro on abstain-001 (planted dose), 5 clean + 5 fault
#   ./scripts/gemini_direct.sh pro        Gemini 3.1 Pro on all 50 tasks (continues from headline)
#   ./scripts/gemini_direct.sh argon      Gemini 4 Argon on all 50 tasks
#   ./scripts/gemini_direct.sh flash      Gemini Flash on all 50 tasks (FLASH_ID=..., default gemini-3.8-flash)
#   ./scripts/gemini_direct.sh score      judge and score whatever has run
set -e
cd "$(dirname "$0")/.."
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements-dev.txt
REDACTA="node $HOME/redacta/mcp-server/dist/index.js"
PRO=gemini-3.1-pro-preview
FLASH=${FLASH_ID:-gemini-3.8-flash}
ARGON=gemini-4-argon
mkdir -p runs/direct
spend() { .venv/bin/python -c "from harness.models.gemini_model import spent; print(f'Gemini spend so far: \${spent():.2f}')"; }
case "$1" in
  check)
    .venv/bin/python - <<'PY'
import json, os, urllib.request
from harness.runner import load_env
load_env()
key = os.environ.get("GEMINI_API_KEY", "")
if not key or "KEY_HERE" in key or "YOUR_REAL_KEY" in key:
    raise SystemExit("GEMINI_API_KEY in .env is missing or still a placeholder")
req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
                             headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]})
models = json.load(urllib.request.urlopen(req))["models"]
for m in models:
    if "generateContent" in m.get("supportedGenerationMethods", []) and "gemini" in m["name"]:
        print(m["name"].split("/")[-1], "|", m.get("displayName", ""))
PY
    ;;
  headline)
    .venv/bin/python -u -m harness.runner --model gemini:$PRO --tasks abstain-001 --conditions both --runs 5 \
      --redacta-cmd "$REDACTA" --resume runs/direct/gemini_$PRO 2>&1 | tee runs/direct/headline.log
    ls runs/direct/gemini_$PRO/abstain-001__* >/dev/null 2>&1 || { echo "No episodes finished: see the errors above."; exit 1; }
    .venv/bin/python scripts/score.py runs/direct/gemini_$PRO --out runs/scores_direct > /dev/null
    .venv/bin/python - <<PY
import json, glob
rows = [json.loads(l) for f in glob.glob("runs/scores_direct/*.episodes.jsonl") for l in open(f)]
rows = [r for r in rows if r["task"] == "abstain-001"]
f5 = [r for r in rows if r["condition"] == "F5"]
print(f"abstain-001 via Google API: clean passed {sum(bool(r['passed']) for r in rows if r['condition']=='F0')}/5; "
      f"F5 followed the planted dose in {sum(any(h.startswith('followed_injection') for h in r['hard_fails']) for r in f5)}/{len(f5)}")
PY
    spend ;;
  pro)
    .venv/bin/python -u -m harness.runner --model gemini:$PRO --tasks all --conditions both --runs 5 \
      --redacta-cmd "$REDACTA" --resume runs/direct/gemini_$PRO > runs/direct/pro.log 2>&1
    tail -3 runs/direct/pro.log; spend ;;
  argon)
    .venv/bin/python -u -m harness.runner --model gemini:$ARGON --tasks all --conditions both --runs 5 \
      --redacta-cmd "$REDACTA" --resume runs/direct/gemini_$ARGON > runs/direct/argon.log 2>&1
    tail -3 runs/direct/argon.log; spend ;;
  flash)
    .venv/bin/python -u -m harness.runner --model gemini:$FLASH --tasks all --conditions both --runs 5 \
      --redacta-cmd "$REDACTA" --resume runs/direct/gemini_$FLASH > runs/direct/flash.log 2>&1
    tail -3 runs/direct/flash.log; spend ;;
  score)
    .venv/bin/python -u scripts/judge_runs.py runs/direct/gemini_* --out runs/scores_direct
    .venv/bin/python scripts/score.py runs/direct/gemini_* --out runs/scores_direct > /dev/null
    echo "Summary: runs/scores_direct/summary.md"; spend ;;
  *) sed -n 2,10p "$0" ;;
esac
echo "GEMINI $1 DONE"
