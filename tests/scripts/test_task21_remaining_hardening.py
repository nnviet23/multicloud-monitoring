from pathlib import Path
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_robusta_runner_non_root():
    path = REPO_ROOT / "deploy/platform/smart-alerting-robusta/03-runner-deployment.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    pod_sec = doc["spec"]["template"]["spec"].get("securityContext", {})
    containers = doc["spec"]["template"]["spec"]["containers"]
    runner_sec = containers[0].get("securityContext", {})
    assert pod_sec.get("runAsNonRoot") is True or runner_sec.get("runAsNonRoot") is True


def test_disallow_root_policy_scope():
    path = REPO_ROOT / "deploy/policies/03-disallow-root-user.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert doc["spec"]["validationActions"] == ["Deny"]
    conditions_text = " ".join(c.get("expression", "") for c in doc["spec"].get("matchConditions", []))
    for ns in ("monitoring", "storage"):
        assert ns in conditions_text


def test_networkpolicy_peer_selectors_complete():
    p11 = REPO_ROOT / "deploy/policies/11-allow-core-traffic-networkpolicy.yaml"
    docs11 = list(yaml.safe_load_all(p11.read_text(encoding="utf-8")))
    for doc in docs11:
        if not doc or doc.get("kind") != "NetworkPolicy":
            continue
        for rule in doc["spec"].get("ingress", []):
            ports = [p.get("port") for p in rule.get("ports", [])]
            if 8080 in ports:
                assert "from" in rule and len(rule["from"]) > 0
        for rule in doc["spec"].get("egress", []):
            ports = [p.get("port") for p in rule.get("ports", [])]
            if 31111 in ports or 31112 in ports:
                assert "to" in rule and len(rule["to"]) > 0

    p12 = REPO_ROOT / "deploy/policies/12-monitoring-storage-networkpolicy.yaml"
    docs12 = list(yaml.safe_load_all(p12.read_text(encoding="utf-8")))
    for doc in docs12:
        if not doc or doc.get("kind") != "NetworkPolicy":
            continue
        for rule in doc["spec"].get("ingress", []):
            ports = [p.get("port") for p in rule.get("ports", [])]
            if 9001 in ports:
                assert "from" in rule and len(rule["from"]) > 0


def test_sync_hosts_targets_mc_monitoring_net_and_checks_rollout():
    cli_text = (REPO_ROOT / "infra/cli.py").read_text(encoding="utf-8")
    start = cli_text.index("def sync_hosts_cmd(")
    end = cli_text.index("\n@app.command", start) if "\n@app.command" in cli_text[start:] else len(cli_text)
    fn_body = cli_text[start:end]
    assert "NETWORK_NAME" in fn_body or "mc-monitoring-net" in fn_body
    assert "NetworkSettings.Networks" in fn_body
    assert "returncode" in fn_body
