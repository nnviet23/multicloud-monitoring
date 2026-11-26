"""Tests for Task 4: ADR & Planning Documentation Alignment with Approach 1+."""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ADR_DIR = REPO_ROOT / "docs" / "architecture" / "decisions"
PLANNING_DIR = REPO_ROOT / "docs" / "planning"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.mark.skipif(not PLANNING_DIR.is_dir(), reason="docs/planning/ is gitignored")
def test_adr_tracker_uses_12_canonical_adrs():
    tracker = _read(PLANNING_DIR / "adr-tracker.md")
    assert "/ 12" in tracker, "adr-tracker.md must divide by 12 canonical ADRs"
    assert "/ 21" not in tracker, "adr-tracker.md must not still reference / 21"
    assert "21 Quyết định Kiến trúc" not in tracker
    assert "21 ADRs" not in tracker


def test_renovate_references_adr_0012_not_0021():
    renovate = _read(REPO_ROOT / "renovate.json")
    assert "ADR-0012" in renovate, "renovate.json should reference ADR-0012"
    assert "ADR-0021" not in renovate, "renovate.json must not reference stale ADR-0021"


@pytest.mark.skipif(not PLANNING_DIR.is_dir(), reason="docs/planning/ is gitignored")
def test_task_md_removes_cloudflare_vpn_claim():
    task_md = _read(PLANNING_DIR / "task.md")
    assert "cloudflare-vpn" not in task_md, "task.md must not claim cloudflare-vpn/ is an active workload"


def test_adr_0001_topology_and_coredns_aligned():
    c = _read(ADR_DIR / "ADR-0001-why-multi-cluster-hub-spoke.md")
    assert "mc-monitoring-net" in c
    assert "hub-gateway.hub.multicloud.local" in c
    assert "thanos-query.hub.multicloud.local" in c


def test_adr_0002_kyverno_phase5_scope():
    c = _read(ADR_DIR / "ADR-0002-why-kyverno.md")
    assert "deploy/policies/" in c
    assert "Phase 5" in c


def test_adr_0003_cert_manager_and_mtls_aligned():
    c = _read(ADR_DIR / "ADR-0003-why-mtls-zero-trust-pki.md")
    assert "v1.16.2" in c
    assert "aws-spoke-client-cert" in c
    assert "azure-spoke-client-cert" in c
    assert "sync-secrets" in c


def test_adr_0004_argocd_version_and_rollouts_scope():
    c = _read(ADR_DIR / "ADR-0004-why-argocd-and-applicationsets.md")
    assert "v2.12.3" in c
    assert "Phase 5" in c


def test_adr_0006_pyrra_and_robusta_scope():
    c = _read(ADR_DIR / "ADR-0006-why-pyrra-and-robusta.md")
    assert "--config-maps-only" in c
    assert "pyrra-api" in c
    assert "Phase 5" in c


def test_adr_0007_otel_edge_tail_sampling_and_initcontainer():
    c = _read(ADR_DIR / "ADR-0007-why-opentelemetry-and-hub-spoke-pipeline.md")
    assert "tail_sampling" in c
    assert "1500ms" in c
    assert "mysql" in c
    assert "initContainer" in c


def test_adr_0008_thanos_sidecar_buckets_and_retention():
    c = _read(ADR_DIR / "ADR-0008-why-thanos-loki-tempo.md")
    assert "thanos-sidecar" in c
    assert "8889" in c
    assert "72h" in c
    assert "24h" in c


def test_adr_0010_teastore_fault_probes_note():
    c = _read(ADR_DIR / "ADR-0010-why-teastore-and-locust.md")
    assert "run_service_faults.py" in c


def test_adr_0012_finops_phase5_scope():
    c = _read(ADR_DIR / "ADR-0012-why-telemetry-finops.md")
    assert "filter/drop_noise" in c
    assert "tail_sampling" in c
    assert "Phase 5" in c


def test_adr_0013_ai_metrics_and_panel7_aligned():
    c = _read(ADR_DIR / "ADR-0013-why-ai-anomaly-detection-and-rca.md")
    assert "ai_anomaly_likelihood_percent" in c
    assert "ai_reconstruction_error" in c
    assert "ai_rca_component_latency_ms" in c
    assert "weights_only=True" in c


def test_adr_0005_layout_aligned():
    c = _read(ADR_DIR / "ADR-0005-why-folder-over-branch-and-kustomize.md")
    assert "workloads/" in c
    assert "workloads/teastore/release-images/" in c or "release-images" in c
    assert "deploy/workloads/" not in c, "ADR-0005 must not reference removed deploy/workloads/ as active"
