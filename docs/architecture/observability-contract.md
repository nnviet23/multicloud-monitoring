---
title: "Observability Contract: TeaStore & AI Anomaly Engine"
doc_id: OBC-TEASTORE-AI-V1
status: approved
created: 2026-11-28
last_modified: 2026-11-28
owner: "Platform & AIOps Engineering Team"
approver: "SRE / Platform Lead"
---

# Observability Contract — TeaStore & AI Anomaly Engine

## 1. Service Context

| Field | Value |
|---|---|
| **Service Name** | TeaStore Microservices (`aws-k3d` compute, `azure-k3d` persistence) & AI Anomaly Detection Engine V3 (`hub-k3d`) |
| **Owner** | Platform & AIOps Engineering Team |
| **Environments** | Local k3d multi-cluster lab (`aws-k3d`, `azure-k3d`, `hub-k3d`) |
| **Dependencies** | TeaStore WebUI/Auth/Recommender/Image/Registry (`aws-k3d`), TeaStore Persistence & MySQL (`azure-k3d`), OpenTelemetry Collector Edge & Hub Gateways, Thanos Receive, Grafana Loki, Grafana Tempo, Pyrra, Robusta + Telegram |
| **SLO reference** | Pyrra SLO-as-Code manifests in `deploy/platform/hub/` (`slo-teastore-availability` 99.5%, `slo-teastore-latency` p99 < 1500ms) |

## 2. Signals Required

Every service must emit all three signals before workload traffic is accepted.

### 2.1 Metrics

| Metric | Type | Name | Definition |
|---|---|---|---|
| Request rate | Counter | `traces_spanmetrics_calls_total` / `http_server_requests_seconds_count` | Label set: `service_name`, `k8s_cluster_name`, `cloud_provider`, `deployment_environment_name`, `status_code` |
| Error rate | Counter | `traces_spanmetrics_calls_total{status_code="STATUS_CODE_ERROR"}` | HTTP 5xx and unhandled exception spans |
| Latency | Histogram | `traces_spanmetrics_duration_milliseconds_bucket` | Buckets covering 10ms to 10000ms; p50, p95, p99 consumed by Pyrra & Grafana |
| Saturation | Gauge | `container_cpu_usage_seconds_total`, `container_memory_working_set_bytes`, `ai_engine_anomaly_score` | Pod CPU/memory saturation and AI Engine (:9108) anomaly score |
| Service Graph | Counter | `traces_service_graph_request_total` | Pre-aggregated at Hub OTel Gateway via `servicegraphconnector` |

- **Scrape endpoint:** `/metrics` on `:9108` (AI Anomaly Engine) and `:8888`/`:8889` (OTel Collectors), scraped by Prometheus/Thanos on `hub-k3d` and remote-written via Thanos Receive.

### 2.2 Logs

- **Format:** Structured JSON with `timestamp`, `level`, `service.name`, `trace_id`, `span_id`, and canonical OTel resource attributes (`k8s.cluster.name`, `cloud.provider`, `deployment.environment.name`).
- **Shipping:** Spoke OTel Collector DaemonSet (`filelog` receiver) -> mTLS 1.3 OTLP -> Hub OTel Gateway -> Grafana Loki.
- **Retention requirement:** Hot tier 7 days in local Loki PVC; cold/archive tier deferred to object-store S3/MinIO in production overlay.
- **Sensitive data:** Never log credentials, private keys, kubeconfigs, Telegram bot tokens, or unredacted PII/session cookies.

### 2.3 Traces

