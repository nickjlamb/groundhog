# Groundhog: common tasks. `make quickstart` needs no API keys.

PY := .venv/bin/python
QS_TASKS := label-003,abstain-001,claim-006

.PHONY: quickstart selfcheck install test validate clean-quickstart

install: .venv/.installed

.venv/.installed: requirements-dev.txt
	python3 -m venv .venv
	.venv/bin/pip install -q -r requirements-dev.txt
	touch $@

## Replay 3 tasks x 5 runs (clean + fault) with the gold-answer mock model, score them, print the summary.
quickstart: install clean-quickstart
	$(PY) -m harness.runner --model mock:submit-gold --tasks $(QS_TASKS) --runs 5 --out runs/quickstart
	$(PY) scripts/score.py runs/quickstart/* --out runs/quickstart-scores > /dev/null
	@echo; sed -n "/^## /,/^\*\*Hard fails/p" runs/quickstart-scores/summary.md
	@echo "Traces: runs/quickstart/   Summary: runs/quickstart-scores/summary.md"

clean-quickstart:
	rm -rf runs/quickstart runs/quickstart-scores

## Offline tests and task validation (what CI runs).
test: install
	$(PY) -m pytest -q tests

validate: install
	$(PY) scripts/validate_tasks.py

## Every task, gold answers through the full pipeline: all code-scored episodes must pass.
selfcheck: install
	rm -rf runs/selfcheck runs/selfcheck-scores
	$(PY) -m harness.runner --model mock:submit-gold --tasks all --runs 1 --out runs/selfcheck > /dev/null
	$(PY) scripts/score.py runs/selfcheck/* --out runs/selfcheck-scores > /dev/null
	$(PY) scripts/selfcheck.py runs/selfcheck-scores/*.episodes.jsonl
