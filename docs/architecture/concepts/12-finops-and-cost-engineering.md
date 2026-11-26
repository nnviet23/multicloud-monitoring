# 12 · FinOps and Cost Engineering

> **Project Applicability:** Reference / Future Extension — Cloud FinOps concepts for future real-cloud deployment; local k3d lab focuses on telemetry volume optimization.

> You can now build, ship, secure, and operate a platform. Every one of those
> capabilities runs on someone else's computer, and at the end of the month a bill
> arrives. This phase makes **cost a first-class, engineered property of the
> platform** — measured, attributed, and optimized the same way you treat latency
> or security. The hard part is not reading the invoice; it is answering *"which
> team, service, and decision caused this number?"* The cloud bill sees **nodes**;
> your platform sees **workloads**. Closing that gap is the whole discipline.

> FinOps baseline for this phase: the
> [FinOps Foundation Framework](https://www.finops.org/framework/) (Inform →
> Optimize → Operate) and the open-source
> [OpenCost specification](https://www.opencost.io/docs/specification). Keep both
> open — the lessons and labs map back to them throughout.

## Why this phase matters

Every prior phase quietly spent money. Requests and limits decided how
densely you pack nodes — and nodes are the unit the cloud charges for. Autoscaling
decided how many nodes you run. Storage, load balancers, and cross-zone traffic all
accrued charges you never saw, because nobody was watching the bill while building
the platform. That is normal, and it is also how organizations wake up to a cloud
spend that doubled while "nothing changed."

Platform engineering answers cost **structurally**, exactly as it answered security.
Instead of asking every product team to become a billing analyst, the platform makes
cost *visible by default* — attributed to the team that caused it, reported on a
cadence, and optimized through the paved road rather than through heroics. This is
the course's recurring theme made concrete: **security and cost are structural, not
bolt-on.** A platform that cannot tell you who spent what is as unfinished as one
that cannot tell you who can access what.

The central problem is **attribution**, and it exists because of a representation
mismatch:

```text
 What the cloud bill sees What the platform sees
 ──────────────────────── ──────────────────────
 3 × n2-standard-8 nodes ?? namespace: team-payments (12 pods)
 1 × regional load balancer │ namespace: team-search (30 pods)
 2 TB egress to the internet │ namespace: team-web (8 pods)
 500 GB SSD persistent disk │ namespace: platform (ingress, logging)
 │ │ │
 ▼ ▼ ▼
 ONE invoice, priced the gap MANY owners, priced
 per node & resource (this phase) per workload & team
```

A node runs pods from several teams at once. The invoice knows the node cost but not
the split; the cluster knows the split but not the cost. FinOps tooling joins the
two — multiplying each node's price by each workload's share of it — so that a line
item on the invoice becomes a number a specific team can own and act on.

This phase gives you the model and the tools to do that:

- **Make cost visible.** You cannot optimize what you cannot see. OpenCost turns node
 prices and pod requests into a cost-per-workload figure, in Grafana, for free.
- **Attribute it to owners.** Mandatory cost labels — enforced with Kyverno, the same
 engine you used for the security baseline — turn anonymous spend into a per-team
 bill you can show (showback) or charge (chargeback).
- **Optimize through the paved road.** Right-sizing, spot capacity, bin-packing, and
 scale-to-zero are platform capabilities teams inherit, not projects each team runs.
- **Operate it as a practice.** FinOps is a culture — unit economics, cost reviews,
 and anomaly alerting — shared across platform and engineering, not a quarterly
 panic.

You have already built every prerequisite. set the requests and limits
that *drive* cost. Project 1 required ownership and cost labels on every workload.
 gave you the policy engine to enforce them. Project 3 gave you the Grafana
in which cost dashboards live. This phase ties them into one coherent, engineered
answer to *"what does this platform cost, and who pays for it?"*

## The FinOps loop

The discipline is a continuous loop, not a one-time cleanup. You will recognize it as
the same shape as an observability or SRE feedback loop, applied to money:

```text
 ┌──────────────────────────────────────────────────────────┐
 │ │
 ▼ │
 ┌─────────┐ ┌──────────┐ ┌──────────┐ │
 │ INFORM │ ─────▶ │ OPTIMIZE │ ─────▶ │ OPERATE │ ───────────┘
 └─────────┘ └──────────┘ └──────────┘
 visibility & right-size, governance,
 attribution spot, bin-pack, anomaly alerts,
 (18.1–18.3) scale-to-zero cost reviews
 (18.4) (18.5)
 "what does it "spend less for "keep it that way
 cost, and who the same value" as the org grows"
 owns it?"
```

Inform comes first and is non-negotiable: optimization without attribution is
guessing, and governance without data is politics. The modules below walk the loop in
order.

## Cloud Cost Fundamentals

> The cloud looks infinite and the pricing page hides a simple truth: you are
> renting physical machines, disks, and network links by the second. Three ways to
> buy compute, four cost components, and one discipline — tag everything — explain
> most of any cloud bill. This module teaches you to **read and model a bill from
> first principles**, before any Kubernetes cost tooling, so the numbers in the rest
> of the phase mean something.

### 1. Concept

#### One formula underneath everything

Strip away the pricing-page complexity and every charge is the same shape:

```text
cost = Σ (unit rate × quantity × time) − discounts
```

A vCPU-second, a gigabyte-month, a gigabyte transferred, an API call — each has a
*rate*, you consume some *quantity* for some *time*, and commitments or spot apply a
*discount*. Everything below is detail about what the unit is and how the rate is
set. Hold this formula; it is the only mental arithmetic FinOps really requires.

#### The three ways to buy compute

The single biggest lever on a compute bill is not *what* you run but *how you buy
it*. The same node can cost wildly different amounts:

- **On-demand.** Pay per second, no commitment, cancel anytime — at the highest rate.
 You are paying a premium for flexibility. The right default for anything new,
 spiky, or short-lived.
- **Committed** (reservations, Committed Use Discounts, savings plans). You promise to
 keep spending — or keep a resource — for **1 or 3 years**, and in exchange the rate
 drops steeply. On GCP, a 3-year resource-based **CUD** reaches roughly **57% off**.
 You pay for the commitment **whether or not you use it**, so it only saves money on
 capacity that genuinely runs all the time.
- **Spot / preemptible.** The cloud sells its spare capacity at **60–90% off**, on one
 condition: it can take it back with little warning (often ~30 seconds; GCP's older
 preemptible VMs also cap at a 24-hour life). Perfect for work that can be
 interrupted and retried; unacceptable for anything that must not vanish.

```text
A hotel analogy:
 on-demand = walk-up rack rate.......... most expensive, leave whenever
 committed = prepaid non-refundable block. cheap, but you pay even if you no-show
 spot = standby room at 80% off...... cheapest, but they can bump you tonight
```

#### The four cost components

Compute dominates most bills, but it is never the whole story. Learn to look for all
four:

- **Compute** — VMs / nodes billed per second while running (vCPU + memory). Usually
 the majority of the bill and the focus of most optimization.
- **Storage** — persistent (block) disks, object storage, and snapshots, billed per
 **GB-month**. Crucially, block storage is **provisioned**: you pay for the size you
 allocated, not the bytes you wrote. Tiers (standard SSD → cold → archive) trade
 retrieval speed for price.
- **Networking** — the subtle one. **Ingress is usually free; egress is charged.**
 Data leaving to the internet, crossing zones or regions, NAT gateways, and load
 balancers all accrue. More on this below.
- **Managed services** — databases, queues, registries, logging/monitoring, and the
 managed Kubernetes control plane each priced in their own units. Convenient, and
 easy to forget in a cost model.

#### Egress: the cost that hides

Egress deserves its own section because it is the line item that surprises people:

- Replicating data **across availability zones** for high availability.
- Chatty microservices whose pods land in **different zones** and talk constantly.
- Pulling container images or datasets **from another region**.
- Shipping logs and metrics **out** to a third-party SaaS.
- Serving user traffic and large assets **to the internet**.

None of it shows up while you build; all of it shows up on the invoice. The fixes are
architectural — schedule chatty workloads together, keep traffic in-region, put a CDN
in front of static assets, use private interconnects — which is exactly why egress is
a **platform** concern, not something an app team can fix alone.

#### Buying strategy, with numbers

You rarely pick one option for everything. You **blend**:

- Put the **always-on floor** (databases, the steady base of a web tier, the control
 plane) on **committed** capacity — it runs 24/7, so the discount is pure savings.
- Put **steady-but-variable** load on **on-demand** so you can scale without
 over-committing.
- Put **interruptible** work — batch jobs, CI, dev environments, ML training — on
 **spot**, with an on-demand fallback for when capacity is reclaimed.

The risk on committed is **over-commitment** (paying for a floor that shrank); the
risk on spot is **interruption**. Both are manageable with measurement, which is what
the rest of this phase builds.

#### The billing hierarchy and its guardrails

Cloud bills are organized as a tree, and attribution starts with its shape:

```text
Organization
└── Billing account
 ├── Project / account: team-payments ← group spend here
 ├── Project / account: team-search
 └── Project / account: platform-shared
 └── resources (VMs, disks, LBs, …) ← each should carry allocation tags
```

Two platform guardrails hang off this tree:

- **Budgets and alerts.** You set a budget and get notified at, say, 50% / 90% / 100%.
 The critical caveat: **a budget alert does not stop spending** — it is a smoke
 detector, not a circuit breaker. Capping spend requires automation or a human.
- **Allocation tags / labels.** Every resource should carry `team`, `environment`, and
 `application` (or `cost-center`) labels so the one big number can be split by owner.

#### Allocation tags are the linchpin of the whole phase

Without tags, a cloud bill is a single undifferentiated total — you know you spent
$80,000 but not who or what caused it. With consistent `team` / `environment` /
`application` labels, that total becomes a per-team, per-service breakdown you can act
on. This is the seed of everything that follows, and the reason
Project 1 required these labels on every workload
from day one. **An untagged resource is unattributable spend** — invisible to the very
people who could reduce it.

---

### 2. Why it matters for platform engineering

- **The platform's defaults set everyone's baseline bill.** The instance types you
 offer, the disk tier you default to, whether workloads span zones — these platform
 decisions are multiplied across every team. A one-line default change can move the
 org's bill by a large fraction.
- **Purchase strategy is a fleet-level decision only the platform can make.** An
 individual team cannot buy a Committed Use Discount sensibly; it sees only its own
 slice. The platform commits for the **aggregate floor** of the whole cluster and
 passes the savings down.
- **Tagging is a platform-owned contract.** A consistent label taxonomy is worthless
 if 30% of resources ignore it. You will *enforce* it with Kyverno in 
 the same move you made for the security baseline in.
- **Modeling cost is an architecture skill.** "Single-region or multi-region?" and
 "how many replicas across how many zones?" are reliability questions *and* cost
 questions. Being able to put a dollar figure on each option makes you a better
 architect, not just a cheaper one.

---

### 3. Mental model

Keep two pictures in your head: the **formula** and the **purchase spectrum**.

```text
cost = Σ (rate × quantity × time) − discounts

Purchase options — price vs risk (same node, three ways to buy it):

 on-demand ████████████████████ 100% flexible, no lock-in, interruptible: never
 committed ████████▌ ~43% cheapest when ALWAYS on, locked 1–3 years
 spot ██▌ 10–40% cheapest of all, can be reclaimed in ~30s

Match the option to the workload:

 stateful DB / control plane → committed (24/7) + a little on-demand headroom
 steady web service → committed baseline + on-demand for spikes
 batch / CI / dev / ML training → spot (interruptible, retried) + on-demand fallback
```

The rule to remember: **buy your floor committed, your fluctuation on-demand, and your
interruptible work on spot.** Most waste is a workload bought on the wrong option.

---

### 4. Minimal implementation

Before any tooling, model a cluster by hand. Take **3 nodes** of 8 vCPU / 32 GB at an
on-demand rate of **$0.38/hour**, running a full month (~730 hours), plus the storage
and egress nobody remembers:

```text
Compute (on-demand): 3 × $0.38 × 730 = $832.20 / month
 same compute, 3-yr CUD (−57%): 832.20 × 0.43 = $357.85 / month (save ~$474)
 same compute, spot (−70%): 832.20 × 0.30 = $249.66 / month (if interruptible)
Storage: 500 GB SSD × $0.17/GB-month = $85.00 / month (paid even if empty)
Egress: 2 TB to internet × $0.12/GB = $245.76 / month (the forgotten line)
 ───────────────
On-demand total (compute + storage + egress) = $1,162.96 / month
```

Two lessons fall straight out of the arithmetic:

- The "server cost" is only ~72% of this bill; **storage and egress quietly add ~40%**
 on top of compute. A model that stops at the VM price is wrong before it starts.
- The **same compute** is \$832 or \$250 a month depending *only* on how you bought it.
 Purchase strategy, not workload size, is often the biggest lever.

You can automate the compute comparison in three lines — the smallest possible cost
model:

```bash
## Monthly on-demand vs 3-year committed vs spot for N identical nodes
NODES=3; RATE=0.38; HOURS=730
on_demand=$(echo "$NODES * $RATE * $HOURS" | bc -l)
committed=$(echo "$on_demand * 0.43" | bc -l) # ~57% CUD discount
spot=$(echo "$on_demand * 0.30" | bc -l) # ~70% spot discount
printf 'on-demand $%.2f | committed $%.2f | spot $%.2f\n' "$on_demand" "$committed" "$spot"
```

That is the entire idea of this module in one script: pick the unit, pick the rate,
multiply by time, apply the discount. The lab turns it into a reusable worksheet.

---

### 6. Production considerations

- **Budgets alert; they do not cap.** To actually stop runaway spend you need
 automation (a function that disables a project) or an on-call human. Treat the alert
 as the *start* of a response, never the control itself.
- **Commitment coverage and utilization are metrics to watch.** A CUD only saves money
 if it stays well-utilized. Track *coverage* (how much of your floor is committed) and
 *utilization* (how much of the commitment you actually use); a 3-year commitment on a
 footprint that later shrinks is money lit on fire.
- **Reason on effective rates, not list prices.** Your real per-unit cost blends
 on-demand, committed, and spot, plus negotiated discounts. Decisions made on list
 price will be wrong.
- **The billing export is the source of truth.** Cloud providers stream detailed
 billing to a data warehouse (GCP → BigQuery, AWS → the Cost and Usage Report). Build
 dashboards and anomaly detection from that, not from screenshots of the console.
- **Commit to the floor, not the peak.** Commit only to capacity you are confident will
 run for the full term; cover everything above it with flexible on-demand and spot.
- **Account/project structure is an attribution tool.** Isolating teams or environments
 into their own projects gives you a clean split even before per-resource tagging.

---

### 7. Common mistakes

- **Modeling only the VM price.** The compute line looks like the whole bill, so
 storage, egress, load balancers, and managed services get ignored — then the invoice
 is 40% higher than the estimate. *Fix:* always model all four components; egress and
 storage first because they are the ones you'll forget.
- **Over-committing to today's peak.** Someone buys a 3-year CUD sized to a seasonal or
 one-off high, then the workload shrinks and the commitment keeps billing. *Fix:*
 commit to the stable floor; cover variable load flexibly.
- **Running stateful or critical work on spot.** Spot's discount is tempting, but a
 reclaim event kills the pod with ~30 seconds' notice. *Fix:* spot only for
 interruptible, retryable work, always with an on-demand fallback.
- **Untagged resources.** "We'll label things later" means a bill you can never split
 by owner. *Fix:* make labels mandatory at creation and enforce them.
- **Treating a budget alert as a spend cap.** The email arrives *after* the money is
 spent and stops nothing. *Fix:* pair every budget with an action — automation or a
 named owner who responds.
- **Reasoning on list price.** Quoting the on-demand rate when half your fleet is
 committed or spot produces decisions that don't match reality. *Fix:* compute and use
 your blended effective rate.

---

## Kubernetes Cost Management

> Your cloud bill is itemized by **node**; your platform is organized by **workload**.
> Nobody is billed for "the `team-payments` deployment" — they're billed for three
> `n2-standard-8` machines that happen to run it alongside four other teams. This
> module closes that gap: it derives the **cost-per-workload** formula from first
> principles, defines **idle cost** and **node efficiency**, and then stands up
> **OpenCost** to compute it automatically and render it in Grafana.

### 1. Concept

#### The attribution gap

A Kubernetes node is a shared machine. The cloud charges you a single hourly price for
it — say \$0.38/hour for 8 vCPU and 32 GB — regardless of what runs inside. But a node
rarely belongs to one team: the scheduler packs pods from `team-payments`,
`team-search`, and the platform's own logging agents onto the same box. So the invoice
says *"\$0.38/hour for node-7"* and the cluster says *"node-7 runs 11 pods from 4
namespaces,"* and **nothing in either system joins the two**.

```text
 The cloud's view The cluster's view
 ─────────────── ──────────────────
 node-7: $0.38/hr ?? node-7 hosts:
 │ payments-api (requests 2 CPU / 4Gi)
 │ search-indexer(requests 3 CPU / 8Gi)
 │ fluent-bit (requests 0.1 CPU / 128Mi)
 ▼ …
 who owes what share of $0.38/hr?
```

Bridging the gap means **splitting each node's price among the pods on it**, using a
share each pod already declares. That share is the pod's **resource request** — the
amount the scheduler reserved for it. Requests are the natural currency
of attribution because they are *what you reserved and therefore what you pay for*,
whether or not the pod uses it.

#### The cost-per-workload formula

A node's hourly price can be split into a **CPU portion** and a **memory portion** (and
GPU/storage where present). Each workload then pays for its fraction of each:

