# tests/scripts/test_task5_dead_code_elimination.py
import os
import subprocess


def test_ansible_directory_eliminated():
    assert not os.path.exists("infra/ansible"), "infra/ansible directory still exists"


def test_legacy_pki_shell_scripts_eliminated():
    assert not os.path.exists("security/pki/scripts"), "security/pki/scripts directory still exists"


def test_legacy_spoke_registration_shell_script_eliminated():
    assert not os.path.exists("infra/scripts/register_argocd_spokes.sh"), "register_argocd_spokes.sh still exists"


def test_makefile_pki_generate_calls_python_cli():
    with open("Makefile", "r", encoding="utf-8") as f:
        content = f.read()
    assert "infra.cli certs" in content, "Makefile pki-generate does not invoke infra.cli certs"
    assert "security/pki/scripts/01-generate-ca.sh" not in content, "Makefile still references legacy shell script"


def test_makefile_env_setup_does_not_copy_to_hub_dir():
    with open("Makefile", "r", encoding="utf-8") as f:
        content = f.read()
    assert "deploy/clusters/hub/.env" not in content, "Makefile env-setup still copies .env to deploy/clusters/hub/"
