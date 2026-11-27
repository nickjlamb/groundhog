"""Compare a returned annotation workbook with the gold answers.

    python scripts/agreement.py --returned "annotation/groundhog-v2-batch1_KD.xlsx" \
        --key annotation/groundhog-v2-batch1-KEY-nick-only.xlsx --out annotation/batch1-agreement.xlsx

    # grading workbook (AI answers): compares with Nick's and the judge's grades
    python scripts/agreement.py --grading --returned annotation/groundhog-v2-grading_KD.xlsx \
        --key annotation/groundhog-v2-grading-KEY-nick-only.xlsx --out annotation/grading-agreement.xlsx

Task workbooks. For each item the annotator's columns are read as an answer and
scored with the benchmark's own outcome scorer (scoring/outcome.py), which
gives a first-pass match: yes, no, or "read it" (comparisons, and anything the
scorer can't decide). Three labels are also compared directly, with Cohen's
kappa: the claim-check verdict, "Not available?" (against abstain gold) and
"Sources disagree?" (against conflict gold). Everything that is not a clean
match goes on the To adjudicate sheet, for Nick to read: a mismatch from the
scorer is a reason to look, not a verdict, because people write answers
differently from agents.

Grading workbooks. Yes/No grades are compared with Nick's and with the judge's
(agreement and kappa); Unsure counts as a disagreement and is listed.

Held-out tasks are read from GROUNDHOG_PRIVATE, as with the workbook script.
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from harness.taskset import by_id  # noqa: E402
from scoring.outcome import score_episode  # noqa: E402
from annotation_workbook import ARIAL, HEAD, THIN  # noqa: E402

VERDICT = {"supported": "supported", "partially supported": "partial", "unsupported": "unsupported"}
PINK = PatternFill("solid", fgColor="FBE3E8")


def kappa(pairs):
    """Cohen's kappa for a list of (a, b) labels. None if undefined."""
    pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
    n = len(pairs)
    if not n:
        return None
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / n ** 2
    return None if pe == 1 else (po - pe) / (1 - pe)


def fmt_k(k):
    return "n/a (no variation)" if k is None else f"{k:.2f}"


def sheet_rows(path, skip=("Read me",)):
    wb = load_workbook(path, data_only=True)
    out = []
    for ws in wb.worksheets:
        if ws.title in skip:
            continue
        head = [str(c.value or "").strip() for c in ws[1]]
        for r in ws.iter_rows(min_row=2, values_only=True):
            d = dict(zip(head, r))
            if d.get("Item") and str(d["Item"]).strip() != "Ex":
                out.append({k: ("" if v is None else str(v).strip()) for k, v in d.items()})
    return out


def as_answer(task, d):
    """The annotator's columns as an agent-style answer."""
    na = d.get("Not available?", "").lower()
    v = VERDICT.get(d.get("Verdict", "").lower())
    rationale = " ".join(x for x in (d.get("Evidence", ""), d.get("Notes", "")) if x)
    ans = {"value": d.get("Answer", ""), "rationale": rationale}
    if v:
        ans["verdict"] = v
    if task.get("answer_type") == "abstain":
        ans = {"abstain": na.startswith("yes"), "value": "", "rationale": d.get("Answer", "") + " " + rationale}
    if task.get("answer_type") == "conflict":
        ans["conflict"] = d.get("Sources disagree?", "").lower().startswith("yes")
    return ans


def expected_na(task):
    return {"abstain": "all", "partial_abstain": "part"}.get(task.get("answer_type"), "no")


def got_na(d):
    s = d.get("Not available?", "").lower()
    return None if not s else "all" if "all" in s else "part" if "part" in s else "no" if s.startswith("no") else "all"


