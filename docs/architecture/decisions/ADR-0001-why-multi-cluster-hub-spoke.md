# ADR-0001: Why Multi-Cluster Hub-Spoke Topology and WAN Emulation

## Status
Accepted

## Context
Evaluating a multi-cloud observability and AIOps platform locally requires a topology that mirrors distributed cloud boundaries—separate compute, persistence, and centralized observability planes—while fitting within a developer workstation's memory budget (8–10 GB RAM).

The system spans three independent Kubernetes (`k3d`) clusters:
- `hub-k3d`: Central control plane for GitOps (Argo CD), observability backends (Thanos, Loki, Tempo, MinIO, Grafana, Pyrra, Robusta), and the AIOps engine.
- `aws-k3d`: Simulated AWS spoke running TeaStore compute microservices (`webui`, `auth`, `recommender`, `image`, `registry`) and Locust load generation.
- `azure-k3d`: Simulated Azure spoke running TeaStore persistence (`persistence`, `teastore-db` MySQL).

Key constraints:
- Cross-cluster L3 routing and DNS resolution must work reliably without heavy Service Mesh sidecars.
- Inter-cluster telemetry must experience realistic WAN degradation (latency, jitter, packet loss) to validate collector retries and AIOps root-cause decomposition ($T_{\text{WAN}}$).

## Decision
We adopt a **3-cluster Hub-Spoke topology** on a dedicated Docker bridge network (`mc-monitoring-net`, `172.28.0.0/16`) with static LoadBalancer/node IPs, **CoreDNS `NodeHosts`** for cross-cluster DNS (`hub-gateway.hub.multicloud.local`, `thanos-query.hub.multicloud.local`, `hub.local`), and **Linux `tc netem`** (`delay 10ms 2ms loss 0.1%` on `eth0`) to emulate WAN links.

## Alternatives Considered
- **Default Docker Bridge:** Does not guarantee deterministic IPs across restarts, breaking cross-cluster OTLP and Argo CD endpoints.
- **Multi-Cluster Service Mesh (Istio / Linkerd):** Automates cross-cluster service discovery but adds 3–4 GB RAM overhead for sidecar proxies, exceeding the local workstation budget.
- **Real Cloud Clusters (EKS & AKS):** Incurs \$150–\$300/month in cloud spend and slows down rapid local iteration.

## Consequences
- **Positive:** 100% reproducible 3-cluster lab under 10 GB RAM; realistic WAN impairment enables end-to-end validation of OTel retries and $T_{\text{WAN}}$ RCA.
- **Negative:** Requires `NET_ADMIN` / Docker root privileges to apply `tc netem` rules and a CLI/script to keep CoreDNS `NodeHosts` synchronized with cluster IPs.
