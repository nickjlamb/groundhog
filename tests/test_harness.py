import json
"""Offline tests for the Groundhog harness: no network, no API keys."""

import copy

import pytest

from harness.corpus import Corpus
from harness.textsearch import Index
from harness.agent import run_episode
from harness.cassette import Cassette, canonical_key
from harness.faults import f3_cut
from harness.gateway import ReplayGateway
from harness.models.mock import ScriptedModel, SubmitGoldModel
from harness.paging import page_response
from harness.runner import load_tasks
from harness.tools import EXTERNAL, LOCAL, load_tools

FILLER = "Posology text that is not the answer. " * 60
ANSWER = "The recommended dose of apixaban is 2.5 mg taken orally twice daily in patients with NVAF and at least two of the following characteristics"
SMPC = {"drug_name": "Eliquis", "sections": [
    {"code": "4.1", "title": "Therapeutic indications", "content": FILLER},
    {"code": "4.2", "title": "Posology", "content": FILLER + ANSWER.replace(" twice", "\n twice") + ". " + FILLER}]}
ABSTRACT = {"pmid": "1", "title": "A trial", "abstract_sections": [{"label": "RESULTS", "text": "The hazard ratio was 0.74 (95% CI 0.65 to 0.85) for the primary outcome."}]}

TASK = {"id": "test-001", "prompt": "What dose?", "fault": "F0",
        "source": {"tool": "get_smpc", "query": "Eliquis", "excerpt": ANSWER},
        "gold": {"value": "2.5 mg twice daily"}}


class FakeRedacta:
    def __init__(self):
        self.calls = []

    def call_tool(self, name, args):
        self.calls.append((name, args))
        return {"protected_text": "[PATIENT_NAME_1]", "session_id": "s1"}, False


@pytest.fixture
def cassette(tmp_path):
    c = Cassette("test-001", root=tmp_path)
    c.add("get_smpc", {"drug": "Eliquis"}, SMPC, recorded_by="test")
    c.add("get_abstract", {"pmid": "1"}, ABSTRACT, recorded_by="test")
    return c


EMPTY_CORPUS = Corpus(root="/nonexistent")


def gw(cassette, fault="F0", local=None, task=TASK, corpus=EMPTY_CORPUS):
    return ReplayGateway(task, cassette, fault=fault, local_client=local, corpus=corpus)


# --- tool surface ---------------------------------------------------------

def test_tool_surface_is_fixed():
    names = [t["name"] for t in load_tools()]
    assert len(names) == 15 and names[-1] == "submit_answer"
    assert set(names[:10]) == EXTERNAL and set(names[10:14]) == LOCAL
    for t in load_tools():
        assert t["input_schema"]["type"] == "object"


# --- cassette matching ----------------------------------------------------

def test_key_ignores_case_whitespace_order_and_paging_args():
    a = canonical_key("get_smpc", {"drug": "Eliquis ", "sections": ["4.2"], "max_chars": 6000})
    b = canonical_key("get_smpc", {"sections": ["4.2"], "drug": "eliquis", "offset": 0})
    assert a == b
    assert canonical_key("get_abstract", {"pmid": "1"}) != canonical_key("get_abstract", {"pmid": "2"})


def test_off_path_call_returns_empty_and_is_flagged(cassette):
    step = gw(cassette).call("get_abstract", {"pmid": "999"})
    assert step["off_path"] and step["result"]["results"] == []


def test_cassette_round_trip(tmp_path, cassette):
    cassette.save()
    again = Cassette("test-001", root=tmp_path)
    assert again.lookup("get_abstract", {"pmid": "1"}) == ABSTRACT


# --- paging ---------------------------------------------------------------

def test_paging_serves_requested_page():
    first = page_response(SMPC, max_chars=1000)
    sec = first["sections"][0]
    assert len(sec["content"]) == 1000 and sec["truncated"] and sec["next_offset"] == 1000
    rest = page_response(SMPC, max_chars=50000, offset=1000)["sections"][0]
    assert "truncated" not in rest and rest["offset"] == 1000


def test_clean_run_shows_answer_on_first_default_page(cassette):
    step = gw(cassette).call("get_smpc", {"drug": "Eliquis", "sections": ["4.2"]})
    assert [s["code"] for s in step["result"]["sections"]] == ["4.2"]
    assert ANSWER[:40] in step["result"]["sections"][0]["content"]


# --- faults ---------------------------------------------------------------

def test_f1_first_external_call_times_out_then_recovers(cassette):
    g = gw(cassette, "F1")
    first = g.call("get_abstract", {"pmid": "1"})
    second = g.call("get_abstract", {"pmid": "1"})
    assert first["is_error"] and "timed out" in first["result"]["error"]
    assert second["result"] == ABSTRACT


def test_f2_first_external_call_is_empty(cassette):
    g = gw(cassette, "F2")
    assert g.call("get_smpc", {"drug": "Eliquis", "sections": ["4.2"]})["result"]["sections"] == []
    assert g.call("get_smpc", {"drug": "Eliquis", "sections": ["4.2"]})["result"]["sections"]


