# ADR-0005: Why Folder-Over-Branch and Kustomize

## Status
Accepted

## Context
A multi-cluster GitOps repository must represent `hub-k3d`, `aws-k3d`, and `azure-k3d` clearly without configuration drift or merge conflicts. Long-lived environment branches (`aws`, `azure`, `hub`) inevitably diverge and require error-prone cherry-picking. Additionally, combining multiple Kubernetes resources into monolithic YAML files hurts code review, and mixing CI-automated image tag updates with human-edited resource patches causes frequent merge conflicts.

## Decision
We adopt a **Folder-Over-Branch** strategy on a single `main` trunk, powered by **Kustomize** and **Single Responsibility Principle (SRP)** manifest hygiene:
- **Single Trunk, Folder Overlays:** All clusters reconcile from `main` via `deploy/clusters/{aws,azure,hub}/kustomization.yaml`, composing shared bases from `deploy/platform/`, `workloads/`, `deploy/policies/`, and `deploy/integrations/`.
- **Kustomize over Helm for internal manifests:** Enables native, template-free patching and `images:` overrides without maintaining custom Helm charts for every internal component.
- **SRP & Release-Pointer Isolation:** One Kubernetes resource per file with ordered prefixes (`00-namespace.yaml` .. `07-hpa.yaml`), and image digests/tags isolated in `workloads/teastore/release-images/` and overlay `images:` blocks so CI bots never conflict with human `patches/*.yaml`.

## Alternatives Considered
- **Branch-per-Environment:** Causes silent configuration drift between branches and makes cross-environment diffs cumbersome.
- **Polyrepo (separate repos per cluster/tier):** Enforces hard isolation but introduces heavy cross-repo coordination overhead.
- **Helm for all internal manifests:** Adds Go-templating complexity for internal workloads that are more cleanly expressed as Kustomize bases and strategic-merge patches.

## Consequences
- **Positive:** Zero environment-branch drift; clean, auditable diffs for promotions; zero merge conflicts between CI image bumps and operator patches.
- **Negative:** Increases the total number of small YAML files in the repository and requires strict discipline on naming prefixes and `CODEOWNERS`/path review rules.
