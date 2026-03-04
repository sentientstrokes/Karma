"""
Tests for karma/health.py — Health Reporter module.

All external calls (Logfire, Langfuse) are mocked. Tests never hit live services.
Uses tmp_path fixture for CSV file isolation — each test gets a clean temp directory.
"""

import csv
import functools
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from karma.health import CSV_FIELDNAMES, append_health_row


# ---------------------------------------------------------------------------
# Shared fixtures — mock return values used across scenarios
# ---------------------------------------------------------------------------

FIXED_UNTIL = datetime(2026, 3, 4, 12, 0, 0, tzinfo=timezone.utc)

LOGFIRE_HAPPY = {
    "red_flag_count": 2,
    "yellow_flag_count": 3,
    "archetype": "Continuous",
    "lifecycle_status": "",
    "session_turn_count": "42",
}

LANGFUSE_HAPPY = {
    "trace_count": 2,
    "total_tokens": 1500,
    "total_cost_usd": 0.0032,
    "total_latency_ms": 2400,
    "error_observation_count": 1,
}

LOGFIRE_EMPTY = {
    "red_flag_count": 0,
    "yellow_flag_count": 0,
    "archetype": "",
    "lifecycle_status": "",
    "session_turn_count": "",
}

LANGFUSE_EMPTY = {
    "trace_count": 0,
    "total_tokens": 0,
    "total_cost_usd": 0.0,
    "total_latency_ms": 0,
    "error_observation_count": 0,
}


# ---------------------------------------------------------------------------
# Scenario 1 — Happy path (flags + Langfuse data)
# ---------------------------------------------------------------------------

def test_append_health_row_happy_path(tmp_path):
    """
    Given mocked logfire and langfuse data,
    when append_health_row is called with since=None,
    then the CSV has 1 data row, correct values, and window_from is empty.
    """
    csv_path = tmp_path / "health-log.csv"

    result_path = append_health_row(
        karma_code="NRD-Sale-101",
        archetype="Continuous",
        since=None,
        until=FIXED_UNTIL,
        logfire_data=LOGFIRE_HAPPY,
        langfuse_data=LANGFUSE_HAPPY,
        csv_path=csv_path,
    )

    assert result_path == csv_path
    assert csv_path.exists()

    rows = list(csv.DictReader(csv_path.open()))
    assert len(rows) == 1  # DictReader skips header row automatically

    row = rows[0]
    assert row["karma_code"] == "NRD-Sale-101"
    assert row["archetype"] == "Continuous"
    assert row["red_flag_count"] == "2"
    assert row["yellow_flag_count"] == "3"
    assert row["total_tokens"] == "1500"
    assert row["total_latency_ms"] == "2400"
    assert row["error_observation_count"] == "1"
    # window_from must be empty cell — not the string "None"
    assert row["window_from"] == ""
    # window_to must be a valid ISO 8601 timestamp
    assert row["window_to"] == FIXED_UNTIL.isoformat()
    # archetype-specific: session_turn_count populated, lifecycle_status empty
    assert row["session_turn_count"] == "42"
    assert row["lifecycle_status"] == ""


# ---------------------------------------------------------------------------
# Scenario 2 — Empty session (no flags, no Langfuse data)
# ---------------------------------------------------------------------------

def test_append_health_row_empty_session(tmp_path):
    """
    Given both queries return zero counts,
    when append_health_row is called,
    then the CSV row contains zero values and cost formatted as "0.000000".
    """
    csv_path = tmp_path / "health-log.csv"

    append_health_row(
        karma_code="NRD-Sale-102",
        archetype="",
        since=None,
        until=FIXED_UNTIL,
        logfire_data=LOGFIRE_EMPTY,
        langfuse_data=LANGFUSE_EMPTY,
        csv_path=csv_path,
    )

    rows = list(csv.DictReader(csv_path.open()))
    assert len(rows) == 1

    row = rows[0]
    assert row["red_flag_count"] == "0"
    assert row["yellow_flag_count"] == "0"
    assert row["trace_count"] == "0"
    # Fixed-precision float: f"{0.0:.6f}" → "0.000000" (NOT "0.0" or "None")
    assert row["total_cost_usd"] == "0.000000"
    assert row["total_latency_ms"] == "0"
    assert row["error_observation_count"] == "0"
    assert row["lifecycle_status"] == ""
    assert row["session_turn_count"] == ""


# ---------------------------------------------------------------------------
# Scenario 3 — Append-only (header written exactly once)
# ---------------------------------------------------------------------------

