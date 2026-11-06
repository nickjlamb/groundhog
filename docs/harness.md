# Harness

The harness runs a model on a task through a fixed tool surface, either live
(record) or against frozen tool responses (replay), and writes one trace per
episode. Scorers read the traces; they are not part of the harness.

```
harness/
  tools.py          tool surface: 10 PubCrawl tools, 4 Redacta tools, submit_answer
  tool_specs/       tool definitions captured from the live servers
  cassette.py       frozen responses per task (cassettes/<task>.json)
  paging.py         label sections served a page at a time, as PubCrawl >= 2.7.1 does
  faults.py         F1-F5 injection; fault_config.yaml holds the F5 texts
  gateway.py        ReplayGateway (cassettes + faults) and RecordGateway (live PubCrawl)
  mcp_client.py     minimal stdio MCP client
  agent.py          one episode: up to 15 tool calls, ends at submit_answer
  models/           adapters: mock (tests), anthropic (cross-check and judge)
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
- **Matching is tolerant of trivia**: key order, case, whitespace and paging
  arguments on label tools. Anything else that is not in the cassette is
  `off_path` and returns an empty result.
- **F4 needs a stale recording.** A task's cassette must hold a `stale`
  variant (a superseded label or registry version); without one the fault is
  logged as unavailable and the run must be excluded, not counted as clean.
- **Faults fire once**, on the first eligible external call, so clean and
  faulty runs of the same task differ in exactly one place.
