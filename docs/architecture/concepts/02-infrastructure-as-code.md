# 02 · Infrastructure as Code

> **Project Applicability:** Active in Project

> Up to now your platform has run on clusters and containers *someone clicked into
> existence*. That doesn't scale, isn't reproducible, and can't be reviewed. This
> phase replaces the clicking with **code**: infrastructure you can version, review,
> test, and apply the same way every time. It's the mechanism that turns "it works
> on my cluster" into "it works in every environment, on demand."

### Why this phase?

A platform is only as reliable as the way its infrastructure is created. If your
staging and production environments were built by hand, they have silently drifted
apart, nobody can recreate them after a disaster, and every change is a risk because
there is no plan to review and no record of what happened.

**Infrastructure as Code (IaC)** fixes this at the root. You describe the desired
state of your infrastructure — clusters, networks, buckets, databases, IAM — in
files that live in Git. A tool reconciles reality to match. The result is
infrastructure that is **reproducible, reviewable, testable, and self-documenting**.

This phase is also where the platform team earns much of its leverage. The reusable
Terraform modules and Crossplane abstractions you build here become the paved road
that every other team consumes: a product team asks for a database with ten lines of
YAML instead of a two-week ticket queue. That is platform engineering in action.

We teach the **problem before the tool** throughout:

- **State and idempotency** — what they are and why any IaC tool needs them —
 *before* a single `terraform apply`.
- **Drift** — why reality diverges from code and how to detect it.
- **Modules and composition** — the DRY, versioned building blocks of a real IaC
 codebase, not copy-pasted HCL.
- **Testing and policy** — security scanning, policy-as-code, and Go integration
 tests, because unreviewed infrastructure is a liability.

## IaC Principles

> Before any Terraform, you need to understand the *ideas* every IaC tool
> implements: describing infrastructure as **declarative code in version control**,
> making changes **idempotent**, tracking **state**, and detecting **drift**. This
> module builds those concepts from first principles — you'll even write a tiny
> idempotent "reconciler" by hand — so that Terraform later feels obvious rather
> than magical.

### 1. Concept

#### What Infrastructure as Code actually means

**Infrastructure as Code (IaC)** is the practice of describing your infrastructure —
servers, clusters, networks, load balancers, buckets, databases, DNS records, IAM
policies — in **machine-readable files kept under version control**, and using a
tool to create and change that infrastructure from those files instead of by hand.

The "in version control" half is not a detail; it is the point. The moment your
infrastructure lives in Git you gain the things the clicking approach can never
give you:

- **Review** — a change is a pull request, not an untracked console action.
- **History** — `git log` tells you who changed what, when, and why.
- **Reproducibility** — the same files produce the same environment, every time.
- **Rollback** — revert the commit, re-apply, and you are back.
- **Collaboration** — many engineers change infrastructure without stepping on
 each other.

#### Declarative vs imperative

There are two ways to tell a computer to get infrastructure into a certain shape.

**Imperative** means you specify the *steps*: "create a VPC, then create a subnet,
then create a cluster, then attach a node pool." A shell script full of `gcloud` or
`aws` commands is imperative. It works — once. Run it again and it fails because the
VPC already exists, or it creates a duplicate.

**Declarative** means you specify the *desired end state*: "I want a VPC, a subnet,
a cluster, and a node pool, configured like this." The tool figures out what to
create, change, or delete to make reality match. Run it again and — if nothing
changed — it does nothing.

```text
IMPERATIVE "Do these steps." → you own the HOW and the ordering
DECLARATIVE "This is what should exist." → the tool owns the HOW; you own the WHAT
```

Platform engineering overwhelmingly prefers **declarative** IaC because the desired
state is reviewable, diffable, and safe to apply repeatedly. You describe the
destination, not the turn-by-turn directions.

#### Idempotency: the property that makes it safe

An operation is **idempotent** if applying it many times has the same effect as
applying it once. "Set the thermostat to 20°C" is idempotent — do it ten times, the
room is still 20°C. "Raise the thermostat by one degree" is **not** idempotent — do
it ten times and you are sweating.

Idempotency is what lets you run the same IaC repeatedly without fear. The tool
inspects what exists, compares it to the desired state, and only acts on the
difference. This is why a second `apply` with no changes is a safe no-op — the
cornerstone of trustworthy automation.

#### State: how the tool knows what it manages

To compute the difference between *desired* and *actual*, a tool needs to know which
real-world resources it is responsible for. It keeps a record called **state**:
essentially a mapping from the resources in your code to the real resource
identifiers in the cloud.

```text
desired state (your code) state file (the map) real world (the cloud)
 resource "bucket" "logs" ─▶ logs = projects/x/bucket/42 ─▶ an actual GCS bucket
```

Without state, the tool cannot tell the difference between "this bucket does not
exist yet, create it" and "I already created this bucket, leave it alone." State is
the memory that makes reconciliation possible — and, as you'll see in,
managing it well is a whole discipline.

#### Drift: when reality wanders off

**Drift** is any divergence between what your code says *should* exist and what
*actually* exists. Someone opens the cloud console at 2am during an incident and
bumps a node count; a different tool edits a firewall rule; a resource is deleted by
hand. Now production no longer matches its definition.

Drift is dangerous because it is invisible until it bites: your next `apply` tries
to "fix" the manual change (reverting an emergency hotfix), or your code no longer
describes what is really running. Detecting and reconciling drift is a core platform
responsibility.

---

### 2. Why it matters for platform engineering

IaC is the substrate the rest of your platform stands on:

- **Reproducibility is the product.** A platform promises teams a consistent,
 paved-road environment. You cannot deliver "consistent" from hand-built
 infrastructure that drifted apart months ago.
- **Review and governance become possible.** "No manual console changes; every
 change is a reviewed PR" is only enforceable when infrastructure *is* code.
- **Disaster recovery stops being a prayer.** If an environment is fully described
 in code, recreating it after a loss is an `apply`, not a two-week archaeology
 project.
- **Leverage.** Reusable IaC modules let a small platform team stamp out correct,
 secure infrastructure for dozens of product teams on demand — the economic case
 for the whole discipline.
- **It is the foundation for GitOps and self-service.** Later phases (GitOps,
 Crossplane) all assume desired state lives in Git. IaC principles are what make
 that work.

Without IaC, every later capability — golden paths, self-service environments,
drift-free production — is impossible.

---

### 3. Mental model

Hold this model: **IaC is a control loop around desired state.**

```text
 ┌──────────────────────────────────────────────────┐
 │ │
 ┌────────▼─────────┐ compare ┌──────────────────┐ │
 │ DESIRED STATE │─────────────▶│ DIFF (plan): │ │
 │ (code in Git) │ │ create/change/ │ │
 └────────▲─────────┘ │ destroy │ │
 │ └─────────┬────────┘ │
 │ │ apply │
 ┌────────┴─────────┐ ┌─────────▼────────┐ │
 │ STATE (map of │◀─────────────│ REAL WORLD │───────┘
 │ managed things) │ refresh │ (the cloud) │ drift pushes
 └──────────────────┘ └──────────────────┘ real ≠ desired
```

Three rules worth remembering a year from now:

1. **You edit desired state, never the real world directly.** The console is
 read-only in your mind.
2. **The tool reconciles; you review the plan.** Never apply a diff you don't
 understand.
3. **State is precious.** Lose it or corrupt it and the tool forgets what it owns.

---

### 4. Minimal implementation

Let's prove the core ideas without Terraform. We'll manage one "resource" — a
directory that should contain exactly a set of files — with a hand-written,
**idempotent, declarative, stateful** reconciler.

The *desired state* is a list. The *state* is what currently exists. The script
computes a *diff* and applies only the difference.

```bash
#!/usr/bin/env bash
set -euo pipefail

# --- desired state (this is our "code") ---
desired=("app.conf" "db.conf" "cache.conf")
target_dir="./managed"

mkdir -p "$target_dir"

# --- refresh: read the real world into "current state" ---
mapfile -t current < <(cd "$target_dir" && ls -1 2>/dev/null || true)

# --- plan + apply: create what's missing ---
for f in "${desired[@]}"; do
 if [[ ! -f "$target_dir/$f" ]]; then
 echo "+ create $f"
 touch "$target_dir/$f"
 fi
done

# --- plan + apply: destroy what's no longer desired ---
for f in "${current[@]}"; do
 if [[ ! " ${desired[*]} " == *" $f "* ]]; then
 echo "- destroy $f"
 rm -f "$target_dir/$f"
 fi
done

echo "converged. desired = ${desired[*]}"
```

