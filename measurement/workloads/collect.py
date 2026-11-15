"""Collect scrape snapshots from Thanos Query on the local workstation."""

from __future__ import annotations

import argparse
import json
import logging
import socket
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import requests

from common.prometheus_client import PrometheusClient, PrometheusError
from common.result_writer import ROOT, write_received_samples
from common.time_utils import parse_timestamp, utc_now_iso

LOGGER = logging.getLogger(__name__)
HUB_CONTEXT = "k3d-hub-k3d"
NAMESPACE = "monitoring"
COUNTER_METRICS = ("measurement_datapoints_total", "measurement_datapoints")
EXPECTED_METRICS = ("measurement_run_expected_total", "measurement_run_expected")
SEQUENCE_METRICS = ("measurement_last_sequence_id",)
VALUE_METRICS = ("measurement_last_value",)


class CollectionError(RuntimeError):
    """Raised when collection cannot produce a trustworthy result."""


@dataclass
class PollState:
    """Bounded poll outcome used by the CLI and unit tests."""

    values: dict[str, float | None]
    polls: int
    stable_polls: dict[str, int]
    counter_resets: dict[str, bool]
    errors: list[str] = field(default_factory=list)
    timed_out: bool = False


def _selector(experiment_id: str, source_id: str) -> str:
    """Build a PromQL label selector for the two measurement dimensions."""

    safe_experiment = experiment_id.replace("\\", "\\\\").replace('"', '\\"')
    safe_source = source_id.replace("\\", "\\\\").replace('"', '\\"')
    return f'{{experiment_id="{safe_experiment}",source_id="{safe_source}"}}'


def _vector(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict) or data.get("resultType") != "vector":
        raise CollectionError(f"expected Prometheus vector response, got {data!r}")
    result = data.get("result")
    if not isinstance(result, list):
        raise CollectionError(f"Prometheus vector result is not a list: {data!r}")
    return [row for row in result if isinstance(row, dict) and isinstance(row.get("value"), list)]


def _series_value(data: Any) -> tuple[float | None, list[dict[str, Any]]]:
    rows = _vector(data)
    if not rows:
        return None, []
    values: list[float] = []
    for row in rows:
        try:
            values.append(float(row["value"][1]))
        except (IndexError, TypeError, ValueError) as exc:
            raise CollectionError(f"invalid Prometheus sample: {row!r}") from exc
    # The configured pipeline has one logical series.  If extra labels create
    # several physical series, max avoids double counting the same counter and
    # the summary records all values for diagnosis.
    return max(values), rows


def query_metric_value(
    client: PrometheusClient,
    metric_names: Iterable[str],
    experiment_id: str,
    source_id: str,
) -> tuple[float | None, str | None, list[dict[str, Any]], list[str]]:
    """Query candidate exporter names and return the highest matching series."""

    empty: list[str] = []
    query_errors: list[str] = []
    selector = _selector(experiment_id, source_id)
    for metric_name in metric_names:
        try:
            data = client.query(f"{metric_name}{selector}")
            value, rows = _series_value(data)
        except (PrometheusError, CollectionError) as exc:
            query_errors.append(f"{metric_name}: {exc}")
            continue
        if rows:
            return value, metric_name, rows, query_errors
        empty.append(metric_name)
    if query_errors:
        return None, None, [], query_errors + [f"query empty for candidates: {', '.join(empty)}"]
    return None, None, [], [f"query empty for candidates: {', '.join(empty)}"]


