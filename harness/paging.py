"""Page label sections the way PubCrawl >= 2.7.1 does (truncated / total_chars / next_offset).

Cassettes store full sections; the replay layer serves the page the agent
asked for, so F3 can move the answer past the first page.
"""

import copy

DEFAULT_MAX_CHARS = 6000


def page_response(response: dict, max_chars=None, offset=None, first_page_cut=None) -> dict:
    """Return a copy of a label response with every section paged.

    first_page_cut, if given, caps the first page (offset 0) at that many
    characters; used by fault F3.
    """
    max_chars = int(max_chars or DEFAULT_MAX_CHARS)
    offset = int(offset or 0)
    out = copy.deepcopy(response)
    for sec in out.get("sections", []) or []:
        full = sec.get("content", "")
        size = max_chars
        if offset == 0 and first_page_cut is not None:
            size = min(size, first_page_cut)
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
