"""Dry-run and explicitly enabled OTLP HTTP workload generator."""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import replace
import time
from pathlib import Path
from typing import Any

import requests

from common.config import ROOT, load_yaml
from common.models import Experiment, Provenance, RunStatus
from common.result_writer import (
    create_run_dir,
    new_experiment_id,
    write_ground_truth,
    write_metadata,
)
from .ground_truth import build_ground_truth_for_sources, build_ground_truth_for_source
from .scenarios import SCENARIOS, expected_count

LOGGER = logging.getLogger(__name__)


def _metrics_endpoint(endpoint: str) -> str:
    """Accept either the OTLP HTTP service root or its metrics path."""

    normalized = endpoint.rstrip("/")
    return normalized if normalized.endswith("/v1/metrics") else f"{normalized}/v1/metrics"


def otlp_json_payload(
    metric_name: str, source_id: str, test_label: str, value: float, timestamp_ns: int
) -> dict[str, Any]:
    """Build the OTLP/HTTP JSON metric payload.

    The collector endpoint must be explicitly verified before sending. This payload
    uses only low-cardinality resource/metric attributes; sequence IDs stay in ground truth.
    """

    return {
        "resourceMetrics": [{
            "resource": {"attributes": [
                {"key": "service.name", "value": {"stringValue": "measurement-workload"}},
                {"key": "source_id", "value": {"stringValue": source_id}},
            ]},
            "scopeMetrics": [{"metrics": [{
                "name": metric_name,
                "sum": {
                    "dataPoints": [{
                        "asDouble": value,
                        "timeUnixNano": str(timestamp_ns),
                        "startTimeUnixNano": str(timestamp_ns),
                        "attributes": [
                            {"key": "test", "value": {"stringValue": test_label}},
                        ],
                    }],
                    "aggregationTemporality": 2,
                    "isMonotonic": True,
                },
            }]}],
        }]
    }


def measurement_otlp_payload(
    experiment_id: str,
    source_id: str,
    point: Any,
    counter_value: int,
    start_timestamp_ns: int,
    timestamp_ns: int,
) -> dict[str, Any]:
    """Build one no-retry measurement request.

    ``measurement_datapoints_total`` is cumulative.  The two gauges provide
    bounded observability of the final sequence/value without a sequence label.
    """

    attributes = [
        {"key": "experiment_id", "value": {"stringValue": experiment_id}},
        {"key": "source_id", "value": {"stringValue": source_id}},
        {"key": "test", "value": {"stringValue": "measurement_framework"}},
    ]
    resource_attributes = [
        {"key": "service.name", "value": {"stringValue": "measurement-workload"}},
        {"key": "experiment_id", "value": {"stringValue": experiment_id}},
        {"key": "source_id", "value": {"stringValue": source_id}},
    ]

    def number(value: float | int) -> dict[str, str]:
        return {"asDouble": float(value)}

    def gauge(name: str, value: float | int) -> dict[str, Any]:
        return {
            "name": name,
            "gauge": {"dataPoints": [dict(number(value), timeUnixNano=str(timestamp_ns), attributes=attributes)]},
        }

    counter = {
        "name": "measurement_datapoints_total",
        "sum": {
            "dataPoints": [{
                **number(counter_value),
                "timeUnixNano": str(timestamp_ns),
                "startTimeUnixNano": str(start_timestamp_ns),
                "attributes": attributes,
            }],
            "aggregationTemporality": 2,
            "isMonotonic": True,
        },
    }
    return {
        "resourceMetrics": [{
            "resource": {"attributes": resource_attributes},
            "scopeMetrics": [{"metrics": [
                counter,
                gauge("measurement_last_sequence_id", point.sequence_id),
                gauge("measurement_last_value", point.metric_value),
            ]}],
        }]
    }


