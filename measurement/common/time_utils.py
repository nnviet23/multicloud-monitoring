"""Time and timestamp validation helpers."""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now_iso() -> str:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc).isoformat()


def parse_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp and require timezone information."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp must be a non-empty ISO-8601 string")
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone information")
    return parsed.astimezone(timezone.utc)


def unix_seconds(value: str) -> float:
    """Convert an ISO timestamp to Unix seconds."""

    return parse_timestamp(value).timestamp()
