"""Performance experiment CLI entry point."""

import argparse

from .run import run_experiment


def main():
    parser = argparse.ArgumentParser(
        description="Run multi-cloud performance experiment"
    )

    parser.add_argument("--rate", type=float, required=True)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument(
        "--scenario",
        default="continuous_load",
    )

    args = parser.parse_args()

    run_experiment(
        rate=args.rate,
        duration=args.duration,
        interval=args.interval,
        scenario=args.scenario,
    )


if __name__ == "__main__":
    main()