#!/usr/bin/env python3
"""
Test Suite for Task 13 (Task 4 of Phase 3): Standardize Prometheus Alert Rules into Domain-Specific Files
Validates modular rules under deploy/platform/metrics-thanos/rules/ sourced from Awesome Prometheus Alerts.
"""

import os
import subprocess
from pathlib import Path
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
THANOS_DIR = REPO_ROOT / "deploy" / "platform" / "metrics-thanos"
MONOLITHIC_RULES_PATH = THANOS_DIR / "01-configmap-prometheus-rules.yaml"
RULES_DIR = THANOS_DIR / "rules"
KUSTOMIZATION_PATH = THANOS_DIR / "kustomization.yaml"

EXPECTED_RULE_FILES = [
    "01-host-rules.yaml",
    "02-kubernetes-rules.yaml",
    "03-mysql-rules.yaml",
    "04-jvm-rules.yaml",
    "05-wan-network-rules.yaml",
    "06-thanos-rules.yaml",
    "07-cert-manager-rules.yaml",
    "08-opentelemetry-collector-rules.yaml",
]


def test_monolithic_rules_configmap_eliminated():
    """Verify monolithic 01-configmap-prometheus-rules.yaml is completely deleted."""
    assert not MONOLITHIC_RULES_PATH.exists(), (
        f"Monolithic rule configmap must be deleted: {MONOLITHIC_RULES_PATH}"
    )


def test_modular_rules_directory_and_files_exist():
    """Verify rules directory and all 8 expected domain rule files exist."""
    assert RULES_DIR.exists() and RULES_DIR.is_dir(), f"Missing rules dir: {RULES_DIR}"
    for filename in EXPECTED_RULE_FILES:
        file_path = RULES_DIR / filename
        assert file_path.exists(), f"Missing modular rule file: {file_path}"


def test_all_modular_rules_valid_yaml_and_structure():
    """Verify all 8 rule files are valid YAML and follow Prometheus rule group schema."""
    for filename in EXPECTED_RULE_FILES:
        file_path = RULES_DIR / filename
        assert file_path.exists(), f"File does not exist: {file_path}"
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert isinstance(data, dict), f"{filename} root must be a YAML dictionary"
        assert "groups" in data, f"{filename} missing 'groups' key"
        groups = data["groups"]
        assert isinstance(groups, list) and len(groups) > 0, f"{filename} 'groups' must be non-empty list"

        for group in groups:
            assert "name" in group and isinstance(group["name"], str), f"Group in {filename} missing 'name'"
            assert "rules" in group and isinstance(group["rules"], list), f"Group {group.get('name')} missing 'rules'"
            assert len(group["rules"]) > 0, f"Group {group.get('name')} has no rules"

            for rule in group["rules"]:
                alert_name = rule.get("alert")
                assert alert_name, f"Rule in {filename} group {group.get('name')} missing 'alert'"
                assert "expr" in rule, f"Alert {alert_name} in {filename} missing 'expr'"
                assert "for" in rule, f"Alert {alert_name} in {filename} missing 'for'"
                assert "labels" in rule, f"Alert {alert_name} in {filename} missing 'labels'"
                assert "annotations" in rule, f"Alert {alert_name} in {filename} missing 'annotations'"
                labels = rule["labels"]
                assert "severity" in labels, f"Alert {alert_name} in {filename} missing 'severity' label"
                assert labels["severity"] in ["critical", "warning", "info"], (
                    f"Alert {alert_name} invalid severity: {labels['severity']}"
                )