def wait_for_stable_counters(
    query: Callable[[str], float | None],
    sources: Iterable[str],
    timeout: float,
    poll_interval: float,
    stable_polls_required: int,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> PollState:
    """Poll counters until all sources are stable or the deadline expires."""

    if timeout <= 0 or poll_interval < 0 or stable_polls_required <= 0:
        raise ValueError("timeout must be positive, interval non-negative and stable polls positive")
    source_list = list(sources)
    previous: dict[str, float | None] = {source: None for source in source_list}
    stable: dict[str, int] = {source: 0 for source in source_list}
    resets: dict[str, bool] = {source: False for source in source_list}
    values: dict[str, float | None] = {source: None for source in source_list}
    errors: list[str] = []
    polls = 0
    deadline = clock() + timeout
    while True:
        polls += 1
        for source in source_list:
            try:
                current = query(source)
            except Exception as exc:  # query errors are reported, never retried forever
                current = None
                errors.append(f"{source}: {exc}")
            values[source] = current
            old = previous[source]
            if current is None:
                stable[source] = 0
            elif old is not None and current < old:
                resets[source] = True
                stable[source] = 1
                errors.append(f"{source}: counter reset {old} -> {current}")
            elif old is not None and current == old:
                stable[source] += 1
            else:
                stable[source] = 1
            previous[source] = current
        if source_list and all(stable[source] >= stable_polls_required for source in source_list):
            return PollState(values, polls, stable, resets, errors)
        remaining = deadline - clock()
        if remaining <= 0:
            errors.append("counter stability timeout")
            return PollState(values, polls, stable, resets, errors, timed_out=True)
        if poll_interval:
            sleeper(min(poll_interval, remaining))


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


class ThanosPortForward:
    """Own a bounded kubectl port-forward process."""

    def __init__(self, port: int | None = None, startup_timeout: float = 60.0):
        self.port = port or _free_port()
        self.startup_timeout = startup_timeout
        self.process: subprocess.Popen[str] | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self) -> "ThanosPortForward":
        command = [
            "kubectl", "--context", HUB_CONTEXT, "-n", NAMESPACE,
            "port-forward", "svc/thanos-query", f"{self.port}:9090",
        ]
        self.process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        try:
            deadline = time.monotonic() + self.startup_timeout
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    output = self.process.stdout.read() if self.process.stdout else ""
                    raise CollectionError(f"kubectl port-forward exited: {output.strip()}")
                try:
                    response = requests.get(f"{self.url}/-/ready", timeout=1)
                    response.raise_for_status()
                except Exception:
                    time.sleep(0.2)
                else:
                    return self
            raise CollectionError(f"timed out opening Thanos port-forward: {command}")
        except Exception:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_: object) -> None:
        if self.process is None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=3)


def _iso_from_seconds(value: object) -> str:
    return datetime.fromtimestamp(float(value), timezone.utc).isoformat()


def _range_rows(data: Any, metric_name: str) -> list[dict[str, Any]]:
    if not isinstance(data, dict) or data.get("resultType") != "matrix":
        raise CollectionError(f"expected Prometheus matrix response, got {data!r}")
    rows: list[dict[str, Any]] = []
    for series in data.get("result", []):
        if not isinstance(series, dict):
            continue
        labels = series.get("metric", {})
        for sample in series.get("values", []):
            if not isinstance(sample, list) or len(sample) < 2:
                continue
            try:
                number = float(sample[1])
                timestamp = _iso_from_seconds(sample[0])
            except (TypeError, ValueError) as exc:
                raise CollectionError(f"invalid range sample: {sample!r}") from exc
            sequence_id: int | None = None
            if metric_name in SEQUENCE_METRICS:
                sequence_id = int(number)
            rows.append({
                "source_id": labels.get("source_id"),
                "sequence_id": sequence_id,
                "timestamp": timestamp,
                "metric_name": metric_name,
                "value": number,
                "labels": json.dumps(labels, sort_keys=True),
            })
    return rows


def _time_window(metadata: dict[str, Any]) -> tuple[str, str]:
    try:
        start = parse_timestamp(str(metadata["created_at"])) - timedelta(minutes=2)
    except (KeyError, TypeError, ValueError):
        start = datetime.now(timezone.utc) - timedelta(minutes=2)
    end = datetime.now(timezone.utc) + timedelta(minutes=2)
    return start.isoformat(), end.isoformat()


