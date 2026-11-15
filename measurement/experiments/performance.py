
"""Run a complete multi-cloud performance experiment."""

from __future__ import annotations

import argparse
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from common.config import ROOT, load_yaml
from common.result_writer import (
    create_performance_run_dir,
    write_performance_metadata,
    write_raw_samples,
    write_summary,
)

from performance.sampler import sample_performance
from performance.sources import load_performance_config
from performance.summarize import summarize_samples


SOURCE_TARGETS = {
    "aws": "spoke_aws",
    "azure": "spoke_azure",
}


def _new_run_id() -> str:
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid.uuid4().hex[:8]
    return f"performance_{now}_{suffix}"


def _get(sample: Any, key: str, default: Any = None) -> Any:
    if isinstance(sample, dict):
        return sample.get(key, default)
    return getattr(sample, key, default)


def _build_raw_rows(samples: Sequence[Any]) -> list[dict[str, Any]]:
    """Convert samples into long-format CSV rows."""

    rows: list[dict[str, Any]] = []

    for sequence_id, sample in enumerate(samples):
        timestamp = (
            _get(sample, "timestamp_utc")
            or _get(sample, "timestamp")
        )

        if hasattr(timestamp, "isoformat"):
            timestamp = timestamp.isoformat()

        target = (
            _get(sample, "target_name")
            or _get(sample, "target")
            or "unknown"
        )

        metrics = _get(sample, "metrics", {}) or {}
        missing = _get(sample, "missing_reasons", {}) or {}

        if not isinstance(metrics, dict):
            metrics = dict(metrics)

        if not isinstance(missing, dict):
            missing = dict(missing)

        for metric_name, value in metrics.items():
            rows.append({
                "timestamp": timestamp,
                "metric_name": metric_name,
                "value": value,
                "source_id": target,
                "sequence_id": sequence_id,
                "labels": json.dumps({
                    "target": target,
                    "pod_name": _get(sample, "pod_name"),
                    "service_instance_id": _get(
                        sample, "service_instance_id"
                    ),
                    "restart_count": _get(sample, "restart_count"),
                }, ensure_ascii=False),
                "missing_reason": missing.get(metric_name),
            })

    return rows