Run it once and it creates three files. Run it again — **it prints nothing to
create or destroy**. That is idempotency. Delete `db.conf` by hand (that's *drift*)
and run again: it re-creates exactly the missing file. Add `cache.conf` to the
desired list and remove `app.conf`: the next run creates one and destroys the other.

You just built, from first principles, the exact loop Terraform runs: **refresh →
diff (plan) → apply**, acting only on the difference. Terraform adds a real state
file, a dependency graph, and thousands of providers — but the idea is this script.

---

### 6. Production considerations

- **State is a single point of truth — protect it.** In real IaC, losing state
 means the tool no longer knows what it owns. Production state is stored remotely,
 locked, versioned, and backed up.
- **Drift detection must be continuous.** Manual changes *will* happen during
 incidents. A scheduled job that runs a read-only `plan` and alerts on drift is
 standard platform hygiene.
- **IaC and configuration management are complementary, not rivals.** IaC
 (Terraform, OpenTofu, Crossplane) provisions *infrastructure* — the cluster, the
 network, the bucket. Configuration management (Ansible, Chef, Puppet) configures
 *inside* already-running machines — packages, files, services. Many platforms use
 IaC to create the fleet and config management (or, increasingly, immutable images
 and Kubernetes) to configure it. Know which problem you're solving.
- **Immutability beats mutation.** Prefer replacing resources (new image, new
 instance) over mutating them in place. It eliminates a class of drift and
 configuration rot.
- **Everything through the pipeline.** In production, humans don't run `apply` from
 laptops; CI does, with review gates. This is both a safety and an audit control.

### 7. Common mistakes

- **Treating IaC as a one-time bootstrap.** Writing code to stand up an environment,
 then editing it by hand forever after. *Why:* the console is faster in the moment.
 *Fix:* make code the *only* way infrastructure changes; forbid manual edits and
 detect drift.
- **Imperative scripts masquerading as IaC.** A pile of `gcloud create …` commands
 in a repo is version-controlled, but it isn't idempotent or declarative — re-runs
 break or duplicate. *Fix:* describe desired state; let a declarative tool
 reconcile.
- **Ignoring state.** Deleting, hand-editing, or not backing up the state file.
 *Why:* it looks like "just a file." *Fix:* treat state as production data —
 remote, locked, versioned.
- **Pretending drift won't happen.** Assuming nobody will ever touch the console.
 *Why:* incidents create pressure to click. *Fix:* expect drift; detect it on a
 schedule and reconcile deliberately.
- **Using IaC for genuinely one-off exploration.** Writing a module to spin up a
 throwaway spike you'll delete in an hour. *Fix:* for true one-offs and
 prototypes, a quick manual action or script is fine — IaC's payoff is
 *repetition* and *longevity*.

### 8. Assessment

**Knowledge checks**

1. Why is "in version control" essential to the definition of IaC, not an optional
 extra?
2. Give one everyday example each of an idempotent and a non-idempotent action.
3. What is the state file for, and what breaks if it's lost?
4. What is drift, and why is it dangerous even when the manual change "worked"?
5. Name a situation where IaC is *not* the right choice.

**Concept exercise**

> Explain idempotency and declarative desired state **without using the words
> "Terraform," "apply," or "state."** Use an analogy a non-engineer would get.

**Debugging / trade-off exercise**

> During an incident, an on-call engineer manually scales a node pool from 3 to 10
> nodes in the cloud console to absorb load, and it resolves the incident. The IaC
> code still says `3`. Walk through what happens on the *next* `apply`, why that's a
> problem, and two different ways a mature platform team should handle this — one
> process change and one technical control.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** Version control is what gives IaC its value — review, history,
 reproducibility, rollback, collaboration. A declarative file that only ever lives
 on one laptop is just a fancier manual process; the "code" part means *managed
 like code*.
- **Q2:** Idempotent: "set the volume to 5," "ensure this file exists." Non-idempotent:
 "turn the volume up by one," "append a line to this file."
- **Q3:** State maps your coded resources to real cloud resource IDs so the tool can
 diff desired vs actual. Lose it and the tool no longer knows what it owns — it may
 try to recreate everything (duplicates/conflicts) or refuse to manage existing
 resources.
- **Q4:** Drift is divergence between code and reality. Even a "working" manual
 change is dangerous because the next `apply` will try to revert it back to what
 the code says, and because your code no longer describes what's actually running —
 so reviews and recovery are based on a lie.
- **Q5:** A genuine one-off: a throwaway spike, a quick debugging VM you'll destroy
 in an hour, a true prototype. IaC's cost (writing, reviewing, maintaining)
 only pays off with repetition or longevity.
- **Debugging:** On the next `apply`, the tool sees desired=3, actual=10, and plans
 to *scale back to 3* — undoing the emergency fix, possibly re-triggering the
 incident. Process fix: codify the change (update the module to the new baseline,
 via PR) before the next apply, and treat emergency console changes as incidents
 that *must* be reconciled. Technical control: automated drift detection (a
 scheduled read-only plan that alerts), plus pipeline-only applies so a stray local
 `apply` can't silently revert prod.

</details>


_Previous:_ overview · _Next:_ Terraform Fundamentals →

## Terraform Fundamentals

> Terraform (and its open-source fork, OpenTofu) is the most widely used IaC tool in
> the industry. This module teaches its building blocks — providers, resources, data
> sources, variables, outputs, dependencies, and the `init → plan → apply → destroy`
> loop — and grounds them in the principles from. You'll read real GKE
> code and run a cost-free local project.

### 1. Concept

#### Terraform in one paragraph

Terraform reads `.tf` files written in **HCL** (HashiCorp Configuration Language),
builds a dependency graph of the resources you declared, compares that desired state
to the recorded **state** and the real world, and produces a **plan** of changes.
You review the plan; `apply` enacts it. It is the control loop from, made
industrial. **OpenTofu** is a drop-in open-source fork; nearly everything here
applies identically — swap `terraform` for `tofu`.

#### Visual model: Terraform lifecycle

See the Terraform lifecycle diagram for the full loop from plan through apply and state.

#### Providers: the plugins that talk to APIs

A **provider** is a plugin that knows how to manage a particular API — Google Cloud,
AWS, Azure, Kubernetes, Docker, GitHub, or local primitives like random values and
files. You declare which providers you need and Terraform downloads them during
`init`.

```hcl
terraform {
 required_version = ">= 1.6"
 required_providers {
 google = {
 source = "hashicorp/google"
 version = "~> 5.0"
 }
 }
}

provider "google" {
 project = var.project_id
 region = var.region
}
```

#### Resources: the things you manage

A **resource** block declares one piece of infrastructure. Its two labels are the
**type** (defined by a provider) and a **local name** (your handle for referencing
it). Here is the real GKE cluster from the outline — production-grade GCP code you'll
read now and run locally in a cheaper form later:

```hcl
resource "google_container_cluster" "platform" {
 name = "platform-cluster"
 location = var.region

 # Best practice: manage node pools separately, so remove the default one.
 remove_default_node_pool = true
 initial_node_count = 1

 release_channel {
 channel = "REGULAR"
 }
}

resource "google_container_node_pool" "primary" {
 name = "primary"
 cluster = google_container_cluster.platform.name
 location = var.region
 node_count = var.node_count

 node_config {
 machine_type = "e2-standard-4"
 oauth_scopes = ["https://www.googleapis.com/auth/cloud-platform"]
 }
}
```

#### Data sources: reading what you don't manage

A **data source** reads information about resources Terraform does *not* manage —
an existing network, the latest image, the current project. It's read-only input to
your configuration.

```hcl
data "google_compute_network" "existing" {
 name = "shared-vpc"
}

# reference it: data.google_compute_network.existing.id
```

#### Variables, locals, and outputs

- **Variables** (`variable`) are typed inputs — the knobs a caller sets.
- **Locals** (`locals`) are named expressions computed once and reused — DRY within
 a config.
- **Outputs** (`output`) expose values after apply, for humans or for other modules.

```hcl
variable "region" {
 type = string
 default = "europe-west1"
 description = "GCP region for regional resources."
}

locals {
 cluster_name = "platform-${var.environment}"
}

output "cluster_endpoint" {
 value = google_container_cluster.platform.endpoint
 description = "The cluster API endpoint."
 sensitive = true
}
```

#### Dependencies: implicit and explicit

Terraform doesn't apply resources top-to-bottom. It builds a **dependency graph** and
applies in the correct order, parallelizing where it can. Most dependencies are
**implicit**: when `google_container_node_pool.primary` references
`google_container_cluster.platform.name`, Terraform knows the cluster must exist
first. When there's a hidden ordering it can't infer, you add an **explicit**
`depends_on`.

#### The core workflow

```text
terraform init # download providers, set up the backend
terraform fmt # canonical formatting
terraform validate # syntax + internal consistency
terraform plan # show the diff — review this!
terraform apply # enact the plan
terraform show # inspect current state in detail
terraform destroy # tear it all down
```

#### Meta-arguments

Meta-arguments work on any resource:

- **`count`** — create N copies, indexed `[0]`, `[1]`, … Good for identical,
 order-numbered resources.
- **`for_each`** — create one per key in a map/set, indexed by key. Preferred when
 instances have stable identities (adding/removing one won't churn the others).
- **`depends_on`** — declare an explicit dependency Terraform can't infer.
- **`lifecycle`** — control behavior: `create_before_destroy`, `prevent_destroy`,
 `ignore_changes`.

```hcl
resource "google_storage_bucket" "env" {
 for_each = toset(["dev", "staging", "prod"])
 name = "acme-platform-${each.key}"
 location = var.region
}
```

`terraform_data` (and the older `null_resource`) hold local-only logic — a value to
trigger replacement, or a `provisioner` for a local command — without managing a real
cloud resource.

---

### 2. Why it matters for platform engineering

- **Terraform is the lingua franca.** Most organizations' infrastructure is already
 in Terraform/OpenTofu; fluency is table stakes for a platform engineer.
- **The plan is a safety and review artifact.** "Show me the plan" is how teams
 review infrastructure change before it happens — the review gate that makes
 governance real.
- **Providers unify a fragmented world.** One workflow and one language manage cloud,
 Kubernetes, DNS, SaaS, and more — you learn the loop once.
- **Variables + outputs are the seam** that will become reusable modules: typed inputs, published outputs. Learn them cleanly now.

---

### 3. Mental model

**Terraform is a compiler for infrastructure.** Your `.tf` files are the source; the
dependency graph is the intermediate representation; the plan is the compiler's "here
is what I'll change"; apply is the link-and-run.

```text
.tf files (HCL) state + real world plan (the diff) apply
 ─────────────── ────────────────── ─────────────── ─────
 desired state ──▶ refresh actual state ──▶ + create ──▶ enact,
 (what you wrote) (what exists now) ~ update update
 - destroy state
 ▲ │
 └───────────────────── you review the plan ◀──────────────────────┘
```

Rules to keep:

- **Never apply a plan you haven't read.** The plan is the contract.
- **References create order.** If B uses A's attribute, A comes first — no manual
 sequencing.
- **State is written by apply.** Guard it.

---

### 4. Minimal implementation

The smallest honest Terraform project needs no cloud account at all — the
`random` and `local` providers create real managed resources (a random value, a file
on disk) through the exact same loop you'll use for GKE.

```hcl
terraform {
 required_providers {
 random = { source = "hashicorp/random", version = "~> 3.6" }
 local = { source = "hashicorp/local", version = "~> 2.5" }
 }
}

resource "random_pet" "name" {
 length = 2
}

resource "local_file" "greeting" {
 filename = "${path.module}/hello.txt"
 content = "Hello from ${random_pet.name.id}\n"
}

output "service_name" {
 value = random_pet.name.id
}
```

```bash
terraform init # downloads the random + local providers
terraform plan # "+ 2 to add": a random_pet and a local_file
terraform apply -auto-approve
cat hello.txt # "Hello from <some-random-pet>"
terraform state list # random_pet.name, local_file.greeting
terraform apply # idempotent: "No changes."
terraform destroy -auto-approve
```

Notice: `local_file.greeting` implicitly depends on `random_pet.name` because its
`content` references the pet's `id`. You wrote no ordering — the graph did it. This
is the whole tool in miniature; GKE just swaps the providers.

---

### 6. Production considerations

- **Pin versions.** Pin `required_version` and provider versions (`~>`). An
 unpinned provider can change behavior under you. Commit the `.terraform.lock.hcl`
 lock file.
- **`plan` before `apply`, always.** In CI, save the plan (`-out=tfplan`) and apply
 *that exact plan*, so what was reviewed is what runs.
- **Prefer `for_each` over `count`.** With `count`, removing the 2nd of three items
 renumbers the 3rd and Terraform destroys/recreates it. `for_each` keys are stable.
- **Mark secrets `sensitive`.** Outputs and variables that carry secrets should set
 `sensitive = true` so they don't print in logs (it's not encryption, just
 redaction).
- **Keep providers least-privileged.** The credentials Terraform runs with can
 create and destroy infrastructure — scope them tightly and run from CI, not
 laptops.
- **OpenTofu is a first-class choice.** If licensing or governance favors fully open
 source, `tofu` is compatible; teams adopt it with minimal change.

### 7. Common mistakes

- **Using `count` for things with identities.** `count` indexes by position, so
 insertions/removals churn unrelated resources. *Fix:* use `for_each` keyed by a
 stable name.
- **Hardcoding values that vary by environment.** Region, project, sizes baked into
 resources. *Why:* it seemed simpler. *Fix:* lift them into typed `variable`s with
 sensible defaults.
- **Adding `depends_on` everywhere "to be safe."** Over-declaring dependencies
 serializes the graph and hides real relationships. *Fix:* rely on implicit
 references; use `depends_on` only for genuinely hidden ordering.
- **Editing resources in the console, then applying.** Terraform reverts your manual
 change. *Fix:* change the code; if you must `ignore_changes` for a field another
 system owns, do so explicitly.
- **Committing `.terraform/` or state to Git.** The provider cache is large and
 state may hold secrets. *Fix:* `.gitignore` them; use a remote backend.

### 8. Assessment

**Knowledge checks**

1. What's the difference between a resource and a data source?
2. How does Terraform decide the order to create resources? Give an example of an
 implicit dependency.
3. When should you reach for `for_each` instead of `count`?
4. What does `terraform plan` produce, and why should you never skip it?
5. What is `terraform_data` / `null_resource` for?

**Concept exercise**

> Explain how Terraform decides *what to change* **without using the words "plan,"
> "state," or "graph."** Describe the behavior to a developer who has only ever
> clicked in a cloud console.

**Debugging / trade-off exercise**

> A teammate wrote `resource "google_storage_bucket" "logs" { count = 3 … }` to make
> three buckets, named `logs-0/1/2`. They now need to delete `logs-1` permanently.
> What does Terraform do when they remove the middle one, why is that bad, and how
> would you have modeled it so deleting one bucket doesn't disturb the others?

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** A resource is something Terraform *creates and manages* (and will change or
 destroy). A data source *reads* information about something Terraform does not
 manage; it's read-only input.
- **Q2:** It builds a dependency graph from references and applies in dependency
 order, parallelizing independent resources. Implicit example: a node pool that
 references `google_container_cluster.platform.name` is created after the cluster.
- **Q3:** When instances have stable identities (named things, per-environment
 resources) so adding/removing one shouldn't disturb the others. `for_each` keys by
 name; `count` keys by position.
- **Q4:** A diff of create/update/destroy actions it intends to take. Skipping it
 means applying changes you haven't reviewed — the opposite of a safe review gate.
- **Q5:** A resource with no cloud object, used to run local logic (a `provisioner`)
 or to force replacement via a `triggers_replace`/`triggers` value. Use sparingly.
- **Debugging:** With `count`, removing `logs-1` renumbers `logs-2` to index `1`;
 Terraform sees `logs-2` "gone" at index 2 and a changed resource at index 1, and
 plans to destroy/recreate — disturbing an unrelated bucket (and possibly deleting
 data). Model it with `for_each = toset(["app","audit","ops"])` so each bucket has a
 stable key and removing one leaves the rest untouched.

</details>


_Previous:_ IaC Principles · _Next:_ Terraform State Management →

## Terraform State Management

> State is the most under-appreciated and most dangerous part of Terraform. It's the
> map between your code and the real world — and if two people apply at once, or the
> file is lost, or someone hand-edits it, you get corruption, duplicated resources,
> or destroyed production. This module teaches **why state exists**, how to store it
> safely (remote backends with locking), how to inspect and surgically manipulate
> it, and how to isolate it to limit blast radius.

### 1. Concept

#### What state actually holds

When you ran `apply` in, Terraform wrote `terraform.tfstate` — a JSON
document mapping each resource in your code to the **real resource's identifier** and
its last-known attributes:

```text
code: resource "docker_container" "svc" (web)
state entry: docker_container.svc["web"] → id = 3f9c…, name = "web-cosmic-ray", …
real world: an actual running container with id 3f9c…
```

State exists because Terraform must answer one question on every run: *"for each
thing in the code, does a real resource already exist, and is it as I left it?"*
Without state it would have no memory — it couldn't tell "create this" from "I
already made this." (You implemented exactly this `state.json` idea by hand in
.)

