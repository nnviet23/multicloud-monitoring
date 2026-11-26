# Cheat Sheet — Internal Developer Platform (IDP)

> An IDP is the product a platform team builds: self-service capabilities composed
> across five planes, surfaced through a portal and golden paths.

## IDP architecture - the five planes

| Plane | Responsibility | Example tools |
|-------|----------------|---------------|
| Developer Control Plane | How developers interact | Backstage, Git, CLI, `kubectl` |
| Integration & Delivery | Build, test, deploy, reconcile | GitHub Actions, Argo CD, Kustomize |
| Resource Plane | Where workloads run | Kubernetes, cloud, databases |
| Monitoring & Logging | Signals and feedback | Prometheus, Loki, Grafana, OTel |
| Security | Identity, policy, secrets | RBAC, Kyverno, ESO, Vault |

- The **portal** (for example Backstage) is a window onto the platform, not the
  platform itself. Every capability must also work via Git, API, or CLI.

## Backstage entity types

| Kind | Represents | Example |
|------|------------|---------|
| **Component** | A piece of software | A service, library, or website |
| **API** | An interface a Component exposes | A REST/gRPC/GraphQL definition |
| **System** | A set of related entities | The "checkout" system |
| **Domain** | A business area grouping systems | "payments" |
| **Resource** | Infrastructure a Component needs | A database, bucket, or queue |
| **Group** | A team or org unit | `team-platform` |
| **User** | A person | `jdoe` |

```yaml
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: checkout
  annotations:
    github.com/project-slug: org/checkout
    backstage.io/techdocs-ref: dir:.
spec:
  type: service
  lifecycle: production
  owner: team-checkout
  system: commerce
  providesApis:
    - checkout-api
  dependsOn:
    - resource:checkout-db
```

- `catalog-info.yaml` lives at each repo root; Backstage discovers and indexes it.
- Relationships: `ownedBy`, `partOf`, `dependsOn`, `providesApis`, `consumesApis`.

## Golden path checklist

A golden path is the paved, supported route for a common task. A good one provides:

- [ ] **Scaffolding** - one command or template creates the repo and skeleton.
- [ ] **CI/CD wired in** - lint, test, build, scan, and deploy on first push.
- [ ] **Secure defaults** - non-root, policies, RBAC, and secrets handling baked in.
- [ ] **Observability by default** - metrics, logs, traces, and a starter dashboard.
- [ ] **Environments** - dev/staging/prod provisioned via GitOps.
- [ ] **Docs** - TechDocs published alongside the service.
- [ ] **Ownership** - a catalog entry with an owning team.
- [ ] **Escape hatches** - advanced users can drop down a layer when needed.
- [ ] **Measured** - adoption and time-to-first-deploy are tracked.

## Software templates & discovery

- **Software templates** (Scaffolder) turn a golden path into a form: pick inputs,
  then Backstage creates the repo, CI, and catalog entry from a skeleton.
- **Discovery:** point Backstage at an org so it auto-ingests every
  `catalog-info.yaml`, instead of registering repositories by hand.
- **TechDocs:** docs-as-code built from Markdown in the repo and rendered in the portal.
- **Scorecards:** score entities against standards (has owner, on-call, SLO, scans
  passing) to drive golden-path adoption.

## Measuring the IDP

| Signal | Example metric |
|--------|----------------|
| Adoption | Share of services with a catalog entry on a golden path |
| Speed | Time-to-first-deploy for a new service |
| Quality | Change-fail rate and DORA on platform-delivered pipelines |
| Satisfaction | DevEx survey score, portal NPS |

## See also

- [`../15-developer-experience-and-idp/`](../15-developer-experience-and-idp/) - IDP
  architecture, the Backstage catalog and templates, and golden paths.
- [`platform-engineering-overview.md`](./platform-engineering-overview.md) - golden
  paths vs guardrails and team topology.
