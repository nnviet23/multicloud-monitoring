# 07 · Observability Engineering

> **Project Applicability:** Active in Project — Core observability stack using **OpenTelemetry Collector**, **Prometheus + Thanos**, **Grafana Loki**, **Tempo**, **Grafana**, and **Pyrra** for SLO-as-code (instead of Sloth).

> You can now build platforms *on* Kubernetes (Phases 3–10). But a platform you
> cannot **see into** is a platform you cannot operate, improve, or trust. This
> phase turns you from someone who *installs* Prometheus into someone who *designs
> the signals* a platform runs on — metrics, logs, and traces unified through
> OpenTelemetry, surfaced in Grafana, and governed by SLOs and error budgets.

## Why observability?

Every platform you have built so far has a blind spot. In Project 1 you onboarded
teams; in you delivered them with GitOps; in you taught the API new
nouns. None of it tells you whether any of it is **working right now** — whether a
deploy made latency worse, which team's runaway query is saturating a node, or why a
developer's request died three services deep.

The reflex is to "add monitoring": a CPU graph, a uptime check, a Slack alert. That
is where most teams stop, and it is not enough. **Monitoring** answers questions you
already knew to ask. **Observability** is the property that lets you ask *new*
questions — about failures you did not predict — from the data your systems already
emit. At platform scale, with hundreds of services you did not write, you cannot
predict the failures. You need observability.

This phase builds that capability from first principles:

- **The theory** — monitoring vs observability, the three pillars (metrics, logs,
 traces), RED / USE / the four golden signals, and the two costs that govern every
 design decision: **cardinality** and **sampling**.
- **The standard** — OpenTelemetry, the vendor-neutral way to instrument once and
 export anywhere, so your platform is never captive to one backend.
- **The stack** — the open-source **LGTM** stack (Loki for logs, Grafana for
 visualization, Tempo for traces, and Mimir / Prometheus for metrics), which you
 will run locally and for free.
- **The discipline** — SLIs, SLOs, SLAs, and multi-window burn-rate alerting, so you
 alert on **user pain**, not on every twitch of a CPU graph.
- **The strategy** — what a *platform team* observes that application teams do not,
 and how to turn signals into runbooks and a paging policy.

Everything here feeds directly into **Project 3 · Observability Platform** (the next
phase), where you will assemble these components into a single self-service product
that every team consumes.

## Observability Fundamentals

> Monitoring tells you *that* something is wrong. Observability lets you ask *why* —
> including for failures you never predicted. This module defines observability from
> first principles, introduces the three pillars and the signal frameworks (RED,
> USE, the four golden signals), and names the two costs — **cardinality** and
> **sampling** — that shape every decision you will make for the rest of the phase.

**You'll need:** concepts and Python 3
for a tiny experiment. No cloud, no cluster.

### Learning objectives

By the end of this module you will be able to:

- Distinguish **monitoring** from **observability** and explain why platform scale
 forces the shift.
- Describe the **three pillars** — metrics, logs, traces — and pick the right one
 for a question.
- Apply **RED**, **USE**, and the **four golden signals** to services and resources.
- Explain **cardinality** and **sampling**, and why they cap what you can afford to
 collect.
- Name the signal a platform owes its tenants versus the signals each app team owns.

---

### 1. Concept

See the end-to-end telemetry model in Observability data flow.

#### Observability borrowed from control theory

The word comes from control theory: a system is **observable** if you can infer its
complete internal state purely from its external outputs. Transplanted to software:
a system is observable when its *outputs* — the telemetry it emits — let you
reconstruct what is happening *inside* it, without shipping new code to answer each
new question.

That last clause is the whole game. If answering "why are checkout requests slow for
users in Germany on the new app version?" requires you to add a log line and redeploy,
your system was not observable with respect to that question. If the data was already
there and you just had to query it, it was.

#### Monitoring vs observability

These are related but not the same, and conflating them is the most common
conceptual error in this field.

- **Monitoring** is collecting and alerting on **predefined** signals. You decide in
 advance what matters — CPU, error rate, a health check — build a dashboard and an
 alert, and watch it. Monitoring answers **known questions**: "Is the thing I
 expected to break, broken?"
- **Observability** is a **property of the system**: how well its telemetry lets you
 explore **unknown** questions after the fact. Observability answers **novel
 questions**: "This symptom is new and I did not predict it — can I still get to the
 cause from the data I already have?"

Monitoring is a *subset* of what observability enables. You still build dashboards
and alerts — but on top of rich, high-dimensional telemetry you can slice and dice,
rather than a handful of pre-aggregated numbers. The shift matters because at
platform scale you operate **hundreds of services you did not write**. You cannot
predict their failure modes, so you cannot pre-build every dashboard. You need the
ability to ask new questions.

#### The three pillars

Observability telemetry comes in three complementary shapes. None is sufficient
alone; the power is in correlating them.

- **Metrics** — numeric measurements aggregated over time (a request counter, a CPU
 gauge, a latency histogram). Cheap to store and fast to query because they are
 just numbers over time. Great for **trends, dashboards, and alerts**; poor at
 explaining a *single* weird request because the detail was aggregated away.
- **Logs** — timestamped records of discrete events, ideally **structured**
 (key-value / JSON) rather than free text. Great for the **detail of what happened**
 in one event; expensive at volume and hard to aggregate if unstructured.
- **Traces** — the end-to-end journey of **one request** across many services,
 broken into timed **spans**. Great at answering **"where did the time go and where
 did it fail"** across a distributed call graph; they need context propagation and
 are usually **sampled**.

```text
Question Reach for…
────────────────────────────────────── ──────────
"Is error rate rising across the fleet?" Metrics (aggregate, trend, alert)
"What exactly happened in request X?" Logs (the event detail)
"Which of 9 services made X slow?" Traces (the span waterfall)
```

#### Frameworks: RED, USE, and the four golden signals

You do not instrument randomly. Three battle-tested frameworks tell you *which*
signals to collect first.

- **RED** (for **request-driven services**): **R**ate (requests/sec), **E**rrors
 (failed requests/sec), **D**uration (latency distribution). If you measure only
 three things about a service, measure these.
- **USE** (for **resources** — nodes, disks, queues): **U**tilization (how busy),
 **S**aturation (how much queued/overcommitted work is waiting), **E**rrors
 (device/driver errors). RED watches the work; USE watches the machine doing it.
- **The four golden signals** (Google SRE, for **any user-facing system**):
 **Latency**, **Traffic**, **Errors**, **Saturation**. A superset-flavored blend of
 RED and USE; the canonical "if you can only build one dashboard" list.

A subtle but critical point about **latency**: always separate the latency of
**successful** requests from **failed** ones, and report **percentiles**
(p50/p95/p99), never just an average. A fast error and a slow success both lie to a
mean. Tail latency is where users actually feel pain.

#### The two costs: cardinality and sampling

Every design choice in this phase is a trade against two costs.

**Cardinality** is the number of unique time series a metric produces — one series
per unique combination of label values. It multiplies:

```text
http_requests_total{method, status, path, pod}

 methods(4) × statuses(5) × paths(200) × pods(50) = 200,000 series
 for ONE metric name
```

Add a high-cardinality label like `user_id` or a raw URL with IDs in it, and series
count explodes into the millions. Memory, storage, and query cost scale with series
count, so **high-cardinality labels are the number-one way to melt a metrics
backend**. The fix is discipline: labels are for *bounded, low-cardinality*
dimensions (method, status, route **template**), never unbounded identifiers.

**Sampling** is the answer to a different scale problem: you cannot afford to store a
trace for **every** request at high throughput. So you keep a representative subset —
a fixed percentage (**head sampling**) or a smart selection that keeps all the errors
and slow ones (**tail sampling**, ). Sampling trades completeness for
affordability; the art is keeping the *interesting* requests.

---

### 2. Why it matters for platform engineering

- **You are on the hook for systems you did not write.** A platform runs other
 teams' code. When something breaks at 2am, "add a log line and redeploy" is not
 available to you — the service is not yours. Observability is the only way you can
 debug a black box you operate but did not author.
- **Signals are a platform product, not an afterthought.** "Every service gets RED
 metrics, structured logs, and traces, pre-wired, for free" is a golden path — one
 of the most valuable things a platform offers. You are selling *insight as a
 default*, not asking each team to reinvent it.
- **Cardinality is a multi-tenant blast radius.** One team's careless `user_id`
 label can bankrupt the shared metrics store for **everyone**. Governing
 cardinality is a platform responsibility, the same way you govern CPU with quotas.
- **Observability is what makes SLOs possible.** You cannot have a Service Level
 Objective without a Service Level Indicator, and an SLI is just a
 well-chosen signal. The discipline starts here.

---

### 3. Mental model

Hold three pictures in your head for the rest of the phase.

**1. Pillars answer different questions; correlation is the payoff.**

```text
 METRICS LOGS TRACES
 (aggregate numbers) (event detail) (one request's path)
 ┌───────────────────┐ ┌──────────────────┐ ┌──────────────────────┐
 │ error rate rising │──▶│ which errors? │──▶│ which hop failed, and │
 │ (alert fires) │ │ (exact messages) │ │ where did time go? │
 └───────────────────┘ └──────────────────┘ └──────────────────────┘
 "something is wrong" "what, exactly" "why, across services"

 The value is the ARROWS: jump metric → log → trace on a shared trace_id.
```

**2. Monitoring is a flashlight; observability is turning the lights on.**
A flashlight shows you where you already pointed it (the dashboards you pre-built).
Observability lights the whole room so you can look wherever the new problem is.

**3. Every signal has a price tag.**

```text
 cheap, coarse ───────────────────────────────▶ rich, expensive
 metrics structured logs traces (sampled)
 (aggregate) (per event) (per request)
 ▲ ▲
 │ cardinality is the hidden cost here │ sampling is the lever here
```

The engineering is choosing the cheapest signal that can still answer the question,
and spending the expensive signals only where they earn it.

---

### 4. Minimal implementation

You do not need a cluster to feel the core idea. The simplest possible "metric" is a
counter you increment and expose as text — the same format Prometheus scrapes. And the simplest way to *feel cardinality* is to multiply label
cardinalities and watch the series count explode.

A hand-rolled Prometheus exposition looks exactly like this:

```text
# HELP http_requests_total Total HTTP requests.
# TYPE http_requests_total counter
http_requests_total{method="GET",status="200",route="/health"} 42
http_requests_total{method="GET",status="500",route="/checkout"} 3
```

Each unique `{...}` label set is **one time series**. Count them for a realistic
label scheme and the problem is obvious:

```python
# cardinality.py — feel the explosion before a backend feels it for you
labels = {
 "method": 4, # GET, POST, PUT, DELETE
 "status": 5, # 2xx, 3xx, 4xx, 5xx, other
 "route": 200, # templated routes: /users/{id}, not /users/42
 "pod": 50, # replicas scraped
}
series = 1
for name, cardinality in labels.items():
 series *= cardinality
print(f"series for one metric: {series:,}") # 200,000

# now add a high-cardinality label by mistake:
series_with_userid = series * 1_000_000 # 1M users
print(f"with user_id label: {series_with_userid:,}") # 200,000,000,000
```

The first number is fine. The second is a dead metrics store. That multiplication —
not any fancy tool — is the single most important intuition in this phase. The lab
turns it into a hands-on experiment and pairs it with a signals-mapping exercise.

---

### 5. Hands-on lab

You will map RED, USE, and the four golden signals onto a concrete service, then run
a tiny experiment that makes cardinality explosion visceral — all locally, with
nothing but Python.

➡️ **Start the lab: Map the signals, feel the cardinality**

---

### 6. Production considerations

- **Decide retention per signal.** Metrics are cheap — keep them for months. Raw
 logs and traces are expensive — keep a short hot window (days) and sample or
 archive the rest. One retention policy for all three wastes money or loses detail.
- **Budget cardinality like a resource.** Set limits (per-tenant series caps,
 `metric_relabel_configs` to drop risky labels) *before* a team DDoSes the shared
 store. Treat "max active series per namespace" as a quota.
- **Sample traces deliberately.** 100% tracing is unaffordable and usually
 unnecessary. Start with a low head-sampling rate plus **tail sampling that keeps
 all errors and slow requests**. Record the sampling rate as metadata
 so you can scale counts back up.
