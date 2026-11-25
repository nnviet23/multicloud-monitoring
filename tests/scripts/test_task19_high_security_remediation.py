"""Tests for Task 2 (Task 19): High-severity security remediations."""

from pathlib import Path
import pickle
import sys
from unittest.mock import patch

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_detector_safe_torch_load_fails_closed():
    """_safe_torch_load must not fall back to weights_only=False."""
    import ast

    detector_path = REPO_ROOT / "ai-engine" / "inference" / "detector.py"
    source = detector_path.read_text(encoding="utf-8")
    assert "weights_only=False" not in source

    tree = ast.parse(source)
    fn = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_safe_torch_load"
    )
    fn_src = ast.get_source_segment(source, fn)
    assert fn_src is not None
    assert "weights_only=True" in fn_src
    assert "weights_only=False" not in fn_src


def test_detector_no_joblib_load():
    """detector.py must not invoke joblib.load."""
    detector_path = REPO_ROOT / "ai-engine" / "inference" / "detector.py"
    source = detector_path.read_text(encoding="utf-8")
    assert "joblib.load" not in source


def test_otel_edge_kubeletstats_tls_verification():
    """kubeletstats receiver must verify kubelet TLS using serviceaccount CA."""
    cfg_path = (
        REPO_ROOT
        / "deploy"
        / "platform"
        / "otel-collector"
        / "edge"
        / "02-configmap.yaml"
    )
    cm = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    otel_cfg = yaml.safe_load(cm["data"]["config.yaml"])
    kubeletstats = otel_cfg["receivers"]["kubeletstats"]
    assert kubeletstats["insecure_skip_verify"] is False
    assert (
        kubeletstats["ca_file"]
        == "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
    )


def test_argocd_vendored_core_install_manifest():
    """Argo CD kustomization must reference local vendored 01-core-install.yaml."""
    argocd_dir = REPO_ROOT / "deploy" / "argocd"
    core_install = argocd_dir / "01-core-install.yaml"
    assert core_install.is_file() and core_install.stat().st_size > 0

    kustomization = yaml.safe_load(
        (argocd_dir / "kustomization.yaml").read_text(encoding="utf-8")
    )
    resources = kustomization["resources"]
    assert "01-core-install.yaml" in resources
    assert not any(
        isinstance(r, str) and r.startswith("https://raw.githubusercontent.com/")
        for r in resources
    )