#### Why local state breaks for teams

A single `terraform.tfstate` on your laptop is fine for a solo experiment and a
disaster for a team:

- **It's not shared.** Your teammate's apply has no idea what yours created, so it
 tries to create everything again → duplicates and conflicts.
- **No locking.** If two applies run at once, they interleave writes and **corrupt**
 the state file.
- **No durability.** Laptop dies, file lost — Terraform forgets everything it owns.
- **Secrets in the clear.** State can contain sensitive attributes (passwords, keys)
 in plaintext; a file in a repo or on a laptop is an exposure.

#### Remote backends

A **backend** determines where state is stored and how operations run. A **remote
backend** keeps the single source of truth in shared, durable storage:

- **Google Cloud Storage (GCS)**, **AWS S3**, **Azure Blob**, or **Terraform/HCP
 Cloud**.
- Enables **sharing** (everyone reads/writes the same state), **durability**
 (versioned object storage), **encryption at rest**, and **locking**.

```hcl
terraform {
 backend "gcs" {
 bucket = "acme-tf-state"
 prefix = "platform/prod"
 }
}
```

#### State locking

A **lock** prevents two applies from mutating state simultaneously. Backends acquire
a lock before writing and release it after. GCS and S3 support locking (S3 via a
DynamoDB table or, newer, native lockfiles); HCP Cloud does it natively. If someone
else is mid-apply, your run waits or errors with a lock message — exactly what you
want, because concurrent writes corrupt state.

#### Inspecting state

Read-only commands that never change anything:

```bash
terraform state list # every managed resource address
terraform state show docker_container.svc # attributes of one resource
terraform show # the whole state, human-readable
terraform output # output values
```

#### Manipulating state (carefully)

Sometimes the *code* is right but the *state* needs surgery — you renamed a resource,
split a module, or imported something created by hand. These commands change the map,
not the infrastructure:

- **`terraform state mv A B`** — rename/move a resource's *address* in state (e.g.
 after renaming it in code) so Terraform doesn't destroy-and-recreate it.
- **`terraform state rm A`** — stop managing a resource *without destroying it*
 (Terraform forgets it; the real thing stays).
- **`terraform import A <id>`** — adopt an existing real resource into state so
 Terraform manages it going forward.

> These are power tools. Always back up state first and run with care — a wrong
> `state rm` on production can orphan resources; a wrong edit can destroy them.

#### Workspaces and state isolation

A **workspace** gives you *multiple state files for the same configuration* —
`terraform workspace new staging` keeps `staging` state separate from `default`.
They're handy for small dev/stage/prod splits of identical config.

But workspaces share the *same backend and code*, so they're a **weak** isolation
boundary. For real environments, platform teams prefer **separate state per
environment** (and often per team/component) via **directory or backend
separation** — because that controls **blast radius**: a bad apply in `dev` can't
touch `prod` state it cannot even reach. (More in.)

```text
Weak isolation (workspaces) Strong isolation (separate states)
───────────────────────── ─────────────────────────────────
one config + backend environments/dev/ → its own backend/state
 ├─ workspace: dev environments/stg/ → its own backend/state
 ├─ workspace: staging environments/prod/ → its own backend/state
 └─ workspace: prod a mistake in dev literally cannot reach prod
```

---

### 2. Why it matters for platform engineering

- **State is production data.** Treat it with the care you'd give a database:
 remote, locked, versioned, encrypted, backed up. Losing it is an outage-grade
 event.
- **Locking is how teams apply safely.** Dozens of engineers and CI jobs touch the
 same infrastructure; locking is what prevents them from corrupting each other.
- **Blast radius is a design decision you make in state layout.** How you split
 state determines what a single mistake can destroy. This is one of the highest-
 leverage decisions a platform team makes.
- **State surgery is a real on-call skill.** Renames, module refactors, and imports
 all require confident, careful state manipulation. Fumbling it causes incidents.

---

### 3. Mental model

**State is a shared ledger; the backend is the vault; the lock is the pen only one
person can hold.**

```text
 ┌─────────────────────── remote backend (the vault) ───────────────────────┐
 │ versioned, encrypted object storage │
 │ │
 │ ┌──────────────┐ lock ┌──────────────┐ │
 you ─┼──────▶ │ state file │ ◀───(pen)───▶ │ teammate │ ─┐ │
 │ │ (ledger) │ │ / CI job │ │ only one writes │
 │ └──────────────┘ └──────────────┘ │ at a time │
 └───────────────────────────────────────────────────────────────────────── ┘
```

