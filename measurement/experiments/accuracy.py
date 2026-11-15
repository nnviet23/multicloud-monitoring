"""Run spoke Jobs in parallel, collect Thanos snapshots, and print accuracy."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from accuracy.completeness import completeness, loss
from common.config import ROOT, load_yaml, validate_configs
from common.result_writer import (
    create_run_dir,
    new_experiment_id,
    write_ground_truth,
    write_metadata,
)
from common.time_utils import utc_now_iso
from workloads.ground_truth import build_ground_truth_for_sources
from workloads.scenarios import SCENARIOS, expected_count
from workloads.collect import collect_run

LOGGER = logging.getLogger(__name__)
CONTEXTS = {"aws": "k3d-aws-k3d", "azure": "k3d-azure-k3d"}
DEFAULT_ENDPOINT = "http://otel-collector-spoke.monitoring.svc:4318"


def _job_name(experiment_id: str, source_id: str) -> str:
    safe = "".join(char if char.isalnum() or char == "-" else "-" for char in experiment_id.lower())
    return f"measurement-{safe}-{source_id}"[:63].rstrip("-")


def _render_manifest(
    template: str,
    experiment_id: str,
    source_id: str,
    scenario: str,
    seed: int,
    image: str,
    endpoint: str,
) -> str:
    values = {
        "${EXPERIMENT_ID}": experiment_id,
        "${SOURCE_ID}": source_id,
        "${SCENARIO}": scenario,
        "${SEED}": str(seed),
        "${IMAGE}": image,
        "${ENDPOINT}": endpoint,
        "${JOB_NAME}": _job_name(experiment_id, source_id),
    }
    for token, value in values.items():
        template = template.replace(token, value)
    return template


def _kubectl(
    context: str,
    args: list[str],
    timeout: float,
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    command = ["kubectl", "--context", context, "-n", "monitoring", *args]
    return subprocess.run(
        command, input=stdin, capture_output=True, text=True, timeout=timeout, check=False
    )


def apply_job(context: str, manifest: str, timeout: float = 30.0) -> None:
    result = _kubectl(context, ["apply", "-f", "-"], timeout, stdin=manifest)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"kubectl apply failed for {context}")


def wait_for_job(context: str, job_name: str, timeout_seconds: float) -> None:
    result = _kubectl(
        context,
        ["wait", f"--for=condition=complete", f"job/{job_name}", f"--timeout={int(timeout_seconds)}s"],
        timeout=timeout_seconds + 10,
    )
    if result.returncode:
        logs = _kubectl(context, ["logs", f"job/{job_name}"], timeout=20)
        detail = logs.stdout.strip() or logs.stderr.strip()
        raise RuntimeError(
            f"Job {job_name} did not complete in {context}: "
            f"{result.stderr.strip()}\n{detail}"
        )


def delete_job(context: str, job_name: str) -> None:
    result = _kubectl(
        context, ["delete", "job", job_name, "--ignore-not-found=true"], timeout=30
    )
    if result.returncode:
        LOGGER.warning("could not delete %s/%s: %s", context, job_name, result.stderr.strip())


def _read_samples(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _accuracy_for_source(
    source: str,
    expected_rows: list[dict[str, Any]],
    collected: dict[str, Any],
    received: list[dict[str, str]],
) -> dict[str, Any]:
    expected_planned = len(expected_rows)
    expected_counter = collected.get("expected_counter_final")
    counter_final = collected.get("counter_final")
    reset = bool(collected.get("counter_reset"))
    denominator = int(expected_counter) if expected_counter is not None else expected_planned
    if reset or counter_final is None or denominator == 0:
        completeness_percent = None
        loss_percent = None
    else:
        completeness_percent = completeness(denominator, float(counter_final))
        loss_percent = loss(denominator, float(counter_final))

    expected_last = max(expected_rows, key=lambda row: int(row["sequence_id"])) if expected_rows else None
    last_sequence = collected.get("last_sequence_id")
    last_value = collected.get("last_value")
    correctness: str
    if reset or last_sequence is None or last_value is None or expected_last is None:
        correctness = "UNKNOWN"
    elif int(float(last_sequence)) != int(expected_last["sequence_id"]):
        correctness = "FAIL"
    elif abs(float(last_value) - float(expected_last["metric_value"])) > 1e-6:
        correctness = "FAIL"
    else:
        correctness = "PASS"

    counter_extra = 0.0
    if expected_counter is not None and counter_final is not None:
        counter_extra = max(0.0, float(counter_final) - float(expected_counter))
    duplicate_keys = Counter(
        (
            row.get("source_id"), row.get("timestamp"), row.get("metric_name"),
            row.get("value"), row.get("labels"),
        )
        for row in received
        if row.get("source_id") == source
    )
    raw_duplicates = sum(count - 1 for count in duplicate_keys.values() if count > 1)
    denominator_for_duplication = float(expected_counter or expected_planned or 1)
    duplication_percent = (counter_extra + raw_duplicates) / denominator_for_duplication * 100.0
    return {
        "source_id": source,
        "expected": expected_counter if expected_counter is not None else expected_planned,
        "planned_expected": expected_planned,
        "counter_final": counter_final,
        "completeness_percent": completeness_percent,
        "loss_percent": loss_percent,
        "correctness": correctness,
        "duplication_percent": duplication_percent,
        "counter_extra": counter_extra,
        "raw_duplicate_samples": raw_duplicates,
        "counter_reset": reset,
        "limitation": (
            "Prometheus stores scrape snapshots, not individual datapoints; "
            "sequence correctness is checked only through last_sequence_id/last_value, "
            "and duplicate detection is bounded to counter excess and exact raw samples."
        ),
    }


def _combined(results: list[dict[str, Any]]) -> dict[str, Any]:
    expected = sum(float(result["expected"]) for result in results)
    counter_final = sum(float(result["counter_final"]) for result in results if result["counter_final"] is not None)
    reset = any(result["counter_reset"] for result in results)
    if reset or any(result["counter_final"] is None for result in results):
        complete = None
        missing = None
    else:
        complete = completeness(int(expected), counter_final) if expected else None
        missing = loss(int(expected), counter_final) if expected else None
    return {
        "source_id": "combined",
        "expected": int(expected),
        "counter_final": int(counter_final),
        "completeness_percent": complete,
        "loss_percent": missing,
        "correctness": "PASS" if all(result["correctness"] == "PASS" for result in results) else "UNKNOWN",
        "duplication_percent": sum(float(result["counter_extra"]) + float(result["raw_duplicate_samples"]) for result in results) / (expected or 1) * 100.0,
        "counter_reset": reset,
        "limitation": "Combined result sums independent source counters; it does not reconstruct per-sequence history.",
    }


def run_experiment(
    scenario: str,
    sources: list[str],
    seed: int = 0,
    image: str = "measurement:latest",
    endpoint: str = DEFAULT_ENDPOINT,
    keep: bool = False,
    job_timeout: float = 600.0,
    collect_wait: float = 120.0,
    thanos_url: str | None = None,
    collect_poll_interval: float = 5.0,
    collect_stable_polls: int = 3,
) -> tuple[str, Path, dict[str, Any]]:
    """Run the complete local orchestration flow."""

    validate_configs()
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario: {scenario}")
    if not sources or any(source not in CONTEXTS for source in sources):
        raise ValueError("sources must be a non-empty subset of aws,azure")
    experiment_id = new_experiment_id(scenario)
    run_dir = create_run_dir(experiment_id)
    metric_name = str(load_yaml(ROOT / "configs" / "workload.yaml")["metric_name"])
    ground_truth = build_ground_truth_for_sources(
        scenario, sources, seed, metric_name, experiment_id
    )
    created_at = utc_now_iso()
    metadata = {
        "experiment_id": experiment_id,
        "scenario": scenario,
        "sources": sources,
        "seed": seed,
        "expected_datapoints_per_source": expected_count(scenario),
        "metric_name": metric_name,
        "created_at": created_at,
        "image": image,
        "generator_endpoint": endpoint,
        "contexts": {source: CONTEXTS[source] for source in sources},
        "status": "RUNNING",
        "provenance": "measured",
    }
    write_metadata(run_dir, metadata)
    write_ground_truth(run_dir, ground_truth)

    template_path = ROOT / "k8s" / "job-template.yaml"
    template = template_path.read_text(encoding="utf-8")
    manifests = {
        source: _render_manifest(template, experiment_id, source, scenario, seed, image, endpoint)
        for source in sources
    }
    jobs = {source: _job_name(experiment_id, source) for source in sources}
    try:
        with ThreadPoolExecutor(max_workers=len(sources)) as executor:
            apply_futures = {
                executor.submit(apply_job, CONTEXTS[source], manifests[source]): source
                for source in sources
            }
            for future in as_completed(apply_futures):
                future.result()
        with ThreadPoolExecutor(max_workers=len(sources)) as executor:
            wait_futures = {
                executor.submit(wait_for_job, CONTEXTS[source], jobs[source], job_timeout): source
                for source in sources
            }
            for future in as_completed(wait_futures):
                future.result()
        collected = collect_run(
            experiment_id, run_dir=run_dir, thanos_url=thanos_url,
            wait=collect_wait, poll_interval=collect_poll_interval,
            stable_polls=collect_stable_polls,
        )
        received = _read_samples(run_dir / "received_samples.csv")
        by_source_expected = {
            source: [point.as_dict() for point in ground_truth if point.source_id == source]
            for source in sources
        }
        accuracy_results = [
            _accuracy_for_source(source, by_source_expected[source], collected["sources"].get(source, {}), received)
            for source in sources
        ]
        accuracy_results.append(_combined(accuracy_results))
        accuracy = {
            "experiment_id": experiment_id,
            "computed_at_utc": utc_now_iso(),
            "sources": accuracy_results,
            "collection_errors": collected["errors"],
        }
        (run_dir / "accuracy.json").write_text(
            json.dumps(accuracy, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        metadata.update({"status": "SUCCESS", "completed_at": utc_now_iso()})
        (run_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return experiment_id, run_dir, accuracy
    finally:
        if not keep:
            for source in sources:
                delete_job(CONTEXTS[source], jobs[source])


def _print_table(results: list[dict[str, Any]]) -> None:
    headers = ["source", "expected", "counter", "complete %", "loss %", "correctness", "duplication %"]
    print(" | ".join(headers))
    print("-|-".join("---" for _ in headers))
    for result in results:
        def percent(value: Any) -> str:
            return "N/A" if value is None else f"{float(value):.2f}"
        print(" | ".join([
            str(result["source_id"]), str(result["expected"]), str(result["counter_final"]),
            percent(result["completeness_percent"]), percent(result["loss_percent"]),
            str(result["correctness"]), percent(result["duplication_percent"]),
        ]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="small")
    parser.add_argument("--sources", default="aws,azure")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--image", default="measurement:latest")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--job-timeout", type=float, default=600.0)
    parser.add_argument("--wait", type=float, default=120.0)
    parser.add_argument("--thanos-url")
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--stable-polls", type=int, default=3)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sources = [item.strip() for item in args.sources.split(",") if item.strip()]
    experiment_id, run_dir, accuracy = run_experiment(
        args.scenario, sources, args.seed, args.image, args.endpoint, args.keep,
        args.job_timeout, args.wait, args.thanos_url, args.poll_interval, args.stable_polls,
    )
    print(f"experiment_id={experiment_id}")
    print(f"results={run_dir}")
    _print_table(accuracy["sources"])
    return 0 if not accuracy["collection_errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
