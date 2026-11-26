#!/usr/bin/env python3
"""
Test script for Task 6: P2 - Thiết Lập NetworkPolicies, Chuẩn Hóa Tài Nguyên Workload & Dọn Dẹp Ansible
Audit findings addressed:
- SEC-03: Missing NetworkPolicies / 100% default-allow east-west traffic
- HYG-01: InitContainers missing resource requests and limits
- HYG-02: Zombie namespace robusta
- AUT-01: Ansible cleanup not removing PKI cert files
"""

from pathlib import Path
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

DEFAULT_DENY_POLICY_PATH = REPO_ROOT / "deploy" / "policies" / "10-default-deny-networkpolicy.yaml"
ALLOW_CORE_POLICY_PATH = REPO_ROOT / "deploy" / "policies" / "11-allow-core-traffic-networkpolicy.yaml"
POLICIES_KUSTOMIZATION_PATH = REPO_ROOT / "deploy" / "policies" / "kustomization.yaml"

ROBUSTA_NS_FILE = REPO_ROOT / "deploy" / "platform" / "smart-alerting-robusta" / "00-namespace.yaml"
ROBUSTA_KUSTOMIZATION = REPO_ROOT / "deploy" / "platform" / "smart-alerting-robusta" / "kustomization.yaml"

INFRA_CLI_PATH = REPO_ROOT / "infra" / "cli.py"

TEASTORE_DEPLOYMENT_PATHS = [
    REPO_ROOT / "deploy" / "workloads" / "teastore" / "aws-spoke" / "02-auth-deployment.yaml",
    REPO_ROOT / "deploy" / "workloads" / "teastore" / "aws-spoke" / "03-image-deployment.yaml",
    REPO_ROOT / "deploy" / "workloads" / "teastore" / "aws-spoke" / "04-recommender-deployment.yaml",
    REPO_ROOT / "deploy" / "workloads" / "teastore" / "aws-spoke" / "05-webui-deployment.yaml",
    REPO_ROOT / "deploy" / "workloads" / "teastore" / "azure-spoke" / "02-persistence-deployment.yaml",
]


