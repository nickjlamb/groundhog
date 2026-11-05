#!/usr/bin/env bash
# Download the HealthBench files this study uses into data/ and check them.
# Source: openai/simple-evals (MIT). The files carry a canary string (a marker
# for detecting benchmark leakage into training data), so data/ is git-ignored.
set -euo pipefail
cd "$(dirname "$0")/../data" 2>/dev/null || { mkdir -p "$(dirname "$0")/../data"; cd "$(dirname "$0")/../data"; }
BASE=https://openaipublic.blob.core.windows.net/simple-evals/healthbench
for f in 2025-05-07-06-14-12_oss_eval.jsonl 2025-05-07-06-14-12_oss_meta_eval.jsonl; do
  [ -f "$f" ] || curl -fSL --retry 3 -o "$f" "$BASE/$f"
done
shasum -a 256 -c <<'SUMS'
e99dd3c6372c10d6fcc5e385c5fae69d0dd40392dae56836ef9493ae324ecd2f  2025-05-07-06-14-12_oss_eval.jsonl
6a343ed3fcb6f28353c2c6c157ae30ddf2db874c947b27ba474ad54da9c5dbac  2025-05-07-06-14-12_oss_meta_eval.jsonl
SUMS
