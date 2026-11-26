# Cheat Sheet — Platform Engineering Overview

> Platform engineering builds an Internal Developer Platform (IDP) as a product, so
> stream-aligned teams can self-serve golden paths within safe guardrails.

## What platform engineering is

- **Goal:** reduce developer cognitive load and shorten lead time by productizing
  the paved road from commit to production.
- **Mindset:** the platform is a **product**, developers are **customers**, and
  adoption is voluntary and earned - not mandated.
- **Output:** self-service capabilities (environments, pipelines, databases) with
  security, observability, and cost built in by default.

## Platform vs DevOps vs SRE

| Discipline | Primary question | Owns | Optimizes |
|------------|------------------|------|-----------|
| DevOps | How do we break down dev/ops silos? | Culture, CI/CD practice | Flow, collaboration |
| SRE | How do we run services reliably? | SLOs, error budgets, toil | Reliability at scale |
| Platform Engineering | How do we make the right way the easy way? | The IDP as a product | Developer self-service |

- They overlap: platform teams **apply** SRE practices to the platform itself and
  **productize** DevOps principles. PE is not a rename of either.

## The five IDP planes

| Plane | Responsibility | Example tools |
|-------|----------------|---------------|
| Developer Control Plane | How developers interact | Backstage, Git, CLI, `kubectl` |
| Integration & Delivery | Build, test, deploy, reconcile | GitHub Actions, Argo CD, Kustomize |
| Resource Plane | Where workloads actually run | Kubernetes, cloud, databases |
| Monitoring & Logging | Signals and feedback | Prometheus, Loki, Grafana, OTel |
| Security | Identity, policy, secrets | RBAC, Kyverno, ESO, Vault |

## Core principles

- **TVP (Thinnest Viable Platform):** start with the smallest platform that delivers
  value; grow by real developer demand, not a speculative up-front build.
- **Golden paths:** opinionated, supported, well-documented routes for the 80% case
  (for example "ship a Go service"). Optional but overwhelmingly attractive.
- **Guardrails:** policy, quotas, and defaults that keep teams safe **without** a
  human gate. Golden path = the easy way; guardrail = the safe boundary.
- **Self-service:** provision without filing a ticket or waiting on the platform team.
- **Product thinking:** roadmap, user research, docs, SLAs, and measured adoption.

## Golden paths vs guardrails

| | Golden path | Guardrail |
|--|-------------|-----------|
| Nature | Paved road (enabling) | Boundary (constraining) |
| Enforcement | Opt-in, attractive default | Automated, always-on |
| Example | Scaffold + CI + deploy template | Kyverno policy, ResourceQuota, RBAC |
| If missing | Everyone reinvents the wheel | Unsafe changes reach production |

## Team Topologies (one screen)

- **Four team types:** stream-aligned (builds product), **platform** (provides the
  IDP), enabling (coaches and upskills), complicated-subsystem (deep specialist).
- **Three interaction modes:** collaboration (temporary, discovery), X-as-a-Service
  (the platform's default - low friction), facilitating (enabling team helps).
- **Team API:** a platform team exposes a clear interface (docs, support, SLOs) and
  minimizes collaboration so consumers stay in **X-as-a-Service** mode.
- **Rule of thumb:** optimize for **fast flow** and low cognitive load in
  stream-aligned teams; the platform exists to enable them.

## Signals that the platform works

- **DORA:** deploy frequency, lead time, change-fail rate, time to restore.
- **Adoption:** share of teams and services on golden paths (voluntary uptake).
- **Developer experience:** DevEx surveys, time-to-first-deploy, onboarding time.
- **Reliability and cost:** platform SLOs met; cost per team/workload attributed.

## See also

- [`../01-platform-foundations/`](../01-platform-foundations/) - foundations, TVP,
  developer experience, the IDP, and platform team topology.
- [`../20-advanced-platform-topics/`](../20-advanced-platform-topics/) - maturity,
  metrics, and platform culture.
