"""Small, deterministic stand-in for a literature search engine.

Queries follow PubMed conventions closely enough for agents: space-separated
terms are ANDed, AND / OR / NOT (upper case) and parentheses work, "quoted
phrases" must appear in order, a trailing * is a prefix wildcard, and field
tags such as [tiab] or [au] are accepted but searched across all fields.
Matching documents are ranked by BM25. Automatic term mapping (MeSH synonyms)
is not modelled; that is the main way this is stricter than PubMed.
"""

import math
import re
from collections import Counter

STOPWORDS = {"a", "an", "the", "of", "in", "and", "or", "with", "for", "on", "to", "by", "at", "from",
             "vs", "versus", "is", "are", "was", "were", "as", "be", "its", "their", "this", "that"}


def stem(tok: str) -> str:
    if len(tok) > 4 and tok.endswith("ies"):
        return tok[:-3] + "y"
    if len(tok) > 3 and tok.endswith("s") and not tok.endswith(("ss", "us", "is")):
        return tok[:-1]
    return tok


def tokens(text: str) -> list[str]:
    return [stem(t) for t in re.findall(r"[a-z0-9]+", str(text).lower())]


# --- query parsing -------------------------------------------------------

_LEX = re.compile(r'\s*(\(|\)|"[^"]*"|[^\s()"]+)')


def _lex(q: str):
    q = re.sub(r"\[[^\]]*\]", " ", q)             # drop field tags
    q = re.sub(r"\b[A-Z_]+:", " ", q)             # drop Europe PMC field prefixes (TITLE:, AUTH:)
    return [m.group(1) for m in _LEX.finditer(q) if m.group(1).strip()]


def parse(q: str):
    """Return a tree: ("and"|"or", [children]), ("not", a, b), ("word", w),
    ("prefix", p), ("phrase", [w...]) or None for an empty query."""
    toks = _lex(q)
    pos = 0

    def leaf(t):
        if t.startswith('"'):
            ws = [w for w in tokens(t.strip('"'))]
            return ("phrase", ws) if len(ws) > 1 else (("word", ws[0]) if ws else None)
        if t.endswith("*") and len(t) > 2:
            return ("prefix", t[:-1].lower())
        ws = [w for w in tokens(t) if w not in STOPWORDS]
        if not ws:
            return None
        return ("word", ws[0]) if len(ws) == 1 else ("and", [("word", w) for w in ws])

    def expr():
        nonlocal pos
        node, op = None, "and"
        while pos < len(toks):
            t = toks[pos]
            if t == ")":
                pos += 1
                break
            pos += 1
            if t in ("AND", "OR", "NOT"):
                op = t.lower()
                continue
            sub = expr() if t == "(" else leaf(t)
            if sub is None:
                continue
            if node is None:
                node = sub
            elif op == "not":
                node = ("not", node, sub)
            else:
                node = (op, [node, sub])
            op = "and"
        return node

    return expr()


def terms(node) -> list[str]:
    """Positive leaf terms, for ranking."""
    if node is None:
        return []
    kind = node[0]
    if kind == "word" or kind == "prefix":
        return [node[1]]
    if kind == "phrase":
        return list(node[1])
    if kind == "not":
        return terms(node[1])
    return [t for c in node[1] for t in terms(c)]


class Index:
    """Documents are (id, text) pairs; text is pre-tokenised once."""

    def __init__(self, docs):
        self.ids, self.toks, self.sets, self.joined = [], [], [], []
        for doc_id, text in docs:
            tk = tokens(text)
            self.ids.append(doc_id)
            self.toks.append(tk)
            self.sets.append(set(tk))
            self.joined.append(" " + " ".join(tk) + " ")
        self.n = len(self.ids)
        self.avgdl = (sum(len(t) for t in self.toks) / self.n) if self.n else 1
        self.df = Counter(w for s in self.sets for w in s)

    def _match(self, node, i) -> bool:
        kind = node[0]
        if kind == "word":
            return node[1] in self.sets[i]
        if kind == "prefix":
            return any(w.startswith(node[1]) for w in self.sets[i])
        if kind == "phrase":
            return (" " + " ".join(node[1]) + " ") in self.joined[i]
        if kind == "and":
            return all(self._match(c, i) for c in node[1])
        if kind == "or":
            return any(self._match(c, i) for c in node[1])
        if kind == "not":
            return self._match(node[1], i) and not self._match(node[2], i)
        return False

    def _bm25(self, qterms, i, k1=1.2, b=0.75):
        tf = Counter(self.toks[i])
        dl = len(self.toks[i])
        score = 0.0
        for w in qterms:
            f = tf.get(w, 0)
            if f:
                idf = math.log(1 + (self.n - self.df[w] + 0.5) / (self.df[w] + 0.5))
                score += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * dl / self.avgdl))
        return score

    def search(self, query: str):
        """Return [(id, score)] for matching documents, best first."""
        node = parse(query)
        if node is None:
            return []
        qterms = terms(node)
        hits = [(self.ids[i], self._bm25(qterms, i)) for i in range(self.n) if self._match(node, i)]
        hits.sort(key=lambda h: (-h[1], str(h[0])))
        return hits
