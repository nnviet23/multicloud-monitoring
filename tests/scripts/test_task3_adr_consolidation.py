# tests/scripts/test_task3_adr_consolidation.py
import os
import re

EXPECTED_ADRS = [
    "ADR-0001-multi-cluster-topology-wan.md",
    "ADR-0002-kyverno-policy-as-code.md",
    "ADR-0003-zero-trust-pki-mtls.md",
    "ADR-0004-multicluster-gitops-argocd.md",
    "ADR-0005-slo-management-smart-alerting.md",
    "ADR-0006-opentelemetry-pipeline-processing.md",
    "ADR-0007-tiered-storage-thanos-loki-tempo.md",
    "ADR-0008-teastore-benchmark-workload.md",
    "ADR-0009-chaos-fault-injection.md",
    "ADR-0010-telemetry-cost-finops.md",
    "ADR-0011-ai-anomaly-detection-rca.md",
    "ADR-0012-folder-over-branch-gitops-layout.md",
]

def test_exactly_twelve_canonical_adrs_exist():
    adr_files = [f for f in os.listdir("docs/adr") if f.startswith("ADR-") and f.endswith(".md")]
    assert sorted(adr_files) == sorted(EXPECTED_ADRS), f"ADR mismatch: {set(adr_files) ^ set(EXPECTED_ADRS)}"

def test_adr_conforms_to_standard_template_structure():
    required_sections = [
        "## Status",
        "## Context",
        "## Decision",
        "## Consequences",
        "## Alternatives considered",
        "## References",
    ]
    for adr in EXPECTED_ADRS:
        p = os.path.join("docs/adr", adr)
        assert os.path.isfile(p), f"File {adr} does not exist"
        with open(p, "r", encoding="utf-8") as f:
            content = f.read()
        for sec in required_sections:
            assert sec in content, f"{adr} is missing section '{sec}'"

def test_normative_specs_embedded_in_adrs():
    # Verify key normative parameters are present in ADRs
    p1 = os.path.join("docs/adr", "ADR-0001-multi-cluster-topology-wan.md")
    assert os.path.isfile(p1), f"{p1} missing"
    with open(p1, "r", encoding="utf-8") as f:
        c1 = f.read()
    assert "172.28.0.0/16" in c1 and "tc netem" in c1

    p7 = os.path.join("docs/adr", "ADR-0007-tiered-storage-thanos-loki-tempo.md")
    assert os.path.isfile(p7), f"{p7} missing"
    with open(p7, "r", encoding="utf-8") as f:
        c7 = f.read()
    assert "thanos-data" in c7 and "365d" in c7

def test_docs_specs_directory_eliminated():
    assert not os.path.exists("docs/specs"), "docs/specs/ directory should be eliminated after consolidation"

def test_adr_readme_has_traceability_matrix():
    readme_path = os.path.join("docs/adr", "README.md")
    assert os.path.isfile(readme_path)
    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "Traceability Matrix" in content or "Bảng Ánh Xạ" in content
