# Cheat Sheet — kubectl

> `kubectl` talks to the API server. The pattern is `kubectl <verb> <resource>
> <name> [flags]`. Add `-o yaml`, `-o wide`, or `-o jsonpath=...` to shape output.

## Contexts & config

```bash
kubectl config get-contexts
kubectl config use-context <ctx>
kubectl config set-context --current --namespace=<ns>
kubectl cluster-info
kubectl version --output=yaml
```

## Inspecting resources

```bash
kubectl get pods -A -o wide                 # all namespaces, node/IP columns
kubectl get deploy,svc,ingress -n app
kubectl get pod <pod> -o yaml
kubectl get pods -l app=web --sort-by=.status.startTime
kubectl get pods -o jsonpath='{.items[*].spec.containers[*].image}'
kubectl describe pod <pod>                  # spec + recent events
kubectl explain deployment.spec.strategy    # API field docs
```

## Logs & exec

```bash
kubectl logs <pod> -c <container> -f --tail=100
kubectl logs <pod> --previous               # last crashed container
kubectl logs -l app=web --max-log-requests=10
kubectl exec -it <pod> -- sh
kubectl cp <pod>:/var/log/app.log ./app.log
```

## Apply, edit, delete

```bash
kubectl apply -f ./manifests/               # declarative, idempotent
kubectl apply -k ./overlays/prod            # kustomize build + apply
kubectl diff -f deploy.yaml                 # preview before apply
kubectl edit deploy/web
kubectl set image deploy/web web=ghcr.io/org/web:v2
kubectl rollout status deploy/web
kubectl rollout undo deploy/web
kubectl delete -f deploy.yaml --grace-period=30
```

## Scale & rollout

```bash
kubectl scale deploy/web --replicas=5
kubectl autoscale deploy/web --min=2 --max=10 --cpu-percent=70
kubectl rollout restart deploy/web
kubectl rollout history deploy/web
```

## Labels, annotations, namespaces

```bash
kubectl create namespace app
kubectl label pod <pod> tier=frontend --overwrite
kubectl annotate deploy/web kubernetes.io/change-cause="v2 rollout"
kubectl get ns --show-labels
```

## Debugging

```bash
kubectl debug -it <pod> --image=busybox --target=<container>
kubectl debug node/<node> -it --image=busybox
kubectl get events --sort-by=.lastTimestamp
kubectl top pod -n app                       # needs metrics-server
kubectl top node
```

## Port-forward & proxy

```bash
kubectl port-forward svc/web 8080:80
kubectl port-forward pod/<pod> 5432:5432
kubectl proxy --port=8001                    # local API proxy
```

## Access review (RBAC)

```bash
kubectl auth can-i create deployments -n app
kubectl auth can-i '*' '*' --all-namespaces
kubectl auth can-i list secrets \
  --as=system:serviceaccount:app:deployer -n app
kubectl auth whoami
```

## Handy flags

| Flag | Effect |
|------|--------|
| `-o wide` | Extra columns (node, IP) |
| `-o yaml` / `-o json` | Full object |
| `-o jsonpath='{...}'` | Extract specific fields |
| `--dry-run=client -o yaml` | Generate manifests without applying |
| `-w` | Watch for changes |
| `-A` / `--all-namespaces` | Across namespaces |

```bash
# Scaffold a manifest without creating anything
kubectl create deployment web --image=nginx --dry-run=client -o yaml > deploy.yaml
```

## Output & formatting

```bash
kubectl get pods -o custom-columns='NAME:.metadata.name,NODE:.spec.nodeName'
kubectl get pods -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[*].image}{"\n"}{end}'
kubectl get pods --field-selector=status.phase=Running --sort-by=.metadata.name
```

## Resource shortnames

| Short | Resource | Short | Resource |
|-------|----------|-------|----------|
| `po` | pods | `deploy` | deployments |
| `svc` | services | `rs` | replicasets |
| `ns` | namespaces | `cm` | configmaps |
| `sa` | serviceaccounts | `pvc` | persistentvolumeclaims |
| `ing` | ingresses | `netpol` | networkpolicies |

## Kustomize & k3d

```bash
# Kustomize (built into kubectl)
kubectl kustomize deploy/clusters/hub-k3d
kubectl apply -k deploy/clusters/hub-k3d
kubectl diff -k deploy/clusters/hub-k3d
kubectl delete -k deploy/clusters/hub-k3d

# k3d multi-cluster management
k3d cluster list
k3d cluster start hub-k3d aws-k3d azure-k3d
k3d cluster stop hub-k3d aws-k3d azure-k3d
k3d kubeconfig merge hub-k3d aws-k3d azure-k3d --kubeconfig-switch-context=false
kubectl config use-context k3d-hub-k3d
```

## See also

- [`../03-kubernetes-fundamentals/`](../03-kubernetes-fundamentals/) - the objects
  these commands manage.
- [`kubernetes-cheat-sheet.md`](./kubernetes-cheat-sheet.md) - architecture, RBAC,
  and the pod debugging workflow.
