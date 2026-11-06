"""Page label sections the way PubCrawl >= 2.7.1 does (truncated / total_chars / next_offset).

Cassettes store full sections; the replay layer serves the page the agent
asked for, so F3 can move the answer past the first page.
"""

import copy

DEFAULT_MAX_CHARS = 6000


def select_sections(response: dict, wanted) -> dict:
    """Filter a full-label response to the requested sections (numbers like '4.2'
    or names like 'posology'), as PubCrawl does for its sections argument."""
    if not wanted:
        return response
    wanted = [str(w).lower().strip() for w in wanted]
    out = copy.deepcopy(response)
    keep = []
    for sec in out.get("sections", []) or []:
        code, title = str(sec.get("code", "")).lower(), str(sec.get("title", "")).lower()
        if any(w == code or (w and w in title) for w in wanted):
            keep.append(sec)
    out["sections"] = keep
    return out


def page_response(response: dict, max_chars=None, offset=None, first_page_cut=None) -> dict:
    """Return a copy of a label response with every section paged.

    first_page_cut, if given, maps section codes to a shorter first page
    (offset 0) for those sections only; used by fault F3.
    """
    max_chars = int(max_chars or DEFAULT_MAX_CHARS)
    offset = int(offset or 0)
    out = copy.deepcopy(response)
    for sec in out.get("sections", []) or []:
        full = sec.get("content", "")
        size = max_chars
        if offset == 0 and first_page_cut and sec.get("code") in first_page_cut:
            size = min(size, first_page_cut[sec.get("code")])
        page = full[offset:offset + size]
        for k in ("truncated", "total_chars", "next_offset", "offset"):
            sec.pop(k, None)
        sec["content"] = page
        if offset:
            sec["offset"] = offset
        if offset + size < len(full):
            sec["truncated"] = True
            sec["total_chars"] = len(full)
            sec["next_offset"] = offset + size
    return out
