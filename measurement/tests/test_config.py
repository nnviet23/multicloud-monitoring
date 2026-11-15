"""Configuration validation tests."""

from pathlib import Path

from common.config import validate_configs


def test_configs_are_valid() -> None:
    paths = validate_configs(Path(__file__).parents[1] / "configs")
    assert len(paths) >= 3