```text
workload cost = (node CPU cost × workload CPU request / node allocatable CPU)
 + (node RAM cost × workload memory request / node allocatable RAM)
```

Worked example. Price the node's \$0.38/hour as 60% CPU / 40% memory (a typical split
for a general-purpose instance), i.e. a **CPU price** of
`$0.38 × 0.6 ÷ 8 vCPU = $0.0285 per vCPU-hour` and a **memory price** of
`$0.38 × 0.4 ÷ 32 GB = $0.00475 per GB-hour`. A workload requesting **2 vCPU and 4 GB**
costs:

```text
CPU: 2 × $0.0285 = $0.0570 /hr
Memory: 4 × $0.00475 = $0.0190 /hr
 ─────────
workload = $0.0760 /hr → × 730 ≈ $55.48 / month
```

That is the whole idea. Notice what drives it: the **request**, not the usage. A team
that requests 2 vCPU "to be safe" and uses 0.3 pays for 2. **Cost is downstream of the
requests you set in ** — which is why right-sizing is the
single biggest optimization lever.

> **Refinement:** real tools charge `max(request, usage)` per resource — you pay for
> what you reserved, but if a burstable pod exceeds its request you pay for the actual
> usage. Requests are the floor; usage above them is still billed.

#### Idle cost: the money nobody requested

