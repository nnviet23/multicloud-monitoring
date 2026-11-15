"""Ground-truth versus received sample correctness checks."""

from __future__ import annotations

from collections.abc import Mapping

from common.time_utils import parse_timestamp


def classify_sample(expected: Mapping[str, object], received: Mapping[str, object]) -> str:
    """Classify one sample as valid or a specific mismatch."""

    try:
        parse_timestamp(str(received["timestamp"]))
    except (KeyError, TypeError, ValueError):
        return "ts_deviation"
    if received.get("metric_name") != expected.get("metric_name"):
        return "value_mismatch"
    if str(received.get("source_id")) != str(expected.get("source_id")):
        return "value_mismatch"
    try:
        if float(received.get("value", float("nan"))) != float(expected["metric_value"]):
            return "value_mismatch"
    except (KeyError, TypeError, ValueError):
        return "value_mismatch"
    return "valid"
