"""Named workload sizes."""

SCENARIOS: dict[str, int] = {
    "small": 1_000,
    "medium": 10_000,
    "large": 50_000,
    "stress": 100_000,
}


def expected_count(name: str) -> int:
    """Return the expected count for a named scenario."""

    try:
        return SCENARIOS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown scenario: {name}") from exc
