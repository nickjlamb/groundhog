"""Frozen evidence corpus shared by all tasks.

Free-text tools (searches, drug-name resolution) cannot be replayed by exact
match: models word their queries differently on every run. Instead they are
answered from a fixed corpus built by scripts/build_corpus.py from live
PubCrawl results: every article and trial that the recorded searches
returned, with abstracts, plus resolved drug names. Every model searches the
same frozen corpus, so results are reproducible and comparable.

corpus/articles.json  pmid -> search-result fields + abstract text
corpus/trials.json    nct_id -> search-result fields
corpus/drugs.json     normalised name -> resolve_drug_name response
"""

import json
import re
from pathlib import Path

from .textsearch import Index, tokens

ROOT = Path(__file__).resolve().parent.parent / "corpus"
CORPUS_TOOLS = {"search_pubmed", "search_europepmc", "search_trials", "resolve_drug_name"}

# Words that describe a product's form, strength or maker rather than the drug.
FORM_WORDS = {"mg", "mcg", "ml", "g", "tablet", "tablets", "capsule", "capsules", "hard", "soft", "film",
              "coated", "filmcoated", "solution", "injection", "infusion", "powder", "concentrate", "for",
              "oral", "suspension", "granule", "granules", "chewable", "prolonged", "release", "extended",
              "modified", "pre", "filled", "pen", "pens", "vial", "the", "and", "of", "in", "bp", "usp",
              "sodium", "hydrochloride", "hcl", "phosphate", "sulfate", "sulphate", "potassium", "calcium",
              "etexilate", "mesilate", "maleate", "propanediol", "medicine", "label", "smpc", "uspi", "pi",
              "prescribing", "information", "uk", "us", "emc", "dailymed", "fda", "product",
              "characteristics", "summary"}


def norm_name(name: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(name).lower()))


def core_tokens(name: str) -> list[str]:
    toks = re.findall(r"[a-z][a-z0-9]+", str(name).lower().replace("film-coated", "filmcoated"))
    return [t for t in toks if t not in FORM_WORDS and len(t) >= 4]


def _abstract_text(rec):
    secs = rec.get("abstract_sections") or []
    if isinstance(secs, list):
        return " ".join(f"{s.get('label', '')} {s.get('text', '')}" for s in secs if isinstance(s, dict))
    return str(rec.get("abstract", ""))


def _year(y):
    try:
        return int(str(y)[:4])
    except ValueError:
        return 0


