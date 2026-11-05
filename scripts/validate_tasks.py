"""Validate every Groundhog task file.

Checks each tasks/*.yaml against schema/task.schema.json, plus rules the
schema can't express:

  - the id matches the file name
  - the id prefix matches the category
  - ids are unique
  - rubric criterion ids are unique within a task
  - a rubric has at least one criterion worth positive points
  - claim_checking and free_text tasks carry a rubric

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


def main() -> int:
    schema = json.loads((ROOT / "schema" / "task.schema.json").read_text())
    validator = Draft202012Validator(schema)
    problems: list[str] = []
    statuses: Counter[str] = Counter()
    seen: set[str] = set()

    files = sorted((ROOT / "tasks").glob("*.yaml"))
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
        statuses[task.get("status", "?")] += 1

    for p in problems:
        print(f"ERROR  {p}")
    summary = ", ".join(f"{n} {s}" for s, n in sorted(statuses.items()))
    print(f"{len(files)} tasks: {summary}. {len(problems)} problem(s).")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
