#!/usr/bin/env python3
"""
Test Suite for Task 5: Deduplicate SRE Alerts & Integrate Infrastructure Rules
Updated for modular domain-specific rule files in deploy/platform/metrics-thanos/rules/
Audit findings: ALT-01, ALT-02
"""

import os
import sys
import unittest
import yaml
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RULES_DIR = REPO_ROOT / "deploy" / "platform" / "metrics-thanos" / "rules"
MYSQL_ALERTS_PATH = REPO_ROOT / "deploy" / "integrations" / "mysql" / "alerts.yaml"
K8S_ALERTS_PATH = REPO_ROOT / "deploy" / "integrations" / "kubernetes" / "alerts.yaml"


class TestTask5AlertRules(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.assertTrue(cls, RULES_DIR.exists() and RULES_DIR.is_dir(), f"Rules directory not found: {RULES_DIR}")
        cls.data = {}
        for rule_file in sorted(RULES_DIR.glob("*.yaml")):
            with open(rule_file, "r", encoding="utf-8") as f:
                cls.data[rule_file.name] = f.read()
        cls.assertTrue(cls, len(cls.data) >= 8, f"Expected at least 8 modular rule files, got {len(cls.data)}")

    def test_deduplicate_servicegraph_alert_alt01(self):
        """ALT-01: CrossClusterCallFailureRateHigh must be removed to avoid duplication with Pyrra SLO and RED."""
        self.assertNotIn("servicegraph-alerts.yaml", self.data,
                         "servicegraph-alerts.yaml should not exist in modular rules")

        # Verify across all embedded files in data that CrossClusterCallFailureRateHigh does not exist
        for filename, raw_yaml in self.data.items():
            parsed = yaml.safe_load(raw_yaml)
            if not parsed or not isinstance(parsed, dict):
                continue
            for group in parsed.get("groups", []):
                self.assertNotEqual(group.get("name"), "servicegraph-cross-cluster",
                                    f"Found redundant rule group 'servicegraph-cross-cluster' in {filename}")
                for rule in group.get("rules", []):
                    alert_name = rule.get("alert")
                    self.assertNotEqual(alert_name, "CrossClusterCallFailureRateHigh",
                                        f"Redundant alert 'CrossClusterCallFailureRateHigh' found in {filename}")

    def test_microservice_high_error_rate_labels_alt01(self):
        """ALT-01: MicroserviceHighErrorRate must have severity: info and strategy: signoz-diagnostic-only."""
        found = False
        for filename, raw_yaml in self.data.items():
            parsed = yaml.safe_load(raw_yaml)
            if not parsed or not isinstance(parsed, dict):
                continue
            for group in parsed.get("groups", []):
                for rule in group.get("rules", []):
                    if rule.get("alert") == "MicroserviceHighErrorRate":
                        found = True
                        labels = rule.get("labels", {})
                        self.assertEqual(labels.get("severity"), "info",
                                         f"MicroserviceHighErrorRate severity must be 'info', got '{labels.get('severity')}'")
                        self.assertEqual(labels.get("category"), "availability",
                                         f"MicroserviceHighErrorRate category must be 'availability', got '{labels.get('category')}'")
                        self.assertEqual(labels.get("strategy"), "signoz-diagnostic-only",
                                         f"MicroserviceHighErrorRate strategy must be 'signoz-diagnostic-only', got '{labels.get('strategy')}'")
        self.assertTrue(found, "MicroserviceHighErrorRate alert not found in any modular rules file")

    def test_mysql_alerts_integrated_alt02(self):
        """ALT-02: Ensure all essential MySQL alert rule groups are incorporated in 03-mysql-rules.yaml."""
        self.assertIn("03-mysql-rules.yaml", self.data,
                      "03-mysql-rules.yaml missing in modular rules")

        cm_mysql = yaml.safe_load(self.data["03-mysql-rules.yaml"])
        cm_rules = {r.get("alert") for g in cm_mysql.get("groups", []) for r in g.get("rules", []) if "alert" in r}

        for essential in ["MysqlDown", "MysqlTooManyConnections", "MysqlSlowQueries", "MysqlRestarted"]:
            self.assertIn(essential, cm_rules, f"Missing essential MySQL alert {essential} in 03-mysql-rules.yaml")

    def test_kubernetes_alerts_integrated_alt02(self):
        """ALT-02: Ensure all essential Kubernetes alert rule groups are incorporated in 02-kubernetes-rules.yaml."""
        self.assertIn("02-kubernetes-rules.yaml", self.data,
                      "02-kubernetes-rules.yaml missing in modular rules")

        cm_k8s = yaml.safe_load(self.data["02-kubernetes-rules.yaml"])
        cm_rules = {r.get("alert") for g in cm_k8s.get("groups", []) for r in g.get("rules", []) if "alert" in r}

        for essential in ["KubernetesNodeReady", "KubernetesPodCrashLooping", "KubernetesDeploymentReplicasMismatch"]:
            self.assertIn(essential, cm_rules, f"Missing essential Kubernetes alert {essential} in 02-kubernetes-rules.yaml")

    def test_all_rules_validity_and_no_duplicates(self):
        """Verify all modular Prometheus alert rule files are valid YAML, properly formatted, and no duplicate alerts exist."""
        all_alerts = {}
        for filename, raw_yaml in self.data.items():
            self.assertTrue(filename.endswith(".yaml") or filename.endswith(".yml"),
                            f"Rule file key {filename} must have .yaml or .yml extension")
            parsed = yaml.safe_load(raw_yaml)
            self.assertIsInstance(parsed, dict, f"Content of {filename} is not a valid YAML dict")
            self.assertIn("groups", parsed, f"{filename} does not contain 'groups'")
            
            for group in parsed["groups"]:
                self.assertIn("name", group, f"Group in {filename} missing 'name'")
                self.assertIn("rules", group, f"Group {group.get('name')} in {filename} missing 'rules'")
                for rule in group["rules"]:
                    alert_name = rule.get("alert")
                    self.assertIsNotNone(alert_name, f"Rule in {group.get('name')} in {filename} missing 'alert'")
                    self.assertIn("expr", rule, f"Alert {alert_name} in {filename} missing 'expr'")
                    self.assertIn("for", rule, f"Alert {alert_name} in {filename} missing 'for'")
                    self.assertIn("labels", rule, f"Alert {alert_name} in {filename} missing 'labels'")
                    self.assertIn("annotations", rule, f"Alert {alert_name} in {filename} missing 'annotations'")
                    self.assertIn("severity", rule["labels"], f"Alert {alert_name} missing 'severity' label")

                    # Duplicate check
                    self.assertNotIn(alert_name, all_alerts,
                                     f"Duplicate alert name '{alert_name}' found in {filename} (previously defined in {all_alerts.get(alert_name)})")
                    all_alerts[alert_name] = filename


if __name__ == "__main__":
    unittest.main()