Add up what every pod on a node requests and you will almost never reach 100% of the
node. The gap is **idle cost** — capacity you are paying for that no workload reserved:

```text
idle cost (per node) = node cost − Σ (cost allocated to its workloads)
```

Suppose node-7 (\$0.38/hr) hosts workloads requesting **3 vCPU and 6 GB** in total:

```text
allocated CPU: 3 × $0.0285 = $0.0855 /hr
allocated RAM: 6 × $0.00475 = $0.0285 /hr
allocated total = $0.1140 /hr
node cost = $0.3800 /hr
idle cost = 0.38 − 0.114 = $0.2660 /hr ← 70% of the node is paid-for emptiness
```

Idle is the uncomfortable truth of Kubernetes cost: the per-pod numbers look cheap, yet
the node bill is three times their sum. **Someone always pays for idle** — either you
distribute it to tenants (so their showback reflects the real cost of running them) or
the platform absorbs it as overhead. Either way you can only manage it once you can
*see* it.

#### Node efficiency

The flip side of idle is **node efficiency** — how much of what you bought is actually
reserved (or used):

```text
node efficiency = Σ (workload requests) / node allocatable [reservation view]
 = Σ (workload usage) / node allocatable [utilization view]
```

For node-7 above, reservation efficiency is `0.114 / 0.38 ≈ 30%`. A cluster running at
30% efficiency is paying for three machines to do one machine's work. Driving
efficiency up — by right-sizing requests and bin-packing pods onto fewer, fuller nodes — is how you turn idle back into savings.

#### OpenCost and Kubecost

You could compute all of this by hand, but not continuously across a live cluster. Two
tools do it for you:

- **OpenCost** — a CNCF project and the **open specification** for Kubernetes cost
 allocation. It reads pod requests/usage from the Kubernetes API and Prometheus,
 applies a cloud price list (or its built-in defaults), and exposes an **allocation
 API** plus Prometheus metrics. Free and self-hosted.
- **Kubecost** — a commercial product built *on* OpenCost, adding a polished UI,
 long-term retention, savings recommendations, and enterprise features. The allocation
 engine underneath is the same OpenCost model.

We use **OpenCost** because it is free, runs on kind, and teaches the model honestly —
you can see exactly how the numbers are derived rather than trusting a black box.

#### Where the data lands: Grafana

OpenCost exports its allocation as **Prometheus metrics**, which means cost becomes just
another time series next to the latency and saturation dashboards you built in
 and
Project 3. Cost-per-namespace graphs live in the same
Grafana, refreshed on the same cadence — cost treated as a first-class signal, not a
monthly spreadsheet.

---

### 2. Why it matters for platform engineering

