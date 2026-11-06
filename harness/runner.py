"""Run models x tasks x conditions x repeats and write one trace per episode.

  python -m harness.runner --model mock:submit-gold --tasks all --runs 1
  python -m harness.runner --model anthropic:<id> --tasks label-001,claim-001 --runs 5

Conditions: each task runs clean (F0) and under its assigned fault, unless
--conditions clean or --conditions fault is given. Replay mode reads
cassettes/; record mode (--record) calls live PubCrawl and writes them.
"""

import argparse
import datetime
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import yaml

from .agent import run_episode
from .cassette import Cassette
from .gateway import RecordGateway, ReplayGateway
from .models import make_model

ROOT = Path(__file__).resolve().parent.parent


def load_tasks(selector: str) -> list[dict]:
    tasks = [yaml.safe_load(p.read_text()) for p in sorted((ROOT / "tasks").glob("*.yaml"))]
    tasks = [t for t in tasks if t.get("status") == "verified"]
    if selector != "all":
        wanted = set(selector.split(","))
        tasks = [t for t in tasks if t["id"] in wanted]
        missing = wanted - {t["id"] for t in tasks}
        if missing:
            sys.exit(f"unknown or unverified tasks: {sorted(missing)}")
    return tasks


def git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


def task_set_hash(tasks) -> str:
    h = hashlib.sha256()
    for t in tasks:
        h.update((ROOT / "tasks" / f"{t['id']}.yaml").read_bytes())
    return h.hexdigest()[:12]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True)
    ap.add_argument("--tasks", default="all")
    ap.add_argument("--runs", type=int, default=1, help="repeats per task per condition (spec: 5)")
    ap.add_argument("--conditions", choices=["both", "clean", "fault"], default="both")
    ap.add_argument("--record", action="store_true", help="call live PubCrawl and write cassettes (clean only)")
    ap.add_argument("--pubcrawl-cmd", default="npx -y @pharmatools/pubcrawl@2.8.0")
    ap.add_argument("--redacta-cmd", default="", help="command for a local Redacta MCP server; omit to run without Redacta")
    ap.add_argument("--out", default=str(ROOT / "runs"))
    args = ap.parse_args(argv)

    tasks = load_tasks(args.tasks)
    run_id = datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + args.model.replace(":", "_").replace("/", "_")
    out = Path(args.out) / run_id
    out.mkdir(parents=True, exist_ok=True)

    from .mcp_client import StdioMCPClient
    local = StdioMCPClient(args.redacta_cmd.split(), "redacta") if args.redacta_cmd else None
    pubcrawl = StdioMCPClient(args.pubcrawl_cmd.split(), "pubcrawl") if args.record else None

    manifest = {"run_id": run_id, "model": args.model, "runs": args.runs, "conditions": args.conditions,
                "mode": "record" if args.record else "replay", "git_sha": git_sha(),
                "task_set_hash": task_set_hash(tasks), "tasks": [t["id"] for t in tasks],
                "pubcrawl": pubcrawl.server_info if pubcrawl else None,
                "redacta": local.server_info if local else None,
                "started": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    for task in tasks:
        conds = ["F0"] if args.record else {"both": ["F0", task["fault"]], "clean": ["F0"], "fault": [task["fault"]]}[args.conditions]
        cassette = Cassette(task["id"])
        for cond in conds:
            for rep in range(1, args.runs + 1):
                model = make_model(args.model)
                if hasattr(model, "bind"):
                    model.bind(task)
                if args.record:
                    gw = RecordGateway(task, cassette, pubcrawl, recorded_by=args.model, local_client=local)
                else:
                    gw = ReplayGateway(task, cassette, fault=cond, local_client=local)
                trace = run_episode(task, model, gw)
                trace.update(run_id=run_id, condition=cond, repeat=rep)
                name = f"{task['id']}__{cond}__r{rep}.json"
                (out / name).write_text(json.dumps(trace, indent=1, ensure_ascii=False) + "\n")
                print(f"{task['id']:14} {cond} r{rep}  {trace['status']:16} calls={trace['tool_calls']}"
                      f" off_path={sum(s['off_path'] for s in trace['steps'])}"
                      + (f"  LIVE ERRORS={len(gw.errors)}" if args.record and gw.errors else ""))
        if args.record:
            cassette.save()

    for c in (local, pubcrawl):
        if c:
            c.close()
    print(f"traces in {out}")


if __name__ == "__main__":
    main()
