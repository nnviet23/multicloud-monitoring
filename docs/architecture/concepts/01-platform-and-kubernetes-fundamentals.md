# 01 · Platform and Kubernetes Fundamentals

> **Project Applicability:** Active in Project

Core architectural principles for internal developer platforms, Linux container primitives, and Kubernetes orchestration.

---

## 1. Platform Engineering Foundations

### The Cognitive Load Crisis

*Team Topologies* (Skelton & Pais) defines three kinds of cognitive load:
- **Intrinsic** — effort inherent to the domain logic itself.
- **Extraneous** — effort imposed by the environment and toolchain (deployment YAML, TLS wiring, CI/CD plumbing).
- **Germane** — effort that builds lasting understanding.

Platform engineering exists to cap and reduce **extraneous cognitive load** so stream-aligned teams can focus on delivering product value.

### Ops → DevOps → Platform Engineering

- **Siloed Ops:** Developers hand off code to a separate operations team. Slow feedback, weak ownership.
- **DevOps:** *"You build it, you run it."* Teams gain ownership, but at scale every team re-solves deployment, observability, and security from scratch.
- **Platform Engineering:** A platform team builds a reusable, **self-service internal product** (APIs, golden paths, guardrails) that abstracts operational complexity without returning to ticket-driven Ops.

### Core Principles

1. **Platform as a Product:** Developers are internal customers. Adoption by choice—not mandate—is the measure of success.
2. **Thinnest Viable Platform (TVP):** Build the smallest capability that removes real developer friction (e.g., a documented golden path and starter template) and evolve it based on demand.
3. **Golden Paths & Guardrails:** Encode security, observability, and reliability defaults once in paved roads so teams get them automatically.

---

## 2. Containerization Primitives

A container is an ordinary Linux process that the kernel **isolates** with namespaces and **limits** with cgroups—there is no guest OS.

### Linux Kernel Primitives

- **Namespaces** (what a process can see):
  - `pid` — isolated process ID space (app runs as PID 1).
  - `net` — isolated network stack (interfaces, routing, ports).
  - `mnt` — isolated mount table and root filesystem.
  - `uts` — isolated hostname and domain name.
  - `ipc` — isolated System V IPC and POSIX message queues.
  - `user` — UID/GID mapping (root inside container can map to unprivileged UID on host).
- **cgroups v2** (what a process can use):
  - Enforces CPU (`cpu.max`), memory (`memory.max`, exceeding triggers `OOMKilled`), and I/O limits. Kubernetes `resources.requests` and `resources.limits` compile directly to cgroup constraints.

### Containers vs. Virtual Machines

| Dimension | Virtual Machines | Containers |
|-----------|------------------|------------|
| Isolation layer | Hardware (Hypervisor + Guest OS) | OS Kernel (Namespaces + cgroups) |
| Overhead | GBs, seconds-to-minutes boot | MBs, millisecond startup, high density |
| Security boundary | Strong (separate kernel) | Shared host kernel (use non-root, seccomp, dropped capabilities, or gVisor/Kata for untrusted multi-tenancy) |

### OCI Images & Container Runtime Interface (CRI)

- **OCI Image:** Content-addressed filesystem **layers** (tar diffs overlaid via `overlay2`), a **config** JSON (entrypoint, env, layer digests), a **manifest** (for one platform), and an optional **index** (multi-arch `linux/amd64`, `linux/arm64`).
- **Tags vs. Digests:** Tags (`:1.0`) are mutable labels; digests (`@sha256:...`) are immutable. Production deployments should promote by digest.
- **CRI Stack:** `kubelet` → CRI (gRPC) → High-level runtime (`containerd` / `CRI-O`) → OCI runtime (`runc` / `crun`) → Linux kernel.

---

## 3. Kubernetes Architecture

Kubernetes is a declarative **control system** built around the **reconciliation loop**:

1. **Desired state** (`spec`) is declared by the user and stored in `etcd`.
2. **Actual state** (`status`) is observed by controllers.
3. **Reconciliation** continuously acts to close the gap between actual and desired state, making the cluster self-healing.

### Control Plane vs. Data Plane

All components communicate exclusively through the **API server**—nothing talks peer-to-peer.

- **Control Plane (the brain):**
  - `kube-apiserver` — central REST hub; authenticates, validates, and persists all state changes.
  - `etcd` — distributed, consistent key-value store holding the entire cluster state.
  - `kube-scheduler` — assigns unscheduled Pods to nodes based on resources, affinity, and taints/tolerations.
  - `kube-controller-manager` — runs core reconciliation loops (Deployment, ReplicaSet, Node, Job controllers).
  - `cloud-controller-manager` — integrates with cloud provider APIs (e.g., `LoadBalancer` Services).
- **Data Plane (worker nodes):**
  - `kubelet` — node agent; watches the API server for assigned Pods and drives the CRI runtime.
  - `kube-proxy` — programs `iptables`/`IPVS` rules so Service virtual IPs route to healthy Pod endpoints.
  - **Container runtime** (`containerd`) — manages images, snapshots, and container lifecycles.

### Resource Model & Core Objects

Every Kubernetes object shares three top-level fields: `metadata` (name, namespace, labels, annotations), `spec` (desired state), and `status` (actual state).

- **Workloads:** `Pod` (atomic scheduling unit), `Deployment` (stateless rolling updates/rollbacks), `StatefulSet` (stable network identity and persistent storage), `DaemonSet` (one Pod per node, e.g., collectors/CNI), `Job` / `CronJob` (run-to-completion).
- **Networking:** `Service` (`ClusterIP`, `NodePort`, `LoadBalancer`, headless) backed by `EndpointSlices` and cluster DNS (`<service>.<namespace>.svc.cluster.local`).
- **Configuration & Storage:** `ConfigMap` (non-sensitive config), `Secret` (sensitive data; base64-encoded by default—requires encryption at rest or external secret stores), `PersistentVolume` / `PersistentVolumeClaim` / `StorageClass` (CSI-backed persistence).
- **Governance & Reliability:** `RBAC` (`Role`/`ClusterRole` + bindings), `ResourceQuota` & `LimitRange`, `HPA` (Horizontal Pod Autoscaler), `liveness`/`readiness`/`startup` probes, `PodDisruptionBudget` (PDB).

---

## References

- [Kubernetes Documentation — Cluster Architecture](https://kubernetes.io/docs/concepts/architecture/)
- [Open Container Initiative (OCI) Specifications](https://opencontainers.org/)
- [CNCF Platforms White Paper](https://tag-app-delivery.cncf.io/whitepapers/platforms/)
