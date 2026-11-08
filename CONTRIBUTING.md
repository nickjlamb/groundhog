# Contributing to Groundhog

Thanks for helping. Groundhog is only as good as its gold answers, so the most valuable contribution is telling us when one is wrong.

## Ways to help

| Contribution | How |
|---|---|
| **A gold answer looks wrong** | [Open a gold-answer issue](https://github.com/nickjlamb/groundhog/issues/new?template=gold-answer.yml) with the task id and the source passage. These are triaged first. |
| **Propose a task** | [Open a task proposal](https://github.com/nickjlamb/groundhog/issues/new?template=task-proposal.yml). Abstention and conflict tasks are most wanted: they are where models differ. |
| **Bug in the harness or scorers** | [Open a bug report](https://github.com/nickjlamb/groundhog/issues/new?template=bug.yml) with the command and the trace. |
| **Add a model adapter** | See [examples §7](docs/examples.md#7-add-a-model); a pull request with the adapter and one smoke run is enough. |

## Development setup

```bash
git clone https://github.com/nickjlamb/groundhog && cd groundhog
make install      # .venv with the dev requirements
make validate     # every task against the schema
make test         # offline tests
make selfcheck    # gold answers through the full pipeline
```

All four run in CI on every push and pull request, with no API keys. Recording new cassettes needs Node.js (PubCrawl runs through `npx`); running real models needs API keys in `.env`.

## Adding a task

1. **Write the YAML** in `tasks/`, following [`schema/task.schema.json`](schema/task.schema.json) and an existing task of the same category. Use `status: draft`.
2. **Verify the gold answer by hand against its source**: the SmPC, USPI, paper or registry entry, not a summary of it. Quote the passage in `source.excerpt(s)` and record `retrieved:` with the date. Where full text exists, check against it, not only the abstract.
3. **Never edit a gold answer to make a model pass.** If a model's answer exposes a mistake in the gold, fix the gold against the source and say so in the pull request.
4. **Assign one fault** (F1–F5) that tests something real for this task, and document any deliberate trap in `notes`.
5. **Use synthetic identifiers only** in privacy tasks. NHS numbers must be in the 999 range and pass the modulus-11 check.
6. **Record its cassette** (`python -m harness.runner --model mock:submit-gold --tasks <id> --record`), then run `make selfcheck`: the gold answer must pass its own scorer.
7. Set `status: verified` only after steps 2–6, and open a pull request.

A task that cannot be verified against a public source is not accepted, however plausible its answer.

## Changing scorers

Scorers decide every number in the README, so changes need care:

- Add a test in `tests/test_scoring.py` for the case you are fixing.
- `make selfcheck` must still pass.
- If the change would move a published result, say which and by how much in the pull request, and add a line to [`docs/scoring.md`](docs/scoring.md) under the corrections. Published results are re-scored, never quietly replaced.

## Pull requests

- One change per pull request; describe what and why.
- Run `make validate test selfcheck` before pushing.
- Add a line to the `[Unreleased]` section of [`CHANGELOG.md`](CHANGELOG.md).

## Releases

Versions follow [semantic versioning](https://semver.org): a new task set or a scoring change that moves results is a minor version, fixes are patches. Each GitHub release is archived on Zenodo with its own DOI.

## Conduct

Be kind, be specific, cite your source. Disagreements about a gold answer are settled by the source text, not by who argues longest.
