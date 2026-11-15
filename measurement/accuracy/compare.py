"""Combine counter completeness and bounded sample comparison."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from .completeness import completeness, loss
from .correctness import classify_sample
from .duplication import duplication_rate


def compare(
    expected: Iterable[dict[str, Any]],
    received: Iterable[dict[str, Any]],
    received_counter: float | None = None,
) -> dict[str, Any]:
    """Compare received samples while preserving explicit unavailable states."""

    expected_rows = list(expected)
    received_rows = list(received)
    expected_by_sequence = {int(row["sequence_id"]): row for row in expected_rows}
    classes: Counter[str] = Counter()
    for row in received_rows:
        sequence = row.get("sequence_id")
        try:
            sequence_number = int(sequence) if sequence not in (None, "") else None
        except (TypeError, ValueError):
            sequence_number = None
        expected_row = expected_by_sequence.get(sequence_number) if sequence_number is not None else None
        if expected_row is None:
            classes["missing_expected"] += 1
        else:
            classes[classify_sample(expected_row, row)] += 1
    counter_value = float(received_counter) if received_counter is not None else None
    return {
        "expected": len(expected_rows),
        "received_samples": len(received_rows),
        "counter_final": counter_value,
        "completeness_percent": (
            completeness(len(expected_rows), counter_value)
            if counter_value is not None else None
        ),
        "loss_percent": (
            loss(len(expected_rows), counter_value)
            if counter_value is not None else None
        ),
        "duplication_percent": duplication_rate(
            int(row["sequence_id"])
            for row in received_rows
            if row.get("sequence_id") not in (None, "")
            and str(row.get("sequence_id")).lstrip("-").isdigit()
        ),
        "classifications": dict(classes),
        "limitation": "Sample counts cannot prove all duplicate or scrape-loss cases.",
    }
