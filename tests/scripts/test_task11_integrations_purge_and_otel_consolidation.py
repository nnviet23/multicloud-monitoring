import os
import shutil
import subprocess
import unittest
import yaml
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_kubectl_kustomize(target_dir):
    kubectl = shutil.which("kubectl") or "kubectl"
    cmd = [kubectl, "kustomize", target_dir]
    return subprocess.run(cmd, capture_output=True, text=True)


class TestTask11IntegrationsPurgeAndOtelConsolidation(unittest.TestCase):

    def test_deploy_integrations_purged(self):
        """Verify the entire deploy/integrations directory is purged."""
        integrations_dir = REPO_ROOT / "deploy" / "integrations"
        self.assertFalse(integrations_dir.exists(), "deploy/integrations directory must not exist on disk")

    def test_workloads_cloudflare_vpn_purged(self):
        """Verify workloads/cloudflare-vpn directory is purged."""
        cf_dir = REPO_ROOT / "workloads" / "cloudflare-vpn"
        self.assertFalse(cf_dir.exists(), "workloads/cloudflare-vpn directory must not exist on disk")

    def test_cluster_overlays_no_integration_references(self):
        """Verify aws, azure, and hub kustomization.yaml do not reference integrations or cloudflare-vpn."""
        for cluster in ["aws", "azure", "hub"]:
            kust_path = REPO_ROOT / "deploy" / "clusters" / cluster / "kustomization.yaml"
            self.assertTrue(kust_path.exists(), f"{kust_path} must exist")
            content = kust_path.read_text(encoding="utf-8")
            self.assertNotIn("integrations", content, f"{kust_path} contains reference to integrations")
            self.assertNotIn("cloudflare-vpn", content, f"{kust_path} contains reference to cloudflare-vpn")

    def test_cluster_identity_patches_cleaned(self):
        """Verify aws and azure patch-cluster-identity.yaml do not mount or reference integrations."""
        for cluster in ["aws", "azure"]:
            patch_path = REPO_ROOT / "deploy" / "clusters" / cluster / "patches" / "patch-cluster-identity.yaml"
            self.assertTrue(patch_path.exists(), f"{patch_path} must exist")
            content = patch_path.read_text(encoding="utf-8")
            self.assertNotIn("integrations", content, f"{patch_path} contains reference to integrations")
            self.assertNotIn("integration-", content, f"{patch_path} contains integration volume references")

    def test_makefile_no_validate_integrations(self):
        """Verify Makefile does not reference validate-integrations target."""
        makefile_path = REPO_ROOT / "Makefile"
        content = makefile_path.read_text(encoding="utf-8")
        self.assertNotIn("validate-integrations", content, "Makefile must not contain validate-integrations target")
        self.assertNotIn("deploy/integrations", content, "Makefile must not contain deploy/integrations")

    def test_otel_edge_collector_receivers(self):
        """Verify deploy/platform/otel-collector/edge/02-configmap.yaml contains required standard receivers."""
        edge_cm_path = REPO_ROOT / "deploy" / "platform" / "otel-collector" / "edge" / "02-configmap.yaml"
        self.assertTrue(edge_cm_path.exists(), f"{edge_cm_path} must exist")
        with open(edge_cm_path, "r", encoding="utf-8") as f:
            cm = yaml.safe_load(f)
        cfg_str = cm.get("data", {}).get("config.yaml", "")
        cfg = yaml.safe_load(cfg_str)
        receivers = cfg.get("receivers", {})
        expected_receivers = ["otlp", "hostmetrics", "kubeletstats", "filelog", "prometheus/internal"]
        for r in expected_receivers:
            self.assertIn(r, receivers, f"Receiver '{r}' must exist in edge collector configmap")

    def test_kustomize_build_all_clusters(self):
        """Verify aws, azure, and hub cluster overlays build cleanly with kubectl kustomize."""
        for cluster in ["aws", "azure", "hub"]:
            target = f"deploy/clusters/{cluster}"
            res = _run_kubectl_kustomize(target)
            self.assertEqual(res.returncode, 0, f"kubectl kustomize {target} failed: {res.stderr}")


if __name__ == "__main__":
    unittest.main()