- **Attribution is the platform's job because only the platform has both halves.** Teams
 see their workloads; finance sees the invoice. Only the platform operates the cluster
 *and* knows the node prices, so only it can join them. This is a structural
 responsibility, like owning the security baseline.
- **It makes over-provisioning visible and therefore fixable.** Without per-workload
 cost, "just request 4 CPUs to be safe" is invisible. With it, that padding shows up as
 a line a team can see and own — the precondition for every optimization in.
- **Idle is a platform metric, not a team one.** Low node efficiency usually means the
 *platform's* bin-packing, node sizing, or autoscaling needs work — a problem no single
 team can fix.
- **It closes the loop with observability.** You already ship metrics to Prometheus and
 dashboards to Grafana. Cost rides the same rails, so "what does reliability cost?"
 becomes answerable on one screen.

---

### 3. Mental model

Think of a node as a **rented apartment** and pods as **tenants**:

```text
 node-7 ($0.38/hr rent, 8 CPU / 32Gi of floor space)
 ┌───────────────────────────────────────────────────────────────┐
 │ payments-api ██████ (requests 2 CPU / 4Gi) │ pays its share
 │ search-indexer ████████████ (requests 3 CPU / 8Gi) │ pays its share
 │ fluent-bit ▌ (requests 0.1 CPU / 128Mi) │ pays its share
 │ │
 │....... EMPTY ROOMS YOU STILL PAY RENT ON....... │ idle cost
 └───────────────────────────────────────────────────────────────┘
 efficiency = reserved floor space ÷ total floor space ≈ 30%
```

- **Rent** = node price (fixed, whether rooms are full or empty).
- **Each tenant's bill** = their reserved floor space (their *request*) as a share of
 the apartment.
- **Idle** = the empty rooms — paid for, used by no one.
- **Efficiency** = how full the apartment is. The platform's goal is a full apartment,
 not a bigger one.

The rule: **you pay for what you reserve, not what you use.** Attribution follows
requests; waste is the gap between requests and reality.

---

### 4. Minimal implementation

Before installing anything, compute a pod's cost by hand from data the cluster already
has. Read a workload's requests with `kubectl`, then apply the formula:

```bash
## What does this deployment request?
kubectl get deploy payments-api -o \
 jsonpath='{.spec.template.spec.containers[*].resources.requests}'
## → {"cpu":"2","memory":"4Gi"}
```

```bash
## Turn requests + node price into a monthly cost (the OpenCost model, by hand)
NODE_HOURLY=0.38; NODE_CPU=8; NODE_MEM_GB=32
POD_CPU=2; POD_MEM_GB=4
cpu_price=$(echo "$NODE_HOURLY * 0.6 / $NODE_CPU" | bc -l) # 60% of node price is CPU
mem_price=$(echo "$NODE_HOURLY * 0.4 / $NODE_MEM_GB" | bc -l) # 40% is memory
pod_hr=$(echo "$POD_CPU*$cpu_price + $POD_MEM_GB*$mem_price" | bc -l)
printf 'payments-api: $%.4f/hr ≈ $%.2f/month\n' "$pod_hr" "$(echo "$pod_hr*730" | bc -l)"
## → payments-api: $0.0760/hr ≈ $55.48/month
```

That script *is* OpenCost in miniature: read requests, split the node price, multiply by
time. OpenCost just does it for every pod, every node, continuously, with real prices —
which is what the lab installs next.

---

### 6. Production considerations

- **Accuracy depends on the price list.** On kind, OpenCost estimates with built-in
 defaults. In production you wire it to your cloud's real pricing (and your negotiated
 rates / CUDs) so the numbers match the invoice — otherwise showback loses credibility.
- **`max(request, usage)` and shared costs.** Decide how you allocate idle and shared
 platform overhead (logging, ingress): spread it proportionally across tenants, or hold
 it in a `platform` namespace. Both are defensible; pick one and document it.
- **Network costs are harder.** CPU and memory are easy; attributing egress between pods
 needs OpenCost's network daemonset and is inherently approximate. Treat network cost as
 directional, not exact.
- **Prometheus retention is your cost history.** Allocation is only as long-lived as the
 metrics behind it. Size retention (or a long-term store like Thanos/Mimir) for the
 reporting window you need — a month of cost history needs a month of metrics.
- **Run OpenCost as a platform service.** It's one more component you operate: resource
 it, monitor it, and alert if it stops scraping, because silent cost blindness is worse
 than no dashboard.

---

### 7. Common mistakes

- **Allocating by usage instead of request.** Billing a pod only for the CPU it burned
 hides the capacity it *reserved* and made unavailable to others. *Fix:* allocate on
 `max(request, usage)` — you pay for what you hold.
- **Ignoring idle cost.** Per-pod numbers look cheap, so the cluster seems efficient
 while half the node bill is emptiness. *Fix:* track node efficiency and idle as
 first-class metrics; idle is the optimization target, not a rounding error.
- **Believing kind's dollar figures.** OpenCost on kind is *estimated*; treating those
 numbers as your real bill will embarrass you in a FinOps review. *Fix:* integrate real
 cloud pricing before anyone makes decisions on the figures.
- **Workloads with no requests.** BestEffort pods (no requests) show near-zero cost yet
 consume real CPU and memory, corrupting every allocation. *Fix:* enforce requests via
 LimitRange/quotas so every pod is attributable.
- **Treating cost as a monthly export.** A spreadsheet that arrives after the money is
 spent changes nothing. *Fix:* put cost in Grafana next to your SLO dashboards so it's
 seen continuously.

---

## Cost Attribution and Chargeback

> gave you a cost per workload. This module gives it an **owner**. A
> number nobody is accountable for changes nothing; the discipline of FinOps is
> turning "the cluster costs \$80k" into "`team-payments` costs \$9k, here's the
> trend, and here's the lever." That requires a **mandatory label contract**
> (enforced with the same Kyverno you used for security), a decision about
> **showback vs chargeback**, and a report that lands in the team's channel on its
> own.

### 1. Concept

#### Two ways to make cost land on a team

Attribution data can be used two ways, and the order matters:

- **Showback.** You *show* each team what it costs; no money actually moves. It is
 cheap to run, politically low-friction, and surprisingly effective — most teams have
 never *seen* their number and will self-correct once they do. Showback is where you
 start.
- **Chargeback.** You *bill* each team's budget for its cloud spend. Now cost has teeth:
 it competes with headcount and features for real money, which drives the strongest
 accountability. But it demands accurate data, finance buy-in, and trust. Bill a team
 for a number they don't believe and you'll spend the next quarter arguing about the
 meter instead of reducing the bill.

```text
 Showback ─────────────────────────────────▶ Chargeback
 "here is your cost" "here is your invoice"
 low friction, builds awareness high accountability, needs trust
 START HERE EARN THIS with accurate showback
```

The progression is the point. **You earn the right to charge back by first proving,
through showback, that your attribution is accurate.** Skipping to chargeback on shaky
data is the fastest way to discredit the whole FinOps effort.

#### The label taxonomy: the contract that makes attribution possible

Attribution is only as good as the labels under it. You need a small, **mandatory,
consistent** set of keys on every workload. Reusing the scheme
Project 1 established:

- `platform.example.com/team` — the owning team. *Who pays?*
- `platform.example.com/environment` — `production` / `staging` / `development`. Splits
 the expensive prod spend from cheap dev spend.