- **Standardize or drown.** Hundreds of services each inventing their own metric
 names and log formats is unqueryable. Mandate **semantic conventions**
 (OpenTelemetry's naming) so `http.server.request.duration` means the same thing
 everywhere. Consistency *is* the platform value.
- **Instrument the paved road once.** Bake RED metrics, structured logging, and trace
 context into the service template so every new service is observable by default —
 the TVP move from applied to telemetry.

### 7. Common mistakes

- **Treating "we have dashboards" as observability.** — Pre-built dashboards are
 monitoring; they answer only the questions you already thought of. *Fix:* invest in
 high-dimensional, explorable telemetry you can query ad hoc, not just a wall of
 fixed graphs.
- **Alerting on causes instead of symptoms.** — A page for "CPU is 90%" fires when
 nothing is actually wrong and misses real user pain. *Fix:* alert on
 user-facing **symptoms** (latency, error rate, SLO burn — ); use
 resource metrics to *diagnose*, not to page.
- **Averaging latency.** — A mean hides the tail where users suffer and is skewed by
 fast errors. *Fix:* use percentiles (p95/p99) and separate success from failure
 latency.
- **High-cardinality labels.** — Putting `user_id`, request ID, or a raw URL in a
 metric label explodes series count and melts the store. *Fix:* keep identifiers in
 logs/traces; labels are for bounded dimensions (status, method, route template).
- **Unstructured logs.** — Free-text logs cannot be filtered or aggregated reliably.
 *Fix:* emit structured (JSON) logs with consistent keys from day one.
- **Collecting everything "just in case."** — Unbounded collection is how
 observability bills rival compute bills. *Fix:* collect against **questions you
 intend to answer** and sample the expensive signals.

### 8. Assessment

**Knowledge checks**

1. In one sentence each, define monitoring and observability, and state how they
 relate.
2. For each pillar (metrics, logs, traces), give one question it answers best and one
 it answers poorly.
3. What do RED and USE each measure, and when do you reach for one versus the other?
4. Why does adding a `user_id` label to a metric endanger a shared metrics backend?
5. Why can't you trace 100% of requests at scale, and what does tail sampling keep?

**Concept exercise**

> Explain to a skeptical engineer what observability gives them **without using the
> words "Prometheus," "Grafana," "metric," "log," or "trace."** Describe the outcome
> — what they can *do* at 2am that they could not before.

**Trade-off / debugging exercise**

> A team's dashboard shows average latency at a healthy 80ms, yet customers are
> complaining checkout is slow and occasionally fails. CPU and memory look fine.
> Explain what the dashboard is hiding, which signals you would add, and in what
> order you would use metrics, logs, and traces to find the cause.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** Monitoring = alerting on predefined signals (known questions);
 observability = a system property letting you answer new, unpredicted questions
 from existing telemetry. Monitoring is a subset of what observability enables.
- **Q2:** Metrics: great for trends/alerts, poor for a single request's detail. Logs:
 great for what exactly happened in one event, poor/expensive for aggregate trends.
 Traces: great for where time went across services, poor as a complete record
 (sampled).
- **Q3:** RED (Rate, Errors, Duration) measures request-driven *work*; USE
 (Utilization, Saturation, Errors) measures the *resources* doing the work. RED for
 services, USE for nodes/disks/queues.
- **Q4:** `user_id` is unbounded; each value creates a new time series, multiplying
 cardinality into the millions and exhausting the store's memory — and in a shared
 store that harms every tenant.
- **Q5:** Volume is too high to store every trace affordably; tail sampling keeps the
 *interesting* traces (errors and slow requests) and discards routine fast successes.
- **Debugging:** The average hides the tail — p99 is likely terrible even though p50
 is 80ms, and fast 5xx errors drag the mean *down*. Add percentile latency split by
 status and a request/error rate. Use metrics to confirm the p99 and error spike,
 logs to see *which* errors, and a trace of a slow checkout to find the offending
 downstream hop.

</details>

---

### 9. Further reading

- Google — [SRE Book: Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/) (the four golden signals)
- Google — [SRE Workbook: Implementing SLOs](https://sre.google/workbook/implementing-slos/)
- OpenTelemetry — [Observability primer](https://opentelemetry.io/docs/concepts/observability-primer/)
- Tom Wilkie — [The RED Method](https://www.weave.works/blog/the-red-method-key-metrics-for-microservices-architecture/)
- Brendan Gregg — [The USE Method](https://www.brendangregg.com/usemethod.html)
- Prometheus — [Metric and label naming best practices](https://prometheus.io/docs/practices/naming/)

---


_Previous:_ · Observability Engineering
· _Next:_ OpenTelemetry →

---

## OpenTelemetry

> Before OpenTelemetry, every observability vendor had its own agent, SDK, and wire
> format — so instrumenting a service locked you into a backend. **OpenTelemetry
> (OTel)** is the vendor-neutral standard that broke that lock: instrument **once**,
> export **anywhere**. This module covers the OTel data model, how you instrument
> services, and the Collector — the routing hub every platform runs.

**You'll need:**, a kind cluster,
`kubectl`, and [Helm](https://helm.sh/). A Go toolchain is optional (the app sketch
is reference).

### Learning objectives

By the end of this module you will be able to:

- Describe the **OTel data model** — traces/spans, metrics, logs — and signal
 correlation via context.
- Choose between **auto-instrumentation** and **manual instrumentation**, and combine
 them.
- Explain the **Collector**'s receive → process → export pipeline and when to run it
 as an **agent** versus a **gateway**.
- Pick the right **processors** (batch, memory limiter, filter, attributes, sampling)
 and **exporters** (OTLP, Prometheus, Loki, Tempo).
- Contrast **head-based** and **tail-based** sampling and say where each belongs.

---

### 1. Concept

#### The problem OTel solves

Observability used to mean picking a vendor and letting their proprietary agent and
SDK colonize your code. Want to switch backends, or send traces to one tool and
metrics to another? Re-instrument everything. OpenTelemetry — a CNCF project, the
merger of OpenTracing and OpenCensus — fixes this with three things:

- a **specification and data model** for traces, metrics, and logs,
- **SDKs** in every major language that implement it, and
- the **OTLP** wire protocol plus the **Collector** that speaks it.

The payoff: instrumentation is decoupled from the backend. Your code emits OTel; a
Collector routes it to Prometheus, Loki, Tempo, Jaeger, or a SaaS — swappable by
config, no code change. For a platform team, that is the difference between owning
your telemetry and renting it from a vendor.

#### The data model: traces, metrics, logs

- **Trace** — the story of one request across services, a tree of **spans**.
- **Span** — one timed operation (an HTTP handler, a DB call). It has a name, start
 and end time, a **status**, key-value **attributes**, and **events**. Spans carry a
 `trace_id` (shared across the whole request) and a `span_id`, plus a parent link —
 that is what stitches the tree together.
- **Context propagation** — passing `trace_id`/`span_id` across process boundaries,
 usually in HTTP headers, so the next service's spans join the same trace. This is the magic that makes a trace *distributed*.
- **Metric** — an aggregated measurement (counter, gauge, histogram) with a name and
 attributes (which become labels downstream).
- **Log** — a timestamped record that OTel can **correlate** with a trace by stamping
 it with the active `trace_id`. That shared ID is how you jump log → trace later.

**Semantic conventions** are the quiet hero: OTel standardizes *names*
(`http.request.method`, `http.response.status_code`, `service.name`) so telemetry is
comparable across every service and language. Enforcing these conventions is a
core platform job — consistency is what makes the data queryable at scale.

#### Instrumenting a service: auto vs manual

- **Auto-instrumentation** — a language agent or library hooks well-known frameworks
 (HTTP servers, gRPC, DB drivers) and emits spans and metrics with **no code
 change**. In Java/Python/Node it is a drop-in agent; in Kubernetes the **OTel
 Operator** can inject it automatically. This is how you get every service to RED +
 traces "for free" — the golden-path move.
- **Manual instrumentation** — you call the SDK yourself to create spans around
 *business* operations the auto layer cannot see ("validate-cart", "charge-card")
 and add domain attributes (`order.value`, `tenant.id`). You almost always want
 **both**: auto for the plumbing, manual for the meaning.

```go
tracer:= otel.Tracer("checkout")
ctx, span:= tracer.Start(ctx, "charge-card")
defer span.End()
span.SetAttributes(attribute.String("tenant.id", tenantID))
```

#### The Collector: receive, process, export

The **OTel Collector** is a standalone binary that receives telemetry, processes it,
and exports it — decoupling your apps from your backends. Its config is three kinds
of component wired into **pipelines**:

- **Receivers** — how data gets in (`otlp` over gRPC/HTTP, `prometheus` scrape,
 `filelog`, `hostmetrics`).
- **Processors** — what happens in between (see below). Order matters.
- **Exporters** — where data goes out (`otlp` to Tempo, `prometheus`, `loki`,
 `debug`).

You run the Collector in two complementary roles:

- **Agent** (a **DaemonSet**, one per node) — collects node-local signals
 (`hostmetrics`, container logs via `filelog`) and receives OTLP from pods on that
 node. Close to the source, cheap network hop.
- **Gateway** (a **Deployment**, a horizontally scaled pool) — agents forward to it;
 it does the expensive, cluster-wide work: **tail sampling**, batching, and fan-out
 to backends. Centralizing here means one place to change routing for everyone.

#### Key processors

- **`memory_limiter`** — caps the Collector's own memory and sheds load before an
 OOM. Put it **first**; a Collector that crashes drops everyone's telemetry.
- **`batch`** — groups telemetry into fewer, larger exports. Essential for throughput;
 put it near the **end**.
- **`attributes` / `resource`** — add, redact, or rename attributes (stamp
 `cluster`, drop a PII field, enforce a semantic name).
- **`filter`** — drop data you do not want (health-check spans, a noisy metric).
- **`tail_sampling`** — decide whether to keep a trace **after** seeing all its spans
 (keep errors and slow traces, drop routine ones). Gateway-only, because it must see
 the whole trace.

#### Head vs tail sampling

- **Head-based** — decide at the **start** of a request, before you know how it ends
 (e.g. keep 10% at random). Cheap and stateless, but it keeps boring requests and
 throws away rare errors just as often.
- **Tail-based** — buffer a trace's spans and decide at the **end**, when you know it
 errored or was slow. Keeps the *interesting* traces, but needs memory and all spans
 of a trace at one Collector — which is exactly why it lives in the **gateway**.

---

### 2. Why it matters for platform engineering

- **It is the anti-lock-in layer.** Instrument with OTel and you can change
 metrics/logs/traces backends by editing Collector config — no team re-instruments.
 That freedom is a strategic platform asset.
- **The Collector is a control point.** One place to enforce semantic conventions,
 redact PII, stamp tenant/cluster labels, cap cardinality, and route by tenant. You
 govern everyone's telemetry without touching their code.
- **Auto-instrumentation is a golden path.** The OTel Operator injecting agents means
 every service is traced by default. "Observable by default" becomes a platform
 guarantee, not a per-team chore.
- **Sampling is a cost lever you own.** Tail sampling at the gateway lets the platform
 keep trace bills sane while preserving the errors engineers actually need.

---

### 3. Mental model

Think of OTel as **standard pipes** between your code and your backends, with the
Collector as the junction box every team shares.

```text
 apps (OTel SDK: auto + manual)
 │ OTLP
 ▼
 ┌───────────────┐ one per node, close to the source
 │ AGENT │ receivers: otlp, hostmetrics, filelog
 │ (DaemonSet) │ light processing: memory_limiter, batch
 └──────┬────────┘
 │ OTLP (forward)
 ▼
 ┌───────────────┐ a scaled pool; the shared control point
 │ GATEWAY │ tail_sampling, attributes (tenant/cluster),
 │ (Deployment) │ filter, batch
 └──────┬────────┘
 ┌──────┼───────────┬───────────────┐
 ▼ ▼ ▼ ▼
 Tempo Prometheus Loki (SaaS / Jaeger)
 traces metrics logs

 Change a backend? Re-wire an exporter here. The apps never notice.
```

Rule of thumb: **receivers are the "in," exporters are the "out," processors are the
"what happens in between," and the pipeline is the plumbing that connects them.**

---

### 4. Minimal implementation

The smallest useful Collector is one pipeline: receive OTLP, batch it, print it. This
single config proves the receive → process → export shape before any backend exists.

```yaml
# otel-collector-config.yaml — the smallest real pipeline
receivers:
 otlp:
 protocols:
 grpc: { endpoint: 0.0.0.0:4317 }
 http: { endpoint: 0.0.0.0:4318 }

processors:
 memory_limiter:
 check_interval: 1s
 limit_percentage: 80
 spike_limit_percentage: 25
 batch: {}

exporters:
 debug:
 verbosity: detailed

service:
 pipelines:
 traces:
 receivers: [otlp]
 processors: [memory_limiter, batch]
 exporters: [debug]
```

Run it and send one trace — no SDK or app required — using OTel's `telemetrygen`:

```bash
# run the Collector locally, then generate 5 spans into it
docker run --rm -p 4317:4317 -p 4318:4318 \
 -v "$PWD/otel-collector-config.yaml:/etc/otelcol-contrib/config.yaml" \
 otel/opentelemetry-collector-contrib:0.110.0

telemetrygen traces --otlp-insecure --otlp-endpoint localhost:4317 --traces 5
```

You will see the spans printed by the `debug` exporter. Swap `debug` for an `otlp`
exporter pointing at Tempo and the exact same apps now feed a real trace store — the
whole point of OTel. The lab builds this into an agent + gateway topology on kind.

---

### 5. Hands-on lab

You will deploy the Collector twice on kind — as a **DaemonSet agent** and a
**Deployment gateway** — forward telemetry agent → gateway, generate traces and
metrics with `telemetrygen`, and watch them arrive at the gateway's debug exporter.

➡️ **Start the lab: An OTel Collector agent + gateway on kind**

---

### 6. Production considerations

- **Put `memory_limiter` first, `batch` last.** A Collector without a memory limiter
 OOMs under load and drops *everyone's* telemetry; without batching it melts your
 backends with tiny writes.
- **Run agent + gateway, not one giant Collector.** Agents stay cheap and node-local;
 the gateway scales horizontally and owns the stateful work (tail sampling). Size the
 gateway for peak trace volume and give it a PodDisruptionBudget.
- **Secure OTLP.** Enable TLS and auth between apps, agents, gateway, and backends;
 `--otlp-insecure` is for labs only. The Collector sees everyone's data — treat it
 like a privileged service.
- **Tail-sample at the gateway.** Head-sample lightly at the edge to shed obvious
 volume, then tail-sample centrally to keep errors and slow traces. Record the
 effective rate so counts can be scaled back up.
- **Govern attributes centrally.** Use `attributes`/`resource` processors to stamp
 `cluster`/`tenant`, drop PII, and enforce semantic conventions — so you do not rely
 on every team getting it right.
- **Version the config in Git.** Collector config is platform infrastructure. Review
 and roll it out like any other deployment, with a canary Collector.

### 7. Common mistakes

- **No `memory_limiter`.** — Under a telemetry spike the Collector OOMs and takes down
 the observability pipeline for every tenant. *Fix:* add `memory_limiter` first in
 every pipeline and set container limits to match.
- **Tail sampling on the agent.** — A per-node agent never sees all spans of a trace,
 so its sampling decisions are wrong. *Fix:* tail-sample only at the gateway, where a
 whole trace lands.
- **Auto-instrumentation only.** — You get HTTP/DB spans but none of the business
 operations that explain *why* something is slow. *Fix:* add manual spans around
 domain logic and attach domain attributes.
- **Ignoring semantic conventions.** — Each service invents `status`, `httpStatus`,
 `code`… and cross-service queries become impossible. *Fix:* adopt OTel semantic
 conventions and enforce them in the Collector.
- **Exporting raw, unbatched OTLP.** — Per-span network calls crush throughput and
 cost. *Fix:* always include a `batch` processor before exporters.
- **Treating the Collector as fire-and-forget.** — It silently drops data when
 queues fill or a backend is down. *Fix:* monitor the Collector's own metrics
 (`otelcol_exporter_send_failed_*`, queue size) — observe your observability.

### 8. Assessment

**Knowledge checks**

1. What problem does OpenTelemetry solve that per-vendor SDKs created?
2. What is a span, and what makes a set of spans a single distributed *trace*?
3. What are the three component types in a Collector pipeline, and in what order do
 `memory_limiter` and `batch` belong?
4. Why must tail-based sampling run on the gateway and not the per-node agent?
5. When would you add manual instrumentation on top of auto-instrumentation?

**Concept exercise**

> Explain to an app developer how they can switch their tracing backend from one tool
> to another **without changing a line of their application code** — and *why* that is
> possible. Do not name a specific vendor.

**Trade-off / debugging exercise**

> Traces are missing for about 1% of requests — and it is always the *errored* ones
> that are missing, which are exactly the ones you need. The team uses 1% head
> sampling. Explain why the errors disappear, and design a sampling strategy that
> keeps them while staying affordable at 50k req/s.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** Per-vendor SDKs coupled instrumentation to a backend; switching meant
 re-instrumenting. OTel standardizes the data model and wire format so you
 instrument once and export anywhere.
- **Q2:** A span is one timed operation with a status and attributes. Spans share a
 `trace_id` and link to parents via `span_id`; propagating that context across
 service boundaries stitches them into one distributed trace.
- **Q3:** Receivers, processors, exporters. `memory_limiter` first (shed load before
 OOM), `batch` last (efficient export).
- **Q4:** Tail sampling must see *all* spans of a trace to judge it; a per-node agent
 only sees the spans that happened on its node, so it cannot make a correct
 whole-trace decision.
- **Q5:** When you need spans around business operations the auto layer cannot see, or
 domain attributes (tenant, order value) for slicing.
- **Debugging:** Head sampling decides at request start, before the error exists, so
 it drops 99% of everything — including 99% of errors — uniformly. Switch to tail
 sampling at the gateway: a policy that keeps 100% of traces with an error status or
 latency over a threshold, plus a small random percentage of the rest. You preserve
 all errors while sampling the boring majority.

</details>

---

### 9. Further reading

- OpenTelemetry — [Documentation](https://opentelemetry.io/docs/) and
 [What is OpenTelemetry?](https://opentelemetry.io/docs/what-is-opentelemetry/)
- OpenTelemetry — [Collector](https://opentelemetry.io/docs/collector/) and
 [Collector configuration](https://opentelemetry.io/docs/collector/configuration/)
- OpenTelemetry — [Sampling](https://opentelemetry.io/docs/concepts/sampling/)
- OpenTelemetry — [Operator and auto-instrumentation](https://opentelemetry.io/docs/kubernetes/operator/)
- OpenTelemetry — [Semantic conventions](https://opentelemetry.io/docs/specs/semconv/)
- CNCF — [OpenTelemetry project](https://www.cncf.io/projects/opentelemetry/)

---


_Previous:_ Observability Fundamentals
· _Next:_ Metrics with Prometheus →

---

## Metrics with Prometheus

> Prometheus is the de-facto standard for metrics in the cloud-native world — a
> pull-based time-series database with a query language (**PromQL**) built for the
> questions platform engineers actually ask. This module covers how it scrapes,
> stores, and queries metrics, the four metric types, and how the Operator turns
> "monitor this service" into a one-object declaration.

**You'll need:**, a kind cluster,
`kubectl`, and [Helm](https://helm.sh/).

### Learning objectives

By the end of this module you will be able to:

- Explain Prometheus's **pull model** and its scrape → store → query architecture.
- Choose the right **metric type** — counter, gauge, histogram, summary.
- Write **PromQL** for rate, error ratio, percentile latency, and aggregation.
- Use **ServiceMonitor / PodMonitor** to declare scrape targets with the Operator.
- Know when to add **recording rules** and **remote write** for scale and retention.

---

### 1. Concept

#### Architecture: scrape, store, query

Prometheus is three things in one binary:

- **Scrape** — on a schedule, Prometheus **pulls** metrics by making an HTTP GET to
 each target's `/metrics` endpoint, which returns the current values in a simple
 text format. This **pull model** is the defining design choice: targets just expose
 a page; Prometheus decides when to read it. That makes targets simpler (no push
 config, no credentials to a remote), gives Prometheus control over load, and makes
 "is the target up?" a free health signal (the `up` metric).
- **Store** — samples land in a local **time-series database (TSDB)** on disk,
 optimized for many numeric series written append-only over time. Each sample is
 `(metric name + labels) → (timestamp, float64)`.
- **Query** — **PromQL** reads that TSDB to answer questions, power dashboards, and evaluate alert and recording rules.

A **time series** is uniquely identified by its metric name plus its label set —
`http_requests_total{method="GET", code="200"}` is a *different* series from
`...{code="500"}`. This is where the cardinality lesson from bites: every
distinct label combination is another series the TSDB must hold in memory and on disk.

#### Service discovery: how targets are found

Hardcoding a list of IPs to scrape does not survive Kubernetes, where Pods come and
go. Prometheus uses **service discovery** — in Kubernetes it watches the API for
Pods, Services, and Endpoints and builds its scrape list dynamically. The
**Prometheus Operator** (which you install via `kube-prometheus-stack`) wraps this in
CRDs so you never hand-edit Prometheus config:

- **ServiceMonitor** — "scrape the Pods behind this Service, on this port and path."
- **PodMonitor** — "scrape these Pods directly," for workloads without a Service.

You label a ServiceMonitor so the Prometheus instance selects it, and the Operator
regenerates Prometheus's config for you. Declaring telemetry as Kubernetes objects is
exactly the GitOps-friendly model a platform wants.

#### Metric types

The exposition format has four types, and picking the right one matters:

- **Counter** — a value that only ever **goes up** (or resets to zero on restart):
 requests served, errors, bytes sent. You almost never read a counter raw; you take
 its **`rate()`** (per-second increase). `http_requests_total` is a counter.
- **Gauge** — a value that goes **up and down**: temperature, memory in use, queue
 depth, in-flight requests. Read it directly or with `avg`/`max` over time.
- **Histogram** — samples observations into **cumulative buckets** (e.g. "requests
 faster than 0.1s"), exposing `_bucket`, `_sum`, and `_count` series. The key power:
 you compute **percentiles** across instances *after the fact* with
 `histogram_quantile()`. This is how you get p99 latency.
- **Summary** — like a histogram but computes **quantiles client-side** at
 observation time. Cheaper to query but you **cannot aggregate** its quantiles
 across instances (a p99 of p99s is meaningless). Prefer histograms in distributed
 systems for exactly that reason.

#### PromQL in one page

PromQL evaluates to **vectors**:

- An **instant vector** is the value of each matching series at one instant:
 `http_requests_total`.
- A **range vector** is a window of samples per series, written with `[5m]`:
 `http_requests_total[5m]`. Functions like `rate()` consume range vectors.

The moves you will use constantly:

- **`rate(counter[5m])`** — per-second average increase over the window. The
 foundation of every request/error-rate query.
- **Aggregation** — `sum`, `avg`, `max`, `count` with `by (label)` or
 `without (label)` to collapse series: `sum by (namespace) (...)`.
- **`histogram_quantile(0.99,...)`** — a percentile from histogram buckets.
- **Label matchers** — `{code=~"5.."}` (regex), `{code!="200"}` (negation).

```promql
# the canonical service error ratio
sum(rate(http_requests_total{code=~"5.."}[5m]))
 /
sum(rate(http_requests_total[5m]))
```

#### Recording rules, remote write, federation

- **Recording rules** pre-compute expensive or frequently used expressions on a
 schedule and save the result as a new series. Dashboards and alerts then read the
 cheap pre-computed series instead of re-running a heavy query every refresh.
- **Remote write** streams samples to an external, horizontally scalable, long-term
 store — **Thanos**, **Mimir**, or **VictoriaMetrics** — because a single
 Prometheus's local TSDB is capped by one node's disk and retention. In the LGTM
 stack, **Mimir** is the long-term metrics home.
- **Federation** lets one Prometheus scrape a curated, aggregated subset of another —
 an older pattern for hierarchies of Prometheis, now often superseded by remote
 write to a central store.
- **kube-state-metrics** is a companion exporter that turns Kubernetes **object
 state** (Deployments desired vs ready, Pod phase, resource requests) into metrics —
 distinct from **node-exporter** (node hardware) and **cAdvisor** (container
 CPU/memory). Together they give you USE signals for the whole cluster.

---

### 2. Why it matters for platform engineering

- **It is the metrics substrate of the whole platform.** Autoscaling (HPA), SLOs, capacity planning, and chargeback all read Prometheus.
 Getting it right underpins everything downstream.
- **ServiceMonitors make observability self-service.** A team adds a ServiceMonitor
 to its chart and is scraped automatically — no ticket to the platform team, no
 central config edit. That is the golden-path pattern applied to metrics.
- **Cardinality is a shared-fate risk.** One team's `user_id` label can exhaust the
 shared Prometheus's memory for everyone. You own the limits (`sample_limit`,
 `metric_relabel_configs`) that contain the blast radius.
- **Retention and scale are platform decisions.** When local TSDB is not enough, *you*
 choose and operate the remote-write backend (Mimir/Thanos). Teams should never feel
 that seam.

---

### 3. Mental model

Prometheus is a **polling librarian**: on a timer it visits every target's `/metrics`
page, copies down the current numbers, files them by name+labels, and answers
questions with PromQL.

```text
 targets expose /metrics Prometheus consumers
 ┌────────────────────┐ scrape ┌───────────────┐ PromQL ┌─────────────┐
 │ app:8080/metrics │ ◀────────── │ TSDB (local) │ ─────────▶ │ Grafana │
 │ node:9100/metrics │ ◀────────── │ + rule eval │ ─────────▶ │ Alertmanager│
 │ ksm:8080/metrics │ ◀────────── │ │ │ HPA / SLOs │
 └────────────────────┘ └───────┬───────┘ └─────────────┘
 ▲ discovered via │ remote_write
 ServiceMonitor/PodMonitor ▼
 Mimir / Thanos (long-term, scalable)

 PULL, not push: targets are dumb pages; Prometheus decides when to read them.
```

Rule of thumb: **counters you `rate()`, gauges you read, histograms you
`histogram_quantile()`.** If you are writing `rate()` on something that is not a
counter, or a quantile on something that is not a histogram, stop and recheck the
type.

---

### 4. Minimal implementation

Before any Operator, see the pull model with nothing but a text page. A Prometheus
target is *just* an HTTP endpoint returning this:

```text
# HELP http_requests_total Total HTTP requests.
# TYPE http_requests_total counter
http_requests_total{code="200",method="get"} 1027
http_requests_total{code="500",method="get"} 3
# HELP inflight_requests In-flight requests right now.
# TYPE inflight_requests gauge
inflight_requests 5
```

Serve that from any process and point Prometheus at it with a three-line scrape job —
no Kubernetes required:

```yaml
# prometheus.yml — the smallest scrape config
scrape_configs:
 - job_name: demo
 static_configs:
 - targets: ["localhost:8080"]
```

```bash
prometheus --config.file=prometheus.yml # scrapes localhost:8080/metrics every 15s
```

Now the counter is queryable. Its per-second rate and error ratio are one PromQL
expression each:

```promql
sum(rate(http_requests_total[1m])) # total req/s
sum(rate(http_requests_total{code=~"5.."}[1m])) / sum(rate(http_requests_total[1m]))
```

That is the whole model: expose numbers on a page, let Prometheus pull them, ask
PromQL questions. The lab scales this up with the Operator and a real histogram.

---

### 5. Hands-on lab

You will install `kube-prometheus-stack` on kind, deploy a sample service, declare a
**ServiceMonitor** so Prometheus scrapes it, generate load, and write PromQL for
**error rate**, **p99 latency**, and **namespace CPU** — then add a recording rule.

➡️ **Start the lab: PromQL against a scraped service**

---

### 6. Production considerations

- **Guard cardinality hard.** Set `sample_limit` on scrapes and use
 `metric_relabel_configs` to drop risky labels *before* ingestion. Watch
 `prometheus_tsdb_head_series` and alert when a tenant's series count spikes.
- **Plan retention and remote write early.** Local TSDB retention is finite; decide
 up front whether long-term data lives in Mimir/Thanos and stream it via
 `remote_write`. Retrofitting history is painful.
- **Make Prometheus itself highly available.** Run redundant replicas (the Operator
 supports it) or front it with Thanos/Mimir; a single Prometheus is a single point
 of blindness. Back the TSDB with a PVC.
- **Scrape intervals cost money.** 15s is a sane default; 5s quadruples storage and
 scrape load versus 30s. Match interval to how fast you actually need to react.
- **Recording rules for hot queries.** Pre-compute the expressions dashboards and SLO
 alerts hit every evaluation; it cuts query load dramatically and keeps alerting
 responsive.
- **Secure `/metrics` and the UI.** Metrics can leak internals; the Prometheus UI and
 Alertmanager must not be publicly reachable. Scope RBAC and network policy.

### 7. Common mistakes

- **`rate()` on a gauge (or reading a counter raw).** — `rate()` assumes
 monotonic counters; on a gauge it is nonsense, and a raw counter is an
 ever-growing number nobody wants. *Fix:* `rate()` counters, read gauges directly.
- **High-cardinality labels.** — `user_id`, request path with IDs, or a raw URL as a
 label explodes series and OOMs Prometheus. *Fix:* bounded labels only; put
 identifiers in logs/traces and use route templates.
- **Summaries where you need cross-instance percentiles.** — Summary quantiles cannot
 be aggregated across replicas, so a fleet-wide p99 is impossible. *Fix:* use
 histograms and `histogram_quantile()`.
- **ServiceMonitor not selected.** — The label the Prometheus instance selects on is
 missing, so the target is silently never scraped. *Fix:* match the Operator's
 selector (e.g. the `release` label) and check the Targets page.
- **Averaging latency or rating over too-short a window.** — Means hide the tail and
 a `[1m]` rate on a 30s scrape is noisy. *Fix:* percentiles via histograms and a
 rate window at least 4× the scrape interval.
- **Treating local TSDB as durable, long-term storage.** — One node's disk and a
 short retention are not an archive. *Fix:* remote-write to Mimir/Thanos for
 long-term, scalable storage.

### 8. Assessment

**Knowledge checks**

1. Why does Prometheus **pull** metrics instead of having targets push them? Name two
 advantages.
2. For each of these, give the metric type: requests served, memory in use, request
 latency distribution. Why?
3. What does `rate(http_requests_total[5m])` compute, and why can't you use it on a
 gauge?
4. How does `histogram_quantile()` get you a p99 across many Pods when a summary
 cannot?
5. What does a ServiceMonitor declare, and what makes a given Prometheus select it?

**Concept exercise**

> Explain how you would measure a service's error rate and tail latency **without
> naming Prometheus or PromQL** — describe the raw numbers you would collect and the
> arithmetic you would do to them.

**Trade-off / debugging exercise**

> A team reports "our dashboard shows zero requests, but the app is clearly serving
> traffic." The app exposes `/metrics`, and other services are scraped fine. Walk
> through how you would diagnose it — from the Targets page to labels to the
> ServiceMonitor — and list three distinct root causes that produce this symptom.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** Targets stay simple (just expose a page), Prometheus controls scrape
 timing/load, and reachability becomes a free `up` signal. (Also: no inbound
 credentials to targets; easy local testing by curling `/metrics`.)
- **Q2:** Counter (requests served — monotonic), gauge (memory — up and down),
 histogram (latency distribution — enables after-the-fact percentiles).
- **Q3:** The per-second average increase of the counter over 5 minutes. Gauges are
 not monotonic, so `rate()`'s "increase per second" is meaningless on them.
- **Q4:** Histograms expose raw cumulative buckets per series; you `sum` the bucket
 rates across Pods first, then compute the quantile — aggregation happens before the
 percentile. Summaries pre-compute the quantile per instance, and quantiles cannot be
 averaged, so a fleet p99 is impossible.
- **Q5:** A ServiceMonitor declares which Service's Pods to scrape, on which
 port/path/interval. A Prometheus selects it when its `serviceMonitorSelector`
 matches the ServiceMonitor's labels (commonly the `release` label).
- **Debugging:** Check the Targets page — is the target present and `up`? Causes:
 (1) ServiceMonitor label doesn't match the Prometheus selector, so it's never
 configured; (2) the Service port name/number in the ServiceMonitor doesn't match
 the Service, so nothing is scraped; (3) the metric exists but under different
 labels than the dashboard query expects (e.g. `code` vs `status`), so the query
 returns empty. Each yields "zero on the dashboard."

</details>

---

### 9. Further reading

- Prometheus — [Overview](https://prometheus.io/docs/introduction/overview/) and
 [Concepts: metric types](https://prometheus.io/docs/concepts/metric_types/)
- Prometheus — [Querying basics (PromQL)](https://prometheus.io/docs/prometheus/latest/querying/basics/)
 and [functions](https://prometheus.io/docs/prometheus/latest/querying/functions/)
- Prometheus Operator — [ServiceMonitor / PodMonitor design](https://prometheus-operator.dev/docs/developer/getting-started/)
- Prometheus — [Metric and label naming best practices](https://prometheus.io/docs/practices/naming/)
- Grafana — [Mimir](https://grafana.com/docs/mimir/latest/) and
 [Thanos](https://thanos.io/) for long-term, scalable metrics

---


_Previous:_ OpenTelemetry
· _Next:_ Logging with Loki →

---

## Logging with Loki

> Prometheus tells you an error rate rose; logs tell you **what the errors actually
> said**. **Loki** is "Prometheus for logs" — it indexes only a small set of
> **labels**, not the full log text, which makes it cheap to run at scale. This
> module covers Loki's architecture, **LogQL**, and the one rule that makes or breaks
> a Loki deployment: keep your labels low-cardinality.

**You'll need:** and
[Docker Compose](https://docs.docker.com/compose/). No cloud.

### Learning objectives

By the end of this module you will be able to:

- Explain how Loki indexes **labels** (not full text) and why that makes it cheap.
- Define a **log stream** and reason about label cardinality in Loki.
- Write **LogQL** to filter, parse structured logs, and compute metrics from logs.
- Choose a log-collection agent (Promtail, Grafana Alloy, or the OTel Collector).
- Apply **structured logging** and set sensible retention and storage backends.

---

### 1. Concept

#### The idea: index labels, not text

Traditional log systems (think Elasticsearch) index the **full content** of every log
line so you can search any word. That is powerful and *expensive* — the index often
dwarfs the logs themselves. Loki makes a different bet, borrowed straight from
Prometheus: **index only a small set of labels**, and store the raw log text as
compressed chunks in cheap object storage. Queries first use the tiny label index to
find the right **streams**, then brute-force scan just those chunks for your text.

The payoff is cost: Loki's index is small, so it is dramatically cheaper to operate
than a full-text system, and it uses the **same label model** as Prometheus — so
`{namespace="team-a", app="checkout"}` means the same thing for your logs as for your
metrics. The trade-off is that Loki is not a fast full-text search engine; it is a
*label-scoped grep over time*. For platform logging at volume, that trade is usually
the right one.

#### Streams and labels

A **log stream** is a unique set of label key-values plus the ordered log lines that
carry it. `{namespace="team-a", app="checkout", level="error"}` is one stream;
changing any label value makes a different stream.

This is where Loki's golden rule lives, and it is the mirror image of the metrics
cardinality lesson:

> **Labels must be low-cardinality.** Every unique label-value combination is a
> separate stream with its own index entry and chunks. Put a high-cardinality field —
> `user_id`, `trace_id`, `request_path`, a raw IP — in a **label** and you create
> millions of tiny streams, which is the number-one way to make Loki fall over.

The fix: use a *few* bounded labels (namespace, app, level, cluster) for *routing*,
and keep the high-cardinality detail **inside the log line** (ideally as JSON), where
LogQL can filter and parse it at query time without paying the index cost.

#### Architecture

Loki splits into components you can run as one binary (small) or scale out (large):

- **Distributor** — receives incoming logs from agents, validates them, and hashes
 each stream to the right ingester(s).
- **Ingester** — buffers log lines in memory per stream, then flushes compressed
 **chunks** and index to long-term storage. It also serves recent, not-yet-flushed
 data to queries.
- **Querier** — executes LogQL: consults the index, fetches the relevant chunks, and
 scans them. Fans out for parallelism.
- **Query frontend** (optional) — splits and queues large queries so they run in
 parallel and cache results.
- **Compactor** — compacts index files and enforces **retention** (deleting old data)
 in the backing store.

The backing store is **object storage** — S3, GCS, Azure Blob, or a local filesystem
for a lab. Loki's deployment modes are **single-binary** (everything in one process,
great for small setups and labs), **simple scalable** (read/write/backend split), and
**microservices** (each component separate, for very large scale). In the LGTM stack,
the **L** is Loki.

#### Collecting logs: Promtail, Alloy, or OTel

Something has to read logs and push them to Loki:

- **Promtail** — Loki's classic agent. Runs as a DaemonSet, discovers Kubernetes Pod
 logs, attaches labels from Pod metadata, and pushes to Loki. Simple and purpose-built.
- **Grafana Alloy** — Grafana's newer, general-purpose collector (OTel-compatible)
 that supersedes Promtail for new deployments; it collects logs *and* metrics *and*
 traces.
- **The OpenTelemetry Collector** — if you already run OTel, its
 `filelog` receiver plus a `loki` exporter sends logs to Loki through the same
 pipeline as your traces and metrics. One agent, all three signals.

For a platform standardizing on OTel, routing logs through the Collector keeps a
single telemetry pipeline. Promtail is the simplest starting point.

#### LogQL

LogQL has two halves. A **log query** selects and filters lines:

- **Stream selector** (required): `{app="checkout", level="error"}` — uses the index.
- **Line filters**: `|= "timeout"` (contains), `!= "healthz"` (does not contain),
 `|~ "5\\d\\d"` (regex). These scan the chunk text.
- **Parsers and pipelines**: `| json`, `| logfmt`, `| pattern` extract fields from the
 line; then `| status >= 500`, `| line_format "{{.msg}}"`, `| label_format...`.

A **metric query** wraps a log query in a function to produce a time series — this is
how logs become graphable and alertable:

```logql
# error lines per second for a service, computed FROM logs
rate({app="checkout"} |= "error" [5m])

# count by level, parsed from JSON
sum by (level) (count_over_time({app="checkout"} | json [5m]))
```

That metric-from-logs capability is why Loki pairs so naturally with Prometheus and
Grafana: you can alert on a log pattern the same way you alert on a metric.

---

### 2. Why it matters for platform engineering

- **Centralized logs are table stakes.** A platform running many teams' workloads
 needs one place to search logs, with consistent labels (`namespace`, `app`, `pod`)
 so any engineer can find any service's logs without bespoke setup.
- **The label rule is a multi-tenant guardrail.** A single team labeling logs by
 `request_id` can blow up the shared Loki's stream count for everyone. You enforce
 the label policy centrally — in the agent config, not by trusting each team.
- **Cheap logging changes what you can afford to keep.** Loki's economics let a
 platform retain more logs for longer than a full-text system would, which matters
 for incident forensics and audit.
- **Structured logging is a platform standard you set.** Mandating JSON logs with
 shared field names (and a `trace_id` field) is what makes logs queryable *and*
 correlatable with traces.

---

### 3. Mental model

Think of Loki as a **filing cabinet indexed only by the label on each folder**. The
label index is tiny, so finding the right folders is instant; then you *read through*
just those folders for the text you want.

```text
 query: {app="checkout", level="error"} |= "timeout"
 │ │
 ▼ ▼
 1) use the LABEL INDEX 2) grep the CHUNKS of
 (tiny) to pick streams only those streams for "timeout"
 ┌──────────────────────────┐ ┌───────────────────────────────┐
 │ {app=checkout,level=error}│──────▶│...raw JSON log lines (chunks) │
 │ {app=checkout,level=info} │ skip │ in cheap object storage │
 │ {app=payments,level=error}│ skip └───────────────────────────────┘
 └──────────────────────────┘

 Labels = how you FIND logs (keep few, bounded).
 Line content (JSON) = the DETAIL you parse at query time (put IDs here).
```

Rule of thumb: **if a field has more than a few dozen possible values, it is log
*content*, not a label.**

---

### 4. Minimal implementation

The smallest useful setup is one agent tailing a file into Loki, then a LogQL query.
Even without Kubernetes, Loki ingests anything pushed to its HTTP API. A structured
log line is just JSON on stdout:

```json
{"ts":"2026-02-01T10:00:03Z","level":"error","service":"checkout","route":"/pay","status":500,"trace_id":"a1b2c3","msg":"payment gateway timeout"}
```

An agent attaches a *few* labels and ships the raw line:

```yaml
# promtail (excerpt): low-cardinality labels only; detail stays in the line
scrape_configs:
 - job_name: app
 static_configs:
 - targets: [localhost]
 labels:
 service: checkout # a label (bounded)
 __path__: /var/log/app/*.log
 pipeline_stages:
 - json: { expressions: { level: level } }
 - labels: { level: {} } # promote ONLY level (info/warn/error) to a label
```

Now LogQL answers questions, with identifiers parsed from the line — never indexed:

```logql
{service="checkout"} | json | level="error" # all error lines
{service="checkout"} | json | status >= 500 # server errors by parsed field
rate({service="checkout"} | json | level="error" [5m])# error lines per second
```

Notice `status` and `trace_id` are **parsed at query time** from JSON — they never
become labels, so cardinality stays flat no matter how many distinct values appear.
The lab runs exactly this stack with Docker Compose and Grafana Explore.

---

### 5. Hands-on lab

You will run Loki, Promtail, Grafana, and a JSON log generator with Docker Compose,
then use LogQL in Grafana Explore to filter logs, parse structured fields, and
compute an error rate from log lines — while keeping labels low-cardinality.

➡️ **Start the lab: LogQL over structured logs**

---

### 6. Production considerations

- **Enforce the label policy centrally.** Cap labels to a known, bounded set in the
 agent config and reject or relabel high-cardinality fields. Watch Loki's active
 stream count; a spike is a tenant about to hurt everyone.
- **Back it with object storage and set retention.** Filesystem is for labs. Use
 S3/GCS/Azure, and configure the compactor's retention per tenant — logs are the
 signal you keep longest for forensics but cannot keep forever.
- **Mandate structured logging.** JSON (or logfmt) with shared field names
 (`level`, `service`, `trace_id`, `msg`) makes logs parseable and correlatable.
 Free-text logs are a query dead end at scale.
- **Include a `trace_id` field.** It is the join key from a log line to its trace in
 Tempo. Bake it into the logging library on the golden path.
- **Multi-tenancy and quotas.** Use Loki's tenant IDs to isolate teams and set
 per-tenant ingestion and stream limits, so one noisy team cannot starve the rest.
- **Do not treat Loki as full-text search.** Queries that scan huge time ranges with
 no label selector are slow and costly. Teach teams to anchor queries with labels
 and a tight time range.

### 7. Common mistakes

- **High-cardinality labels.** — Labeling by `request_id`, `trace_id`, user, or raw
 path creates millions of streams and cripples Loki. *Fix:* few bounded labels; keep
 identifiers in the JSON line and parse them with `| json` at query time.
- **Unstructured, free-text logs.** — `| json`/`| logfmt` cannot parse them, so you
 are stuck with brittle substring filters. *Fix:* emit structured logs with
 consistent keys.
- **No label selector in LogQL.** — `{} |= "error"` over all streams and all time
 scans everything and times out. *Fix:* always start with a label selector and a
 bounded time range.
- **Expecting Elasticsearch-style relevance search.** — Loki is label-scoped grep,
 not a ranked full-text engine. *Fix:* design labels and structured fields for the
 queries you actually run.
- **Filesystem storage in production.** — It does not scale or survive node loss, and
 retention is awkward. *Fix:* object storage (S3/GCS) with the compactor managing
 retention.
- **Forgetting the trace join key.** — Logs with no `trace_id` cannot be linked to
 traces, breaking correlation. *Fix:* propagate and log `trace_id` everywhere.

### 8. Assessment

**Knowledge checks**

1. What does Loki index, and how does that differ from a full-text log system?
2. What is a log stream, and why must labels be low-cardinality?
3. Where should a `trace_id` live — in a Loki label or in the log line? Why?
4. Write a LogQL query for the per-second rate of error lines from `app="checkout"`.
5. Name two ways to collect logs into Loki and when you'd pick each.

**Concept exercise**

> Explain to a team why they should **not** add a `user_id` label to their logs, and
> what to do instead so they can still find a specific user's requests — **without
> using the words "cardinality" or "stream."**

**Trade-off / debugging exercise**

> After a team deployed a new logging config, Loki's memory ballooned and queries
> slowed to a crawl, though log *volume* barely changed. Their config promotes
> `level`, `service`, **and `request_id`** to labels. Explain the root cause, predict
> what the active-stream count did, and give the one-line fix.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** Loki indexes a small set of labels and stores raw log text as compressed
 chunks; a full-text system indexes every token in every line. Loki's index is far
 smaller and cheaper, at the cost of not being a fast relevance search engine.
- **Q2:** A stream is a unique label set plus its ordered lines. Each unique label
 combination is a separate indexed stream, so high-cardinality labels multiply
 streams and overwhelm the index and ingesters.
- **Q3:** In the log line (as a JSON field). As a label it would be astronomically
 high-cardinality; in the line it is parsed at query time for free and still lets you
 jump to the trace.
- **Q4:** `rate({app="checkout"} |= "error" [5m])` (or
 `rate({app="checkout"} | json | level="error" [5m])`).
- **Q5:** Promtail (simple, Kubernetes-native log DaemonSet) or Grafana Alloy / the
 OTel Collector (one agent for logs+metrics+traces, ideal if you already run OTel).
- **Debugging:** `request_id` is unbounded, so promoting it to a label creates a new
 stream per request — the active-stream count exploded into the millions, blowing up
 ingester memory and index size and slowing every query. Fix: stop labeling by
 `request_id` (drop it from the `labels` stage); keep it in the JSON line and parse
 with `| json` when needed.

</details>

---

### 9. Further reading

- Grafana — [Loki documentation](https://grafana.com/docs/loki/latest/)
- Grafana — [LogQL](https://grafana.com/docs/loki/latest/query/) and
 [log queries](https://grafana.com/docs/loki/latest/query/log_queries/)
- Grafana — [Loki labels and cardinality best practices](https://grafana.com/docs/loki/latest/get-started/labels/)
- Grafana — [Promtail](https://grafana.com/docs/loki/latest/send-data/promtail/) and
 [Grafana Alloy](https://grafana.com/docs/alloy/latest/)
- Grafana — [Loki storage and retention](https://grafana.com/docs/loki/latest/operations/storage/)

---


_Previous:_ Metrics with Prometheus
· _Next:_ Distributed Tracing with Tempo →

---

## Distributed Tracing with Tempo

> Metrics say "error rate is up"; logs say "payment timed out"; only a **trace** says
> "the request spent 3 seconds waiting on the inventory service, which was blocked on
> a slow database call." **Tempo** is Grafana's trace store — cheap because, like
> Loki, it indexes very little. This module covers traces, context propagation, and
> how a `trace_id` stitches all three pillars together.

**You'll need:**,
, and
[Docker Compose](https://docs.docker.com/compose/).

### Learning objectives

By the end of this module you will be able to:

- Explain a **trace**, a **span**, and how **context propagation** builds a distributed
 trace.
- Describe **W3C TraceContext** and B3 headers and why a standard matters.
- Outline Tempo's architecture and query traces with **TraceQL**.
- Correlate traces with logs and metrics using a shared `trace_id` and **exemplars**.
- Choose a sampling strategy that keeps the traces you actually need.

---

### 1. Concept

#### Traces and spans

A **trace** is the complete record of one request as it travels through a system — a
tree of **spans**. Each **span** is a single timed operation with:

- a **name** (`POST /checkout`, `SELECT orders`),
- a **start and end time** (so you see duration),
- a **status** (ok / error),
- **attributes** (`http.route`, `db.system`, `tenant.id`), and
- identifiers: a **`trace_id`** shared by every span in the request, a unique
 **`span_id`**, and a **`parent_span_id`** linking a span to the one that caused it.

Those three IDs are what turn a pile of spans into a tree. Rendered on a timeline, a
trace is a **waterfall** that shows exactly where time went and where a failure began:

```text
trace a1b2c3… (total 420ms)
├─ POST /checkout [████████████████████] 420ms SERVER
│ ├─ validate-cart [██] 20ms
│ ├─ charge-card → payments [ ██████████ ] 300ms CLIENT
│ │ └─ SELECT ledger [ ████████ ] 260ms ← the cost
│ └─ reserve-stock → inventory [ ██ ] 60ms
```

#### Context propagation: how a trace becomes distributed

The hard part of *distributed* tracing is that each service is a separate process.
When `checkout` calls `payments` over HTTP, `payments` must know it is part of the
same trace and who its parent span is. That is **context propagation**: the caller
injects the trace context into the outgoing request (HTTP headers), and the callee
extracts it and continues the same trace.

The standard is **W3C TraceContext**, carried in two headers:

- **`traceparent`** — version, `trace_id`, parent `span_id`, and trace flags
 (including whether it was sampled), e.g.
 `00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01`.
- **`tracestate`** — optional vendor-specific key-values.

**B3** (single or multi-header, from Zipkin) is the older propagation format you will
still meet. The point of a standard is interoperability: as long as every service and
proxy speaks the same propagation format, a trace flows unbroken across languages,
frameworks, and service-mesh hops. OpenTelemetry handles inject/extract
for you — your job as a platform is to make sure **every** hop propagates it, including
gateways and meshes.

#### Tempo architecture

Tempo makes the same bet Loki does: **do not index the payload**. It stores whole
traces in cheap object storage keyed by `trace_id`, with only a lightweight index.
That makes ingesting 100% of spans affordable. Its components mirror Loki's:

- **Distributor** — receives spans (OTLP, Jaeger, Zipkin) and routes them by
 `trace_id`.
- **Ingester** — batches spans into blocks and flushes them to object storage.
- **Querier** — fetches and assembles traces for queries.
- **Compactor** — merges blocks and enforces retention.
- **Metrics-generator** (optional) — derives **span metrics** (RED from spans) and
 **service-graph** metrics, and writes them to Prometheus/Mimir.

Backends are S3, GCS, Azure, or local filesystem for a lab. In the LGTM stack, the
**T** is Tempo.

#### TraceQL

**TraceQL** queries traces by their spans' attributes:

```text
{ resource.service.name = "checkout" } all traces touching checkout
{ duration > 500ms } slow traces
{ status = error } failed traces
{ resource.service.name = "checkout" && span.http.status_code >= 500 }
```

You select spans with `{... }` and Tempo returns the traces that contain matching
spans. This is how you find "the slow, errored checkout traces from the last hour"
without knowing a `trace_id` in advance.

#### Correlation: the real payoff

A trace is most powerful when it is a **hub** linking the other pillars:

- **Logs ↔ traces.** If every log line carries a `trace_id`, you can
 jump from an error log straight to its trace — and from a slow span to its logs.
 Grafana wires this with a derived field (log → trace) and trace-to-logs (trace →
 log).
- **Metrics ↔ traces: exemplars.** An **exemplar** is a specific trace `trace_id`
 attached to a metric sample — "this one point in the p99 latency histogram came
 from *this* trace." Click the spike on the latency graph and land on an actual slow
 trace. Exemplars are the bridge from an aggregate metric to a concrete example.

This metric → log → trace path is the whole reason you collect all three. It is the
difference between "something is wrong" and "here is the exact request that failed and
why."

#### Sampling

You usually cannot store every trace at scale, so you sample:

- **Head-based** — decide at the start (e.g. keep 10%). Cheap and stateless, but it
 discards rare errors as readily as routine successes.
- **Tail-based** — buffer a trace's spans and decide at the end, keeping errors and
 slow traces. More useful, needs memory and a view of the whole trace — which is why
 it runs in the OTel **gateway**, not per node.

Tempo's cheap storage means some teams ingest 100% and rely on retention plus TraceQL
rather than aggressive sampling — a cost trade-off you decide per environment.

---

### 2. Why it matters for platform engineering

- **Tracing is how you debug a system you did not write.** In a microservice platform,
 a user-facing failure crosses many teams' services. A trace localizes the fault to
 one hop in seconds — without it, you are guessing across a dozen dashboards.
- **Propagation is a platform guarantee.** A single service that drops the
 `traceparent` header breaks every trace that passes through it. The platform must
 ensure the gateway, mesh, and service template all propagate context — teams should
 get it for free.
- **Correlation is the platform's force multiplier.** Wiring metrics → logs → traces
 once, centrally, means every engineer can pivot between pillars without configuring
 anything. That is a huge reduction in cognitive load.
- **Cheap tracing changes the economics.** Choosing Tempo (index-light) over a
 heavyweight tracing store lets a platform keep far more traces for the same spend —
 more forensic coverage when it matters.

---

### 3. Mental model

A trace is a **story with a shared ID**; spans are its chapters; the `trace_id` is the
ISBN that lets every other system point at the same book.

```text
 one request ───────────────────────────────────────────────▶ time
 trace_id = a1b2c3 (every span carries it; parent/child links build the tree)

 metrics logs traces (Tempo)
 "p99 latency ↑" ─────▶ "pay timeout ─────▶ span waterfall:
 exemplar: a1b2c3 trace_id=a1b2c3" payments → ledger
 │ │ ▲
 └──────────── same trace_id is the join key ───────────┘

 Collect all three so you can walk: alert → exact log → exact trace → root cause.
```

Rule of thumb: **metrics find the *when*, logs tell you the *what*, traces show you
the *where* — and `trace_id` is the thread connecting them.**

---

### 4. Minimal implementation

A trace is just structured data you can emit over OTLP. The smallest meaningful trace
is a parent span and one child, sharing a `trace_id`, linked by `parent_span_id`:

```json
{
 "resourceSpans": [{
 "resource": { "attributes": [
 { "key": "service.name", "value": { "stringValue": "checkout" } } ] },
 "scopeSpans": [{ "spans": [
 { "traceId": "a1b2c3d4e5f60718293a4b5c6d7e8f90",
 "spanId": "1111111111111111", "name": "POST /checkout",
 "kind": 2, "startTimeUnixNano": "1", "endTimeUnixNano": "420000000",
 "status": { "code": 2 } },
 { "traceId": "a1b2c3d4e5f60718293a4b5c6d7e8f90",
 "spanId": "2222222222222222", "parentSpanId": "1111111111111111",
 "name": "charge-card", "kind": 3,
 "startTimeUnixNano": "60000000", "endTimeUnixNano": "360000000" }
 ]}]
 }]
}
```

Post it to any OTLP endpoint and the trace is stored and queryable — no SDK required
(`trace_id`/`span_id` are hex strings in OTLP/JSON):

```bash
curl -X POST http://localhost:4318/v1/traces \
 -H 'Content-Type: application/json' -d @trace.json
```

That is exactly what the lab's generator does in a loop — and it writes a matching log
line carrying the same `trace_id`, so you can jump log → trace for real.

---

### 5. Hands-on lab

You will run Tempo, Loki, Grafana, and a generator that emits **correlated** traces
and logs (same `trace_id`), then query traces with TraceQL and pivot from an error log
straight to its trace in Grafana.

➡️ **Start the lab: TraceQL and log↔trace correlation**

---

### 6. Production considerations

- **Propagate context everywhere, or traces break.** Audit that gateways, service
 meshes, and every service template inject/extract W3C TraceContext. One non-
 propagating hop severs every trace through it. Prefer auto-instrumentation to make
 it the default.
- **Decide sampling per environment.** Aggressive head sampling in high-volume
 production; little or none in staging. Where you need errors, tail-sample at the
 gateway so you keep them. Record the effective rate.
- **Right-size storage and retention.** Tempo is cheap, but 100% ingest at scale still
 costs. Set block retention and back it with object storage; keep enough history to
 investigate yesterday's incident.
- **Make correlation a default.** Provision the trace↔log and metric→trace
 (exemplar) links in Grafana centrally so every team can pivot without setup. Mandate
 a `trace_id` field in the logging library.
- **Protect PII in spans.** Span attributes can leak secrets or personal data. Use the
 Collector's `attributes`/`redaction` processors to scrub before export.
- **Watch the tracing pipeline itself.** Dropped spans (Collector queue full, Tempo
 ingester pressure) silently lose data. Monitor Tempo and Collector metrics.

### 7. Common mistakes

- **A hop that doesn't propagate context.** — A service or proxy drops
 `traceparent`, so traces fragment into disconnected pieces. *Fix:* standardize on
 W3C TraceContext and verify propagation through gateways and meshes.
- **Head-sampling away your errors.** — 1% head sampling keeps 1% of errors, exactly
 the ones you need. *Fix:* tail-sample at the gateway to keep all errors and slow
 traces.
- **No `trace_id` in logs.** — You cannot pivot from a log to its trace, losing half
 the value of running both. *Fix:* inject `trace_id` into every structured log line.
- **Indexing traces like a search engine.** — Expecting full-text search over span
 contents misunderstands Tempo. *Fix:* query with TraceQL on attributes; add the
 attributes you will search for at instrumentation time.
- **Unbounded span attributes.** — Huge or high-cardinality attributes bloat storage
 and can carry PII. *Fix:* attach bounded, useful attributes; redact sensitive ones.
- **Treating traces as the only signal.** — Traces are sampled and per-request; they
 do not replace aggregate metrics or full logs. *Fix:* use all three, correlated.

### 8. Assessment

**Knowledge checks**

1. What three identifiers turn a set of spans into a single trace tree?
2. What is context propagation, and which headers does W3C TraceContext use?
3. Why can Tempo afford to ingest far more traces than a full-text tracing store?
4. What is an exemplar, and which two pillars does it connect?
5. Why does tail-based sampling preserve errors that head-based sampling loses?

**Concept exercise**

> Explain how you would find *which* downstream service made one specific user request
> slow **without using the words "trace," "span," or "Tempo."** Describe the data you
> would need to record per request and how you would reconstruct the timeline.

**Trade-off / debugging exercise**

> A request fails for a user. You have the error log (with a `trace_id`), full metrics,
> and 100%-ingested traces. Describe the exact pivot sequence you would use across the
> three pillars to reach root cause — and explain what you would be unable to do if the
> team had used 1% head sampling instead.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** `trace_id` (shared by all spans), `span_id` (unique per span), and
 `parent_span_id` (links a span to its cause).
- **Q2:** Injecting trace context into outgoing requests and extracting it in the
 callee so both share one trace. W3C TraceContext uses `traceparent` (and optional
 `tracestate`).
- **Q3:** It indexes only a little and stores whole traces by `trace_id` in cheap
 object storage, rather than indexing every span's contents.
- **Q4:** An exemplar is a specific `trace_id` attached to a metric sample; it links
 **metrics** to **traces** (click a point on a graph, jump to the example trace).
- **Q5:** Head sampling decides before the outcome is known and drops most traces
 uniformly, including errors. Tail sampling decides after seeing the whole trace, so
 it can keep every errored or slow trace.
- **Debugging:** Start at the error log, copy its `trace_id`, open that exact trace,
 read the waterfall to the failing/slow span, and inspect its attributes and child
 spans for the root cause; use metrics to see blast radius and timing. With 1% head
 sampling, the failed request's trace would almost certainly not exist, so the log's
 `trace_id` would resolve to nothing — you could see *that* it failed but not *where*.

</details>

---

### 9. Further reading

- Grafana — [Tempo documentation](https://grafana.com/docs/tempo/latest/) and
 [TraceQL](https://grafana.com/docs/tempo/latest/traceql/)
- W3C — [Trace Context specification](https://www.w3.org/TR/trace-context/)
- OpenTelemetry — [Context propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
 and [traces](https://opentelemetry.io/docs/concepts/signals/traces/)
- Grafana — [Exemplars](https://grafana.com/docs/grafana/latest/fundamentals/exemplars/)
- Grafana — [Tempo metrics-generator](https://grafana.com/docs/tempo/latest/metrics-generator/)

---


_Previous:_ Logging with Loki
· _Next:_ Grafana Dashboards →

---

## Grafana Dashboards

> A dashboard is where raw telemetry becomes a decision. **Grafana** is the "G" in the
> LGTM stack — one pane of glass over metrics (Prometheus), logs (Loki), and traces
> (Tempo). This module is about building dashboards that *answer a question* instead
> of drowning you in graphs, and treating them as **code** you version in Git, not
> clicks you lose.

**You'll need:**, a kind cluster,
`kubectl`, and [Helm](https://helm.sh/).

### Learning objectives

By the end of this module you will be able to:

- Apply **dashboard design principles**: one purpose, top-down hierarchy, readable panels.
- Use **variables and templating** to make one dashboard serve many services.
- Combine **mixed data sources** and correlate pillars on a single board.
- Explain Grafana **alert rules**, contact points, and notification policies.
- Deliver dashboards **as code** (Grafonnet/Jsonnet) and version them in Git.

---

### 1. Concept

#### A dashboard answers one question

The most common dashboard failure is the "wall of graphs": forty panels nobody reads,
built by accretion. A good dashboard has **one purpose** and a clear audience, and it
is organized **top-down** — the summary that tells you *if* something is wrong at the
top, the detail that tells you *what and where* below.

Design principles that actually matter:

- **One purpose per dashboard.** "Platform Overview" (health at a glance) and "Service
 Deep-Dive" (debugging one service) are *different* dashboards, not one giant board.
- **Top-down hierarchy.** First row: the four golden signals / SLO status — the
 "should I care?" answer. Lower rows: the breakdowns that explain it.
- **Lead with symptoms, support with causes.** Put user-facing signals (latency, error
 rate) above resource signals (CPU, memory); causes are for drilling, not the headline.
- **Readable panels.** Title every panel as the question it answers, set units
 (seconds, bytes, percent), and use consistent time ranges. A graph with no units is
 a trap.
- **Few, well-chosen panels** beat many. If a panel has never driven a decision,
 delete it.

#### Variables and templating

Hardcoding a service name into every query means one dashboard per service — hundreds
of near-identical boards to maintain. **Template variables** fix this: a dropdown at
the top (`$service`, `$namespace`, `$datasource`) rewrites every query on the board.

```promql
# a templated query: $service is chosen from a dropdown
sum by (job) (rate(http_requests_total{job="$service"}[5m]))
```

Variables can be **queries** (populate a `namespace` dropdown from
`label_values(kube_pod_info, namespace)`), **custom** lists, or **data source**
variables (so one board works across clusters). One well-templated dashboard replaces
a hundred copies — the platform-scale move.

#### Mixed data sources and correlation

A Grafana panel can query different **data sources**, and a dashboard can mix them: a
metrics panel from Prometheus next to a logs panel from Loki next to a traces panel
from Tempo — all sharing the dashboard's time range. This is where the three pillars
come together visually: see the error-rate spike, the error logs, and a slow trace on
*one screen*. **Exemplars** let you click a point on a latency graph and
jump to the trace behind it. Correlation configured once, consumed by everyone.

#### Alerting in Grafana

Grafana has its own alerting engine (complementary to Prometheus Alertmanager):

- **Alert rules** evaluate a query on a schedule and fire when a condition holds for a
 duration (e.g. error ratio > 5% for 5 minutes).
- **Contact points** are *where* a notification goes: Slack, PagerDuty, email, a webhook.
- **Notification policies** route firing alerts to contact points by label (team,
 severity), with grouping, timing, and silences.

The platform-engineering point: alert on **symptoms and SLO
burn**, route by **ownership labels**, and keep the policy as code. A dashboard is for
investigation; an alert is for waking someone — do not confuse them.

#### Dashboards as code

Dashboards built by clicking live only in Grafana's database. They drift, they are
not reviewed, and they vanish when someone "tidies up." Treat them like any other
platform artifact — **as code in Git**:

- **JSON model** — Grafana's native dashboard format. Exportable and importable, but
 verbose and painful to diff or template by hand.
- **Grafonnet** — a **Jsonnet** library that builds the JSON programmatically, so you
 compose panels from functions, share defaults, and avoid copy-paste. The idiomatic
 "dashboards as code" tool.
- **Grizzly / the sidecar** — tools and patterns to *apply* dashboards to Grafana from
 Git. In Kubernetes, the common pattern is a **ConfigMap** labelled
 `grafana_dashboard=1` that a Grafana sidecar auto-imports — so a merged pull request
 deploys a dashboard, GitOps-style.

Dashboards as code means review, diffs, rollback, and reuse — the same discipline you
apply to infrastructure.

---

### 2. Why it matters for platform engineering

- **Dashboards are a platform product surface.** The boards you ship — a Platform
 Overview, per-team RED dashboards generated from a template — are how teams *see*
 their services. A good default dashboard is a golden path.
- **Templating is how you scale to N teams.** One parameterized dashboard serves every
 service; you do not hand-build a board per team. That is the leverage argument again.
- **As-code dashboards survive people.** Click-built boards rot and disappear.
 Versioned dashboards are reviewable, diffable, and reproducible across clusters — and
 they are a portfolio-grade artifact.
- **One pane over three pillars reduces cognitive load.** Teams should pivot
 metrics → logs → traces without learning three tools or wiring correlation
 themselves. You configure it once, centrally.

---

### 3. Mental model

A dashboard is an **inverted pyramid**: the headline answer on top, the supporting
detail beneath, and links out to the raw evidence.

```text
 ┌─────────────────────────────────────────────┐
 │ ROW 1 SLO status · golden signals │ "should I care?" (summary)
 ├─────────────────────────────────────────────┤
 │ ROW 2 rate · errors · latency per service │ "what is wrong?" (breakdown)
 ├─────────────────────────────────────────────┤
 │ ROW 3 CPU/mem · logs · traces (exemplars) │ "why / where?" (drill-down)
 └─────────────────────────────────────────────┘
 ▲ $datasource $namespace $service ← templating rewrites every query

 Source of truth = Jsonnet in Git → rendered JSON → applied to Grafana (as code).
```

Rule of thumb: **if you cannot answer "what one question does this dashboard answer,
and for whom?" it is two dashboards wearing a trench coat.** Split it.

---

### 4. Minimal implementation

The smallest dashboard-as-code is a JSON model with one templated panel. Even hand-
written, the shape is clear — a variable and a panel whose query references it:

```json
{
 "title": "Service RED (minimal)",
 "templating": { "list": [
 { "name": "service", "type": "query", "datasource": { "type": "prometheus" },
 "query": "label_values(http_requests_total, job)" } ] },
 "panels": [
 { "type": "timeseries", "title": "Request rate — $service",
 "gridPos": { "h": 8, "w": 24, "x": 0, "y": 0 },
 "targets": [ { "expr": "sum(rate(http_requests_total{job=\"$service\"}[5m]))" } ] }
 ],
 "schemaVersion": 39
}
```

Hand-maintaining that JSON across dozens of panels is miserable — which is the whole
argument for Grofonnet. The same panel in **Grafonnet** is a function call you can
reuse and parameterize:

```jsonnet
local g = import 'g.libsonnet';
local panel = g.panel.timeSeries;

panel.new('Request rate — $service')
+ panel.queryOptions.withTargets([
 g.query.prometheus.new('$datasource',
 'sum(rate(http_requests_total{job="$service"}[5m]))'),
 ])
```

You `jsonnet` it into the JSON model, commit both, and apply it from Git. The lab
builds a real **Platform Overview Dashboard** this way and imports it via a ConfigMap.

---

### 5. Hands-on lab

You will deploy the metrics stack on kind, import a **Platform Overview Dashboard**
(delivered as Grafonnet *and* ready-to-import JSON) via a Grafana sidecar ConfigMap,
watch it populate with namespace CPU, RED, latency, and active alerts, and template it
by service.

➡️ **Start the lab: A Platform Overview Dashboard as code**

---

### 6. Production considerations

- **Version dashboards in Git, deploy via GitOps.** No production dashboard should
 exist only in Grafana's database. Render from Jsonnet, review the diff, and apply via
 sidecar/Grizzly so changes are auditable and reversible.
- **Templatize instead of copying.** Maintain a *few* parameterized dashboards
 (Overview, Service Deep-Dive) and generate per-team views from them. Hundreds of
 bespoke boards are unmaintainable.
- **Standardize units, thresholds, and layout.** A shared Grafonnet library of panel
 helpers keeps every team's board consistent and readable — consistency is a platform
 value.
- **Mind query cost.** Heavy panels on auto-refresh hammer the datasource; back hot
 panels with recording rules and set sane refresh intervals.
- **Control access and secrets.** Scope folders and permissions per team; keep data
 source credentials out of the JSON (use Grafana-managed secrets); do not expose
 Grafana publicly.
- **Separate dashboards from alerts.** Dashboards are for humans investigating; alerts
 page machines-to-humans. Keep alert rules as code too, routed by
 ownership labels.

### 7. Common mistakes

- **The wall of graphs.** — A dashboard with no single purpose and forty panels nobody
 reads. *Fix:* one question per dashboard, top-down, delete panels that never drive a
 decision.
- **Hardcoding service names.** — One static dashboard per service becomes hundreds to
 maintain. *Fix:* template variables (`$service`, `$namespace`, `$datasource`).
- **Click-built, unversioned dashboards.** — They drift, cannot be reviewed, and
 vanish. *Fix:* dashboards as code (Grafonnet) committed to Git and applied from there.
- **Panels without units or clear titles.** — "0.few" on an axis means nothing; a
 panel titled `panel 3` answers no question. *Fix:* set units, title each panel as its
 question.
- **Causes above symptoms.** — Leading with CPU graphs buries the user-facing signal.
 *Fix:* golden signals and SLO status on top, resources below.
- **Dashboards as alerts.** — Expecting someone to *watch* a board to catch incidents.
 *Fix:* alert on SLO burn and symptoms; dashboards are for investigation after the page.

### 8. Assessment

**Knowledge checks**

1. What is the single most important question to ask before building a dashboard?
2. How do template variables let one dashboard serve many services?
3. Why put user-facing symptoms above resource metrics in the layout?
4. Name two advantages of Grafonnet over a hand-edited JSON export.
5. What does the ConfigMap-plus-sidecar pattern achieve for dashboards?

**Concept exercise**

> Describe how you would present the health of 50 services to an on-call engineer on
> **one screen** — **without using the words "Grafana," "panel," or "dashboard."**
> Focus on what they must see first and what they drill into.

**Architecture / trade-off exercise**

> Your team has 120 click-built dashboards, many near-duplicates, and nobody trusts
> them. Design a plan to get to a small set of versioned, templated dashboards: what
> you consolidate, how you template, how you store and deploy them, and how you prevent
> the sprawl from returning.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** "What one question does this dashboard answer, and for whom?" Purpose and
 audience drive every other choice.
- **Q2:** A variable (`$service`) is a dropdown whose value is substituted into every
 query, so one board re-renders for any selected service instead of needing a copy per
 service.
- **Q3:** You want the "should I care?" (user impact) answer first; resource metrics
 are causes you drill into, not the headline. Leading with causes buries the signal.
- **Q4:** Reuse (panels are functions with shared defaults), and diffable/parameterized
 source instead of giant copy-pasted JSON — plus easy consistency across teams.
- **Q5:** It makes dashboards GitOps-deployable: a dashboard committed as a ConfigMap
 (labelled `grafana_dashboard=1`) is auto-imported by the Grafana sidecar, so a merged
 PR ships the dashboard — versioned, reviewed, reproducible.
- **Trade-off:** Consolidate duplicates into a few templated boards (one Overview, one
 Service Deep-Dive) parameterized by `$service`/`$namespace`; author in Grafonnet with
 a shared panel library; store in Git and deploy via sidecar/Grizzly; prevent sprawl
 by making the templated boards the paved road and disallowing unversioned production
 dashboards.

</details>

---

### 9. Further reading

- Grafana — [Dashboards documentation](https://grafana.com/docs/grafana/latest/dashboards/)
 and [best practices](https://grafana.com/docs/grafana/latest/dashboards/build-dashboards/best-practices/)
- Grafana — [Templating and variables](https://grafana.com/docs/grafana/latest/dashboards/variables/)
- Grafana — [Grafonnet](https://grafana.github.io/grafonnet/) and
 [Grizzly](https://grafana.github.io/grizzly/)
- Grafana — [Alerting](https://grafana.com/docs/grafana/latest/alerting/)
- Grafana — [Provision dashboards and data sources](https://grafana.com/docs/grafana/latest/administration/provisioning/)

---


_Previous:_ Distributed Tracing with Tempo
· _Next:_ SLOs and Error Budgets →

---

## SLOs and Error Budgets

> Not everything that twitches deserves a page. **SLOs** turn "is it healthy?" into a
> precise, user-centred target, and **error budgets** turn reliability into a number
> you can spend. This module defines SLI/SLO/SLA, shows how **multi-window,
> multi-burn-rate** alerting replaces noisy threshold alerts, and uses **Sloth** to
> generate it all from one small spec.

**You'll need:** and
[Docker](https://docs.docker.com/) (optionally kind + Helm for the live extension).

### Learning objectives

By the end of this module you will be able to:

- Distinguish **SLI**, **SLO**, and **SLA** and write a good SLI from existing metrics.
- Compute an **error budget** and explain what "spending" it means.
- Explain **burn rate** and design **multi-window, multi-burn-rate** alerts.
- Generate SLO recording and alert rules with **Sloth** from a single definition.
- Pick platform-relevant SLOs and avoid the classic SLO anti-patterns.

---

### 1. Concept

#### SLI, SLO, SLA

Three terms, often muddled, with a strict hierarchy:

- **SLI — Service Level Indicator.** The *measured* number: the proportion of good
 events over valid events. "The fraction of HTTP requests that return non-5xx in
 under 300ms." An SLI is a ratio between 0 and 1, computed from the metrics you
 already collect.
- **SLO — Service Level Objective.** The *target* for the SLI over a window: "99.9% of
 requests are good over 30 days." Internal, chosen by you, and the thing you actually
 engineer toward.
- **SLA — Service Level Agreement.** The *external, contractual* promise to customers,
 usually with financial penalties: "99.5% uptime or you get a credit." An SLA is a
 business/legal artifact; your SLO should be **stricter** than your SLA so you notice
 trouble before a breach.

> Rule of thumb: SLI is what you *measure*, SLO is what you *target*, SLA is what you
> *promise* (and pay for if you miss). Alert on the SLO; never let the SLA be your
> first warning.

A good SLI is **user-centred** and **event-based**: good events ÷ valid events, where
"good" reflects what a user actually experiences (fast, correct responses), not an
internal proxy like CPU.

#### Error budgets

If your SLO is 99.9%, you are explicitly saying **0.1% of events are allowed to be
bad**. That 0.1% is your **error budget** — a concrete allowance of failure over the
window:

```text
SLO 99.9% over 30 days
 error budget = 100% − 99.9% = 0.1%
 at ~43,200,000 requests/30d → ~43,200 requests may fail before you breach
```

The error budget reframes reliability from "never fail" (impossible, infinitely
expensive) to "fail no more than *this much*." It is also a **shared currency**
between platform/SRE and product teams:

- Budget **remaining** → you can afford to ship risky changes, run chaos experiments,
 move fast.
- Budget **exhausted** → freeze risky releases and spend effort on reliability until
 it recovers.

An error budget makes the speed-versus-reliability trade *explicit and data-driven*
instead of an argument.

#### Burn rate

**Burn rate** is how fast you are spending the budget relative to "sustainable."

```text
burn rate = (observed error ratio) / (1 − SLO)

 burn rate 1 → spending budget exactly fast enough to run out at window's end
 burn rate 2 → budget gone in half the window
 burn rate 14.4→ an entire month's budget gone in ~2 days
```

Burn rate is the key to *good* alerting: instead of "error ratio > 5%", you alert when
you are **burning budget fast enough to care**, scaled to your SLO.

#### Multi-window, multi-burn-rate alerting

Naïve budget alerts have a dilemma. Alert on a **short** window and you page on every
transient blip (noisy, non-actionable). Alert on a **long** window and you react too
slowly to a real outage. The Google SRE solution is **multi-window, multi-burn-rate**:

- Require a **fast burn** over both a **long** and a **short** window before paging —
 the long window proves it is sustained; the short window makes the alert **reset
 quickly** once the incident ends.
- Use **several tiers**: a high burn rate pages immediately; a lower burn rate over a
 longer window opens a ticket.

The canonical table (for a 30-day SLO):

```text
severity long win short win burn rate budget consumed meaning
──────── ──────── ───────── ───────── ─────────────── ───────────────────────
page 1h 5m 14.4 2% in 1h fast burn — wake someone
page 6h 30m 6 5% in 6h sustained fast burn
ticket 1d 2h 3 10% in 1d slow burn — investigate
ticket 3d 6h 1 10% in 3d chronic drain — plan work
```

You alert on **symptoms scaled to the budget**, not raw thresholds — far fewer, far
more meaningful pages.

#### SLO tooling: Sloth and Pyrra

Hand-writing the recording rules (the SLI at every window) and the four multi-window
alert expressions per SLO is tedious and error-prone. Tools generate them from one
small spec:

- **Sloth** — you write a `PrometheusServiceLevel` (service, objective, an
 error/total query), and `sloth generate` expands it into a complete `PrometheusRule`:
 SLI recording rules at all windows, budget/metadata rules, and the multi-window
 burn-rate `page`/`ticket` alerts. Declarative SLOs as code.
- **Pyrra** — a similar SLO manager with a UI, running as a controller that reconciles
 SLO objects into rules and shows budget/burn dashboards.

Both encode the Google SRE methodology so you do not re-derive burn-rate math per
service — exactly the kind of leverage a platform provides.

---

### 2. Why it matters for platform engineering

- **SLOs are how a platform defines "working."** Platform services (Argo CD, the
 ingress, the registry, the metrics pipeline) need published SLOs so teams know what
 to expect and you know when *you* are failing *them*.
- **Error budgets govern platform change.** The platform ships constantly; the budget
 tells you when to slow down. It turns "should we risk this upgrade?" into a number.
- **Good alerting is a platform gift.** Teams drowning in threshold alerts get a
 template: define an SLI, and burn-rate alerts are generated for them. You hand out
 *actionable* paging, not noise — a huge cognitive-load win.
- **It makes reliability a conversation, not a blame game.** A shared budget aligns
 platform, SRE, and product on one number instead of competing anecdotes.

---

### 3. Mental model

An error budget is a **prepaid balance of failure**; burn rate is how fast you are
drawing it down; multi-window alerts are **two clocks** that must agree before they
wake you.

```text
 budget = (1 − SLO) × events ← a balance you may spend
 │
 │ incidents withdraw from it at the BURN RATE
 ▼
 ┌───────────────────────────────────────────────┐
 │ fast burn (14.4×) → short+long window agree → PAGE │ "bleeding now"
 │ slow burn (3×) → long window only → TICKET│ "chronic leak"
 └───────────────────────────────────────────────┘
 short window = fast reset long window = proof it's sustained

 Spend budget? ship fast. Budget gone? freeze features, fix reliability.
```

Rule of thumb: **page on fast burn, ticket on slow burn, and never page on anything a
human cannot act on.** If an alert is not tied to budget burn or user pain, it is
probably noise.

---

### 4. Minimal implementation

The whole method fits in a few PromQL lines. Start from an event-based SLI — good vs
total — using metrics you already have:

```promql
# SLI: the BAD-event ratio over a window (lower is better)
sum(rate(http_requests_total{code=~"5.."}[5m]))
 /
sum(rate(http_requests_total[5m]))
```

Turn it into a **burn rate** by dividing by the budget, then page when a fast burn
holds over **both** a short and a long window:

```promql
# page: budget burning ~14.4x over 1h AND 5m (SLO = 99.9%, budget = 0.001)
(
 sum(rate(http_requests_total{code=~"5.."}[1h])) / sum(rate(http_requests_total[1h]))
) / 0.001 > 14.4
and
(
 sum(rate(http_requests_total{code=~"5.."}[5m])) / sum(rate(http_requests_total[5m]))
) / 0.001 > 14.4
```

Writing that by hand for every window and every service is exactly the toil Sloth
removes. The same SLO as a Sloth spec is a dozen readable lines:

```yaml
version: "prometheus/v1"
service: checkout
slos:
 - name: requests-availability
 objective: 99.9
 sli:
 events:
 error_query: sum(rate(http_requests_total{job="checkout",code=~"5.."}[{{.window}}]))
 total_query: sum(rate(http_requests_total{job="checkout"}[{{.window}}]))
 alerting:
 page_alert: { labels: { severity: page } }
 ticket_alert: { labels: { severity: ticket } }
```

`sloth generate` expands that into all the recording rules and multi-window alerts for
you. The lab runs exactly this and reads the generated output.

---

### 5. Hands-on lab

You will write an SLO as a Sloth `PrometheusServiceLevel`, run `sloth generate` to
expand it into a full `PrometheusRule` (SLI recording rules at every window plus
multi-window burn-rate `page`/`ticket` alerts), and read the generated alerting to see
the Google SRE method made concrete.

➡️ **Start the lab: SLOs and burn-rate alerts with Sloth**

### 6. Production considerations

- **Choose SLIs users feel.** Availability and latency of user-facing requests, not
 CPU or a liveness probe. An SLO on the wrong indicator is green while users suffer.
- **Set SLOs stricter than SLAs.** Your internal target must trip before the
 contractual promise so you act before a breach and a credit.
- **Enforce the error-budget policy.** Agree *in advance* what happens at zero budget
 (freeze risky releases, reprioritize reliability). An unenforced budget is theatre.
- **Prefer multi-window burn-rate alerts.** They cut false pages dramatically and reset
 fast when incidents end. Retire single-threshold alerts that page on transient blips.
- **Keep SLOs as code and review them.** Sloth/Pyrra specs in Git, rendered into
 `PrometheusRule`s and deployed via GitOps. SLOs change; version them.
- **Do not over-SLO.** A few meaningful SLOs per service beat dozens nobody watches.
 Every SLO needs an owner, a dashboard, and a runbook.

### 7. Common mistakes

- **SLIs on the wrong signal.** — An SLO on CPU or uptime-ping can read 100% while
 users get errors. *Fix:* event-based, user-centred SLIs (good requests ÷ valid
 requests).
- **SLO equals SLA (or is looser).** — You find out you breached the contract from the
 customer. *Fix:* set the SLO tighter than the SLA with margin to react.
- **Single-threshold budget alerts.** — Short windows page on blips; long windows react
 too late. *Fix:* multi-window, multi-burn-rate alerts (page on fast burn, ticket on
 slow).
- **100% as a target.** — Chasing 100% is infinitely costly and leaves no budget for
 change. *Fix:* pick an achievable target (99.9%, 99.95%) and *use* the resulting
 budget.
- **Ignoring the budget once set.** — Teams keep shipping with the budget at zero.
 *Fix:* a written, enforced error-budget policy with agreed consequences.
- **Burning effort on too many SLOs.** — Dozens of SLOs per service become noise nobody
 trusts. *Fix:* a handful of meaningful ones, each owned and runbooked.

### 8. Assessment

**Knowledge checks**

1. Define SLI, SLO, and SLA, and state which one you alert on and why.
2. For a 99.95% SLO over 30 days, what is the error budget, and what does "spending
 it" let a team do?
3. What is burn rate, and what does a burn rate of 14.4 mean for a 30-day budget?
4. Why does a multi-window alert use both a short and a long window?
5. What does Sloth generate from a single `PrometheusServiceLevel`?

**Concept exercise**

> Explain to a product manager how "99.9% reliable" lets the team **ship features
> faster** — **without using the words "SLA," "burn rate," or "alert."** Frame it
> around a budget they can choose to spend.

**Trade-off / debugging exercise**

> A team pages on `error_ratio > 1%` for 2 minutes. They get paged several times a
> night for blips that self-heal, and they *also* missed a slow 6-hour degradation that
> breached their SLO. Explain why one rule produces both failures, and design the
> alerting that fixes both — with specific windows and burn rates.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** SLI = measured good/valid ratio; SLO = internal target for it; SLA = external
 contractual promise. You alert on the SLO (via burn rate) so you act before the SLA
 is breached.
- **Q2:** Budget = 0.05% of valid events over 30 days. While budget remains, the team
 can ship risky changes, run experiments, and move fast; when it is gone, they slow
 down and invest in reliability.
- **Q3:** Burn rate = error ratio ÷ (1 − SLO). 14.4 means you would exhaust a 30-day
 budget in about two days — a fast burn worth paging on.
- **Q4:** The long window proves the burn is *sustained* (not a blip); the short window
 makes the alert **fire quickly** and, crucially, **reset quickly** once the incident
 ends.
- **Q5:** All the SLI recording rules at each window, budget/metadata rules, and the
 multi-window, multi-burn-rate `page` and `ticket` alerts — a complete `PrometheusRule`.
- **Debugging:** A single short-window threshold both over-fires on transient blips
 (short window, low bar) and under-detects slow burns (no long-window tier). Replace
 it with multi-window multi-burn-rate: page when burn ≥ 14.4 over 1h **and** 5m, and
 when ≥ 6 over 6h **and** 30m; ticket when ≥ 3 over 1d/2h and ≥ 1 over 3d/6h. The slow
 6-hour degradation trips the 6h/6× page tier; the blips no longer page because they
 fail the long-window condition.

</details>

---

### 9. Further reading

- Google — [SRE Book: Service Level Objectives](https://sre.google/sre-book/service-level-objectives/)
- Google — [SRE Workbook: Implementing SLOs](https://sre.google/workbook/implementing-slos/)
 and [Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)
- Sloth — [Documentation](https://sloth.dev/) and
 [GitHub](https://github.com/slok/sloth)
- Pyrra — [SLO manager](https://github.com/pyrra-dev/pyrra)
- Prometheus — [Alerting rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)

---


_Previous:_ Grafana Dashboards
· _Next:_ Platform Observability Strategy →

---

## Platform Observability Strategy

> You now have the tools — OpenTelemetry, Prometheus, Loki, Tempo, Grafana, Sloth. This
> final module is about **strategy**: what a *platform team* observes (which is not what
> app teams observe), how to watch the GitOps pipeline and the cluster control plane,
> who gets paged and when, and why every alert must link to a runbook. It turns a pile
> of tools into an operating discipline — and sets up Project 3.

**You'll need:** –11.7.
No cloud; this is a design module.

### Learning objectives

By the end of this module you will be able to:

- Distinguish what a **platform team** observes from what **application teams** observe.
- Define golden signals for **platform services** (Argo CD, Prometheus, Grafana, ESO).
- Observe the **GitOps pipeline** and the **cluster control plane**.
- Design an **alerting and paging** policy: who is woken, by what, and when.
- Attach a **runbook** to every alert and publish shared signals teams self-serve.

---

### 1. Concept

#### Two different jobs: platform vs application observability

An application team observes **their service**: its RED metrics, its logs, its traces,
its SLOs. A platform team observes **two** things, and conflating them is a strategic
error:

- **The platform's own services** — Argo CD, Prometheus, Grafana, the ingress, the
 secret operator, the registry, the Collector pipeline. These are *products you
 operate*, and they have their own golden signals and SLOs. When Argo CD is down,
 nobody can deploy; that is *your* incident, not any app team's.
- **The substrate every app runs on** — the cluster control plane (API server, etcd,
 scheduler), nodes, and shared capacity. App teams should rarely think about etcd; you
 always do.

Crucially, the platform also **provides** observability *to* app teams (the shared
Prometheus/Loki/Tempo/Grafana), but it does **not** own their SLOs. The dividing line:
*you own the platform's reliability and the observability plumbing; teams own their
own services' reliability on top of it.*

#### Golden signals for platform services

Apply RED / the four golden signals to the platform's own products:

- **Argo CD** — sync success rate and sync latency, app health/drift, reconciliation
 queue depth, controller errors. (You met `argocd_app_sync_total` in.)
- **Prometheus / Mimir** — scrape success (`up`), TSDB head series (cardinality!),
 rule-evaluation failures, remote-write latency and failures, ingestion rate.
- **Grafana** — availability, request latency/errors, datasource health, failed logins.
- **External Secrets Operator (ESO)** / secret tooling — secret sync success/latency,
 provider API errors, reconcile failures (a stuck ESO silently breaks deploys).
- **The OTel Collector** — queue size, `exporter_send_failed_*`, refused spans/metrics,
 memory pressure. Observe your observability pipeline, or it fails silently.

Each of these deserves an SLO. A platform that cannot say "Argo CD is
99.9% available" is not operating it as a product.

#### Observing the GitOps pipeline

GitOps is the platform's delivery mechanism, so its health is a
first-class platform signal:

- **Sync latency** — time from a Git commit to the change being live. A rising trend
 means delivery is slowing for everyone.
- **Sync errors** — failed reconciliations; spikes indicate a broken manifest, a bad
 image, or a cluster problem.
- **Drift events** — resources diverging from Git (manual `kubectl edit`), which Argo
 CD detects and (optionally) self-heals. Frequent drift signals a process problem.
- **Reconciliation throughput / queue depth** — the controller falling behind.

These make the invisible pipeline visible — and feed the "recent deployments" panel you
stubbed in.

#### Cluster-level signals

The control plane and nodes are the platform's foundation:

- **API server** — request latency and error rate (`apiserver_request_duration_seconds`,
 `apiserver_request_total`), inflight requests, and throttling. A slow API server slows
 every controller and `kubectl`.
- **etcd** — health, leader changes, fsync/commit latency, DB size. etcd trouble is a
 cluster-wide emergency.
- **Nodes** — pressure conditions (CPU/memory/disk/PID), `NotReady` nodes, kubelet
 health — the USE method applied to the fleet.
- **Scheduler / controller-manager** — scheduling latency and failures (Pods stuck
 `Pending`).
- **Capacity** — allocatable vs requested CPU/memory per node and per namespace, so you
 see saturation before it bites.

#### Cross-team observability: shared signals

Some signals every team should see without asking — published by the platform as a
product surface:

- A **Platform Overview** dashboard with cluster health and per-namespace
 usage, visible to all.
- **Per-team RED dashboards** generated from a template, so each team gets a consistent
 view of its services for free.
- Shared conventions (metric/label/log naming) so a metric means the same thing across
 teams — the standardization that makes self-service querying possible.

#### Alerting and paging: who, what, when

Tools do not page people; *policy* does. A platform paging policy answers:

- **Page only on symptoms and SLO burn.** Platform alerts fire on *user-facing* impact
 (Argo CD can't sync, API server latency breaching SLO, a node fleet losing capacity) —
 via multi-window burn-rate alerts, not raw thresholds.
- **Route by ownership.** A platform-service alert pages the **platform on-call**; an app
 alert pages the **owning team**. Routing uses labels (`team`, `severity`), so the
 right human is woken — never "everyone."
- **Tier by urgency.** `page` (wake someone now) vs `ticket` (handle in hours). Most
 alerts should be tickets; pages are rare and sacred.
- **Protect the on-call.** Group and dedupe related alerts, use silences during planned
 work, and track alert volume as a health metric. A noisy pager is a broken pager.

#### Runbooks: every alert links to one

An alert at 3am that says only "HighErrorRate" is cruel. **Every alert must carry a
`runbook_url`** pointing to a short page: what this alert means, how to confirm it, the
first diagnostic steps, how to mitigate, and how to escalate. Runbooks turn tribal
knowledge into something any on-call engineer can act on — and they are the single
cheapest way to reduce incident stress and time-to-recovery.

---

### 2. Why it matters for platform engineering

- **The platform is a dependency of everyone.** When a platform service degrades, every
 team is affected. Observing and SLO-ing your own services is how you catch that before
 they do — and how you earn trust.
- **Unobserved pipelines fail silently.** A stuck Argo CD or ESO means "deploys stopped
 working" with no error anyone sees until a team complains. Pipeline observability is
 how the platform notices first.
- **Good paging policy protects your team.** Alert fatigue burns out platform engineers
 and trains people to ignore the pager. Symptom-based, routed, runbooked alerting is a
 sustainability issue, not a nicety.
- **Shared signals reduce whole-org cognitive load.** Publishing consistent dashboards
 and conventions means every team sees the same truth without building it — the
 platform-as-product thesis applied to observability.

---

### 3. Mental model

Draw a line: the platform observes *the platform and the substrate*; app teams observe
*their apps*; a shared layer in the middle is published for everyone.

```text
 ┌─────────────────────────────────────────────────────────────┐
 │ APP TEAMS own: their service RED, logs, traces, and SLOs │ (self-serve)
 ├─────────────────────────────────────────────────────────────┤
 │ SHARED (platform publishes): Overview dashboard, per-team │ (a product
 │ RED templates, naming conventions, the Prom/Loki/Tempo stack │ surface)
 ├─────────────────────────────────────────────────────────────┤
 │ PLATFORM owns: Argo CD · Grafana · Prometheus · ESO · OTel │ (your SLOs,
 │ GitOps pipeline (sync latency/errors/drift) │ your pages)
 │ Cluster: API server · etcd · nodes · scheduler · capacity │
 └─────────────────────────────────────────────────────────────┘
 every alert here → routed by ownership → links to a runbook
```

Rule of thumb: **if its failure blocks many teams, the platform owns the signal and the
page; if it affects one service, that team does.** When unsure, ask "whose 3am is this?"

---

### 4. Minimal implementation

Strategy becomes real as a short, written **observability charter** — a table that
assigns, for each thing you watch, an owner, the golden signals, an SLO, who gets paged,
and the runbook. Even three rows beat an unwritten plan:

```text
service | signals (SLI) | SLO | page | runbook
-------------+--------------------------+---------+-----------+------------------------
Argo CD | sync success ratio | 99.9% | platform | /runbooks/argocd
API server | request latency p99, 5xx | 99.95% | platform | /runbooks/apiserver
<app>/checkout| request availability | 99.9% | app-team | /runbooks/checkout
```

The corresponding alert simply carries the ownership and the runbook as labels, so
routing and response are automatic:

```yaml
labels:
 severity: page
 team: platform # → routes to the platform on-call, not everyone
annotations:
 summary: "Argo CD sync error budget burning fast"
 runbook_url: "https://runbooks.example.com/argocd-availability"
```

That is the whole discipline: decide who owns each signal, set an SLO, route the page by
ownership, and link a runbook. The lab turns this into a filled-in strategy for a
realistic platform — the design document Project 3 implements.

---

### 5. Hands-on lab

You will produce a **platform observability strategy**: classify what the platform
observes versus what app teams observe, define golden signals and SLOs for the core
platform services, design a paging policy routed by ownership, and write one runbook.

➡️ **Start the lab: Design a platform observability strategy**

### 6. Production considerations

- **Dogfood your own stack.** Run the platform's services *on* the observability you
 give others, with the same SLOs and dashboards. If your monitoring of Argo CD is worse
 than a team's monitoring of its app, fix that first.
- **Watch the watchers.** Prometheus, the Collector, and Grafana must themselves be
 observed and, ideally, redundant. Alert on `up`, scrape failures, remote-write errors,
 and Collector drops — the pipeline failing silently is the classic trap.
- **Make on-call volume a tracked metric.** Count pages per week per team; a rising
 trend is an action item. Budget time to tune or delete noisy alerts.
- **Keep runbooks alive.** A stale runbook is worse than none. Link them from alerts,
 review them after incidents, and treat them as code in Git.
- **Separate tenancy and access.** Teams see their own data by default; platform-wide
 views are explicit. Enforce with Grafana folders/permissions and Loki/Prometheus
 tenancy.
- **Plan for the observability bill.** Metrics cardinality, log volume, and trace
 retention are real costs you govern centrally. Budget
 and cap them before a tenant does it for you.

### 7. Common mistakes

- **Platform team only watches app metrics.** — You see tenants' services but miss your
 own (Argo CD, etcd, the Collector), so platform outages surprise you. *Fix:* golden
 signals and SLOs for every platform service and the control plane.
- **Paging everyone for everything.** — Broad routing and threshold alerts create fatigue
 and trained helplessness. *Fix:* route by ownership label, page only on symptoms/SLO
 burn, make tickets the default.
- **Alerts with no runbook.** — On-call gets a cryptic name at 3am and no next step.
 *Fix:* mandate `runbook_url` on every alert; block alerts that lack one.
- **Ignoring the GitOps pipeline.** — Sync latency, errors, and drift go unwatched, so
 "deploys stopped working" is discovered by complaint. *Fix:* observe sync
 latency/errors/drift as first-class platform signals.
- **No tenancy or shared conventions.** — Every team invents names and can see
 everything, so cross-team querying and access control break. *Fix:* shared semantic
 conventions and per-team access.
- **Unobserved observability stack.** — The monitoring that watches everything is itself
 unmonitored and fails quietly. *Fix:* monitor Prometheus/Loki/Tempo/Collector health
 and make them redundant.

### 8. Assessment

**Knowledge checks**

1. Name two things a platform team observes that an application team does not.
2. Give the golden signals you would track for Argo CD and for the Kubernetes API server.
3. What three GitOps-pipeline signals belong on a platform's radar, and why?
4. How should a platform alert be *routed*, and what must every alert link to?
5. Why must the observability stack itself be observed and made redundant?

**Concept exercise**

> Explain where a platform team's observability responsibility **ends** and an app
> team's **begins** — **without using the words "SLO," "metric," or "dashboard."** Use
> the idea of who is woken when something breaks.

**Architecture / design exercise**

> Your platform runs Argo CD, a shared Prometheus, Grafana, and ESO for 40 teams on one
> cluster. Design the alerting-and-paging policy: which failures page the platform
> on-call versus a team, which are pages versus tickets, how routing decides, and what
> each alert links to. Then name the one platform-service outage that would hurt the most
> and justify its SLO.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** The platform's own services (Argo CD, Prometheus, Grafana, ESO, the Collector)
 and the cluster substrate (API server, etcd, nodes, scheduler, capacity).
- **Q2:** Argo CD: sync success rate, sync latency, app health/drift, controller errors.
 API server: request latency (p99), error rate (5xx), inflight/throttling.
- **Q3:** Sync latency (delivery slowing), sync errors (broken reconciliations), and
 drift events (resources diverging from Git) — they make the delivery pipeline's health
 visible to the team responsible for it.
- **Q4:** Routed by ownership labels (`team`, `severity`) to the right on-call — platform
 service → platform on-call, app → owning team — and tiered page vs ticket. Every alert
 must link to a `runbook_url`.
- **Q5:** If Prometheus/Loki/Tempo/the Collector fail silently, you lose the ability to
 see any other failure; redundancy and self-monitoring keep the safety net intact.
- **Design:** Platform-service and control-plane failures (Argo CD down, API server SLO
 breach, etcd unhealthy, Collector dropping data) page the platform on-call; app SLO
 burns page the owning team by label. Page on fast burn / hard-down; ticket on slow burn
 and capacity trends. Route by `team`/`severity`; every alert carries a runbook. The
 most damaging single outage is usually **Argo CD** (no team can deploy) or the **API
 server/etcd** (cluster-wide) — justify a strict SLO (e.g. 99.9–99.95%) because its
 failure blocks everyone.

</details>

---

### 9. Further reading

- Google — [SRE Book: Monitoring](https://sre.google/sre-book/monitoring-distributed-systems/)
 and [Being On-Call](https://sre.google/sre-book/being-on-call/)
- Google — [SRE Workbook: Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)
- Argo CD — [Monitoring and metrics](https://argo-cd.readthedocs.io/en/stable/operator-manual/metrics/)
- Kubernetes — [Monitoring the control plane / system metrics](https://kubernetes.io/docs/concepts/cluster-administration/system-metrics/)
- Prometheus — [Alertmanager routing](https://prometheus.io/docs/alerting/latest/configuration/)
 and the [Runbooks pattern](https://prometheus.io/docs/practices/alerting/)

---


_Previous:_ SLOs and Error Budgets
· _Next:_ Project 3 · Observability Platform →
