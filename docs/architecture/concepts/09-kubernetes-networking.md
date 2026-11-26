# 09 · Kubernetes Networking

> **Project Applicability:** Reference / Future Extension — The local **k3d** simulation uses default Flannel CNI and simulated WAN latency; Cilium/eBPF, Gateway API, and Service Mesh are reference/future extensions.

> Networking is where "it works on my laptop" goes to die. A pod that can't reach its
> database, a Service that silently drops traffic, a NetworkPolicy that locks out DNS —
> these are the incidents a platform team owns for every team on the cluster. This
> phase builds Kubernetes networking from first principles (the flat pod network, the
> CNI, Services and DNS), then levels up to **default-deny security with
> NetworkPolicies**, **Cilium and eBPF**, the **Gateway API**, and a grounded look at
> **service mesh**.

## Why networking?

Every earlier phase assumed the network just works. Pods found each other, Services
load-balanced, DNS resolved. This phase opens that black box — because when it
breaks, the platform engineer is the one who has to explain *why*, and because the
platform's **security** and **traffic** guarantees are enforced here:

- **Isolation** — in Project 1 and
 Project 2 you isolated teams with namespaces, RBAC,
 and quotas. The missing layer is the *network*: by default every pod can reach
 every other pod. Default-deny NetworkPolicies close that gap.
- **Zero trust** — 
 introduced identity-based, L7-aware authorization. This phase shows the networking
 machinery (Cilium, eBPF, mTLS) that makes it real.
- **Ingress** — getting external traffic *in* safely, with role separation between the
 platform team and app teams, is the Gateway API's whole reason to exist.

The throughline: **understand the model first, build the smallest demonstration
yourself, then reach for the production tool (Cilium, Gateway API) — and know why.**

## Kubernetes Networking Fundamentals

> Kubernetes networking looks like magic until you learn the one rule it's built on:
> **every pod can reach every other pod directly, with no NAT**, as if they were all
> on one big flat network. This module builds the mental model from that rule — veth
> pairs and bridges, the pod-to-pod and pod-to-Service paths, DNS, and what kube-proxy
> actually does — so that when traffic doesn't flow, you know exactly where to look.

**You'll need:** · Services and Networking,
Docker, and [kind](https://kind.sigs.k8s.io/).

### Learning objectives

By the end of this module you will be able to:

- State the Kubernetes networking model and its four core requirements.
- Explain how a packet travels **pod → pod** on the same node and across nodes.
- Explain how a packet travels **pod → Service → pod**, and what rewrites the IP.
- Trace the **DNS resolution** chain for a Service name.
- Describe what **kube-proxy** does (and what replaces it).

---

### 1. Concept

The network model is visualized in Kubernetes networking.

#### The one rule: a flat network, no NAT

Kubernetes imposes a deliberately simple networking model. Every implementation (every
CNI) must satisfy four requirements:

```text
1. Every Pod gets its own unique IP address.
2. Pods on a node can reach all Pods on all nodes WITHOUT NAT.
3. Agents on a node (e.g. kubelet) can reach all Pods on that node.
4. A Pod sees its own IP as the same IP others use to reach it (no NAT surprises).
```

The result is a **flat network**: from any pod's point of view, every other pod is
directly reachable at its IP, as if they shared one giant LAN — regardless of which
node they're actually on. No port mapping, no NAT between pods. This is a huge
simplification versus the Docker single-host world, where you published
ports and containers lived behind the host.

Everything else — Services, DNS, NetworkPolicies, ingress — is built *on top of* this
flat pod network. Hold onto the rule; it explains almost every "why can't X reach Y?"

#### Inside a node: veth pairs and a bridge

How does a pod get a network interface that's reachable from the node and from other
nodes? With a **virtual ethernet (veth) pair** — think of it as a virtual cable with
two ends:

```text
 Node's network namespace Pod's network namespace
 ┌──────────────────────────────┐ ┌────────────────────────────┐
 │ cni0 (bridge) │ │ eth0 (10.244.1.5) │
 │ │ │ │ │ │
 │ vethXXXX ◄────── veth pair ─────────────► (other end) │
 └──────────────────────────────┘ └────────────────────────────┘
```

- One end of the veth pair (`eth0`) lives **inside the pod's network namespace** (the
 isolation primitive from ) and holds the pod's IP.
- The other end lives in the **node's** namespace and is plugged into a **bridge**
 (often `cni0`) — a virtual switch connecting all pods on that node.

Two pods on the *same node* talk through the bridge, like two machines on one switch.

#### Across nodes: the CNI's job

When a pod on node A talks to a pod on node B, the packet leaves the bridge and must
cross the physical network. Getting it to the right node, with the destination's pod
IP intact (no NAT, per the rule), is the **CNI plugin's** responsibility. Different
CNIs do this differently — a VXLAN overlay (encapsulate the pod packet inside a
node-to-node packet), or native routing (teach the network how to reach each node's
pod CIDR via BGP). That's; for now, know that **the CNI is what makes the
flat network real across nodes.**

#### Pod → Service: a stable IP over shifting pods

Pods are mortal — they come and go, and their IPs change. You can't hardcode a pod IP.
A **Service** gives a stable **virtual IP (ClusterIP)** that load-balances to the
current healthy pods behind it. But that ClusterIP isn't a real
interface anywhere — no machine "owns" it. So what makes traffic to it actually reach
a pod?

```text
 pod ──► 10.96.0.10:80 (Service ClusterIP — virtual, owned by nobody)
 │
 │ on the way out, the kernel REWRITES the destination:
 ▼
 10.244.2.7:8080 (a real pod IP, chosen from the Service's endpoints)
```

A component programs the kernel to **DNAT** (destination NAT) the Service IP to one of
the backing pod IPs. Classically that component is **kube-proxy**, writing `iptables`
(or IPVS) rules; with Cilium it's **eBPF** doing the same job faster.
The Service's set of real pod IPs is tracked as **EndpointSlices**, updated as pods
come and go.

#### DNS: names, not IPs

Developers use names (`backend`), not ClusterIPs. The cluster runs **CoreDNS**, and
every pod's `/etc/resolv.conf` points at the DNS Service. The resolution chain for a
Service follows a predictable pattern:

```text
 backend
 → backend.<namespace>.svc.cluster.local (search-domain expansion)
 → CoreDNS returns the Service's ClusterIP
 → kube-proxy/eBPF DNAT to a real pod IP
```

- A normal Service resolves to its **ClusterIP**.
- A **headless** Service (`clusterIP: None`) resolves straight to the **pod IPs** —
 used by StatefulSets where each pod has a stable identity.

> **Why this matters for debugging:** a huge fraction of "can't connect" incidents are
> *DNS*, not routing. If `nslookup backend` fails but the pod IP works, you have a DNS
> problem, not a network problem.

#### kube-proxy: the Service plumber

**kube-proxy** runs on every node and watches Services and EndpointSlices, programming
the node's `iptables`/`IPVS` rules so that Service IPs DNAT to pod IPs. It does *not*
proxy packets itself in the common modes — it just configures the kernel to do the
rewriting. Its modes:

- **iptables** — the default; a chain of NAT rules. Simple, but rule evaluation scales
 linearly with Service count (slow at very large scale).
- **IPVS** — kernel-level load balancing with hash tables; scales better.
- **eBPF (Cilium)** — replaces kube-proxy entirely with eBPF programs.

---

### 2. Why it matters for platform engineering

The platform team owns the network for *every* team on the cluster. When a service
can't reach its database, when DNS is flaky, when a NetworkPolicy locks something out,
the platform engineer is the one holding the pager. You cannot debug what you don't
understand:

- **A shared mental model saves incidents.** "Pod → Service → pod with a DNAT in the
 middle, names resolved by CoreDNS" is the map you follow under pressure.
- **Security is built on this layer.** Default-deny isolation and
 zero-trust L7 policy only make sense once you know the default is a
 wide-open flat network.
- **It's the substrate for ingress and mesh.** The Gateway API (14.5) and service
 meshes (14.6) are elaborations on these fundamentals.

### 3. Mental model

```text
 NAME IP LAYER WHO MAKES IT WORK
 ───── ──────── ─────────────────
 backend → Service ClusterIP → CoreDNS resolves the name
 (DNS) 10.96.0.10 kube-proxy / eBPF DNATs ClusterIP → pod IP
 │
 ▼
 pod IP 10.244.2.7 CNI makes pod IPs routable (flat, no NAT)
 (real):8080 veth pair + bridge (same node)
 overlay/routing (across nodes)

 Debug top-down: name resolves? → Service has endpoints? → pod reachable at its IP?
```

One sentence: **names resolve to Service IPs, Service IPs get rewritten to pod IPs,
and the CNI makes every pod IP directly reachable on a flat network.**

### 4. Minimal implementation

You don't need a diagram to believe the flat network — you can watch a packet get
rewritten. On a kind cluster, deploy a Service and inspect the actual kernel rules:

```bash
kubectl create deployment web --image=nginx --replicas=2
kubectl expose deployment web --port=80

# The Service has a virtual ClusterIP owned by no interface:
kubectl get svc web # e.g. 10.96.0.10

# The real backends behind it (EndpointSlices):
kubectl get endpointslices -l kubernetes.io/service-name=web

# On a node, the DNAT rules that rewrite ClusterIP -> pod IP:
docker exec <kind-node> iptables -t nat -L KUBE-SERVICES -n | grep 10.96.0.10
```

You'll see a rule matching the Service IP that jumps to a chain which DNATs to one of
the pod IPs. That rule *is* the Service. Delete a pod, watch the EndpointSlice and the
rule update. The lab walks this end to end.

