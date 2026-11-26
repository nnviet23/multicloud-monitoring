# 13 · Multi-Cluster and Multi-Cloud

> **Project Applicability:** Active in Project — Directly applied in the **k3d** local hub-spoke simulation (hub-k3d, ws-k3d, zure-k3d) using **Kustomize + Argo CD** (instead of Helm) for multi-cluster GitOps.

> One cluster is where every platform starts and where most should stay as long
> as they can. But isolation, availability, data residency, and raw scale
> eventually force a second cluster — and then a tenth — and now you own a
> **fleet**: many API servers, many copies of policy, many desired states that
> must stay identical without anyone hand-editing them. This phase turns "we have
> several clusters" into an engineered capability: segment them on purpose, create
> and upgrade them as code, deliver one source of truth to all of them, and route
> users to the healthy one. It also tells you the honest truth about **multi-cloud**:
> it is almost always more expensive and complex than one cloud, and you should
> name the problem it solves before you pay for it.

## Why this phase matters

Everything up to here assumed a single cluster you could hold in your head. Real
platforms outgrow that. A regulator says "EU data stays in the EU." A region has a
bad morning and takes your whole product down with it. A security review decides the
payments workload needs its own blast radius, not a shared namespace. Each of those
is a *boundary* a namespace cannot draw, and each one adds a cluster.

The trap is that clusters are easy to *create* and brutal to keep *consistent*. Click
three clusters into existence from three consoles and you have three snowflakes:
different versions, different add-ons, different RBAC, and an incident on each that
nobody else's runbook covers. The discipline of this phase is the same control loop
you have used since, lifted to the fleet:

```text
 The snowflake fleet The engineered fleet
 ─────────────────── ─────────────────────
 console-created clusters Git (one desired state for the fleet)
 hand-installed add-ons │
 per-cluster kubectl apply ┌──────────▼──────────┐
 drift nobody notices │ management cluster │
 │ │ CAPI · ArgoCD · RBAC │
 ▼ └───┬───────────┬──────┘
 "which cluster is this reconcile reconcile
 and why is it different?" ▼ ▼
 cluster A cluster B … (add one → it
 (defined, (defined, conforms
 reconciled) reconciled) automatically)
```

This phase gives you the four capabilities that turn a pile of clusters into a
platform:

- **Architecture.** Decide *why* and *how* you split — by environment, team, or
 region — and how clusters discover each other when they genuinely must.
- **Fleet lifecycle.** Treat a cluster as a declarative resource with **Cluster API**:
 create, upgrade, scale, and delete clusters with `kubectl apply`, reproducibly.
- **Multi-cloud, honestly.** Use **Crossplane** and Kubernetes as a portability layer
 *if* the problem demands it — and recognize the common case where multi-cloud buys
 only cost and complexity.
- **Global reach.** Put a cluster near every user, route traffic to the healthy
 region, and fail over automatically when one goes dark.

It is the direct runway to **Capstone 3 — Multi-Cluster GitOps Platform**, where you
bootstrap workload clusters from a management cluster with CAPI, fan apps out with
ApplicationSets, share service visibility across prod regions, and front it all with a
global load balancer. Learn the moves here; assemble them there.

## Multi-Cluster Architecture

> argued
> *why* a platform ends up with more than one cluster and showed the hub-and-spoke
> shape. This module is about the **decisions** that turn a pile of clusters into an
> architecture: which boundary you cut along, where identity lives, how (and whether)
> services talk across clusters, and how one GitOps source of truth reaches the right
> subset of a fleet. The recurring discipline is the course's: add a cluster only for
> a boundary a namespace cannot draw, and connect clusters only when you can name why.

### 1. Concept

#### Start from the boundary, not the cluster count

 listed the forces that push you past one cluster: blast radius, regional
availability, data residency, team ownership, and scale ceilings. The architecture
question is the next one: **along which boundary do you cut?** A cluster is the
strongest isolation unit Kubernetes offers — its own API server, etcd, RBAC, and
failure domain — so you spend one each time you draw a line that a softer boundary
(namespace + quota + NetworkPolicy + RBAC) cannot hold.

Three segmentation axes dominate, and real platforms combine them:

- **Per environment (dev / staging / prod).** The most common first split: it keeps a
 broken dev controller or a noisy load test away from production and gives prod its own
 version, change-freeze calendar, and blast radius — none of which a namespace can draw.
- **Per team / tenant.** A whole cluster for a team (or external tenant) that needs control
 over upgrades, cluster-wide resources (CRDs, admission webhooks), or a hard compliance
 boundary. Expensive — reserve it for genuine isolation, not org-chart tidiness; most teams
 are better served by a namespace with quotas.
