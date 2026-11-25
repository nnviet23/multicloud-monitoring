#!/usr/bin/env python3
"""
Test Suite for Task 4: Normalize Grafana Dashboards Datasource & Wire OTel Edge Pipelines
Audit findings: DSH-01, OBS-02, OBS-03
"""

import json
import os
import sys
import unittest
import yaml
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestTask4DashboardsAndOtel(unittest.TestCase):

    def test_mysql_dashboard_datasource(self):
        """DSH-01: Verify mysql dashboard has no __inputs block and no ${DS_PROMETHEUS}."""
        path = REPO_ROOT / "deploy" / "platform" / "visualization-grafana" / "dashboards" / "05-mysql-database-overview.json"
        self.assertTrue(path.exists(), f"MySQL dashboard not found at {path}")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
            data = json.loads(content)

        self.assertNotIn("__inputs", data, f"'__inputs' block found in {path}")
        self.assertNotIn("${DS_PROMETHEUS}", content, f"'${{DS_PROMETHEUS}}' found in {path}")
        self.assertNotIn("${ds_prometheus}", content, f"'${{ds_prometheus}}' found in {path}")
        self.assertIn("thanos-query-ds", content, f"'thanos-query-ds' not found in {path}")

    def test_host_compute_dashboard_datasource(self):
        """DSH-01: Verify host-compute dashboard has no ${ds_prometheus} and uses thanos-query-ds."""
        path = REPO_ROOT / "deploy" / "platform" / "visualization-grafana" / "dashboards" / "02-host-compute-node-exporter.json"
        self.assertTrue(path.exists(), f"Host compute dashboard not found at {path}")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
            data = json.loads(content)

        self.assertNotIn("${ds_prometheus}", content, f"'${{ds_prometheus}}' found in {path}")
        self.assertNotIn("${DS_PROMETHEUS}", content, f"'${{DS_PROMETHEUS}}' found in {path}")
        self.assertIn("thanos-query-ds", content, f"'thanos-query-ds' not found in {path}")

    def test_otel_edge_kubeletstats_receiver(self):
        """OBS-02: Verify kubeletstats receiver exists and is wired in metrics pipeline."""
        configmap_path = REPO_ROOT / "deploy" / "platform" / "otel-collector" / "edge" / "02-configmap.yaml"
        self.assertTrue(configmap_path.exists(), f"ConfigMap file not found: {configmap_path}")

        with open(configmap_path, "r", encoding="utf-8") as f:
            cm = yaml.safe_load(f)

        raw_cfg = cm.get("data", {}).get("config.yaml", "")
        cfg = yaml.safe_load(raw_cfg)

        # 1. Receiver check
        receivers = cfg.get("receivers", {})
        self.assertIn("kubeletstats", receivers, "kubeletstats receiver is missing in edge collector")
        ks = receivers["kubeletstats"]
        self.assertEqual(ks.get("endpoint"), "https://${env:K8S_NODE_NAME}:10250")
        self.assertFalse(ks.get("insecure_skip_verify"))
        self.assertIn("node", ks.get("metric_groups", []))
        self.assertIn("pod", ks.get("metric_groups", []))
        self.assertIn("container", ks.get("metric_groups", []))

        # 2. Pipeline check
        metrics_pipeline = cfg.get("service", {}).get("pipelines", {}).get("metrics", {})
        pipe_receivers = metrics_pipeline.get("receivers", [])
        self.assertIn("kubeletstats", pipe_receivers, "kubeletstats missing from service.pipelines.metrics.receivers")

        # 3. Deployment downward API check
        deployment_path = REPO_ROOT / "deploy" / "platform" / "otel-collector" / "edge" / "03-deployment.yaml"
        self.assertTrue(deployment_path.exists(), f"Deployment file not found: {deployment_path}")
        with open(deployment_path, "r", encoding="utf-8") as f:
            deploy_yaml = yaml.safe_load(f)
        containers = deploy_yaml.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        self.assertTrue(containers, "No containers in edge collector deployment")
        env_vars = {e.get("name"): e for e in containers[0].get("env", []) if isinstance(e, dict)}
        self.assertIn("K8S_NODE_NAME", env_vars, "K8S_NODE_NAME missing from edge deployment container env")
        field_ref = env_vars["K8S_NODE_NAME"].get("valueFrom", {}).get("fieldRef", {})
        self.assertEqual(field_ref.get("fieldPath"), "spec.nodeName", "K8S_NODE_NAME must reference spec.nodeName")

    def test_otel_edge_probabilistic_sampler(self):
        """OBS-03: Verify tail_sampling preserves errors, >=1500ms latency, and 20% probabilistic in traces pipeline."""
        configmap_path = REPO_ROOT / "deploy" / "platform" / "otel-collector" / "edge" / "02-configmap.yaml"
        with open(configmap_path, "r", encoding="utf-8") as f:
            cm = yaml.safe_load(f)

        raw_cfg = cm.get("data", {}).get("config.yaml", "")
        cfg = yaml.safe_load(raw_cfg)

        # 1. Processor check
        processors = cfg.get("processors", {})
        self.assertIn("tail_sampling", processors, "tail_sampling processor missing in edge collector")
        ts = processors["tail_sampling"]
        policies = ts.get("policies", [])
        self.assertTrue(
            any(p.get("type") == "status_code" and "ERROR" in p.get("status_code", {}).get("status_codes", []) for p in policies),
            "tail_sampling must preserve ERROR status_code traces"
        )
        self.assertTrue(
            any(p.get("type") == "latency" and float(p.get("latency", {}).get("threshold_ms", 0)) >= 1500 for p in policies),
            "tail_sampling must preserve latency >= 1500ms traces"
        )
        self.assertTrue(
            any(p.get("type") == "probabilistic" and float(p.get("probabilistic", {}).get("sampling_percentage", 0)) == 20.0 for p in policies),
            "tail_sampling must include 20% probabilistic policy"
        )

        # 2. Pipeline check
        traces_pipeline = cfg.get("service", {}).get("pipelines", {}).get("traces", {})
        pipe_processors = traces_pipeline.get("processors", [])
        self.assertIn("tail_sampling", pipe_processors, "tail_sampling missing from service.pipelines.traces.processors")
        self.assertEqual(pipe_processors[0], "memory_limiter", "Pipeline must start with memory_limiter")


if __name__ == "__main__":
    unittest.main()
