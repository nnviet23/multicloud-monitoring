#!/usr/bin/env python3
"""
Test script for Task 4: Container SecurityContext & Dormant Policies Wiring (SEC-04, SEC-06)
Audit findings addressed:
- SEC-04: Lack of Container Security Contexts (privilege escalation, read-only rootfs, dropped capabilities)
- SEC-06: Dormant Zero-Trust Policies (NetworkPolicies & Kyverno policies not wired into spoke overlays)
"""

import subprocess
from pathlib import Path
import yaml
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

OTEL_GATEWAY_PATH = REPO_ROOT / "deploy" / "platform" / "otel-collector" / "gateway" / "04-deployment.yaml"
OTEL_EDGE_PATH = REPO_ROOT / "deploy" / "platform" / "otel-collector" / "edge" / "03-deployment.yaml"
ROBUSTA_PATH = REPO_ROOT / "deploy" / "platform" / "smart-alerting-robusta" / "03-runner-deployment.yaml"
MINIO_PATH = REPO_ROOT / "deploy" / "platform" / "storage-minio" / "04-statefulset.yaml"
MYSQL_PATH = REPO_ROOT / "workloads" / "teastore" / "azure-spoke" / "01-mysql-statefulset.yaml"

AWS_KUSTOMIZATION_PATH = REPO_ROOT / "deploy" / "clusters" / "aws" / "kustomization.yaml"
AZURE_KUSTOMIZATION_PATH = REPO_ROOT / "deploy" / "clusters" / "azure" / "kustomization.yaml"
HUB_KUSTOMIZATION_PATH = REPO_ROOT / "deploy" / "clusters" / "hub" / "kustomization.yaml"