def collect_run(
    experiment_id: str,
    run_dir: Path | None = None,
    thanos_url: str | None = None,
    wait: float = 120.0,
    timeout: float = 5.0,
    poll_interval: float = 5.0,
    stable_polls: int = 3,
    port: int | None = None,
    client: PrometheusClient | None = None,
) -> dict[str, Any]:
    """Collect counters and raw scrape samples for one experiment."""

    output_dir = run_dir or (ROOT / "results" / "raw" / experiment_id)
    metadata_path = output_dir / "metadata.json"
    if not metadata_path.is_file():
        raise CollectionError(f"metadata.json not found: {metadata_path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    sources = [str(source) for source in metadata.get("sources", ["aws", "azure"])]
    if not sources:
        raise CollectionError("metadata contains no sources")

    forward: ThanosPortForward | None = None
    endpoint_source = "thanos"
    if client is None:
        if thanos_url:
            client = PrometheusClient(thanos_url, timeout=timeout, retries=0)
        else:
            forward = ThanosPortForward(port=port)
            forward.__enter__()
            client = PrometheusClient(forward.url, timeout=timeout, retries=0)
    try:
        def counter_for(source: str) -> float | None:
            value, _, _, _ = query_metric_value(client, COUNTER_METRICS, experiment_id, source)
            return value

        poll = wait_for_stable_counters(
            counter_for, sources, wait, poll_interval, stable_polls
        )
        start, end = _time_window(metadata)
        received: list[dict[str, Any]] = []
        source_summary: dict[str, Any] = {}
        all_errors = list(poll.errors)
        for source in sources:
            expected, expected_metric, expected_rows, expected_errors = query_metric_value(
                client, EXPECTED_METRICS, experiment_id, source
            )
            counter, counter_metric, counter_rows, counter_errors = query_metric_value(
                client, COUNTER_METRICS, experiment_id, source
            )
            last_sequence, sequence_metric, _, sequence_errors = query_metric_value(
                client, SEQUENCE_METRICS, experiment_id, source
            )
            last_value, value_metric, _, value_errors = query_metric_value(
                client, VALUE_METRICS, experiment_id, source
            )
            for error in expected_errors + counter_errors + sequence_errors + value_errors:
                all_errors.append(f"{source}: {error}")
            source_summary[source] = {
                "expected_counter_final": expected,
                "counter_final": counter,
                "last_sequence_id": last_sequence,
                "last_value": last_value,
                "expected_metric_name": expected_metric,
                "counter_metric_name": counter_metric,
                "sequence_metric_name": sequence_metric,
                "value_metric_name": value_metric,
                "counter_series_values": [row.get("value") for row in counter_rows],
                "expected_series_values": [row.get("value") for row in expected_rows],
                "counter_reset": poll.counter_resets.get(source, False),
            }
            for metric_names in (COUNTER_METRICS, EXPECTED_METRICS, SEQUENCE_METRICS, VALUE_METRICS):
                for metric_name in metric_names:
                    selector = _selector(experiment_id, source)
                    try:
                        range_data = client.query_range(
                            f"{metric_name}{selector}", start, end, step="5s", dedup=False
                        )
                    except (PrometheusError, ValueError) as exc:
                        all_errors.append(f"{source}: range {metric_name}: {exc}")
                        continue
                    rows = _range_rows(range_data, metric_name)
                    received.extend(rows)
                    if rows:
                        break

        write_received_samples(output_dir, received)
        summary = {
            "experiment_id": experiment_id,
            "observed_at_utc": utc_now_iso(),
            "sources": source_summary,
            "poll_count": poll.polls,
            "stable_polls_required": stable_polls,
            "timed_out": poll.timed_out,
            "endpoint_used": client.base_url,
            "query_source": endpoint_source,
            "time_window_utc": {"start": start, "end": end, "clock_slack_seconds": 120},
            "received_sample_count": len(received),
            "errors": sorted(set(all_errors)),
        }
        (output_dir / "collect_summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return summary
    finally:
        if forward is not None:
            forward.__exit__(None, None, None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--thanos-url")
    parser.add_argument("--wait", type=float, default=120.0)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--stable-polls", type=int, default=3)
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    summary = collect_run(
        args.experiment_id, thanos_url=args.thanos_url, wait=args.wait,
        timeout=args.timeout, poll_interval=args.poll_interval,
        stable_polls=args.stable_polls, port=args.port,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if not summary["timed_out"] and not summary["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
