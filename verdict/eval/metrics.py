"""Shared metric helpers.

    wilson(k, n) -> (low, high)   95% interval for a proportion k/n

With 100 or 200 questions, an accuracy of 85% could really be anywhere from
about 77% to 91%. Every accuracy in the calibration report carries this
interval so small samples are not over-read.
"""

from __future__ import annotations

import math


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval. Better than the plain +/- formula near 0% and 100%."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def rate(k: int, n: int) -> dict:
    """{"k", "n", "rate", "low", "high"} for reports."""
    low, high = wilson(k, n)
    return {"k": k, "n": n, "rate": k / n if n else 0.0, "low": low, "high": high}
