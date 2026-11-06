#!/bin/sh
# Pilot: 10 tasks x 2 models.
#   ./scripts/pilot.sh          record live routes, build the corpus, then replay
#   ./scripts/pilot.sh replay   build/extend the corpus, then replay only
# Replay runs clean and fault conditions, 5 repeats each. Needs python3,
# node/npx and API keys in .env.
set -e
cd "$(dirname "$0")/.."
TASKS=label-001,label-002,cmp-003,cmp-004,claim-001,cite-001,trial-001,conflict-002,conflict-005,abstain-004
MODELS="anthropic:claude-sonnet-5-5 perplexity:google/gemini-3.5-flash"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements-dev.txt
mkdir -p runs
LOG=runs/pilot-$(date +%Y%m%d-%H%M).log
echo "Logging to $LOG"
if [ "$1" != "replay" ]; then
  for M in $MODELS; do
    .venv/bin/python -u -m harness.runner --model "$M" --tasks "$TASKS" --record --runs 2 2>&1 | tee -a "$LOG" || true
  done
fi
echo "Building corpus (resumable; about 45 min the first time)" | tee -a "$LOG"
.venv/bin/python -u scripts/build_corpus.py 2>&1 | tee -a "$LOG"
for M in $MODELS; do
  .venv/bin/python -u -m harness.runner --model "$M" --tasks "$TASKS" --conditions both --runs 5 2>&1 | tee -a "$LOG" || true
done
echo "PILOT DONE" | tee -a "$LOG"
