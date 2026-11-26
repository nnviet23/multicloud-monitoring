#!/usr/bin/env python3
"""
Test script for Task 2: P0 - Thanos Store Gateway & Thanos Compactor (TSDB Long-Term Storage)
Addresses OBS-01: Missing Thanos Store Gateway & Compactor (historical data query failure after 2 hours).
Aligns with ADR-0016 & ADR-0017.
"""

import os
import subprocess
from pathlib import Path
import yaml
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

METRICS_THANOS_DIR = REPO_ROOT / "deploy" / "platform" / "metrics-thanos"
HUB_CLUSTER_DIR = REPO_ROOT / "deploy" / "clusters" / "hub"

THANOS_STORE_DEPLOY_PATH = METRICS_THANOS_DIR / "07-deployment-thanos-store.yaml"
THANOS_STORE_SVC_PATH = METRICS_THANOS_DIR / "08-service-thanos-store.yaml"
THANOS_COMPACT_STS_PATH = METRICS_THANOS_DIR / "09-statefulset-thanos-compact.yaml"
THANOS_QUERY_DEPLOY_PATH = METRICS_THANOS_DIR / "05-deployment-thanos-query.yaml"
THANOS_KUSTOMIZATION_PATH = METRICS_THANOS_DIR / "kustomization.yaml"


def load_yaml_documents(file_path: Path):
    with open(file_path, "r", encoding="utf-8") as f:
        return list(yaml.safe_load_all(f))


def test_thanos_store_deployment_exists_and_valid():
    """Verify Thanos Store Gateway deployment manifest configuration."""
    assert THANOS_STORE_DEPLOY_PATH.exists(), f"Missing {THANOS_STORE_DEPLOY_PATH}"
    docs = load_yaml_documents(THANOS_STORE_DEPLOY_PATH)
    assert len(docs) >= 1, f"Empty file: {THANOS_STORE_DEPLOY_PATH}"
    doc = docs[0]

    assert doc.get("apiVersion") == "apps/v1"
    assert doc.get("kind") == "Deployment"
    assert doc.get("metadata", {}).get("name") == "thanos-store"
    assert doc.get("metadata", {}).get("namespace") == "monitoring"

    pod_spec = doc.get("spec", {}).get("template", {}).get("spec", {})
    containers = pod_spec.get("containers", [])
    assert len(containers) == 1, "Expected exactly 1 container in thanos-store"

    c = containers[0]
    assert c.get("name") == "thanos-store"
    assert c.get("image") == "quay.io/thanos/thanos:v0.36.1"

    args = c.get("args", [])
    assert "store" in args
    assert "--data-dir=/var/thanos/store" in args
    assert "--objstore.config-file=/etc/thanos/objstore.yml" in args
    assert "--http-address=0.0.0.0:10902" in args
    assert "--grpc-address=0.0.0.0:10901" in args

    ports = {p.get("name"): p.get("containerPort") for p in c.get("ports", [])}
    assert ports.get("grpc") == 10901, "Expected grpc port 10901"
    assert ports.get("http") == 10902, "Expected http port 10902"

    # Volume mounts
    volume_mounts = {vm.get("name"): vm.get("mountPath") for vm in c.get("volumeMounts", [])}
    assert "/etc/thanos" in volume_mounts.values(), "Missing mount for /etc/thanos"
    assert "/var/thanos/store" in volume_mounts.values(), "Missing mount for /var/thanos/store"

    # Volumes
    volumes = {v.get("name"): v for v in pod_spec.get("volumes", [])}
    objstore_vol = next((v for v in volumes.values() if v.get("secret", {}).get("secretName") == "thanos-objstore-secret"), None)
    assert objstore_vol is not None, "thanos-objstore-secret volume not found"

    # Resources
    resources = c.get("resources", {})
    assert resources.get("requests", {}).get("cpu") == "30m"
    assert resources.get("requests", {}).get("memory") == "64Mi"
    assert resources.get("limits", {}).get("memory") == "256Mi"


def test_thanos_store_service_exists_and_valid():
    """Verify Thanos Store Gateway service manifest configuration."""
    assert THANOS_STORE_SVC_PATH.exists(), f"Missing {THANOS_STORE_SVC_PATH}"
    docs = load_yaml_documents(THANOS_STORE_SVC_PATH)
    assert len(docs) >= 1, f"Empty file: {THANOS_STORE_SVC_PATH}"
    doc = docs[0]

    assert doc.get("apiVersion") == "v1"
    assert doc.get("kind") == "Service"
    assert doc.get("metadata", {}).get("name") == "thanos-store"
    assert doc.get("metadata", {}).get("namespace") == "monitoring"

    spec = doc.get("spec", {})
    assert spec.get("selector", {}).get("app") == "thanos-store"

    ports = {p.get("name"): p.get("port") for p in spec.get("ports", [])}
    assert ports.get("grpc") == 10901, "Service thanos-store must expose grpc port 10901"