def compare_tasks(returned, key_path):
    tasks = by_id()
    key = {r["Item"]: r for r in sheet_rows(key_path, skip=())}
    rows, todo = [], []
    for d in sheet_rows(returned):
        k = key.get(d["Item"])
        if not k:
            sys.exit(f"{d['Item']} is not in the key")
        t = tasks[k["Task"]]
        res = score_episode(t, {"status": "submitted", "answer": as_answer(t, d), "steps": []})
        match = {True: "yes", False: "no", None: "read it"}[res["correct"]]
        gv = (t.get("gold") or {}).get("verdict")
        kv = VERDICT.get(d.get("Verdict", "").lower())
        gc = (t.get("gold") or {}).get("conflict") if t.get("answer_type") == "conflict" else False
        gc = None if gc == "either" else bool(gc)      # "either": both flags count as agreement
        kc = d.get("Sources disagree?", "").lower().startswith("yes") if d.get("Sources disagree?") else None
        row = {"Item": d["Item"], "Task": k["Task"], "QC": k.get("Quality check") or "", "Answer type": t.get("answer_type"),
               "Auto match": match, "Scorer notes": "; ".join(res["notes"]),
               "Verdict (gold / KD)": f"{gv} / {kv}" if gv else "",
               "Not available (gold / KD)": f"{expected_na(t)} / {got_na(d)}",
               "Sources disagree (gold / KD)": f"{'either' if gc is None else 'yes' if gc else 'no'} / {'' if kc is None else 'yes' if kc else 'no'}",
               "KD answer": d.get("Answer", ""), "KD evidence": d.get("Evidence", ""),
               "Gold": k.get("Gold", ""), "Confidence": d.get("Confidence", ""), "Flag": d.get("Flag", ""),
               "Minutes": d.get("Minutes", ""), "KD notes": d.get("Notes", ""),
               "_v": (gv, kv) if gv else None, "_na": (expected_na(t) != "no", None if got_na(d) is None else got_na(d) != "no"),
               "_na3": (expected_na(t), got_na(d)), "_c": (gc, kc)}
        reasons = []
        if match != "yes":
            reasons.append(f"auto match: {match}")
        if gv and kv != gv:
            reasons.append("verdict differs")
        if row["_na"][1] is not None and row["_na"][0] != row["_na"][1]:
            reasons.append("not-available flag differs")
        elif row["_na3"][1] and row["_na3"][0] != row["_na3"][1]:
            reasons.append("part/all differs")
        if kc is not None and gc is not None and kc != gc:
            reasons.append("sources-disagree flag differs")
        if d.get("Flag", "").lower() not in ("", "none"):
            reasons.append(f"flagged: {d['Flag']}")
        if d.get("Confidence", "").lower() == "low":
            reasons.append("low confidence")
        row["Why look"] = "; ".join(reasons)
        rows.append(row)
        if reasons:
            todo.append(row)
    mins = [float(r["Minutes"]) for r in rows if r["Minutes"].replace(".", "", 1).isdigit()]
    qc = [r for r in rows if r["QC"]]
    summary = [
        ("Items", len(rows)),
        ("Auto match: yes / no / read it", "{yes} / {no} / {read}".format(**{"yes": 0, "no": 0, "read": 0, **{
            ("read" if k == "read it" else k): v for k, v in Counter(r["Auto match"] for r in rows).items()}})),
        ("Claim-check verdicts agreeing", f"{sum(a == b for a, b in (r['_v'] for r in rows if r['_v']))} of {sum(1 for r in rows if r['_v'])}"),
        ("Kappa, verdict (3 labels)", fmt_k(kappa([r["_v"] for r in rows if r["_v"]]))),
        ("Kappa, not available (yes/no)", fmt_k(kappa([r["_na"] for r in rows]))),
        ("Kappa, sources disagree (yes/no)", fmt_k(kappa([r["_c"] for r in rows]))),
        ("Quality-check items matching", f"{sum(r['Auto match'] == 'yes' for r in qc)} of {len(qc)}" if qc else "none in this batch"),
        ("Items flagged by KD", sum(1 for r in rows if r["Flag"].lower() not in ("", "none"))),
        ("Minutes: total / median", f"{sum(mins):.0f} / {sorted(mins)[len(mins) // 2]:.0f}" if mins else "not given"),
        ("Items to adjudicate", len(todo)),
        ("", ""),
        ("Notes", "Auto match runs the benchmark's outcome scorer on KD's columns. 'no' and 'read it' are reasons to read the "
                  "item, not verdicts: a correct human answer can miss a scorer pattern. Kappa on one batch is unstable "
                  "with few items; the paper pools all batches."),
    ]
    cols = ["Item", "Task", "QC", "Answer type", "Auto match", "Why look", "Verdict (gold / KD)", "Not available (gold / KD)",
            "Sources disagree (gold / KD)", "Scorer notes", "KD answer", "KD evidence", "Gold", "Confidence", "Flag", "Minutes", "KD notes"]
    return summary, cols, rows, todo


