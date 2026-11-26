# 04 · Kubernetes Package Management

> **Project Applicability:** Active in Project

> **Project Note:** While this module covers Helm as a general industry tool, this project uses **Kustomize + Argo CD** (deploy/) instead of Helm for declarative Kubernetes manifest management and GitOps delivery.

> You can write Kubernetes YAML. The problem is that a real platform has to ship
> *the same workload* to dozens of teams and a handful of environments — each with
> slightly different replicas, images, and limits — without copy-pasting manifests
> and praying they stay in sync. This phase is about **packaging**: turning raw
> manifests into versioned, parameterized, distributable products that teams consume
> on demand. It is where the "golden path" you keep hearing about stops being a slide
> and becomes an artifact with a version number.

### Why this phase?

By now you can hand-write a Deployment, a Service, and an HPA. That works for one
app in one environment. It falls apart the moment you have **N apps × M
environments**: every manifest is copied, every copy drifts, and a security fix in
the "standard" Deployment has to be pasted into forty repos by hand. This is the
single most common way platform good intentions rot — the paved road exists, but
there is no mechanism to *distribute* it or *update* it.

Package management is that mechanism. It gives you three things raw YAML cannot:

- **Parameterization** — one definition, many configurations. Dev gets one replica
 and a debug image; prod gets three replicas, tight limits, and an HPA — from the
 *same* source of truth.
- **Packaging and versioning** — a workload becomes a named, versioned artifact
 (`platform-app-1.4.2`) you can publish, pin, roll back, and audit, exactly like a
 library dependency.
- **Distribution** — that artifact lives in a registry, so "adopt the golden path"
 becomes `helm install` instead of "clone this repo and edit nine files."

This is a **product** concern, not a YAML concern. The hardened chart you build in
 is the literal thing a product team consumes to get a secure,
observable, autoscaled service for free — the payload behind the self-service
experience you'll wire up in the IDP phase. Treating your workload template as a
distributed, versioned package is what lets a two-person platform team keep a
hundred services on a consistent, secure baseline.

We teach the **problem before the tool** throughout:

- **Why templating exists** — you'll feel the pain of duplicated manifests *before*
 reaching for Helm.
- **Templating vs overlays** — Helm *generates* YAML from templates; Kustomize
 *patches* YAML that already exists. Different philosophies, different sweet spots.
- **When each wins** — and how to combine them instead of fighting a religious war.
- **Distribution as a first-class concern** — charts and other artifacts travel
 through OCI registries, the same place your container images already live.

## Helm Fundamentals

> Helm is the package manager for Kubernetes: it turns a pile of templated YAML plus
> a set of values into a **release** you can install, upgrade, roll back, and
> uninstall as one unit. This module teaches the parts — charts, values, releases,
> repositories — and the lifecycle commands, so Helm stops feeling like "magic that
> generates YAML" and starts feeling like `apt`/`npm` for your cluster.

### 1. Concept

#### The problem: manifests don't scale by copy-paste

A single service needs a Deployment, a Service, probably an HPA, a
PodDisruptionBudget, a ServiceAccount, and a NetworkPolicy. That's six manifests.
Now ship that service to `dev`, `staging`, and `prod`, where only the image tag, the
replica count, and the resource limits differ. The naive answer is three copies of
six files — eighteen manifests — that are 90% identical and drift the instant someone
edits one and forgets the others.

Multiply by *every* team's *every* service and you have the core failure mode of
hand-rolled Kubernetes: **duplication with no single source of truth**. What you
actually want is *one* definition with a few knobs:

```text
one template + "dev" values → dev manifests
 + "prod" values → prod manifests
```

That is exactly what Helm provides, plus the lifecycle machinery to install and
update the result as one tracked unit.

#### Charts, values, releases, repositories

Four nouns carry the whole model:

- **Chart** — a package: a directory (or a `.tgz`) of **templates** plus **default
 values** plus metadata. It is the *definition*, like a class or a Debian package.
 It is inert until you install it.
- **Values** — the configuration you feed a chart. The chart ships sensible defaults
 in `values.yaml`; you override what you need per environment.
- **Release** — an *installed instance* of a chart with a specific set of values and
 a name, living in a namespace. Install the same chart twice with different names
 and you get two independent releases. A release has a **revision** number that
 increments on every change.
- **Repository** — an index of packaged charts you can pull from, served over HTTPS
 (a classic Helm repo) or an **OCI registry**. `helm repo add` wires
 one up the way `apt` adds a source.

> The relationship to remember: a **chart** is a class, **values** are the
> constructor arguments, and a **release** is the object you actually instantiated.
>
> Install the chart three times with three names and you have three releases from
> one class.

#### Chart structure

A chart is just a directory with conventions:

```text
platform-app/
├── Chart.yaml # name, version, appVersion, dependencies — the metadata
├── values.yaml # DEFAULT values (every key the templates can read)
├── values.schema.json # optional JSON Schema that validates user-supplied values
├── templates/ # the templated manifests
│ ├── _helpers.tpl # reusable named templates (helpers), not rendered directly
│ ├── deployment.yaml
│ ├── service.yaml
│ └── NOTES.txt # post-install message printed to the user
└── charts/ # vendored sub-charts (dependencies), if any
```

Two version fields in `Chart.yaml` trip people up:

- **`version`** — the version of the *chart* (the package). Bump it whenever the
 templates change.
- **`appVersion`** — the version of the *application* the chart deploys (e.g. the
 default image tag). Informational; bump it when the app changes.

#### Templates and the functions you'll actually use

