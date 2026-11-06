#!/bin/sh
# Full run: all tasks x 2 models x clean + fault x 5 repeats, replay only.
# The two models run in parallel (different providers). Re-run the same
# command to resume: finished episodes are kept.
#   ./scripts/full_run.sh                 all tasks except privacy
#   ./scripts/full_run.sh privacy         privacy tasks only (needs Redacta)
cd "$(dirname "$0")/.."
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements-dev.txt
REDACTA="node $HOME/redacta/mcp-server/dist/index.js"
ALL=$(ls tasks/*.yaml | xargs -n1 basename | sed 's/\.yaml$//')
if [ "$1" = "privacy" ]; then
  TASKS=$(echo "$ALL" | grep '^privacy-' | paste -sd, -)
else
  TASKS=$(echo "$ALL" | grep -v '^privacy-' | paste -sd, -)
fi
mkdir -p runs/full
run_model() {
  M="$1"; SLUG=$(echo "$M" | tr ':/' '__')
  DIR="runs/full/$SLUG"
  mkdir -p "$DIR"
  .venv/bin/python -u -m harness.runner --model "$M" --tasks "$TASKS" --conditions both --runs 5 \
    --redacta-cmd "$REDACTA" --resume "$DIR" > "runs/full/$SLUG.log" 2>&1
  echo "$M finished: $(ls "$DIR" | grep -c '__') episodes"
}
echo "Running $(echo "$TASKS" | tr ',' '\n' | wc -l | tr -d ' ') tasks; logs in runs/full/*.log"
run_model anthropic:claude-sonnet-5-5 &
run_model perplexity:google/gemini-3.5-flash &
wait
echo "FULL RUN DONE"