def load_yaml(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_otel_gateway_and_edge_have_restricted_security_context():
    """SEC-04: Ensure OTel gateway and edge collectors enforce restricted container securityContext and /tmp emptyDir."""
    for manifest_path, name in [(OTEL_GATEWAY_PATH, "otel-collector-hub"), (OTEL_EDGE_PATH, "otel-collector-spoke")]:
        assert manifest_path.exists(), f"Missing manifest: {manifest_path}"
        doc = load_yaml(manifest_path)
        spec = doc["spec"]["template"]["spec"]
        
        # Check container securityContext
        containers = spec["containers"]
        collector_c = next((c for c in containers if c["name"] == "otel-collector"), None)
        assert collector_c is not None, f"Container 'otel-collector' not found in {manifest_path}"
        
        sec_ctx = collector_c.get("securityContext", {})
        assert sec_ctx.get("allowPrivilegeEscalation") is False, (
            f"{name} must set allowPrivilegeEscalation: false"
        )
        assert sec_ctx.get("readOnlyRootFilesystem") is True, (
            f"{name} must set readOnlyRootFilesystem: true"
        )
        caps = sec_ctx.get("capabilities", {})
        dropped = [c.upper() for c in caps.get("drop", [])]
        assert "ALL" in dropped, f"{name} must drop ALL capabilities"
        
        # Check /tmp volume mount
        mounts = collector_c.get("volumeMounts", [])
        tmp_mount = next((m for m in mounts if m.get("mountPath") == "/tmp"), None)
        assert tmp_mount is not None, f"{name} must mount /tmp emptyDir volume"
        
        # Check emptyDir volume in spec
        volumes = spec.get("volumes", [])
        tmp_vol = next((v for v in volumes if v.get("name") == tmp_mount.get("name")), None)
        assert tmp_vol is not None, f"{name} volume for /tmp mount not found in pod spec"
        assert "emptyDir" in tmp_vol, f"{name} /tmp volume must be emptyDir"


def test_robusta_and_minio_have_security_context():
    """SEC-04: Ensure Robusta runner and MinIO storage enforce security contexts."""
    # Test Robusta
    assert ROBUSTA_PATH.exists(), f"Missing manifest: {ROBUSTA_PATH}"
    robusta_doc = load_yaml(ROBUSTA_PATH)
    r_spec = robusta_doc["spec"]["template"]["spec"]
    r_container = next((c for c in r_spec["containers"] if c["name"] == "runner"), None)
    assert r_container is not None, f"Container 'runner' not found in {ROBUSTA_PATH}"
    
    r_sec = r_container.get("securityContext", {})
    assert r_sec.get("allowPrivilegeEscalation") is False, (
        "Robusta runner must set allowPrivilegeEscalation: false"
    )
    assert r_sec.get("readOnlyRootFilesystem") is True, (
        "Robusta runner must set readOnlyRootFilesystem: true"
    )
    r_caps = r_sec.get("capabilities", {})
    r_dropped = [c.upper() for c in r_caps.get("drop", [])]
    assert "ALL" in r_dropped, "Robusta runner must drop ALL capabilities"
    
    r_mounts = r_container.get("volumeMounts", [])
    r_tmp_mount = next((m for m in r_mounts if m.get("mountPath") == "/tmp"), None)
    assert r_tmp_mount is not None, "Robusta runner must mount /tmp emptyDir volume"
    r_tmp_vol = next((v for v in r_spec.get("volumes", []) if v.get("name") == r_tmp_mount.get("name")), None)
    assert r_tmp_vol is not None and "emptyDir" in r_tmp_vol, "Robusta /tmp volume must be emptyDir"
    
    # Test MinIO
    assert MINIO_PATH.exists(), f"Missing manifest: {MINIO_PATH}"
    minio_doc = load_yaml(MINIO_PATH)
    m_spec = minio_doc["spec"]["template"]["spec"]
    m_container = next((c for c in m_spec["containers"] if c["name"] == "minio"), None)
    assert m_container is not None, f"Container 'minio' not found in {MINIO_PATH}"
    
    m_sec = m_container.get("securityContext", {})
    assert m_sec.get("allowPrivilegeEscalation") is False, (
        "MinIO must set allowPrivilegeEscalation: false"
    )
    m_caps = m_sec.get("capabilities", {})
    m_dropped = [c.upper() for c in m_caps.get("drop", [])]
    assert "ALL" in m_dropped, "MinIO must drop ALL capabilities"


def test_mysql_disallows_privilege_escalation():
    """SEC-04: Ensure MySQL statefulset disallows privilege escalation and uses dedicated MySQL UID/GID."""
    assert MYSQL_PATH.exists(), f"Missing manifest: {MYSQL_PATH}"
    doc = load_yaml(MYSQL_PATH)
    spec = doc["spec"]["template"]["spec"]
    
    # Pod securityContext
    pod_sec = spec.get("securityContext", {})
    assert pod_sec.get("runAsUser") == 999, "MySQL Pod must set runAsUser: 999 (mysql user)"
    assert pod_sec.get("fsGroup") == 999, "MySQL Pod must set fsGroup: 999"
    
    # Container securityContext
    container = next((c for c in spec["containers"] if c["name"] == "teastore-db"), None)
    assert container is not None, f"Container 'teastore-db' not found in {MYSQL_PATH}"
    c_sec = container.get("securityContext", {})
    assert c_sec.get("allowPrivilegeEscalation") is False, (
        "MySQL container must set allowPrivilegeEscalation: false"
    )
    
    # Capabilities must not add SETUID / SETGID
    added_caps = [c.upper() for c in c_sec.get("capabilities", {}).get("add", [])]
    assert "SETUID" not in added_caps, "MySQL must not retain SETUID capability"
    assert "SETGID" not in added_caps, "MySQL must not retain SETGID capability"


def test_cluster_overlays_wire_policies():
    """SEC-06: Ensure AWS and Azure cluster overlays wire ../../policies."""
    for path, name in [(AWS_KUSTOMIZATION_PATH, "aws"), (AZURE_KUSTOMIZATION_PATH, "azure")]:
        assert path.exists(), f"Missing {name} kustomization: {path}"
        kust = load_yaml(path)
        resources = kust.get("resources", [])
        has_policies = any(r.endswith("policies") for r in resources)
        assert has_policies, f"{name} kustomization resources must include '../../policies'"


def test_kustomize_build_all_clusters_passes_with_policies():
    """Verify kubectl kustomize passes for all 3 clusters with policies wired."""
    for cluster_name, path in [("aws", AWS_KUSTOMIZATION_PATH), ("azure", AZURE_KUSTOMIZATION_PATH), ("hub", HUB_KUSTOMIZATION_PATH)]:
        res = subprocess.run(
            ["kubectl", "kustomize", str(path.parent)],
            capture_output=True,
            text=True
        )
        assert res.returncode == 0, f"kubectl kustomize failed for {cluster_name}:\n{res.stderr}"
        if cluster_name in ("aws", "azure"):
            assert "kind: NetworkPolicy" in res.stdout, (
                f"Cluster {cluster_name} must output NetworkPolicy when policies are wired"
            )
