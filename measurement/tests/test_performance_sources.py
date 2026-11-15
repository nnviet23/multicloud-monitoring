from __future__ import annotations

import json
from pathlib import Path

import pytest

from performance import sources


FIXTURE = Path(__file__).parent / "fixtures" / "collector_metrics.txt"


def field(record: object, name: str):
    if isinstance(record, dict):
        return record[name]
    return getattr(record, name)


def test_collector_metrics_filter_and_aggregate() -> None:
    values, missing = sources.extract_collector_metrics(FIXTURE.read_text(), "otlp/hub")

    assert values["otelcol_receiver_accepted_metric_points"] == 3936
    assert values["otelcol_exporter_sent_metric_points"] == 0
    assert values["otelcol_exporter_send_failed_metric_points"] == 8469
    assert values["otelcol_exporter_queue_size"] == 102
    assert values["service_instance_id"] == "2325a40e-29a3-4a0d-987f-9f6698745a9e"
    assert "HELP" not in values and "TYPE" not in values
    assert "accepted_log_records" in missing


def test_missing_metric_is_none_with_reason() -> None:
    values, missing = sources.extract_collector_metrics("# HELP x x\n# TYPE x gauge\n", "otlp/hub")

    assert values["otelcol_process_uptime"] is None
    assert "otelcol_process_uptime" in missing


def test_kubectl_error_is_recorded_without_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_kubectl(context: str, args: list[str], timeout: int) -> tuple[None, str]:
        return None, "timeout"

    monkeypatch.setattr(sources, "run_kubectl", failing_kubectl)
    record = sources.collect_sample(
        {
            "name": "spoke_aws",
            "context": "ctx",
            "namespace": "monitoring",
            "deployment": "collector",
            "exporter": "otlp/hub",
        }
    )

    assert field(record, "pod_name") is None
    assert "pod_name" in field(record, "missing_reasons")


def test_sample_uses_mocked_kubectl_and_keeps_raw_counters(monkeypatch: pytest.MonkeyPatch) -> None:
    metrics = FIXTURE.read_text()
    pod_json = json.dumps(
        {
            "items": [
                {
                    "metadata": {
                        "name": "collector-abc",
                        "creationTimestamp": "2026-01-01T00:00:00Z",
                        "ownerReferences": [{"kind": "ReplicaSet", "name": "collector-123"}],
                    },
                    "status": {"containerStatuses": [{"restartCount": 2}]},
                }
            ]
        }
    )

    def fake_kubectl(context: str, args: list[str], timeout: int) -> tuple[str, None]:
        if args[1] == "pods":
            return pod_json, None
        if args[1] == "--raw" and args[2].endswith("/metrics"):
            return metrics, None
        return "", None

    monkeypatch.setattr(sources, "run_kubectl", fake_kubectl)
    record = sources.collect_sample(
        {
            "name": "spoke_aws",
            "context": "ctx",
            "namespace": "monitoring",
            "deployment": "collector",
            "exporter": "otlp/hub",
        }
    )

    assert field(record, "restart_count") == 2
    assert field(record, "metrics")["otelcol_exporter_send_failed_metric_points"] == 8469


@pytest.mark.skip(reason="cAdvisor selection requires a real cAdvisor fixture; logic is not yet verified with real data")
def test_cadvisor_with_real_fixture() -> None:
    raise AssertionError("enable after adding a real cAdvisor fixture")
