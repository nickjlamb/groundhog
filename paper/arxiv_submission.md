# arXiv submission: Groundhog v1

**Title:** Groundhog: Reliability of Tool-Using Agents on Medical-Evidence Tasks

**Authors:** Nick Lamb (PharmaTools.AI, Oxford, United Kingdom)

**Primary category:** cs.AI  ·  **Cross-list:** cs.CL
(Endorsed for cs.AI since 8 Oct 2026; no further endorsement needed.)

**Licence:** CC BY 4.0

**Comments:** Code, tasks, frozen tool responses and scorers: https://github.com/nickjlamb/groundhog (v1.0.0 archived at https://doi.org/10.5281/zenodo.24043717)

**Abstract** (plain text for the arXiv form, 1,709 characters, under the 1,920 limit):

Tool-using agents are increasingly asked to check medical evidence, where an answer that is right only some of the time still has to be checked every time. We introduce Groundhog, a benchmark of 50 medical-evidence tasks drawn from medical-communications practice: drug-label look-ups, US-UK label comparisons, claim checking against cited papers, citations, trial facts, source conflicts, questions that should not be answered, and requests carrying patient identifiers. Gold answers were verified against primary sources by a medical writer. Agents use real literature, label, registry and privacy tools, frozen as recorded responses and a fixed search collection so every model sees the same evidence. Each task runs five times clean and five times under one injected fault (timeout, empty result, truncated page, outdated label, planted instruction), scored with pass^k. A model judge, used only where code cannot score, agrees with the medical writer's blinded grading on 29 of 30 items (Cohen's kappa 0.91). Across 1,000 scored runs, Claude Sonnet 5.5 succeeded on 98% of tasks in a single run and 96% when all five runs had to be right; Gemini 3.5 Flash fell from 84% to 72%. Most of Gemini's failures (58 of 79) were runs that exhausted the tool-call budget searching for evidence that does not exist. In all 20 runs of one claim-checking task, both models identified that a relative risk reduction had been presented as absolute, yet rated the claim partially supported rather than unsupported. Injected faults barely changed pass rates; only an outdated label changed behaviour, altering where models looked rather than what they concluded. We release the tasks, tools, scorers and failure taxonomy.

## Order of steps

1. Zenodo: connect the GitHub repo in Zenodo (Account > GitHub), then publish a GitHub release `v1.0.0`. Zenodo mints a DOI from `.zenodo.json`.
2. Add that DOI to the write-up (Section 9) and to the Comments line above.
3. Export the doc to PDF and submit to arXiv with the metadata above (arXiv accepts PDFs not produced from TeX).