def compare_grading(returned, key_path):
    key = {r["Item"]: r for r in sheet_rows(key_path, skip=())}
    rows, todo = [], []
    for d in sheet_rows(returned):
        k = key[d["Item"]]
        g = d.get("Grade", "")
        row = {"Item": d["Item"], "Calibration id": k["Calibration id"], "Task": k["Task"], "Kind": k["Kind"],
               "KD": g, "Nick": k["Nick"], "Judge": k["Judge"], "Confidence": d.get("Confidence", ""),
               "Minutes": d.get("Minutes", ""), "KD notes": d.get("Notes", ""), "Judge's reason": k.get("Judge's reason", "")}
        reasons = [f"differs from {who}" for who in ("Nick", "Judge") if g != k[who]]
        if g not in ("Yes", "No"):
            reasons = ["no Yes/No grade" if not g else f"graded {g}"]
        row["Why look"] = "; ".join(reasons)
        rows.append(row)
        if reasons:
            todo.append(row)
    yn = [r for r in rows if r["KD"] in ("Yes", "No")]

    def agree(who, sub=yn):
        return f"{sum(r['KD'] == r[who] for r in sub)} of {len(sub)}"
    mins = [float(r["Minutes"]) for r in rows if r["Minutes"].replace(".", "", 1).isdigit()]
    summary = [("Items", len(rows)), ("Graded Yes or No", len(yn)),
               ("KD agrees with Nick", agree("Nick")), ("Kappa, KD vs Nick", fmt_k(kappa([(r["KD"], r["Nick"]) for r in yn]))),
               ("KD agrees with the judge", agree("Judge")), ("Kappa, KD vs judge", fmt_k(kappa([(r["KD"], r["Judge"]) for r in yn]))),
               ("Nick agrees with the judge (v1)", f"{sum(r['Nick'] == r['Judge'] for r in rows)} of {len(rows)}"),
               ("Single criterion: KD agrees with Nick", agree("Nick", [r for r in yn if r["Kind"] == "Single criterion"])),
               ("US/UK comparison: KD agrees with Nick", agree("Nick", [r for r in yn if r["Kind"] != "Single criterion"])),
               ("Minutes: total / median", f"{sum(mins):.0f} / {sorted(mins)[len(mins) // 2]:.0f}" if mins else "not given"),
               ("Items to adjudicate", len(todo))]
    cols = ["Item", "Calibration id", "Task", "Kind", "KD", "Nick", "Judge", "Why look", "Confidence", "Minutes", "KD notes", "Judge's reason"]
    return summary, cols, rows, todo


def write(out, summary, cols, rows, todo):
    wb = Workbook()
    s = wb.active
    s.title = "Summary"
    for i, (a, b) in enumerate(summary, 1):
        s.cell(row=i, column=1, value=a).font = Font(name=ARIAL, size=10, bold=True)
        c = s.cell(row=i, column=2, value=b)
        c.font = Font(name=ARIAL, size=10)
        c.alignment = Alignment(wrap_text=True, vertical="top")
    s.column_dimensions["A"].width, s.column_dimensions["B"].width = 38, 90
    wide = {"Why look": 34, "Scorer notes": 34, "KD answer": 45, "KD evidence": 45, "Gold": 45, "KD notes": 30, "Judge's reason": 60}
    for name, data in (("To adjudicate", todo), ("All items", rows)):
        ws = wb.create_sheet(name)
        for j, h in enumerate(cols, 1):
            c = ws.cell(row=1, column=j, value=h)
            c.font, c.fill, c.border = Font(name=ARIAL, bold=True, color="FFFFFF", size=10), HEAD, THIN
            c.alignment = Alignment(wrap_text=True, vertical="center")
            ws.column_dimensions[c.column_letter].width = wide.get(h, 13)
        if name == "To adjudicate":
            j = len(cols) + 1
            c = ws.cell(row=1, column=j, value="Nick's ruling")
            c.font, c.fill = Font(name=ARIAL, bold=True, size=10), PINK
            ws.column_dimensions[c.column_letter].width = 40
        for i, r in enumerate(data, 2):
            for j, h in enumerate(cols, 1):
                c = ws.cell(row=i, column=j, value=r.get(h, ""))
                c.font, c.border = Font(name=ARIAL, size=10), THIN
                c.alignment = Alignment(wrap_text=True, vertical="top")
            if name == "To adjudicate":
                ws.cell(row=i, column=len(cols) + 1).fill = PINK
        ws.freeze_panes = "C2"
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--returned", required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--grading", action="store_true")
    a = ap.parse_args()
    summary, cols, rows, todo = (compare_grading if a.grading else compare_tasks)(a.returned, a.key)
    write(a.out, summary, cols, rows, todo)
    for k, v in summary:
        if k and k != "Notes":
            print(f"{k}: {v}")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
