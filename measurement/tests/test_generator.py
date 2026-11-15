"""Generator tests with a mocked HTTP sender."""

from workloads.generator import measurement_batch_payload, run_generation


def test_batch_payload_has_no_sequence_label() -> None:
    points, _ = run_generation("small", "aws", "exp", 11, None, False)
    payload = measurement_batch_payload("exp", "aws", points, 1_000_000_000)
    metrics = payload["resourceMetrics"][0]["scopeMetrics"][0]["metrics"]
    assert {metric["name"] for metric in metrics} == {
        "measurement_datapoints_total",
        "measurement_last_sequence_id",
        "measurement_last_value",
    }
    assert all(
        attribute["key"] != "sequence_id"
        for metric in metrics
        for kind in ("sum", "gauge")
        if kind in metric
        for point in metric[kind]["dataPoints"]
        for attribute in point.get("attributes", [])
    )
    assert len(metrics[0]["sum"]["dataPoints"]) == 1000


def test_send_failure_is_counted_without_retry(monkeypatch) -> None:
    calls = []

    def fail_once(*args, **kwargs):
        calls.append(1)
        raise RuntimeError("synthetic send failure")

    monkeypatch.setattr("workloads.generator.send_point", fail_once)
    _, summary = run_generation("small", "azure", "exp", 11, "http://fake", True)
    assert summary["sent_ok"] == 0
    assert summary["sent_fail"] == 1000
    assert len(calls) == 2  # data batch and terminal expected counter; no retry
