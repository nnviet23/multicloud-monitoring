# ADR-0006: Why Pyrra and Robusta for SLOs and Smart Alerting

## Status
Accepted

## Context
Static threshold alerts (e.g., `CPU > 80%`) cause severe alert fatigue during brief traffic spikes while missing slow error-budget burns (e.g., a 1% error rate over 12 hours). Moreover, raw Alertmanager notifications lack pod logs and Kubernetes events, forcing engineers to manually run `kubectl` commands and lengthening MTTR.

## Decision
We adopt **Pyrra** for declarative Google SRE SLO-as-Code and **Robusta** for automated alert enrichment:
- **Pyrra (`--config-maps-only` + `pyrra-api`):** Generates multi-window, multi-burn-rate Prometheus/Thanos recording and alerting rules from declarative SLO definitions without requiring heavy CRD operators.
- **Robusta Runner + Telegram (60s Cooldown):** Enriches Alertmanager webhooks with the last 50 container log lines and Kubernetes events (`OOMKilled`, `CrashLoopBackOff`) before routing to Telegram with a 60s cooldown buffer and grouping by `k8s.cluster.name` and `service.name`. (Spoke Robusta Forwarders are deferred to Phase 5 to save local RAM.)
- **Modular Alert Rules:** Domain-driven rule files under `deploy/platform/metrics-thanos/rules/` (`01-host-rules.yaml` through `08-opentelemetry-collector-rules.yaml`), deduplicated against Pyrra SLO alerts.

## Alternatives Considered
- **Hand-written Multi-Burn-Rate PromQL:** Error-prone and inconsistent across services.
- **Sloth:** A strong SLO generator, but Pyrra provides native Thanos Query compatibility, a built-in SLO UI, and direct Grafana integration.
- **Plain Alertmanager without Robusta:** Lacks automated log/event enrichment, increasing manual triage time.
- **Commercial SaaS (Datadog / PagerDuty):** Prohibitive licensing cost and vendor lock-in for an open-source research platform.

## Consequences
- **Positive:** Alerts focus on user-facing error-budget burn; enriched Telegram notifications cut MTTR; burn-rate + 60s cooldown reduces alert noise by up to 85%.
- **Negative:** Requires team familiarity with SLI/SLO/burn-rate concepts; Robusta Runner consumes ~150–200 MB RAM on `hub-k3d`.
