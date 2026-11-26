# 11 · Platform SRE

> **Project Applicability:** Active in Project — Directly applied via **Pyrra** (SLO-as-code, replacing Sloth), **Robusta + Telegram** (incident alerting), and **chaos/fault-injection** experiments on **k3d** hub-spoke clusters.

> You have built a platform — clusters, GitOps, a portal, observability, security.
> Now you have to **keep it up** for every team that depends on it. A platform team
> runs at a **higher reliability bar than any single app team**, because when the
> platform is down, *every* stream-aligned team is down at once. This phase is how
> you operate a platform like a Site Reliability Engineer: SLOs for your own
> services, relentless toil elimination, incident command, capacity planning, chaos
> testing, and disaster recovery.

## Why this phase?

Everything before this phase was about *building* capabilities. This phase is about
*running* them under the weight of production and many teams. The shift in mindset
is large and specific:

- **Your blast radius is the whole org.** An app team's outage affects one product.
 A platform outage — Argo CD stops syncing, the registry is unreachable, secrets
 stop propagating — blocks *every* team that builds on you, simultaneously. That is
 why a platform's reliability target is higher, and why the discipline here is
 borrowed wholesale from Google's SRE practice.
- **Toil is the enemy.** Platform teams drown in manual, repetitive operational work
 — creating namespaces, rotating secrets by hand, babysitting cluster upgrades. SRE
 gives you a way to *measure* that toil and a mandate to *automate it away* so the
 team scales with adoption instead of collapsing under it.
- **Reliability is engineered, not hoped for.** SLOs turn "is the platform healthy?"
 into a number. Error budgets turn reliability into something you can *spend*.
 Incident command turns chaos into a process. Chaos engineering finds the weakness
 before your users do. DR makes "the cluster is gone" a drill, not a catastrophe.

This phase builds directly on your earlier work: platform SLOs extend
 and
Project 3; the incident lab runs against the
Project 2 Argo CD platform; and DR protects the
clusters you stood up in Projects 1 and 2. You are now the SRE **for the platform
itself**.

## Platform SRE Fundamentals

> A platform team is Site Reliability Engineering for *other engineers*. When your
> platform wobbles, every stream-aligned team wobbles with it — so your reliability
> bar is **higher** than any single app team's. This module defines platform SRE,
> explains the blast-radius problem, and introduces the discipline's central enemy:
> **toil**, the manual repetitive work you must measure and automate away.

### 1. Concept

#### SRE, applied to the platform itself

Site Reliability Engineering (SRE) is Google's name for *treating operations as a
software problem*: you run production to explicit reliability targets, you cap the
amount of manual work you tolerate, and you automate everything else. Classic SRE
teams run *application* services. **Platform SRE** points the same discipline at the
platform — the clusters, GitOps controllers, registries, secret operators, and
portals that *other teams* build on.

The methods are identical to app SRE — SLOs, error budgets, incident response,
capacity planning. What changes is **who your users are** and **what an outage
costs**. Your users are engineers, and your outage is an *outage multiplier*.

#### The higher reliability bar: blast radius

Here is the defining fact of platform SRE:

```text
An app team's outage: A platform team's outage:
 one product is down EVERY team's delivery is down

 payments-api 500s Argo CD stops syncing → nobody can deploy
 → payments customers hurt registry unreachable → no image pulls, no new pods
 secrets stop syncing → apps fail on next restart
 cluster API down → nothing can be changed at all
```

When a platform service fails, the failure **fans out** to all consumers at once.
Fifty teams are blocked by one incident. That is why a platform's SLO targets are
typically *stricter* than the services running on it — a 99.9% platform supporting
teams that each want 99.9% is already the ceiling on what those teams can achieve,
because your downtime is included in *their* downtime. You are in everyone's
critical path, so you must be more reliable than any one of them.

> The rule to internalize: **a platform is only as trustworthy as its worst
> critical-path dependency.** If teams cannot rely on your paved road being up, they
> build their own — and your platform has failed as a product.

#### The four responsibilities of platform SRE

Platform SRE work organizes into four reinforcing areas, which are the rest of
this phase:

- **SLOs and error budgets** — define "working" as a number for every
 platform service, and let the budget govern how fast you change things.
- **Toil reduction** (this module) — measure the manual operational load and
 automate it away so the team scales with adoption.
- **Capacity planning** — make sure there are enough nodes of the
 right shape, without paying for idle ones.
- **Incident management** — detect, respond to, mitigate, and learn
 from failures with a repeatable process.

They reinforce each other: good SLOs tell you *when* an incident is happening;
incident postmortems generate *toil-reduction* and *capacity* work; eliminating
toil frees the time you need to do the other three well.

#### Toil: the central enemy

**Toil** is Google's term for a specific kind of work. It is operational work tied
to running a service that is:

- **manual** — a human runs it;
- **repetitive** — you have done it before and will again;
- **automatable** — a machine could do it;
- **tactical / reactive** — interrupt-driven, not strategic;
- **devoid of enduring value** — the service is no better after than before;
- **O(n) with growth** — it scales linearly with users, traffic, or teams.

Toil is *not* "work I dislike." Answering a hard design question, writing a new
controller, or debugging a novel failure is engineering, even when it is tedious.
The test is the list above — especially **"scales linearly with growth"** and
**"leaves nothing better behind."** Manually creating a namespace for every new team
is toil: the hundredth one teaches you nothing and takes as long as the first.

Why obsess over it? Because toil **grows with adoption**. A successful platform adds
teams; if onboarding each team is manual, your ops load grows with your success
until the team is 100% firefighting and 0% building — the death spiral of a
platform team. SRE's answer is blunt: **cap toil** (Google's guidance is to keep it
below ~50% of a team's time) and spend the rest *engineering toil away*.

#### Measuring toil

You cannot manage what you do not measure. Toil is measured as a **fraction of team
time**:

```text
toil % = (hours spent on toil) / (total working hours) over a window (e.g. a sprint)
```

The practical method: for a sprint or two, every engineer tags their time as
**toil** or **engineering/project** work (a simple tally in a shared sheet is
enough). You will usually find a few categories dominate. Then you rank those
categories by `hours × frequency` and attack the top of the list with automation —
the same "start from observed pain" move you used for the platform as a whole in
, now pointed at your *own* operations.

#### Where platform toil comes from

The usual top offenders on a Kubernetes platform:

```text
toil source manual form automation that kills it
────────────────────────────── ───────────────────────── ─────────────────────────
onboarding a new team hand-create namespace, GitOps + templates /
 RBAC, quotas, limits a "new team" generator
secret creation / rotation kubectl create secret, External Secrets Operator
 rotate by hand
cluster / addon upgrades click through consoles, IaC + staged rollout,
 manual node drains automated canary upgrades
responding to the same alert manual restart every time a runbook, then an operator
certificate renewal renew + redeploy by hand cert-manager
access requests edit RBAC per request self-service + policy as code
```

Notice the pattern: nearly every entry is removed by something you already built
earlier in this course. Platform SRE is where that earlier work pays reliability
dividends — **automation is the primary tool against toil**, and you have been
accumulating automation the whole time.

---

### 2. Why it matters for platform engineering

- **It is the economic case for the platform.** The platform's whole promise is
 leverage: a small team multiplying many teams. Toil destroys leverage — if ops
 load grows linearly with adoption, the platform stops scaling exactly when it
 succeeds. Measuring and capping toil protects the leverage.
- **It sets the reliability expectation correctly.** Framing the blast radius makes
 teams (and leadership) understand why platform reliability investment is not
 gold-plating — it is the floor under everyone else's reliability.
- **It makes the team sustainable.** A team at 80% toil is burning out and cannot do
 the project work (SLOs, capacity, chaos, DR) that *prevents the next fire*. The
 toil budget is how you protect time to engineer.
- **It prioritizes ruthlessly.** "Which automation should we build next?" stops
 being a matter of taste and becomes "which toil category costs the most hours?" —
 a data-driven backlog.

---

### 3. Mental model

Think of a platform team as a tank with a **leak** (toil) and an **inflow** of
engineering time. Reliability and new capabilities are built from whatever time is
left after the leak:

```text
 total team time
 │
 ┌───────────┴────────────┐
 ▼ ▼
 TOIL (the leak) ENGINEERING (the build)
 manual, repetitive, SLOs, automation, capacity,
 O(n) with growth chaos, DR, new capabilities
 │ │
 ▼ ▼
 grows with adoption is what PREVENTS future toil
 unless you plug it

 If toil > ~50%, the leak outruns the build:
 the team spends all day bailing and never fixes the hull.

 SRE move: MEASURE the leak → cap it → spend saved time
 welding it shut (automation) → leak shrinks → repeat.
```

