#!/usr/bin/env python3
"""
Test script for Task 3: Security & Secrets Hardening (SEC-01, SEC-02, SEC-03, SEC-05)
Audit findings addressed:
- SEC-01: Live Telegram bot token in repo (.env / .env.example)
- SEC-02: Argo CD Spoke registration creates over-privileged cluster-admin ServiceAccount
- SEC-03: Prometheus enables unauthenticated --web.enable-lifecycle
- SEC-05: Hardcoded shared password literals in deploy/clusters/hub/kustomization.yaml
"""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_telegram_token_sanitized():
    """SEC-01: Ensure live Telegram bot token and chat ID are sanitized."""
    for rel_path in [".env", ".env.example"]:
        env_file = REPO_ROOT / rel_path
        if env_file.exists():
            content = env_file.read_text(encoding="utf-8")
            assert "9098288921:AAHocihKtbtW5p0wdNv0ejp_Hm0kRKJ8axY" not in content, (
                f"Active Telegram bot token found in {rel_path}"
            )
            assert "6018907300" not in content, (
                f"Active Telegram chat ID found in {rel_path}"
            )


def test_argocd_spoke_sa_not_bound_to_unrestricted_cluster_admin():
    """SEC-02: Ensure Argo CD spoke registration scopes down RBAC from cluster-admin to argocd-spoke-manager-role."""
    script_path = REPO_ROOT / "infra" / "scripts" / "register_argocd_spokes.py"
    assert script_path.exists(), f"Missing {script_path}"
    content = script_path.read_text(encoding="utf-8")
    assert "name: cluster-admin" not in content, (
        "register_argocd_spokes.py still binds to unrestricted cluster-admin"
    )
    assert "argocd-spoke-manager-role" in content, (
        "register_argocd_spokes.py must define and bind argocd-spoke-manager-role"
    )
    assert "kyverno.io" in content, (
        "register_argocd_spokes.py must grant permissions for kyverno.io"
    )
    assert "clusterpolicies" in content, (
        "register_argocd_spokes.py must grant permissions for clusterpolicies"
    )


def test_prometheus_enable_lifecycle_removed():
    """SEC-03: Ensure --web.enable-lifecycle is removed to prevent unauthenticated remote shutdown."""
    prom_path = REPO_ROOT / "deploy" / "platform" / "metrics-thanos" / "03-statefulset-prometheus.yaml"
    assert prom_path.exists(), f"Missing {prom_path}"
    content = prom_path.read_text(encoding="utf-8")
    assert "--web.enable-lifecycle" not in content, (
        "Prometheus statefulset still enables unauthenticated lifecycle management (--web.enable-lifecycle)"
    )


def test_hub_kustomization_no_hardcoded_shared_password():
    """SEC-05: Ensure deploy/clusters/hub/kustomization.yaml does not contain plaintext shared password."""
    hub_kust = REPO_ROOT / "deploy" / "clusters" / "hub" / "kustomization.yaml"
    assert hub_kust.exists(), f"Missing {hub_kust}"
    content = hub_kust.read_text(encoding="utf-8")
    assert "MultiCloudSecurePassword2026!" not in content, (
        "deploy/clusters/hub/kustomization.yaml still contains hardcoded plaintext password literal"
    )


def test_hub_kustomization_minio_credentials_aligned():
    """SEC-05: Ensure MinIO root password matches client credentials (Loki, Tempo, Thanos) in hub kustomization."""
    import yaml
    hub_kust_path = REPO_ROOT / "deploy" / "clusters" / "hub" / "kustomization.yaml"
    assert hub_kust_path.exists(), f"Missing {hub_kust_path}"
    with open(hub_kust_path, "r", encoding="utf-8") as f:
        hub_kust = yaml.safe_load(f)

    sec_gens = {sg["name"]: sg.get("literals", []) for sg in hub_kust.get("secretGenerator", [])}

    def get_val(literals, key):
        for lit in literals:
            if lit.startswith(f"{key}="):
                return lit.split("=", 1)[1]
        return None

    minio_pw = get_val(sec_gens.get("minio-creds", []), "MINIO_ROOT_PASSWORD")
    loki_pw = get_val(sec_gens.get("loki-s3-creds", []), "MINIO_ROOT_PASSWORD")
    tempo_pw = get_val(sec_gens.get("tempo-s3-creds", []), "MINIO_ROOT_PASSWORD")
    thanos_pw = get_val(sec_gens.get("thanos-s3-creds", []), "AWS_SECRET_ACCESS_KEY")

    assert minio_pw == "CHANGE_ME_MINIO_PASSWORD", (
        f"Expected CHANGE_ME_MINIO_PASSWORD for MinIO root, found: {minio_pw}"
    )
    assert loki_pw == minio_pw, (
        f"Loki S3 password '{loki_pw}' does not match MinIO root password '{minio_pw}'"
    )
    assert tempo_pw == minio_pw, (
        f"Tempo S3 password '{tempo_pw}' does not match MinIO root password '{minio_pw}'"
    )
    assert thanos_pw == minio_pw, (
        f"Thanos S3 secret key '{thanos_pw}' does not match MinIO root password '{minio_pw}'"
    )


if __name__ == "__main__":
    import pytest
    pytest.main(["-v", __file__])
