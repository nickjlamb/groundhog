"""Consistency metrics across repeated runs of the same task.

Spec (docs/design-spec.md, section 5, Consistency and Uncertainty):
  pass@1  - mean success across runs
  pass^k  - probability that k runs, drawn without replacement from the n
            runs of a task, all succeed: C(c, k) / C(n, k), where c is the
            number of successful runs. Averaged across tasks.
  Bootstrap confidence intervals over tasks for every headline figure.
"""

import random
from math import comb


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k for one task with n runs, of which c succeeded."""
    return comb(c, k) / comb(n, k)


def mean_pass_hat_k(results: dict, k: int) -> float:
    """Average pass^k across tasks.

    results maps each task id to its list of run outcomes, e.g.
    {"label-001": [True, True, False, True, True], ...}
    Tasks with fewer than k runs are left out.
    """
    scores = [pass_hat_k(len(runs), sum(runs), k) for runs in results.values() if len(runs) >= k]
    return sum(scores) / len(scores) if scores else float("nan")


def pass_at_1(results: dict) -> float:
    """Mean success rate per task, averaged across tasks (equals pass^1)."""
    return mean_pass_hat_k(results, 1)


def bootstrap_ci(results: dict, stat, n_boot: int = 2000, alpha: float = 0.05, seed: int = 0):
    """Percentile bootstrap over tasks: resample tasks with replacement and
    recompute stat(results). Returns (low, high)."""
    rng = random.Random(seed)
    tasks = list(results)
    if not tasks:
        return float("nan"), float("nan")
    vals = []
    for _ in range(n_boot):
        sample = {f"{i}": results[rng.choice(tasks)] for i in range(len(tasks))}
        v = stat(sample)
        if v == v:                     # skip NaN
            vals.append(v)
    vals.sort()
    lo = vals[int(alpha / 2 * len(vals))]
    hi = vals[min(len(vals) - 1, int((1 - alpha / 2) * len(vals)))]
    return lo, hi
