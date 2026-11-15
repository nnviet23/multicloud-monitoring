"""Collector tests use a fake Prometheus-compatible client only."""

import json
from pathlib import Path

from common.result_writer import write_metadata
from workloads.collect import collect_run, wait_for_stable_counters
from workloads.ground_truth import build_ground_truth_for_source
from workloads.run_experiment import _accuracy_for_source


class FakeClient:
    base_url = "http://fake-thanos"

    def __init__(self, counter_values: list[float], expected: float = 1000):
        self.counter_values = iter(counter_values)
        self.last_counter = None
        self.expected = expected

    def query(self, expression: str):
        if "measurement_datapoints" in expression and "measurement_run" not in expression:
            try:
                self.last_counter = next(self.counter_values)
            except StopIteration:
                pass
            value = self.last_counter
        elif "measurement_run_expected" in expression:
            value = self.expected
        elif "measurement_last_sequence_id" in expression:
            value = 1000
        elif "measurement_last_value" in expression:
            value = build_ground_truth_for_source("small", "aws", 7, "measurement_datapoints_total", "exp")[-1].metric_value
        else:
            value = None
        result = [] if value is None else [{"metric": {"source_id": "aws"}, "value": [1, str(value)]}]
        return {"resultType": "vector", "result": result}

    def query_range(self, expression: str, start: str, end: str, step: str, dedup: bool = False):
        metric = expression.split("{", 1)[0]
        value = {
            "measurement_datapoints_total": 1000,
            "measurement_run_expected_total": 1000,
            "measurement_last_sequence_id": 1000,
            "measurement_last_value": build_ground_truth_for_source("small", "aws", 7, "measurement_datapoints_total", "exp")[-1].metric_value,
        }.get(metric)
        return {
            "resultType": "matrix",
            "result": [{
                "metric": {"source_id": "aws", "experiment_id": "exp"},
                "values": [[1, str(value)], [2, str(value)]],
            }],
        }


def _metadata(path: Path) -> None:
    write_metadata(path, {"experiment_id": "exp", "sources": ["aws"], "created_at": "2026-01-01T00:00:00+00:00"})


def test_collect_full_and_raw_samples(tmp_path: Path) -> None:
    _metadata(tmp_path)
    summary = collect_run(
        "exp", run_dir=tmp_path, client=FakeClient([1000, 1000, 1000]),
        wait=1, poll_interval=0, stable_polls=3,
    )
    assert summary["sources"]["aws"]["counter_final"] == 1000
    assert summary["timed_out"] is False
    assert (tmp_path / "received_samples.csv").is_file()
    assert json.loads((tmp_path / "collect_summary.json").read_text())["poll_count"] == 3


def test_collect_two_percent_loss_and_counter_duplication() -> None:
    expected = build_ground_truth_for_source("small", "aws", 7, "measurement_datapoints_total", "exp")
    loss_result = _accuracy_for_source(
        "aws", [point.as_dict() for point in expected],
        {"expected_counter_final": 1000, "counter_final": 980, "last_sequence_id": 980, "last_value": expected[979].metric_value},
        [],
    )
    assert loss_result["completeness_percent"] == 98
    assert loss_result["loss_percent"] == 2

    duplicate_result = _accuracy_for_source(
        "aws", [point.as_dict() for point in expected],
        {"expected_counter_final": 1000, "counter_final": 1002, "last_sequence_id": 1000, "last_value": expected[-1].metric_value},
        [],
    )
    assert duplicate_result["duplication_percent"] == 0.2


def test_stability_reset_and_timeout() -> None:
    clock_value = [0.0]

    def clock() -> float:
        return clock_value[0]

    def sleep(seconds: float) -> None:
        clock_value[0] += seconds

    reset_values = iter([100.0, 80.0, 80.0])
    reset = wait_for_stable_counters(
        lambda _source: next(reset_values), ["aws"], 2, 0, 2,
    )
    assert reset.values["aws"] == 80.0
    assert reset.counter_resets["aws"] is True

    changing = iter([1.0, 2.0, 3.0, 4.0])
    timeout = wait_for_stable_counters(
        lambda _source: next(changing), ["aws"], 1, 0.5, 3, clock, sleep,
    )
    assert timeout.timed_out is True
    assert any("timeout" in error for error in timeout.errors)

    empty = wait_for_stable_counters(lambda _source: None, ["aws"], 1, 0.5, 2, clock, sleep)
    assert empty.timed_out is True
    assert empty.values["aws"] is None
