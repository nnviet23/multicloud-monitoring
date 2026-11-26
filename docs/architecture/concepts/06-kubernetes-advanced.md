# 06 · Kubernetes Advanced

> **Project Applicability:** Active in Project — Custom Resource Definitions (CRDs), Operators (e.g., OpenTelemetry Operator), and Admission Webhooks (Kyverno under `deploy/policies/`) are actively used in the platform.

> You can already run workloads on Kubernetes and deliver them with Helm
> and GitOps (Phases 7–8, Project 2). This phase is where you stop being a *user* of
> Kubernetes and become a *builder of platforms on top of it*: you teach the API new
> nouns, encode your operational runbooks as software, enforce guardrails at the
> moment a request is admitted, and operate across many clusters. This is the
> machinery behind every real Internal Developer Platform.

## Why extend Kubernetes?

In Project 1 you onboarded a team **by hand**: create a namespace, label it, apply a
`ResourceQuota` and `LimitRange`, wire up RBAC, and hope nobody forgot a step. That
runbook works for three teams. It does not work for three hundred, and it does not
survive the 2am mistake where someone skips the quota and a runaway Deployment eats
the cluster.

The Kubernetes answer is not "write a bigger shell script." It is to **extend the
platform itself** so the right thing happens automatically:

- **Custom Resource Definitions (CRDs)** let you add your own objects — an
 `Environment`, a `Database`, a `TenantApp` — to the same API every tool already
 speaks. Your platform's concepts become first-class API citizens.
- **Operators** encode your runbook as a controller: the reconciliation loop from
, now driving *your* resources. "Create a namespace, RBAC, quota, and
 limits for this team" becomes software that never forgets a step and heals drift.
- **Admission control** (webhooks and CEL policies) enforces guardrails *before* an
 object is ever stored — injecting cost labels, requiring security context, or
 rejecting what violates policy — without trusting every developer to remember.
- **API extension patterns** (subresources, field selectors, Server-Side Apply)
 make your custom APIs behave like the built-ins, so `kubectl scale`, HPAs, and
 multi-writer automation Just Work on them.
- **Multi-cluster** is the reality once you have more than one environment, region,
 or tenant boundary — and it changes how you think about desired state and delivery.

Every idea here is the same reconciliation loop you already know, aimed at problems
you previously solved with tickets and tribal knowledge. By the end you will have
turned Project 1's manual onboarding into a running operator.

## Custom Resource Definitions

> Kubernetes ships with Pods, Deployments, and Services — but your platform thinks in
> `Environment`s, `Database`s, and `TenantApp`s. A **Custom Resource Definition**
> teaches the API server a new noun, so your own concepts become first-class API
> objects that `kubectl`, RBAC, GitOps, and admission all understand. This is the
> foundation every operator and most of the CNCF ecosystem is built on.

**You'll need:** Kubernetes Architecture (the reconciliation loop, `spec`/`status`) and a local [kind](https://kind.sigs.k8s.io/) cluster.

### Learning objectives

By the end of this module you will be able to:

- Explain what a CRD adds to a cluster — and, crucially, what it does **not** add.
- Read a CRD in terms of **group, version, kind, scope, and schema**.
- Validate custom resources with an **OpenAPI v3 structural schema** and **CEL**
 (`x-kubernetes-validations`) rules, and say when CEL replaces a webhook.
- Reason about **CRD versioning** (`v1alpha1 → v1beta1 → v1`), served vs stored
 versions, and conversion.
- Explain why the **status subresource** splits spec writes from status writes.

---

### 1. Concept

#### The problem: your platform's nouns don't exist yet

Your platform has concepts. "Give team-payments a **dev environment**." "Provision a
**database** for this service." But the Kubernetes API has never heard of an
`Environment` or a `Database`. So where does that state live?

- **In a ConfigMap?** It's an unvalidated blob of YAML-in-a-string. No typing, no
 required fields, no `kubectl get environments`, and every tool has to re-parse it.
- **In an external database?** Now you have two sources of truth, no `kubectl`, no
 RBAC, no `watch`, no audit log — you've left the platform.

Both lose the things that make Kubernetes good: a typed, validated, watchable,
access-controlled API.

#### What a CRD actually does

A **CustomResourceDefinition** registers a new resource *type* with the API server.
Apply one, and the API server immediately:

- serves a new REST endpoint, e.g. `/apis/platform.example.com/v1alpha1/environments`;
- stores instances (**custom resources**, or CRs) in etcd, the same way it stores Pods;
- gives you `kubectl get/describe/apply/delete`, labels and selectors, RBAC, admission,
 the audit log, and `watch` — **for free**, because everything flows through the one
 hub you met in.

```bash
kubectl apply -f environment-crd.yaml # register the "Environment" type
kubectl get crds | grep environments # the API now knows the noun
kubectl explain environment.spec # schema-driven docs, like any built-in
```

#### The point you must not miss: a CRD is data, not behavior

Here is the idea that sets up the entire phase. A CRD adds **storage and validation**
— a new noun — and **nothing else**. There is no controller. When you create an
`Environment`, its `spec` sits in etcd and *nothing happens*: no namespace is created,
no `status` is driven toward anything. The reconciliation loop from is
**not** running for your type, because you haven't written one yet.

```text
Built-in Deployment Your Environment CRD (alone)
─────────────────── ────────────────────────────
spec ─┐ spec ─┐
 ├─► Deployment controller ├─► (nobody is watching)
status ┘ drives status→spec status ┘ status stays empty forever
```

- **CRD** = the data model (the noun, its schema). *This module.*
- **Operator** = the behavior (the control loop for that noun). *.*

Keeping these separate is deliberate: it means you can validate and store your API
before you've written a line of controller code, and different controllers can watch
the same type.

#### CRD anatomy: group, version, kind, scope, schema

```yaml
spec:
 group: platform.example.com # your API group — use a domain you own
 names:
 kind: Environment # CamelCase type name used in YAML
 plural: environments # the REST path segment
 singular: environment
 shortNames: [env] # kubectl get env
 scope: Namespaced # or Cluster (no namespace)
 versions:
 - name: v1alpha1
 served: true # exposed on the API
 storage: true # persisted to etcd in THIS version (exactly one)
 schema:
 openAPIV3Schema: {... } # the structural schema (below)
```

#### Validation 1 — the OpenAPI v3 structural schema

For a v1 CRD the schema is **required** and must be *structural*: every field is
typed, and the API server **prunes** (drops) anything you didn't declare. That is what
makes a CR trustworthy — you can't smuggle untyped data into it. Structural schemas
give you per-field validation familiar from JSON Schema: `type`, `enum`, `pattern`,
`minimum`/`maximum`, `minLength`, `required`, and `default`.

```yaml
spec:
 type: object
 required: [team, tier]
 properties:
 team:
 type: string
 pattern: '^[a-z][a-z0-9-]{1,30}$'
 tier:
 type: string
 enum: [dev, staging, prod]
 replicas:
 type: integer
 minimum: 1
 default: 1
```

#### Validation 2 — CEL rules that span fields

