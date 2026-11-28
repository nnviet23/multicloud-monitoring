# Platform exception record

- Requestor and consumer: Platform Engineering Team (consuming `hub-k3d` observability stack)
- Platform capability/policy: High-availability (HA) deployment policy (`replicas >= 2`) and full GitOps Alerting provisioning for production-grade observability components
- Requested deviation:
  1. **Grafana `replicas: 1`**: Run Grafana on `hub-k3d` with a single replica (`replicas: 1`) instead of HA (`replicas >= 2`).
  2. **Alerting provisioning deferred**: Defer full automated Grafana/Alertmanager notification-policy provisioning in GitOps, relying on Robusta + AI Engine Telegram Alert Sink (:9108) for lab alerting.
- Resources and environments in scope: `deploy/platform/hub/grafana/` and `deploy/platform/hub/` alerting manifests in local `hub-k3d` lab environment.
- Reason and duration: Local k3d lab runs on a single-host Docker environment with constrained CPU/RAM; HA Grafana requires shared external DB (PostgreSQL/MySQL) for session/dashboard state. Duration: valid for the local k3d research prototype phase (until real-cloud deployment).
- Risk/blast-radius assessment: Low blast radius — affects only local lab UI availability during Grafana pod restarts and delays full Alertmanager GitOps routing; telemetry ingestion (OTel Gateway, Thanos, Loki, Tempo) and AI Engine alerting remain unaffected.
- Compensating controls:
  - Dashboards are stored as code in Git (`deploy/platform/hub/grafana/`) and re-provisioned automatically on pod restart.
  - Active alerting is covered by Robusta and AI Anomaly Engine Telegram Alert Sink with a 60s cooldown buffer.
- Evidence or test results: Verified in `hub-k3d` lab that Grafana recovers dashboard state from GitOps ConfigMaps on pod restart and Telegram alerts fire from AI Engine (:9108).
- Accountable owner: Platform Engineering Team
- Required approver(s): SRE / Platform Lead
- Decision: approved
- Narrow scope applied: Applies strictly to local `hub-k3d` lab environment; prohibited in real-cloud production overlays.
- Decision record or policy version: `AGENTS.md` (Project Baseline) & `docs/architecture/observability-contract.md` (`OBC-TEASTORE-AI-V1`)
- Expiry and review date: 2027-02-28 (or upon transition to real-cloud Terraform deployment)
- Closure, renewal, or product backlog follow-up: Track HA Grafana (with external DB) and full Alertmanager GitOps provisioning in `docs/planning/roadmap-board.md` for the real-cloud phase.
