# Cheat Sheet — Argo CD

> Argo CD is a pull-based GitOps controller. It reconciles `Application`s toward Git
> and reports **sync** status (vs Git) and **health** status (runtime).

## Application anatomy

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: web
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/org/config
    targetRevision: main
    path: envs/prod
  destination:
    server: https://kubernetes.default.svc
    namespace: web
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

## ApplicationSet (generators)

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: web-all-clusters
  namespace: argocd
spec:
  generators:
    - clusters: {}            # one Application per registered cluster
  template:
    metadata:
      name: "web-{{name}}"
    spec:
      project: default
      source:
        repoURL: https://github.com/org/config
        targetRevision: main
        path: envs/prod
      destination:
        server: "{{server}}"
        namespace: web
```

- Generators: `list`, `clusters`, `git` (files/directories), `matrix`, `merge`,
  `pullRequest`, `scmProvider`.

## Sync status

| Status      | Meaning                           |
| ----------- | --------------------------------- |
| `Synced`    | Live state matches Git            |
| `OutOfSync` | Git changed or live state drifted |
| `Unknown`   | Comparison not available yet      |
|             |                                   |

## Health status

| Status | Meaning |
|--------|---------|
| `Healthy` | Resources are running as intended |
| `Progressing` | A rollout is in progress |
| `Degraded` | Failed or unhealthy resources |
| `Missing` | Declared but not present in the cluster |

## Sync options & waves

- **Sync options:** `CreateNamespace=true`, `ApplyOutOfSyncOnly=true`,
  `ServerSideApply=true`, `PrunePropagationPolicy=foreground`.
- **Sync waves:** order resources with an annotation; lower waves apply first.

```yaml
metadata:
  annotations:
    argocd.argoproj.io/sync-wave: "-1"      # e.g. CRDs/namespaces before apps
    argocd.argoproj.io/hook: PreSync        # or run the resource as a hook
```

## App of apps

- A parent `Application` whose path contains child `Application` manifests, so one
  root bootstraps a whole environment (often superseded by ApplicationSet).

## argocd CLI

```bash
argocd login argocd.example.com --sso
argocd app list
argocd app get web
argocd app sync web
argocd app sync web --prune
argocd app diff web
argocd app set web --kustomize-image=app=ghcr.io/org/app:v2  # override Kustomize image
argocd app history web
argocd app rollback web 12
argocd app wait web --health
argocd repo add https://github.com/org/config
argocd cluster add <kube-context>
```

## Projects (guardrails)

```yaml
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: team-a
  namespace: argocd
spec:
  sourceRepos:
    - https://github.com/org/*
  destinations:
    - server: https://kubernetes.default.svc
      namespace: team-a-*
  clusterResourceWhitelist:
    - group: ""
      kind: Namespace
```

- An `AppProject` restricts which repos, clusters, namespaces, and resource kinds its
  Applications may use - multi-tenant guardrails for self-service.

## Troubleshooting

```bash
argocd app get web --refresh        # force a comparison against Git
argocd app logs web                 # app container logs via Argo CD
argocd app resources web            # managed resources and their status
argocd app sync web --resource apps:Deployment:web   # sync one resource
```

- `OutOfSync` + `Healthy`: Git changed but the live app still works - safe to sync.
- `Synced` + `Degraded`: the manifest applied but the workload is failing.
- Revert with `argocd app history web`, then `argocd app rollback web <id>`.

## See also

- [`../08-gitops/`](../08-gitops/) - Argo CD fundamentals, ApplicationSets, and
  multi-environment GitOps.
- [`gitops-cheat-sheet.md`](./gitops-cheat-sheet.md) - GitOps principles and
  repository strategy.
