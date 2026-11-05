# Repository Agent Guide

## Mission
Build and evaluate a reproducible multi-cloud observability platform using TeaStore, OpenTelemetry, three local k3d clusters, and an extensible Hub-Spoke design.

## Read selectively
- Start with `PLAN.md` for current phase and decisions.
- Load the relevant Skill in `.agents/skills/` for the task.
- Read detailed architecture, schemas, and research notes only when the task needs them.

## Fixed project context
- `aws-k3d`: Spoke 1, AWS-like label; TeaStore compute services and Locust load generator.
- `azure-k3d`: Spoke 2, Azure-like label; TeaStore persistence/data services and MySQL.
- `hub-k3d`: central hub receiving telemetry from both spokes.
- Local provider names are simulation labels, not real cloud deployments.
- Architecture baseline: **Phương án A** (Edge-Filtered Ingestion with Centralized Processing & Batch Ingestion). Initial trace sampling rate is **20%** at edge collectors (with 100% preservation of error traces and high latency); AI streaming inference is deferred to a subsequent phase.
- Stack: Docker, Kubernetes/k3d, OpenTelemetry, Prometheus + Thanos, Loki, Tempo, Grafana, Pyrra (SLO-as-code), Robusta (smart alerting) + Telegram; Locust for load testing; Ansible for local lab; Terraform for later real-cloud deployment.
- TeaStore is the benchmark application; Locust (`locustfile.py`) is the official workload generator.
- Collector processor order: Memory Limiter → Filter → Transform → Batch → Exporter.
- Service Graph Topology: Pre-aggregated at Hub OTel Gateway via `servicegraphconnector` producing `traces_service_graph_request_total` directly into Thanos Receive.
- Protect Spoke-to-Hub OTLP with mutual TLS (mTLS 1.3) when traversing the simulated WAN.
- Strict Version Pinning: Every container image and tool version is pinned in `infra/README.md`. Never use `latest` or floating tags.
- Manifest hygiene: Kustomize Base (`k8s/base/`) vs Overlays (`k8s/overlays/`). Each manifest adheres to the Single Responsibility Principle (SRP).

## Engineering contract
1. Inspect the repository before proposing edits. Preserve existing conventions and avoid duplicate infrastructure.
2. State assumptions. Distinguish verified facts, project decisions, hypotheses, and recommendations.
3. Prefer small, reviewable changes. Do not rewrite unrelated files.
4. Never invent benchmark results, measurements, citations, cloud prices, or support claims.
5. Keep raw telemetry immutable. Derived datasets must record source run IDs and transformation steps.
6. Every experiment must be reproducible from a manifest, workload parameters, software/config versions, and raw outputs.
7. Preserve source timestamps and record observed/received/normalized timestamps separately.
8. Record missing, unsupported, dropped, sampled, and filtered data explicitly.
9. Do not commit credentials, private keys, kubeconfigs, tokens, or unredacted sensitive logs.
10. Before destructive commands, cluster resets, Terraform apply/destroy, or broad file deletion: explain impact and ask for approval.
11. Enforce Single Responsibility Principle (SRP) for Kubernetes manifests: One resource per file, prefixed by deployment order (`00-namespace.yaml`, `01-secret.yaml`, `02-configmap.yaml`, `03-pvc.yaml`, `04-statefulset.yaml`, `05-service.yaml`).
12. Never use `latest` or floating image tags. All image references must use pinned versions from `infra/README.md`.
13. Central Hub must normalize all heterogeneous cloud/cluster attributes to canonical OpenTelemetry Semantic Conventions via OTTL before exporting to backends.

## Change workflow
- Inspect → plan → implement → validate → summarize.
- Before implementation, list target files and expected behavior.
- Run only relevant validation. Report commands actually run and their exit status.
- If validation cannot run, state why and provide exact follow-up commands.
- Update `PLAN.md` or a decision record when an architectural decision changes.

## Naming
- Kubernetes resources: lowercase kebab-case.
- Cluster IDs: `aws-k3d`, `azure-k3d`, `hub-k3d`.
- Experiment IDs: `YYYYMMDD_<workload>_<scenario>_<runNN>`.
- Config snapshots: `config_<component>_<version-or-commit>_<YYYYMMDD>.yaml`.
- Reports: `report_<topic>_<YYYYMMDD>.md`.
- Decision records: `docs/decisions/ADR-NNN-<short-title>.md`.

## Output style
Use Vietnamese for explanations unless the user asks for English. Keep technical identifiers and standard terms in English; on first use in reports, explain important English terms in Vietnamese parentheses.
