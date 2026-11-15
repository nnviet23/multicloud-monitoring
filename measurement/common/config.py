"""YAML configuration loading and validation."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

import yaml

LOGGER = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]


class ConfigError(ValueError):
    """Raised when a measurement YAML file is invalid."""


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a mapping from a YAML file."""

    if not path.is_file():
        raise ConfigError(f"Configuration file does not exist: {path}")
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ConfigError(f"Top-level YAML value must be a mapping: {path}")
    return value


def validate_configs(config_dir: Path = ROOT / "configs") -> list[Path]:
    """Validate all YAML configuration files and required sections."""

    paths = sorted(config_dir.glob("*.yaml"))
    if not paths:
        raise ConfigError(f"No YAML configuration files found in {config_dir}")
    for path in paths:
        if "schema_version" not in load_yaml(path):
            raise ConfigError(f"Missing schema_version: {path}")
    endpoints = load_yaml(config_dir / "endpoints.yaml")
    if not isinstance(endpoints.get("endpoints"), dict):
        raise ConfigError("endpoints.yaml must contain an endpoints mapping")
    LOGGER.info("Validated %d configuration files", len(paths))
    return paths


def main() -> int:
    """CLI entry point for configuration validation."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    if not args.validate:
        parser.error("Use --validate")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    validate_configs()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
