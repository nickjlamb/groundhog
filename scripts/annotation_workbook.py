"""Build an annotation workbook for the second annotator, plus Nick's private key.

    python scripts/annotation_workbook.py --batch "Practice=label-002,claim-004,abstain-004" \
        --out annotation/practice.xlsx --key annotation/practice-key.xlsx

    # several sheets in one workbook:
    python scripts/annotation_workbook.py --batch "Batch 1=abstain-031,...,label-007" --qc label-007,trial-001 ...

The annotator's workbook shows each task's question and the kinds of source to
check, never the gold answer, the task's notes or its excerpts. Items carry
neutral codes (P-01, B1-07), so v1 quality-check tasks look like any other;
items are shuffled with a fixed seed. The key maps each code to its task id,
says which items are quality checks, and gives the gold answer, for Nick only.

Held-out tasks are read from GROUNDHOG_PRIVATE: run this yourself for batch 3,
and keep both files out of the repo and out of AI tools.
"""

import argparse
import random
import re
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from harness.taskset import by_id  # noqa: E402

# The Kind column describes what the question looks like, never its answer: abstention
# tasks are labelled by the source they point to, and conflict tasks (some of which
# are v2 decoys with no real conflict) as "Two sources".
KIND = {"label_lookup": "Label look-up", "us_uk_comparison": "US/UK comparison", "claim_checking": "Claim check",
        "citation": "Citation", "trial_facts": "Trial facts", "conflict_detection": "Two sources",
        "abstention": None, "privacy": "Label look-up (patient details)"}
LOOKS_LIKE = {"get_smpc": "Label look-up", "get_uspi": "Label look-up", "compare_labels": "US/UK comparison",
              "get_trial": "Trial facts", "get_abstract": "Trial facts", "get_full_text": "Trial facts",
              "search_pubmed": "Citation", "format_citation": "Citation", "search_trials": "Trial facts"}
SOURCE = {"get_smpc": "UK SmPC (eMC)", "get_uspi": "US label (DailyMed)", "compare_labels": "UK SmPC (eMC) and US label (DailyMed)",
          "get_abstract": "PubMed", "get_full_text": "PubMed Central full text", "format_citation": "PubMed",
          "search_pubmed": "PubMed / Europe PMC search", "get_trial": "ClinicalTrials.gov", "search_trials": "ClinicalTrials.gov"}

GIVEN = ["Item", "Kind", "Question", "Where to look"]
FILL = ["Answer", "Verdict", "Sources disagree?", "Not available?", "Evidence", "Sources used",
        "Confidence", "Flag", "Minutes", "Notes"]
WIDTH = {"Item": 7, "Kind": 16, "Question": 60, "Where to look": 24, "Answer": 40, "Verdict": 16,
         "Sources disagree?": 11, "Not available?": 13, "Evidence": 40, "Sources used": 24,
         "Confidence": 11, "Flag": 15, "Minutes": 9, "Notes": 30}
LISTS = {"Verdict": ["Supported", "Partially supported", "Unsupported", "Not a claim check"],
         "Sources disagree?": ["No", "Yes"], "Not available?": ["No", "Yes, part", "Yes, all"],
         "Confidence": ["High", "Medium", "Low"], "Flag": ["None", "Ambiguous", "Source problem", "Question unclear"]}
EXAMPLE = {"Item": "Ex", "Kind": "Label look-up",
           "Question": "EXAMPLE (not a task): According to the UK SmPC for Lipitor (atorvastatin) film-coated tablets, "
                       "what is the maximum daily dose?",
           "Where to look": "UK SmPC (eMC)", "Answer": "80 mg once a day", "Verdict": "Not a claim check",
           "Sources disagree?": "No", "Not available?": "No",
           "Evidence": "4.2: \"The usual starting dose is 10 mg once a day. ... The maximum dose is 80 mg once a day.\"",
           "Sources used": "eMC product 1059 (Lipitor 10 mg)", "Confidence": "High", "Flag": "None", "Minutes": 4, "Notes": ""}

ARIAL = "Arial"
GREY = PatternFill("solid", fgColor="E7E9EC")
HEAD = PatternFill("solid", fgColor="0F1A2E")
YELLOW = PatternFill("solid", fgColor="FFF6D5")
THIN = Border(*(Side(style="thin", color="C9CED6"),) * 4)


def kind_of(task):
    k = KIND.get(task["category"])
    if k:
        return k
    first = re.split(r"\s*;\s*", str((task.get("source") or {}).get("tool") or ""))[0].strip()
    return LOOKS_LIKE.get(first, "Look-up")


def where_to_look(task):
    """Kinds of source only. Identifiers are in the question when the task gives them."""
    tools = re.split(r"\s*;\s*", str((task.get("source") or {}).get("tool") or ""))
    seen = []
    for t in tools:
        s = SOURCE.get(t.strip())
        if s and s not in seen:
            seen.append(s)
    return "; ".join(seen) or "Any public source"


def gold_text(task):
    g = task.get("gold") or {}
    keep = {k: v for k, v in g.items() if k not in ("identifiers", "acceptable_variants", "key")}
    return "\n".join(f"{k}: {str(v).strip()}" for k, v in keep.items())


