"""Read-only kubectl wrapper."""

from __future__ import annotations

import subprocess
import json
from typing import Sequence


class KubernetesError(RuntimeError):
    """Raised when a read-only kubectl command fails."""


class KubernetesClient:
    """Allow only explicitly read-only kubectl subcommands."""

    ALLOWED = {"get", "describe", "logs", "top", "config"}

    def __init__(self, context: str, kubectl: str = "kubectl"):
        if not context.strip():
            raise ValueError("context is required")
        self.context = context
        self.kubectl = kubectl

    def run(self, args: Sequence[str], timeout: float = 20.0) -> str:
        """Run a read-only command and return stdout."""

        if not args or args[0] not in self.ALLOWED:
            raise ValueError(f"Unsupported non-read-only kubectl command: {args}")
        command = [self.kubectl, *args, "--context", self.context]
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=timeout, check=False
            )
        except subprocess.TimeoutExpired as exc:
            raise KubernetesError(f"kubectl timed out: {command}") from exc
        if result.returncode:
            raise KubernetesError(result.stderr.strip() or f"kubectl failed: {command}")
        return result.stdout

    
   
    def get_raw(self, path: str, timeout: float = 20.0) -> str:
        """Read a raw Kubernetes API endpoint."""

        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("Raw API path must start with a single '/'")

        return self.run(
            ["get", "--raw", path],
            timeout=timeout,
        )

    def find_collector_pods(
        self,
        namespace: str = "monitoring",
        label_selector: str = "app=otel-collector-spoke",
        timeout: float = 20.0,
    ) -> list[dict]:
        """Find currently running OpenTelemetry Collector pods."""

        output = self.run(
            [
                "get",
                "pods",
                "-n", namespace,
                "-l", label_selector,
                "-o", "json",
            ],
            timeout=timeout,
        )

        try:
            data = json.loads(output)
        except json.JSONDecodeError as exc:
            raise KubernetesError(
                "Invalid JSON returned when listing collector pods"
            ) from exc

        collectors = []

        for pod in data.get("items", []):
            metadata = pod.get("metadata", {})
            status = pod.get("status", {})

            if status.get("phase") != "Running":
                continue

            container_statuses = status.get("containerStatuses", [])

            collectors.append({
                "name": metadata.get("name"),
                "namespace": metadata.get("namespace"),
                "node": pod.get("spec", {}).get("nodeName"),
                "phase": status.get("phase"),
                "ready": bool(container_statuses) and all(
                    container.get("ready", False)
                    for container in container_statuses
                ),
            })

        return collectors
