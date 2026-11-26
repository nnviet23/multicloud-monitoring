# ADR-0009: Why MinIO for S3-Compatible Object Storage

## Status
Accepted

## Context
Thanos, Grafana Loki, and Grafana Tempo all require an S3-compatible object storage backend to offload historical metrics blocks, log chunks, and trace blocks, as well as to store immutable raw telemetry for reproducible benchmark experiments. Relying on local Persistent Volumes (SSD/NVMe) costs 5–10x more than object storage and cannot be shared cleanly across tiered storage components in a local `k3d` lab.

## Decision
We deploy **MinIO** on `hub-k3d` as the central S3-compatible object storage tier with dedicated buckets:
- `thanos-metrics`: Historical Prometheus/Thanos TSDB blocks.
- `loki-data`: Grafana Loki log chunks.
- `tempo-traces`: Grafana Tempo trace blocks.
- `raw-telemetry`: Immutable raw telemetry datasets for benchmark reproducibility.

## Alternatives Considered
- **Local Kubernetes Persistent Volumes (SSD/hostPath):** Expensive at scale and incompatible with Thanos/Loki/Tempo's object-storage-native compaction and stateless query architecture.
- **Real cloud object storage (AWS S3 / Azure Blob) during local lab:** Introduces external network dependency, cloud credentials, and egress costs during local development.

## Consequences
- **Positive:** Provides a single, S3-compatible backend shared by Thanos, Loki, and Tempo; enables reproducible local experiments without cloud lock-in or external egress fees.
- **Trade-offs:** Adds another stateful component to `hub-k3d` that requires bucket initialization and local disk capacity management.
