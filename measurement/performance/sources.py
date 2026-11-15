"""Single-sample collector and cAdvisor sources.

This module deliberately does not schedule jobs, calculate rates, persist output,
or retry kubectl calls.  A failed call or an absent series is represented by
``None`` and an entry in ``missing_reasons``.

The cAdvisor selectors are configurable because cAdvisor label layouts differ
between kubelet versions.  The default is pod scope, summing non-infra
containers, and summing every network interface.  This is *chưa kiểm chứng với
dữ liệu thật, cần xác nhận bằng mẫu cAdvisor thật*.
"""

from __future__ import annotations

import datetime as _datetime
import inspect
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CONFIG = _ROOT / "configs" / "performance.yaml"
_KUBECTL_TIMEOUT = 15


@dataclass(frozen=True)
class PodInfo:
    name: str | None
    restart_count: int | None
    reason: str | None = None


_METRIC_RE = re.compile(
    r"^([a-zA-Z_:][a-zA-Z0-9_:]*)"
    r"(?:\{(.*)\})?\s+"
    r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|NaN|[+-]?Inf)"
    r"(?:\s+\d+)?$"
)


def _parse_labels(text: str) -> dict[str, str]:
    labels: dict[str, str] = {}
    pos = 0
    while pos < len(text):
        while pos < len(text) and text[pos] in " ,\t":
            pos += 1
        if pos >= len(text):
            break
        key_match = re.match(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*\"", text[pos:])
        if not key_match:
            raise ValueError("invalid Prometheus label")
        key = key_match.group(1)
        pos += key_match.end()
        value: list[str] = []
        while pos < len(text):
            char = text[pos]
            if char == "\\":
                if pos + 1 >= len(text):
                    raise ValueError("unterminated Prometheus escape")
                escaped = text[pos + 1]
                value.append({"n": "\n", "r": "\r", "t": "\t"}.get(escaped, escaped))
                pos += 2
            elif char == '"':
                pos += 1
                break
            else:
                value.append(char)
                pos += 1
        else:
            raise ValueError("unterminated Prometheus label")
        labels[key] = "".join(value)
    return labels


