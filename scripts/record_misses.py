"""Record, live, every off-path call seen in run traces, so legitimate routes
that no recording covered are available in replay.

Labels are recorded whole (any section request is then served from them).
Errors that are answers in their own right ("no open-access full text") are
stored and replayed as errors; transient failures (rate limits, outages) are not.

    python scripts/record_misses.py runs/<run_dir> [runs/<run_dir> ...]
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.cassette import Cassette          # noqa: E402
from harness.mcp_client import StdioMCPClient  # noqa: E402
from harness.tools import PAGED                # noqa: E402

TRANSIENT = ("429", "too many", "unreachable", "timed out", "timeout", "econn", "fetch failed", "503", "502")


def main(run_dirs):
    misses = {}
    for d in run_dirs:
        for f in sorted(Path(d).glob("*__*.json")):
            task = f.name.split("__")[0]
            for s in json.loads(f.read_text())["steps"]:
                if s.get("off_path"):
                    args = dict(s["args"])
                    if s["tool"] in PAGED:
                        args = {"drug": args["drug"]} if args.get("drug") else args
                    if s["tool"] == "get_full_text":
                        args = {k: v for k, v in args.items() if k != "sections"}
                    misses[json.dumps([task, s["tool"], args], sort_keys=True)] = (task, s["tool"], args)
    print(f"{len(misses)} distinct off-path calls")
    client = StdioMCPClient("npx -y @pharmatools/pubcrawl@2.8.0".split(), "pubcrawl")
    try:
        for task, tool, args in misses.values():
            cas = Cassette(task, ROOT / "cassettes")
            if cas.lookup(tool, args) is not None:
                continue
            live_args = dict(args, max_chars=50000) if tool in PAGED else args
            for wait in (5, 20, 45, None):
                res, err = client.call_tool(tool, live_args)
                if not err or wait is None or not any(m in json.dumps(res).lower() for m in TRANSIENT):
                    break
                time.sleep(wait)
            text = json.dumps(res).lower()
            soft_error = isinstance(res, dict) and len(res) == 1 and any(
                k in res for k in ("error", "text")) and ("no " in text or "not " in text)
            if err or soft_error:
                if any(m in text for m in TRANSIENT):
                    print(f"  transient, skipped: {task} {tool} {args}")
                    continue
                cas.add(tool, args, {"_recorded_error": res}, recorded_by="record-misses")
                print(f"  error recorded:   {task} {tool} {args} -> {text[:80]}")
            else:
                cas.add(tool, args, res, recorded_by="record-misses")
                print(f"  recorded:         {task} {tool} {args}")
            cas.save()
    finally:
        client.close()


if __name__ == "__main__":
    main(sys.argv[1:])
