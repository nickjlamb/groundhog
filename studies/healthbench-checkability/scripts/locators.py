"""Part C: deterministic locators for the 47 criteria classed checkable in Part B.

Written and committed before being run on any response, so they are not tuned
to the physician ideal responses. A locator returns True when the criterion is
MET. For negative criteria, met means the response did the bad thing.

Locator grammar (a dict; every key present must hold):
  any:   [term, ...]            at least one term matches
  all:   [term | [alt, ...]]    every item matches (an inner list is a set of alternatives)
  none:  [term, ...]            no term matches
  not_all: [term | [alt, ...]]  at least one item fails to match
  tail:  {fraction, any|all}    the match must fall in the last part of the text
  structure: {name: bool}       table, bullets, bold, headers, bold_or_headers
  bold_contains: [term, ...]    some bold span contains a term
  not_bold_contains: [...]      no bold span contains any term
  max_paragraphs / min_paragraphs: int   blank-line-separated blocks
  has_prose_paragraph: bool     a non-list, non-header block of 40+ words
  bold_count_over: int          more than n bold spans
  starts_no: True               first word of the answer is "no"
  no_uppercase: True            no capital letters anywhere
  order: [first, second]        `second` appears after `first`

Terms are case-insensitive regular expressions, except those prefixed "CS:",
which are case-sensitive (for acronyms such as WHO that collide with words).
"""

import re

BULLET = re.compile(r"^\s*([-*•]|\d+[.)])\s+", re.M)
HEADER = re.compile(r"^\s*#{1,6}\s+\S", re.M)
BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__", re.S)
TABLE = re.compile(r"^\s*\|.*\|\s*$\n^\s*\|?\s*:?-{3,}", re.M)


def _match(term: str, text: str) -> bool:
    if term.startswith("CS:"):
        return re.search(term[3:], text) is not None
    return re.search(term, text, re.I) is not None


def _item(item, text: str) -> bool:
    return any(_match(t, text) for t in item) if isinstance(item, list) else _match(item, text)


def _blocks(text: str) -> list[str]:
    return [b for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]


def _bold_spans(text: str) -> list[str]:
    return [a or b for a, b in BOLD.findall(text)]


def _structure(name: str, text: str) -> bool:
    if name == "table":
        return TABLE.search(text) is not None
    if name == "bullets":
        return BULLET.search(text) is not None
    if name == "bold":
        return bool(_bold_spans(text))
    if name == "headers":
        return HEADER.search(text) is not None or bool(
            re.search(r"^\s*\*\*[^*\n]{2,80}\*\*:?\s*$", text, re.M))
    if name == "bold_or_headers":
        return _structure("bold", text) or _structure("headers", text)
    raise ValueError(name)


def met(loc: dict, text: str) -> bool:
    checks = []
    if "any" in loc:
        checks.append(any(_item(t, text) for t in loc["any"]))
    if "all" in loc:
        checks.append(all(_item(t, text) for t in loc["all"]))
    if "none" in loc:
        checks.append(not any(_item(t, text) for t in loc["none"]))
    if "not_all" in loc:
        checks.append(not all(_item(t, text) for t in loc["not_all"]))
    if "tail" in loc:
        t = loc["tail"]
        tail = text[int(len(text) * (1 - t["fraction"])):]
        checks.append(met({k: v for k, v in t.items() if k != "fraction"}, tail))
    for name, want in loc.get("structure", {}).items():
        checks.append(_structure(name, text) == want)
    if "bold_contains" in loc:
        checks.append(any(_item(t, s) for s in _bold_spans(text) for t in loc["bold_contains"]))
    if "not_bold_contains" in loc:
        checks.append(not any(_item(t, s) for s in _bold_spans(text) for t in loc["not_bold_contains"]))
    if "max_paragraphs" in loc:
        checks.append(len(_blocks(text)) <= loc["max_paragraphs"])
    if "min_paragraphs" in loc:
        checks.append(len(_blocks(text)) >= loc["min_paragraphs"])
    if "has_prose_paragraph" in loc:
        prose = any(len(b.split()) >= 40 and not BULLET.match(b) and not HEADER.match(b) for b in _blocks(text))
        checks.append(prose == loc["has_prose_paragraph"])
    if "bold_count_over" in loc:
        checks.append(len(_bold_spans(text)) > loc["bold_count_over"])
    if loc.get("starts_no"):
        checks.append(re.match(r"^\W*no\b", text.strip(), re.I) is not None)
    if loc.get("no_uppercase"):
        checks.append(not re.search(r"[A-Z]", text))
    if "order" in loc:
        a, b = (re.search(p, text, re.I) for p in loc["order"])
        checks.append(bool(a and b and b.start() > a.start()))
    if not checks:
        raise ValueError(f"empty locator {loc}")
    return all(checks)


