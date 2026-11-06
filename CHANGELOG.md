# Changelog

All notable changes to Groundhog are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Design spec (`docs/design-spec.md`): research questions, tool surface, fault conditions F0–F5, scoring (pass@1, pass^k, hard fails), models and budget, reporting rules.
- First 10 tasks, verified by hand against their sources: 5 label lookups (`label-001`–`label-005`) and 5 US/UK comparisons (`cmp-001`–`cmp-005`).
- Rubrics: optional `rubric` field of yes/no criteria (points −10 to 10, `deterministic` with a `locator` or `judge`, optional HealthBench axis). Required for claim-checking and free-text tasks. Validator checks unique criterion ids and at least one positive criterion. Scoring rules in spec §5.
- Claim-checking tasks, verified: `claim-001` (ARISTOTLE, partially supported claim, F5) and `claim-002` (DAPA-HF, supported control with a derived 26% figure, F2) and `claim-003` (EMPA-REG OUTCOME, unsupported claim about composite components, F1), completing the eight claim-checking tasks with `claim-004` (RE-LY, noninferiority as superiority), `claim-005` (SELECT, population stretch), `claim-006` (PARADIGM-HF, relative as absolute), `claim-007` (RECOVERY, subgroup direction reversed) and `claim-008` (SPRINT, supported only in the full text).
- Abstention tasks, verified: `abstain-001` (Ozempic under 18), `abstain-002` (metformin in PCOS, unlicensed), `abstain-003` (completed trial with no reported results), `abstain-004` (SPRINT in diabetes, excluded population), `abstain-005` (non-existent trial citation).
- Conflict tasks, verified: `conflict-001` (RE-LY paper vs Pradaxa SmPC after newly identified events), `conflict-002` (ARISTOTLE enrolled vs randomised), `conflict-003` (EMPA-REG registry vs publication), `conflict-004` (RECOVERY preliminary vs final report), `conflict-005` (ARISTOTLE mortality CI rounding, paper vs Eliquis SmPC).
- Citation tasks, verified: `cite-001` to `cite-006` (EMPEROR-Reduced, FOURIER, CREDENCE, DESTINY-Breast04, LEADER, DESTINY-Breast03), each with a near-neighbour trap.
- Privacy tasks, verified: `privacy-001` to `privacy-005` (structured header, identifiers buried in a letter, over-redaction, quasi-identifiers, injected instruction). Synthetic identifiers only.
- Privacy scoring (spec §5): direct identifiers reaching an external tool are a hard fail, quasi-identifiers a rubric penalty; locator field `tool_calls`; validator requires `gold.identifiers` on privacy tasks.
- Label and comparison tasks, verified: `label-006` (Forxiga initiation eGFR), `label-007` (Enhertu breast vs gastric dose), `label-008` (Eliquis PE schedule), `cmp-006` (apixaban in severe renal impairment, US vs UK), `cmp-007` (Enhertu boxed warning, US vs UK).
- Trial facts tasks, verified: `trial-001` to `trial-006` (DAPA-HF, DESTINY-Breast04, FOURIER, DESTINY-Breast03, LEADER, CREDENCE), each with a secondary-endpoint or wrong-population trap.
- Rubric locator `all_of`: every string must appear.
- Task schema (`schema/task.schema.json`) and validator (`scripts/validate_tasks.py`), run in CI on every push.

### Notes
- Requires PubCrawl ≥ 2.7.1 (full label sections, paged), so clean runs never see accidentally truncated labels.
