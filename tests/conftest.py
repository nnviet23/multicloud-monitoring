"""
Shared pytest configuration and fixtures for multi-cloud monitoring platform tests.
"""

from pathlib import Path
import shutil
import pytest


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Return the absolute Path to the repository root directory."""
    return Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def kubectl_available() -> bool:
    """Return True if kubectl is available in the current environment PATH."""
    return shutil.which("kubectl") is not None
