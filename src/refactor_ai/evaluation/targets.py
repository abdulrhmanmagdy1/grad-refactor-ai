"""Numerical targets of protocol eval-v1, set from the validation baseline before the test run.

Rule (fixed on 2026-10-21, before any test-split run; docs/evaluation/protocol.md):

- Floors: for every arm, the target for overall acceptance (proposal_ready) and for
  syntax validity is the lower limit of the two-sided 95 % Clopper-Pearson (exact
  binomial) interval of the validation proportion. A floor is met when the test-split
  rate, over all attempted cases, is at least that limit.
- Ceiling: for every arm, the target for the failure rate (run failed, any reason) is the
  upper limit of the same interval for the validation failure proportion. It is met when
  the test-split failure rate is at most that limit.
- Where a validation count is not determinable under the frozen code (see
  experiments/evaluation/validation-2026-10-21/code-change-check.json), a floor uses the
  smallest and a ceiling the largest attainable count.
- Expected directions: for each pre-declared paired comparison, the expected direction is
  the sign of the validation difference when its Holm-adjusted exact McNemar p-value is
  below 0.05 for every attainable validation outcome; otherwise no direction is expected.
  On the test split a direction is "confirmed" when the difference has that sign with a
  Holm-adjusted p below 0.05, "reversed" when it has the opposite sign with such a p, and
  "not confirmed" otherwise.

The interval limits describe the sampling variation of an 84-case validation estimate;
the test split comes from unseen families, so a missed target is reported as a finding,
never re-tuned. Targets are thresholds, not hypothesis tests.
"""

from __future__ import annotations

import math

CONFIDENCE = 0.95
ALPHA = 0.05
FLOOR_METRICS = ("proposal_ready", "syntax_valid")
CEILING_METRICS = ("failed",)
RULE = (
    "Floors (proposal_ready, syntax_valid): lower limit of the two-sided 95% Clopper-Pearson "
    "interval of the validation proportion; ceiling (failed): upper limit of that interval; "
    "a count that is not determinable under the frozen code uses its least favourable "
    "attainable value. Expected direction of a paired comparison: the sign of the validation "
    "difference when its Holm-adjusted exact McNemar p < 0.05 for every attainable "
    "validation outcome, otherwise none."
)


def _log_binomial_pmf(k: int, n: int, p: float) -> float:
    return (
        math.lgamma(n + 1)
        - math.lgamma(k + 1)
        - math.lgamma(n - k + 1)
        + k * math.log(p)
        + (n - k) * math.log1p(-p)
    )


def binomial_cdf(k: int, n: int, p: float) -> float:
    """P(X <= k) for X ~ Binomial(n, p)."""
    if k < 0:
        return 0.0
    if k >= n or p <= 0.0:
        return 1.0
    if p >= 1.0:
        return 0.0
    return min(1.0, sum(math.exp(_log_binomial_pmf(i, n, p)) for i in range(k + 1)))


def _bisect(function, target: float, increasing: bool) -> float:
    low, high = 0.0, 1.0
    for _ in range(200):
        middle = (low + high) / 2
        value = function(middle)
        if (value < target) == increasing:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def clopper_pearson(successes: int, n: int, confidence: float = CONFIDENCE) -> tuple[float, float]:
    """Two-sided exact (Clopper-Pearson) confidence interval for a binomial proportion."""
    if n < 1 or not 0 <= successes <= n:
        raise ValueError(f"need 0 <= successes <= n and n >= 1, got {successes} of {n}")
    tail = (1.0 - confidence) / 2
    if successes == 0:
        lower = 0.0
    else:  # P(X >= successes; p) = tail, increasing in p
        lower = _bisect(lambda p: 1.0 - binomial_cdf(successes - 1, n, p), tail, True)
    if successes == n:
        upper = 1.0
    else:  # P(X <= successes; p) = tail, decreasing in p
        upper = _bisect(lambda p: binomial_cdf(successes, n, p), tail, False)
    return lower, upper


