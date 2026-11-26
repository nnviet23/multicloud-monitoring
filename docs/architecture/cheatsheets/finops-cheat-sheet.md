# Cheat Sheet — FinOps & Cost Engineering

> FinOps brings financial accountability to variable cloud spend through a loop of
> Inform, Optimize, Operate - making cost a first-class, attributable signal.

## Lifecycle

| Phase | Goal | Activities |
|-------|------|------------|
| **Inform** | Visibility and allocation | Tag/label, attribute cost, show back |
| **Optimize** | Reduce waste | Right-size, spot, scale-to-zero, commitments |
| **Operate** | Make it continuous | Budgets, alerts, policy, culture |

## The attribution gap

- Cloud bills are per **resource** (VM, disk, load balancer); value is per
  **team/service**.
- A shared Kubernetes cluster hides this: one node runs many teams' pods.
- Close the gap by **splitting shared cost** down to namespace and workload using
  each pod's resource **requests** and the node's cost over time.

## Cost per workload

```text
workload_cost =
  sum(pod_requests_share * node_hourly_cost * hours)
  + attached storage (PV GiB * price per GiB-month)
  + network egress + per-workload managed services

pod_requests_share = pod_requests / node_allocatable
```

- Bill on **requests** (reserved capacity), not just usage - idle reservations still
  cost money. OpenCost and Kubecost implement this split.

## Cost allocation labels

```yaml
metadata:
  labels:
    team: checkout
    app: web
    env: prod
    cost-center: "cc-4211"
```

- Enforce required labels with policy (Kyverno) so **everything** is attributable.
- Map cloud tags to Kubernetes labels so cluster and cloud spend reconcile.

## Showback vs chargeback

- **Showback:** report each team's cost for visibility, with no internal billing.
- **Chargeback:** bill a team's budget for its actual spend (full accountability).
- Start with showback to build trust, then move to chargeback where it changes
  behavior. Track **unit economics** (cost per request/tenant/feature), not just
  total spend.

## Optimization checklist

- [ ] **Right-size** requests/limits to real usage (VPA recommendations).
- [ ] **Spot / preemptible** nodes for fault-tolerant and batch workloads.
- [ ] **Consolidate / bin-pack** nodes (Karpenter or autoscaler consolidation).
- [ ] **Scale to zero** idle dev/preview environments (off-hours, KEDA).
- [ ] **Commitments** - Savings Plans or CUDs for steady baseline load.
- [ ] **Egress** - cut cross-AZ/region and internet egress; cache and use a CDN.
- [ ] **Orphans** - delete unattached disks, old snapshots, idle LBs and IPs.
- [ ] **Storage tiering** - move cold data to cheaper storage classes.
- [ ] **Budgets and alerts** - per team, with anomaly detection.

## Kubernetes cost quick reference

```bash
# OpenCost / Kubecost allocation (namespace, 7d, with efficiency)
kubectl cost namespace --window 7d --show-efficiency
opencost --exporter-port 9003            # Prometheus-sourced allocation
```

- **Rightsizing signal:** a request far above usage means waste; usage near the
  limit means risk. Set CPU requests near p90-p95 of real usage, memory above the
  working set.
- **Spot readiness:** stateless, replicated, retry-tolerant, or batch workloads are
  good spot candidates; stateful leaders and singletons are not.

## Anomaly & budget guardrails

- **Budget alert:** fire when projected month-end spend exceeds budget, or when the
  day-over-day delta per team label crosses a threshold.
- **Policy guardrails:** block pods without a `team`/`cost-center` label, and cap
  namespace requests with a ResourceQuota so one team cannot drain the cluster.
- **Review cadence:** a weekly waste report, a monthly commitment/coverage review,
  and quarterly rate negotiation.

## See also

- [`../18-finops-and-cost-engineering/`](../18-finops-and-cost-engineering/) - cloud
  cost fundamentals, Kubernetes cost, attribution, and optimization patterns.
