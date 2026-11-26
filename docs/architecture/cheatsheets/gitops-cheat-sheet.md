# Cheat Sheet — GitOps

> GitOps makes Git the single source of truth: an in-cluster agent continuously
> reconciles the cluster toward the declared state and reverts drift.

## The four principles (OpenGitOps)

1. **Declarative** - the whole system is described declaratively.
2. **Versioned & immutable** - desired state lives in Git (audited, revertible).
3. **Pulled automatically** - agents pull the approved state from Git.
4. **Continuously reconciled** - agents detect drift and correct it.

## Push vs pull

| | Push (CI deploys) | Pull (GitOps agent) |
|--|-------------------|---------------------|
| Who applies | CI pipeline with cluster creds | In-cluster controller |
| Credentials | Cluster creds leave CI | Stay inside the cluster |
| Drift handling | None by default | Detected and self-healed |
| Examples | `kubectl apply` in CI | Argo CD, Flux |

## Repository strategy

- **Separate app code from config:** the app repo builds images; a config repo holds
  the manifests the agent reconciles.
- **Folders over branches** for environments: `envs/{dev,staging,prod}` are easy to
  diff and promote. Long-lived per-env branches drift and cause messy merges.
- **Promotion is a commit or PR** that bumps an image tag or values from one env
  folder to the next (optionally automated by an image updater).

```text
config-repo/
  base/                 # shared manifests (Kustomize base)
  envs/
    dev/                # overlay + image tags
    staging/
    prod/
```

## Drift & self-heal

- **Drift:** live state diverges from Git (a manual `kubectl edit`, an operator).
- **Self-heal:** the agent reapplies Git state, reverting out-of-band changes.
- **Prune:** deleting from Git deletes from the cluster (guarded, opt-in).

## Why it works

- **Recovery:** rebuild a cluster by pointing the agent at the repo.
- **Audit:** every change is a reviewed, attributable commit.
- **Consistency:** the same state reconciled everywhere, continuously.

## Secrets in GitOps

| Option | How it keeps Git clean |
|--------|------------------------|
| **Sealed Secrets** | Commit an encrypted `SealedSecret`; the controller decrypts in-cluster |
| **External Secrets (ESO)** | Commit a reference; ESO syncs from Vault/cloud store |
| **SOPS (+ age/KMS)** | Commit encrypted YAML; decrypt at apply time |
| **Vault Agent/CSI** | Inject secrets at runtime; nothing lands in Git |

- Rule: **never** commit plaintext secrets. Commit ciphertext or a reference only.

## Common pitfalls

- **Config in the app repo** - couples build and deploy; split them.
- **Per-env branches** - drift and merge pain; use folders/overlays instead.
- **Manual `kubectl` on managed resources** - reverted by self-heal; change Git.
- **Plaintext secrets** - use Sealed Secrets, ESO, SOPS, or Vault.

## Reconciliation flow

```text
Developer -> PR to config repo -> review and merge (approved desired state)
          -> GitOps agent detects the new commit
          -> diff live vs desired -> apply -> report Synced/Healthy
          -> watch for drift -> self-heal -> repeat
```

Promote by copying a tested image tag from one overlay to the next:

```bash
# bump prod to a version already validated in staging
yq -i '.images[0].newTag = "v2.3.1"' envs/prod/kustomization.yaml
git commit -am "promote web v2.3.1 to prod" && git push   # the agent syncs
```

## Tooling

| Tool | Notes |
|------|-------|
| **Argo CD** | App-centric, rich UI, ApplicationSets, sync waves and hooks |
| **Flux** | A toolkit of controllers (source, kustomize) driven by CRDs |
| **Config Sync / Rancher Fleet** | Fleet-scale reconciliation across many clusters |

## See also

- [`../08-gitops/`](../08-gitops/) - GitOps principles, Argo CD, multi-environment
  promotion, and secrets.
- [`argocd-cheat-sheet.md`](./argocd-cheat-sheet.md) - Argo CD operations.
