# ADR-0008: Why Thanos, Loki, and Tempo for Observability Storage

## Status
Accepted

## Context
Aggregating metrics, logs, and traces from `aws-k3d`, `azure-k3d`, and `hub-k3d` on local SSDs is expensive and limits retention. Standalone Prometheus cannot provide a unified multi-cluster view or downsample historical series for fast long-term queries, and we need a tracing backend that integrates cleanly with metrics and logs within a single-workstation RAM budget.

## Decision
We adopt the **Grafana LGTM + Thanos** tiered storage stack on `hub-k3d`:
- **Metrics (Prometheus + Thanos):** Prometheus scrapes the Hub OTel Gateway (`:8889`) with a 2h local TSDB retention; `thanos-sidecar` uploads 2h blocks to object storage, `thanos-store` serves historical blocks, `thanos-compact` (single-replica) downsamples data (raw 30d, 5m after 40h for 90d, 1h after 10d for 365d), and `thanos-query` provides a single deduplicated global query endpoint.
- **Logs (Grafana Loki):** Deployed in single-binary mode receiving OTLP/Push logs with 72h local lab retention and chunks offloaded to object storage.
- **Traces (Grafana Tempo):** Deployed as the distributed tracing backend with 24h local lab retention, indexing by trace ID and enabling Metrics -> Traces -> Logs correlation in Grafana.
- **Dashboards:** Grafana on `hub-k3d` uses `k8s-sidecar` to auto-load dashboards labeled `grafana_dashboard: "1"`.

## Alternatives Considered
- **Local Prometheus TSDB only:** No global multi-cluster query view, no automatic downsampling, and high SSD usage.
- **Cortex / Grafana Mimir:** Requires more microservices and higher memory (~1.5 GB vs ~500 MB for Thanos), exceeding workstation RAM constraints.
- **Jaeger instead of Tempo:** Mature trace-search UI, but relies on heavier tag indexing rather than Tempo's object-storage-first model and native LGTM correlation.
- **Commercial SaaS (Datadog / New Relic):** Licensing and egress costs are outside the self-hosted research scope.

## Consequences
- **Positive:** Unified global observability in Grafana; sub-second long-term metric queries via Thanos downsampling; ~70% storage cost reduction compared to SSD-only retention.
- **Trade-offs:** Operating multiple distributed components (Thanos Query/Store/Compactor, Loki, Tempo) increases configuration complexity; `thanos-compact` must run as a single replica to avoid S3 block conflicts.
