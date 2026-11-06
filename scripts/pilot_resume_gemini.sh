#!/bin/sh
# Finish the pilot's Gemini replay run, keeping episodes already done.
cd "$(dirname "$0")/.."
TASKS=label-001,label-002,cmp-003,cmp-004,claim-001,cite-001,trial-001,conflict-002,conflict-005,abstain-004
RUN=$(ls -d runs/*perplexity_google_gemini-3.5-flash | tail -1)
.venv/bin/python -u -m harness.runner --model perplexity:google/gemini-3.5-flash --tasks "$TASKS" \
  --conditions both --runs 5 --resume "$RUN" 2>&1 | tee -a runs/pilot-gemini-resume.log
echo "GEMINI DONE"
