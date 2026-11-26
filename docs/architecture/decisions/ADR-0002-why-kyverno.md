# ADR-0002: Why Kyverno for Policy-as-Code

## Status
Accepted

## Context
In a multi-cluster Kubernetes platform (`hub-k3d`, `aws-k3d`, `azure-k3d`), pod hardening (non-root execution, read-only root filesystems, dropped capabilities, pinned/signed images, no `hostPath`) must be enforced structurally rather than relying on manual review.

Constraints:
- The platform team primarily works with Kubernetes YAML, not specialized policy languages.
- Policies must support shift-left static validation in CI/CD (`make validate-k8s`) on local `k3d` labs while deferring live admission controllers and Sigstore Cosign verification to real-cloud deployment (Phase 5) to stay within the local RAM budget.

## Decision
We use **Kyverno** as the declarative Policy-as-Code engine (`deploy/policies/`), enforcing `disallow-latest-tag`, `require-ro-rootfs`, `disallow-root-user`, `drop-all-capabilities`, and `restrict-host-path` via `ClusterPolicy` resources, paired with `kyverno test` in CI and Sigstore Cosign keyless signing (OIDC + SLSA Build L2) for internal images.

## Alternatives Considered
- **OPA / Gatekeeper (Rego):** Expressive for complex logic, but Rego introduces a steep learning curve compared to Kyverno's native Kubernetes YAML.
- **Built-in Pod Security Admission (PSA):** Good baseline for namespace-level pod security, but lacks custom rules for image tags, labels, mutation, and signature verification.
- **Long-lived KMS / GPG Signing Keys:** Increases secret-management risk compared to Sigstore OIDC keyless signing.

## Consequences
- **Positive:** Zero new DSL to learn; shift-left CI validation catches misconfigurations before Argo CD sync; `Audit` vs. `Enforce` modes enable safe rollout; pinned tags guarantee benchmark reproducibility.
- **Negative:** Strict `readOnlyRootFilesystem` requires explicit `emptyDir` mounts for third-party containers; running the live admission controller in Phase 5 adds ~100–150 MB RAM per cluster.
