"""Statistics tests using synthetic, non-experimental data."""

from common.statistics import summarize


def test_statistics() -> None:
    result = summarize([1, 2, 3, 4])
    assert result["mean"] == 2.5
    assert result["p95"] is not None
    assert result["std"] > 0


def test_empty_statistics() -> None:
    result = summarize([])
    assert result["count"] == 0
    assert result["mean"] is None

