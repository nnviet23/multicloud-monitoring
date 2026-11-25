import os
import shutil
import subprocess

def _run_kubectl_kustomize(target_dir):
    kubectl = shutil.which("kubectl") or "kubectl"
    cmd = [kubectl, "kustomize", target_dir]
    # On Windows, shell=False works cleanly when kubectl is resolved via shutil.which or in PATH
    return subprocess.run(cmd, capture_output=True, text=True)

def test_root_policies_directory_eliminated():
    assert not os.path.exists("policies"), "Root policies/ directory still exists"

def test_integrations_relocated_under_deploy():
    assert not os.path.exists("deploy/integrations"), "deploy/integrations directory should be purged"
    assert not os.path.exists("integrations"), "Legacy root integrations/ directory still exists"

def test_kustomize_build_aws_cluster():
    result = _run_kubectl_kustomize("deploy/clusters/aws")
    assert result.returncode == 0, f"AWS cluster kustomize build failed: {result.stderr}"

def test_kustomize_build_azure_cluster():
    result = _run_kubectl_kustomize("deploy/clusters/azure")
    assert result.returncode == 0, f"Azure cluster kustomize build failed: {result.stderr}"

def test_kustomize_build_hub_cluster():
    result = _run_kubectl_kustomize("deploy/clusters/hub")
    assert result.returncode == 0, f"Hub cluster kustomize build failed: {result.stderr}"

def test_no_fictional_crd_cluster_telemetry_policy():
    for root, dirs, files in os.walk("deploy"):
        for f in files:
            if f.endswith((".yaml", ".yml")):
                p = os.path.join(root, f)
                with open(p, "r", encoding="utf-8", errors="ignore") as fp:
                    content = fp.read()
                    assert "ClusterTelemetryPolicy" not in content, f"Phantom CRD found in {p}"

def test_makefile_references_deploy_integrations():
    with open("Makefile", "r", encoding="utf-8") as f:
        makefile = f.read()
    assert "deploy/integrations" not in makefile, "Makefile should not reference deploy/integrations"
    assert "validate-integrations" not in makefile, "Makefile should not reference validate-integrations"
