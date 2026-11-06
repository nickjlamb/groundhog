"""The fixed tool surface every model sees (design spec section 2).

PubCrawl tools are external and recorded/replayed. Redacta tools are local
and deterministic, so they run live in both record and replay mode.
submit_answer ends the episode with a typed final answer (spec section 4).
"""

import json
from pathlib import Path

SPECS = Path(__file__).resolve().parent / "tool_specs"

PUBCRAWL_TOOLS = [
    "search_pubmed", "get_abstract", "get_full_text", "format_citation", "get_smpc",
    "get_uspi", "compare_labels", "resolve_drug_name", "search_trials", "get_trial",
]
REDACTA_TOOLS = ["protect", "redact", "reinstate", "check_output"]
EXTERNAL = frozenset(PUBCRAWL_TOOLS)
LOCAL = frozenset(REDACTA_TOOLS)
PAGED = frozenset({"get_smpc", "get_uspi"})   # label sections are paged by the replay layer

SUBMIT_ANSWER = {
    "name": "submit_answer",
    "description": (
        "Submit your final answer. Call this exactly once, when you are done. "
        "Fill the fields that apply to the question and always give a rationale "
        "that cites the evidence you relied on."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "value": {"type": "string", "description": "The answer value (a dose, threshold, endpoint and result, or short answer)."},
            "unit": {"type": "string", "description": "Unit for value, if any."},
            "pmid": {"type": "string", "description": "PubMed ID, for citation questions."},
            "verdict": {"type": "string", "enum": ["supported", "partial", "unsupported"], "description": "For claim-checking questions."},
            "abstain": {"type": "boolean", "description": "True if the requested information is not available in any source you could access."},
            "conflict": {"type": "boolean", "description": "True if sources disagree on the requested figure."},
            "rationale": {"type": "string", "description": "Explanation citing the sources and figures relied on."},
        },
        "required": ["rationale"],
    },
}


def _pubcrawl():
    data = json.loads((SPECS / "pubcrawl_live_2.8.0.json").read_text())
    by_name = {t["name"]: t for t in data["tools"]}
    missing = [n for n in PUBCRAWL_TOOLS if n not in by_name]
    if missing:
        raise RuntimeError(f"PubCrawl spec is missing tools: {missing}")
    return [by_name[n] for n in PUBCRAWL_TOOLS]


def _redacta():
    data = json.loads((SPECS / "redacta.json").read_text())
    by_name = {t["name"]: t for t in data["tools"]}
    return [by_name[n] for n in REDACTA_TOOLS]


def load_tools() -> list[dict]:
    """Tool definitions in a neutral form: name, description, input_schema."""
    out = []
    for t in _pubcrawl() + _redacta() + [SUBMIT_ANSWER]:
        out.append({"name": t["name"], "description": t.get("description", ""), "input_schema": t["inputSchema"]})
    return out


def server_of(tool: str) -> str:
    if tool in EXTERNAL:
        return "pubcrawl"
    if tool in LOCAL:
        return "redacta"
    if tool == "submit_answer":
        return "harness"
    raise KeyError(tool)