def _floor_limit(successes: int, n: int) -> float:
    """Lower interval limit, rounded down to 6 decimals (never stricter than the rule)."""
    return math.floor(clopper_pearson(successes, n)[0] * 1e6) / 1e6


def _ceiling_limit(failures: int, n: int) -> float:
    """Upper interval limit, rounded up to 6 decimals (never stricter than the rule)."""
    return math.ceil(clopper_pearson(failures, n)[1] * 1e6) / 1e6


def derive_arm_targets(counts: dict[str, dict[str, list[int]]], n: int, test_n: int) -> dict:
    """Targets per arm from validation counts given as [least, most] attainable counts.

    The test counts are the smallest (floor) or largest (ceiling) count k out of test_n
    whose rate k / test_n meets the limit, computed exactly as assess() compares rates.
    """
    targets: dict[str, dict] = {}
    for arm, by_metric in sorted(counts.items()):
        entry = {}
        for metric in FLOOR_METRICS:
            least, most = by_metric[metric]
            limit = _floor_limit(least, n)
            entry[metric] = {
                "kind": "floor",
                "validation_count": [least, most],
                "validation_n": n,
                "count_used": least,
                "limit_rate": limit,
                "test_n": test_n,
                "test_count_needed": next(k for k in range(test_n + 1) if k / test_n >= limit),
            }
        for metric in CEILING_METRICS:
            least, most = by_metric[metric]
            limit = _ceiling_limit(most, n)
            entry[metric] = {
                "kind": "ceiling",
                "validation_count": [least, most],
                "validation_n": n,
                "count_used": most,
                "limit_rate": limit,
                "test_n": test_n,
                "test_count_allowed": max(k for k in range(test_n + 1) if k / test_n <= limit),
            }
        targets[arm] = entry
    return targets


def direction(first_only: int, second_only: int, holm_p: float, alpha: float = ALPHA) -> str:
    """'first' or 'second' (the arm that accepts more cases) when significant, else 'none'."""
    if holm_p >= alpha or first_only == second_only:
        return "none"
    return "first" if first_only > second_only else "second"


def assess(targets: dict, metrics: dict, paired: list[dict]) -> dict:
    """Compare report metrics (report.arm_metrics) and paired results with frozen targets."""
    rows = []
    for arm, by_metric in sorted(targets["arms"].items()):
        for metric, target in by_metric.items():
            limit = target["limit_rate"]
            row = {"arm": arm, "metric": metric, "kind": target["kind"], "limit_rate": limit}
            row.update(numerator=None, denominator=None, rate=None, met=None)
            measured = (metrics.get(arm) or {}).get("rates", {}).get(metric)
            if measured is not None:  # an arm that was not run stays unassessed
                rate = measured["rate"]
                row.update(
                    numerator=measured["numerator"],
                    denominator=measured["denominator"],
                    rate=rate,
                    met=rate >= limit if target["kind"] == "floor" else rate <= limit,
                )
            rows.append(row)
    by_name = {item["comparison"]: item for item in paired}
    comparisons = []
    for expected in targets["directions"]:
        name = expected["comparison"]
        first, second = name.split(" vs ")
        item = by_name.get(name)
        if item is None:
            comparisons.append({**expected, "observed": None, "outcome": "not measured"})
            continue
        observed = direction(item[f"{first}_only"], item[f"{second}_only"], item["holm_adjusted_p"])
        if expected["expected"] == "none":
            outcome = "no direction expected"
        elif observed == expected["expected"]:
            outcome = "confirmed"
        elif observed == "none":
            outcome = "not confirmed"
        else:
            outcome = "reversed"
        comparisons.append(
            {
                **expected,
                "first_only": item[f"{first}_only"],
                "second_only": item[f"{second}_only"],
                "holm_adjusted_p": item["holm_adjusted_p"],
                "observed": observed,
                "outcome": outcome,
            }
        )
    return {"rule": targets["rule"], "arms": rows, "comparisons": comparisons}
