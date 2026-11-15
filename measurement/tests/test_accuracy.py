"""Accuracy tests with explicitly synthetic inputs."""

from datetime import datetime, timezone

import pytest

from accuracy.compare import compare
from accuracy.completeness import completeness, loss
from accuracy.correctness import classify_sample
from accuracy.duplication import duplication_rate


def test_counter_completeness_and_loss() -> None:
    assert completeness(100, 90) == 90
    assert loss(100, 90) == 10
    assert completeness(0, 0) is None


def test_duplication() -> None:
    assert duplication_rate([1, 1, 2, 3]) == 25
    assert duplication_rate([]) is None


def test_correctness_and_classification() -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    expected = {"metric_name": "m", "source_id": "aws", "metric_value": 1}
    received = {"metric_name": "m", "source_id": "aws", "value": 1, "timestamp": timestamp}
    assert classify_sample(expected, received) == "valid"
    received["timestamp"] = "not-a-timestamp"
    assert classify_sample(expected, received) == "ts_deviation"


def test_compare_missing_fields_and_empty() -> None:
    expected = [{"sequence_id": 1, "metric_name": "m", "source_id": "aws", "metric_value": 1}]
    received = [{
        "sequence_id": 1, "metric_name": "m", "source_id": "aws", "value": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }]
    result = compare(expected, received, received_counter=1)
    assert result["completeness_percent"] == 100
    assert result["classifications"]["valid"] == 1
    assert compare([], [], None)["completeness_percent"] is None


def test_invalid_count() -> None:
    with pytest.raises(ValueError):
        completeness(-1, 0)


def test_invalid_timestamp_is_classified() -> None:
    expected = {"metric_name": "m", "source_id": "aws", "metric_value": 1}
    received = {"metric_name": "m", "source_id": "aws", "value": 1, "timestamp": ""}
    assert classify_sample(expected, received) == "ts_deviation"
