# Cheat Sheets

> Dense, copy-pasteable quick-reference pages for the Multi-Cloud Hub-Spoke Observability Platform.
> Each sheet links back to the full module(s) that teach the topic in depth.

These are for **recall, not learning**. If a command, policy, or query here needs
context, follow the "See also" links to the full modules.

## Index

| Cheat sheet | What's inside |
|-------------|---------------|
| [Platform Engineering Overview](./platform-engineering-overview.md) | PE vs DevOps vs SRE, the five IDP planes, TVP, golden paths vs guardrails, Team Topologies |
| [Platform Maturity & Operations](./platform-maturity-model.md) | Maturity Levels 1-5, production readiness, multi-cluster patterns, chaos template, CI/CD pipeline |
| [Kubernetes](./kubernetes-cheat-sheet.md) | Architecture, resource model, workloads, resource management, RBAC, pod debugging |
| [kubectl](./kubectl-cheat-sheet.md) | Task-grouped commands: get/describe/logs/exec/apply/kustomize/k3d/debug/port-forward/auth |
| [Terraform](./terraform-cheat-sheet.md) | init/plan/apply, state, variables, modules, backends, workspaces, testing |
| [GitOps](./gitops-cheat-sheet.md) | The four principles, push vs pull, repo strategy, drift/self-heal, secrets |
| [Argo CD](./argocd-cheat-sheet.md) | Application/ApplicationSet, sync & health, sync waves, app-of-apps, CLI |
| [Observability](./observability-cheat-sheet.md) | Three pillars, RED/USE/golden signals, PromQL, LogQL, SLO/burn-rate, OTel |
| [Security & Policy](./security-cheat-sheet.md) | Kyverno patterns, secret-management options, SLSA levels, hardening checklist |
| [Networking](./networking-cheat-sheet.md) | Flat pod network, Services/DNS, NetworkPolicy, Cilium/eBPF/Hubble, Gateway API |
| [Internal Developer Platform](./idp-cheat-sheet.md) | The five planes, Backstage entities, golden path checklist |
| [FinOps & Cost](./finops-cheat-sheet.md) | Inform/Optimize/Operate, the attribution gap, cost-per-workload, optimization checklist |

## How to use these

- **Scan** for the section you need; the headings and tables are the index.
- **Copy** commands and snippets directly - they are real, not pseudo-code.
- **Verify** against your own versions; flags and APIs evolve over time.
- **Go deeper** via each sheet's "See also" and the [ROADMAP](../ROADMAP.md).

## See also

- [Concepts](../concepts/01-platform-and-kubernetes-fundamentals.md) - core platform engineering concepts and architecture modules.
- [Architecture Decisions](../decisions/README.md) - canonical ADRs for the multi-cloud hub-spoke platform.
