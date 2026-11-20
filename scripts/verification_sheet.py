"""Build a verification workbook for draft tasks, for Nick to check against the sources.

    python scripts/verification_sheet.py --out annotation/v2-batch1-verification.xlsx [--tasks id,id,...]

One row per draft task: question, gold answer, source excerpts, links to the
sources, fault, rubric, traps and any decision the drafter left for Nick, then
columns for his verdict. Defaults to every task with status: draft.
Output goes to annotation/ (git-ignored).
"""

import argparse
import re
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from harness.taskset import load_all  # noqa: E402

ARIAL = "Arial"
HEAD = PatternFill("solid", fgColor="0F1A2E")
GREY = PatternFill("solid", fgColor="E7E9EC")
DECIDE = PatternFill("solid", fgColor="FDECEF")
YELLOW = PatternFill("solid", fgColor="FFF6D5")
THIN = Border(*(Side(style="thin", color="C9CED6"),) * 4)
COLS = [("Task", 13), ("Category", 14), ("Subtype", 17), ("Question", 50), ("Gold answer", 45),
        ("Source excerpts", 60), ("Link 1", 22), ("Link 2", 22), ("Link 3", 22), ("Faults", 18),
        ("Rubric", 50), ("Traps and notes", 50), ("Decision needed from you", 40),
        ("Your verdict", 16), ("Your decision / answer", 30), ("Changes needed", 35), ("Date checked", 12)]
FILL_FROM = "Your verdict"
VERDICTS = ["Verified", "Verified with changes", "Rewrite", "Drop"]


def text(v):
    if isinstance(v, dict):
        return "\n".join(f"{k}: {text(x)}" for k, x in v.items())
    if isinstance(v, list):
        return "\n".join(f"- {text(x)}" for x in v)
    return " ".join(str(v).split())


def gold(t):
    g = dict(t.get("gold") or {})
    g.pop("identifiers", None)
    out = text(g)
    if t.get("gold_under_persistent"):
        out += "\n\nUNDER PERSISTENT FAULT:\n" + text(t["gold_under_persistent"])
    return out


def links(t):
    src = t.get("source") or {}
    out = []
    if src.get("url"):
        out.append(src["url"])
    for pid in re.findall(r"eMC product (\d+)", str(src.get("product", ""))):
        u = f"https://www.medicines.org.uk/emc/product/{pid}/smpc"
        if u not in out:
            out.append(u)
    for p in re.findall(r"\d{7,8}", str(src.get("pmid", ""))):
        out.append(f"https://pubmed.ncbi.nlm.nih.gov/{p}/")
    if src.get("pmcid"):
        out.append(f"https://pmc.ncbi.nlm.nih.gov/articles/{src['pmcid']}/")
    for n in re.findall(r"NCT\d{8}", str(src.get("nct_id", "")) + " " + str(t.get("prompt", ""))):
        u = f"https://clinicaltrials.gov/study/{n}"
        if u not in out:
            out.append(u)
    for k, v in (src.get("excerpts") or {}).items():           # PMIDs named in excerpt keys or texts
        for p in re.findall(r"PMID[ _]?(\d{7,8})|pmid_(\d{7,8})", f"{k} {v}"):
            u = f"https://pubmed.ncbi.nlm.nih.gov/{p[0] or p[1]}/"
            if u not in out:
                out.append(u)
    return out[:3]


def faults(t):
    s = f"Transient: {t.get('fault')}"
    pf = t.get("persistent_fault")
    if pf:
        s += f"\nPersistent: {pf['code']}p on {pf['tool']}"
    if t.get("injection"):
        s += f"\nInjection: {t['injection']['type']}"
    return s


def rubric(t):
    return "\n".join(f"{c['id']} ({c['points']:+d}, {c['check']}): {c['criterion']}" for c in t.get("rubric") or [])


def task_text(t):
    """Notes plus the persistent-fault gold's detail, where a drafter may also leave a question."""
    return f"{t.get('notes', '')} {(t.get('gold_under_persistent') or {}).get('detail', '')}"


def decisions(notes):
    flat = " ".join(str(notes or "").split())
    asked = re.findall(r"DECISION FOR NICK: (.*?\?(?:\s*\([^)]*\))?)", flat)
    if asked:
        return " ".join(q[0].upper() + q[1:] for q in asked)
    return _loose_decisions(flat)


def _loose_decisions(notes):
    sents = re.split(r"(?<=[.?])\s+", " ".join(str(notes or "").split()))
    keep = [s for s in sents if re.search(r"\bNick\b", s, re.I) and not s.startswith(("Verified by Nick", "Nick confirmed"))]
    # A "DECISION FOR NICK:" sentence usually runs on into the question; keep the next two sentences with it.
    for i, s in enumerate(sents):
        if s.upper().startswith("DECISION FOR NICK"):
            keep += [x for x in sents[i + 1:i + 3] if x not in keep]
    return " ".join(dict.fromkeys(keep))