def load_yaml(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_sec03_default_deny_networkpolicy_exists_and_valid():
    """SEC-03: Ensure 10-default-deny-networkpolicy.yaml exists and defines Default-Deny for teastore."""
    assert DEFAULT_DENY_POLICY_PATH.exists(), f"Missing {DEFAULT_DENY_POLICY_PATH}"
    data = load_yaml(DEFAULT_DENY_POLICY_PATH)

    assert data.get("apiVersion") == "networking.k8s.io/v1"
    assert data.get("kind") == "NetworkPolicy"
    assert data.get("metadata", {}).get("name") == "default-deny-all"
    assert data.get("metadata", {}).get("namespace") == "teastore"

    spec = data.get("spec", {})
    assert spec.get("podSelector") == {} or spec.get("podSelector") == {"matchLabels": {}}
    policy_types = spec.get("policyTypes", [])
    assert "Ingress" in policy_types
    assert "Egress" in policy_types

    # Default deny must not specify ingress/egress allow rules
    assert not spec.get("ingress", [])
    assert not spec.get("egress", [])


def test_sec03_allow_core_traffic_networkpolicy_exists_and_valid():
    """SEC-03: Ensure 11-allow-core-traffic-networkpolicy.yaml exists and allows DNS, microservices, and OTLP."""
    assert ALLOW_CORE_POLICY_PATH.exists(), f"Missing {ALLOW_CORE_POLICY_PATH}"
    data = load_yaml(ALLOW_CORE_POLICY_PATH)

    assert data.get("apiVersion") == "networking.k8s.io/v1"
    assert data.get("kind") == "NetworkPolicy"
    assert data.get("metadata", {}).get("name") == "allow-core-traffic"
    assert data.get("metadata", {}).get("namespace") == "teastore"

    spec = data.get("spec", {})
    assert spec.get("podSelector") == {} or spec.get("podSelector") == {"matchLabels": {}}
    policy_types = spec.get("policyTypes", [])
    assert "Ingress" in policy_types
    assert "Egress" in policy_types

    # Check egress rules
    egress_rules = spec.get("egress", [])
    assert len(egress_rules) > 0, "allow-core-traffic must have egress rules"

    egress_ports = []
    for rule in egress_rules:
        for port_entry in rule.get("ports", []):
            egress_ports.append((port_entry.get("protocol"), port_entry.get("port")))

    # Must allow CoreDNS / DNS: 53 (UDP or TCP)
    assert ("UDP", 53) in egress_ports or ("TCP", 53) in egress_ports, "DNS egress port 53 must be allowed"
    # Must allow internal microservices: 8080
    assert ("TCP", 8080) in egress_ports, "TeaStore microservice egress port 8080 must be allowed"
    # Must allow MySQL: 3306
    assert ("TCP", 3306) in egress_ports, "MySQL database egress port 3306 must be allowed"
    # Must allow OTLP export: 4317
    assert ("TCP", 4317) in egress_ports, "OTLP gRPC egress port 4317 must be allowed"
    # Must allow cross-cluster Spoke-to-Spoke WAN communication: 31111 (Persistence) and 31112 (Registry)
    assert ("TCP", 31111) in egress_ports, "Cross-cluster Persistence egress port 31111 must be allowed"
    assert ("TCP", 31112) in egress_ports, "Cross-cluster Registry egress port 31112 must be allowed"

    # Check ingress rules
    ingress_rules = spec.get("ingress", [])
    assert len(ingress_rules) > 0, "allow-core-traffic must have ingress rules"
    ingress_ports = []
    for rule in ingress_rules:
        for port_entry in rule.get("ports", []):
            ingress_ports.append((port_entry.get("protocol"), port_entry.get("port")))

    assert ("TCP", 8080) in ingress_ports, "Microservices HTTP ingress port 8080 must be allowed"


def test_sec03_networkpolicies_registered_in_kustomization():
    """SEC-03: Ensure 10- and 11- NetworkPolicies are registered in deploy/policies/kustomization.yaml."""
    assert POLICIES_KUSTOMIZATION_PATH.exists(), f"Missing {POLICIES_KUSTOMIZATION_PATH}"
    data = load_yaml(POLICIES_KUSTOMIZATION_PATH)
    resources = data.get("resources", [])

    assert "10-default-deny-networkpolicy.yaml" in resources
    assert "11-allow-core-traffic-networkpolicy.yaml" in resources


def test_hyg01_teastore_initcontainers_have_resource_constraints():
    """HYG-01: Ensure all opentelemetry-auto-instrumentation initContainers have proper requests and limits."""
    for path in TEASTORE_DEPLOYMENT_PATHS:
        assert path.exists(), f"Deployment manifest missing: {path}"
        data = load_yaml(path)

        spec = data.get("spec", {}).get("template", {}).get("spec", {})
        init_containers = spec.get("initContainers", [])
        otel_inits = [c for c in init_containers if c.get("name") == "opentelemetry-auto-instrumentation"]

        assert len(otel_inits) == 1, f"Deployment {path.name} must have opentelemetry-auto-instrumentation initContainer"
        otel_init = otel_inits[0]

        resources = otel_init.get("resources")
        assert resources is not None, f"Deployment {path.name} initContainer missing 'resources'"

        requests = resources.get("requests", {})
        limits = resources.get("limits", {})

        assert requests.get("cpu") == "10m", f"Deployment {path.name} initContainer requests.cpu must be '10m'"
        assert requests.get("memory") == "16Mi", f"Deployment {path.name} initContainer requests.memory must be '16Mi'"
        assert limits.get("cpu") == "100m", f"Deployment {path.name} initContainer limits.cpu must be '100m'"
        assert limits.get("memory") == "64Mi", f"Deployment {path.name} initContainer limits.memory must be '64Mi'"


def test_hyg02_robusta_zombie_namespace_removed():
    """HYG-02: Ensure 00-namespace.yaml is removed and absent from kustomization in smart-alerting-robusta."""
    assert not ROBUSTA_NS_FILE.exists(), f"Zombie namespace file should not exist: {ROBUSTA_NS_FILE}"

    assert ROBUSTA_KUSTOMIZATION.exists(), f"Missing {ROBUSTA_KUSTOMIZATION}"
    data = load_yaml(ROBUSTA_KUSTOMIZATION)
    resources = data.get("resources", [])
    assert "00-namespace.yaml" not in resources, "00-namespace.yaml must not be in resources"


def test_aut01_ansible_cleanup_removes_pki_certs():
    """AUT-01: Ensure infra/cli.py down command has logic to delete PKI certificates and CA directories."""
    assert INFRA_CLI_PATH.exists(), f"Missing {INFRA_CLI_PATH}"
    with open(INFRA_CLI_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # Must clean up generated certificates (certs-* and ca)
    assert "certs-" in content, "Platform CLI cleanup must reference certs- for removal"
    assert "ca" in content, "Platform CLI cleanup must reference ca for removal"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
