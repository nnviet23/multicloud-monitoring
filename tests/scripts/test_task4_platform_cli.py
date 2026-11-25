import subprocess
import sys
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

def test_infra_cli_module_exists_and_renders_help():
    cmd = [sys.executable, "-m", "infra.cli", "--help"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"CLI help failed: {result.stderr}"
    assert "up" in result.stdout
    assert "down" in result.stdout
    assert "wan" in result.stdout
    assert "certs" in result.stdout
    assert "register-spokes" in result.stdout

def test_infra_cli_subcommands_have_help():
    subcommands = ["up", "down", "wan", "certs", "sync-hosts", "pull-images", "preload-images", "register-spokes", "status"]
    for sub in subcommands:
        cmd = [sys.executable, "-m", "infra.cli", sub, "--help"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, f"Subcommand {sub} --help failed: {result.stderr}"

def test_makefile_invokes_python_infra_cli():
    with open("Makefile", "r", encoding="utf-8") as f:
        makefile = f.read()
    assert "infra.cli" in makefile, "Makefile does not invoke infra.cli"
    assert "infra.cli up" in makefile
    assert "infra.cli down" in makefile
    assert "infra.cli pull-images" in makefile

def test_infra_helper_scripts_exist_and_render_help():
    scripts = [
        "infra/scripts/register_argocd_spokes.py",
    ]
    for script in scripts:
        assert Path(script).is_file(), f"Script {script} does not exist"
        cmd = [sys.executable, script, "--help"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        assert res.returncode == 0, f"Script {script} --help failed: {res.stderr}"

def test_legacy_redundant_infra_scripts_removed():
    for legacy in [
        "infra/scripts/generate_certs.py",
        "infra/scripts/import_k3d_images.sh",
        "infra/scripts/pull_images.sh",
    ]:
        assert not Path(legacy).exists(), f"Redundant script {legacy} should be removed"

def test_register_argocd_spokes_dry_run():
    from infra.scripts.register_argocd_spokes import register_spokes_in_argocd
    # Dry run should execute without attempting cluster mutations
    res = register_spokes_in_argocd(dry_run=True)
    assert res is True
