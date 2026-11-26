# tests/scripts/test_task6_docs_template_compliance.py
"""
Test Suite for Task 2: Documentation Upstream Template Alignment & Dead Link Fixes.
Verifies compliance of modular runbooks, production readiness checklist, and fixed cross-references.
"""

from pathlib import Path
import re
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

MODULAR_RUNBOOKS = [
    "runbook-01-spoke-wan-latency-high.md",
    "runbook-02-cross-cluster-trace-broken.md",
    "runbook-03-thanos-compact-halted.md",
    "runbook-04-prometheus-scrape-failed.md",
    "runbook-05-otel-collector-memory-pressure.md",
    "runbook-06-ai-anomaly-inference-down.md",
    "runbook-07-teastore-database-latency.md",
]

RUNBOOK_REQUIRED_SECTIONS = [
    "## Summary",
    "## What this means",
    "## How to confirm",
    "## First mitigations",
    "### What NOT to do (known footguns)",
    "## Escalation",
    "## Related dashboards and queries",
    "## After the incident",
]


@pytest.mark.skipif(
    not (REPO_ROOT / "docs" / "production-readiness-checklist.md").is_file(),
    reason="production-readiness-checklist.md is gitignored",
)
def test_production_readiness_checklist_exists_and_covers_five_pillars():
    checklist_path = REPO_ROOT / "docs" / "production-readiness-checklist.md"
    assert checklist_path.is_file(), f"Missing {checklist_path}"
    content = checklist_path.read_text(encoding="utf-8")

    pillars = ["Availability", "Security", "Observability", "Cost", "Operations"]
    for pillar in pillars:
        assert re.search(rf"(?i)pillar.*{pillar}|#+ .*{pillar}", content), f"Missing pillar: {pillar} in checklist"


def test_runbooks_readme_indexes_all_modular_runbooks():
    readme_path = REPO_ROOT / "docs" / "runbooks" / "README.md"
    assert readme_path.is_file(), f"Missing {readme_path}"
    content = readme_path.read_text(encoding="utf-8")

    for rb in MODULAR_RUNBOOKS:
        assert rb in content, f"Modular runbook {rb} not indexed in {readme_path}"


@pytest.mark.parametrize("rb_filename", MODULAR_RUNBOOKS)
def test_modular_runbook_structure_compliance(rb_filename):
    rb_path = REPO_ROOT / "docs" / "runbooks" / rb_filename
    assert rb_path.is_file(), f"Runbook {rb_path} does not exist"
    content = rb_path.read_text(encoding="utf-8")

    for sec in RUNBOOK_REQUIRED_SECTIONS:
        assert sec in content, f"Runbook {rb_filename} missing required section: '{sec}'"

    # Verify Summary contains required attributes
    summary_lower = content.lower()
    assert "severity" in summary_lower, f"{rb_filename} summary missing severity"
    assert "owner" in summary_lower or "on-call" in summary_lower, f"{rb_filename} summary missing owner/on-call"
    assert "slo" in summary_lower, f"{rb_filename} summary missing linked slo"


def test_runbooks_overview_redirection_and_cli_command():
    overview_path = REPO_ROOT / "docs" / "runbooks.md"
    assert overview_path.is_file(), f"Missing {overview_path}"
    content = overview_path.read_text(encoding="utf-8")

    assert "docs/runbooks/" in content or "runbooks/" in content, "runbooks.md must point to docs/runbooks/"
    assert "python -m infra.cli sync-hosts" in content, "runbooks.md must reference 'python -m infra.cli sync-hosts'"
    assert "04_sync_cluster_hosts.yml" not in content, "runbooks.md must not reference old 04_sync_cluster_hosts.yml"


