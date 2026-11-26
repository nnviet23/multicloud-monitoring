# ADR-0004: Why Argo CD, ApplicationSets, and App-of-Apps

## Status
Accepted

## Context
Managing three Kubernetes clusters (`hub-k3d`, `aws-k3d`, `azure-k3d`) with dozens of platform and workload manifests requires a centralized, declarative GitOps engine. Hand-maintaining an `Application` manifest for every service-cluster pair does not scale and invites copy-paste drift, while `kubectl apply` scripts lack continuous reconciliation and drift detection.

## Decision
We standardize on **Argo CD (`v2.12.3`)** deployed centrally on `hub-k3d` as the single GitOps control plane:
- **App-of-Apps + ApplicationSets:** A single root `Application` bootstraps the platform, while **ApplicationSets** (List/Matrix generators) automatically generate per-cluster `Application` objects targeting `deploy/clusters/{{name}}` with **Sync Waves** (0: Namespaces/CRDs, 1: ConfigMaps/Secrets/Storage, 2: Operators, 3: Workloads).
- **Progressive Delivery (Phase 5):** Standard `Deployment` resources are used in local `k3d` to conserve RAM; in real-cloud Phase 5, **Argo Rollouts** will provide metric-driven canary rollbacks against Thanos/Prometheus.

## Alternatives Considered
- **Flux v2:** Lightweight and Kubernetes-native, but its decentralized per-cluster controller model lacks Argo CD's centralized Hub-Spoke UI/CLI ("single pane of glass") and ApplicationSet ergonomics.
- **Push-based CI (`kubectl apply` in GitHub Actions/Jenkins):** Exposes cluster API endpoints to external CI runners and provides no continuous drift self-healing.
- **Hand-written `Application` manifests:** Simple for 1–2 apps, but creates excessive YAML duplication across multiple clusters.

## Consequences
- **Positive:** Single pane of glass for multi-cluster sync/health; saves ~500 MB RAM per spoke by running Argo CD only on `hub-k3d`; adding a service or cluster requires minimal, reviewable Git changes.
- **Negative:** Hub-to-spoke WAN outages pause new syncs (though running spoke workloads remain unaffected); ApplicationSet generator changes have a wide blast radius and require careful review.