- `platform.example.com/cost-center` — the finance code this maps to. *Which budget?*
- `app.kubernetes.io/name` — the service. Gives per-application granularity within a
 team.

Two design choices worth understanding:

- **Namespaced keys** (`platform.example.com/…`) avoid collisions with app labels and
 signal that the platform owns and enforces them — they are not teams' to redefine.
- **Consistency is everything.** One team writing `team: payments` and another
 `team: Payments` fractures every report into two half-teams. The taxonomy is a
 *contract*: fixed keys, controlled values, documented, and — crucially — enforced.

Where the labels go matters for OpenCost. OpenCost aggregates by **pod** labels, so the
labels must be on the **pod template** (`spec.template.metadata.labels`), not just the
Deployment's top-level metadata. The coarse, always-reliable boundary is the
**namespace** (often one namespace per team/environment); labels add finer per-service
attribution on top.

#### Enforcing the contract with Kyverno

A taxonomy that relies on people remembering decays exactly like the security checklist
did in so you enforce it the same way. A `require-cost-labels`
ClusterPolicy inspects every workload at admission and **rejects any that lack the
mandatory labels**. You roll it out the safe way you already know:

```text
Audit ──(measure the gap via policy reports)──▶ Enforce ──(reject non-compliant)──▶
```

This is the course theme made literal: **cost labels are structural, not bolt-on**, and
the same admission-control guardrail that makes workloads secure by default makes them
*attributable* by default. (A more advanced setup uses a Kyverno **mutate** rule to
*add* a default `cost-center` from the namespace, reserving hard `validate` rejections
for the labels only a human can supply — like `team`.)

#### From labels to per-team reporting

With labels enforced and OpenCost running, reporting is a query. OpenCost aggregates
allocation by any label:

```text
GET /allocation/compute?window=7d&aggregate=label:team → cost per team
GET /allocation/compute?window=7d&aggregate=namespace → cost per namespace
```

Two delivery channels turn that query into behavior change:

- **Dashboards.** A Grafana row per team (filtered on the team label) shows each team
 its own 30-day trend next to the latency and error dashboards it already watches —
 cost as just another signal.
- **A pushed weekly report.** Dashboards require someone to go and look; most won't. A
 weekly job queries OpenCost per team, formats "this week vs last week, top services,
 anything anomalous," and posts it to each team's Slack channel. Push beats pull.

#### The FinOps conversation

The hardest part is not the tooling; it's the conversation. A few rules that keep it
productive:

- **Lead with trend and unit economics, not absolute dollars.** "Your cost per request
 rose 30% after Tuesday's deploy" is an engineering bug report. "You spent \$9,000" is
 just a number that invites defensiveness.
- **Make it their data, with levers attached.** Hand teams their own dashboard and a
 concrete recommendation ("these five workloads request 4× what they use"), not a
 scolding.
- **Frame cost as a quality attribute**, peer to latency and reliability — something
 good engineers tune, not a punishment. The platform's job is to make the efficient
 path the easy one, never to play cost police.

---

### 2. Why it matters for platform engineering

- **Attribution is the deliverable of the whole "Inform" phase.** Without a credible
 per-team number, optimization is unfocused guessing and governance is just politics.
 Everything in and 18.5 assumes this data exists and is trusted.
- **The label contract is a platform responsibility.** Only the platform can define one
 taxonomy for everyone and *enforce* it uniformly — a team can't make its peers label
 consistently. This is identical in shape to owning the security baseline.
- **Showback is the cheapest behavior-change tool you have.** Making cost visible to the
 people who create it, with no billing machinery, moves numbers on its own.
- **It's where platform meets finance.** The `cost-center` label is the join key between
 your cluster and the company's budget. Get it right and chargeback becomes possible;
 get it wrong and finance never trusts your data.

---

### 3. Mental model

Hold the **attribution pipeline** — each stage owned by a tool you already know:

```text
 LABEL ALLOCATE REPORT ACT
 ───── ──────── ────── ───
 Kyverno ─▶ OpenCost ─▶ Grafana + Slack ─▶ team right-sizes
 enforces splits node per-team trend platform commits CUDs
 the taxonomy cost by label pushed weekly finance charges back
 (18.3) (18.2) (18.3) (18.4 / 18.5)

 Maturity: showback ───────────────────────────▶ chargeback
 (show the number) (bill the budget)
```

The rule: **enforce the label, trust the allocation, push the report, and only then
discuss the money.** Skip a stage and the conversation collapses into an argument about
the data.

---

### 4. Minimal implementation

The smallest useful attribution is one enforced label plus one aggregation query.

The policy — require a `team` label on the pods of every Deployment (start in Audit):

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
 name: require-team-label
spec:
 validationFailureAction: Audit
 background: true
 rules:
 - name: check-team-label
 match:
 any:
 - resources:
 kinds: [Deployment]
 validate:
 message: "Every workload must set spec.template.metadata.labels['platform.example.com/team']."
 pattern:
 spec:
 template:
 metadata:
 labels:
 platform.example.com/team: "?*"
```

The report — cost per team, straight from OpenCost:

```bash
curl -sG http://localhost:9003/allocation/compute \
 -d window=7d -d aggregate=label:team -d accumulate=true \
| jq -r '.data[0] | to_entries | sort_by(-.value.totalCost)
 |.[] | "\(.key)\t$\((.value.totalCost*100|round)/100)"'
