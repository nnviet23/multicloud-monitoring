#!/usr/bin/env python3
"""Verification tests for Task 20 Priority 2 & Priority 3 fixes."""

from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_model_config_required_entities():
    cfg_path = ROOT / "ai-engine" / "configs" / "model_config.yaml"
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    required = data.get("inference", {}).get("required_entities", [])
    expected = [
        "aws:teastore-webui",
        "aws:teastore-auth",
        "aws:teastore-image",
        "aws:teastore-recommender",
        "aws:teastore-registry",
        "azure:teastore-persistence",
    ]
    assert required == expected, f"Expected {expected}, got {required}"


def test_gateway_rbac_no_nodes_proxy():
    rbac_path = ROOT / "deploy" / "platform" / "otel-collector" / "gateway" / "02-rbac.yaml"
    docs = list(yaml.safe_load_all(rbac_path.read_text(encoding="utf-8")))
    cluster_role = next(d for d in docs if d and d.get("kind") == "ClusterRole")
    resources = []
    for rule in cluster_role.get("rules", []):
        resources.extend(rule.get("resources", []))
    for forbidden in ("nodes/proxy", "nodes/stats", "nodes/spec"):
        assert forbidden not in resources, f"{forbidden} should be removed from gateway ClusterRole"


def test_gateway_services_split():
    svc_path = ROOT / "deploy" / "platform" / "otel-collector" / "gateway" / "05-service.yaml"
    services = [d for d in yaml.safe_load_all(svc_path.read_text(encoding="utf-8")) if d]
    lb = next(s for s in services if s["metadata"]["name"] == "otel-collector-hub")
    assert lb["spec"]["type"] == "LoadBalancer"
    lb_ports = {p["port"] for p in lb["spec"]["ports"]}
    assert lb_ports == {4317, 4318}, f"LoadBalancer ports should be {{4317, 4318}}, got {lb_ports}"

    metrics_svc = next(s for s in services if s["metadata"]["name"] == "otel-collector-hub-metrics")
    assert metrics_svc["spec"]["type"] == "ClusterIP"
    metrics_ports = {p["port"] for p in metrics_svc["spec"]["ports"]}
    assert metrics_ports == {8888, 8889}, f"Metrics ClusterIP ports should be {{8888, 8889}}, got {metrics_ports}"


def test_azure_kustomization_mysql_secret():
    kust_path = ROOT / "deploy" / "clusters" / "azure" / "kustomization.yaml"
    data = yaml.safe_load(kust_path.read_text(encoding="utf-8"))
    generators = data.get("secretGenerator", [])
    namespaces = {g["namespace"] for g in generators if g.get("name") == "teastore-mysql-secret"}
    assert {"monitoring", "teastore"}.issubset(namespaces), f"Missing teastore-mysql-secret in {namespaces}"


def test_gru_autoencoder_docstring():
    gru_path = ROOT / "ai-engine" / "models" / "gru_autoencoder.py"
    text = gru_path.read_text(encoding="utf-8")
    assert "Features=8" in text
    assert "Features=14" not in text
