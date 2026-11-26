# 10 · Developer Experience and IDP

> **Project Applicability:** Reference / Future Extension — IDP and Backstage concepts serve as a reference for future developer self-service portal extensions.

> Back in 
> you learned the **five planes** of an Internal Developer Platform and the rule that
> *the platform API is the product, not the portal*. In 
> you learned about **golden paths** and measured time-to-first-production-deployment.
> This phase is where those ideas stop being theory. You will build the **developer
> control plane** — Backstage, a software catalog, golden-path templates, plugins, a
> `platform` CLI, and docs-as-code — that turns the capabilities from Projects 1–3
> into genuine self-service.

## Why developer experience and an IDP now?

Everything you have built so far is powerful but **not yet self-service**. In
Project 1 you onboarded a team by hand: you created the
namespace, the RBAC, and the quota yourself. In Project 2
you delivered new services through GitOps, but someone still wrote the ArgoCD
`Application` and the manifests. In Project 3 you wired
in observability — but a developer who wants a dashboard still copies one from
another repo. Every one of those is a **ticket waiting to happen**, and a ticket for
routine work is the bottleneck platform engineering exists to remove.

This phase closes the loop. It builds the plane that sits in front of all the others:

- **The developer control plane.** The portal, catalog, templates, and CLI that let a
 developer *ask for* a new service — and get it, fully wired, without a ticket.
- **Golden paths, realized.** The paved road from 
 becomes a concrete template that scaffolds a repo, a pipeline (the
 templates-as-product
 work from ), GitOps config, observability, and docs in one click.
- **The catalog.** A live inventory answering "what exists, who owns it, where it
 runs, and is it healthy?" — the question Slack currently answers badly.
- **Docs-as-code.** Documentation that lives with the service and renders in the
 portal, so the paved road is also well-lit.

Keep two sentences from in your pocket the whole way through: **the
portal is not the platform**, and **the platform API is the product**. Backstage is
*one* client of a platform you already mostly built — this phase wires it up and adds
the interface.

## IDP Architecture

> In 
> you learned the **five planes** of an IDP as a map. This module turns the map into a
> buildable architecture: how the planes connect through an **orchestration layer**,
> how to design the **platform API** that is the real product, the product principles
> that keep an IDP usable (convention over configuration, escape hatches, supported
> migration), and a **build-vs-buy decision matrix** you can actually fill in.

and 01.4; the
mindset from Projects 1–3.

### 1. Concept

#### From map to architecture

 gave you the five planes: **developer control**, **integration &
delivery**, **resource**, **monitoring**, and **security**. That is the *what*. This
module is the *how they connect*. An IDP is not five tools sitting next to each other;
it is five planes stitched together by an **orchestration layer** that turns one
developer request into coordinated action across all of them.

```text
Five planes (the WHAT, from 01.4) This module adds the HOW:
 control · delivery · resource → a platform API + orchestration that
 monitoring · security make the planes act as one system
```

#### The orchestration layer

When a developer says *"I want a new Go service with a small Postgres in staging,"* no
single plane can satisfy that. Something has to:

- scaffold the repo from the golden-path template (control + delivery),
- open a GitOps PR to deploy it (delivery),
- provision the Postgres via IaC/Crossplane (resource),
- wire a default dashboard and alerts (monitoring),
- inject secrets and set least-privilege access (security).

The component that fans one request out across the planes is the **orchestration
layer** (Humanitec calls its product a *Platform Orchestrator*). You do not have to
buy one — across this course you assemble it from open-source pieces you already know:
a **template** (Backstage scaffolder, ) triggers **CI**, which
commits to a **GitOps** repo that ArgoCD reconciles, provisioning
**resources** and wiring **observability**.
The orchestration is the *glue and sequencing*, and it is where your platform's
opinion lives.

#### The platform API is the product

The single most important architectural decision is the **platform API**: the stable,
versioned, declarative contract that describes *what a developer wants*, independent of
*how* it is fulfilled. Portals and CLIs are thin clients of it; the API is what
endures.

A good platform API is:

