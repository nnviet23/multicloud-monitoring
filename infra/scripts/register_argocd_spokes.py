#!/usr/bin/env python3
"""Cross-platform script to register Spoke clusters in Argo CD on Hub cluster.

Implements OpenGitOps v1.0.0 & ADR-0003 standards for multi-cluster GitOps delivery.
"""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import subprocess
import sys
import time
from typing import NamedTuple


class SpokeConfig(NamedTuple):
    name: str
    context: str
    server_url: str


DEFAULT_SPOKES = [
    SpokeConfig("aws-k3d", "k3d-aws-k3d", "https://k3d-aws-k3d-serverlb:6443"),
    SpokeConfig("azure-k3d", "k3d-azure-k3d", "https://k3d-azure-k3d-serverlb:6443"),
]


def run_kubectl(cmd_args: list[str], input_data: str | None = None) -> subprocess.CompletedProcess[str]:
    """Execute kubectl with given arguments and optional stdin."""
    kubectl_bin = shutil.which("kubectl") or "kubectl"
    full_cmd = [kubectl_bin] + cmd_args
    return subprocess.run(
        full_cmd,
        input=input_data,
        capture_output=True,
        text=True,
    )


def register_spokes_in_argocd(
    hub_context: str = "k3d-hub-k3d",
    argocd_namespace: str = "argocd",
    spokes: list[SpokeConfig] | None = None,
    dry_run: bool = False,
) -> bool:
    """Register Spoke clusters into Argo CD on Hub."""
    if spokes is None:
        spokes = DEFAULT_SPOKES

    print(f"--> Ensuring Argo CD namespace '{argocd_namespace}' on Hub ({hub_context})...")
    ns_manifest = f"""apiVersion: v1
kind: Namespace
metadata:
  name: {argocd_namespace}
"""
    if not dry_run:
        res = run_kubectl(["--context", hub_context, "apply", "-f", "-"], input_data=ns_manifest)
        if res.returncode != 0:
            print(f"[WARN] Failed to apply namespace {argocd_namespace} on Hub: {res.stderr.strip()}")

    all_ok = True
    for spoke in spokes:
        print(f"\n--> Processing Spoke Cluster: {spoke.name} (Context: {spoke.context})...")
        if dry_run:
            print(f"    [DRY-RUN] Validated spoke parameters for {spoke.name} ({spoke.context}) -> {spoke.server_url}")
            continue

        # Check reachability
        check = run_kubectl(["--context", spoke.context, "get", "nodes"])
        if check.returncode != 0:
            print(f"    [WARN] Cluster {spoke.name} ({spoke.context}) not reachable; skipping registration.")
            all_ok = False
            continue

        # RBAC manifest: least-privilege scoped ClusterRole for spoke management (SEC-02)
        rbac_manifest = """apiVersion: v1
kind: ServiceAccount
metadata:
  name: argocd-manager
  namespace: kube-system
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: argocd-spoke-manager-role
rules:
  - apiGroups:
      - ""
    resources:
      - configmaps
      - endpoints
      - events
      - namespaces
      - persistentvolumeclaims
      - pods
      - secrets
      - services
      - serviceaccounts
    verbs:
      - get
      - list
      - watch
      - create
      - update
      - patch
      - delete
  - apiGroups:
      - apps
    resources:
      - daemonsets
      - deployments
      - replicasets
      - statefulsets
    verbs:
      - get
      - list
      - watch
      - create
      - update
      - patch
      - delete
  - apiGroups:
      - batch
    resources:
      - cronjobs
      - jobs
    verbs:
      - get
      - list
      - watch
      - create
      - update
      - patch
      - delete
  - apiGroups:
      - networking.k8s.io
    resources:
      - ingresses
      - networkpolicies
    verbs:
      - get
      - list
      - watch
      - create
      - update
      - patch
      - delete
  - apiGroups:
      - monitoring.coreos.com
    resources:
      - servicemonitors
      - podmonitors
      - prometheusrules
    verbs:
      - get
      - list
      - watch
      - create
      - update
      - patch
      - delete
  - apiGroups:
      - opentelemetry.io
    resources:
      - opentelemetrycollectors
    verbs:
      - get
      - list
      - watch
      - create
      - update
      - patch
      - delete
  - apiGroups:
      - kyverno.io
    resources:
      - clusterpolicies
      - policies
      - policyexceptions
    verbs:
      - get
      - list
      - watch
      - create
      - update
      - patch
      - delete
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: argocd-manager-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: argocd-spoke-manager-role
subjects:
- kind: ServiceAccount
  name: argocd-manager
  namespace: kube-system
---
apiVersion: v1
kind: Secret
metadata:
  name: argocd-manager-token
  namespace: kube-system
  annotations:
    kubernetes.io/service-account.name: argocd-manager
type: kubernetes.io/service-account-token
"""
        if not dry_run:
            print(f"    - Applying 'argocd-manager' RBAC on {spoke.name}...")
            apply_rbac = run_kubectl(["--context", spoke.context, "apply", "-f", "-"], input_data=rbac_manifest)
            if apply_rbac.returncode != 0:
                print(f"    [ERROR] Failed to apply RBAC on {spoke.name}: {apply_rbac.stderr.strip()}")
                all_ok = False
                continue

        # Extract token
        token = ""
        for _ in range(5):
            tok_res = run_kubectl(
                ["--context", spoke.context, "-n", "kube-system", "get", "secret", "argocd-manager-token", "-o", "jsonpath={.data.token}"]
            )
            raw_b64 = tok_res.stdout.strip()
            if raw_b64:
                try:
                    token = base64.b64decode(raw_b64).decode("utf-8")
                    if token:
                        break
                except Exception:
                    pass
            time.sleep(1)

        if not token:
            print(f"    - Token secret empty, attempting 'kubectl create token argocd-manager'...")
            # Token policy: 90-day validity window (2160h) with regular rotation requirement
            tok_gen = run_kubectl(["--context", spoke.context, "-n", "kube-system", "create", "token", "argocd-manager", "--duration=2160h"])
            token = tok_gen.stdout.strip()

        if not token:
            print(f"    [ERROR] Failed to obtain token for argocd-manager on {spoke.name}")
            all_ok = False
            continue

        # Extract CA Data
        ca_res = run_kubectl(
            ["--context", spoke.context, "-n", "kube-system", "get", "secret", "argocd-manager-token", "-o", "jsonpath={.data.ca\\.crt}"]
        )
        ca_data = ca_res.stdout.strip()
        if not ca_data:
            ca_cfg = run_kubectl(
                ["--context", spoke.context, "config", "view", "--raw", "--minify", "-o", "jsonpath={.clusters[0].cluster.certificate-authority-data}"]
            )
            ca_data = ca_cfg.stdout.strip()

        # Build Argo CD Cluster Secret for Hub
        cluster_config = {
            "bearerToken": token,
            "tlsClientConfig": {
                "insecure": False,
                "caData": ca_data,
            },
        }

        cluster_secret_manifest = f"""apiVersion: v1
kind: Secret
metadata:
  name: cluster-{spoke.name}
  namespace: {argocd_namespace}
  labels:
    argocd.argoproj.io/secret-type: cluster
type: Opaque
stringData:
  name: {spoke.name}
  server: {spoke.server_url}
  config: |
    {json.dumps(cluster_config, indent=4)}
"""
        if not dry_run:
            print(f"    - Applying cluster Secret for {spoke.name} into Hub Argo CD...")
            hub_apply = run_kubectl(["--context", hub_context, "apply", "-f", "-"], input_data=cluster_secret_manifest)
            if hub_apply.returncode == 0:
                print(f"    [OK] Cluster {spoke.name} registered successfully in Hub Argo CD.")
            else:
                print(f"    [ERROR] Failed applying secret in Hub: {hub_apply.stderr.strip()}")
                all_ok = False
        else:
            print(f"    [DRY-RUN] Manifest generated for {spoke.name}.")

    return all_ok


def main() -> None:
    parser = argparse.ArgumentParser(description="Register Spoke clusters in Argo CD on Hub")
    parser.add_argument("--hub-context", default="k3d-hub-k3d", help="Hub cluster kubectl context")
    parser.add_argument("--argocd-namespace", default="argocd", help="Argo CD namespace on Hub")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without modifying cluster")
    args = parser.parse_args()

    success = register_spokes_in_argocd(
        hub_context=args.hub_context,
        argocd_namespace=args.argocd_namespace,
        dry_run=args.dry_run,
    )
    if not success and not args.dry_run:
        sys.exit(1)


if __name__ == "__main__":
    main()
