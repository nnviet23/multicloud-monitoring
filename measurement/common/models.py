"""Typed data models used by measurement groups."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class Provenance(str, Enum):
    """Origin classification for a value."""

    MEASURED = "measured"
    ESTIMATED = "estimated"
    UNAVAILABLE = "unavailable"
    SIMULATED = "simulated"


class RunStatus(str, Enum):
    """Status of an experiment run."""

    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class DataPoint:
    """One ground-truth datapoint."""

    experiment_id: str
    source_id: str
    sequence_id: int
    event_timestamp: str
    metric_name: str
    metric_value: float
    sent_ok: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Experiment:
    """Experiment identity and immutable run metadata."""

    experiment_id: str
    scenario: str
    expected_datapoints: int
    sources: list[str]
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    provenance: Provenance = Provenance.SIMULATED
    status: RunStatus = RunStatus.PARTIAL

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["provenance"] = self.provenance.value
        result["status"] = self.status.value
        return result


@dataclass
class MeasurementResult:
    """Result with explicit status and provenance."""

    status: RunStatus
    provenance: Provenance
    values: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["status"] = self.status.value
        result["provenance"] = self.provenance.value
        return result
