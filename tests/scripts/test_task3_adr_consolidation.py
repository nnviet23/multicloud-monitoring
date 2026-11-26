# tests/scripts/test_task3_adr_consolidation.py
import os

EXPECTED_ADRS = [
    "ADR-0001-why-multi-cluster-hub-spoke.md",
    "ADR-0002-why-kyverno.md",
    "ADR-0003-why-mtls-zero-trust-pki.md",
    "ADR-0004-why-argocd-and-applicationsets.md",
    "ADR-0005-why-folder-over-branch-and-kustomize.md",
    "ADR-0006-why-pyrra-and-robusta.md",
    "ADR-0007-why-opentelemetry-and-hub-spoke-pipeline.md",
    "ADR-0008-why-thanos-loki-tempo.md",
    "ADR-0009-why-minio-object-storage.md",
    "ADR-0010-why-teastore-and-locust.md",
    "ADR-0011-why-chaos-fault-injection.md",
    "ADR-0012-why-telemetry-finops.md",
    "ADR-0013-why-ai-anomaly-detection-and-rca.md",
]


def test_exactly_thirteen_canonical_adrs_exist():
    adr_files = [f for f in os.listdir("docs/architecture/decisions") if f.startswith("ADR-") and f.endswith(".md")]
    assert sorted(adr_files) == sorted(EXPECTED_ADRS), f"ADR mismatch: {set(adr_files) ^ set(EXPECTED_ADRS)}"


def test_adr_conforms_to_standard_template_structure():
    required_sections = [
        "## Status",
        "## Context",
        "## Decision",
        "## Consequences",
    ]
    for adr in EXPECTED_ADRS:
        p = os.path.join("docs/architecture/decisions", adr)
        assert os.path.isfile(p), f"File {adr} does not exist"
        with open(p, "r", encoding="utf-8") as f:
            content = f.read()
        for sec in required_sections:
            assert sec in content, f"{adr} is missing section '{sec}'"


def test_docs_specs_directory_eliminated():
    assert not os.path.exists("docs/specs"), "docs/specs/ directory should be eliminated after consolidation"


def test_adr_readme_has_traceability_matrix():
    readme_path = os.path.join("docs/architecture/decisions", "README.md")
    assert os.path.isfile(readme_path)
    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "Traceability Matrix" in content