The insight: toil is not just annoying, it is **self-reinforcing**. Time lost to
toil is time you cannot spend eliminating toil, so it compounds. The only way out is
to deliberately protect engineering time and point it at the biggest leaks first.

---

### 4. Minimal implementation

You do not need a tool to start — you need a tally. The smallest useful toil
measurement is a table each engineer fills in for one sprint:

```text
task type minutes times/sprint toil-minutes
─────────────────────── ─────────── ─────── ──────────── ────────────
create namespace+RBAC toil 20 8 160
rotate a leaked secret toil 15 3 45
debug novel CNI bug engineering — — —
write upgrade runbook engineering — — —
restart stuck ESO pod toil 10 6 60
─────────────────────── ─────────── ─────── ──────────── ────────────
 toil total this sprint: 265 min
```

Then compute the fraction and rank the categories:

```bash
## toil fraction for one engineer, 2-week sprint at ~60 productive hours
echo "scale=3; 265 / (60*60) " | bc # minutes of toil / minutes available
## → 0.073 → ~7% of this person's time, this sprint
##
# Ranked by cost, the backlog writes itself:
## 1. namespace+RBAC onboarding (160 min) → template it (GitOps generator)
## 2. restart stuck ESO pod (60 min) → add a liveness probe + runbook/operator
## 3. secret rotation (45 min) → External Secrets Operator
```

That is the entire method: **tag, total, rank, automate the top item, repeat next
sprint.** No dashboard required to begin — though at scale you graph the toil
fraction over time and treat a rising line as a reliability risk. The lab turns this
into a reusable worksheet you can run on a real team.

---

### 6. Production considerations

- **Budget toil explicitly, like an SLO.** Pick a cap (Google uses ~50%) and track
 the fraction per sprint. When it trends up, that is a signal to stop taking on new
 scope and invest in automation — the same discipline as an error-budget policy.
- **Protect the engineering time.** Toil is interrupt-driven and will expand to fill
 all available hours. Shield project time with an on-call/interrupt rotation so one
 person absorbs the toil while the rest build the automation that removes it.
- **Not all toil is worth automating.** If automating a task costs more than the toil
 it saves over its lifetime, do not. Estimate `toil-saved-over-a-year` versus
 `build-plus-maintain cost` before committing.
- **Beware automation that becomes toil.** A brittle script that needs babysitting is
 just toil wearing a costume. Automation needs the same reliability standard as the
 platform; otherwise you have moved the leak, not plugged it.
- **Make toil visible to leadership.** A graph of "team time spent on toil" is the
 single most effective argument for headcount or for pausing feature work to pay
 down operational debt.

### 7. Common mistakes

- **Treating toil as "just part of the job."** — Teams normalize manual work and
 never measure it, so it grows invisibly until they are 90% firefighting. *Fix:*
 measure the fraction every sprint and treat a rising line as an incident in slow
 motion.
- **Confusing toil with all boring work.** — Labeling hard-but-novel engineering as
 "toil" and trying to automate the unautomatable. *Fix:* apply the six-point test;
 if it is not repetitive *and* automatable *and* value-less, it is engineering.
- **Automating the wrong thing first.** — Building the fun automation instead of the
 expensive one. *Fix:* rank by `hours × frequency` and attack the top of the list.
- **Automation without an owner or SLO.** — A clever script nobody maintains rots
 into a new source of toil and outages. *Fix:* treat internal automation as a
 product with an owner, tests, and monitoring.
- **Ignoring the blast-radius argument when prioritizing.** — Spending reliability
 effort evenly instead of on critical-path services. *Fix:* weight by how many
 teams a failure blocks; the registry and Argo CD matter more than a nice-to-have
 dashboard.

## Platform SLOs

> App teams write SLOs for their services. A platform must write SLOs for **its own
> services** — the GitOps controller, the API server, the secret operator, the build
> pipeline — because teams build on them and deserve a published promise. This module
> takes the SLO machinery from 
> and points it at the platform itself: which SLIs to choose, the error-budget policy
> that decides **freeze versus investigate**, and how to communicate status to teams.

(SLIs, error budgets, burn rate, Pyrra (project choice; Sloth in upstream reference)) and the Argo CD work from
Project 2 and
Project 3. Docker for the lab.

### 1. Concept

 gave you the mechanics: an **SLI** is good events ÷ valid events, an
**SLO** is a target for it, the **error budget** is `1 − SLO`, **burn rate** is how
fast you spend it, and **multi-window, multi-burn-rate** alerts page on fast burn and
ticket on slow burn — all generated by **Pyrra (project choice; Sloth in upstream reference)** from one spec. This module assumes
all of that and asks a different question: **what should a *platform* measure, and
what do you do when the budget runs out?**

#### What is a platform SLI? The user is a team

The SLO burn-rate framing is illustrated in SLO burn rate.

For an app, "good" means a user got a fast, correct response. For a platform service,
the "user" is a **stream-aligned team** (or its automation), so "good" means *the
capability the team depends on worked*:

- For Argo CD, good means **the API answered** and **syncs succeeded** — teams can
 deploy.
- For the secret operator, good means **secrets landed fresh** — apps start with
 valid credentials.
- For the build pipeline, good means **builds finished in reasonable time** — teams
 are not blocked waiting.

The discipline is the same as 11.7: pick an **event-based, user-visible** indicator,
never an internal proxy like controller CPU. A platform SLO that is green while teams
cannot deploy is worse than useless — it hides the outage behind a healthy-looking
dashboard.

#### The platform SLO catalog

A mature platform publishes an SLO for every service on a team's critical path. A
representative catalog (your lab builds the first four as Pyrra (project choice; Sloth in upstream reference) specs):

```text
service SLI (good ÷ valid) objective (30d)
─────────────────── ───────────────────────────────────────── ──────────────
GitOps sync latency syncs completing within 60s ÷ all syncs 95%
Argo CD availability API requests served OK ÷ all API requests 99.9%
Secret propagation ESO syncs succeeding fresh ÷ all ESO syncs 95% within 10m
Cluster API server apiserver requests OK ÷ all (managed SLA) 99.95%
Build pipeline builds finishing within 10m ÷ all builds 95%
Backstage portal portal requests served OK ÷ all requests 99.5%
```

Three things to notice:

- **Not every SLO is availability.** Latency SLOs (sync within 60s, build within
 10m) matter as much as uptime — a GitOps controller that is "up" but takes ten
 minutes to sync is failing its users. Model these as a latency SLI: good = events
 faster than the threshold, using a histogram bucket.
- **The targets differ by blast radius.** The cluster API server (everything depends
 on it) is held to 99.95%; the portal (convenient but not in the deploy path) to
 99.5%. Reliability investment follows criticality — spend your effort where an
 outage blocks the most teams.
- **Some targets are inherited.** The managed control-plane SLO (e.g. 99.95%) is your
 cloud provider's SLA; you adopt it and add your own margin, because you cannot be
 more available than your foundation.

#### Error-budget burn for a platform: the freeze decision

The error budget turns platform reliability into a spendable number, and for a
platform the spending decision has teeth. When a platform SLO is burning budget fast
or the budget is exhausted, you face a choice:

```text
budget healthy → ship freely: upgrade Argo CD, roll addons, change defaults
fast burn / near-zero → FREEZE risky platform changes; the platform IS the incident
budget exhausted (slow) → stop feature work on the platform; INVESTIGATE and repay
 reliability before resuming change
```

The nuance versus an app team: when a *platform* freezes, it freezes **changes to the
platform** — not the teams building on it. A common failure is to confuse the two and
block every team's deploys because *your* budget is spent. Your error-budget policy
governs *your* change rate, so you stop destabilizing an already-struggling platform,
while keeping the teams' paved road open.

**Freeze versus investigate** is the burn-rate distinction from 11.7 applied here:

- **Fast burn (page):** an active incident — the platform is actively failing teams.
 Freeze changes *and* respond now. You are bleeding budget.
- **Slow burn (ticket):** a chronic drain — a flaky webhook, a slow sync creeping up.
 No page, but the budget is leaking. Investigate and fix before it becomes a fast
 burn, and hold new risky changes.

#### Communicating SLO status to teams

A platform SLO that only the platform team can see is half a product. Because your
users are other teams, **publishing** the status is part of the service:

- A **status page / dashboard** per platform service showing current SLO, budget
 remaining, and recent incidents — so a team debugging a slow deploy can see "Argo
 CD sync latency budget is at 12%, known degradation" instead of filing a ticket.
- **Published objectives** in the service catalog (Backstage, ): every
 platform service lists its SLO so teams know what to expect and can set their own
 SLOs accordingly (your 99.9% is a hard ceiling on their 99.9%).
