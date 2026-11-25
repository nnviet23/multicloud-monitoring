#!/usr/bin/env python3
"""
Test script for Task 5: Python Dependency Manifests, Fixture Consolidation & Makefile Gating
Verifies:
- requirements.txt and requirements-dev.txt exist and pin exact versions
- tests/conftest.py exists and provides shared fixtures (repo_root, kubectl_available)
- Makefile defines test-scripts target and gates it within the master test target
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_requirements_files_exist_and_pinned():
    """Verify requirements.txt and requirements-dev.txt exist with pinned versions."""
    req_file = REPO_ROOT / "requirements.txt"
    dev_req_file = REPO_ROOT / "requirements-dev.txt"
    for req in [req_file, dev_req_file]:
        assert req.is_file(), f"{req.name} missing"
        lines = [
            line.strip()
            for line in req.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        assert len(lines) > 0, f"{req.name} is empty"
        for line in lines:
            assert "==" in line, f"Unpinned dependency in {req.name}: {line}"

    # Verify core dependencies in requirements.txt
    req_content = req_file.read_text(encoding="utf-8").lower()
    for pkg in [
        "typer",
        "rich",
        "cryptography",
        "pyyaml",
        "prometheus-client",
        "requests",
        "locust",
        "torch",
        "scikit-learn",
        "numpy",
        "pandas",
    ]:
        assert pkg in req_content, f"Missing required dependency {pkg} in requirements.txt"

    # Verify dev dependencies in requirements-dev.txt
    dev_content = dev_req_file.read_text(encoding="utf-8").lower()
    for pkg in ["pytest", "pytest-cov"]:
        assert pkg in dev_content, f"Missing required dev dependency {pkg} in requirements-dev.txt"


def test_conftest_exists_with_shared_fixtures():
    """Verify tests/conftest.py exists and provides shared fixtures (repo_root, kubectl_available)."""
    conftest_file = REPO_ROOT / "tests" / "conftest.py"
    assert conftest_file.is_file(), "tests/conftest.py missing"
    c = conftest_file.read_text(encoding="utf-8")
    assert "repo_root" in c, "conftest.py missing repo_root fixture"
    assert "kubectl_available" in c, "conftest.py missing kubectl_available fixture"


def test_makefile_has_test_scripts_target():
    """Verify Makefile defines test-scripts target and includes it in test target."""
    makefile_file = REPO_ROOT / "Makefile"
    assert makefile_file.is_file(), "Makefile missing"
    c = makefile_file.read_text(encoding="utf-8")
    assert "test-scripts:" in c, "Makefile missing test-scripts target"
    # Ensure test-scripts is in the test target prerequisites
    test_line = [line for line in c.splitlines() if line.startswith("test:")][0]
    assert "test-scripts" in test_line, f"Makefile test target does not gate test-scripts: {test_line}"
