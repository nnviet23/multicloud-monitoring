<!-- markdownlint-disable MD033 -->
<div align="center">

# Multi-Cloud Observability & AIOps Platform

**A reproducible Hub-Spoke observability platform using OpenTelemetry, three local k3d clusters, GitOps, and Deep Learning anomaly detection.**

![k3s](https://img.shields.io/badge/k3s-v1.31.2-blue)
![OpenTelemetry](https://img.shields.io/badge/OpenTelemetry-v0.114.0-blueviolet)
![Grafana](https://img.shields.io/badge/Grafana-11.5.0-orange)
![GitOps](https://img.shields.io/badge/Argo%20CD-v2.12.3-success)

</div>

> **Built from first principles for multi-cloud telemetry research.**
> Every pipeline, policy, dashboard, and alert rule is declarative, version-pinned, and reproducible locally on a 20 GB RAM workstation.

---

## Architecture Overview

The platform implements **Baseline Architecture A** (Edge-Filtered Ingestion with Centralized Processing & Batch Ingestion) across three simulated clusters connected over a `tc/netem` WAN bridge (`mc-monitoring-net`, `172.28.0.0/16`, 10ms ±2ms RTT, 0.1% loss):

```text
  aws-k3d (Compute Spoke)                     azure-k3d (Data Spoke)
  ┌──────────────────────────┐                ┌──────────────────────────┐
  │ TeaStore WebUI / Auth    │                │ TeaStore Persistence     │
  │ Recommender / Image /Reg │                │ MySQL (teastore-db)      │
  │ OTel Edge Collector      │                │ OTel Edge Collector      │
  └────────────┬─────────────┘                └────────────┬─────────────┘
               │  OTLP/gRPC + mTLS 1.3 (tc/netem WAN)      │
               └─────────────────────┬─────────────────────┘
                                     ▼
                     hub-k3d (Central Observability Hub)
  ┌─────────────────────────────────────────────────────────────────────────┐
  │ OTel Hub Gateway (OTTL SemConv v1.45.0, ServiceGraph, Tail Sampling)    │
  │   ├── Metrics: Prometheus + Thanos Sidecar / Query / Store / Compact    │
  │   ├── Logs:    Grafana Loki         Traces: Grafana Tempo               │
  │   ├── Storage: MinIO S3 (thanos-metrics, loki-data, tempo-traces, raw)  │
  │   ├── SLO/UI:  Pyrra (API + K8s Operator) · Grafana (10 Dashboards)     │
  │   ├── Alerting: Alertmanager -> Robusta Runner -> Telegram              │
  │   └── PKI/Sec: cert-manager v1.16.2 · SealedSecrets · NetworkPolicies   │
  └──────────────────────────────────┬──────────────────────────────────────┘
                                     ▼
               AI Anomaly Engine (GRU + TCN + Tempo Trace RCA :9108)
```

---

## Pinned Tech Stack

All container images and tools are strictly pinned (no `:latest` tags); full details live in [infra/README.md](infra/README.md).

| Layer | Component | Pinned Version | Role |
|---|---|---|---|
| **Clusters** | `k3s` / `k3d` | `v1.31.2+k3s1` / `v5.6.0` | Local 3-cluster Hub-Spoke simulation (`hub-k3d`, `aws-k3d`, `azure-k3d`) |
| **Automation** | Python Platform CLI (`infra.cli`) / Kustomize | `3.12+` / `v5.3.0` | Declarative lifecycle, WAN emulation, and in-memory cert sync |
| **GitOps & PKI** | Argo CD / `cert-manager` / SealedSecrets | `v2.12.3` / `v1.16.2` / `v0.24.5` | Multi-cluster GitOps delivery and zero-host-key mTLS 1.3 PKI |
| **Telemetry** | OTel Collector Contrib / Java Agent | `0.114.0` / `2.10.0` | Edge tail-sampling, OTTL SemConv v1.45.0 normalization, Service Graph |
| **Backends** | Prometheus / Thanos / Loki / Tempo / MinIO | `v2.50.0` / `v0.36.1` / `2.9.4` / `2.4.0` | Tiered metrics, logs, traces, and immutable raw S3 storage |
| **Visualization & SLO** | Grafana / Pyrra / Alertmanager / Robusta | `11.5.0` / `v0.7.3` / `v0.27.0` / `0.53.0` | Upstream dashboards, Multi-Burn-Rate SLOs, and Telegram alerting |
| **Benchmark & AI** | Descartes TeaStore / PyTorch (`GRU + TCN`) | `1.4.1` (`teastore-db:1.4.1`) / `2.x` | Microservice workload, chaos injection (`tests/chaos/`), and RCA |

---

## Quickstart

Provisioning and lifecycle are orchestrated via `Makefile` and the **Python Platform CLI** (`python -m infra.cli`):

```bash
# 1. Create .env from .env.example and pre-pull all pinned container images
make setup

# 2. Provision the 3 k3d clusters, WAN bridge, CoreDNS, in-cluster cert-manager PKI, and import images
make infra

# 3. Deploy Hub & Spoke observability stacks and TeaStore benchmark
make deploy

# 4. Run static validation, OTel architecture rules, and 142 automated tests
make test

# 5. Tear down clusters cleanly
make teardown
```

### Service Endpoints

| Service | URL | Credentials | Purpose |
|---|---|---|---|
| **TeaStore WebUI** | `http://localhost:8080/tools.descartes.teastore.webui/` | Anonymous | Benchmark e-commerce storefront |
| **Grafana** | `http://localhost:3000` | `admin` / see `.env` (`CHANGE_ME_GRAFANA_ADMIN_PASSWORD`) | 10 standardized SRE & AIOps dashboards |
| **MinIO Console** | `http://localhost:9001` | `admin` / see `.env` (`CHANGE_ME_MINIO_PASSWORD`) | S3 buckets (`thanos-metrics`, `loki-data`, `tempo-traces`, `raw-telemetry`) |
| **Thanos Query** | `http://localhost:9090` | None | Cross-cluster PromQL query UI |
| **Pyrra SLO UI** | `http://localhost:9099` | None | Availability (99.5%) & Latency (95%) SLO error budgets |

---

## Standardized Grafana Dashboards

All dashboards are provisioned as code from [`deploy/platform/visualization-grafana/dashboards/`](deploy/platform/visualization-grafana/dashboards/) using official upstream templates:

1. `01-platform-overview-golden-signals.json` — **Platform Overview** (4 Golden Signals + AI Anomaly Dual Y-Axis Panel 7)
2. `02-host-compute-node-exporter.json` — **Node Exporter Full** (Community ID #1860)
3. `03-kubernetes-cluster-overview.json` — **Kubernetes / Compute Resources / Cluster** (Kubernetes Mixin)
4. `04-jvm-teastore-runtime.json` — **JVM (Micrometer)** (Community ID #4701)
5. `05-mysql-database-overview.json` — **MySQL Overview** (Community ID #7362)
6. `06-wan-network-latency.json` — **WAN Network & Inter-Cluster Latency** (`tc/netem` RTT & drops)
7. `07-cross-cluster-service-graph.json` — **Cross-Cluster Service Graph** (`traces_service_graph_request_total`)
8. `08-slo-governance-pyrra-list.json` — **Pyrra - List** (Official Pyrra SLO fleet overview)
9. `09-slo-governance-pyrra-detail.json` — **Pyrra - Detail** (Official Pyrra Multi-Window Burn Rate)
10. `10-logs-traces-deepdive.json` — **Logs & Traces Deep-Dive** (Loki LogQL + Tempo TraceQL + Exemplars)

---

## Chaos Engineering & WAN Fault Injection

Controlled fault-injection experiments validate observability coverage, SLO burn-rate alerts, and AI Anomaly Detection RCA:
- **WAN Degradation (`CHAOS-01`):** `python -m infra.cli wan` & `tests/chaos/run_live.py` inject `tc/netem` latency/packet loss on `mc-monitoring-net` with automatic watchdog cleanup.
- **Service & Data Faults (`CHAOS-02..04`):** `tests/chaos/run_service_faults.py` & `tests/chaos/java/FaultAgent.java` trigger HTTP 5xx/pod outages, MySQL `LOCK TABLES`, and JVM CPU/memory leaks.

---

## Repository Layout & Documentation

- `deploy/platform/` — Core Hub & Spoke observability, PKI (`cert-manager`), and GitOps manifests (SRP-organized; metrics use Prometheus + Thanos Sidecar/Query/Store/Compact without Thanos Ruler)
- `deploy/policies/` — Active `NetworkPolicies` (`teastore`, `monitoring`, `storage`) + static Kyverno `ClusterPolicies` (runtime Kyverno controller deferred to Phase 5 Real-Cloud)
- `deploy/argocd/` — Multi-cluster Argo CD `ApplicationSet`s for Hub & Spokes (paired with `python -m infra.cli register-spokes`)
- `deploy/clusters/` — Environment overlays for `hub`, `aws`, and `azure`
- `workloads/` — Benchmark catalog (`teastore/`, `_template/`)
- `infra/` — `Python Platform CLI` (`infra/cli.py`), Argo CD spoke registration, pinned version matrix (`infra/README.md`)
- `ai-engine/` — Deep Learning anomaly detection & Tempo Trace RCA ([`ai-engine/README.md`](ai-engine/README.md))
- `tests/` — Automated verification (`tests/scripts/`, 142 tests) and chaos experiments (`tests/chaos/`)
- `docs/adr/` — 12 Canonical Architecture Decision Records ([`docs/adr/README.md`](docs/adr/README.md))
- `docs/runbooks/` — Modular SRE incident runbooks ([`docs/runbooks/README.md`](docs/runbooks/README.md))
- `docs/planning/progress.md` — Local implementation progress & milestone log

---

## Upstream References

Third-party reference repositories are excluded from Git via `.gitignore` and cataloged here for reproducibility:

| Reference | Upstream Source | Usage in This Platform |
|---|---|---|
| **Platform Engineering Zero to Production** | [`platform-engineering-zero-to-production`](https://github.com/platwright/platform-engineering-zero-to-production) | README structure, 4 Golden Signals dashboard, GitOps & SRE practices |
| **OpenTelemetry Collector Contrib** | [`open-telemetry/opentelemetry-collector-contrib`](https://github.com/open-telemetry/opentelemetry-collector-contrib) | Receiver `metadata.yaml` contracts, OTTL, `tail_sampling`, `servicegraph` |
| **OpenTelemetry Semantic Conventions** | [`open-telemetry/semantic-conventions`](https://github.com/open-telemetry/semantic-conventions) | Canonical attributes (`SemConv v1.45.0`) |
| **OpenTelemetry Operator** | [`open-telemetry/opentelemetry-operator`](https://github.com/open-telemetry/opentelemetry-operator) | Auto-instrumentation patterns & Phase 5 reference |
| **Kubernetes Mixin** | [`kubernetes-monitoring/kubernetes-mixin`](https://github.com/kubernetes-monitoring/kubernetes-mixin) | Cluster resource dashboard & Kubernetes alert rules |
| **Grafana Community Dashboards** | Grafana Labs (`#1860`, `#4701`, `#7362`) | Node Exporter Full, JVM Micrometer, MySQL Overview |
| **Awesome Prometheus Alerts** | [`samber/awesome-prometheus-alerts`](https://github.com/samber/awesome-prometheus-alerts) | 8 domain-modular Prometheus alert rule files |
| **Pyrra & Thanos** | [`pyrra-dev/pyrra`](https://github.com/pyrra-dev/pyrra) & [`thanos-io/thanos`](https://github.com/thanos-io/thanos) | Official SLO dashboards (`Pyrra - List`/`Detail`) & Thanos federation |
| **Grafana Loki & Tempo** | [`grafana/loki`](https://github.com/grafana/loki) & [`grafana/tempo`](https://github.com/grafana/tempo) | S3 MinIO tiered storage configs & trace exemplars |
| **Robusta & Kyverno Policies** | [`robusta-dev/robusta`](https://github.com/robusta-dev/robusta) & [`kyverno/policies`](https://github.com/kyverno/policies) | Telegram alert playbooks & Pod Security admission policies |
| **Descartes TeaStore** | [`DescartesResearch/TeaStore`](https://github.com/DescartesResearch/TeaStore) | Multi-tier microservice benchmark application (`v1.4.1`) |