- **Proactive comms on budget events:** when a platform SLO goes into freeze, teams
 hear it from you (a banner, a channel post) — not by guessing why deploys feel
 slow. Transparency is how a platform keeps trust through an incident.

---

### 2. Why it matters for platform engineering

- **SLOs define the platform's promise.** Without published SLOs, "reliable" is an
 opinion. With them, teams know exactly what they can build on, and you know exactly
 when you are failing them.
- **The budget governs your change rate.** A platform ships constantly — upgrades,
 new defaults, controller changes. The error budget is the objective signal for when
 to push and when to hold, replacing gut feeling and politics.
- **It turns "the platform feels flaky" into data.** Burn-rate graphs make vague
 complaints concrete and prioritized, and make your reliability wins visible.
- **It builds trust as a product.** Publishing SLOs and status — including bad news —
 is what separates a platform teams *choose* from one they route around.

---

### 3. Mental model

Each platform service has a **budget meter** that every team watching the platform
can read. Incidents drain it; your change rate is throttled by how full it is.

```text
 each platform service = one budget meter (published, not hidden)

 Argo CD availability [■■■■■■■■■□] 87% budget left → ship freely
 GitOps sync latency (60s) [■■■□□□□□□□] 22% budget left → slow down, investigate
 Secret propagation (10m) [■□□□□□□□□□] 4% budget left → FREEZE platform changes
 (teams still deploy)

 fast burn → PAGE + freeze platform changes + respond (it's an incident)
 slow burn → TICKET + investigate + hold risky changes
 budget ok → change the platform as fast as you like

 The meter is a shared language with your users: they can SEE why
 a deploy feels slow, instead of filing a ticket to ask.
```

The move to remember: **a platform's error budget throttles the platform team's own
risk-taking, and the meter is published so teams trust the road even on a bad day.**

---

### 4. Minimal implementation

A platform SLO is a Pyrra (project choice; Sloth in upstream reference) `PrometheusServiceLevel` just like an app's — the only
difference is the metric comes from a platform component. Here is Argo CD
availability as errored API requests ÷ total, at 99.9%:

```yaml
version: "prometheus/v1"
service: argocd
labels:
 tier: platform
slos:
 - name: argocd-api-availability
 objective: 99.9
 description: Argo CD API server answers requests so teams can deploy.
 sli:
 events:
 error_query: sum(rate(grpc_server_handled_total{grpc_service=~"argocd.*",grpc_code!="OK"}[{{.window}}]))
 total_query: sum(rate(grpc_server_handled_total{grpc_service=~"argocd.*"}[{{.window}}]))
 alerting:
 name: ArgoCDApiAvailability
 page_alert:
 labels: { severity: page }
 ticket_alert:
 labels: { severity: ticket }
```

A latency SLO (GitOps sync within 60s) is the same shape, but "good" is a histogram
bucket and "bad" is everything slower:

```yaml
 sli:
 events:
 # bad = syncs that took LONGER than the 60s bucket boundary
 error_query: >-
 sum(rate(argocd_app_reconcile_count[{{.window}}]))
 - sum(rate(argocd_app_reconcile_bucket{le="60"}[{{.window}}]))
 total_query: sum(rate(argocd_app_reconcile_count[{{.window}}]))
```

Run `sloth generate` (as in 11.7) and you get the recording rules at every window and
the multi-window burn-rate `page`/`ticket` alerts — for a *platform* service, with no
new math to learn. The lab builds four of these and renders them.

```bash
docker run --rm -v "${PWD}:/data" ghcr.io/slok/sloth:v0.16.0 \
 generate -i /data/argocd-availability-slo.yaml -o /data/argocd-availability-rules.yaml
```

---

### 6. Production considerations

- **Inherit what you cannot control.** For managed components (the cluster API
 server), adopt the provider's SLA as your SLO and monitor against it; you cannot be
 more available than your foundation, so set teams' expectations accordingly.
- **Latency SLOs need real histogram buckets.** The `le` you threshold on must be a
 configured bucket boundary, or the query silently returns nothing. Confirm the
 component actually exposes a bucket at your target (60s, 600s) before trusting the
 SLO.
- **Write the error-budget policy *before* the incident.** Agree in advance — with
 teams — what a freeze means, who declares it, and when it lifts. An unwritten policy
 becomes an argument during the worst possible moment.
- **Keep SLOs as code in GitOps.** Pyrra (project choice; Sloth in upstream reference) specs in Git, rendered to `PrometheusRule`s
 and deployed by Argo CD. Review SLO changes like any other platform
 change — a looser objective is a reliability decision, not a config tweak.
- **Publish status, including bad news.** A per-service SLO/budget dashboard and a
 catalog entry turn your reliability into a product teams can see and trust. Hiding a
 degradation erodes trust faster than the degradation itself.
- **A few meaningful SLOs beat many.** One availability and one latency SLO per
 critical service, each owned and runbooked, is better than a wall of
 indicators nobody watches.

### 7. Common mistakes

- **No SLO for the platform's own services.** — The team monitors app SLOs but never
 publishes one for Argo CD or the registry, so "is the platform healthy?" has no
 answer. *Fix:* an SLO for every service on a team's critical path.
- **Freezing teams instead of the platform.** — The platform's budget is spent, so
 the team blocks everyone's deploys. *Fix:* the error-budget policy throttles *your*
 change rate; keep the teams' paved road open while you stabilize.
- **Availability-only thinking.** — A GitOps controller is "up" but syncs take ten
 minutes; the SLO is green while teams wait. *Fix:* add latency SLOs with a real
 histogram bucket.
- **SLIs on controller internals.** — Alerting on Argo CD CPU or pod restarts instead
 of whether syncs succeed. *Fix:* event-based, user-visible SLIs (did the team's
 deploy work?).
- **An error-budget policy nobody enforces.** — The budget hits zero and the team
 keeps shipping risky upgrades. *Fix:* a written, agreed policy with real
 consequences, declared and lifted transparently.
- **Hidden status.** — Teams discover a platform degradation by guessing. *Fix:*
 publish SLO/budget dashboards and proactively announce freezes.

## Platform Incident Management

> When the platform breaks, every team is watching and the pressure is high. The
> difference between a chaotic scramble and a calm recovery is **process**: a clear
> severity scale, one person in command, disciplined communication, a runbook for the
> failure mode, and a blameless postmortem that makes the next incident less likely.
> This module gives you that process and applies it to a real platform failure.

