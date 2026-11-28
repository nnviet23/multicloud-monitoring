# tests/scripts/test_task1_skills_pruning.py
import os
import subprocess
import pytest

EXPECTED_SKILLS = {
    "project-architecture",
    "k3d-platform-lab",
    "kustomize-gitops",
    "otel-collector-engineering",
    "otel-instrumentation",
    "observability-platform",
    "aiops-anomaly-engine",
    "benchmark-and-chaos",
    "grafana",
    "platform-engineering",
}

@pytest.mark.skipif(not os.path.isdir(".agents/skills"), reason=".agents/ is gitignored")
def test_skills_pruned_to_exactly_eight_core_skills():
    skills_dir = ".agents/skills"
    actual_skills = {
        d for d in os.listdir(skills_dir)
        if os.path.isdir(os.path.join(skills_dir, d)) and not d.startswith(".")
    }
    assert actual_skills == EXPECTED_SKILLS, f"Skills mismatch: extra={actual_skills - EXPECTED_SKILLS}, missing={EXPECTED_SKILLS - actual_skills}"

@pytest.mark.skipif(not os.path.isdir(".agents/skills"), reason=".agents/ is gitignored")
def test_each_core_skill_has_skill_md():
    skills_dir = ".agents/skills"
    for skill in EXPECTED_SKILLS:
        skill_md = os.path.join(skills_dir, skill, "SKILL.md")
        assert os.path.isfile(skill_md), f"Missing SKILL.md in {skill}"

def test_validate_otel_rules_script_relocated_and_executable():
    import sys
    validator_path = os.path.join("tests", "scripts", "validate_otel_rules.py")
    assert os.path.isfile(validator_path), "validate_otel_rules.py not found in tests/scripts/"
    result = subprocess.run([sys.executable, validator_path], capture_output=True, text=True)
    assert result.returncode == 0, f"Validator failed: {result.stderr}"

def test_makefile_validate_otel_target_updated():
    with open("Makefile", "r", encoding="utf-8") as f:
        makefile = f.read()
    assert "tests/scripts/validate_otel_rules.py" in makefile, "Makefile validate-otel does not reference relocated validator"