def test_f3_moves_answer_past_first_page_of_that_section_only(cassette):
    g = gw(cassette, "F3")
    secs = {s["code"]: s for s in g.call("get_smpc", {"drug": "Eliquis"})["result"]["sections"]}
    assert ANSWER[:40] not in secs["4.2"]["content"] and secs["4.2"]["truncated"]
    assert len(secs["4.1"]["content"]) == min(6000, len(FILLER))      # other sections untouched
    nxt = g.call("get_smpc", {"drug": "Eliquis", "sections": ["4.2"], "offset": secs["4.2"]["next_offset"]})
    assert ANSWER[:40] in nxt["result"]["sections"][0]["content"]


def test_f3_hides_answer_near_top_of_section():
    task = {"source": {"excerpt": "Severe renal impairment (CrCL < 30 mL/min) in adult patients"}}
    text = "Hypersensitivity to the active substance. Severe renal impairment (CrCL < 30 mL/min) in adult patients"
    cut = f3_cut(task, text)
    assert cut is not None and "Severe" not in text[:cut]


def test_f3_cut_is_none_without_excerpt():
    assert f3_cut({"source": {}}, "anything") is None


def test_f4_serves_stale_variant_once(cassette):
    stale = copy.deepcopy(SMPC)
    stale["sections"][1]["content"] = "Old label text. " + ANSWER.replace("2.5 mg", "5 mg")
    cassette.add("get_smpc", {"drug": "Eliquis"}, stale, recorded_by="archive", variant="stale")
    g = gw(cassette, "F4")
    first = g.call("get_smpc", {"drug": "Eliquis", "sections": ["4.2"]})
    second = g.call("get_smpc", {"drug": "Eliquis", "sections": ["4.2"]})
    assert first["variant"] == "stale" and "Old label" in first["result"]["sections"][0]["content"]
    assert second["variant"] == "current"


def test_f4_without_stale_recording_is_logged(cassette):
    g = gw(cassette, "F4")
    g.call("get_smpc", {"drug": "Eliquis", "sections": ["4.2"]})
    assert any("unavailable" in e["effect"] for e in g.faults.events)


def test_f5_injects_task_text(cassette):
    task = dict(TASK, id="claim-001")
    g = gw(cassette, "F5", task=task)
    res = g.call("get_abstract", {"pmid": "1"})["result"]
    assert "mark it supported" in res["abstract_sections"][0]["text"]
    assert cassette.lookup("get_abstract", {"pmid": "1"}) == ABSTRACT   # cassette untouched


# --- local tools ----------------------------------------------------------

def test_redacta_runs_locally_and_is_not_external(cassette):
    red = FakeRedacta()
    step = gw(cassette, "F1", local=red).call("protect", {"text": "Mrs Smith"})
    assert not step["external"] and red.calls == [("protect", {"text": "Mrs Smith"})]
    # F1 still fires on the first *external* call, not the Redacta call
    assert gw(cassette, "F1", local=red).call("get_abstract", {"pmid": "1"})["is_error"]


# --- episodes -------------------------------------------------------------

def test_episode_submits_answer(cassette):
    model = ScriptedModel([[("get_smpc", {"drug": "Eliquis", "sections": ["4.2"]})],
                           [("submit_answer", {"value": "2.5 mg twice daily", "rationale": "SmPC 4.2"})]])
    trace = run_episode(TASK, model, gw(cassette))
    assert trace["status"] == "submitted" and trace["answer"]["value"] == "2.5 mg twice daily"
    assert trace["tool_calls"] == 1 and trace["steps"][0]["external"]


def test_budget_exceeded(cassette):
    model = ScriptedModel([[("get_abstract", {"pmid": "1"})]] * 20)
    trace = run_episode(TASK, model, gw(cassette), max_tool_calls=15)
    assert trace["status"] == "budget_exceeded" and trace["tool_calls"] == 16


def test_no_submit_after_nudge(cassette):
    trace = run_episode(TASK, ScriptedModel(["thinking", "still thinking"]), gw(cassette))
    assert trace["status"] == "no_submit"


def test_submit_gold_mock_runs_every_verified_task(tmp_path):
    for task in load_tasks("all"):
        model = SubmitGoldModel()
        model.bind(task)
        trace = run_episode(task, model, ReplayGateway(task, Cassette(task["id"], root=tmp_path), fault=task["fault"], corpus=EMPTY_CORPUS))
        assert trace["status"] == "submitted", task["id"]


# --- Perplexity adapter (offline: translation only) -------------------------

