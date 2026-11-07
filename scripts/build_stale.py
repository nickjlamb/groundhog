"""Build F4 'stale' cassette variants from archived DailyMed SPL versions.

Each stale entry mirrors a recorded current entry (same tool and arguments) but
its US label content comes from an archived label version, in PubCrawl's
response shape. Sources are kept in cassettes/archive_sources/.

    python scripts/build_stale.py
"""
import copy
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from harness.cassette import Cassette          # noqa: E402
from harness.paging import select_sections     # noqa: E402

NS = {"v3": "urn:hl7-org:v3"}
TITLES = {"34066-1": "Boxed Warning", "34067-9": "Indications and Usage", "34068-7": "Dosage and Administration",
          "43678-2": "Dosage Forms and Strengths", "34070-3": "Contraindications", "43685-7": "Warnings and Precautions",
          "34071-1": "Warnings", "42232-9": "Precautions", "34084-4": "Adverse Reactions", "34073-7": "Drug Interactions",
          "42228-7": "Use in Specific Populations", "34088-5": "Overdosage", "34090-1": "Clinical Pharmacology",
          "34089-3": "Description", "34069-5": "How Supplied"}

SOURCES = {
    # task: (archived SPL file, setid, version, published date)
    "cmp-004": ("codeine-sulfate_5819bdf7_v9_20170217.xml", "5819bdf7-300e-45b8-8f3a-447b53656293", "9", "Feb 27, 2017"),
    "cmp-002": ("metformin_0ff1ba75_v11_20131230.xml", "0ff1ba75-3c86-4baf-a6b1-1bb883839866", "11", "Dec 31, 2013"),
}


def spl_sections(path):
    root = ET.parse(path).getroot()
    title = " ".join("".join(root.find("v3:title", NS).itertext()).split()) if root.find("v3:title", NS) is not None else ""
    out = []
    for sec in root.findall("v3:component/v3:structuredBody/v3:component/v3:section", NS):
        code = sec.find("v3:code", NS)
        c = code.get("code") if code is not None else ""
        if c not in TITLES:
            continue
        text = " ".join(" ".join(sec.itertext()).split())
        out.append({"code": c, "title": TITLES[c], "content": text})
    return title, out


def main():
    for task, (fname, setid, ver, date) in SOURCES.items():
        title, secs = spl_sections(ROOT / "cassettes/archive_sources" / fname)
        cas = Cassette(task, ROOT / "cassettes")
        cas.data["entries"] = [e for e in cas.data["entries"] if e.get("variant", "current") != "stale"]
        current = [e for e in cas.data["entries"] if e["tool"] in ("get_uspi", "compare_labels")]
        by_code = {s["code"]: s for s in secs}
        src = f"dailymed-archive {setid} v{ver} ({date})"
        url = f"https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid={setid}&version={ver}"
        for e in current:
            if e["tool"] == "get_uspi":
                whole = {"drug_name": e["response"].get("drug_name", ""), "setid": setid, "spl_version": ver,
                         "published_date": date, "sections": copy.deepcopy(secs), "dailymed_url": url}
                resp = select_sections(whole, e["args"].get("sections")) if e["args"].get("sections") else whole
            else:
                resp = copy.deepcopy(e["response"])
                for c in resp.get("comparisons", []):
                    us = c.get("us_section") or {}
                    if us.get("code") in by_code:
                        c["us_section"] = copy.deepcopy(by_code[us["code"]])
                    elif us.get("code") == "43685-7" and "34071-1" in by_code:      # old-format labels: Warnings
                        c["us_section"] = copy.deepcopy(by_code["34071-1"])
                resp["us_source"] = url
            cas.add(e["tool"], e["args"], resp, recorded_by=src, variant="stale")
        cas.save()
        n = sum(1 for e in cas.data["entries"] if e.get("variant") == "stale")
        print(f"{task}: {n} stale entries from {src}; sections {[s['code'] for s in secs]}")


if __name__ == "__main__":
    main()
