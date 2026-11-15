"""Descriptive statistics with explicit empty-input behavior."""

from __future__ import annotations

from math import sqrt
from statistics import median
from typing import Iterable


def summarize(values: Iterable[float]) -> dict[str, float | None]:
    """Return descriptive statistics; null values mean no observations."""

    data = [float(value) for value in values]
    if not data:
        return {
            "count": 0.0, "mean": None, "median": None, "std": None,
            "min": None, "max": None, "p50": None, "p90": None,
            "p95": None, "p99": None,
        }
    mean = sum(data) / len(data)
    variance = sum((value - mean) ** 2 for value in data) / len(data)

    def percentile(percent: float) -> float:
        ordered = sorted(data)
        index = (len(ordered) - 1) * percent / 100
        lower = int(index)
        upper = min(lower + 1, len(ordered) - 1)
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)

    return {
        "count": float(len(data)),
        "mean": mean,
        "median": float(median(data)),
        "std": sqrt(variance),
        "min": min(data),
        "max": max(data),
        "p50": percentile(50),
        "p90": percentile(90),
        "p95": percentile(95),
        "p99": percentile(99),
    }




def counter_rate(
    timestamps: Iterable[float],
    counters: Iterable[float],
) -> list[float | None]:
    """Calculate counter rate while handling counter resets."""

    times = list(timestamps)
    values = list(counters)

    if len(times) != len(values):
        raise ValueError("timestamps and counters must have equal length")

    rates: list[float | None] = []

    for i in range(len(values)):
        if i == 0:
            rates.append(None)
            continue

        elapsed = float(times[i]) - float(times[i - 1])
        current = float(values[i])
        previous = float(values[i - 1])

        if elapsed <= 0:
            rates.append(None)
            continue

        if current < previous:
            # Counter reset: assume it restarted from zero.
            increment = current
        else:
            increment = current - previous

        rates.append(increment / elapsed)

    return rates
