"""Look up, once, every PMID or NCT number that appears in an answer but was
never shown to the agent, and cache what it resolves to (scoring/id_cache.json).
Scoring then stays offline: a resolvable ID whose title matches the answer is
'untraced' (a process flag); anything else is 'fabricated' (a hard fail).

    python scripts/resolve_untraced.py runs/full/*/ runs/budget30/*/
"""
import glob
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from harness.mcp_client import StdioMCPClient          # noqa: E402
from scoring.outcome import ID_CACHE, unseen_ids         # noqa: E402

TASKS = {yaml.safe_load(f.read_text())["id"]: yaml.safe_load(f.read_text()) for f in (ROOT / "tasks").glob("*.yaml")}


def main(dirs):
    cache = json.loads(ID_CACHE.read_text()) if ID_CACHE.exists() else {}
    todo = set()
    for d in dirs:
        for f in glob.glob(str(Path(d) / "*__*.json")):
            t = json.load(open(f))
            todo.update(i for i in unseen_ids(TASKS[t["task_id"]], t, t.get("answer") or {}) if i not in cache)
    print(f"{len(todo)} IDs to resolve")
    if todo:
        client = StdioMCPClient("npx -y @pharmatools/pubcrawl@2.8.0".split(), "pubcrawl")
        try:
            for i in sorted(todo):
                if i.upper().startswith("NCT"):
                    res, err = client.call_tool("get_trial", {"nctId": i})
                    title = (res or {}).get("title") or (res or {}).get("brief_title") if not err else None
                else:
                    res, err = client.call_tool("get_abstract", {"pmid": i})
                    title = (res or {}).get("title") if not err and isinstance(res, dict) and res.get("pmid") else None
                cache[i] = {"exists": bool(title), "title": title or ""}
                print(i, cache[i])
        finally:
            client.close()
    ID_CACHE.write_text(json.dumps(dict(sorted(cache.items())), indent=1, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:])
