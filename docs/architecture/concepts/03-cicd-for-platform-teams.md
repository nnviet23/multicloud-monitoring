# 03 · CI/CD for Platform Teams

> **Project Applicability:** Active in Project

> Up to now you have built container images, Kubernetes manifests, and Terraform
> modules — mostly by running commands on your own machine. That doesn't scale and
> it isn't safe. This phase turns those manual steps into **pipelines**: automated,
> reviewable, least-privilege workflows that build, scan, sign, and promote the
> platform's artifacts. Crucially, you'll learn why a platform team's CI/CD is a
> *different discipline* from application CI/CD — and why the pipeline itself is a
> product your developers consume.

### Why this phase?

Most engineers meet CI/CD as an application concern: run the tests, build the app,
deploy it. Platform CI/CD is a different animal. The thing being changed is the
*substrate every other team runs on* — clusters, networks, IAM, shared Helm charts,
base images, the pipeline templates themselves. A bad application deploy breaks one
service; a bad platform change can break every service at once. That raises the
stakes on review, blast radius, and the question *"who is allowed to approve this?"*

There is a second, quieter shift. In a mature platform, developers do **not** write
their own pipelines from scratch — they *consume* a pipeline the platform team
builds, versions, and supports. The pipeline is a golden path, exactly like the
`new-service.sh` of: encode the paved road once, let every team use it on
demand. That reframes CI/CD from "a YAML file in my repo" to "an internal product
with customers, versions, and adoption metrics."

This phase teaches the problem before the tool, throughout:

- **Why platform pipelines differ** — infrastructure, configuration, and validation
 pipelines, and a failure philosophy that fails fast and *loud*, never silently.
- **GitHub Actions from first principles** — triggers, jobs, contexts, environments,
 and why **keyless OIDC** beats long-lived cloud secrets every time.
- **Reuse** — composite actions and reusable workflows so you write a thing once and
 pin it by SHA everywhere.
- **Pipelines as a product** — versioning, migration, enforcement, escape hatches,
 and measuring adoption of the golden-path pipeline.
- **The two flagship pipelines** — a container `build → scan → sign → push` pipeline
 (Project 1) and a Terraform `plan-on-PR → apply-on-merge` pipeline (Project 2).

## CI/CD Fundamentals for Platform Teams

> Continuous integration and delivery are not new to you as an application
> developer. But when the thing you are shipping is the *platform itself* — clusters,
> shared charts, base images, IAM, and the pipelines other teams depend on — the
> rules change. This module reframes CI/CD from a platform team's point of view:
> what you are really changing, the three kinds of pipeline you will build, and a
> failure philosophy that refuses to fail quietly.

### 1. Concept

#### What is actually being changed?

Application CI/CD answers one question: *is this version of this service good enough
to ship?* The blast radius is one service. If it breaks, one team gets paged and
rolls back.

Platform CI/CD changes the ground every service stands on. A merge to the platform's
Terraform can resize a cluster, rewrite a network rule, or rotate an IAM role. A push
to a shared Helm chart or a base image flows into *every* team that depends on it. The
unit of change is small; the **blast radius is the whole estate**. That single fact
reshapes everything: how you review, how you gate, how you fail, and who gets to
approve.

```text
Application change Platform change
───────────────── ────────────────
one service the substrate every service runs on
one team rolls back many teams affected at once
"did the tests pass?" "what exactly will this do to prod, and who approved it?"
```

#### Three kinds of platform pipeline

Nearly every pipeline a platform team owns is one of three types. Naming them helps
you design the right gates for each.

