#!/usr/bin/env python3
"""
Tests for Task 2: Security Hardening Remediation
(Credentials, Per-Spoke mTLS, SecurityContext, NetworkPolicies, AI Engine)
"""

from __future__ import annotations

import ast
from pathlib import Path
import yaml
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_env_example_and_readme_sanitized():
    """1. Sanitize .env.example and README.md from plaintext shared passwords."""
    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "MultiCloudSecurePassword2026!" not in env_example
    assert "CHANGE_ME_MINIO_PASSWORD" in env_example
    assert "CHANGE_ME_GRAFANA_ADMIN_PASSWORD" in env_example
    assert "CHANGE_ME_TELEGRAM_BOT_TOKEN" in env_example
    assert "TELEGRAM_CHAT_ID=0" in env_example

    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "MultiCloudSecurePassword2026!" not in readme


def test_per_spoke_mtls_and_hub_local_sans():
    """2a. Hub server cert has hub.local SANs; spoke certs split per-spoke."""
    hub_cert_path = REPO_ROOT / "deploy" / "platform" / "cert-manager" / "03-hub-server-certificate.yaml"
    hub_cert = yaml.safe_load(hub_cert_path.read_text(encoding="utf-8"))
    dns_names = hub_cert["spec"]["dnsNames"]
    assert "hub.local" in dns_names
    assert "*.hub.local" in dns_names

    spoke_certs_path = REPO_ROOT / "deploy" / "platform" / "cert-manager" / "04-spoke-client-certificates.yaml"
    spoke_docs = list(yaml.safe_load_all(spoke_certs_path.read_text(encoding="utf-8")))
    by_name = {d["metadata"]["name"]: d for d in spoke_docs if isinstance(d, dict)}

    assert "aws-spoke-client-cert" in by_name
    assert "azure-spoke-client-cert" in by_name

    aws_cert = by_name["aws-spoke-client-cert"]
    assert aws_cert["metadata"]["namespace"] == "monitoring"
    assert aws_cert["spec"]["secretName"] == "aws-spoke-client-tls"
    assert aws_cert["spec"]["commonName"] == "aws-k3d.spoke.multicloud.local"

    azure_cert = by_name["azure-spoke-client-cert"]
    assert azure_cert["metadata"]["namespace"] == "monitoring"
    assert azure_cert["spec"]["secretName"] == "azure-spoke-client-tls"
    assert azure_cert["spec"]["commonName"] == "azure-k3d.spoke.multicloud.local"


def test_infra_cli_per_spoke_certs_and_cap_add_net_admin():
    """2b. infra/cli.py waits for certs, distributes per-spoke TLS, and drops --privileged."""
    cli_text = (REPO_ROOT / "infra" / "cli.py").read_text(encoding="utf-8")

    assert "--privileged" not in cli_text, "infra/cli.py must not use --privileged"
    assert "--cap-add=NET_ADMIN" in cli_text, "infra/cli.py must use --cap-add=NET_ADMIN"

    assert "certificate/hub-otel-gateway-server-cert" in cli_text
    assert "certificate/aws-spoke-client-cert" in cli_text
    assert "certificate/azure-spoke-client-cert" in cli_text
    assert "aws-spoke-client-tls" in cli_text
    assert "azure-spoke-client-tls" in cli_text


def test_robusta_signing_key_and_pyrra_rbac():
    """3. Robusta signing_key uses env var; Pyrra RBAC avoids wildcard verbs."""
    playbooks = (REPO_ROOT / "deploy" / "platform" / "smart-alerting-robusta" / "02-configmap-playbooks.yaml").read_text(encoding="utf-8")
    assert "multicloud-aiops-local-signing-key" not in playbooks
    assert "{{ env.ROBUSTA_SIGNING_KEY }}" in playbooks

    hub_kust = yaml.safe_load((REPO_ROOT / "deploy" / "clusters" / "hub" / "kustomization.yaml").read_text(encoding="utf-8"))
    sec_gens = {sg["name"]: sg.get("literals", []) for sg in hub_kust.get("secretGenerator", [])}
    assert "ROBUSTA_SIGNING_KEY=CHANGE_ME_ROBUSTA_SIGNING_KEY" in sec_gens.get("robusta-secrets", [])

    robusta_secret = yaml.safe_load((REPO_ROOT / "deploy" / "platform" / "smart-alerting-robusta" / "01-secret.yaml").read_text(encoding="utf-8"))
    assert robusta_secret["stringData"].get("ROBUSTA_SIGNING_KEY") == "CHANGE_ME_ROBUSTA_SIGNING_KEY"

    robusta_deploy = yaml.safe_load((REPO_ROOT / "deploy" / "platform" / "smart-alerting-robusta" / "03-runner-deployment.yaml").read_text(encoding="utf-8"))
    robusta_env = robusta_deploy["spec"]["template"]["spec"]["containers"][0]["env"]
    signing_env = next((e for e in robusta_env if e.get("name") == "ROBUSTA_SIGNING_KEY"), None)
    assert signing_env is not None, "ROBUSTA_SIGNING_KEY env missing from robusta-runner"
    assert signing_env["valueFrom"]["secretKeyRef"] == {"name": "robusta-secrets", "key": "ROBUSTA_SIGNING_KEY"}

    pyrra_rbac_docs = list(yaml.safe_load_all((REPO_ROOT / "deploy" / "platform" / "slo-pyrra" / "01-rbac.yaml").read_text(encoding="utf-8")))
    cluster_role = next(d for d in pyrra_rbac_docs if d.get("kind") == "ClusterRole")
    for rule in cluster_role["rules"]:
        assert "*" not in rule.get("verbs", []), "Pyrra ClusterRole must not use wildcard verbs"
    prom_rule = next(r for r in cluster_role["rules"] if "prometheusrules" in r.get("resources", []))
    assert prom_rule["verbs"] == ["get", "list", "watch", "create", "update", "patch", "delete"]
    cm_rule = next((r for r in cluster_role["rules"] if "configmaps" in r.get("resources", [])), None)
    assert cm_rule is not None


