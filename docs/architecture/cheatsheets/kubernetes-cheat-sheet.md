# Cheat Sheet — Kubernetes

> The control plane stores desired state and runs controllers; the data plane runs
> your pods. Every object is declarative and reconciled toward its desired state.

## Architecture

### Control plane

- **kube-apiserver** - the front door; validates and persists every object (REST).
- **etcd** - consistent key-value store; the single source of truth.
- **kube-scheduler** - binds unscheduled pods to nodes by resources and constraints.
- **kube-controller-manager** - runs built-in controllers (Deployment, Node, Job).
- **cloud-controller-manager** - integrates cloud load balancers, routes, volumes.

### Data plane (every node)

- **kubelet** - starts and stops containers, reports node and pod status.
- **container runtime** - containerd or CRI-O runs containers via the CRI.
- **kube-proxy** - programs Service load-balancing (iptables/IPVS); eBPF CNIs can
  replace it.

> Reconciliation loop: you declare desired state, a controller observes the diff and
> acts, then repeats. Self-healing is this loop, not a one-shot apply.

## Resource model

- **Pod** - smallest deployable unit; one or more containers sharing network and IPC.
- **Namespace** - soft tenancy boundary for names, quotas, and RBAC.
- **Labels/selectors** - how objects find each other (Service to Pods).
- **Annotations** - non-identifying metadata for tooling and config.
- **Controllers own pods** - you deploy a Deployment; it owns ReplicaSets to Pods.

## Workloads

| Workload | Use for | Key behavior |
|----------|---------|--------------|
| Deployment | Stateless apps | Rolling update, easy rollback, N replicas |
| StatefulSet | Stateful apps | Stable network IDs + per-pod PVCs, ordered |
| DaemonSet | Node agents | One pod per matching node |
| Job | Run-to-completion | Retries to success, then stops |
| CronJob | Scheduled jobs | Creates Jobs on a cron schedule |
| ReplicaSet | Managed by Deployment | Maintains the replica count |

## Resource management

| Concept | What it does |
|---------|--------------|
| **requests** | Scheduler reserves this; basis for bin-packing and QoS |
| **limits** | Hard cap; CPU is throttled, memory over-limit is **OOMKilled** |
| **ResourceQuota** | Caps total requests/limits/object counts per namespace |
| **LimitRange** | Default/min/max per pod or container in a namespace |
| **HPA** | Scales replicas on CPU/memory/custom metrics |
| **VPA** | Recommends or sets right-sized requests |
| **PodDisruptionBudget** | Minimum available pods during voluntary disruptions |

- **QoS classes:** `Guaranteed` (requests == limits), `Burstable` (requests < limits),
  `BestEffort` (none set). Under node pressure, BestEffort is evicted first.

Example requests/limits, plus an HPA command:

```yaml
resources:
  requests: { cpu: "100m", memory: "128Mi" }
  limits:   { cpu: "500m", memory: "256Mi" }
```

```bash
kubectl autoscale deployment web --cpu-percent=70 --min=2 --max=10
```

## RBAC model

- **Subjects:** User, Group, ServiceAccount.
- **Verbs:** get, list, watch, create, update, patch, delete, deletecollection.
- **Role** (namespaced) and **ClusterRole** (cluster-wide) define permissions.
- **RoleBinding** and **ClusterRoleBinding** grant a role to subjects.
- **Least privilege:** prefer a Role + RoleBinding scoped to a namespace; grant a
  ClusterRole only when the access is genuinely cluster-wide.

```bash
kubectl auth can-i create deployments -n app
kubectl auth can-i list secrets --as=system:serviceaccount:app:ci
```

## Pod debugging workflow

| Symptom | Likely cause | First checks |
|---------|--------------|--------------|
| **CrashLoopBackOff** | App exits/panics, bad command, failing probe | `logs --previous`, check probes, exit code |
| **ImagePullBackOff** | Bad tag, private registry auth | `describe pod` events; verify image + `imagePullSecrets` |
| **OOMKilled** | Memory limit too low or a leak | `describe` shows `Last State: OOMKilled`; raise limit or fix leak |
| **Pending** | No schedulable node, quota, PVC unbound | `describe pod` events: insufficient cpu/mem, taints, affinity |
| **CreateContainerConfigError** | Missing ConfigMap/Secret key | `describe` events; verify the referenced keys exist |

```bash
kubectl get pods -o wide
kubectl describe pod <pod>                 # events are at the bottom
kubectl logs <pod> -c <container> --previous
kubectl get events --sort-by=.lastTimestamp -n <ns>
kubectl debug -it <pod> --image=busybox --target=<container>
```

## See also

- [`../03-kubernetes-fundamentals/`](../03-kubernetes-fundamentals/) - architecture,
  workloads, RBAC, resource management, and debugging in depth.
- [`../10-kubernetes-advanced/`](../10-kubernetes-advanced/) - CRDs, operators, and
  admission control.
- [`kubectl-cheat-sheet.md`](./kubectl-cheat-sheet.md) - the command reference.
