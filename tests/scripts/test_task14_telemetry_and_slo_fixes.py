#!/usr/bin/env python3
"""
Test Suite for Task 14 (Plan Task 1): Telemetry Pipeline & Observability Fixes
1. Edge tail_sampling preserving 100% errors & slow traces (>1500ms) + 20% probabilistic
2. Azure Spoke MySQL receiver ConfigMap & Deployment patch
3. Pyrra Kubernetes operator container & Latency SLO
4. Grafana Panel 7 AI Anomaly Detection & Reconstruction Error Dual Y-Axis
"""

import json
import unittest
import yaml
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestTask14TelemetryAndSloFixes(unittest.TestCase):

    def test_edge_otel_tail_sampling(self):
        """Edge collector must use tail_sampling instead of blind probabilistic_sampler."""
        cm_path = REPO_ROOT / "deploy" / "platform" / "otel-collector" / "edge" / "02-configmap.yaml"
        self.assertTrue(cm_path.exists(), f"Missing {cm_path}")
        with open(cm_path, "r", encoding="utf-8") as f:
            cm = yaml.safe_load(f)

        cfg = yaml.safe_load(cm["data"]["config.yaml"])
        processors = cfg.get("processors", {})

        self.assertNotIn("probabilistic_sampler", processors, "Blind probabilistic_sampler must be removed")
        self.assertIn("tail_sampling", processors, "tail_sampling processor must be configured")

        ts = processors["tail_sampling"]
        self.assertEqual(ts.get("decision_wait"), "2s")
        self.assertEqual(ts.get("num_traces"), 2000)
        self.assertEqual(ts.get("expected_new_traces_per_sec"), 100)

        policies = {p.get("name"): p for p in ts.get("policies", []) if isinstance(p, dict)}
        self.assertTrue(len(policies) >= 3, "tail_sampling must have at least 3 policies")

        status_policies = [p for p in policies.values() if p.get("type") == "status_code"]
        self.assertTrue(status_policies, "Missing status_code policy in tail_sampling")
        self.assertIn("ERROR", status_policies[0].get("status_code", {}).get("status_codes", []))

        latency_policies = [p for p in policies.values() if p.get("type") == "latency"]
        self.assertTrue(latency_policies, "Missing latency policy in tail_sampling")
        self.assertGreaterEqual(latency_policies[0].get("latency", {}).get("threshold_ms", 0), 1500)

        prob_policies = [p for p in policies.values() if p.get("type") == "probabilistic"]
        self.assertTrue(prob_policies, "Missing probabilistic policy in tail_sampling")
        self.assertEqual(float(prob_policies[0].get("probabilistic", {}).get("sampling_percentage", 0)), 20.0)

        traces_procs = cfg["service"]["pipelines"]["traces"]["processors"]
        self.assertEqual(traces_procs[0], "memory_limiter", "memory_limiter must be first")
        self.assertIn("tail_sampling", traces_procs, "tail_sampling must be in traces pipeline")
        self.assertNotIn("probabilistic_sampler", traces_procs, "probabilistic_sampler must not be in traces pipeline")

    def test_azure_spoke_mysql_receiver(self):
        """Azure Spoke must configure and mount mysql receiver."""
        mysql_cm_path = REPO_ROOT / "deploy" / "clusters" / "azure" / "patches" / "01-configmap-mysql-receiver.yaml"
        self.assertTrue(mysql_cm_path.exists(), f"Missing {mysql_cm_path}")
        with open(mysql_cm_path, "r", encoding="utf-8") as f:
            mysql_cm = yaml.safe_load(f)

        self.assertEqual(mysql_cm.get("kind"), "ConfigMap")
        self.assertEqual(mysql_cm.get("metadata", {}).get("namespace"), "monitoring")
        data = mysql_cm.get("data", {})
        self.assertIn("mysql.yaml", data, "mysql.yaml key missing from ConfigMap")

        mysql_cfg = yaml.safe_load(data["mysql.yaml"])
        mysql_recv = mysql_cfg.get("receivers", {}).get("mysql", {})
        self.assertEqual(mysql_recv.get("endpoint"), "teastore-db.teastore.svc.cluster.local:3306")
        self.assertEqual(mysql_recv.get("username"), "root")
        self.assertEqual(mysql_recv.get("password"), "${env:MYSQL_ROOT_PASSWORD}")
        self.assertEqual(mysql_recv.get("collection_interval"), "15s")

        metrics_recvs = mysql_cfg.get("service", {}).get("pipelines", {}).get("metrics", {}).get("receivers", [])
        self.assertIn("mysql", metrics_recvs)

        # Check kustomization.yaml registers the ConfigMap
        kust_path = REPO_ROOT / "deploy" / "clusters" / "azure" / "kustomization.yaml"
        with open(kust_path, "r", encoding="utf-8") as f:
            kust = yaml.safe_load(f)
        self.assertIn("patches/01-configmap-mysql-receiver.yaml", kust.get("resources", []))

        # Check patch-cluster-identity.yaml mounts and passes args + MYSQL_ROOT_PASSWORD
        patch_path = REPO_ROOT / "deploy" / "clusters" / "azure" / "patches" / "patch-cluster-identity.yaml"
        with open(patch_path, "r", encoding="utf-8") as f:
            patch = yaml.safe_load(f)

        container = patch["spec"]["template"]["spec"]["containers"][0]
        args = container.get("args", [])
        self.assertIn("--config=/etc/otelcol/config.yaml", args)
        self.assertIn("--config=/etc/otelcol-mysql/mysql.yaml", args)

        envs = {e["name"]: e for e in container.get("env", [])}
        self.assertIn("MYSQL_ROOT_PASSWORD", envs)
        secret_ref = envs["MYSQL_ROOT_PASSWORD"].get("valueFrom", {}).get("secretKeyRef", {})
        self.assertFalse(secret_ref.get("optional"), "MYSQL_ROOT_PASSWORD secretKeyRef should be optional: false")

        mounts = {m["mountPath"]: m for m in container.get("volumeMounts", [])}
        self.assertIn("/etc/otelcol-mysql", mounts)

        volumes = {v["name"]: v for v in patch["spec"]["template"]["spec"].get("volumes", [])}
        self.assertIn("mysql-config", volumes)

    def test_pyrra_kubernetes_operator_and_latency_slo(self):
        """Pyrra deployment must run pyrra-kubernetes and define teastore-webui-latency SLO."""
        deploy_path = REPO_ROOT / "deploy" / "platform" / "slo-pyrra" / "02-deployment.yaml"
        with open(deploy_path, "r", encoding="utf-8") as f:
            deploy = yaml.safe_load(f)

        containers = {c["name"]: c for c in deploy["spec"]["template"]["spec"]["containers"]}
        self.assertIn("pyrra-api", containers)
        self.assertIn("pyrra-kubernetes", containers, "Missing pyrra-kubernetes container")

        pk = containers["pyrra-kubernetes"]
        self.assertEqual(pk["image"], "ghcr.io/pyrra-dev/pyrra:v0.7.3")
        args = pk.get("args", [])
        self.assertIn("kubernetes", args)
        self.assertIn("requests", pk.get("resources", {}))
        self.assertIn("limits", pk.get("resources", {}))

        rbac_path = REPO_ROOT / "deploy" / "platform" / "slo-pyrra" / "01-rbac.yaml"
        with open(rbac_path, "r", encoding="utf-8") as f:
            rbac_docs = [doc for doc in yaml.safe_load_all(f) if doc]
        cluster_role = next(d for d in rbac_docs if d.get("kind") == "ClusterRole")
        cm_rules = [r for r in cluster_role.get("rules", []) if "configmaps" in r.get("resources", [])]
        self.assertTrue(cm_rules, "ClusterRole/pyrra missing configmaps RBAC rule for --config-maps-only")
        self.assertIn("", cm_rules[0].get("apiGroups", []))
        for verb in ("get", "list", "watch", "create", "update", "patch", "delete"):
            self.assertIn(verb, cm_rules[0].get("verbs", []))

        slo_path = REPO_ROOT / "deploy" / "slos" / "teastore-slos.yaml"
        with open(slo_path, "r", encoding="utf-8") as f:
            slos = [doc for doc in yaml.safe_load_all(f) if doc]

        slo_map = {s["metadata"]["name"]: s for s in slos}
        self.assertIn("teastore-webui-availability", slo_map)
        self.assertIn("teastore-webui-latency", slo_map, "Missing teastore-webui-latency SLO")

        lat = slo_map["teastore-webui-latency"]
        self.assertEqual(lat.get("kind"), "ServiceLevelObjective")
        self.assertEqual(lat["spec"].get("target"), "95")
        self.assertEqual(lat["spec"].get("window"), "28d")
        indicator = lat["spec"].get("indicator", {})
        self.assertIn("latency", indicator)
        success_metric = indicator["latency"].get("success", {}).get("metric", "")
        self.assertIn("traces_service_graph_request_server_seconds_bucket", success_metric)
        self.assertIn('server="teastore-webui"', success_metric)

    def test_grafana_panel7_ai_anomaly_dual_yaxis(self):
        """Grafana Panel 7 must show AI Anomaly Detection & Reconstruction Error with Dual Y-Axis."""
        dash_path = REPO_ROOT / "deploy" / "platform" / "visualization-grafana" / "dashboards" / "01-platform-overview-golden-signals.json"
        with open(dash_path, "r", encoding="utf-8") as f:
            dash = json.load(f)

        panels = {p.get("id"): p for p in dash.get("panels", [])}
        self.assertIn(7, panels, "Panel 7 missing from dashboard")
        p7 = panels[7]

        self.assertEqual(p7.get("type"), "timeseries")
        self.assertEqual(p7.get("title"), "AI Anomaly Detection & Reconstruction Error")
        self.assertEqual(p7.get("datasource", {}).get("uid"), "${datasource}")

        targets = {t.get("refId"): t for t in p7.get("targets", [])}
        self.assertIn("A", targets)
        self.assertIn("B", targets)
        self.assertIn("ai_anomaly_likelihood_percent", targets["A"].get("expr", ""))
        self.assertIn("ai_reconstruction_error", targets["B"].get("expr", ""))

        overrides = p7.get("fieldConfig", {}).get("overrides", [])
        self.assertTrue(len(overrides) >= 2, "Panel 7 must have Dual Y-Axis fieldConfig overrides for A and B")

        override_by_ref = {}
        for ov in overrides:
            matcher = ov.get("matcher", {})
            if matcher.get("id") == "byFrameRefID":
                override_by_ref[matcher.get("options")] = {
                    prop["id"]: prop["value"] for prop in ov.get("properties", [])
                }

        self.assertIn("A", override_by_ref, "Missing override for refId A")
        self.assertEqual(override_by_ref["A"].get("unit"), "percent")
        self.assertIn("B", override_by_ref, "Missing override for refId B")
        self.assertEqual(override_by_ref["B"].get("unit"), "short")
        self.assertEqual(override_by_ref["B"].get("custom.axisPlacement"), "right")


if __name__ == "__main__":
    unittest.main()