OpenAPI validates one field at a time. Real rules relate fields ("prod environments
need an owner") or forbid changes ("tier is immutable"). Historically you reached for
a **validating webhook** — a TLS server you build, deploy, and keep alive — for this.
Since Kubernetes 1.25+, **CEL** (Common Expression Language) rules embedded in the
schema via `x-kubernetes-validations` handle most of these with **no server at all**:

```yaml
x-kubernetes-validations:
 - rule: "self.tier != 'prod' || has(self.owner)"
 message: "prod environments must set spec.owner"
 - rule: "self.tier == oldSelf.tier" # a transition rule (compares to old value)
 message: "tier is immutable once set"
```

`self` is the object being validated; `oldSelf` is the previous version (available on
updates — a *transition rule*). CEL runs inside the API server, synchronously, with no
certificates to rotate. **Reach for CEL first; reach for a webhook only when CEL
genuinely can't express the rule**.

#### Versioning: served vs stored

APIs evolve. You start at `v1alpha1` (anything may change), graduate to `v1beta1`,
then `v1` (stable). A CRD can serve several versions at once:

- **`served: true`** — clients can read/write this version.
- **`storage: true`** — exactly **one** version is the one written to etcd. Other
 served versions are converted to/from it on the fly.

For simple, additive changes, the built-in `None` conversion strategy suffices. For
renames or restructures you register a **conversion webhook** that translates between
versions. The golden rule: **never make a breaking change to an already-served
version** — add a new version instead.

#### The status subresource

Enabling `subresources.status: {}` splits the object into two independently writable
halves: clients write `spec`, controllers write `status` via a separate endpoint. This
matters because it lets RBAC grant "update status" without "update spec", and because
status writes don't bump `metadata.generation` — so a controller can tell *user edits*
from its *own* status updates. You'll switch this on and exploit it fully in; know it exists now.

---

### 2. Why it matters for platform engineering

- **Your platform gets a declarative API.** Instead of a ticket ("please make me a
 dev environment"), a team commits an `Environment` manifest and GitOps applies it.
 The platform's capabilities become `kubectl`-and-Git-native.
- **Everything else comes for free.** RBAC, admission, audit, labels/selectors,
 `watch`, and every dashboard that speaks to the API now work on *your* types,
 because they're real API objects — not a side database.
- **Validation moves left.** A malformed request is rejected at the API boundary with
 a clear message, long before it becomes a 2am incident.
- **It's the industry pattern.** cert-manager `Certificate`s, Argo CD `Application`s,
 Crossplane `Composition`s, Prometheus `ServiceMonitor`s — all CRDs. Learn the
 pattern once and the whole ecosystem reads the same way.

---

### 3. Mental model

A CRD is **teaching the API server a new word**. Once it knows the word, instances of
that word travel the same hub-and-spoke path as every built-in object — validated on
the way in, stored in etcd, and available to anything that watches.

```text
 kubectl apply environment.yaml
 │
 ▼
 ┌──────────────────────── API SERVER ────────────────────────┐
 │ 1. Is "Environment" a known type? ── yes (CRD registered) │
 │ 2. OpenAPI structural schema ── types / enums / regex │
 │ 3. CEL x-kubernetes-validations ── cross-field + oldSelf │
 │ 4. (admission plugins, ) │
 └───────────────────────────┬────────────────────────────────┘
 │ store
 ▼
 etcd...and then? NOTHING —
 no controller watches it yet.
 (That is.)
```

Remember the split: **CRD defines the noun; a controller gives it a verb.**

---

### 4. Minimal implementation

Let's prove both halves of the claim: a CRD gives you a real, validated API *and* does
nothing on its own. The smallest useful CRD:

```yaml
# environment-crd.yaml (abridged — full version in the lab)
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
 name: environments.platform.example.com
spec:
 group: platform.example.com
 names: { kind: Environment, plural: environments, singular: environment, shortNames: [env] }
 scope: Cluster
 versions:
 - name: v1alpha1
 served: true
 storage: true
 schema:
 openAPIV3Schema:
 type: object
 properties:
 spec:
 type: object
 required: [team, tier]
 properties:
 team: { type: string }
 tier: { type: string, enum: [dev, staging, prod] }
```

Register it and create an instance:

```bash
kubectl apply -f environment-crd.yaml
kubectl apply -f - <<'EOF'
apiVersion: platform.example.com/v1alpha1
kind: Environment
metadata: { name: payments-dev }
spec: { team: payments, tier: dev }
EOF

kubectl get environments # payments-dev is there — a real API object
kubectl get namespace payments-dev # NotFound — nothing was created
```

The CR exists and is queryable, but **no namespace appeared**, because nothing is
reconciling it. Now watch validation do its job:

```bash
kubectl apply -f - <<'EOF'
apiVersion: platform.example.com/v1alpha1
kind: Environment
metadata: { name: bad }
spec: { team: payments, tier: production } # not in the enum
EOF
# Error: spec.tier: Unsupported value: "production": supported values: "dev","staging","prod"
```

You built a typed, self-validating API endpoint with a single YAML file — and saw
exactly where behavior will have to be added next.

---

### 5. Hands-on lab

You'll author a complete, production-shaped `Environment` CRD — structural schema,
enums, regex, defaults, a CEL cross-field rule, a CEL transition (immutability) rule,
printer columns, and the status subresource — then apply it to kind and prove it
accepts valid resources and rejects invalid ones with clear messages.

➡️ **Start the lab: Design and validate an Environment CRD**

---

### 6. Production considerations

- **Own your API group.** `platform.example.com` is fine for docs, but in production
 use a domain you actually control to avoid collisions with other installed CRDs.
- **Structural schemas are non-negotiable.** Avoid blanket
 `x-kubernetes-preserve-unknown-fields: true`; it disables pruning and validation and
 becomes a dumping ground. Type every field.
- **Treat a served version as a contract.** Never make breaking changes to it. Add
 `v1beta1`/`v1`, keep old versions served, and migrate storage with a conversion
 strategy. Alpha versions are your only license to break things.
- **Enable the status subresource from day one.** Retrofitting it later means
 reworking RBAC and controllers.
- **CRDs are cluster-scoped and destructive.** Installing or deleting one is a
 privileged, cluster-wide act, and **deleting a CRD cascades to every CR of that
 type**. Gate CRD management behind tight RBAC and GitOps review.
- **Mind etcd.** CRs live in etcd like everything else; don't model high-volume,
 high-churn data (metrics, events) as custom resources.
- **Budget CEL cost.** The API server enforces a per-rule and per-request CEL cost
 limit; keep rules simple, and prefer them over webhooks for latency and reliability.

---

### 7. Common mistakes

- **Storing platform state in ConfigMaps or annotations.** — It "works" but gives up
 typing, validation, and discoverability, and every consumer re-invents parsing.
 *Fix:* model the concept as a CRD and let the API server validate it.
- **Blanket `preserve-unknown-fields`.** — Copied from an old example, it disables
 pruning so typos and junk silently persist. *Fix:* write a full structural schema;
 only preserve unknown fields on a specific sub-tree you deliberately keep open.
- **Breaking a served version.** — Renaming or retyping a field in `v1alpha1` that
 users already depend on breaks their manifests on upgrade. *Fix:* add a new version
 and convert; treat each served version as frozen.
- **Forgetting the status subresource.** — Controllers then fight `generation` bumps
 and you can't separate "user changed spec" from "controller wrote status." *Fix:*
 set `subresources: { status: {} }` from the start.
- **Reaching for a webhook when CEL would do.** — A TLS server to enforce "prod needs
 an owner" is a lot of moving parts to keep alive. *Fix:* express it as an
 `x-kubernetes-validations` rule; keep webhooks for logic CEL can't do.
- **Using someone else's API group.** — Reusing `example.com` or a vendor's group
 risks clashing with an installed CRD of the same name. *Fix:* use a group under a
 domain you own.

---

### 8. Assessment

**Knowledge checks**

1. After you `kubectl apply` a CRD and create one custom resource, what exactly has
 happened in the cluster — and what has **not**?
2. In a CRD's `versions` list, what's the difference between `served` and `storage`,
 and how many versions can set `storage: true`?
3. Give one validation rule that OpenAPI v3 *can't* express but CEL can, and write it.
4. What two concrete benefits does enabling the status subresource give you?
5. What happens to existing custom resources when you delete their CRD?

**Concept exercise**

> Explain how you would add a brand-new "Environment" concept to a cluster so that
> `kubectl`, RBAC, the audit log, and GitOps all work on it — **without using the
> words "CRD" or "CustomResourceDefinition."** Describe the capability, not the tool.

**Debugging / trade-off exercise**

> A teammate applies an `Environment` CR and complains: "I created it but no namespace
> showed up — the CRD is broken." Explain why this is expected behavior, what's
> actually missing, and which module fixes it. Then: when would you choose a
> *conversion webhook* over a CEL rule?

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** The API server now serves a new type and has stored one instance in etcd;
 it's queryable with `kubectl` and governed by RBAC/admission. What has *not* happened
 is any action — no controller is reconciling it, so `status` stays empty and nothing
 is created in the world.
- **Q2:** `served` means clients may read/write that version; `storage` means etcd
 persists in that version. Exactly **one** version may be `storage: true`; others are
 converted to/from it.
- **Q3:** Any cross-field or transition rule, e.g.
 `self.tier != 'prod' || has(self.owner)` (cross-field), or
 `self.tier == oldSelf.tier` (immutability). OpenAPI validates fields in isolation
 and has no `oldSelf`.
- **Q4:** (a) RBAC can grant "update status" separately from "update spec"; (b) status
 writes don't bump `metadata.generation`, so a controller can distinguish user spec
 edits from its own status updates.
- **Q5:** Deleting the CRD **cascades**: all custom resources of that type are deleted
 too. It's a destructive, cluster-wide operation.
- **Trade-off:** The "broken" CRD isn't broken — there's simply no controller; adds the operator that reconciles it. Choose a conversion webhook when versions
 differ structurally enough that a mechanical/`None` conversion can't map them (field
 renames, restructures); use CEL for in-version validation, not cross-version shape
 changes.

</details>

---

### 9. Further reading

- Kubernetes — [Custom Resources and CRDs (concepts)](https://kubernetes.io/docs/concepts/extend-kubernetes/api-extension/custom-resources/)
- Kubernetes — [Extend the API with CustomResourceDefinitions](https://kubernetes.io/docs/tasks/extend-kubernetes/custom-resources/custom-resource-definitions/)
- Kubernetes — [Specifying a structural schema](https://kubernetes.io/docs/tasks/extend-kubernetes/custom-resources/custom-resource-definitions/#specifying-a-structural-schema)
- Kubernetes — [Validation rules (CEL in CRDs)](https://kubernetes.io/docs/tasks/extend-kubernetes/custom-resources/custom-resource-definitions/#validation-rules)
- Kubernetes — [Versions in CustomResourceDefinitions](https://kubernetes.io/docs/tasks/extend-kubernetes/custom-resources/custom-resource-definition-versioning/)
- Kubernetes — [CEL language overview](https://kubernetes.io/docs/reference/using-api/cel/)

---


_Previous:_ · Kubernetes Advanced
· _Next:_ Kubernetes Operators →

---

## Kubernetes Operators

> In Project 1 you onboarded a team **by hand**: create a namespace, label it, apply a
> `ResourceQuota` and `LimitRange`, wire up RBAC. An **operator** is that runbook
> encoded as software — a controller running the reconciliation loop from,
> but for *your own* `Environment` resource. You did it by hand; now you'll make the
> platform do it, consistently, forever, and self-heal when someone breaks it.

**You'll need:** CRDs, the reconciliation loop from, a local [kind](https://kind.sigs.k8s.io/) cluster, and (for the full lab) a [Go](https://go.dev/dl/) toolchain.

### Learning objectives

By the end of this module you will be able to:

- Explain the **operator pattern** — a custom controller that encodes operational
 knowledge for a CRD — and build one with **controller-runtime**.
- Write an idempotent, **level-triggered** `Reconcile` that drives actual state toward
 a resource's `spec`.
- Report progress with **status conditions** and choose sane **requeue** strategies.
- Use **owner references** for garbage collection and **finalizers** for pre-delete
 cleanup.

---

### 1. Concept

#### An operator is the reconciliation loop, for your resource

 taught you that built-in controllers watch built-in types and drive actual
state toward desired state. The Deployment controller keeps N Pods running; the Node
controller reacts to nodes dying. gave you a new *type* — `Environment` —
but warned you nothing reconciles it.

An **operator** fills that gap. It is nothing more exotic than:

```text
operator = one or more CRDs (the nouns) + a custom controller (the verb)
```

The controller runs the same loop you already know, aimed at your type:

```text
watch Environment ──► observe desired (spec) ──► observe actual (the real namespace,
 ▲ quota, limits, RBAC in the cluster)
 │ │
 └───────────── write status ◄── create/update/delete to close the gap ◄──┘
```

The name comes from SRE: an *operator* encodes what a skilled human operator knows
about running a piece of software — the runbook — as a program. "To give a team an
environment, create a namespace, apply a quota and limits, bind RBAC, and watch for
drift" is exactly such a runbook. An operator makes it executable and tireless.

#### controller-runtime: the library everyone builds on

You could talk to the API server by hand, but almost nobody does. **controller-runtime**
(the library beneath both **kubebuilder** and **operator-sdk**) gives you:

- a **Manager** that wires up shared caches, clients, leader election, and metrics;
- **informers/caches** so your controller reads from a local watch-backed cache
 instead of hammering the API server;
- a **work queue** with rate limiting and retries;
- a **Reconciler** interface — you implement one method.

```go
func (r *EnvironmentReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
 env:= &platformv1alpha1.Environment{}
 if err:= r.Get(ctx, req.NamespacedName, env); err != nil {
 return ctrl.Result{}, client.IgnoreNotFound(err) // already deleted — nothing to do
 }
 //... ensure namespace, quota, limits, RBAC; then update status...
 return ctrl.Result{}, nil
}
```

#### Level-triggered, not edge-triggered — so it must be idempotent

This is the mistake that bites every beginner. Your `Reconcile` is **not** called with
"a Pod was deleted" or "the spec changed." It's called with *"something about this
object might have changed — go make reality match its spec."* It may be called once, or
fifty times, for the same object. Therefore:

- **Never assume you saw a specific event.** Always read the current state and compute
 the difference.
- **Make every action idempotent.** "Create the namespace" must mean "ensure the
 namespace exists with these labels," not "POST a new namespace" (which fails the
 second time). The helper `controllerutil.CreateOrUpdate` exists for exactly this.

Level-triggered design is *why* Kubernetes self-heals: delete the quota your operator
created and the next reconcile puts it back, because the loop re-derives desired state
from `spec` every time.

#### Requeue strategies

`Reconcile` returns `(ctrl.Result, error)`, which tells the queue when to call you again:

- `return ctrl.Result{}, err` — on error, requeue with **exponential backoff**.
- `return ctrl.Result{}, nil` — success; don't requeue *proactively* (you still get
 called when the object or a watched child changes).
- `return ctrl.Result{RequeueAfter: 5 * time.Minute}, nil` — re-check periodically
 (useful when you poll something the cluster can't watch).

Prefer **watches over polling**: `Owns(&corev1.ResourceQuota{})` makes the framework
reconcile the parent `Environment` whenever one of its quotas changes — including when
someone deletes it.

#### Status conditions: how your operator talks back

Users and other controllers need to know *how it's going*. The convention is an array of
**conditions**, each with a `type` (e.g. `Ready`), `status` (`True`/`False`/`Unknown`),
`reason`, `message`, `lastTransitionTime`, and `observedGeneration`. Use
`meta.SetStatusCondition`, which only updates `lastTransitionTime` when the state
actually changes — important for avoiding hot loops. Write status through the status
subresource so it doesn't bump `generation`.

#### Owner references and finalizers

Two mechanisms manage the lifecycle of what your operator creates:

- **Owner references** — stamp "this ResourceQuota is owned by `payments-dev`" on each
 child. Kubernetes **garbage-collects** children when the parent is deleted, and the
 framework uses the reference to map child events back to the parent (`Owns`).
- **Finalizers** — a string in `metadata.finalizers` that **blocks deletion** until your
 operator removes it. That pause is your chance to run cleanup that GC can't do:
 deleting an external cloud resource, deregistering from DNS, or (here) deleting the
 namespace the `Environment` owns. The pattern: when `deletionTimestamp` is set, run
 cleanup, then remove the finalizer so deletion can complete.

#### Scaffolding: kubebuilder and operator-sdk

You rarely write all this from scratch. `kubebuilder init` / `operator-sdk init` scaffold
the Manager, a sample API, and a controller; `controller-gen` generates deepcopy code,
the CRD YAML, and RBAC from `// +kubebuilder:...` markers in your Go types. You'll use a
pre-scaffolded project in the lab and focus on the part that matters: `Reconcile`.

---

### 2. Why it matters for platform engineering

- **It turns a runbook into a product.** The manual onboarding doc from Project 1 becomes
 software that never forgets a step and applies the same guardrails every time.
- **It self-heals.** Drift — a deleted quota, a tampered RoleBinding — is corrected on the
 next reconcile. Your platform defends its own invariants.
- **It's self-service at scale.** A team commits an `Environment` and the platform
 provisions everything. No ticket, no human in the critical path, no inconsistency
 between the 3rd and the 300th environment.
- **It's the universal extension pattern.** cert-manager, Argo CD, Crossplane,
 Prometheus Operator, and database operators are all this exact shape. Learn it once and
 you can read — and build — the ecosystem.

---

### 3. Mental model

Picture your operator as a thermostat wired to the cluster. It never trusts its memory;
every tick it *measures* the room (reads actual state), compares to the *dial* (the
`spec`), and acts to close the gap.

```text
 ┌──────────────── Environment (your CRD) ────────────────┐
 │ spec: {team: payments, tier: dev} status: {...} │
 └───────────────────────┬────────────────────────────────┘
 │ watch (For)
 ┌─────────────▼─────────────┐
 │ EnvironmentReconciler │ level-triggered:
 │ observe spec vs actual │ reads real state every time,
 │ CreateOrUpdate children │ idempotent, safe to repeat
 └─────────────┬─────────────┘
 ensure (and re-heal) ┌─────┼───────┬───────────┬───────────┐
 ▼ ▼ ▼ ▼ ▼
 Namespace Quota LimitRange RoleBinding status
 ▲ ▲ ▲
 └───────┴───────────┘ watch (Owns):
 delete one and the loop restores it
```

Three rules: **read actual state every time**, **make every change idempotent**, and
**report what you did in `status`.**

---

### 4. Minimal implementation

The smallest honest operator: fetch the resource, ensure one namespace exists, and
report ready. Everything else (quota, limits, RBAC, finalizers) is "more of the same."

```go
func (r *EnvironmentReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
 env:= &platformv1alpha1.Environment{}
 if err:= r.Get(ctx, req.NamespacedName, env); err != nil {
 return ctrl.Result{}, client.IgnoreNotFound(err)
 }

 ns:= &corev1.Namespace{ObjectMeta: metav1.ObjectMeta{Name: env.Spec.Team + "-" + env.Spec.Tier}}
 _, err:= controllerutil.CreateOrUpdate(ctx, r.Client, ns, func() error {
 ns.Labels = map[string]string{"platform.example.com/team": env.Spec.Team}
 return nil // idempotent: ensure, don't blindly create
 })
 if err != nil {
 return ctrl.Result{}, err // requeue with backoff
 }

 meta.SetStatusCondition(&env.Status.Conditions, metav1.Condition{
 Type: "Ready", Status: metav1.ConditionTrue, Reason: "Provisioned",
 Message: "namespace ready", ObservedGeneration: env.Generation,
 })
 env.Status.Phase = "Ready"
 env.Status.Namespace = ns.Name
 return ctrl.Result{}, r.Status().Update(ctx, env)
}
```

Run it against kind and `kubectl apply` an `Environment`: a namespace appears, and
`kubectl get env` shows `Ready`. Delete the namespace and watch the loop recreate it.
That's the whole idea; the lab fills in the production details.

---

### 5. Hands-on lab

You'll run a complete `NamespaceProvisioner` operator (the `EnvironmentReconciler`)
against kind. Apply an `Environment` and watch it provision a namespace, `ResourceQuota`,
`LimitRange`, and RBAC, set status conditions, self-heal when you delete a child, and
clean up via a finalizer on delete. The full Go project is provided; the README is honest
about what needs the Go toolchain.

➡️ **Start the lab: Build the NamespaceProvisioner operator**

---

### 6. Production considerations

- **Idempotency is the whole game.** Use `CreateOrUpdate` or Server-Side Apply; never write code that only works the first time.
- **Don't hot-loop on status.** Writing `status` every reconcile even when nothing
 changed re-triggers the watch and spins the CPU. Only update when the computed status
 differs; `meta.SetStatusCondition` helps.
- **Finalizers must be robust.** Cleanup has to be idempotent and must not deadlock; a
 bug that never removes the finalizer leaves objects stuck `Terminating`. Always keep an
 operational escape hatch (how to force-remove a finalizer).
- **Least-privilege RBAC.** The operator runs as a ServiceAccount; generate its Role from
 `+kubebuilder:rbac` markers and grant only what it touches — not `cluster-admin`.
- **Leader election for HA.** Run two replicas with leader election so one is always
 active without two controllers fighting over the same objects.
- **Observability.** controller-runtime exposes reconcile count/latency/error metrics;
 emit Events for human-visible milestones; surface conditions for dashboards.
- **Test with envtest.** Run the controller against a real API server + etcd (no kubelet)
 in CI, so reconcile logic is tested without a full cluster.

---

### 7. Common mistakes

- **Edge-triggered thinking.** — Writing `Reconcile` as if it receives "the thing that
 changed." It doesn't. *Fix:* always read current state and reconcile to `spec`; assume
 you may have missed events.
- **Non-idempotent actions.** — Blindly `Create`-ing children, which errors on the second
 reconcile. *Fix:* `CreateOrUpdate`/SSA so "ensure" is safe to repeat.
- **Status hot loop.** — Unconditionally updating status each pass, which re-queues
 forever and pins a core. *Fix:* compute desired status, compare, and only write on a
 real change.
- **Stuck finalizers.** — Adding a finalizer but a cleanup bug never removes it, so the
 object hangs in `Terminating`. *Fix:* make cleanup idempotent and tolerant of
 already-deleted children; remove the finalizer whenever cleanup is done.
- **Swallowing errors.** — Logging an error and returning `nil`, so the queue thinks it
 succeeded and never retries. *Fix:* return the error to get backoff-and-retry.
- **God-mode RBAC.** — Granting the operator `cluster-admin` "to be safe." *Fix:* scope
 permissions to exactly the resources and verbs it uses.

---

### 8. Assessment

**Knowledge checks**

1. In one sentence, what is an operator, and how does it relate to a CRD?
2. What does "level-triggered" mean for `Reconcile`, and why does it force idempotency?
3. Name the three things a `Reconcile` return value can tell the work queue to do.
4. What problem do **owner references** solve, and what problem do **finalizers** solve —
 and why can't one replace the other?
5. Why should status updates go through the status subresource rather than a normal update?

**Concept exercise**

> Explain how you'd automate team onboarding so that deleting the team's quota by mistake
> is silently repaired — **without using the words "operator," "controller," or
> "reconcile."** Describe it as a control system.

**Debugging / trade-off exercise**

> An `Environment` has been stuck in `Terminating` for an hour; its namespace is already
> gone. What is almost certainly happening, how do you confirm it, and what's the safe
> fix? Separately: your operator's CPU is pinned at 100% and the logs show thousands of
> reconciles per second for one unchanged object — what's the likely cause?

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** An operator is a custom controller (plus its CRD) that encodes operational
 knowledge, running the reconciliation loop for a user-defined type.
- **Q2:** `Reconcile` is called to "make reality match spec," not for a specific event; it
 may run many times for one object, so every action must be safe to repeat (idempotent).
- **Q3:** Requeue with backoff (return an error), stop proactive requeue (return
 `Result{}, nil`), or requeue after a delay (`RequeueAfter`).
- **Q4:** Owner references give automatic garbage collection of children when the parent is
 deleted; finalizers pause deletion so the operator can run cleanup GC can't do (external
 resources, ordered teardown). GC can't call your code; finalizers can't auto-delete
 owned objects — you need both.
- **Q5:** The status subresource separates status writes from spec and doesn't bump
 `generation`, so the operator can distinguish user spec changes from its own status
 writes and avoid permission/loop problems.
- **Debugging:** Stuck `Terminating` means a finalizer is never removed — confirm with
 `kubectl get environment X -o jsonpath='{.metadata.finalizers}'`; fix by repairing the
 operator (or, as an escape hatch, patching the finalizer off). The 100% CPU is a status
 hot loop: status is written unconditionally every reconcile, re-triggering the watch.

</details>

---

### 9. Further reading

- Kubernetes — [Operator pattern](https://kubernetes.io/docs/concepts/extend-kubernetes/operator/)
- Kubernetes — [Controllers and the control loop](https://kubernetes.io/docs/concepts/architecture/controller/)
- Kubernetes — [Finalizers](https://kubernetes.io/docs/concepts/overview/working-with-objects/finalizers/) and [Owners and dependents](https://kubernetes.io/docs/concepts/overview/working-with-objects/owners-dependents/)
- The Kubebuilder Book — [Architecture and tutorial](https://book.kubebuilder.io/)
- controller-runtime — [Package reference](https://pkg.go.dev/sigs.k8s.io/controller-runtime)
- Operator SDK — [Go operator tutorial](https://sdk.operatorframework.io/docs/building-operators/golang/)

---


_Previous:_ Custom Resource Definitions
· _Next:_ Admission Webhooks →

---

## Admission Webhooks

> CRDs and operators let you *add* resources and *react* to them. Admission control lets
> you *intercept* every write — mutating or validating it **before** it's stored. This
> is how platforms enforce guardrails that can't be skipped: inject the sidecar, require
> the security context, stamp the cost-center label. You'll learn the webhook machinery
> and the newer, server-free **CEL policies** — and when to use which.

**You'll need:** CRDs and Operators, a local [kind](https://kind.sigs.k8s.io/) cluster (Kubernetes ≥ 1.30 for `ValidatingAdmissionPolicy`), plus `openssl` for the webhook part.

### Learning objectives

By the end of this module you will be able to:

- Place **mutating** and **validating** admission in the request path, and say why
 order matters.
- Write a **`ValidatingAdmissionPolicy`** (pure CEL, no server) to enforce a rule.
- Explain the **webhook server** contract: TLS, `caBundle`, registration, and
 `failurePolicy`.
- Choose **CEL first, webhook only when needed**, and scope admission safely.

---

### 1. Concept

#### Admission happens in the request path — before storage

An operator reacts *after* an object is stored, asynchronously. Admission is the
opposite: it runs **synchronously, inside the API request**, before the object is
written to etcd. Every `kubectl apply` travels this pipeline:

```text
request ─► authentication ─► authorization ─► MUTATING admission ─► schema/CEL
 (who are you?) (may you?) (change the object) validation
 │
 etcd ◄── VALIDATING admission ◄───────────────────────────────┘
 (stored) (accept or reject; cannot change)
```

Two properties fall out of this and explain everything else:

- **Mutating runs before validating.** You mutate first (add a label, inject a
 sidecar), *then* the final object is validated. A validator always sees the
 post-mutation object.
- **It's in the hot path.** Because admission blocks the request, a slow or broken
 admission component slows or breaks *every* matching write in the cluster. Admission
 buys you un-skippable guardrails at the cost of being on the critical path.

#### The four tools, from lightest to heaviest

| Tool | Can it mutate? | Server? | Status |
|------|----------------|---------|--------|
| `ValidatingAdmissionPolicy` (VAP) | No — validate only | **No** (CEL in-process) | GA (1.30) |
| `MutatingAdmissionPolicy` | Yes (CEL) | **No** (CEL in-process) | Alpha (1.32+) |
| `ValidatingWebhookConfiguration` | No — validate only | Yes (your HTTPS server) | GA |
| `MutatingWebhookConfiguration` | Yes (JSON Patch) | Yes (your HTTPS server) | GA |

The trend is clear: move logic **out of webhook servers and into CEL**, which the API
server evaluates itself — no TLS, no deployment, no availability risk. Today, VAP
covers *validation* with no server; CEL-based *mutation* exists but is still alpha, so
mutation in production generally still means a mutating webhook.

#### ValidatingAdmissionPolicy: enforcement with no server

A VAP is two objects: the **policy** (the CEL rules) and a **binding** (which resources
it applies to). No certificates, no pods, no `failurePolicy`-induced outages from a
crashed server.

```yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicy
metadata:
 name: require-cost-labels
spec:
 matchConstraints:
 resourceRules:
 - apiGroups: [""]
 apiVersions: ["v1"]
 operations: ["CREATE", "UPDATE"]
 resources: ["pods"]
 validations:
 - expression: "'platform.example.com/cost-center' in object.metadata.labels"
 message: "pods must carry a platform.example.com/cost-center label"
```

`object` is the incoming resource; `oldObject`, `request`, and `namespaceObject` are
also available. This is the **no-server option**: reach for it first.

#### The webhook contract: TLS, caBundle, registration

When CEL isn't enough (you need to *mutate*, call an external system, or run logic CEL
can't express), you register a webhook. A webhook is an HTTPS server the API server
**calls** with an `AdmissionReview` and that replies with an `AdmissionResponse`:

- **TLS is mandatory.** The API server will only talk HTTPS, and it must trust your
 server's certificate — so the webhook configuration carries a `caBundle` (the CA that
 signed the server cert). A mismatch is the classic `x509: certificate signed by
 unknown authority` failure.
- **A mutating webhook returns a JSON Patch** (base64-encoded) that the API server
 applies to the object. A validating webhook just returns `allowed: true|false` with a
 message.
- **Registration** (`MutatingWebhookConfiguration` / `ValidatingWebhookConfiguration`)
 declares the `rules` (which resources/operations), the `clientConfig` (a Service or
 URL + `caBundle`), and the knobs below.

```yaml
webhooks:
 - name: inject-cost-labels.platform.example.com
 clientConfig:
 service: { name: label-injector, namespace: platform-system, path: /mutate }
 caBundle: <base64 CA cert>
 rules:
 - apiGroups: [""]
 apiVersions: ["v1"]
 operations: ["CREATE"]
 resources: ["pods"]
 namespaceSelector: # ONLY team namespaces — limit the blast radius
 matchLabels: { platform.example.com/managed-by: namespace-provisioner }
 failurePolicy: Ignore # label injection is best-effort, not security
 sideEffects: None
 admissionReviewVersions: ["v1"]
 timeoutSeconds: 5
```

#### The dial that decides reliability: `failurePolicy`

If the API server can't reach your webhook (crashed, slow, cert expired), what should
happen to the request?

- **`Fail`** (fail closed) — reject the request. Safe for *security* gates ("no Pod
 without a signed image"), but a non-HA webhook that goes down now **blocks every
 matching write in the cluster**.
- **`Ignore`** (fail open) — allow the request through un-mutated. Right for
 *best-effort* mutation like label injection, where availability matters more than a
 missing label on one Pod.

Choosing this per webhook, and scoping with `namespaceSelector`/`objectSelector`, is
the difference between a guardrail and an outage.

#### Testing and certificates

Hand-rolling TLS and keeping `caBundle` in sync is the painful part. In production,
**cert-manager** issues and rotates the webhook certificate and injects the `caBundle`
automatically via an annotation. For unit/integration tests, **envtest** runs a real
API server so you can assert that your webhook mutates/rejects as intended.

---

### 2. Why it matters for platform engineering

- **Un-skippable guardrails.** Policy enforced at admission can't be forgotten in a
 template or bypassed by a hand-written manifest — it applies to *every* write.
- **Invisible paved roads.** A mutating webhook injects the right defaults (sidecar,
 security context, labels) so developers get correct behavior *without doing anything*.
 That's the platform doing the work, not the human.
- **FinOps starts here.** Cost tools attribute spend by label. If every Pod is stamped
 with `team` and `cost-center` automatically, 's cost reports are accurate by
 construction — no nagging developers to label things.
- **Security and compliance.** Pod Security admission, image-signature checks, and
 "no `:latest`" rules are all admission control. It's where "secure by default"
 becomes literally true.

---

### 3. Mental model

Admission is a **checkpoint on the way into etcd**: first a station that can *change*
your object, then stations that can *reject* it. Nothing is stored until it passes.

```text
 kubectl apply pod.yaml
 │
 ▼
 authn ─► authz ─► ┌───────── MUTATING ─────────┐ ─► schema + CEL ─► ┌──── VALIDATING ────┐ ─► etcd
 │ mutating webhooks │ validation │ VAP (CEL, no server)│
 │ (JSON Patch: add labels, │ │ validating webhooks │
 │ inject sidecar, defaults) │ │ (allow / deny) │
 └─────────────────────────────┘ └─────────────────────┘
 change it judge the final object
```

Three things to remember: **mutate before validate**, **it blocks the request**, and
**CEL (in-process) beats a webhook (a server you must keep alive) whenever it can
express the rule.**

---

### 4. Minimal implementation

The smallest useful admission control needs **no server at all**. Require that Pods
carry a cost-center label, with a `ValidatingAdmissionPolicy` and its binding:

```yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicy
metadata: { name: require-cost-center }
spec:
 matchConstraints:
 resourceRules:
 - apiGroups: [""]
 apiVersions: ["v1"]
 operations: ["CREATE", "UPDATE"]
 resources: ["pods"]
 validations:
 - expression: "'platform.example.com/cost-center' in object.metadata.labels"
 message: "every Pod needs a platform.example.com/cost-center label"
---
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicyBinding
metadata: { name: require-cost-center-binding }
spec:
 policyName: require-cost-center
 validationActions: ["Deny"]
 matchResources:
 namespaceSelector:
 matchLabels: { platform.example.com/managed-by: namespace-provisioner }
```

Apply it, then try to create a bare Pod in a managed namespace: it's rejected with your
message. No TLS, no deployment, no `failurePolicy` outage surface. That's the baseline;
a webhook is what you add only when you must *change* the object (inject the label) or
reach outside the cluster.

---

### 5. Hands-on lab

Two halves. First, the **no-server** path: a `ValidatingAdmissionPolicy` that *requires*
`team` and `cost-center` labels on Pods in managed namespaces, and rejects those that
lack them. Then the **webhook** path: a small mutating webhook that *injects* those
labels from the namespace's annotations — so developers never set them and the VAP
passes automatically. The webhook runs on a stock image via a ConfigMap; a script mints
the TLS cert.

➡️ **Start the lab: Enforce and inject cost labels**

---

### 6. Production considerations

- **Default to VAP.** It runs in-process: no TLS, no pods, no availability risk, lower
 latency. Use a webhook only for mutation or external calls.
- **Pick `failurePolicy` deliberately, per webhook.** `Fail` for security gates (and
 then make the webhook HA); `Ignore` for best-effort mutation. A `Fail` webhook that
 isn't highly available is a cluster-wide outage waiting to happen.
- **Scope tightly.** Use `namespaceSelector`/`objectSelector` and precise `rules` so you
 match only what you must. **Exclude `kube-system`** and your own control-plane
 namespace to avoid bootstrap deadlocks.
- **Keep it fast and set a low timeout.** Admission is in the hot path; a slow webhook
 taxes every matching write. Set `timeoutSeconds` low and keep the handler cheap.
- **Automate certs with cert-manager.** Manual `caBundle` management breaks on rotation;
 cert-manager issues, rotates, and injects it for you.
- **Declare `sideEffects: None`** (or `NoneOnDryRun`) so dry-run works, and make
 mutations **idempotent** — reinvocation (`reinvocationPolicy`) can call you twice.

---

### 7. Common mistakes

- **`failurePolicy: Fail` on a non-HA webhook.** — The webhook crashes and now *nothing*
 matching it can be created cluster-wide. *Fix:* run the webhook HA, scope it tightly,
 or use `Ignore` for non-security mutation.
- **Matching `kube-system` or the webhook's own namespace.** — You create a bootstrap
 deadlock where the webhook can't start because its own Pods are blocked. *Fix:* exclude
 system namespaces with a `namespaceSelector`.
- **No `namespaceSelector`.** — The webhook fires on every namespace, including CI and
 system workloads you never meant to touch. *Fix:* select only managed namespaces.
- **`caBundle` mismatch.** — `x509: certificate signed by unknown authority`; the API
 server won't trust the server cert. *Fix:* put the signing CA in `caBundle` (let
 cert-manager inject it) and rotate together.
- **Reaching for a webhook when VAP would do.** — A whole TLS server to enforce "label
 must exist." *Fix:* write a `ValidatingAdmissionPolicy`; keep webhooks for mutation.
- **Non-idempotent mutation.** — Appending a sidecar twice because reinvocation called
 you again. *Fix:* check before you add; make the patch a no-op if already applied.

---

### 8. Assessment

**Knowledge checks**

1. In the admission pipeline, does mutating or validating run first, and why does the
 order matter?
2. What can a `ValidatingAdmissionPolicy` do that a validating webhook also does — and
 what can it *not* do that a mutating webhook can?
3. Explain the `Fail` vs `Ignore` `failurePolicy` trade-off with one example of each.
4. Why is a slow admission webhook a cluster-wide problem, not a local one?
5. What is `caBundle` for, and what error do you get when it's wrong?

**Concept exercise**

> Explain how you'd guarantee every Pod in a team's namespace carries a cost-center
> label *without asking developers to add it and without running a server* — then
> explain the one capability that would force you to run a server after all. Do it
> **without using the words "webhook" or "ValidatingAdmissionPolicy."**

**Debugging / trade-off exercise**

> Right after a teammate deploys a new admission webhook, **all** Pod creation in the
> cluster starts failing — including in `kube-system`. List the three most likely causes
> and how you'd confirm and fix each, in the order you'd check them.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** Mutating runs first; validating sees the final, post-mutation object, so a
 validator can enforce rules about fields a mutator just added.
- **Q2:** VAP can validate (accept/reject) with CEL and no server; it *cannot* mutate.
 A mutating webhook can change the object (inject labels, sidecars, defaults).
- **Q3:** `Fail` rejects when the webhook is unreachable — correct for a security gate
 like "block unsigned images," but risky without HA. `Ignore` lets the request through
 — correct for best-effort label injection.
- **Q4:** Admission is synchronous and in the request path; a slow webhook adds latency
 to (or times out) every matching write across the whole cluster.
- **Q5:** `caBundle` is the CA cert the API server uses to trust the webhook's TLS
 certificate; if it's wrong you get `x509: certificate signed by unknown authority`.
- **Debugging:** (1) `failurePolicy: Fail` combined with the webhook being down or slow;
 (2) the configuration matches too broadly (no `namespaceSelector`) and hits
 `kube-system`, deadlocking the webhook's own pods; (3) a bad `caBundle`/TLS error.
 Confirm with `kubectl get mutatingwebhookconfiguration -o yaml`, the API server logs,
 and the webhook pod logs; fix by scoping/excluding namespaces, switching to `Ignore`
 while you debug, or correcting the cert.

</details>

---

### 9. Further reading

- Kubernetes — [Dynamic Admission Control (webhooks)](https://kubernetes.io/docs/reference/access-authn-authz/extensible-admission-controllers/)
- Kubernetes — [Validating Admission Policy](https://kubernetes.io/docs/reference/access-authn-authz/validating-admission-policy/)
- Kubernetes — [Admission Controllers Reference](https://kubernetes.io/docs/reference/access-authn-authz/admission-controllers/)
- Kubernetes — [CEL for admission](https://kubernetes.io/docs/reference/using-api/cel/)
- cert-manager — [Securing webhooks / CA injection](https://cert-manager.io/docs/)
- Kubernetes — [Pod Security Admission](https://kubernetes.io/docs/concepts/security/pod-security-admission/)

---


_Previous:_ Kubernetes Operators
· _Next:_ API Extension Patterns →

---

## Kubernetes API Extension Patterns

> A CRD gives you a new type; this module makes that type behave like a **first-class
> citizen** of the API. You'll add `/status` and `/scale` subresources (so `kubectl
> scale` and HPAs work on your resource), field selectors and printer columns (so it's
> queryable), and use **Server-Side Apply** so your operator and your users can co-own
> fields without clobbering each other. These are the patterns that separate a toy CRD
> from a production API.

**You'll need:** CRDs and Operators, and a local [kind](https://kind.sigs.k8s.io/) cluster (Kubernetes ≥ 1.31 for CRD field selectors).

### Learning objectives

By the end of this module you will be able to:

- Add `/status` and `/scale` **subresources** to a CRD and explain what each unlocks.
- Make a custom resource queryable with **field selectors** and **printer columns**.
- Use **Server-Side Apply** and reason about field ownership and conflicts.
- Explain **informers/indexers** and when you'd reach for an **aggregated API server**
 instead of a CRD.

---

### 1. Concept

#### Subresources: one object, several endpoints

A subresource is a *second endpoint* on the same object that behaves differently from the
main one. You met `/status` in; `/scale` is the other common one.

- **`/status`** splits spec writes from status writes. Users `PUT` the main resource
 (spec); controllers `PUT /status`. RBAC can grant them separately, and status writes
 don't bump `metadata.generation`, so a controller can tell *"the user changed what they
 want"* from *"I updated how it's going."*
- **`/scale`** exposes a tiny, uniform `Scale` object (`spec.replicas` /
 `status.replicas` / a selector). Enabling it is what makes `kubectl scale
 environment/payments-dev --replicas=5` work **and** lets a HorizontalPodAutoscaler
 target your custom resource — because the HPA only knows how to talk to `/scale`, not
 your bespoke schema.

```yaml
subresources:
 status: {}
 scale:
 specReplicasPath:.spec.replicas # where "desired count" lives
 statusReplicasPath:.status.replicas # where "actual count" lives
 labelSelectorPath:.status.selector # lets an HPA find the Pods
```

The power here is **uniformity**: by implementing the standard scale contract, every
tool that already speaks it works on your type for free.

#### Field selectors and printer columns: make it queryable

By default you can only `--field-selector` a custom resource on a couple of built-in
fields (`metadata.name`, `metadata.namespace`). Declaring **`selectableFields`** lets the
API server index your own fields so the *server* filters for you:

```yaml
selectableFields:
 - jsonPath:.spec.tier
 - jsonPath:.spec.team
```

```bash
kubectl get environments --field-selector spec.tier=prod # server-side filter
```

This matters at scale: without it, "give me all prod environments" means listing
*everything* and filtering client-side. **`additionalPrinterColumns`** is the display
counterpart — it makes `kubectl get` show the columns that matter (tier, replicas,
owner) instead of just name and age.

#### Server-Side Apply: who owns which field?

`kubectl apply` historically diffed against a `last-applied-configuration` annotation
stored client-side — fragile, and blind to other writers. **Server-Side Apply (SSA)**
moves that intelligence into the API server. Every field is tagged with the **field
manager** that set it (visible in `metadata.managedFields`). When two managers try to own
the same field with different values, the server returns a **conflict** rather than
silently letting the last writer win.

```bash
kubectl apply --server-side --field-manager=user -f environment.yaml
# If the operator already owns a field you're changing:
# conflict... field managed by "namespace-provisioner"
kubectl apply --server-side --field-manager=user --force-conflicts -f environment.yaml
```

This is exactly what you want when an **operator** and a **human** (or two controllers)
both write to the same object: the operator owns `status` and the fields it manages, the
user owns `spec` fields, and SSA keeps them from stomping on each other. Controllers
written with controller-runtime increasingly use SSA (`client.Apply`) for precisely this
reason.

#### Informers and indexers: how controllers read efficiently

A controller that did a live `LIST` on every reconcile would hammer the API server. It
doesn't. controller-runtime builds an **informer**: a local, watch-backed **cache** of
the objects you care about. Reads (`r.Get`, `r.List`) hit that cache, not the network.

When you need to look objects up by a field — "find the Environment whose
`status.namespace` is `payments-dev`" — you register an **indexer**:

```go
mgr.GetFieldIndexer().IndexField(ctx, &platformv1alpha1.Environment{},
 "status.namespace", func(o client.Object) []string {
 return []string{o.(*platformv1alpha1.Environment).Status.Namespace}
 })
// then: r.List(ctx, &list, client.MatchingFields{"status.namespace": "payments-dev"})
```

Informers + indexers are why an operator watching thousands of objects stays cheap: it
reads from memory and is notified of changes, instead of polling.

#### Aggregated API servers: when a CRD isn't enough

A CRD stores its data in etcd through the main API server. Occasionally you need more
than that: custom storage (not etcd), arbitrary subresource behavior, on-the-fly computed
responses, or protobuf. For those cases you run your **own API server** and register it
with an `APIService` object so the main API server **aggregates** (proxies) a slice of the
API surface to it. The canonical example is **metrics-server**, which serves
`metrics.k8s.io` with live, uncached data that would be absurd to store in etcd.

> Reach for an aggregated API server rarely. It's a full server to build, secure, and
> operate. CRDs + CEL + webhooks cover the overwhelming majority of needs; aggregation is
> for the few percent that genuinely can't be a CRD.

---

### 2. Why it matters for platform engineering

- **Ecosystem compatibility for free.** Implement the `/scale` contract and HPAs,
 `kubectl scale`, and dashboards work on your resource with zero extra code. Standards
 beat bespoke.
- **Operability at scale.** Field selectors and printer columns turn "list everything and
 grep" into real, server-side queries — essential when there are thousands of custom
 resources.
- **Safe multi-writer automation.** SSA's field ownership is what lets an operator and a
 GitOps pipeline and an occasional human all touch the same object without a last-writer
 race. On a platform, there is *always* more than one writer.
- **Performance.** Informers and indexers keep your controllers cheap and your API server
 healthy as the fleet grows.

---

### 3. Mental model

Think of your CRD graduating from "a row in a database" to "a full API object" by adding
the facets built-in resources already have.

```text
 a bare CRD a first-class API object
 ────────── ────────────────────────
 /environments /environments (spec)
 /environments/<n>/status (controller writes)
 /environments/<n>/scale (kubectl scale, HPA)
 get by name/ns only --field-selector spec.tier=prod
 name + age columns TEAM TIER REPLICAS OWNER PHASE
 last-writer-wins apply Server-Side Apply: every field has an owner
 (managedFields); conflicts are surfaced
```

Rule of thumb: **anything the built-ins can do, your CRD can do too** — you just opt into
each facet (subresource, selectable field, printer column) explicitly.

---

### 4. Minimal implementation

Turn on `/scale` and a field selector, then use them — no controller required to feel the
effect:

```yaml
# in the CRD version:
subresources:
 status: {}
 scale:
 specReplicasPath:.spec.replicas
 statusReplicasPath:.status.replicas
selectableFields:
 - jsonPath:.spec.tier
```

```bash
kubectl apply --server-side -f environment-crd-v2.yaml
kubectl apply --server-side -f environment-sample.yaml

kubectl scale environment/payments-dev --replicas=5 # /scale in action
kubectl get environment payments-dev -o jsonpath='{.spec.replicas}{"\n"}' # 5

kubectl get environments --field-selector spec.tier=prod # server-side filter
```

`kubectl scale` worked on a resource you defined, because you implemented the standard
scale contract. That's the whole theme of the module in four commands.

---

### 5. Hands-on lab

You'll upgrade the `Environment` CRD from into a first-class API: add the
`/scale` subresource and `kubectl scale` it, add `selectableFields` and query by tier, add
printer columns, apply everything with **Server-Side Apply**, provoke and resolve a field
**conflict** between two managers, and add a new **CEL** rule.

➡️ **Start the lab: Make your CRD a first-class API**

---

### 6. Production considerations

- **Add the status subresource from day one; add `/scale` when it's meaningful.** Not
 every resource scales, but if yours has a replica-like notion, `/scale` buys you HPA and
 tooling compatibility cheaply.
- **Declare `selectableFields` for the fields people filter on**, and keep them few —
 each is an index the API server maintains. They need Kubernetes ≥ 1.31 (beta, on by
 default; 1.30 behind a feature gate).
- **Adopt Server-Side Apply for controllers.** Use a stable `fieldManager` name per
 controller so ownership is clear, and only force conflicts deliberately — a forced
 overwrite is you saying "I know better than the other manager."
- **Trust the cache, but know its limits.** Informer reads can be momentarily stale; for
 read-modify-write you still rely on `resourceVersion` optimistic concurrency on write.
- **Prefer CRDs; justify aggregation.** An aggregated API server is a long-term
 operational commitment (its own availability, certs, and upgrades). Only take it on when
 a CRD genuinely can't do the job.

---

### 7. Common mistakes

- **Enabling `/scale` without the backing fields.** — Pointing `specReplicasPath` at a
 field that isn't in the schema makes scale calls fail. *Fix:* ensure `spec.replicas` and
 `status.replicas` exist and are integers.
- **Client-side filtering at scale.** — Listing thousands of CRs and filtering in the
 client because you never declared `selectableFields`. *Fix:* declare the selectable
 fields and let the server filter.
- **Blindly `--force-conflicts`.** — Scripting `--force-conflicts` everywhere to "make the
 error go away," silently overwriting another controller's fields. *Fix:* understand who
 owns the field; force only when you intend to take ownership.
- **Two controllers, no field managers.** — Different controllers writing the same object
 with the default manager name, re-introducing last-writer-wins. *Fix:* give each
 controller a distinct, stable `fieldManager`.
- **Live-listing in the reconcile hot path.** — Bypassing the informer cache with direct
 `APIReader` list calls on every reconcile. *Fix:* read from the cached client; add an
 indexer for field lookups.
- **Reaching for an aggregated API server by default.** — Building a whole server for
 something a CRD would hold. *Fix:* start with a CRD; aggregate only when you hit a real
 CRD limitation.

---

### 8. Assessment

**Knowledge checks**

1. What does enabling the `/scale` subresource let external tools do that they couldn't
 with a bespoke `spec.replicas` field alone?
2. What problem does Server-Side Apply solve that the old client-side apply did not?
3. Why are `selectableFields` better than filtering a full list on the client?
4. What is an informer, and why does a controller read from it instead of the API server
 directly?
5. Name one situation that justifies an aggregated API server instead of a CRD.

**Concept exercise**

> Explain how you'd let both an automated controller and an occasional human safely edit
> the same object's different fields without overwriting each other — **without using the
> words "Server-Side Apply" or "field manager."** Describe the ownership model.

**Debugging / trade-off exercise**

> Your GitOps controller and your operator both manage the same `Environment`. After a
> change, `kubectl apply --server-side` from CI fails with a conflict naming the operator
> as the field's manager. Explain what this is telling you, the two legitimate ways to
> resolve it, and how you'd decide which is correct.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** It implements the standard `Scale` contract, so `kubectl scale`, a
 HorizontalPodAutoscaler, and other tools that speak `/scale` work on your resource
 without knowing its schema.
- **Q2:** SSA tracks per-field ownership on the server (`managedFields`) and surfaces
 conflicts, instead of a client-side `last-applied` annotation that silently lets the
 last writer win and can't see other writers.
- **Q3:** The API server filters server-side using an index, returning only matches;
 client-side filtering means transferring and processing every object.
- **Q4:** An informer is a local, watch-backed cache of objects; controllers read from it
 to avoid hammering the API server and to get change notifications efficiently.
- **Q5:** Serving live/computed data that shouldn't live in etcd (e.g. metrics-server),
 custom storage, or arbitrary subresource behavior a CRD can't express.
- **Debugging:** The conflict means the operator already owns that field; SSA is
 protecting you from silently clobbering it. Resolve by either (a) *not* setting that
 field in CI (let the operator own it) or (b) `--force-conflicts` to take ownership —
 correct only if the field genuinely belongs to Git, not the operator. Decide by asking
 which writer is the source of truth for that field.

</details>

---

### 9. Further reading

- Kubernetes — [CRD subresources (`/status`, `/scale`)](https://kubernetes.io/docs/tasks/extend-kubernetes/custom-resources/custom-resource-definitions/#subresources)
- Kubernetes — [Field selectors for custom resources](https://kubernetes.io/docs/tasks/extend-kubernetes/custom-resources/custom-resource-definitions/#crd-selectable-fields)
- Kubernetes — [Server-Side Apply](https://kubernetes.io/docs/reference/using-api/server-side-apply/)
- Kubernetes — [Setting up an Aggregated API server](https://kubernetes.io/docs/tasks/extend-kubernetes/setup-extension-api-server/)
- Kubernetes — [Horizontal Pod Autoscaler](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/)
- The Kubebuilder Book — [Watching, caches, and indexes](https://book.kubebuilder.io/reference/watching-resources)

---


_Previous:_ Admission Webhooks
· _Next:_ Multi-Cluster Kubernetes →

---

## Multi-Cluster Kubernetes

> One cluster is never the end state. Isolation, availability, data residency, and simple
> scale limits push every serious platform to run *several* clusters — and now you have N
> API servers, N copies of RBAC, and N desired states to keep in sync. This module is
> about taming that: topologies, the management-cluster pattern, treating clusters
> themselves as declarative resources, and delivering one source of truth to a whole
> fleet.

**You'll need:** · Kubernetes Fundamentals, the GitOps ideas from, and a machine that can run **two** small [kind](https://kind.sigs.k8s.io/) clusters at once.

### Learning objectives

By the end of this module you will be able to:

- Give concrete reasons to run **multiple clusters** — and reasons *not* to.
- Compare **hub-and-spoke, mesh, and hierarchical** topologies and the
 **management-cluster** pattern.
- Explain how **Cluster API** treats a cluster as a declarative resource.
- Deliver one application to a whole **fleet** with an Argo CD **ApplicationSet**, and
 manage **multi-cluster kubeconfig**.

---

### 1. Concept

#### Why more than one cluster?

A single cluster is simpler, so you should stay on one as long as you can. You move to
several when one of these forces this on you:

- **Isolation / blast radius.** One cluster is one failure domain and one security
 boundary. A bad admission webhook, a runaway controller, or an etcd problem affects
 *everything* in it. Separating prod from dev — or tenant from tenant — caps the damage.
- **Availability.** A region or zone can fail. Running clusters across regions lets you
 survive the loss of one. A single cluster can't span the planet safely.
- **Regulatory / data residency.** "EU customer data stays in the EU" is often cleanest as
 a cluster in the EU, with a hard boundary rather than a soft namespace one.
- **Team ownership.** Some orgs give platform-critical teams their own cluster so they
 control upgrades and blast radius.
- **Scale limits.** Clusters have real ceilings (nodes, Pods, objects in etcd). Past a
 point you shard across clusters rather than grow one without bound.

The cost is real: every extra cluster is another control plane to run, secure, upgrade,
and pay for. **Multi-cluster is a tool for isolation and scale, not a default.**

#### The new problem: N desired states

With many clusters, the naive workflow is `kubectl --context cluster-1 apply …`, then
`cluster-2`, then `cluster-3`. This is the same anti-pattern you've met all phase:
**imperative, drift-prone, and with no single source of truth.** Miss a cluster and it
silently diverges; there's no loop correcting it. The platform answer is the one you
already know — a **control loop with a declarative source of truth** — lifted to the fleet
level.

#### Topologies

- **Hub-and-spoke (management cluster).** One **management/hub** cluster runs the
 controllers (Argo CD, Cluster API, policy) that provision and deliver to many
 **workload/spoke** clusters. Centralized control, clear separation. This is the most
 common platform shape and the one you'll build in the lab.
- **Mesh.** Clusters peer with each other (e.g. a service mesh spanning clusters) for
 cross-cluster traffic and failover. More capable, much more complex networking.
- **Hierarchical.** Management clusters managing other management clusters — large
 enterprises and cloud providers. Rare; mentioned for completeness.

#### The management-cluster pattern

A **management cluster** hosts the brains and holds credentials to the workload clusters.
It's where your fleet controllers run. Two delivery styles:

- **Push.** The hub reaches out and applies to each spoke (the hub holds spoke
 credentials). Simple, but the hub is a high-value target with wide reach.
- **Pull.** An agent *inside* each spoke pulls its desired state from Git (Flux, or an
 Argo CD agent). The hub never needs inbound access to spokes; better blast-radius and
 security properties at scale.

#### Cluster API: clusters as declarative resources

Here's the reconciliation loop one more time, aimed at the clusters themselves.
**Cluster API (CAPI)** represents a cluster as Kubernetes objects — `Cluster`,
`MachineDeployment`, `KubeadmControlPlane`, and infrastructure objects — in a management
cluster. A CAPI controller reconciles *actual infrastructure* toward that spec: it
provisions control-plane and worker machines, bootstraps them, and heals them. You
`kubectl apply` a cluster the same way you apply a Deployment.

```yaml
# ILLUSTRATIVE ONLY — do not apply. CAPI needs an infrastructure provider installed.
apiVersion: cluster.x-k8s.io/v1beta1
kind: Cluster
metadata:
 name: eu-prod
spec:
 clusterNetwork:
 pods: { cidrBlocks: ["192.168.0.0/16"] }
 controlPlaneRef: { kind: KubeadmControlPlane, name: eu-prod-cp }
 infrastructureRef: { kind: DockerCluster, name: eu-prod } # or AWSCluster, GCPCluster…
```

- **Providers** implement the infrastructure half: CAPA (AWS), CAPG (GCP), CAPZ (Azure),
 vSphere, and a Docker provider for local testing. The top-level `Cluster` contract is
 the same regardless of where it runs.
- CAPI is **heavy** — it's a platform in its own right. We keep it conceptual here: the
 idea to carry forward is "clusters are cattle, defined and reconciled as code," the same
 as everything else in Kubernetes. (Many teams use their cloud's managed cluster +
 Terraform instead; goes deeper.)

#### Fleet delivery: ApplicationSet

Once clusters exist and are **registered** with Argo CD, an **ApplicationSet** with a
**cluster generator** templates one Argo CD `Application` per matching cluster — so a
single object deploys (and keeps reconciled) an app across the whole fleet.

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata: { name: demo-everywhere }
spec:
 generators:
 - clusters: {} # every cluster registered with Argo CD
 template:
 metadata: { name: 'demo-{{name}}' }
 spec:
 project: default
 source: { repoURL: 'https://example.com/platform/apps', path: demo, targetRevision: main }
 destination: { server: '{{server}}', namespace: demo }
 syncPolicy: { automated: { prune: true, selfHeal: true } }
```

`selfHeal: true` is the fleet-level reconciliation loop: drift on any cluster is corrected
back to Git. Add a cluster, and the generator produces an `Application` for it
automatically — no per-cluster edits.

#### Multi-cluster kubeconfig

A **kubeconfig** holds many **contexts** (cluster + user + namespace). One file can drive
every cluster; `kubectl config use-context` switches between them. This is fine for humans
and small fleets, but a single file full of long-lived, high-privilege tokens is a
liability — prefer short-lived, per-cluster credentials and let controllers (not people)
hold fleet-wide reach.

---

### 2. Why it matters for platform engineering

- **Isolation is a platform feature.** Offering "prod is a separate cluster" or "your
 regulated workload runs in-region" is a capability your platform provides — and you need
 to deliver to those clusters consistently.
- **Consistency across the fleet.** The hard part of N clusters isn't creating them; it's
 keeping them *the same*. GitOps fan-out (ApplicationSet) is how one paved road reaches
 every cluster without snowflakes.
- **Clusters as cattle.** Treating clusters as declarative, reproducible resources (CAPI
 or Terraform) is what lets you run many without drowning in manual toil.
- **Security posture.** Where credentials live and which way delivery flows (push vs pull)
 is a core platform security decision once more than one cluster is in play.

---

### 3. Mental model

Picture a **hub** holding the brains and a declarative source of truth, fanning work out
to many **spokes** — and the same self-healing loop running at the fleet level.

```text
 Git (desired state of the fleet)
 │
 ┌──────────────────▼──────────────────┐
 │ MANAGEMENT (hub) cluster │
 │ Argo CD ApplicationSet (clusters) │
 │ Cluster API (clusters as resources) │
 └───────┬───────────────┬───────────────┘
 reconcile │ │ reconcile
 ▼ ▼
 ┌───────────────┐ ┌───────────────┐... (add a spoke →
 │ spoke: dev │ │ spoke: prod │ the generator makes
 │ (context A) │ │ (context B) │ an Application for it)
 └───────────────┘ └───────────────┘
```

Two things to remember: **the fleet is just the reconciliation loop again** (Git is
desired state, a hub controller closes the gap on every cluster), and **clusters
themselves are resources** you define and reconcile, not pets you hand-build.

---

### 4. Minimal implementation

Feel the problem before the tool. With two local clusters you get two contexts; deploying
to "everywhere" by hand is two commands — and already smells of drift:

```bash
kubectl config get-contexts # kind-hub, kind-spoke
kubectl --context kind-hub create deployment demo --image=nginx:1.27
kubectl --context kind-spoke create deployment demo --image=nginx:1.27
# Two clusters = two commands. Fifty clusters = a script that drifts and lies.
```

The declarative answer registers the spokes once and lets one object own the fan-out:

```bash
# on the hub: one ApplicationSet deploys demo to EVERY registered cluster, and self-heals
kubectl --context kind-hub apply -f applicationset.yaml
```

You've turned "apply to each cluster, hope none drift" into "declare it once; a loop keeps
all clusters correct." That's the whole move, and it's the lab.

---

### 5. Hands-on lab

You'll stand up **two** kind clusters (a hub and a spoke), manage both from one kubeconfig
with contexts, install Argo CD on the hub, register the spoke, and apply an
**ApplicationSet** cluster generator that deploys a demo app to both clusters at once. CAPI
stays conceptual (it needs an infra provider); everything you *run* is free and local.

➡️ **Start the lab: Two clusters, one fleet**

---

### 6. Production considerations

- **Credentials are the crown jewels.** A hub with push access to every spoke is a huge
 blast radius. Prefer short-lived, per-cluster credentials, scope them tightly, and
 consider **pull-based** agents so spokes have no inbound exposure.
- **Standardize or drown.** Keep clusters identical via generators/overlays and a single
 Git source. Every manual, per-cluster tweak is a future snowflake you'll debug at 2am.
- **Roll out in waves.** Don't change all clusters at once. Use generators and sync waves
 to canary a change on one cluster, then widen — the fleet version of a progressive
 rollout.
- **Mind version skew.** Clusters drift in Kubernetes version; test against the spread you
 actually run and have an upgrade strategy (CAPI or managed-provider upgrades).
- **Cross-cluster networking isn't free.** Services don't resolve across clusters by
 default. If you need it, adopt **Submariner** or a multi-cluster service mesh
 deliberately — and prefer loosely coupled designs that don't.
- **Right-size the fleet.** Each cluster has fixed overhead. Sometimes namespaces +
 quotas + RBAC in one cluster is the better isolation story than another whole cluster.

---

### 7. Common mistakes

- **Clusters as pets.** — Clicking clusters up in a console, each slightly different, with
 no reproducible definition. *Fix:* define clusters as code (CAPI or Terraform); make
 them rebuildable.
- **Imperative fleet deploys.** — `kubectl apply` to each cluster by hand or in a loop,
 which drifts the moment one call fails. *Fix:* GitOps fan-out (ApplicationSet/Fleet) with
 self-heal.
- **One god credential on the hub.** — A single long-lived, cluster-admin token for every
 spoke. *Fix:* per-cluster, least-privilege, short-lived credentials; consider pull
 delivery.
- **Assuming cross-cluster networking works.** — Expecting a Service in cluster A to be
 reachable from cluster B. *Fix:* it isn't, without explicit multi-cluster discovery;
 design for it or avoid needing it.
- **Snowflake clusters.** — Each cluster configured differently, so nothing is
 reproducible and every incident is bespoke. *Fix:* standardize via generators and a
 single source of truth.
- **Multi-cluster when one would do.** — Splitting into clusters for isolation that
 namespaces + quotas + policy already provide. *Fix:* reserve separate clusters for hard
 boundaries (security, region, availability), not routine separation.

---

### 8. Assessment

**Knowledge checks**

1. Give three distinct reasons an organization runs multiple clusters, and one reason not
 to.
2. In the hub-and-spoke pattern, what runs on the management cluster, and what runs on the
 workload clusters?
3. What does Cluster API treat a *cluster* as, and what does that let you do with
 `kubectl`?
4. What does an ApplicationSet **cluster generator** produce, and what happens when you
 register a new cluster?
5. Contrast **push** and **pull** multi-cluster delivery in terms of where credentials
 live and inbound access.

**Concept exercise**

> Explain how you'd keep the same application deployed and continuously in sync across 20
> clusters, automatically repairing drift on any of them — **without using the words
> "Argo CD," "ApplicationSet," or "GitOps."** Describe it as a control loop with a source
> of truth.

**Debugging / trade-off exercise**

> A company adopted "a cluster per team for isolation" and now runs 50 clusters that were
> each hand-configured; upgrades take weeks and no two clusters are alike. What went wrong,
> and what three changes would you make to get the fleet under control? Separately: name a
> case where a *single* cluster with strong namespace isolation is the better call.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** Isolation/blast radius, availability (region/zone failure), data residency, team
 ownership, or scale limits — any three. A reason not to: the operational and cost
 overhead of running, securing, and upgrading each extra cluster.
- **Q2:** The management cluster runs the fleet controllers (Argo CD, Cluster API, policy)
 and holds credentials; workload clusters run the actual application workloads.
- **Q3:** CAPI treats a cluster as a declarative resource (`Cluster` and friends), so you
 create, scale, upgrade, and delete clusters with `kubectl apply`, reconciled by a
 controller.
- **Q4:** It templates one Argo CD `Application` per matching cluster; registering a new
 cluster makes the generator produce an `Application` for it automatically, with no
 per-cluster edits.
- **Q5:** Push: the hub holds spoke credentials and reaches into each spoke (wide blast
 radius, needs outbound to spokes). Pull: an agent in each spoke pulls from Git, so the
 hub needs no inbound access to spokes — better isolation at scale.
- **Debugging:** The clusters are pets (hand-configured, non-reproducible) with imperative
 management. Fix: define clusters as code (CAPI/Terraform), standardize config via
 generators/overlays from one Git source, and deliver with GitOps fan-out + self-heal. A
 single cluster with namespaces, quotas, RBAC, and policy is better when the isolation you
 need is between *teams/workloads* rather than a hard security, region, or availability
 boundary.

</details>

---

### 9. Further reading

- The Cluster API Book — [Introduction and concepts](https://cluster-api.sigs.k8s.io/)
- Argo CD — [ApplicationSet and the cluster generator](https://argo-cd.readthedocs.io/en/stable/user-guide/application-set/)
- Argo CD — [Declaratively managing clusters](https://argo-cd.readthedocs.io/en/stable/operator-manual/declarative-setup/#clusters)
- Kubernetes — [Configure access to multiple clusters (kubeconfig)](https://kubernetes.io/docs/tasks/access-application-cluster/configure-access-multiple-clusters/)
- Submariner — [Cross-cluster service discovery](https://submariner.io/)
- Istio — [Multicluster deployment models](https://istio.io/latest/docs/ops/deployment/deployment-models/)

---


_Previous:_ API Extension Patterns
· _Next:_ · Observability Engineering →