Three rules:

1. **One source of truth, stored remotely.** Never the laptop for anything shared.
2. **Lock before you write.** Concurrency without locks corrupts.
3. **Change the map with intent.** `state mv/rm/import` move the ledger entries;
 back up first, every time.

---

### 4. Minimal implementation

You don't need a cloud bucket to understand remote state — the **`local` backend**
and a **state move** demonstrate the mechanics. Start with the local-backend default
and inspect it:

```bash
# A tiny config using the random provider (no cloud):
cat > main.tf <<'EOF'
terraform {
 required_providers { random = { source = "hashicorp/random", version = "~> 3.6" } }
}
resource "random_pet" "old" { length = 2 }
EOF

terraform init
terraform apply -auto-approve
terraform state list # random_pet.old
```

Now rename the resource in code from `old` to `new`. Naïvely, Terraform would
**destroy** `old` and **create** `new`. Instead, move it in state so the *same* real
resource keeps its identity:

```bash
sed -i 's/"old"/"new"/' main.tf
terraform state mv random_pet.old random_pet.new # move the ledger entry
terraform plan # "No changes." — nothing destroyed
```

That is the heart of state management: the real resource never changed, but you
updated the **map** so code and state agree. Swapping the `local` backend for `gcs`
or `s3` changes *where the ledger lives and how it locks* — not these mechanics.

---

### 6. Production considerations

- **Always remote, always locked, always versioned.** Use GCS/S3/HCP with object
 versioning and encryption on. Versioning is your undo button after a bad apply.
- **Restrict who can read state.** State may contain secrets; lock down bucket IAM
 as tightly as the infrastructure it describes.
- **Back up before surgery.** `terraform state pull > backup.tfstate` before any
 `mv`/`rm`/`import`. If it goes wrong, `state push` the backup.
- **Isolate state to bound blast radius.** Separate state per environment and per
 high-risk component (networking, IAM) so one mistake can't cascade.
- **Don't overuse workspaces for prod.** They're convenient but share code and
 backend; prefer directory/backend separation for environments that matter.
- **Never hand-edit state JSON.** Use the `state` subcommands. Manual edits silently
 corrupt the structure Terraform depends on.

### 7. Common mistakes

- **Committing `terraform.tfstate` to Git.** It's shared-mutable and may hold
 secrets; Git is neither locked nor encrypted. *Fix:* remote backend +
 `.gitignore` state.
- **No locking.** "We both applied and now resources are duplicated/half-created."
 *Why:* concurrent writes. *Fix:* a backend with locking enabled; let it block the
 second run.
- **`state rm` expecting it to delete the resource.** It only stops managing it —
 the real resource is orphaned and still costs money. *Fix:* use `destroy` to
 delete; use `rm` only to intentionally hand off ownership.
- **Renaming a resource without `state mv`.** Terraform destroys the old and creates
 a new one — downtime and data loss for stateful resources. *Fix:* `state mv` (or a
 `moved {}` block) to preserve identity.
- **One giant state for everything.** A single mistake can destroy the whole estate,
 and plans get slow. *Fix:* split by environment/component.

### 8. Assessment

**Knowledge checks**

1. Why does local state fail as soon as a second engineer joins?
2. What does state locking prevent, and what happens to a second apply when a lock
 is held?
3. What's the difference between `terraform state rm` and `terraform destroy`?
4. When do you need `terraform state mv`, and what goes wrong if you skip it?
5. Why do platform teams prefer separate state per environment over workspaces for
 production?

**Concept exercise**

> Explain why Terraform needs state at all **without using the words "state,"
> "backend," or "file."** (Describe the problem it solves.)

**Debugging / trade-off exercise**

> On-call at 2am: a `terraform apply` failed halfway and now every subsequent run
> errors with *"Error acquiring the state lock."* The engineer who started it is
> asleep. Walk through how you'd diagnose whether the lock is stale, what
> `force-unlock` does and its danger, and what you'd verify about state *before and
> after* breaking the lock.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** Local state isn't shared — the second engineer's Terraform has no record of
 what the first created, so it tries to create everything again (duplicates), and
 there's no lock to stop concurrent corruption.
- **Q2:** Locking prevents two operations from writing state at the same time, which
 would corrupt it. A second apply either waits for the lock or fails fast with a
 lock error identifying who holds it.
- **Q3:** `state rm` tells Terraform to *forget* a resource (stop managing it); the
 real resource keeps running (and billing). `destroy` *deletes* the real resource.
- **Q4:** When you rename/move a resource's address in code (or restructure modules).
 Without `state mv`, Terraform sees the old address gone and a new one added, and
 destroys+recreates — fatal for stateful resources. (A `moved {}` block is the
 declarative equivalent.)
- **Q5:** Workspaces share one backend and one codebase, so isolation is weak and a
 mistake can reach the wrong environment. Separate state (separate backends/dirs)
 means a bad `dev` apply literally cannot address `prod` — real blast-radius
 control.
- **Debugging:** Diagnose with `terraform force-unlock`'s reported lock info (who,
 when, operation) and the backend's lock record; check the object's last-modified
 time and whether the holder's process is truly dead. `force-unlock <ID>` removes
 the lock *without* checking that the other operation finished — dangerous because
 if that apply is secretly still running you'll corrupt state. Before breaking it:
 `terraform state pull > backup` and confirm no live apply. After: `plan` to verify
 state is coherent (no unexpected creates/destroys) before doing anything else.

</details>


_Previous:_ Terraform Fundamentals · _Next:_ Terraform Modules →

## Terraform Modules

> Copy-pasting HCL between environments is how IaC rots. **Modules** are Terraform's
> unit of reuse: a parameterized, versioned package with a clean interface. This
> module teaches how to structure modules, design their interfaces, compose them, and
> version an internal module library — the building blocks a platform team ships as
> its paved road.

### 1. Concept

#### Every configuration is already a module

In Terraform, a **module** is just a directory of `.tf` files. The directory you run
`terraform apply` in is the **root module**. When one module calls another, the
callee is a **child module**. So you've been writing modules since 
"making a module" is mostly about giving a child module a clean interface and reusing
it.

```text
root module (you run apply here)
└── module "network" { source = "./modules/vpc" … } ← a child module call
 module "cluster" { source = "./modules/gke" … } ← another child module call
```

#### Standard module structure

A well-formed module has three conventional files (plus optional extras):

```text
modules/gke-cluster/
├── main.tf # the resources this module manages
├── variables.tf # the INPUTS (the interface the caller fills in)
├── outputs.tf # the OUTPUTS (what the caller can read back)
├── versions.tf # required_version + required_providers
└── README.md # how to use it (the module is a product; document it)
```

- **`variables.tf` is the module's API.** Each `variable` is a knob the caller sets.
- **`outputs.tf` is the return value.** Other modules wire to these.
- **`main.tf` is the implementation** — hidden behind the interface.

#### Interface design: the heart of a good module

A module is a product with developers as customers (sound familiar from ?).
Good interfaces share qualities:

- **Minimal required inputs.** Require only what truly varies; everything else gets a
 sensible default. A caller should stand up a correct resource with two or three
 inputs, not twenty.
- **Safe, opinionated defaults.** Encode good practice *once* — private nodes,
 encryption on, least-privilege — so every consumer gets it for free.
- **Validated inputs.** Use `validation` blocks and types to reject bad input early
 with a clear message.
- **Useful outputs.** Export the things callers actually need (endpoints, names, IDs)
 and nothing secret unless marked `sensitive`.
- **Stable.** Changing an input's name or meaning is a breaking change for every
 consumer — version it (below).

```hcl
variable "node_count" {
 type = number
 default = 3
 description = "Number of nodes in the primary pool."

 validation {
 condition = var.node_count >= 1 && var.node_count <= 100
 error_message = "node_count must be between 1 and 100."
 }
}
```

#### Composition: small modules, assembled

Rather than one mega-module, platform teams build **small, focused modules** (a VPC,
a GKE cluster, a node pool, a bucket, a secret) and **compose** them in environment
root modules. Outputs of one feed inputs of the next:

```hcl
module "vpc" {
 source = "../../modules/vpc"
 name = "platform-${var.environment}"
}

module "gke" {
 source = "../../modules/gke-cluster"
 name = "platform-${var.environment}"
 network = module.vpc.network_name # output → input: implicit dependency
 subnetwork = module.vpc.subnet_name
}
```

#### Published vs internal modules

