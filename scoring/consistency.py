"""Consistency metrics across repeated runs of the same task.

Spec (docs/design-spec.md, section 5, Consistency):
  pass@1  - mean success across runs
  pass^k  - probability that k runs, drawn without replacement from the n
            runs of a task, all succeed: C(c, k) / C(n, k), where c is the
            number of successful runs. Averaged across tasks.
"""

from math import comb


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k for one task with n runs, of which c succeeded."""
    raise NotImplementedError("Nick: write this")