- **Instrumentation:** OpenTelemetry Java Agent auto-instrumentation on TeaStore services; OpenTelemetry Python SDK on AI Engine & Locust.
- **Context propagation:** W3C TraceContext (`traceparent`, `tracestate`) across all outbound HTTP/JDBC calls, including cross-cluster `aws-k3d` -> `azure-k3d` WAN calls.
- **Sampling:** **Phương án A** — Edge `filter/drop_noise` drops health probes at Spoke; 20% head-based sampling at edge collectors; Hub Central Gateway executes `tail_sampling` preserving 100% error traces and high-latency spans (>1500ms).
- **Key spans:** HTTP entry (`teastore-webui`), inter-service RPC (`teastore-auth`, `teastore-recommender`), cross-cluster persistence (`teastore-persistence`), MySQL JDBC queries, and Tempo Trace RCA decomposition ($T_{\text{WAN}}, T_{\text{self}}, T_{\text{DB}}$).

## 3. Dashboards and Recording Rules

| Artifact | Name / Path in Git | Content |
|---|---|---|
| Service dashboard | `deploy/platform/hub/grafana/` | RED panels (traffic, errors, latency, saturation), Service Graph topology, Panel 7 Dual Y-Axis (Latency vs AI Anomaly Score) |
| Recording rules | `deploy/platform/hub/prometheus/` & Pyrra CRDs | Rate/error-duration derivations, SLO burn-rate expressions, anti-collision compound keys (`k8s_cluster_name`, `cloud_provider`) |
| Dashboard links | Grafana provisioned folder `Multi-Cloud Observability` | Cross-cluster dependency view linking `aws-k3d`, `azure-k3d`, and `hub-k3d` |

- **Dashboard-as-code requirement:** All dashboards and recording rules live in Git under `deploy/platform/hub/` and change via review, not ad-hoc UI edits.

## 4. Alerting and Error Budgets

| Alert | Condition (query) | Severity | Routing | Action |
|---|---|---|---|---|
| High error rate | `sum(rate(traces_spanmetrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m])) by (k8s_cluster_name, service_name) / sum(rate(traces_spanmetrics_calls_total[5m])) by (k8s_cluster_name, service_name) > 0.05` | critical | Robusta -> Telegram Alert Sink (60s cooldown) | Triage via Tempo Trace RCA; check recent deployments |
| Latency p99 breach | `histogram_quantile(0.99, sum(rate(traces_spanmetrics_duration_milliseconds_bucket[5m])) by (le, k8s_cluster_name, service_name)) > 1500` | warning | Robusta -> Telegram Alert Sink | Inspect $T_{\text{WAN}}$ vs $T_{\text{DB}}$ breakdown |
| AI Anomaly Detected | `ai_engine_anomaly_score > 0.8` | warning | Telegram Alert Sink (60s cooldown) | Correlate with Panel 7 Dual Y-Axis and chaos/load state |

- **Error budget policy applied:** Pyrra SLO error budget tracking (99.5% availability over 28d rolling window); budget burn > 2% triggers investigation.
- **Noise control:** `for: 2m` on Prometheus rules, 60s cooldown buffer on AI Engine Telegram sink, and `filter/drop_noise` at edge collectors.

## 5. Release and Verification Gate

| Gate | Requirement |
|---|---|
| Pre-release | `make validate-otel` passes; K8s manifests pass SRP & pinned-tag checks; dashboards and scrape targets healthy |
| Canary verification | Compare error rate (<1%) and p99 latency (<1500ms) against baseline during Locust ramp-up |
| Post-release | Verify all 3 signals (metrics in Thanos, logs in Loki, traces in Tempo) within 5 minutes of deployment |

- **Verification evidence:** Recorded in `docs/planning/progress.md` and `docs/planning/activity.md` with experiment IDs (`YYYYMMDD_<workload>_<scenario>_<runNN>`).

## 6. Ownership and Review

| Item | Value |
|---|---|
| **Observability owner** | Platform & AIOps Engineering Team |
| **Review cadence** | Quarterly or on ADR / architecture change |
| **Next review date** | 2027-02-28 |

### Sign-off

| Role | Name | Date |
|---|---|---|
| Service Owner | Platform & AIOps Engineering Team | 2026-11-28 |
| SRE / Platform Lead | SRE / Platform Lead | 2026-11-28 |

*This contract is part of the service's production readiness review and lives in Git next to the dashboards and rules it describes.*
