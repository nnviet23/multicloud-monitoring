# 05 · GitOps and Argo CD

> **Project Applicability:** Active in Project — This project uses **Kustomize + Argo CD** under `deploy/argocd/` and `deploy/clusters/` for multi-cluster GitOps delivery across `hub-k3d`, `aws-k3d`, and `azure-k3d` (instead of Helm-only workflows).

> You have containers, a cluster, infrastructure as code, CI pipelines, and a way
> to package Kubernetes manifests. The missing piece is **how declared state
> actually, continuously, and safely reaches the cluster** — without a human
> running `kubectl apply` and without handing production credentials to a CI job.
> That piece is GitOps: Git becomes the single source of truth, and an in-cluster
> agent continuously reconciles the live cluster toward what Git says.

## Why GitOps?

By now you can build and package software, but *delivery* is still fragile. The
most common way teams ship to Kubernetes is some variation of "a CI job runs
`kubectl apply` with cluster-admin credentials." That approach has four structural
problems, and GitOps fixes all four:

- **No source of truth.** The live cluster and your manifests drift apart. Someone
 hotfixes a replica count at 2 a.m., nobody writes it down, and now "what's
 actually running" is a mystery. With GitOps, Git *is* the state; the cluster is
 a cache of it.
- **No audit trail.** "Who changed this, when, and why?" has no answer when changes
 are imperative `kubectl` commands. With GitOps, every change is a reviewed,
 attributable commit — change management you get for free.
- **A security nightmare.** Push-based CI needs long-lived cluster credentials
 sitting in your pipeline, reachable from the internet. GitOps **pulls** from
 inside the cluster, so those credentials never leave it.
- **No self-healing.** When reality diverges from intent, nothing notices. GitOps
 runs a reconciliation loop — the same idea that makes Kubernetes self-healing — now applied to *delivery itself*.

This phase is also the direct setup for **Project 2**: immediately after it you
build a full multi-environment, multi-team GitOps platform. Everything here —
principles, Argo CD, ApplicationSets, promotion, secrets — is a component you will
assemble there. Learn it well; you are about to use all of it.

## GitOps Principles

> GitOps is **operating infrastructure and applications by making Git the single
> source of truth and letting software continuously reconcile reality toward it.**
> This module builds that idea from first principles — the four principles, why
> *pull* beats *push*, and how drift detection and self-healing are just the
> Kubernetes reconciliation loop applied to delivery — before you touch a single
> GitOps tool.

**You'll need:** · Kubernetes Fundamentals (the reconciliation loop) and a local kind cluster from `00-orientation`.

### Learning objectives

By the end of this module you will be able to:

- State the **four OpenGitOps principles** and explain what each one buys you.
- Explain **push-based vs pull-based** delivery and why pull wins for security.
- Describe **drift detection and self-healing** as the reconciliation loop applied
 to delivery, not a new invention.
- Draw the boundary between **CI and CD** — where continuous integration ends and
 GitOps begins.
- Judge **when GitOps adds value and when it adds complexity without value.**

---

### 1. Concept

The deployment model is captured in the GitOps model diagram and the ArgoCD promotion flow.

#### What GitOps actually is

GitOps is an operating model with one core move: **describe the entire desired
state of your system declaratively, store that description in Git, and run software
that continuously makes the real system match it.** You stop issuing commands
("create this, scale that") and start editing a desired state that a machine
enforces.

