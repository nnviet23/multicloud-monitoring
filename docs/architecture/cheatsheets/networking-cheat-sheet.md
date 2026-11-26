# Cheat Sheet — Kubernetes Networking

> Every pod gets a routable IP on a flat network; Services give stable names and
> load-balancing; NetworkPolicy and the Gateway API control traffic.

## The model

- **Flat pod network:** every pod has its own IP and reaches every other pod
  directly, with no NAT, across nodes. The CNI wires this up.
- **Service** - a stable virtual IP and DNS name load-balancing to pod endpoints.
- **Service DNS:** `<svc>.<namespace>.svc.cluster.local`, resolved by CoreDNS.

| Service type | Reaches | Use |
|--------------|---------|-----|
| ClusterIP | In-cluster only | Default, east-west traffic |
| NodePort | Node IP and port | Dev, or behind an external LB |
| LoadBalancer | Cloud load balancer | External L4 exposure |
| ExternalName | CNAME | Alias an external host |
| Headless (`clusterIP: None`) | Pod IPs directly | StatefulSets, discovery |

## NetworkPolicy default-deny

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny
  namespace: app
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
```

- An empty `podSelector` selects all pods; with no rules, all traffic is denied.
- Policies are **additive** and allow-only; layer explicit allows on top.

```yaml
# Allow same-namespace ingress and DNS egress (needed once egress is denied)
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: web-allow
  namespace: app
spec:
  podSelector:
    matchLabels:
      app: web
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector: {}
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
```

## Cilium & eBPF

- **eBPF** runs sandboxed programs in the Linux kernel for networking, security, and
  observability without iptables or sidecars.
- Cilium can **replace kube-proxy**, enforce L3/L4/L7 policy, and encrypt traffic.

```bash
cilium status
cilium connectivity test
cilium hubble enable
```

### Hubble flow observability

```bash
hubble observe --namespace app --verdict DROPPED
hubble observe --pod app/web --protocol http
hubble observe --from-label app=web --to-label app=db
```

## Gateway API

- The successor to Ingress: role-oriented, extensible, and portable.
- **GatewayClass** (infra, cluster-scoped) to **Gateway** (listeners, platform team)
  to **HTTPRoute** (routing rules, app team).

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: web
spec:
  parentRefs:
    - name: public-gateway
  hostnames:
    - app.example.com
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /
      backendRefs:
        - name: web-v1
          port: 80
          weight: 90
        - name: web-v2
          port: 80
          weight: 10   # weighted canary
```

## DNS & debugging

```bash
kubectl run tmp --rm -it --image=nicolaka/netshoot -- bash
nslookup web.app.svc.cluster.local
curl -sS http://web.app.svc.cluster.local/healthz   # call a Service by name
```

- A pod resolves `web` in its own namespace, `web.app` across namespaces, and the
  FQDN anywhere; `search` domains in `/etc/resolv.conf` make the short forms work.

## Ingress vs Gateway API

| | Ingress | Gateway API |
|--|---------|-------------|
| Model | One object, annotation-driven | Role-split GatewayClass/Gateway/Route |
| Protocols | Mostly HTTP(S) | HTTP, gRPC, TCP, TLS (typed routes) |
| Portability | Vendor annotations diverge | Standard, implementation-agnostic |
| Maturity | Stable, legacy | Successor; HTTPRoute is GA |

## See also

- [`../14-kubernetes-networking/`](../14-kubernetes-networking/) - networking
  fundamentals, CNI plugins, NetworkPolicy, Cilium/eBPF, and the Gateway API.
