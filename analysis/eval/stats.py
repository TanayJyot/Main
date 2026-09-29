"""Small, dependency-free statistics for the lexicon comparison."""

from __future__ import annotations

from typing import Callable, Dict, Optional, Sequence

import numpy as np


def bootstrap_ci(values: Sequence[float], statistic: Callable = np.mean,
                 resamples: int = 2000, level: float = 0.95,
                 seed: Optional[int] = 0) -> Dict[str, float]:
    """Percentile bootstrap over items (glosses), ignoring NaN.

    Resampling is over glosses because glosses are the unit that varies: a
    different pilot list would give a different number, and the interval
    should say how much.
    """
    data = np.asarray([v for v in values if v is not None and np.isfinite(v)], float)
    if data.size == 0:
        return {"estimate": float("nan"), "low": float("nan"), "high": float("nan"), "n": 0}
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, data.size, size=(resamples, data.size))
    stats = np.array([statistic(data[row]) for row in draws])
    tail = (1 - level) / 2
    return {"estimate": float(statistic(data)),
            "low": float(np.quantile(stats, tail)),
            "high": float(np.quantile(stats, 1 - tail)),
            "n": int(data.size)}


def separation_auc(same: Sequence[float], different: Sequence[float]) -> float:
    """Probability that a random same-sign pair is closer than a random
    different-sign pair (ties count half). 0.5 means the metric cannot tell
    them apart at all; 1.0 means it always can.

    This is the calibration question in one number: if it is not well above
    0.5, a small distance between an old and a new sign means nothing.
    """
    same = np.asarray([v for v in same if np.isfinite(v)], float)
    different = np.asarray([v for v in different if np.isfinite(v)], float)
    if same.size == 0 or different.size == 0:
        return float("nan")
    less = (same[:, None] < different[None, :]).sum()
    ties = (same[:, None] == different[None, :]).sum()
    return float((less + 0.5 * ties) / (same.size * different.size))


def top_k_hit(distances: Dict[str, float], correct: set, k: int) -> bool:
    """Whether any correct candidate is among the k nearest."""
    ranked = sorted(distances, key=distances.get)
    return any(candidate in correct for candidate in ranked[:k])