The [OpenGitOps](https://opengitops.dev/) project (a CNCF effort) distills it to
**four principles**. A system is GitOps *only if all four hold*:

- **Declarative.** The whole system is described declaratively — *what* you want,
 not *how* to achieve it. Kubernetes manifests, Helm values, and Kustomize
 overlays are declarative; a shell script full of `kubectl` commands is not.
- **Versioned and immutable.** Desired state is stored so it is versioned,
 immutable, and retains a complete history. Git does this: every state is a commit,
 nothing is overwritten in place, and you can always roll back to a prior commit.
- **Pulled automatically.** Software agents **pull** the declared state from the
 source automatically — nobody pushes changes into the cluster. The cluster reaches
 out for its own config.
- **Continuously reconciled.** Agents continuously observe actual state and
 **reconcile** it toward desired state, correcting drift without human action.

Read those again and notice: the last one is exactly what Kubernetes controllers do
with `spec` and `status`. GitOps is not a new mechanism — it is the reconciliation
loop you already know, with **Git as the declared `spec` for the whole cluster.**

#### Push vs pull delivery

There are two ways declared state can reach a cluster:

- **Push (traditional CI/CD).** A pipeline runs *outside* the cluster, authenticates
 *into* it, and pushes changes: `kubectl apply`, `helm upgrade`, `terraform apply`.
 The pipeline needs cluster credentials, and it only acts when it runs — between
 runs, nothing keeps the cluster in line.
- **Pull (GitOps).** An agent runs *inside* the cluster, watches Git, and pulls
 changes in. Credentials to the cluster never leave the cluster; the pipeline never
 touches production. The agent runs constantly, so drift is corrected continuously.

```text
PUSH (CI holds the keys to prod) PULL (cluster fetches its own state)
──────────────────────────────── ──────────────────────────────────────
 CI runner (public, internet) Git repo (desired state)
 │ kubectl apply ▲ pull
 │ (needs cluster-admin creds) │
 ▼ ┌──┴───────────────┐
 ┌──────────────┐ │ in-cluster agent │
 │ cluster │ ◄── creds exfiltrated │ (holds creds │
 │ (prod) │ = cluster owned │ locally only) │
 └──────────────┘ └──┬───────────────┘
 ▼ apply
 ┌──────────────┐
 │ cluster │
 └──────────────┘
```

**Why pull wins for security:** push-based delivery requires long-lived, highly
privileged cluster credentials to live in your CI system — an internet-reachable
target that, if compromised, hands an attacker your production cluster. Pull-based
delivery keeps credentials inside the trust boundary. CI's job shrinks to *build an
image and open a pull request*; it never needs cluster access at all.

#### Where CI ends and GitOps (CD) begins

GitOps does **not** replace CI — it replaces the *deploy* half of CI/CD.

```text
 CI (continuous integration) │ CD via GitOps (continuous delivery)
 ────────────────────────────── │ ──────────────────────────────────
 build → test → scan → publish │ update config repo → PR → merge
 image to a registry, then write │ → agent pulls → reconciles cluster
 the new image tag into the │ to the declared state
 config repo (a commit/PR) │
 ───────────────────────────────────┼────────────────────────────────────
 ends at a Git commit │ starts at that Git commit
```

The handoff is a **commit to the config repository**. CI produces an artifact and
proposes a desired-state change; GitOps takes it from there. This clean seam is
what lets CI stay credential-free.

#### Drift detection and self-healing

**Drift** is any divergence between what Git declares and what the cluster runs —
someone ran `kubectl edit`, an operator mutated a field, a node died. A GitOps agent
continuously compares the two and reports the resource as **OutOfSync**. With
**self-healing** enabled, it goes further: it *reverts* the live object back to the
Git-declared state automatically. The 2 a.m. hotfix someone forgot to commit is
undone within seconds — which is exactly the point. The only way to change the
cluster for good is to change Git.

#### Config GitOps vs application GitOps, and when to skip it

GitOps applies to two things: **application delivery** (your services' manifests)
and **cluster/infra config** (ingress controllers, RBAC, operators, network
policies). The second is often the bigger win — your cluster's entire configuration
becomes reproducible from Git. But GitOps is not free. It adds a config repository,
an agent to operate, and a promotion workflow. For a solo developer on a throwaway
cluster, `kubectl apply` is fine. GitOps earns its keep when you have **multiple
environments, multiple people, or a need for audit and reproducibility** — i.e.
almost every real platform, and the reason this whole phase exists.

---

### 2. Why it matters for platform engineering

GitOps is the backbone of modern platform delivery, and as a platform engineer you
provide it *as a capability* to every team:

- **Security posture, structurally.** Removing cluster credentials from CI closes
 one of the largest attack surfaces in a delivery pipeline. You get least privilege
 by architecture, not by policy.
- **Audit and compliance for free.** `git log` is your change-management record:
 every production change is a reviewed, signed, reversible commit with an author
 and a reason. Auditors love this; so will you during an incident.
- **Disaster recovery becomes trivial.** If a cluster is lost, you don't restore
 from tribal knowledge — you point a fresh cluster at the repo and it rebuilds
 itself. The repo *is* the backup.
- **Reduced cognitive load (the whole point of the course).** Developers promote by
 opening a pull request, not by learning `kubectl`, cluster endpoints, and
 credentials. The paved road is "edit YAML, open PR."
- **Consistency across teams and clusters.** One model — reconcile to Git — governs
 every environment, so the Nth cluster behaves like the first.

---

### 3. Mental model

Hold one picture for the entire phase: **the reconciliation loop, with Git as the
desired state.** taught you that Kubernetes controllers drive `status`
toward `spec`. GitOps wraps the whole cluster in the same loop and moves the `spec`
into Git.

```text
 ┌──────────────────────────────────────────────┐
 │ Git repository — DESIRED STATE │
 │ declarative manifests, versioned, reviewed │
 └───────────────────────┬──────────────────────┘
 │ 1. observe (poll or webhook)
 ▼
 ┌───────────────┐ 2. compare ┌───────────────────────────┐
 │ Live cluster │ ◄──────────── │ GitOps agent (in-cluster)│
 │ ACTUAL state │ ──────────────►│ diff desired vs actual │
 └──────┬────────┘ 4. observe └─────────────┬─────────────┘
 │ │ 3. act: sync if drift
 └──────────────────────────────────────┘
 a loop that never stops running
```

Three rules to remember a year from now:

1. **Git is the `spec`; the cluster is the `status`.** You edit intent in Git; the
 agent owns convergence.
2. **Nobody pushes to prod.** The cluster pulls its own state, so credentials stay
 inside it.
3. **Drift is temporary by design.** Anything not in Git is reverted; the only
 durable way to change the system is to change Git.

---

### 4. Minimal implementation

Before Argo CD (next module), build the reconcile loop **by hand** so you can see
there's no magic. A GitOps agent is, in essence, this loop:

```bash
# The entire idea of GitOps in five lines. Point it at a Git checkout of manifests.
while true; do
 git -C./config pull --quiet # 1. observe desired state
 kubectl apply -f./config/manifests/ >/dev/null # 2+3. compare & converge
 sleep 15 # 4....then do it again, forever
done
```

That loop satisfies all four principles: the manifests are **declarative**, Git
makes them **versioned and immutable**, the loop **pulls** rather than being pushed
to, and it **continuously reconciles**. Now watch it behave like a real GitOps
system:

```bash
# Introduce drift out-of-band — the kind of thing a 2 a.m. hotfix does:
kubectl scale deployment web --replicas=7
# Within ~15s the loop re-applies the manifest (replicas: 2) and drift vanishes.

# Make a durable change the right way — change the declared state in Git:
sed -i 's/replicas: 2/replicas: 4/'./config/manifests/web.yaml
git -C./config commit -am "scale web to 4"
# The next pull brings replicas: 4, and the cluster converges to it.
```

This toy agent is missing everything a real one has — health assessment, pruning,
ordering, a UI, multi-cluster, RBAC — but it is *conceptually complete*. Argo CD is
this loop, done properly. You'll replace the shell script with it in.

---

### 5. Hands-on lab

You'll stand up a local Git repo of manifests and run a hand-written reconcile loop
against a kind cluster, then prove the two behaviours that define GitOps: it heals
out-of-band drift, and it only accepts durable change through a Git commit.

➡️ **Start the lab**

---

### 6. Production considerations

Moving from the toy loop to a platform capability means handling:

- **Poll vs webhook.** Polling (every N seconds) is simple and robust; webhooks give
 near-instant sync but add a public endpoint to secure. Most teams poll and add
 webhooks later for latency.
- **Repo topology.** Keep **application source** and **deployment config** in
 separate repos. Mixing them creates a loop where a CI build commits a tag, which
 the same repo's CI re-triggers. A dedicated config repo also scopes who can change
 production.
- **Agent RBAC.** The in-cluster agent is powerful — it can apply anything in its
 scope. Give it least privilege per project/namespace, not blanket cluster-admin.
- **Secrets.** Plaintext secrets must never enter Git. This is a big enough topic to
 own for now, just know the reconcile loop alone is not a secrets
 story.
- **Observability of sync.** You need to see sync status, drift, and failures, and
 alert on "OutOfSync for >N minutes." A silent agent that stopped reconciling is a
 latent outage.
- **Scale.** One loop per cluster is fine; hundreds of apps across many clusters
 needs generators and a controller built for it.

---

### 7. Common mistakes

- **Calling push-based CI "GitOps" because the manifests live in Git.** Storing YAML
 in Git is necessary but not sufficient; if a pipeline pushes with cluster creds,
 it is not pull-based or continuously reconciled. *Fix:* use an in-cluster agent
 that pulls and reconciles — verify all four principles hold.
- **One repo for app code and deploy config.** CI commits an image tag, which
 re-triggers CI, which commits again — plus everyone who can touch code can now
 touch prod. *Fix:* separate the config repo and scope its access.
- **Leaving self-heal off and calling it GitOps.** Without reconciliation, drift
 accumulates silently and Git stops reflecting reality. *Fix:* enable self-heal (or
 at least alert loudly on drift) so Git stays authoritative.
- **Putting plaintext secrets in Git "temporarily."** Git history is forever; a
 leaked secret in a commit is leaked permanently. *Fix:* never commit secrets —
 use the patterns in from day one.
- **Adopting GitOps where it adds only overhead.** A solo dev on a scratch cluster
 gains little and pays the operating cost. *Fix:* adopt it when you have multiple
 environments, people, or audit needs — otherwise keep it simple.

---

### 8. Assessment

**Knowledge checks**

1. Name the four OpenGitOps principles. Which one makes a cluster self-healing?
2. Why does pull-based delivery have a smaller attack surface than push-based?
3. Where exactly is the handoff between CI and GitOps-based CD?
4. What is drift, and what does a self-healing agent do when it detects drift?
5. Give one situation where adopting GitOps is *not* worth the complexity.

**Concept exercise**

> Explain GitOps to a skeptical engineer **without naming Argo CD, Flux, or any
> other tool.** Describe the operating model and the four principles so they'd
> recognize a GitOps system by its behavior, not its logo.

**Trade-off / debugging exercise**

> A teammate says: "Our CI runs `kubectl apply` on every merge and all our YAML is
> in Git, so we already do GitOps." List what's missing against the four principles.
> Then: a service keeps reverting to 2 replicas minutes after on-call scales it to
> 8 during an incident. Explain what's happening and the *correct* way to make the
> change stick.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** Declarative; versioned and immutable; pulled automatically; continuously
 reconciled. **Continuous reconciliation** provides self-healing.
- **Q2:** Pull keeps cluster credentials inside the cluster; push puts long-lived,
 highly privileged creds in an internet-reachable CI system that becomes a prime
 target.
- **Q3:** At a **commit to the config repository** — CI ends by proposing a
 desired-state change (e.g. a new image tag); GitOps reconciles from there.
- **Q4:** Drift is divergence between Git (desired) and the cluster (actual). A
 self-healing agent reverts the live object back to the Git-declared state.
- **Q5:** A solo developer on a short-lived/scratch cluster: the audit, multi-env,
 and reproducibility benefits don't apply, and the agent/repo/workflow are pure
 overhead.
- **Missing from the "we already do GitOps" claim:** it's push, not pull (CI holds
 creds); it's not continuously reconciled (only on merge); so drift isn't healed.
- **Debugging:** a reconcile loop with self-heal is reverting the manual scale to
 the Git value (2). The correct fix is to change the declared replica count in Git
 (commit/PR), or temporarily pause auto-sync for a deliberate incident override —
 then reconcile Git back to reality.

</details>

---

### 9. Further reading

- OpenGitOps — [Principles v1.0](https://opengitops.dev/) and the [GitOps Glossary](https://github.com/open-gitops/documents)
- CNCF — [What is GitOps?](https://www.cncf.io/blog/2021/09/28/the-cncf-tag-app-delivery-provides-gitops-principles/)
- Argo CD — [Core concepts](https://argo-cd.readthedocs.io/en/stable/core_concepts/)
- Flux — [GitOps and the reconciliation model](https://fluxcd.io/flux/concepts/)
- Weaveworks — [Guide to GitOps](https://www.weave.works/technologies/gitops/)

---


_Previous:_ · GitOps overview
· _Next:_ 08.2 — Argo CD Fundamentals →

---

## Argo CD Fundamentals

> Argo CD is the production version of the reconcile loop you built by hand in the
> last module: an in-cluster controller that pulls declarative config from Git and
> continuously reconciles the cluster toward it. This module covers its
> architecture, the `Application` resource, and the health/sync model you'll live in
> every day.

**You'll need:** GitOps Principles, a local kind cluster, and `kubectl` from `00-orientation`.

### Learning objectives

By the end of this module you will be able to:

- Describe Argo CD's **core components** and how a sync flows through them.
- Author an **`Application`** resource: source, destination, and sync policy.
- Distinguish **health status** from **sync status**, and read both correctly.
- Configure **sync options** — automated sync, `prune`, `selfHeal`,
 `CreateNamespace` — and know what each one risks.
- Drive Argo CD declaratively and with the **CLI**, and reason about RBAC and
 notifications.

---

### 1. Concept

#### What Argo CD is

Argo CD is a declarative, GitOps continuous-delivery controller for Kubernetes. You
hand it the location of some manifests in Git (plain YAML, a Helm chart, or a
Kustomize overlay) and a target cluster/namespace; it renders them, compares the
result to what's live, and reconciles. It is the hand-built loop from,
made correct: it assesses health, prunes safely, orders resources, exposes a UI and
API, and enforces RBAC.

#### Architecture

Argo CD is a handful of cooperating components, all running *inside* the cluster:

- **API server.** Serves the gRPC/REST API that the web UI and `argocd` CLI use, and
 enforces authentication, RBAC, and the app management operations.
- **Repository server (repo-server).** Clones Git repos and **renders** the final
 manifests — runs `helm template`, `kustomize build`, or reads plain YAML — then
 hands the result to the controller. It holds no cluster state; it's a manifest
 factory and cache.
- **Application controller.** The heart of the loop. It compares the rendered
 desired state against live cluster state, computes `OutOfSync`/`Healthy`, and
 performs syncs. This is the reconciliation engine.
- **Dex (optional).** An identity broker for SSO (OIDC/SAML/LDAP). You can also wire
 OIDC directly and skip Dex.
- **Redis.** A cache for rendered manifests and computed state. It's disposable —
 losing it just forces recomputation.

```text
 Git repo ──clone/render──► repo-server ──manifests──► application controller
 (desired state) │
 │ compare + sync
 UI / argocd CLI ──► API server ──(RBAC)──► controller ───▼──► target cluster
 ▲ (live state)
 └── Dex/OIDC (SSO) Redis (cache)
```

Everything flows toward the **application controller**, which is the only component
that reconciles live state — just like the API server was the hub in the Kubernetes
architecture you studied in.

#### The Application resource

An **`Application`** is a custom resource that defines one reconciliation unit: *this
source* should be made live in *this destination* using *this sync policy*.

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
 name: guestbook
 namespace: argocd # Applications live in the argocd namespace
spec:
 project: default
 source: # WHERE desired state comes from
 repoURL: https://github.com/argoproj/argocd-example-apps
 targetRevision: HEAD # a branch, tag, or commit — pin this in prod
 path: guestbook # folder (or chart) within the repo
 destination: # WHERE it should run
 server: https://kubernetes.default.svc # the in-cluster API
 namespace: guestbook
 syncPolicy:
 automated: # omit this block for manual sync
 prune: true # delete resources removed from Git
 selfHeal: true # revert out-of-band drift
 syncOptions:
 - CreateNamespace=true # make the namespace if it doesn't exist
```

Three parts carry the meaning: **source** (what to deploy and from where),
**destination** (which cluster and namespace), and **syncPolicy** (how reconciliation
behaves). The same `source` block can point at a Helm chart (`source.helm`) or a
Kustomize overlay — Argo CD detects and renders each.

#### Health status vs sync status — two different questions

New users conflate these; they answer different questions, and reading them wrong
sends you debugging the wrong thing.

- **Sync status** answers: *does live state match Git?*
 - **Synced** — the cluster matches the rendered manifests.
 - **OutOfSync** — it doesn't (someone drifted it, or Git moved ahead).
- **Health status** answers: *are the running resources actually healthy?*
 - **Healthy** — resources are up and ready (Deployment available, Service has
 endpoints).
 - **Progressing** — still rolling out.
 - **Degraded** — failed (crash-looping Pods, failed rollout).
 - **Missing** — declared in Git but not present in the cluster.
 - **Unknown** — Argo CD can't determine health.

They are independent. An app can be **Synced + Degraded** (Git matches the cluster,
but the image crash-loops — a *code* problem) or **OutOfSync + Healthy** (it's
running fine, but Git has a newer version not yet applied — a *delivery* problem).
Knowing which pair you're looking at tells you whether to fix the app or run a sync.

#### Sync options you must understand

- **`automated`** — reconcile automatically on drift/new commits. Omit it and sync
 is manual (a human or pipeline triggers it) — common for production gates.
- **`prune`** — delete live resources that were removed from Git. Powerful and
 dangerous; off by default so a bad render can't wipe resources.
- **`selfHeal`** — revert out-of-band changes back to Git. This is your drift
 defense.
- **`CreateNamespace=true`** — create the destination namespace automatically.
- **`replace`** — use `kubectl replace` instead of `apply` for resources that can't
 be patched. A last resort.

#### Repository types and the CLI

A `source` can be **Git** (plain YAML, Helm, or Kustomize), a **Helm** repository,
or an **OCI** registry (the artifacts you packaged in ). Day to day you'll
drive Argo CD declaratively (commit `Application` manifests) and inspect it with the
CLI: `argocd app list`, `argocd app get <name>`, `argocd app sync <name>`,
`argocd app history <name>`, and `argocd app rollback <name> <id>`.

---

### 2. Why it matters for platform engineering

Argo CD is, for most platforms, *the* delivery control plane — the thing every team
ships through:

- **It's the paved road for delivery.** Teams get continuous, auditable deployment
 without learning cluster credentials or `kubectl`. Their interface is a pull
 request; Argo CD does the rest.
- **It centralizes delivery policy.** Health checks, prune/self-heal behavior,
 sync windows, and RBAC are configured once by the platform team and inherited by
 every app.
- **It makes multi-tenancy real.** Argo CD **Projects** scope which repos, clusters,
 and namespaces a set of Applications may touch — so Team A can't deploy into Team
 B's namespace. That boundary is a platform responsibility.
- **It's the substrate for everything next.** ApplicationSets (08.3), promotion
 (08.4), and secrets (08.5) all build on the `Application`. Project 2 is essentially
 "operate Argo CD well for many teams."

---

### 3. Mental model

Picture Argo CD as the loop with real organs bolted on. The controller
is the loop; the repo-server renders desired state; the API server guards the door.

```text
 ┌──────────────────────────────────────────────┐
 │ Git repo — DESIRED STATE (per Application) │
 └───────────────────────┬──────────────────────┘
 │ repo-server renders (helm/kustomize/yaml)
 ▼
 ┌───────────────┐ compare ┌───────────────────────────┐
 │ Live cluster │ ◄──────────── │ application controller │
 │ ACTUAL state │ ──────────────►│ sync status + health │
 └──────┬────────┘ observe └─────────────┬─────────────┘
 │ │ sync if OutOfSync
 └──────────────────────────────────────┘
 one Application = one reconcile unit
```

Three rules to remember:

1. **One `Application` is one reconcile unit** mapping a Git source to a cluster
 destination.
2. **Sync status ≠ health status.** "Matches Git" and "actually works" are different
 questions.
3. **`prune` and `selfHeal` are the sharp edges.** Self-heal protects you; prune can
 delete — enable each deliberately.

---

### 4. Minimal implementation

The smallest useful Argo CD setup is: install it, then apply one `Application`
manifest. No UI clicking required — the `Application` is itself declarative GitOps.

```bash
# Install Argo CD from the upstream manifests (free, local kind cluster).
kubectl create namespace argocd
kubectl apply -n argocd \
 -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl -n argocd rollout status deploy/argocd-server --timeout=180s
```

```bash
# Declare one Application and let the controller reconcile it.
kubectl apply -f - <<'YAML'
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
 name: guestbook
 namespace: argocd
spec:
 project: default
 source:
 repoURL: https://github.com/argoproj/argocd-example-apps
 targetRevision: HEAD
 path: guestbook
 destination:
 server: https://kubernetes.default.svc
 namespace: guestbook
 syncPolicy:
 automated: { prune: true, selfHeal: true }
 syncOptions: [ CreateNamespace=true ]
YAML

kubectl -n argocd get applications # watch SYNC STATUS and HEALTH columns
```

That's the whole model: desired state is a public Git repo; the `Application` is the
reconcile unit; the controller drives the cluster to **Synced + Healthy**. The lab
turns this into a guided exercise with drift and the CLI.

---

### 5. Hands-on lab

You'll install Argo CD on kind, deploy the public guestbook app as an auto-syncing
`Application`, watch self-heal revert drift, promote a change by editing the
`Application`, and use the `argocd` CLI to inspect sync status, health, and history.

➡️ **Start the lab**

---

### 6. Production considerations

- **High availability.** The upstream `install.yaml` is non-HA. Production uses the
 HA manifests (replicated controller shards, redis-ha) and enough repo-server
 replicas to render all your apps without queueing.
- **SSO and RBAC.** Wire OIDC/SSO and define Argo CD RBAC so teams see and sync only
 their own apps. Never share the local `admin` account beyond bootstrap.
- **Projects for tenancy.** Use `AppProject` to whitelist source repos, destination
 clusters/namespaces, and allowed resource kinds per tenant. This is how you stop
 one team's Application from touching another's namespace.
- **Sync windows.** Configure windows to block (or allow) syncs during change
 freezes or business hours, especially for production.
- **Notifications.** Enable argocd-notifications to post to Slack/email on sync
 failure, health degradation, or sustained drift — a silent controller is a hidden
 outage.
- **Pin revisions.** `targetRevision: HEAD` is fine for demos; in production pin to a
 branch you control or a tag/commit so a random upstream push can't change prod.
- **Resource scale.** The repo-server CPU/memory and the controller's reconcile
 concurrency must be tuned as app count grows; watch sync latency.

---

### 7. Common mistakes

- **Confusing OutOfSync with Degraded.** Chasing a "broken app" that is actually
 Synced-but-Degraded (a code/image problem), or syncing an app that is merely
 OutOfSync-but-Healthy. *Fix:* read both statuses first and treat them as separate
 questions.
- **Enabling `prune` blindly, then losing resources.** A bad render or a wrong path
 can delete live resources. *Fix:* adopt prune deliberately, start without it, and
 use Argo CD's prune preview / `prune=false` dry runs.
- **Leaving `selfHeal` off and wondering why drift persists.** Without it, manual
 `kubectl edit` sticks and Git stops being authoritative. *Fix:* enable self-heal
 for anything you want Git to own.
- **Managing apps by clicking the UI.** Creating Applications in the UI makes the
 Applications themselves non-GitOps. *Fix:* commit `Application` manifests (and use
 app-of-apps / ApplicationSets from ).
- **Using the `admin` account for everything.** Convenient and unaccountable. *Fix:*
 disable or rotate `admin` after bootstrap and use SSO with scoped RBAC.
- **`targetRevision: HEAD` in production.** An unrelated upstream commit can change
 your cluster. *Fix:* pin to a controlled branch, tag, or commit.

---

### 8. Assessment

**Knowledge checks**

1. Name Argo CD's core components and say which one performs reconciliation.
2. What are the three required parts of an `Application` `spec`?
3. An app shows **Synced + Degraded**. What does that tell you, and where do you
 look?
4. What does `selfHeal` do, and how does it differ from `prune`?
5. Why is creating Applications through the UI an anti-pattern for GitOps?

**Concept exercise**

> Explain what an Argo CD `Application` is **without using the words "Argo CD" or
> "controller."** Describe it as a mapping and a loop, so someone could recognize the
> concept in any GitOps tool.

**Trade-off / debugging exercise**

> You enable `automated: { prune: true, selfHeal: true }` on a production app. On-call
> scales it up during an incident and it snaps back; later a bad PR removes a
> resource from Git and it vanishes from the cluster. Explain *why each happened* and
> propose a policy (sync options, sync windows, manual gate) that keeps safety during
> normal operations but allows a controlled emergency override.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** API server, repo-server, application controller, (optional) Dex, and
 Redis. The **application controller** reconciles.
- **Q2:** `source`, `destination`, and `syncPolicy` (project is also required but
 defaults to `default`).
- **Q3:** Live state *matches Git* (Synced) but the resources are *failing*
 (Degraded) — so it's an application/image problem (e.g. crash loop), not a delivery
 problem. Look at Pod logs/events, not at Git.
- **Q4:** `selfHeal` reverts out-of-band drift back to Git; `prune` deletes live
 resources that were removed from Git. One restores declared state; the other
 removes undeclared state.
- **Q5:** The Applications themselves become imperative, unversioned, and
 unreviewable — they should be declared in Git like everything else.
- **Debugging:** self-heal reverted the manual scale (drift); prune deleted the
 resource the PR removed (desired state changed). A safer policy: keep self-heal on
 but gate production with manual sync or sync windows, require review on the config
 repo, and for emergencies temporarily disable auto-sync (or use an override
 window) then reconcile Git back to reality.

</details>

---

### 9. Further reading

- Argo CD — [Core concepts](https://argo-cd.readthedocs.io/en/stable/core_concepts/)
 and [Architecture](https://argo-cd.readthedocs.io/en/stable/operator-manual/architecture/)
- Argo CD — [`Application` specification](https://argo-cd.readthedocs.io/en/stable/user-guide/application-specification/)
- Argo CD — [Automated sync, prune, and self-heal](https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/)
- Argo CD — [Resource health](https://argo-cd.readthedocs.io/en/stable/operator-manual/health/)
 and [RBAC](https://argo-cd.readthedocs.io/en/stable/operator-manual/rbac/)
- Argo CD — [Getting started](https://argo-cd.readthedocs.io/en/stable/getting_started/)

---


_Previous:_ 08.1 — GitOps Principles
· _Next:_ 08.3 — Argo CD ApplicationSets →

---

## Argo CD ApplicationSets

> One `Application` per service, per environment, per cluster does not scale — you'd
> hand-write and maintain hundreds of near-identical manifests. **ApplicationSets**
> generate Applications from a template and a *generator*, so onboarding a new app,
> environment, or cluster becomes "add a directory" or "add a list entry." This
> module covers generators, templating, and the related **app-of-apps** pattern.

**You'll need:** Argo CD Fundamentals with Argo CD installable on a local kind cluster.

### Learning objectives

By the end of this module you will be able to:

- Explain what an **ApplicationSet** is and how its controller generates
 Applications.
- Choose the right **generator** — list, git (directory/file), cluster, matrix,
 merge — for a problem.
- Template Applications with generator parameters and avoid common templating traps.
- Contrast the **app-of-apps** pattern with ApplicationSets and know when to use
 each.
- Design app/environment onboarding so it's a one-line or one-folder change.

---

### 1. Concept

#### The scaling problem

In you wrote one `Application`. Now imagine 40 services across dev,
staging, and prod on three clusters. Hand-writing `40 × 3 × 3 = 360` Applications —
and keeping them consistent as policy changes — is exactly the copy-paste toil a
platform is supposed to delete. You want to declare the *pattern* once and let
something stamp out the instances.

#### ApplicationSet: a template plus a generator

An **ApplicationSet** is a controller (bundled with Argo CD) and a custom resource
that produces Applications from two parts:

- A **generator** that yields a set of parameter maps (one per thing you want an
 Application for).
- A **template** — an `Application` spec with `{{placeholders}}` filled from each
 generator's parameters.

The controller renders `template × generator results` into real Applications and
keeps them reconciled: add an entry to the generator and a new Application appears;
remove it and the Application (optionally) goes away.

```text
 generator (produces a set) template (one Application, parameterized)
 ───────────────────────── ────────────────────────────────────────
 { env: dev, cluster: a } name: web-{{env}}
 { env: stg, cluster: a } ──► render path: overlays/{{env}}
 { env: prod, cluster: b } namespace: web-{{env}}
 │
 ▼
 Application web-dev, Application web-stg, Application web-prod (kept in sync)
```

#### The generators you'll actually use

- **List generator** — an explicit, hand-written list of parameter maps. Best for a
 small, stable set like your environments. Simple and predictable.
- **Git generator (directory)** — one Application per *directory* matching a glob in
 a repo (e.g. `apps/*`). Onboard an app by adding a folder. This is the workhorse
 for monorepo-of-apps layouts.
- **Git generator (file)** — one Application per *config file* (e.g. each
 `config.json` under `apps/`), with the file's contents available as parameters.
 Best when each app needs structured, per-app values.
- **Cluster generator** — one Application per cluster registered in Argo CD. Best for
 rolling a platform add-on (ingress, cert-manager) out to every cluster.
- **Matrix generator** — the Cartesian product of two generators, e.g.
 *(git directory: each app) × (list: each cluster)*. Powerful; also the easiest to
 make explode, so use it deliberately.
- **Merge generator** — combine generators by a key to override/augment parameters
 (e.g. base values from one generator, per-cluster overrides from another).

#### The app-of-apps pattern

Before (and alongside) ApplicationSets there's a simpler composition pattern: a
single **root Application** whose Git `path` contains *other `Application`
manifests*. Syncing the root creates all the child Applications, which in turn
deploy workloads. It's how you **bootstrap** a cluster from one entry point: point
Argo CD at the root, and the whole platform unfolds.

```text
 root Application ──deploys──► child Application manifests (in Git)
 (the "app of apps") │ each is itself reconciled
 ▼
 workloads: ingress, monitoring, the apps…
```

**app-of-apps vs ApplicationSet:** app-of-apps is a *static* tree — you write each
child Application by hand (or generate them). ApplicationSet is *dynamic* — children
are generated from data (directories, a list, clusters). A common real design uses
**an app-of-apps root that contains a few ApplicationSets**: one entry point, and
most children generated. Use app-of-apps for bootstrapping/composition; reach for
ApplicationSets when the children are repetitive and data-driven.

#### Templating notes

Parameters are substituted with `{{param}}`. The git directory generator exposes
`{{path}}` (full path), `{{path.basename}}` (last segment — handy for names and
namespaces), and path segments. Newer Argo CD supports **Go templating**
(`goTemplate: true`) for conditionals and functions, which is far more robust than
string substitution for anything non-trivial. Keep names DNS-safe and deterministic
so generated Applications are stable across renders.

---

### 2. Why it matters for platform engineering

ApplicationSets are how GitOps becomes a *platform capability* rather than a
per-app chore:

- **Onboarding is self-service.** With a git directory generator, a team ships a new
 service by adding a folder and opening a PR — no platform ticket, no hand-written
 Application. That's the paved road.
- **Consistency by construction.** Every generated Application inherits the same
 template: the same project, sync policy, labels, and guardrails. Policy changes in
 one place, not 360.
- **Fleet operations.** The cluster generator rolls a platform add-on to every
 cluster at once; the matrix generator deploys every app to every environment from
 one resource.
- **Bootstrapping.** app-of-apps (often containing ApplicationSets) lets you rebuild
 an entire cluster's platform layer from a single root Application — core to
 disaster recovery and to standing up new clusters in Project 2 and beyond.

---

### 3. Mental model

An ApplicationSet is a **factory** sitting in front of the reconcile loop: the
generator decides *how many* Applications exist and *with what parameters*, the
template decides *what each one is*, and the Argo CD controller then reconciles each
generated Application exactly as in.

```text
 data source ──► [ GENERATOR ] ──► set of params ──► [ TEMPLATE ] ──► N Applications
 (list/git/ │
 clusters) ▼
 each reconciled Git → cluster
```

Three rules to remember:

1. **Generator = how many and with what; template = what each is.** Keep the two
 concerns separate in your head.
2. **Change the data, not the manifests.** Add a directory/list entry to scale out;
 don't hand-edit generated Applications.
3. **app-of-apps composes; ApplicationSet generates.** Bootstrap with the former,
 scale repetition with the latter.

---

### 4. Minimal implementation

The smallest ApplicationSet uses a **list generator** to produce two Applications
from one template — the "hello world" of generation:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
 name: guestbook-envs
 namespace: argocd
spec:
 generators:
 - list:
 elements:
 - env: dev
 - env: prod
 template:
 metadata:
 name: 'guestbook-{{env}}'
 spec:
 project: default
 source:
 repoURL: https://github.com/argoproj/argocd-example-apps
 targetRevision: HEAD
 path: guestbook
 destination:
 server: https://kubernetes.default.svc
 namespace: 'guestbook-{{env}}'
 syncPolicy:
 automated: { prune: true, selfHeal: true }
 syncOptions: [ CreateNamespace=true ]
```

```bash
kubectl apply -f applicationset-list.yaml
kubectl -n argocd get applicationset,applications
# → one ApplicationSet produced two Applications: guestbook-dev and guestbook-prod
```

Add `- env: staging` to the list and a third Application appears on the next
reconcile. You changed *data*, not manifests — that's the whole idea. The lab scales
this up with a git directory generator and an app-of-apps.

---

### 5. Hands-on lab

You'll build a list-generator ApplicationSet (one Application per environment), then
a git-directory-generator ApplicationSet that creates one Application per app folder
in the public example repo, and finally an app-of-apps root that composes multiple
Applications from a single entry point.

➡️ **Start the lab**

---

### 6. Production considerations

- **Deletion behavior.** By default, removing a generator result deletes its
 Application (and, with prune, its workloads). Set
 `preserveResourcesOnDeletion` or use the ApplicationSet's deletion policies when
 that's too aggressive — a mistaken file deletion shouldn't wipe prod.
- **Matrix blast radius.** A matrix of *(apps) × (clusters)* can generate thousands
 of Applications from a tiny change. Review renders (there's a dry-run/preview) and
 constrain generators so an edit can't carpet-bomb the fleet.
- **Progressive syncs.** ApplicationSets can roll changes out in ordered waves across
 the generated Applications (e.g. dev before prod), so one template change doesn't
 hit every environment simultaneously.
- **Go templating over string substitution.** For anything with conditionals,
 defaults, or nested values, enable `goTemplate: true` — naive `{{...}}` substitution
 silently produces broken manifests.
- **Generator source security.** The git generator reads structure/values from a
 repo; who can add a directory or edit a config file can now create Applications.
 Scope write access and pair it with `AppProject` restrictions.
- **Stable, DNS-safe names.** Generated names must be deterministic and valid;
 non-deterministic names cause churn (delete/recreate) on every reconcile.

---

### 7. Common mistakes

- **Hand-maintaining many near-identical Applications.** The exact toil
 ApplicationSets exist to remove. *Fix:* identify the varying dimension (env, app,
 cluster) and express it as a generator.
- **Reaching for a matrix generator first.** It's the most powerful and the easiest
 to make explode. *Fix:* start with list or git-directory; add matrix only when you
 truly need the product, and preview the render.
- **String templating complex values.** `{{...}}` substitution can't do conditionals
 and will emit invalid YAML silently. *Fix:* enable `goTemplate: true`.
- **Forgetting deletion semantics.** Deleting a folder/list entry can delete live
 resources. *Fix:* understand and configure deletion/preserve policies before you
 rely on it in prod.
- **Confusing app-of-apps with ApplicationSet.** Writing dozens of child Applications
 by hand "because app-of-apps," when a generator would produce them. *Fix:* use
 app-of-apps to compose/bootstrap, ApplicationSets to generate repetition — often
 together.
- **Unbounded git generators over an untrusted repo.** Anyone who can add a directory
 can create an Application. *Fix:* restrict repo write access and bound
 destinations with an `AppProject`.

---

### 8. Assessment

**Knowledge checks**

1. What two parts make up an ApplicationSet, and what does each decide?
2. Which generator onboards a new app by "just adding a folder," and what does
 `{{path.basename}}` give you?
3. When would you choose a cluster generator over a list generator?
4. What's the difference between app-of-apps and an ApplicationSet?
5. Why is the matrix generator the one to use most cautiously?

**Concept exercise**

> Explain how you'd deploy 30 microservices to 3 environments **without writing 90
> Application manifests** — and do it without naming any specific generator. Describe
> the "template plus a set of parameters" idea so it would apply to any GitOps tool.

**Trade-off / debugging exercise**

> A teammate proposes a single matrix generator of *(every app) × (every cluster) ×
> (every environment)* to manage the whole company from one resource. Give two
> concrete risks and a safer decomposition. Then: after someone deletes an `apps/`
> subfolder in a PR, a production service disappears. Explain the mechanism and two
> ways to prevent a folder deletion from deleting live prod resources.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** A **generator** (produces the set of parameter maps — how many and with
 what) and a **template** (the parameterized `Application` — what each one is).
- **Q2:** The **git directory generator**; `{{path.basename}}` is the final path
 segment (the folder name), handy for the Application name and namespace.
- **Q3:** When you want one Application *per cluster* (e.g. rolling a platform add-on
 to every registered cluster) rather than an explicit hand-listed set.
- **Q4:** app-of-apps is a *static* composition — a root Application whose path holds
 hand-written child Applications; ApplicationSet *dynamically generates* children
 from data. They're often combined.
- **Q5:** It's a Cartesian product — a small change multiplies into many
 Applications, so it has the largest blast radius.
- **Debugging:** the git generator created one Application per folder; deleting the
 folder removed the generator result, which deleted the Application and (with prune)
 its resources. Prevent it with `preserveResourcesOnDeletion`/deletion policies,
 branch protection + review on the config repo, and treating prod folders as
 protected paths.

</details>

---

### 9. Further reading

- Argo CD — [ApplicationSet overview](https://argo-cd.readthedocs.io/en/stable/user-guide/application-set/)
- Argo CD — [Generators](https://argo-cd.readthedocs.io/en/stable/operator-manual/applicationset/Generators/)
 (list, git, cluster, matrix, merge)
- Argo CD — [The app-of-apps pattern](https://argo-cd.readthedocs.io/en/stable/operator-manual/cluster-bootstrapping/)
- Argo CD — [ApplicationSet Go templating](https://argo-cd.readthedocs.io/en/stable/operator-manual/applicationset/GoTemplate/)
- Argo CD — [Progressive syncs](https://argo-cd.readthedocs.io/en/stable/operator-manual/applicationset/Progressive-Syncs/)

---


_Previous:_ 08.2 — Argo CD Fundamentals
· _Next:_ 08.4 — Multi-Environment GitOps →

---

## Multi-Environment GitOps

> One environment is easy; the money is in **promoting the same change through dev →
> staging → prod safely and auditably.** This module covers the folder-over-branch
> strategy, promotion by pull request, sync waves for ordering, and rollback by Git
> revert — the workflow your platform offers every team.

**You'll need:** ApplicationSets, Kustomize from, and Argo CD on kind.

### Learning objectives

By the end of this module you will be able to:

- Choose a **folder-per-environment** layout and justify it over branch-per-environment.
- Run a **promotion workflow**: change an overlay → PR → review → merge → auto-sync.
- Order resource creation with **sync waves** (namespace before workload, CRDs
 before CRs).
- **Roll back** an environment by reverting a Git commit, and reason about rollback
 across environments.
- Decide where to **gate** production (manual sync, sync windows) while keeping lower
 environments fast.

---

### 1. Concept

#### Folder strategy vs branch strategy

You have two ways to represent environments in Git, and the choice shapes
everything:

- **Branch per environment** — a `dev`, `staging`, and `prod` branch; promotion is a
 merge between branches. It sounds natural but rots quickly: branches **diverge**,
 cherry-picks get messy, and "what's different between staging and prod?" becomes a
 confusing branch diff rather than a config diff. You also can't see all
 environments at once.
- **Folder per environment** — one branch (usually `main`), with a directory per
 environment (`overlays/dev`, `overlays/staging`, `overlays/prod`). Promotion is a
 change to the target environment's folder. Every environment is visible in one
 tree, diffs are explicit, and history is linear.

**Folder wins** for auditability and clarity, and it's the near-universal convention.
A single `main` branch holds the truth for all environments; a reviewer sees exactly
which environment a PR touches and exactly what changes.

```text
config-repo/ ← ONE branch (main) is the source of truth
└── apps/web/
 ├── base/ ← shared manifests (the common case)
 └── overlays/
 ├── dev/ ← replicas: 1, image::1.27.1 (candidate) auto-sync
 ├── staging/ ← replicas: 2, image::1.27.0 auto-sync
 └── prod/ ← replicas: 3, image::1.27.0 manual gate
```

With Kustomize, `base/` holds what's common and each `overlay/` holds only
the differences — replica count, image tag, resource limits. A **promotion is just a
change to an overlay** — usually bumping the image tag that was validated one
environment earlier.

#### Promotion by pull request

GitOps turns "deploy to staging" into "open a PR that changes `overlays/staging`."
The flow:

```text
 CI builds image:1.27.1, validates in dev
 │
 ▼
 PR: bump overlays/staging image tag:1.27.0 →:1.27.1
 │ review (a human approves the diff)
 ▼
 merge to main ──► Argo CD sees overlays/staging changed ──► auto-sync staging
 │ staging validated
 ▼
 PR: bump overlays/prod:1.27.0 →:1.27.1 ──► merge ──► prod sync (gated)
```

Every promotion is a reviewed, attributable commit. "What's in prod?" is answered by
reading `overlays/prod` at `main`; "how did it get there?" is answered by `git log`.
CI can even **open the promotion PR automatically** after tests pass — promotion
becomes a reviewable diff a human approves, not a credentialed deploy.

#### Sync waves: ordering a sync

A single sync often contains resources with **dependencies**: the namespace must
exist before the Deployment; a CRD must be established before its custom resources; a
database migration Job should run before the new Pods start. Argo CD orders a sync
with **sync waves** — an annotation on each resource:

```yaml
metadata:
 annotations:
 argocd.argoproj.io/sync-wave: "-1" # lower numbers apply first
```

Within a sync, Argo CD applies all resources in wave `-1`, waits for them to be
healthy, then wave `0`, then `1`, and so on (default wave is `0`). Typical ordering:
namespace (`-1`) → config/secrets (`0`) → workloads (`1`) → Services/Ingress (`2`).
PreSync/PostSync **hooks** (e.g. a migration Job) layer on top for lifecycle steps.
Waves make a multi-resource sync deterministic instead of a race.

#### Rollback by revert

Because Git is the source of truth, **rollback is `git revert`**. You revert the
commit that introduced the bad change; Argo CD sees the environment is now OutOfSync
against the restored state and reconciles back. No special tooling, no snapshot — the
same mechanism as forward delivery, run backward. Across environments, Git history
*is* the correlation: the commit that promoted a change to prod points at the diff to
revert, and reverting it returns prod to the exact prior declared state.

---

### 2. Why it matters for platform engineering

Multi-environment promotion is the day-to-day workflow a delivery platform exists to
provide:

- **It's the paved road for shipping.** Teams promote by opening a PR against a
 folder — no environment-specific credentials, no bespoke deploy scripts. The same
 motion works for every service.
- **Environments stay consistent and auditable.** A folder layout makes "what differs
 between staging and prod" a one-line diff, which is how you catch the config drift
 that causes "works in staging, breaks in prod."
- **Production gets the right guardrails.** You configure fast auto-sync for dev and
 staging but a manual gate (and sync windows) for prod — centrally, once, for every
 team.
- **Recovery is routine.** Rollback is a revert any engineer can do and any reviewer
 can understand, which shortens incidents.
- **It composes with 08.3.** An ApplicationSet with a list/git generator produces the
 per-environment Applications from this folder layout, so the whole promotion
 pipeline is itself declarative.

---

### 3. Mental model

Environments are **folders**, promotion is a **diff you move forward**, and a sync is
an **ordered** reconcile. The loop is the same as always — Git is desired state —
only now there are several destinations, each reading its own folder.

```text
 main branch (one source of truth)
 ├── overlays/dev ──► Application web-dev ──► reconcile ──► namespace web-dev
 ├── overlays/staging ──► Application web-staging ──► reconcile ──► namespace web-staging
 └── overlays/prod ──► Application web-prod ──► reconcile ──► namespace web-prod
 ▲
 promotion = a PR that copies a validated change from one overlay to the next
 rollback = git revert of that PR; the loop reconciles back
```

Three rules to remember:

1. **Folders, not branches.** One branch of truth; a directory per environment.
2. **Promote a diff, don't redeploy.** Move the validated change forward by PR; don't
 rebuild per environment.
3. **Order with waves; recover with revert.** Sync waves sequence a rollout; `git
 revert` reverses it.

---

### 4. Minimal implementation

The smallest honest multi-environment setup is a Kustomize base plus two overlays
that differ only by what must differ. The "promotion" is visible as a one-field diff:

```bash
# Render each environment and compare — the diff IS the promotion surface.
kubectl kustomize overlays/dev | grep -E 'image:|replicas:'
# → image: nginx:1.27.1-alpine replicas: 1 (candidate under test in dev)
kubectl kustomize overlays/prod | grep -E 'image:|replicas:'
# → image: nginx:1.27.0-alpine replicas: 3 (current prod)
```

```yaml
# overlays/prod/kustomization.yaml — prod differs from base ONLY where it must.
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: web-prod
resources:
 -../../base
 - namespace.yaml # annotated sync-wave "-1": created before the workload
patches:
 - path: replicas-patch.yaml # replicas: 3
images:
 - name: nginx
 newTag: 1.27.0-alpine # promoting = bump this to the validated tag
```

Promoting `1.27.1-alpine` to prod is a one-line change to `newTag`, reviewed as a PR;
rolling back is `git revert` of that commit. The lab turns this into the full
dev→staging→prod workflow with sync waves and a manual prod gate.

---

### 5. Hands-on lab

You'll build a base-plus-overlays config repo for dev, staging, and prod; render each
overlay to see the promotion surface; watch Argo CD apply a sync in wave order
(namespace → config → workload → service); promote a validated image tag forward by a
PR-style commit; gate prod behind a manual sync; and roll an environment back with
`git revert`.

➡️ **Start the lab**

---

### 6. Production considerations

- **Environment parity.** Overlays should differ *only* where they must (scale,
 tags, limits, hostnames). The more base you share, the less "works in staging,
 fails in prod." Review overlay diffs for accidental divergence.
- **Promotion automation and provenance.** Have CI open the promotion PR with the
 exact validated digest (prefer immutable image **digests** over mutable tags), so
 what you tested is byte-for-byte what you ship.
- **Production gates.** Use manual sync and **sync windows** to require approval and
 to block deploys during freezes or outside business hours — while keeping dev and
 staging fully automated.
- **Sync-wave health gating.** Waves advance only when the prior wave is healthy;
 make sure your resources report health correctly (e.g. a migration Job must
 actually complete) or a sync can stall. Keep waves few and meaningful.
- **Rollback correlation.** Record which commit is live in each environment (Argo CD
 tracks the synced revision). During an incident you want to map "prod is broken" to
 "revert commit abc123" in seconds.
- **Config vs app repos.** Keep the config repo separate from app source so a
 promotion PR touches only deployment intent, with its own reviewers and branch
 protection.

---

### 7. Common mistakes

- **Branch-per-environment.** Branches diverge, promotion becomes merge archaeology,
 and "what's different in prod?" is unanswerable. *Fix:* one branch, a folder per
 environment.
- **Copy-pasting whole environments.** Duplicating full manifests per env guarantees
 drift and double edits. *Fix:* a shared base with thin overlays holding only
 differences.
- **Mutable image tags (`:latest`, floating tags).** "It worked yesterday" because
 the tag moved under you. *Fix:* pin immutable tags or digests and promote the exact
 artifact.
- **No ordering, racey syncs.** Workloads start before their namespace/config/CRDs
 exist and fail intermittently. *Fix:* sync waves (and PreSync hooks for migrations).
- **Auto-syncing prod like dev.** A bad merge ships straight to customers. *Fix:*
 manual sync gate and sync windows on prod; fast auto-sync below it.
- **Treating rollback as special.** Scrambling for a bespoke rollback path during an
 incident. *Fix:* rehearse `git revert`; it's just delivery in reverse.

---

### 8. Assessment

**Knowledge checks**

1. Give two concrete reasons folder-per-environment beats branch-per-environment.
2. In a Kustomize layout, what belongs in `base/` vs an `overlay/`?
3. What problem do sync waves solve, and which wave would a namespace use relative to
 its Deployment?
4. How do you roll back a bad production change in GitOps?
5. Why gate prod with a manual sync while leaving dev on auto-sync?

**Concept exercise**

> Describe how you'd promote a change from test to production **without using the
> words "merge a branch" or naming a tool.** Explain promotion as moving a reviewed
> difference forward, so it would apply to any declarative delivery system.

**Trade-off / debugging exercise**

> A team runs `dev`, `staging`, `prod` as three long-lived branches and keeps hitting
> "staging and prod have silently drifted." Propose a folder-based redesign and say
> what it fixes. Then: after a prod sync, the new Pods crash-loop because their
> namespace and config aren't present yet. Explain the ordering bug and the exact
> sync-wave annotations that fix it.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** Environments are all visible on one branch (explicit diffs, linear
 history), and promotion is a reviewable config change rather than a divergent
 branch merge; no branch drift or cherry-pick tangle.
- **Q2:** `base/` holds what's common to all environments; an `overlay/` holds only
 the per-environment differences (replicas, image tag, limits, hostnames).
- **Q3:** They order a multi-resource sync by dependency. A namespace uses a *lower*
 wave (e.g. `-1`) than its Deployment (e.g. `1`) so it exists first.
- **Q4:** `git revert` the commit that introduced the change; the agent reconciles
 the environment back to the restored declared state.
- **Q5:** Dev values speed and fast feedback; prod values control and reviewability.
 A manual gate (plus sync windows) prevents an unreviewed or ill-timed change from
 reaching customers automatically.
- **Debugging:** the redesign is one `main` branch with `overlays/{dev,staging,prod}`
 so drift is a visible diff. The crash-loop is a wave ordering bug: annotate the
 Namespace `sync-wave: "-1"` and config `"0"` so they apply (and go healthy) before
 the Deployment at `"1"`.

</details>

---

### 9. Further reading

- Kustomize — [Bases and overlays](https://kubectl.docs.kubernetes.io/references/kustomize/)
- Argo CD — [Sync phases and waves](https://argo-cd.readthedocs.io/en/stable/user-guide/sync-waves/)
- Argo CD — [Sync windows](https://argo-cd.readthedocs.io/en/stable/user-guide/sync_windows/)
 and [resource hooks](https://argo-cd.readthedocs.io/en/stable/user-guide/resource_hooks/)
- Codefresh — [Environment promotion and the GitOps repo-per-environment debate](https://codefresh.io/blog/how-to-model-your-gitops-environments-and-promote-releases-between-them/)
- Argo CD — [Best practices: separate config and source repos](https://argo-cd.readthedocs.io/en/stable/user-guide/best_practices/)

---


_Previous:_ 08.3 — Argo CD ApplicationSets
· _Next:_ 08.5 — Secrets in GitOps →

---

## Secrets in GitOps

> GitOps says "put all desired state in Git" — but you must **never** put secrets in
> Git in plaintext, because Git history is permanent and world-readable to anyone
> who clones it. This module resolves that tension: keep the *reference* in Git and
> the *value* in a secret manager, and let a controller materialize the real Secret
> in-cluster. We compare Sealed Secrets, External Secrets Operator, Vault, and SOPS,
> and implement the recommended one.

**You'll need:** Argo CD Fundamentals, Helm from, and a kind cluster.

### Learning objectives

By the end of this module you will be able to:

- Explain why **plaintext secrets in Git are unacceptable**, and why base64 is not
 encryption.
- Compare the four mainstream patterns — **Sealed Secrets, ESO, Vault, SOPS** — and
 their trade-offs.
- Justify **External Secrets Operator (ESO)** as the default for most platforms.
- Implement an **`ExternalSecret`** that syncs a secret from a backend into a native
 Kubernetes Secret.
- Describe **secret rotation** under GitOps and where the audit trail lives.

---

### 1. Concept

#### The core problem

GitOps wants everything in Git. Secrets are state. So the naive move is to commit a
Kubernetes `Secret` — but a `Secret`'s `data` is only **base64-encoded, not
encrypted**. Anyone who can read the repo can decode it in one command:

```bash
echo 'c3VwZXItc2VjcmV0LXBhc3N3b3Jk' | base64 -d # -> super-secret-password
```

Worse, **Git history is forever**. Even if you delete the secret in a later commit,
it lives in the history, in every clone, fork, and backup. A credential committed
once must be considered compromised and rotated. So the rule is absolute: **no
plaintext secrets in Git — ever.** The whole field below exists to keep the GitOps
promise ("state in Git") without breaking that rule.

The resolution is a separation: **the reference lives in Git; the value lives in a
secret manager; a controller joins them in the cluster.** Git stays the source of
truth for *what secret a workload needs*, never for *the secret itself*.

#### Four ways to do it

- **Sealed Secrets (Bitnami).** You encrypt a Secret *client-side* with `kubeseal`
 using an in-cluster controller's public key, producing a `SealedSecret` (ciphertext)
 that is safe to commit. The controller decrypts it in-cluster into a real Secret.
 - *Pros:* simple, no external system; Git holds only ciphertext.
 - *Cons:* the controller's private key is now your crown jewel (back it up, or a
 cluster loss means you can't decrypt anything); keys are per-cluster, so the same
 `SealedSecret` isn't portable; rotation and re-sealing are manual chores.
- **External Secrets Operator (ESO).** Secrets live in a dedicated **secret manager**
 (HashiCorp Vault, AWS/GCP/Azure secret managers, and many more). An `ExternalSecret`
 in Git *references* them; ESO fetches the values and **syncs** them into native
 Kubernetes Secrets, refreshing on an interval.
 - *Pros:* one source of truth for secrets with real access control, auditing, and
 rotation; Git holds only references; integrates with tools your org already uses.
 - *Cons:* you must run a secret manager and the operator.
- **Vault Agent / Secrets Store CSI driver.** Instead of creating Kubernetes Secrets,
 secrets are **injected or mounted into the Pod at runtime** straight from Vault.
 - *Pros:* secrets need never become Kubernetes `Secret` objects; supports dynamic,
 short-lived, leased credentials.
 - *Cons:* couples workloads to Vault and adds sidecar/CSI complexity; a bigger lift
 than ESO for the common case.
- **SOPS (Secrets OPerationS).** Encrypt the *values* inside a YAML/JSON file with a
 KMS key (cloud KMS, `age`, or PGP); commit the encrypted file to Git; decrypt at
 apply time.
 - *Pros:* file-level encryption that works for any config; Git-native, and Flux
 supports it directly.
 - *Cons:* key management is on you; Argo CD needs a plugin (e.g. KSOPS) to decrypt
 during render; encrypts fields in files rather than centralizing secrets.

#### Why ESO is the default recommendation

For most platforms, **ESO wins** because it keeps secrets in a purpose-built manager
— the system your security team already audits, rotates, and access-controls — while
Git holds nothing sensitive at all, only a pointer. You get rotation (change the
value in the manager, ESO propagates it), a real audit trail (the manager logs
access), and least privilege (scope ESO's access per namespace/store). Sealed Secrets
is a fine lightweight start when you have no secret manager; SOPS is excellent when
you prefer file-based encryption (and especially with Flux); Vault
Agent/CSI is the choice when you need runtime injection or dynamic credentials. But
the sensible default for a GitOps platform is **ESO backed by a secret manager.**

#### What goes in Git with ESO

An `ExternalSecret` is **safe to commit** — it contains no secret, only a reference:

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
 name: web-db
 namespace: web
spec:
 refreshInterval: 1h # re-read the backend this often (rotation window)
 secretStoreRef:
 name: vault-backend # which SecretStore (backend) to use
 kind: SecretStore
 target:
 name: web-db # the native K8s Secret ESO will create/own
 creationPolicy: Owner
 data:
 - secretKey: DATABASE_URL # key in the resulting K8s Secret
 remoteRef:
 key: web # path/name in the backend
 property: database-url # field within that entry
```

A **`SecretStore`** (also committable) describes *how to reach the backend* and *how
to authenticate* — the credential for the store itself is the one secret you bootstrap
out-of-band (or via workload identity in the cloud). Everything else is GitOps as
usual.

---

### 2. Why it matters for platform engineering

Secrets are where GitOps most often goes wrong, and getting them right is a core
platform responsibility:

- **One leaked commit is a permanent breach.** A platform that makes "commit a Secret"
 easy will eventually leak one irreversibly. Providing a safe, paved path (ESO +
 store) is how you prevent it by design.
- **Rotation becomes a platform feature.** With ESO, rotating a credential is "update
 it in the manager"; every consuming cluster picks it up automatically. Without it,
 rotation means hunting through repos and re-sealing files.
- **Least privilege and audit.** A secret manager gives per-secret access policies and
 an access log. The platform wires ESO to it with scoped, per-tenant permissions so
 Team A can't read Team B's secrets.
- **It closes the GitOps security story.** –08.4 removed cluster
 credentials from CI; this module ensures the one thing you *don't* put in Git stays
 out of it. Project 2 requires exactly this: secrets via ESO, not plaintext files.

---

### 3. Mental model

Extend the reconcile loop to secrets with one rule: **reference in Git, value in a
vault, join in the cluster.** Git never holds the value; a controller reconciles the
native Secret from the backend.

```text
 Git repo (desired state) Secret manager (the VALUE)
 ┌───────────────────────┐ ┌───────────────────────┐
 │ ExternalSecret │ references │ web/database-url = │
 │ (a pointer, no value) │ ─────────────────► │ "postgres://…" │
 └───────────┬───────────┘ └───────────┬───────────┘
 │ Argo CD syncs the pointer │ ESO fetches the value
 ▼ ▼
 ┌──────────────────────────────────────────────────────┐
 │ cluster: ESO materializes a native Secret `web-db` │
 │ (refreshed every interval; rotates when the backend │
 │ value changes) │
 └──────────────────────────────────────────────────────┘
```

Three rules to remember:

1. **Base64 is not encryption.** A committed `Secret` is a plaintext leak.
2. **Reference in Git, value in a manager.** Git holds a pointer; the backend holds
 the secret.
3. **Rotation = change the value in the manager.** The controller propagates it; no
 Git change needed.

---

### 4. Minimal implementation

The smallest real setup: run ESO, point a `SecretStore` at a backend, and declare one
`ExternalSecret`. ESO then creates a native Secret you can mount like any other.

```bash
# Install ESO (free, in-cluster). It serves the external-secrets.io/v1 CRDs.
helm repo add external-secrets https://charts.external-secrets.io
helm install external-secrets external-secrets/external-secrets \
 -n external-secrets --create-namespace --wait
```

```bash
# With a SecretStore and ExternalSecret applied, ESO produces a normal Secret:
kubectl -n web get externalsecret web-db # STATUS: SecretSynced
kubectl -n web get secret web-db -o jsonpath='{.data.DATABASE_URL}' | base64 -d; echo
# -> the value, fetched from the backend — never stored in Git
```

The `ExternalSecret` and `SecretStore` are committed to Git and synced by Argo CD like
any other manifest; the sensitive value only ever exists in the backend and in the
in-cluster Secret ESO creates. The lab stands up a local Vault as the backend and
demonstrates rotation end to end.

---

### 5. Hands-on lab

You'll install ESO, run a local HashiCorp Vault (dev mode) as the secret backend,
store a database URL in it, and declare a `SecretStore` and `ExternalSecret` that sync
it into a native Kubernetes Secret. Then you'll rotate the value in Vault and watch
ESO propagate it — with nothing sensitive ever touching Git.

➡️ **Start the lab**

---

### 6. Production considerations

- **Lock down the store credential.** The one bootstrap secret (how ESO authenticates
 to the backend) should use workload identity (IRSA/Workload Identity) or a tightly
 scoped token, not a shared root token. In the lab we use a root token for
 simplicity — never do that in production.
- **Scope access per tenant.** Use namespaced `SecretStore`s (or carefully scoped
 `ClusterSecretStore`s) and backend policies so each team reads only its own secrets.
- **Rotation strategy.** Decide refresh intervals against your rotation SLA; shorter
 intervals propagate rotations faster but add backend load. Rotating in the manager
 should require no Git change.
- **Audit and alerting.** Rely on the backend's access log for "who read what," and
 alert on `ExternalSecret` sync failures — a stale or missing Secret is an outage
 waiting to happen.
- **Blast radius and backups.** For Sealed Secrets, back up the controller's private
 key or a cluster loss is unrecoverable. For SOPS, protect and rotate the KMS keys.
 For ESO/Vault, protect the backend and its unseal/root material.
- **Don't log or echo secrets.** Materialized Secrets are still Kubernetes Secrets —
 apply RBAC, enable encryption at rest for etcd, and avoid dumping them in CI logs.

---

### 7. Common mistakes

- **Committing a base64 `Secret` and thinking it's safe.** Base64 is encoding, not
 encryption; it's a plaintext leak with extra steps. *Fix:* never commit secret
 values — use ESO/SOPS/Sealed Secrets.
- **"We'll remove it from Git later."** History is permanent; the secret is already
 compromised across every clone. *Fix:* treat any committed secret as leaked and
 rotate it immediately.
- **Using a root/admin token for the store in production.** Convenient and
 catastrophic if leaked. *Fix:* workload identity or a least-privilege token scoped
 to the needed paths.
- **No rotation plan.** Secrets set once and never changed. *Fix:* rotate in the
 manager on a schedule; let ESO propagate; alert on failures.
- **Not backing up Sealed Secrets keys / SOPS keys.** A lost key makes every encrypted
 secret unrecoverable. *Fix:* back up and rotate key material deliberately.
- **One giant Secret for everything.** A single blob maximizes blast radius and
 over-shares. *Fix:* scope secrets per app/namespace with least-privilege access.

---

### 8. Assessment

**Knowledge checks**

1. Why is committing a base64-encoded Kubernetes `Secret` to Git unsafe?
2. Name the four approaches and give ESO's main advantage over Sealed Secrets.
3. With ESO, what exactly is stored in Git, and what is *not*?
4. How does secret rotation work under ESO, and where is it audited?
5. When might you choose Vault Agent/CSI or SOPS instead of ESO?

**Concept exercise**

> Explain how a GitOps system can "keep all state in Git" **without ever putting a
> secret value in Git** — and do it without naming ESO, Vault, or SOPS. Describe the
> reference-vs-value split so it would apply to any implementation.

**Trade-off / debugging exercise**

> A teammate commits a `Secret` with a real database password (base64) "just to
> unblock the deploy," planning to remove it tomorrow. State exactly why "remove it
> tomorrow" doesn't fix it and what must happen now. Then design the replacement: which
> approach you'd adopt for a multi-team platform, what lives in Git, and how a
> credential rotation would flow with zero Git changes.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** Base64 is reversible encoding, not encryption — anyone who can read the repo
 decodes it instantly — and Git history keeps it forever, in every clone.
- **Q2:** Sealed Secrets, ESO, Vault Agent/CSI, SOPS. ESO keeps secrets in a central,
 auditable, rotatable manager with per-secret access control, and puts only
 references in Git.
- **Q3:** Git holds the `ExternalSecret` and `SecretStore` (references and connection
 config); it does **not** hold the secret value, which stays in the backend and in
 the in-cluster Secret ESO materializes.
- **Q4:** You change the value in the secret manager; ESO re-reads it on its refresh
 interval and updates the Kubernetes Secret — no Git change. The manager's access log
 is the audit trail.
- **Q5:** Vault Agent/CSI for runtime injection or dynamic/short-lived credentials;
 SOPS for file-based encryption workflows (especially with Flux) or when you don't
 want to run a secret manager.
- **Debugging:** "remove it tomorrow" fails because the password is already in history
 and every clone — it's compromised now and must be **rotated immediately** (and the
 commit history scrubbed). Replacement: ESO backed by a secret manager; Git holds the
 `ExternalSecret`/`SecretStore`; rotation is a value change in the manager that ESO
 propagates with no Git commit.

</details>

---

### 9. Further reading

- External Secrets Operator — [Documentation](https://external-secrets.io/latest/)
 and [the `ExternalSecret` API](https://external-secrets.io/latest/api/externalsecret/)
- Sealed Secrets — [Bitnami Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets)
- SOPS — [Mozilla/`getsops` SOPS](https://github.com/getsops/sops)
- HashiCorp Vault — [Kubernetes integrations](https://developer.hashicorp.com/vault/docs/platform/k8s)
 and the [Secrets Store CSI driver](https://secrets-store-csi-driver.sigs.k8s.io/)
- Argo CD — [Secret management options](https://argo-cd.readthedocs.io/en/stable/operator-manual/secret-management/)

---


_Previous:_ 08.4 — Multi-Environment GitOps
· _Next:_ 08.6 — GitOps Maturity Model →

---

## GitOps Maturity Model

> "Do we do GitOps?" is the wrong question — it's not a yes/no. This module gives you
> a **maturity model**: five honest levels from "manual `kubectl`" to "adaptive
> platform GitOps," a way to assess where a real platform sits, and the discipline to
> pick the single next rung instead of chasing the top. It's also your bridge into
> Project 2, where you build toward Level 3.

**You'll need:** –08.5. This is a reflection and assessment module — no cluster required.

### Learning objectives

By the end of this module you will be able to:

- Describe the **five GitOps maturity levels** and what distinguishes each.
- **Assess** a platform's maturity across concrete dimensions, honestly.
- Identify the **single highest-value next step** rather than boiling the ocean.
- Recognize **maturity theater** — tools adopted without the practice.
- Connect the model to the **platform you'll build in Project 2**.

---

### 1. Concept

Maturity isn't about owning the most tools; it's about how much of your delivery is
**declarative, pulled, continuously reconciled, and safe** — and how much is still
manual, tribal, or risky. Here is a five-level model (adapted from community GitOps
and CNCF maturity work) with the signals that place a platform at each level.

#### Level 0 — No GitOps

- Changes are `kubectl apply`, `helm upgrade`, or console clicks done by hand.
- Knowledge lives in scripts, runbooks, and people's heads.
- **No audit trail**: "who changed prod, when, why?" has no reliable answer.
- *Signal:* the cluster is a pet; nobody is sure it could be rebuilt from Git.

#### Level 1 — Manual GitOps

- Declarative config lives in Git (the source of truth is written down).
- But sync is **manual** — a human runs the deploy — and there's **no self-healing or
 drift detection**.
- You get *some* audit trail (commits), but the cluster can still silently diverge
 from Git.
- *Signal:* "it's all in Git" is true, yet drift and manual steps remain.

#### Level 2 — Automated GitOps

- **Auto-sync** is on: merges reconcile without a human.
- **Self-healing** corrects out-of-band drift; the cluster converges to Git.
- Simple apps may get an **image updater** that bumps tags automatically.
- *Signal:* for application delivery, the reconcile loop runs itself.

#### Level 3 — Full Platform GitOps

- **All** cluster configuration — not just apps, but ingress, RBAC, operators,
 add-ons — is managed via GitOps.
- **Secrets** are handled safely (ESO or equivalent), never plaintext in Git.
- **Multi-environment promotion** is automated (overlay bump → PR → auto-sync) with
 a production gate.
- **Drift alerts** and breaking-change detection are wired into observability.
- *Signal:* a new cluster can be bootstrapped from Git, secrets and all. **This is the
 target for Project 2.**

#### Level 4 — Adaptive Platform GitOps

- **Progressive delivery** (Argo Rollouts / Flagger) — canary/blue-green with
 automated analysis and rollback — is integrated into sync.
- **Cross-cluster GitOps** manages a fleet from one control plane.
- **Policy evaluation** (OPA/Kyverno) runs as part of the sync, so non-compliant
 changes are rejected before they land.
- **Cluster bootstrapping** is automated: stand up a new cluster and it configures
 itself.
- *Signal:* delivery is self-driving and self-governing across many clusters.

```text
 L0 ──────► L1 ──────► L2 ──────► L3 ──────► L4
 manual in Git, auto-sync whole progressive,
 kubectl manual + self- platform multi-cluster,
 no audit sync heal in GitOps policy-gated
 + secrets + bootstrap
 │ │ │ │ │
 └──────────┴──────────┴──────────┴───────────┘
 how much of delivery is declarative, pulled, reconciled, and safe?
```

#### Dimensions, not a single number

A platform is rarely cleanly "a Level 2." Assess it across **dimensions** and you'll
see a realistic, jagged profile:

- **Source of truth** — is all state in Git, or just some?
- **Sync automation** — manual, auto-sync, or fully hands-off?
- **Drift & self-healing** — detected? corrected? alerted?
- **Secrets** — plaintext (danger), Sealed/SOPS, or a managed store via ESO?
- **Promotion** — manual per env, or PR-driven with gates?
- **Scope** — apps only, or all cluster config and add-ons?
- **Progressive delivery** — big-bang sync, or canary with analysis?
- **Multi-cluster** — one cluster, or a fleet from one control plane?
- **Policy & compliance** — reviewed by humans, or enforced at sync?
- **Observability** — can you see sync status, drift, and failures, and alert on them?

Your **overall** level is best read as the *lowest* dimension that still causes real
pain — because that's what breaks first. A platform with slick progressive delivery
but plaintext secrets in Git is not "Level 4"; it's a Level 3 practice with a Level 0
security hole.

---

### 2. Why it matters for platform engineering

A maturity model is a planning and communication tool, not a vanity score:

- **It creates a shared language.** "We're Level 2 and want Level 3 by Q3, starting
 with secrets" communicates strategy to leadership and teams in one line.
- **It prevents over- and under-investing.** Many platforms rush to progressive
 delivery (Level 4 shininess) while still hand-syncing prod or committing secrets.
 The model forces you to fix the foundation first.
- **It turns a vague goal into a roadmap.** Assess dimensions, find the lowest painful
 one, and that's your next quarter's work — concrete and defensible.
- **It sets expectations honestly.** Maturity is earned rung by rung; you can't buy
 Level 4 by installing a tool. Naming the levels keeps everyone grounded.
- **It frames Project 2.** The next thing you build in this course is a Level 3
 platform: all config in Git, ESO for secrets, multi-env promotion, drift alerts.
 This module is how you'll know you got there.

---

### 3. Mental model

Maturity is a **ladder you climb one rung at a time**, and each rung widens how much
of delivery the reconcile loop owns — from one app, to all apps, to all config, to
the whole fleet under policy.

```text
 coverage of the reconcile loop grows as you climb:

 L0 nothing reconciles (manual) □□□□□
 L1 Git holds state, humans sync ■□□□□
 L2 apps auto-sync and self-heal ■■□□□
 L3 ALL config + secrets + promotion, with alerts ■■■■□ ← Project 2 target
 L4 + progressive delivery, fleet, policy gates ■■■■■
```

Three rules to remember:

1. **Assess by dimensions; score by the weakest painful one.** The lowest rung that
 hurts is your real level.
2. **Climb the next rung, not the tallest.** The best next step removes your current
 biggest pain — usually secrets or manual prod sync, not a canary engine.
3. **Tools are not maturity.** Installing Argo Rollouts doesn't make you Level 4;
 *practicing* progressive delivery does.

---

### 4. Minimal implementation

A maturity assessment is just a scored rubric. Rate each dimension 0–4, note the
evidence, and read off the weakest painful rung:

```text
dimension level evidence
------------------- ----- ---------------------------------------------------
source of truth 3 apps + most config in Git; a few manual add-ons
sync automation 2 auto-sync on; prod still manually synced (by design)
drift & self-healing 2 self-heal on; no drift ALERTING yet
secrets 1 Sealed Secrets for some; two plaintext Secrets remain ← weakest, and risky
promotion 2 overlays + PRs; promotion not automated from CI
.........
------------------- ----- ---------------------------------------------------
overall: Level 2 (secrets at 1 is the dangerous outlier → fix first)
next step: migrate the two plaintext Secrets to ESO; add drift alerts
```

The output isn't the number — it's the **one prioritized next step** the number
justifies. That's exactly what the lab produces for a platform you choose.

---

### 5. Hands-on lab

You'll run a structured self-assessment: score a platform (a real one you know, or the
provided fictional scenario) across the maturity dimensions, compute an honest overall
level, and write a single prioritized next step with its justification. The deliverable
is a maturity rating plus a next-step plan — the artifact a platform team actually
presents.

➡️ **Start the lab**

---

### 6. Production considerations

- **Measure, don't guess.** Back scores with evidence: sync status dashboards, drift
 reports, "percentage of config under GitOps," time-to-rollback. A maturity claim you
 can't show is theater.
- **Beware maturity theater.** Argo Rollouts installed but every release still
 big-bangs; ESO present but secrets still committed "temporarily." The tool is not
 the practice.
- **Sequence by risk, then value.** A Level 0 dimension in **secrets** or **audit**
 outranks a shiny Level 4 feature elsewhere — fix the dangerous outlier first.
- **Organizational maturity matters too.** Who can approve a prod sync? Is there
 on-call for failed syncs? Culture and process gate how high the tech can climb.
- **It's never "done."** Like the platform itself, maturity has a
 roadmap, not a finish line; re-assess periodically as scope and scale grow.
- **Right-size the target.** Not every platform needs Level 4. A small team may
 rationally stop at a solid Level 3. Match the level to the stakes, not to fashion.

---

### 7. Common mistakes

- **Treating maturity as a single number.** It hides a dangerous low dimension behind
 a flattering average. *Fix:* score dimensions; act on the weakest painful one.
- **Chasing Level 4 with a Level 1 foundation.** Canary deploys while prod is
 hand-synced and secrets sit in Git. *Fix:* climb the next rung; secure the base
 first.
- **Confusing tools with practice (maturity theater).** "We have Rollouts/ESO" while
 not actually doing progressive delivery or removing plaintext secrets. *Fix:* assess
 the practice and its evidence, not the install list.
- **Assessing without evidence.** Optimistic self-scores that don't survive an
 incident. *Fix:* require a dashboard, report, or metric behind each score.
- **One-and-done assessment.** Scoring once and never revisiting as the platform
 grows. *Fix:* re-assess on a cadence; maturity drifts like everything else.
- **Copying someone else's target level.** Adopting Level 4 goals that your stakes
 don't warrant. *Fix:* choose a target proportional to your reliability and
 compliance needs.

---

### 8. Assessment

**Knowledge checks**

1. In one line each, what distinguishes Level 1 from Level 2, and Level 2 from Level 3?
2. Why read overall maturity as the *weakest painful dimension* rather than an average?
3. Give a concrete example of "maturity theater."
4. Which maturity level is the target for Project 2, and name three of its properties.
5. Why isn't "install Argo Rollouts" enough to be Level 4?

**Concept exercise**

> Describe how you'd judge a team's delivery maturity **without naming any tool or any
> maturity level number.** Phrase it entirely in terms of behavior — what's declared,
> what's automated, what's reconciled, what's safe — so it would apply to any stack.

**Trade-off / debugging exercise**

> A platform has automated canary deployments and multi-cluster sync, but two database
> passwords are committed as base64 Secrets and production is still synced by hand.
> What overall level is this, and why? Name the first two next steps and justify the
> order against the dimensions.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** L1→L2: sync becomes automatic and the cluster self-heals drift (vs. manual
 sync, no drift correction). L2→L3: scope expands from apps to **all** config, plus
 safe secrets, automated multi-env promotion, and drift alerting.
- **Q2:** An average hides a dangerous low dimension (e.g. plaintext secrets) that will
 break or breach first; the weakest painful rung is what actually limits you.
- **Q3:** Having ESO or Argo Rollouts installed while secrets are still committed to
 Git or every release still big-bangs — the tool without the practice.
- **Q4:** **Level 3** (Full Platform GitOps): all cluster config in Git, secrets via
 ESO (no plaintext), automated multi-environment promotion with a prod gate, drift
 alerts.
- **Q5:** Maturity is the *practice*, not the install; Level 4 means you actually run
 analyzed canaries with automated rollback across the fleet, not that a controller
 exists.
- **Debugging:** Despite Level 4 features, committed secrets (Level 0 on the secrets
 dimension) make this a **Level 1–2 platform with a critical security hole**. First
 steps: (1) rotate and migrate the two secrets to a managed store (ESO) — it's a live
 breach; (2) add a production sync gate/policy and drift alerting. Security and audit
 outrank progressive-delivery polish.

</details>

---

### 9. Further reading

- OpenGitOps — [Principles](https://opengitops.dev/) (the yardstick maturity measures
 against)
- CNCF — [Platform Engineering Maturity Model](https://tag-app-delivery.cncf.io/whitepapers/platform-eng-maturity-model/)
- Argo — [Rollouts (progressive delivery)](https://argo-rollouts.readthedocs.io/en/stable/)
 and [Flagger](https://flagger.app/)
- CNCF — [GitOps WG and OpenGitOps project](https://github.com/open-gitops/project)
- Codefresh — [GitOps maturity and best practices](https://codefresh.io/learn/gitops/)

---


_Previous:_ 08.5 — Secrets in GitOps
· _Next:_ 09 · Platform Project 02 — GitOps Platform →
