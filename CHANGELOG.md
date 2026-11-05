# Changelog

All notable changes to Groundhog are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Design spec (`docs/design-spec.md`): research questions, tool surface, fault conditions F0–F5, scoring (pass@1, pass^k, hard fails), models and budget, reporting rules.
- First 10 tasks, verified by hand against their sources: 5 label lookups (`label-001`–`label-005`) and 5 US/UK comparisons (`cmp-001`–`cmp-005`).
- Rubrics: optional `rubric` field of yes/no criteria (points −10 to 10, `deterministic` with a `locator` or `judge`, optional HealthBench axis). Required for claim-checking and free-text tasks. Validator checks unique criterion ids and at least one positive criterion. Scoring rules in spec §5.
- First claim-checking task, verified: `claim-001` (ARISTOTLE, partially supported claim, F5).
- Task schema (`schema/task.schema.json`) and validator (`scripts/validate_tasks.py`), run in CI on every push.

### Notes
- Requires PubCrawl ≥ 2.7.1 (full label sections, paged), so clean runs never see accidentally truncated labels.