- **Published modules** live on the [Terraform Registry](https://registry.terraform.io/)
 (and OpenTofu's registry) — community/vendor modules you consume by `source` and
 `version`. Great for common building blocks; review them like any dependency.
- **Internal module library** — your own modules, shared across repos. Version them
 with **Git tags** and pin consumers to a tag:

```hcl
module "gke" {
 source = "git::https://github.com/acme/tf-modules.git//gke-cluster?ref=v1.4.0"
 #...
}
```

Pinning a `ref` is what makes upgrades **deliberate**: a consumer moves from `v1.4.0`
to `v1.5.0` on purpose, in a reviewed PR — not silently.

#### When *not* to make a module

Abstraction has a cost. Don't wrap a single resource in a module just to feel
organized, and don't build a configurable mega-module with forty toggles. A good
rule: **extract a module when you have the same shape of infrastructure in two or
more places, and the interface is small.** Premature or over-parameterized modules
are harder to use than the raw resources.

---

### 2. Why it matters for platform engineering

- **Modules are the paved road, as code.** The platform team's opinions — secure
 defaults, naming, tagging, network layout — live in modules that every team
 consumes. Build the right thing once; everyone gets it.
- **They turn copy-paste drift into versioned upgrades.** Instead of each team's
 forked YAML rotting apart, a single module evolves and teams adopt new versions
 deliberately.
- **They encode compliance by construction.** "All buckets are encrypted and
 private" becomes true-by-default when the only sanctioned way to make a bucket is
 your module.
- **They're how a small team scales.** A five-person platform team can equip
 hundreds of developers because the hard decisions are packaged, not re-made each
 time.

### 3. Mental model

**A module is a function; the root module is `main()`.**

```text
 module = function(inputs) -> outputs

 module "gke" { f( returns
 source = "./gke" name = "...", module.gke.endpoint
 name = "platform" node_count = 3, module.gke.name
 node_count = 3 ) -> { endpoint, name,... }
 }

 root module = main(): calls functions, wires outputs → inputs, owns the state
```

Rules to keep:

- **Inputs in, outputs out, implementation hidden.** Callers shouldn't need to read
 `main.tf`.
- **Version your functions.** A changed signature breaks callers; tag releases.
- **Compose, don't inflate.** Many small functions beat one giant configurable one.

### 4. Minimal implementation

Here's the smallest useful module and a root module that calls it — using the free
`random`/`local` providers so you can run it immediately. The module wraps "a named
config file with a generated token" behind a two-input interface.

```hcl
# modules/service-config/variables.tf
variable "name" {
 type = string
}

variable "log_level" {
 type = string
 default = "info"
}

# modules/service-config/main.tf
resource "random_password" "token" {
 length = 16
 special = false
}
resource "local_file" "config" {
 filename = "${path.root}/${var.name}.conf"
 content = "name=${var.name}\nlog_level=${var.log_level}\ntoken=${random_password.token.result}\n"
}

# modules/service-config/outputs.tf
output "path" { value = local_file.config.filename }
```

```hcl
# main.tf (root module) — compose two instances of the module
module "payments" {
 source = "./modules/service-config"
 name = "payments"
 log_level = "debug"
}
module "orders" {
 source = "./modules/service-config"
 name = "orders" # log_level defaults to "info"
}

output "config_paths" {
 value = [module.payments.path, module.orders.path]
}
```

```bash
terraform init && terraform apply -auto-approve
# → creates payments.conf (debug) and orders.conf (info), each with a token.
```

Two calls, one definition, zero copy-paste. Swap the implementation for a GKE cluster
and you have the lab.

### 6. Production considerations

- **Version everything; pin consumers.** Tag module releases (`v1.2.3`,
 semver-style) and pin each consumer to a tag. Treat module upgrades like dependency
 upgrades — reviewed and tested.
- **Document the interface.** A module without a README is a riddle. Describe each
 input, its default, and show an example call. (`terraform-docs` can generate this.)
- **Keep modules provider-agnostic where sensible, but don't over-abstract.** A
 module that tries to support three clouds usually serves none well.
- **Validate inputs aggressively.** `validation` blocks and precise types turn
 runtime cloud errors into fast, clear plan-time failures.
- **Beware breaking changes.** Renaming an input or output breaks every consumer.
 Deprecate gracefully; bump the major version; communicate.
- **Test modules in isolation.** Contract-test the interface, not the implementation.

### 7. Common mistakes

- **The mega-module.** One module with dozens of flags trying to cover every case.
 *Why:* fear of duplication. *Fix:* compose several small, focused modules instead.
- **Abstracting too early.** Wrapping a single resource used in one place. *Why:*
 tidiness. *Fix:* wait until you have two-plus real consumers and a small interface.
- **Unpinned module sources.** `source = ".../modules.git//gke"` with no `?ref=`.
 *Why:* convenience. *Fix:* pin a tag so upgrades are deliberate and reproducible.
- **Leaking implementation through the interface.** Requiring callers to pass
 low-level IDs the module could derive. *Fix:* require the minimum; compute the
 rest internally.
- **No defaults, so every call is huge.** Forcing callers to specify everything.
 *Fix:* sensible, secure defaults; require only what truly varies.

### 8. Assessment

**Knowledge checks**

1. What are the three conventional files in a module, and what role does each play?
2. What makes an input "part of the module's interface"? Why is renaming one a
 breaking change?
3. How do you pin an internal module to a specific version, and why does that matter?
4. Give a concrete signal that some HCL *should* be extracted into a module — and one
 that it shouldn't.
5. How does one module's output become another module's input?

**Concept exercise**

> Explain what a Terraform module gives you **without using the words "module,"
> "Terraform," or "reuse."** (Describe it to someone who knows functions in a
> programming language.)

**Architecture / trade-off exercise**

> Your team has three environments whose GKE clusters are identical except for node
> count and region. One engineer proposes a single `gke` module with a `node_count`
> and `region` input, called three times. Another proposes three copies of the raw
> resources "so each environment can diverge freely." Argue for the module approach,
> then name the one situation where the copy approach is actually defensible.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** `variables.tf` (inputs / interface), `main.tf` (the resources /
 implementation), `outputs.tf` (return values other modules consume). Plus
 `versions.tf` and a README in practice.
- **Q2:** Any `variable` (its name, type, meaning) is the public API callers depend
 on. Renaming/retyping it breaks every caller's block — hence it's a breaking change
 that warrants a major version bump.
- **Q3:** Pin the `source` with `?ref=vX.Y.Z` (Git tag) or `version` (registry). It
 makes upgrades deliberate and builds reproducible — consumers move versions in a
 reviewed PR, not silently.
- **Q4:** Extract when the same shape appears in two-plus places with a small, stable
 interface. Don't extract a single-use single resource, or when every consumer would
 need a different large set of flags (over-parameterization).
- **Q5:** By reference: `module.vpc.network_name` used as an input to the `gke`
 module creates an implicit dependency and passes the value.
- **Trade-off:** The module removes duplication, encodes secure defaults once, makes
 upgrades uniform, and keeps environments genuinely identical (a feature). The copy
 approach is defensible only when environments must diverge in *structural,
 unpredictable* ways (e.g., a legacy prod with a fundamentally different topology you
 don't want to model as options) — but that's rare and usually a smell.

</details>


_Previous:_ Terraform State Management · _Next:_ Terraform Testing and Quality →

## Terraform Testing and Quality

> Unreviewed, untested infrastructure code is a liability waiting to cause an
> outage or a breach. This module covers the quality ladder every serious IaC
> codebase climbs: **formatting and validation**, **static security scanning**
> (tfsec/Checkov), **policy as code** (OPA/Conftest), **integration tests**
> (Terratest), and the **PR workflow** — plan on PR, apply on merge — that enforces
> all of it.

### 1. Concept

#### A ladder of increasing confidence

Testing infrastructure isn't one thing; it's a ladder, cheap and fast at the bottom,
slower and higher-fidelity at the top. Run the cheap checks on every change; reserve
the expensive ones where they earn their keep.

```text
 slow / high-fidelity
 ▲ Terratest — apply real resources, assert, destroy (integration)
 │ Policy (OPA) — org rules on the PLAN (no "public buckets", required tags)
 │ Security scan — tfsec / Checkov: known misconfigurations (static)
 │ validate — internal consistency, provider schema
 ▼ fmt — canonical formatting (style)
 fast / cheap
```

#### Formatting and validation: the free wins

- **`terraform fmt`** rewrites files to canonical style. Enforced with
 `fmt -check` in CI, it ends every formatting debate.
- **`terraform validate`** checks a configuration is internally consistent and
 matches provider schemas — undeclared variables, wrong types, bad references —
 without touching real infrastructure.

These catch a surprising share of mistakes in milliseconds. They are the floor.

#### Static security scanning

**tfsec** and **Checkov** scan Terraform *statically* (no apply) for known insecure
patterns: a storage bucket open to the public, an unencrypted disk, an over-broad
IAM binding, a security group open to `0.0.0.0/0`. They ship hundreds of built-in
rules mapped to benchmarks (CIS, etc.).

```bash
tfsec. # scans the current module, prints findings by severity
checkov -d. # same idea, different rule set and output
```

They're fast, run in CI on every PR, and turn "we'll review security later" into a
blocking gate. Neither is complete — they catch *known* misconfigurations — so pair
them with policy and human review.

#### Policy as code (OPA / Conftest)

Scanners enforce *generic* best practice. **Policy as code** enforces *your
organization's* rules: "every resource must have an `owner` tag," "no resource
outside approved regions," "prod databases must have deletion protection." You write
policies in **Rego** and evaluate them with **Conftest** (built on **Open Policy
Agent**) against the JSON form of a Terraform **plan**.

```bash
terraform plan -out=tfplan
terraform show -json tfplan > plan.json
conftest test plan.json # evaluates your Rego policies against the plan
```

```rego
# policy/deny_public.rego — deny any bucket with public access
package main

import rego.v1

deny contains msg if {
 resource:= input.resource_changes[_]
 resource.type == "google_storage_bucket"
 resource.change.after.public_access_prevention == "inherited"
 msg:= sprintf("bucket %q must set public_access_prevention = enforced", [resource.address])
}
```

Testing the **plan** (not the code text) means you check what Terraform *will
actually do*, after variables and defaults are resolved.

#### Terratest: real integration tests

**Terratest** is a Go library that drives Terraform programmatically: it runs
`init`/`apply`, inspects outputs and real resources, asserts, and then `destroy`s —
even if the test fails (via `defer`). It's how you verify a module *actually
produces working infrastructure*, not just valid HCL.

```go
func TestServiceModule(t *testing.T) {
 opts:= &terraform.Options{TerraformDir: "../modules/service"}
 defer terraform.Destroy(t, opts) // always clean up
 terraform.InitAndApply(t, opts) // provision for real

 path:= terraform.Output(t, opts, "config_path")
 assert.FileExists(t, path) // assert the real result
}
```

Terratest is slower and costs real resources (so target cheap/local resources in CI
where possible), but it's the only layer that proves end-to-end behavior.

#### Contract testing: interface, not implementation

Test a module's **interface** — given these inputs, I get these outputs and these
externally observable properties — not its internal resource wiring. That way the
module can be refactored freely as long as the contract holds, and your tests don't
break on every internal change.

#### The PR workflow that enforces it all

Quality only matters if it's enforced. The standard platform pattern:

```text
open PR ─▶ CI runs: fmt-check · validate · tfsec/checkov · conftest · terraform plan
 └─ plan posted as a PR comment for human review
merge ─▶ CI runs: terraform apply (of the reviewed plan) ← only path to prod
```

Humans never apply from laptops. The pipeline is the only way to change
infrastructure, which makes every change reviewed, scanned, policy-checked, and
auditable.

---

### 2. Why it matters for platform engineering

- **Modules are shared blast radius.** A bug in a platform module ships to every
 consumer. Tests are what let you refactor and upgrade shared modules with
 confidence.
- **Security and compliance become structural.** Scanning + policy-as-code bake "no
 public buckets, everything tagged, approved regions only" into the pipeline — not
 into a wiki nobody reads.
- **The plan-on-PR gate is governance.** It's the concrete mechanism behind "no
 manual console changes; every change reviewed".
- **Fast feedback = adoption.** If the paved-road module has tests and scans, teams
 trust it and stay on it. Quality is part of developer experience.

### 3. Mental model

**Shift left: catch each class of problem at the cheapest possible stage.**

```text
 cost to catch a problem
 ▲
 prod │ ● incident (worst, most expensive)
 │ ● manual review
 │ ● Terratest (apply)
 │ ● policy / security scan
 │ ● validate
 cheap│ ● fmt
 └──────────────────────────────────────────▶ earlier = cheaper
```

Rules to keep:

- **Every layer catches what cheaper layers can't** — don't skip, stack them.
- **Test the plan and the real outputs**, not the HCL text.
- **If it isn't enforced in CI, it doesn't exist.**

### 4. Minimal implementation

The cheapest meaningful quality gate is three commands and a tiny policy — no cloud
needed. Given any module:

```bash
terraform fmt -check -recursive # fail if not canonically formatted
terraform validate # fail on inconsistency/bad types
tfsec. # fail on known-insecure patterns
```

Add a one-rule policy on the plan to enforce an org convention — here, "every
`local_file` must live under a `generated/` directory" (a stand-in for a real rule
like "every bucket must be private"):

```rego
# policy/naming.rego
package main

import rego.v1

deny contains msg if {
 rc:= input.resource_changes[_]
 rc.type == "local_file"
 not startswith(rc.change.after.filename, "./generated/")
 msg:= sprintf("%s: files must be created under./generated/", [rc.address])
}
```

```bash
terraform plan -out=tfplan && terraform show -json tfplan > plan.json
conftest test plan.json
```

That's the whole idea: fast static checks plus a plan-level policy, both runnable
locally and both suitable as blocking CI gates. Terratest (the lab) adds the
apply-and-assert layer on top.

### 6. Production considerations

- **Make checks blocking, not advisory.** A scan that only warns gets ignored. Fail
 the PR on high-severity findings; provide a documented, reviewed exception
 mechanism (e.g. inline ignores with a justification).
- **Keep Terratest costs bounded.** Integration tests apply real resources. Use
 cheap/ephemeral ones, short-lived projects, aggressive `defer destroy`, and run the
 expensive suite on a schedule or label, not every commit.
- **Version your policies.** Rego policies are code too — review, test (OPA has a
 test framework), and roll out changes deliberately so you don't break every PR at
 once.
- **Scan modules *and* compositions.** A module can be clean while a composition
 wires it insecurely. Scan the environment root modules as well.
- **Store and apply the exact plan.** `plan -out=tfplan` on PR, `apply tfplan` on
 merge — so what was reviewed and policy-checked is byte-for-byte what applies.
- **Supply-chain hygiene.** Pin provider and module versions, commit lockfiles, and
 scan third-party modules before adopting them.

### 7. Common mistakes

- **Formatting/linting that only warns.** Non-blocking checks rot. *Fix:*
 `fmt -check` and scanners **fail** the build.
- **Testing the HCL text instead of the plan.** Asserting on source strings misses
 what defaults/variables resolve to. *Fix:* evaluate policy against
 `terraform show -json` of a plan.
- **Terratest with no `defer destroy`.** A failed test leaks real resources and
 cost. *Fix:* `defer terraform.Destroy(...)` is the first line after options.
- **Relying on one scanner as "security done."** tfsec/Checkov catch *known* issues
 only. *Fix:* layer policy-as-code and human review; they're complementary.
- **Applying from laptops "just this once."** Bypasses every gate and creates drift.
 *Fix:* pipeline-only apply; no human has prod apply creds.
- **Giant, slow test suites run on every commit.** People start skipping them. *Fix:*
 fast checks on every PR; heavy Terratest on merge/schedule.

### 8. Assessment

**Knowledge checks**

1. What's the difference between `terraform validate` and a tfsec scan?
2. Why do you evaluate policy against the JSON *plan* rather than the `.tf` files?
3. What does `defer terraform.Destroy` do in a Terratest test, and why is it
 essential?
4. What does "plan on PR, apply on merge" buy you beyond convenience?
5. What is contract testing a module, and why test the interface not the
 implementation?

**Concept exercise**

> Explain how you'd stop a teammate from ever merging a publicly-readable storage
> bucket **without using the words "tfsec," "Checkov," or "scanner."** (Describe the
> control, not the product.)

**Debugging / trade-off exercise**

> Your Terratest suite takes 40 minutes because it provisions a real GKE cluster per
> test, and engineers have started merging with the tests skipped. Diagnose why this
> happened, then propose a layered strategy: what should run on every PR (seconds),
> what on merge, and what on a nightly schedule — and how you'd keep integration-test
> cost and flakiness under control.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** `validate` checks internal consistency and provider-schema correctness
 (does the config make sense?). A tfsec scan checks for known *security*
 misconfigurations (is the config *safe*?). Different questions; both static.
- **Q2:** The plan reflects what Terraform will actually do after variables, defaults,
 and computed values resolve. The raw `.tf` text may not reveal the effective
 settings; the plan does.
- **Q3:** It schedules the destroy to run when the test function returns — pass or
 fail — guaranteeing provisioned resources are cleaned up so tests don't leak cost.
- **Q4:** It makes the pipeline the only path to prod: every change is reviewed via
 its plan, scanned, policy-checked, and auditable; humans don't apply from laptops,
 which prevents drift and un-reviewed changes.
- **Q5:** Asserting that given inputs you get the expected outputs and externally
 observable properties — not which internal resources exist. It lets you refactor
 the module's internals without breaking tests, as long as the contract holds.
- **Debugging:** Tests got slow and expensive, so humans routed around them —
 classic. Layer it: on every PR run fmt/validate/tfsec/conftest and a `plan`
 (seconds, no cost); on merge run a *small* Terratest against cheap/local or a
 single ephemeral resource; run the full real-cluster Terratest nightly or behind a
 label. Bound cost/flakiness with ephemeral projects, `defer destroy`, retries on
 known-eventual-consistency checks, and parallelism caps. Make the fast gates
 blocking so nothing merges unchecked.

</details>


_Previous:_ Terraform Modules · _Next:_ Crossplane →

## Crossplane

> Terraform provisions infrastructure *from the outside* — a CLI run from CI, state
> in a bucket, reconciliation only when you run `apply`. **Crossplane** flips this:
> it turns your Kubernetes cluster into a **control plane** that provisions and
> *continuously reconciles* cloud infrastructure using the same API machinery as Pods
> and Services. This module teaches managed resources, composite resources (XRs),
> XRDs, and compositions — and how they enable true `kubectl apply` self-service.

### 1. Concept

#### The problem: provisioning lives outside the cluster

With Terraform, the desired state is HCL, the record is a state file, and
reconciliation happens only when a pipeline runs `apply`. Between runs, nothing
watches for drift. And "let a developer provision a database" means giving them a
pipeline, a module, and cloud permissions — or a ticket.

Kubernetes already solved "continuously reconcile desired state" for *workloads*: you
declare a Deployment, and a controller works forever to make reality match, healing
drift automatically. **Crossplane extends that exact pattern to cloud
infrastructure.** You declare "an S3 bucket" or "a Cloud SQL instance" as a
Kubernetes object, and a controller continuously reconciles the real cloud resource —
no out-of-band `apply`, no separate state file (the cluster's etcd *is* the state).

#### Managed resources and providers

A **provider** is a Crossplane package that teaches the control plane to manage a
cloud's resources (AWS, GCP, Azure, Kubernetes itself, SQL, …). Installing one
registers a set of **managed resources (MRs)** — fine-grained CRDs that map
one-to-one to a real cloud resource.

```yaml
# A managed resource: one CRD == one real cloud resource, reconciled continuously.
apiVersion: storage.gcp.upbound.io/v1beta1
kind: Bucket
metadata:
 name: platform-logs
spec:
 forProvider:
 location: EU
 providerConfigRef:
 name: default
```

Apply that and Crossplane creates the bucket and keeps it reconciled forever. Delete
the object and it deletes the bucket. It's Terraform's reconcile loop, running
always, inside Kubernetes.

#### The abstraction problem: MRs are too low-level for developers

You don't want app developers wiring up a bucket *and* an IAM policy *and* a database
*and* a firewall rule correctly every time — that's the cognitive load warned
about. You want to offer them a single, high-level, safe thing: *"give me a
PostgreSQL instance."* Crossplane's composition machinery is how a platform team
builds that abstraction.

#### XRDs, composite resources, and claims

- A **CompositeResourceDefinition (XRD)** defines a *new API* — your own CRD — e.g.
 `XPostgreSQLInstance`, with a schema (`storageGB`, `version`). This is the shape of
 the self-service API you offer.
- A **Composite Resource (XR)** is an instance of that API. It's cluster-scoped and
 usually created on a developer's behalf.
- A **Claim** is the *namespaced* developer-facing handle to an XR (kind
 `PostgreSQLInstance`). Developers create claims in their namespace; Crossplane
 creates the matching XR. (Claims are optional in newer Crossplane, but they're the
 classic self-service entry point.)

#### Compositions: how an XR becomes real resources

A **Composition** tells Crossplane *how to implement* an XR — which managed resources
to create and how to fill them in from the XR's parameters. One high-level request
fans out into many correctly-wired managed resources.

```text
developer applies platform team authored
─────────────────── ──────────────────────
PostgreSQLInstance ──XRD──▶ XPostgreSQLInstance ──Composition──▶ CloudSQLInstance
(claim, namespaced) (XR, cluster-scoped) + Database
 storageGB: 20 + User
 version: "15" + firewall rule
```

The developer sees one simple object; the platform team's Composition encodes all the
expertise. Modern Crossplane runs Compositions as a **pipeline of composition
functions** (e.g. `function-patch-and-transform`), which patch values from the XR
onto the composed resources.

#### Self-service via `kubectl apply` + RBAC

Because everything is a Kubernetes API, **self-service falls out for free**: give a
team RBAC to create `PostgreSQLInstance` claims in their namespace, and they
provision databases with `kubectl apply` — no cloud credentials, no tickets, no
Terraform access. The guardrails live in the Composition; the developer can only ask
for what the XRD allows.

---

### 2. Why it matters for platform engineering

- **It's a self-service engine.** Crossplane is one of the cleanest ways to offer
 "databases/environments/namespaces on demand" as a Kubernetes-native API — the
 literal realization of the paved road.
- **Continuous reconciliation, not periodic applies.** Drift is corrected
 automatically by controllers, the same way Kubernetes heals a crashed Pod — a
 stronger guarantee than "we run `terraform plan` nightly."
- **One control plane, one RBAC model.** Infrastructure and workloads share
 Kubernetes' auth, policy, and GitOps tooling. Your ArgoCD already knows
 how to deploy a `PostgreSQLInstance`.
- **Abstraction is first-class.** XRDs + Compositions are a native way to encode
 platform opinions and expose a minimal interface — modules, but as live APIs.

### 3. Mental model

**Crossplane is a Kubernetes controller for the cloud; your XRD is a new "kind," your
Composition is its controller logic.**

```text
 ┌──────────────────────── your Kubernetes cluster (the control plane) ─────────┐
 │ │
 │ developer: kubectl apply PostgreSQLInstance (claim) │
 │ │ │
 │ ▼ │
 │ XRD defines the API ──▶ XR created ──▶ Composition (functions) selects │
 │ and patches managed resources │
 │ │ │
 │ ▼ │
 │ Provider controllers reconcile ──────▶ real cloud resources ◀─ drift ──┐│
 │ (continuously, forever) (DB, bucket, user) auto-heal ││
 └──────────────────────────────────────────────────────────────────────────────┘
```

Rules to keep:

- **MRs are the atoms; XRs are the molecules.** Developers touch molecules; the
 platform team composes them from atoms.
- **The cluster is the state.** etcd + controllers replace the state file + periodic
 apply.
- **The XRD is the contract.** Developers can only request what it allows — guardrails
 by schema.

### 4. Minimal implementation

The smallest end-to-end Crossplane abstraction, using a **no-cloud provider** so it
costs nothing, is four objects: a provider, a function, an XRD, and a Composition —
then a developer applies a claim.

```yaml
# 1) a provider that creates fake "managed resources" (no cloud, no credentials)
apiVersion: pkg.crossplane.io/v1
kind: Provider
metadata:
 name: provider-nop
spec:
 package: xpkg.upbound.io/crossplane-contrib/provider-nop:v0.4.0
```

```yaml
# 2) the function that patches composed resources
apiVersion: pkg.crossplane.io/v1
kind: Function
metadata:
 name: function-patch-and-transform
spec:
 package: xpkg.upbound.io/crossplane-contrib/function-patch-and-transform:v0.8.2
```

With the XRD and Composition applied (see the lab), a developer does exactly this —
and nothing else:

```yaml
apiVersion: platform.example.com/v1alpha1
kind: PostgreSQLInstance
metadata:
 name: my-app-db
spec:
 parameters:
 storageGB: 20
 version: "15"
 compositionSelector:
 matchLabels:
 environment: production
```

```bash
kubectl apply -f my-app-db.yaml
kubectl get postgresqlinstance,xpostgresqlinstance # claim → XR
kubectl get managed # the composed resource(s)
```

The developer requested a database in nine lines; the platform team's Composition
turned it into correctly-wired managed resources. Swap `provider-nop` for
`provider-gcp` and the same claim provisions a real Cloud SQL instance — the
developer's YAML doesn't change.

### 6. Production considerations

- **Protect the control plane.** It now holds credentials that can create cloud
 infrastructure. Treat the Crossplane cluster as tier-0: locked-down RBAC, audited,
 isolated from workloads.
- **Version providers, functions, and XRDs.** They're packages and APIs; pin
 versions and roll out upgrades deliberately, exactly like Terraform modules.
- **Design XRD schemas like product APIs.** Minimal inputs, safe defaults, validated
 fields. A sloppy XRD is a sloppy platform API every team must live with.
- **Plan for day-two.** Updates, field immutability, deletion policies
 (`Delete` vs `Orphan`), and what happens to real resources when a claim is deleted
 are critical — a stray `kubectl delete` must not nuke a production database by
 accident.
- **Observe it.** Composed-resource readiness, reconciliation errors, and provider
 health need dashboards and alerts like any controller.
- **GitOps the claims.** Don't let humans `kubectl apply` prod infrastructure by hand;
 drive claims through Git + ArgoCD/Flux for review and audit.

### 7. Common mistakes

- **Exposing managed resources directly to developers.** Making teams wire up
 buckets, IAM, and databases themselves re-creates the cognitive load. *Fix:* offer
 XRs/claims; compose the atoms for them.
- **Treating Crossplane as "Terraform in YAML."** It's a *continuous control plane*,
 not a one-shot apply. *Fix:* design for always-on reconciliation and controller
 semantics, not pipeline runs.
- **Ignoring deletion/immutability policies.** Defaults can delete real
 infrastructure when a claim is removed, or fail updates on immutable fields. *Fix:*
 set deletion policies deliberately; document which fields are immutable.
- **Giving the control plane cloud-admin and forgetting it.** It becomes the softest
 path to your whole cloud. *Fix:* least-privilege provider credentials, isolation,
 auditing.
- **One mega-Composition with dozens of toggles.** Same anti-pattern as the
 mega-module. *Fix:* small, composable XRs; multiple Compositions selected by label.

### 8. Assessment

**Knowledge checks**

1. How does Crossplane's reconciliation model differ from `terraform apply`?
2. What's the difference between a managed resource, an XR, and a claim?
3. What does an XRD define, and what does a Composition define?
4. How does `kubectl apply` self-service work without handing developers cloud
 credentials?
5. Name one scenario where Crossplane is a better fit than Terraform, and one where
 it isn't.

**Concept exercise**

> Explain how a developer can "ask for a database and get one safely" **without using
> the words "Crossplane," "Composition," or "Kubernetes."** Describe the
> request/fulfilment model and the guardrails.

**Architecture / trade-off exercise**

> Your org already runs all infrastructure in Terraform. A team wants fully
> self-service, auto-reconciling dev databases via `kubectl`. Make the case for
> introducing Crossplane *for that use case* while keeping Terraform for the
> foundational estate (networks, clusters, IAM). What boundary would you draw between
> the two tools, and why is "use both" often the right answer?

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** Terraform reconciles only when a pipeline runs `apply`, with state in a
 file. Crossplane runs controllers that reconcile *continuously*, auto-healing drift,
 with the cluster's etcd as the record of state.
- **Q2:** A managed resource maps 1:1 to a real cloud resource (low-level). An XR is a
 high-level, cluster-scoped composite your platform defines (via an XRD) that fans
 out into managed resources. A claim is the namespaced, developer-facing handle to an
 XR.
- **Q3:** An XRD defines a new API/CRD (its name, schema, claim) — the *interface*. A
 Composition defines how an XR of that type is *implemented* — which managed
 resources to create and how to patch them from the XR's parameters.
- **Q4:** Everything is a Kubernetes API, so you grant RBAC to create *claims* in a
 namespace. The cloud credentials live only in the control plane's providers;
 developers never see them and can only request what the XRD schema allows.
- **Q5:** Crossplane shines for self-service, continuously-reconciled, abstracted
 resources (dev databases, namespaces, ephemeral environments) in Kubernetes-centric
 orgs. Terraform is often better for foundational, one-time-ish, cross-cutting estate
 (account/org setup, networks, the clusters themselves — including the one Crossplane
 runs on) and for teams without a Kubernetes control plane.
- **Trade-off:** Draw the boundary at "foundational vs self-service / app-adjacent."
 Terraform bootstraps the cluster, networks, and IAM (including Crossplane's own
 install and credentials); Crossplane offers the day-to-day, developer-requested
 resources on top. Using both plays to each tool's strengths: Terraform's maturity
 for the base, Crossplane's continuous self-service for the paved road.

</details>


_Previous:_ Terraform Testing and Quality · _Next:_ IaC Patterns for Platform Teams →

## IaC Patterns for Platform Teams

> You now know Terraform, state, modules, testing, and Crossplane. This final module
> assembles them into the **patterns a platform team runs in production**: a
> mono-repo structure, environment promotion (dev → staging → prod), blast-radius
> isolation, governance (PR-only, no console changes), scheduled **drift detection**,
> deliberate **module versioning**, and automated **bootstrapping** of new
> environments.

### 1. Concept

#### The reference layout: modules + environments

The pattern almost every mature Terraform estate converges on separates *reusable
building blocks* from *per-environment composition*:

```text
IaC mono-repo
├── modules/ ← reusable, versioned modules (the paved road)
│ ├── vpc/
│ ├── gke-cluster/
│ └── gcs-bucket/
├── environments/
│ ├── dev/ ← calls modules with dev vars; its OWN state
│ ├── staging/ ← calls modules with staging vars; its OWN state
│ └── prod/ ← calls modules with prod vars; its OWN state
└──.github/workflows/
 ├── plan.yaml ← runs on PR (plan + checks)
 └── apply.yaml ← runs on merge to main (apply)
```

Modules hold the *how*; environments hold the *what* (which modules, which inputs).
Each environment is a separate root module with its **own state** — the key to blast
radius (below).

#### DRY IaC: when to abstract, when not to

DRY (don't repeat yourself) is a tool, not a religion. **Abstract into a module when
the same shape recurs with a small interface; tolerate repetition when forcing DRY
would couple things that should vary independently.** Over-DRYing environments into
one clever parameterized config is how a single change takes down dev *and* prod at
once. A little duplication across `environments/*` is often *safer* than a brittle
abstraction — the duplication is a blast-radius boundary.

#### Environment promotion

A change should prove itself in low-risk environments before reaching prod:

```text
author change ─▶ apply to DEV ─▶ observe ─▶ promote to STAGING ─▶ observe ─▶ PROD
 (cheap, safe) (prod-like) (guarded)
```

Promotion is usually one of two styles:

- **Same code, different inputs:** identical module calls across environments, only
 variable values differ (region, sizes, counts). Promotion = apply the same code to
 the next environment.
- **Versioned module promotion:** environments pin module *versions*; you bump dev to
 `v1.5.0`, verify, then bump staging, then prod. Promotion = moving a version pin.

#### Blast radius management

**Blast radius** is how much a single mistake can destroy. You control it through
**state isolation**:

- **Per environment:** separate state for dev/staging/prod so a bad `dev` apply
 *cannot address* prod resources.
- **Per component:** separate state for high-risk, slow-moving layers (networking,
 IAM, the cluster) from fast-moving ones (app infra). A mistake in app infra can't
 destroy the VPC.

```text
one giant state isolated states
─────────────── ───────────────
all envs + all layers in one vs. dev/ stg/ prod/ × network/ data/ app/
 → one typo can nuke prod → a typo is contained to one small state
 → slow plans, scary applies → fast plans, bounded applies
```

#### Governance: the pipeline is the only door

Governance turns "please don't click in the console" into an enforced control:

- **PR-only changes.** All IaC changes arrive as pull requests.
- **Plan on PR, apply on merge.** CI posts the plan for review; merge triggers apply
 of that reviewed plan. Humans hold **no** prod apply credentials.
- **No manual console changes.** Enforced culturally *and* detected automatically
 (drift detection, below). The console is read-only.
- **Required reviews + policy gates.** fmt/validate/scan/policy all
 block merge.

#### Drift detection

Even with governance, drift happens — an incident, another tool, a rogue click. A
**scheduled drift-detection pipeline** runs a read-only plan on a timer and alerts
when reality diverges from code:

```bash
# nightly, per environment:
terraform plan -detailed-exitcode
# exit 0 = no drift, 2 = drift detected (alert!), 1 = error
```

`-detailed-exitcode` is the magic: exit `2` means "changes pending" (drift), which you
turn into an alert and a ticket to reconcile — deliberately, via PR, not a panicked
apply.

#### Module versioning and bootstrapping

- **Version modules; pin consumers.** Tag module releases and pin each environment to
 a version. Upgrade dev first, promote deliberately. Never let `main` of a module
 silently change prod.
- **Bootstrapping** is the automation that stands up a *new* environment from near-
 nothing: create the project/account, the state backend bucket, baseline IAM, then
 apply the environment root. A mature platform can go from "new team needs an
 environment" to a running, governed environment with minimal manual steps — the
 ultimate paved road.

---

### 2. Why it matters for platform engineering

- **This is the platform team's operating model.** Everything above — repo layout,
 promotion, isolation, governance, drift, versioning — *is* how a platform team runs
 infrastructure safely at scale. The earlier modules were the vocabulary; this is the
 sentence.
- **Blast radius is risk management.** The single highest-leverage decision you make
 is how you split state. Get it right and mistakes are survivable; get it wrong and a
 typo is an outage.
- **Governance is what makes "reproducible and auditable" true.** Without PR-only +
 drift detection, IaC quietly degrades back into hand-managed infrastructure.
- **Promotion + versioning are how you change safely.** They let you move fast on dev
 without betting prod on every change.

### 3. Mental model

**Modules are shared and versioned; environments are isolated and promoted; the
pipeline is the only door; a watchdog checks for drift.**

```text
 ┌─────────────── modules/ (versioned paved road, shared) ───────────────┐
 │ vpc @v1.4 gke @v2.1 bucket @v1.0... │
 └───────────────┬───────────────┬───────────────┬───────────────────────┘
 pin ▼ pin ▼ pin ▼
 ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ each env:
 │ environments │ │ environments │ │ environments │ - own state
 │ /dev │──▶│ /staging │──▶│ /prod │ - own backend
 └──────────────┘ └──────────────┘ └──────────────┘ - promoted in order
 ▲ promote ▲ promote ▲
 └─── PR ─▶ plan-on-PR ─▶ apply-on-merge (the ONLY door) ───┘
 ⟳ nightly drift detection alerts if reality ≠ code
```

Rules to keep:

- **Share the building blocks; isolate the deployments.**
- **One door to prod: the reviewed pipeline.**
- **Trust, but verify — on a schedule.** (Drift detection.)

### 4. Minimal implementation

You can see the whole operating model with `plan` alone — no apply, no cost. A
drift-detection check is just `plan` with a meaningful exit code:

```bash
#!/usr/bin/env bash
# drift-check.sh — alert if reality has drifted from code (read-only).
set -euo pipefail
for env in dev staging prod; do
 echo "== $env =="
 terraform -chdir="environments/$env" init -input=false -backend=false >/dev/null
 if terraform -chdir="environments/$env" plan -detailed-exitcode -lock=false >/dev/null 2>&1; then
 echo " no drift"
 else
 code=$?
 [[ $code -eq 2 ]] && echo " DRIFT DETECTED — open a reconciliation PR" || echo " plan error"
 fi
done
```

And the two-workflow governance skeleton — plan on PR, apply on merge — is the entire
"one door" pattern:

```yaml
#.github/workflows/plan.yaml (on: pull_request) → terraform plan, post for review
#.github/workflows/apply.yaml (on: push to main) → terraform apply the reviewed plan
```

That's the operating model in miniature: isolated environments, a read-only drift
watchdog, and a pipeline that is the only path to prod. The lab assembles these into a
real repo structure.

### 6. Production considerations

- **Right-size your state split.** Too coarse = big blast radius and slow plans; too
 fine = painful cross-state wiring and sprawl. Split by environment always, and by
 component where risk or change-rate differs sharply.
- **Make the pipeline the only credential holder.** Use OIDC/workload identity so CI
 authenticates to the cloud without long-lived keys, and no human has standing prod
 apply rights.
- **Drift detection must create action, not noise.** Route exit-code-2 to a ticket/
 alert with an owner, not a channel everyone mutes. Reconcile via PR.
- **Promote by version, test at each stage.** Pin module versions per environment;
 run the checks at every promotion; never skip straight to prod.
- **Automate bootstrapping, but review it.** New-environment automation is powerful
 and dangerous — it creates accounts and IAM. Gate it behind review and least
 privilege.
- **Document the operating model.** The repo README should state the rules: PR-only,
 how to promote, how drift is handled. Governance that isn't written down erodes.

### 7. Common mistakes

- **One state to rule them all.** Everything in a single state/workspace. *Why:* it's
 simplest at first. *Fix:* isolate per environment (and risky components) before the
 blast radius bites.
- **Over-DRY environments.** A single hyper-parameterized config for all envs so one
 change hits prod instantly. *Fix:* accept some duplication across `environments/*`;
 it's a safety boundary.
- **Manual "just this once" console changes.** They create silent drift and break
 reproducibility. *Fix:* PR-only culture + automated drift detection to catch
 slips.
- **Floating module references.** Environments tracking a module's `main`. *Why:*
 "always latest." *Fix:* pin versions; promote upgrades deliberately.
- **Drift detection that nobody acts on.** A nightly job whose alerts are ignored.
 *Fix:* make each drift a ticket with an owner and an SLA; reconcile via PR.
- **Humans with prod apply creds "for emergencies."** The emergency path becomes the
 normal path. *Fix:* break-glass with audit, not standing access.

### 8. Assessment

**Knowledge checks**

1. Why does each environment get its own state, and what does that protect?
2. What does `terraform plan -detailed-exitcode` return on drift, and how do you use
 it?
3. Give one case where *duplicating* config across environments is better than a DRY
 abstraction.
4. What does "plan on PR, apply on merge" enforce beyond convenience?
5. How do you promote a module upgrade from dev to prod safely?

**Concept exercise**

> Explain "blast radius" and how you'd limit it **without using the words "state,"
> "Terraform," or "workspace."** Use an analogy (e.g. bulkheads in a ship).

**Architecture / trade-off exercise**

> You inherit a single Terraform configuration with one state file managing the VPC,
> the GKE cluster, IAM, and every team's app infrastructure for *all three*
> environments. A recent `apply` meant for dev nearly destroyed a prod subnet. Design
> the target structure: how would you split state (by environment and/or component),
> how would changes flow dev → prod, and what two governance controls would you add
> first? Name one risk your new split introduces and how you'd mitigate it.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** So a mistake in one environment cannot address or destroy another's
 resources. It bounds blast radius and also speeds up plans (smaller state).
- **Q2:** Exit `0` = no changes, `2` = changes pending (drift), `1` = error. Run it on
 a schedule; treat exit `2` as a drift alert → reconciliation PR (not an auto-apply).
- **Q3:** When environments must vary independently or when a shared abstraction would
 couple them so a single change hits all envs at once. The duplication is a
 blast-radius boundary; e.g. keeping `environments/prod` separate so a dev change
 can't touch it.
- **Q4:** It makes the reviewed pipeline the only path to prod: every change is
 planned, reviewed, scanned, policy-checked, applied from CI (not laptops), and
 audited — preventing un-reviewed changes and drift.
- **Q5:** Pin module versions per environment; bump dev to the new version, run checks
 and observe; then promote the pin to staging, verify; then prod. Each step is a
 reviewed PR.
- **Architecture:** Split state at least by environment (dev/staging/prod each own
 backend) and by component within an environment (network/IAM separate from app
 infra), so the slow-moving, high-risk layers are isolated from fast-moving app
 changes. Changes flow as PRs: apply to dev, observe, promote to staging, then prod,
 via plan-on-PR/apply-on-merge. First two governance controls: (1) remove human prod
 apply credentials — pipeline-only via OIDC; (2) scheduled drift detection with
 owned alerts. New risk: more states mean cross-state references (e.g. app infra
 needs the VPC id) — mitigate with `terraform_remote_state` data sources or a
 published outputs contract, and keep the split only as fine as the risk warrants.

</details>


_Previous:_ Crossplane · _Next:_ CI/CD for Platform Teams →