Templates are YAML with [Go template](https://pkg.go.dev/text/template) directives in
`{{ }}`, extended by the [Sprig](https://masterminds.github.io/sprig/) function
library. Four functions do most of the work:

- **`.Values.foo`** — read a value. `.Chart`, `.Release`, and `.Capabilities` expose
 chart metadata, release info (name, namespace, revision), and cluster facts.
- **`default`** — supply a fallback: `{{.Values.replicas | default 2 }}`.
- **`required`** — fail the render with a message if a value is missing:
 `{{ required "image.repository is required".Values.image.repository }}`. This is
 how a chart refuses to produce a broken manifest.
- **`toYaml`** — serialize a values sub-tree back into YAML (for `resources`,
 `nodeSelector`, etc.), almost always paired with `nindent` for correct indentation.
- **`include`** — render a **named template** (defined in `_helpers.tpl` with
 `define`) and capture its output, so shared snippets like labels live in one place.

#### The lifecycle

Helm manages a release through four verbs, and remembers every step:

- **`helm install <name> <chart>`** — render templates with the merged values, then
 create the objects. Records **revision 1**.
- **`helm upgrade <name> <chart>`** — re-render with new values/chart and apply the
 diff. Records **revision 2, 3, …**.
- **`helm rollback <name> <revision>`** — re-apply a *previous* revision's rendered
 manifests. (Rollback itself creates a *new* revision.)
- **`helm uninstall <name>`** — delete the release's objects and its history.

Helm stores each revision's rendered manifest in a **Secret** in the release's
namespace (named `sh.helm.release.v1.<name>.v<n>`). That's why `helm history` and
`helm rollback` work with no server-side component — the state lives in the cluster,
in the open, owned by you. (Helm 2's cluster-side "Tiller" is gone; Helm 3 is a
client that talks straight to the Kubernetes API.)

#### The values hierarchy

Final values are *merged*, last-wins, in this order:

```text
chart's values.yaml (defaults shipped by the chart author)
 └─ overridden by -f my-values.yaml (your file, e.g. per environment)
 └─ overridden by -f more.yaml (later -f files win over earlier ones)
 └─ overridden by --set key=value (highest precedence)
```

So a chart ships safe defaults, each environment supplies a values file, and a
one-off `--set image.tag=abc123` pins a specific build in CI. Understanding this
ordering is how you reason about "where did this field's value actually come from?"

---

### 2. Why it matters for platform engineering

- **A chart is how you distribute the golden path.** The hardened workload template
 your platform team maintains ships as a chart. "Adopt the paved road" becomes
 `helm install`, not "clone and edit nine files." One chart, consumed by everyone.
- **Upgrades become a product capability.** When you fix a security default, you cut
 a new chart version and teams upgrade — a versioned, reviewable change, not a
 manual sweep across forty repos.
- **Rollback is a safety net you get for free.** Because Helm keeps rendered
 revisions, a bad release is one `helm rollback` away. That changes the risk profile
 of shipping.
- **Third-party software arrives as charts.** ingress-nginx, cert-manager,
 Prometheus, ArgoCD — the ecosystem you install to *build* the platform is almost
 all Helm charts. Operating them competently is table stakes.

---

### 3. Mental model

Hold this picture: a chart + values is a **function**, and a release is its **return
value**, versioned every time you call it.

```text
 VALUES (merged, last-wins)
 defaults ─▶ -f env.yaml ─▶ --set...
 │
 ▼
 CHART ─────▶ [ render templates ] ─────▶ rendered Kubernetes manifests
 (templates + (Go template + │
 defaults) Sprig funcs) ▼
 ┌───────────────────────────┐
 │ RELEASE "web" │
 │ rev 1 → rev 2 → rev 3 … │
 │ (each stored as a Secret)│
 └───────────────────────────┘
 install = create rev 1 upgrade = new rev rollback = re-apply an old rev
```

The durable rule: **charts are classes, releases are instances, revisions are
history.** Everything `helm` does is instantiate, re-instantiate, or rewind.

---

### 4. Minimal implementation

First, feel the problem Helm solves — do the simplest possible "templating" by hand.
Imagine a manifest where only the image tag changes per environment:

```bash
cat > deploy.tmpl.yaml <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata: { name: web }
spec:
 replicas: ${REPLICAS}
 selector: { matchLabels: { app: web } }
 template:
 metadata: { labels: { app: web } }
 spec:
 containers:
 - name: app
 image: nginx:${TAG}
EOF

REPLICAS=1 TAG=1.25 envsubst < deploy.tmpl.yaml | kubectl apply -f -
```

That works for one variable, but it has no defaults, no validation, no packaging, no
history, and no rollback. The moment you need "fail if `TAG` is unset" or "roll this
back," you are reinventing Helm badly. So use Helm:

```bash
# Scaffold a working chart to read and learn from
helm create demo

# Render templates locally WITHOUT touching a cluster — your fastest feedback loop
helm template demo./demo | head -n 40

# Install it as a release named "web" (records revision 1)
helm install web./demo

# Change a value and upgrade (records revision 2)
helm upgrade web./demo --set replicaCount=3

# See the history, then rewind to revision 1
helm history web
helm rollback web 1

# Remove everything the release created
helm uninstall web
```

`helm template` renders without a cluster (great for CI and review); `helm install`
renders *and* applies. Same engine, and every `install`/`upgrade`/`rollback` is a
tracked revision you can inspect and reverse.

---

### 6. Production considerations

- **Pin chart versions.** Always install with `--version`. An unpinned
 `helm install` grabs "latest," so the same command produces different results next
 week. Pin the chart version the way you pin a container digest.
- **Values belong in Git, not in your shell history.** Keep `values-<env>.yaml` under
 version control and review changes. Reserve `--set` for ephemeral CI inputs like
 the image tag of the build under test.
- **Never put secrets in plain values.** `helm get values` and the release Secret
 expose them. Use a secrets manager, External Secrets, or SOPS — not `values.yaml`.
- **Make upgrades atomic.** `helm upgrade --atomic --wait --timeout 5m` rolls back
 automatically if the release doesn't become healthy, so a bad deploy self-heals
 instead of leaving you half-upgraded.
- **Mind release-history growth.** Helm keeps every revision as a Secret. Cap it with
 `--history-max` (CLI) so long-lived releases don't accumulate thousands of Secrets.
- **CRDs are special.** Helm installs CRDs from `crds/` but does **not** upgrade or
 delete them. Plan CRD upgrades explicitly; a careless chart uninstall can orphan or
 destroy cluster-wide types.
- **Diff before you upgrade.** The `helm diff upgrade` plugin shows exactly what will
 change — treat it like `terraform plan` for releases.

---

### 7. Common mistakes

- **Confusing `version` and `appVersion`.** — Bumping the app image but leaving the
 chart `version` unchanged means consumers can't tell a new package exists. *Fix:*
 bump `version` on every chart change; use `appVersion` for the app's own version.
- **Treating `helm install` as idempotent.** — Running `install` again on an existing
 release errors with "cannot re-use a name." *Fix:* use `helm upgrade --install`
 (a.k.a. `helm upgrade -i`) so first run installs and later runs upgrade.
- **Editing released objects with `kubectl`.** — Hand-editing a Deployment Helm owns
 makes the live state diverge from the release; the next `helm upgrade` silently
 reverts you. *Fix:* change values and upgrade; let Helm own what Helm created.
- **Unpinned chart versions.** — "It worked yesterday" breaks when upstream ships a
 new chart. *Fix:* always `--version`, and record it in Git.
- **Secrets in `values.yaml`.** — They leak through `helm get values` and the release
 Secret. *Fix:* reference an external secret store; never template plaintext secrets.
- **Forgetting `helm uninstall` leaves PVCs and CRDs.** — Data volumes and custom
 resource definitions can survive an uninstall. *Fix:* check for and clean up PVCs
 and CRDs deliberately when you really mean to delete.

---

### 8. Assessment

**Knowledge checks**

1. Define chart, release, and repository, and give the one-line analogy that relates
 them.
2. A teammate runs `helm install api./chart` twice and the second run errors. What
 happened, and what single flag fixes the workflow?
3. Where does Helm store a release's revision history, and why does that matter for
 `rollback`?
4. Given `values.yaml` sets `replicas: 2`, a `-f prod.yaml` sets `replicas: 3`, and
 the command adds `--set replicas=5`, what is the final value and why?
5. What's the difference between `Chart.yaml`'s `version` and `appVersion`?

**Concept exercise**

> Explain how you'd ship *one* workload definition to three environments that differ
> only in image tag and replica count — **without using the words "Helm," "chart," or
> "template."** Describe the inputs, the thing that combines them, and the output.

**Trade-off / debugging exercise**

> A service was installed with `helm install`, then someone ran
> `kubectl edit deployment` to bump replicas during an incident. A week later a
> routine `helm upgrade` quietly reset replicas back down and caused a brown-out.
> Explain exactly why, and describe the correct way to have made that change
> permanent.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** A chart is the package/definition (class), a release is an installed
 instance of it (object) with values (constructor args), and a repository is the
 index you pull charts from (like an apt source).
- **Q2:** `helm install` is not idempotent — a release with that name already exists.
 Use `helm upgrade --install api./chart` so the first run installs and subsequent
 runs upgrade the same release.
- **Q3:** In the release's namespace as Secrets (`sh.helm.release.v1.<name>.v<n>`),
 each holding a revision's rendered manifest. `rollback` just re-applies a stored
 revision — no external state needed.
- **Q4:** `5`. Values merge last-wins: defaults (`2`) are overridden by `-f prod.yaml`
 (`3`), and `--set` has the highest precedence (`5`).
- **Q5:** `version` is the chart/package version (bump on template changes);
 `appVersion` tracks the deployed application's version (informational).
- **Debugging:** Helm's desired state still said `replicas: 2`, so `upgrade`
 re-rendered that and overwrote the manual edit. The fix was to change the value in
 the release (`helm upgrade --set replicaCount=…` or the env values file), so Helm's
 source of truth matches the intent.

</details>

---


· _Next:_ Helm Chart Development →

## Helm Chart Development

> Installing other people's charts is table stakes. The platform-engineering skill is
> **authoring** one: a reusable, hardened, self-validating chart that becomes the
> golden-path workload every team consumes. This module builds that chart — named
> templates and helpers, `values.schema.json` validation, lifecycle hooks, a
> `helm test`, and the lint → test → package → push pipeline that ships it.

### 1. Concept

#### From "a folder of templates" to a product

A chart that only you can operate is a liability. A chart that *any* team can install
to get a secure, observable, autoscaled service — without reading its internals — is
a **product**. The difference is in the craft: shared helpers so the chart is DRY,
schema validation so misuse fails loudly, tests so it's verifiable, and defaults that
are safe even when the consumer sets nothing. This module is about that craft.

#### Named templates and helpers

The same labels, names, and selectors appear in every manifest of a chart. Repeating
them is how a Service's selector drifts from its Deployment's labels and silently
sends traffic nowhere. The fix is **named templates** — reusable snippets defined
once in `templates/_helpers.tpl` and pulled in with `include`:

```text
{{/* Define a reusable "fullname" and a standard label set, once. */}}
{{- define "platform-app.fullname" -}}
{{- printf "%s-%s".Release.Name.Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "platform-app.labels" -}}
app.kubernetes.io/name: {{.Chart.Name }}
app.kubernetes.io/instance: {{.Release.Name }}
app.kubernetes.io/managed-by: {{.Release.Service }}
helm.sh/chart: {{ printf "%s-%s".Chart.Name.Chart.Version }}
{{- end -}}
```

Then every manifest reuses them:

```text
metadata:
 name: {{ include "platform-app.fullname". }}
 labels:
 {{- include "platform-app.labels". | nindent 4 }}
```

Two functions you'll pair constantly:

- **`include "name".`** renders a named template and returns a string (unlike the
 older `template` action, `include` can be piped). The trailing `.` passes the
 current context so the helper can read `.Release`, `.Values`, etc.
- **`toYaml` + `nindent N`** serializes a values sub-tree to YAML and indents every
 line by `N` spaces, so `resources: {{- toYaml.Values.resources | nindent 4 }}`
 drops the user's whole `resources` block in with correct indentation.

#### Validating input with `values.schema.json`

Templates fail in ugly ways when a value is the wrong type (`replicaCount: "two"`) or
missing. A **`values.schema.json`** (standard JSON Schema) sits next to `values.yaml`
and Helm validates the merged values against it on every `install`, `upgrade`,
`template`, and `lint`:

```json
{
 "$schema": "https://json-schema.org/draft-07/schema",
 "type": "object",
 "required": ["image"],
 "properties": {
 "replicaCount": { "type": "integer", "minimum": 1 },
 "image": {
 "type": "object",
 "required": ["repository"],
 "properties": { "repository": { "type": "string" } }
 }
 }
}
```

Now `--set replicaCount=two` is rejected *before* anything reaches the cluster, with
a clear message. Schema validation is the difference between a chart that trusts its
users and one that *protects* them — exactly the posture a platform chart needs.

#### Hooks: run work at lifecycle points

Sometimes you need an action *around* a release, not just objects *in* it: run a
database migration before the new version starts, or warm a cache after install.
**Hooks** are ordinary manifests annotated with `helm.sh/hook`:

```text
metadata:
 annotations:
 "helm.sh/hook": pre-upgrade
 "helm.sh/hook-weight": "0"
 "helm.sh/hook-delete-policy": before-hook-creation,hook-succeeded
```

The hook events fire in order: `pre-install`, `post-install`, `pre-upgrade`,
`post-upgrade`, `pre-delete`, `post-delete`, plus `pre-rollback`/`post-rollback`.
Hook *weight* orders multiple hooks; the *delete policy* controls cleanup. Use hooks
sparingly — they run outside the normal reconcile and can wedge a release if they
hang — but a migration Job is their canonical, legitimate use.

#### `helm test`: a release that verifies itself

A chart can ship its own smoke test: a Pod template under `templates/tests/`
annotated with `"helm.sh/hook": test`. `helm test <release>` runs it against the
*live* release and reports pass/fail:

```text
# templates/tests/test-connection.yaml
apiVersion: v1
kind: Pod
metadata:
 name: "{{ include "platform-app.fullname". }}-test"
 annotations: { "helm.sh/hook": test }
spec:
 restartPolicy: Never
 containers:
 - name: curl
 image: curlimages/curl:8.10.1
 command: ["curl"]
 args: ["-sf", "http://{{ include "platform-app.fullname". }}:{{.Values.service.port }}/readyz"]
```

If the Pod exits 0, the test passes. This is how a consumer gains confidence that
"the release is actually serving," not just "the objects were created."

#### Testing templates without a cluster: `helm-unittest`

`helm test` needs a running release. To test *rendering logic* fast — "does setting
`autoscaling.enabled=true` produce an HPA?" — use the
[`helm-unittest`](https://github.com/helm-unittest/helm-unittest) plugin. It asserts
on rendered YAML with no cluster, so it belongs in CI as the first gate. Example
assertion: with `autoscaling.enabled: false`, assert the HPA document is *not*
rendered.

#### Packaging and distribution

A finished chart is packaged into a versioned tarball and pushed to a registry:

```text
helm lint./platform-app # static checks + schema validation
helm template./platform-app # render; eyeball or pipe to a policy check
helm unittest./platform-app # fast, cluster-free template assertions
helm package./platform-app # → platform-app-1.0.0.tgz
helm push platform-app-1.0.0.tgz oci://<registry>/charts # distribute
```

That pipeline — **lint → unit test → package → push** — is the chart author's
equivalent of a library's build-and-publish. covers the OCI push in
depth.

---

### 2. Why it matters for platform engineering

- **This chart *is* the golden path.** The hardened `platform-app` chart you build
 here is the concrete payload behind "adopt the paved road." A team sets five
 values and gets a secure, observable, autoscaled workload — the exact deliverable
 the IDP phase wraps a self-service UI around.
- **Security becomes a default, not a checklist.** When non-root, read-only root
 filesystem, and dropped capabilities are baked into the chart, every consumer gets
 them for free. You've moved security *left of the developer* entirely.
- **Schema validation is a support-ticket deflector.** A chart that rejects bad input
 with a clear message is a chart your two-person platform team doesn't have to debug
 over Slack.
- **Versioned charts make fleet-wide change tractable.** Fix a default once, bump the
 chart version, and teams upgrade on their own cadence — governed, reviewable, and
 auditable.

---

### 3. Mental model

Think of a chart as a **typed function with a safety harness**:

```text
 values.schema.json
 (the TYPE SIGNATURE: rejects bad input at the door)
 │ validates
 ▼
 values.yaml ──▶ TEMPLATES ──▶ rendered, HARDENED manifests
 (+ user (_helpers.tpl = (non-root, RO-rootfs,
 overrides) shared private dropped caps, probes,
 functions) HPA/PDB/NetworkPolicy)
 │
 hooks ─────────┤ run work AROUND the release (migrations, etc.)
 tests ─────────┘ verify the LIVE release (helm test)

 Package the whole thing → versioned.tgz → push to a registry → teams install it.
```

The durable rule: **a good chart protects its consumer.** It validates their input,
ships safe defaults they can't forget to set, and can prove it works.

---

### 4. Minimal implementation

Scaffold a chart, then watch schema validation and rendering do their jobs — all
cluster-free:

```bash
helm create platform-app # a working chart skeleton to edit down
rm -rf platform-app/templates/tests # we'll write our own

# Add a tiny schema that requires an integer replicaCount
cat > platform-app/values.schema.json <<'EOF'
{
 "$schema": "https://json-schema.org/draft-07/schema",
 "type": "object",
 "properties": { "replicaCount": { "type": "integer", "minimum": 1 } }
}
EOF

# Valid input renders; the schema is happy
helm template demo./platform-app --set replicaCount=2 >/dev/null && echo "OK: valid"

# Invalid input is rejected BEFORE the cluster is ever touched
helm template demo./platform-app --set replicaCount=two || echo "Rejected by schema"
```

The second command fails with a schema error, not a broken manifest. You just moved a
whole class of mistakes from "3 a.m. incident" to "instant, local, obvious." The lab
turns this skeleton into a production-grade, hardened chart.

---

### 6. Production considerations

- **Harden by default; let consumers opt *out*, not *in*.** Non-root, read-only root
 filesystem, `allowPrivilegeEscalation: false`, and `drop: [ALL]` should be the
 defaults. A team that genuinely needs a writable path sets one value — but the safe
 path is the default path.
- **Pin the schema strictly, loosen deliberately.** Use `required`, types, and
 `additionalProperties: false` where you can. Every gap in the schema is a way for a
 consumer to produce a broken release you'll be paged about.
- **Keep hooks idempotent and bounded.** A migration hook must be safe to re-run and
 must time out. A hook that hangs blocks the whole release.
- **Template defensively.** Guard optional blocks (`{{- with.Values.resources }}`),
 use `required` for values with no safe default, and never let a missing value
 render an empty-but-valid-looking manifest.
- **Version the chart like an API.** Bump `version` on every change; treat removing a
 value or changing a default as a breaking change with a migration note.
- **Lint and unit-test in CI.** `helm lint`, `helm template | <policy>`, and
 `helm unittest` are fast and catch regressions before a chart ever reaches a
 cluster. Sign and provenance-check published charts.

### 7. Common mistakes

- **Copy-pasting labels and selectors into every template.** — They drift, and a
 Service stops matching its Pods. *Fix:* define `selectorLabels`/`labels` helpers in
 `_helpers.tpl` and `include` them everywhere.
- **Wrong indentation with `toYaml`.** — `toYaml` with the wrong `nindent` (or
 `indent` vs `nindent`) produces invalid YAML. *Fix:* use `{{- toYaml x | nindent N }}`
 and render with `helm template` to verify.
- **No `values.schema.json`.** — Bad input becomes a cryptic template error or a
 broken object. *Fix:* ship a schema; require what must be set and type everything.
- **Security as an opt-in value.** — `securityContext` defaulting to empty means most
 consumers run privileged. *Fix:* make hardened settings the default; require a
 conscious override to relax them.
- **Hooks that can't be re-run or never finish.** — A non-idempotent or unbounded
 migration hook wedges upgrades. *Fix:* make hooks idempotent, set timeouts, and set
 a sensible `hook-delete-policy`.
- **Skipping `helm test`.** — "The objects exist" is not "the service works." *Fix:*
 ship a test Pod that actually hits a health endpoint of the live release.

### 8. Assessment

**Knowledge checks**

1. Why use `include` + a named template instead of repeating labels in each manifest?
 What does the trailing `.` do?
2. What does `values.schema.json` catch, and at what point in the lifecycle?
3. Name three hardened defaults a platform chart should ship, and the exact fields
 that set them.
4. What's the difference between `helm test` and `helm-unittest`, and where does each
 belong?
5. When would you reach for a hook, and what makes a hook safe?

**Concept exercise**

> Describe how you'd give a hundred teams a secure, autoscaled workload they can adopt
> by setting five values — **without using the words "Helm" or "chart."** Name the
> inputs, the validation, the safe defaults, and the output.

**Architecture / trade-off exercise**

> Your `platform-app` chart defaults to `readOnlyRootFilesystem: true`. A team's app
> writes temp files and now crash-loops on your chart. List the options (relax the
> default for everyone, expose a value, mount an `emptyDir`, reject the app) and argue
> for one. What does your choice say about who owns the security baseline?

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** DRY and correctness — one definition of names/labels/selectors keeps the
 Service selector and Deployment labels in lockstep. The trailing `.` passes the
 current render context so the helper can read `.Release`, `.Values`, `.Chart`.
- **Q2:** Type and shape errors in the merged values (wrong type, missing required,
 out-of-range), validated on `install`/`upgrade`/`template`/`lint` — before objects
 reach the cluster.
- **Q3:** e.g. `runAsNonRoot: true` + numeric `runAsUser`; `readOnlyRootFilesystem:
 true`; `allowPrivilegeEscalation: false`; `capabilities.drop: [ALL]`;
 `seccompProfile.type: RuntimeDefault`.
- **Q4:** `helm-unittest` asserts on *rendered templates* with no cluster (fast CI
 gate); `helm test` runs a Pod against a *live release* to prove it serves. Use both.
- **Q5:** For work that must happen around the release (a migration before the new
 version). A safe hook is idempotent, bounded by a timeout, and has a sane delete
 policy.
- **Trade-off:** Best answer is usually expose a value *and* mount a writable
 `emptyDir` at `/tmp` by default, keeping `readOnlyRootFilesystem: true`. Relaxing
 the default for everyone forfeits the baseline; the platform should own the safe
 default and offer a narrow, explicit escape hatch.

</details>


_Previous:_ Helm Fundamentals
· _Next:_ Kustomize →

## Kustomize

> Kustomize takes the opposite bet from Helm: instead of *generating* YAML from
> templates, it starts with plain, valid Kubernetes manifests (a **base**) and
> **patches** them per environment (**overlays**) — no template language, no `{{ }}`.
> This module teaches bases, overlays, patches, generators, and transformers, and
> builds the `dev`/`prod` overlay pattern you'll use constantly in GitOps.

### 1. Concept

#### A different answer to the same problem

 framed the core problem: one workload, many environments, and no
single source of truth if you copy manifests. Helm solves it by **templating** —
parameterize the YAML and render it with values. Kustomize solves it by
**composition and patching** — keep one set of *real* manifests and describe the
*differences* for each environment as overlays. No new language, no rendering step:
what you check in is valid Kubernetes YAML that `kubectl` already understands.

#### Resources, bases, and overlays

Three nouns:

- **Resource** — an ordinary Kubernetes manifest (a Deployment, a Service). Nothing
 Kustomize-specific; it's valid YAML you could `kubectl apply` directly.
- **Base** — a directory with a `kustomization.yaml` that lists `resources`. It's the
 environment-agnostic definition — the common truth every environment shares.
- **Overlay** — a directory whose `kustomization.yaml` references the base (and adds
 patches, extra resources, name prefixes, etc.). One overlay per environment.

```text
base/ # the shared, valid manifests
├── kustomization.yaml # resources: [deployment.yaml, service.yaml]
├── deployment.yaml
└── service.yaml

overlays/
├── dev/ # base + "dev is small and verbose"
│ ├── kustomization.yaml
│ └── replicas-patch.yaml
└── prod/ # base + "prod is bigger and adds an HPA"
 ├── kustomization.yaml
 ├── replicas-patch.yaml
 └── hpa.yaml
```

The overlay *includes* the base and layers changes on top. You never copy the base;
you reference it. Fix a container port in the base and every overlay inherits the fix.

#### Patches: strategic-merge vs JSON

Overlays change the base through **patches**. Two flavors:

- **Strategic-merge patch** — a partial manifest that is *merged* into the base by
 Kubernetes' field-aware merge rules. You write just the fields you want to change,
 in the natural shape of the object. Kubernetes knows that `containers` is a list
 keyed by `name`, so it merges by name rather than replacing the whole list:

```text
# overlays/prod/replicas-patch.yaml — only the deltas
apiVersion: apps/v1
kind: Deployment
metadata:
 name: web
spec:
 replicas: 3
```

- **JSON patch (RFC 6902)** — a precise, operation-based edit (`add`, `replace`,
 `remove`) against a path. Reach for it when a merge is ambiguous or you must target
 one list element exactly:

```text
# overlays/prod/kustomization.yaml (excerpt)
patches:
 - target: { kind: Deployment, name: web }
 patch: |-
 - op: replace
 path: /spec/template/spec/containers/0/image
 value: registry.example.com/web:1.4.2
```

Rule of thumb: **strategic-merge for the common case** (it reads like the object);
**JSON patch for surgical precision** (a specific array index, a remove).

#### Generators: config and secrets with built-in rollouts

`configMapGenerator` and `secretGenerator` build ConfigMaps/Secrets from literals or
files — and, crucially, append a **content hash** to the name
(`app-config-7f9c2b`). When the content changes, the name changes, so any Deployment
referencing it is *forced to roll* (new pod template), fixing the classic bug where
editing a ConfigMap leaves pods running the old values:

```text
configMapGenerator:
 - name: app-config
 literals:
 - LOG_LEVEL=info
```

#### Transformers: rewrite the whole set at once

Transformers apply a change across *all* resources an overlay produces:

- **`images`** — override image name/tag/digest without editing the Deployment:
 `images: [{ name: web, newTag: 1.4.2 }]`.
- **`namespace`** — drop every resource into a target namespace.
- **`namePrefix`/`nameSuffix`** — e.g. prefix `prod-` to every object name.
- **`commonLabels`/`labels`** and **`commonAnnotations`** — stamp labels/annotations
 onto everything (and, for `commonLabels`, into selectors too).
- **`replicas`** — set replica counts by resource name.

Transformers are why an overlay can retarget an entire app to a namespace, retag its
image, and label everything — in a few declarative lines, no patch files.

#### Running it: `kustomize build` and `kubectl apply -k`

Kustomize renders by *building* an overlay into a flat stream of manifests:

```text
kustomize build overlays/prod # print the final YAML
kubectl apply -k overlays/prod # build AND apply (kustomize is built into kubectl)
kubectl kustomize overlays/prod # same build, via kubectl, no apply
```

Because the output is just manifests, you can pipe `kustomize build` into a policy
check, a diff, or `kubectl apply` — it composes with everything that speaks YAML.

> `kubectl` bundles its *own* copy of Kustomize, which can lag the standalone
> `kustomize` binary. For newer fields, install and use the standalone CLI and treat
> `kubectl -k` as the convenience path.

---

### 2. Why it matters for platform engineering

- **It's the native GitOps format.** Argo CD and Flux both render Kustomize overlays
 directly. "Promote dev → prod" becomes a small, readable overlay diff in a pull
 request — exactly the change unit GitOps wants.
- **No templating means low cognitive load.** Everything in the repo is real YAML a
 reviewer can read without mentally executing a template. For teams that own a
 *handful* of apps, that clarity is often worth more than Helm's power.
- **Safe fleet-wide edits.** A platform team can patch a base (add a security context,
 a label, a sidecar) and every overlay inherits it — without forking manifests.
- **It pairs with Helm.** You can render a third-party Helm chart and then Kustomize
 the output to enforce your standards — overlays as a post-processor.

---

### 3. Mental model

Think **inheritance by patching**: a base class and per-environment subclasses that
override only what differs.

```text
 ┌───────────────────────────┐
 │ BASE │
 │ deployment.yaml (valid) │
 │ service.yaml (valid) │
 └─────────────┬─────────────┘
 references │ references
 ┌───────────────────────┐ │ ┌───────────────────────┐
 │ overlay: dev │ │ │ overlay: prod │
 │ + replicas = 1 │◀┘ └▶ + replicas = 3 │
 │ + image tag:dev │ + image tag:1.4.2 │
 │ │ + adds hpa.yaml │
 └───────────┬───────────┘ └───────────┬──────────┘
 ▼ ▼
 kustomize build dev kustomize build prod
 → flat, valid manifests → flat, valid manifests
 │ │
 └──────── kubectl apply -k ────┘

 No templates. The repo always holds real YAML; overlays describe the DIFFERENCES.
```

The durable rule: **Helm renders; Kustomize patches.** Kustomize never invents a
value — it only transforms manifests that already exist.

---

### 4. Minimal implementation

Create one real manifest as a base, then an overlay that changes just the replica
count — no templating anywhere:

```bash
mkdir -p base overlays/dev

cat > base/deployment.yaml <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata: { name: web }
spec:
 replicas: 2
 selector: { matchLabels: { app: web } }
 template:
 metadata: { labels: { app: web } }
 spec:
 containers:
 - name: web
 image: nginx:1.27
EOF

cat > base/kustomization.yaml <<'EOF'
resources:
 - deployment.yaml
EOF

# The overlay references the base and patches ONLY the delta
cat > overlays/dev/kustomization.yaml <<'EOF'
resources:
 -../../base
replicas:
 - name: web
 count: 1
images:
 - name: nginx
 newTag: "1.27-alpine"
EOF

kustomize build overlays/dev # base, with replicas=1 and the image retagged
```

The base is untouched, valid YAML. The overlay declared *differences* (one replica,
a different tag) and Kustomize produced the combined result. That's the whole idea.

---

### 6. Production considerations

- **Keep the base environment-agnostic.** No namespaces, no environment-specific
 images or replica counts in the base. If it differs per environment, it belongs in
 an overlay. A leaky base forces copy-paste later.
- **Prefer generators for config, and keep the hash behavior.** Letting
 `configMapGenerator` append content hashes is a feature, not noise — it guarantees
 rollouts on config change. Disabling it (`disableNameSuffixHash`) silently
 reintroduces the stale-config bug.
- **Pin the Kustomize version in CI.** `kubectl`'s built-in Kustomize and the
 standalone binary can render differently. Pin one version so builds are
 reproducible, and render in CI rather than relying on `kubectl -k` locally.
- **Don't put real secrets in `secretGenerator` literals.** They land in Git in plain
 text (base64 is not encryption). Use SOPS, Sealed Secrets, or External Secrets and
 generate only references.
- **Review the built output, not just the overlay.** `kustomize build | kubectl diff`
 shows what will actually change. Patches can interact in surprising ways; diff the
 result.
- **Mind patch brittleness.** JSON patches target paths and indexes; a base change can
 invalidate them. Keep patches minimal and prefer strategic-merge where possible.

### 7. Common mistakes

- **Environment specifics leaking into the base.** — A namespace or `:prod` image in
 the base defeats the whole model. *Fix:* base holds only the shared truth; put all
 differences in overlays.
- **Editing a ConfigMap in place and expecting a rollout.** — Pods keep the old values
 because nothing in the pod template changed. *Fix:* use `configMapGenerator` so the
 name hash changes and forces a new rollout.
- **Reaching for JSON patches by default.** — Index-based paths are brittle and hard to
 read. *Fix:* use strategic-merge for the common case; reserve JSON patch for precise
 list surgery or `remove`.
- **Assuming `kubectl -k` == latest Kustomize.** — The embedded version lags, so a
 field that works in the standalone CLI errors under `kubectl`. *Fix:* install the
 standalone `kustomize`, pin it, and build with it in CI.
- **Secrets in overlays, in plaintext.** — base64 literals in Git are not secret.
 *Fix:* keep secret material out of the repo; integrate a real secrets solution.
- **Overlapping, order-dependent patches.** — Multiple patches touching the same field
 produce confusing results. *Fix:* keep patches small and single-purpose; diff the
 build.

### 8. Assessment

**Knowledge checks**

1. In one sentence, how does Kustomize's approach differ from Helm's?
2. What does `configMapGenerator`'s name-hash behavior fix, and what breaks if you
 disable it?
3. When would you choose a JSON patch over a strategic-merge patch?
4. What belongs in a base, and what belongs in an overlay?
5. Why can `kubectl apply -k` and the standalone `kustomize build` produce different
 output?

**Concept exercise**

> Explain how you'd ship one app to `dev` and `prod` that differ only in replica count
> and image tag — **without using the words "template," "values," or "Helm."**
> Describe the shared definition, the per-environment differences, and how they
> combine.

**Trade-off / debugging exercise**

> A team edited a ConfigMap referenced by their Deployment and bumped the image, then
> ran `kubectl apply -k overlays/prod`. The new image rolled out but the app still
> logs at the old level. Explain why the config change didn't take effect and how
> Kustomize is designed to prevent exactly this.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** Helm *generates* manifests from a template language + values; Kustomize
 starts from real manifests and *patches/transforms* them — no templating.
- **Q2:** The name hash forces a rollout when config content changes; disabling it
 (`disableNameSuffixHash`) means editing a ConfigMap leaves pods on stale values.
- **Q3:** When you must target a specific list element by index or `remove` a field —
 precision a field-aware merge can't express cleanly.
- **Q4:** Base: the environment-agnostic shared manifests. Overlay: everything that
 differs per environment (replicas, image tag, namespace, extra resources, labels).
- **Q5:** `kubectl` embeds its own (often older) Kustomize; a newer standalone binary
 supports fields/behaviors the embedded one doesn't, so builds can diverge.
- **Debugging:** The Deployment referenced the ConfigMap by a fixed name, and editing
 its data didn't change the pod template, so no rollout happened. A
 `configMapGenerator` appends a content hash to the name, so changed content yields a
 new name and an automatic rollout.

</details>


_Previous:_ Helm Chart Development
· _Next:_ Helm vs Kustomize →

## Helm vs Kustomize

> Helm and Kustomize are constantly framed as rivals. They're not — they solve
> overlapping problems with opposite philosophies: Helm **generates** manifests from
> templates and packages them for distribution; Kustomize **patches** manifests that
> already exist, with no templating. This module gives you a decision framework for
> which to reach for, and shows how to **combine** them instead of picking a side.

### 1. Concept

#### Two philosophies, one goal

Both tools exist to kill manifest duplication. They disagree on *how*:

- **Helm templates.** You write YAML with `{{ }}` placeholders and ship default
 **values**; `helm` renders the template into manifests at install time. The source
 in your repo is *not* valid Kubernetes YAML — it's a program that produces YAML.
 In exchange you get parameterization, a package format, versioning, a repository,
 and lifecycle management (install/upgrade/rollback/history).
- **Kustomize patches.** You keep *real*, valid manifests (a **base**) and describe
 per-environment **differences** as overlays. There is no template language and no
 render-time logic — just merge and transform. In exchange you get transparency
 (everything in the repo is apply-able YAML) and low cognitive load.

Neither is "more correct." They optimize different things: Helm optimizes
**distribution and flexibility**; Kustomize optimizes **clarity and simplicity**.

#### What Helm does that Kustomize doesn't

- **Packaging and distribution.** A chart is a versioned artifact you publish to a
 repository or OCI registry and others install by name and version.
 Kustomize has no package or registry concept — you consume a base by referencing
 its files (usually via Git).
- **Parameterization with logic.** Conditionals, loops, functions, computed values,
 `required`/`default`, schema validation. When a single artifact must flex across
 *many unknown consumers*, templating expresses that cleanly.
- **Lifecycle management.** Releases, revisions, `rollback`, hooks, and `helm test`
 are a release-management layer Kustomize simply doesn't have (it hands a flat
 stream of manifests to `kubectl`/Argo/Flux and stops there).

#### What Kustomize does that Helm doesn't (well)

- **Patching manifests you don't own.** Given raw YAML — a vendor's manifests, a
 rendered chart, an upstream example — Kustomize layers changes without forking or
 templatizing it. Doing the same in Helm means wrapping it in a chart.
- **Zero templating cognitive load.** Reviewers read plain YAML, not a template they
 must mentally execute. For a team with a handful of apps, that transparency is
 often worth more than Helm's power.
- **No render step to trust.** What you commit is what applies (after merges). There's
 no `{{ }}` indentation footgun and no "works until a value is empty" surprise.

#### When each wins

```text
Reach for HELM when … Reach for KUSTOMIZE when …
────────────────────── ───────────────────────────
you DISTRIBUTE software to consumers you own the manifests and just need
you don't control (a product, an OSS per-environment variants (dev/stg/prod)
chart, an internal golden-path package)

you need parameterization with LOGIC you want everything in the repo to be
(conditionals, loops, computed values, plain, valid, apply-able YAML with no
schema validation) templating to reason about

you want lifecycle management you need to patch manifests you DON'T
(releases, rollback, history, hooks, own (a vendor's YAML, a rendered chart)
helm test) without forking them

you're installing third-party software a small team wants the lowest-ceremony
(ingress-nginx, cert-manager, Argo CD) path and minimal cognitive load
```

A useful heuristic: **Am I producing a package for others, or configuring manifests
for myself?** Producing → Helm. Configuring → Kustomize.

#### Combining them (the pragmatic answer)

You don't have to choose. A common, powerful pattern is **Helm chart as base,
Kustomize overlay for environment differences**:

- The platform team ships the hardened chart (one versioned, tested artifact).
- A consuming team renders it and applies a *tiny* Kustomize overlay for the handful
 of things their environment changes (a label, a namespace, an extra annotation, a
 sidecar) — without forking the chart or drowning in chart values.

Two ways to wire it:

```text
# 1) Render with Helm, then patch the output with Kustomize
helm template app./chart > base/rendered.yaml
kubectl apply -k overlays/prod # overlay references rendered.yaml + patches

# 2) Let Kustomize inflate the chart natively (needs the helm plugin)
kustomize build --enable-helm overlays/prod # kustomization.yaml has a helmCharts: block
```

#### How Argo CD sees both

Argo CD renders both natively: point an Application at a Helm chart (with
values) *or* a Kustomize path, and it produces manifests and reconciles them to the
cluster. It even supports the combination (Helm charts inflated through Kustomize, or
charts with Kustomize post-rendering). So "Helm vs Kustomize" is rarely a platform
mandate — GitOps tooling treats them as interchangeable rendering front-ends, and you
can use the right one per app.

---

### 2. Why it matters for platform engineering

- **You will operate both, forever.** Third-party platform components ship as Helm
 charts; many teams' app config is cleanest as Kustomize overlays. Fluency in both —
 and in combining them — is the actual job, not allegiance to one.
- **The decision is a developer-experience decision.** Handing a five-app team a
 50-value chart when they needed a three-line overlay is a cognitive-load mistake.
 Matching the tool to the consumer *is* platform product thinking.
- **It de-risks the religious war.** Teams burn weeks arguing Helm vs Kustomize. A
 clear framework ("distribute → Helm, configure → Kustomize, and here's how to
 combine them") ends the argument and lets people ship.
- **It sets up GitOps.** drives whichever one you chose. Knowing how Argo
 renders each means your packaging choice and your delivery system fit together.

---

### 3. Mental model

Put them on one axis — **generate vs transform** — and let the job pick the point:

```text
 GENERATE (templating) TRANSFORM (patching)
 Helm ◀───────────────────────────────────────────────────────▶ Kustomize

 "I ship a package to consumers "I own these manifests and need
 I don't control, with logic and per-environment variants, in plain
 a version number." apply-able YAML, no templating."

 COMBINE: Helm renders the base ──▶ Kustomize patches the environment deltas
 (one versioned artifact) (a tiny, readable overlay per env)

 Decision test: Producing a package for others? → Helm
 Configuring manifests for myself? → Kustomize
 Both at once? → Chart base + overlay
```

The durable rule: **Helm is a packaging system; Kustomize is a configuration
transformer.** They're complementary layers, not competitors — and Argo CD will run
whichever you pick.

---

### 4. Minimal implementation

Deploy the *same* trivial app two ways and feel the difference in source shape. With
Helm, the source is a template that needs rendering:

```bash
helm template app./helm-app --set replicaCount=3 | head -n 20 # {{ }} → YAML
```

With Kustomize, the source is already valid YAML; the overlay only states the delta:

```bash
# overlays/prod/kustomization.yaml declares: resources: [../../base], replicas: [{name: web, count: 3}]
kubectl kustomize overlays/prod | head -n 20 # real YAML in, real YAML out
```

Same running result (three replicas of one app), two philosophies: Helm *produced*
the manifest from a template; Kustomize *transformed* a manifest that already
existed. The lab deploys one app **three** ways — Helm, Kustomize, and Helm+Kustomize
— so you can compare them head to head.

### 6. Production considerations

- **Pick per use case, not per religion.** Distributing the golden-path workload →
 Helm chart. A team configuring their own three services → Kustomize overlays.
 Mandating one everywhere creates friction somewhere.
- **Standardize the *combination* pattern if you mix them.** If teams render charts
 and patch with Kustomize, pick one approach (post-render vs `helm template` +
 overlay vs Argo's native support) and document it, so every repo looks the same.
- **Keep secrets out of both.** Neither encrypts anything. Values files and
 `secretGenerator` literals both leak plaintext into Git. Use a real secrets
 solution regardless of tool.
- **Pin versions on both sides.** Pin chart versions *and* the Kustomize/`kubectl`
 version used to render, or "it worked yesterday" returns from either direction.
- **Render in CI and diff.** Whatever the tool, produce the manifests in CI
 (`helm template`, `kustomize build`) and run policy checks and `kubectl diff`
 before applying. Argo CD does this continuously; mirror it in pipelines.

### 7. Common mistakes

- **Treating it as a holy war.** — Teams waste weeks arguing instead of shipping.
 *Fix:* apply the framework (distribute → Helm, configure → Kustomize, combine when
 useful) and move on.
- **Templating everything, even what you own.** — A full chart for a single app you
 control adds a template language you must mentally execute for no distribution
 benefit. *Fix:* if you're not distributing it, a Kustomize overlay is often simpler.
- **Forking a third-party chart to change two fields.** — Now you own a fork and its
 upgrades forever. *Fix:* keep the chart as-is and layer a Kustomize overlay (or use
 chart values / post-render) for the deltas.
- **Re-implementing Helm in Kustomize.** — Piling on patches and generators to fake
 parameterization for many unknown consumers. *Fix:* if you need real logic and
 distribution, that's Helm's job.
- **Assuming you must choose one.** — Picking a single tool org-wide and contorting
 every use case into it. *Fix:* combine them, and let Argo CD render whichever fits.

### 8. Assessment

**Knowledge checks**

1. In one sentence each, what does Helm optimize for and what does Kustomize optimize
 for?
2. Give a concrete job where Helm clearly wins, and one where Kustomize clearly wins.
3. Describe the "Helm base + Kustomize overlay" pattern and a situation where it beats
 either tool alone.
4. How does Argo CD treat Helm and Kustomize, and why does that defuse the "which one"
 debate?
5. Why is "fork the chart to change two fields" an anti-pattern, and what's the fix?

**Concept exercise**

> Explain to a teammate when to template a workload versus when to patch it —
> **without naming Helm or Kustomize.** Frame it around *distributing a package* vs
> *configuring manifests you own*.

**Architecture / trade-off exercise**

> Your platform ships a hardened chart. A product team needs the same
> workload but with one extra sidecar and a team-specific annotation in prod only.
> Compare three approaches — (a) add sidecar support to the chart's values, (b) fork
> the chart, (c) render the chart and apply a Kustomize overlay — and recommend one.
> What does your choice optimize for, and what does it cost?

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** Helm optimizes distribution and flexible parameterization (packaging +
 templating + lifecycle); Kustomize optimizes clarity and simplicity (plain YAML +
 overlays, no templating).
- **Q2:** Helm wins for distributing a versioned golden-path chart or installing
 ingress-nginx; Kustomize wins for a team producing dev/stg/prod variants of
 manifests they own, or patching a vendor's raw YAML.
- **Q3:** Helm renders one versioned, tested base; a small Kustomize overlay applies
 the handful of environment deltas. It beats pure Helm when you'd otherwise add many
 niche values, and pure Kustomize when you still want a distributed, versioned base.
- **Q4:** Argo CD renders both natively (and the combination), reconciling the output.
 So packaging choice is per-app, not a platform-wide mandate.
- **Q5:** A fork means owning upstream's maintenance and upgrades forever for a tiny
 change. Fix: keep the chart intact and layer an overlay / use values / post-render.
- **Trade-off:** (a) is best if the sidecar is a *reusable platform capability* (bake
 it into the chart behind a value); (c) is best if it's *team-specific* (keep it in
 the team's overlay, chart stays generic); (b) is almost never right. The choice is
 really "is this a platform concern or a team concern?"

</details>


_Previous:_ Kustomize
· _Next:_ OCI Artifacts and Distribution →

## OCI Artifacts and Distribution

> The registry that stores your container images can store *far* more: Helm charts,
> SBOMs, signatures, provenance attestations, even Wasm modules. The OCI specs turned
> container registries into a **universal, content-addressable store for platform
> artifacts**. This module shows how charts travel as OCI artifacts (`helm push`/
> `pull oci://`), how ORAS pushes anything else, and why one distribution plane for
> everything is a platform superpower.

### 1. Concept

#### A registry is a content-addressable object store

Under the hood, an OCI registry doesn't know or care about "images." It stores three
kinds of things, addressed by **digest** (a SHA-256 of the content):

- **Blobs** — opaque bytes (a tarball layer, a chart archive, a JSON document).
- **A manifest** — a small JSON document that lists a `config` blob and an ordered set
 of `layers` (blobs), each tagged with a **media type** that says what it is.
- **Tags** — human-friendly names (`1.0.0`) that point at a manifest digest.

An "image" is just one *convention* on top of this: a manifest whose config media type
is `application/vnd.oci.image.config.v1+json` and whose layers are filesystem tarballs.
Change the media types and the *same* machinery stores something else entirely. That's
the key insight: **the registry is generic; "image" is one artifact type among many.**

#### OCI artifacts: everything beyond images

The [OCI Image](https://github.com/opencontainers/image-spec) and
[Distribution](https://github.com/opencontainers/distribution-spec) specs formalize
this. An **artifact** is any manifest whose `config.mediaType` (or, in OCI 1.1, an
`artifactType`) marks it as "not a runnable image." Registries that implement the spec
can therefore store:

- **Helm charts** (`application/vnd.cncf.helm.chart.content.v1.tar+gzip`),
- **SBOMs** (SPDX/CycloneDX documents describing an image's contents),
- **Signatures and attestations** (cosign/Sigstore, SLSA provenance),
- **Wasm modules**, Terraform modules, policy bundles, ML models, and more.

One registry, one auth model, one replication story — for *all* of it.

#### Helm charts as OCI artifacts

Helm 3.8+ treats OCI registries as a first-class chart repository. There's no separate
`index.yaml` to host; the registry *is* the index:

```text
helm package./platform-app # → platform-app-1.0.0.tgz
helm push platform-app-1.0.0.tgz oci://<registry>/charts
# stored at <registry>/charts/platform-app:1.0.0 as an OCI artifact

helm show chart oci://<registry>/charts/platform-app --version 1.0.0
helm pull oci://<registry>/charts/platform-app --version 1.0.0
helm install web oci://<registry>/charts/platform-app --version 1.0.0
```

The chart's `version` becomes the OCI tag. `helm registry login` handles auth the same
way `docker login` does — because it's the same registry API.

#### ORAS: push *anything* to a registry

[ORAS](https://oras.land/) ("OCI Registry As Storage") is the generic CLI for
artifacts that aren't images or charts. It pushes files as blobs with media types you
choose:

```text
oras push <registry>/sboms/web:1.0.0 \
 --artifact-type application/vnd.example.sbom \
 sbom.spdx.json:application/spdx+json
# pull it back anywhere with:
oras pull <registry>/sboms/web:1.0.0
```

Where `helm push` is chart-specific, ORAS is the Swiss-army knife: SBOMs, config
bundles, test fixtures, signed metadata — any bytes you want distributed through the
registry you already run.

#### Attaching metadata: the referrers graph

Supply-chain metadata is most useful *attached to the thing it describes*. OCI 1.1
adds a **`subject`** field: an artifact manifest can declare that it *refers to*
another manifest (an image, a chart). The registry's **Referrers API** then lets you
ask "what SBOMs/signatures/attestations are attached to this image digest?"

```text
image:1.0.0 (digest sha256:abc…)
 ├── refers ◀── SBOM (subject = sha256:abc…)
 ├── refers ◀── cosign signature
 └── refers ◀── SLSA provenance attestation
```

This is how `cosign sign`/`cosign attest` and `oras attach` work: they push a new
artifact whose `subject` is the image, so the signature and SBOM travel *with* the
image and are discoverable by digest — no side database required.

#### The platform distribution pattern

Put it together and a platform gets **one distribution plane**:

```text
CI builds → pushes to ONE registry:
 the image (app:1.0.0)
 + its SBOM (attached by digest)
 + its signature (cosign, attached by digest)
 + the golden-path chart (oci://…/charts/platform-app:1.0.0)

Clusters/consumers pull by digest; admission verifies signatures before running.
```

Everything the platform ships — code, config, and the metadata that makes it
trustworthy — flows through infrastructure you already operate for images.

---

### 2. Why it matters for platform engineering

- **One plane to secure and operate.** Auth, RBAC, quotas, retention, geo-replication,
 and air-gap mirroring that you already run for images now cover charts and
 supply-chain metadata too. You don't stand up a second system for chart hosting.
- **The golden-path chart becomes a real dependency.** Teams `helm install
 oci://…/charts/platform-app --version 1.4.2` exactly like pulling a library. Pin it,
 audit it, roll it forward — it's a versioned artifact in the registry.
- **Supply-chain security gets a home.** SBOMs, signatures, and provenance live *next
 to* the artifacts they describe, discoverable by digest. That's the foundation for
 "only signed, SBOM-backed images run here" admission policy (Phase on security).
- **It's how GitOps and clusters consume packages.** Argo CD and clusters pull charts
 and images from the registry; a single registry endpoint is far simpler to secure
 and mirror than a sprawl of HTTP chart repos and ad-hoc file servers.

---

### 3. Mental model

Think of the registry as a **content-addressable warehouse**, and every artifact as a
labeled crate referenced by the hash of its contents:

```text
 ┌──────────────────────── OCI REGISTRY ────────────────────────┐
 │ content-addressable store: everything keyed by sha256 digest │
 │ │
 │ MANIFEST (json) ── config.mediaType / artifactType ──┐ │
 │ │ lists blobs + media types │ │
 │ ├── blob: fs layer → it's an IMAGE │ │
 │ ├── blob: chart.tgz → it's a HELM CHART │ │
 │ ├── blob: sbom.json → it's an SBOM │ │
 │ └── subject: sha256:abc… → ATTACHED to another one │ │
 │ ▼ │
 │ tag "1.0.0" ───────────────▶ points at a manifest digest │
 └───────────────────────────────────────────────────────────────┘

 The media type is the ONLY thing that makes bytes "an image" vs "a chart" vs
 "an SBOM." Same warehouse, different labels.
```

The durable rule: **a registry stores artifacts, not images.** Images, charts, SBOMs,
and signatures are all just manifests + blobs + media types — and digests make them
immutable and verifiable.

### 4. Minimal implementation

Run a throwaway registry, then push and pull a chart as an OCI artifact — no cloud, no
account:

```bash
# A local OCI registry in one container
docker run -d -p 5000:5000 --name registry registry:2

# Package a chart and push it; the chart version becomes the OCI tag
helm package./platform-app # → platform-app-1.0.0.tgz
helm push platform-app-1.0.0.tgz oci://localhost:5000/charts

# Pull it back and inspect — the registry IS the index
helm show chart oci://localhost:5000/charts/platform-app --version 1.0.0
helm pull oci://localhost:5000/charts/platform-app --version 1.0.0
```

That's the whole distribution loop: a versioned, content-addressed chart living in the
same kind of registry as your images. The lab extends it with a cluster install and an
ORAS-pushed SBOM.

### 6. Production considerations

- **Pin by digest, not just tag.** Tags are mutable; a digest (`@sha256:…`) is the
 exact bytes. Production installs and admission policies should reference digests so a
 retag can't swap what runs.
- **Sign and verify.** Sign charts and images (cosign/Sigstore), store the signatures
 as referrers, and *verify* at admission. An unsigned-but-pushed artifact is just a
 convenient way to ship an attack.
- **Registry RBAC, retention, and GC.** Scope who can push to `charts/` vs `images/`,
 set tag-retention/immutability, and run garbage collection — artifacts accumulate
 fast and untagged blobs cost money.
- **Air-gapped and multi-region.** One of OCI's biggest wins: mirror/replicate the
 *whole* artifact set (images + charts + metadata) with the same tooling. Plan
 pull-through caches and promotion between registries.
- **Mind registry support levels.** The OCI 1.1 Referrers API and arbitrary
 `artifactType`s aren't uniformly supported; some managed registries lag. Confirm
 your registry supports what your signing/SBOM workflow needs, or use the tag-schema
 fallback.
- **Rate limits and availability.** If every pod pull and every CI job hits one
 registry, it's a availability and cost hotspot. Cache aggressively; treat the
 registry as tier-1 infrastructure.

### 7. Common mistakes

- **Treating OCI charts like HTTP repos.** — Running `helm repo add` against an
 `oci://` URL, or expecting an `index.yaml`. *Fix:* there's no `repo add` for OCI; you
 reference `oci://…/chart --version X` directly, and `helm registry login` for auth.
- **Pushing unsigned, unscanned artifacts.** — "It's in the registry" is mistaken for
 "it's trustworthy." *Fix:* sign (cosign), scan, and attach an SBOM; verify at
 admission.
- **Pinning only by tag.** — A mutable tag gets re-pushed and your "known-good" release
 changes under you. *Fix:* record and deploy the digest.
- **Forgetting the chart version *is* the tag.** — Pushing two different charts with the
 same `version` overwrites the tag. *Fix:* bump `Chart.yaml` `version` on every change;
 treat it as immutable once published.
- **No retention/GC policy.** — The registry balloons with old tags and dangling blobs.
 *Fix:* set retention and run garbage collection from day one.
- **Assuming every registry supports every artifact type.** — The Referrers API or a
 custom `artifactType` silently fails on an older registry. *Fix:* check support; fall
 back to the referrers tag schema where needed.

### 8. Assessment

**Knowledge checks**

1. What actually makes a set of bytes in a registry "an image" versus "a Helm chart"
 versus "an SBOM"?
2. How do you consume a chart from an OCI registry, and how does that differ from a
 classic HTTP Helm repo?
3. What is the `subject` field / Referrers API for, and what does it enable?
4. Why pin a production deployment to a digest rather than a tag?
5. Name three artifact types — beyond images — that a platform might distribute through
 one OCI registry.

**Concept exercise**

> Explain how one registry can distribute your app, its configuration package, and the
> metadata that proves it's trustworthy — **without using the words "Docker" or
> "image."** Describe blobs, manifests, media types, and digests.

**Architecture / trade-off exercise**

> Your org hosts Helm charts on an HTTP chart repo (a static site with `index.yaml`)
> and images in a container registry. Make the case for consolidating charts into the
> OCI registry: what do you gain (security, ops, supply chain), what could break
> (tooling that expects `repo add`, registries lacking Referrers support), and how
> would you migrate without a flag day?

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** The media types (and OCI 1.1 `artifactType`) on the manifest's config/layers.
 Same manifest+blobs machinery; the labels decide what it is.
- **Q2:** Reference it directly: `helm install name oci://registry/charts/app
 --version X` (with `helm registry login` for auth). No `helm repo add`, no hosted
 `index.yaml` — the registry is the index.
- **Q3:** `subject` links an artifact (SBOM, signature, provenance) to the manifest it
 describes; the Referrers API lists everything attached to a digest — so metadata
 travels with the artifact and is discoverable without a side database.
- **Q4:** Tags are mutable and can be re-pushed; a digest is the exact immutable bytes,
 so deploying/verifying by digest guarantees you run precisely what you reviewed.
- **Q5:** e.g. Helm charts, SBOMs (SPDX/CycloneDX), cosign signatures, SLSA provenance
 attestations, Wasm modules, Terraform/policy bundles.
- **Trade-off:** Gains: one auth/RBAC/retention/replication plane, supply-chain
 metadata attached by digest, simpler air-gap mirroring. Risks: tooling/CI that
 assumes `repo add`/`index.yaml`, and registries without Referrers/`artifactType`
 support. Migrate by dual-publishing (HTTP repo + OCI) for a deprecation window, then
 cut consumers over.

</details>


_Previous:_ Helm vs Kustomize
· _Next phase:_ 08 · GitOps →
