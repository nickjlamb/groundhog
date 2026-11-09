"""Validate every Groundhog task file.

Checks each tasks/*.yaml against schema/task.schema.json, plus rules the
schema can't express:

  - the id matches the file name
  - the id prefix matches the category
  - ids are unique
  - rubric criterion ids are unique within a task
  - a rubric has at least one criterion worth positive points
  - claim_checking and free_text tasks carry a rubric
  - v2: held-out tasks are only in the private directory, public tasks only in tasks/
  - v2: a persistent F1/F2/F4 fault has gold_under_persistent or says why the clean gold still holds
  - v2: partial_abstain gold has a key for the answerable part and gap_any_of for the rest
  - v2: tasks with a split and an F5 fault declare their injection type and text

Tasks past their recheck_by date are listed as warnings (re-check the source).
Set GROUNDHOG_PRIVATE to validate held-out tasks too.

Prints a one-line summary per status and exits non-zero on any problem.

Usage:  python scripts/validate_tasks.py
"""

import datetime
import json
import sys
from collections import Counter
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from harness.taskset import PUBLIC_TASKS, task_files  # noqa: E402
PREFIX = {
    "label_lookup": "label",
    "us_uk_comparison": "cmp",
    "claim_checking": "claim",
    "citation": "cite",
    "trial_facts": "trial",
    "conflict_detection": "conflict",
    "abstention": "abstain",
    "privacy": "privacy",
}


def as_json(value):
    """YAML reads 2026-10-16 as a date; the schema expects ISO text."""
    if isinstance(value, dict):
        return {k: as_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [as_json(v) for v in value]
    if isinstance(value, datetime.date):
        return value.isoformat()
    return value


def check_rubric(name: str, task: dict) -> list[str]:
    """Rubric rules the schema can't express."""
    found: list[str] = []
    rubric = task.get("rubric")
    if task.get("category") == "privacy":
        ids = (task.get("gold") or {}).get("identifiers")
        if not ids or not all(isinstance(i, dict) and i.get("patterns") for i in ids):
            found.append(f"{name}: privacy tasks need gold.identifiers, each with patterns")
    needs_rubric = task.get("category") == "claim_checking" or task.get("answer_type") == "free_text"
    if not rubric:
        if needs_rubric:
            found.append(f"{name}: claim_checking and free_text tasks need a rubric")
        return found
    if not isinstance(rubric, list):
        return found
    ids = [c.get("id") for c in rubric if isinstance(c, dict)]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        found.append(f"{name}: duplicate rubric id '{dup}'")
    if not any(isinstance(c, dict) and isinstance(c.get("points"), int) and c["points"] > 0 for c in rubric):
        found.append(f"{name}: rubric needs at least one criterion with positive points")
    return found


def check_v2(name: str, task: dict, path: Path) -> list[str]:
    found: list[str] = []
    public = path.parent.resolve() == PUBLIC_TASKS.resolve()
    if task.get("split") == "heldout" and public:
        found.append(f"{name}: held-out task in the public tasks/ folder; move it to the private directory")
    if task.get("split") != "heldout" and not public:
        found.append(f"{name}: task in the private directory must have split: heldout")
    pf = task.get("persistent_fault") or {}
    if pf.get("code") in ("F1", "F2", "F4") and not task.get("gold_under_persistent") and not pf.get("why"):
        found.append(f"{name}: persistent {pf['code']} needs gold_under_persistent, or persistent_fault.why "
                     "explaining why the clean gold is still reachable")
    if task.get("gold_under_persistent") and not pf:
        found.append(f"{name}: gold_under_persistent without a persistent_fault")
    golds = [("gold", task.get("answer_type"), task.get("gold") or {})]
    gup = task.get("gold_under_persistent") or {}
    golds.append(("gold_under_persistent", gup.get("answer_type", task.get("answer_type")), gup))
    for where, atype, g in golds:
        if atype == "partial_abstain" and g:
            if not (isinstance(g.get("key"), dict) and g["key"].get("all_of")):
                found.append(f"{name}: {where}: partial_abstain needs key.all_of for the answerable part")
            if not g.get("gap_any_of"):
                found.append(f"{name}: {where}: partial_abstain needs gap_any_of (how the answer says the rest is unavailable)")
    if "split" in task and "F5" in (task.get("fault"), pf.get("code")) and not task.get("injection"):
        found.append(f"{name}: v2 F5 tasks declare injection.type and injection.text")
    return found


def main() -> int:
    schema = json.loads((ROOT / "schema" / "task.schema.json").read_text())
    validator = Draft202012Validator(schema)
    problems: list[str] = []
    statuses: Counter[str] = Counter()
    seen: set[str] = set()

    files = task_files()
    warnings: list[str] = []
    today = datetime.date.today().isoformat()
    if not files:
        print("No task files found.")
        return 1

    for path in files:
        task = as_json(yaml.safe_load(path.read_text()))
        for err in validator.iter_errors(task):
            where = "/".join(str(p) for p in err.absolute_path) or "(top level)"
            problems.append(f"{path.name}: {where}: {err.message}")
        if not isinstance(task, dict):
            continue
        task_id = task.get("id")
        if task_id != path.stem:
            problems.append(f"{path.name}: id '{task_id}' does not match the file name")
        if task_id in seen:
            problems.append(f"{path.name}: duplicate id '{task_id}'")
        seen.add(task_id)
        expected = PREFIX.get(task.get("category"))
        if expected and task_id and not str(task_id).startswith(expected + "-"):
            problems.append(f"{path.name}: category '{task['category']}' needs the id prefix '{expected}-'")
        problems.extend(check_rubric(path.name, task))
        problems.extend(check_v2(path.name, task, path))
        if task.get("recheck_by") and task["recheck_by"] < today and task.get("status") == "verified":
            warnings.append(f"{path.name}: past its recheck_by date ({task['recheck_by']}); re-check the source")
        statuses[task.get("status", "?")] += 1

    for w in warnings:
        print(f"WARN   {w}")
    for p in problems:
        print(f"ERROR  {p}")
    summary = ", ".join(f"{n} {s}" for s, n in sorted(statuses.items()))
    print(f"{len(files)} tasks: {summary}. {len(problems)} problem(s).")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
