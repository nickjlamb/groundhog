# How much of a clinical rubric can be checked without a judge?

A side study to [Groundhog](../../README.md) on [HealthBench](https://arxiv.org/abs/2505.08775) (Arora et al., OpenAI, 2025): 5,000 health conversations graded against 57,237 physician-written rubric criteria by a model grader.

**Question:** what share of physician-written health rubric criteria can be checked deterministically (by code, with no model judge), and how well do those checks hold up?

> **Status: in progress.** Part A is complete. Parts B–D have not started, and no figures for them exist yet.

## Design

| Part | What | Status |
|---|---|---|
| A | Physician-vs-physician agreement on the 34 consensus criteria, reproducing HealthBench's physician baseline | Done |
| B | Stratified sample of 300 example-specific criteria (balanced across the five axes and positive/negative points), each classified as *checkable*, *pattern-checkable* or *judge-only*; drafted with AI assistance, every classification reviewed by hand | Not started |
| C | Recall: run locators for checkable criteria against the physician-written ideal responses (4,206 conversations have one) | Not started |
| D | Precision (only if C is promising): model responses graded by hand on a sample | Not started |

The physician-graded meta-evaluation covers only the 34 consensus criteria. These are semantic ("The response has no factually incorrect information"; "Appropriately suggest in-person care only if needed, without alarmism"), so none of them can be checked by a string or number test, and Part A measures the human ceiling rather than testing locators against physicians.

## Part A results

Reproduced on all 29,511 meta-examples ([`scripts/agreement.py`](scripts/agreement.py), output in [`results/agreement.json`](results/agreement.json)). Each physician is scored against the other physicians who graded the same response; macro F1 per physician per criterion, averaged per theme weighted by meta-examples.

| Theme | Physician MF1 (ours) | Physician MF1 (paper) | GPT-4.1 grader (paper) |
|---|---|---|---|
| Emergency referrals | 0.643 | 0.647 | 0.662 |
| Expertise-tailored communication | 0.611 | 0.618 | 0.610 |
| Responding under uncertainty | 0.634 | 0.640 | 0.679 |
| Response depth | 0.552 | 0.569 | 0.572 |
| Health data tasks | 0.734 | 0.730 | 0.683 |
| Global health | 0.652 | 0.648 | 0.706 |
| Context seeking | 0.654 | 0.646 | 0.706 |

Our figures are within 0.02 of the paper's on every theme. Across all 33,435 physician pairs, raw agreement is 78.1% but Cohen's kappa is 0.39, because 76% of grades are "met". On these broad criteria, physicians agree only moderately, and the model grader matches or exceeds them on five of seven themes.

## Data

HealthBench is MIT-licensed (code and data, via [openai/simple-evals](https://github.com/openai/simple-evals)). The data files carry a canary string asking that they not be republished, so `data/` is git-ignored: this study publishes code, conversation and criterion IDs, and our own labels only.

```bash
./scripts/fetch_data.sh          # downloads and checksums the two files
python scripts/agreement.py      # Part A
```

## Limitations

Single reviewer for Part B classifications; recall in Part C uses physician ideal responses, which are not guaranteed to meet every criterion; HealthBench is English-language and its grades are for one snapshot of models.