def test_domain_specific_alert_coverage():
    """Verify essential alerts per domain exist in the corresponding modular files."""
    def get_alerts_in_file(filename):
        file_path = RULES_DIR / filename
        if not file_path.exists():
            return set()
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        alerts = set()
        for g in data.get("groups", []):
            for r in g.get("rules", []):
                if "alert" in r:
                    alerts.add(r["alert"])
        return alerts

    # 01-host-rules.yaml
    host_alerts = get_alerts_in_file("01-host-rules.yaml")
    for req in ["HostHighCpuLoad", "HostOutOfMemory", "HostOutOfDiskSpace", "HostSystemdServiceCrashed"]:
        assert req in host_alerts, f"Missing {req} in 01-host-rules.yaml"

    # 02-kubernetes-rules.yaml
    k8s_alerts = get_alerts_in_file("02-kubernetes-rules.yaml")
    for req in ["KubernetesNodeReady", "KubernetesPodCrashLooping", "KubernetesDeploymentReplicasMismatch"]:
        assert req in k8s_alerts, f"Missing {req} in 02-kubernetes-rules.yaml"
    assert ("KubernetesContainerOomKilled" in k8s_alerts or "KubernetesContainerOomKiller" in k8s_alerts), (
        "Missing KubernetesContainerOomKilled/KubernetesContainerOomKiller in 02-kubernetes-rules.yaml"
    )

    # 03-mysql-rules.yaml
    mysql_alerts = get_alerts_in_file("03-mysql-rules.yaml")
    for req in ["MysqlDown", "MysqlTooManyConnections", "MysqlSlowQueries", "MysqlRestarted"]:
        assert req in mysql_alerts, f"Missing {req} in 03-mysql-rules.yaml"

    # 04-jvm-rules.yaml
    jvm_alerts = get_alerts_in_file("04-jvm-rules.yaml")
    for req in ["JvmMemoryFillingUp", "JvmThreadsDeadlocked"]:
        assert req in jvm_alerts, f"Missing {req} in 04-jvm-rules.yaml"
    assert ("JvmGarbageCollectionDurationHigh" in jvm_alerts or "JvmGcTimeTooHigh" in jvm_alerts), (
        "Missing JvmGarbageCollectionDurationHigh/JvmGcTimeTooHigh in 04-jvm-rules.yaml"
    )

    # 05-wan-network-rules.yaml
    wan_alerts = get_alerts_in_file("05-wan-network-rules.yaml")
    for req in ["WanInterClusterLatencyHigh", "WanPacketLossDetected", "NetworkInterfaceErrorsHigh"]:
        assert req in wan_alerts, f"Missing {req} in 05-wan-network-rules.yaml"

    # 06-thanos-rules.yaml
    thanos_alerts = get_alerts_in_file("06-thanos-rules.yaml")
    for req in ["ThanosCompactHalted", "ThanosCompactMultipleRunning", "ThanosQueryHighErrorRate"]:
        assert req in thanos_alerts, f"Missing {req} in 06-thanos-rules.yaml"

    # 07-cert-manager-rules.yaml
    cert_alerts = get_alerts_in_file("07-cert-manager-rules.yaml")
    for req in ["CertManagerCertExpirySoon", "CertManagerCertNotReady", "CertManagerHittingRateLimits"]:
        assert req in cert_alerts, f"Missing {req} in 07-cert-manager-rules.yaml"

    # 08-opentelemetry-collector-rules.yaml
    otel_alerts = get_alerts_in_file("08-opentelemetry-collector-rules.yaml")
    for req in ["OtelCollectorQueueIsFillingUp", "OtelCollectorDataDropped", "OtelCollectorReceiverRefusedData"]:
        assert req in otel_alerts, f"Missing {req} in 08-opentelemetry-collector-rules.yaml"


def test_no_duplicate_alert_names_across_all_files():
    """Verify that every alert name across all modular rule files is globally unique."""
    all_alerts = {}
    for filename in EXPECTED_RULE_FILES:
        file_path = RULES_DIR / filename
        if not file_path.exists():
            continue
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        for g in data.get("groups", []):
            for r in g.get("rules", []):
                alert_name = r.get("alert")
                if not alert_name:
                    continue
                assert alert_name != "CrossClusterCallFailureRateHigh", (
                    f"Redundant alert CrossClusterCallFailureRateHigh found in {filename}"
                )
                assert alert_name not in all_alerts, (
                    f"Duplicate alert name '{alert_name}' in {filename} (already in {all_alerts[alert_name]})"
                )
                all_alerts[alert_name] = filename


def test_kustomization_wires_rules_configmap():
    """Verify deploy/platform/metrics-thanos/kustomization.yaml configures prometheus-rules generator."""
    assert KUSTOMIZATION_PATH.exists(), f"Missing kustomization: {KUSTOMIZATION_PATH}"
    with open(KUSTOMIZATION_PATH, "r", encoding="utf-8") as f:
        kust = yaml.safe_load(f)

    # 01-configmap-prometheus-rules.yaml must not be in resources
    resources = kust.get("resources", [])
    assert "01-configmap-prometheus-rules.yaml" not in resources, (
        "01-configmap-prometheus-rules.yaml must be removed from kustomization resources"
    )

    # configMapGenerator must contain prometheus-rules
    generators = kust.get("configMapGenerator", [])
    rule_gen = next((g for g in generators if g.get("name") == "prometheus-rules"), None)
    assert rule_gen is not None, "prometheus-rules configMapGenerator missing"
    assert rule_gen.get("namespace") == "monitoring"
    assert rule_gen.get("options", {}).get("disableNameSuffixHash") is True

    files = rule_gen.get("files", [])
    for expected in EXPECTED_RULE_FILES:
        expected_path = f"rules/{expected}"
        assert expected_path in files, f"Missing {expected_path} in configMapGenerator files"


def test_kubectl_kustomize_build_hub_cluster():
    """Verify kubectl kustomize deploy/clusters/hub builds cleanly with the new modular rules."""
    hub_path = REPO_ROOT / "deploy" / "clusters" / "hub"
    result = subprocess.run(
        ["kubectl", "kustomize", str(hub_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert result.returncode == 0, f"kubectl kustomize failed for hub cluster:\n{result.stderr}"
    assert "kind: ConfigMap" in result.stdout
    assert "name: prometheus-rules" in result.stdout
