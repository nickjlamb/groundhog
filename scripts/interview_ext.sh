#!/bin/sh
# Interview extension (v1.1), resumable. Re-run the same command to continue.
#  1. Budget sweep: the tasks where a model ran out of its 15 tool calls in v1,
#     re-run with 30 calls (clean + fault, 5 repeats).
#  2. Gemini 3.1 Pro on all 50 tasks with the standard 15-call budget.
#  3. Judge and score both.
cd "$(dirname "$0")/.."
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements-dev.txt
REDACTA="node $HOME/redacta/mcp-server/dist/index.js"
FLASH_TASKS=conflict-003,abstain-003,abstain-005,cmp-005,conflict-001,trial-004,claim-002,abstain-002,claim-003,claim-008,abstain-001,claim-004,abstain-004
mkdir -p runs/budget30 runs/full
echo "1/3 Budget sweep (30 calls)"
.venv/bin/python -u -m harness.runner --model perplexity:google/gemini-3.5-flash --tasks "$FLASH_TASKS" \
  --conditions both --runs 5 --max-tool-calls 30 --redacta-cmd "$REDACTA" \
  --resume runs/budget30/perplexity_google_gemini-3.5-flash > runs/budget30/flash.log 2>&1
.venv/bin/python -u -m harness.runner --model anthropic:claude-sonnet-5-5 --tasks abstain-003 \
  --conditions both --runs 5 --max-tool-calls 30 \
  --resume runs/budget30/anthropic_claude-sonnet-5-5 > runs/budget30/claude.log 2>&1
echo "2/3 Gemini 3.1 Pro, all tasks (takes a few hours)"
.venv/bin/python -u -m harness.runner --model perplexity:google/gemini-3.1-pro-preview --tasks all \
  --conditions both --runs 5 --redacta-cmd "$REDACTA" \
  --resume runs/full/perplexity_google_gemini-3.1-pro-preview > runs/full/perplexity_google_gemini-3.1-pro-preview.log 2>&1
echo "3/3 Judging and scoring"
.venv/bin/python -u scripts/judge_runs.py runs/full/perplexity_google_gemini-3.1-pro-preview
.venv/bin/python -u scripts/judge_runs.py runs/budget30/perplexity_google_gemini-3.5-flash runs/budget30/anthropic_claude-sonnet-5-5 --out runs/scores_budget30
.venv/bin/python scripts/score.py runs/full/anthropic_claude-sonnet-5-5 runs/full/perplexity_google_gemini-3.5-flash runs/full/perplexity_google_gemini-3.1-pro-preview --out runs/scores > /dev/null
.venv/bin/python scripts/score.py runs/budget30/perplexity_google_gemini-3.5-flash runs/budget30/anthropic_claude-sonnet-5-5 --out runs/scores_budget30 > /dev/null
echo "INTERVIEW EXTENSION DONE"