incident), the Project 2 Argo CD platform, a local
[kind](https://kind.sigs.k8s.io/) cluster, and `kubectl`.

### 1. Concept

#### The incident lifecycle

An incident is any unplanned degradation of a platform service against its SLO. The
response follows a fixed lifecycle so nobody has to invent the steps under pressure:

```text
DETECT → TRIAGE → MITIGATE → RESOLVE → LEARN
 │ │ │ │ │
 │ │ │ │ └─ blameless postmortem, action items
 │ │ │ └─ confirm SLO recovered, close incident
 │ │ └─ stop the bleeding (restore service) BEFORE root cause
 │ └─ scope & impact: how many teams? which capability? assign severity + IC
 └─ a burn-rate alert fires, not a human noticing
```

The order matters. **Mitigate before you diagnose:** restore service first (roll
back, restart, fail over) and find the root cause later. Teams need the platform
working; the forensic analysis belongs in the postmortem, not the outage.

#### Severity: how many teams are blocked?

For a platform, severity is defined by **blast radius** — the number of
teams affected and how badly:

```text
sev name meaning example
─── ───────────── ───────────────────────────────────────── ─────────────────────────
P0 critical ALL teams blocked; core capability down cluster API server down;
 Argo CD cannot sync at all
P1 major a major capability degraded for many teams secret propagation failing;
 builds failing org-wide
P2 partial partial degradation; a subset affected one cluster's ingress slow;
 portal read-only
P3 minor minor issue, workaround exists, low urgency a dashboard stale;
 non-critical addon flaky
```

Severity drives the response: a **P0 pages immediately**, pulls in an incident
commander, and opens a status-page incident; a **P3** is a ticket handled in business
hours. Classify early and re-classify as you learn — it is normal to open at P1 and
downgrade once you understand the scope.

#### The incident commander and supporting roles

Under pressure, the biggest failure mode is **everyone debugging and nobody
coordinating**. The fix is explicit roles, borrowed from emergency response:

- **Incident Commander (IC)** — owns the incident, not the fix. Decides, delegates,
 keeps the timeline, and protects the responders' focus. The IC may not touch a
 terminal at all; their job is coordination and decisions.
- **Operations / subject expert** — the person(s) actually running commands to
 mitigate, directed by the IC.
- **Communications lead** — owns updates to teams and stakeholders (status page,
 chat, email) so the IC and ops are not interrupted to answer "any update?".
- **Scribe** (often the IC early on) — records the timeline: every action, time, and
 observation, for the postmortem.

On a small platform team one person may wear several hats, but the **IC role must
always be named and known** — "who is the IC?" should have an instant answer. The IC
is a role, not a rank: a junior engineer can command an incident a principal is
debugging.

#### Communication during the incident

Your users are other teams, and silence is corrosive — teams that hear nothing assume
the worst and flood your channels. Communicate on three surfaces:

```text
surface audience cadence content
──────────── ─────────────────── ─────────────────── ────────────────────────────
status page all teams / org on change + regular service, impact, severity, ETA
chat (Slack) responders + teams live coordination + quick updates
email leadership / wide at start, resolve summary, impact, next steps
```

Rules that keep comms useful under stress:

- **Say impact, not internals.** "Deploys are paused platform-wide; no data loss;
 next update in 30 min" beats "the webhook TLS cert expired on repo-server."
- **Promise the next update time, every time.** A predictable "next update at 14:30"
 stops the stream of "any news?" interruptions.
- **One voice.** The comms lead publishes; responders do not freelance updates.

#### Runbooks: every failure mode has one

A **runbook** is a short, tested document for a specific failure: symptoms, how to
confirm it, how to mitigate, and how to verify recovery. The SRE standard is blunt —
**every known failure mode must have a runbook**, linked from the alert that detects
it (notice the `runbook:` annotation on the SLO alerts in ).

A runbook turns a 3 a.m. page from "improvise under stress" into "follow the steps."
It is also toil reduction: a repeated manual recovery is a runbook today
and an automated remediation tomorrow. Runbooks are living documents — every incident
either used a runbook (improve it) or revealed a missing one (write it).

#### The postmortem: blameless, structured, action-tracked

After every significant incident you write a **postmortem**. Three properties make it
worth the effort:

- **Blameless.** It examines *systems and conditions*, never "who messed up." People
 act reasonably given the information and tools they had; if a single human error
 could take down the platform, the *system* allowed it — that is the finding. Blame
 kills the honesty that postmortems depend on.
- **Structured.** A fixed template (timeline, impact, contributing factors, what went
 well, action items) so they are comparable and nothing is skipped.
- **Action-tracked.** Every action item has an **owner and a due date**, and is
 tracked to completion like any other work. A postmortem whose actions are never done
 is theatre — the same incident will recur.

> The goal is not to assign fault; it is to **change the system so the next incident
> is less likely or less severe.** A culture that blames individuals gets quieter
> incidents and worse outages; a blameless culture gets honesty and real fixes.

---

### 2. Why it matters for platform engineering

- **Your incidents are everyone's incidents.** A calm, well-run platform incident
 limits org-wide damage; a chaotic one amplifies it. Process is the multiplier that
 works in your favor instead of against you.
- **Trust is won or lost during incidents.** Teams forgive outages; they do not
 forgive silence and surprises. Disciplined comms keep the platform a product teams
 trust even on its worst day.
- **Postmortems compound reliability.** Each action item removes a failure mode or
 adds a runbook. Over time this is how a platform gets genuinely reliable — not by
 never failing, but by never failing the *same way twice*.
- **It connects the whole phase.** Burn-rate alerts (17.2) detect, runbooks mitigate,
 postmortems feed toil reduction (17.1), capacity (17.4), and chaos (17.5). Incident
 management is where platform SRE comes together.

---

### 3. Mental model

Think of an incident as an **aircraft emergency**: one pilot flying (ops), one
captain commanding and talking to the tower (IC + comms), a **checklist** (runbook),
and a **flight recorder** (timeline) you read afterward to prevent the next one.

```text
 ALARM (burn-rate alert)
 │
 ▼
 CAPTAIN takes command ──► "I am Incident Commander" (coordination, not keyboard)
 │
 ├─ assigns severity by blast radius (P0..P3)
 ├─ directs OPS to run the CHECKLIST (runbook) → stop the bleeding
 ├─ COMMS keeps the tower (teams) informed on a fixed cadence
 └─ SCRIBE records the flight recorder (timeline)
 │
 ▼
 LAND SAFELY (SLO recovers) → close incident
 │
 ▼
 READ THE RECORDER (blameless postmortem) → change the system → fewer alarms
```

The durable idea: **mitigate first, coordinate always, blame never, and feed every
lesson back into the system.**

---

### 4. Minimal implementation

The smallest real incident process is three artifacts: a way to **declare**, a
**runbook** to mitigate, and a **template** to learn. Declaring can be as simple as a
chat command that names the IC and severity:

```text
/incident declare
 title: Argo CD not syncing (deploys paused platform-wide)
 severity: P1
 ic: @alex
 channel: #inc-argocd-sync
 status: https://status.internal.example.com/incidents/1042
```

The runbook it points to is a few decisive steps, not an essay:

```text
RUNBOOK: Argo CD sync failing
 CONFIRM: burn-rate alert "GitOpsSyncLatency" or "ArgoCDApiAvailability" firing;
 `kubectl -n argocd get applications` shows apps stuck/OutOfSync.
 DIAGNOSE: `kubectl -n argocd logs deploy/argocd-repo-server` (TLS? webhook? repo?)
 `kubectl -n argocd get events --sort-by=.lastTimestamp`
 MITIGATE: restart the controller to clear the stuck state:
 `kubectl -n argocd rollout restart deploy/argocd-application-controller`
 if a bad config was pushed, revert the Git commit (GitOps rolls back).
 VERIFY: apps return to Synced/Healthy; burn-rate alert clears.
 ESCALATE: if not recovered in 15 min, raise severity and page platform lead.
```

That is enough to run an incident calmly. The lab walks this exact flow against a real
Argo CD, and you capture the outcome in the postmortem template.

```bash
## detect: which apps are not syncing?
kubectl -n argocd get applications -o wide
## mitigate: clear stuck controller state
kubectl -n argocd rollout restart deploy/argocd-application-controller
```

---

### 6. Production considerations

- **Name the IC instantly.** The single most valuable incident habit is that "who is
 the IC?" always has an answer. Rotate the role and train people into it; it is a
 skill, not a title.
- **Automate declaration.** A `/incident` bot that spins up a channel, a status-page
 entry, and a timeline doc removes toil and ensures consistency at the worst moment.
- **Keep runbooks next to the alert.** The alert that fires should link the runbook
 that fixes it (the `runbook:` annotation from 17.2). A runbook nobody can find
 during a page does not exist.
- **Separate mitigation from root cause.** Train responders to restore service first.
 Heroic live debugging while teams are down is the wrong instinct — roll back, then
 investigate.
- **Track action items like product work.** Postmortem actions go in the same backlog
 with owners and due dates, and are reviewed until done. Unclosed actions are how the
 same incident recurs.
- **Run postmortems for near-misses too.** An alert that nearly breached, a mitigation
 that barely worked — these are free lessons without the damage. Harvest them.

### 7. Common mistakes

- **No incident commander — everyone debugging at once.** — The response is
 uncoordinated, actions collide, and nobody talks to teams. *Fix:* name an IC
 immediately whose job is coordination, not the keyboard.
- **Diagnosing before mitigating.** — Responders chase root cause while teams stay
 down. *Fix:* stop the bleeding first (roll back/restart/fail over); diagnose in the
 postmortem.
- **Silence toward teams.** — Users hear nothing, assume the worst, and flood the
 channel. *Fix:* a comms lead posting impact and a next-update time on a fixed
 cadence.
- **Blameful postmortems.** — The write-up names a culprit, so next time people hide
 details. *Fix:* examine the system and conditions; a single human error that can
 break the platform is a *system* finding.
- **Action items with no owner or date.** — The postmortem is filed and nothing
 changes. *Fix:* every action has an owner and due date, tracked to done.
- **Severity inflation or paralysis.** — Everything is a P0 (alert fatigue) or nothing
 is (slow response). *Fix:* classify by teams-blocked blast radius and re-classify as
 you learn.

## Platform Capacity Planning

> A platform must have **enough** compute for every team's workloads — but not so much
> that you burn money on idle nodes. Too tight and pods go `Pending` and incidents
> follow; too loose and the cloud bill balloons. This module covers node-pool design,
> the autoscaling stack (HPA/VPA for pods, Cluster Autoscaler and Karpenter for
> nodes), forecasting from adoption, and right-sizing from real usage.

limits, scheduling), a local [kind](https://kind.sigs.k8s.io/) cluster, `kubectl`, and
metrics-server. The live Karpenter steps are **cloud-optional** (see the lab note).

### 1. Concept

#### The capacity problem has two failure modes

Capacity planning is a balance between two expensive mistakes:

```text
 too TIGHT ◄───────────────────────────────► too LOOSE
 pods Pending, evictions, nodes idle at 20% utilization,
 throttling, incidents paying for air
 (reliability cost) (money cost)
```

The whole discipline is finding the middle: enough headroom to absorb spikes and node
failures, without paying for capacity nobody uses. On a platform this is multiplied —
you are provisioning for *every* team, so a 20% waste is 20% of a very large bill, and
a shortage blocks many teams at once.

#### Requests are the currency of capacity

Kubernetes schedules on **requests**, not actual usage. A pod's CPU/memory
*requests* reserve space on a node; the scheduler bin-packs pods onto nodes until
requests fill allocatable capacity. Two consequences drive everything in this module:

- **Over-requesting wastes capacity.** A pod that requests 1 CPU but uses 0.1 holds a
 whole CPU of reservation idle. Multiply across a platform and you buy nodes for
 requests nobody uses — the number-one source of cluster waste.
- **Under-requesting causes incidents.** A pod that requests too little gets scheduled
 onto a crowded node and then starves or is OOM-killed under load.

So "capacity planning" is really two jobs: **provision the right nodes** for the
requests, and **make the requests match reality** (right-sizing).

#### Node-pool design

You rarely want one uniform node type. Different workloads need different shapes, so
you define **node pools** (node groups), each a template for a class of node:

```text
pool shape workloads
───────────────── ──────────────────────────── ───────────────────────────────
general-purpose balanced CPU:memory (m-class) most services, controllers
compute-optimized high CPU (c-class) build agents, CPU-bound jobs
memory-optimized high memory (r-class) caches, in-memory data
GPU accelerators ML training/inference
spot interruptible, cheap fault-tolerant batch, stateless
```

Pools let you match workloads to hardware, isolate noisy neighbors, and target
cheap **spot** capacity at workloads that tolerate interruption. Taints/labels steer
pods to the right pool.

#### The autoscaling stack: four autoscalers, four jobs

Autoscaling has two axes — pods and nodes — and a tool for each:

```text
 scales PODS scales NODES
 ┌───────────────────────┐ ┌──────────────────────────────┐
 OUT │ HPA: more/fewer │ │ Cluster Autoscaler: add/remove│
 (count)│ replicas on a metric │ │ nodes within fixed node pools │
 └───────────────────────┘ └──────────────────────────────┘
 UP ┌───────────────────────┐ ┌──────────────────────────────┐
 (size) │ VPA: adjust a pod's │ │ Karpenter: provision right- │
 │ requests to fit usage │ │ sized nodes on demand, any │
 └───────────────────────┘ │ shape, prefer spot, consolidate│
 └──────────────────────────────┘
```

- **HPA (Horizontal Pod Autoscaler)** — adds/removes *replicas* based on CPU, memory,
 or custom metrics. Handles load that scales horizontally.
- **VPA (Vertical Pod Autoscaler)** — recommends/sets a pod's *requests* to match
 observed usage. The automation behind right-sizing (use in recommend mode first).
- **Cluster Autoscaler (CA)** — adds/removes *nodes* from **predefined node groups**
 when pods are `Pending` or nodes are empty. Node sizes are fixed by the groups.
- **Karpenter** — a newer node autoscaler that provisions **just-in-time, right-sized**
 nodes of whatever shape best fits the pending pods, chooses **spot** when allowed,
 and **consolidates** underutilized nodes by replacing or removing them.

HPA and CA are the classic pairing; VPA + Karpenter is the modern, efficiency-focused
pairing. They compose: HPA adds replicas → requests exceed capacity → Karpenter/CA add
nodes.

#### Karpenter: nodes shaped to the work

Cluster Autoscaler scales *within* node groups you defined up front, so it can only add
more of a shape you already chose. **Karpenter** flips this: you describe *constraints*
(allowed instance families, architectures, capacity types) in a `NodePool`, and
Karpenter looks at the **actual pending pods** and launches the cheapest node that
fits them — right-sizing the node to the work instead of the work to the node.

Three Karpenter behaviors matter for a platform:

- **Right-sizing.** It bin-packs pending pods and picks an instance type that fits,
 avoiding both tiny-node sprawl and giant half-empty nodes.
- **Spot preference with fallback.** Allow both `spot` and `on-demand` capacity types
 and Karpenter prefers cheap spot, falling back to on-demand when spot is
 unavailable — large savings for interruption-tolerant work.
- **Consolidation.** On low utilization it actively **consolidates**: it removes empty
 nodes and replaces underused ones with cheaper/smaller nodes, continuously driving
 the cluster toward the minimum cost that still fits the requests.

#### Forecasting from adoption

A platform's capacity demand tracks **adoption**, not calendar time. The signal is the
onboarding pipeline: teams coming on, services per team, and their request footprint.

```text
forecast ≈ (current requested CPU/mem)
 × (projected teams / current teams)
 × (growth per team)
 + headroom for spikes and node-failure tolerance
```

You do not need a data-science model — a simple trend from "requested resources per
month" plus the onboarding roadmap gets you a defensible number for the next quarter.
The point is to provision *ahead* of adoption so new teams are not blocked, while
autoscaling absorbs the day-to-day variation.

#### Right-sizing: usage versus requests

The highest-leverage efficiency work is closing the gap between **requests** and
**actual usage**. The method:

- Observe actual CPU/memory over a representative window (e.g. 30 days, including peaks)
 from Prometheus or `kubectl top`.
- Compare to requests. A pod requesting 1 CPU and using a p95 of 0.15 is massively
 over-provisioned; one using a p95 of 0.95 against a 1 CPU request is at risk.
- Recommend new requests at roughly **p95 usage + headroom** — enough for peaks, not
 for imaginary load. VPA automates exactly this recommendation.

Right-sizing is continuous (usage drifts) and it is a platform service: you give teams
a report or a VPA recommendation so their defaults improve, which shrinks the cluster
Karpenter has to provision.

---

### 2. Why it matters for platform engineering

- **Capacity is a reliability *and* a cost control.** The same lever that prevents
 `Pending`-pod incidents also governs the biggest line on the platform bill. Get it
 wrong tight and teams are blocked; wrong loose and finance comes asking.
- **You provision for everyone.** A platform's waste and shortage are both multiplied
 across all teams, so efficiency work here has outsized leverage.
- **Right-sizing is scalable toil elimination.** Instead of arguing requests with each
 team, the platform ships good defaults and a recommendation pipeline — the paved
 road stays efficient by default.
- **Autoscaling turns capacity into a property, not a project.** Well-configured
 Karpenter/HPA means capacity tracks demand automatically, freeing the team from
 manual node math.

---

### 3. Mental model

Think of the cluster as a **moving van** you rent by the cubic metre. **Requests** are
the box sizes teams declare; the scheduler **packs boxes into vans**; Karpenter
**rents exactly enough vans of the right size, prefers the cheap off-peak rate (spot),
and returns half-empty vans (consolidation)**. Right-sizing is making teams label their
boxes honestly so you do not rent vans for air.

```text
 teams declare box sizes (requests)
 │ (often bigger than what's inside → right-sizing fixes this)
 ▼
 scheduler packs boxes into vans (bin-pack onto nodes)
 │ boxes don't fit? → pods Pending
 ▼
 Karpenter rents vans to fit the boxes:
 ├─ right-sized (smallest van that fits the pending boxes)
 ├─ spot rate preferred, on-demand fallback
 └─ consolidation: return empty/half-empty vans, repack cheaper
 │
 ▼
 result: enough capacity for everyone, minimal money spent on air
```

The durable idea: **you pay for requests, not usage — so capacity planning is node
provisioning (Karpenter) plus honest requests (right-sizing), with headroom for
failure.**

---

### 4. Minimal implementation

First, *see* the capacity problem from first principles: schedule more requests than a
node can hold and watch a pod go `Pending` with nowhere to run — the exact condition a
node autoscaler reacts to.

```bash
## how much is allocatable vs already requested?
kubectl describe node | grep -A5 "Allocated resources"

## ask for more CPU than any node can give → Pending
kubectl create deployment hog --image=registry.k8s.io/pause:3.9 --replicas=5
kubectl set resources deployment/hog --requests=cpu=2
kubectl get pods -l app=hog # some stay Pending: "0/ N nodes available: insufficient cpu"
```

On a managed cluster, a Karpenter `NodePool` turns that `Pending` into a right-sized,
spot-preferring node automatically — and consolidation removes it when the load drops:

```yaml
apiVersion: karpenter.sh/v1
kind: NodePool
spec:
 template:
 spec:
 requirements:
 - key: karpenter.sh/capacity-type
 operator: In
 values: ["spot", "on-demand"] # prefer spot, fall back to on-demand
 disruption:
 consolidationPolicy: WhenEmptyOrUnderutilized # consolidate idle nodes
 consolidateAfter: 1m
```

The lab validates the full `NodePool` and lets you watch pending pods, bin-packing, and
a right-sizing calculation locally — Karpenter's live provisioning is the cloud-optional
extension.

```bash
## right-sizing signal: actual usage vs requests
kubectl top pods --containers
```

### 6. Production considerations

- **Keep failure headroom.** Provision so that losing a node (or an AZ) does not cause
 `Pending` pods for critical workloads. Autoscaling reacts in minutes; headroom covers
 the gap. Use PodDisruptionBudgets so consolidation and upgrades respect availability.
- **Spot needs interruption-tolerance.** Spot is cheap because it can be reclaimed.
 Put stateless, retry-safe, or batch work on spot; keep stateful and critical
 singletons on on-demand. Spread across instance types to reduce correlated reclaims.
- **VPA and HPA conflict on the same metric.** Do not run HPA and VPA both on CPU for
 the same workload — they fight. Use HPA on a load metric and VPA (or manual
 right-sizing) on requests, or VPA in *recommend-only* mode.
- **Consolidation causes churn.** Aggressive consolidation saves money but reschedules
 pods; tune `consolidateAfter` and protect latency-sensitive apps with PDBs so you do
 not trade cost for instability.
- **Right-size continuously, from peaks.** Usage drifts and traffic is spiky; size on
 p95-including-peaks, not averages, and revisit regularly. Ship recommendations to
 teams rather than silently changing their requests.
- **Forecast ahead of onboarding.** Tie capacity reviews to the adoption roadmap so new
 teams never wait on nodes; let autoscaling handle the noise, not the trend.

### 7. Common mistakes

- **Sizing on usage, scheduling on requests.** — Teams watch CPU graphs but set
 requests arbitrarily, so the cluster is full of reservation nobody uses. *Fix:*
 right-size requests to p95 usage + headroom; that is what the scheduler actually
 packs.
- **One giant node pool.** — Every workload on identical nodes wastes money and mixes
 noisy neighbors. *Fix:* purpose-built pools (general, compute, memory, GPU, spot)
 with taints/labels.
- **Putting stateful workloads on spot.** — A reclaimed spot node kills a database
 pod. *Fix:* spot for interruption-tolerant work only; on-demand for critical state.
- **HPA and VPA on the same signal.** — They oscillate against each other. *Fix:*
 separate the metrics, or run VPA in recommend mode.
- **No failure headroom.** — The cluster is packed to 100% of requests, so one node
 loss causes `Pending` pods and an incident. *Fix:* plan explicit headroom and PDBs.
- **Treating capacity as a one-time project.** — Provision once, never revisit, and
 drift into waste or shortage. *Fix:* continuous right-sizing and adoption-driven
 forecasting.

## Chaos Engineering for Platforms

> You do not actually know your platform is resilient until you break it on purpose.
> **Chaos engineering** injects controlled failure — killed pods, network latency, a
> dead dependency — to find weaknesses *before* your users do, and to prove that your
> SLOs hold, your alerts fire, and your runbooks work. This module frames chaos as a
> disciplined experiment and runs three against real platform components.

 (runbooks), a local
[kind](https://kind.sigs.k8s.io/) cluster, `kubectl`, and
[Chaos Mesh](https://chaos-mesh.org/) (installed in the lab, free and local).

### 1. Concept

#### Chaos engineering is an experiment, not vandalism

Chaos engineering is the practice of **deliberately injecting failure into a system to
build confidence in its ability to withstand turbulent conditions.** The key word is
*confidence*: you are not breaking things for fun, you are running a **scientific
experiment** to test a belief about resilience. Real failures are inevitable; chaos
engineering just schedules them for a time when the team is watching, the blast radius
is contained, and you can learn safely.

The method mirrors the scientific method:

```text
1. STEADY STATE define a measurable "normal" (an SLI: syncs succeeding, p99 latency)
2. HYPOTHESIS "when I kill a third of Argo CD pods, steady state HOLDS"
3. INJECT introduce the failure in the smallest blast radius that tests it
4. OBSERVE did steady state hold? did the SLO stay green? did alerts fire?
5. LEARN weakness found → fix it (and add a runbook); held → confidence up
```

#### The steady-state hypothesis

The foundation of a good experiment is the **steady-state hypothesis**: a *measurable*
definition of normal system behavior, expressed as the SLIs you built in.
You state it **before** injecting failure, and you predict it will *keep holding*
through the failure.

```text
Weak: "Argo CD should be fine." (not measurable)
Strong: "Argo CD app-sync success stays >= 99% and the
 API p99 stays < 500ms while a third of its pods
 are killed." (measurable → falsifiable)
```

A strong hypothesis is **falsifiable** — the experiment can prove it wrong. If the
steady state breaks, you have found a real weakness; if it holds, you have earned real
confidence. Vague hypotheses ("it should work") teach you nothing.

#### Control the blast radius

Chaos is controlled failure, so every experiment has guardrails:

- **Start small.** One pod before a third; one component before the whole namespace;
 a dev cluster before production.
- **Define abort conditions.** Decide in advance the signal that means "stop the
 experiment now" (e.g. real user-facing SLO starts burning) and how to halt it.
- **Announce it.** A chaos experiment should not look like a real incident to the rest
 of the org — tell people, or run it as a scheduled GameDay.
- **Prefer a kill switch.** Chaos Mesh experiments have a `duration` and can be deleted
 instantly; never inject failure you cannot immediately undo.

#### Platform failure modes worth testing

Point chaos at the failures that actually take platforms down:

```text
failure mode example injection what it tests
──────────────────────── ──────────────────────────────── ──────────────────────────
control-plane / component kill a third of Argo CD pods does the service tolerate
unavailability losing replicas?
dependency failure delete the ESO pod do dependents degrade or die?
network degradation +500ms latency to Prometheus graceful degradation vs
 total blackout?
node failure drain / kill a node do pods reschedule in time?
network partition cut a namespace off split-brain? stuck sync?
storage failure fail a PVC / slow I/O data-plane resilience
```

The three you run in the lab cover the first three — the most common platform
failure modes — against Argo CD, Prometheus, and the External Secrets Operator.

#### Tools: Chaos Mesh and Litmus

You could `kubectl delete pod` by hand, but real chaos tooling gives you *controlled,
declarative, repeatable* fault injection with selectors, scheduling, and a kill
switch:

- **Chaos Mesh** — a CNCF, Kubernetes-native chaos platform. Faults are CRDs
 (`PodChaos`, `NetworkChaos`, `StressChaos`, `IOChaos`, …) with label selectors, a
 `mode` (one / fixed-percent / all), and a `duration`. Declarative chaos, applied and
 removed like any manifest — which is exactly why the lab uses it.
- **Litmus** — another CNCF chaos framework, organized around reusable *chaos
 experiments* and *workflows*, with a hub of predefined faults and GameDay tooling.

Both encode the discipline so your experiments are versioned, scoped, and reversible
rather than ad-hoc `kubectl delete`.

#### GameDays and reading the results

A **GameDay** is a scheduled, structured chaos exercise with the platform team in the
room: you pick a failure mode, state the hypothesis, inject it, and watch the system
*and the team's response* together. The GameDay tests three layers at once, and the
results are judged against each:

```text
layer the question a failing result
─────────── ──────────────────────────────────────── ─────────────────────────────
the system did the steady-state SLO hold? sync failed when pods died
the signals did the right alert fire (and only it)? no alert, or alert storm
the humans did the runbook work? was the IC clear? runbook missing/wrong/slow
```

That last column is the point: chaos does not just test the software, it tests your
**SLOs, alerts, and runbooks** — the whole /17.3 machinery — under
realistic failure, while it is safe to find the gaps.

---

### 2. Why it matters for platform engineering

- **Your resilience claims are untested until you test them.** "Argo CD is HA" is a
 hope until you kill a third of its pods and watch syncs continue. Chaos converts
 hope into evidence — exactly what a platform's many dependents need.
- **It validates the rest of this phase cheaply.** A GameDay exercises your SLOs
 (17.2), alerts, runbooks, and incident process (17.3) without a real outage. You find
 the missing runbook on a Tuesday afternoon, not at 3 a.m.
- **It finds the weakness before all teams feel it.** A platform failure hits everyone, so proactively hunting failure modes has outsized value — one found
 weakness prevents an org-wide incident.
- **It builds a resilience culture.** Teams that routinely rehearse failure respond
 calmly to the real thing; teams that never do, panic.

---

### 3. Mental model

Chaos engineering is a **vaccine**: a small, controlled dose of the pathogen (failure),
given while the patient is monitored, so the system builds immunity before it meets the
real infection.

```text
 define STEADY STATE (measurable normal: SLO green)
 │
 ▼
 form a FALSIFIABLE HYPOTHESIS "steady state HOLDS when I inject X"
 │
 ▼
 inject the smallest dose ───────► OBSERVE three layers:
 (one pod → a third →...) ├─ system: did the SLO hold?
 with a kill switch (duration) ├─ signals: did the alert fire?
 │ └─ humans: did the runbook work?
 ▼
 HELD → confidence earned BROKE → weakness found → fix + runbook
 │ │
 └──────────────── repeat, widen blast radius ◄──┘
```

The durable idea: **a resilience you have not tested is a guess. Chaos turns the guess
into a measured result — safely, on your schedule.**

---

### 4. Minimal implementation

A chaos experiment is just a manifest plus a steady-state check. First, establish the
steady state (the thing you predict will keep holding):

```bash
## steady state: all Argo CD apps are Synced/Healthy and the API answers
kubectl -n argocd get applications
kubectl -n argocd get deploy
```

Then inject the smallest failure that tests the hypothesis — here, kill a third of
Argo CD's pods with Chaos Mesh:

```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
 name: argocd-pod-kill
 namespace: chaos-testing
spec:
 action: pod-kill
 mode: fixed-percent
 value: "33" # a third of the matched pods
 selector:
 namespaces: ["argocd"]
 labelSelectors:
 app.kubernetes.io/part-of: argocd
```

Apply it, then immediately re-check the steady state — did syncs keep working while a
third of the pods restarted?

```bash
kubectl apply -f argocd-pod-kill.yaml
kubectl -n argocd get pods # a third terminating/recreating
kubectl -n argocd get applications # hypothesis: still Synced/Healthy
```

If the apps stayed healthy, the hypothesis held and you have *evidence* Argo CD
tolerates losing replicas. If not, you found a weakness worth a fix and a runbook. The
lab runs three such experiments and records the results.

### 6. Production considerations

- **Earn your way to production chaos.** Start in dev, with small blast radius and a
 team watching. Only run chaos in production once experiments are boring in staging
 and you trust the kill switch — then it is the most valuable (real traffic, real
 dependencies).
- **Always have a kill switch and abort conditions.** Every experiment needs a
 `duration` and a pre-agreed signal to stop (a real user SLO burning). Never inject a
 fault you cannot instantly remove.
- **Steady state must be a real user signal.** Hypothesize on SLOs users feel (sync
 success, request latency), not on internal proxies. An experiment that keeps CPU
 steady while users get errors proved nothing.
- **Automate the regression, keep GameDays human.** Turn proven experiments into
 scheduled, automated resilience tests (so a regression re-breaks loudly); keep
 periodic GameDays for the human layer — new failure modes, runbook rehearsal, IC
 practice.
- **Measure all three layers.** A "passed" experiment where no alert fired is a
 *failure* of your alerting even though the system survived. Record system, signals,
 and humans every time.
- **Respect data and tenants.** Scope selectors tightly; a careless `mode: all` on a
 shared cluster can hit tenants you did not intend. Blast-radius control is a safety
 requirement, not a nicety.

### 7. Common mistakes

- **No steady-state hypothesis.** — The team kills pods and eyeballs the result, with
 no measurable prediction. *Fix:* state a falsifiable SLO-based hypothesis before
 injecting anything.
- **Chaos with no blast-radius control.** — A production `mode: all` fault becomes a
 real incident. *Fix:* start with one pod, scope selectors tightly, set a `duration`,
 and define abort conditions.
- **Only testing the software.** — Judging success purely on "did it stay up?" and
 ignoring whether alerts fired and runbooks worked. *Fix:* grade all three layers —
 system, signals, humans.
- **Running chaos nobody announced.** — A real responder pages out on your experiment.
 *Fix:* schedule GameDays and communicate; distinguish chaos from incidents.
- **Stopping after a pass.** — One green experiment is treated as "we're resilient
 forever." *Fix:* widen the blast radius, vary the failure mode, and automate the
 experiment as a recurring regression test.
- **Injecting unrecoverable faults.** — A fault with no kill switch that outlives the
 experiment. *Fix:* prefer time-boxed, declaratively-removable faults (Chaos Mesh
 `duration`).

## Disaster Recovery for Platform

> Pods fail, nodes fail — you have planned for those. This module plans for the worst:
> an **entire cluster or region is gone.** Disaster recovery is how a platform comes
> back from total loss within a *defined* time and with a *defined* amount of data
> lost — targets called **RTO** and **RPO** — using backups you have actually tested.
> For a platform, "the cluster is gone" must be a rehearsed drill, not a catastrophe.

local [kind](https://kind.sigs.k8s.io/) cluster, `kubectl`, and the
[Velero](https://velero.io/) CLI (the lab uses a local MinIO backend — free).

### 1. Concept

#### Disaster recovery is about total loss

Resilience handles *partial* failure — a pod, a node, a
dependency. **Disaster recovery (DR)** handles *total* loss: a whole cluster deleted,
a region offline, a control plane corrupted, a catastrophic human error that wipes
everything. The question DR answers is simple and brutal:

> If this entire cluster disappeared right now, how fast could the platform be back,
> and how much data would we lose?

For a platform the stakes are maximal — a lost platform cluster takes *every* team's
deploy pipeline, secrets, and config with it. DR is the plan that makes that
survivable.

#### RTO and RPO: the two numbers that define DR

Every DR plan is anchored to two targets:

```text
 disaster
 │
 ┌─────────┼──────────────────────────────┐
 │ │ │
 last DISASTER service
 backup │ restored
 │◄─ RPO ─►│◄────────── RTO ──────────────►│
 │ │ │
 data you how much data you LOSE how long you are DOWN
 can afford (Recovery Point Objective) (Recovery Time Objective)
 to lose
```

- **RPO — Recovery Point Objective:** the maximum acceptable *data loss*, measured as
 time. An RPO of 1 hour means you back up at least hourly and may lose up to an
 hour's changes. RPO drives **backup frequency**.
- **RTO — Recovery Time Objective:** the maximum acceptable *downtime* — how long from
 disaster to restored service. An RTO of 2 hours means recovery must complete within
 two hours. RTO drives **how automated and rehearsed** your recovery is.

Tighter targets cost more (more frequent backups, warm standby, automation), so you
set them per service by criticality: the cluster API and GitOps controller get tight
RTO/RPO; a non-critical dashboard can tolerate loose ones.

#### What to back up (and where the truth lives)

A Kubernetes platform's state is in several places, and DR must cover all of them:

```text
what how it's protected recovery path
─────────────────────────── ──────────────────────────────── ─────────────────────
cluster resources (objects) Velero backup of the API objects Velero restore
persistent volumes (data) Velero volume snapshots / restic Velero restore
control-plane state (etcd) etcd snapshot (self-managed) etcd restore / managed
cluster itself (infra) IaC in Git (Terraform) re-apply to re-create
app & platform config GitOps repo (Argo CD) re-sync from Git
secrets' source of truth external vault / secrets manager ESO re-syncs
```

The crucial insight from everything you have built: **most of your platform's
definition already lives in Git.** If you did GitOps and IaC, the
cluster's *configuration* is reproducible from source — you do not back it up, you
**re-create** it. What you genuinely must back up is the **stateful data** that is not
in Git: persistent volumes (databases, registries) and, for self-managed clusters,
etcd.

#### The GitOps + IaC recovery path

This is why the earlier phases pay off at the worst moment. Recovering a lost platform
cluster becomes a pipeline, not an archaeology dig:

```text
1. RE-CREATE the cluster → Terraform apply stands up a fresh cluster
2. BOOTSTRAP GitOps → install Argo CD
3. RE-SYNC all config → Argo CD pulls every app/platform manifest from Git
4. RESTORE stateful data → Velero restores PVs; ESO re-syncs secrets from vault
5. VERIFY → SLOs green, teams can deploy again
```

Steps 1–3 are *reproducible from source* — the entire value of declarative,
Git-backed platforms is that config recovery is deterministic. Only step 4 needs
real backups. A platform built this way has a dramatically smaller DR surface than one
whose state lives in a cluster nobody can rebuild.

#### Velero: cluster backup and restore

**Velero** is the standard tool for backing up and restoring Kubernetes *cluster
state*. It:

- backs up **API objects** (namespaces, deployments, configmaps, CRDs, …) by querying
 the API and storing them in object storage (S3/GCS/MinIO);
- backs up **persistent volumes** via snapshots or filesystem backup (restic/Kopia);
- runs **scheduled** backups (a cron) and supports selective **restore** by namespace,
 label, or resource;
- can **migrate** a cluster's workloads to a new cluster — which is exactly a DR
 restore.

Velero is your answer for "restore the stuff that is not in Git" and for fast
namespace-level recovery from human error.

#### etcd snapshots (self-managed control planes)

For **self-managed** clusters, the control-plane state lives in **etcd**. A raw
**etcd snapshot** (`etcdctl snapshot save`) captures the entire cluster state at a
point in time and can rebuild a control plane. On **managed** Kubernetes (GKE/EKS/AKS)
the provider runs and backs up etcd for you — you do not snapshot it, you rely on the
provider's control-plane SLA and focus your DR on resources (Velero) and data (PV
snapshots).

#### Multi-region: active-active versus active-passive

To survive a whole *region* loss, you run in more than one:

```text
ACTIVE-ACTIVE ACTIVE-PASSIVE
both regions serve traffic one serves; the other is standby
 + near-zero RTO (failover is live) + simpler, cheaper
 + load shared + standby may be "warm" or "cold"
 − complex: data sync, split-brain − RTO = time to promote the standby
 − most expensive − risk the standby is untested/stale
```

Active-active gives the best RTO/RPO at the highest cost and complexity (you must
solve data replication and split-brain); active-passive is simpler and cheaper but
your RTO is however long promotion takes — which is only trustworthy if you **drill**
it.

#### DR runbooks and drills: tested, not assumed

A DR plan that has never been executed is a *hypothesis*, and usually a wrong one.
Backups silently fail, restores hit missing dependencies, and the one person who knew
the steps has left. The discipline:

- **Write the DR runbook** — the exact, ordered recovery steps with the RTO/RPO
 targets, who does what, and every command.
- **Drill it regularly** (quarterly is common): actually restore into a scratch
 environment, time it against the RTO, and verify the RPO. A drill that beats the
 target is confidence; one that misses it is a backlog.
- **Treat a failed drill as a finding**, not an embarrassment — that is the entire
 point of drilling before the real disaster.

> The only backup that counts is one you have **restored**. "We have backups" is not a
> DR plan; "we restored last quarter in 48 minutes against a 2-hour RTO" is.

---

### 2. Why it matters for platform engineering

- **The platform is everyone's single point of failure.** A lost platform cluster
 halts every team at once. DR is the difference between a bad afternoon and an
 existential incident — the ultimate expression of the blast-radius argument.
- **It is where GitOps and IaC cash in.** The declarative, Git-backed platform you
 built recovers by re-create-and-re-sync. DR is the proof that those investments were
 about survivability, not just convenience.
- **Untested DR is a liability disguised as safety.** Leadership believes "we have
 backups" means "we are safe." Drills convert that false comfort into a real,
 measured capability — or expose the gap while it is cheap to fix.
- **Regulators and customers increasingly require it.** Defined RTO/RPO and evidence
 of drills are table stakes for many compliance regimes; the platform team usually
 owns this for the whole org.

### 3. Mental model

Think of DR like **insurance with a tested claim process.** RPO is your deductible
(how much loss you accept); RTO is the claim's payout time (how fast you are made
whole). Backups are the policy — worthless unless you have actually filed a claim
(restored) and know it pays out in time.

```text
 ┌──────────── sources of truth (Git) ────────────┐
 │ IaC (Terraform)....... re-create the cluster │ ← reproduced, not backed up
 │ GitOps repo (Argo CD). re-sync all config │
 └─────────────────────────────────────────────────┘
 +
 ┌──────────── backups (not in Git) ──────────────┐
 │ Velero........ cluster objects + volumes │ ← RPO = backup frequency
 │ etcd snapshot. self-managed control plane │
 │ vault......... secrets' source of truth │
 └─────────────────────────────────────────────────┘
 │
 DISASTER (cluster/region lost)
 │
 re-create ─► bootstrap GitOps ─► re-sync ─► restore data ─► verify
 │
 measured against RTO / RPO in a DRILL
```

The durable idea: **reproduce what is in Git, restore what is not, and prove the whole
path with a timed drill — because an untested backup is just a hope.**

### 4. Minimal implementation

The smallest real DR capability is backup-and-restore you have actually run. With
Velero pointed at object storage, a backup and a scheduled backup are one command
each:

```bash
## back up a namespace's resources (and its volumes) now
velero backup create demo-backup --include-namespaces demo

## schedule a daily full backup (this is your RPO lever)
velero schedule create daily-full --schedule="0 2 * * *"
```

Now simulate disaster and recover — the move that turns "we have backups" into "we can
restore":

```bash
## disaster: the namespace (and everything in it) is gone
kubectl delete namespace demo

## recover from the backup
velero restore create --from-backup demo-backup

## verify: the resources are back
kubectl get all -n demo
```

That loop — backup, destroy, restore, verify — is the heart of DR. Scale it up and it
becomes "re-create the cluster from Terraform, re-sync from Git, restore volumes from
Velero," timed against an RTO. The lab runs exactly this loop on a local MinIO backend,
then has you fill in a DR runbook with real RTO/RPO targets.

### 6. Production considerations

- **Back up to a *different* failure domain.** A backup in the same region/account as
 the cluster dies with it. Store backups in another region (and ideally another
 account) so a region loss does not take the backups too.
- **Encrypt and access-control backups.** A cluster backup contains secrets and
 config — it is as sensitive as the cluster. Encrypt at rest, lock down the bucket,
 and audit access.
- **Test restores, not just backups.** A green backup job proves nothing about
 restorability. Schedule real restore drills; alert on backup *age* and *failure*, and
 track restore time against RTO.
- **Mind what Velero does not cover.** Managed control-plane/etcd is the provider's
 job; in-flight data not yet snapshotted is lost to RPO; external secret *values* come
 from the vault, not the cluster backup. Map every piece of state to an owner.
- **Automate the recovery path.** The re-create (Terraform) and re-sync (Argo CD) steps
 should be scripted so RTO is not gated on tribal knowledge. The GitOps bootstrap is
 the one manual step to rehearse until it is routine.
- **Drill on a schedule and after major changes.** Quarterly, and after anything that
 changes the recovery path (new CRDs, new storage, a cluster upgrade). Document each
 drill's time-to-recover and findings.

### 7. Common mistakes

- **"We have backups" with no tested restore.** — Backups exist but have never been
 restored, so nobody knows if they work or how long recovery takes. *Fix:* regular,
 timed restore drills; the restore is the deliverable, not the backup.
- **No defined RTO/RPO.** — Recovery has no target, so decisions during a disaster are
 improvised. *Fix:* set RTO/RPO per service by criticality and design backups and
 automation to meet them.
- **Backups in the same blast radius.** — Stored in the region/account that just died.
 *Fix:* replicate backups to an independent failure domain.
- **Backing up what is already in Git.** — Elaborate backups of config that GitOps/IaC
 reproduces, while neglecting the stateful data that is *not* in Git. *Fix:* reproduce
 config from source; back up volumes, etcd (self-managed), and secret sources.
- **Ignoring secrets and CRDs in restore.** — Restore the apps but not their CRDs,
 operators, or secret sources, so nothing actually runs. *Fix:* include CRDs/operators
 and re-sync secrets; test the *whole* path end to end.
- **A DR runbook nobody has run.** — Written once, never drilled, out of date by the
 disaster. *Fix:* treat the runbook as living; every drill updates it.

---

## References

- Google — [SRE Book: Eliminating Toil](https://sre.google/sre-book/eliminating-toil/)
- Google — [SRE Book: Introduction](https://sre.google/sre-book/introduction/) and
- Google — [SRE Book: Embracing Risk](https://sre.google/sre-book/embracing-risk/)
- Matthew Skelton & Manuel Pais — [*Team Topologies*](https://teamtopologies.com/)
- CNCF — [Platform Engineering Maturity Model](https://tag-app-delivery.cncf.io/whitepapers/platform-eng-maturity-model/)
- Google — [SRE Workbook: Implementing SLOs](https://sre.google/workbook/implementing-slos/)
- Google — [SRE Book: Service Level Objectives](https://sre.google/sre-book/service-level-objectives/)
- Pyrra (project choice; Sloth in upstream reference) — [Documentation](https://sloth.dev/) and [GitHub](https://github.com/slok/sloth)
- Argo CD — [Metrics reference](https://argo-cd.readthedocs.io/en/stable/operator-manual/metrics/)
- External Secrets Operator — [Metrics](https://external-secrets.io/latest/api/metrics/)
