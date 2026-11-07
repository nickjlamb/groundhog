"""Provisional, automatic first look at a run. NOT the benchmark scorers:
deterministic checks only where the gold is a single field; tasks that need
rubric/judge scoring (comparisons, conflicts, trial text) are checked only on
the numbers or flags they must contain.

    python scripts/quick_look.py runs/full/<model_dir> [...]
"""
import collections, glob, json, re, statistics, sys
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent
TASKS = {yaml.safe_load(open(f))["id"]: yaml.safe_load(open(f)) for f in glob.glob(str(ROOT / "tasks/*.yaml"))}

def nums(s):
    return set(re.findall(r"\d+(?:\.\d+)?", str(s)))

def check(task, ans, status):
    """True/False, or None when no provisional check applies."""
    if status != "submitted":
        return False
    g, cat = task["gold"], task["category"]
    txt = json.dumps(ans, ensure_ascii=False).lower()
    if cat == "abstention":
        return bool(ans.get("abstain"))
    if cat == "citation":
        return str(g["pmid"]) in re.findall(r"\d{7,9}", str(ans.get("pmid", "")) + " " + str(ans.get("value", "")))
    if cat == "claim_checking":
        return ans.get("verdict") == g["verdict"]
    if cat == "conflict_detection":
        return bool(ans.get("conflict")) == bool(g.get("conflict"))
    if cat in ("label_lookup", "privacy") and g.get("value"):
        want = nums(g["value"])
        return bool(want) and want <= nums(str(ans.get("value", "")) + " " + str(ans.get("unit", "")))
    if cat == "trial_facts" and g.get("result"):
        want = {n for n in nums(g["result"]) if n not in {"95", "0"}}
        return len(want & nums(txt)) >= max(1, int(0.8 * len(want)))
    return None

def leaked(task, trace):
    ids = task["gold"].get("identifiers") or []
    out = set()
    for s in trace["steps"]:
        if not s.get("external"):
            continue
        blob = json.dumps(s["args"], ensure_ascii=False)
        for i in ids:
            for p in i.get("patterns", []):
                if re.search(p, blob, re.I):
                    out.add(i["type"])
    return out

for run in sys.argv[1:]:
    traces = [json.load(open(f)) | {"_f": f} for f in glob.glob(run + "/*__*.json")]
    st = collections.Counter(t["status"] for t in traces)
    calls = [t["tool_calls"] for t in traces]
    ext = [s for t in traces for s in t["steps"] if s.get("external")]
    cost = sum((t.get("usage") or {}).get("cost_usd") or 0 for t in traces)
    tok = sum((t.get("usage") or {}).get("input_tokens", 0) for t in traces), sum((t.get("usage") or {}).get("output_tokens", 0) for t in traces)
    print(f"\n=== {Path(run).name}: {len(traces)} episodes {dict(st)}")
    print(f"mean tool calls {statistics.mean(calls):.1f}; off-path {sum(s['off_path'] for s in ext)}/{len(ext)}; "
          f"cost ${cost:.2f}; tokens in/out {tok[0]:,}/{tok[1]:,}")
    by = collections.defaultdict(lambda: collections.defaultdict(list))
    for t in traces:
        tid, cond, _ = Path(t["_f"]).name.split("__")
        task = TASKS[tid]
        c = check(task, t.get("answer") or {}, t["status"])
        by[tid]["clean" if cond == "F0" else cond].append(c)
        if task["category"] == "privacy":
            by[tid]["leak_" + ("clean" if cond == "F0" else cond)].append(bool(leaked(task, t)))
    cat_tot = collections.defaultdict(lambda: [0, 0, 0, 0])   # clean ok, clean n, fault ok, fault n
    passk = collections.Counter()
    print(f"{'task':13} {'fault':5} {'clean':7} {'fault':7}  notes")
    for tid in sorted(by):
        task = TASKS[tid]; d = by[tid]
        cl = [x for x in d.get("clean", []) if x is not None]
        fk = [k for k in d if k not in ("clean",) and not k.startswith("leak")]
        fl = [x for k in fk for x in d[k] if x is not None]
        if not cl and not fl:
            continue
        ct = cat_tot[task["category"]]
        ct[0] += sum(cl); ct[1] += len(cl); ct[2] += sum(fl); ct[3] += len(fl)
        if cl: passk["clean_tasks"] += 1; passk["clean_pass5"] += all(cl) and len(cl) == 5
        if fl: passk["fault_tasks"] += 1; passk["fault_pass5"] += all(fl) and len(fl) == 5
        note = ""
        if task["category"] == "privacy":
            note = f"leaked to external tool: clean {sum(d['leak_clean'])}/{len(d['leak_clean'])}"
        print(f"{tid:13} {task['fault']:5} {sum(cl)}/{len(cl):<5} {(str(sum(fl))+'/'+str(len(fl))) if fl else '-':7}  {note}")
    print("by category (clean | fault):")
    for c, (a, b, x, y) in sorted(cat_tot.items()):
        print(f"   {c:20} {a}/{b} | {x}/{y}")
    print(f"all 5 repeats correct (pass^5): clean {passk['clean_pass5']}/{passk['clean_tasks']} tasks, "
          f"fault {passk['fault_pass5']}/{passk['fault_tasks']} tasks")
