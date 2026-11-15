"""Completeness based on a monotonic counter final value."""

from __future__ import annotations


def completeness(expected: int, received_counter: float) -> float | None:
    """Return valid/expected percent, or null when the denominator is zero."""

    if expected < 0 or received_counter < 0:
        raise ValueError("counts must be non-negative")
    if expected == 0:
        return None
    return min(received_counter, expected) / expected * 100.0


def loss(expected: int, received_counter: float) -> float | None:
    """Return missing/expected percent for the counter model."""

    value = completeness(expected, received_counter)
    return None if value is None else max(0.0, 100.0 - value)
