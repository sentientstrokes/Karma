"""
Tests for karma/utils.py — shared utilities.
"""

import pytest
from datetime import datetime, timezone, timedelta

from karma.utils import parse_since


class TestParseSince:
    def test_none_returns_none(self):
        assert parse_since(None) is None

    def test_relative_hours(self):
        before = datetime.now(timezone.utc)
        result = parse_since("2h")
        after = datetime.now(timezone.utc)
        expected = before - timedelta(hours=2)
        # Allow 2-second tolerance for test execution time
        assert abs((result - expected).total_seconds()) < 2

    def test_relative_minutes(self):
        result = parse_since("30m")
        expected = datetime.now(timezone.utc) - timedelta(minutes=30)
        assert abs((result - expected).total_seconds()) < 2

    def test_relative_days(self):
        result = parse_since("1d")
        expected = datetime.now(timezone.utc) - timedelta(days=1)
        assert abs((result - expected).total_seconds()) < 2

    def test_iso_absolute_with_timezone(self):
        result = parse_since("2026-03-03T09:00:00+00:00")
        assert result == datetime(2026, 3, 3, 9, 0, 0, tzinfo=timezone.utc)

    def test_iso_absolute_without_timezone_gets_utc(self):
        result = parse_since("2026-03-03T09:00:00")
        assert result.tzinfo == timezone.utc
        assert result.year == 2026 and result.hour == 9

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="since/until"):
            parse_since("yesterday")

    def test_invalid_format_raises_for_garbage(self):
        with pytest.raises(ValueError):
            parse_since("not-a-date!")
