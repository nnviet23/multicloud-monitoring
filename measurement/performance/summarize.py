
"""Summarize performance samples and derive rates from counters."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from statistics import mean, median, pstdev
from typing import Any, Mapping, Sequence


# Cumulative counters collected by sources.py.
COUNTER_METRICS = {
    "otelcol_process_cpu_seconds",
    "otelcol_receiver_accepted_metric_points",
    "accepted_log_records",
    "accepted_spans",
    "otelcol_exporter_sent_metric_points",
    "otelcol_exporter_send_failed_metric_points",
    "container_cpu_usage_seconds_total",
    "container_network_transmit_bytes_total",
    "container_network_receive_bytes_total",
}

RATE_NAMES = {
    "otelcol_process_cpu_seconds": "otelcol_process_cpu_cores",
    "otelcol_receiver_accepted_metric_points": "otelcol_receiver_accepted_metric_points_per_second",
    "accepted_log_records": "accepted_log_records_per_second",
    "accepted_spans": "accepted_spans_per_second",
    "otelcol_exporter_sent_metric_points": "otelcol_exporter_sent_metric_points_per_second",
    "otelcol_exporter_send_failed_metric_points": "otelcol_exporter_send_failed_metric_points_per_second",
    "container_cpu_usage_seconds_total": "container_cpu_cores",
    "container_network_transmit_bytes_total": "container_network_transmit_bytes_per_second",
    "container_network_receive_bytes_total": "container_network_receive_bytes_per_second",
}


def _get(sample: Any, key: str, default: Any = None) -> Any:
    """Read a field from either a dict or a model object."""
    if isinstance(sample, Mapping):
        return sample.get(key, default)
    return getattr(sample, key, default)


def _timestamp(sample: Any) -> datetime | None:
    value = _get(sample, "timestamp_utc")
    if value is None:
        value = _get(sample, "timestamp")

    if isinstance(value, datetime):
        return value

    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    return None


def _metrics(sample: Any) -> dict[str, Any]:
    """Get nested metrics, with support for flattened sample fields."""
    nested = _get(sample, "metrics", {})
    result = dict(nested) if isinstance(nested, Mapping) else {}

    # sources.py also exposes metrics at the top level.
    for name in set(COUNTER_METRICS) | {
        "otelcol_process_memory_rss",
        "otelcol_process_uptime",
        "otelcol_exporter_queue_size",
        "container_memory_working_set_bytes",
    }:
        value = _get(sample, name)
        if name not in result and value is not None:
            result[name] = value

    return result


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None

    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(result):
        return None

    return result


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    """Calculate a linearly interpolated percentile."""
    if not values:
        return None

    ordered = sorted(values)

    if len(ordered) == 1:
        return ordered[0]

    position = (len(ordered) - 1) * percentile / 100
    lower = math.floor(position)
    upper = math.ceil(position)

    if lower == upper:
        return ordered[lower]

    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def summarize_values(values: Sequence[float]) -> dict[str, float | int | None]:
    """Calculate descriptive statistics for a list of numeric values."""
    clean = [float(value) for value in values if math.isfinite(float(value))]

    if not clean:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "stddev": None,
            "min": None,
            "max": None,
            "p50": None,
            "p90": None,
            "p95": None,
            "p99": None,
        }

    return {
        "count": len(clean),
        "mean": mean(clean),
        "median": median(clean),
        "stddev": pstdev(clean),
        "min": min(clean),
        "max": max(clean),
        "p50": _percentile(clean, 50),
        "p90": _percentile(clean, 90),
        "p95": _percentile(clean, 95),
        "p99": _percentile(clean, 99),
    }


def _counter_delta(previous: float, current: float) -> float:
    """Handle a counter reset by treating the new value as post-reset data."""
    if current >= previous:
        return current - previous

    return current


def _derive_rates(samples: Sequence[Any]) -> tuple[
    dict[str, list[float]],
    dict[str, dict[str, float]],
]:
    """Calculate rates between consecutive valid samples per target."""
    grouped: dict[str, list[Any]] = defaultdict(list)

    for sample in samples:
        target = str(
            _get(sample, "target_name")
            or _get(sample, "target")
            or "unknown"
        )
        grouped[target].append(sample)

    rate_values: dict[str, list[float]] = defaultdict(list)
    counter_totals: dict[str, dict[str, float]] = {}

    for target, target_samples in grouped.items():
        target_samples.sort(
            key=lambda item: _timestamp(item) or datetime.min
        )

        previous: dict[str, tuple[datetime, float]] = {}
        totals: dict[str, float] = defaultdict(float)
        first_values: dict[str, float] = {}
        last_values: dict[str, float] = {}

        for sample in target_samples:
            current_time = _timestamp(sample)
            if current_time is None:
                continue

            metrics = _metrics(sample)

            for metric_name in COUNTER_METRICS:
                current_value = _number(metrics.get(metric_name))

                if current_value is None:
                    continue

                first_values.setdefault(metric_name, current_value)
                last_values[metric_name] = current_value

                old = previous.get(metric_name)

                if old is not None:
                    old_time, old_value = old
                    elapsed = (current_time - old_time).total_seconds()

                    if elapsed > 0:
                        delta = _counter_delta(old_value, current_value)
                        rate = delta / elapsed
                        rate_name = RATE_NAMES[metric_name]

                        rate_values[f"{target}.{rate_name}"].append(rate)
                        totals[metric_name] += delta

                previous[metric_name] = (current_time, current_value)

        for metric_name in first_values:
            counter_totals[f"{target}.{metric_name}"] = {
                "first": first_values[metric_name],
                "last": last_values[metric_name],
                "total_increase": totals.get(metric_name, 0.0),
            }

    return dict(rate_values), counter_totals


def summarize_samples(samples: Sequence[Any]) -> dict[str, Any]:
    """Build a JSON-serializable summary grouped by target."""
    grouped: dict[str, list[Any]] = defaultdict(list)

    for sample in samples:
        target = str(
            _get(sample, "target_name")
            or _get(sample, "target")
            or "unknown"
        )
        grouped[target].append(sample)

    rates, counter_totals = _derive_rates(samples)

    targets_summary: dict[str, Any] = {}

    for target, target_samples in grouped.items():
        gauge_values: dict[str, list[float]] = defaultdict(list)
        missing_counts: dict[str, int] = defaultdict(int)

        timestamps = []

        for sample in target_samples:
            current_time = _timestamp(sample)
            if current_time is not None:
                timestamps.append(current_time)

            metrics = _metrics(sample)
            missing = _get(sample, "missing_reasons", {}) or {}

            for metric_name, value in metrics.items():
                if metric_name in COUNTER_METRICS:
                    continue

                number = _number(value)
                if number is not None:
                    gauge_values[metric_name].append(number)

            if isinstance(missing, Mapping):
                for metric_name in missing:
                    missing_counts[metric_name] += 1

        target_rates = {
            name.split(".", 1)[1]: summarize_values(values)
            for name, values in rates.items()
            if name.startswith(f"{target}.")
        }

        target_counters = {
            name.split(".", 1)[1]: values
            for name, values in counter_totals.items()
            if name.startswith(f"{target}.")
        }

        targets_summary[target] = {
            "sample_count": len(target_samples),
            "start_time": min(timestamps).isoformat() if timestamps else None,
            "end_time": max(timestamps).isoformat() if timestamps else None,
            "gauges": {
                name: summarize_values(values)
                for name, values in gauge_values.items()
            },
            "rates": target_rates,
            "counters": target_counters,
            "missing_counts": dict(missing_counts),
        }

    return {
        "sample_count": len(samples),
        "target_count": len(grouped),
        "targets": targets_summary,
    }
