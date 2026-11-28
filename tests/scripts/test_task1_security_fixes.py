#!/usr/bin/env python3
"""
Test script for Task 1: P0 - Security Fixes
- SEC-01: Robusta wildcard RBAC restriction to least privilege
- SEC-02: Kyverno policy exception for MySQL (disallow-privilege-escalation)
"""

import os
import subprocess
from pathlib import Path
import yaml
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

ROBUSTA_RBAC_PATH = REPO_ROOT / "deploy" / "platform" / "smart-alerting-robusta" / "00-rbac.yaml"
KYVERNO_EXCEPTION_PATH = REPO_ROOT / "deploy" / "policies" / "06-policy-exception-mysql.yaml"
KYVERNO_KUSTOMIZATION_PATH = REPO_ROOT / "deploy" / "policies" / "kustomization.yaml"
ROBUSTA_DIR = REPO_ROOT / "deploy" / "platform" / "smart-alerting-robusta"
POLICIES_DIR = REPO_ROOT / "deploy" / "policies"


def load_yaml_documents(file_path: Path):
    with open(file_path, "r", encoding="utf-8") as f:
        return list(yaml.safe_load_all(f))


def test_robusta_rbac_no_wildcards_and_least_privilege():
    """Verify Robusta ClusterRole does not have wildcard permissions and follows least privilege."""
    assert ROBUSTA_RBAC_PATH.exists(), f"Missing {ROBUSTA_RBAC_PATH}"
    docs = load_yaml_documents(ROBUSTA_RBAC_PATH)

    cluster_roles = [d for d in docs if d and d.get("kind") == "ClusterRole" and d.get("metadata", {}).get("name") == "robusta-runner-cluster-role"]
    assert len(cluster_roles) == 1, "Expected exactly 1 robusta-runner-cluster-role ClusterRole"

    role = cluster_roles[0]
    rules = role.get("rules", [])
    assert len(rules) > 0, "Robusta ClusterRole must have rules"

    # Ensure no wildcards anywhere
    for rule in rules:
        api_groups = rule.get("apiGroups", [])
        resources = rule.get("resources", [])
        verbs = rule.get("verbs", [])

        assert "*" not in api_groups, f"Wildcard found in apiGroups: {api_groups}"
        assert "*" not in resources, f"Wildcard found in resources: {resources}"
        assert "*" not in verbs, f"Wildcard found in verbs: {verbs}"

    # Verify exact required least privilege rules
    rule_map = {tuple(sorted(r.get("apiGroups", []))): r for r in rules}
    
    # 1. Core API group ("")
    assert ("",) in rule_map, "Missing core ('') apiGroup rule"
    core_rule = rule_map[("",)]
    expected_core_resources = {"pods", "pods/log", "nodes", "events", "services", "namespaces", "configmaps"}
    assert set(core_rule.get("resources", [])) == expected_core_resources
    assert set(core_rule.get("verbs", [])) == {"get", "list", "watch"}

    # 2. apps API group
    assert ("apps",) in rule_map, "Missing 'apps' apiGroup rule"
    apps_rule = rule_map[("apps",)]
    expected_apps_resources = {"deployments", "daemonsets", "statefulsets", "replicasets"}
    assert set(apps_rule.get("resources", [])) == expected_apps_resources
    assert set(apps_rule.get("verbs", [])) == {"get", "list", "watch"}

    # 3. batch API group
    assert ("batch",) in rule_map, "Missing 'batch' apiGroup rule"
    batch_rule = rule_map[("batch",)]
    expected_batch_resources = {"jobs", "cronjobs"}
    assert set(batch_rule.get("resources", [])) == expected_batch_resources
    assert set(batch_rule.get("verbs", [])) == {"get", "list", "watch"}


def test_kyverno_validating_policies():
    """Verify Kyverno policies use policies.kyverno.io/v1 ValidatingPolicy."""
    policy_files = sorted(POLICIES_DIR.glob("0[1-5]-*.yaml"))
    assert len(policy_files) == 5, f"Expected 5 policy files, found {len(policy_files)}"
    for policy_file in policy_files:
        docs = load_yaml_documents(policy_file)
        assert len(docs) >= 1, f"{policy_file.name} is empty"
        doc = docs[0]
        assert doc.get("apiVersion") == "policies.kyverno.io/v1", f"{policy_file.name}: expected apiVersion policies.kyverno.io/v1"
        assert doc.get("kind") == "ValidatingPolicy", f"{policy_file.name}: expected kind ValidatingPolicy"


def test_kyverno_policy_exception_mysql():
    """Verify Kyverno PolicyException file exists and is configured properly for MySQL."""
    assert KYVERNO_EXCEPTION_PATH.exists(), f"PolicyException file not found: {KYVERNO_EXCEPTION_PATH}"

    docs = load_yaml_documents(KYVERNO_EXCEPTION_PATH)
    assert len(docs) >= 1, "PolicyException file is empty"
    doc = docs[0]

    assert doc.get("apiVersion") == "policies.kyverno.io/v1"
    assert doc.get("kind") == "PolicyException"
    assert doc.get("metadata", {}).get("name") == "teastore-mysql-privilege-escalation-exception"
    assert doc.get("metadata", {}).get("namespace") == "teastore"

    spec = doc.get("spec", {})
    policy_refs = spec.get("policyRefs", [])
    assert any(
        ref.get("name") == "disallow-privilege-escalation"
        and ref.get("kind") == "ValidatingPolicy"
        for ref in policy_refs
    ), "policyRefs for ValidatingPolicy disallow-privilege-escalation not found"


def test_kyverno_kustomization_includes_exception():
    """Verify deploy/policies/kustomization.yaml includes 06-policy-exception-mysql.yaml."""
    assert KYVERNO_KUSTOMIZATION_PATH.exists(), f"Missing {KYVERNO_KUSTOMIZATION_PATH}"
    with open(KYVERNO_KUSTOMIZATION_PATH, "r", encoding="utf-8") as f:
        kust = yaml.safe_load(f)

    resources = kust.get("resources", [])
    assert "06-policy-exception-mysql.yaml" in resources, "06-policy-exception-mysql.yaml must be in resources list"


def test_kustomize_build_policies():
    """Verify kubectl kustomize succeeds on deploy/policies."""
    res = subprocess.run(
        ["kubectl", "kustomize", str(POLICIES_DIR)],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"kubectl kustomize deploy/policies failed: {res.stderr}"
    assert "teastore-mysql-privilege-escalation-exception" in res.stdout


def test_kustomize_build_robusta():
    """Verify kubectl kustomize succeeds on deploy/platform/smart-alerting-robusta."""
    res = subprocess.run(
        ["kubectl", "kustomize", str(ROBUSTA_DIR)],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"kubectl kustomize deploy/platform/smart-alerting-robusta failed: {res.stderr}"
    assert "robusta-runner-cluster-role" in res.stdout


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
