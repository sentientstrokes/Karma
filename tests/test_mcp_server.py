"""
Tests for karma/mcp_server.py — KARMA MCP Server.

All external calls (Logfire, Langfuse) are mocked. Tests never hit live services.
Tool functions are called directly (not via MCP protocol) to keep tests fast and simple.
"""

from unittest.mock import MagicMock, patch
import pytest

from karma.mcp_server import (
    get_briefcase, get_health, get_trace_url, list_briefcases, read_briefcase_file, query_flags,
    # Deep investigation tools
    query_logfire, list_langfuse_traces, get_langfuse_trace,
    get_langfuse_observation, list_langfuse_observations,
    # Playbook resources
    get_investigation_playbook, get_quick_check_playbook,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _mock_flags(red=1, yellow=1):
    flags = []
    for i in range(red):
        flags.append({"timestamp": f"2026-03-04T10:0{i}:00Z", "message": f"Fail {i}",
                      "event": f"FAIL_{i}", "flag": "red", "archetype": "Continuous"})
    for j in range(yellow):
        flags.append({"timestamp": f"2026-03-04T10:1{j}:00Z", "message": f"Warn {j}",
                      "event": f"WARN_{j}", "flag": "yellow", "archetype": "Continuous"})
    return flags


def _mock_langfuse_context():
    return {
        "traces": [{"trace_name": "NRD-Sale-101", "duration_ms": 1200, "total_tokens": 500, "total_cost": 0.001}],
        "error_observations": [],
    }


def _mock_logfire_health():
    return {"red_flag_count": 1, "yellow_flag_count": 1, "archetype": "Continuous",
            "lifecycle_status": "", "session_turn_count": "42"}


def _mock_langfuse_health():
    return {"trace_count": 3, "total_tokens": 1500, "total_cost_usd": 0.003,
            "total_latency_ms": 3600, "error_observation_count": 1}


# ---------------------------------------------------------------------------
# get_briefcase
# ---------------------------------------------------------------------------

class TestGetBriefcase:
    @patch("karma.mcp_server.write_briefcase", return_value=__import__("pathlib").Path("/tmp/bc.md"))
    @patch("karma.mcp_server.generate_briefcase", return_value="# Briefcase content")
    @patch("karma.mcp_server.query_langfuse_context", return_value=_mock_langfuse_context())
    @patch("karma.mcp_server.query_langfuse_trace_fields", return_value={"langfuse_trace_url": None, "langfuse_trace_id": None})
    @patch("karma.mcp_server.query_logfire_flags", return_value=_mock_flags())
    @patch("logfire.query_client.LogfireQueryClient")
    def test_returns_content_and_path(self, mock_client, mock_flags, mock_tf, mock_lfc, mock_gen, mock_write):
        mock_client.return_value.__enter__ = lambda s: MagicMock()
        mock_client.return_value.__exit__ = MagicMock(return_value=False)

        result = get_briefcase("NRD-Sale-101")

        assert "content" in result
        assert "path" in result
        assert result["content"] == "# Briefcase content"

    def test_invalid_karma_code_raises_before_api(self):
        with pytest.raises(ValueError, match="Invalid karma_code format"):
            get_briefcase("not valid!")


# ---------------------------------------------------------------------------
# get_health
# ---------------------------------------------------------------------------

class TestGetHealth:
    @patch("karma.mcp_server.query_langfuse_health", return_value=_mock_langfuse_health())
    @patch("karma.mcp_server.query_logfire_health", return_value=_mock_logfire_health())
    def test_returns_all_health_fields(self, mock_lf, mock_lang):
        result = get_health("NRD-Sale-101")

        assert result["karma_code"] == "NRD-Sale-101"
        assert result["red_flag_count"] == 1
        assert result["total_tokens"] == 1500
        assert result["archetype"] == "Continuous"

    @patch("karma.mcp_server.query_langfuse_health", return_value=_mock_langfuse_health())
    @patch("karma.mcp_server.query_logfire_health", return_value=_mock_logfire_health())
    def test_has_all_13_keys(self, mock_lf, mock_lang):
        result = get_health("NRD-Sale-101")
        expected_keys = {
            "karma_code", "archetype", "red_flag_count", "yellow_flag_count",
            "trace_count", "total_tokens", "total_cost_usd", "total_latency_ms",
            "error_observation_count", "lifecycle_status", "session_turn_count",
            "window_from", "window_to",
        }
        assert set(result.keys()) == expected_keys

    @patch("karma.mcp_server.query_langfuse_health", return_value=_mock_langfuse_health())
    @patch("karma.mcp_server.query_logfire_health", return_value=_mock_logfire_health())
    def test_does_not_call_append_health_row(self, mock_lf, mock_lang):
        """MCP get_health must never append to CSV."""
        with patch("karma.health.append_health_row") as mock_append:
            result = get_health("NRD-Sale-101")
            mock_append.assert_not_called()
        assert "csv_path" not in result

    def test_invalid_karma_code_raises(self):
        with pytest.raises(ValueError, match="Invalid karma_code format"):
            get_health("bad code")


# ---------------------------------------------------------------------------
# query_flags
# ---------------------------------------------------------------------------

class TestQueryFlags:
    @patch("karma.mcp_server.query_logfire_flags", return_value=_mock_flags(red=2, yellow=1))
    @patch("logfire.query_client.LogfireQueryClient")
    def test_returns_all_flags_when_no_filter(self, mock_client, mock_flags):
        mock_client.return_value.__enter__ = lambda s: MagicMock()
        mock_client.return_value.__exit__ = MagicMock(return_value=False)
        result = query_flags("NRD-Sale-101")
        assert len(result) == 3

    @patch("karma.mcp_server.query_logfire_flags", return_value=_mock_flags(red=2, yellow=1))
    @patch("logfire.query_client.LogfireQueryClient")
    def test_filters_to_red_only(self, mock_client, mock_flags):
        mock_client.return_value.__enter__ = lambda s: MagicMock()
        mock_client.return_value.__exit__ = MagicMock(return_value=False)
        result = query_flags("NRD-Sale-101", flag="red")
        assert all(e["flag"] == "red" for e in result)
        assert len(result) == 2

    @patch("karma.mcp_server.query_logfire_flags", return_value=_mock_flags(red=2, yellow=1))
    @patch("logfire.query_client.LogfireQueryClient")
    def test_filters_to_yellow_only(self, mock_client, mock_flags):
        mock_client.return_value.__enter__ = lambda s: MagicMock()
        mock_client.return_value.__exit__ = MagicMock(return_value=False)
        result = query_flags("NRD-Sale-101", flag="yellow")
        assert all(e["flag"] == "yellow" for e in result)

    def test_invalid_flag_value_raises(self):
        with pytest.raises(ValueError):
            query_flags("NRD-Sale-101", flag="orange")

    def test_invalid_karma_code_raises(self):
        with pytest.raises(ValueError, match="Invalid karma_code format"):
            query_flags("bad code!")


# ---------------------------------------------------------------------------
# get_trace_url
# ---------------------------------------------------------------------------

class TestGetTraceUrl:
    @patch("karma.mcp_server.query_langfuse_trace_fields",
           return_value={"langfuse_trace_url": "http://localhost:3000/traces/abc", "langfuse_trace_id": "abc"})
    @patch("logfire.query_client.LogfireQueryClient")
    def test_returns_both_fields(self, mock_client, mock_tf):
        mock_client.return_value.__enter__ = lambda s: MagicMock()
        mock_client.return_value.__exit__ = MagicMock(return_value=False)
        result = get_trace_url("NRD-Sale-101")
        assert result["langfuse_trace_url"] == "http://localhost:3000/traces/abc"
        assert result["langfuse_trace_id"] == "abc"

    @patch("karma.mcp_server.query_langfuse_trace_fields",
           return_value={"langfuse_trace_url": None, "langfuse_trace_id": None})
    @patch("logfire.query_client.LogfireQueryClient")
    def test_returns_none_when_no_trace(self, mock_client, mock_tf):
        mock_client.return_value.__enter__ = lambda s: MagicMock()
        mock_client.return_value.__exit__ = MagicMock(return_value=False)
        result = get_trace_url("NRD-Sale-101")
        assert result["langfuse_trace_url"] is None

    def test_invalid_karma_code_raises(self):
        with pytest.raises(ValueError, match="Invalid karma_code format"):
            get_trace_url("!bad")


# ---------------------------------------------------------------------------
# Resources — Briefcases
# ---------------------------------------------------------------------------

class TestListBriefcases:
    def test_returns_empty_list_when_no_directory(self, tmp_path, monkeypatch):
        import json
        import karma.mcp_server as mcp_mod
        monkeypatch.setattr(mcp_mod, "_BRIEFCASES_DIR", tmp_path / "briefcases")
        result = list_briefcases()
        assert json.loads(result) == []

    def test_returns_filenames_sorted_newest_first(self, tmp_path, monkeypatch):
        import json
        import time
        import karma.mcp_server as mcp_mod
        briefcases_dir = tmp_path / "briefcases"
        briefcases_dir.mkdir()
        (briefcases_dir / "old.md").write_text("old")
        time.sleep(0.01)
        (briefcases_dir / "new.md").write_text("new")
        monkeypatch.setattr(mcp_mod, "_BRIEFCASES_DIR", briefcases_dir)
        result = json.loads(list_briefcases())
        assert result[0] == "new.md"
        assert result[1] == "old.md"


class TestReadBriefcaseFile:
    def test_reads_valid_file(self, tmp_path, monkeypatch):
        import karma.mcp_server as mcp_mod
        briefcases_dir = tmp_path / "briefcases"
        briefcases_dir.mkdir()
        (briefcases_dir / "test.md").write_text("# Briefcase content")
        monkeypatch.setattr(mcp_mod, "_BRIEFCASES_DIR", briefcases_dir)
        result = read_briefcase_file("test.md")
        assert result == "# Briefcase content"

    def test_path_traversal_rejected(self, tmp_path, monkeypatch):
        import karma.mcp_server as mcp_mod
        briefcases_dir = tmp_path / "briefcases"
        briefcases_dir.mkdir()
        monkeypatch.setattr(mcp_mod, "_BRIEFCASES_DIR", briefcases_dir)
        with pytest.raises(ValueError, match="path traversal"):
            read_briefcase_file("../../etc/passwd")

    def test_nonexistent_file_raises(self, tmp_path, monkeypatch):
        import karma.mcp_server as mcp_mod
        briefcases_dir = tmp_path / "briefcases"
        briefcases_dir.mkdir()
        monkeypatch.setattr(mcp_mod, "_BRIEFCASES_DIR", briefcases_dir)
        with pytest.raises(FileNotFoundError, match="karma://briefcases"):
            read_briefcase_file("does-not-exist.md")


# ---------------------------------------------------------------------------
# Deep Investigation Tools — query_logfire
# ---------------------------------------------------------------------------

class TestQueryLogfire:
    @patch("logfire.query_client.LogfireQueryClient")
    def test_returns_all_entries_for_karma_code(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = lambda s: mock_client
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.query_json_rows.return_value = {
            "columns": [],
            "rows": [
                {"start_timestamp": "2026-03-04T10:00:00Z", "message": "Starting CRM lookup",
                 "event": "GET_CRM", "flag": None, "archetype": "Continuous",
                 "karma_code": "NRD-Sale-101", "agent": "NRD", "type": "Sale",
                 "sub_id": "101", "tool_name": None,
                 "langfuse_trace_url": None, "langfuse_trace_id": None},
                {"start_timestamp": "2026-03-04T10:01:00Z", "message": "CRM failed",
                 "event": "GET_CRM", "flag": "red", "archetype": "Continuous",
                 "karma_code": "NRD-Sale-101", "agent": "NRD", "type": "Sale",
                 "sub_id": "101", "tool_name": None,
                 "langfuse_trace_url": None, "langfuse_trace_id": None},
            ],
        }
        # Need LOGFIRE_READ_TOKEN set for this tool
        with patch.dict("os.environ", {"LOGFIRE_READ_TOKEN": "fake-token"}):
            result = query_logfire("NRD-Sale-101")
        assert len(result) == 2
        assert result[0]["event"] == "GET_CRM"

    @patch("logfire.query_client.LogfireQueryClient")
    def test_event_filter(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = lambda s: mock_client
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.query_json_rows.return_value = {"columns": [], "rows": []}
        with patch.dict("os.environ", {"LOGFIRE_READ_TOKEN": "fake-token"}):
            query_logfire("NRD-Sale-101", event="GET_CRM")
        sql_arg = mock_client.query_json_rows.call_args[1]["sql"]
        assert "attributes->>'event' = 'GET_CRM'" in sql_arg

    def test_invalid_karma_code_raises(self):
        with pytest.raises(ValueError, match="Invalid karma_code format"):
            query_logfire("not valid!")

    def test_invalid_event_filter_raises(self):
        with pytest.raises(ValueError, match="Invalid event filter"):
            query_logfire("NRD-Sale-101", event="DROP TABLE")

    @patch("logfire.query_client.LogfireQueryClient")
    def test_message_contains_escapes_like_wildcards(self, mock_client_cls):
        """message_contains must escape %, _, and ' to prevent SQL injection."""
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = lambda s: mock_client
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.query_json_rows.return_value = {"columns": [], "rows": []}
        with patch.dict("os.environ", {"LOGFIRE_READ_TOKEN": "fake-token"}):
            query_logfire("NRD-Sale-101", message_contains="100% fail_test's")
        sql_arg = mock_client.query_json_rows.call_args[1]["sql"]
        # % and _ must be escaped with backslash, ' must be doubled
        assert "100\\%" in sql_arg
        assert "fail\\_test" in sql_arg
        assert "''" in sql_arg
        assert "ESCAPE" in sql_arg

    def test_limit_capped_at_200(self):
        """Requesting limit > 200 gets capped silently."""
        with patch("logfire.query_client.LogfireQueryClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__ = lambda s: mock_client
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.query_json_rows.return_value = {"columns": [], "rows": []}
            with patch.dict("os.environ", {"LOGFIRE_READ_TOKEN": "fake-token"}):
                query_logfire("NRD-Sale-101", limit=500)
            sql_arg = mock_client.query_json_rows.call_args[1]["sql"]
            assert "LIMIT 200" in sql_arg


# ---------------------------------------------------------------------------
# Deep Investigation Tools — Langfuse
# ---------------------------------------------------------------------------

class TestListLangfuseTraces:
    @patch("karma.mcp_server._get_langfuse_client")
    def test_returns_trace_summaries(self, mock_get_client):
        from datetime import datetime, timezone
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_trace = MagicMock()
        mock_trace.id = "trace-abc"
        mock_trace.name = "NRD-Sale-101"
        mock_trace.timestamp = datetime(2026, 3, 4, 10, 0, tzinfo=timezone.utc)
        mock_trace.latency = 4.2
        mock_trace.total_tokens = 1200
        mock_trace.total_cost = 0.003
        mock_trace.tags = ["production"]
        mock_trace.html_path = "/traces/trace-abc"
        mock_client.trace.list.return_value = MagicMock(data=[mock_trace])
        result = list_langfuse_traces("NRD-Sale-101")
        assert len(result) == 1
        assert result[0]["trace_id"] == "trace-abc"
        assert result[0]["latency_ms"] == 4200.0

    def test_invalid_karma_code_raises(self):
        with pytest.raises(ValueError, match="Invalid karma_code format"):
            list_langfuse_traces("bad!")


class TestGetLangfuseTrace:
    @patch("karma.mcp_server._get_langfuse_client")
    def test_returns_trace_with_observations(self, mock_get_client):
        from datetime import datetime, timezone
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_obs = MagicMock()
        mock_obs.id = "obs-1"
        mock_obs.name = "llm-call"
        mock_obs.type = "GENERATION"
        mock_obs.level = "DEFAULT"
        mock_obs.status_message = None
        mock_obs.start_time = datetime(2026, 3, 4, 10, 0, tzinfo=timezone.utc)
        mock_obs.end_time = datetime(2026, 3, 4, 10, 0, 2, tzinfo=timezone.utc)
        mock_obs.latency = 2.0
        mock_obs.model = "claude-sonnet-4-6"
        mock_obs.usage_details = {"total": 500}
        mock_obs.cost_details = {"total": 0.001}
        mock_obs.usage = None
        mock_obs.parent_observation_id = None
        mock_trace = MagicMock()
        mock_trace.id = "trace-abc"
        mock_trace.name = "NRD-Sale-101"
        mock_trace.session_id = "NRD-Sale-101"
        mock_trace.timestamp = datetime(2026, 3, 4, 10, 0, tzinfo=timezone.utc)
        mock_trace.latency = 4.2
        mock_trace.total_tokens = 500
        mock_trace.total_cost = 0.001
        mock_trace.input = {"prompt": "hello"}
        mock_trace.output = {"response": "world"}
        mock_trace.tags = []
        mock_trace.metadata = {}
        mock_trace.observations = [mock_obs]
        mock_client.trace.get.return_value = mock_trace
        result = get_langfuse_trace("trace-abc")
        assert result["trace_id"] == "trace-abc"
        assert len(result["observations"]) == 1
        assert result["observations"][0]["id"] == "obs-1"
        assert result["observations"][0]["model"] == "claude-sonnet-4-6"

    def test_empty_trace_id_raises(self):
        with pytest.raises(ValueError, match="trace_id"):
            get_langfuse_trace("")


class TestGetLangfuseObservation:
    @patch("karma.mcp_server._get_langfuse_client")
    def test_returns_full_content(self, mock_get_client):
        from datetime import datetime, timezone
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_obs = MagicMock()
        mock_obs.id = "obs-1"
        mock_obs.trace_id = "trace-abc"
        mock_obs.name = "pitch-draft"
        mock_obs.type = "GENERATION"
        mock_obs.level = "ERROR"
        mock_obs.status_message = "Rate limit exceeded"
        mock_obs.start_time = datetime(2026, 3, 4, 10, 0, tzinfo=timezone.utc)
        mock_obs.end_time = datetime(2026, 3, 4, 10, 0, 2, tzinfo=timezone.utc)
        mock_obs.latency = 2.1
        mock_obs.time_to_first_token = 0.5
        mock_obs.model = "claude-sonnet-4-6"
        mock_obs.model_parameters = {"max_tokens": 4096}
        mock_obs.input = "System: You are a sales agent. Draft a pitch for..."
        mock_obs.output = "Error: Rate limit exceeded"
        mock_obs.usage_details = {"input": 200, "output": 10, "total": 210}
        mock_obs.cost_details = {"input": 0.0006, "output": 0.00003, "total": 0.00063}
        mock_obs.parent_observation_id = None
        mock_obs.metadata = {"step": "pitch"}
        mock_obs.prompt_name = "sales-pitch-v2"
        mock_obs.prompt_version = 3
        mock_client.observations.get.return_value = mock_obs
        result = get_langfuse_observation("obs-1")
        # Full content — no truncation
        assert result["input"] == "System: You are a sales agent. Draft a pitch for..."
        assert result["output"] == "Error: Rate limit exceeded"
        assert result["model"] == "claude-sonnet-4-6"
        assert result["time_to_first_token_ms"] == 500.0
        assert result["prompt_name"] == "sales-pitch-v2"

    @patch("karma.mcp_server._get_langfuse_client")
    def test_truncation_with_max_content_length(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_obs = MagicMock()
        mock_obs.id = "obs-1"
        mock_obs.trace_id = "trace-abc"
        mock_obs.name = "big-call"
        mock_obs.type = "GENERATION"
        mock_obs.level = "DEFAULT"
        mock_obs.status_message = None
        mock_obs.start_time = None
        mock_obs.end_time = None
        mock_obs.latency = None
        mock_obs.time_to_first_token = None
        mock_obs.model = None
        mock_obs.model_parameters = None
        mock_obs.input = "A" * 5000
        mock_obs.output = "B" * 5000
        mock_obs.usage_details = {}
        mock_obs.cost_details = {}
        mock_obs.parent_observation_id = None
        mock_obs.metadata = None
        mock_obs.prompt_name = None
        mock_obs.prompt_version = None
        mock_client.observations.get.return_value = mock_obs
        result = get_langfuse_observation("obs-1", max_content_length=100)
        assert len(result["input"]) < 200  # truncated + suffix
        assert "truncated" in result["input"]
        assert "5000 chars total" in result["input"]

    def test_empty_observation_id_raises(self):
        with pytest.raises(ValueError, match="observation_id"):
            get_langfuse_observation("")


class TestListLangfuseObservations:
    @patch("karma.mcp_server._get_langfuse_client")
    def test_returns_observation_summaries(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_obs = MagicMock()
        mock_obs.id = "obs-1"
        mock_obs.name = "llm-call"
        mock_obs.type = "GENERATION"
        mock_obs.level = "ERROR"
        mock_obs.status_message = "Timeout"
        mock_obs.start_time = None
        mock_obs.latency = 3.0
        mock_obs.model = "claude-sonnet-4-6"
        mock_obs.usage_details = {"total": 300}
        mock_obs.cost_details = {"total": 0.0005}
        mock_obs.usage = None
        mock_client.observations.get_many.return_value = MagicMock(data=[mock_obs])
        result = list_langfuse_observations("trace-abc", level="ERROR")
        assert len(result) == 1
        assert result[0]["level"] == "ERROR"
        # Summaries only — no input/output fields
        assert "input" not in result[0]
        assert "output" not in result[0]

    def test_invalid_level_raises(self):
        with pytest.raises(ValueError, match="level must be"):
            list_langfuse_observations("trace-abc", level="CRITICAL")

    def test_invalid_type_raises(self):
        with pytest.raises(ValueError, match="type must be"):
            list_langfuse_observations("trace-abc", type="FUNCTION")

    def test_empty_trace_id_raises(self):
        with pytest.raises(ValueError, match="trace_id"):
            list_langfuse_observations("")


# ---------------------------------------------------------------------------
# Playbook Resources
# ---------------------------------------------------------------------------

class TestPlaybookResources:
    def test_investigation_playbook_contains_tool_names(self):
        result = get_investigation_playbook()
        assert "query_flags" in result
        assert "query_logfire" in result
        assert "list_langfuse_traces" in result
        assert "get_langfuse_trace" in result
        assert "get_langfuse_observation" in result

    def test_quick_check_playbook_contains_tool_names(self):
        result = get_quick_check_playbook()
        assert "query_flags" in result
        assert "get_health" in result
        assert "get_trace_url" in result
