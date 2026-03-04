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


def test_append_health_row_happy_path(tmp_path):
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
    assert len(rows) == 1
    row = rows[0]
    assert row["karma_code"] == "NRD-Sale-101"
    assert row["archetype"] == "Continuous"
    assert row["red_flag_count"] == "2"
    assert row["yellow_flag_count"] == "3"
    assert row["total_tokens"] == "1500"
    assert row["total_latency_ms"] == "2400"
    assert row["error_observation_count"] == "1"
    assert row["window_from"] == ""
    assert row["window_to"] == FIXED_UNTIL.isoformat()
    assert row["session_turn_count"] == "42"
    assert row["lifecycle_status"] == ""


def test_append_health_row_empty_session(tmp_path):
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
    assert row["total_cost_usd"] == "0.000000"
    assert row["total_latency_ms"] == "0"
    assert row["error_observation_count"] == "0"
    assert row["lifecycle_status"] == ""
    assert row["session_turn_count"] == ""


def test_append_health_row_append_only(tmp_path):
    csv_path = tmp_path / "health-log.csv"
    path1 = append_health_row(
        karma_code="NRD-Sale-101", archetype="Continuous", since=None, until=FIXED_UNTIL,
        logfire_data=LOGFIRE_HAPPY, langfuse_data=LANGFUSE_HAPPY, csv_path=csv_path,
    )
    path2 = append_health_row(
        karma_code="NRD-Sale-102", archetype="Pipeline", since=None, until=FIXED_UNTIL,
        logfire_data=LOGFIRE_EMPTY, langfuse_data=LANGFUSE_EMPTY, csv_path=csv_path,
    )
    assert path1 == path2 == csv_path
    rows = list(csv.DictReader(csv_path.open()))
    assert len(rows) == 2
    assert rows[0]["karma_code"] == "NRD-Sale-101"
    assert rows[1]["karma_code"] == "NRD-Sale-102"
    non_empty_lines = [l for l in csv_path.read_text().splitlines() if l.strip()]
    assert len(non_empty_lines) == 3
    with csv_path.open() as f:
        header_line = f.readline().strip()
    assert header_line == ",".join(CSV_FIELDNAMES)


@functools.lru_cache(maxsize=None)
def _load_health_script() -> object:
    scripts_dir = Path(__file__).parent.parent / "scripts"
    spec = importlib.util.spec_from_file_location("scripts_health", scripts_dir / "health.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_langfuse_flush_called_on_success(mocker, tmp_path):
    scripts_health = _load_health_script()
    mocker.patch.object(sys, "argv", ["health.py", "--karma-code", "NRD-Sale-101"])
    mocker.patch.object(scripts_health, "query_logfire_health", return_value=LOGFIRE_HAPPY)
    mocker.patch.object(scripts_health, "query_langfuse_health", return_value=LANGFUSE_HAPPY)
    test_csv = tmp_path / "health-log.csv"
    mocker.patch.object(scripts_health, "append_health_row", return_value=test_csv)
    mocker.patch.object(scripts_health.logfire, "configure")
    mock_flush = mocker.patch.object(scripts_health.langfuse, "flush")
    scripts_health.main()
    mock_flush.assert_called_once()


def test_langfuse_flush_called_on_error(mocker, tmp_path):
    scripts_health = _load_health_script()
    mocker.patch.object(sys, "argv", ["health.py", "--karma-code", "NRD-Sale-101"])
    mocker.patch.object(scripts_health, "query_logfire_health", side_effect=RuntimeError("logfire exploded"))
    mocker.patch.object(scripts_health.logfire, "configure")
    mock_flush = mocker.patch.object(scripts_health.langfuse, "flush")
    with pytest.raises(RuntimeError, match="logfire exploded"):
        scripts_health.main()
    mock_flush.assert_called_once()


def test_query_logfire_health_pipeline_lifecycle_complete(mocker):
    from karma.health import query_logfire_health
    mock_client = MagicMock()
    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_client)
    mock_cm.__exit__ = MagicMock(return_value=False)
    mocker.patch("karma.health.LogfireQueryClient", return_value=mock_cm)
    mocker.patch.dict("os.environ", {"LOGFIRE_READ_TOKEN": "test-token"})
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