```

Enforce the label, and `?*` (Kyverno's "any non-empty value") guarantees every future
workload is attributable. Aggregate by it, and you have a per-team bill. Everything
else — more labels, dashboards, Slack — is scale and polish on these two moves.

---

### 6. Production considerations

- **Showback first, always.** Run showback until teams trust the numbers and the data
 reconciles with the cloud invoice. Only then discuss chargeback — and introduce it
 gradually (e.g. charge back a subset of clearly-attributable cost first).
- **Have a plan for shared and idle cost.** Idle, ingress, logging, and the platform's
 own components aren't any one team's. Decide a split rule — spread proportionally to
 usage, or hold it in a `platform` cost-center — and make it **transparent**, because
 unexplained "overhead" on a team's bill destroys trust.
- **Backfill existing workloads.** Flip the policy to Enforce only after Audit shows the
 gap is closed; give teams a window and a mutate-default where you safely can, so
 enforcement doesn't block deploys on day one.
- **Normalize values, not just keys.** Consider a Kyverno rule (or CI check) that
 rejects unknown `team`/`environment` values, so `prod`, `production`, and `Prod` don't
 become three cost centers.
- **Make reports actionable, not noise.** A weekly report that's just a number gets
 muted. Highlight the *change* and the *anomaly*, and attach the lever. (Anomaly
 alerting is.)
- **Reconcile with the bill.** Periodically check that the sum of attributed cost plus
 idle equals the actual invoice. Drift means your price list or allocation rules need
 attention.

---

### 7. Common mistakes

- **Chargeback before trust.** Billing teams on inaccurate or unexplained data turns
 every finance meeting into an argument about the meter. *Fix:* earn chargeback with a
 period of accurate, reconciled showback.
- **Inconsistent label keys or values.** `team` vs `Team`, `prod` vs `production` —
 each split fractures the report. *Fix:* namespaced keys, a controlled value list, and
 enforcement (optionally a mutate rule that normalizes).
- **Labeling the Deployment but not the pod template.** OpenCost aggregates on *pod*
 labels, so top-level-only labels produce empty per-team reports. *Fix:* require the
 labels on `spec.template.metadata.labels`.
- **Enforcing on day one.** Flipping straight to Enforce rejects every existing
 non-compliant deploy and causes an outage of goodwill. *Fix:* Audit → measure →
 backfill → Enforce.
- **Hiding shared cost or dumping it on teams.** Silently spreading idle onto tenants
 makes their numbers look wrong and untrustworthy. *Fix:* an explicit, documented
 shared-cost policy.
- **Playing cost police.** Reports framed as blame make teams hide from FinOps. *Fix:*
 give teams their own data and levers; make the efficient path the easy one.

---

## Cost Optimization Patterns

> You can now see cost and attribute it to an owner. This module **reduces** it. The
> waste in a typical cluster is not mysterious — it is a handful of recurring patterns:
> workloads that request far more than they use, dev environments running at 3 a.m.,
> half-empty nodes, on-demand prices for interruptible work, and orphaned disks nobody
> deleted. Each has a specific fix, and the fixes have an **order**. Get the order
> wrong — commit before you right-size — and you lock in the very waste you meant to
> remove.

### 1. Concept

#### The waste taxonomy

Every optimization pattern targets a specific kind of waste. Name the waste first:

- **Over-provisioned** — requests far exceed usage. → *right-size.*
- **Idle / always-on** — running when nobody needs it (nights, weekends). → *scale-to-zero.*
- **Poorly packed** — many half-empty nodes. → *bin-pack / consolidate.*
- **Wrong purchase option** — on-demand for interruptible work, or an un-committed steady
 floor. → *spot* and *commitments.*
- **Orphaned** — unattached disks, idle load balancers, reserved IPs, dead namespaces.
 → *delete.*
- **Wrong tier** — hot storage for cold data, avoidable egress. → *tiering / egress
 reduction.*

The rest of this section is one pattern per waste type.

#### Pattern 1 — Right-sizing (the biggest, safest lever)

Cost follows **requests**, and most workloads request far more than they
use "to be safe." Right-sizing pulls requests down toward real usage. The
**Vertical Pod Autoscaler** does the observing: in `updateMode: "Off"` it
watches actual consumption and publishes a *recommendation* without touching the pod,
so you can review and apply it deliberately.

The judgment call is *which usage number to target*. Right-size to a **high percentile
plus headroom** (think p95–p99), never the average — a request set to p50 means half the
time the pod is throttled or `OOMKilled`. Right-sizing is high-leverage precisely
because it is low-risk *when you leave headroom*.

#### Pattern 2 — Spot for interruptible work

Spot/preemptible capacity is 60–90% cheaper in exchange for being reclaimable with
little notice. The rule is simple: **spot is for work that can die and
retry** — batch jobs, CI runners, dev environments, and stateless replicas that have
siblings. Make it safe with **PodDisruptionBudgets**, spreading replicas across nodes,
and an **on-demand fallback** when spot capacity disappears. Never put a stateful
singleton or a critical control-plane component on spot.

#### Pattern 3 — Bin-packing and consolidation

The scheduler places pods by request, but it does not *re-pack* them as workloads come
and go, so you drift into many half-full nodes. **Karpenter** fixes this with
**consolidation**: it continuously looks for pods it could move onto fewer, fuller nodes
and then removes the emptied ones — and when it does add a node, it provisions a
right-sized one just-in-time. This is the pattern that turns the **node efficiency** gap
from back into money. Consolidation causes controlled pod churn, so it
**respects PodDisruptionBudgets**. (The older Cluster Autoscaler only adds/removes nodes
for pending pods; it does not actively re-pack.)

#### Pattern 4 — Scale-to-zero off-hours

A production service can't scale to zero, but your **dev, staging, and preview**
environments have no reason to run nights and weekends — which is roughly **two-thirds
of the week**. Scaling non-prod workloads to zero on a schedule (a CronJob, or a KEDA
cron scaler) simply deletes that spend. The engineering detail is **restoring the right
replica count** in the morning, so real implementations store the original count (for
example in an annotation) rather than hard-coding it.

#### Pattern 5 — Commitments on the lean floor

Once requests are right-sized and nodes consolidated, you have a true **steady floor** —
the capacity that genuinely runs 24/7. *That* is what you commit to with a 1-year CUD or
reservation, and the platform makes the commitment for the whole fleet.
The ordering is the whole point: committing *before* right-sizing buys a discount on
bloat.

#### Pattern 6 — Storage tiering and egress

The non-compute costs are easy to ignore and add up:

- **Storage** — delete unattached volumes and old snapshots, right-size over-provisioned
 disks, and move cold data down the tiers (standard → nearline → coldline → archive).
- **Egress** — keep chatty traffic in-zone/in-region, front static assets with a **CDN**,
 and avoid shipping uncompressed logs out of the cloud.

#### Pattern 7 — Delete idle resources

Orphaned load balancers, unattached persistent disks, reserved-but-unused IPs, abandoned
namespaces, and old container images all bill for nothing. Detect them (OpenCost's idle
view, cloud recommenders) and delete them on a grace period — ideally automatically.

#### The order matters

```text
1. SHRINK right-size requests to real usage → fewer resources per pod
2. PACK consolidate pods onto fewer, fuller nodes → fewer nodes
3. SLEEP scale non-prod to zero off-hours → fewer node-hours
4. BUY RIGHT spot for interruptible, CUD for the floor → cheaper per node-hour
5. CLEAN delete orphaned disks, LBs, namespaces → stop paying for nothing
```

Always **shrink before you buy.** Right-sizing and consolidation shrink the floor;
commitments and spot make that lean floor cheaper. Reverse the order and you commit to
waste.

---

### 2. Why it matters for platform engineering

- **This is where FinOps pays for itself** — but only on top of attribution. You spend
 your effort on the biggest and most wasteful workloads *because told you
 which they are.* Optimizing blind is how you save \$5 on a dev pod while a right-sizing
 opportunity worth thousands sits untouched.
- **The patterns are platform capabilities, not per-team chores.** Consolidation, spot
 node pools, off-hours schedules, and fleet commitments are things the platform
 operates once and every team inherits — the paved road, applied to cost.
- **Optimization must not trade away reliability.** Every pattern here has a failure mode
 (OOM from over-tight requests, outages from spot reclaim, disruption from
 consolidation). Doing them *safely* — headroom, PDBs, non-prod only — is the platform's
 responsibility and the subject of the cost/quality/reliability triangle in.
- **Right-sizing closes the loop with.** The requests you learned to set
 there are the single biggest cost lever; VPA makes setting them data-driven instead of
 guesswork.

---

### 3. Mental model

Climb the **optimization ladder** top to bottom; each rung multiplies the next:

```text
 risk typical first win
 1. SHRINK right-size requests (VPA) ▇▇▇▇ low 20–50% of requests
 2. PACK consolidate nodes (Karpenter) ▇▇▇ medium 30–40% fewer nodes
 3. SLEEP scale non-prod to zero off-hours ▇▇ low ~65% off dev spend
 4. BUY RIGHT spot + committed-use discounts ▇▇▇▇ medium 60–90% (spot) / ~57% (CUD)
 5. CLEAN delete orphaned disks/LBs/ns ▇ low pure waste removed

 Golden rule: SHRINK before you BUY RIGHT — never commit to bloated requests.