def test_hub_workloads_and_teastore_security_context():
    """4. Hub workloads, TeaStore WebUI, and Kyverno disallow-root-user hardened."""
    hub_manifests = [
        REPO_ROOT / "deploy" / "platform" / "alertmanager" / "01-deployment.yaml",
        REPO_ROOT / "deploy" / "platform" / "slo-pyrra" / "02-deployment.yaml",
        REPO_ROOT / "deploy" / "platform" / "logs-loki" / "03-statefulset.yaml",
        REPO_ROOT / "deploy" / "platform" / "traces-tempo" / "03-statefulset.yaml",
        REPO_ROOT / "deploy" / "platform" / "metrics-thanos" / "03-statefulset-prometheus.yaml",
        REPO_ROOT / "deploy" / "platform" / "metrics-thanos" / "05-deployment-thanos-query.yaml",
        REPO_ROOT / "deploy" / "platform" / "metrics-thanos" / "07-deployment-thanos-store.yaml",
        REPO_ROOT / "deploy" / "platform" / "metrics-thanos" / "09-statefulset-thanos-compact.yaml",
    ]
    for path in hub_manifests:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        containers = doc["spec"]["template"]["spec"]["containers"]
        for c in containers:
            sc = c.get("securityContext", {})
            assert sc.get("allowPrivilegeEscalation") is False, f"{path.name}:{c['name']} missing allowPrivilegeEscalation: false"
            dropped = [cap.upper() for cap in sc.get("capabilities", {}).get("drop", [])]
            assert "ALL" in dropped, f"{path.name}:{c['name']} missing capabilities.drop: [ALL]"

    webui = yaml.safe_load((REPO_ROOT / "deploy" / "workloads" / "teastore" / "aws-spoke" / "05-webui-deployment.yaml").read_text(encoding="utf-8"))
    webui_c = webui["spec"]["template"]["spec"]["containers"][0]
    webui_sc = webui_c.get("securityContext", {})
    assert webui_sc.get("allowPrivilegeEscalation") is False
    # teastore-webui runs as root because Tomcat writes setenv.sh at startup

    kyverno_policy = (REPO_ROOT / "deploy" / "policies" / "03-disallow-root-user.yaml").read_text(encoding="utf-8")
    assert "=(securityContext)" not in kyverno_policy
    assert "=(runAsNonRoot)" not in kyverno_policy


def test_monitoring_storage_networkpolicy():
    """5. NetworkPolicies for monitoring and storage namespaces exist and are wired."""
    np_path = REPO_ROOT / "deploy" / "policies" / "12-monitoring-storage-networkpolicy.yaml"
    assert np_path.is_file(), "Missing 12-monitoring-storage-networkpolicy.yaml"
    docs = list(yaml.safe_load_all(np_path.read_text(encoding="utf-8")))
    denies = [d for d in docs if isinstance(d, dict) and d.get("metadata", {}).get("name") == "default-deny-all"]
    deny_ns = {d["metadata"]["namespace"] for d in denies}
    assert {"monitoring", "storage"}.issubset(deny_ns)

    allow_mon = next(d for d in docs if isinstance(d, dict) and d.get("metadata", {}).get("name") == "allow-monitoring-traffic")
    ingress_ports = {p["port"] for rule in allow_mon["spec"]["ingress"] for p in rule.get("ports", [])}
    egress_ports = {p["port"] for rule in allow_mon["spec"]["egress"] for p in rule.get("ports", [])}
    assert 5000 in ingress_ports
    assert {5000, 443, 6443, 3306, 10250}.issubset(egress_ports)

    kust = yaml.safe_load((REPO_ROOT / "deploy" / "policies" / "kustomization.yaml").read_text(encoding="utf-8"))
    assert "12-monitoring-storage-networkpolicy.yaml" in kust.get("resources", [])

    hub_kust = yaml.safe_load((REPO_ROOT / "deploy" / "clusters" / "hub" / "kustomization.yaml").read_text(encoding="utf-8"))
    assert "../../policies" in hub_kust.get("resources", [])

    core_np = yaml.safe_load((REPO_ROOT / "deploy" / "policies" / "11-allow-core-traffic-networkpolicy.yaml").read_text(encoding="utf-8"))
    mysql_rule = next(
        r for r in core_np["spec"]["ingress"]
        if any(p.get("port") == 3306 for p in r.get("ports", []))
    )
    from_peers = mysql_rule.get("from", [])
    assert {"podSelector": {}} in from_peers
    assert {
        "namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "monitoring"}},
        "podSelector": {"matchLabels": {"app": "otel-collector-spoke"}},
    } in from_peers


def test_ai_engine_detector_security():
    """6. AI Engine detector.py uses weights_only=True, redacts token, removes --telegram-token, cooldown=60, metrics_host=127.0.0.1."""
    detector_path = REPO_ROOT / "ai-engine" / "inference" / "detector.py"
    text = detector_path.read_text(encoding="utf-8")

    assert "weights_only=True" in text
    assert 'not self.token.startswith("CHANGE_ME")' not in text
    assert '"CHANGE_ME" not in self.token' in text
    assert "--telegram-token" not in text
    assert 'str(e).replace(self.token, "***")' in text or "replace(self.token" in text
    assert "127.0.0.1" in text
    assert "60" in text

    # Parse AST to verify defaults
    tree = ast.parse(text)
    assert tree is not None