def test_append_health_row_append_only(tmp_path):
    """
    Given two calls to append_health_row on the same CSV file,
    then the file has exactly 3 lines (1 header + 2 data rows),
    the header is NOT duplicated, and both calls return the same path.
    """
    csv_path = tmp_path / "health-log.csv"

    path1 = append_health_row(
        karma_code="NRD-Sale-101",
        archetype="Continuous",
        since=None,
        until=FIXED_UNTIL,
        logfire_data=LOGFIRE_HAPPY,
        langfuse_data=LANGFUSE_HAPPY,
        csv_path=csv_path,
    )
    path2 = append_health_row(
        karma_code="NRD-Sale-102",
        archetype="Pipeline",
        since=None,
        until=FIXED_UNTIL,
        logfire_data=LOGFIRE_EMPTY,
        langfuse_data=LANGFUSE_EMPTY,
        csv_path=csv_path,
    )

    # Both calls return the same path
    assert path1 == path2 == csv_path
    assert csv_path.exists()

    # Verify via DictReader — header is NOT duplicated
    rows = list(csv.DictReader(csv_path.open()))
    assert len(rows) == 2, f"Expected 2 data rows, got {len(rows)}"
    assert rows[0]["karma_code"] == "NRD-Sale-101"
    assert rows[1]["karma_code"] == "NRD-Sale-102"

    # Verify raw line count: 1 header + 2 data rows (trailing newline may add 1 blank line)
    non_empty_lines = [l for l in csv_path.read_text().splitlines() if l.strip()]
    assert len(non_empty_lines) == 3

    # Verify column order matches CSV_FIELDNAMES spec exactly
    with csv_path.open() as f:
        header_line = f.readline().strip()
    assert header_line == ",".join(CSV_FIELDNAMES)


# ---------------------------------------------------------------------------
# Scenario 4 — langfuse.flush() always called (AC 9)
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=None)
def _load_health_script() -> object:
    """
    Load scripts/health.py as a module via importlib — scripts/ has no __init__.py
    (it is an entry-points directory, not a package), so standard import doesn't work.
    Cached so module-level code (get_client, load_dotenv) runs only once across tests.
    Returns the loaded module object.
    """
    scripts_dir = Path(__file__).parent.parent / "scripts"
    spec = importlib.util.spec_from_file_location("scripts_health", scripts_dir / "health.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_langfuse_flush_called_on_success(mocker, tmp_path):
    """
    Scenario 4a: Given a successful main() run (happy path),
    then langfuse.flush() is called exactly once.
    """
    # Load the script module fresh so patches apply cleanly
    scripts_health = _load_health_script()

    # Patch sys.argv so argparse sees our test args
    mocker.patch.object(sys, "argv", ["health.py", "--karma-code", "NRD-Sale-101"])

    # Patch the functions called inside main() — patch on the loaded module's namespace
    mocker.patch.object(scripts_health, "query_logfire_health", return_value=LOGFIRE_HAPPY)
    mocker.patch.object(scripts_health, "query_langfuse_health", return_value=LANGFUSE_HAPPY)

    # Redirect CSV output to tmp_path
    test_csv = tmp_path / "health-log.csv"
    mocker.patch.object(scripts_health, "append_health_row", return_value=test_csv)

    # Patch logfire.configure to no-op (avoids Logfire SDK init in tests)
    mocker.patch.object(scripts_health.logfire, "configure")

    # Patch langfuse.flush on the module-level langfuse client instance
    mock_flush = mocker.patch.object(scripts_health.langfuse, "flush")

    scripts_health.main()

    mock_flush.assert_called_once()


def test_langfuse_flush_called_on_error(mocker, tmp_path):
    """
    Scenario 4b: Given query_logfire_health raises an exception,
    then langfuse.flush() is still called exactly once (verifies the finally guarantee).
    """
    scripts_health = _load_health_script()

    mocker.patch.object(sys, "argv", ["health.py", "--karma-code", "NRD-Sale-101"])

    # Simulate a mid-execution failure
    mocker.patch.object(
        scripts_health, "query_logfire_health", side_effect=RuntimeError("logfire exploded")
    )
    mocker.patch.object(scripts_health.logfire, "configure")
    mock_flush = mocker.patch.object(scripts_health.langfuse, "flush")

    with pytest.raises(RuntimeError, match="logfire exploded"):
        scripts_health.main()

    # flush must have been called even though an exception propagated
    mock_flush.assert_called_once()


# ---------------------------------------------------------------------------
# Scenario 5 — Pipeline lifecycle_status derivation
# ---------------------------------------------------------------------------

def test_query_logfire_health_pipeline_lifecycle_complete(mocker):
    """
    Scenario 5: Given a Pipeline karma_code and a COMPLETE_RUN lifecycle marker,
    when query_logfire_health is called,
    then lifecycle_status == "complete" and session_turn_count is empty.
    """
    from karma.health import query_logfire_health

    # Build a mock LogfireQueryClient context manager
    mock_client = MagicMock()
    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_client)
    mock_cm.__exit__ = MagicMock(return_value=False)
    mocker.patch("karma.health.LogfireQueryClient", return_value=mock_cm)
    mocker.patch.dict("os.environ", {"LOGFIRE_READ_TOKEN": "test-token"})

    # First call: flagged entries — returns one Pipeline red-flag row
    # Second call: lifecycle query — returns COMPLETE_RUN event
    mock_client.query_json_rows.side_effect = [
        {"rows": [{"flag": "red", "archetype": "Pipeline", "event": "ABORT_RUN"}]},
        {"rows": [{"event": "COMPLETE_RUN"}]},
    ]

    result = query_logfire_health("NRD-Sale-101", None, FIXED_UNTIL)

    assert result["archetype"] == "Pipeline"
    assert result["lifecycle_status"] == "complete"
    assert result["session_turn_count"] == ""
    assert result["red_flag_count"] == 1
    assert result["yellow_flag_count"] == 0