```

The mnemonic: **shrink, pack, sleep, buy right, clean.** Start at the top (biggest,
safest) and only commit money once the floor is lean.

---

### 4. Minimal implementation

Right-size one workload straight from its VPA recommendation. First read what VPA
learned by watching real usage:

```bash
kubectl get vpa payments-api \
 -o jsonpath='{.status.recommendation.containerRecommendations[0].target}'
## → {"cpu":"27m","memory":"115Mi"} (it was requesting 1 CPU / 1Gi)
```

Then apply a right-sized request with a little headroom above the recommendation:

```bash
kubectl patch deploy payments-api --type=merge -p '{
 "spec": {"template": {"spec": {"containers": [
 {"name": "nginx", "resources": {"requests": {"cpu": "50m", "memory": "128Mi"}}}
 ]}}}}'
```

The cost math is immediate: dropping the CPU request from
`1000m` to `50m` cuts this workload's CPU cost by **20×**. Multiply that by five
over-provisioned workloads and you have the lab's headline saving — with no code change
and, because you kept headroom, no reliability cost.

---

### 6. Production considerations

- **Right-size to a percentile, then watch.** Target p95–p99 with headroom and monitor
 for `OOMKilled`/throttling afterward. Requests drift back up over time, so right-sizing
 is continuous, not one-off.
- **VPA and HPA can fight.** Don't run VPA in `Auto` on the *same resource metric* an HPA
 scales on — they oscillate. Use VPA for requests and HPA for replicas on *different*
 signals, or a multidimensional autoscaler.
- **Spot needs blast-radius control.** PodDisruptionBudgets, anti-affinity to spread
 replicas, and an on-demand fallback pool; never 100% of a service's replicas on spot.
- **Consolidation is disruption.** It evicts and reschedules pods, so gate it with PDBs
 and, for sensitive workloads, maintenance windows or rate limits.
- **Scale-to-zero needs state handling.** Preserve the original replica count (annotation
 or a controller), account for cold starts, and never apply it to stateful or
 production workloads.
- **Measure savings and guard against regression.** Record before/after cost per
 optimization and set an efficiency target (e.g. cluster request-utilization > 60%) so
 wins don't silently erode.
- **Automate orphan cleanup carefully.** Dry-run first, grace periods, and an allowlist —
 deleting a "disused" PVC that held real data is an expensive mistake.

---

### 7. Common mistakes

- **Right-sizing to the average.** Setting requests at p50 saves money until the next
 traffic peak throttles or OOMKills the pod. *Fix:* target p95–p99 and leave headroom.
- **Committing before right-sizing.** A 1-year CUD bought against bloated requests locks
 in the waste for a year. *Fix:* shrink and consolidate first, then commit the lean
 floor.
- **Spot for stateful or singleton-critical workloads.** The discount is irresistible
 until a reclaim event kills your only database replica. *Fix:* spot only for
 interruptible, replicated, retryable work — with a PDB and a fallback.
- **Aggressive consolidation without PodDisruptionBudgets.** Re-packing evicts pods; with
 no PDB you can take a service below quorum. *Fix:* set PDBs before enabling
 consolidation.
- **Optimizing the small stuff.** Hours spent shaving a dev pod while the top-five costly
 workloads go untouched. *Fix:* attribute first, then optimize the biggest
 and least efficient.
- **Treating it as a one-time cleanup.** Requests re-inflate, new orphans appear. *Fix:*
 continuous right-sizing, scheduled orphan sweeps, and an efficiency alert.

---

## FinOps Culture and Process

> Tools make cost *visible* and *lower*; culture keeps it that way. Right-sized
> requests re-inflate, new orphans appear, and last quarter's savings quietly erode
> unless cost becomes a **standing engineering practice** — owned by the teams that
> create it, measured in **unit economics**, watched by **anomaly alerts**, and kept on
> the rails by **platform governance**. This module turns the mechanics of the last
> four lessons into a durable operating model: Inform → Optimize → **Operate**.

### 1. Concept

#### FinOps is a practice, not a department

The FinOps Foundation defines FinOps as a **cultural practice** that brings financial
accountability to the variable spend of cloud, letting teams make deliberate trade-offs
between speed, cost, and quality. The emphasis is *cultural*. A central "cost team" that
owns all cost decisions recreates the gatekeeper anti-pattern you rejected in — a bottleneck everyone routes around. FinOps works when responsibility is shared:

- **Engineering** owns its spend and its unit economics, like it owns its latency.
- **The platform** provides the visibility, the paved road, and the guardrails (every
 tool in this phase).
- **Finance** provides budget context, forecasting, and the commitment framework.
- **Product** weighs cost against features in prioritization.

The platform's role is **enablement**: make the efficient path the easy, default path,
and give every team its own data and levers — not to police them.

#### The lifecycle: Inform → Optimize → Operate

The FinOps Foundation framework is a continuous loop, and this whole phase is one lap of
it:

- **Inform** — visibility, allocation, budgeting, benchmarking. You cannot manage what
 you cannot see.
- **Optimize** — identify and act on waste: right-size, consolidate, spot, commit.
- **Operate** — make it continuous: govern, review, forecast, and alert so the gains
 from Optimize don't decay (this module).

Teams enter at different maturity — the Foundation calls it **Crawl → Walk → Run**. You
don't launch full chargeback, unit economics, and anomaly alerting on day one; you crawl
(showback, basic tags), then walk (optimization, reviews), then run (automated
governance, forecasting).

#### Unit economics: the number that makes cost mean something

An absolute bill is almost useless on its own. A spend that **doubled** is *good* news if
traffic **tripled** — your efficiency improved. The metric that captures this divides
cost by a business quantity:

```text
unit cost = total cost / business unit
 = $ per 1,000 requests · $ per active user · $ per order · $ per tenant
```

Unit economics is the single most important FinOps metric because it:

- turns "we spent \$80k" into "**\$0.002 per request, down 12% this quarter**" — a trend
 an engineer and a CFO both understand;
- distinguishes **good cost** (scales with revenue/usage) from **bad cost** (scales with
 waste); and
- is the bridge between the cluster and the business, making cost a *product* metric
 rather than an IT line item.

If you build one thing from this module, build a unit-cost metric for your most important
service.

#### The cost / reliability / velocity triangle

You cannot maximize all three of **low cost**, **high reliability**, and **high delivery
velocity** at once — push hard on any corner and another pays:

```text
 LOW COST
 / \
 / \
 RELIABILITY —— VELOCITY
 (optimize any two; the third corner pays the bill)
