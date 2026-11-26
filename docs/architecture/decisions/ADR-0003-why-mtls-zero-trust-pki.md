# ADR-0003: Why Native mTLS 1.3 and Zero-Trust PKI

## Status
Accepted

## Context
Telemetry (metrics, logs, traces) and control-plane traffic traverse the emulated WAN between `aws-k3d`, `azure-k3d`, and `hub-k3d`. Because this traffic may carry sensitive cluster identifiers or PII, transit must be encrypted and mutually authenticated without adding heavy reverse proxies (e.g., Nginx or Envoy) that consume scarce local RAM. Furthermore, GitOps repositories must never store plaintext secrets.

## Decision
We implement a three-pillar Zero-Trust security model:
1. **Internal PKI via `cert-manager` (`v1.16.2`):** A `multicloud-root-ca` on `hub-k3d` issues short-lived (90-day, 30-day auto-renew) server certificates for Hub OTel Gateway and distinct client certificates (`aws-spoke-client-cert`, `azure-spoke-client-cert`) for each spoke.
2. **Native mTLS 1.3 on OTLP:** Configured directly in OpenTelemetry Collector receivers/exporters (`min_version: "1.3"`, `TLS_AES_256_GCM_SHA384`, `TLS_CHACHA20_POLY1305_SHA256`) with mutual CA verification, eliminating external TLS-terminating proxies.
3. **GitOps Secret Encryption via Bitnami Sealed Secrets:** Secrets are encrypted with `kubeseal` for safe Git storage (with `infra/cli.py sync-secrets` supporting local headless `k3d` dev).

## Alternatives Considered
- **WireGuard / IPSec VPN:** Encrypts L3 traffic but complicates host OS networking and lacks application-level spoke identity verification.
- **HashiCorp Vault:** Comprehensive secret management, but requires ~500 MB–1 GB RAM, which is too heavy for the local workstation budget.
- **Server-only TLS on OTLP:** Encrypts transit but cannot authenticate spoke identity, leaving the Hub vulnerable to spoofed telemetry poisoning AIOps.

## Consequences
- **Positive:** Defense-in-depth encryption across the WAN; pure GitOps-compatible secret storage; minimal CPU/RAM overhead by terminating mTLS natively in Go.
- **Negative:** Requires automated bootstrap scripts to distribute the Root CA and client certificates to `k3d` nodes, and requires backing up the Sealed Secrets controller private key for disaster recovery.