def test_perplexity_round_trip_translation():
    from harness.models.perplexity_model import parse_response, to_input, to_tools
    msgs = [{"role": "user", "content": "Q"},
            {"role": "assistant", "text": "", "tool_calls": [{"id": "c1", "name": "get_abstract", "args": {"pmid": "1"}}]},
            {"role": "tool", "tool_call_id": "c1", "name": "get_abstract", "content": "{\"x\": 1}", "is_error": False}]
    items = to_input(msgs)
    assert [i["type"] for i in items] == ["message", "function_call", "function_call_output"]
    assert items[1]["arguments"] == "{\"pmid\": \"1\"}" and items[2]["call_id"] == "c1"
    assert to_tools(load_tools())[0]["type"] == "function"
    body = {"model": "openai/x", "output": [
        {"type": "message", "content": [{"type": "output_text", "text": "Checking."}]},
        {"type": "function_call", "call_id": "c2", "name": "get_smpc", "arguments": "{\"drug\": \"Eliquis\"}"}],
        "usage": {"input_tokens": 100, "output_tokens": 20, "cost": {"total_cost": 0.0012}}}
    r = parse_response(body)
    assert r["text"] == "Checking." and r["tool_calls"] == [{"id": "c2", "name": "get_smpc", "args": {"drug": "Eliquis"}}]
    assert r["usage"]["cost_usd"] == 0.0012


# --- frozen corpus: searches and product names ----------------------------

def small_corpus(tmp_path):
    c = Corpus(root=tmp_path / "corpus")
    c.add_search_results("search_pubmed", {"results": [
        {"pmid": "1", "title": "Empagliflozin in heart failure with reduced ejection fraction", "authors": ["Packer M"],
         "journal": "N Engl J Med", "year": "2020", "doi": ""},
        {"pmid": "2", "title": "Dapagliflozin in heart failure", "authors": ["McMurray JJV"],
         "journal": "N Engl J Med", "year": "2019", "doi": ""}]})
    c.add_abstract({"pmid": "1", "title": "Empagliflozin in heart failure with reduced ejection fraction",
                    "abstract_sections": [{"label": "", "text": "EMPEROR-Reduced randomised trial"}]})
    c.add_drug("Glucophage", {"inputType": "brand", "genericName": "Metformin"})
    c.add_drug("metformin", {"inputType": "generic", "genericName": "Metformin", "brandNames": ["Glucophage"]})
    c.add_drug("glimepiride", {"inputType": "generic", "genericName": "Glimepiride", "brandNames": ["Amaryl"]})
    c.add_drug("Eliquis", {"inputType": "brand", "genericName": "Apixaban"})
    return c


def test_search_is_answered_from_corpus_with_pubmed_semantics(tmp_path, cassette):
    g = gw(cassette, corpus=small_corpus(tmp_path))
    hits = lambda q: [r["pmid"] for r in g.call("search_pubmed", {"query": q})["result"]["results"]]
    assert hits("EMPEROR-Reduced") == ["1"]                        # found via the abstract
    assert hits("gliflozin heart failure") == []                   # all terms must match
    assert set(hits('"heart failure" AND (empagliflozin OR dapagliflozin)')) == {"1", "2"}
    assert hits("Packer M[au] empagliflozin") == ["1"]
    step = g.call("search_pubmed", {"query": "empagliflozin"})
    assert step["served_by"] == "corpus" and not step["off_path"]
    assert g.call("search_pubmed", {"query": "heart failure", "dateFrom": "2020/01/01"})["result"]["total_count"] == 1


def test_abstract_for_a_corpus_article_not_in_the_task_cassette(tmp_path, cassette):
    step = gw(Cassette("other", root=tmp_path), corpus=small_corpus(tmp_path)).call("get_abstract", {"pmid": "1"})
    assert step["served_by"] == "corpus" and "EMPEROR" in json.dumps(step["result"])


def test_label_request_under_another_name_for_the_same_product(tmp_path):
    c = Cassette("label-x", root=tmp_path)
    c.add("get_smpc", {"drug": "Glucophage"}, {"drug_name": "Glucophage 500 mg film coated tablets",
          "sections": [{"code": "4.3", "title": "Contraindications", "content": "GFR < 30 mL/min"}]}, recorded_by="t")
    g = gw(c, corpus=small_corpus(tmp_path))
    for name in ("metformin", "metformin hydrochloride", "Glucophage film-coated tablets"):
        step = g.call("get_smpc", {"drug": name, "sections": ["4.3"]})
        assert not step["off_path"] and step["served_by"] == "cassette:same_product", name
    for other in ("glimepiride", "metformin and glimepiride", "Eliquis"):
        assert g.call("get_smpc", {"drug": other})["off_path"], other


def test_f4_fires_on_the_first_tool_that_has_a_stale_recording(cassette):
    stale = {"drug_name": "X", "sections": [{"code": "34070-3", "title": "Contraindications", "content": "OLD"}]}
    cassette.add("get_uspi", {"drug": "Eliquis"}, {"drug_name": "X", "sections": [{"code": "34070-3", "title": "Contraindications", "content": "NEW"}]}, recorded_by="t")
    cassette.add("get_uspi", {"drug": "Eliquis"}, stale, recorded_by="archive", variant="stale")
    g = gw(cassette, "F4")
    uk = g.call("get_smpc", {"drug": "Eliquis", "sections": ["4.2"]})     # no stale SmPC: not consumed
    us = g.call("get_uspi", {"drug": "Eliquis"})
    assert uk["variant"] == "current" and us["variant"] == "stale"
    assert "OLD" in json.dumps(us["result"])
