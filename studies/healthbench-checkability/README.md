# How much of a clinical rubric can be checked without a judge?

A side study to [Groundhog](../../README.md) on [HealthBench](https://arxiv.org/abs/2505.08775) (Arora et al., OpenAI, 2025): 5,000 health conversations graded against 57,237 physician-written rubric criteria by a model grader.

**Question:** what share of physician-written health rubric criteria can be checked deterministically (by code, with no model judge), and how well do those checks hold up?

> **Status:** Parts A–C are complete. Part D (hand-grading model responses) was not run: see below.

## Design

| Part | What | Status |
|---|---|---|
| A | Physician-vs-physician agreement on the 34 consensus criteria, reproducing HealthBench's physician baseline | Done |
| B | Stratified sample of 300 example-specific criteria (balanced across the five axes and positive/negative points), each classified as *checkable*, *pattern-checkable* or *judge-only*; drafted with AI assistance, every classification adjudicated by Nick | Done |
| C | Run locators for the checkable criteria against the physician-written ideal responses (4,206 conversations have one); read every disagreement by hand | Done |
| D | Precision: model responses graded by hand on a sample | Not run (would not change the conclusions) |

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

## Part B results

300 example-specific criteria, 30 from each axis × sign stratum ([`scripts/sample.py`](scripts/sample.py), seed 20261105). Claude drafted a class for each; Nick adjudicated all 300 and changed 42 (32 pattern → judge-only, 10 pattern → checkable). Draft–final agreement 86%, Cohen's kappa 0.74. Final labels: [`results/part_b_labels.csv`](results/part_b_labels.csv) (IDs only).

Shares reweighted from the strata to all 49,184 example-specific criteria, with 95% bootstrap intervals (resampling within strata):

| Class | Share | 95% CI |
|---|---|---|
| Checkable: a specific entity, number, code or format feature decides it | 11.7% | 7.6–16.0 |
| Pattern-checkable: a short synonym or keyword list decides it | 19.3% | 13.3–26.0 |
| Judge-only | 69.1% | 61.8–76.0 |
| **Checkable or pattern-checkable** | **30.9%** | **24.0–38.2** |

| Stratum (n = 30 each) | C | P | J |
|---|---|---|---|
| Accuracy, positive | 8 | 6 | 16 |
| Accuracy, negative | 4 | 0 | 26 |
| Completeness, positive | 1 | 9 | 20 |
| Completeness, negative | 3 | 8 | 19 |
| Context awareness, positive | 0 | 4 | 26 |
| Context awareness, negative | 2 | 0 | 28 |
| Communication quality, positive | 11 | 2 | 17 |
| Communication quality, negative | 5 | 2 | 23 |
| Instruction following, positive | 8 | 6 | 16 |
| Instruction following, negative | 5 | 7 | 18 |

What the pattern shows:

- **Negative accuracy criteria are almost never checkable.** "Recommends tilting the head back during a nosebleed" cannot be checked by finding the words, because a good response may mention the act to warn against it.
- **Context-seeking criteria are judge-only.** A question mark plus a keyword does not establish that the response sought the right context, so 54 of 60 context-awareness criteria need a judge.
- **Format criteria are where code wins.** Communication and instruction-following criteria often specify structure (a table, bullet points, SOAP headings, a signature block, a length limit), which code can check reliably given structural and length locators.

These are classifications of what *could* be checked; Part C tests whether locators written for the checkable criteria actually work.

## Part C results

Locators for all 47 checkable criteria ([`scripts/locators.py`](scripts/locators.py)) were written and committed (a118afc) before being run on any response, then run on the 43 that have a physician-written ideal response ([`scripts/run_locators.py`](scripts/run_locators.py)). The expectation was that an ideal response meets every positive criterion and none of the negative ones. Every disagreement was read by Claude and then reviewed by Nick, who agreed with 22 of 23 readings and marked one unclear ([`results/part_c_review.csv`](results/part_c_review.csv)).

| Outcome | n |
|---|---|
| Locator agrees with the expectation | 21 |
| Disagrees, but the locator is right: the ideal response does not satisfy the criterion | 16 |
| Locator wrong | 5 |
| Unclear (named resources but no URLs, against "reference links") | 1 |
| **Locator verdict correct** | **37 / 43 (86%); 37 / 42 (88%) excluding the unclear case** |

One engine bug was found after the freeze (start-of-line patterns in terms lacked the multiline flag) and fixed; it changed one verdict (row 210). Before the fix the figure was 36 / 43.

The five locator errors, and the unclear case, show where "checkable" breaks down:

- **The number is present but in a different role** – 0.14 units/kg given as a bolus, where the criterion penalises it as an infusion rate.
- **Format without the expected markup** – point form written one step per line with no bullet characters.
- **The answer in substance, not in words** – "I can't confirm that it does" is a "no" that doesn't start with "No".
- **Examples read as requirements** – "organisations like HAS and SFD": the response followed French guidelines without naming either.
- **Language** – an English phrase checked against a Portuguese response.
- **Borderline wording (unclear)** – named resources with no URLs, against "reference links".

A second finding: **16 of 43 ideal responses (37%) fail the very criterion being tested** – no table where one is required, 16 teeth where the criterion says 20, no CDC or WHO where omitting them is penalised. In HealthBench, physician ideal responses and rubric criteria were written separately, so an "ideal" response is not a gold answer for its own rubric. That limits the ideal responses as a recall test, and it is why every disagreement was read rather than counted.

Limitations: the 21 agreements were not read by hand (a locator and the expectation could both be wrong); n is small.

## Data

HealthBench is MIT-licensed (code and data, via [openai/simple-evals](https://github.com/openai/simple-evals)). The data files carry a canary string asking that they not be republished, so `data/` is git-ignored: this study publishes code, conversation and criterion IDs, and our own labels only.

```bash
./scripts/fetch_data.sh          # downloads and checksums the two files
python scripts/agreement.py      # Part A
```

## Limitations

Single reviewer for Part B classifications; recall in Part C uses physician ideal responses, which are not guaranteed to meet every criterion; HealthBench is English-language and its grades are for one snapshot of models.
