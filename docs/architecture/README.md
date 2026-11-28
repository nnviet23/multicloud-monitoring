# Architecture Overview — Multi-Cloud Observability & Closed-Loop AIOps

> This document serves as the unified entry point for `docs/architecture/`. It explains **how the system works**, **how telemetry flows across clusters**, and **how security, cost, and reliability are enforced**. Detailed design rationales and normative specifications live in [Architecture Decision Records (`decisions/`)](decisions/README.md).

---

## 1. Documentation Map

- **[Architecture Decision Records (`decisions/`)](decisions/README.md)** — 13 canonical ADRs (`ADR-0001`–`ADR-0013`) covering topology, policy-as-code, zero-trust mTLS, GitOps, SLOs, OpenTelemetry pipelines, tiered storage, benchmarking, chaos engineering, FinOps, AIOps, and repository layout.
- **[Platform Concepts (`concepts/`)](concepts/)** — 14 foundational guides (`01`–`14`):
  - [01 — Platform and Kubernetes Fundamentals](concepts/01-platform-and-kubernetes-fundamentals.md)
  - [02 — Infrastructure as Code](concepts/02-infrastructure-as-code.md)
  - [03 — CI/CD for Platform Teams](concepts/03-cicd-for-platform-teams.md)
  - [04 — Kubernetes Package Management](concepts/04-kubernetes-package-management.md)
  - [05 — GitOps and Argo CD](concepts/05-gitops-and-argocd.md)
  - [06 — Kubernetes Advanced](concepts/06-kubernetes-advanced.md)
  - [07 — Observability Engineering](concepts/07-observability-engineering.md)
  - [08 — Security and Policy Engineering](concepts/08-security-and-policy-engineering.md)
  - [09 — Kubernetes Networking](concepts/09-kubernetes-networking.md)
  - [10 — Developer Experience and IDP](concepts/10-developer-experience-and-idp.md)
  - [11 — Platform SRE](concepts/11-platform-sre.md)
  - [12 — FinOps and Cost Engineering](concepts/12-finops-and-cost-engineering.md)
  - [13 — Multi-Cluster and Multi-Cloud](concepts/13-multi-cluster-and-multi-cloud.md)
  - [14 — Advanced Platform Topics](concepts/14-advanced-platform-topics.md)
- **[Cheatsheets (`cheatsheets/`)](cheatsheets/README.md)** — Quick-reference operational guides for `kubectl`, Kubernetes, GitOps, Argo CD, Terraform, observability, security, networking, FinOps, and platform maturity.

---

## 2. System Components

The platform follows a **Hub-Spoke** model across three local `k3d` Kubernetes clusters orchestrated via `infra.cli` and `Makefile`:

