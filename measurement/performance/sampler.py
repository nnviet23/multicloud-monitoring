
"""Periodic performance sampler for configured Kubernetes targets.

Responsibilities:
- Load configured targets.
- Collect one sample from each target.
- Schedule repeated collection using a fixed interval.
- Stop after the requested duration.

This module does not calculate statistics, retry kubectl calls,
or persist experiment results.
"""

from __future__ import annotations

import time

from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .sources import (
    collect_sample,
    load_performance_config,
)


# ---------------------------------------------------------
# Defaults
# ---------------------------------------------------------

DEFAULT_INTERVAL = 1.0
DEFAULT_DURATION = 300.0
DEFAULT_TIMEOUT = 15


# ---------------------------------------------------------
# Validation
# ---------------------------------------------------------

def _validate_sampling_parameters(
    interval: float,
    duration: float,
) -> None:
    """Validate sampling interval and duration."""

    if interval <= 0:
        raise ValueError("interval must be greater than zero")

    if duration <= 0:
        raise ValueError("duration must be greater than zero")


# ---------------------------------------------------------
# Target resolution
# ---------------------------------------------------------

def resolve_targets(
    config: Mapping[str, Any],
    targets: Sequence[str | Mapping[str, Any]] | None = None,
) -> list[str | Mapping[str, Any]]:
    """Resolve target names from configuration."""

    configured_targets = config.get("targets", {})

    if not isinstance(configured_targets, Mapping):
        raise ValueError("Invalid targets configuration")

    if targets is not None:
        selected = list(targets)
    else:
        selected = list(configured_targets.keys())

    if not selected:
        raise ValueError("No performance targets configured")

    for target in selected:
        if isinstance(target, str):
            if target not in configured_targets:
                raise ValueError(
                    f"Target '{target}' is not configured"
                )
        elif not isinstance(target, Mapping):
            raise TypeError(
                "Each target must be a name or configuration mapping"
            )

    return selected


# ---------------------------------------------------------
# Single sampling round
# ---------------------------------------------------------

def collect_targets_once(
    targets: Sequence[str | Mapping[str, Any]],
    config: Mapping[str, Any] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    collector: Callable[..., Any] | None = None,
) -> list[Any]:
    """Collect exactly one sample from every target.

    Collection is sequential. Each target produces one record.
    """

    collect = collector or collect_sample

    samples: list[Any] = []

    for target in targets:
        sample = collect(
            target,
            config=config,
            timeout=timeout,
        )

        samples.append(sample)

    return samples


# ---------------------------------------------------------
# Periodic sampling
# ---------------------------------------------------------

def sample_targets(
    targets: Sequence[str | Mapping[str, Any]],
    duration: float = DEFAULT_DURATION,
    interval: float = DEFAULT_INTERVAL,
    config: Mapping[str, Any] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    collector: Callable[..., Any] | None = None,
) -> list[Any]:
    """Collect samples continuously for the requested duration.

    Sampling schedule:
        t = 0
        t = interval
        t = 2 * interval
        ...

    If a collection round takes longer than the interval,
    missed sampling slots are skipped instead of running
    multiple rounds back-to-back.
    """

    _validate_sampling_parameters(interval, duration)

    if not targets:
        raise ValueError("At least one target is required")

    collect = collector or collect_sample

    samples: list[Any] = []

    start_time = time.monotonic()
    next_sample_time = start_time

    while True:
        current_time = time.monotonic()

        # Stop when the experiment duration has elapsed.
        if current_time - start_time >= duration:
            break

        # Collect one sample from each target.
        for target in targets:
            sample = collect(
                target,
                config=config,
                timeout=timeout,
            )

            samples.append(sample)

        # Schedule the next sampling round.
        next_sample_time += interval

        current_time = time.monotonic()

        remaining = next_sample_time - current_time

        if remaining > 0:
            time.sleep(remaining)

        else:
            # Skip missed slots to avoid back-to-back sampling.
            missed_slots = int(
                (-remaining) // interval
            ) + 1

            next_sample_time += missed_slots * interval

    return samples


# ---------------------------------------------------------
# Config-based sampling entry point
# ---------------------------------------------------------

def sample_performance(
    duration: float = DEFAULT_DURATION,
    interval: float = DEFAULT_INTERVAL,
    targets: Sequence[str | Mapping[str, Any]] | None = None,
    config_path: str | Path | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    collector: Callable[..., Any] | None = None,
) -> list[Any]:
    """Load configuration and run a performance sampling session."""

    _validate_sampling_parameters(interval, duration)

    if config_path is None:
        config = load_performance_config()
    else:
        config = load_performance_config(config_path)

    if config.get("_error"):
        raise RuntimeError(config["_error"])

    selected_targets = resolve_targets(
        config,
        targets,
    )

    return sample_targets(
        targets=selected_targets,
        duration=duration,
        interval=interval,
        config=config,
        timeout=timeout,
        collector=collector,
    )
