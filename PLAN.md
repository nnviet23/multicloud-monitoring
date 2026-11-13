# Project Plan — Multicloud Monitoring

> Update this file when the phase, acceptance criteria, or architecture decisions change. Do not treat unchecked items as completed.

## Current phase
**Phase 4 — Benchmark and evaluation (Ready)**

## Research questions
- [ ] What prior Hub-Spoke / centralized multi-cloud observability systems are closest to this design?
- [ ] What is the project's differentiator, and what evidence would demonstrate it?
- [ ] Which application and cloud dependencies can be discovered and observed?
- [ ] How will source timestamps be normalized across regions while preserving original values?
- [ ] Which fields are unavailable from each provider/source, and how are gaps reported?
- [ ] How are service state, instance state, and storage capacity represented?
- [ ] How will coverage, accuracy, end-to-end latency, post-encryption latency, scalability, and cost be evaluated?

## Phases and exit criteria

### Phase 0 — Baseline
- [x] Inspect repository and document existing components.
- [x] Create architecture diagram and component inventory (`docs/architecture/00_TechStack.md`).
- [x] Define telemetry schema and data dictionary (`docs/architecture/01_SystemArchitecturePlan.md`).
- [x] Create architecture plan resolving architectural choices (Phương án A, 20% trace sampling).

### Phase 1 — Local infrastructure
- [x] Use Ansible to provision three k3d clusters: `aws-k3d`, `azure-k3d`, `hub-k3d`.
- [x] Restore Spoke 3 `gcp-k3d` (Recommender) and AWS `nginx-api-gateway` on the Kustomize layout; verified on the live lab 2026-11-12.
- [x] Connect clusters through a documented Docker network / simulated WAN (`mc-monitoring-net`: `172.28.0.0/16`).
- [x] Add controlled latency and packet loss only through a reproducible profile (`tc/netem`: delay 10ms 2ms, loss 0.1%).
- [x] Verify cluster reachability, DNS, time synchronization assumptions, and resource limits (`05_verify_clusters.yml`).

### Phase 2 — Workload and telemetry
- [x] Deploy TeaStore compute services in Spoke 1.
- [x] Deploy TeaStore persistence/data services and MySQL in Spoke 2.
- [x] Deploy OTel collectors and verify receiver/exporter coverage.
- [x] Enforce processor order: Memory Limiter → Filter → Transform → Batch.
- [x] Configure OTLP transport with mTLS between spokes and hub.
- [x] Verify metrics, logs, traces and service dependency correlation.

### Phase 3 — Hub and storage
- [x] Deploy Hub Processor / enrichment.
- [x] Deploy Prometheus + Thanos, Loki, Tempo, Grafana, and MinIO if required by the selected architecture.
- [x] Document retention, object-store buckets, query paths, and failure behavior.
- [x] Configure Telegram alerts with secrets external to Git (Robusta runner deployed with templated Telegram secret).

### Phase 3.5 — Full-Stack Hostmetrics & SRE Dashboards Upgrade
- [x] Enable all 7 hostmetrics scrapers (cpu, load, memory, paging, disk, filesystem, network) on Edge and Hub collectors.
- [x] Upgrade all 7 Grafana SRE dashboards (USE method, Dual Y-Axis via byFrameRefID, multi-query table merge transformation).

### Phase 3.6 — Unified Resource Monitoring Schemas
- [x] Publish RESOURCE_MONITORING_SCHEMAS.md with 3-tier acquisition mechanics and cross-layer RCA decision trees.
- [x] Create machine-readable webapp-monitoring-schema.yaml and instance-monitoring-schema.yaml.
- [x] Add Panel 6 (JVM Memory Heap & Thread Count) on red-metrics.json.

### Phase 3.7 — AI Anomaly Detection Engine V3 & Closed-Loop AIOps Pipeline
- [x] Merge and align AI Anomaly Detection Engine V3 (Universal GRU + TCN Autoencoders, Isolation Forest, Online Calibration).
- [x] Align 8 PromQL features with Dual SemConv fallback and Tempo Trace RCA decomposition (T_WAN, T_self, T_DB).
- [x] Establish Closed-Loop AIOps feedback: Embedded Prometheus Exporter (:9108), Panel 7 on Grafana, and Telegram Alert Sink with rate limiting.
- [x] Standardize chaos engineering scripts (run_live.py, run_service_faults.py, FaultAgent.java) for 3-cluster baseline.