def test_architecture_md_alignments():
    arch_path = REPO_ROOT / "docs" / "architecture" / "README.md"
    assert arch_path.is_file(), f"Missing {arch_path}"
    content = arch_path.read_text(encoding="utf-8")

    # 1. Links to unified decisions index
    assert "decisions/README.md" in content, "docs/architecture/README.md should link to decisions/README.md"

    # 2. No broken legacy ADR references (ADR-0014 .. ADR-0021)
    for i in range(14, 22):
        bad_ref = f"ADR-00{i}" if i < 100 else f"ADR-{i}"
        assert bad_ref not in content, f"architecture README contains legacy reference {bad_ref}"

    # 3. Pinned images alignment with infra/README.md
    assert "0.114.0" in content, "OTel Collector must be 0.114.0"
    assert "v0.36.1" in content, "Thanos must be v0.36.1"
    assert "2.9.4" in content, "Loki must be 2.9.4"
    assert "2.4.0" in content, "Tempo must be 2.4.0"
    assert "RELEASE.2025-10-15T17-29-55Z" in content, "MinIO must be RELEASE.2025-10-15T17-29-55Z"
    assert "11.5.0" in content, "Grafana must be 11.5.0"
    assert "0.53.0" in content, "Robusta must be 0.53.0"
    assert "2.24.0" in content, "Locust must be 2.24.0"

    # 4. Automation mentions Python CLI
    assert "infra.cli" in content, "architecture.md should reference infra.cli"


def test_github_setup_md_alignments():
    gh_path = REPO_ROOT / "docs" / "github-setup.md"
    assert gh_path.is_file(), f"Missing {gh_path}"
    content = gh_path.read_text(encoding="utf-8")

    # Check broken ADR links fixed
    assert "ADR-0004.md" not in content, "ADR-0004.md should be updated to ADR-0002.md"
    assert "ADR-0011.md" not in content, "ADR-0011.md should be updated to ADR-0005.md"
    assert "ADR-0006.md" not in content, "ADR-0006.md should be updated to ADR-0003.md"
    assert "ADR-0007.md" not in content, "ADR-0007.md should be updated to ADR-0003.md"

    # Check PKI command
    assert "python -m infra.cli certs" in content, "github-setup.md must use python -m infra.cli certs"
    assert "cert-manager" in content, "github-setup.md must reference cert-manager"
    assert "bash certs/generate_certs.sh" not in content, "github-setup.md must not use bash certs/generate_certs.sh"


def test_readme_md_alignments():
    readme_path = REPO_ROOT / "README.md"
    assert readme_path.is_file(), f"Missing {readme_path}"
    content = readme_path.read_text(encoding="utf-8")

    # Check broken link
    assert "docs/progress/IMPLEMENTATION.md" not in content, "Broken link to IMPLEMENTATION.md still present"
    assert "docs/planning/progress.md" in content, "README.md should link to docs/planning/progress.md"

    # Check dashboards path
    assert "k8s/base/visualization-grafana/dashboards/" not in content, "Legacy dashboard path present"
    assert "deploy/platform/visualization-grafana/dashboards/" in content, "README.md should link to deploy/platform/visualization-grafana/dashboards/"

    # Check automation reference
    assert "Python Platform CLI" in content or "infra.cli" in content, "README.md should mention Python Platform CLI / infra.cli"


def test_infra_readme_teardown_alignments():
    infra_readme = REPO_ROOT / "infra" / "README.md"
    assert infra_readme.is_file(), f"Missing {infra_readme}"
    content = infra_readme.read_text(encoding="utf-8")

    assert "python -m infra.cli down" in content or "make teardown" in content, "infra/README.md should mention python -m infra.cli down or make teardown"
    assert "00_cleanup_all.yml" not in content, "infra/README.md should not reference old 00_cleanup_all.yml"


def test_runbooks_and_checklist_relative_links_resolve():
    target_files = []
    checklist = REPO_ROOT / "docs" / "production-readiness-checklist.md"
    if checklist.is_file():
        target_files.append(checklist)
    target_files.extend((REPO_ROOT / "docs" / "runbooks").glob("*.md"))

    link_pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')

    for md_file in target_files:
        assert md_file.is_file(), f"Target file {md_file} missing"
        content = md_file.read_text(encoding="utf-8")
        matches = link_pattern.findall(content)

        for text, target in matches:
            # Skip external links or pure in-page anchors
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue

            # Strip in-file anchor if present (e.g. file.md#heading)
            target_path_str = target.split("#")[0].strip()
            if not target_path_str:
                continue

            resolved_path = (md_file.parent / target_path_str).resolve()
            assert resolved_path.exists(), (
                f"Broken relative link in {md_file.relative_to(REPO_ROOT)}: "
                f"[{text}]({target}) resolves to missing path {resolved_path}"
            )

