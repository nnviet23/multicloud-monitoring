#!/usr/bin/env python3
"""
Test script for Task 3: P0 - GitOps Orchestration Compatibility (ArgoCD Spoke Secrets & Kustomize Decoupling)
Audit findings addressed:
- GIT-01: GitOps Headless Rendering fails due to local .env dependency in Kustomize hub
- GIT-02: Missing Spoke cluster credentials / registration secrets for Argo CD Multi-Cluster
- GIT-03: Missing Argo CD Core CRDs & controller installation manifests in deploy/argocd
- GIT-04: ArgoCD targetRevision floating HEAD causing conflicts with local deployments
"""

import os
import shutil
import subprocess
from pathlib import Path
import yaml
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

HUB_KUSTOMIZATION_PATH = REPO_ROOT / "deploy" / "clusters" / "hub" / "kustomization.yaml"
HUB_ENV_PATH = REPO_ROOT / "deploy" / "clusters" / "hub" / ".env"
ARGOCD_KUSTOMIZATION_PATH = REPO_ROOT / "deploy" / "argocd" / "kustomization.yaml"
ARGOCD_APPSET_HUB_PATH = REPO_ROOT / "deploy" / "argocd" / "applicationset-hub.yaml"
ARGOCD_APPSET_SPOKES_PATH = REPO_ROOT / "deploy" / "argocd" / "applicationset-spokes.yaml"
REGISTER_SPOKES_SCRIPT_PATH = REPO_ROOT / "infra" / "scripts" / "register_argocd_spokes.py"
CLI_PATH = REPO_ROOT / "infra" / "cli.py"


def load_yaml(file_path: Path):
    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_all_yaml(file_path: Path):
    with open(file_path, "r", encoding="utf-8") as f:
        return list(yaml.safe_load_all(f))


def test_kustomize_hub_decoupled_from_local_env():
    """GIT-01: Verify Kustomize hub builds cleanly without .env present."""
    assert HUB_KUSTOMIZATION_PATH.exists(), f"Missing {HUB_KUSTOMIZATION_PATH}"
    
    # Check that kustomization.yaml does not refer to .env in secretGenerator
    hub_kust = load_yaml(HUB_KUSTOMIZATION_PATH)
    secret_gens = hub_kust.get("secretGenerator", [])
    for sg in secret_gens:
        envs = sg.get("envs", [])
        assert ".env" not in envs, f"secretGenerator '{sg.get('name')}' still references '.env'"
        assert not envs, f"secretGenerator '{sg.get('name')}' should not rely on external env files: {envs}"

    # Temporarily move .env aside if it exists to test true headless rendering
    backup_path = HUB_ENV_PATH.with_suffix(".env.test_backup")
    had_env = HUB_ENV_PATH.exists()
    if had_env:
        shutil.move(str(HUB_ENV_PATH), str(backup_path))

    try:
        res = subprocess.run(
            ["kubectl", "kustomize", str(HUB_KUSTOMIZATION_PATH.parent)],
            capture_output=True,
            text=True
        )
        assert res.returncode == 0, f"kubectl kustomize failed without .env:\n{res.stderr}"
        
        output = res.stdout
        # Ensure essential secrets are generated
        for sec in ["minio-creds", "grafana-admin-creds", "loki-s3-creds", "tempo-s3-creds", "thanos-s3-creds", "robusta-secrets"]:
            assert f"name: {sec}" in output, f"Expected generated secret '{sec}' in kustomize output"
    finally:
        if had_env and backup_path.exists():
            shutil.move(str(backup_path), str(HUB_ENV_PATH))


def test_applicationsets_pinned_to_main():
    """GIT-04: Verify ApplicationSets targetRevision is pinned to 'main' instead of floating 'HEAD'."""
    assert ARGOCD_APPSET_HUB_PATH.exists(), f"Missing {ARGOCD_APPSET_HUB_PATH}"
    assert ARGOCD_APPSET_SPOKES_PATH.exists(), f"Missing {ARGOCD_APPSET_SPOKES_PATH}"

    hub_appset = load_yaml(ARGOCD_APPSET_HUB_PATH)
    spokes_appset = load_yaml(ARGOCD_APPSET_SPOKES_PATH)

    hub_target = hub_appset["spec"]["template"]["spec"]["source"].get("targetRevision")
    assert hub_target == "main", f"Hub ApplicationSet targetRevision must be 'main', found: {hub_target}"

    spokes_target = spokes_appset["spec"]["template"]["spec"]["source"].get("targetRevision")
    assert spokes_target == "main", f"Spokes ApplicationSet targetRevision must be 'main', found: {spokes_target}"


def test_argocd_kustomization_includes_core_manifests():
    """GIT-03: Verify deploy/argocd/kustomization.yaml includes Argo CD Core installation."""
    assert ARGOCD_KUSTOMIZATION_PATH.exists(), f"Missing {ARGOCD_KUSTOMIZATION_PATH}"
    argocd_kust = load_yaml(ARGOCD_KUSTOMIZATION_PATH)
    
    resources = argocd_kust.get("resources", [])
    has_core = any("core-install" in r or "argocd" in r.lower() for r in resources if r != "00-namespace.yaml")
    assert has_core, f"deploy/argocd/kustomization.yaml resources must include ArgoCD Core manifests: {resources}"

    # Build kustomize and verify CRDs/controllers are rendered
    res = subprocess.run(
        ["kubectl", "kustomize", str(ARGOCD_KUSTOMIZATION_PATH.parent)],
        capture_output=True,
        text=True
    )
    assert res.returncode == 0, f"kubectl kustomize deploy/argocd failed:\n{res.stderr}"
    assert "applicationsets.argoproj.io" in res.stdout, "CRD applicationsets.argoproj.io missing from deploy/argocd"
    assert "applications.argoproj.io" in res.stdout, "CRD applications.argoproj.io missing from deploy/argocd"


def test_register_argocd_spokes_script():
    """GIT-02: Verify register_argocd_spokes.py exists, contains required logic."""
    assert REGISTER_SPOKES_SCRIPT_PATH.exists(), f"Missing {REGISTER_SPOKES_SCRIPT_PATH}"
    
    content = REGISTER_SPOKES_SCRIPT_PATH.read_text(encoding="utf-8")
    
    # Must handle both spoke clusters
    assert "aws-k3d" in content, "register_argocd_spokes.py must handle aws-k3d"
    assert "azure-k3d" in content, "register_argocd_spokes.py must handle azure-k3d"
    
    # Must configure argocd-manager and cluster secret
    assert "argocd-manager" in content, "Script must configure argocd-manager ServiceAccount"
    assert "argocd.argoproj.io/secret-type" in content, "Script must create Secret labeled argocd.argoproj.io/secret-type: cluster"
    assert "serverlb:6443" in content, "Script must use destination cluster endpoint serverlb:6443"


def test_ansible_playbook_includes_spoke_registration():
    """Verify infra/cli.py includes spoke registration command."""
    assert CLI_PATH.exists(), f"Missing {CLI_PATH}"
    content = CLI_PATH.read_text(encoding="utf-8")
    assert "register-spokes" in content, "infra/cli.py must include register-spokes command"


if __name__ == "__main__":
    pytest.main(["-v", __file__])