class Corpus:
    def __init__(self, root: Path = ROOT):
        self.root = Path(root)
        self.articles = self._load("articles.json")
        self.trials = self._load("trials.json")
        self.drugs = self._load("drugs.json")
        self._aix = self._tix = None

    def _load(self, name):
        p = self.root / name
        return json.loads(p.read_text()) if p.exists() else {}

    def save(self):
        self.root.mkdir(parents=True, exist_ok=True)
        for name, data in (("articles.json", self.articles), ("trials.json", self.trials), ("drugs.json", self.drugs)):
            (self.root / name).write_text(json.dumps(dict(sorted(data.items())), indent=1, ensure_ascii=False) + "\n")
        self._aix = self._tix = None

    # --- building ----------------------------------------------------------
    def add_search_results(self, tool, response):
        for r in (response or {}).get("results", []) or []:
            if tool == "search_trials" and r.get("nct_id"):
                self.trials.setdefault(r["nct_id"], r)
            elif tool in ("search_pubmed", "search_europepmc") and r.get("pmid"):
                rec = self.articles.setdefault(str(r["pmid"]), {})
                for k, v in r.items():
                    if v not in ("", None, []) and k not in rec:
                        rec[k] = v

    def add_abstract(self, response):
        if not isinstance(response, dict) or not response.get("pmid"):
            return
        rec = self.articles.setdefault(str(response["pmid"]), {})
        for k in ("pmid", "title", "journal", "year", "doi"):
            if response.get(k) and not rec.get(k):
                rec[k] = response[k]
        rec["abstract"] = _abstract_text(response)
        rec["mesh_terms"] = response.get("mesh_terms") or []
        rec["abstract_record"] = response

    def add_drug(self, name, response):
        self.drugs[norm_name(name)] = response

    # --- answering ---------------------------------------------------------
    @property
    def article_index(self):
        if self._aix is None:
            docs = []
            for pmid, r in self.articles.items():
                authors = " ".join(a for a in r.get("authors", []) if isinstance(a, str))
                mesh = " ".join(m if isinstance(m, str) else " ".join(str(v) for v in m.values()) if isinstance(m, dict)
                                else str(m) for m in r.get("mesh_terms", []))
                docs.append((pmid, " ".join([r.get("title", ""), r.get("abstract", ""), authors,
                                             r.get("journal", ""), mesh, str(r.get("doi", ""))])))
            self._aix = Index(docs)
        return self._aix

    @property
    def trial_index(self):
        if self._tix is None:
            docs = []
            for nct, r in self.trials.items():
                iv = " ".join(i.get("name", "") if isinstance(i, dict) else str(i) for i in r.get("interventions", []))
                docs.append((nct, " ".join([nct, r.get("title", ""), " ".join(r.get("conditions", [])), iv,
                                            r.get("sponsor", "")])))
            self._tix = Index(docs)
        return self._tix

    def answer(self, tool, args):
        return getattr(self, "_" + tool)(args or {})

    def _filtered_articles(self, args):
        hits = self.article_index.search(args.get("query", ""))
        lo = _year((args.get("dateFrom") or "0")[:4])
        hi = _year((args.get("dateTo") or "9999")[:4]) or 9999
        hits = [(p, s) for p, s in hits if lo <= _year(self.articles[p].get("year")) <= hi]
        if args.get("sort") == "date":
            hits.sort(key=lambda h: (-_year(self.articles[h[0]].get("year")), -h[1]))
        elif args.get("sort") == "cited":
            hits.sort(key=lambda h: (-(self.articles[h[0]].get("cited_by_count") or 0), -h[1]))
        return hits

    def _search_pubmed(self, args):
        hits = self._filtered_articles(args)
        n = int(args.get("maxResults") or 10)
        keys = ("pmid", "title", "authors", "journal", "year", "doi")
        return {"results": [{k: self.articles[p].get(k, "" if k != "authors" else []) for k in keys}
                            for p, _ in hits[:n]], "total_count": len(hits)}

    def _search_europepmc(self, args):
        hits = self._filtered_articles(args)
        n = int(args.get("maxResults") or 10)
        out = []
        for p, _ in hits[:n]:
            r = self.articles[p]
            out.append({"id": p, "source": "MED", "pmid": p, "pmcid": r.get("pmcid", ""), "doi": r.get("doi", ""),
                        "title": r.get("title", ""), "authors": r.get("authors", []), "journal": r.get("journal", ""),
                        "year": r.get("year", ""), "is_preprint": False,
                        "is_open_access": bool(r.get("is_open_access", False)),
                        "cited_by_count": r.get("cited_by_count", 0), "has_full_text": bool(r.get("has_full_text", False)),
                        "abstract_snippet": r.get("abstract", "")[:300],
                        "url": f"https://europepmc.org/article/MED/{p}"})
        return {"results": out, "total_count": len(hits)}

    def _search_trials(self, args):
        parts = [args.get(k) for k in ("term", "condition", "intervention") if args.get(k)]
        query = " ".join(f"({p})" for p in parts)
        hits = self.trial_index.search(query) if query else [(k, 0.0) for k in sorted(self.trials)]
        rs = [(n, s) for n, s in hits
              if (not args.get("status") or self.trials[n].get("status") == args["status"])
              and (not args.get("phase") or args["phase"] in str(self.trials[n].get("phase", "")))]
        if args.get("sort") == "enrollment":
            rs.sort(key=lambda h: -(self.trials[h[0]].get("enrollment") or 0))
        elif args.get("sort") == "start_date":
            rs.sort(key=lambda h: str(self.trials[h[0]].get("start_date", "")), reverse=True)
        n = int(args.get("maxResults") or 10)
        return {"results": [self.trials[k] for k, _ in rs[:n]], "total_count": len(rs)}

    def abstract(self, pmid):
        rec = self.articles.get(str(pmid).strip())
        return rec.get("abstract_record") if rec else None

    def _resolve_drug_name(self, args):
        hit = self.drugs.get(norm_name(args.get("drug", "")))
        return hit if hit is not None else None

    # --- drug identity, for matching label requests ---------------------------
    def generic_of(self, name):
        r = self.drugs.get(norm_name(name)) or {}
        g = r.get("genericName") or (r.get("inputName") if r.get("inputType") == "generic" else None)
        return norm_name(g) if g else None

    def is_drug_word(self, tok):
        r = self.drugs.get(tok)
        return bool(r and (r.get("genericName") or r.get("brandNames")))

    def identity(self, names):
        """Core tokens of a product's names plus their generics."""
        ids = set()
        for n in names:
            for t in core_tokens(n):
                ids.add(t)
                g = self.generic_of(t)
                if g:
                    ids.update(core_tokens(g))
            g = self.generic_of(n)
            if g:
                ids.update(core_tokens(g))
        return ids

    def same_product(self, query_name, entry_names) -> bool:
        """True if a label request names the recorded product: its first core word
        is (or resolves to) the product, and it names no other drug."""
        q = core_tokens(query_name)
        if not q:
            return False
        ident = self.identity(entry_names)
        first_ok = q[0] in ident or (self.generic_of(q[0]) or "") in ident
        others = [t for t in q[1:] if t not in ident and (self.generic_of(t) or "") not in ident]
        return first_ok and not any(self.is_drug_word(t) for t in others)
