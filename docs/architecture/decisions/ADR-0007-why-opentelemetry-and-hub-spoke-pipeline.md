# ADR-0007: Why OpenTelemetry and a Hub-Spoke Collector Pipeline

## Status
Accepted

## Context
The multi-cloud platform emits metrics, logs, and traces across distributed TeaStore microservices running on `aws-k3d` and `azure-k3d`, which must be aggregated at `hub-k3d`. Using backend-specific agents and SDKs couples application code to individual backends, while sending raw telemetry unfiltered over the simulated WAN wastes bandwidth (Kubernetes health probes alone account for 60–80% of raw spans/logs) and causes semantic label collisions across clusters.

## Decision
We standardize on **OpenTelemetry (OTel)** with zero-code instrumentation and a **DaemonSet + Gateway Hub-Spoke collector pipeline** (Architecture Baseline: Edge-Filtered Ingestion with Centralized Processing & Batch Ingestion):
- **Zero-code instrumentation:** Attach the OTel Javaagent via `initContainer` (`JAVA_TOOL_OPTIONS`) on TeaStore pods and use the `mysql` receiver on `azure-k3d`.
- **Two-tier collector topology:** Run node-local DaemonSet/edge collectors on `aws-k3d` and `azure-k3d` for host metrics, pod logs, `filter/drop_noise` (dropping `/health`, `/ready`, `/actuator/health`), and 20% head-based sampling (preserving 100% of `ERROR` and `>1500ms` traces) before WAN egress.
- **Hub Central Gateway (`hub-k3d`):** Terminates mTLS 1.3, runs `tail_sampling` (100% error and `>1500ms` preservation), normalizes attributes to OTel Semantic Conventions (`deployment.environment.name`, `cloud.provider`, `cloud.region`, `k8s.cluster.name`, `k8s.pod.uid`) via OTTL, and pre-aggregates `traces_service_graph_request_total` via `servicegraphconnector` before tail sampling.
- **Strict processor order:** Every collector pipeline enforces `memory_limiter` -> `filter` -> `transform` -> `batch` -> `exporter`.

## Alternatives Considered
- **Backend-native agents/SDKs (Prometheus client + Jaeger + Promtail):** Couples application code to specific backends and fragments operational tooling.
- **Single-tier collector (Agent-only or Gateway-only):** Agent-only cannot perform cluster-wide tail sampling; gateway-only cannot gather node-local host metrics and pod logs.
- **100% full ingestion without edge filtering:** Overwhelms storage and inflates WAN egress costs.
- **Manual SDK instrumentation:** Requires invasive Java source changes to SPEC RG TeaStore.

## Consequences
- **Positive:** Vendor-neutral instrumentation; 60–80% reduction in WAN egress volume; consistent cross-cluster correlation across Prometheus/Thanos, Loki, and Tempo.
- **Trade-offs:** OTel Javaagent adds ~3–5s container startup time and ~50 MB RAM per pod; operating both edge collectors and a central gateway adds an extra network hop and requires memory sizing for `tail_sampling` buffers.