def build(tasks, out):
    wb = Workbook()
    ws = wb.active
    ws.title = "Read me"
    lines = [("Groundhog v2: draft task verification", True), ("", False),
             ("One row per draft task. Grey columns are the draft; fill in the white columns from 'Your verdict' on.", False),
             ("Check each task against its source (links in Link 1-3), as for v1: the gold must rest on the source, never on what a model said.", False),
             ("Pink cells are decisions I left for you; answer them in 'Your decision / answer'.", False),
             ("Your verdict: Verified / Verified with changes (say what in 'Changes needed') / Rewrite / Drop.", False),
             ("The yellow row on the Tasks sheet is an example of a completed row, not a task.", False),
             ("When you're done, save the workbook and tell Claude: it copies your sign-offs into the task files.", False)]
    for i, (s, b) in enumerate(lines, 1):
        c = ws.cell(row=i, column=1, value=s)
        c.font = Font(name=ARIAL, size=12 if b else 10, bold=b)
    ws.column_dimensions["A"].width = 120

    ws = wb.create_sheet("Tasks")
    for i, (name, w) in enumerate(COLS, 1):
        c = ws.cell(row=1, column=i, value=name)
        c.font = Font(name=ARIAL, bold=True, color="FFFFFF", size=10)
        c.fill = HEAD
        c.alignment = Alignment(wrap_text=True, vertical="center")
        c.border = THIN
        ws.column_dimensions[c.column_letter].width = w
    ws.row_dimensions[1].height = 30
    ws.freeze_panes = "E2"
    first_fill = [n for n, _ in COLS].index(FILL_FROM) + 1

    example = {"Task": "Example", "Category": "label_lookup", "Subtype": "", "Question": "(v1 example) According to the UK SmPC for ...",
               "Gold answer": "value: ...", "Source excerpts": "...", "Faults": "Transient: F3",
               "Your verdict": "Verified with changes", "Your decision / answer": "",
               "Changes needed": "Excerpt is from 4.2, not 4.3; gold value right", "Date checked": "2026-11-20"}
    rows = [(example, True)] + [(t, False) for t in tasks]
    for r, (t, is_ex) in enumerate(rows, 2):
        if is_ex:
            vals = example
            lk = []
        else:
            lk = links(t)
            vals = {"Task": t["id"], "Category": t["category"], "Subtype": t.get("subtype", ""),
                    "Question": " ".join(str(t["prompt"]).split()), "Gold answer": gold(t),
                    "Source excerpts": text((t.get("source") or {}).get("excerpts") or (t.get("source") or {}).get("excerpt", "")),
                    "Faults": faults(t), "Rubric": rubric(t), "Traps and notes": " ".join(str(t.get("notes", "")).split()),
                    "Decision needed from you": decisions(task_text(t))}
        for i, (name, _) in enumerate(COLS, 1):
            c = ws.cell(row=r, column=i, value=vals.get(name, ""))
            c.font = Font(name=ARIAL, size=9, italic=is_ex, color="6B7B8D" if is_ex else "000000")
            c.alignment = Alignment(wrap_text=True, vertical="top")
            c.border = THIN
            if is_ex:
                c.fill = YELLOW
            elif i < first_fill:
                c.fill = DECIDE if name == "Decision needed from you" and vals.get(name) else GREY
        for j, u in enumerate(lk):
            c = ws.cell(row=r, column=[n for n, _ in COLS].index(f"Link {j + 1}") + 1, value=u)
            c.hyperlink = u
            c.font = Font(name=ARIAL, size=9, color="0D5BA8", underline="single")
    col = ws.cell(row=1, column=first_fill).column_letter
    dv = DataValidation(type="list", formula1='"' + ",".join(VERDICTS) + '"', allow_blank=True)
    dv.add(f"{col}2:{col}{len(rows) + 1}")
    ws.add_data_validation(dv)
    ws.auto_filter.ref = f"A1:{ws.cell(row=1, column=len(COLS)).column_letter}{len(rows) + 1}"

    ds = wb.create_sheet("Decisions")
    for i, (name, w) in enumerate([("Task", 13), ("Decision needed", 90), ("Your answer", 50)], 1):
        c = ds.cell(row=1, column=i, value=name)
        c.font = Font(name=ARIAL, bold=True, color="FFFFFF", size=10)
        c.fill = HEAD
        ds.column_dimensions[c.column_letter].width = w
    r = 2
    for t in tasks:
        d = decisions(task_text(t))
        if d:
            for i, v in enumerate((t["id"], d, ""), 1):
                c = ds.cell(row=r, column=i, value=v)
                c.font = Font(name=ARIAL, size=10)
                c.alignment = Alignment(wrap_text=True, vertical="top")
            r += 1
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    print(f"wrote {out}: {len(tasks)} tasks, {r - 2} with decisions")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--tasks", default="")
    a = ap.parse_args()
    tasks = load_all(include_private=False)
    if a.tasks:
        want = a.tasks.split(",")
        tasks = sorted([t for t in tasks if t["id"] in want], key=lambda t: want.index(t["id"]))
    else:
        order = {"abstention": 0, "conflict_detection": 1, "claim_checking": 2}
        tasks = sorted([t for t in tasks if t.get("status") == "draft"], key=lambda t: (order.get(t["category"], 9), t["id"]))
    build(tasks, a.out)


if __name__ == "__main__":
    main()