### 5. Hands-on lab

Trace a request from a pod, through a Service, to a backing pod on a local cluster —
watching DNS resolve the name, the EndpointSlice list the real pods, and the iptables
DNAT rule do the rewrite. Then break DNS and see the difference between a *name*
problem and a *routing* problem.

➡️ **Start the lab**

### 6. Production considerations

- **DNS is the usual suspect.** At scale, CoreDNS load, `ndots` search-domain
 expansion, and caching cause subtle latency. Monitor CoreDNS and consider NodeLocal
 DNSCache. When debugging, test the name *and* the IP to localize the fault.
- **kube-proxy iptables scaling.** Thousands of Services mean long iptables chains and
 slow rule updates. IPVS or an eBPF dataplane (Cilium) scale far better — a real
 reason platforms adopt Cilium.
- **Pod CIDR sizing.** The pod network has a finite address space; undersizing the pod
 CIDR caps how many pods the cluster can ever run. Plan it at cluster creation.
- **MTU mismatches.** Overlays (VXLAN) add encapsulation overhead; a wrong MTU causes
 mysterious hangs on large payloads while small requests work. A classic gotcha.
- **The flat network is wide open by default.** Requirement #2 (any pod reaches any
 pod) is also a security problem until you add NetworkPolicies.

### 7. Common mistakes

- **Assuming "can't connect" means a routing problem.** — It's usually DNS or a missing
 Service endpoint. *Fix:* debug top-down — resolve the name, check EndpointSlices,
 then test the pod IP.
- **Hardcoding pod IPs.** — Pods are ephemeral; their IPs change on restart. *Fix:*
 always go through a Service (a stable name/ClusterIP).
- **Forgetting the Service has no endpoints.** — A Service with a wrong selector
 matches no pods and silently blackholes traffic. *Fix:* `kubectl get endpointslices`
 — empty means the selector is wrong (you saw this in the Project 1 debugging lab).
- **Expecting NodePort/ClusterIP to be reachable from outside.** — ClusterIP is
 cluster-internal only. *Fix:* use a LoadBalancer, NodePort, or the Gateway API
 (14.5) for external access.
- **Ignoring MTU on overlays.** — Large responses hang while health checks pass. *Fix:*
 set the CNI MTU correctly for your underlay.

### 8. Assessment

**Knowledge checks**

1. State the Kubernetes networking model's core rule about pod-to-pod traffic and NAT.
2. On the same node, what two kernel constructs connect a pod to the node's network?
3. When a pod sends to a Service ClusterIP, what happens to the packet's destination,
 and which component programmed that?
4. What does a **headless** Service resolve to, and when would you use one?
5. Does kube-proxy proxy packets in its default mode? If not, what does it do?

**Concept exercise**

> Explain how one pod reaches another pod on a different node **without using the words
> "Service" or "DNS."** Describe the IP-level path and what keeps it NAT-free.

**Debugging exercise**

> A developer says "my frontend can't reach the backend." Walk through the exact
> top-down sequence of checks you'd run, and what each result would tell you.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** Every pod gets a unique IP and can reach every other pod directly, with **no
 NAT** — a flat network.
- **Q2:** A **veth pair** (one end in the pod's netns as `eth0`, the other in the
 node) plugged into a **bridge** (e.g. `cni0`) that connects all pods on the node.
- **Q3:** The destination IP is **DNAT-rewritten** from the virtual ClusterIP to a real
 pod IP, programmed by **kube-proxy** (iptables/IPVS) or **eBPF** (Cilium).
- **Q4:** A headless Service (`clusterIP: None`) resolves to the **pod IPs** directly;
 used for StatefulSets / when clients need per-pod identity.
- **Q5:** No — in iptables/IPVS mode it doesn't handle packets; it **programs the
 kernel** (iptables/IPVS rules) so the kernel does the DNAT/load-balancing.
- **Debugging:** (1) `nslookup backend` from the frontend pod — DNS working? (2)
 `kubectl get svc backend` — does it exist, right port? (3) `kubectl get
 endpointslices` — any endpoints, or is the selector wrong? (4) `kubectl exec` curl
 the **pod IP** directly — pod healthy/listening? (5) check NetworkPolicies — is
 traffic being denied? Each step localizes the fault to name → Service
 → endpoints → pod → policy.

</details>

### 9. Further reading