def _load_workload_config(
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Load workload endpoint configuration."""

    path = (
        Path(config_path)
        if config_path
        else ROOT / "configs" / "workload.yaml"
    )

    config = load_yaml(path)

    if not isinstance(config, dict):
        raise ValueError(f"Invalid workload configuration: {path}")

    return config


def _resolve_source_targets(
    sources: Sequence[str],
    configured_targets: dict[str, Any],
) -> list[str]:
    """Map workload sources to performance targets."""

    selected = []

    for source in sources:
        if source not in SOURCE_TARGETS:
            raise ValueError(f"Unsupported source: {source}")

        target = SOURCE_TARGETS[source]

        if target not in configured_targets:
            raise ValueError(
                f"Target '{target}' for source '{source}' "
                "does not exist in performance.yaml"
            )

        selected.append(target)

    return selected


def _resolve_endpoints(
    sources: Sequence[str],
    workload_config: dict[str, Any],
) -> dict[str, str]:
    """Resolve only verified OTLP HTTP endpoints."""

    source_config = workload_config.get("sources", {})
    endpoints: dict[str, str] = {}

    for source in sources:
        entry = source_config.get(source, {})

        if not isinstance(entry, dict):
            raise ValueError(f"Invalid workload config for {source}")

        if entry.get("status") != "verified":
            raise ValueError(
                f"OTLP endpoint for {source} is not verified"
            )

        endpoint = entry.get("otlp_http_url")

        if not endpoint:
            raise ValueError(
                f"Missing OTLP HTTP endpoint for {source}"
            )

        endpoints[source] = str(endpoint)

    return endpoints


def _run_generators(
    sources: Sequence[str],
    endpoints: dict[str, str],
    rate: float,
    duration: float,
    experiment_id: str,
    scenario: str,
    seed: int,
) -> dict[str, Any]:
    """Run AWS/Azure workload generators concurrently."""

    from workloads.generator import run_continuous_generation

    def run_one(source: str) -> dict[str, Any]:
        _, summary = run_continuous_generation(
            scenario=scenario,
            source_id=source,
            experiment_id=experiment_id,
            seed=seed,
            endpoint=endpoints[source],
            rate=rate,
            duration=duration,
        )
        return summary

    summaries = {}

    with ThreadPoolExecutor(max_workers=len(sources)) as executor:
        futures = {
            source: executor.submit(run_one, source)
            for source in sources
        }

        for source, future in futures.items():
            summaries[source] = future.result()

    return summaries


def _save_repeat(
    samples: Sequence[Any],
    summary: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Persist one repeat independently."""

    run_id = _new_run_id()
    output_dir = create_performance_run_dir(run_id)

    raw_rows = _build_raw_rows(samples)

    write_raw_samples(output_dir, raw_rows)
    write_summary(output_dir, summary)

    metadata.update({
        "run_id": run_id,
        "experiment_type": "performance",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "sample_count": len(samples),
    })

    write_performance_metadata(output_dir, metadata)

    return {
        "run_id": run_id,
        "output_dir": str(output_dir),
        "sample_count": len(samples),
        "summary": summary,
        "metadata": metadata,
    }


def run_performance(
    duration: float = 300,
    interval: float = 1,
    targets: Sequence[str] | None = None,
    config_path: str | Path | None = None,
    timeout: int = 15,
    *,
    sources: Sequence[str] | None = None,
    levels: float = 100,
    warmup: float = 15,
    idle: float = 30,
    repeats: int = 1,
    scenario: str = "small",
    seed: int = 0,
    workload_config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Execute a complete performance experiment."""

    if duration <= 0:
        raise ValueError("duration must be greater than zero")

    if interval <= 0:
        raise ValueError("interval must be greater than zero")

    if warmup < 0 or idle < 0:
        raise ValueError("warmup and idle cannot be negative")

    if repeats < 1:
        raise ValueError("repeats must be at least 1")

    if levels <= 0:
        raise ValueError("levels must be greater than zero")

    config = (
    load_performance_config(config_path)
    if config_path is not None
    else load_performance_config()
    )

    if config.get("_error"):
        raise RuntimeError(config["_error"])

    configured_targets = config.get("targets", {})

    if not isinstance(configured_targets, dict) or not configured_targets:
        raise ValueError("No targets configured in performance.yaml")

    selected_sources = list(sources) if sources else []

    if selected_sources:
        selected_targets = _resolve_source_targets(
            selected_sources,
            configured_targets,
        )

        workload_config = _load_workload_config(
            workload_config_path
        )

        endpoints = _resolve_endpoints(
            selected_sources,
            workload_config,
        )

    else:
        # Backward-compatible sampling-only mode.
        selected_targets = (
            list(targets) if targets else list(configured_targets)
        )
        endpoints = {}
        workload_config = {}

    unknown_targets = [
        target for target in selected_targets
        if target not in configured_targets
    ]

    if unknown_targets:
        raise ValueError(
            f"Unknown target(s): {', '.join(unknown_targets)}"
        )

    repeat_results = []

    for repeat in range(1, repeats + 1):
        experiment_id = _new_run_id()

        generation_summaries = {}

        # ---------------------------------------------
        # Phase 1: Warmup
        # ---------------------------------------------

        if selected_sources and warmup > 0:
            warmup_id = f"{experiment_id}_warmup"

            generation_summaries["warmup"] = _run_generators(
                sources=selected_sources,
                endpoints=endpoints,
                rate=levels,
                duration=warmup,
                experiment_id=warmup_id,
                scenario=scenario,
                seed=seed,
            )

        # ---------------------------------------------
        # Phase 2: Measurement
        # Generator and sampler run concurrently.
        # ---------------------------------------------

        if selected_sources:
            from workloads.generator import run_continuous_generation

            def generate_one(source: str) -> dict[str, Any]:
                _, result = run_continuous_generation(
                    scenario=scenario,
                    source_id=source,
                    experiment_id=experiment_id,
                    seed=seed + repeat,
                    endpoint=endpoints[source],
                    rate=levels,
                    duration=duration,
                )
                return result

            with ThreadPoolExecutor(
                max_workers=len(selected_sources)
            ) as executor:

                futures = {
                    source: executor.submit(generate_one, source)
                    for source in selected_sources
                }

                samples = sample_performance(
                    duration=duration,
                    interval=interval,
                    targets=selected_targets,
                    config_path=config_path,
                    timeout=timeout,
                )

                for source, future in futures.items():
                    generation_summaries[source] = future.result()

        else:
            samples = sample_performance(
                duration=duration,
                interval=interval,
                targets=selected_targets,
                config_path=config_path,
                timeout=timeout,
            )

        # ---------------------------------------------
        # Phase 3: Summarization and persistence
        # ---------------------------------------------

        summary = summarize_samples(samples)

        metadata = {
            "repeat": repeat,
            "total_repeats": repeats,
            "experiment_id": experiment_id,
            "duration_seconds": duration,
            "sampling_interval_seconds": interval,
            "warmup_seconds": warmup,
            "idle_seconds": idle,
            "target_rate": levels if selected_sources else None,
            "kubectl_timeout_seconds": timeout,
            "sources": selected_sources,
            "targets": selected_targets,
            "target_config": {
                name: configured_targets[name]
                for name in selected_targets
            },
            "generator_summary": generation_summaries,
        }

        result = _save_repeat(
            samples=samples,
            summary=summary,
            metadata=metadata,
        )

        repeat_results.append(result)

        # ---------------------------------------------
        # Phase 4: Idle between repeats only
        # ---------------------------------------------

        if repeat < repeats and idle > 0:
            import time
            time.sleep(idle)

    return {
        "repeat_count": len(repeat_results),
        "results": repeat_results,
        "output_dir": repeat_results[-1]["output_dir"],
        "sample_count": sum(
            item["sample_count"] for item in repeat_results
        ),
        "summary": repeat_results[-1]["summary"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a multi-cloud performance experiment."
    )

    parser.add_argument("--config", default=None)
    parser.add_argument(
        "--workload-config",
        default=None,
        help="Path to workload.yaml",
    )
    parser.add_argument(
        "--target",
        action="append",
        dest="targets",
        help="Legacy sampling-only target. Can be repeated.",
    )
    parser.add_argument(
        "--sources",
        default=None,
        help="Comma-separated workload sources, e.g. aws,azure",
    )
    parser.add_argument(
        "--levels",
        type=float,
        default=100,
        help="Target workload rate in datapoints/second.",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=60,
        help="Measurement duration in seconds.",
    )
    parser.add_argument(
        "--warmup",
        type=float,
        default=15,
        help="Warmup duration in seconds.",
    )
    parser.add_argument(
        "--idle",
        type=float,
        default=30,
        help="Idle duration between repeats.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=5,
        help="Performance sampling interval in seconds.",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=1,
        help="Number of experiment repetitions.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=15,
        help="Kubectl timeout in seconds.",
    )
    parser.add_argument(
        "--scenario",
        default="small",
        help="Workload ground-truth scenario.",
    )
    parser.add_argument("--seed", type=int, default=0)

    args = parser.parse_args()

    sources = (
        [item.strip() for item in args.sources.split(",") if item.strip()]
        if args.sources
        else None
    )

    result = run_performance(
        duration=args.duration,
        interval=args.interval,
        targets=args.targets,
        config_path=args.config,
        timeout=args.timeout,
        sources=sources,
        levels=args.levels,
        warmup=args.warmup,
        idle=args.idle,
        repeats=args.repeats,
        scenario=args.scenario,
        seed=args.seed,
        workload_config_path=args.workload_config,
    )

    print(json.dumps({
        "repeat_count": result["repeat_count"],
        "output_dir": result["output_dir"],
        "sample_count": result["sample_count"],
        "results": [
            {
                "run_id": item["run_id"],
                "output_dir": item["output_dir"],
                "sample_count": item["sample_count"],
            }
            for item in result["results"]
        ],
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