| Component | Cluster / Location | Technology & Version | Role & ADR Reference |
| :--- | :--- | :--- | :--- |
| **TeaStore Compute** | `aws-k3d` (Spoke 1) | Java 11 Tomcat (`webui`, `auth`, `recommender`, `image`, `registry`) | Compute service tier of the benchmark workload ([ADR-0010](decisions/ADR-0010-why-teastore-and-locust.md)) |
| **TeaStore Data** | `azure-k3d` (Spoke 2) | Java 11 JPA (`persistence`), TeaStore DB (`teastore-db:1.4.1`) | Persistence tier and relational database ([ADR-0010](decisions/ADR-0010-why-teastore-and-locust.md)) |
| **OTel Java Agent** | Both Spokes | `opentelemetry-javaagent:v2.10.0` | Zero-code bytecode instrumentation ([ADR-0007](decisions/ADR-0007-why-opentelemetry-and-hub-spoke-pipeline.md)) |
| **Locust Generator** | Host / External | Python `locustio/locust:2.24.0` | E-commerce user traffic simulation ([ADR-0010](decisions/ADR-0010-why-teastore-and-locust.md)) |
| **Spoke OTel Collector** | `aws-k3d`, `azure-k3d` | `otel/opentelemetry-collector-contrib:0.114.0` | Edge metrics/logs/traces collection and health-probe noise filtering ([ADR-0007](decisions/ADR-0007-why-opentelemetry-and-hub-spoke-pipeline.md)) |
| **WAN Network Bridge** | Docker Network | Linux Kernel `tc netem` | Simulated wide-area network impairment (RTT $10\text{ ms} \pm 2\text{ ms}$, loss $0.1\%$) ([ADR-0001](decisions/ADR-0001-why-multi-cluster-hub-spoke.md)) |
| **Native mTLS 1.3** | gRPC Transport | Go `crypto/tls` (TLS 1.3) | End-to-end encrypted OTLP `:4317` transport without L7 reverse proxies ([ADR-0003](decisions/ADR-0003-why-mtls-zero-trust-pki.md)) |
| **Hub OTel Gateway** | `hub-k3d` (Central) | `otel/opentelemetry-collector-contrib:0.114.0` | OTTL normalization, service graph aggregation, tail-based sampling ([ADR-0007](decisions/ADR-0007-why-opentelemetry-and-hub-spoke-pipeline.md)) |
| **Thanos Suite** | `hub-k3d` (Central) | `quay.io/thanos/thanos:v0.36.1` (Receive, Query, Store, Compact, Ruler) | Hot TSDB ingestion, global query federation, and alerting ([ADR-0008](decisions/ADR-0008-why-thanos-loki-tempo.md)) |
| **Grafana Loki** | `hub-k3d` (Central) | `grafana/loki:2.9.4` | Distributed log aggregation and indexing ([ADR-0008](decisions/ADR-0008-why-thanos-loki-tempo.md)) |
| **Grafana Tempo** | `hub-k3d` (Central) | `grafana/tempo:2.4.0` | High-volume distributed trace storage ([ADR-0008](decisions/ADR-0008-why-thanos-loki-tempo.md)) |
| **MinIO S3** | `hub-k3d` (Central) | `cgr.dev/chainguard/minio:latest` | Cold object storage tier for Metrics, Logs, and Traces ([ADR-0009](decisions/ADR-0009-why-minio-object-storage.md)) |
| **Grafana + Sidecar** | `hub-k3d` (Central) | `grafana/grafana:11.5.0` | SRE dashboards (USE/RED, Dual Y-Axis) ([ADR-0008](decisions/ADR-0008-why-thanos-loki-tempo.md)) |
| **Pyrra (SLO-as-Code)** | `hub-k3d` (Central) | `ghcr.io/pyrra-dev/pyrra:v0.7.3` | Multi-window multi-burn-rate PromQL SLO alerting ([ADR-0006](decisions/ADR-0006-why-pyrra-and-robusta.md)) |
| **Robusta Runner** | `hub-k3d` (Central) | `robustadev/robusta-runner:0.53.0` | 4W alert enrichment and automated remediation ([ADR-0006](decisions/ADR-0006-why-pyrra-and-robusta.md)) |
| **AI Anomaly Engine V3** | Host / Container | PyTorch 2.1+, Scikit-Learn | Deep Ensemble (GRU + TCN + Isolation Forest), Tempo Trace RCA, Exporter `:9108` ([ADR-0013](decisions/ADR-0013-why-ai-anomaly-detection-and-rca.md)) |

---

## 3. Multi-Cluster Topology & Telemetry Flow

