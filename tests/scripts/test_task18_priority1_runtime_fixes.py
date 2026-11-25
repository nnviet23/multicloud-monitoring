"""Tests for Task 18 / Priority 1 runtime fixes."""
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_networkpolicy_allows_egress_9108():
    path = ROOT / "deploy/policies/12-monitoring-storage-networkpolicy.yaml"
    docs = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    allow_mon = next(d for d in docs if d["metadata"]["name"] == "allow-monitoring-traffic")
    egress_ports = [
        p["port"]
        for rule in allow_mon["spec"]["egress"]
        for p in rule.get("ports", [])
        if p.get("protocol") == "TCP"
    ]
    assert 9108 in egress_ports, "TCP port 9108 must be in allow-monitoring-traffic egress"


def test_chaos_faults_uses_statefulset_teastore_db():
    text = (ROOT / "tests/chaos/run_service_faults.py").read_text(encoding="utf-8")
    assert "statefulset/teastore-db" in text
    assert "deploy/teastore-db" not in text


def test_validate_otel_rules_checks_traces_pipeline():
    text = (ROOT / "tests/scripts/validate_otel_rules.py").read_text(encoding="utf-8")
    assert '"traces" in service_pipelines' in text
    assert '"traces/servicegraph" in service_pipelines' not in text


def test_infra_cli_pulls_matching_k3s_image():
    text = (ROOT / "infra/cli.py").read_text(encoding="utf-8")
    assert '"rancher/k3s:v1.31.2-k3s1"' in text
    assert '"rancher/k3s:v1.31.4-k3s1"' not in text


def test_makefile_sync_secrets_uses_hub_ctx():
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    for line in text.splitlines():
        if "kubectl" in line and "deploy/clusters/hub" in line:
            assert "--context $(HUB_CTX)" in line
            break
    else:
        raise AssertionError("sync-secrets kubectl apply -k deploy/clusters/hub not found")


def test_prometheus_has_pyrra_rules_sidecar():
    path = ROOT / "deploy/platform/metrics-thanos/03-statefulset-prometheus.yaml"
    sts = yaml.safe_load(path.read_text(encoding="utf-8"))
    spec = sts["spec"]["template"]["spec"]
    containers = {c["name"]: c for c in spec["containers"]}

    assert "pyrra-rules-sidecar" in containers
    sidecar = containers["pyrra-rules-sidecar"]
    assert sidecar["image"] == "kiwigrid/k8s-sidecar:1.28.0"
    assert sidecar["securityContext"]["allowPrivilegeEscalation"] is False
    assert sidecar["securityContext"]["capabilities"]["drop"] == ["ALL"]
    assert sidecar["resources"]["requests"] == {"cpu": "20m", "memory": "32Mi"}
    assert sidecar["resources"]["limits"] == {"memory": "64Mi"}

    env = {e["name"]: e["value"] for e in sidecar["env"]}
    assert env["LABEL"] == "pyrra.dev/rule"
    assert env["FOLDER"] == "/etc/prometheus/rules/pyrra"
    assert env["RESOURCE"] == "configmap"
    assert env["NAMESPACE"] == "monitoring"

    volumes = {v["name"]: v for v in spec["volumes"]}
    assert "pyrra-rules" in volumes
    assert "emptyDir" in volumes["pyrra-rules"]

    for cname in ("prometheus", "pyrra-rules-sidecar"):
        mounts = {m["name"]: m["mountPath"] for m in containers[cname]["volumeMounts"]}
        assert mounts.get("pyrra-rules") == "/etc/prometheus/rules/pyrra"