def style_header(ws, cols):
    for i, name in enumerate(cols, 1):
        c = ws.cell(row=1, column=i, value=name)
        c.font = Font(name=ARIAL, bold=True, color="FFFFFF", size=10)
        c.fill = HEAD
        c.alignment = Alignment(wrap_text=True, vertical="center")
        c.border = THIN
        ws.column_dimensions[c.column_letter].width = WIDTH.get(name, 14)
    ws.row_dimensions[1].height = 30
    ws.freeze_panes = "E2"


def write_row(ws, r, values, cols, example=False):
    for i, name in enumerate(cols, 1):
        c = ws.cell(row=r, column=i, value=values.get(name, ""))
        c.font = Font(name=ARIAL, size=10, italic=example, color="6B7B8D" if example else "000000")
        c.alignment = Alignment(wrap_text=True, vertical="top")
        c.border = THIN
        if name in GIVEN:
            c.fill = GREY
        elif example:
            c.fill = YELLOW


def add_lists(ws, cols, first, last):
    for name, opts in LISTS.items():
        col = ws.cell(row=1, column=cols.index(name) + 1).column_letter
        dv = DataValidation(type="list", formula1='"' + ",".join(opts) + '"', allow_blank=True)
        dv.add(f"{col}{first}:{col}{last}")
        ws.add_data_validation(dv)


def readme(wb, batches):
    ws = wb.active
    ws.title = "Read me"
    lines = [
        ("Groundhog v2: annotation workbook", True),
        ("", False),
        ("One row per task. Grey columns are filled in already; fill in the white ones (Answer to Notes).", False),
        ("Verdict, Sources disagree?, Not available?, Confidence and Flag have drop-down lists.", False),
        ("The yellow row at the top of each sheet is a worked example of the format, not a task.", False),
        ("Answer from the public sources listed, without AI tools, and without looking at the Groundhog task files.", False),
        ("Full instructions: the annotator briefing.", False),
        ("", False),
        ("Sheets in this workbook: " + ", ".join(f"{n} ({len(ids)} items)" for n, ids in batches), False),
        ("When you're done, save and email the workbook back.", False),
    ]
    for i, (text, bold) in enumerate(lines, 1):
        c = ws.cell(row=i, column=1, value=text)
        c.font = Font(name=ARIAL, size=12 if bold else 10, bold=bold)
    ws.column_dimensions["A"].width = 110


def build(batches, qc, seed, out, key_out):
    tasks = by_id()
    missing = [t for _, ids in batches for t in ids if t not in tasks]
    if missing:
        sys.exit(f"unknown tasks (held-out ones need GROUNDHOG_PRIVATE): {missing}")
    wb, key = Workbook(), Workbook()
    readme(wb, batches)
    kws = key.active
    kws.title = "Key"
    kcols = ["Sheet", "Item", "Task", "Quality check", "Category", "Answer type", "Gold"]
    style_header(kws, kcols)
    kws.freeze_panes = "A2"
    for name, w in zip(kcols, (12, 7, 14, 10, 18, 14, 90)):
        kws.column_dimensions[kws.cell(row=1, column=kcols.index(name) + 1).column_letter].width = w
    krow = 2
    rng = random.Random(seed)
    cols = GIVEN + FILL
    for b, (sheet, ids) in enumerate(batches):
        ids = list(ids)
        rng.shuffle(ids)
        prefix = "P" if sheet.lower().startswith("practice") else f"B{b + (0 if batches[0][0].lower().startswith('practice') else 1)}"
        ws = wb.create_sheet(sheet)
        style_header(ws, cols)
        write_row(ws, 2, EXAMPLE, cols, example=True)
        for i, tid in enumerate(ids, 1):
            t = tasks[tid]
            code = f"{prefix}-{i:02d}"
            write_row(ws, i + 2, {"Item": code, "Kind": kind_of(t), "Question": " ".join(str(t["prompt"]).split()) if t["category"] != "privacy" else str(t["prompt"]).strip(),
                                  "Where to look": where_to_look(t)}, cols)
            for k, v in zip(kcols, (sheet, code, tid, "yes" if tid in qc else "", t["category"], t.get("answer_type"), gold_text(t))):
                c = kws.cell(row=krow, column=kcols.index(k) + 1, value=v)
                c.font = Font(name=ARIAL, size=10)
                c.alignment = Alignment(wrap_text=True, vertical="top")
            krow += 1
        add_lists(ws, cols, 2, len(ids) + 2)
        ws.cell(row=1, column=cols.index("Answer") + 1).comment = Comment(
            "Fill in Answer to Notes for each row. See the yellow example row.", "Nick")
    for p in (out, key_out):
        Path(p).parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    key.save(key_out)
    print(f"wrote {out} and {key_out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--batch", action="append", required=True, help='"Sheet name=task-1,task-2,..." (repeatable)')
    ap.add_argument("--qc", default="", help="comma-separated task ids that are quality checks (marked in the key only)")
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--out", required=True)
    ap.add_argument("--key", required=True)
    a = ap.parse_args()
    batches = []
    for spec in a.batch:
        name, ids = spec.split("=", 1)
        batches.append((name.strip(), [i.strip() for i in ids.split(",") if i.strip()]))
    build(batches, set(filter(None, a.qc.split(","))), a.seed, a.out, a.key)


if __name__ == "__main__":
    main()
