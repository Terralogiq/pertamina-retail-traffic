"""Spearman rank correlation with uncertainty, for the Places vs traffic screen (docs/plans/poi-analysis.md).

Pure Python, no numpy. With 10 sites an exact test would enumerate 10! pairings, so the p-value is a seeded Monte
Carlo estimate over PERMUTATIONS shuffles (error about +-0.003) and the interval is a percentile bootstrap. The
shuffles are cached per sample size: every test of one screen reuses them, so the work is shared.
"""
import math
import random
from functools import lru_cache
from operator import itemgetter, mul

PERMUTATIONS = 20_000
BOOTSTRAPS = 2_000
SEED = 1
MIN_N = 3
_EPS = 1e-9


def rank(values):
    """1-based ranks; tied values share the average of the ranks they span."""
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def _centered(values):
    ranks = rank(values)
    mean = sum(ranks) / len(ranks)
    return [r - mean for r in ranks]


def _pearson(a, b):
    """Correlation of two centred vectors; None when either is constant."""
    denom = math.sqrt(sum(v * v for v in a) * sum(v * v for v in b))
    return sum(map(mul, a, b)) / denom if denom > _EPS else None


def spearman(x, y):
    """Rank correlation (Pearson on average ranks, so ties are handled); None when x or y is constant."""
    return _pearson(_centered(x), _centered(y)) if len(x) >= 2 else None


@lru_cache(maxsize=8)
def _shuffles(n, count, seed):
    rng = random.Random(seed)
    return tuple(tuple(rng.sample(range(n), n)) for _ in range(count))


@lru_cache(maxsize=8)
def _resamples(n, count, seed):
    rng = random.Random(seed)
    return tuple(tuple(rng.randrange(n) for _ in range(n)) for _ in range(count))


def permutation_p(x, y, count=PERMUTATIONS, seed=SEED):
    """Two-sided p: the share of random re-pairings of x with y whose |rho| is at least the observed one."""
    rx, ry = _centered(x), _centered(y)
    denom = math.sqrt(sum(v * v for v in rx) * sum(v * v for v in ry))
    if len(x) < MIN_N or denom <= _EPS:
        return None
    observed = abs(sum(map(mul, rx, ry))) - _EPS * denom
    hits = sum(1 for perm in _shuffles(len(x), count, seed)
               if abs(sum(map(mul, rx, itemgetter(*perm)(ry)))) >= observed)
    return (hits + 1) / (count + 1)


def _percentile(sorted_values, q):
    """Linear interpolation between closest ranks (numpy's default)."""
    pos = (len(sorted_values) - 1) * q
    low = math.floor(pos)
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (pos - low)


def bootstrap_ci(x, y, count=BOOTSTRAPS, seed=SEED):
    """95% percentile interval of rho over resampled sites; resamples where x or y is constant are skipped."""
    values = []
    for idx in _resamples(len(x), count, seed):
        rho = spearman([x[i] for i in idx], [y[i] for i in idx])
        if rho is not None:
            values.append(rho)
    if len(values) < count // 2:
        return None, None
    values.sort()
    return _percentile(values, 0.025), _percentile(values, 0.975)


def loo_range(x, y):
    """Smallest and largest rho with each site dropped in turn; shows whether one site carries the result."""
    values = [r for i in range(len(x))
              if (r := spearman(x[:i] + x[i + 1:], y[:i] + y[i + 1:])) is not None]
    return (min(values), max(values)) if values else (None, None)


def analyse(x, y):
    """rho, 95% interval, permutation p, leave-one-out range and n for paired samples (needs n >= MIN_N)."""
    n = len(x)
    empty = {"rho": None, "ci_low": None, "ci_high": None, "p": None, "loo_min": None, "loo_max": None, "n": n}
    rho = spearman(x, y) if n >= MIN_N else None
    if rho is None:
        return empty
    ci_low, ci_high = bootstrap_ci(x, y)
    loo_min, loo_max = loo_range(x, y)
    return {"rho": rho, "ci_low": ci_low, "ci_high": ci_high, "p": permutation_p(x, y),
            "loo_min": loo_min, "loo_max": loo_max, "n": n}