- Kubernetes — [Cluster Networking (the model)](https://kubernetes.io/docs/concepts/cluster-administration/networking/)
- Kubernetes — [Service](https://kubernetes.io/docs/concepts/services-networking/service/)
 and [DNS for Services and Pods](https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/)
- Kubernetes — [Virtual IPs and Service Proxies (kube-proxy)](https://kubernetes.io/docs/reference/networking/virtual-ips/)
- [A Guide to the Kubernetes Networking Model (Julia Evans)](https://jvns.ca/blog/2016/12/22/container-networking/)
- [CNI specification](https://github.com/containernetworking/cni/blob/main/SPEC.md)

---


_Previous:_ overview · _Next:_ 14.2 — CNI Plugins →

---

## CNI Plugins

> The flat pod network from doesn't implement itself. A **CNI plugin** is
> the component that actually gives each pod an IP and makes pod IPs routable across
> nodes. Which CNI you pick shapes your cluster's performance, its NetworkPolicy
> capabilities, and how you debug it — so this module explains what the CNI does, how
> pods get IPs (IPAM), how Flannel/Calico/Cilium differ, and how to diagnose the
> classic "pod stuck in ContainerCreating" failure.

**You'll need:**, Docker, and
[kind](https://kind.sigs.k8s.io/).

### Learning objectives

By the end of this module you will be able to:

- Explain what the **CNI specification** requires a plugin to do.
- Describe **IPAM** — how a pod gets its IP, and what happens when the pool runs out.
- Compare **Flannel**, **Calico**, and **Cilium** on the criteria that matter.
- Diagnose a pod stuck in **ContainerCreating** due to a CNI problem.
- Choose a CNI on real requirements, not hype.

---

### 1. Concept

#### What the CNI is

**CNI (Container Network Interface)** is a small, deliberately minimal specification:
when the kubelet creates a pod, it calls a CNI plugin binary and asks it to **set up
the pod's network**; when the pod dies, it asks the plugin to **tear it down**. That's
essentially the whole contract:

```text
 kubelet creates a pod
 │ "ADD: give this pod a network"
 ▼
 CNI plugin (a binary in /opt/cni/bin, configured in /etc/cni/net.d)
 ├─ allocate an IP for the pod (IPAM)
 ├─ create the veth pair + wire the bridge
 └─ set up routes so the pod IP is reachable across nodes
 │ "DEL" on pod teardown → release the IP, remove the plumbing
```

The CNI is what turns the *rule* ("every pod has a routable IP, no NAT") into reality.
Without a working CNI, pods can't get an IP at all — which is exactly the
ContainerCreating failure below.

#### IPAM: how a pod gets its IP

**IPAM (IP Address Management)** is the part of the CNI that hands out pod IPs. The
cluster has a **pod CIDR** (e.g. `10.244.0.0/16`), usually carved into a per-node
slice (e.g. each node gets a `/24`). When a pod is created, IPAM picks a free address
from the local node's slice.

Two consequences platform engineers must plan for:

- **The pod CIDR is a hard ceiling.** If every node gets a `/24` (254 usable IPs), no
 node can ever run more than ~254 pods, and the whole `/16` caps the cluster. Size it
 at cluster creation — you can't easily change it later.
- **IP exhaustion is a real outage.** When IPAM has no free address, new pods stick in
 ContainerCreating. On cloud CNIs that assign *real* VPC IPs (like AWS VPC CNI), you
 can exhaust the *subnet*, not just a pod CIDR.

#### The field: Flannel, Calico, Cilium

Dozens of CNIs exist; three represent the common design points:

```text
 FLANNEL simple overlay (VXLAN). Easy, few features.
 NO NetworkPolicy of its own. Good for learning / simple clusters.

 CALICO L3 routing (often BGP) or overlay. Mature, rich NetworkPolicy.
 Scales well; the long-time default for policy-heavy clusters.

 CILIUM eBPF-based. CNI + L7-aware policy + observability (Hubble) +
 kube-proxy replacement + cluster mesh. Most capable, most to learn.
```

- **Flannel** — a straightforward VXLAN overlay: wrap each pod packet inside a
 node-to-node UDP packet. Minimal and reliable, but it has **no NetworkPolicy
 enforcement** of its own, so you can't do default-deny with Flannel alone.
- **Calico** — can run as a pure L3 router (advertising each node's pod routes via
 **BGP**, no encapsulation overhead) or as an overlay. Rich, mature NetworkPolicy
 support; a very common production choice.
- **Cilium** — uses **eBPF** instead of iptables for the dataplane,
 adding L7-aware policy, deep observability (Hubble), kube-proxy replacement, and
 multi-cluster mesh. The most powerful — and the course's choice
 (Project 1 ADR-002) —
 at the cost of more concepts to learn.

#### Overlay vs native routing

A recurring axis across CNIs:

- **Overlay (encapsulation)** — wrap the pod packet inside a node-to-node packet
 (VXLAN/Geneve). Works on almost any underlying network because the underlay only
 sees node-to-node traffic. Cost: encapsulation overhead and **MTU** care.
- **Native routing** — no wrapping; the underlying network is taught how to reach each
 node's pod CIDR (via BGP or cloud route tables). Faster, but needs an underlay you
 control or a cloud that integrates.

#### Choosing a CNI

Decide on requirements, not fashion:

- **Do you need NetworkPolicy?** (Almost always yes, for isolation —.)
 Then not Flannel-alone.
- **Do you need L7 policy, mTLS, or deep flow observability?** Cilium.
- **What's your scale and underlay?** BGP-native (Calico) or eBPF (Cilium) scale
 better than iptables-heavy setups.
- **What can your team operate?** Cilium is powerful but has the steepest learning
 curve. A platform runs the CNI for everyone — operability counts.
- **Managed clusters often choose for you.** GKE Dataplane V2 *is* Cilium; other
 managed offerings bundle a default. Know what you're getting.

---

### 2. Why it matters for platform engineering

The CNI is a **cluster-wide, hard-to-change foundation**. You pick it once (usually at
cluster creation), and every team's networking, security policy, and observability
inherit its capabilities and limits:

- Choose Flannel and you've quietly ruled out default-deny isolation.
- Choose Cilium and you've unlocked L7 policy and Hubble — but taken on eBPF to
 operate.
- Mis-size the pod CIDR and you cap cluster growth from day one.

It's also the layer behind the most alarming-looking failures (every pod on a node
stuck ContainerCreating), so the platform team must be able to diagnose it fast.

### 3. Mental model

```text
 CNI = the plugin kubelet calls to NETWORK a pod.

 It does three things: and it's chosen on:
 ┌───────────────────────┐ ┌──────────────────────────────┐
 │ 1. IPAM: give an IP │ │ NetworkPolicy support? │
 │ 2. Wire veth + bridge │ │ L7 / observability / mTLS? │
 │ 3. Make it routable │ │ overlay vs native routing? │
 │ (overlay or routes) │ │ scale + operability? │
 └───────────────────────┘ └──────────────────────────────┘

 No CNI working ⇒ no pod IP ⇒ ContainerCreating forever.
```

One sentence: **the CNI gives each pod a routable IP and sets the ceiling on your
cluster's policy, performance, and observability — choose it on requirements, size the
pod CIDR up front.**

### 4. Minimal implementation

You can *see* the CNI's output without touching its internals. The config that tells
kubelet which plugin to use, and the IP it handed a pod, are both inspectable:

```bash
# Which CNI config is active on a node?
docker exec <kind-node> ls /etc/cni/net.d
docker exec <kind-node> cat /etc/cni/net.d/* # the plugin + its IPAM config

# The pod CIDR assigned to each node (IPAM's pool):
kubectl get nodes -o jsonpath='{range.items[*]}{.metadata.name}{"\t"}{.spec.podCIDR}{"\n"}{end}'

# A pod's IP came from its node's slice of that CIDR:
kubectl get pods -o wide
```

kind ships a simple default CNI (kindnet). The lab swaps in Calico or Cilium so you
can watch policy support and the dataplane change under the same workloads.

### 5. Hands-on lab

Compare CNIs hands-on: create a cluster, observe its default CNI and IPAM, then
diagnose a pod stuck in **ContainerCreating** and fix it. You'll see why "no CNI = no
IP = ContainerCreating" and how to read the signal.

➡️ **Start the lab**

### 6. Production considerations

- **Size the pod CIDR for the cluster's lifetime.** It's painful to change later. Model
 max pods/node × nodes and leave headroom.
- **Pick the CNI for the capabilities you'll need in a year**, not just today —
 especially NetworkPolicy and observability. Migrating CNIs on a live cluster is a
 major, risky operation.
- **Know your managed cluster's CNI.** GKE Dataplane V2 is Cilium; EKS defaults to the
 AWS VPC CNI (real VPC IPs → mind subnet exhaustion). The default shapes everything.
- **Monitor IP exhaustion.** Alert before the pool fills; exhaustion presents as new
 pods stuck ContainerCreating with no obvious app cause.
- **Account for overlay MTU.** Set the CNI MTU correctly or suffer intermittent
 large-payload hangs.

### 7. Common mistakes

- **Choosing Flannel then needing NetworkPolicy.** — Flannel alone can't enforce
 policy, so default-deny isolation is impossible. *Fix:* pick a policy-capable CNI
 (Calico/Cilium) from the start, or run a policy plugin alongside.
- **Under-sizing the pod CIDR.** — Caps pods-per-node and total cluster size forever.
 *Fix:* size generously at creation.
- **Blaming the app for ContainerCreating.** — It's almost always CNI/IPAM (no IP, no
 plugin, or a failed node agent), not the container. *Fix:* `kubectl describe pod` →
 read the CNI error in Events.
- **Ignoring subnet exhaustion on cloud CNIs.** — VPC-IP CNIs exhaust real subnets, not
 just a pod CIDR. *Fix:* size subnets and use prefix delegation where available.
- **Treating the CNI as swappable.** — It's a foundational, disruptive change. *Fix:*
 choose deliberately; migrate only with a tested plan.

### 8. Assessment

**Knowledge checks**

1. In one sentence, what does a CNI plugin do when the kubelet creates a pod?
2. What is IPAM, and what symptom appears when its address pool is exhausted?
3. Why can't you implement default-deny NetworkPolicy with Flannel alone?
4. Give the main trade-off between an **overlay** CNI and a **native-routing** CNI.
5. A whole node's new pods are stuck in ContainerCreating. Is the app the likely
 cause? Where do you look first?

**Concept exercise**

> Explain why the choice of CNI constrains a platform's security and observability
> **without naming Flannel, Calico, or Cilium.** Talk in terms of capabilities.

**Trade-off exercise**

> Your team is bootstrapping a new platform cluster. One engineer wants Flannel
> ("simplest"), another wants Cilium ("most powerful"). You need default-deny
> isolation and flow visibility, and the team is small. What do you choose and why,
> and what's the cost of your choice?

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** It sets up the pod's networking — allocates an IP (IPAM), creates the
 veth/bridge plumbing, and makes the pod IP routable — and tears it down on delete.
- **Q2:** IPAM hands out pod IPs from the pod CIDR; exhaustion makes new pods stick in
 **ContainerCreating** with no free address.
- **Q3:** Flannel provides connectivity only — it has no NetworkPolicy enforcement, so
 there's nothing to apply a default-deny rule.
- **Q4:** Overlay works on almost any underlay but adds encapsulation overhead and MTU
 concerns; native routing is faster but needs an underlay/cloud that can route each
 node's pod CIDR.
- **Q5:** No — ContainerCreating at the node level is almost always CNI/IPAM (plugin
 not ready, node agent down, or IPs exhausted). Look at `kubectl describe pod` Events
 and the CNI/agent pods on that node.
- **Trade-off:** Given default-deny + flow visibility are hard requirements, Flannel is
 out (no policy). Cilium meets both (NetworkPolicy + Hubble) and is the course
 default — the cost is the eBPF/Cilium learning curve for a small team; Calico would
 also satisfy policy with a gentler curve but weaker built-in observability. Choose
 Cilium and budget for the learning, or Calico if the team can't absorb eBPF yet.

</details>

### 9. Further reading

- [CNI specification](https://github.com/containernetworking/cni/blob/main/SPEC.md)
- Kubernetes — [Network Plugins](https://kubernetes.io/docs/concepts/extend-kubernetes/compute-storage-net/network-plugins/)
- [Cilium](https://docs.cilium.io/) · [Calico](https://docs.tigera.io/calico/latest/about/) · [Flannel](https://github.com/flannel-io/flannel)
- [GKE Dataplane V2 (Cilium-based)](https://cloud.google.com/kubernetes-engine/docs/concepts/dataplane-v2)
- Project 1 · ADR-002 — Why Cilium

---


_Previous:_ 14.1 — Kubernetes Networking Fundamentals · _Next:_ 14.3 — Network Policies →

---

## Network Policies

> The flat pod network has a dark side: by default, **every pod can talk
> to every other pod**, across every namespace. One compromised workload can reach your
> whole cluster. **NetworkPolicies** close that door — you start from **default-deny**
> and open only the exact flows each workload needs. This is the network half of the
> isolation you built with namespaces, RBAC, and quotas in Projects 1 and 2.

**You'll need:**,
 (a **policy-capable CNI**), Docker, and
[kind](https://kind.sigs.k8s.io/).

### Learning objectives

By the end of this module you will be able to:

- Explain why the Kubernetes default is **allow-all**, and why default-deny matters.
- Write **default-deny** ingress/egress policies and selectively allow traffic.
- Use **pod**, **namespace**, and **IP block** selectors correctly.
- Allow **DNS egress** so default-deny doesn't break name resolution.
- Name the **limits** of vanilla NetworkPolicy (no FQDN, no L7) and what fixes them.

---

### 1. Concept

#### The default is wide open

By default, Kubernetes applies **no** network restrictions: any pod can connect to any
other pod, in any namespace, on any port. Namespaces give you *naming* and RBAC
isolation, but **not network isolation** — `team-a`'s pods can reach `team-b`'s
database unless you say otherwise. For a multi-tenant platform that's a serious gap,
and it's exactly the kind of lateral movement an attacker exploits (the zero-trust
concern from ).

A **NetworkPolicy** is a namespaced resource that selects pods and declares which
traffic is allowed to/from them. The critical behavior:

```text
 A pod with NO NetworkPolicy selecting it → allow all (the default)
 A pod selected by ANY NetworkPolicy → DENY everything not explicitly allowed
 (for the policy types listed)
```

So NetworkPolicies are **additive allow-lists that flip the default to deny** for the
pods they select. You don't write "deny" rules; you write a default-deny policy that
selects everything, then add narrow "allow" policies on top.

#### Default-deny: start closed

The foundational pattern is a policy that selects **all pods** in a namespace and
allows **nothing** — flipping that namespace to deny-by-default for both directions:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
 name: default-deny-all
 namespace: team-a
spec:
 podSelector: {} # select EVERY pod in the namespace
 policyTypes: [Ingress, Egress]
 # no ingress/egress rules => nothing is allowed
```

With that applied, every pod in `team-a` is now isolated — no traffic in or out until
you explicitly allow it. This is "start closed, open only what's needed," the same
guardrail philosophy as Project 1's Pod Security Admission.

#### Selectively allow: the three selectors

You then add policies that allow specific flows. Rules select peers three ways:

- **podSelector** — allow pods with certain labels (e.g. `app: frontend`).
- **namespaceSelector** — allow pods from certain namespaces (e.g. `team: team-a`).
- **ipBlock** — allow a CIDR (for external IPs, with optional `except`).

```yaml
# Allow frontend pods to reach backend pods on 8080 (ingress TO backend)
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
 name: allow-frontend-to-backend
 namespace: team-a
spec:
 podSelector:
 matchLabels:
 app: backend
 policyTypes: [Ingress]
 ingress:
 - from:
 - podSelector:
 matchLabels:
 app: frontend
 ports:
 - protocol: TCP
 port: 8080
```

#### The DNS trap (the #1 default-deny gotcha)

Here's what bites everyone: the moment you apply **default-deny egress**, pods can no
longer reach **CoreDNS**, so *every name lookup fails*. The app looks broken in a
baffling way — it can't resolve `backend`, its database, or anything. You must
explicitly allow egress to kube-dns:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
 name: allow-dns-egress
 namespace: team-a
spec:
 podSelector: {}
 policyTypes: [Egress]
 egress:
 - to:
 - namespaceSelector:
 matchLabels:
 kubernetes.io/metadata.name: kube-system
 podSelector:
 matchLabels:
 k8s-app: kube-dns
 ports:
 - protocol: UDP
 port: 53
 - protocol: TCP
 port: 53
```

> **Remember this one.** "Default-deny egress broke everything" is almost always
> missing DNS egress. It's the networking equivalent of forgetting `runAsNonRoot`.

#### Ingress vs egress

- **Ingress** policies control traffic **coming into** the selected pods.
- **Egress** policies control traffic **leaving** the selected pods.

A policy with `policyTypes: [Ingress, Egress]` but empty rule lists denies both
directions. Many teams start with default-deny **ingress** only (simpler), then add
egress control later for stronger zero-trust posture.

#### The limits of vanilla NetworkPolicy

The built-in `networking.k8s.io` NetworkPolicy is **L3/L4 only** and has real gaps:

- **No FQDN/DNS-name rules.** You can allow a CIDR, not `api.stripe.com` — and external
 API IPs change. (Cilium adds DNS-based egress —.)
- **No L7 awareness.** You can allow port 8080, not "GET /api/* but not DELETE".
 (Cilium/Istio add L7 — /14.6.)
- **Enforced by the CNI, not Kubernetes.** If your CNI doesn't implement
 NetworkPolicy (e.g. Flannel alone), the objects apply but **nothing is enforced** —
 a dangerous false sense of security.

These gaps are precisely why platforms reach for Cilium (next module).

---

### 2. Why it matters for platform engineering

Network isolation is a **platform-owned security control**, and NetworkPolicy is how
you deliver it as a default rather than a hope:

- **Blast-radius containment.** A compromised or buggy workload shouldn't reach the
 whole cluster. Default-deny per namespace contains it — the network complement to
 the RBAC/quota isolation from Projects 1 and 2.
- **Multi-tenancy.** Teams must not accidentally (or maliciously) reach each other's
 workloads. Namespace-scoped default-deny enforces that boundary.
- **Compliance.** "Default-deny with documented, reviewed exceptions" is a baseline
 control in most security frameworks (and the Production Readiness checklist).
- **It's a guardrail you can enforce.** A Kyverno policy can *require*
 that every namespace has a default-deny policy — making isolation structural.

### 3. Mental model

```text
 Default (no policy selects a pod): ALLOW ALL ── wide open, flat network
 │ apply a default-deny policy
 ▼
 Selected by a policy: DENY ALL ── except what you allow-list
 │ add narrow allow policies
 ▼
 team-a namespace:
 default-deny (ingress+egress) ← start closed
 allow-dns-egress ← or DNS breaks EVERYTHING
 allow-frontend → backend:8080 ← open only the real flows
 allow-egress to the database CIDR ← and nothing else leaves

 You never write "deny". You write default-deny + explicit allows.
```

One sentence: **NetworkPolicies turn the open-by-default pod network into
deny-by-default-with-allow-lists — and you must allow DNS or everything breaks.**

### 4. Minimal implementation

The smallest meaningful demonstration is two pods and one policy. Prove the flat
network is open, then close it:

```bash
# Before any policy: frontend can reach backend (open by default)
kubectl exec frontend -- curl -s -m 3 http://backend && echo " <- open"

# Apply default-deny ingress on backend
kubectl apply -f default-deny.yaml

# Now it's blocked (times out) — the flat network is closed for backend
kubectl exec frontend -- curl -s -m 3 http://backend || echo " <- denied"

# Allow exactly frontend -> backend, and it works again — but ONLY that flow
kubectl apply -f allow-frontend.yaml
kubectl exec frontend -- curl -s -m 3 http://backend && echo " <- allowed"
```

Three commands take you from open → closed → precisely-open. The lab does this fully,
including the DNS trap, which you'll trigger and fix on purpose.

### 5. Hands-on lab

Lock a namespace to **default-deny**, watch it break (including DNS), then open exactly
the flows that are needed — frontend→backend plus DNS egress — and verify that
everything else stays blocked.

➡️ **Start the lab**

### 6. Production considerations

- **Default-deny every tenant namespace, by policy.** Use Kyverno to
 *require* a default-deny NetworkPolicy in every namespace, so a new team is isolated
 automatically — not when someone remembers.
- **Always allow DNS egress** in your default-deny baseline, or you'll ship an outage.
 Bake it into the namespace template.
- **Confirm the CNI actually enforces policy.** Applying NetworkPolicy objects on a
 non-enforcing CNI gives false security. Test with a real denied connection.
- **Egress control needs FQDN in practice.** Vanilla policy only does CIDRs; external
 endpoints change IPs. Plan for Cilium DNS-based egress for real
 "allow only these external APIs" rules.
- **Test policies as code.** Policy changes can silently cut traffic. Validate in CI
 (a connectivity test) before rollout; treat them like any other production change.
- **Observe denials.** Without flow visibility (Hubble, ), a wrong policy is
 an invisible outage. Log/monitor dropped flows.

### 7. Common mistakes

- **Default-deny egress without allowing DNS.** — Every name lookup fails and the app
 looks mysteriously broken. *Fix:* always include the kube-dns egress allow.
- **Assuming namespaces isolate network traffic.** — They don't; only NetworkPolicy
 does. *Fix:* add default-deny per namespace.
- **Applying policy on a non-enforcing CNI (e.g. Flannel).** — Objects exist, nothing
 is enforced. *Fix:* use a policy-capable CNI and verify a real denial.
- **Writing broad allows that defeat the purpose.** — `from: [{}]` allows everything.
 *Fix:* select specific pods/namespaces and ports.
- **Forgetting policies are namespaced.** — A policy in `team-a` doesn't protect
 `team-b`. *Fix:* apply the baseline to every namespace (templated/enforced).
- **Confusing "no ingress rules" with "allow all ingress".** — An Ingress-type policy
 with no rules **denies** all ingress. *Fix:* understand selected ⇒ deny-by-default.

### 8. Assessment

**Knowledge checks**

1. What happens to a pod's traffic the moment *any* NetworkPolicy selects it?
2. Write (in words) the two policies you need so `team-a` is default-deny but its pods
 can still resolve DNS.
3. What are the three ways a NetworkPolicy rule can select its peers?
4. Name two things vanilla NetworkPolicy **cannot** express.
5. You applied a default-deny policy but nothing is actually blocked. What's the most
 likely cause?

**Concept exercise**

> Explain "default-deny with allow-lists" to a developer **without using the words
> "NetworkPolicy" or "firewall."** Use the idea of a guest list.

**Debugging exercise**

> A team enables default-deny egress and immediately every service in the namespace
> starts failing with timeouts on *all* outbound calls — even to services that should
> be allowed. What's almost certainly wrong, and what's the one policy you'd check
> first?

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** For the `policyTypes` it lists, the pod flips to **deny-by-default** —
 everything not explicitly allowed by some policy is dropped.
- **Q2:** (1) a default-deny policy selecting all pods for Ingress+Egress; (2) an
 egress-allow policy permitting UDP/TCP 53 to the kube-dns pods in kube-system.
- **Q3:** `podSelector` (by pod labels), `namespaceSelector` (by namespace labels),
 and `ipBlock` (a CIDR).
- **Q4:** Any two of: FQDN/DNS-name rules, L7 (HTTP method/path) rules — it's L3/L4
 only.
- **Q5:** The CNI doesn't enforce NetworkPolicy (e.g. Flannel alone) — the objects
 apply but nothing acts on them.
- **Debugging:** Default-deny egress blocked DNS, so names don't resolve and *all*
 outbound calls fail (even allowed ones, because they can't resolve their target).
 Check for / add the **kube-dns egress allow** policy first.

</details>

### 9. Further reading

- Kubernetes — [Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- Kubernetes — [Declare Network Policy (walkthrough)](https://kubernetes.io/docs/tasks/administer-cluster/declare-network-policy/)
- [kubernetes-network-policy-recipes (ahmetb)](https://github.com/ahmetb/kubernetes-network-policy-recipes) — practical policy examples
- [Cilium Network Policies (L7 + DNS)](https://docs.cilium.io/en/stable/security/policy/) — what fixes the gaps
- · Zero Trust for Platforms

---


_Previous:_ 14.2 — CNI Plugins · _Next:_ 14.4 — Cilium and eBPF →

---

## Cilium and eBPF

> Everything so far has pointed here. Vanilla NetworkPolicy can't do FQDN or L7; kube-
> proxy's iptables don't scale; and you've had no way to *see* network flows. **Cilium**
> — built on **eBPF** — answers all three: it's a CNI, an L7-aware policy engine,
> kube-proxy replacement, and (via **Hubble**) a network-observability tool, all in
> one. This is the CNI the course chose in
> Project 1's ADR-002.

**You'll need:**, Docker, and
[kind](https://kind.sigs.k8s.io/). The lab installs Cilium locally.

### Learning objectives

By the end of this module you will be able to:

- Explain what **eBPF** is and why it's faster and safer than kernel modules.
- Describe what Cilium provides: CNI, L7 policy, kube-proxy replacement, observability.
- Use **Hubble** to see allowed and dropped network flows.
- Write a **Cilium L7** policy (e.g. allow `GET /api` but not `DELETE`).
- Explain **DNS-based egress** and when Cilium is worth its complexity.

---

### 1. Concept

For the datapath flow, see Cilium eBPF path.

#### eBPF in one paragraph

**eBPF** (extended Berkeley Packet Filter) lets you run small, sandboxed programs
**inside the Linux kernel** — attached to hooks like "a packet arrived" or "a syscall
happened" — **without writing a kernel module or rebooting**. The kernel verifies each
program is safe (bounded loops, no bad memory access) before running it, so a bug
can't crash the kernel. For networking, this means packet processing logic that runs at
kernel speed, updatable at runtime:

```text
 Traditional (iptables): a long, linear chain of rules the kernel walks per packet
 — slow to evaluate and update at thousands of Services.

 eBPF (Cilium): a verified program at the network hook, using hash-map
 lookups — O(1)-ish, updated live, no rule-chain walk.
```

eBPF is also the foundation of Falco's runtime security — same kernel
technology, different hook. It's one of the most important shifts in Linux
infrastructure of the last decade.

#### What Cilium is (four tools in one)

Cilium uses eBPF to deliver, in a single component, what used to take several:

```text
 ┌─────────────────────── Cilium (eBPF dataplane) ───────────────────────┐
 │ 1. CNI pod networking (the flat network, ) │
 │ 2. NetworkPolicy++ L3/L4 AND L7 (HTTP/gRPC/DNS) + FQDN egress │
 │ 3. kube-proxy replace Service load-balancing in eBPF (no iptables) │
 │ 4. Observability Hubble: every flow, allowed or dropped, with id │
 └────────────────────────────────────────────────────────────────────────┘
```

- **CNI** — it implements the flat pod network, replacing kindnet/Flannel/
 Calico as the dataplane.
- **Policy beyond L4** — standard NetworkPolicy **plus** CiliumNetworkPolicy, which adds
 **L7** (HTTP methods/paths, gRPC, Kafka) and **DNS/FQDN** egress — the exact gaps
 ended on.
- **kube-proxy replacement** — Service DNAT done in eBPF, which scales far
 better than iptables chains at high Service counts.
- **Identity-based security** — Cilium assigns a security **identity** to each workload
 (from its labels) and enforces policy on identity, not IP — the basis for zero trust
 and mTLS.

#### Hubble: finally, you can see the network

The single biggest day-to-day win is **Hubble** — Cilium's observability layer. Because
eBPF sits in the datapath, Hubble sees **every flow**: source and destination identity,
port, verdict (FORWARDED or DROPPED), and even L7 details (the HTTP method and path).

```bash
hubble observe --namespace team-a --follow # watch live flows
hubble observe --verdict DROPPED --follow # see exactly what policy dropped
```

This turns NetworkPolicy debugging from guesswork ("is it blocked? I can't tell") into
observation ("that DROPPED flow is attacker→backend, denied by policy X"). It's the
missing piece from 's "a wrong policy is an invisible outage."

#### L7 and DNS policy: closing the gaps

A **CiliumNetworkPolicy** can express what vanilla NetworkPolicy cannot:

```yaml
# Allow frontend -> backend, but ONLY HTTP GET /api/* (not POST/DELETE, not other paths)
apiVersion: cilium.io/v2
kind: CiliumNetworkPolicy
metadata:
 name: allow-get-api
 namespace: team-a
spec:
 endpointSelector:
 matchLabels:
 app: backend
 ingress:
 - fromEndpoints:
 - matchLabels:
 app: frontend
 toPorts:
 - ports:
 - port: "8080"
 protocol: TCP
 rules:
 http:
 - method: "GET"
 path: "/api/.*"
```

And **DNS-based egress** — "allow only `api.github.com`" — which is impossible with
CIDR-only vanilla policy:

```yaml
# (sketch) allow egress only to a specific FQDN
egress:
 - toFQDNs:
 - matchName: "api.github.com"
 toPorts:
 - ports:
 - port: "443"
 protocol: TCP
```

These are the rules real platforms need (allow this API, this HTTP verb) and the reason
teams adopt Cilium despite its learning curve.

#### When Cilium is worth it

Cilium is powerful but adds real conceptual surface (eBPF, identities, its own CRDs). It
earns its place when you need:

- **L7 or FQDN policy** (allow specific APIs/verbs) — not expressible otherwise.
- **Flow observability** (Hubble) — invaluable for multi-tenant platforms.
- **Scale** — eBPF service LB beats iptables at high Service counts.
- **A path to mTLS / zero trust** and **multi-cluster** (Cluster Mesh).

For a tiny single-tenant cluster, it may be more than you need — but for a *platform*
serving many teams, these are table stakes, which is why it's the course default.

---

### 2. Why it matters for platform engineering

Cilium is a platform **force multiplier**: one component replaces a CNI, a policy
engine, kube-proxy, and a network-observability tool, with capabilities none of the
individual pieces had:

- **It makes zero trust achievable.** Identity-based, L7-aware policy + mTLS is the
 concrete mechanism behind 's principles.
- **Hubble turns network incidents from invisible to obvious**, which directly reduces
 MTTR for the whole cluster — a platform-wide DX and reliability win.
- **It's the dataplane managed clusters are standardizing on** (GKE Dataplane V2 is
 Cilium), so understanding it is increasingly non-optional.

The trade-off — operability and learning curve — is exactly the kind of build-vs-adopt,
capability-vs-complexity decision a platform team must own (and document, as Project 1
did in ADR-002).

### 3. Mental model

```text
 eBPF = safe, verified programs in the kernel, at the network hook, updated live.

 Cilium rides eBPF to be FOUR things at once:
 CNI + L7/FQDN policy + kube-proxy replacement + Hubble observability
 │ │ │ │
 flat network allow GET /api, Service LB without SEE every flow, only api.github.com iptables chains allowed or DROPPED

 Identity (from labels), not IP, is what policy is enforced on → zero trust.
```

One sentence: **Cilium uses eBPF to be your CNI, your L7-aware policy engine, your
kube-proxy, and your network microscope — enforcing on workload identity, not IP.**

### 4. Minimal implementation

The quickest way to feel the difference is Hubble. On a Cilium cluster, you *watch* the
policy decisions you made in instead of inferring them:

```bash
# Apply a default-deny, then observe the drops in real time
kubectl apply -f default-deny.yaml
hubble observe --namespace team-a --verdict DROPPED --follow
# Each blocked connection shows: source identity -> dest identity: DROPPED (Policy denied)
```

Where left you curling and guessing, Hubble shows the verdict and the
reason. The lab installs Cilium + Hubble and has you watch an L7 policy allow a GET and
drop a DELETE — a decision vanilla NetworkPolicy literally cannot make.

### 5. Hands-on lab

Install Cilium with Hubble on a local cluster, watch allowed and dropped flows in real
time, then apply an **L7** CiliumNetworkPolicy that allows `GET /` but blocks other
HTTP methods — and see Hubble report each verdict with the HTTP detail.

➡️ **Start the lab**

### 6. Production considerations

- **Operability is the real cost.** eBPF, Cilium identities, and its CRDs are a genuine
 learning curve; the platform team operates this for everyone. Budget training and
 runbooks (ADR-002 named this trade-off).
- **Kernel version matters.** eBPF features depend on the kernel; verify your nodes'
 kernels support the Cilium features you want (L7, kube-proxy replacement).
- **L7 policy adds a proxy hop.** L7 enforcement routes through an Envoy proxy in
 Cilium — slightly more latency and resource use than pure L3/L4. Use L7 where it
 earns its keep, not everywhere.
- **Retain Hubble flow data.** Hubble's live view is great, but for incident
 forensics, export flows to a backend (and mind the volume/cost — a FinOps concern).
- **On managed clusters, know what you get.** GKE Dataplane V2 is Cilium but
 managed/limited; self-installed Cilium gives more control but you own upgrades.
- **FQDN policy depends on DNS visibility.** Cilium learns FQDN→IP by watching DNS; make
 sure DNS egress goes through Cilium so `toFQDNs` rules work.

### 7. Common mistakes

- **Adopting Cilium for a problem you don't have.** — On a tiny single-tenant cluster,
 the complexity may exceed the benefit. *Fix:* adopt it for L7/FQDN/observability/scale
 needs, not hype.
- **Expecting L7 rules on a kernel that can't.** — Features silently unavailable on old
 kernels. *Fix:* check kernel/Cilium compatibility before relying on L7.
- **Ignoring Hubble.** — Teams install Cilium and still debug blind. *Fix:* enable
 Hubble; it's the biggest operational win.
- **Mixing vanilla and Cilium policies without understanding precedence.** — Confusing
 allow/deny interactions. *Fix:* standardize on CiliumNetworkPolicy where you need L7,
 and learn how they compose.
- **FQDN egress without DNS going through Cilium.** — `toFQDNs` rules don't match
 because Cilium never saw the lookup. *Fix:* route DNS through Cilium.

### 8. Assessment

**Knowledge checks**

1. What is eBPF, and why is it safer than loading a kernel module?
2. Name the four things Cilium provides in one component.
3. What does Hubble let you see that vanilla NetworkPolicy debugging cannot?
4. Give one policy rule Cilium can express that vanilla NetworkPolicy cannot.
5. Cilium enforces policy on *identity* rather than IP. Why does that matter for a
 dynamic, multi-tenant cluster?

**Concept exercise**

> Explain the advantage of Cilium's eBPF dataplane over iptables **without using the
> word "eBPF."** Focus on how each decides what to do with a packet and why one scales.

**Trade-off exercise**

> A platform team runs 40 teams on one cluster and keeps having "is this connection
> blocked or not?" debates and slow Service load-balancing at high Service counts. They
> currently use a simple CNI. Make the case for (or against) migrating to Cilium, and
> name the main risk.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** eBPF runs sandboxed, kernel-**verified** programs at kernel hooks without a
 module or reboot; the verifier rejects unsafe programs, so a bug can't crash the
 kernel (unlike a buggy module).
- **Q2:** CNI, L7/FQDN-aware network policy, kube-proxy replacement, and observability
 (Hubble).
- **Q3:** Every flow with its verdict (FORWARDED/DROPPED) and the reason, by workload
 identity — turning invisible policy decisions into observable ones.
- **Q4:** L7 rules (e.g. allow `GET /api/*` but not `DELETE`) or DNS/FQDN egress (allow
 `api.github.com`) — neither is expressible in vanilla NetworkPolicy.
- **Q5:** Pod IPs churn constantly; enforcing on identity (derived from stable labels)
 means policy stays correct as pods are rescheduled and IPs change — essential for
 zero trust.
- **Trade-off:** Strong case *for*: Hubble ends the "blocked or not?" debates (flow
 visibility), and eBPF service LB fixes the iptables-at-scale slowness; it also opens
 L7 policy and a zero-trust path. Main risk: operability/learning curve and a
 disruptive CNI migration on a live multi-tenant cluster — plan and test it carefully
 (ADR-002's exact trade-off).

</details>

### 9. Further reading

- [Cilium documentation](https://docs.cilium.io/) and [Hubble](https://docs.cilium.io/en/stable/observability/hubble/)
- [CiliumNetworkPolicy (L7 + DNS)](https://docs.cilium.io/en/stable/security/policy/)
- [eBPF.io — what is eBPF?](https://ebpf.io/what-is-ebpf/)
- [GKE Dataplane V2](https://cloud.google.com/kubernetes-engine/docs/concepts/dataplane-v2)
- Project 1 · ADR-002 — Why Cilium

---


_Previous:_ 14.3 — Network Policies · _Next:_ 14.5 — Kubernetes Gateway API →

---

## Kubernetes Gateway API

> How does external traffic get *into* the cluster, safely, when the platform team owns
> the entry point but app teams own their own routes? The old **Ingress** API muddled
> those roles and bolted vendor features onto annotations. The **Gateway API** — its
> official successor — fixes this with clean **role separation**: the platform owns the
> `Gateway`, developers own their `HTTPRoute`s, and richer routing (traffic splitting,
> header matching) is first-class, not an annotation hack.

**You'll need:**,
 · Services and Networking,
Docker, and [kind](https://kind.sigs.k8s.io/).

### Learning objectives

By the end of this module you will be able to:

- Explain why the Gateway API replaces Ingress, and the problems it solves.
- Describe the **role-separated** resources: GatewayClass, Gateway, HTTPRoute.
- Write an **HTTPRoute** with path/header matching and **weighted traffic splitting**.
- Explain how the Gateway API enables safe **multi-tenant** ingress.
- Name reference implementations and where TLS is terminated.

---

### 1. Concept

The role split in the Gateway API is shown in Gateway API roles.

#### Why Ingress wasn't enough

The original **Ingress** API was a single resource that tried to be everything: it
described host/path routing, but anything beyond basic HTTP (TLS options, traffic
splitting, header rules, timeouts) was shoved into **controller-specific
annotations**. The results were painful:

- **No portability** — an nginx-ingress annotation means nothing to GKE's controller.
 Switching ingress controllers meant rewriting everything.
- **No role separation** — one Ingress object mixed concerns the *platform* owns (the
 load balancer, TLS certs, the public entry point) with concerns *developers* own
 (which path routes to my service). Everyone edited the same resource.
- **Limited expressiveness** — canary splits, header-based routing, and non-HTTP
 protocols were awkward or impossible in standard Ingress.

#### The Gateway API: roles as resources

The **Gateway API** (the official Kubernetes successor to Ingress) redesigns ingress
around **who owns what**. It splits one monolith into a layered set of resources, each
owned by a different role:

```text
 ROLE RESOURCE OWNS
 ──── ──────── ────
 Infrastructure → GatewayClass what KIND of gateway exists (the impl),
 provider e.g. "gke-l7-global" or "cilium"

 Platform team → Gateway the actual entry point: ports, listeners,
 hostnames, TLS certs. One shared front door.

 Developer team → HTTPRoute "route /api/my-app to my Service" — in the
 TEAM's own namespace, no platform ticket.
```

This is the IDP **role separation** made concrete at the network layer: the platform
team runs the Gateway (the load balancer, the TLS, the public IP) as a service;
developers attach their own `HTTPRoute`s to it from their namespaces, self-service,
without touching shared infrastructure. It's the networking expression of the
golden-path, X-as-a-Service model from.

#### HTTPRoute: expressive, developer-owned routing

An `HTTPRoute` attaches to a `Gateway` (via `parentRefs`) and declares how matching
requests reach backends. It natively supports what Ingress couldn't:

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
 name: my-app
 namespace: team-a
spec:
 parentRefs:
 - name: platform-gateway
 namespace: platform-system
 rules:
 - matches:
 - path:
 type: PathPrefix
 value: /api/my-app
 backendRefs:
 - name: my-app
 port: 8080
```

- **Path and header matching** — route by path prefix, exact path, method, or headers.
- **Weighted traffic splitting** — send 90% to `v1` and 10% to `v2` for a **canary**,
 just by setting `weight` on multiple `backendRefs`. This is progressive delivery
 without a mesh.
- **Cross-namespace with guardrails** — a Gateway can allow routes only from specific
 namespaces (via `allowedRoutes`), so the platform controls who may attach.

#### Traffic splitting for canary releases

Weighted `backendRefs` make canary deployments a native, declarative operation:

```yaml
 rules:
 - backendRefs:
 - name: my-app-v1
 port: 8080
 weight: 90
 - name: my-app-v2
 port: 8080
 weight: 10
```

Ninety percent of traffic goes to v1, ten percent to the new v2 — shift the weights to
roll forward, or zero out v2 to roll back. (Full automated progressive delivery adds
Argo Rollouts/Flagger — GitOps maturity Level 4 from but the *mechanism*
is right here in the Gateway API.)

#### TLS, protocols, and implementations

- **TLS** — the Gateway terminates TLS at its listeners (or passes it through for
 end-to-end encryption). Certs are a platform concern, configured once on the Gateway.
- **Beyond HTTP** — `TCPRoute` and `TLSRoute` handle non-HTTP traffic.
- **Reference implementations** — the API is a spec; a controller implements it:
 **GKE Gateway**, **Cilium Gateway**, **Envoy Gateway**, **Istio**, NGINX Gateway
 Fabric, and others. You write portable Gateway/HTTPRoute resources; the controller
 realizes them. Switching implementations no longer means rewriting annotations.

---

### 2. Why it matters for platform engineering

Ingress is where "the platform owns the front door, teams own their routes" either
works or turns into a ticket queue. The Gateway API makes the good version structural:

- **Self-service ingress.** Developers publish routes from their own namespaces without
 a platform ticket — the exact friction reduction is about — while the
 platform keeps control of the shared Gateway, TLS, and which namespaces may attach.
- **Portability.** Gateway/HTTPRoute are standard resources; you can change the
 underlying controller (even move clouds) without rewriting every team's routing.
- **Progressive delivery built in.** Weighted splits give canary releases natively,
 reducing deploy risk across every team.
- **Clean multi-tenancy.** `allowedRoutes` and namespaced HTTPRoutes enforce who can
 expose what — a governance control the old Ingress lacked.

### 3. Mental model

```text
 Internet
 │
 ▼
 Gateway (platform-system) ← PLATFORM owns: LB, port 443, TLS, who may attach
 │ listeners, certs
 ├── HTTPRoute (team-a) ← DEVELOPERS own: /api/my-app -> their Service
 │ path/header match, weighted canary (90/10)
 └── HTTPRoute (team-b) ← each team, in its own namespace, self-service

 GatewayClass ← the IMPLEMENTATION (GKE / Cilium / Envoy) behind it all

 One front door, many self-service routes, portable across controllers.
```

One sentence: **the Gateway API splits ingress by role — platform owns the Gateway,
developers own their HTTPRoutes — with native path/header matching and weighted canary
splits, portable across implementations.**

### 4. Minimal implementation

The smallest demonstration needs a Gateway controller, a Gateway, and one HTTPRoute.
On a local cluster you install a controller (the lab uses NGINX Gateway Fabric or
Envoy Gateway), then:

```bash
# Platform team: one shared Gateway (the front door)
kubectl apply -f gateway.yaml

# Developer team: attach a route from their own namespace
kubectl apply -f httproute.yaml

# Reach the service through the Gateway
curl -H "Host: demo.example.com" http://<gateway-address>/
```

Two resources, two owners, one front door. The lab extends this to a **90/10 canary
split** between two versions — watching requests distribute across them — which is the
capability that most clearly separates the Gateway API from Ingress.

### 5. Hands-on lab

Install a Gateway controller on a local cluster, stand up a shared **Gateway**
(platform-owned), attach **HTTPRoutes** from an app namespace, and configure a **90/10
weighted canary split** between two versions — watching traffic distribute.

➡️ **Start the lab**

### 6. Production considerations

- **The Gateway is the public front door — treat it as tier-1.** Its availability, TLS
 certs, and capacity affect every exposed service. Give it SLOs and monitoring.
- **Govern who may attach.** Use `allowedRoutes` (by namespace label) so only sanctioned
 teams expose services through the shared Gateway; pair with policy (Kyverno).
- **Automate TLS.** Integrate cert-manager (or the cloud's managed certs) so certificate
 issuance/rotation isn't a manual, expiry-prone task.
- **Pick the implementation deliberately.** GKE Gateway (managed), Cilium Gateway
 (unifies with your CNI — ), Envoy Gateway (portable). Capabilities and
 operational models differ.
- **Plan the Ingress → Gateway migration.** Many clusters still run Ingress; migrating
 is a real project. Run both during transition and move teams incrementally.
- **Weighted splits are a mechanism, not full progressive delivery.** For automated,
 metric-driven rollouts add Argo Rollouts/Flagger.

### 7. Common mistakes

- **Recreating the Ingress monolith.** — Having the platform team hand-edit every team's
 routes defeats the point. *Fix:* let teams own HTTPRoutes in their namespaces; govern
 with `allowedRoutes`.
- **No namespace governance on attachment.** — Any namespace attaching to the shared
 Gateway is a security gap. *Fix:* restrict `allowedRoutes`.
- **Manual TLS.** — Certs expire and cause outages. *Fix:* automate with cert-manager/
 managed certs.
- **Assuming all implementations are equal.** — Feature and behavior gaps between GKE/
 Cilium/Envoy gateways. *Fix:* validate your required features on the chosen
 controller.
- **Treating weighted split as safe-by-itself.** — A canary with no metrics is just
 slower breakage. *Fix:* watch error rate/latency on the new version (Project 3) and
 automate rollback.

### 8. Assessment

**Knowledge checks**

1. Name the three core Gateway API resources and which role owns each.
2. What problem with Ingress annotations does the Gateway API solve?
3. How do you express a 90/10 canary split in an HTTPRoute?
4. How does the platform control which namespaces may attach routes to a shared
 Gateway?
5. Where is TLS typically terminated in a Gateway API setup?

**Concept exercise**

> Explain how the Gateway API lets developers publish their own external routes without
> the platform team becoming a bottleneck — **without using the words "Gateway" or
> "HTTPRoute."** Describe it in terms of ownership.

**Design exercise**

> A platform serves 30 teams, each needing to expose HTTP services on the company
> domain, with TLS, and the ability to canary new versions. Sketch how you'd use the
> Gateway API: what the platform team owns, what teams own, and how you'd keep it safe.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** GatewayClass (infrastructure provider — the implementation), Gateway
 (platform team — the entry point/LB/TLS), HTTPRoute (developer team — routing rules).
- **Q2:** Ingress crammed everything into controller-specific annotations
 (non-portable, limited); the Gateway API makes routing, splitting, and roles
 first-class, portable resources.
- **Q3:** Multiple `backendRefs` with `weight` values (e.g. v1 weight 90, v2 weight 10)
 in one rule.
- **Q4:** The Gateway's `allowedRoutes` restricts which namespaces (by label) may attach
 routes.
- **Q5:** At the Gateway's listeners (terminate there, or pass through for end-to-end
 TLS) — a platform-owned concern configured once on the Gateway.
- **Design:** Platform team owns one (or a few) shared Gateway(s) in `platform-system`
 with TLS (cert-manager) and `allowedRoutes` limited to team namespaces; each team
 owns HTTPRoutes in its namespace for its paths, using weighted backendRefs to canary;
 governance via Kyverno + `allowedRoutes`, and observability on the Gateway and each
 service (Project 3).

</details>

### 9. Further reading

- [Kubernetes Gateway API](https://gateway-api.sigs.k8s.io/) and [API concepts](https://gateway-api.sigs.k8s.io/concepts/api-overview/)
- [Gateway API — traffic splitting](https://gateway-api.sigs.k8s.io/guides/traffic-splitting/)
- [GKE Gateway controller](https://cloud.google.com/kubernetes-engine/docs/concepts/gateway-api) · [Cilium Gateway API](https://docs.cilium.io/en/stable/network/servicemesh/gateway-api/gateway-api/) · [Envoy Gateway](https://gateway.envoyproxy.io/)
- [Ingress vs Gateway API — migration](https://gateway-api.sigs.k8s.io/guides/migrating-from-ingress/)
- [cert-manager](https://cert-manager.io/) for automated TLS

---


_Previous:_ 14.4 — Cilium and eBPF · _Next:_ 14.6 — Service Mesh Reference →

---

## Service Mesh Reference

> A **service mesh** promises mTLS everywhere, rich traffic management, and per-call
> observability — without changing application code. It can also add a sidecar to every
> pod, a control plane to operate, and a pile of new CRDs. This reference module
> explains what a mesh actually solves, how Istio works (sidecar and the newer ambient
> mode), how it compares to Cilium, and — most importantly — **when a mesh adds more
> complexity than value.**

**You'll need:** · Cilium and eBPF and
 · Zero Trust.

### Learning objectives

By the end of this module you will be able to:

- State the three problems a service mesh solves: **mTLS**, **traffic management**,
 **observability**.
- Describe Istio's architecture — the control plane and the **sidecar** vs **ambient**
 dataplanes.
- Compare a mesh (Istio) with a CNI-based approach (Cilium) and know when to pick which.
- Judge **when a mesh is not worth it**, and what lighter options cover the same needs.

---

### 1. Concept

#### What a mesh actually solves

A service mesh adds a dedicated infrastructure layer for **service-to-service**
communication. It intercepts traffic between your services (via a proxy) and provides
three families of capability, **without application code changes**:

```text
 1. SECURITY automatic mTLS between every service: encrypted + mutually
 authenticated, with certificates managed for you (SPIFFE ids).

 2. TRAFFIC MGMT retries, timeouts, circuit breaking, canary/traffic splitting,
 fault injection — declaratively, per route.

 3. OBSERVABILITY golden-signal metrics, distributed traces, and access logs for
 every call, uniformly, without instrumenting each app.
```

The trick is the **proxy**: the mesh puts a proxy in the request path for every
workload, and that proxy — configured centrally — does the mTLS, the retries, the
metrics. Your app just makes a normal HTTP call; the mesh handles the rest.

#### Istio architecture: control plane + dataplane

**Istio** is the most widely used mesh. Two parts:

- **Control plane (`istiod`)** — the brain. It configures the proxies, issues and
 rotates certificates (workload identity via **SPIFFE**), and distributes your traffic
 policies.
- **Dataplane (the proxies)** — the muscle, where traffic actually flows. Istio has two
 models here:

```text
 SIDECAR model (classic):
 every pod gets an Envoy proxy container injected next to the app.
 + mature, full L7 features per pod
 - a proxy per pod: real CPU/memory overhead and lifecycle complexity

 AMBIENT model (newer):
 NO sidecars. A per-node "ztunnel" handles mTLS + L4; optional "waypoint"
 proxies handle L7 only where needed.
 + much lower overhead, simpler app pods
 - newer; you add L7 proxies only for services that need them
```

Ambient mesh exists precisely because "a sidecar in every pod" was the biggest cost of
the classic model. It splits the cheap part (L4 + mTLS, done per node) from the
expensive part (L7, done only where needed).

#### Traffic management primitives

Istio exposes traffic control through resources like:

- **VirtualService** — routing rules: match requests and send them to subsets, with
 retries, timeouts, fault injection.
- **DestinationRule** — defines subsets (e.g. `v1`/`v2`) and policies like connection
 pools and **circuit breaking**.

Together these enable canary releases, A/B testing, resilience patterns (retry/
timeout/circuit-break), and fault injection for chaos testing — all declaratively.

#### Istio vs Cilium: overlapping, not identical

You already have a powerful network layer in **Cilium**. Where do they
overlap, and where do they differ?

```text
 Cilium (eBPF) Istio (mesh)
 ───────────── ─────────────── ─────────────
 dataplane eBPF (kernel), fast Envoy proxies (sidecar/ambient)
 mTLS yes (SPIFFE, eBPF) yes (SPIFFE), very mature
 L7 policy HTTP/gRPC/Kafka/DNS rich L7 routing + resilience
 traffic mgmt basic rich (retry/timeout/circuit-break,
 fault injection, mirroring)
 observability Hubble (flows) per-call metrics/traces/logs
 overhead low (no sidecars) sidecar: high; ambient: moderate
```

- **Cilium** is **networking-first**: it's your CNI and does identity-based policy,
 mTLS, and L7 rules in the kernel with low overhead and great flow visibility — but
 lighter traffic-management features.
- **Istio** is **traffic-management-first**: the richest routing, resilience, and
 per-call telemetry — at the cost of running Envoy proxies and a control plane.

The rule of thumb: **Cilium for networking-first platforms; Istio when you need rich
traffic management** (sophisticated canaries, circuit breaking, fault injection,
mirroring) that goes beyond what your CNI offers.

#### When a mesh is NOT worth it

This is the most important section. A mesh is a **big** operational commitment —
another control plane, proxies in the datapath, new CRDs, upgrade cycles, and a new
failure mode for every service. Don't adopt one until you can name the problem it
solves *for you*. You probably **don't** need a mesh if:

- You have a handful of services and simple routing — the Gateway API
 already covers ingress and basic splitting.
- Your mTLS need is met by **Cilium** or you don't yet require encryption
 in transit between services.
- Your observability is handled by **OpenTelemetry instrumentation** (Project 3) — apps
 emitting their own traces/metrics can be richer than mesh-inferred telemetry.
- Nobody on the team can operate Envoy and `istiod` confidently.

You **do** have a strong case when: you need automatic mTLS across *many* services
without instrumenting them, sophisticated traffic management (progressive delivery,
circuit breaking, mirroring, fault injection), and uniform L7 telemetry across a large
fleet — and you have the operational maturity to run it.

---

### 2. Why it matters for platform engineering

"Should we run a service mesh?" is one of the highest-stakes architecture decisions a
platform team makes — and one of the most over-adopted technologies in the industry.
Getting it right matters because:

- **A mesh you don't need is pure cost** — overhead on every pod, a control plane to
 operate, and complexity every engineer must learn, with little benefit. The course's
 anti-tool-sprawl principle applies hard here.
- **A mesh you *do* need, done well, is transformative** — org-wide mTLS, resilience,
 and observability as a platform capability teams get for free.
- **The alternatives are real.** Much of a mesh's value is now available more cheaply
 via Cilium (mTLS, L7, Hubble), the Gateway API (ingress, splitting), and OTel
 (telemetry). A platform engineer must know what each covers before reaching for the
 heaviest tool.

This module is deliberately a **reference and a decision**, not a mandate to deploy a
mesh — matching how a thoughtful platform team actually treats it.

### 3. Mental model

```text
 A mesh = a proxy on every request path + a control plane configuring them,
 giving mTLS + traffic management + observability WITHOUT app changes.

 Need it? Ask what you actually require:
 mTLS only, few services → Cilium, no mesh
 ingress + basic canary → Gateway API, no mesh
 rich telemetry → OpenTelemetry (Project 3), no mesh
 ALL of: org-wide mTLS + rich → a mesh (Istio); prefer AMBIENT to cut overhead
 traffic mgmt + uniform L7
 telemetry, at scale

 Default stance: don't adopt a mesh until you can name the problem it solves for you.
```

One sentence: **a service mesh buys mTLS, traffic management, and observability via
proxies — adopt it only when lighter tools (Cilium, Gateway API, OTel) genuinely can't
meet the need, and prefer ambient mode to cut the sidecar tax.**

### 4. Minimal implementation

There's no "smallest mesh" worth deploying casually — that's the point. The minimal
*useful* action here is a **decision**, not an install. The lightest way to get a
mesh's headline feature (mTLS between two services) without a full mesh is often Cilium:

```yaml
# Cilium can enforce that traffic between services is authenticated (mTLS),
# using workload identities — no sidecars, no separate control plane.
# (sketch — see / Cilium docs for the full setup)
apiVersion: cilium.io/v2
kind: CiliumNetworkPolicy
metadata:
 name: require-mtls-backend
spec:
 endpointSelector:
 matchLabels:
 app: backend
 ingress:
 - fromEndpoints:
 - matchLabels:
 app: frontend
 authentication:
 mode: "required" # mutually authenticated
```

If that (plus the Gateway API and OTel) covers your needs, you've just avoided adopting
a mesh — the right outcome for most platforms. If it doesn't, the lab helps you make the
case for Istio deliberately.

### 5. Hands-on lab

This is a **decision** module, so the lab is a structured architecture exercise: given
a scenario, decide whether to adopt a service mesh, which one, and why — and defend it
against the lighter alternatives. You'll produce a short decision memo (the artifact a
platform team actually writes before taking on a mesh).

➡️ **Start the lab**

### 6. Production considerations

- **Prefer ambient over sidecars** if you adopt Istio — it removes the per-pod proxy
 tax that sinks most sidecar rollouts, at the cost of being newer.
- **The mesh control plane is tier-1.** `istiod` down, or a bad config push, degrades
 every meshed service. Give it SLOs, careful change management, and canary its configs.
- **mTLS cert rotation must be automatic and tested** — expired certs are an outage.
- **Budget the overhead honestly.** Sidecars add real CPU/memory per pod and latency per
 hop; measure it against the benefit before fleet-wide rollout.
- **Don't double up.** Running Cilium *and* a full Istio sidecar mesh often means paying
 twice for overlapping features. Pick the layer that owns each capability.
- **Adopt incrementally.** Mesh one namespace, prove value, expand — never big-bang the
 whole cluster.

### 7. Common mistakes

- **Adopting a mesh because it's trendy.** — Huge complexity for a problem you didn't
 have. *Fix:* name the specific need (mTLS/traffic-mgmt/telemetry) first; check if
 Cilium/Gateway API/OTel already cover it.
- **Sidecar-everything by default.** — The per-pod proxy tax dominates. *Fix:* prefer
 ambient mode, or mesh only the services that need L7 features.
- **Ignoring the control plane as a dependency.** — `istiod`/config pushes become a new
 cluster-wide failure mode. *Fix:* treat it as tier-1 with SLOs and safe rollouts.
- **Running overlapping layers.** — Cilium mTLS *and* Istio mTLS, paying twice. *Fix:*
 assign each capability to one layer.
- **Big-bang rollout.** — Meshing everything at once turns one bug into a cluster-wide
 incident. *Fix:* incremental, namespace-by-namespace adoption with measurement.

### 8. Assessment

**Knowledge checks**

1. What are the three problem families a service mesh addresses?
2. What is the difference between Istio's **sidecar** and **ambient** dataplanes, and
 why does ambient exist?
3. Give one capability where Istio is stronger than Cilium, and one where Cilium is
 lighter-weight than Istio.
4. Name two lighter tools that cover parts of what a mesh does, and which part each
 covers.
5. State one concrete situation where adopting a mesh would be the *wrong* call.

**Concept exercise**

> Explain what a service mesh gives you **without using the words "sidecar," "proxy," or
> "Istio."** Describe the capabilities from the application team's point of view.

**Trade-off exercise**

> A 12-service platform wants encryption between services and better canary deploys. A
> senior engineer proposes a full Istio sidecar mesh. You already run Cilium and the
> Gateway API. Argue for the approach you'd actually take and why — and say what would
> change your answer.

<details>
<summary>Discussion (open after you've answered)</summary>

- **Q1:** Security (mTLS), traffic management (retries/timeouts/circuit-breaking/
 splitting/fault injection), and observability (per-call metrics/traces/logs).
- **Q2:** Sidecar injects an Envoy proxy into every pod (mature, full L7, high
 overhead); ambient uses a per-node ztunnel for L4+mTLS and optional waypoints for L7
 only where needed. Ambient exists to remove the per-pod sidecar overhead.
- **Q3:** Istio is stronger at rich traffic management (retries, circuit breaking, fault
 injection, mirroring); Cilium is lighter-weight (eBPF, no sidecars) for CNI + identity
 policy + mTLS + flow observability.
- **Q4:** Cilium (mTLS + L7 policy + Hubble observability), the Gateway API (ingress +
 weighted canary), OpenTelemetry (per-service telemetry) — each covers a slice a mesh
 would otherwise provide.
- **Q5:** e.g. a small handful of services whose mTLS is already met by Cilium and whose
 routing is handled by the Gateway API — a full sidecar mesh is pure cost.
- **Trade-off:** With Cilium + Gateway API already running, cover mTLS via Cilium
 (identity-based, no sidecars) and canary via the Gateway API's weighted splits; add
 OTel for telemetry. That meets both needs without a mesh's overhead. What would change
 it: needing rich resilience (circuit breaking, fault injection, mirroring) or uniform
 L7 telemetry across many services the apps can't instrument — then evaluate Istio
 **ambient**, incrementally.

</details>

### 9. Further reading

- [Istio documentation](https://istio.io/latest/docs/) and [Ambient mesh](https://istio.io/latest/docs/ambient/)
- [Istio traffic management (VirtualService/DestinationRule)](https://istio.io/latest/docs/concepts/traffic-management/)
- [Cilium Service Mesh](https://docs.cilium.io/en/stable/network/servicemesh/) — mesh features without sidecars
- [SPIFFE/SPIRE](https://spiffe.io/) — workload identity underpinning mesh mTLS
- · Zero Trust for Platforms

---

### complete 🎉

You can now reason about the whole networking stack: the flat pod network and how a
request really flows, the CNI that makes it real, default-deny NetworkPolicies for
isolation, Cilium and eBPF for L7 policy and observability, the Gateway API for
role-separated ingress, and a clear-eyed view of when a service mesh earns its
complexity.


_Previous:_ 14.5 — Kubernetes Gateway API
· _Next phase:_ 15 · Developer Experience and IDP →
