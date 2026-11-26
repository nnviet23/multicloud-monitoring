# Cheat Sheet — Security & Policy

> Enforce least privilege and secure defaults as code: admission policies, external
> secrets, signed and provenanced artifacts, and a hardened pod baseline.

## Kyverno policy patterns

- **Rule types:** `validate` (allow/deny/audit), `mutate` (inject defaults),
  `generate` (create resources), `verifyImages` (signatures/attestations).
- **Actions:** `Enforce` blocks the request; `Audit` reports only.

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: require-requests-limits
spec:
  validationFailureAction: Enforce
  rules:
    - name: require-resources
      match:
        any:
          - resources:
              kinds:
                - Pod
      validate:
        message: "CPU/memory requests and limits are required."
        pattern:
          spec:
            containers:
              - resources:
                  requests:
                    memory: "?*"
                    cpu: "?*"
                  limits:
                    memory: "?*"
```

- Common patterns: disallow the `latest` tag, require non-root, enforce labels,
  restrict registries, auto-generate a default-deny `NetworkPolicy`.

## Secret management options

| Option | Model | Where the secret lives | Best for |
|--------|-------|------------------------|----------|
| **Sealed Secrets** | Encrypt-to-cluster | Ciphertext in Git | Simple GitOps, one cluster |
| **External Secrets (ESO)** | Sync from a store | Vault / cloud SM | A central store, many clusters |
| **Vault** | Dynamic / leased | Vault, injected | Short-lived, audited secrets |
| **SOPS (+ age/KMS)** | File encryption | Ciphertext in Git | Encrypting files in any repo |

- Decision: one cluster, keep it simple then Sealed Secrets; a central source of
  truth then ESO; dynamic DB/cloud creds then Vault; encrypt arbitrary files then SOPS.

## Supply chain security (SLSA)

- **SLSA** is Supply-chain Levels for Software Artifacts: provenance and integrity.

| Level | Build requirement |
|-------|-------------------|
| L1 | Provenance exists (how it was built) |
| L2 | Signed provenance from a hosted build service |
| L3 | Hardened, isolated builds; non-falsifiable provenance |

```bash
# Sign and verify an image (keyless, Sigstore/cosign)
cosign sign ghcr.io/org/web@sha256:<digest>
cosign verify ghcr.io/org/web@sha256:<digest> \
  --certificate-identity-regexp '.*' \
  --certificate-oidc-issuer-regexp '.*'

# Generate an SBOM and scan for vulnerabilities
syft ghcr.io/org/web:v2 -o spdx-json > sbom.json
grype ghcr.io/org/web:v2 --fail-on high
trivy image --exit-code 1 --severity HIGH,CRITICAL ghcr.io/org/web:v2
```

- Generate provenance in CI (for example with the SLSA GitHub generator) and store
  it as an attestation alongside the image.
- Verify signatures at admission with Kyverno `verifyImages` or a Sigstore policy.

## Security hardening checklist

- [ ] Run as **non-root** (`runAsNonRoot: true`, a high `runAsUser`).
- [ ] **Read-only** root filesystem (`readOnlyRootFilesystem: true`).
- [ ] **Drop all capabilities**; add back only what is needed.
- [ ] `allowPrivilegeEscalation: false`; no `privileged` containers.
- [ ] **seccomp** `RuntimeDefault` profile.
- [ ] Set **requests/limits**; enforce them via policy.
- [ ] **NetworkPolicy** default-deny ingress and egress (allow DNS).
- [ ] **Least-privilege RBAC**; a dedicated ServiceAccount; no cluster-admin.
- [ ] **Sign images**; verify provenance at admission; scan in CI.
- [ ] **Runtime detection** (Falco) for anomalous syscalls and behavior.

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 10001
  readOnlyRootFilesystem: true
  allowPrivilegeEscalation: false
  seccompProfile:
    type: RuntimeDefault
  capabilities:
    drop:
      - ALL
```

## See also

- [`../13-security-and-policy-engineering/`](../13-security-and-policy-engineering/)
  - RBAC, Kyverno, secrets, supply chain, image signing, and runtime security.
