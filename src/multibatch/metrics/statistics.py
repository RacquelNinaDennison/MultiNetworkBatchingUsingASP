"""Statistical tests for comparing experiment configurations.

Provides paired Wilcoxon signed-rank tests, bootstrap confidence
intervals, and effect size computation for resilience metric
comparisons across instance seeds.
"""

from __future__ import annotations

import numpy as np
from scipy import stats


def paired_wilcoxon(
    baseline: list[float],
    treatment: list[float],
) -> dict:
    """Paired Wilcoxon signed-rank test.

    Compares two matched sets of resilience values (e.g. R_1 under
    off_off vs both, paired by instance seed).

    Returns dict with statistic, p_value, effect_size (rank-biserial r),
    n_pairs, median_diff, and significant (bool at alpha=0.05).
    """
    baseline_arr = np.array(baseline)
    treatment_arr = np.array(treatment)
    diffs = treatment_arr - baseline_arr

    # Drop zero differences (ties)
    nonzero = diffs[diffs != 0]
    n = len(nonzero)

    if n < 5:
        return {
            "statistic": None,
            "p_value": None,
            "effect_size": None,
            "n_pairs": len(baseline),
            "n_nonzero": n,
            "median_diff": float(np.median(diffs)),
            "significant": False,
            "note": "too few non-tied pairs for Wilcoxon (need >= 5)",
        }

    result = stats.wilcoxon(
        baseline_arr, treatment_arr, alternative="two-sided",
    )

    # Rank-biserial effect size: r = 1 - (2W / (n*(n+1)/2))
    # where W is the test statistic (sum of negative ranks)
    w = result.statistic
    r = 1.0 - (2.0 * w) / (n * (n + 1) / 2.0)

    return {
        "statistic": float(w),
        "p_value": float(result.pvalue),
        "effect_size": round(float(r), 4),
        "n_pairs": len(baseline),
        "n_nonzero": n,
        "median_diff": round(float(np.median(diffs)), 4),
        "significant": result.pvalue < 0.05,
    }


def bootstrap_ci(
    values: list[float],
    n_bootstrap: int = 10_000,
    confidence: float = 0.95,
    seed: int = 42,
) -> dict:
    """Bootstrap confidence interval for the mean.

    Returns dict with mean, ci_lower, ci_upper, std, n.
    """
    arr = np.array(values)
    n = len(arr)

    if n < 2:
        return {
            "mean": float(arr[0]) if n == 1 else None,
            "ci_lower": None,
            "ci_upper": None,
            "std": 0.0,
            "n": n,
        }

    rng = np.random.default_rng(seed)
    boot_means = np.array([
        rng.choice(arr, size=n, replace=True).mean()
        for _ in range(n_bootstrap)
    ])

    alpha = 1.0 - confidence
    lo = np.percentile(boot_means, 100 * alpha / 2)
    hi = np.percentile(boot_means, 100 * (1 - alpha / 2))

    return {
        "mean": round(float(arr.mean()), 4),
        "ci_lower": round(float(lo), 4),
        "ci_upper": round(float(hi), 4),
        "std": round(float(arr.std(ddof=1)), 4),
        "n": n,
    }


def compare_configs(
    results: dict[str, list[float]],
    baseline_key: str = "baseline",
) -> dict[str, dict]:
    """Compare all configs against baseline.

    Parameters
    ----------
    results : dict mapping config name to list of metric values,
              one per instance (matched across configs).
    baseline_key : which config is the baseline.

    Returns dict mapping each non-baseline config to its
    Wilcoxon test result + bootstrap CIs for both configs.
    """
    baseline_vals = results[baseline_key]
    comparisons = {}

    for config, vals in results.items():
        if config == baseline_key:
            continue
        comparisons[config] = {
            "wilcoxon": paired_wilcoxon(baseline_vals, vals),
            "baseline_ci": bootstrap_ci(baseline_vals),
            "treatment_ci": bootstrap_ci(vals),
        }

    return comparisons
