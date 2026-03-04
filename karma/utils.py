"""
Karma shared utilities.

Common helper functions used by karma/ modules and scripts/ entry points.
Centralised here to prevent duplication across scripts.
"""

import re
from datetime import datetime, timedelta, timezone


def parse_since(value: str | None) -> datetime | None:
    """
    Parse a time window start value into a UTC-aware datetime, or None if not provided.

    Supported relative formats: 30m (minutes), 2h (hours), 1d (days).
    Supported absolute format: any ISO 8601 string.
    Returns None when value is None (no time filter applied).
    Raises ValueError for unrecognised formats.
    """
    if value is None:
        return None

    match = re.fullmatch(r"(\d+)(m|h|d)", value.strip())
    if match:
        amount = int(match.group(1))
        unit   = match.group(2)
        delta  = {"m": timedelta(minutes=amount),
                  "h": timedelta(hours=amount),
                  "d": timedelta(days=amount)}[unit]
        return datetime.now(timezone.utc) - delta

    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        pass

    raise ValueError(
        "since/until must be a relative duration (e.g. 2h, 30m, 1d) or ISO 8601 timestamp"
    )
