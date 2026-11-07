# Harness

The harness runs a model on a task through a fixed tool surface, either live
(record) or against frozen tool responses (replay), and writes one trace per
episode. Scorers read the traces; they are not part of the harness.

```
harness/
  tools.py          tool surface: 10 PubCrawl tools, 4 Redacta tools, submit_answer
  tool_specs/       tool definitions captured from the live servers
  cassette.py       frozen responses per task (cassettes/<task>.json)
  corpus.py         frozen shared corpus (corpus/) answering searches and drug names
  textsearch.py     PubMed-style boolean query matching with BM25 ranking
  paging.py         label sections served a page at a time, as PubCrawl >= 2.7.1 does
  faults.py         F1-F5 injection; fault_config.yaml holds the F5 texts
  gateway.py        ReplayGateway (cassettes + faults) and RecordGateway (live PubCrawl)
  mcp_client.py     minimal stdio MCP client
  agent.py          one episode: up to 15 tool calls, ends at submit_answer
  models/           adapters: mock (tests, gold-path recording), perplexity, anthropic
  runner.py         models x tasks x conditions x repeats -> runs/<run_id>/
```

## Running

```bash
pip install -r requirements-dev.txt
python -m pytest -q tests                                # offline tests
python -m harness.runner --model mock:submit-gold        # smoke run, all tasks, clean + fault
python -m harness.runner --model anthropic:<model-id> --record --tasks label-001
```

Each run writes `runs/<run_id>/manifest.json` (model, mode, git SHA, task-set
hash, server versions) and one `<task>__<condition>__r<n>.json` trace with
every tool call, its arguments, whether it was external, whether it was
off-path, any fault events, the final answer and token usage.

## Design decisions

- **Redacta runs live in both modes.** It is local and deterministic, and its
  output depends on the text each model sends, so replaying it from cassettes
  would break the privacy tasks. Only PubCrawl, the external and changeable
  side, is recorded and replayed.
- **Cassettes store full label sections** (recorded with `max_chars` 50,000);
  the replay layer pages them to whatever the agent asks for. This is what
  lets F3 move the answer past the first page.
- **Searches are answered from a frozen corpus, not by exact replay.** The
  pilot showed models reword searches on every run (Claude: 107 of 148 PubMed
  searches missed the cassette), so exact matching measured luck, not
  reliability. `scripts/build_corpus.py` re-runs every search seen in
  cassettes and traces against live PubCrawl and keeps every article and
  trial returned, with abstracts, plus resolved drug names. In replay,
  `search_pubmed`, `search_europepmc`, `search_trials` and `resolve_drug_name`
  are answered from that corpus: space-separated terms are ANDed, AND/OR/NOT,
  parentheses, quoted phrases and trailing wildcards work, field tags are
  accepted, and hits are ranked by BM25. MeSH term mapping is not modelled,
  and the corpus is far smaller than PubMed, so retrieval is easier than live;
  report retrieval separately. Freeze the corpus before the full run.
- **Label requests match the product, not the wording.** A request for
  "metformin" is served the task's recorded Glucophage SmPC; a request that
  names another drug ("metformin and glimepiride", a different brand) is not.
  Abstracts of any corpus article are served too.
- **Everything else must match the cassette** (tolerating key order, case,
  whitespace and paging arguments). A miss is `off_path` and returns an empty
  result. Each step records `served_by`: cassette, cassette:same_product or
  corpus.
- **F4 serves a real archived version.** `scripts/build_stale.py` builds the
  stale variant from an archived DailyMed SPL (kept in
  `cassettes/archive_sources/`), mirroring each recorded call. It fires on the
  first call to a tool that has a stale recording. Only two tasks have an
  archive that changes the gold answer (cmp-002, metformin renal criteria
  before 2016; cmp-004, codeine in children before Sept 2017), so F4 is
  reported as case studies, not a rate.
- **F4 needs a stale recording.** A task's cassette must hold a `stale`
  variant (a superseded label or registry version); without one the fault is
  logged as unavailable and the run must be excluded, not counted as clean.
- **Gold paths are seeded by the mock.** `mock:submit-gold --record` makes the
  calls on each task's evidence path (from its `source` block, or
  `GOLD_PATH_OVERRIDES` in `models/mock.py`): labels fetched whole, citations
  in every style. Search routes are added when real models run live in the
  pilot (spec §5, record/replay).
- **Recording retries** failed live calls (5, 20, 45 s) because NCBI rate
  limits and eMC/openFDA misses are usually transient; calls that still fail
  are not stored and are reported as `LIVE ERRORS` in the run log.
- **Faults fire once**, on the first eligible external call, so clean and
  faulty runs of the same task differ in exactly one place.
