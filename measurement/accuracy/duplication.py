"""Duplicate observations, without claiming complete duplicate detection."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable


def duplication_rate(sequence_ids: Iterable[int]) -> float | None:
    """Return duplicate/received percent; null means no received samples."""

    values = list(sequence_ids)
    if not values:
        return None
    duplicates = sum(count - 1 for count in Counter(values).values() if count > 1)
    return duplicates / len(values) * 100.0
