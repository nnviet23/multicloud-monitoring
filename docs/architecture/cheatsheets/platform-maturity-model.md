# Cheat Sheet — Platform Maturity & Operations

> Where a platform sits on the maturity curve, what "production-ready" means, and
> reusable templates for multi-cluster, chaos experiments, and platform pipelines.

## Platform engineering maturity model

| Level | Stage | Provisioning | Time to environment |
|-------|-------|--------------|---------------------|
| 1 | Ad hoc | Manual tickets, tribal knowledge | Days to weeks |
| 2 | Repeatable | Scripts plus some IaC | Hours to days |
| 3 | Standardized | Golden paths, self-service templates | Minutes to hours |
| 4 | Self-service | Full IDP, guardrails, GitOps | Minutes |
| 5 | Optimizing | Data-driven cost and DX feedback loops | Seconds to minutes |

- Progress by **adoption and outcomes** (DORA, DX, cost), not tool count. Measure
  time-to-first-deploy and the share of workloads on golden paths.

## Production readiness checklist

- **Availability:** multi-AZ, HPA, PodDisruptionBudgets, probes, autoscaling tested.
- **Security:** non-root, policies enforced, least-privilege RBAC, images signed,
  secrets externalized, network default-deny.
- **Observability:** RED/USE metrics, logs, traces, dashboards, SLOs plus alerts.
- **Cost:** requests right-sized, labels for attribution, budget and anomaly alerts.
- **Operations:** runbooks, on-call, backups **tested**, DR plan, capacity plan,
  rollback verified.

## Multi-cluster architecture patterns

| Pattern | Shape | Use when |
|---------|-------|----------|
| **Hub-and-spoke** | A central mgmt cluster governs workload clusters | Fleet governance, GitOps control |
| **Management cluster** | A cluster that provisions clusters (Cluster API) | Lifecycle automation at scale |
| **Cluster mesh** | Clusters interconnected (e.g. Cilium Cluster Mesh) | Cross-cluster services, failover |

- Drivers: blast-radius isolation, compliance/residency, scale limits, HA/DR, and
  tenant separation. Cost: more clusters means more overhead, so automate lifecycle.

## Chaos engineering experiment template

```text
1. Steady state  - define a measurable healthy signal (e.g. p95 < 300ms, 0 5xx).
2. Hypothesis    - "If <failure> happens, the system stays within steady state."
3. Blast radius  - smallest scope; start in staging; set abort conditions.
4. Inject        - kill pods / add latency / drain a node / cut a dependency.
5. Observe       - compare metrics to steady state; did the SLOs hold?
6. Learn and fix - file actions; revert; automate the test as a regression guard.
```

```bash
# Example: delete a random running pod to test self-healing
kubectl delete pod -l app=web -n app \
  --field-selector=status.phase=Running --wait=false
```

## Platform CI/CD pipeline template

```text
lint -> test -> build -> scan -> sign -> push -> deploy (GitOps)
```

```yaml
# GitHub Actions sketch: one job per stage, fail fast
jobs:
  lint:   { steps: ["yamllint", "tflint", "kubeconform"] }
  test:   { needs: lint,  steps: ["unit tests", "kubeconform", "terraform test"] }
  build:  { needs: test,  steps: ["docker buildx build"] }
  scan:   { needs: build, steps: ["trivy image --severity HIGH,CRITICAL"] }
  sign:   { needs: scan,  steps: ["cosign sign (keyless OIDC)"] }
  push:   { needs: sign,  steps: ["push image + SBOM attestation"] }
  deploy: { needs: push,  steps: ["commit image tag to the config repo"] }
```

- Gate merges on scan and sign; deploy by **committing to Git** and letting the
  GitOps agent reconcile - CI never holds cluster credentials.

## See also

- [`../20-advanced-platform-topics/`](../20-advanced-platform-topics/) - the maturity
  model, platform metrics, and culture.
- [`../17-platform-sre/`](../17-platform-sre/) - SLOs, incident response, chaos, DR.
- [`../19-multi-cluster-and-multi-cloud/`](../19-multi-cluster-and-multi-cloud/) -
  multi-cluster architecture and fleet management.
- [`../21-capstone-projects/production-readiness-checklist.md`](../21-capstone-projects/production-readiness-checklist.md)
  - the full production readiness checklist.