- **Per region.** Required for availability (survive a region outage) and residency ("EU
 data stays in the EU") — a boundary physics and law draw for you; you just make it explicit.

These multiply. A modest platform is often an **environment × region** grid —
`dev-eu`, `prod-eu`, `prod-us` — plus a management cluster. The number of clusters is
an *output* of the boundaries you chose, never a target you pick first.

```text
 region → eu-west us-east
 environment ↓ ┌───────────────┐ ┌───────────────┐
 prod │ prod-eu │ │ prod-us │ ← availability + residency
 └───────────────┘ └───────────────┘
 staging │ staging-eu │ (none) ← cost: only where needed
 dev │ dev-eu │ (none)
```

#### The management cluster, and where the brains live

As in 10.5, a **management (hub) cluster** runs the controllers that provision and
deliver to **workload (spoke) clusters** — ArgoCD, Cluster API, policy — and holds the
credentials to reach them. Two delivery directions, recapped because the security
trade-off is central:

- **Push:** the hub holds spoke credentials and applies into each spoke. Simple;
 the hub is a high-value target with wide reach.
- **Pull:** an agent inside each spoke pulls its desired state from Git. The hub needs
 no inbound path to spokes — better blast radius at fleet scale.

The management cluster is the crown jewels: compromise it and you own every workload
cluster. It gets the strictest RBAC, the tightest network exposure, and ideally
pull-based delivery so it never needs standing credentials into production.

#### Multi-cluster traffic: ingress per cluster vs a global front door

Each cluster still has its own ingress/Gateway and its own external IP. Two patterns
put users in front of a fleet:

- **Ingress per cluster.** Every cluster is independently reachable (its own DNS name
 or IP). Simple, and fine when clients know which cluster to hit (internal tools,
 region-pinned apps).
- **Global load balancer in front.** One hostname/anycast IP routes each user to the
 nearest healthy cluster and fails over when a region dies. This is what makes an
 environment × region grid feel like one service. It is the whole of
; here, just know the fleet is
 *built* to sit behind it.

#### Cross-cluster service discovery: the default is "no"

Here is the fact that surprises people: **a Service in cluster A is not reachable from
cluster B.** Each cluster has its own `ClusterIP` range and its own DNS
(`svc.namespace.svc.cluster.local` resolves only locally). Pods do not route to another
cluster's pod network. If `checkout` in `prod-us` needs `payments` in `prod-eu`, nothing
connects them until you build it.

Three tools build it, in rising order of capability and cost:

- **Cilium Cluster Mesh.** Builds on the Cilium CNI you met in
. It connects the pod
 networks of meshed clusters and lets a Service be marked **global**
 (`service.cilium.io/global: "true"`), so it load-balances across clusters and fails
 over automatically. L3/L4, eBPF-fast, no sidecars. Best when you already run Cilium.
- **Istio multi-cluster.** Extends an Istio service mesh across clusters with an
 east-west gateway, giving cross-cluster mTLS, L7 routing, and a unified service
 registry. Powerful, but it is a mesh — real proxy and operational overhead
 (see ).
- **Submariner.** CNI-agnostic: it builds encrypted tunnels between clusters and uses a
 **Lighthouse** DNS component so `service.ns.svc.clusterset.local` resolves across the
 clusterset. Good when clusters run different CNIs and you only need connectivity.

The strongest architectural advice is to **not need it.** Cross-cluster synchronous
calls couple two failure domains — the thing you split clusters to decouple. Prefer
designs where each cluster is self-sufficient and clusters share **data**
(async replication, a message bus, a shared datastore) rather than **live request
paths**. Reserve Cluster Mesh and friends for the genuine cases: active-active data
locality, gradual migration, or a service that truly must span regions.

#### Multi-cluster RBAC: one identity, many enforcers

Ten clusters must not mean ten user databases. The pattern is **centralized identity,
distributed enforcement**:

- **Centralized identity.** Every cluster trusts the same identity provider (OIDC — your
 IdP, Entra ID, Okta, Google). A person or workload has *one* identity across the fleet;
 no per-cluster local accounts or long-lived kubeconfig tokens handed around.
- **Distributed enforcement.** Each cluster still owns its own `Role`/`ClusterRole`
 bindings and decides what that identity may do *there*. A platform group might be
 admin on `dev-eu` and read-only on `prod-eu`. Enforcement is local (the API server
 checks), but the identity it checks is global.

Deliver those bindings the same way you deliver everything else — through GitOps — so
"who can do what, where" is itself declarative and auditable.

#### Multi-cluster GitOps: target segments, not just "everywhere"

's ApplicationSet used `clusters: {}` — deploy to *every* registered cluster.
Real fleets are segmented, so you target subsets. The cluster generator exposes each
registered cluster's **labels**, and a selector filters them:

```yaml
spec:
 generators:
 - clusters:
 selector:
 matchLabels:
 environment: prod # only clusters labelled prod
 template:
 metadata:
 name: 'payments-{{name}}'
 spec:
 source:
 repoURL: https://example.com/platform/apps
 path: 'payments/overlays/{{metadata.labels.environment}}' # per-segment config
 targetRevision: main
 destination:
 server: '{{server}}'
 namespace: payments
```

Label a cluster `environment=prod,region=eu` when you register it, and one
ApplicationSet rolls the prod overlay to exactly the prod clusters — and picks up a new
prod cluster automatically the day you add one. This is the segmentation strategy made
executable, and it is the lab.

---

### 2. Why it matters for platform engineering

- **Segmentation is a product decision.** "Prod is a separate cluster," "your regulated
 workload runs in-region," "your team gets its own cluster" are *capabilities* your
 platform offers. Choosing the axes deliberately is platform design, not an accident of
 growth.
- **Consistency is the hard part.** Creating clusters is easy; keeping a segmented fleet
 identical is the work. Label-targeted GitOps fan-out is how one paved road reaches each
 segment without snowflakes.
- **Identity cannot be per-cluster.** Without centralized identity, a ten-cluster fleet
 becomes ten access-control problems and a pile of long-lived tokens — an audit
 nightmare and a breach waiting to happen.
- **Coupling is the silent cost.** Whether you ever need Cluster Mesh is decided by how
 loosely you architect services. A platform that encourages cross-cluster synchronous
 calls has quietly rebuilt one big failure domain out of many small ones.

### 3. Mental model

**Cut along boundaries you cannot erase; keep clusters independent; connect only when
you can name why.** Hold this picture: a management cluster drives a segmented grid, one
GitOps source targets segments by label, and most services never cross a cluster line.

```text
 Git (desired state, per segment via labels)
 │
 ┌────────────────▼─────────────────┐
 │ MANAGEMENT cluster │
 │ ArgoCD ApplicationSets (selector) │
 │ Cluster API · policy · OIDC trust │
 └───┬──────────────┬─────────────┬───┘
 env=prod │ env=prod │ env=dev │ (label selectors
 region=eu ▼ region=us ▼ region=eu ▼ route config to
 ┌────────────┐ ┌────────────┐ ┌────────────┐ the right segment)
 │ prod-eu │ │ prod-us │ │ dev-eu │
 │ (self- │ │ (self- │ │ (self- │
 │ sufficient)│ │ sufficient)│ │ sufficient)│
 └─────┬──────┘ └──────┬─────┘ └────────────┘
 └─ async data ──┘ ← share DATA, not live request paths
 (replication) (cross-cluster calls only when justified)
```

Two rules to keep: **the fleet is the reconciliation loop again** (Git is desired state;
a hub closes the gap on each segment), and **a cluster line is a failure-domain line** —
every synchronous call you draw across it trades away the isolation you paid for.

### 4. Minimal implementation

Feel the targeting problem before the tool. "Deploy to everything" is one line; "deploy
the prod overlay to prod only, and self-heal" is the real requirement — and doing it by
hand drifts the moment you add a cluster:

```bash
## imperative, per-cluster, drift-prone
kubectl --context prod-eu apply -k payments/overlays/prod
kubectl --context prod-us apply -k payments/overlays/prod
## forget dev? deploy prod config to dev by mistake? nothing stops you.
```

The declarative answer labels clusters once and lets a selector own the fan-out:

```bash
## register each cluster WITH labels (done once), e.g. prod-eu:
argocd cluster add kind-prod-eu --name prod-eu \
 --label environment=prod --label region=eu

## then one ApplicationSet with a selector targets the segment and self-heals
kubectl --context mgmt apply -f applicationset-by-label.yaml
```

You have turned "apply the right thing to the right clusters, hope none drift" into
"declare it once; a loop keeps each segment correct, and new clusters inherit their
segment automatically." That is the whole move, and it is the lab.

### 6. Production considerations

- **Segment on hard boundaries only.** Environment, region, and genuine
 security/compliance isolation justify a cluster. "Each team wants their own" usually
 does not — offer namespaces with quotas and RBAC first, and escalate to a cluster when
 a team actually needs cluster-scoped control.
- **Centralize identity from day one.** Wire every cluster to the same OIDC provider and
 deliver RBAC bindings via GitOps. Retrofitting identity onto a sprawled fleet is
 painful; starting there is nearly free.
- **Treat the management cluster as crown jewels.** Strict RBAC, minimal exposure,
 pull-based delivery where possible, and no standing human credentials into prod.
- **Adopt cross-cluster discovery deliberately.** Cluster Mesh / Istio / Submariner each
 add a networking layer to run, secure, and debug. Require a named use case, and prefer
 async data sharing over synchronous cross-cluster calls.
- **Standardize add-ons per segment.** Ingress, logging, policy, and cert management
 should be identical within a segment and versioned in Git. Every manual per-cluster
 tweak is a future 2 a.m. snowflake.
- **Plan the front door early.** Decide ingress-per-cluster vs global LB before you have
 users in two regions; it shapes DNS, certificates, and health-check design.

### 7. Common mistakes

- **Cluster sprawl.** — A cluster per app or per team "for isolation" that namespaces,
 quotas, and NetworkPolicy already provide. Every cluster is fixed overhead to run,
 secure, and upgrade. *Fix:* reserve clusters for hard boundaries; default to namespaces.
- **Snowflake segments.** — `prod-eu` and `prod-us` drift to different versions and
 add-ons because each was tweaked by hand. *Fix:* one Git source, label-targeted
 ApplicationSets, identical overlays per segment.
- **Assuming cross-cluster DNS works.** — Expecting `payments.payments.svc` in one
 cluster to resolve from another. It does not. *Fix:* design self-sufficient clusters;
 add Cluster Mesh/Submariner only for a named need.
- **Per-cluster identity stores.** — Local accounts and long-lived kubeconfig tokens
 copied around the fleet. *Fix:* central OIDC, short-lived credentials, RBAC via GitOps.
- **A service mesh across clusters by default.** — Reaching for Istio multi-cluster before
 a problem requires it, buying latency and operational load for every service. *Fix:*
 name the problem first; most fleets never need it.
- **Cross-cluster synchronous coupling.** — `checkout` calls `payments` in another region
 on the hot path, so one region's outage cascades. *Fix:* keep request paths in-cluster;
 share data asynchronously across clusters.

## Fleet Management with Cluster API

> showed one
> illustrative `Cluster` object and promised "clusters are cattle, defined as code."
> This module makes that real. **Cluster API (CAPI)** turns a management cluster into a
> control plane for *other clusters*: you `kubectl apply` a cluster, a controller
> provisions and heals it, you bump a field to upgrade it, and you delete the object to
> tear it down. You'll run it locally with the **Docker provider** — a real reconcile
> loop building real "clusters" as containers, for free — and meet **ClusterClass**, the
> template that makes a whole fleet reproducible.

### 1. Concept

#### The reconciliation loop, aimed at clusters

You have used one idea all course: declare desired state, let a controller close the gap
and heal drift. Deployments do it for Pods. **Cluster API does it for clusters.** In a
**management cluster**, a cluster is a set of Kubernetes objects; CAPI controllers watch
them and reconcile *actual infrastructure* — they provision machines, bootstrap
Kubernetes onto them, join them, and replace them when they die. Create the objects and a
cluster appears; delete them and it is gone.

The core objects, and the separation that makes CAPI portable:

```text
 Cluster ───────────────┬──────────────────────────────┐
 (the contract) │ controlPlaneRef │ infrastructureRef
 ▼ ▼
 KubeadmControlPlane DockerCluster | AWSCluster | GCPCluster …
 (control-plane provider: (infrastructure provider:
 runs/upgrades the API server) where machines & networks come from)
 │
 │ workers
 ▼
 MachineDeployment ──▶ Machine ──┬── bootstrap: KubeadmConfig
 (like a Deployment, │ (how a node joins: cloud-init + kubeadm)
 but for nodes) └── infrastructure: DockerMachineTemplate …
```

Three provider *kinds* cooperate, and each is swappable:

- **Bootstrap provider** — turns a blank machine into a Kubernetes node (the Kubeadm
 bootstrap provider writes cloud-init that runs `kubeadm join`).
- **Control-plane provider** — manages the control plane's lifecycle and upgrades
 (`KubeadmControlPlane`).
- **Infrastructure provider** — creates the actual machines, load balancers, and
 networks. This is the only part that is cloud-specific.

Because only the infrastructure refs change, **the top-level `Cluster` contract is
identical** whether you target Docker, AWS, GCP, or Azure. That portability is the whole
point.

#### Management vs workload, and providers

- A **management cluster** runs the CAPI controllers and holds the cluster objects. It is
 small, long-lived, and precious — it is the control plane for your fleet.
- **Workload clusters** are what CAPI creates: the clusters your applications actually run
 on. They are disposable and reproducible.
- A **provider** teaches CAPI about a target. `clusterctl init --infrastructure docker`
 installs **CAPD**, which builds workload "clusters" as Docker containers on your host —
 perfect for learning and CI. The cloud providers are **CAPA** (AWS/EKS), **CAPG**
 (GCP/GKE), and **CAPZ** (Azure/AKS); you swap the provider and the infrastructure refs,
 and everything else — the workflow, the objects, the upgrade mechanics — stays the same.

#### ClusterClass: a template for clusters

Authoring a raw `Cluster` means writing six-plus coordinated objects (control plane
template, worker templates, infra templates, bootstrap templates) correctly, every time.
Across a fleet that is copy-paste drift waiting to happen — the cluster-level version of
the problem ApplicationSets solved for apps.

**ClusterClass** fixes it. A platform team authors *one* `ClusterClass` — the templates,
plus declared **variables** (e.g. `workerMachineCount`, Kubernetes `version`) and
**patches** that apply them — and then each cluster is a tiny `Cluster` object with a
`spec.topology` that references the class and fills in the variables:

```yaml
apiVersion: cluster.x-k8s.io/v1beta1
kind: Cluster
metadata:
 name: team-a-prod
spec:
 topology:
 class: platform-cluster # the ClusterClass authored once
 version: v1.31.2
 controlPlane:
 replicas: 1
 workers:
 machineDeployments:
 - class: default-worker
 name: md-0
 replicas: 3
```

That is the entire definition of a cluster. ClusterClass is to clusters what a Deployment
template is to Pods, or a Crossplane Composition is to cloud resources: **platform
opinions encoded once, instances stamped out cheaply.** It is the paved road for clusters
themselves.

#### Declarative upgrades and auto-scaling

- **Upgrades.** Change `spec.topology.version` from `v1.31.2` to `v1.32.x` and commit.
 CAPI performs a **rolling upgrade**: it provisions new control-plane machines at the new
 version, moves etcd and the API server, then rolls the worker `MachineDeployments` —
 cordon, drain, replace — honoring your surge settings. No SSH, no manual `kubeadm
 upgrade` per node. The change is a diff in Git: reviewable, auditable, revertible.
- **Auto-scaling node groups.** A `MachineDeployment`'s `replicas` is a number you can set
 — or let the **cluster-autoscaler** set, by annotating min/max so it adds and removes
 worker Machines with demand. For provider-managed node groups there is **`MachinePool`**
 (e.g. an AWS ASG or a GKE node pool managed as one CAPI object). Either way, node
 capacity becomes declarative and elastic instead of hand-provisioned.

#### Bootstrapping a cluster into a usable state

A fresh CAPI cluster is empty — no CNI, no ingress, no GitOps agent. You do **not** want
to `kubectl apply` add-ons by hand onto every new cluster (snowflakes again). Two
declarative patterns close the gap automatically:

- **`ClusterResourceSet`** — a CAPI object that applies a set of manifests (a CNI, say) to
 every cluster matching a label, as soon as it exists.
- **GitOps hand-off** — install an ArgoCD/Flux agent as part of bootstrap, then let GitOps
 take over all further add-ons (the Cluster API Add-on Provider for Flux, or an
 ApplicationSet from ). The result: *create a cluster → it comes up already
 connected to the platform's source of truth*, production-ready without a human.

This is the end-to-end platform move — **cluster creation and app delivery are both just
reconciliation loops**, chained so one triggers the other.

---

### 2. Why it matters for platform engineering

- **Clusters become cattle at scale.** CAPI is what lets a small team run dozens of
 clusters without drowning in manual provisioning and upgrade toil.
- **Lifecycle is auditable.** Create, scale, upgrade, and delete are diffs in Git, reviewed
 by PR and reconciled by a controller — the same governance you have for apps, now for
 the clusters under them.
- **ClusterClass is a paved road for infrastructure.** It encodes the platform's opinions
 (sizes, versions, add-ons) once, so every team's cluster is consistent and compliant by
 default instead of by reminder.
- **Fleet-wide upgrades stop being heroics.** Declarative, rolling, canary-able upgrades
 replace the per-cluster, late-night `kubeadm` ritual that creates version-skew
 snowflakes.

### 3. Mental model

**Kubernetes already reconciles desired state into running software; CAPI reconciles
desired state into running *clusters*. ClusterClass is the Deployment template, and each
`Cluster` with a `topology` is a replica.**

```text
 Git (desired state: ClusterClass + Cluster topologies)
 │ kubectl apply / GitOps
 ┌─────────────▼──────────────┐
 │ MANAGEMENT cluster │
 │ CAPI controllers: │
 │ bootstrap · control-plane │
 │ · infrastructure provider │
 └───────┬───────────────┬──────┘
 reconcile │ │ reconcile
 ▼ ▼
 ┌───────────────┐ ┌───────────────┐ change version → rolling upgrade
 │ workload: dev │ │ workload: prod │ change replicas → scale nodes
 │ (from class) │ │ (from class) │ delete object → cluster destroyed
 └───────────────┘ └───────────────┘ add a label → ClusterResourceSet adds CNI
```

Rules to keep: **the management cluster is the brain** (protect and back it up); **never
hand-edit a workload cluster** — change its spec and let CAPI reconcile; and **author a
ClusterClass, not N raw clusters**, so the fleet stays a template with parameters, not a
pile of snowflakes.

### 4. Minimal implementation

Feel the loop with the Docker provider — real CAPI, no cloud. Turn a kind cluster into a
management cluster, then ask it for a workload cluster:

```bash
## 1. a management cluster, then install CAPI with the Docker infrastructure provider
kind create cluster --name capi-mgmt
clusterctl init --infrastructure docker

## 2. generate a workload cluster definition and apply it (the "apply a cluster" moment)
clusterctl generate cluster demo --flavor development \
 --kubernetes-version v1.31.2 --control-plane-machine-count 1 --worker-machine-count 1 \
 > demo-cluster.yaml
kubectl apply -f demo-cluster.yaml

## 3. watch infrastructure get reconciled into existence
kubectl get cluster,machine
```

You applied a cluster and a controller is building it — control plane, a worker, the
networking — with no SSH and no cloud console. That is the entire thesis of CAPI, and the
lab turns it into a ClusterClass-templated, upgradeable, GitOps-ready workflow.

### 6. Production considerations

- **The management cluster is a single point of truth — treat it like one.** Make it HA,
 back up its etcd (and the CAPI objects), and know how to **`clusterctl move`** (pivot) the
 fleet to a rebuilt management cluster for disaster recovery.
- **Never reconcile by hand.** Changing a workload cluster with imperative `kubectl` behind
 CAPI's back creates drift CAPI will fight or overwrite. Change the spec; let the loop act.
- **Template everything with ClusterClass.** Raw per-cluster manifests re-introduce
 snowflakes. Variables and patches keep the fleet uniform and upgrades uniform.
- **Upgrade in waves with skew in mind.** Canary a version bump on one non-critical cluster,
 watch it, then widen. Respect Kubernetes control-plane/worker skew rules and CAPI's own
 provider contract versions.
- **Scope provider credentials tightly.** CAPA/CAPG/CAPZ hold cloud credentials that can
 create machines and networks — least privilege, short-lived, and audited.
- **Bootstrap to production-ready, not blank.** Pair CAPI with `ClusterResourceSet` or a
 GitOps agent so new clusters arrive with CNI, policy, and the platform's apps — never a
 bare control plane someone has to finish by hand.
- **CAPD is for learning and CI, not production.** The Docker provider builds containers on
 one host; use a real infrastructure provider (or a managed service) for anything that
 serves traffic.

### 7. Common mistakes

- **An unprotected management cluster.** — No HA, no etcd backup, no pivot plan; lose it and
 you lose declarative control of the whole fleet. *Fix:* HA control plane, regular backups,
 a tested `clusterctl move` DR runbook.
- **Clusters as pets, again.** — Clicking clusters up in a console "just this once" beside
 the CAPI-managed ones. *Fix:* every cluster is a `Cluster` object from a ClusterClass — no
 exceptions.
- **Raw clusters instead of a ClusterClass.** — Copy-pasting six objects per cluster, which
 drift immediately. *Fix:* author one ClusterClass with variables; make each cluster a
 short `topology`.
- **Hand-editing workload clusters.** — `kubectl edit` on a node or control-plane behind
 CAPI's back. *Fix:* change desired state in Git; let CAPI reconcile.
- **Big-bang upgrades.** — Bumping every cluster's version at once and hoping. *Fix:* canary
 one, roll waves, respect skew.
- **Shipping blank clusters.** — A new cluster with no CNI/GitOps that a human must finish,
 recreating snowflakes. *Fix:* `ClusterResourceSet` / GitOps bootstrap so it is usable on
 arrival.

## Multi-Cloud Platform Patterns

> Multi-cloud is the most over-specified requirement in platform engineering. It arrives
> as a mandate — "we must avoid lock-in" — far more often than as a solved problem, and it
> almost always costs **more** than one cloud: more expertise, more tooling, more
> networking, more egress fees, and a lowest-common-denominator tax on the managed services
> you can use. This module does the unglamorous work of separating the few real drivers
> from the many weak ones, shows how Crossplane and Kubernetes keep the developer interface
> sane *if* you genuinely need it, and argues that for most teams the right goal is
> **exit-readiness**, not actively running everywhere.

### 1. Concept

#### Say what you actually mean

"Multi-cloud" is used for several different things; the economics differ wildly:

- **Incidental / polycloud.** Different, *independent* workloads happen to run on different
 clouds (often after an acquisition). Each workload is single-cloud; you just have more
 than one. Manageable.
- **Portability-ready.** You run on **one** cloud today, but deliberately keep switching
 costs low — standardize on Kubernetes, use IaC and open formats, avoid deep proprietary
 coupling — so you *could* move. Cheap insurance.
- **Actively multi-cloud.** A single workload (or platform) runs across **two or more**
 clouds simultaneously, with data and traffic spanning them. This is the expensive, hard
 case people usually imagine — and rarely the one they actually need.

Most "we need multi-cloud" conversations want portability-ready and accidentally ask for
actively-multi-cloud. Naming which one you mean is 80% of the decision.

#### The drivers: a short real list and a long weak one

**Drivers that can justify actively multi-cloud:**

- **Regulatory / sovereignty.** A jurisdiction requires a specific provider or a sovereign
 cloud for certain data. A hard external constraint.
- **A genuinely unique service.** One cloud has a capability with no real equivalent (a
 specific ML/data product) that is core to your product.
- **Acquisition / contractual reality.** You bought a company on another cloud, or a large
 customer contractually requires their cloud. The world handed you the constraint.
- **Provider-failure disaster recovery.** You must survive an *entire cloud provider*
 failing — rare, and extremely expensive to do for real (you duplicate everything).

**Weak drivers (sound good, usually aren't):**

- **"Avoid lock-in."** A fear, not a requirement, until you quantify the switching cost you
 are buying down and the premium you are paying for it.
- **"Negotiating leverage."** Enterprise discounts rarely move enough to offset running two
 clouds, and vendors know whether you can actually leave.
- **"Best-of-breed everything."** Stitching the best service from each cloud sounds optimal
 and produces an integration and data-egress nightmare.
- **Résumé-driven architecture.** The most expensive reason, never written down.

If you cannot write the driver in one sentence that names an external constraint, you are
probably buying complexity, not value.

#### The costs are real and mostly hidden

Single-cloud teams underestimate every one of these:

- **Duplicated expertise.** Your team must now be genuinely good at *two* clouds' IAM,
 networking, quotas, and failure modes — or hire twice.
- **Duplicated tooling and automation.** Every pipeline, module, and runbook needs a second
 implementation and a second set of tests.
- **Inter-cloud networking.** Connecting VPCs across providers needs a VPN,
 **Cloud Interconnect** (GCP), **Direct Connect** (AWS), or **ExpressRoute** (Azure) —
 real money, real latency, and a new failure domain.
- **Data egress.** Moving data *out* of a cloud is billed per gigabyte, every time.
 Chatty cross-cloud traffic turns into a silent, growing line item. **Data has gravity:**
 it is the hardest and most expensive thing to make multi-cloud.
- **The lowest-common-denominator tax.** To stay portable you can only lean on the
 *intersection* of what the clouds offer — so you give up the best managed databases,
 queues, and serverless that made a single cloud productive, and rebuild them yourself.

This is why the honest default is: **multi-cloud usually costs more than single-cloud.**
The question is never "is it cool?" but "does a named driver justify this premium?"

#### The abstraction layer: Crossplane XRDs (one API, many clouds)

If you *do* need it, you do not want developers writing cloud-specific manifests. This is
exactly the Crossplane move from 
publish **one** self-service API with a **CompositeResourceDefinition (XRD)**, and back it
with **a Composition per cloud**. The developer asks for a bucket; the platform's
Composition decides whether that is an S3 bucket or a GCS bucket.

```text
developer asks for platform authored real resource
────────────────── ───────────────── ─────────────
ObjectBucket (claim) XObjectStorage (XRD) ──Composition-aws──▶ S3 Bucket + policy
 name: reports one API, two backings ──Composition-gcp──▶ GCS Bucket + IAM
 versioned: true
```

The power is a stable developer contract across clouds. The catch — and you must say it out
loud — is that **the XRD can only expose what both clouds share.** Every cloud-specific
feature you surface leaks the abstraction, and someone maintains N Compositions forever.
Crossplane makes multi-cloud *tolerable*; it does not make it *cheap*.

#### Kubernetes as the portability layer (the practical 80%)

The most pragmatic portability strategy is the one you have been building all course:
**standardize on Kubernetes.** The Kubernetes API is the same on EKS, GKE, and AKS, so the
same Helm charts and manifests deploy anywhere. Your *application layer* becomes genuinely
portable, which buys down most switching cost without running two clouds.

What Kubernetes does **not** make portable is the part that actually locks you in: the
**managed services** around the cluster — the database, the queue, the object store, the
IAM. A Helm chart moves in an afternoon; a 4 TB managed Postgres with ten dependent
services does not. So the realistic posture for most platforms is:

- **Portable by default** at the app layer (Kubernetes + Helm + IaC).
- **Deliberately coupled** to a few best managed services, with the coupling isolated
 behind a narrow interface (a Crossplane XRD, a repository abstraction) so a future move is
 *bounded*, not *catastrophic*.
- **Federated identity** (OIDC / workload identity federation) so one identity model spans
 clouds if you ever go there.

That is **exit-readiness**: not running everywhere, but making sure you *could* leave for a
bounded cost. It is cheap, and it is usually the right answer.

---

### 2. Why it matters for platform engineering

- **It is the headline over-engineering trap.** Speculative multi-cloud abstractions are a
 classic way to pour months of platform effort into complexity no developer asked for —
 the opposite of the Thinnest Viable Platform.
- **It is a cost decision.** Multi-cloud quietly multiplies egress, networking,
 and operational spend. A platform team that cannot articulate that premium should not be
 signing up for it.
- **Exit-readiness is a real, cheap deliverable.** "We standardized on Kubernetes and
 isolated our cloud coupling" is defensible, valuable platform work. "We run on three
 clouds to avoid lock-in" usually is not.
- **If you must, keep the interface sane.** When a genuine driver exists, Crossplane and
 Kubernetes are how you stop multi-cloud complexity from reaching developers.

### 3. Mental model

**Treat multi-cloud as a dial, not a switch — and set it by naming the driver.** Almost
everyone belongs near "portability-ready"; only a named external constraint pushes you to
"actively multi-cloud," and you pay for every notch.

```text
 cheap ◀─────────────────────────────────────────────────────────────▶ expensive

 single cloud portability-ready actively multi-cloud
 (deep coupling) (K8s + IaC + isolated (one workload across clouds,
 │ managed-service coupling) data + traffic spanning them)
 │ │ │
 lock-in risk, most teams live here needs a NAMED driver:
 fast + cheap exit-readiness, low cost regulation, acquisition,
 unique service, provider DR
 ▲
 "name the driver in one sentence
 that references an external constraint,
 or stay to the left."
```

Rules to keep: **data has gravity** (it anchors you to a cloud more than compute ever will);
**portability lives at the Kubernetes layer, lock-in lives in the managed services**; and
**the cheapest multi-cloud is the one you are *ready* for but do not run.**

### 4. Minimal implementation

There is nothing to provision — the "implementation" is a decision and a thin abstraction.
First, Kubernetes already gives you app-layer portability for free:

```bash
## the same chart deploys to any conformant cluster — EKS, GKE, AKS, or kind
helm install web./charts/web --kube-context eks-prod
helm install web./charts/web --kube-context gke-prod
```

Second, when a managed resource genuinely must be portable, hide it behind one XRD and let
a per-cloud Composition implement it (sketches you'll read in the lab):

```bash
## developer interface is identical regardless of which cloud backs it
kubectl apply -f - <<'EOF'
apiVersion: platform.example.org/v1alpha1
kind: ObjectBucket
metadata: { name: reports }
spec: { versioned: true }
EOF
```

The developer never names a cloud. That is the whole deliverable of a portability layer —
and the lab's job is to decide whether building it is worth it for a given scenario.

### 6. Production considerations

- **Budget egress and model data gravity first.** Before any multi-cloud design, map where
 data lives and what crosses a cloud boundary. Egress and cross-cloud chatter are the
 costs that surprise teams; data location decides what is even feasible.
- **Pay the lowest-common-denominator tax knowingly.** If portability forbids the best
 managed service, write down what you are giving up and what rebuilding it costs. Often the
 single-cloud managed service plus exit-readiness is cheaper overall.
- **Federate identity and standardize policy.** One identity provider, consistent RBAC and
 policy-as-code across clouds; otherwise security drifts per cloud and audits become
 impossible.
- **Isolate cloud coupling behind narrow interfaces.** A Crossplane XRD or a repository
 interface turns a future migration from "rewrite everything" into "write one new
 Composition/adapter." That is the real value, whether or not you go multi-cloud now.
- **Double the operational plan.** On-call, runbooks, quota management, and upgrades all
 exist per cloud. Make sure the team is staffed and trained for two, not one.
- **Prefer portability-ready.** For most organizations, standardizing on Kubernetes and
 keeping exit costs bounded delivers the real benefit (reduced risk) without the real cost
 (running everywhere).

### 7. Common mistakes

- **Multi-cloud "to avoid lock-in" with no named driver.** — A fear mandates an expensive
 architecture nobody can justify in one sentence. *Fix:* require a written, external driver;
 otherwise choose portability-ready.
- **Abstracting to the lowest common denominator.** — Giving up the best managed services to
 stay portable, then rebuilding them at great cost. *Fix:* use the best single-cloud service
 and isolate the coupling; only abstract what a real driver requires.
- **Ignoring egress and data gravity.** — Designing chatty cross-cloud traffic and a
 split dataset, then getting a shocking bill. *Fix:* model egress and keep data (and its
 compute) co-located per cloud.
- **Building a portability abstraction nobody uses.** — Months spent on a speculative
 multi-cloud XRD layer for a single-cloud reality. *Fix:* TVP — build the abstraction when a
 driver is real, not in anticipation.
- **Assuming Kubernetes equals portable.** — Shipping to "any cloud" while bound to one
 cloud's managed database, queue, and IAM. *Fix:* recognize the lock-in is in the managed
 services; isolate it deliberately.
- **Underestimating the operational doubling.** — Planning compute for two clouds but not
 the people, runbooks, and on-call. *Fix:* budget the human and process cost explicitly.

## Global Load Balancing and Edge

> You have a fleet of clusters across regions. Now you put one front
> door on them so a user in Frankfurt and a user in São Paulo each hit a fast, nearby,
> *healthy* region — and so losing a whole region is a routing event, not an outage. The
> trap is to think this is a routing problem. Routing is the easy half. The hard half, the
> one that decides your whole design, is **state**: whether your data can be written in two
> regions at once. Choose active-active vs active-passive by your data, not your traffic.

### 1. Concept

#### The goal, and the substrate

You want two things at once: every user served from a **nearby** region (low latency), and
the product **surviving the loss of a whole region** (availability). Your multi-region
clusters are the substrate; a **global load balancer** is the front door that sends each
request to the right region and stops sending to a dead one. Simple to say — and the
routing part really is simple. The design is dominated by what sits *underneath*: your data.

#### Active-active vs active-passive (the decision that drives everything)

- **Active-active.** Every region serves traffic simultaneously. Best latency (everyone
 near a live region), best utilization (no idle hardware), and failover is nearly
 instant — you just stop routing to the failed region. The price is the hard part:
 **writes can land in any region**, so your data layer must handle multi-region writes
 (multi-primary with conflict resolution, or regional sharding so each record has a home
 region). Get this wrong and you get split-brain and lost writes.
- **Active-passive.** One region serves; a standby is promoted on failure. The data story
 is far simpler — one writer, asynchronous replica — so most teams start here. The costs
 are **idle standby capacity** and a non-zero **RTO** (time to detect, promote, and
 reroute) plus possible **RPO** loss (anything not yet replicated when the primary died).

```text
 ACTIVE-ACTIVE ACTIVE-PASSIVE
 ───────────── ──────────────
 users ─▶ global LB ─▶ region A (serving) users ─▶ global LB ─▶ region A (serving)
 └─▶ region B (serving) ·· region B (standby)
 failover: stop routing to the dead one failover: promote B, then route to it
 RTO ≈ seconds, RPO ≈ 0* RTO = detect+promote, RPO = replication lag
 HARD PART: multi-region writes HARD PART: tested, fast promotion
 *if the data layer truly supports it
```

The routing diagrams are almost identical; the **data layer** is where the real cost and
risk live. So the first question in any global design is not "which load balancer?" — it is
**"can my data be written in more than one region at once, and do I need it to?"**

#### How a global load balancer routes

Two broad mechanisms put a user on a region:

- **DNS-based routing.** The load balancer is a smart DNS: it returns a different regional
 IP depending on the asker. **Latency routing** returns the lowest-latency healthy region;
 **geo routing** returns a region by the user's location (also used for data residency).
 Universal and simple — but **DNS caching (TTL)** means failover is only as fast as the
 TTL clients honour, which can be minutes.
- **Anycast routing.** The **same IP address** is announced from many points of presence;
 the internet's routing (BGP) delivers each user to the nearest PoP, and the provider's
 backbone carries them to a healthy region. **Anycast fails over in seconds** (no DNS TTL
 to wait out) and hides regional failure behind one stable IP. This is how GCP's global
 external load balancer, AWS Global Accelerator, and Cloudflare work.

Both are paired with **health-based failover**: each regional backend is health-checked, and
an unhealthy region is automatically removed from rotation. The quality of your health check
*is* the quality of your failover — a shallow check that only pings the load balancer will
happily route users into a region whose database is down.

#### Anycast vs DNS, in one line

- **DNS/latency routing:** simple, works everywhere, failover limited by TTL. Fine for many
 apps.
- **Anycast:** one global IP, seconds-fast failover, needs a provider that offers it. Better
 for strict availability.

#### Edge compute: thin, close, and cross-cutting

The **edge** is the CDN's PoPs — hundreds of locations close to users. **Edge compute**
(Cloudflare Workers, AWS Lambda@Edge, Fastly Compute) runs small, stateless logic there,
before a request ever reaches a region. It earns its place for **cross-cutting, latency-
sensitive, stateless** concerns:

- auth/token validation and bot filtering at the door,
- A/B routing, redirects, and header/geo rewrites,
- caching and request collapsing,
- serving static or personalized-but-cacheable content.

What the edge is **not**: a home for your core application or any stateful logic. State at
hundreds of PoPs is a consistency nightmare, and business logic scattered across the edge is
impossible to reason about. The platform rule is **keep the edge thin** — put cross-cutting
concerns that benefit *every* region there, version and observe them like any other
deployment, and keep the actual product in your regional clusters.

---

### 2. Why it matters for platform engineering

- **Availability is a platform SLO.** Surviving a regional outage is a capability the
 platform provides to every service on it. The global front door and a tested
 failover are how that SLO is met in practice.
- **Latency is product quality.** Routing users to a nearby region is often the single
 biggest latency win, and on many products latency moves revenue.
- **The routing layer makes a fleet one product.** –19.2 built many clusters;
 the global LB is what makes them feel like one service to a user.
- **The data model is a platform-level decision.** Active-active vs active-passive determines
 your consistency, cost, and failure behaviour. Letting each team improvise it is how you
 get split-brain in one service and silent data loss in another.

### 3. Mental model

**Routing is the easy half; state is the hard half. Pick active-active vs active-passive by
your data, then let health checks and anycast (or DNS) handle the traffic.**

```text
 users (worldwide)
 │
 ┌───────────▼────────────┐ routes by: latency / geo / anycast
 │ GLOBAL LOAD BALANCER │ removes unhealthy regions automatically
 └───┬──────────────┬──────┘
 health ✓ │ │ health ✗ (auto-removed from rotation)
 ▼ ▼
 ┌──────────────┐ ┌──────────────┐ EASY HALF ↑ (routing + health checks)
 │ region EU │ │ region US │ ─────────────────────────────────────
 │ cluster(s) │ │ cluster(s) │ HARD HALF ↓ (does your DATA allow this?)
 └──────┬───────┘ └──────┬───────┘
 └── data layer ──┘
 active-active: multi-region writes (sharded / multi-primary) → RTO~0, RPO~0
 active-passive: one writer + async replica, promote on failure → RTO>0, RPO>0
```

Rules to keep: **choose the data model first** (it dictates everything above it); **your
failover is only as good as your health check and your last failover *test***; and **keep
the edge thin** — cross-cutting concerns only, never core state.

### 4. Minimal implementation

You cannot stand up a real global anycast LB for free, but the essence is tiny: a
**meaningful health endpoint** plus a **routing policy that drops unhealthy regions.** The
health check is the part you control and the part that matters most:

```text
## A DEEP health check actually exercises the dependencies failover depends on:
GET /healthz → 200 only if THIS region can serve: app up AND its datastore reachable
 (a shallow check that returns 200 from the LB proves nothing)
```

Everything else is policy you declare, not code you write — "route to the lowest-latency
healthy region, fail over when health drops":

```text
## Illustrative global routing policy (provider-agnostic shape):
record: app.example.com
policy: latency # or: geo, weighted, failover
regions:
 - eu-west backend: lb-eu health: /healthz priority: 1
 - us-east backend: lb-us health: /healthz priority: 1 # active-active: equal priority
## active-passive instead: us-east priority 2 (only used when eu-west is unhealthy)
```

The whole lab is to design this deliberately — model, routing, health, failover, and the
data strategy underneath — for a concrete scenario, rather than discover the gaps during an
incident.

### 6. Production considerations

- **Decide the data strategy first.** Active-active needs a real multi-region write story
 (sharding by home region, or a multi-primary datastore with conflict handling);
 active-passive needs replication plus a **tested** promotion. This choice sets your RTO/RPO
 and most of your cost.
- **Test failover on a schedule.** An untested failover is a hope. Run game days that
 actually fail a region and measure real RTO/RPO; most "automatic" failovers break the first
 time they are used for real.
- **Make health checks deep and stable.** They must verify the region can truly serve (app
 plus critical dependencies), with thresholds that avoid flapping. Shallow checks cause
 false confidence; twitchy checks cause flapping failovers.
- **Mind failover speed vs DNS TTL.** If you rely on DNS routing, low TTLs speed failover but
 increase lookups; anycast sidesteps TTL entirely. Choose with your availability target in
 mind.
- **Handle TLS and identity globally.** Certificates, WAF rules, and auth must be consistent
 across regions and at the edge, or you get per-region drift and security gaps.
- **Account for statefulness and sessions.** Prefer stateless regional tiers; if you need
 session affinity, make it explicit and failover-safe rather than accidental.
- **Cost the model honestly.** Active-passive pays for idle standby; active-active pays for
 double-serving and cross-region data. Price both against the availability you actually need.
- **Keep the edge thin and observable.** Edge logic is still software — versioned, tested,
 monitored, and limited to cross-cutting concerns.

### 7. Common mistakes

- **Solving routing, ignoring data.** — The stateless web tier fails over cleanly while the
 database cannot, so "failover" serves errors or corrupts data. *Fix:* design the data layer
 first; match the routing model to it.
- **Active-active without a consistency plan.** — Serving writes in two regions with no
 multi-region write strategy, producing split-brain and lost updates. *Fix:* shard by home
 region or use a datastore built for multi-primary — or choose active-passive.
- **Never testing failover.** — A failover path that has only ever existed on a diagram.
 *Fix:* scheduled game days that fail a real region and measure RTO/RPO.
- **Long DNS TTLs.** — Failover "works" but clients keep hitting the dead region for minutes
 because of cached DNS. *Fix:* lower TTLs for failover-critical records, or use anycast.
- **Shallow health checks.** — Checks that pass while the app is broken, so traffic keeps
 flowing into a dead region. *Fix:* deep checks that exercise critical dependencies.
- **Business logic sprawled across the edge.** — Core, sometimes stateful, logic scattered
 over hundreds of PoPs, impossible to reason about. *Fix:* keep the edge thin; core logic
 and state stay in regional clusters.

---

## References

- Cilium — [Cluster Mesh guide](https://docs.cilium.io/en/stable/network/clustermesh/clustermesh/)
- Istio — [Multicluster deployment models](https://istio.io/latest/docs/ops/deployment/deployment-models/)
- Submariner — [Architecture and Lighthouse service discovery](https://submariner.io/getting-started/architecture/)
- Argo CD — [ApplicationSet cluster generator](https://argo-cd.readthedocs.io/en/stable/operator-manual/applicationset/Generators-Cluster/)
- Kubernetes — [Using OpenID Connect (OIDC) tokens for cluster auth](https://kubernetes.io/docs/reference/access-authn-authz/authentication/#openid-connect-tokens)
- CNCF — [Introduction to multicluster (kubernetes.io)](https://kubernetes.io/docs/concepts/cluster-administration/#planning-a-cluster)
- The Cluster API Book — [Introduction and quick start](https://cluster-api.sigs.k8s.io/)
- Cluster API — [ClusterClass and managed topologies](https://cluster-api.sigs.k8s.io/tasks/experimental-features/cluster-class/)
- Cluster API — [Quick start with the Docker provider (CAPD)](https://cluster-api.sigs.k8s.io/user/quick-start)
- Cluster API — [`clusterctl` move and pivot](https://cluster-api.sigs.k8s.io/clusterctl/commands/move)