- **Infrastructure pipelines** change real cloud/cluster resources. The canonical
 shape is Terraform: `fmt → validate → plan → (review) → apply`. The `plan` is a
 preview of changes; `apply` makes them real. These are the highest-stakes pipelines
 because `apply` is often irreversible (you can't un-delete a database).
- **Configuration pipelines** package and publish *desired state* that something else
 will apply later. The canonical shape is a Helm chart: `lint → test (template /
 unit) → package → push` to a registry. Nothing in production changes when this runs
 — it produces a versioned artifact that a deploy or GitOps controller consumes.
- **Validation pipelines** change nothing and *assert* things are as they should be:
 policy checks (OPA/Conftest/Kyverno in CI), **drift detection** (a scheduled
 `terraform plan` that should be empty), security scans (Trivy, `tfsec`, `checkov`),
 and linters. They are the platform's smoke detectors.

```text
Infrastructure plan → apply mutates real resources (highest stakes)
Configuration build → publish produces an artifact (no prod change)
Validation check → report asserts, never mutates (smoke detectors)
```

A useful rule: **a pipeline should do exactly one of these.** Mixing "apply
infrastructure" and "publish a chart" in one job makes the blast radius and the
required reviewers ambiguous.

#### Fail fast, fail loud, never silently skip

Application pipelines can sometimes get away with a flaky step and a retry. Platform
pipelines cannot, because a *silent* failure means the platform's guarantees quietly
stopped being true — and nobody noticed until an incident.

Three rules:

- **Fail fast.** Order cheap, decisive checks first (`fmt`, `lint`, `validate`) so a
 broken change dies in seconds, not after a ten-minute build.
- **Fail loud.** A failed security gate or a non-empty drift plan must turn the build
 red and notify a human. Red is information.
- **Never silently skip.** The most dangerous pattern in platform CI is a check that
 is accidentally disabled: a `continue-on-error: true` left on a scanner, a gate that
 only runs on one branch, a `|| true` that swallows an exit code. A check that can be
 skipped without anyone noticing is worse than no check, because it manufactures false
 confidence.

#### Review requirements differ

Because the blast radius differs, so does the bar for merging. An application change
might need one reviewer. A platform change that touches production infrastructure
typically needs: a reviewed **plan** attached to the PR, a **second approver**
(four-eyes), a protected environment, and often a named owner for the blast-radius
domain (networking, IAM). The pipeline's job is to *make the right review happen
automatically* — surface the plan, require the approval, and refuse to apply without it.

---

### 2. Why it matters for platform engineering

A platform's promise is "consume this and you get security, reliability, and speed by
default." Pipelines are how that promise is **kept mechanically** rather than hoped
for. If signing, scanning, and policy live in a pipeline every change must pass, then
"we sign our images" is a fact, not an aspiration.

The three-type taxonomy also tells you *where the danger is*. Infrastructure pipelines
need the strongest gates because `apply` is irreversible. Configuration pipelines are
safer (they only publish artifacts) but need provenance so you can trust what you
later deploy. Validation pipelines are cheap to run and catch the drift and CVEs that
would otherwise accumulate silently. Designing gates per type — instead of one
copy-pasted pipeline for everything — is a core platform skill.

Finally, this is the phase where the course's throughline becomes real. The container
pipeline and the Terraform pipeline are the engines of
Project 1 and Project 2. Everything here is in service of those two paved roads.

### 3. Mental model

Think of the three pipeline types as a **traffic system** with different controls for
different risks:

```text
 PLATFORM CI/CD — three roads, three sets of controls
 ───────────────────────────────────────────────────

 INFRASTRUCTURE ──► [ fmt ]→[ validate ]→[ plan ]═►(REVIEW GATE)═►[ apply ]
 (mutating) fast cheap checks preview human + policy real change
 four-eyes, env gate

 CONFIGURATION ──► [ lint ]→[ test ]→[ package ]→[ push to registry ]
 (artifact) no production is touched; output is a versioned artifact

 VALIDATION ──► [ scan / policy / drift-plan ] ──► RED if anything is wrong
 (assert) runs on PRs and on a schedule; never mutates; always loud

 Rule of thumb: mutation needs a gate · artifacts need provenance · asserts must be loud
```

If you remember one sentence: **classify the pipeline first, then choose gates to
match its blast radius — and never let a check fail quietly.**

### 4. Minimal implementation

You don't need GitHub Actions to feel the philosophy. A platform pipeline is, at its
core, an ordered list of checks where **any failure stops the line and is visible**.
Here is that idea as a plain shell script — fail-fast via `set -e`, fail-loud via a
non-zero exit, and *no* silent skips:

```bash
#!/usr/bin/env bash
set -euo pipefail # -e fail fast, -u no undefined vars, -o pipefail no masked errors

echo "::group::validation"
terraform fmt -check # cheap, decisive — runs first
terraform validate
tfsec. # security gate; a finding exits non-zero -> red
echo "::endgroup::"

echo "::group::plan"
terraform plan -out plan.tfplan # preview only; mutates nothing
echo "::endgroup::"

# NOTE: no 'apply' here, and no '|| true' anywhere.
# A gate you can skip without noticing is worse than no gate.
```

The anti-pattern to internalize:

```bash
tfsec. || true # <-- WRONG: swallows the exit code; failures vanish
continue-on-error: true # <-- WRONG on a security gate: red becomes green
```

Both lines *look* harmless and are how platforms quietly lose their guarantees. The
whole of this phase is building this same ordered, loud, ungameable pipeline in
GitHub Actions.

### 6. Production considerations

- **One pipeline, one job type.** Keep infrastructure `apply`, artifact `publish`, and
 validation in separate workflows (or at least separate, independently gated jobs) so
 reviewers and permissions match the blast radius.
- **Least privilege per type.** A validation pipeline needs read-only credentials; an
 `apply` pipeline needs write. Don't hand every pipeline an admin role "to be safe" —
 that *is* the unsafe choice.
- **Drift detection is a first-class pipeline.** Schedule a nightly `plan`; a non-empty
 result means reality diverged from code. Alert on it, don't just log it.
- **Make red mean something.** Route pipeline failures to a channel a human watches,
 and treat a flaky platform pipeline as a bug to fix, not noise to mute — muted alarms
 are how silent failures hide.
- **Record who approved what.** For infrastructure changes, the approval trail (plan +
 approver + timestamp) is an audit artifact, not a nicety.
- **Idempotency and reruns.** Platform pipelines get re-run; design them so a second run
 is safe (plans are safe to repeat; applies must be guarded by state locking).

### 7. Common mistakes

- **Treating a platform change like an app change** — one reviewer, no plan attached,
 merge and hope. *Fix:* require a reviewed plan and four-eyes for anything that mutates
 shared infrastructure.
- **`continue-on-error` / `|| true` on a gate** — the build goes green while the check is
 actually failing. *Fix:* gates must be able to fail the build; only use
 `continue-on-error` for genuinely optional, informational steps, and say so explicitly.
- **One mega-pipeline that builds, publishes, and applies** — ambiguous blast radius and
 reviewers; a chart typo can block an urgent infra fix. *Fix:* separate by pipeline type.
- **No drift detection** — you believe prod matches code; it hasn't for weeks. *Fix:* a
 scheduled, alerting `plan`.
- **Slowest check first** — a ten-minute build runs before a one-second `fmt` that would
 have failed anyway. *Fix:* order checks cheap-and-decisive first (fail fast).
- **Giving pipelines standing admin credentials** — huge blast radius if the token leaks.
 *Fix:* least-privilege, short-lived credentials (keyless OIDC, ).

### 8. Assessment

**Knowledge checks**

1. In blast-radius terms, how does a platform change differ from an application change?
2. Name the three platform pipeline types and give the canonical stages of each.
3. Which pipeline type is highest-stakes, and why?
4. What does "never silently skip" mean, and give two concrete anti-patterns that
 violate it.
5. Why might a production infrastructure change need a reviewed plan plus a second
 approver when an app change needs neither?

**Concept exercise**

> Explain the difference between an infrastructure pipeline and a configuration
> pipeline **without using the words "Terraform" or "Helm."** Describe what each one
> changes and when the real-world effect happens.

**Trade-off / debugging exercise**

> A teammate's platform workflow is green on every run, yet production has a critical
> CVE and the staging network rule never actually changed. You open the YAML and see
> `continue-on-error: true` on the Trivy step and an `apply` job with an `if:` that
> only matches a branch nobody uses. Explain what went wrong in failure-philosophy
> terms, and what you'd change.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** An app change affects one service; a platform change alters the shared
 substrate (clusters, networking, IAM, base images, shared charts), so a single merge
 can affect every team at once.
- **Q2:** Infrastructure (`fmt → validate → plan → apply`), configuration (`lint →
 test → package → push`), validation (`scan/policy/drift → report`).
- **Q3:** Infrastructure, because `apply` mutates real resources and is often
 irreversible (you can't un-delete data), so its gates must be strongest.
- **Q4:** It means no check may fail without turning the build red and notifying
 someone. Anti-patterns: `|| true` swallowing an exit code, and `continue-on-error:
 true` on a gate — both turn red into green.
- **Q5:** Because the blast radius is the whole estate and `apply` can be
 irreversible; a reviewed plan shows exactly what will change and four-eyes reduces
 the chance a destructive change merges unnoticed.
- **Debugging:** Both failures are *silent skips*. `continue-on-error` let a real CVE
 pass as green (fail-loud violated); the branch-scoped `if:` meant the apply never ran
 yet the pipeline still reported success (never-silently-skip violated). Fix: remove
 `continue-on-error` from the gate, correct the branch condition, and add an assertion
 that the apply actually executed (or fail the job if it was skipped).

</details>


## GitHub Actions Deep Dive

> GitHub Actions is the engine for every pipeline in this phase. This module takes it
> apart from first principles — triggers, jobs, steps, contexts, environments, and
> concurrency — and then spends its energy on the single most important platform
> security move in CI: **keyless authentication with OIDC**, so your pipelines reach
> the cloud with short-lived, scoped credentials instead of a long-lived secret
> waiting to leak.

(free), and optionally [`actionlint`](https://github.com/rhysd/actionlint). The core lab
is local; a cloud account is optional and clearly marked.

### 1. Concept

#### Workflow anatomy

A workflow is a YAML file in `.github/workflows/`. Four nouns do all the work:

- **Event** — *what* starts the run (`on:`). A push, a pull request, a button, a timer.
- **Job** — a unit that runs on one **runner** (a fresh VM/container). Jobs run in
 parallel by default; `needs:` makes one wait for another.
- **Step** — an ordered action inside a job: either a `run:` shell command or a
 `uses:` reusable action.
- **Runner** — the machine the job executes on (`runs-on: ubuntu-latest` for
 GitHub-hosted, or a self-hosted label).

```yaml
on: [push] # event
jobs:
 build: # job
 runs-on: ubuntu-latest # runner
 steps:
 - uses: actions/checkout@v4 # step (an action)
 - run: echo "hello" # step (a command)
```

Each job gets a **clean machine**. Nothing persists between jobs unless you pass it
explicitly (outputs, artifacts, or a cache). That isolation is a feature: it makes
runs reproducible and stops one job's mess from leaking into another.

#### Events: pick the trigger that matches the intent

- **`pull_request`** — run validation on proposed changes *before* merge. This is
 where your `plan`, lint, and scan gates live.
- **`push`** (often filtered to `main`) — run the pipeline that acts on the merged
 result: publish an artifact, apply infrastructure, deploy.
- **`workflow_dispatch`** — a manual button (with typed inputs). Use for promotions,
 one-off applies, and break-glass.
- **`schedule`** — a cron timer. Use for drift detection and nightly re-scans.

```yaml
on:
 pull_request:
 push:
 branches: [main]
 workflow_dispatch:
 schedule:
 - cron: "0 3 * * *"
```

#### Contexts: where your data comes from

**Contexts** are read-only objects you interpolate with `${{ }}`:

- **`github`** — the event payload: `github.ref`, `github.sha`, `github.event_name`,
 `github.actor`, `github.repository`.
- **`env`** — environment variables you set at workflow/job/step scope.
- **`vars`** — organization/repo **configuration variables** (non-secret).
- **`secrets`** — encrypted secrets. *Masked* in logs, but still long-lived if they are
 static credentials — which is exactly what OIDC lets you avoid.
- **`runner`** — facts about the machine (`runner.os`, `runner.temp`).
- **`job` / `steps`** — status and **outputs** of the current job and prior steps
 (`steps.build.outputs.digest`).

#### GitHub Environments and protection rules

A GitHub **Environment** (for example `dev`, `staging`, `production`) is a named
deployment target you attach rules to:

- **Required reviewers** — a human must approve before a job targeting that
 environment runs. This is your four-eyes gate for `apply`.
- **Wait timer** — a forced delay (soak time) before deploy.
- **Deployment branches** — only `main` may deploy to `production`.
- **Environment secrets/variables** — scoped per environment, so prod credentials
 never load on a dev run.

```yaml
jobs:
 deploy-prod:
 runs-on: ubuntu-latest
 environment: production # pauses here until a required reviewer approves
 steps:
 - run:./deploy.sh
```

#### Keyless OIDC: the headline act

The old way to let a pipeline touch your cloud: mint a static access key, paste it
into a GitHub secret, and hope it never leaks, never gets logged, and someone
remembers to rotate it. That secret is **long-lived, broadly scoped, and invisible
once stolen** — the worst properties a credential can have.

**OIDC (OpenID Connect)** removes the stored secret entirely. On each run, GitHub
mints a short-lived, signed **JSON Web Token (JWT)** describing *who is asking*: the
repository, the branch/tag (`ref`), the environment, the workflow. Your cloud
provider is configured to **trust GitHub's token issuer** and to exchange that JWT
for **short-lived cloud credentials** — but only when the token's claims match
conditions you set (e.g. "repo = `platform-org/infra` AND environment =
`production`"). Nothing durable is stored in GitHub.

```text
No stored secret. A fresh, scoped identity is minted per run and expires in minutes.
```

To request the token, the workflow must be granted the `id-token: write` permission:

```yaml
permissions:
 id-token: write # allows the runner to request an OIDC token
 contents: read
```

#### Concurrency: don't let two runs collide

Two pipelines applying to `production` at once is a recipe for corrupted state and
half-applied changes. A **concurrency group** serializes runs that share a key, and
can cancel superseded ones:

```yaml
concurrency:
 group: deploy-${{ github.ref }}
 cancel-in-progress: false # for apply/deploy: queue, don't cancel mid-apply
```

Use `cancel-in-progress: true` for PR validation (newer commit supersedes the old
run) and `false` for anything that mutates state (let the in-flight apply finish).

#### Self-hosted runners: when and why

GitHub-hosted runners are ephemeral and maintenance-free — prefer them. Reach for
**self-hosted** runners only when you genuinely need: access to a private network,
a specific GPU/architecture, or caches too large for hosted runners. The cost is that
*you* now own their security and patching — and a self-hosted runner on a public repo
is a well-known attack vector. Default to hosted; justify self-hosted.

---

### 2. Why it matters for platform engineering

Platform pipelines hold the keys to the kingdom: they can change infrastructure,
publish the base image everyone pulls, and deploy to production. That makes their
*credentials* the single juiciest target in your whole system. Moving from stored
secrets to **keyless OIDC** removes the highest-value, longest-lived secret from your
pipelines — there is nothing durable left to steal, and access is scoped to exactly
the repo, branch, and environment that should have it.

Environments and concurrency turn the fuzzy idea "production is special" into
*mechanical* controls: a required reviewer the pipeline literally waits for, and a
lock that stops two applies racing. These are the primitives you'll compose into the
Project 1 and Project 2 pipelines — the signing step, the Trivy gate, the Terraform
`apply` behind a prod environment — later in this phase.

### 3. Mental model

```text
 GITHUB ACTIONS — anatomy + the OIDC token exchange
 ──────────────────────────────────────────────────

 EVENT ──► WORKFLOW ──► JOB (fresh runner) ──► STEP ──► STEP ──►...
 push.yml runs-on: uses: run:
 pull_req ubuntu-latest action command
 dispatch │
 schedule │ needs: (ordering) contexts: ${{ github.* env.* steps.* }}
 ▼
 ENVIRONMENT ── required reviewer? ──► (wait) ──► run

 Keyless cloud access (no stored secret):

 Runner ──(1) request OIDC token (id-token: write)──► GitHub OIDC issuer
 Runner ◄─(2) short-lived signed JWT (claims: repo, ref, environment) ─┘
 Runner ──(3) present JWT ──► Cloud STS ──(4) verify issuer + claims──► short-lived creds
 Runner ──(5) use creds for a few minutes, then they expire

 One line: a workflow is events→jobs→steps, gated by environments, authenticating
 with a fresh scoped identity per run instead of a stored key.
```

### 4. Minimal implementation

Start with the smallest workflow that shows anatomy *and* contexts — no cloud yet:

```yaml
name: hello
on:
 pull_request:
 workflow_dispatch:

permissions:
 contents: read

concurrency:
 group: hello-${{ github.ref }}
 cancel-in-progress: true

jobs:
 greet:
 runs-on: ubuntu-latest
 steps:
 - uses: actions/checkout@v4
 - name: Show context
 run: |
 echo "event=${{ github.event_name }}"
 echo "ref=${{ github.ref }} sha=${{ github.sha }}"
 echo "actor=${{ github.actor }} os=${{ runner.os }}"
 - id: build
 run: echo "digest=sha256:deadbeef" >> "$GITHUB_OUTPUT"
 - name: Use a prior step's output
 run: echo "built ${{ steps.build.outputs.digest }}"
```

Two things to notice: the job runs on a clean machine, and data flows forward through
**outputs** (`$GITHUB_OUTPUT`) and **contexts**, never through shared disk. Now
contrast the two ways to reach the cloud:

```yaml
# ❌ The old way: a long-lived secret, stored forever, scoped to everything.
# - run: gcloud auth activate-service-account --key-file=<(echo "${{ secrets.GCP_SA_KEY }}")

# ✅ Keyless: request a short-lived token; exchange it for minutes-long creds.
permissions:
 id-token: write
 contents: read
```

You'll wire the full keyless exchange in the lab.

### 6. Production considerations

- **Keyless everywhere.** Make OIDC the default for every cloud and registry that
 supports it; treat a remaining long-lived credential as tech debt with a removal date.
- **Scope the trust conditions tightly.** On the cloud side, bind the role to a
 specific repo *and* ref/environment. A trust policy that accepts "any repo in the
 org" is a lateral-movement risk.
- **Least-privilege `permissions:`.** Set `permissions:` to the minimum at the top of
 every workflow (`contents: read`), and widen per-job only where needed.
- **Protect production with Environments.** Required reviewers, deployment branches,
 and environment-scoped secrets are the difference between "prod is special" as a
 slogan and as an enforced rule.
- **Concurrency on anything that mutates.** `cancel-in-progress: false` for apply/deploy;
 `true` for PR validation.
- **Prefer hosted runners.** Reach for self-hosted only with a concrete reason, and then
 isolate them (ephemeral, no secrets on disk, never on untrusted PRs).
- **Pin actions.** Use pinned versions (ideally by SHA — ), not a moving
 `@master`, so a compromised upstream can't silently change your pipeline.

### 7. Common mistakes

- **Storing a static cloud key as a secret** — long-lived, broadly scoped, invisible
 when leaked. *Fix:* keyless OIDC with `id-token: write` and a scoped trust policy.
- **Over-broad `permissions:`** — leaving the default read/write token on every job.
 *Fix:* default `contents: read`; grant more only where required.
- **No concurrency control on deploy** — two merges apply to prod simultaneously and
 corrupt state. *Fix:* a `concurrency` group keyed to the environment, no cancel.
- **`pull_request_target` misuse** — running untrusted PR code with write permissions.
 *Fix:* use `pull_request` for validation; never expose secrets to fork PRs.
- **Trust condition too loose** — the cloud role accepts tokens from any repo/branch.
 *Fix:* bind to the exact repository and ref/environment claim.
- **Secrets in `echo`** — printing a secret, which may survive in logs. *Fix:* never log
 secrets; rely on masking and, better, don't have a stored secret at all.

### 8. Assessment

**Knowledge checks**

1. What are the four building blocks of a workflow, and what runs in parallel by default?
2. Which trigger fits each: pre-merge validation, nightly drift check, a manual
 promotion, acting on a merge to `main`?
3. What claims does a GitHub OIDC token carry, and how does the cloud use them?
4. What single permission must a workflow have to request an OIDC token?
5. When do you want `cancel-in-progress: true` versus `false`?

**Concept exercise**

> Explain how a pipeline can authenticate to a cloud provider **without storing any
> credential**, and why that is safer — *without using the words "OIDC" or "token."*
> Describe what is presented, what is checked, and how long the access lasts.

**Trade-off / debugging exercise**

> A workflow deploys to production. It uses `on: push` with no branch filter, no
> `environment:`, a static `secrets.CLOUD_KEY`, and no `concurrency`. List four
> concrete risks this design creates and the specific change that fixes each.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** Events, jobs, steps, runners. Jobs run in parallel unless ordered with
 `needs:`.
- **Q2:** `pull_request` (pre-merge validation), `schedule` (nightly drift),
 `workflow_dispatch` (manual promotion), `push` filtered to `main` (act on merge).
- **Q3:** Claims like repository, `ref`, environment, and workflow. The cloud verifies
 the token's issuer signature and matches the claims against a trust policy, then
 issues short-lived credentials.
- **Q4:** `id-token: write`.
- **Q5:** `true` for PR validation (a newer commit should supersede the running job);
 `false` for apply/deploy (let the in-flight mutation finish rather than cancel it).
- **Debugging:** (1) No branch filter → any branch can deploy to prod — add
 `branches: [main]` and/or deployment-branch rules. (2) No `environment:` → no required
 reviewer — add `environment: production`. (3) Static key → leak risk — switch to keyless
 OIDC. (4) No `concurrency` → racing applies — add a concurrency group keyed to prod with
 `cancel-in-progress: false`.

</details>


_Previous:_ CI/CD Fundamentals for Platform Teams · _Next:_ Reusable Workflows and Composite Actions

## Reusable Workflows and Composite Actions

> The fastest way to lose control of a platform's CI is to let every team copy-paste
> the same 80 lines of YAML into their repo. The moment you need to change the scan
> step, you're editing 200 files. This module teaches the two mechanisms that fix
> that — **composite actions** and **reusable workflows** — and the security practice
> that makes shared automation safe: **pinning everything by commit SHA**.

and [`actionlint`](https://github.com/rhysd/actionlint). The lab is local.

### 1. Concept

#### The copy-paste problem

Shared logic that lives as copied YAML has no single source of truth. Fixing a bug or
tightening the Trivy gate means a migration across every repository — and the repos
drift out of sync in the meantime. The platform move is the same one you've made all
course: **encode the paved road once, let teams consume it.** GitHub gives you two
tools for that, at two different granularities.

#### Composite action — bundle *steps*

A **composite action** packages several steps behind one `uses:`. It runs *inside* a
caller's job, on the caller's runner. Reach for it when you want to say "do these five
steps as one" — checkout, set up a toolchain, log in, build.

```yaml
# action.yml (a composite action)
name: "Build and tag"
description: "Compute an immutable tag and build the image."
inputs:
 image-name:
 description: "Image name."
 required: true
outputs:
 tag:
 description: "Computed tag."
 value: ${{ steps.meta.outputs.tag }}
runs:
 using: "composite"
 steps:
 - id: meta
 shell: bash # composite run steps MUST set a shell
 run: echo "tag=${{ inputs.image-name }}:${GITHUB_SHA::7}" >> "$GITHUB_OUTPUT"
```

Key facts: it uses `inputs`/`outputs`, every `run` step needs an explicit `shell:`, and
it has no `runs-on` of its own — it borrows the caller's job.

#### Reusable workflow — bundle *jobs*

A **reusable workflow** packages one or more whole **jobs**, called from another
workflow as a job via `uses:` plus `workflow_call`. Reach for it when you want to share
an *entire pipeline* — its own runners, matrix, environments, and gates.

```yaml
#.github/workflows/app-ci.yml (a reusable workflow)
on:
 workflow_call:
 inputs:
 image-name: { required: true, type: string }
 outputs:
 tag: { value: ${{ jobs.build.outputs.tag }} }
 secrets:
 registry-token: { required: false }
jobs:
 build:
 runs-on: ubuntu-latest
 outputs: { tag: ${{ steps.m.outputs.tag }} }
 steps:
 - uses: actions/checkout@v4
 - id: m
 run: echo "tag=${{ inputs.image-name }}:${GITHUB_SHA::7}" >> "$GITHUB_OUTPUT"
```

#### Which one? A decision rule

```text
Sharing a few STEPS inside someone's job → composite action
Sharing one or more whole JOBS / a pipeline → reusable workflow
Need your own runners/matrix/environments → reusable workflow
Need to drop into an existing job mid-stream → composite action
```

The two compose: a reusable workflow's jobs can *use* your composite actions. That's
the normal shape of a mature library.

#### Inputs, outputs, secrets

- **Inputs** are typed (`string`, `boolean`, `number`) for reusable workflows; composite
 action inputs are strings. Always give sensible defaults.
- **Outputs** let callers read a result — a computed tag, a digest, a plan summary.
- **Secrets** are passed explicitly to reusable workflows (`secrets:` block) or in bulk
 with `secrets: inherit`. Prefer explicit passing so a workflow only sees what it needs.

#### Versioning and the central registry

Put shared automation in **one or two dedicated repositories** — a `platform-actions`
repo for composite actions and a `platform-workflows` repo for reusable workflows — so
there is a single source of truth and a single place to review changes. Cut **releases**
(Git tags like `v1.4.0`) so consumers have stable versions to point at, and maintain a
moving major tag (`v1`) for convenience.

```text
platform-actions/ platform-workflows/
├── semver-tag/action.yml └──.github/workflows/
├── build-and-push/action.yml ├── app-ci.yml (reusable)
└── terraform-plan/action.yml └── terraform.yml (reusable)
 releases: v1.0.0, v1.1.0, v1 → releases: v2.0.0, v2.3.1, v2 → …
```

#### Pin by SHA — the security rule that matters

A tag like `@v1` is **mutable**: whoever controls the upstream repo can move it to
point at new code. If that upstream is compromised, your pipeline silently starts
running the attacker's steps — with your repo's token. This is not hypothetical;
real supply-chain attacks have worked exactly by moving a popular action's tag.

The defense is to pin third-party (and even your own) actions by **immutable commit
SHA**, with the human version in a trailing comment:

```yaml
- uses: actions/checkout@08c6903cd8c0fde910a37f88322edcfb5dd907a8 # v5.0.0
```

A moved tag can't change a SHA. Let Dependabot propose SHA bumps so pinning doesn't
mean going stale. First-party, same-org actions are lower risk, but pinning is still
the platform-grade default.

#### Build vs adopt

Don't rebuild `actions/checkout`. **Adopt** well-maintained, popular community actions
for commodity tasks (checkout, cloud auth, Docker buildx) — pinned by SHA. **Build** a
custom action when you need to bake in *your organization's* policy: the exact scan
thresholds, the required labels, the signing step every image must pass. Custom actions
are where your platform's opinions live.

---

### 2. Why it matters for platform engineering

Reuse is the mechanism behind "the platform owns the pipeline." When the scan gate, the
signing step, and the tag convention live in one composite action and one reusable
workflow, the platform team can improve security for every team with a single
versioned release — no mass migration, no drift. That is enormous leverage: one change,
hundreds of repos.

SHA pinning is where platform engineering's "security is structural" principle meets
CI. Your pipelines carry the most powerful tokens you own; an unpinned action is a
standing invitation for a supply-chain compromise to use them. Pinning turns a trust
decision you make *once* (review this exact commit) into something an attacker can't
quietly revoke by moving a tag. This library and these pins are the substrate for the
Project 1 build pipeline and the Project 2 Terraform pipeline you assemble next.

### 3. Mental model

```text
 COMPOSITE ACTION vs REUSABLE WORKFLOW
 ─────────────────────────────────────

 Caller workflow
 ├── job: build (runs-on: ubuntu-latest)
 │ ├── step ── uses: org/platform-actions/semver-tag@<SHA> ◄── COMPOSITE
 │ │ (expands into several steps, in THIS job) = bundle of STEPS
 │ └── step ── run: docker build...
 │
 └── job: ci ──── uses: org/platform-workflows/.github/workflows/app-ci.yml@<SHA>
 (runs as its OWN job(s), own runner/matrix) ◄── REUSABLE WORKFLOW
 with: {…} secrets: inherit = bundle of JOBS

 Supply chain: @v1 (mutable tag — can be MOVED by upstream) ✗
 @<40-char SHA> (immutable — cannot change) ✓ + Dependabot bumps

 One line: steps → composite action; jobs/pipelines → reusable workflow; pin both by SHA.
```

### 4. Minimal implementation

Feel the difference by factoring one duplicated idea — "compute an immutable tag" — into
a composite action, then calling it:

```yaml
# platform-actions/semver-tag/action.yml
name: "Semantic version tag"
description: "Compute main-<shortsha> style tag."
inputs:
 prefix: { description: "Optional prefix", required: false, default: "" }
outputs:
 tag: { description: "Computed tag", value: ${{ steps.c.outputs.tag }} }
runs:
 using: "composite"
 steps:
 - id: c
 shell: bash
 run: |
 t="${GITHUB_REF_NAME//\//-}-${GITHUB_SHA::7}"
 [ -n "${{ inputs.prefix }}" ] && t="${{ inputs.prefix }}:${t}"
 echo "tag=${t}" >> "$GITHUB_OUTPUT"
```

```yaml
# a caller, pinning the action by SHA
jobs:
 build:
 runs-on: ubuntu-latest
 steps:
 - uses: actions/checkout@08c6903cd8c0fde910a37f88322edcfb5dd907a8 # v5.0.0
 - id: v
 uses: platform-org/platform-actions/semver-tag@a1b2c3d4e5f6… # v1.4.0
 with: { prefix: payments }
 - run: echo "tag is ${{ steps.v.outputs.tag }}"
```

One definition, every repo consumes it, and the pin makes the supply chain auditable.
In the lab you'll build this plus a reusable workflow and wire a caller to both.

### 6. Production considerations

- **A real central registry.** Put actions and reusable workflows in dedicated repos
 with CODEOWNERS, required reviews, and their own CI that tests the actions themselves.
- **Pin by SHA, automate the bumps.** SHA pins everywhere; Dependabot (or Renovate) to
 propose updates so pinning doesn't rot into staleness.
- **Version deliberately.** Semantic versioning for your library; a moving major tag for
 convenience, but publish release notes and a changelog — consumers depend on you.
- **Test your actions.** A broken shared action breaks everyone at once. Give the
 library a test matrix and a canary consumer before you move the major tag.
- **Least-secret passing.** Prefer explicit `secrets:` over `secrets: inherit` so a
 called workflow sees only what it needs.
- **Document inputs/outputs.** Treat the action/workflow interface like a public API —
 because to your developers, it is.

### 7. Common mistakes

- **Copy-pasting YAML across repos** — no source of truth; a fix means editing N files.
 *Fix:* a composite action or reusable workflow in a central library.
- **Pinning third-party actions by moving tag (`@v1`, `@master`)** — a compromised
 upstream silently runs in your pipeline with your tokens. *Fix:* pin by SHA with a
 version comment; automate bumps.
- **Reaching for a reusable workflow to share three steps** — heavyweight; you wanted a
 composite action. *Fix:* match granularity — steps→composite, jobs→reusable workflow.
- **Forgetting `shell:` in a composite action** — the run step fails to parse. *Fix:*
 every composite `run` sets `shell: bash` (or similar).
- **`secrets: inherit` everywhere** — passes every secret to code that may not need it.
 *Fix:* pass only the secrets required, explicitly.
- **Rebuilding commodity actions** — maintaining your own checkout/buildx wrapper for no
 reason. *Fix:* adopt popular community actions (pinned); build only org-specific policy.

### 8. Assessment

**Knowledge checks**

1. In one sentence each, what is a composite action and what is a reusable workflow?
2. You want to share an entire build-scan-sign pipeline, with its own runner — which do
 you use?
3. Why must you pin third-party actions by SHA rather than by tag?
4. How do you return a value from a reusable workflow to its caller?
5. What's one thing you should *build* a custom action for, and one you shouldn't?

**Concept exercise**

> Explain the difference between sharing "a few steps" and "a whole pipeline" **without
> naming composite actions or reusable workflows.** Describe where each shared unit runs
> and what it brings with it.

**Trade-off / debugging exercise**

> Your org pins every action by `@v1`. A popular third-party action's maintainer account
> is compromised and `v1` is moved to malicious code; within an hour, build tokens across
> the org are exfiltrated. Walk through exactly how the attack reached your pipelines, and
> the change that would have prevented it — plus how you'd keep that change from going stale.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** A composite action bundles several *steps* behind one `uses:`, running inside
 the caller's job. A reusable workflow bundles whole *jobs* called via `workflow_call`.
- **Q2:** A reusable workflow — it brings its own `runs-on`, matrix, and environments.
- **Q3:** Tags are mutable; upstream (or an attacker who compromises it) can move `@v1`
 to new code that then runs in your pipeline with your permissions. A SHA is immutable.
- **Q4:** Declare it under `on.workflow_call.outputs` with a `value:` referencing a job
 output; the caller reads `needs.<job>.outputs.<name>` (or the job's `outputs`).
- **Q5:** Build: org-specific policy (your scan thresholds, signing, required labels).
 Don't build: commodity tasks like checkout or cloud auth — adopt and pin those.
- **Debugging:** The mutable `@v1` tag let the attacker point your `uses:` at new code
 without changing your YAML; your runner executed it with the job's `GITHUB_TOKEN`/cloud
 identity and exfiltrated it. SHA pinning (`@<40-char sha>`) would have made the moved
 tag irrelevant. Keep it fresh with Dependabot/Renovate proposing reviewed SHA bumps.

</details>


_Previous:_ GitHub Actions Deep Dive · _Next:_ Pipeline Templates as a Platform Product

## Pipeline Templates as a Platform Product

> In you learned that a platform is a *product* with customers. Here that
> idea gets concrete and technical: the pipeline itself is a product. The platform
> team owns, versions, and supports a golden-path pipeline template; application teams
> *consume* it with a few lines instead of writing CI from scratch. This module is
> about treating that template like software with users — versioning, migration,
> enforcement, escape hatches, and adoption metrics.

account (free). The lab is local.

### 1. Concept

#### The template is the product

Left to themselves, every application team writes its own CI: a slightly different
build, a scanner someone forgot to add, a signing step nobody got around to. The
result is N subtly different pipelines and N different security postures. The platform
move is the one from 's `new-service.sh`: **encode the paved road once.**
The platform team builds a reusable workflow — call it `app-ci@v2` — that does the
right things in the right order (lint → test → build → scan → sign → push), and app
teams consume it:

```yaml
jobs:
 ci:
 uses: platform-org/platform-workflows/.github/workflows/app-ci.yml@v2
 with:
 image-name: payments
 secrets: inherit
```

That is the whole of an app team's CI. They get the platform's security and
conventions *by default*, and the platform team can improve all of them at once.

#### Consume, don't author

The point is not to hide YAML — it's to move the **responsibility**. When teams author
their own pipelines, the platform team can only *advise*. When teams consume a
template, the platform team can *guarantee*: "every production image is scanned and
signed" becomes a property of the template, not a hope about 50 repos. Developers trade
control they didn't want for cognitive load they're glad to shed — exactly the deal
platform engineering offers everywhere.

#### Versioning and migration — you have users now

A template with consumers is an API. Break it and you break everyone. So you version it
and provide a migration path, like any product:

- **Semantic versions.** `v1`, `v1.1`, `v2`. A moving major tag (`v2`) lets consumers
 track non-breaking improvements automatically; a breaking change means a new major.
- **Deprecation, not deletion.** When `v2` lands, `v1` keeps working and starts emitting
 a deprecation warning with a migration link and a sunset date. You don't yank it.
- **Migration guides and codemods.** Tell consumers exactly what changed and, ideally,
 open the PRs for them (a bot that bumps `@v1` → `@v2` and adjusts inputs).
- **Changelogs.** Consumers plan around your releases; give them release notes.

```text
v1 ──(non-breaking)──► v1.1 ──► v1.2 (v1 tag follows along)
 │
 breaking change ──────────────► v2 (v1 still works; warns; sunset date set)
```

#### Enforcement without gatekeeping

For production, "please use the template" isn't enough — but *mandating* it the wrong
way recreates the gatekeeper bottleneck warned against. Enforce the
**outcome**, not the keystrokes:

- **Required workflows / org rulesets.** GitHub can require a given workflow to run on
 matching repos before merge.
- **Required status checks.** Branch protection requires the template's check names to
 pass before merge to `main`.
- **Provenance at the deployment gate.** The strongest option: the production
 environment only admits images **signed by the platform pipeline**. A hand-rolled pipeline literally can't
 produce a deployable artifact, because it can't sign with the platform's identity.

The last one is the platform ideal: you don't police *how* teams build; you make the
paved road the only path that *reaches production*, because only it yields a signed,
admissible artifact.

#### Escape hatches — opinionated, not mandatory

Real teams have legitimate exceptions: a service that genuinely can't run the slow
integration suite on every PR, a one-off that needs a different base image. A platform
that forbids all deviation gets routed around. So build **visible, auditable** escape
hatches:

- A typed input (`skip-integration-tests: true`) that is **off by default**, **logged**,
 and surfaced in an adoption/exception report.
- An exception process (a label + platform sign-off) for anything higher-stakes.
- A clean way to *extend* the template (pre/post hooks) rather than fork it.

The rule from: **opinionated defaults, not mandatory cages.** An escape hatch
you can see and count is far safer than teams silently forking the template.

#### Adoption is the scoreboard

A gorgeous template nobody uses is a failed product. Measure adoption from day one:

- **What % of production services deploy via the golden-path pipeline?** (Count repos
 whose workflows `uses:` the template, or — better — count production images that carry
 the platform's signature.)
- **Escape-hatch rate.** How often is each hatch used? A spike means the default is wrong
 and the template needs to change — the hatch is a product-feedback signal.
- **Time-to-adopt a new version.** How long until consumers move from `v1` to `v2`?
 Slow migration means your migration path is too painful.

---

### 2. Why it matters for platform engineering

This module is where CI/CD stops being "a YAML file" and becomes platform product
management. The reusable-workflow mechanics from are the *how*; this is the
*why and for whom*. Owning the template is the single highest-leverage thing a platform
team does in CI: one release improves security, speed, and consistency for every team
simultaneously — the leverage that justifies the platform team's existence.

It also reframes governance. Instead of chasing teams to adopt good practice, you make
good practice the path of least resistance and the only route to production. Enforcement
by provenance, escape hatches you can count, and adoption metrics are how you get
security and reliability *by default* while still treating developers as customers, not
subjects. This template is literally the pipeline Project 1 and Project 2 teams consume.

### 3. Mental model

```text
 THE PIPELINE TEMPLATE AS A PRODUCT
 ──────────────────────────────────

 PLATFORM TEAM (owns) APP TEAMS (consume)
 ┌───────────────────────────┐ ┌───────────────────────────┐
 │ app-ci@v2 (reusable wf) │ │ uses: …/app-ci.yml@v2 │
 │ lint→test→build→scan→ │ ◄─────── │ with: { image-name: … } │ × N repos
 │ sign→push │ consume │ (3 lines of CI, not 300) │
 └───────────────────────────┘ └───────────────────────────┘
 │ releases: v1→v1.1→v2 (deprecate, don't delete; migration guide)
 │ enforce OUTCOME: prod admits only images SIGNED by this pipeline
 │ escape hatches: typed, default-off, logged, counted
 ▼
 ADOPTION METRIC = % of prod services on the golden path ← the real scoreboard

 One line: own and version the template; enforce the outcome; keep hatches visible;
 measure adoption — a platform product, not a mandate.
```

### 4. Minimal implementation

The smallest "template as product" is a reusable workflow plus a three-line consumer.
Here's the consumer — the entire CI an application team maintains:

```yaml
#.github/workflows/ci.yml in an APPLICATION repo
on: [push, pull_request]
jobs:
 ci:
 uses: platform-org/platform-workflows/.github/workflows/app-ci.yml@v2
 with:
 image-name: payments
 # escape hatch intentionally NOT set -> integration tests run (safe default)
 secrets: inherit
```

And the product-shaped details that make it more than a shared file:

```text
- v2 is a MOVING major tag: consumers get non-breaking fixes automatically.
- app-ci@v1 still exists, prints a deprecation warning + migration link, sunsets 2025-12.
- The template emits `::notice::` telemetry on every run -> adoption dashboard.
- `skip-integration-tests: true` is possible, off by default, and `::warning::`-logged.
```

You'll build exactly this template and consumer in the lab, including the escape hatch
and the adoption-telemetry line.

### 6. Production considerations

- **Treat breaking changes as events.** Announce, provide a migration guide, open bump
 PRs, set a sunset date — and hold it. Surprise breakage destroys trust in the platform.
- **Enforce by provenance where you can.** Admitting only platform-signed images to prod
 is stronger and less annoying than policing how teams write YAML.
- **Instrument the template.** Emit per-run telemetry (service, version, hatch usage) so
 adoption and exceptions are dashboards, not guesses.
- **Make the hatch a feedback loop.** A frequently-used escape hatch is a bug report
 about your defaults — change the template, don't just tolerate the workaround.
- **Support it like a product.** Docs, a support channel, office hours, and a changelog.
 "Knowledge and support" are in the platform definition for a reason.
- **Version the template's own CI.** Test the template against canary consumers before
 moving the major tag; a broken `v2` breaks everyone at once.

### 7. Common mistakes

- **Mandating the template with no escape hatch** — teams fork it or route around it,
 and you lose visibility entirely. *Fix:* opinionated defaults plus visible, audited
 hatches.
- **Breaking consumers by editing in place** — changing `v2`'s behavior under everyone.
 *Fix:* semantic versions; breaking change → new major; deprecate the old one.
- **Enforcing keystrokes, not outcomes** — requiring a specific YAML shape teams can fake.
 *Fix:* enforce the outcome (signed, scanned artifact admitted to prod).
- **No adoption metric** — you can't tell if the product succeeded. *Fix:* measure % of
 prod services on the golden path and the escape-hatch rate.
- **Ignoring migration cost** — shipping `v2` with no guide or bump PRs; adoption stalls.
 *Fix:* migration guides, codemods/bots, and generous sunset windows.
- **Hiding the hatch instead of counting it** — an undocumented override everyone shares
 in Slack. *Fix:* make it a typed input that logs and reports.

### 8. Assessment

**Knowledge checks**

1. Why should the platform team *own* the pipeline template rather than each app team
 writing its own?
2. What is the difference between enforcing the *outcome* and enforcing the *keystrokes*,
 and why does provenance-based enforcement avoid gatekeeping?
3. How do you ship a breaking change to a template that has 50 consumers?
4. Give two properties a good escape hatch must have.
5. Name two adoption metrics and what a spike in escape-hatch usage tells you.

**Concept exercise**

> Explain why a pipeline template is a *product* **without using the words "pipeline,"
> "CI," or "YAML."** Describe who the customers are, what they consume, and how you'd know
> it succeeded.

**Trade-off / debugging exercise**

> Adoption of your `app-ci` template is stuck at 40%. Investigating, you find: teams on
> `v1` won't move because `v2` broke an input with no migration guide; three teams forked
> the template to skip a slow test because there's no supported way to; and you have no
> dashboard, so you only learned this by asking around. Diagnose each problem in
> product-management terms and give the fix.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** Ownership turns advice into guarantees — the platform can ensure every prod
 image is scanned and signed, and improve all consumers with one release, instead of
 hoping each of N hand-rolled pipelines does the right thing.
- **Q2:** Outcome enforcement checks the *result* (a signed, scanned, admissible
 artifact); keystroke enforcement checks the *form* (a specific YAML), which teams can
 satisfy without the substance. Provenance (only platform-signed images reach prod) means
 the paved road is the only path that works, so you don't gatekeep *how* teams build.
- **Q3:** Cut a new major (`v2`), keep `v1` working with a deprecation warning and sunset
 date, publish a migration guide, and ideally open bump PRs for consumers.
- **Q4:** Default-off and visible/auditable (typed input, logged, counted) — plus
 ideally an approval path for higher-stakes exceptions.
- **Q5:** % of prod services on the golden path and time-to-adopt a new version; a spike
 in hatch usage means your default is wrong and the template should change.
- **Debugging:** (1) Breaking change without migration path → add a guide + bump PRs, and
 next time deprecate rather than break. (2) Forks to skip a test → add a supported,
 default-off escape hatch and track it. (3) No dashboard → instrument the template with
 per-run telemetry so adoption and exceptions are visible.

</details>


_Previous:_ Reusable Workflows and Composite Actions · _Next:_ Container Build Pipelines

## Container Build Pipelines

> This is the pipeline the whole course has been pointing at: the one that turns
> source code into a **signed, scanned, immutable** container image that production
> will trust. You'll assemble the full arc — `lint → test → build → scan → sign →
> push` — with layer caching, multi-arch builds, a vulnerability **gate**, an SBOM,
> **keyless** signing with Cosign, and promotion by **digest**. This is the engine of
> Project 1.

[Trivy](https://trivy.dev/). Cosign is installed in the lab. The core lab is local/free.

### 1. Concept

#### The pipeline arc, and why the order is the lesson

```text
lint → test → build → scan → sign → push
 │ │ │ │ │ └ publish the exact artifact you just vouched for
 │ │ │ │ └ cryptographically attest "this pipeline built this digest"
 │ │ │ └ GATE: block if the image has critical, fixable CVEs
 │ │ └ produce an immutable image + its digest
 │ └ fail fast on logic errors before the expensive build
 └ cheapest checks first (Dockerfile lint, formatting)
```

The order encodes the failure philosophy from cheap, decisive checks
first; the **scan is a gate** that runs *before* you sign or push, so a vulnerable
image can't be blessed; and you **sign then push** the *same* artifact you scanned.
Signing a different image than you scanned would defeat the whole point.

#### Caching: don't rebuild the world every time

A cold container build re-downloads base layers and re-runs every step. **Layer
caching** reuses unchanged layers across runs. Two common backends in CI:

- **GitHub Actions cache** (`cache-from/to: type=gha`) — convenient, scoped to the repo.
- **Registry cache** (`type=registry,ref=…`) — shared across runners and repos, better
 for an org-wide base image.

Combined with Buildx, caching turns multi-minute builds into seconds when only your
app layer changed — which matters a lot when every team's pipeline runs this.

#### Multi-arch: build for every CPU your fleet runs

Clusters increasingly mix `amd64` and `arm64` (Graviton, Ampere, Apple silicon dev
machines). You build **both** from one pipeline using Buildx + QEMU emulation, and push
a **multi-arch manifest** — a single tag that resolves to the right architecture per
node. One image reference, correct everywhere.

#### The vulnerability gate

 taught scanning; here it becomes a **gate**. Trivy compares the image's
packages against CVE databases; `--exit-code 1 --severity CRITICAL` makes a critical,
fixable finding **fail the build** so the image is never signed or pushed. Use
`--ignore-unfixed` so you block on things you can actually fix, not noise you can't.

#### SBOM: a bill of materials you can query later

A **Software Bill of Materials** lists every package and version in the image. Generate
it in the pipeline (Trivy or Syft, CycloneDX/SPDX format), keep it as an **artifact**,
and **attest** it to the image. When the next Log4Shell drops, "are we affected?"
becomes a query against stored SBOMs instead of a frantic week of archaeology.

#### Keyless signing with Cosign

How does production know an image came from *your* pipeline and not an attacker's
laptop? You **sign** it. The old way needs a private key you must store and rotate — the
same long-lived-secret problem as cloud auth. **Keyless Cosign** removes the key
entirely, using the OIDC identity from 

```text
1. The runner requests an OIDC token (id-token: write): "I am repo X, workflow Y."
2. Cosign gets a SHORT-LIVED certificate from Fulcio bound to that identity.
3. Cosign signs the image's DIGEST with that ephemeral key and logs it to Rekor
 (a public transparency log) — then the key is thrown away.
4. Verifiers check the signature + certificate identity + issuer. No key was stored.
```

You verify with the *expected identity*: "only images signed by
`repo = platform-org/service-*, issuer = GitHub Actions` may run in production"
(enforced by policy in ). No key to leak, and the signature is tied to exactly
*which workflow in which repo* produced the image.

#### Promotion by digest, not tag

A tag like `:latest` or `:v1.2` is **mutable** — it can be re-pointed at new bytes. A
**digest** (`@sha256:…`) names the *exact content* and cannot change. So you **promote
the same image across environments by digest**: build and scan once in dev, and move
*that digest* to staging and production. You never rebuild per environment (a rebuild is
a different image you didn't scan). Immutable promotion is how "what we tested is what we
ship" becomes literally true.

```text
build once ─► ghcr.io/org/app@sha256:abc… (scanned, signed)
 │ promote the SAME digest, unchanged
 dev ───────┼──────── staging ──────── production
 (tag:dev) (tag:staging) (tag:prod) ← tags are just pointers;
 the digest is the truth
```

---

### 2. Why it matters for platform engineering

This pipeline is where the platform *keeps its security promises mechanically*. "Every
production image is scanned, has an SBOM, and is signed by our pipeline" is only true if
a pipeline every image must pass makes it true. Bake the gate, SBOM, and signature into
the golden-path template and every team gets them by default — structural
security, not a checklist someone might skip.

Keyless signing plus digest promotion close the supply-chain loop. Signing binds an
image to the exact workflow that built it; digest promotion guarantees the bytes you
scanned are the bytes that run; and verification at the deployment gate means a
hand-built or tampered image simply can't reach production. That chain — build → scan →
sign → verify → admit — is the backbone of Project 1 and a cornerstone of SLSA-style
supply-chain integrity.

### 3. Mental model

```text
 CONTAINER BUILD PIPELINE — trust, assembled step by step
 ───────────────────────────────────────────────────────

 source ─► [lint] ─► [test] ─► [BUILD]──────────► image + DIGEST (immutable id)
 Buildx │
 multi-arch ├─► [SCAN] Trivy ──► CRITICAL? ──► ✗ fail (gate)
 cache: gha/reg │ else ▼
 ├─► [SBOM] CycloneDX ─► artifact + attestation
 ▼
 [SIGN] Cosign keyless (OIDC → Fulcio → Rekor)
 ▼
 [PUSH] the SAME digest you scanned & signed
 ▼
 promote by DIGEST: dev ──► staging ──► production (verify signature at the gate)

 One line: build once, scan as a gate, sign keylessly, and promote the immutable
 digest everywhere — so what you tested is provably what you run.
```

### 4. Minimal implementation

Before the full workflow, feel each trust step by hand, locally and free. First, the
**gate** — a scan that *fails* on a critical finding (exactly what CI will do):

```bash
# Build your image, then gate on it. A non-zero exit = the build should stop.
docker build -t app:dev.
trivy image --exit-code 1 --severity CRITICAL --ignore-unfixed app:dev
echo "exit code was: $?" # 0 = clean (proceed), 1 = blocked (never sign/push)
```

Then an **SBOM** you could query later:

```bash
trivy image --format cyclonedx --output sbom.cdx.json app:dev
```

Then the idea of a **signature** (here with a local key to see the shape; CI is keyless):

```bash
cosign generate-key-pair # local demo only
cosign sign-blob --key cosign.key sbom.cdx.json > sbom.sig
cosign verify-blob --key cosign.pub --signature sbom.sig sbom.cdx.json # -> Verified OK
```

In CI there is **no `cosign.key`** — the identity comes from OIDC and the key is
ephemeral. The lab builds the full keyless, digest-promoting workflow; here you've seen
that each step is just "produce the artifact, prove something about it, carry the proof."

### 6. Production considerations

- **Scan continuously, not just at build.** New CVEs land daily; re-scan images already
 in registries and alert, don't only gate at build time.
- **Gate on fixable criticals; triage the rest.** Block on `CRITICAL` + fixable to stay
 actionable; track unfixable/high findings without halting every build.
- **Pin and rebuild base images.** Track base-image digests; rebuild on disclosures.
 Minimal/distroless bases make this cheap.
- **Verify signatures at admission.** Signing is only half the value — enforce
 "verify by expected identity" at the deployment gate (Kyverno/Cosign policy, ).
- **Promote by digest, always.** Never let an environment rebuild; move the signed digest.
 Tags are human conveniences layered on top.
- **Cache safely.** Caches speed builds but can poison them if shared across trust
 boundaries; scope caches per repo/base and don't cache secrets.
- **Keep SBOMs and provenance.** Store them as attestations so audits and CVE hunts are
 queries, not excavations.

### 7. Common mistakes

- **Scanning *after* pushing (or not gating)** — the vulnerable image is already
 published. *Fix:* scan before sign/push and make it a gate (`--exit-code 1`).
- **Signing a tag, then pushing a different build** — the signature doesn't cover what
 ran. *Fix:* sign and promote by **digest**, the immutable identity.
- **Storing a Cosign private key as a secret** — the long-lived-key problem again.
 *Fix:* keyless signing via OIDC (`id-token: write`), no stored key.
- **Rebuilding per environment** — "staging" and "prod" are now different, unscanned
 images. *Fix:* build once; promote the same digest.
- **Gating on every severity including unfixable** — builds fail on noise nobody can fix,
 so teams disable the gate. *Fix:* `--ignore-unfixed`, block on critical/fixable.
- **No multi-arch, then `exec format error` on arm64 nodes** — amd64-only image on an
 arm64 node. *Fix:* build `linux/amd64,linux/arm64` and push a manifest.
- **No SBOM** — a new CVE turns into a week of "which images even contain this?" *Fix:*
 generate and attest an SBOM every build.

### 8. Assessment

**Knowledge checks**

1. Why must the scan run *before* sign and push, and why is `--exit-code 1` essential?
2. What does keyless Cosign replace, and where does the signing identity come from?
3. Why promote by digest instead of by tag across environments?
4. What is an SBOM and what future problem does storing one solve?
5. How do you build an image that runs on both `amd64` and `arm64` nodes from one
 pipeline?

**Concept exercise**

> Explain how production can be sure an image came from the official pipeline and hasn't
> been tampered with — **without using the words "sign," "key," or "Cosign."** Describe
> what is produced, what is checked, and what makes it trustworthy.

**Trade-off / debugging exercise**

> A team's pipeline builds `app:latest`, pushes it, *then* scans `app:latest`, and signs
> `app:latest` in a separate later job. Production pulls `app:latest`. Identify three ways
> this can ship an unsafe or wrong image to production, and the specific change that fixes
> each.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** So a vulnerable image is never blessed or published; the scan must be able to
 **fail the build** (`--exit-code 1`), otherwise it's advisory and the pipeline proceeds
 anyway (a silent skip).
- **Q2:** It replaces a stored private signing key. The identity comes from the workflow's
 OIDC token (repo + workflow), which Fulcio binds to a short-lived certificate; the
 signature is recorded in Rekor.
- **Q3:** A digest names exact bytes and is immutable; a tag can be re-pointed. Promoting
 by digest guarantees staging/prod run exactly what you scanned and signed.
- **Q4:** A list of every package/version in the image; stored SBOMs turn "are we exposed
 to CVE-X?" into a fast query instead of re-scanning or guessing.
- **Q5:** Use Buildx with QEMU to build `linux/amd64,linux/arm64` and push a multi-arch
 manifest that resolves per node.
- **Debugging:** (1) Push-before-scan publishes a bad image → scan before push as a gate.
 (2) `:latest` is mutable, so the scanned/signed image may differ from what prod pulls →
 promote by digest. (3) Signing in a separate later job on a tag doesn't bind to the
 scanned build → sign the digest in the same job, immediately after the gate.

</details>


_Previous:_ Pipeline Templates as a Platform Product · _Next:_ IaC Pipelines

## IaC Pipelines

> Infrastructure is the highest-stakes thing a platform changes: an `apply` can resize a
> cluster, rewrite a firewall rule, or delete a database. This module builds the pipeline
> that makes those changes **safe and reviewable** — plan on every pull request, apply on
> merge behind environment gates, detect drift on a schedule, and authenticate with a
> **least-privilege, keyless** identity. This is the `plan → review → apply` engine behind
> Project 2's promotion-by-PR.

[Terraform](https://developer.hashicorp.com/terraform/install). The core lab is local/free.

### 1. Concept

#### The plan is the review artifact

Terraform's superpower is that `plan` shows *exactly* what will change before anything
happens. An IaC pipeline turns that into a review ritual: on every pull request, run
`plan` and **post the output as a PR comment**, so a human reviews the concrete diff —
"this will replace the database" — not just the HCL. The plan, attached to the PR, is the
thing reviewers approve.

```text
PR opened ─► fmt ─► validate ─► tfsec/checkov ─► PLAN ─► comment the plan on the PR
 (cheap, decisive first; the plan is what humans actually review)
```

#### Apply on merge, gated per environment

Once reviewers approve and the PR merges, the pipeline **applies**. But not all
environments are equal, so you gate them differently using **GitHub Environments**:

- **dev** — apply **automatically** on merge. Fast feedback; low blast radius.
- **staging / production** — apply behind a **required reviewer** (and optionally a wait
 timer and `main`-only deployment branches). The job *pauses* until a human approves.

```text
merge to main ─► apply(dev) ──auto──► apply(staging) ──gate──► apply(production) ──gate──►
 low risk required reviewer required reviewer, main-only
```

This is the mechanical version of "platform changes need stronger review than app
changes" from the gate is enforced by the platform, not by politeness.

#### Drift detection: reality vs code

Code says one thing; someone clicked something in the console; now they disagree. That's
**drift**, and it's silent until an incident. Detect it with a **scheduled** workflow: run
`terraform plan` nightly against production. A truly reconciled environment produces an
**empty** plan. `terraform plan -detailed-exitcode` returns `0` for no changes and `2` for
a non-empty plan — so a non-empty plan can **fail the job loudly** and alert you.

```text
nightly: terraform plan -detailed-exitcode
 exit 0 → in sync (quiet)
 exit 2 → DRIFT → red build + alert (fail loud, )
```

#### State conflicts and locking

Terraform **state** is the source of truth it diffs against, and two applies touching it
at once will corrupt it. Two mechanisms keep CI safe:

- **State locking.** A remote backend (S3+DynamoDB, GCS, Terraform Cloud) takes a **lock**
 during `plan`/`apply`; a second run waits or fails rather than racing.
- **Concurrency groups.** A GitHub `concurrency` group keyed to the environment, with
 `cancel-in-progress: false`, ensures only one state-mutating run proceeds at a time and
 an in-flight apply is never cancelled mid-write.

Together they turn "two merges at once" from a corruption risk into an orderly queue.

#### Least-privilege, keyless credentials

An IaC pipeline holds the power to change infrastructure — so its credentials are the
highest-value target you own. Two rules:

- **Keyless (OIDC).** No stored cloud keys; the pipeline authenticates with a short-lived,
 scoped identity per run. Nothing durable to steal.
- **Least privilege per job.** The **plan** job needs only **read** access (it previews);
 only the **apply** job needs **write**. Bind separate cloud roles so a PR plan — which
 can run code from a fork — can never mutate anything.

```text
plan job → OIDC → read-only role (safe to run on PRs)
apply job → OIDC → write role (only after merge + environment gate)
```

#### Atlantis: the PR-native alternative

**Atlantis** is a self-hosted app that runs the whole flow *inside the PR*: it comments
the `plan` automatically, and you type `atlantis apply` in a PR comment to apply, with
approval rules enforced. It centralizes Terraform automation, locking, and policy for
many repos — appealing for larger orgs that want a single, consistent Terraform workflow
rather than a workflow file copied into every repo. The trade-off is operating another
service; GitHub Actions needs nothing extra to run. Same concepts either way: plan on PR,
gated apply, locking.

---

### 2. Why it matters for platform engineering

Infrastructure changes are where a platform team can do the most damage and the most good.
This pipeline makes the damage *hard* and the good *routine*: every change is previewed and
reviewed as a concrete plan, applied behind gates that match blast radius, and watched for
drift so the platform's "infrastructure is code" claim stays true instead of quietly
rotting. Least-privilege keyless credentials mean the most dangerous automation you run
also has the smallest standing attack surface.

It's also the final piece of the course's throughline. Project 2 promotes changes by
**pull request into a config repository**: you open a PR, the pipeline plans and shows the
diff, reviewers approve, merge applies behind a gate — and in a GitOps controller
reconciles the result. The `plan → review → apply` loop you build here is exactly that
promotion mechanism, and the same review-by-diff discipline carries straight into GitOps.

### 3. Mental model

```text
 IaC PIPELINE — plan to review, gated apply, watched for drift
 ────────────────────────────────────────────────────────────

 PULL REQUEST ─► fmt ─► validate ─► tfsec ─► PLAN ─► 💬 comment plan on PR
 (read-only OIDC role — safe even for fork PRs) │ humans review the DIFF
 ▼
 MERGE to main ─► apply(dev) ──auto──► apply(staging) ──[gate]──► apply(prod) ──[gate]──►
 (write OIDC role) low blast radius required reviewer required reviewer, main-only
 │ state lock + concurrency(group=env, cancel-in-progress:false)
 ▼
 NIGHTLY ─► plan -detailed-exitcode ─► exit 2? ─► DRIFT → red + alert (fail loud)

 One line: the plan is the review; gates match blast radius; state is locked; drift is
 caught on a schedule; and credentials are keyless and least-privilege.
```

### 4. Minimal implementation

Feel the review loop locally, with no cloud — the `local` provider makes `plan`/`apply`
real and free:

```bash
terraform init # downloads the provider (no cloud account needed)
terraform fmt -check # cheap, decisive — fails fast on formatting
terraform validate
terraform plan -out tfplan # the artifact a reviewer would read
```

The two ideas the pipeline automates are visible already — the **plan as review artifact**
and **drift as a non-empty plan**:

```bash
terraform apply tfplan # apply the EXACT plan you reviewed (no surprises)

# Later, detect drift: a reconciled workspace plans empty; a changed one exits 2.
terraform plan -detailed-exitcode
echo "exit $? # 0 = in sync, 2 = DRIFT (alert), 1 = error"
```

Notice you `apply` the *saved* plan, not a fresh one — so what's applied is exactly what
was reviewed. In the lab you wrap this in a workflow that plans on PRs, comments the diff,
applies on merge behind an environment gate, and runs the drift check nightly.

### 6. Production considerations

- **Apply the saved plan.** Pass the `plan` artifact to `apply` so you apply exactly what
 was reviewed; re-planning at apply time can pick up changes nobody saw.
- **Remote state with locking.** Use a locking backend (S3+DynamoDB, GCS, TF Cloud);
 never keep state local or unlocked in CI.
- **Separate roles for plan vs apply.** Read-only for plan (PR-safe), write for apply.
 Never let a fork PR's plan job hold write credentials.
- **Gate by environment and blast radius.** Auto for dev; required reviewers (and
 `main`-only, wait timers) for staging/prod.
- **Drift is an alert, not a log line.** Route the nightly non-empty plan to a channel a
 human watches; decide whether to reconcile or codify the change.
- **Scope the scan gates sensibly.** `tfsec`/`checkov` should block on real misconfig; curate
 exceptions explicitly rather than disabling the gate.
- **Consider Atlantis at scale.** If you're copying the same workflow into dozens of repos,
 a central Terraform automation service may be worth operating.

### 7. Common mistakes

- **Applying without reviewing a plan** — merge straight to `apply`, surprises in prod.
 *Fix:* plan on PR, comment it, require approval; apply the saved plan.
- **Plan job with write credentials** — a fork PR can run code with mutate rights.
 *Fix:* read-only role for plan; write only for apply after merge + gate.
- **No state locking / no concurrency group** — two applies corrupt state. *Fix:* locking
 backend plus `concurrency` keyed to the environment, `cancel-in-progress: false`.
- **Stored cloud keys in secrets** — long-lived, high-privilege, leakable. *Fix:* keyless
 OIDC with least-privilege roles.
- **No drift detection** — console changes diverge silently for weeks. *Fix:* a scheduled
 `plan -detailed-exitcode` that fails loud on exit 2.
- **Same gate for dev and prod** — either dev is annoyingly slow or prod is dangerously
 open. *Fix:* auto for dev, required reviewers for prod.
- **Ignoring `apply` failures mid-change** — partial apply leaves infra inconsistent.
 *Fix:* locking, retries with the same plan, and alerting; never swallow the error.

### 8. Assessment

**Knowledge checks**

1. Why post the `terraform plan` output as a PR comment instead of just running it?
2. How do you gate dev vs production applies differently, and with what mechanism?
3. What does `terraform plan -detailed-exitcode` return, and how do you use it for drift?
4. Why should the plan job and the apply job have *different* cloud permissions?
5. What two mechanisms prevent two CI applies from corrupting state?

**Concept exercise**

> Explain how a team safely changes shared infrastructure through code review **without
> using the words "Terraform," "plan," or "apply."** Describe what a reviewer sees, what
> happens on approval, and how you'd notice if reality later drifted from the agreed state.

**Trade-off / debugging exercise**

> An IaC pipeline stores a cloud admin key as a secret and uses it for both the PR plan
> job and the merge apply job. There's no environment gate (prod applies automatically on
> merge), no state locking, and no scheduled plan. A contributor opens a PR from a fork, and
> two PRs merge within the same minute. List four things that can go wrong and the specific
> fix for each.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** So a human reviews the concrete diff (what will actually change) attached to the
 PR, not just the HCL — the plan is the review artifact.
- **Q2:** dev applies automatically on merge; staging/production use a GitHub Environment
 with required reviewers (and optionally wait timers and `main`-only deployment branches)
 so the job pauses for approval.
- **Q3:** `0` = no changes, `2` = non-empty plan (drift), `1` = error. Run it on a schedule
 and fail loud / alert on exit `2`.
- **Q4:** Plan only previews, so it needs read-only — and PR plan jobs can run untrusted
 fork code; only apply needs write. Splitting roles stops a PR from mutating anything.
- **Q5:** A locking remote backend (one writer at a time) and a GitHub `concurrency` group
 keyed to the environment with `cancel-in-progress: false`.
- **Debugging:** (1) Admin key as a secret → keyless OIDC, least privilege. (2) Same role
 for plan and apply + fork PR → read-only plan role, write only on apply. (3) Auto prod
 apply → environment gate with required reviewers. (4) Two simultaneous merges, no locking
 → locking backend + concurrency group; add the nightly drift plan too.

</details>


_Previous:_ Container Build Pipelines · _Next:_ Kubernetes Package Management
