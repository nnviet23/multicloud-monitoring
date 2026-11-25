#!/usr/bin/env python3
"""
Test Suite for Task 12 (Task 3): Centralize & Standardize 10 Grafana Dashboards from Upstream Reference
"""

import json
import subprocess
import unittest
import yaml
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARDS_DIR = REPO_ROOT / "deploy" / "platform" / "visualization-grafana" / "dashboards"
KUSTOMIZATION_PATH = REPO_ROOT / "deploy" / "platform" / "visualization-grafana" / "kustomization.yaml"

EXPECTED_DASHBOARDS = [
    "01-platform-overview-golden-signals.json",
    "02-host-compute-node-exporter.json",
    "03-kubernetes-cluster-overview.json",
    "04-jvm-teastore-runtime.json",
    "05-mysql-database-overview.json",
    "06-wan-network-latency.json",
    "07-cross-cluster-service-graph.json",
    "08-slo-governance-pyrra-list.json",
    "09-slo-governance-pyrra-detail.json",
    "10-logs-traces-deepdive.json",
]

OBSOLETE_DASHBOARDS = [
    "logs-traces-deepdive.json",
    "mc-cost-telemetry.json",
    "mc-executive-overview.json",
    "slo-governance.json",
]


class TestTask12DashboardsCentralization(unittest.TestCase):

    def test_exactly_ten_standardized_dashboards_exist(self):
        """Assert exactly 10 standardized dashboard files exist and obsolete ones are removed."""
        self.assertTrue(DASHBOARDS_DIR.is_dir(), f"Dashboards directory missing: {DASHBOARDS_DIR}")
        actual_files = sorted([f.name for f in DASHBOARDS_DIR.glob("*.json")])
        self.assertEqual(actual_files, sorted(EXPECTED_DASHBOARDS),
                         f"Dashboard files mismatch: expected {sorted(EXPECTED_DASHBOARDS)}, got {actual_files}")

        for old in OBSOLETE_DASHBOARDS:
            self.assertFalse((DASHBOARDS_DIR / old).exists(), f"Old obsolete dashboard still exists: {old}")

    def test_all_dashboards_valid_json_and_have_panels(self):
        """Assert all 10 dashboards are valid JSON, contain panels, and have standard English titles."""
        expected_titles = {
            "01-platform-overview-golden-signals.json": ["Platform Overview", "Platform Overview - Golden Signals"],
            "02-host-compute-node-exporter.json": ["Node Exporter Full", "Host Compute / Node Exporter Full"],
            "03-kubernetes-cluster-overview.json": ["Kubernetes / Compute Resources / Cluster", "Kubernetes Cluster Overview"],
            "04-jvm-teastore-runtime.json": ["JVM (Micrometer)", "JVM Runtime - TeaStore"],
            "05-mysql-database-overview.json": ["MySQL Overview", "MySQL Database Overview"],
            "06-wan-network-latency.json": ["WAN Network & Inter-Cluster Latency", "WAN Network Latency"],
            "07-cross-cluster-service-graph.json": ["Cross-Cluster Service Graph", "Cross-Cluster Service Graph (Tempo)"],
            "08-slo-governance-pyrra-list.json": ["Pyrra - List"],
            "09-slo-governance-pyrra-detail.json": ["Pyrra - Detail"],
            "10-logs-traces-deepdive.json": ["Logs & Traces Deep-Dive", "Logs & Traces Deepdive"],
        }

        for fname in EXPECTED_DASHBOARDS:
            fpath = DASHBOARDS_DIR / fname
            self.assertTrue(fpath.exists(), f"Missing expected dashboard: {fname}")
            with open(fpath, "r", encoding="utf-8") as fp:
                data = json.load(fp)

            self.assertIsInstance(data, dict, f"{fname} is not a valid JSON object")
            title = data.get("title", "")
            self.assertTrue(title, f"{fname} title is empty")
            valid_titles = expected_titles.get(fname, [])
            self.assertTrue(
                any(t.lower() in title.lower() for t in valid_titles),
                f"{fname} title '{title}' does not match expected English titles: {valid_titles}"
            )

            # Check panels (support either top-level panels or legacy rows with panels)
            panels = data.get("panels", [])
            rows = data.get("rows", [])
            total_panels = len(panels) + sum(len(r.get("panels", [])) for r in rows)
            self.assertGreater(total_panels, 0, f"{fname} has no panels")

    def test_datasource_normalization_no_unreplaced_inputs(self):
        """Assert no __inputs block or unresolved ${DS_PROMETHEUS} in any dashboard."""
        for fname in EXPECTED_DASHBOARDS:
            fpath = DASHBOARDS_DIR / fname
            if not fpath.exists():
                continue
            with open(fpath, "r", encoding="utf-8") as fp:
                raw = fp.read()
                data = json.loads(raw)

            self.assertNotIn("__inputs", data, f"'{fname}' contains Grafana __inputs block")
            self.assertNotIn("${DS_PROMETHEUS}", raw, f"'{fname}' contains unreplaced ${{DS_PROMETHEUS}}")
            self.assertNotIn("${ds_prometheus}", raw, f"'{fname}' contains unreplaced ${{ds_prometheus}}")

    def test_kustomization_references_all_ten_dashboards(self):
        """Assert visualization-grafana/kustomization.yaml loads all 10 dashboards in configMapGenerator."""
        self.assertTrue(KUSTOMIZATION_PATH.exists(), f"Kustomization missing: {KUSTOMIZATION_PATH}")
        with open(KUSTOMIZATION_PATH, "r", encoding="utf-8") as fp:
            kust = yaml.safe_load(fp)

        cm_gens = kust.get("configMapGenerator", [])
        dash_gen = next((cm for cm in cm_gens if cm.get("name") == "grafana-dashboards"), None)
        self.assertIsNotNone(dash_gen, "ConfigMapGenerator 'grafana-dashboards' not found")

        generator_files = dash_gen.get("files", [])
        for fname in EXPECTED_DASHBOARDS:
            expected_ref = f"dashboards/{fname}"
            self.assertIn(expected_ref, generator_files,
                          f"Dashboard reference '{expected_ref}' missing in configMapGenerator")
        self.assertEqual(len(generator_files), 10,
                         f"configMapGenerator should reference exactly 10 files, found: {generator_files}")

    def test_kustomize_build_hub_cluster_succeeds(self):
        """Assert kubectl kustomize deploy/clusters/hub exits 0."""
        cmd = ["kubectl", "kustomize", str(REPO_ROOT / "deploy" / "clusters" / "hub")]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"kubectl kustomize build hub failed: {res.stderr}")


if __name__ == "__main__":
    unittest.main()