### Phase 4 — Benchmark and evaluation (Ready)
- [ ] Implement SigNoz-inspired Edge Pre-filtering (`filter/drop_noise`) to eliminate health probes before WAN traversal.
- [ ] Implement Hub Tail-based sampling (`tail_sampling`) to guarantee 100% error trace and high-latency span preservation.
- [ ] Evaluate TSDB sample reduction via Collection Interval Tiering (10s Golden Signals vs 30s-60s Host OS metrics).
- [ ] Execute Locust workload generator benchmarks across multiple concurrency tiers (Browse, Cart, Checkout).
- [x] Retrain the AI engine on the 4-cluster topology (model v1 on 4 h run02, v2 = v1 at replay-tuned threshold 1.6) and evaluate on real faults: 8 scenarios (3 WAN, CPU, DB lock, JVM memory leak, HTTP 5xx, WebUI outage); see `experiments/reports/report_ai-engine-v2-evaluation_20261113.md`.
- [ ] Reach reliable WAN RCA localisation for GCP (sparse sampled heartbeats) and remove the CPU `rate[1m]` recovery tail; evaluate the remaining synthetic-only scenarios.
- [ ] Measure observability metrics: Coverage, Accuracy, End-to-End Latency, Encryption Overhead, and Bandwidth Savings.
- [ ] Publish scientific benchmark analysis, trade-off matrix, and final graduation thesis report.

### Phase 5 — Real cloud design (after local validation)
- [ ] Select providers and regions based on explicit criteria.
- [ ] Estimate compute, network egress/ingress, storage, control-plane, IAM, and managed-service costs.
- [ ] Use Terraform modules with separate state and environments.
- [ ] Compare hub placement on a primary provider versus a third provider.
- [ ] Do not deploy or incur costs without explicit approval.

## Acceptance criteria (to be made measurable)
| Dimension | Evidence required |
|---|---|
| Coverage | Inventory of expected vs observed entities/attributes, by source and provider |
| Accuracy | Comparison with ground truth or source-of-truth API/export |
| Latency | Event/source → collector → hub ingest → query/dashboard; report p50/p95/p99 |
| Encryption overhead | Matched runs with equivalent load/config, TLS/mTLS on vs controlled baseline |
| Scalability | Repeatable increase in services, instances, telemetry volume, and/or providers |
| Cost | Explicit assumptions, unit prices, egress, storage, retention, sampling, and sensitivity |
| Reproducibility | Manifest, config snapshots, raw data, scripts, environment and commit identifiers |

## Current open decisions
- [x] Exact TeaStore deployment topology and version: Spoke 1 (Compute: WebUI, Auth, Image Provider, Recommender), Spoke 2 (Persistence & MySQL).
- [x] OTel Collector distribution/version and receiver/exporter compatibility: OTel Collector Contrib (Edge & Hub Gateway).
- [x] Canonical telemetry schema and cardinality budget: Defined in `01_SystemArchitecturePlan.md`.
- [x] Timestamp authority, clock-sync method, and uncertainty handling: 4-tier contract (event, observed, received, normalized UTC).
- [x] Raw-data retention and storage format: MinIO S3 immutable raw partition with run IDs.
- [x] Sampling policy per signal: Phương án A with initial 20% head-based trace sampling.
- [x] WAN impairment profiles: tc/netem with RTT 10ms, jitter 2ms, packet loss 0.1%.
- [x] GitOps & delivery: Kustomize SRP (Base vs Overlays) with GNU Make master orchestration; Ansible for local lab provisioning.

## Next action
AI engine (2026-11-13): model v2 is deployed in `ai-engine/models/saved` (hashes in `model_v2_sha256.txt`).
Open items from the evaluation report: GCP WAN localisation coverage, CPU recovery tail (`rate[1m]`), minimum
request count for client P95, robusta CrashLoop and Makefile CRD ordering. Nothing has been pushed from branch `AI`.
