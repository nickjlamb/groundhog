"""Where tasks live, which conditions each one runs under, and which gold applies.

Public tasks are in tasks/ and their cassettes in cassettes/. Held-out tasks
(split: heldout) never enter the public repo: point GROUNDHOG_PRIVATE at a
directory with tasks/ and cassettes/ subfolders to include them.

Conditions: F0 is clean; F1-F5 are the task's transient (fire-once) fault;
F1p-F5p are its persistent fault (every call to the named tool), if it has one.
"""

import copy
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PUBLIC_TASKS = ROOT / "tasks"
PUBLIC_CASSETTES = ROOT / "cassettes"
WHICH = ("both", "clean", "fault", "persistent", "all")


def private_root():
    p = os.environ.get("GROUNDHOG_PRIVATE")
    return Path(p).expanduser() if p else None


def task_files(include_private: bool = True) -> list[Path]:
    files = sorted(PUBLIC_TASKS.glob("*.yaml"))
    pr = private_root()
    if include_private and pr is not None:
        files += sorted((pr / "tasks").glob("*.yaml"))
    return files


def load_all(include_private: bool = True) -> list[dict]:
    """Every task file, each with its path in task['_path']."""
    out = []
    for p in task_files(include_private):
        t = yaml.safe_load(p.read_text())
        t["_path"] = str(p)
        out.append(t)
    return out


def by_id(include_private: bool = True) -> dict:
    return {t["id"]: t for t in load_all(include_private)}


def cassette_root(task: dict) -> Path:
    if task.get("split") == "heldout":
        pr = private_root()
        if pr is None:
            raise RuntimeError(f"{task['id']} is held out: set GROUNDHOG_PRIVATE to the private directory")
        return pr / "cassettes"
    return PUBLIC_CASSETTES


def is_persistent(condition: str) -> bool:
    return bool(condition) and condition.endswith("p")


def fault_code(condition: str) -> str:
    """'F3p' -> 'F3'; 'F3' -> 'F3'; 'F0' -> 'F0'."""
    return condition[:-1] if is_persistent(condition) else (condition or "F0")


def persistent_condition(task: dict):
    pf = task.get("persistent_fault")
    return pf["code"] + "p" if pf else None


def conditions(task: dict, which: str = "both") -> list[str]:
    """Conditions to run. 'both' (the v1 default) is clean plus the transient
    fault; 'all' adds the persistent fault when the task has one."""
    t, p = task.get("fault", "F0"), persistent_condition(task)
    table = {"clean": ["F0"], "fault": [t], "persistent": [p], "both": ["F0", t], "all": ["F0", t, p]}
    out = []
    for c in table[which]:
        if c and c not in out:
            out.append(c)
    return out


def task_for_condition(task: dict, condition: str) -> dict:
    """The task as scored under a condition: under a persistent fault, the gold
    (and answer type, if it changes) come from gold_under_persistent."""
    gup = task.get("gold_under_persistent")
    if not (is_persistent(condition) and gup):
        return task
    t = copy.copy(task)
    gup = dict(gup)
    if "answer_type" in gup:
        t["answer_type"] = gup.pop("answer_type")
    if "rubric" in gup:
        t["rubric"] = gup.pop("rubric")
    t["gold"] = gup
    return t
