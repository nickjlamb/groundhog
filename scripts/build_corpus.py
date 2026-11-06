"""Build or extend the frozen corpus (corpus/) from live PubCrawl.

Seeds: search calls and drug names found in cassettes and in run traces
(runs/*/), plus whole-label recordings for the label-comparison tasks.
Every search is re-run live and its results kept; every article found gets
its abstract fetched. Progress is saved after each job, so the script can be
stopped and resumed (use --budget to run in chunks).

    python scripts/build_corpus.py [--budget SECONDS] [--runs-glob 'runs/*/*.json']
"""

import argparse
import glob
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.cassette import Cassette                    # noqa: E402
from harness.corpus import Corpus, core_tokens, norm_name  # noqa: E402
from harness.mcp_client import StdioMCPClient           # noqa: E402

SEARCH_TOOLS = ("search_pubmed", "search_europepmc", "search_trials")
LABEL_KEYS = ("drug", "us_drug", "uk_drug")
STATE = ROOT / "corpus" / "_build_state.json"
WAITS = (5, 20, 45, None)


def live(client, tool, args):
    for wait in WAITS:
        res, err = client.call_tool(tool, args)
        if not err or wait is None:
            return res, err
        time.sleep(wait)


def seed_jobs(runs_glob):
    jobs, names = [], set()
    cassettes = sorted((ROOT / "cassettes").glob("*.json"))
    for p in cassettes:
        for e in json.loads(p.read_text())["entries"]:
            if e["tool"] in SEARCH_TOOLS:
                jobs.append(("search", e["tool"], e["args"]))
            for k in LABEL_KEYS:
                if e["args"].get(k):
                    names.add(e["args"][k])
            if isinstance(e["response"], dict) and e["response"].get("drug_name"):
                names.add(e["response"]["drug_name"])
    for f in sorted(glob.glob(str(ROOT / runs_glob))):
        try:
            steps = json.load(open(f)).get("steps", [])
        except (json.JSONDecodeError, OSError):
            continue
        for s in steps:
            if s["tool"] in SEARCH_TOOLS:
                jobs.append(("search", s["tool"], s["args"]))
            if s["tool"] in ("get_smpc", "get_uspi", "compare_labels", "resolve_drug_name"):
                names.update(s["args"].get(k) for k in LABEL_KEYS if s["args"].get(k))
    for n in sorted(names):
        jobs.append(("drug", "resolve_drug_name", {"drug": n}))
        for t in core_tokens(n):
            jobs.append(("drug", "resolve_drug_name", {"drug": t}))
    # Whole labels for comparison tasks, so any section request can be served.
    for p in cassettes:
        task = p.stem
        if not task.startswith("cmp-"):
            continue
        for e in json.loads(p.read_text())["entries"]:
            a = e["args"]
            if e["tool"] == "compare_labels":
                whole = {k: a[k] for k in LABEL_KEYS if a.get(k)}
                jobs.append(("label", task, ("compare_labels", whole)))
                jobs.append(("label", task, ("get_uspi", {"drug": a.get("us_drug") or a["drug"]})))
                jobs.append(("label", task, ("get_smpc", {"drug": a.get("uk_drug") or a["drug"]})))
            elif e["tool"] in ("get_uspi", "get_smpc") and not a.get("sections"):
                jobs.append(("label", task, (e["tool"], {"drug": a["drug"]})))
    seen, out = set(), []
    for j in jobs:
        key = json.dumps(j, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            out.append(j)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=0, help="stop after this many seconds (0 = no limit)")
    ap.add_argument("--runs-glob", default="runs/*/*__*.json")
    ap.add_argument("--pubcrawl-cmd", default="npx -y @pharmatools/pubcrawl@2.8.0")
    ap.add_argument("--unfreeze", action="store_true", help="allow changes to a frozen corpus")
    args = ap.parse_args()
    if (ROOT / "corpus" / "FROZEN").exists() and not args.unfreeze:
        sys.exit("corpus/ is frozen for the full run (corpus/FROZEN). Use --unfreeze to change it deliberately.")
    t0 = time.time()
    corpus = Corpus()
    state = json.loads(STATE.read_text()) if STATE.exists() else {"done": [], "failed": []}
    done = set(state["done"])

    # Abstracts already recorded in cassettes cost nothing.
    for p in (ROOT / "cassettes").glob("*.json"):
        for e in json.loads(p.read_text())["entries"]:
            if e["tool"] == "get_abstract":
                corpus.add_abstract(e["response"])
            if e["tool"] in SEARCH_TOOLS:
                corpus.add_search_results(e["tool"], e["response"])

    client = StdioMCPClient(args.pubcrawl_cmd.split(), "pubcrawl")
    def out_of_time():
        return args.budget and time.time() - t0 > args.budget

    def checkpoint():
        corpus.save()
        state["done"] = sorted(done)
        STATE.write_text(json.dumps(state, indent=1) + "\n")

    try:
        jobs = seed_jobs(args.runs_glob)
        todo = [j for j in jobs if json.dumps(j, sort_keys=True, default=str) not in done]
        print(f"{len(jobs)} seed jobs, {len(todo)} to do", flush=True)
        for i, job in enumerate(todo):
            if out_of_time():
                break
            kind, a, b = job
            if kind == "search":
                live_args = dict(b)
                res, err = live(client, a, live_args)
                if not err:
                    corpus.add_search_results(a, res)
            elif kind == "drug":
                key = norm_name(b["drug"])
                if key in corpus.drugs:
                    err = False
                else:
                    res, err = live(client, a, b)
                    corpus.add_drug(b["drug"], res if not err else None)
                    err = False         # "not a drug" is an answer too
            else:
                tool, targs = b
                cas = Cassette(a, ROOT / "cassettes")
                if cas.lookup(tool, targs) is None:
                    live_args = dict(targs, max_chars=50000) if tool in ("get_smpc", "get_uspi") else targs
                    res, err = live(client, tool, live_args)
                    if not err:
                        cas.add(tool, targs, res, recorded_by="corpus-build")
                        cas.save()
                else:
                    err = False
            key = json.dumps(job, sort_keys=True, default=str)
            if err:
                state["failed"].append(key)
            done.add(key)
            if i % 3 == 0:
                checkpoint()
        # Abstracts for every article found.
        missing = [p for p, r in corpus.articles.items() if "abstract_record" not in r and p not in state.get("no_abstract", [])]
        print(f"{len(missing)} abstracts to fetch", flush=True)
        for i, pmid in enumerate(missing):
            if out_of_time():
                break
            res, err = live(client, "get_abstract", {"pmid": pmid})
            if not err and isinstance(res, dict) and res.get("pmid"):
                corpus.add_abstract(res)
            else:
                state.setdefault("no_abstract", []).append(pmid)
            if i % 20 == 0:
                checkpoint()
    finally:
        checkpoint()
        client.close()
    left = len([p for p, r in corpus.articles.items() if "abstract_record" not in r
                and p not in state.get("no_abstract", [])])
    print(f"articles={len(corpus.articles)} trials={len(corpus.trials)} drugs={len(corpus.drugs)} "
          f"abstracts_missing={left} elapsed={time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