def expected_otlp_payload(
    experiment_id: str,
    source_id: str,
    expected_count_value: int,
    timestamp_ns: int,
) -> dict[str, Any]:
    """Build the terminal successful-send counter."""

    return {
        "resourceMetrics": [{
            "resource": {"attributes": [
                {"key": "service.name", "value": {"stringValue": "measurement-workload"}},
                {"key": "experiment_id", "value": {"stringValue": experiment_id}},
                {"key": "source_id", "value": {"stringValue": source_id}},
            ]},
            "scopeMetrics": [{"metrics": [{
                "name": "measurement_run_expected_total",
                "sum": {
                    "dataPoints": [{
                        "asDouble": float(expected_count_value),
                        "timeUnixNano": str(timestamp_ns),
                        "startTimeUnixNano": str(timestamp_ns),
                        "attributes": [
                            {"key": "experiment_id", "value": {"stringValue": experiment_id}},
                            {"key": "source_id", "value": {"stringValue": source_id}},
                        ],
                    }],
                    "aggregationTemporality": 2,
                    "isMonotonic": True,
                },
            }]}],
        }]
    }


def measurement_batch_payload(
    experiment_id: str,
    source_id: str,
    points: list[Any],
    start_timestamp_ns: int,
) -> dict[str, Any]:
    """Build one request containing the complete source stream.

    The hub currently converts its receive-time resource attribute to a
    Prometheus label.  One request keeps that dynamic label constant for the
    run/source and avoids one physical series per HTTP request.
    """

    attributes = [
        {"key": "experiment_id", "value": {"stringValue": experiment_id}},
        {"key": "source_id", "value": {"stringValue": source_id}},
        {"key": "test", "value": {"stringValue": "measurement_framework"}},
    ]
    resource_attributes = [
        {"key": "service.name", "value": {"stringValue": "measurement-workload"}},
        {"key": "experiment_id", "value": {"stringValue": experiment_id}},
        {"key": "source_id", "value": {"stringValue": source_id}},
    ]

    def point(value: float | int, timestamp_ns: int, include_start: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {
            "asDouble": float(value),
            "timeUnixNano": str(timestamp_ns),
            "attributes": attributes,
        }
        if include_start:
            result["startTimeUnixNano"] = str(start_timestamp_ns)
        return result

    timestamps = [start_timestamp_ns + sequence * 1_000_000 for sequence in range(1, len(points) + 1)]
    counter = {
        "name": "measurement_datapoints_total",
        "sum": {
            "dataPoints": [
                point(index, timestamp, include_start=True)
                for index, timestamp in enumerate(timestamps, start=1)
            ],
            "aggregationTemporality": 2,
            "isMonotonic": True,
        },
    }
    sequence_gauge = {
        "name": "measurement_last_sequence_id",
        "gauge": {"dataPoints": [
            point(item.sequence_id, timestamp)
            for item, timestamp in zip(points, timestamps)
        ]},
    }
    value_gauge = {
        "name": "measurement_last_value",
        "gauge": {"dataPoints": [
            point(item.metric_value, timestamp)
            for item, timestamp in zip(points, timestamps)
        ]},
    }
    return {
        "resourceMetrics": [{
            "resource": {"attributes": resource_attributes},
            "scopeMetrics": [{"metrics": [counter, sequence_gauge, value_gauge]}],
        }]
    }


def send_point(url: str, payload: dict[str, Any], timeout: float = 5.0) -> None:
    """Send one OTLP JSON request with a bounded timeout."""

    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()


def run_generation(
    scenario: str,
    source_id: str,
    experiment_id: str,
    seed: int,
    endpoint: str | None,
    send: bool,
    timeout: float = 5.0,
) -> tuple[list[Any], dict[str, int | str | bool]]:
    """Generate one source stream, optionally sending it from the cluster."""

    if source_id not in {"aws", "azure"}:
        raise ValueError("source_id must be aws or azure")
    if send and not endpoint:
        raise ValueError("--endpoint is required with --send")
    target_endpoint = _metrics_endpoint(str(endpoint)) if endpoint else None
    metric_name = "measurement_datapoints_total"
    points = build_ground_truth_for_source(scenario, source_id, seed, metric_name, experiment_id)
    sent_ok = 0
    sent_fail = 0
    start_ns = time.time_ns()
    if send:
        try:
            send_point(
                str(target_endpoint),
                measurement_batch_payload(experiment_id, source_id, points, start_ns),
                timeout=timeout,
            )
        except Exception as exc:  # one failed request is counted, never retried
            sent_fail = len(points)
            LOGGER.warning("batch send failed source=%s: %s", source_id, exc)
        else:
            sent_ok = len(points)
            points = [replace(point, sent_ok=True) for point in points]

    if send:
        try:
            send_point(
                str(target_endpoint),
                expected_otlp_payload(experiment_id, source_id, sent_ok, time.time_ns()),
                timeout=timeout,
            )
        except Exception as exc:
            LOGGER.warning("terminal expected counter send failed: %s", exc)
    summary: dict[str, int | str | bool] = {
        "experiment_id": experiment_id,
        "source_id": source_id,
        "sent_ok": sent_ok,
        "sent_fail": sent_fail,
        "send": send,
    }
    return points, summary


def run_continuous_generation(
    scenario: str,
    source_id: str,
    experiment_id: str,
    seed: int,
    endpoint: str,
    rate: float,
    duration: float,
    timeout: float = 5.0,
) -> tuple[list[Any], dict[str, int | float | str | bool]]:
    """Send one measurement datapoint per scheduled tick for a fixed duration.

    ``rate`` is the target datapoints/second. Requests are not retried: failed
    sends are counted as failures so the observed delivery rate is not inflated.
    The finite scenario stream is cycled when the requested run is longer than
    the generated fixture.
    """
    if source_id not in {"aws", "azure"}:
        raise ValueError("source_id must be aws or azure")
    if rate <= 0:
        raise ValueError("--rate must be greater than 0")
    if duration <= 0:
        raise ValueError("--duration must be greater than 0")
    if not endpoint:
        raise ValueError("--endpoint is required in continuous mode")

    target_endpoint = _metrics_endpoint(endpoint)
    metric_name = "measurement_datapoints_total"
    template_points = build_ground_truth_for_source(
        scenario, source_id, seed, metric_name, experiment_id
    )
    if not template_points:
        raise ValueError("scenario generated no datapoints")

    start_wall_ns = time.time_ns()
    start_monotonic = time.monotonic()
    deadline = start_monotonic + duration
    interval = 1.0 / rate
    generated: list[Any] = []
    sent_ok = 0
    sent_fail = 0
    next_tick = start_monotonic
    sequence = 0

    while next_tick < deadline:
        delay = next_tick - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        if time.monotonic() >= deadline:
            break

        template = template_points[sequence % len(template_points)]
        sequence += 1
        point = replace(template, sequence_id=sequence, sent_ok=False)
        timestamp_ns = time.time_ns()
        payload = measurement_otlp_payload(
            experiment_id=experiment_id,
            source_id=source_id,
            point=point,
            counter_value=sequence,
            start_timestamp_ns=start_wall_ns,
            timestamp_ns=timestamp_ns,
        )
        try:
            send_point(target_endpoint, payload, timeout=timeout)
        except Exception as exc:  # one failed request is counted, never retried
            sent_fail += 1
            LOGGER.warning(
                "continuous send failed source=%s sequence=%d: %s",
                source_id, sequence, exc
            )
        else:
            sent_ok += 1
            point = replace(point, sent_ok=True)
        generated.append(point)
        next_tick = start_monotonic + sequence * interval

    elapsed = max(time.monotonic() - start_monotonic, 1e-9)
    summary: dict[str, int | float | str | bool] = {
        "experiment_id": experiment_id,
        "source_id": source_id,
        "mode": "continuous",
        "target_rate": rate,
        "duration_seconds": duration,
        "elapsed_seconds": round(elapsed, 6),
        "generated": sequence,
        "sent_ok": sent_ok,
        "sent_fail": sent_fail,
        "observed_send_rate": round(sent_ok / elapsed, 3),
        "send": True,
    }
    return generated, summary


def generate(
    scenario: str, sources: list[str], send: bool = False
) -> tuple[Experiment, Path]:
    """Generate a run; sending requires explicit ``send=True`` and verified URLs."""

    count = expected_count(scenario)
    config = load_yaml(ROOT / "configs" / "workload.yaml")
    metric_name = str(config["metric_name"])
    test_label = str(config["test_label"])
    experiment_id = new_experiment_id(scenario)
    points = build_ground_truth_for_sources(
        scenario, sources, seed=0, metric_name=metric_name, experiment_id=experiment_id
    )
    run_dir = create_run_dir(experiment_id)
    status = RunStatus.PARTIAL
    provenance = Provenance.SIMULATED
    warnings = ["dry-run: no telemetry was sent"]
    if send:
        source_config = config.get("sources", {})
        urls = [source_config.get(source, {}).get("otlp_http_url") for source in sources]
        if not urls or any(not url for url in urls):
            status = RunStatus.UNAVAILABLE
            provenance = Provenance.UNAVAILABLE
            warnings = ["OTLP HTTP endpoint is null or unverified for at least one source"]
        else:
            for point, url in zip(points, urls):
                timestamp_ns = int(
                    __import__("datetime").datetime.fromisoformat(
                        point.event_timestamp
                    ).timestamp() * 1_000_000_000
                )
                send_point(
                    str(url),
                    otlp_json_payload(
                        metric_name, point.source_id, test_label, point.metric_value, timestamp_ns
                    ),
                )
            points = [replace(point, sent_ok=True) for point in points]
            status = RunStatus.SUCCESS
            provenance = Provenance.MEASURED
            warnings = []
    metadata = Experiment(
        experiment_id=experiment_id,
        scenario=scenario,
        expected_datapoints=len(points),
        sources=sources,
        provenance=provenance,
        status=status,
    ).as_dict()
    metadata.update({
        "metric_name": metric_name,
        "test_label": test_label,
        "sent_ok": status == RunStatus.SUCCESS,
        "warnings": warnings,
        "data_model": "scrape_counter_and_independent_ground_truth",
    })
    write_metadata(run_dir, metadata)
    write_ground_truth(run_dir, points)
    return Experiment(
        experiment_id=experiment_id,
        scenario=scenario,
        expected_datapoints=len(points),
        sources=sources,
        provenance=provenance,
        status=status,
    ), run_dir


def main() -> int:
    """CLI entry point; dry-run is the default."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="small")
    parser.add_argument("--source", action="append", choices=["aws", "azure"])
    parser.add_argument("--experiment-id")
    parser.add_argument("--source-id", choices=["aws", "azure"])
    parser.add_argument("--endpoint")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--send", action="store_true", help="Explicitly send telemetry")
    parser.add_argument(
        "--rate", type=float,
        help="Continuous mode target rate in datapoints/second"
    )
    parser.add_argument(
        "--duration", type=float,
        help="Continuous mode duration in seconds"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    
    if (args.rate is None) != (args.duration is None):
        parser.error("--rate and --duration must be provided together")
    if args.rate is not None:
        if not args.send:
            parser.error("continuous mode requires --send")
        if not args.endpoint:
            parser.error("continuous mode requires --endpoint")
        source_id = args.source_id or (args.source[0] if args.source else "aws")
        experiment_id = args.experiment_id or new_experiment_id(args.scenario)
        _, summary = run_continuous_generation(
            args.scenario,
            source_id,
            experiment_id,
            args.seed,
            args.endpoint,
            args.rate,
            args.duration,
        )
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    
    if args.source_id or args.endpoint or args.experiment_id or args.send:
        source_id = args.source_id or (args.source[0] if args.source else "aws")
        experiment_id = args.experiment_id or new_experiment_id(args.scenario)
        points, summary = run_generation(
            args.scenario, source_id, experiment_id, args.seed, args.endpoint, args.send
        )
        print(json.dumps(summary, ensure_ascii=False))
        # A failed individual request is part of the measurement result.  The
        # Job must still reach Complete so the workstation can collect the
        # resulting counter and report the loss rather than hiding it as a
        # Kubernetes Job failure.
        return 0

    sources = args.source or ["aws", "azure"]
    experiment, run_dir = generate(args.scenario, sources, send=args.send)
    print(json.dumps({"experiment_id": experiment.experiment_id,
                      "status": experiment.status.value,
                      "run_dir": str(run_dir)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
