"""CLI for comparing run-specific ground truth and received samples."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from .compare import compare


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    """Read two CSV files and print a JSON accuracy result."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--ground-truth", type=Path, required=True)
    parser.add_argument("--received", type=Path, required=True)
    parser.add_argument("--counter", type=float)
    args = parser.parse_args()
    print(json.dumps(compare(
        _read_csv(args.ground_truth), _read_csv(args.received), args.counter
    ), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
