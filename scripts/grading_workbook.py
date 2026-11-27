"""Build the grading workbook for the second annotator (30 v1 AI answers), plus Nick's key.

    python scripts/grading_workbook.py --out annotation/groundhog-v2-grading.xlsx \
        --key annotation/groundhog-v2-grading-KEY-nick-only.xlsx

Source: review/judge_calibration.xlsx (the items Nick graded in v1) and
review/judge_calibration_results.json (Nick's and the judge's verdicts). The
annotator's workbook carries neither grade, no model names and no task ids:
items get neutral codes (G-01 ...) and are shuffled with a fixed seed. The key
maps each code to its calibration id and task and gives both grades.
"""

import argparse
import json
import random
import sys
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from annotation_workbook import ARIAL, GREY, YELLOW, HEAD, THIN  # noqa: E402

GIVEN = ["Item", "Kind", "What to judge", "Question the AI was asked", "Reference answer", "AI answer"]
FILL = ["Grade", "Confidence", "Minutes", "Notes"]
WIDTH = {"Item": 7, "Kind": 14, "What to judge": 38, "Question the AI was asked": 45, "Reference answer": 50,
         "AI answer": 70, "Grade": 10, "Confidence": 11, "Minutes": 9, "Notes": 30}
LISTS = {"Grade": ["Yes", "No", "Unsure"], "Confidence": ["High", "Medium", "Low"]}
EXAMPLE = {"Item": "Ex", "Kind": "Single criterion",
           "What to judge": "EXAMPLE (not an item). Does the answer meet this criterion?\n\nCriterion: Gives the 95% confidence interval",
           "Question the AI was asked": "What was the primary result of trial X?",
           "Reference answer": "HR 0.80 (95% CI 0.70 to 0.91)",
           "AI answer": "The hazard ratio was 0.80 (P<0.001).",
           "Grade": "No", "Confidence": "High", "Minutes": 1,
           "Notes": "No CI given. Grade only the criterion: the HR being right doesn't matter here."}


def tidy_reference(text):
    """'Gold answer: {json}' becomes 'key: value' lines; other text is kept."""
    t = str(text or "").strip()
    if t.startswith("Gold answer:"):
        body = t[len("Gold answer:"):].strip()
        try:
            g = json.loads(body)
            if isinstance(g, dict):
                return "\n".join(f"{k}: {' '.join(str(v).split())}" for k, v in g.items())
        except ValueError:
            pass
        return body
    return t


def kind(what):
    return "US/UK comparison" if what.startswith("Is the answer correct for the US label") else "Single criterion"


def header(ws, cols, width):
    for i, name in enumerate(cols, 1):
        c = ws.cell(row=1, column=i, value=name)
        c.font = Font(name=ARIAL, bold=True, color="FFFFFF", size=10)
        c.fill, c.border = HEAD, THIN
        c.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[c.column_letter].width = width.get(name, 14)
    ws.row_dimensions[1].height = 30


def row(ws, r, values, cols, example=False):
    for i, name in enumerate(cols, 1):
        c = ws.cell(row=r, column=i, value=values.get(name, ""))
        c.font = Font(name=ARIAL, size=10, italic=example, color="6B7B8D" if example else "000000")
        c.alignment = Alignment(wrap_text=True, vertical="top")
        c.border = THIN
        if name in GIVEN:
            c.fill = GREY
        elif example:
            c.fill = YELLOW


def build(src, results, seed, out, key_out):
    ws_in = load_workbook(src)["Grade these"]
    head = [c.value for c in ws_in[1]]
    items = [dict(zip(head, r)) for r in ws_in.iter_rows(min_row=2, values_only=True) if r[0]]
    res = {i["id"]: i for i in json.load(open(results))["items"]}
    random.Random(seed).shuffle(items)

    wb = Workbook()
    rd = wb.active
    rd.title = "Read me"
    for i, (text, bold) in enumerate([
        ("Groundhog v2: grading AI answers", True), ("", False),
        ("30 items from version 1. Each gives a question an AI agent was asked, the reference answer, the agent's answer,", False),
        ("and one yes/no question in 'What to judge'. Grey columns are given; fill in Grade to Notes.", False),
        ("Single criterion (16): Yes if the answer meets the criterion. Some criteria describe a mistake: Yes means the mistake is there.", False),
        ("US/UK comparison (14): Yes only if the US answer, the UK answer and the 'do they differ' call are all right.", False),
        ("Judge only what's asked, not the answer as a whole. Grade the substance, not the wording or which field it sits in.", False),
        ("Take the reference answer as correct; if you think it's wrong, grade anyway and say so in Notes.", False),
        ("The yellow row is a worked example, not an item. Use Unsure sparingly, with a note.", False),
        ("No AI tools. Full instructions: the annotator briefing (Grading AI answers).", False), ("", False),
        ("When you're done, save and email the workbook back.", False)], 1):
        c = rd.cell(row=i, column=1, value=text)
        c.font = Font(name=ARIAL, size=12 if bold else 10, bold=bold)
    rd.column_dimensions["A"].width = 120

    ws = wb.create_sheet("Grade these")
    cols = GIVEN + FILL
    header(ws, cols, WIDTH)
    ws.freeze_panes = "C2"
    row(ws, 2, EXAMPLE, cols, example=True)

    key = Workbook()
    ks = key.active
    ks.title = "Key"
    kcols = ["Item", "Calibration id", "Task", "Kind", "Nick", "Judge", "Judge's reason"]
    header(ks, kcols, {"Item": 7, "Calibration id": 12, "Task": 14, "Kind": 16, "Nick": 8, "Judge": 8, "Judge's reason": 90})
    yn = {True: "Yes", False: "No", None: ""}
    for n, it in enumerate(items, 1):
        code = f"G-{n:02d}"
        what = str(it["What to judge"])
        row(ws, n + 2, {"Item": code, "Kind": kind(what), "What to judge": what,
                        "Question the AI was asked": it["Question the model was asked"],
                        "Reference answer": tidy_reference(it["Reference (gold)"]),
                        "AI answer": it["Model's answer"]}, cols)
        r = res[it["ID"]]
        if yn[r["human"]] != it["Your verdict"]:
            sys.exit(f"{it['ID']}: grade in the workbook ({it['Your verdict']}) and results file ({r['human']}) differ")
        for k, v in zip(kcols, (code, it["ID"], it["Task"], kind(what), yn[r["human"]], yn[r["judge"]], r.get("reason", ""))):
            c = ks.cell(row=n + 1, column=kcols.index(k) + 1, value=v)
            c.font = Font(name=ARIAL, size=10)
            c.alignment = Alignment(wrap_text=True, vertical="top")
    for name, opts in LISTS.items():
        col = ws.cell(row=1, column=cols.index(name) + 1).column_letter
        dv = DataValidation(type="list", formula1='"' + ",".join(opts) + '"', allow_blank=True)
        dv.add(f"{col}2:{col}{len(items) + 2}")
        ws.add_data_validation(dv)
    for p in (out, key_out):
        Path(p).parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    key.save(key_out)
    print(f"wrote {out} ({len(items)} items) and {key_out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(ROOT / "review/judge_calibration.xlsx"))
    ap.add_argument("--results", default=str(ROOT / "review/judge_calibration_results.json"))
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--out", required=True)
    ap.add_argument("--key", required=True)
    a = ap.parse_args()
    build(a.src, a.results, a.seed, a.out, a.key)


if __name__ == "__main__":
    main()
