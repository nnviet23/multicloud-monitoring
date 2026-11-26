# ADR-0012: Why Multi-Cloud Telemetry FinOps Governance

## Status
Accepted

## Context
In multi-cloud architectures, inter-cloud WAN data egress costs \$0.08–\$0.12/GB, and raw SSD storage costs 5–8x more than object storage. Without explicit cost controls, shipping 100% of raw traces, health-check noise, and uncompressed OTLP payloads across clusters causes telemetry infrastructure costs to scale unsustainably.

## Decision
We enforce **Multi-Cloud Telemetry FinOps** using four technical cost-reduction levers (with real-time $C_{\text{egress}}$ FinOps exporter/OpenCost planned for Phase 5 real-cloud):
1. **Edge noise elimination (`filter/drop_noise`):** Drops 100% of Kubernetes health probes (`/health`, `/ready`, `/actuator/health`) at Spoke collectors, eliminating 60–80% of raw spans/logs before WAN egress.
2. **Error-preserving edge sampling (`tail_sampling`):** Forwards 20% of normal traces while preserving 100% of `ERROR` and `>1500ms` traces.
3. **OTLP gRPC compression:** Enables `gzip` compression on OTLP exporters, reducing WAN payload size by 70–85%.
4. **Tiered storage & downsampling:** Offloads metrics, logs, and traces to MinIO S3 (~70% cheaper than SSD) and downsamples historical metrics via Thanos Compactor (5m after 40h, 1h after 10d).

## Alternatives Considered
- **Unfiltered 100% raw ingestion:** Simple initially, but causes exponential WAN egress and storage cost growth.
- **Metrics-only (drop all traces):** Minimizes cost but eliminates distributed trace RCA.
- **Cross-cluster Kafka buffer:** Improves buffering durability but roughly doubles infrastructure cost compared to direct OTLP mTLS.

## Consequences
- **Positive:** Reduces estimated telemetry WAN and storage costs by 75–85% while preserving 100% of error and high-latency diagnostic traces.
- **Trade-offs:** Compression/decompression adds minor CPU overhead on Spokes and Hub; downsampled metrics (>40h) lose sub-minute spike granularity.
