# Architecture Decision Records (ADR) — Multi-Cloud Observability & AIOps

This directory contains the **13 Canonical Architecture Decision Records (ADRs)** for the **Multi-Cloud Observability & AIOps** platform using the **SPEC RG TeaStore** benchmark across three Kubernetes clusters (`hub-k3d`, `aws-k3d`, `azure-k3d`).

All normative PromQL formulas, retention periods, WAN emulation parameters, and Zero-Trust security configurations are embedded directly into their corresponding ADRs to ensure full traceability.

---

## 1. Index of 13 Canonical ADRs

| ADR ID | Title | Domain |
| :--- | :--- | :--- |
| [ADR-0001](./ADR-0001-why-multi-cluster-hub-spoke.md) | Why Multi-Cluster Hub-Spoke Topology & WAN Emulation | Infrastructure & Network |
| [ADR-0002](./ADR-0002-why-kyverno.md) | Why Kyverno for Policy-as-Code & Supply Chain Security | DevSecOps & Compliance |
| [ADR-0003](./ADR-0003-why-mtls-zero-trust-pki.md) | Why Native mTLS 1.3 & Zero-Trust PKI | Security & Zero-Trust |
| [ADR-0004](./ADR-0004-why-argocd-and-applicationsets.md) | Why Argo CD & ApplicationSets for Multi-Cluster GitOps | GitOps & Delivery |
| [ADR-0005](./ADR-0005-why-folder-over-branch-and-kustomize.md) | Why Folder-Over-Branch GitOps Layout & Kustomize | Repository & Manifest Hygiene |
| [ADR-0006](./ADR-0006-why-pyrra-and-robusta.md) | Why Pyrra for SLO-as-Code & Robusta for Smart Alerting | SRE & Smart Alerting |
| [ADR-0007](./ADR-0007-why-opentelemetry-and-hub-spoke-pipeline.md) | Why OpenTelemetry & Hub-Spoke Collector Pipeline | Telemetry & Processing |
| [ADR-0008](./ADR-0008-why-thanos-loki-tempo.md) | Why Thanos, Loki, and Tempo for Observability Storage | Storage & Query Federation |
| [ADR-0009](./ADR-0009-why-minio-object-storage.md) | Why MinIO for Tiered S3 Object Storage | Storage & Persistence |
| [ADR-0010](./ADR-0010-why-teastore-and-locust.md) | Why TeaStore & Locust for Multi-Cloud Benchmarking | Benchmark & Workloads |
| [ADR-0011](./ADR-0011-why-chaos-fault-injection.md) | Why Chaos Fault Injection & Quantitative Validation | Chaos & Reliability |
| [ADR-0012](./ADR-0012-why-telemetry-finops.md) | Why Telemetry FinOps & WAN Egress Optimization | FinOps & Economics |
| [ADR-0013](./ADR-0013-why-ai-anomaly-detection-and-rca.md) | Why Closed-Loop AI Anomaly Detection & Trace RCA | AIOps & Intelligence |

---

## 2. Traceability Matrix

| Canonical ADR | Key Quantitative & Normative Parameters |
| :--- | :--- |
| **ADR-0001** (Hub-Spoke Topology & WAN) | Docker subnet `172.28.0.0/16`, static k3d node IPs (`172.28.0.2`–`4`), CoreDNS NodeHosts (`hub.local`, `aws.local`, `azure.local`), `tc netem` (10ms delay, 2ms jitter, 0.1% loss), 8–10 GB RAM budget. |
| **ADR-0002** (Kyverno Policy-as-Code) | Kyverno ClusterPolicies (`deploy/policies/`), Enforce/Fail-Closed mode, Shift-Left `kyverno test`, disallow `:latest`, require `readOnlyRootFilesystem: true`, drop `ALL` capabilities, Sigstore Cosign & SLSA Build L2. |
| **ADR-0003** (Zero-Trust PKI & mTLS 1.3) | cert-manager PKI (Root CA, Intermediate CA, SANs `*.hub.local`), native mTLS 1.3 in OTel Collector (`TLS_AES_256_GCM_SHA384`, `TLS_CHACHA20_POLY1305_SHA256`), 90-day cert lifetime, Bitnami Sealed Secrets. |
| **ADR-0004** (Argo CD & ApplicationSets) | Argo CD on `hub-k3d`, ApplicationSets (List/Matrix Generators), Sync Waves (0–3), Argo Rollouts with AnalysisTemplate (P99 < 500ms, 5xx < 1%, auto-rollback). |
| **ADR-0005** (Folder-Over-Branch & Kustomize) | Single-branch `main` Folder-Over-Branch GitOps layout (`deploy/platform/`, `workloads/`, `deploy/policies/`, `deploy/argocd/`, `deploy/clusters/`), SRP manifests (`00-`–`07-`), separated `release-images` pointers. |
| **ADR-0006** (Pyrra & Robusta) | Pyrra `ServiceLevelObjective` CRDs, Google SRE Multi-Window Multi-Burn-Rate alerting (1h/5%, 6h/10%, 3d/2%), Robusta Runner 4W enrichment, Telegram sink with 60s cooldown buffer. |
| **ADR-0007** (OpenTelemetry Hub-Spoke Pipeline) | OTel Operator & Javaagent bytecode, standard pipeline (`memory_limiter` → `filter` → `transform` → `batch` → `exporter`), `filter/drop_noise`, 20% head sampling at edge, central tail sampling (100% errors & >1500ms), OTTL normalization, `traces_service_graph_request_total`. |
| **ADR-0008** (Thanos, Loki, Tempo) | TSDB 2h hot storage, Thanos Compactor downsampling (5m after 40h, 1h after 10d), retention (raw 30d, 5m 90d, 1h 365d), Loki 7d, Tempo 7d, Grafana Sidecar. |
| **ADR-0009** (MinIO Object Storage) | MinIO S3 buckets (`thanos-metrics`, `loki-data`, `tempo-traces`, `raw-telemetry`), cold object storage tiering. |
| **ADR-0010** (TeaStore & Locust) | TeaStore split: compute (`webui`, `auth`, `recommender`, `image`, `registry`) on `aws-k3d`, persistence (`persistence`, `teastore-db`) on `azure-k3d`, headless Locust (`locustfile.py`). |
| **ADR-0011** (Chaos Fault Injection) | 4-scenario chaos matrix (CHAOS-01: WAN impairment via `tc netem`, CHAOS-02: pod/service crash, CHAOS-03: DB lock & MySQL latency, CHAOS-04: CPU/Memory saturation), MTTD/MTTR & burn-rate validation. |
| **ADR-0012** (Telemetry FinOps) | Multi-cloud WAN egress cost model ($0.08–$0.12/GB), edge noise filtering ROI, S3 vs SSD tiered storage savings (~70%), OTLP gRPC compression. |
| **ADR-0013** (AI Anomaly Detection & Trace RCA) | Deep Ensemble (GRU Autoencoder + TCN + Isolation Forest), PromQL feature extraction, distributed trace RCA ($T_{\text{total}} = T_{\text{WAN}} + T_{\text{self}} + T_{\text{DB}}$), `:9108` exporter, Grafana Panel 7 Dual Y-Axis, Telegram 60s cooldown. |

---

## 3. ADR Evolution Rules

1. Any change to technical architecture, platform components, or SLO/FinOps/AIOps parameters must be reflected in the corresponding canonical ADR.
2. ADR lifecycle states: `Proposed` → `In-Progress` → `Implemented` → `Verified` → `Superseded`.
3. Every Kubernetes manifest under `deploy/` or infrastructure script under `infra/` must trace back to these ADRs.
