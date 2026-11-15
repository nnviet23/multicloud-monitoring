"""Small Prometheus HTTP API client with bounded retries."""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

LOGGER = logging.getLogger(__name__)


class PrometheusError(RuntimeError):
    """Prometheus request or response error."""


class PrometheusClient:
    """Read-only Prometheus API client."""

    def __init__(self, base_url: str, timeout: float = 5.0, retries: int = 2):
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must use http or https")
        if timeout <= 0 or retries < 0:
            raise ValueError("timeout must be positive and retries non-negative")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = requests.get(
                    f"{self.base_url}{path}", params=params, timeout=self.timeout
                )
                response.raise_for_status()
                body = response.json()
                if body.get("status") != "success":
                    raise PrometheusError(f"Prometheus returned non-success: {body}")
                if body.get("warnings"):
                    LOGGER.warning("Prometheus partial warnings: %s", body["warnings"])
                return body["data"]
            except (requests.RequestException, ValueError, PrometheusError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(0.2 * (attempt + 1))
        raise PrometheusError(f"GET {path} failed after retries: {last_error}") from last_error

    def query(self, expression: str, time_value: str | None = None) -> Any:
        """Run an instant query."""

        if not expression.strip():
            raise ValueError("expression must not be empty")
        params: dict[str, Any] = {"query": expression}
        if time_value:
            params["time"] = time_value
        return self._get("/api/v1/query", params)

    def query_range(
        self, expression: str, start: str, end: str, step: str, dedup: bool = False
    ) -> Any:
        """Run a range query preserving raw returned samples."""

        if not expression.strip() or not start or not end or not step:
            raise ValueError("expression, start, end and step are required")
        params = {
            "query": expression, "start": start, "end": end, "step": step,
            "dedup": str(dedup).lower(),
        }
        return self._get("/api/v1/query_range", params)

    def label_values(self, label: str = "__name__") -> list[str]:
        """List values for a label."""

        if not label or "/" in label:
            raise ValueError("invalid label")
        return self._get(f"/api/v1/label/{label}/values")