```mermaid
flowchart TD
    subgraph SpokeAWS["Spoke 1 — aws-k3d (Compute Simulation)"]
        TS_UI["TeaStore WebUI / Auth / Rec / Image"]
        LOCUST["Locust Workload Generator"] --> TS_UI
        JAVA_AGENT1["OTel Java Agent (Bytecode)"] -.-> TS_UI
        TS_UI -->|Internal OTLP| EDGE_OTEL1["OTel Edge Collector<br/>(Drop Health Probes / Filter Noise)"]
    end

    subgraph SpokeAzure["Spoke 2 — azure-k3d (Data Simulation)"]
        TS_DATA["TeaStore Persistence (Hibernate JPA)"]
        MYSQL[("TeaStore DB (teastore-db:1.4.1)")]
        TS_DATA --> MYSQL
        JAVA_AGENT2["OTel Java Agent (Bytecode)"] -.-> TS_DATA
        TS_DATA -->|Internal OTLP| EDGE_OTEL2["OTel Edge Collector<br/>(MySQL Receiver + App Traces)"]
    end

    subgraph WANBridge["Simulated WAN Bridge (172.28.0.0/16)"]
        NETEM["tc netem: RTT 10ms ± 2ms, Loss 0.1%<br/>Native mTLS 1.3 (gRPC :4317)"]
    end

    EDGE_OTEL1 ==>|mTLS 1.3 WAN| NETEM
    EDGE_OTEL2 ==>|mTLS 1.3 WAN| NETEM

    subgraph CentralHub["Central Hub — hub-k3d (Observability & Control)"]
        NETEM ==>|mTLS 1.3| HUB_GW["Hub OTel Gateway (:4317)<br/>• OTTL Normalization<br/>• Tail Sampling (100% Error, Latency>1500ms)<br/>• Service Graph Topology Aggregation"]

        HUB_GW -->|Metrics| THANOS_RCV["Thanos Receive (:19291)"]
        HUB_GW -->|Logs| LOKI["Grafana Loki (:3100)"]
        HUB_GW -->|Traces| TEMPO["Grafana Tempo (:4317)"]

        THANOS_RCV -->|Cold TSDB Blocks| MINIO[("MinIO S3 Object Storage")]
        LOKI -->|Cold Chunks| MINIO
        TEMPO -->|Cold Trace Blocks| MINIO

        THANOS_QUERY["Thanos Query (:9090)"] --> THANOS_RCV
        THANOS_RULER["Thanos Ruler"] --> THANOS_QUERY
        PYRRA["Pyrra SLO-as-Code"] --> THANOS_QUERY

        GRAFANA["Grafana (:3000)<br/>SRE Dashboards"] --> THANOS_QUERY
        GRAFANA --> LOKI
        GRAFANA --> TEMPO

        ALERTMGR["Alertmanager (:9093)"] --> ROBUSTA["Robusta Runner (:5000)<br/>4W Enrichment (Logs, Events, Graph)"]
        THANOS_RULER --> ALERTMGR
        ROBUSTA --> TELEGRAM["Telegram Alert Sink"]
    end

    subgraph AIOpsEcosystem["AI Anomaly Detection Engine V3"]
        AI_ENGINE["AI Anomaly Detection Engine V3<br/>• PromQL Features (15s poller)<br/>• GRU + TCN + Isolation Forest<br/>• Tempo Trace RCA (T_WAN, T_self, T_DB)"]
        AI_ENGINE <-->|PromQL Query| THANOS_QUERY
        AI_ENGINE <-->|Trace RCA| TEMPO
        AI_ENGINE -->|Metrics Exporter :9108| THANOS_RCV
        AI_ENGINE -->|Direct Alerts (Cooldown 60s)| TELEGRAM
    end
```

---

## 4. Security & Operational Principles

1. **Native mTLS 1.3 Across Cluster Boundaries ([ADR-0003](decisions/ADR-0003-why-mtls-zero-trust-pki.md)):** OTLP traffic over the simulated WAN is encrypted with mutual x509 certificates without L7 reverse proxies, saving 150–300 MB RAM on the Hub.
2. **Centralized Secret Management ([ADR-0003](decisions/ADR-0003-why-mtls-zero-trust-pki.md)):** Secrets are managed outside Git via `.env` and `kustomize secretGenerator`, with least-privilege S3 credentials.
3. **Single Responsibility Principle (SRP) Manifests ([ADR-0005](decisions/ADR-0005-why-folder-over-branch-and-kustomize.md)):** One Kubernetes resource per file, prefixed by load order (`00-namespace.yaml` through `05-service.yaml`).
4. **Strict Version Pinning ([ADR-0002](decisions/ADR-0002-why-kyverno.md)):** Floating tags (`latest`, `master`) are forbidden; all versions are pinned in `infra/README.md`.
5. **Edge Noise Filtering & Central Tail Sampling ([ADR-0007](decisions/ADR-0007-why-opentelemetry-and-hub-spoke-pipeline.md)):** Spoke collectors drop health probes (`/healthz`, `/readyz`) before WAN egress; Hub Gateway retains 100% of error and high-latency (>1500ms) traces.

---

## 5. Workstation Resource Budget (8–10 GB RAM)

| Cluster / Component | Key Processes | Estimated RAM |
| :--- | :--- | :---: |
| **`hub-k3d`** | K3s control plane, OTel Gateway, Thanos, Loki, Tempo, MinIO, Grafana, Pyrra, Alertmanager, Robusta | **~4.2 – 5.2 GB** |
| **`aws-k3d`** | K3s control plane, TeaStore 5 compute services + Java Agent, Spoke OTel Collector | **~2.2 – 2.8 GB** |
| **`azure-k3d`** | K3s control plane, TeaStore Persistence + Java Agent, TeaStore DB (`teastore-db:1.4.1`), Spoke OTel Collector | **~1.3 – 1.7 GB** |
| **Host Components** | Locust load generator, AI Anomaly Engine V3 | **~0.8 – 1.2 GB** |
| **TOTAL** | **Full Multi-Cloud Observability & Closed-Loop AIOps Platform** | **~8.5 – 9.8 GB** |
