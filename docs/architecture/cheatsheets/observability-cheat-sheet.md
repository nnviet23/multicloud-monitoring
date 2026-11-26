# Cheat Sheet — Observability

> Three pillars - metrics, logs, traces - answer "is it broken, why, and where".
> Instrument with OpenTelemetry and alert on symptoms (SLOs), not causes.

## Three pillars

| Pillar | Answers | Tools |
|--------|---------|-------|
| Metrics | Is it healthy? (cheap, aggregate) | Prometheus, Mimir |
| Logs | What happened? (events, detail) | Loki, ELK |
| Traces | Where is the latency? (per-request) | Tempo, Jaeger |

## Monitoring methods

- **RED (services):** Rate, Errors, Duration - request-centric.
- **USE (resources):** Utilization, Saturation, Errors - resource-centric.
- **Four golden signals (SRE):** Latency, Traffic, Errors, Saturation.

## PromQL quick reference

```promql
# Request rate per second over 5m, by route
sum(rate(http_requests_total[5m])) by (route)

# Error ratio (5xx share of traffic)
sum(rate(http_requests_total{status=~"5.."}[5m]))
  / sum(rate(http_requests_total[5m]))

# p95 latency from a histogram
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket[5m])) by (le))

# Memory working set by pod
sum(container_memory_working_set_bytes) by (pod)

# Predict a disk filling within 4 hours
predict_linear(node_filesystem_avail_bytes[1h], 4 * 3600) < 0
```

- Matchers: `=`, `!=`, `=~`, `!~`. A range like `[5m]` makes a range vector for
  `rate()`. Use `rate()` on counters and `histogram_quantile()` on buckets.

## LogQL quick reference

```logql
# Stream selector + line filters
{app="web", namespace="prod"} |= "error" != "healthz"

# Parse JSON then filter by a field
{app="web"} | json | status >= 500

# Parse logfmt then filter by a label
{app="web"} | logfmt | duration > 500ms

# Metric query: error lines per second by pod
sum(rate({app="web"} |= "error" [5m])) by (pod)
```

- `|=` contains, `!=` excludes, `|~` regex, `!~` not-regex. Parsers: `json`,
  `logfmt`, `pattern`, `regexp`.

## SLO & error budget

- **SLI** is the measurement (for example good requests / total requests).
- **SLO** is the target over a window (for example 99.9% over 30 days).
- **Error budget** is `100% - SLO` (0.1% is about 43 minutes per 30 days).

```promql
# 30-day availability SLI
sum(rate(http_requests_total{status!~"5.."}[30d]))
  / sum(rate(http_requests_total[30d]))
```

### Burn-rate alerting

| Burn rate | Budget spent | Response |
|-----------|--------------|----------|
| 1x | At the exact budget pace | On track |
| 6x | 5% in 6h | Ticket (slow burn) |
| 14.4x | 2% in 1h | Page now (fast burn) |

```promql
# Fast burn: 1h error ratio above 14.4x the budget (for a 99.9% SLO)
(sum(rate(http_requests_total{status=~"5.."}[1h]))
  / sum(rate(http_requests_total[1h]))) > 14.4 * 0.001
```

- Combine fast and slow windows (multi-window, multi-burn-rate) to cut false pages.

## OpenTelemetry collector roles

- **Receivers** - ingest data (OTLP, Prometheus, Jaeger).
- **Processors** - batch, filter, tail-sample, add resource attributes.
- **Exporters** - send to Prometheus/Tempo/Loki or a vendor.
- **Deployment:** an **agent** (DaemonSet, per-node collection) feeds a **gateway**
  (central batching, sampling, and export).

## Traces & recording rules

- **Trace = a tree of spans** across services; propagate context via the W3C
  `traceparent` header so spans join a single trace.
- **Sampling:** head (decide at the start, cheap) vs tail (decide after seeing the
  whole trace, keeps errors and slow traces). Tail-sample in the collector gateway.
- **Recording rules** precompute expensive PromQL; **alerting rules** fire on
  conditions. Keep SLO burn-rate alerts as alerting rules.

```yaml
groups:
  - name: slo
    rules:
      - record: job:http_error_ratio:5m
        expr: |
          sum(rate(http_requests_total{status=~"5.."}[5m]))
            / sum(rate(http_requests_total[5m]))
```

## See also

- [`../11-observability-engineering/`](../11-observability-engineering/) -
  OpenTelemetry, Prometheus, Loki, Tempo, Grafana, and SLOs.
- [`../17-platform-sre/`](../17-platform-sre/) - platform SLOs and incident response.