def test_thanos_compactor_statefulset_exists_and_valid():
    """Verify Thanos Compactor singleton StatefulSet manifest configuration."""
    assert THANOS_COMPACT_STS_PATH.exists(), f"Missing {THANOS_COMPACT_STS_PATH}"
    docs = load_yaml_documents(THANOS_COMPACT_STS_PATH)
    assert len(docs) >= 1, f"Empty file: {THANOS_COMPACT_STS_PATH}"
    doc = docs[0]

    assert doc.get("apiVersion") == "apps/v1"
    assert doc.get("kind") == "StatefulSet"
    assert doc.get("metadata", {}).get("name") == "thanos-compact"
    assert doc.get("metadata", {}).get("namespace") == "monitoring"

    spec = doc.get("spec", {})
    assert spec.get("replicas") == 1, "Thanos Compactor must be a singleton (replicas: 1)"

    pod_spec = spec.get("template", {}).get("spec", {})
    containers = pod_spec.get("containers", [])
    assert len(containers) == 1, "Expected exactly 1 container in thanos-compact"

    c = containers[0]
    assert c.get("name") == "thanos-compact"
    assert c.get("image") == "quay.io/thanos/thanos:v0.36.1"

    args = c.get("args", [])
    assert "compact" in args
    assert "--data-dir=/var/thanos/compact" in args
    assert "--objstore.config-file=/etc/thanos/objstore.yml" in args
    assert "--http-address=0.0.0.0:10902" in args
    assert "--retention.resolution-raw=30d" in args
    assert "--retention.resolution-5m=90d" in args
    assert "--retention.resolution-1h=365d" in args
    assert "--wait" in args

    # Volume mounts
    volume_mounts = {vm.get("name"): vm.get("mountPath") for vm in c.get("volumeMounts", [])}
    assert "/etc/thanos" in volume_mounts.values(), "Missing mount for /etc/thanos"
    assert "/var/thanos/compact" in volume_mounts.values(), "Missing mount for /var/thanos/compact"

    # Resources
    resources = c.get("resources", {})
    assert resources.get("requests", {}).get("cpu") == "50m"
    assert resources.get("requests", {}).get("memory") == "128Mi"
    assert resources.get("limits", {}).get("memory") == "512Mi"


def test_thanos_query_has_store_endpoint():
    """Verify Thanos Query deployment contains endpoint for thanos-store."""
    assert THANOS_QUERY_DEPLOY_PATH.exists(), f"Missing {THANOS_QUERY_DEPLOY_PATH}"
    docs = load_yaml_documents(THANOS_QUERY_DEPLOY_PATH)
    doc = docs[0]

    containers = doc.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
    query_c = next((c for c in containers if c.get("name") == "thanos-query"), None)
    assert query_c is not None, "thanos-query container not found"

    args = query_c.get("args", [])
    store_endpoint = "--endpoint=thanos-store.monitoring.svc.cluster.local:10901"
    assert store_endpoint in args, f"Expected {store_endpoint} in thanos-query args: {args}"


def test_kustomization_includes_new_resources():
    """Verify metrics-thanos kustomization.yaml registers the new manifests."""
    assert THANOS_KUSTOMIZATION_PATH.exists(), f"Missing {THANOS_KUSTOMIZATION_PATH}"
    with open(THANOS_KUSTOMIZATION_PATH, "r", encoding="utf-8") as f:
        kust = yaml.safe_load(f)

    resources = kust.get("resources", [])
    assert "07-deployment-thanos-store.yaml" in resources
    assert "08-service-thanos-store.yaml" in resources
    assert "09-statefulset-thanos-compact.yaml" in resources


def test_kustomize_build_metrics_thanos():
    """Verify kubectl kustomize succeeds on deploy/platform/metrics-thanos."""
    res = subprocess.run(
        ["kubectl", "kustomize", str(METRICS_THANOS_DIR)],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"kubectl kustomize failed: {res.stderr}"
    assert "thanos-store" in res.stdout
    assert "thanos-compact" in res.stdout


def test_kustomize_build_hub_cluster():
    """Verify kubectl kustomize succeeds on deploy/clusters/hub."""
    res = subprocess.run(
        ["kubectl", "kustomize", str(HUB_CLUSTER_DIR)],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"kubectl kustomize hub failed: {res.stderr}"
    assert "thanos-store" in res.stdout
    assert "thanos-compact" in res.stdout


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
