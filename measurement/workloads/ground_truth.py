"""Independent, deterministic ground-truth generation.

The cluster job never has to copy this file back to the workstation.  Both sides
derive the same values from ``scenario``, ``source_id`` and ``seed``.
"""

from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta, timezone
from typing import Sequence

from common.models import DataPoint
from .scenarios import expected_count


def _stable_rng(scenario: str, source_id: str, seed: int) -> random.Random:
    """Return a process-independent RNG for one source stream."""

    material = f"{scenario}\0{source_id}\0{seed}".encode("utf-8")
    digest = hashlib.sha256(material).digest()
    return random.Random(int.from_bytes(digest[:16], "big"))


def _build_for_source(
    scenario: str,
    source_id: str,
    seed: int,
    metric_name: str,
    experiment_id: str,
    count: int | None = None,
) -> list[DataPoint]:
    if source_id not in {"aws", "azure"}:
        raise ValueError("source_id must be aws or azure")
    count = expected_count(scenario) if count is None else count
    rng = _stable_rng(scenario, source_id, seed)
    base = datetime(2020, 1, 1, tzinfo=timezone.utc)
    points: list[DataPoint] = []
    for sequence in range(1, count + 1):
        # A deterministic value makes the last-value gauge independently
        # checkable without putting sequence_id in a Prometheus label.
        value = round(rng.uniform(0.0, 1000.0), 6)
        points.append(
            DataPoint(
                experiment_id=experiment_id,
                source_id=source_id,
                sequence_id=sequence,
                event_timestamp=(base + timedelta(microseconds=sequence)).isoformat(),
                metric_name=metric_name,
                metric_value=value,
            )
        )
    return points


def build_ground_truth(
    experiment_id: str,
    sources: list[str],
    count_per_source: int,
    metric_name: str,
) -> list[DataPoint]:
    """Create deterministic datapoints using the original public signature."""

    if not sources or count_per_source <= 0:
        raise ValueError("sources and positive count_per_source are required")
    points: list[DataPoint] = []
    for source in sources:
        generated = _build_for_source(
            f"legacy-{count_per_source}",
            source,
            int.from_bytes(hashlib.sha256(experiment_id.encode()).digest()[:8], "big"),
            metric_name,
            experiment_id,
            count=count_per_source,
        )
        points.extend(generated[:count_per_source])
    return points


def build_ground_truth_for_source(
    scenario: str,
    source_id: str,
    seed: int,
    metric_name: str,
    experiment_id: str,
) -> list[DataPoint]:
    """Build one source using the deterministic scenario/source/seed contract."""

    return _build_for_source(scenario, source_id, seed, metric_name, experiment_id)


def build_ground_truth_for_sources(
    scenario: str,
    sources: Sequence[str],
    seed: int,
    metric_name: str,
    experiment_id: str,
) -> list[DataPoint]:
    """Build the complete local ground truth for an experiment."""

    points: list[DataPoint] = []
    for source in sources:
        points.extend(build_ground_truth_for_source(scenario, source, seed, metric_name, experiment_id))
    return points
