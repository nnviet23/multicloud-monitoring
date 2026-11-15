"""Immutable experiment result storage."""

from __future__ import annotations

import csv
import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .models import DataPoint

ROOT = Path(__file__).resolve().parents[1]


def new_experiment_id(scenario: str) -> str:
    """Create a collision-resistant experiment ID."""

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}_{scenario}_{uuid.uuid4().hex[:8]}"


def create_run_dir(experiment_id: str) -> Path:
    """Create a run directory without overwriting an existing run."""

    path = ROOT / "results" / "accuracy" / experiment_id
    path.mkdir(parents=True, exist_ok=False)
    return path


def write_metadata(path: Path, metadata: dict[str, Any]) -> None:
    """Write metadata exactly once."""

    (path / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def write_ground_truth(path: Path, points: Iterable[DataPoint]) -> None:
    """Write ground truth as an independent CSV."""

    rows = [point.as_dict() if isinstance(point, DataPoint) else asdict(point) for point in points]
    fields = [
        "experiment_id", "source_id", "sequence_id", "event_timestamp",
        "metric_name", "metric_value", "sent_ok",
    ]
    with (path / "ground_truth.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_received_samples(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    """Write raw received samples."""

    fields = ["source_id", "sequence_id", "timestamp", "metric_name", "value", "labels"]
    with (path / "received_samples.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)



def create_performance_run_dir(run_id: str) -> Path:
    """Create an isolated performance experiment directory."""

    path = ROOT / "results" / "performance" / run_id
    path.mkdir(parents=True, exist_ok=False)
    return path


def _write_json_once(path: Path, filename: str, data: dict[str, Any]) -> None:
    """Write a JSON file without overwriting an existing result."""

    with (path / filename).open("x", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def write_raw_samples(
    path: Path,
    rows: Iterable[dict[str, Any]],
) -> None:
    """Write raw performance measurements to CSV."""

    rows = list(rows)

    # Preserve all fields supplied by the measurement source.
    fields = [
        "timestamp",
        "metric_name",
        "value",
        "source_id",
        "sequence_id",
        "labels",
    ]

    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)

    with (path / "raw_samples.csv").open(
        "x", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="raise",
        )
        writer.writeheader()

        for row in rows:
            normalized = {
                key: (
                    json.dumps(value, ensure_ascii=False)
                    if isinstance(value, (dict, list))
                    else value
                )
                for key, value in row.items()
            }
            writer.writerow(normalized)


def write_summary(
    path: Path,
    summary: dict[str, Any],
) -> None:
    """Write aggregated performance statistics."""

    _write_json_once(path, "summary.json", summary)


def write_performance_metadata(
    path: Path,
    metadata: dict[str, Any],
) -> None:
    """Write performance experiment metadata."""

    _write_json_once(path, "metadata.json", metadata)