def parse_prometheus_metrics(text: str) -> list[tuple[str, dict[str, str], float]]:
    """Parse Prometheus samples, ignoring HELP and TYPE metadata lines."""
    samples: list[tuple[str, dict[str, str], float]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _METRIC_RE.match(line)
        if not match:
            continue
        try:
            value = float(match.group(3))
            labels = _parse_labels(match.group(2) or "")
        except (ValueError, OverflowError):
            continue
        samples.append((match.group(1), labels, value))
    return samples


def _result_text(result: Any) -> tuple[str | None, str | None]:
    if isinstance(result, str):
        return result, None
    if isinstance(result, bytes):
        return result.decode("utf-8", "replace"), None
    if isinstance(result, tuple) and result:
        text = result[0]
        return (text.decode("utf-8", "replace") if isinstance(text, bytes) else str(text)), None
    if result is None:
        return None, "kubectl returned no result"
    stdout = getattr(result, "stdout", None)
    stderr = getattr(result, "stderr", None)
    return (str(stdout) if stdout is not None else None), (str(stderr) if stderr else None)


def _load_kubernetes_client() -> Any:
    try:
        from common import kubernetes_client  # type: ignore
    except ImportError:
        try:
            from ..common import kubernetes_client  # type: ignore
        except ImportError:
            return None
    return kubernetes_client


def run_kubectl(context: str, args: Sequence[str], timeout: int = _KUBECTL_TIMEOUT) -> tuple[str | None, str | None]:
    """Call the project's kubectl helper, always passing a timeout.

    Tests can replace this function; production code does not invoke kubectl
    directly and therefore keeps authentication/context handling in the shared
    client.
    """
    client = _load_kubernetes_client()
    if client is None:
        return None, "common.kubernetes_client is unavailable"
    helper = next(
        (getattr(client, name, None) for name in ("run_kubectl", "kubectl", "run_command", "run") if getattr(client, name, None)),
        None,
    )
    if helper is None:
        return None, "no kubectl helper found in common.kubernetes_client"

    command = ["kubectl", "--context", context, *args]
    try:
        parameters = inspect.signature(helper).parameters
        kwargs: dict[str, Any] = {}
        positional: list[Any] = []
        for parameter in parameters.values():
            if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
                continue
            name = parameter.name.lower()
            if name in {"context", "ctx", "kube_context"}:
                kwargs[parameter.name] = context
            elif name in {"timeout", "timeout_seconds", "seconds"}:
                kwargs[parameter.name] = timeout
            elif name in {"args", "argv", "command", "cmd", "command_args"}:
                kwargs[parameter.name] = command if name in {"command", "cmd"} else list(args)
            elif parameter.default is parameter.empty:
                positional.append(command)
        result = helper(*positional, **kwargs)
    except Exception as exc:  # kubectl errors must not abort collection
        return None, f"kubectl error: {exc}"
    text, error = _result_text(result)
    return text, error


def _minimal_yaml(text: str) -> dict[str, Any]:
    """Parse the small mapping-only YAML subset used by performance.yaml."""
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip() or ":" not in line:
            continue
        indent = len(line) - len(line.lstrip())
        key, raw_value = line.strip().split(":", 1)
        key = key.strip().strip('"\'')
        raw_value = raw_value.strip()
        while stack[-1][0] >= indent:
            stack.pop()
        current = stack[-1][1]
        if not raw_value:
            child: dict[str, Any] = {}
            current[key] = child
            stack.append((indent, child))
            continue
        value: Any = raw_value.strip('"\'')
        if value.lower() in {"true", "false"}:
            value = value.lower() == "true"
        else:
            try:
                value = float(value) if "." in value else int(value)
            except ValueError:
                pass
        current[key] = value
    return root


def load_performance_config(path: str | Path = _DEFAULT_CONFIG) -> dict[str, Any]:
    """Load performance configuration without requiring PyYAML."""
    try:
        return _minimal_yaml(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        return {"targets": {}, "_error": f"cannot read performance config: {exc}"}


def _target_config(target: str | Mapping[str, Any], config: Mapping[str, Any] | None) -> tuple[str, dict[str, Any]]:
    if isinstance(target, Mapping):
        return str(target.get("name", target.get("target", "unknown"))), dict(target)
    loaded = dict(config or load_performance_config())
    targets = loaded.get("targets", {})
    selected = dict(targets.get(target, {})) if isinstance(targets, Mapping) else {}
    selected["name"] = target
    return target, selected


def _owner_is_deployment(pod: Mapping[str, Any], deployment: str) -> bool:
    for owner in pod.get("metadata", {}).get("ownerReferences", []) or []:
        if owner.get("kind") == "ReplicaSet" and str(owner.get("name", "")).startswith(deployment + "-"):
            return True
        if owner.get("name") == deployment:
            return True
    labels = pod.get("metadata", {}).get("labels", {}) or {}
    return any(labels.get(key) == deployment for key in ("app", "app.kubernetes.io/name", "app.kubernetes.io/instance"))


def find_collector_pod(context: str, namespace: str, deployment: str, timeout: int = _KUBECTL_TIMEOUT) -> PodInfo:
    """Find the newest running pod owned by ``deployment`` and sum restarts."""
    output, error = run_kubectl(
        context,
        ["get", "pods", "-n", namespace, "-o", "json", f"--request-timeout={timeout}s"],
        timeout,
    )
    if not output:
        return PodInfo(None, None, error or "pod list is empty")
    try:
        items = json.loads(output).get("items", [])
    except (TypeError, ValueError) as exc:
        return PodInfo(None, None, f"invalid pod list: {exc}")
    candidates = [pod for pod in items if _owner_is_deployment(pod, deployment)]
    candidates.sort(key=lambda pod: pod.get("metadata", {}).get("creationTimestamp", ""), reverse=True)
    if not candidates:
        return PodInfo(None, None, f"no pod found for deployment {deployment}")
    pod = candidates[0]
    statuses = pod.get("status", {}).get("containerStatuses", []) or []
    restart_count = sum(int(status.get("restartCount", 0) or 0) for status in statuses)
    return PodInfo(pod.get("metadata", {}).get("name"), restart_count)


def _collector_proxy(context: str, namespace: str, pod: str, timeout: int) -> tuple[str | None, str | None]:
    path = f"/api/v1/namespaces/{namespace}/pods/{pod}:8888/proxy/metrics"
    return run_kubectl(context, ["get", "--raw", path, f"--request-timeout={timeout}s"], timeout)


def _cadvisor_proxy(context: str, node: str, timeout: int) -> tuple[str | None, str | None]:
    path = f"/api/v1/nodes/{node}/proxy/metrics/cadvisor"
    return run_kubectl(context, ["get", "--raw", path, f"--request-timeout={timeout}s"], timeout)


def _first(samples: Iterable[tuple[str, dict[str, str], float]], name: str, predicate: Callable[[dict[str, str]], bool] | None = None) -> float | None:
    for metric, labels, value in samples:
        if metric == name and (predicate is None or predicate(labels)):
            return value
    return None


def _sum(samples: Iterable[tuple[str, dict[str, str], float]], name: str, predicate: Callable[[dict[str, str]], bool] | None = None) -> float | None:
    values = [value for metric, labels, value in samples if metric == name and (predicate is None or predicate(labels))]
    return sum(values) if values else None


def extract_collector_metrics(text: str, exporter: str) -> tuple[dict[str, float | str | None], dict[str, str]]:
    """Extract otelcol 0.114.0 metrics without converting counters to rates."""
    samples = parse_prometheus_metrics(text)
    values: dict[str, float | str | None] = {}
    reasons: dict[str, str] = {}

    def take(key: str, value: float | None, reason: str) -> None:
        values[key] = value
        if value is None:
            reasons[key] = reason

    service_id = next((labels.get("service_instance_id") for _, labels, _ in samples if labels.get("service_instance_id")), None)
    take("service_instance_id", service_id, "service_instance_id label is missing")
    for name in ("otelcol_process_cpu_seconds", "otelcol_process_memory_rss", "otelcol_process_uptime"):
        take(name, _first(samples, name), f"metric {name} is missing")
    take(
        "otelcol_receiver_accepted_metric_points",
        _sum(samples, "otelcol_receiver_accepted_metric_points", lambda labels: labels.get("receiver") == "otlp"),
        "otlp metric receiver series is missing",
    )
    for suffix, metric in (("accepted_log_records", "otelcol_receiver_accepted_log_records"), ("accepted_spans", "otelcol_receiver_accepted_spans")):
        value = _sum(samples, metric, lambda labels: labels.get("receiver") == "otlp")
        take(suffix, value, f"otlp {metric} series is missing")
        values[metric] = value
        if value is None:
            reasons[metric] = f"otlp {metric} series is missing"
    for name in ("otelcol_exporter_sent_metric_points", "otelcol_exporter_send_failed_metric_points"):
        take(name, _first(samples, name, lambda labels: labels.get("exporter") == exporter), f"exporter {exporter} metric {name} is missing")
    take(
        "otelcol_exporter_queue_size",
        _first(samples, "otelcol_exporter_queue_size", lambda labels: labels.get("exporter") == exporter and labels.get("data_type") == "metrics"),
        f"metrics queue series for exporter {exporter} is missing",
    )
    return values, reasons


def _label(labels: Mapping[str, str], *names: str) -> str | None:
    for name in names:
        if labels.get(name):
            return labels[name]
    return None


def extract_cadvisor_metrics(text: str, pod: str, namespace: str, options: Mapping[str, Any] | None = None) -> tuple[dict[str, float | None], dict[str, str]]:
    """Extract cAdvisor metrics using configurable pod/container selectors.

    The selection logic is **chưa kiểm chứng với dữ liệu thật, cần xác nhận
    bằng mẫu cAdvisor thật**.
    """
    opts = dict(options or {})
    scope = str(opts.get("scope", "pod"))
    container_name = opts.get("container")
    network_interface = opts.get("network_interface", "all")
    configured_excluded = opts.get("pod_container_exclude", ["", "POD"])
    if isinstance(configured_excluded, str):
        excluded = {configured_excluded}
    else:
        excluded = set(configured_excluded)
    parsed = parse_prometheus_metrics(text)
    selected: list[tuple[str, dict[str, str], float]] = []
    for metric, labels, value in parsed:
        label_pod = _label(labels, "pod", "pod_name", "container_label_io_kubernetes_pod_name")
        label_namespace = _label(labels, "namespace", "container_label_io_kubernetes_namespace")
        if label_pod != pod or (label_namespace and label_namespace != namespace):
            continue
        container = _label(labels, "container", "container_name", "container_label_io_kubernetes_container_name") or ""
        if scope == "container" and container_name and container != container_name:
            continue
        if scope == "pod" and container in excluded:
            continue
        if metric.startswith("container_network_") and network_interface != "all" and labels.get("interface") != network_interface:
            continue
        selected.append((metric, labels, value))
    values: dict[str, float | None] = {}
    reasons: dict[str, str] = {}
    for metric in ("container_cpu_usage_seconds_total", "container_memory_working_set_bytes", "container_network_transmit_bytes_total", "container_network_receive_bytes_total"):
        value = _sum(selected, metric)
        values[metric] = value
        if value is None:
            reasons[metric] = f"no cAdvisor series selected for pod {pod}"
    return values, reasons


def _utc_now() -> _datetime.datetime:
    return _datetime.datetime.now(_datetime.timezone.utc)


def _make_record(data: dict[str, Any]) -> Any:
    """Adapt the record to a compatible model class when one exists."""
    try:
        from common import models  # type: ignore
    except ImportError:
        try:
            from ..common import models  # type: ignore
        except ImportError:
            models = None
    if models is not None:
        for class_name in ("PerformanceSample", "MeasurementSample", "MetricSample", "PerformanceRecord", "Sample"):
            cls = getattr(models, class_name, None)
            if cls is None:
                continue
            try:
                parameters = inspect.signature(cls).parameters
                aliases = {"timestamp": "timestamp_utc", "target": "target_name", "pod": "pod_name", "restarts": "restart_count"}
                kwargs = {name: data.get(name, data.get(aliases.get(name, ""))) for name in parameters if name != "self"}
                return cls(**kwargs)
            except (TypeError, ValueError):
                continue
    return data


def collect_sample(target: str | Mapping[str, Any], config: Mapping[str, Any] | None = None, timeout: int = _KUBECTL_TIMEOUT) -> Any:
    """Take exactly one cleaned sample for one configured target."""
    target_name, settings = _target_config(target, config)
    context = str(settings.get("context", ""))
    namespace = str(settings.get("namespace", ""))
    deployment = str(settings.get("deployment", ""))
    exporter = str(settings.get("exporter", "otlp/hub"))
    missing: dict[str, str] = {}
    pod_info = find_collector_pod(context, namespace, deployment, timeout)
    if not pod_info.name:
        missing["pod_name"] = pod_info.reason or "collector pod is missing"
        collector_values = {key: None for key in (
            "service_instance_id", "otelcol_process_cpu_seconds", "otelcol_process_memory_rss",
            "otelcol_process_uptime", "otelcol_receiver_accepted_metric_points", "accepted_log_records",
            "accepted_spans", "otelcol_exporter_sent_metric_points",
            "otelcol_exporter_send_failed_metric_points", "otelcol_exporter_queue_size",
        )}
        collector_missing = {key: "collector pod is missing" for key in collector_values}
        cadvisor_values = {key: None for key in (
            "container_cpu_usage_seconds_total", "container_memory_working_set_bytes",
            "container_network_transmit_bytes_total", "container_network_receive_bytes_total",
        )}
        cadvisor_missing = {key: "collector pod is missing" for key in cadvisor_values}
    else:
        collector_text, collector_error = _collector_proxy(context, namespace, pod_info.name, timeout)
        if collector_text is None:
            collector_values = {key: None for key in (
                "service_instance_id", "otelcol_process_cpu_seconds", "otelcol_process_memory_rss",
                "otelcol_process_uptime", "otelcol_receiver_accepted_metric_points", "accepted_log_records",
                "accepted_spans", "otelcol_exporter_sent_metric_points",
                "otelcol_exporter_send_failed_metric_points", "otelcol_exporter_queue_size",
            )}
            collector_missing = {key: collector_error or "collector metrics unavailable" for key in collector_values}
        else:
            collector_values, collector_missing = extract_collector_metrics(collector_text, exporter)
        node = settings.get("node")
        if node:
            cadvisor_text, cadvisor_error = _cadvisor_proxy(context, str(node), timeout)
            if cadvisor_text is None:
                cadvisor_values = {key: None for key in (
                    "container_cpu_usage_seconds_total", "container_memory_working_set_bytes",
                    "container_network_transmit_bytes_total", "container_network_receive_bytes_total",
                )}
                cadvisor_missing = {key: cadvisor_error or "cAdvisor metrics unavailable" for key in cadvisor_values}
            else:
                cadvisor_values, cadvisor_missing = extract_cadvisor_metrics(cadvisor_text, pod_info.name, namespace, settings.get("cadvisor"))
        else:
            cadvisor_values = {key: None for key in (
                "container_cpu_usage_seconds_total", "container_memory_working_set_bytes",
                "container_network_transmit_bytes_total", "container_network_receive_bytes_total",
            )}
            cadvisor_missing = {key: "node is not configured" for key in cadvisor_values}
    missing.update(collector_missing)
    missing.update(cadvisor_missing)
    metrics = {**collector_values, **cadvisor_values}
    data: dict[str, Any] = {
        "timestamp": _utc_now(),
        "timestamp_utc": None,
        "target": target_name,
        "target_name": target_name,
        "pod_name": pod_info.name,
        "service_instance_id": metrics.get("service_instance_id"),
        "restart_count": pod_info.restart_count,
        "metrics": metrics,
        "missing_reasons": missing,
    }
    data["timestamp_utc"] = data["timestamp"]
    data.update(metrics)
    return _make_record(data)


def collect_one_sample(target: str | Mapping[str, Any], config: Mapping[str, Any] | None = None, timeout: int = _KUBECTL_TIMEOUT) -> Any:
    """Alias with the name used by callers that emphasize one-shot collection."""
    return collect_sample(target, config=config, timeout=timeout)

