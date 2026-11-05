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

### Phase 4 — Benchmark and evaluation
- [ ] Define workload profile, repetitions, warm-up, cooldown, and noise controls.
- [ ] Capture immutable raw data and run manifests.
- [ ] Compare no-sampling and sampling profiles.
- [ ] Evaluate coverage, accuracy, latency (including encryption overhead), scalability, and cost.
- [ ] Publish analysis scripts, plots, and limitations.

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
- [x] GitOps & delivery: Kustomize for local lab declarative overlays; ArgoCD ready for multi-cluster sync.

## Next action
Inspect the repository and existing diagrams/configs. Produce a gap analysis before changing deployment files.