- **Declarative.** The developer states the desired end-state ("a service named
 `payments`, owner `team-payments`, needs a small Postgres in staging"), not the
 steps. This is the same shift GitOps made in.
- **Stable and versioned.** It has consumers, so it is subject to the same rules as
 's pipeline template: semantic versions, deprecation over deletion, a
 migration path. Break it and you break every team.
- **Documented.** A schema with required/optional fields, defaults, and examples —
 rendered in the portal.
- **Abstracted at the right level.** It exposes *workloads and their needs*, not raw
 Kubernetes. The open-source [Score](https://score.dev/) spec and Humanitec's
 workload model are examples of this "describe the workload, not the YAML" idea.

```yaml
## platform-request.yaml — a v1 platform API as a declarative spec
apiVersion: platform.example.com/v1
kind: ServiceRequest
metadata:
 name: payments
 owner: team-payments
spec:
 language: go
 path: go-microservice # the golden path this service follows
 environments:
 - name: staging
 resources:
 - type: postgres
 size: small
```

Every interface — Backstage, the `platform` CLI, a CI job — produces or
consumes *this*, and the orchestration behind it does the work. Design this contract
**before** you choose a portal.

#### IDP product principles

Three principles separate an IDP developers *choose* from one they resent:

- **Convention over configuration.** The golden path encodes good defaults so the
 common case needs almost no input. A developer names a service and picks a team;
 non-root containers, SBOMs, dashboards, and sane resource limits come for free. The
 fewer decisions a developer must make to do the right thing, the better.
- **Escape hatches exist.** From golden paths are the *easiest* route,
 not a mandatory cage. A sanctioned, documented, auditable way to deviate (a custom
 base image, a database the platform does not support yet) keeps teams on the
 platform instead of routing around it. An escape hatch you can see and count is far
 safer than a silent fork.
- **Migration is supported.** Golden paths and the API evolve. When v2 lands, v1 keeps
 working with a deprecation warning and a sunset date, and you provide tooling (a bot
 that opens the bump PR) to move teams. This is 's versioning discipline
 applied to the whole platform.

#### Build vs buy, deliberately

 surveyed the portal landscape (Backstage, Port, Cortex, Compass, custom).
The architecture question is sharper: for *each* component, do you build, buy, or
adopt open source? Decide with a **matrix**, not a vibe. Weigh, per component:

- **Differentiation** — does this encode *your* opinion (golden paths, orchestration)
 or is it a commodity (a catalog UI)? Build where you differentiate; buy commodities.
- **Operational cost** — can you run and upgrade it? Backstage is powerful but is a
 real application you must operate.
- **Time to value** — SaaS is faster to stand up; open source is cheaper per seat and
 more extensible.
- **Lock-in and exit** — how hard is it to leave? Favor open standards and an
 API-first core so the portal stays swappable.

The recurring heuristic: **buy the portal, build the paths.** Spend scarce engineering
on the orchestration and golden paths that are yours; do not reimplement a catalog UI.

---

### 2. Why it matters for platform engineering

This module is the blueprint for everything else in the phase — and for Project 4. If
you skip the architecture and jump straight to installing Backstage, you will build a
pretty portal over a pile of tickets. Getting
the architecture right means:

- **The API outlives the UI.** You can swap Backstage for Port, add a CLI, or let CI
 consume the platform, all without re-plumbing — because they are clients of a stable
 contract.
- **Orchestration is your moat.** Any team can install a portal; few can make one
 request reliably provision, deploy, secure, and observe a service. That glue is the
 platform's actual value.
- **You choose components on purpose.** A filled-in build-vs-buy matrix is a decision
 you can defend to leadership, not a bandwagon you jumped on.

When you can sketch the planes, the orchestration, and the API for any platform — and
justify each build-vs-buy call — you are architecting an IDP, not assembling tools.

---

### 3. Mental model

```text
 DEVELOPER
 │ "I want a Go service + small Postgres in staging"
 ▼
 ┌───────────────────────────────┐
 │ INTERFACES (thin clients) │ Backstage · platform CLI · CI
 └───────────────┬───────────────┘
 ▼
 ┌───────────────────────────────┐
 │ PLATFORM API (the product) │ declarative · versioned · documented
 │ ServiceRequest spec in Git │
 └───────────────┬───────────────┘
 ▼
 ┌───────────────────────────────┐
 │ ORCHESTRATION LAYER (the glue)│ sequences the planes; holds your opinion
 └───┬───────┬───────┬───────┬────┘
 ▼ ▼ ▼ ▼
 delivery resource monitor security ← the five planes (control = interfaces above)
 (GitOps) (IaC/XP) (OTel/ (secrets/
 Grafana) policy)

Rule of thumb: design the API first, build the orchestration, treat every
interface as swappable, and buy the commodity planes while building your paths.
```

One sentence to carry: **an IDP is a stable platform API plus orchestration across the
five planes, exposed through interchangeable interfaces.**

---

### 4. Minimal implementation

The thinnest honest architecture is the `platform-request.yaml` above plus a sketch of
the orchestration that fulfills it — *no portal required yet*. Write the contract, then
list what each field triggers across the planes:

```text
spec.path: go-microservice → control/delivery: scaffold repo from template
spec.language: go → delivery: select the Go CI pipeline
spec.environments[].name: staging → delivery: GitOps App targets the staging cluster
spec.resources[].type: postgres → resource: Crossplane/Terraform claim
(always-on defaults) → monitoring: default dashboard + alerts
(always-on defaults) → security: secret injection + least-privilege RBAC
```

Notice three things. First, the developer's interface is **one declarative file** —
exactly the shape of 's minimal IDP, now with explicit API versioning.
Second, the **always-on defaults** (monitoring, security) are *convention*, not
developer choices — they are in the path by default, never bolted on. Third, every
trigger maps to work you already did in Projects 1–3; this phase is wiring a
self-service front end onto it. Add a CLI, then a portal, **only as demand justifies**
(the Thinnest Viable Platform).

---

### 6. Production considerations

- **Version the API from v1.** It has consumers the moment anyone uses it. Decide the
 schema, defaults, and deprecation policy before the second team adopts it.
- **Make the orchestration idempotent and observable.** Re-applying the same
 `ServiceRequest` must not create duplicates, and every fulfillment should emit
 events you can trace when a provision half-fails (which it will).
- **Design for partial failure.** Provisioning spans Git, CI, a cloud, and a cluster.
 Decide what happens when the repo is created but the database claim fails — roll
 back, retry, or surface a clear, actionable error. Silent half-states erode trust.
- **Keep security and monitoring in the path by default.** Retrofitting them per team
 leaves gaps. They are always-on conventions, not opt-in parameters.
- **Treat escape-hatch usage as a signal.** A frequently used hatch is a bug report
 about your defaults — change the path, do not just tolerate the workaround.
- **Document the contract where developers already are.** The API schema belongs in
 the portal (TechDocs, ), versioned with the platform.

---

### 7. Common mistakes

- **UI-first instead of API-first.** Building the Backstage portal before the
 declarative contract, then being unable to automate against it or swap the UI.
 *Fix:* design and version the API spec first; the portal is one client.
- **No orchestration — a portal over tickets.** The "create" button files a ticket a
 human fulfills. That is 's top anti-pattern. *Fix:* real automation that
 fans the request across the planes.
- **Configuration over convention.** A template with forty required fields reproduces
 the cognitive load you set out to remove. *Fix:* sensible defaults; ask only for
 what is genuinely service-specific.
- **No escape hatch, so teams fork.** Forbidding all deviation pushes teams off the
 platform silently, destroying your visibility. *Fix:* sanctioned, logged, counted
 hatches.
- **Breaking the API in place.** Changing the spec's meaning under everyone, with no
 version or migration. *Fix:* semantic versions, deprecation windows, bump tooling.
- **Build-vs-buy by hype.** Adopting a tool because it is trendy, or building a
 catalog UI because building is fun. *Fix:* score each component on differentiation,
 op-cost, time-to-value, and lock-in.

---

## Backstage Fundamentals

> Backstage is the open-source framework most teams reach for to build the **developer
> control plane** — the portal surface of the IDP you architected in. This
> module explains what Backstage is, why *every feature is a plugin*, how it is
> deployed (a Node.js app with a Postgres backend), how authentication works, and how
> to run it as a platform **product**. You will run it locally; cloud deployment is
> optional.

GitHub account (free). The lab's core runs on `localhost`; GKE is optional.

### 1. Concept

#### What Backstage is (and is not)

**Backstage** is an open-source framework for building developer portals, created
inside **Spotify** to tame the sprawl of hundreds of services and teams, and donated
to the **CNCF** in 2020 (now a CNCF Incubating project). The key word is *framework*:
Backstage is not a finished product you install and use as-is. It is a React + Node.js
application skeleton that **you** scaffold, configure, extend with plugins, and
operate.

Hold on to the warning: **the portal is not the platform.** Backstage is
(part of) the **developer control plane** — one client of the platform API you
designed in. It makes your catalog, golden paths, and runtime data
*visible and usable*; it does not, by itself, provision, deploy, or secure anything.
Installing Backstage no more gives you an IDP than buying a storefront gives you a
supply chain.

#### Every feature is a plugin

Backstage's architecture is radical in one way: **everything is a plugin**, including
the core features. The app is a thin shell that composes plugins. This is why it is so
extensible — adding ArgoCD sync status or a cost widget is "install a
plugin," the same mechanism the core is built from.

Plugins come in two halves:

- **Frontend plugins** — React components that render pages and widgets in the UI.
- **Backend plugins** — Node.js services that talk to external systems (GitHub, your
 cluster, your CI) and expose APIs the frontend calls.

```text
 Backstage app (a thin shell)
 ┌──────────────────────────────────────────┐
 │ Frontend (React) Backend (Node) │
 │ ┌────────────┐ ┌─────────────┐ │
 │ │ catalog │◄────────►│ catalog │ │
 │ │ scaffolder │◄────────►│ scaffolder │ │
 │ │ techdocs │◄────────►│ techdocs │ │
 │ │ search │◄────────►│ search │ │
 │ │ (your) │ │ (your) │ │
 │ └────────────┘ └─────────────┘ │
 └──────────────────────────────────────────┘
 every box above is a PLUGIN
```

#### The four core features

Out of the box, the scaffolded app ships four plugins you will use constantly:

- **Software Catalog** — the live inventory of components, APIs, systems, and teams. This is the backbone everything else hangs off.
- **Software Templates** (the *scaffolder*) — self-service "create a new service" that
 realizes golden paths.
- **TechDocs** — docs-as-code: MkDocs documentation that lives in each repo and renders
 in the portal.
- **Search** — across the catalog, docs, and more.

Those four map neatly onto the IDP capabilities from *application
catalog*, *self-service provisioning*, *knowledge*, and *findability*.

#### Deployment shape: a Node.js app with a Postgres backend

Backstage is, concretely, a **Node.js application**. For anything beyond a laptop demo
it needs a **PostgreSQL** database (the default in-memory SQLite is for local
development only — it is wiped on restart). The production shape is familiar:

```text
Browser ──► Backstage frontend (static) ──► Backstage backend (Node.js) ──► PostgreSQL
 │
 ├──► GitHub (catalog discovery, auth)
 ├──► Kubernetes (plugin)
 └──► ArgoCD / Grafana / … (plugins)
```

You containerize it and run it on Kubernetes like any other stateful-ish web app —
typically with the community **Helm chart**, backed by a managed Postgres (Cloud SQL
on GKE). The lab shows the local run in full and the Helm deploy as an optional step.

#### Authentication

Backstage separates **sign-in** (who are you?) from **identity** (which catalog
`User`/`Group` are you, for ownership and access). For sign-in it supports pluggable
providers: **GitHub**, Google, GitLab, Okta, and generic **OIDC**. In the lab you will
wire up **GitHub OAuth**, because it doubles as the credential for catalog discovery
and the scaffolder's `publish:github` step later.

> Local development has a **guest** sign-in so you can explore without any provider.
> Never enable guest access on a shared or internet-facing instance.

#### Backstage as a platform product

Backstage is itself software your platform team owns — so 's product
discipline applies to it directly:

- **Versioning and upgrades.** Backstage releases frequently (roughly monthly). You
 pin a version and upgrade deliberately using the official `backstage-cli` upgrade
 helper and the changelog. Falling years behind makes plugins and security fixes
 painful.
- **A support model.** A support channel, office hours, and docs — "knowledge and
 support" are in the platform definition for a reason.
- **An internal changelog.** When you add a plugin or change a golden path, your
 developers are consumers; tell them what changed.

---

### 2. Why it matters for platform engineering

Backstage is the most common realization of the developer control plane, so knowing
its shape — framework, plugins, Node.js + Postgres, pluggable auth — is core platform
literacy. But the deeper reason this module matters is **discipline**: it is easy to
mistake "we installed Backstage" for "we have an IDP." Keeping Backstage in its place —
a swappable client of your platform API — is what stops you from building the
ticket-queue-with-nicer-fonts anti-pattern.

Running it locally also demystifies it. Once you have scaffolded the app and watched
the catalog, scaffolder, and TechDocs load from local config, the rest of the phase
(and Project 4) becomes concrete: you are no longer configuring a black box, you are
composing plugins on a Node app you understand.

---

### 3. Mental model

```text
 BACKSTAGE = a React+Node SHELL that COMPOSES PLUGINS
 ────────────────────────────────────────────────────

 framework, not product → you scaffold + operate it (it is YOUR app)
 every feature is a plugin → core = catalog, scaffolder, techdocs, search
 deployment → Node.js app + PostgreSQL, on Kubernetes (Helm)
 auth → pluggable sign-in (GitHub/OIDC) + catalog identity
 its place → the developer CONTROL PLANE — ONE client of the
 platform API; "the portal is not the platform"

 Run order you will follow: scaffold → run locally → add auth → (optional) deploy
```

One sentence: **Backstage is a plugin-composed Node.js app you operate as a product to
present your platform — not the platform itself.**

---

### 4. Minimal implementation

The smallest real Backstage is one command plus a run. It creates a monorepo with the
four core plugins already wired:

```bash
## Node.js 20+ required. Scaffold a new app (interactive: it asks for an app name).
npx @backstage/create-app@latest

cd my-backstage-app
yarn install

## Run frontend + backend together (uses local SQLite + guest auth)
yarn dev
## → open http://localhost:3000 (frontend) / backend on:7007
```

What you get is already a working portal: a Software Catalog seeded with an example
component, the scaffolder, TechDocs, and search — all composed in a handful of files:

```text
my-backstage-app/
├── app-config.yaml # the main config: auth, catalog, integrations
├── packages/
│ ├── app/ # the FRONTEND (React) — composes frontend plugins
│ └── backend/ # the BACKEND (Node.js) — composes backend plugins
└── examples/ # sample catalog entities + a sample template
```

Everything in this phase is edits to `app-config.yaml` and `packages/*` — adding
integrations, auth providers, catalog locations, and plugins. The lab walks the full
local run; cloud comes later and only if you want it.

---

### 6. Production considerations

- **Always use PostgreSQL.** SQLite is development-only and non-durable. Back
 production with managed Postgres (Cloud SQL) and real backups.
- **Have an upgrade cadence.** Backstage moves fast. Schedule regular upgrades with the
 `backstage-cli` and read the changelog; do not let the version rot.
- **Lock down auth.** Disable guest access everywhere but local dev, scope OAuth apps
 correctly, and map sign-in to catalog `User`/`Group` identity for ownership.
- **Run it like a real service.** HA replicas, health checks, resource limits,
 observability (it is a Node app — scrape it), and an SLO. The portal going down
 blocks every developer who depends on it.
- **Secure the backend's credentials.** Its GitHub token and cluster access are
 powerful; store them with your secrets manager (ESO/Vault), never in `app-config`.
- **Treat it as a product.** Changelog, support channel, and adoption metrics — a
 portal nobody opens is a failed product.

---

### 7. Common mistakes

- **"We installed Backstage, so we have an IDP."** The portal is one plane's surface,
 not the platform. *Fix:* keep the five-planes and API-first view from 
 and 15.1.
- **Running on SQLite in production.** Data vanishes on restart and it does not scale.
 *Fix:* PostgreSQL from the first shared deployment.
- **Never upgrading.** Falling many releases behind makes every future plugin and
 security patch a slog. *Fix:* a regular, boring upgrade cadence.
- **Leaving guest auth on.** An unauthenticated internal portal leaks your whole
 service inventory. *Fix:* a real identity provider; guest only on localhost.
- **Hand-editing in production.** Treating the running portal as config-by-clicking.
 *Fix:* it is a Node app in Git — change it via code review and redeploy.
- **Secrets in `app-config.yaml`.** Committing the GitHub token or DB password. *Fix:*
 environment variables sourced from your secrets manager.

---

## Backstage Software Catalog

> The Software Catalog is Backstage's backbone and the IDP's **application catalog**
> capability from a live inventory of *what exists, who owns it, where it
> runs, and how the pieces relate*. This module covers the catalog's entity kinds, the
> `catalog-info.yaml` descriptor that lives in every repo, the relationships that turn a
> list into a graph, automatic **GitHub discovery**, and how to keep the catalog from
> rotting into fiction.

app (local is fine). A GitHub account for the discovery step.

### 1. Concept

#### The catalog is the inventory you keep asking Slack for

Every organization past a handful of services develops the same blind spots: *Who owns
this service? What depends on the orders database? Which team do I page? Where is this
deployed?* Today those are answered — badly, inconsistently — in Slack threads and
tribal memory. The **Software Catalog** makes them a queryable, always-current graph.
It is the concrete form of 's *application catalog* capability and the thing
most of the portal's value hangs off.

#### Entity kinds

The catalog models your world with a small set of **entity kinds**:

- **Component** — a piece of software you build and run: a service, website, or
 library. The most common entity.
- **API** — an interface a component exposes (REST/OpenAPI, gRPC, GraphQL,
 AsyncAPI). Catalogued separately so consumers can discover it.
- **System** — a collection of components and resources that work together toward a
 capability (e.g. "order-management"). The right altitude for most architecture
 conversations.
- **Domain** — a group of related systems sharing a business area (e.g. "commerce").
- **Resource** — infrastructure a component needs: a database, bucket, queue, or
 cluster.
- **Group** — a team or org unit (e.g. `team-payments`).
- **User** — a person, usually mapped from your identity provider.

```text
 Domain (commerce)
 └── System (order-management)
 ├── Component (checkout-service) ──provides──► API (checkout-api)
 │ └── dependsOn ──► Resource (orders-database)
 └── Component (payment-gateway)
 Group (team-payments) ──owns──► checkout-service, checkout-api
```

#### `catalog-info.yaml`: the descriptor in every repo

Each entity is declared in a YAML descriptor, conventionally `catalog-info.yaml` at the
root of the repo that owns it. This is **docs-as-code for your architecture**: the
inventory lives with the code, is reviewed in PRs, and cannot drift from the repo it
describes. A minimal Component:

```yaml
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
 name: checkout-service
 description: Handles payment and order checkout
 annotations:
 github.com/project-slug: org/checkout-service
 backstage.io/techdocs-ref: dir:.
spec:
 type: service
 lifecycle: production
 owner: team-payments
 system: order-management
```

The `spec.type` (service/website/library), `spec.lifecycle`
(experimental/production/deprecated), and `spec.owner` are the fields you will set most
often. **Annotations** wire the entity to external systems — the `github.com/*`
annotation links it to a repo; later modules add `argocd/app-name`,
`backstage.io/kubernetes-id`, and Grafana annotations to light up plugins.

#### Relationships turn a list into a graph

A flat list of services is a phone book. The value appears when entities **reference
each other** and Backstage renders the relationships:

- **`spec.owner`** → an `ownedBy` relationship to a Group. Every entity should have a
 real owner; "who do I ask?" becomes a link, not a guess.
- **`spec.system`** → a `partOf` relationship: this component belongs to a system.
- **`spec.dependsOn`** → explicit dependencies on other components or resources
 (`component:payment-gateway`, `resource:orders-database`).
- **`spec.providesApis`** / **`spec.consumesApis`** → links components to the API
 entities they expose or call.

From these, Backstage draws a dependency graph, a system diagram, and "what will I
break if I change this?" views. The relationships are the point — model them honestly.

#### API catalog from OpenAPI

An **API** entity can embed or reference a definition (an OpenAPI spec), and Backstage
renders browsable docs and a try-it view from it:

```yaml
apiVersion: backstage.io/v1alpha1
kind: API
metadata:
 name: checkout-api
spec:
 type: openapi
 lifecycle: production
 owner: team-payments
 definition:
 $text:./openapi.yaml # or an inline spec / a URL
```

Now API consumers discover and read the contract in the portal instead of asking the
owning team — a direct cut to the "waiting friction" from.

#### Catalog ingestion: GitHub discovery

Registering each `catalog-info.yaml` by hand does not scale. **GitHub discovery**
points Backstage at an org and automatically ingests every repo that contains a
descriptor:

```yaml
## app-config.yaml
catalog:
 providers:
 github:
 myOrg:
 organization: your-org
 catalogPath: /catalog-info.yaml
 schedule:
 frequency: { minutes: 30 }
 timeout: { minutes: 3 }
```

Add a descriptor to a new repo and it shows up in the catalog within the refresh
window — no central registry to maintain. This is the ingestion automation 
insisted on: *"automate ingestion or the catalog rots into fiction."*

#### Catalog health

A catalog is only useful if it is **current and complete**. Two failure modes to watch:

- **Staleness** — an entity still listed but the repo is archived or gone. Discovery
 plus periodic refresh prunes most of it; processing errors surface the rest.
- **Missing or fake owners** — `owner: unknown` or a group that does not exist. These
 are the entries that make the catalog untrustworthy. Enforce that every entity has a
 real `owner` (a validation step in CI, or a Soundcheck/scorecard-style check).

Treat catalog health as an operational metric: *what percent of entities have a real
owner, valid relationships, and no processing errors?*

---

### 2. Why it matters for platform engineering

The catalog is the **substrate** the rest of the portal builds on. Templates register new components into it; plugins attach live deploy,
runtime, and cost data to its entities; golden paths depend on every new
service arriving pre-catalogued. Without a trustworthy catalog, none of that works — a
plugin that shows ArgoCD status needs to know *which* ArgoCD app an entity maps to, and
that mapping lives in `catalog-info.yaml`.

More broadly, the catalog is how a platform answers ownership, dependency, and
incident-routing questions at scale. When an alert fires at 3am, "which team owns this
and what does it depend on?" is a catalog query, not an archaeology dig. That is the
difference between a platform and a pile of services.

---

### 3. Mental model

```text
 THE SOFTWARE CATALOG = your architecture, as a living graph
 ──────────────────────────────────────────────────────────

 entity kinds Component · API · System · Domain · Resource · Group · User
 descriptor catalog-info.yaml in each repo (docs-as-code for architecture)
 relationships ownedBy · partOf · dependsOn · provides/consumesApis
 (the edges are the value, not the nodes)
 ingestion GitHub discovery auto-imports every repo with a descriptor
 health every entity has a REAL owner + valid refs + no stale entries

 Ask of the catalog: who owns it? what's it part of? what does it depend on?
 what does it expose? — and get a link, not a Slack thread.
```

One sentence: **the catalog is your architecture expressed as owned, related entities
that live with the code and refresh themselves.**

---

### 4. Minimal implementation

The smallest useful catalog is one descriptor registered in Backstage. Create a
`catalog-info.yaml` describing a service and its owning team, then register its
location:

```yaml
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
 name: hello-service
 description: A minimal example service
spec:
 type: service
 lifecycle: experimental
 owner: team-demo
---
apiVersion: backstage.io/v1alpha1
kind: Group
metadata:
 name: team-demo
spec:
 type: team
 children: []
```

```yaml
## app-config.yaml — register a single location (before you set up discovery)
catalog:
 locations:
 - type: url
 target: https://github.com/your-org/hello-service/blob/main/catalog-info.yaml
```

Reload the catalog and `hello-service` appears, owned by `team-demo`, with a working
"owner" link. That is the whole mechanism — the lab scales it to a realistic multi-
entity graph and switches from hand-registered locations to automatic discovery.

---

### 6. Production considerations

- **Enforce a real owner on every entity.** A validation check in CI (or a scorecard)
 that fails on missing/unknown owners keeps the catalog trustworthy. An unowned entity
 is an incident waiting to misroute.
- **Prefer discovery over hand registration.** Manual `catalog.locations` lists rot.
 Point discovery at the org and let descriptors self-register.
- **Watch processing errors.** Backstage surfaces entities that fail to process (bad
 YAML, dangling refs). Treat a rising error count as a catalog incident.
- **Model at the right altitude.** Systems and Domains keep large catalogs navigable;
 without them you get a flat wall of hundreds of components.
- **Keep descriptors in the service repo.** Co-locating `catalog-info.yaml` with the
 code (not in a central repo) is what prevents drift and enables PR review.
- **Govern annotations.** Plugins depend on specific annotations; document the required
 set and validate them, so a new service lights up every plugin by default.

---

### 7. Common mistakes

- **Treating the catalog as a one-time import.** Bulk-adding entities, then never
 refreshing. *Fix:* discovery + scheduled refresh so it stays current automatically.
- **Entities with no real owner.** `owner: unknown` makes the whole catalog
 untrustworthy. *Fix:* require a valid Group owner, enforced in CI.
- **Skipping relationships.** A flat list of components with no `system`, `dependsOn`,
 or `providesApis`. *Fix:* model the edges — they are where the value is.
- **A central `catalog-info` repo.** Descriptors far from the code drift immediately.
 *Fix:* one descriptor per service repo, reviewed with the code.
- **Dangling references.** `dependsOn: resource:orders-database` when that resource
 entity does not exist. *Fix:* catch processing errors; declare resources too.
- **Ignoring API entities.** Services with undocumented interfaces. *Fix:* catalogue
 APIs from OpenAPI so consumers self-serve the contract.

---

## Backstage Software Templates

> Software Templates (the **scaffolder**) are where self-service provisioning becomes
> real: a developer fills in a short form and gets a new, production-ready repository —
> code skeleton, CI, Helm chart, and `catalog-info.yaml` — created and registered
> automatically. This is the **golden path** from 
> turned into a one-click action, and the end of Project 1's "onboard a service by
> hand."

app, and the pipeline-templates-as-product
ideas from. A GitHub account for the publish step (optional).

### 1. Concept

#### The scaffolder is the "new-service.sh" from, grown up

Back in 
the Thinnest Viable Platform was a `new-service.sh` that stamped out a known-good
starter. The Backstage **scaffolder** is that idea at full strength: a form in the
portal that, on submit, runs a sequence of actions to create and wire up a new
service. It is the IDP's **self-service provisioning** capability and the
most direct attack on *setup friction*. A developer who used to spend two
days copying YAML now spends two minutes filling a form.

#### Anatomy of a template

A template is a single `Template` entity (catalogued like anything else) with three
parts:

```text
Template
├── metadata name, title, description, tags — how it appears in "Create"
├── spec.parameters the FORM: fields the developer fills in (name, owner, …)
└── spec.steps the ACTIONS: what runs on submit (fetch, publish, register)
```

- **Metadata** controls how the template shows up in the portal's *Create* page.
- **Parameters** define the form. Each parameter is a typed field (string, enum,
 boolean) rendered by Backstage; they become `${{ parameters.<name> }}` values in the
 steps. You can group parameters into pages and add validation (required fields,
 patterns, entity pickers that read the catalog).
- **Steps** are an ordered list of **actions** executed server-side on submit. Each
 step can consume outputs of earlier steps via `${{ steps.<id>.output.<field> }}`.

#### The core actions

Three built-in actions do the bulk of the work; a fourth is common:

- **`fetch:template`** — reads a **skeleton** directory and renders it, substituting
 `${{ values.* }}` placeholders with the developer's parameters. This produces the new
 repo's contents in a workspace.
- **`publish:github`** — creates a GitHub repository and pushes the rendered contents,
 setting default branch, protection, and topics. (Equivalents exist for GitLab,
 Bitbucket, Azure.)
- **`catalog:register`** — registers the new repo's `catalog-info.yaml` into the
 Software Catalog, so the service appears in the inventory **immediately**. The service is born catalogued.
- **`github:actions:dispatch`** (optional) — kicks off a workflow in the new repo, e.g.
 to run the first build or request initial infrastructure.

```text
Developer submits the form
 │
 ▼
 fetch:template render./skeleton with { name, owner, … } → workspace
 │
 ▼
 publish:github create repo + push rendered files → remoteUrl
 │
 ▼
 catalog:register register catalog-info.yaml from the repo → catalog entry
 │
 ▼
 (github:actions:dispatch) trigger first CI run → green build
```

#### The skeleton: a templated starter

The **skeleton** is a directory of real files with `${{ values.* }}` placeholders. For a
Go microservice it contains exactly what Project 1 and 2 taught you to want *by
default*:

- `main.go` — a working HTTP service.
- `Dockerfile` — a secure, multi-stage, non-root build.
- `chart/` — a Helm chart with sane defaults.
- `.github/workflows/ci.yaml` — CI that **consumes the platform's reusable workflow** rather than re-authoring a pipeline.
- `catalog-info.yaml` — so the service is catalogued on creation.

Because these defaults are baked in, every service created from the template starts
secure, observable, deployable, and catalogued — the golden path, by construction. The
developer never *chooses* non-root or SBOMs; convention supplies them.

> **Escaping GitHub Actions expressions.** GitHub workflows use `${{ … }}` too, which
> collides with the scaffolder's templating. Mark workflow files
> `copyWithoutTemplating` in `fetch:template` (or escape them) so the new repo keeps its
> literal `${{ github.sha }}` expressions. The lab does this.

#### Templates are products: version them

A template with users is an API — the exact lesson of.
Reference templates (and the reusable workflow they wire in) at a **specific Git tag**,
not `main`, so a change to the template does not silently alter what new services get.
Ship breaking changes as a new version, keep the old one working with a deprecation
note, and track **adoption** — what percent of new services use the current template
version? That metric reappears, front and centre, in.

#### Custom actions and escape hatches

The built-in actions cover most needs, but you can write **custom actions** (a Node
module) to do platform-specific work: open a GitOps PR, create a namespace via your
Namespace Operator, or request a secret via ESO. Custom actions are how the
scaffolder fans a single request across all five planes — the orchestration from, realized. And because golden paths are not cages, a good template offers
**escape-hatch parameters** (e.g. an advanced page to override the base image), kept
default-off and visible.

---

### 2. Why it matters for platform engineering

The scaffolder is where the IDP stops *describing* services and starts *creating* them.
It is the single highest-leverage piece of the developer control plane: one well-made
template means every new service across the org starts on the paved road, with security
and observability wired in, catalogued and deployable from minute one. That is how a
platform makes the Nth team as fast as the first and how "golden path"
stops being a slide and becomes a button.

It also unifies the whole course. A single `fetch → publish → register` template pulls
in your Dockerfile, your pipeline template, your chart, and your
 catalog entry — and sets up the custom actions that will drive /8
provisioning in Project 4. The template *is* the golden path, and the golden path is the
product.

---

### 3. Mental model

```text
 SOFTWARE TEMPLATE = a FORM (parameters) + a SEQUENCE (steps) over a SKELETON
 ───────────────────────────────────────────────────────────────────────────

 parameters → the questions you ask the developer (keep them few: convention!)
 skeleton → real files with ${{ values.* }} — your defaults, baked in
 steps → fetch:template → publish:github → catalog:register (+ dispatch)
 outputs → each step feeds the next (${{ steps.publish.output.remoteUrl }})
 product → pin to a TAG, version it, measure adoption, offer escape hatches
 orchestration → custom actions fan the request across the five planes

 One line: ask little, generate a lot — the paved road as a one-click action.
```

One sentence: **a template is a form plus an ordered set of actions that renders your
golden-path skeleton and registers the result — self-service provisioning, realized.**

---

### 4. Minimal implementation

The smallest useful template asks for a name, renders a one-file skeleton, and
publishes it. Here is the shape (the lab builds the full Go version):

```yaml
apiVersion: scaffolder.backstage.io/v1beta3
kind: Template
metadata:
 name: go-microservice
 title: Go Microservice
 description: Create a production-ready Go service on the golden path
spec:
 owner: team-platform
 type: service
 parameters:
 - title: Service information
 required: [name, owner]
 properties:
 name:
 title: Service name
 type: string
 pattern: "^[a-z][a-z0-9-]*$"
 owner:
 title: Owning team
 type: string
 ui:field: OwnerPicker # reads Groups from the catalog
 steps:
 - id: fetch
 name: Render the skeleton
 action: fetch:template
 input:
 url:./skeleton
 copyWithoutTemplating: [".github/workflows/*"]
 values:
 name: "${{ parameters.name }}"
 owner: "${{ parameters.owner }}"
 - id: publish
 name: Create the GitHub repo
 action: publish:github
 input:
 repoUrl: "github.com?owner=your-org&repo=${{ parameters.name }}"
 - id: register
 name: Register in the catalog
 action: catalog:register
 input:
 repoContentsUrl: "${{ steps.publish.output.repoContentsUrl }}"
 catalogInfoPath: /catalog-info.yaml
 output:
 links:
 - title: Open the new repository
 url: "${{ steps.publish.output.remoteUrl }}"
```

Notice how little the developer supplies (a name and a team) versus how much they get
(a whole repo, catalogued). That asymmetry — **ask little, generate a lot** — is the
entire value. The lab fleshes out the skeleton with a real Go service, Dockerfile,
chart, CI, and descriptor.

---

### 6. Production considerations

- **Pin to tags, not `main`.** Reference the template and the reusable workflow it
 wires in at a specific version, so new services are reproducible and template changes
 are deliberate.
- **Keep parameters minimal.** Every extra field is cognitive load and a chance to pick
 the wrong thing. Supply defaults by convention; ask only for what is service-specific.
- **Make the skeleton the source of truth for defaults.** Security (non-root, signed
 images, SBOM) and observability (OTel wiring) belong in the skeleton so they are
 guaranteed, not optional.
- **Handle partial failure.** If `publish:github` succeeds but `catalog:register`
 fails, the developer has a repo that is invisible to the catalog. Make steps
 idempotent and surface clear errors.
- **Govern template sprawl.** Ten near-identical templates are as bad as none. Prefer a
 few parameterized golden paths over a template per team.
- **Measure adoption and escape-hatch use.** Track which template version new services
 use and how often advanced overrides are set — both are product-feedback signals.

---

### 7. Common mistakes

- **A template with twenty required fields.** It reproduces the setup friction it was
 meant to remove. *Fix:* convention over configuration; sensible defaults.
- **Referencing `main` instead of a tag.** New services silently change when the
 template does. *Fix:* pin template and reusable-workflow versions.
- **Forgetting `catalog:register`.** Services get created but never appear in the
 catalog, so the inventory is incomplete from day one. *Fix:* always register; verify
 the entry shows up.
- **GitHub Actions expressions eaten by the scaffolder.** `${{ github.sha }}` in the
 skeleton's workflow gets templated away. *Fix:* `copyWithoutTemplating` for workflow
 files.
- **Re-authoring CI in the skeleton.** Pasting a full pipeline instead of consuming the
 platform's reusable workflow. *Fix:* the skeleton's CI should `uses:` the 
 template.
- **No escape hatch.** Teams with a legitimate variation fork the template and vanish
 from your metrics. *Fix:* default-off advanced parameters, kept visible.

---

## Backstage Plugins

> A catalog entry becomes genuinely useful when its page shows **live** data:
> deployment status, running pods, dashboards, and cost — all in one place. Plugins are
> how Backstage pulls those in. This module covers the plugin architecture, the
> official plugins for **ArgoCD**, **Kubernetes**, **Grafana**, and **cost**, the
> annotations that wire them to catalog entities, and when to build a custom plugin.

running Backstage app. Live plugin data needs the backing systems (ArgoCD, a cluster,
Grafana) — all **optional**; the lesson works with the catalog you already have.

### 1. Concept

#### Why plugins: the single pane of glass

A service page that lists only metadata ("owned by team-payments, lifecycle
production") answers *who* but not *how is it doing right now*. Plugins close that gap
by pulling runtime truth from the systems you already run — turning the catalog entry
into a **single pane of glass**:

- **ArgoCD** → is it in sync? healthy? what version is deployed? (your GitOps
 state)
- **Kubernetes** → which pods, deployments, and events are live? (your /10
 runtime)
- **Grafana** → the service's golden-signal dashboard, embedded. (your 
 observability)
- **Cost** → what is this team/service spending? (your FinOps data)

That is the monitoring plane surfaced in the developer control plane,
exactly where a developer is already looking.

#### Plugin architecture: frontend + backend

Recall from that *everything is a plugin*. A plugin typically has two
halves:

- **Frontend plugin** (React) — the cards, tabs, and pages shown in the UI. For entity
 plugins, you add a card to the entity page layout in `packages/app`.
- **Backend plugin** (Node.js) — a service that talks to the external system (ArgoCD's
 API, the Kubernetes API, Grafana) and exposes a clean API the frontend calls, so
 credentials never touch the browser.

```text
 Entity page (React) Backstage backend (Node.js)
 ┌───────────────────────┐ calls ┌───────────────────────────┐
 │ ArgoCD card │ ───────────► │ argocd backend ──► ArgoCD │
 │ Kubernetes card │ ───────────► │ kubernetes ──► cluster│
 │ Grafana dashboard │ ───────────► │ (proxy) ──► Grafana│
 │ Cost card │ ───────────► │ cost backend ──► billing│
 └───────────────────────┘ └───────────────────────────┘
 which entity? ▲
 answered by ANNOTATIONS on catalog-info.yaml
```

#### Annotations bind plugins to entities

A plugin needs to know *which* ArgoCD app or *which* pods belong to *this* entity. That
mapping lives in the entity's `catalog-info.yaml` **annotations** — the ones you
already added in 

```yaml
metadata:
 annotations:
 argocd/app-name: checkout-service # ArgoCD plugin
 backstage.io/kubernetes-id: checkout-service # Kubernetes plugin (label selector)
 grafana/dashboard-selector: "tags @> 'checkout-service'" # Grafana plugin
```

This is why the catalog is the substrate: the annotations are the wiring
that lets each plugin find its slice of reality for a given service. Govern them — a
service that is missing `argocd/app-name` silently shows no deploy status.

#### The official plugins

Backstage has a large plugin ecosystem — some maintained by the core project, many by
the community (notably **Roadie**). For the four capabilities here:

- **ArgoCD** (`@roadiehq/backstage-plugin-argo-cd`) — shows sync/health status and
 history on the entity page. Reads `argocd/app-name`.
- **Kubernetes** (`@backstage/plugin-kubernetes`) — shows deployments, pods, and events
 for the entity across configured clusters. Reads `backstage.io/kubernetes-id` (a
 label selector). Needs a cluster and a service-account token.
- **Grafana** (`@roadiehq/backstage-plugin-grafana`) — embeds dashboards and alert
 state. Reads a dashboard selector annotation; proxied through the backend.
- **Cost** (`@backstage/plugin-cost-insights`) — a frontend that renders cost trends;
 you supply a backend data source (OpenCost/Kubecost or cloud billing).

> Plugin APIs evolve across Backstage's "old" and "new" backend systems. Pin your
> Backstage version and follow each plugin's install guide for the matching version —
> this is the upgrade discipline from.

#### Building a custom plugin

When no official plugin fits — an internal system, a bespoke scorecard, a team's
on-call schedule from an in-house tool — you build a **custom plugin** with the
Backstage plugin SDK (`yarn backstage-cli new --select plugin`). You write a React
frontend card and (if it needs credentials or server logic) a Node backend. A custom
plugin is also how you surface your **platform API** directly in the
portal. Build these sparingly: each is code you own and upgrade. Prefer configuration
and official plugins; build only where you add unique value.

---

### 2. Why it matters for platform engineering

Plugins are what make the portal *sticky*. A catalog alone is a nice directory;
a catalog whose pages show live deploy status, running pods, the right dashboard, and
cost is where developers actually start their day. That stickiness is adoption, and
adoption is the scoreboard.

Plugins are also the payoff for everything you built in earlier phases. The ArgoCD
plugin surfaces Project 2's GitOps; the Kubernetes plugin surfaces Project 1's clusters
and namespaces; the Grafana plugin surfaces Project 3's observability; the cost plugin
previews 's FinOps. The platform's value was always there — plugins make it
*visible* in one place, which is often the difference between a capability existing and
a developer using it.

---

### 3. Mental model

```text
 PLUGINS = live data from the systems you already run, on the entity page
 ────────────────────────────────────────────────────────────────────────

 frontend (React card) ◄── calls ──► backend (Node) ──► external system
 ▲
 which entity's data? ── answered by ANNOTATIONS in catalog-info.yaml

 ArgoCD → deploy/sync Kubernetes → pods/events
 Grafana → dashboards Cost → spend

 Build CUSTOM only when no official plugin fits (and to surface YOUR platform API).
```

One sentence: **plugins turn a catalog entry into a single pane of glass by binding
live data from your existing systems to the entity through annotations.**

---

### 4. Minimal implementation

The smallest plugin win is the Kubernetes plugin showing pods for one service. Three
moves: install, configure a cluster, annotate the entity.

```bash
## 1. Install the frontend + backend packages (from the app root)
yarn --cwd packages/app add @backstage/plugin-kubernetes
yarn --cwd packages/backend add @backstage/plugin-kubernetes-backend
```

```yaml
## 2. app-config.yaml — point Backstage at a cluster
kubernetes:
 serviceLocatorMethod:
 type: multiTenant
 clusterLocatorMethods:
 - type: config
 clusters:
 - name: dev
 url: ${KUBE_API_URL}
 authProvider: serviceAccount
 serviceAccountToken: ${KUBE_SA_TOKEN}
```

```yaml
## 3. catalog-info.yaml — bind the entity to its workloads
metadata:
 annotations:
 backstage.io/kubernetes-id: checkout-service
```

Add the Kubernetes tab to the entity page in `packages/app/src/components/catalog/EntityPage.tsx`,
reload, and the `checkout-service` page now lists its live pods, deployments, and
events. The same install → configure → annotate pattern repeats for ArgoCD, Grafana,
and cost. The lab does all four and sketches a custom plugin.

---

### 6. Production considerations

- **Keep credentials in the backend.** Plugin backends hold powerful tokens (cluster
 access, ArgoCD, billing). Source them from your secrets manager (ESO/Vault), never in
 `app-config` or the frontend.
- **Govern annotations.** A plugin only works if the entity is annotated. Bake the
 required annotations into the golden-path skeleton and validate them,
 so every service lights up every plugin by default.
- **Mind read-access scope.** The Kubernetes and ArgoCD plugins need read access across
 namespaces/apps. Use least-privilege, read-only service accounts.
- **Pin versions and test upgrades.** Plugins break across Backstage major upgrades.
 Pin, read changelogs, and test plugins against a canary before upgrading everyone.
- **Fail gracefully.** A down backend (Grafana, billing) should degrade the card, not
 the whole page. Prefer plugins that handle missing data cleanly.
- **Build custom plugins sparingly.** Each is owned code with an upgrade cost. Justify
 it against configuration or an existing community plugin first.

---

### 7. Common mistakes

- **Missing annotations, blank cards.** The plugin is installed but the entity lacks
 `argocd/app-name` or `kubernetes-id`, so it shows nothing. *Fix:* annotate in the
 skeleton and validate.
- **Secrets in the frontend or `app-config`.** Putting a cluster token where the
 browser or Git can see it. *Fix:* backend plugin + secrets manager.
- **Over-broad cluster access.** Granting the Kubernetes plugin cluster-admin. *Fix:*
 read-only, least-privilege service accounts.
- **Version drift.** Installing a plugin version that mismatches your Backstage
 backend. *Fix:* follow the plugin's versioned install guide; pin Backstage.
- **Building custom when official exists.** Reinventing the ArgoCD card. *Fix:* survey
 the ecosystem (core + Roadie) before writing code.
- **One giant entity page.** Twelve plugin cards nobody reads. *Fix:* curate the layout
 to the few signals developers actually use.

---

## Golden Paths

> A golden path is the recommended, supported, opinionated way to do a common thing —
> and it is the product your whole platform exists to deliver. 
> defined it; and 15.5 built the pieces. This module assembles them into a
> *complete, end-to-end* golden path: everything it must include, the escape hatches
> that keep it honest, how you version it, and how you measure whether anyone uses it.

15.5; the versioning ideas from
.

### 1. Concept

#### A golden path is end-to-end, or it is not golden

 defined a golden path as the paved road for a specific journey — "create a
new Go service." The crucial word is **end-to-end**. A template that scaffolds a repo
but leaves the developer to wire CI, deployment, observability, and docs by hand is not
a golden path; it is a nicer starting line for the same marathon. A golden path carries
a change from *idea* to *running, observable, documented production service* without
the developer leaving the paved road.

So the golden path is not any single tool from this phase — it is the **composition** of
them, orchestrated behind one request.

#### What a golden path must include

A complete golden path for a service wires in, by default, every capability you built
across the course:

- **Repository scaffold** — a working skeleton from the Backstage template: code, structure, sane config.
- **CI/CD pipeline** — the platform's reusable workflow, consumed, not
 re-authored: lint, test, build, scan.
- **Container build and push** — a secure multi-stage image to the registry.
- **IaC for cloud resources** — if the service needs a database or bucket, provisioned
 via Terraform/Crossplane, not a ticket.
- **GitOps deployment config** — an ArgoCD `Application` and manifests so the service
 deploys itself.
- **Observability** — the OpenTelemetry SDK pre-configured and a default dashboard — wired in, not bolted on.
- **Security** — non-root containers, a signed image, and an SBOM by default; least-privilege access.
- **Documentation** — a TechDocs skeleton so the service is documented from day one.

```text
Developer requests "new service" in the portal
 │
 ▼ the golden path creates, in one flow:
 ├─ GitHub repo (skeleton: code, Dockerfile, chart, catalog-info.yaml)
 ├─ CI/CD workflow (consumes the platform template)
 ├─ config-repo entry (GitOps Application)
 ├─ namespace in the dev cluster (via the Namespace Operator — Project 1)
 ├─ monitoring dashboard (from a Grafana template)
 ├─ secret wiring (via External Secrets)
 └─ docs skeleton (TechDocs)
 │
 ▼
Developer starts coding in a pre-wired, production-ready service
```

Every item on that list is something a team used to do by hand (or skip). The golden
path makes the secure, observable, deployable choice the **default** — "make the right
thing the easy thing", by construction.

#### Escape hatches: documented, reviewed, visible

From and 06.4: golden paths are the *easiest* route, not a mandatory cage.
Real teams have legitimate exceptions — a service that needs a database the path does
not support yet, or a non-standard base image. A golden path without escape hatches
gets **forked and routed around**, and you lose all visibility. So make deviation a
**process, not a rebellion**:

- **Documented.** A written way to request a deviation, with the trade-offs stated.
- **Reviewed.** Higher-stakes deviations get a lightweight platform sign-off (a label +
 approval), not a silent fork.
- **Visible and counted.** Every escape hatch is logged and shows up in a report. A
 frequently used hatch is a **bug report about your defaults** — change the path.

The rule holds: *guardrails are for safety (mandatory); paths are preferences (win by
being better).* Never use a safety mechanism to enforce a preference.

#### Versioning and migration

A golden path has consumers, so it is a product with versions — the exact discipline
from, now applied to the whole path:

- **Semantic versions.** `v1`, `v1.1`, `v2`. Non-breaking improvements flow to
 consumers; breaking changes mean a new major.
- **Deprecate, do not delete.** When `v2` lands, `v1` keeps working with a warning and
 a sunset date.
- **Migration tooling.** Do not just publish a guide — ship a **codemod or bot** that
 opens the PR to move a service from `v1` to `v2`. Migration you make easy actually
 happens; migration you document gets ignored.

> You cannot update a golden path in place for 200 services by editing one file —
> because the path is distributed across each service's repo. Versioning plus migration
> tooling is how you evolve it safely.

#### Adoption metrics: the scoreboard

A beautiful golden path nobody uses is a failed product. Measure, from
day one:

- **Coverage** — what percent of production services are *on* a golden path at all?
- **Version adoption** — what percent are on the *current* version vs. a deprecated
 one? Slow migration means your migration path is too painful.
- **Escape-hatch rate** — how often is each hatch used? A spike says the default is
 wrong.
- **Time-to-adopt** — how long from `v2` release to the fleet moving? This measures
 your migration tooling.

Pair these with the north-star from **time-to-first-production-deployment**
for a new service on the path. If the golden path works, that number is hours, not
weeks.

---

### 2. Why it matters for platform engineering

This module is the keystone of the phase. The catalog, templates, and plugins are
components; the **golden path is the product** they combine into — the single thing a
platform team can point to and say "this is how you ship here, and it is genuinely the
easiest way." Everything in Projects 1–3 was building the capabilities; the golden path
is where they become *self-service* for real.

It is also where platform engineering is most clearly **product management, not just
engineering**. Owning a golden path means owning its versioning, migrations, escape
hatches, support, and adoption — the same work a product manager does for external
customers, aimed at your own developers. Teams that do this well get security and
reliability *by default* across the whole fleet, from one place.

---

### 3. Mental model

```text
 GOLDEN PATH = the end-to-end paved road, owned as a product
 ──────────────────────────────────────────────────────────

 MUST INCLUDE (by default, not opt-in):
 scaffold · CI/CD · image · IaC · GitOps · observability · security · docs

 KEEP IT HONEST:
 escape hatches = documented + reviewed + visible/counted (not forks)
 guardrails (safety) mandatory · paths (preference) win by being better

 OWN IT AS A PRODUCT:
 version (v1→v2) · deprecate not delete · SHIP migration tooling
 measure: coverage · version adoption · hatch rate · time-to-first-deploy

 One line: make the secure, observable, deployable choice the DEFAULT —
 end to end — then version it and prove adoption.
```

One sentence: **a golden path is the complete, opinionated, self-service route to
production, owned and versioned like a product and measured by adoption.**

---

### 4. Minimal implementation

You already built the pieces; the smallest "golden path" is composing them and writing
down what "done" means. Take the template and ensure its skeleton wires in
*every* required capability by default, then publish a one-page definition:

```text
Golden path: "standard Go service" (v1)
 scaffold → Backstage template `go-microservice`
 CI/CD → skeleton CI uses platform workflow `app-ci@v2`
 image → multi-stage non-root Dockerfile, signed in CI
 GitOps → skeleton includes an ArgoCD Application
 observability → OTel SDK pre-wired + default dashboard
 security → non-root, SBOM, least-privilege RBAC
 docs → TechDocs skeleton
 escape hatch → `advanced` params (base image), default-off, logged
 owner + support → team-platform, #platform-support, SLO published
 adoption metric → % of prod Go services created from this template @ current version
```

That one page *is* the golden-path contract: what it includes, who owns it, how to
deviate, and how you will know it is working. The lab turns it into a reusable
checklist you can apply to any golden path.

---

### 6. Production considerations

- **"By default" is the whole game.** If security, observability, or GitOps are opt-in
 steps rather than baked into the skeleton, teams will skip them. Make them automatic.
- **Ship migration tooling, not just guides.** A bot that opens the `v1 → v2` PR is the
 difference between a migration that happens and one that stalls for a year.
- **Treat a stale golden path as an incident.** An out-of-date path leads people
 confidently into a ditch. Own it like production software.
- **Make escape-hatch usage a feedback loop.** Review hatch metrics regularly; a
 popular hatch is a backlog item to fold into the default path.
- **Keep the number of paths small.** A few well-maintained golden paths beat a dozen
 half-maintained ones. Parameterize before you proliferate.
- **Publish the contract.** Owner, support channel, SLO, versioning policy, and
 deprecation calendar — consumers need to know what they can depend on.

---

### 7. Common mistakes

- **A "golden path" that is only a scaffold.** It creates a repo but not CI,
 deployment, observability, or docs. *Fix:* end-to-end or it is not golden.
- **Security and observability as optional steps.** Left to the developer, they get
 skipped. *Fix:* bake them into the skeleton as defaults.
- **No escape hatch, so teams fork.** Forbidding deviation hides it. *Fix:* a
 documented, reviewed, counted hatch.
- **Updating in place with no versioning.** Changing the path under 200 services at
 once. *Fix:* semantic versions, deprecation, and migration tooling.
- **Publishing a migration guide but no tooling.** Adoption of `v2` stalls. *Fix:* ship
 a bot/codemod that opens the bump PR.
- **No adoption metric.** You cannot tell if the product succeeded. *Fix:* track
 coverage, version adoption, hatch rate, and time-to-first-deploy.

---

## Platform CLI Tools

> A portal is one interface to the platform; a **CLI** is the other — and for many
> developers, the one they live in. 
> said the platform API is the product and the portal is just a client; the CLI is a
> second client of that same API. This module covers when to build a CLI, the Go +
> Cobra + Viper stack, the commands a platform CLI offers, distribution and config, and
> the discipline that keeps it thin: **the CLI wraps API calls, not business logic.**

1.22+**. The lab builds a real CLI locally.

### 1. Concept

#### Why a CLI, when you have a portal

A portal is great for discovery, browsing, and one-off actions. But developers work in
a terminal, and the highest-friction tasks are **frequent and repetitive**: spin up an
environment, deploy a version, tail logs, check cost. For those, a CLI is faster than
clicking, scriptable in CI, and composable with the rest of the shell. It is the same
move as every other interface in this phase — meet developers where they already are
and remove friction.

Crucially, the CLI is **another client of the platform API**, not a
separate platform. Portal, CLI, and CI all produce or consume the same declarative
requests; the CLI just happens to be the terminal-shaped door. Build one **when a task
is frequent enough that the terminal beats the portal** — not reflexively.

#### The stack: Go + Cobra + Viper

The de facto standard for platform CLIs (kubectl, helm, gh, argocd are all built this
way) is:

- **Go** — single static binary, cross-compiles to every OS/arch, trivial to
 distribute (no runtime to install).
- **[Cobra](https://cobra.dev/)** — the command framework: subcommands, flags, args,
 help, and shell completions, all generated for you.
- **[Viper](https://github.com/spf13/viper)** — configuration: merges flags, env vars,
 and config files with a clear precedence, so `--env`, `PLATFORM_ENV`, and
 `~/.platform/config.yaml` all work.

```text
 platform <command> <subcommand> [flags]
 └── Cobra: parses, routes, validates, --help, completions
 └── your handler: build a request, call the platform API, print the result
 └── Viper: resolves config (flag > env > file > default)
```

#### The command surface

A platform CLI mirrors the platform's capabilities as verbs a developer thinks in:

```bash
platform env list
platform env create --name my-feature-env --base dev
platform deploy --app my-service --version sha-abc123 --env dev
platform logs --app my-service --env prod --since 1h
platform cost --team payments --month current
```

Notice the shape: **noun → verb → flags** (`env create`, not `create-env`). Each command
maps to a platform-API call — `env create` POSTs an environment request; `deploy` sends
a deployment request that GitOps fulfils; `logs` proxies to the logging
backend; `cost` queries FinOps data. The CLI is a **friendly
façade over the API**, nothing more.

#### Config: flags, env vars, and a config file

Viper gives a predictable precedence so the CLI behaves well both interactively and in
automation:

```text
highest ──► command-line flag (--env prod)
 environment variable (PLATFORM_ENV=prod) ← great for CI
 config file (~/.platform/config.yaml)
lowest ──► built-in default
```

```yaml
## ~/.platform/config.yaml
api_url: https://platform.internal.example.com
default_env: dev
team: payments
```

A developer sets their team once in the file; CI overrides with env vars; a one-off run
overrides with a flag. Same binary, no surprises.

#### Distribution, versioning, and auto-update

A CLI has users, so it is a product (the recurring theme). Ship it like one:

- **Distribution.** Publish cross-compiled binaries to **GitHub Releases**, a
 **Homebrew tap** (`brew install your-org/tap/platform`), or an internal package
 manager/registry. [GoReleaser](https://goreleaser.com/) automates building and
 publishing all platforms from one tag.
- **Versioning.** Embed the version at build time (`platform version`), and check for
 updates so users are not stranded on an old build. Breaking changes to flags or
 output are versioned like any API.
- **Shell completions.** Cobra generates **bash, zsh, and fish** completions for free —
 a big DX win (`platform completion zsh`). Ship them.

#### The cardinal rule: wrap the API, do not become it

The single most important design discipline: **the CLI contains no business logic.** It
parses input, calls the platform API, and formats output. All the real work —
provisioning, deployment orchestration, policy — lives behind the API,
where the portal and CI reach it too. The moment the CLI starts doing orchestration
itself, you have logic that only terminal users get, that CI and the portal cannot
reuse, and that you must reimplement elsewhere. Keep it thin.

---

### 2. Why it matters for platform engineering

The CLI is the interface that proves the API-first principle pays off. If your platform
API is well-designed, adding a CLI is a weekend of Cobra scaffolding — a
thin client over endpoints that already exist. If it is *not* — if logic lives in the
portal — the CLI either can't be built or duplicates that logic, and you feel the design
debt immediately. Building the CLI is a test of whether you really built a platform API
or just a portal.

It is also where a lot of developer goodwill is earned. `platform deploy --app x
--version y --env dev` from a terminal or a CI job, with completions and sane config, is
the kind of frictionless tool that drives adoption — the scoreboard from.
In Project 4, this CLI sits beside Backstage as the second door to the same platform.

---

### 3. Mental model

```text
 PLATFORM CLI = a thin, terminal-shaped CLIENT of the platform API
 ────────────────────────────────────────────────────────────────

 Go (static binary) + Cobra (commands) + Viper (config)
 shape: noun → verb → flags (env create, deploy, logs, cost)
 config: flag > env var > ~/.platform/config.yaml > default
 ship: GitHub Releases / Homebrew / GoReleaser · completions · `version`
 RULE: wrap API calls, NEVER business logic (logic lives behind the API,
 where the portal and CI reach it too)

 One line: another door to the SAME platform API — thin, fast, scriptable.
```

One sentence: **a platform CLI is a thin Cobra client that turns terminal commands into
platform-API calls — a second interface to the product, never a second implementation.**

---

### 4. Minimal implementation

The smallest real CLI is a Cobra root command with one subcommand. `main.go` just
executes the root:

```go
// main.go
package main

import "github.com/your-org/platform-cli/cmd"

func main() {
 cmd.Execute()
}
```

```go
// cmd/root.go (abridged)
package cmd

import (
 "github.com/spf13/cobra"
)

var rootCmd = &cobra.Command{
 Use: "platform",
 Short: "The platform CLI — a thin client of the platform API",
}

func Execute() {
 cobra.CheckErr(rootCmd.Execute())
}
```

```go
// cmd/env.go (abridged) — `platform env list`
package cmd

import (
 "fmt"

 "github.com/spf13/cobra"
)

var envCmd = &cobra.Command{Use: "env", Short: "Manage environments"}

var envListCmd = &cobra.Command{
 Use: "list",
 Short: "List environments",
 RunE: func(cmd *cobra.Command, args []string) error {
 // In a real CLI: call the platform API and print the result.
 fmt.Println("dev\nstaging\nprod")
 return nil
 },
}

func init() {
 envCmd.AddCommand(envListCmd)
 rootCmd.AddCommand(envCmd)
}
```

That compiles into a single `platform` binary with `--help`, subcommands, and
completions, all for free. The handler's one job is "call the API, print the result" —
the lab fleshes out `env`, `deploy`, and `logs` with flags, Viper config, and a
`version` command, keeping every handler a thin wrapper.

---

### 6. Production considerations

- **Keep it thin.** No orchestration or policy in the CLI — only input, API call,
 output. Logic in the CLI is logic the portal and CI cannot reuse.
- **Version and auto-update.** Embed the build version, expose `platform version`, and
 nudge users off stale builds. Version breaking flag/output changes like an API.
- **Config precedence must be predictable.** Flag > env var > file > default, so the CLI
 behaves identically for humans and in CI. Document it.
- **Authenticate like everything else.** The CLI should use the org's SSO/OIDC, not a
 bespoke token scheme. It is a client of the same API the portal secures.
- **Ship completions and good `--help`.** These are cheap DX wins that drive adoption;
 Cobra generates them.
- **Automate releases.** GoReleaser + a tag → binaries for every OS/arch, a Homebrew
 tap, and checksums. Manual release builds rot.
- **Output for both humans and machines.** A `--output json` mode makes the CLI usable
 in scripts and CI, not just at a prompt.

---

### 7. Common mistakes

- **Business logic in the CLI.** Orchestration that only terminal users get and CI/the
 portal cannot reuse. *Fix:* wrap the platform API; keep logic behind it.
- **Over-engineering a tool nobody asked for.** A sprawling CLI for rare tasks. *Fix:*
 build commands for *frequent* friction; let the portal handle the rest.
- **Inconsistent config.** Flags, env, and file disagree or have murky precedence.
 *Fix:* Viper with documented precedence (flag > env > file > default).
- **No versioning or update path.** Users stuck on old builds with broken assumptions.
 *Fix:* embedded version, `version` command, update check, versioned changes.
- **Hand-built, hand-shipped releases.** Slow, error-prone, missing platforms. *Fix:*
 GoReleaser from a tag.
- **Reinventing auth.** A custom token file instead of org SSO. *Fix:* reuse the
 platform's identity (OIDC), least-privilege.

---

## Developer Portal Documentation

> A golden path makes the right thing easy; **documentation makes it well-lit.** The
> paved road is only paved if a developer can read where it goes, how to run the
> service, what to do when it pages them, and *why* it was built this way. This module
> covers **TechDocs** and **docs-as-code** (MkDocs docs that live with the code and
> render in the portal), a documentation structure for services, **ADRs**, API docs,
> **runbook standards**, and the rule that the platform itself must be documented best
> of all.

plugin) and 15.3 (the `techdocs-ref` annotation).
Python + `pip` for a local MkDocs preview (optional).

### 1. Concept

#### Docs-as-code: documentation lives with the code

The failure mode of documentation is a separate wiki that drifts from reality: the code
changes, the wiki does not, and within months the docs are confidently wrong — worse
than none. **Docs-as-code** fixes this the same way GitOps fixed config: put the
documentation **in the repository, next to the code**, written in Markdown, reviewed in
the same pull request as the change it describes, and versioned with it. When docs are a
PR-reviewable artifact, they stay honest.

#### TechDocs: docs-as-code, rendered in the portal

**TechDocs** is Backstage's documentation plugin. It takes
[MkDocs](https://www.mkdocs.org/)-based Markdown from a service's repo and renders it as
a browsable site **on that service's catalog page**. The developer reading about
`checkout-service` in the portal sees its docs right there, generated from the repo —
no separate wiki, no drift.

The wiring is a single annotation you already met in 

```yaml
## catalog-info.yaml
metadata:
 annotations:
 backstage.io/techdocs-ref: dir:. # docs live in this repo
```

Plus two files in the repo: an `mkdocs.yml` and a `docs/` directory.

```text
 service repo Backstage
 ┌───────────────────────┐ ┌──────────────────────────┐
 │ mkdocs.yml │ build + │ checkout-service page │
 │ docs/ │ publish │ └─ Docs tab (rendered │
 │ index.md │ ─────────► │ from docs/ ) │
 │ architecture.md │ │ │
 │ runbooks/… │ └──────────────────────────┘
 └───────────────────────┘
 docs-as-code same docs, in the portal
```

#### A standard documentation structure

Convention over configuration applies to docs too: a predictable
structure means developers always know where to look, and the golden-path skeleton can
ship it by default. A solid baseline for a service:

- **Overview / `index.md`** — what the service does, who owns it, how to run it
 locally. The "I just found this service, now what?" page.
- **Architecture** — how it works, its dependencies, and a diagram. The context a new
 maintainer needs.
- **Runbooks** — operational procedures: what to do when a specific alert fires.
- **API** — the interface contract (often the OpenAPI spec surfaced as an API entity,
 ).
- **ADRs** — the record of *why* the important decisions were made.

#### Architecture Decision Records (ADRs)

Code shows *what* the system does; it rarely shows *why* it is that way. Six months
later, nobody remembers why you chose Postgres over DynamoDB, and someone "fixes" it by
switching — re-learning the original reasons the hard way. An **ADR** is a short,
immutable record of one significant decision: its context, the options, the choice, and
the consequences.

```text
ADR 0007 — Use PostgreSQL for the orders datastore
 Status: Accepted
 Context: We need strong consistency and relational queries for orders.
 Decision: Use managed PostgreSQL (Cloud SQL).
 Consequences: Operable and familiar; must manage connection limits and backups.
```

ADRs are **append-only**: you do not edit a past decision, you supersede it with a new
ADR. The log becomes the architecture's memory. This course uses ADRs for its own
project decisions — see the shared
ADR template.

#### API documentation

An interface nobody can read is a support ticket generator. Catalogue each service's
API from its **OpenAPI** spec as an API entity so consumers browse the
contract in the portal and self-serve instead of asking the owning team — a direct cut
to *waiting friction*. Keep the spec in the repo and treat it as docs-as-
code too.

#### Runbook standards: every alert links to a runbook

Observability tells you *something is wrong*; a **runbook** tells you *what
to do about it*. The standard that makes this real is simple and strict:

> **Every alert must link to a runbook.** No runbook, no alert.

A good runbook is written for a stressed on-call engineer at 3am: the symptom, how to
confirm it, the likely causes, the step-by-step mitigation, and how to escalate. The
alert's annotation carries the link (`runbook_url`), so the pager notification is one
click from the fix. Runbooks live in `docs/runbooks/` as docs-as-code, rendered in
TechDocs, so they are versioned and discoverable — not a stale Google Doc.

#### The platform must be the best-documented thing you own

"Knowledge and support" are in the definition of a platform. A platform is
a product with customers, and an undocumented product does not get adopted. So the
platform's *own* docs — how to use each golden path, the platform API reference, the support channel and SLOs (the platform contract from ) — must be
exemplary. If your developers cannot find how to create a service without asking you,
you have recreated the ticket queue in documentation form. Dogfood TechDocs for the
platform itself.

---

### 2. Why it matters for platform engineering

Documentation is the difference between a golden path that is *discoverable* and one
that is tribal knowledge. You can build the best template, catalog, and CLI in the
world, but if a developer cannot find how to use them — or cannot tell, at 3am, what to
do when a service pages them — the platform's value is locked away. Docs-as-code plus
TechDocs is how the paved road gets signposts and streetlights.

It also closes the loop on the whole phase. The catalog (15.3) says *what exists*;
plugins (15.5) say *how it is doing*; TechDocs says *how it works, how to run it, and
why*. Together they make the portal a place developers can actually self-serve — which
is the entire point of the developer control plane. And runbooks tie the control plane
back to the monitoring plane: an alert from Project 3 becomes an actionable, documented
response.

---

### 3. Mental model

```text
 DOCS-AS-CODE + TECHDOCS = the paved road, well-lit
 ──────────────────────────────────────────────────

 docs live in the repo (Markdown) → reviewed in the SAME PR as the code
 │ mkdocs.yml + docs/ → stays honest, versioned with the code
 ▼
 TechDocs renders them on the service's catalog page (one annotation)

 Standard set: overview · architecture · runbooks · API · ADRs
 ADR = WHY a decision was made (append-only memory)
 Runbook = WHAT to do when an alert fires (every alert links to one)
 Meta = the PLATFORM itself must be the best-documented product you own

 One line: put the docs with the code, render them in the portal, and make
 every alert one click from its runbook.
```

One sentence: **documentation is docs-as-code rendered in the portal — overview,
architecture, runbooks, API, and ADRs that live with the code and keep the golden path
discoverable.**

---

### 4. Minimal implementation

The smallest TechDocs setup is two files plus one annotation. An `mkdocs.yml` and a
`docs/index.md` in the service repo:

```yaml
## mkdocs.yml
site_name: checkout-service
nav:
 - Home: index.md
 - Architecture: architecture.md
plugins:
 - techdocs-core
```

```markdown
<!-- docs/index.md -->
## checkout-service

Handles payment and order checkout. Owned by team-payments.

### Run locally

 go run.
```

```yaml
## catalog-info.yaml — point TechDocs at the repo's docs
metadata:
 annotations:
 backstage.io/techdocs-ref: dir:.
```

Preview locally with `mkdocs serve`, and TechDocs renders the same `docs/` on the
service's portal page. From here you add `architecture.md`, a `runbooks/` folder, and an
`adr/` folder — the lab builds the full starter, including an ADR and a runbook.

---

### 6. Production considerations

- **Review docs in the code PR.** Treat a change with no doc update as incomplete. The
 only docs that stay accurate are the ones reviewed alongside the code.
- **Ship docs in the golden path.** The skeleton should include
 `mkdocs.yml`, a `docs/` tree, and the `techdocs-ref` annotation, so every service is
 documented from creation — convention, not an afterthought.
- **Enforce "every alert has a runbook."** Make `runbook_url` a required alert
 annotation and fail CI on alerts that lack it. An alert with no runbook is a 3am
 guessing game.
- **Build TechDocs in CI, not on demand.** For scale and speed, generate docs in a
 pipeline and publish to object storage; Backstage serves the built site rather than
 building per view.
- **Keep ADRs append-only.** Never rewrite history — supersede. The value is the record
 of *why*, including decisions you later reversed.
- **Document the platform best of all.** Dogfood TechDocs for the platform's own golden
 paths, API, and contract. Measure doc coverage like any other quality metric.

---

### 7. Common mistakes

- **A separate wiki.** Docs far from the code drift into confident fiction. *Fix:*
 docs-as-code in the repo, reviewed with the change.
- **Docs that are not part of "done."** Shipping code with no doc update. *Fix:* require
 doc changes in the PR; treat missing docs as a bug.
- **Alerts with no runbook.** The pager fires and on-call guesses. *Fix:* require
 `runbook_url`; no runbook, no alert.
- **No ADRs.** The *why* evaporates and decisions get silently reversed. *Fix:*
 lightweight, append-only ADRs for significant choices.
- **Editing past ADRs.** Rewriting a decision erases the memory. *Fix:* supersede with a
 new ADR; keep the old one.
- **An undocumented platform.** The platform team answers the same questions in Slack
 forever. *Fix:* exemplary, dogfooded platform docs — knowledge and support are part of
 the product.

---

---

## References

- CNCF — [Platforms White Paper](https://tag-app-delivery.cncf.io/whitepapers/platforms/)
- Humanitec — [IDP reference architecture and the Platform Orchestrator](https://humanitec.com/blog/what-is-an-internal-developer-platform)
- [Score](https://score.dev/) — an open workload specification (a platform-API shape)
- [PlatformEngineering.org](https://platformengineering.org/) — reference
- Martin Fowler — [Platform Engineering and the platform-as-a-product idea](https://martinfowler.com/articles/platform-prerequisites.html)
- Backstage — [Getting started and `create-app`](https://backstage.io/docs/getting-started/)
- Backstage — [Backstage architecture overview](https://backstage.io/docs/overview/architecture-overview)
- Backstage — [Authentication and identity](https://backstage.io/docs/auth/)
- Backstage — [Deploying with the community Helm chart](https://github.com/backstage/charts)
- CNCF — [Backstage project](https://www.cncf.io/projects/backstage/)
