# ADR-0011: Why Controlled Chaos Fault Injection

## Status
Accepted

## Context
Testing the observability platform only under steady-state conditions cannot validate SLO burn-rate alerting, MTTD/MTTR, or AIOps root-cause localization. We need controlled, repeatable fault injection across network, application, data, and infrastructure layers without exceeding workstation RAM or leaving clusters in a broken state.

## Decision
We implement a **Multi-Tier Chaos Fault Injection Matrix** executed through a 5-step scientific loop (steady-state baseline -> hypothesis -> timed fault injection -> SRE/AIOps evaluation -> automated rollback):
- **CHAOS-01 (Network):** Linux `tc netem` on `eth0` between Hub and Spokes (200–500ms latency, 5–10% packet loss).
- **CHAOS-02 (Application):** Pod deletion / `SIGKILL` on `teastore-webui` or `teastore-auth` in `aws-k3d`.
- **CHAOS-03 (Data):** MySQL `SLEEP()` and lock contention queries on `teastore-db` in `azure-k3d`.
- **CHAOS-04 (Infrastructure):** `stress-ng` or cgroup limits for CPU saturation and `OOMKilled` memory exhaustion.

## Alternatives Considered
- **Chaos Mesh / LitmusChaos:** Provides Kubernetes CRDs but consumes 400–600 MB RAM per cluster for controllers/daemonsets, exceeding local workstation budgets.
- **Ad-hoc manual fault injection:** Non-reproducible and unsuitable for quantitative MTTD/MTTR and AIOps evaluation.
- **Simulated software mocks:** Fails to capture real Linux kernel network latency and container protocol behavior.

## Consequences
- **Positive:** Validates the full observability pipeline (OTel -> Thanos -> Pyrra -> Robusta -> Telegram -> AIOps); generates labeled anomaly datasets; includes fast automated recovery (`make reset-wan`).
- **Trade-offs:** `tc netem` requires privileged Docker/container access; database fault tests can leave inconsistent MySQL state requiring re-seeding.