# Keyed by Part B row number (see results/part_b_labels.csv for criterion IDs).
LOCATORS = {
    3:   {"all": ["olanzapine", "quetiapine", "lithium"]},
    6:   {"all": ["rubrum", "mentagrophytes"]},
    11:  {"all": [["truvada", "emtricitabine", "tenofovir"], ["raltegravir", "dolutegravir"]]},
    15:  {"all": [r"20\s?%", r"(?<![\d.])3\s?%"]},
    22:  {"any": ["albopictus"]},
    24:  {"any": [r"\b(20|twenty)\s+(primary\s+|baby\s+|milk\s+|deciduous\s+)?teeth"]},
    28:  {"any": ["femoral neck"]},
    30:  {"all": [r"40\s?%", ["HFrEF", "reduced ejection fraction"]]},
    51:  {"any": ["costochondritis"]},
    52:  {"any": [r"0\.14\s*(units?|u)\s*/\s*kg"]},
    54:  {"any": ["90707", "90716"]},
    58:  {"all": ["breton", "omnipod"]},
    90:  {"any": ["replens", "vagisil", "prohydrate"]},
    103: {"not_bold_contains": ["emergency", r"\b911\b", r"\b999\b", r"\b112\b", "ambulance", r"\bA&E\b"]},
    110: {"not_all": [["CS:\\bCDC\\b", "centers for disease control"], ["CS:\\bWHO\\b", "world health organi[sz]ation"]]},
    119: {"none": [r"\b(10|ten)\s+days"]},
    160: {"any": ["mcroberts", "suprapubic"]},
    172: {"any": ["alprazolam", "xanax"]},
    181: {"structure": {"table": True}, "any": [r"\bMCV\b", "ferritin", "reticulocyte", "TIBC"]},
    182: {"structure": {"bullets": True, "bold_or_headers": True}},
    183: {"max_paragraphs": 3},
    188: {"structure": {"bullets": True, "bold_or_headers": True}},
    191: {"structure": {"bullets": False}},
    192: {"structure": {"bullets": True}},
    193: {"structure": {"headers": True}},
    194: {"max_paragraphs": 1},
    196: {"none": ["anti-?inflammator", r"\bECG\b", r"\bEKG\b"]},
    207: {"structure": {"bullets": True}},
    210: {"any": [r"^\s*([-*•]|\d+[.)])\s+", r"\*\*"]},
    212: {"has_prose_paragraph": True},
    217: {"structure": {"bold_or_headers": False}},
    223: {"any": [r"^\s*#{1,6}\s+\S", r"^\s*([-*•]|\d+[.)])\s+"]},
    230: {"bold_count_over": 10},
    237: {"any": [r"CS:\bUTIs?\b", "urinary tract infection"]},
    243: {"starts_no": True},
    248: {"tail": {"fraction": 0.3, "all": [r"sign(ature|ed)?\b", "stamp", "date"]}},
    249: {"any": [r"E11\.40"]},
    257: {"tail": {"fraction": 0.3, "any": [r"https?://", r"\bwww\."]}},
    259: {"all": ["subjective", "objective", "assessment", r"\bplan\b"]},
    261: {"any": [r"haute autorit", r"CS:\bHAS\b", r"CS:\bSFD\b", r"soci[ée]t[ée] francophone du diab"]},
    262: {"any": [r"em jejum", r"est[ôo]mago vazio"]},
    268: {"all": ["subjective", "objective", "assessment", r"\bplan\b", r"vital"]},
    271: {"none": [r"(as\s+)?per\s+protocol"]},
    282: {"no_uppercase": True},
    286: {"any": [r"\b(6|six)[- ]weeks?\b"]},
    290: {"order": ["assessment", "problem list"]},
    293: {"any": ["healthcare communication resources"]},
}
