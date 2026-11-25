"""Tests for Task 1: In-Cluster PKI with cert-manager and purge of security/ directory."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
import yaml
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_security_directory_purged():
    """Verify that the local security/ directory does not exist anywhere in the repository."""
    security_dir = REPO_ROOT / "security"
    assert not security_dir.exists(), f"security/ directory still exists at {security_dir}"


def test_gitignore_no_security_references():
    """Verify that .gitignore has been cleansed of obsolete security/ references."""
    gitignore = REPO_ROOT / ".gitignore"
    assert gitignore.is_file(), "Missing .gitignore"
    content = gitignore.read_text(encoding="utf-8")
    assert "security/" not in content, ".gitignore still contains security/ references"


def test_cert_manager_manifests_exist_and_valid():
    """Verify all required cert-manager manifests exist, parse as valid YAML, and contain expected resources."""
    cm_dir = REPO_ROOT / "deploy" / "platform" / "cert-manager"
    assert cm_dir.is_dir(), f"Missing directory: {cm_dir}"

    expected_files = [
        "00-namespace.yaml",
        "01-cert-manager.yaml",
        "02-cluster-issuer-root-ca.yaml",
        "03-hub-server-certificate.yaml",
        "04-spoke-client-certificates.yaml",
        "kustomization.yaml",
    ]
    for filename in expected_files:
        filepath = cm_dir / filename
        assert filepath.is_file(), f"Missing cert-manager manifest: {filepath}"

    # 00-namespace.yaml
    ns_docs = list(yaml.safe_load_all((cm_dir / "00-namespace.yaml").read_text(encoding="utf-8")))
    assert len(ns_docs) == 1
    ns = ns_docs[0]
    assert ns["apiVersion"] == "v1"
    assert ns["kind"] == "Namespace"
    assert ns["metadata"]["name"] == "cert-manager"
    assert ns["metadata"]["labels"].get("app.kubernetes.io/managed-by") == "kustomize"

    # 01-cert-manager.yaml
    cm_docs = list(yaml.safe_load_all((cm_dir / "01-cert-manager.yaml").read_text(encoding="utf-8")))
    assert len(cm_docs) > 0
    kinds = [doc.get("kind") for doc in cm_docs if isinstance(doc, dict)]
    assert "CustomResourceDefinition" in kinds
    assert "Deployment" in kinds

    cm_text = (cm_dir / "01-cert-manager.yaml").read_text(encoding="utf-8")
    assert "quay.io/jetstack/cert-manager-controller:v1.16.2" in cm_text
    assert "quay.io/jetstack/cert-manager-webhook:v1.16.2" in cm_text
    assert "quay.io/jetstack/cert-manager-cainjector:v1.16.2" in cm_text

    # 02-cluster-issuer-root-ca.yaml
    issuer_docs = list(yaml.safe_load_all((cm_dir / "02-cluster-issuer-root-ca.yaml").read_text(encoding="utf-8")))
    issuer_names = {d.get("metadata", {}).get("name"): d for d in issuer_docs if isinstance(d, dict)}
    assert "selfsigned-root-issuer" in issuer_names
    assert issuer_names["selfsigned-root-issuer"]["apiVersion"] == "cert-manager.io/v1"
    assert issuer_names["selfsigned-root-issuer"]["kind"] == "ClusterIssuer"
    assert "selfSigned" in issuer_names["selfsigned-root-issuer"]["spec"]

    assert "multicloud-root-ca" in issuer_names
    root_ca = issuer_names["multicloud-root-ca"]
    assert root_ca["apiVersion"] == "cert-manager.io/v1"
    assert root_ca["kind"] == "Certificate"
    assert root_ca["spec"]["secretName"] == "multicloud-root-ca-secret"

    assert "multicloud-ca-issuer" in issuer_names
    ca_issuer = issuer_names["multicloud-ca-issuer"]
    assert ca_issuer["apiVersion"] == "cert-manager.io/v1"
    assert ca_issuer["kind"] == "ClusterIssuer"
    assert ca_issuer["spec"]["ca"]["secretName"] == "multicloud-root-ca-secret"

    # 03-hub-server-certificate.yaml
    hub_cert_docs = list(yaml.safe_load_all((cm_dir / "03-hub-server-certificate.yaml").read_text(encoding="utf-8")))
    assert len(hub_cert_docs) == 1
    hub_cert = hub_cert_docs[0]
    assert hub_cert["apiVersion"] == "cert-manager.io/v1"
    assert hub_cert["kind"] == "Certificate"
    assert hub_cert["metadata"]["name"] == "hub-otel-gateway-server-cert"
    assert hub_cert["metadata"]["namespace"] == "monitoring"
    dns_names = hub_cert["spec"]["dnsNames"]
    ip_addresses = [str(ip) for ip in hub_cert["spec"]["ipAddresses"]]

    assert "otel-collector-hub" in dns_names
    assert "otel-collector-hub.monitoring.svc.cluster.local" in dns_names
    assert "hub-gateway.hub.multicloud.local" in dns_names
    assert "localhost" in dns_names
    assert "127.0.0.1" in ip_addresses
    assert "172.28.0.2" in ip_addresses
    assert "172.28.0.3" in ip_addresses

    # 04-spoke-client-certificates.yaml
    spoke_cert_docs = list(yaml.safe_load_all((cm_dir / "04-spoke-client-certificates.yaml").read_text(encoding="utf-8")))
    assert len(spoke_cert_docs) >= 2
    spoke_names = [d.get("metadata", {}).get("name") for d in spoke_cert_docs if isinstance(d, dict)]
    assert "aws-spoke-client-cert" in spoke_names
    assert "azure-spoke-client-cert" in spoke_names
    for d in spoke_cert_docs:
        assert d["apiVersion"] == "cert-manager.io/v1"
        assert d["kind"] == "Certificate"

    # kustomization.yaml
    kust = yaml.safe_load((cm_dir / "kustomization.yaml").read_text(encoding="utf-8"))
    resources = kust.get("resources", [])
    assert "00-namespace.yaml" in resources
    assert "01-cert-manager.yaml" in resources
    assert "02-cluster-issuer-root-ca.yaml" in resources
    assert "03-hub-server-certificate.yaml" in resources
    assert "04-spoke-client-certificates.yaml" in resources


def test_hub_kustomization_references_cert_manager():
    """Verify that deploy/clusters/hub/kustomization.yaml includes cert-manager platform component."""
    hub_kust_file = REPO_ROOT / "deploy" / "clusters" / "hub" / "kustomization.yaml"
    content = hub_kust_file.read_text(encoding="utf-8")
    kust = yaml.safe_load(content)
    resources = kust.get("resources", [])
    assert "../../platform/cert-manager" in resources or any("cert-manager" in r for r in resources), \
        "Hub kustomization.yaml does not reference platform/cert-manager"


def test_kubectl_kustomize_build_hub_cluster_with_cert_manager():
    """Verify that kubectl kustomize deploy/clusters/hub runs cleanly with cert-manager."""
    res = subprocess.run(
        ["kubectl", "kustomize", "deploy/clusters/hub"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"kubectl kustomize deploy/clusters/hub failed: {res.stderr}"
    assert "cert-manager" in res.stdout
    assert "selfsigned-root-issuer" in res.stdout
    assert "hub-otel-gateway-server-cert" in res.stdout