```

Squeeze cost to the bone and you remove the headroom and redundancy that reliability
needs, or you starve teams of the capacity that keeps them fast. The FinOps job is **not
to minimize cost** — it is to make the trade-off *conscious*. That is why cost lives next
to your SLOs: a reliability budget and a cost budget are two dials on the same
console, set deliberately per workload. A payments service and a nightly report sit at
very different points on the triangle, and that's correct.

#### Cost reviews: making it routine

"Operate" means cost stops being a monthly surprise and becomes a standing concern,
reviewed on a cadence:

- A **weekly** per-team report in the team's channel.
- A **monthly** review where each team looks at its trend and unit economics alongside
 its SLOs.
- **Quarterly** commitment planning (CUD coverage) with finance.

The cultural shift is treating a **cost regression like a performance regression**: if
the bill jumped after Tuesday's deploy, that's a bug to investigate, not a fact of life.

#### Anomaly detection and alerting

Nobody watches a dashboard. Durable cost control needs **alerts** that fire when spend
behaves abnormally — for example, a team's cost rising **more than 20% week-over-week**,
or an hourly cost rate that suddenly steps up. Because you attributed cost in,
the alert can route to the **owning team**, exactly like an SRE page. You build these from
cloud provider anomaly detection or your own rules over OpenCost metrics in Prometheus —
and you tune them for seasonality and launches so they signal rather than nag. **Cost is
just another SRE signal.**

#### Governance: guardrails, not gates

Finally, the platform keeps the whole fleet on the efficient path by making good choices
the default — the same paved-road philosophy as security:

- **Required requests and autoscaling** — LimitRange/ResourceQuota so nothing runs
 resource-less or unbounded; HPA/VPA available by default.
- **Required cost labels** — the Kyverno policy from, so all spend is
 attributable.
- **Approved instance types / families** — a curated menu, not the full catalog, so teams
 can't accidentally pick a wildly expensive node.
- **Per-namespace budgets** — a ResourceQuota is a *cost cap* as much as a fairness tool.

Governance is guardrails with escape hatches, not a committee that approves tickets. A
gate becomes a bottleneck; a guardrail scales.

---

### 2. Why it matters for platform engineering

- **Without Operate, the savings decay.** Requests re-inflate, new orphans accrue, and the
 work of silently unwinds. Culture and automation are what make the gains
 *stick*.
- **Unit economics is how cost earns a seat at the engineering table.** It reframes cost
 as a tunable quality attribute and connects platform work to business outcomes — the
 argument that funds the platform.
- **Shared practice scales; a cost team does not.** Centralizing every cost decision
 recreates the gatekeeper bottleneck. The platform enables; teams own.
- **Anomaly alerting prevents the month-end shock.** Catching a runaway bill on the day it
 starts — routed to the team that caused it — is the difference between a \$200 blip and a
 \$20,000 surprise.
- **Governance is leverage.** Encoding the efficient defaults once, for everyone, is the
 same high-leverage move that makes security structural.

---

### 3. Mental model

Hold the **flywheel** and the **triangle** together:

```text
 ┌──────────────── INFORM ────────────────┐
 │ see & attribute cost (18.1–18.3) │
 ▼ │
 OPERATE ◀──────────────────────────── OPTIMIZE
 govern · review · anomaly-alert right-size · spot · consolidate
 (18.5) (18.4)
 │ ▲
 └─────────────────────────────────────────┘
 each lap lowers COST PER UNIT at the SAME reliability

 Every decision is a point on the triangle:
 LOW COST
 / \
 RELIABILITY — VELOCITY ← choose the trade on purpose, per workload
```

The rule: **spin the flywheel, don't do a one-time cleanup.** FinOps is operated, like
reliability — and every optimization is a conscious move on the triangle, never blind
minimization.

---

### 4. Minimal implementation

Two tiny artifacts capture the heart of "Operate": a unit cost and an anomaly threshold.

Unit economics — cost per 1,000 requests:

```bash
COST_THIS_WEEK=1420.00
REQUESTS_THIS_WEEK=71000000
echo "scale=4; $COST_THIS_WEEK / ($REQUESTS_THIS_WEEK / 1000)" | bc -l
## → 0.0200 → $0.0200 per 1,000 requests (track this trend, not the raw $1,420)
```

Anomaly rule — the plain-language version you'll encode as an alert:

```text
IF this_week_cost(team) > 1.20 × last_week_cost(team)
THEN page the owning team # a 20% week-over-week jump is a cost regression to triage
```

That is the Operate phase in miniature: a number that tells you if efficiency is
improving, and a trigger that tells a specific team when it isn't. The lab turns both
into a reusable process document (and an optional Prometheus alert).

---

### 6. Production considerations

- **Meet teams at their maturity.** Don't mandate run-level practices on a crawl-level
 team. Sequence Crawl → Walk → Run so FinOps feels like enablement, not audit.
- **Tune anomaly alerts for the real world.** Account for seasonality, marketing launches,
 and planned scale-ups, and always route to the owning team with context — a noisy cost
 alert gets muted exactly like a noisy page.
- **Instrument the denominator.** Unit economics needs a trustworthy business metric
 (requests, active users, orders). If you can't measure the denominator reliably, fixing
 that is the prerequisite.
- **Make the triangle explicit per workload.** Record, per service, where it sits — a
 payments API buys reliability with cost; a batch job buys cost with latency. Ambiguity
 here is how "save money" becomes an outage.
- **Report up in unit economics and trend**, not raw dollars. Executives act on "cost per
 order fell 15%," not a six-figure lump sum.
- **Govern with guardrails and escape hatches.** A curated instance menu and required
 autoscaling scale; a per-request approval gate does not. Keep a documented exception
 path so teams don't route around you.

---

### 7. Common mistakes

- **Running FinOps as a cost-cutting mandate or a central team.** It breeds resentment and
 a bottleneck, and teams disengage. *Fix:* a shared practice where the platform enables
 and teams own their spend.
- **Optimizing without unit economics.** You "cut costs" by throttling a service whose
 spend was actually efficient, hurting the business to shave a bill. *Fix:* measure cost
 per unit and cut *bad* cost, not *all* cost.
- **No anomaly detection.** The runaway bill is discovered at month-end, long after it
 could have been stopped. *Fix:* alert on week-over-week spikes, routed to the owner.
- **Governance as approval gates.** Per-request sign-off becomes a bottleneck and spawns
 shadow workarounds. *Fix:* paved-road guardrails (policies, quotas, a curated menu) with
 escape hatches.
- **Blind cost minimization.** Pushing the cost corner alone quietly spends reliability or
 velocity. *Fix:* make the triangle trade-off conscious and tie it to SLOs.
- **Treating optimization as one-and-done.** Savings erode without the Operate loop. *Fix:*
 reviews, alerts, and governance that keep spinning the flywheel.

---

---

## References

- FinOps Foundation — [What is FinOps / the Framework](https://www.finops.org/framework/)
- FinOps Foundation — [Unit Economics](https://www.finops.org/wg/unit-economics/)
- Google Cloud — [Committed Use Discounts](https://cloud.google.com/docs/cuds)
- Google Cloud — [Spot VMs](https://cloud.google.com/compute/docs/instances/spot) and [create and use budgets](https://cloud.google.com/billing/docs/how-to/budgets)
- Google Cloud — [Network pricing (egress)](https://cloud.google.com/vpc/network-pricing)
- AWS — [Pricing Calculator](https://calculator.aws/) (model before you build)
- OpenCost — [How cloud costs are modeled](https://www.opencost.io/docs/configuration/)
- OpenCost — [Documentation](https://www.opencost.io/docs/) and the [cost allocation specification](https://www.opencost.io/docs/specification)
- OpenCost — [Installing with Helm](https://www.opencost.io/docs/installation/install) and the [Allocation API](https://www.opencost.io/docs/integrations/api)
- Kubecost — [How cost allocation works](https://docs.kubecost.com/using-kubecost/navigating-the-kubecost-ui/cost-allocation)
