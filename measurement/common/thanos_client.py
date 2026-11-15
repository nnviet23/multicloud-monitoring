"""Thanos Query HTTP client."""

from __future__ import annotations

from .prometheus_client import PrometheusClient


class ThanosClient(PrometheusClient):
    """Prometheus-compatible Thanos client with explicit dedup control."""
