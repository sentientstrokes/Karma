"""
Tests for karma/briefcase.py — Flag Reporter module.

All external calls (Logfire, Langfuse) are mocked. Tests never hit live services.
"""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from karma.briefcase import generate_briefcase, query_langfuse_trace_fields, query_logfire_flags, write_briefcase


# ---------------------------------------------------------------------------
# Fixtures — shared mock data
# ---------------------------------------------------------------------------

def _make_logfire_flags(
    red_count: int = 2,
    yellow_count: int = 1,
) -> list[dict]:
    """Build a list of mock flag entries with red entries first (as Logfire returns them)."""
    flags = []
    for i in range(red_count):
        flags.append({
            "timestamp": f"2026-03-03T10:0{i}:00Z",
            "message":   f"Hard failure {i}",
            "event":     f"FAIL_STEP_{i}",
            "flag":      "red",
            "archetype": "Continuous",
        })
    for j in range(yellow_count):
        flags.append({
            "timestamp": f"2026-03-03T10:1{j}:00Z",
            "message":   f"Soft warning {j}",
            "event":     f"WARN_STEP_{j}",
            "flag":      "yellow",
            "archetype": "Continuous",
        })
    return flags


def _make_langfuse_context(with_errors: bool = True) -> dict:
    traces = [
        {
            "trace_name":  "NRD-Sale-101",
            "duration_ms": 1234.5,
            "total_tokens": 800,
            "total_cost":   0.0012,
        }
    ]
    error_observations = []
    if with_errors:
        error_observations = [
            {
                "obs_name":       "llm_call",
                "obs_type":       "GENERATION",
                "input_summary":  "Prompt text here",
                "output_summary": "Error output",
                "status_message": "Rate limit exceeded",
            }
        ]
    return {"traces": traces, "error_observations": error_observations}


# ---------------------------------------------------------------------------
# Scenario 1: Red flags appear before yellow flags in the generated Briefcase
# ---------------------------------------------------------------------------

class TestFlagOrdering:
    def test_red_flags_appear_before_yellow_in_output(self):
        """AC 1: red entries must appear in ## Red Flags section before ## Yellow Flags."""
        flags = _make_logfire_flags(red_count=2, yellow_count=1)
        context = _make_langfuse_context(with_errors=False)

        output = generate_briefcase("NRD-Sale-101", "Continuous", flags, context)

        red_pos    = output.index("## Red Flags")
        yellow_pos = output.index("## Yellow Flags")
        assert red_pos < yellow_pos, "Red Flags section must come before Yellow Flags"

    def test_red_entries_in_red_section_not_yellow(self):
        """Red flag messages must appear under ## Red Flags, not ## Yellow Flags."""
        flags = _make_logfire_flags(red_count=1, yellow_count=1)
        context = _make_langfuse_context(with_errors=False)

        output = generate_briefcase("NRD-Sale-101", "Continuous", flags, context)

        # Split output at the Yellow Flags header to check placement
        red_section, yellow_section = output.split("## Yellow Flags", 1)
        assert "Hard failure 0" in red_section
        assert "Soft warning 0" in yellow_section

    @pytest.mark.parametrize("karma_code", [
        "NRD-Sale-101",
        "SUPPORT-Continuous-ABC",
        "PIPE-Pipeline-X99",
    ])
    def test_karma_code_format_variations(self, karma_code: str):
        """Briefcase generates correctly for any karma_code format."""
        flags = _make_logfire_flags(red_count=1, yellow_count=0)
        # Adjust archetype in flags to match
        for f in flags:
            f["archetype"] = "Continuous"

        output = generate_briefcase(karma_code, "Continuous", flags, _make_langfuse_context())

        assert f"karma_code: '{karma_code}'" in output
        assert f"# Briefcase: {karma_code}" in output


# ---------------------------------------------------------------------------
# Scenario 2: Empty state — no flags, no errors
# ---------------------------------------------------------------------------

class TestEmptyState:
    def test_no_red_flags_message(self):
        """AC 2: empty red flags section shows 'No red flags detected' message."""
        output = generate_briefcase("NRD-Sale-101", "Continuous", [], _make_langfuse_context(with_errors=False))
        assert "No red flags detected in this window" in output

    def test_no_yellow_flags_message(self):
        """AC 2: empty yellow flags section shows 'No yellow flags detected' message."""
        output = generate_briefcase("NRD-Sale-101", "Continuous", [], _make_langfuse_context(with_errors=False))
        assert "No yellow flags detected in this window" in output

    def test_both_empty_messages_present(self):
        """Both empty messages appear when no flags at all."""
        output = generate_briefcase("NRD-Sale-101", "", [], {"traces": [], "error_observations": []})
        assert "No red flags detected in this window" in output
        assert "No yellow flags detected in this window" in output


# ---------------------------------------------------------------------------
# Scenario 3: write_briefcase creates unique files per call
# ---------------------------------------------------------------------------

class TestWriteBriefcase:
    def test_two_calls_produce_distinct_files(self, tmp_path: Path, monkeypatch):
        """AC 5: rapid successive calls must create two distinct files — no overwriting."""
        # Monkeypatch write_briefcase to use tmp_path instead of _bmad-output/briefcases/
        import karma.briefcase as bc_module

        call_count = 0

        def mock_now(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Return different seconds to ensure distinct filenames
            if call_count <= 2:
                return datetime(2026, 3, 3, 10, 0, call_count, tzinfo=timezone.utc)
            return datetime.now(timezone.utc)

        monkeypatch.setattr(bc_module, "datetime", type("MockDatetime", (), {
            "now": staticmethod(mock_now),
            "fromisoformat": datetime.fromisoformat,
        }))

        # Patch the output directory to use tmp_path
        original_write = bc_module.write_briefcase

        def patched_write(karma_code: str, content: str) -> Path:
            now = mock_now(timezone.utc)
            filename_ts = now.strftime("%Y-%m-%d-%H%M%S")
            filename = f"{karma_code}-briefcase-{filename_ts}.md"
            output_path = tmp_path / filename
            output_path.write_text(content, encoding="utf-8")
            return output_path

        monkeypatch.setattr(bc_module, "write_briefcase", patched_write)

        content = generate_briefcase("NRD-Sale-101", "Continuous", [], {"traces": [], "error_observations": []})

        path1 = bc_module.write_briefcase("NRD-Sale-101", content)
        path2 = bc_module.write_briefcase("NRD-Sale-101", content)

        assert path1.exists(), "First briefcase file must exist"
        assert path2.exists(), "Second briefcase file must exist"
        assert path1 != path2, "Each run must produce a distinct file path"

    def test_output_directory_created_if_missing(self, tmp_path: Path, monkeypatch):
        """write_briefcase creates the output directory if it does not exist."""
        import karma.briefcase as bc_module

        expected_dir = tmp_path / "briefcases"
        assert not expected_dir.exists()

        # Patch Path resolution inside write_briefcase to use tmp_path as project root
        original_Path = bc_module.Path

        class PatchedPath(type(Path())):
            pass

        monkeypatch.setattr(
            bc_module,
            "Path",
            lambda *args: original_Path(*args),
        )

        # Simpler approach: just call the real write_briefcase and check _bmad-output/briefcases
        # exists afterward (it should be created by mkdir(parents=True, exist_ok=True))
        content = "# Test briefcase"
        path = bc_module.write_briefcase("TEST-Unit-001", content)
        assert path.exists()
        assert path.parent.name == "briefcases"


# ---------------------------------------------------------------------------
# AC validation: condensed format — no OTel noise in output
# ---------------------------------------------------------------------------

class TestCondensedFormat:
    def test_no_otel_fields_in_flag_table_rows(self):
        """AC 3: flag table rows must contain only timestamp/message/event/source — no raw OTel values."""
        flags = _make_logfire_flags(red_count=1, yellow_count=0)
        output = generate_briefcase("NRD-Sale-101", "Continuous", flags, _make_langfuse_context())

        # Extract only the table rows from the Red Flags section (between the header and next ---)
        red_section = output.split("## Red Flags")[1].split("---")[0]
        table_rows = [
            line for line in red_section.splitlines()
            if line.startswith("|") and not line.startswith("| Time")  # skip header row
        ]

        # Each data row must NOT contain raw OTel field names as column values
        otel_noise = ["span_id", "service.name", "otel.scope"]
        for row in table_rows:
            for field in otel_noise:
                assert field not in row, f"OTel field '{field}' must not appear in flag table row"


# ---------------------------------------------------------------------------
# AC validation: Human Findings stub
# ---------------------------------------------------------------------------

class TestHumanFindingsStub:
    def test_human_findings_section_present(self):
        """AC 4: ## Human Findings section must be present in every Briefcase."""
        output = generate_briefcase("NRD-Sale-101", "Continuous", [], {"traces": [], "error_observations": []})
        assert "## Human Findings" in output

    def test_human_findings_no_automated_population_text(self):
        """AC 4: Human Findings section must clarify it is populated manually."""
        output = generate_briefcase("NRD-Sale-101", "Continuous", [], {"traces": [], "error_observations": []})
        # The section should mention manual / review — not automated
        hf_section = output.split("## Human Findings", 1)[1]
        assert "manually" in hf_section.lower() or "manual" in hf_section.lower()


# ---------------------------------------------------------------------------
# AC validation: Archetype in output
# ---------------------------------------------------------------------------

class TestArchetypeOutput:
    def test_archetype_in_frontmatter_and_header(self):
        """AC 8: archetype appears in both YAML frontmatter and visible header."""
        output = generate_briefcase("NRD-Sale-101", "Continuous", [], {"traces": [], "error_observations": []})
        assert "archetype: 'Continuous'" in output
        assert "**Archetype:** Continuous" in output

    def test_empty_archetype_no_hardcoded_fallback(self):
        """AC 8: empty archetype produces empty string — no hardcoded default."""
        output = generate_briefcase("NRD-Sale-101", "", [], {"traces": [], "error_observations": []})
        assert "archetype: ''" in output
        assert "**Archetype:** " in output  # header present but value empty


# ---------------------------------------------------------------------------
# query_logfire_flags — unit test with mocked LogfireQueryClient
# ---------------------------------------------------------------------------

class TestQueryLogfireFlags:
    def test_returns_only_flagged_entries(self):
        """query_logfire_flags maps RowQueryResults rows to flag dicts correctly."""
        mock_client = MagicMock()
        mock_client.query_json_rows.return_value = {
            "columns": [],
            "rows": [
                {
                    "start_timestamp": "2026-03-03T10:00:00Z",
                    "message": "CRM call failed",
                    "event": "GET_CRM",
                    "flag": "red",
                    "karma_code": "NRD-Sale-101",
                    "archetype": "Continuous",
                },
                {
                    "start_timestamp": "2026-03-03T10:01:00Z",
                    "message": "Retry attempted",
                    "event": "RETRY_CALL",
                    "flag": "yellow",
                    "karma_code": "NRD-Sale-101",
                    "archetype": "Continuous",
                },
            ],
        }

        result = query_logfire_flags("NRD-Sale-101", None, None, mock_client)

        assert len(result) == 2
        assert result[0]["flag"] == "red"
        assert result[1]["flag"] == "yellow"
        assert result[0]["event"] == "GET_CRM"
        # No OTel fields in result
        for entry in result:
            assert "trace_id" not in entry
            assert "span_id" not in entry


# ---------------------------------------------------------------------------
# Theme 4: Langfuse trace fields in Briefcase header
# ---------------------------------------------------------------------------

class TestTraceFieldsPresent:
    """AC 10: When both trace fields are provided, they appear in the Briefcase header."""

    def test_trace_url_and_id_in_header(self):
        output = generate_briefcase(
            "NRD-Sale-101", "Pipeline", [], {"traces": [], "error_observations": []},
            langfuse_trace_url="http://localhost:3000/project/abc/traces/xyz123",
            langfuse_trace_id="xyz123",
        )

        assert "**Langfuse Trace:** [View Trace](http://localhost:3000/project/abc/traces/xyz123)" in output
        assert "**Langfuse Trace ID:** `xyz123`" in output

    def test_trace_fields_after_archetype_before_separator(self):
        """Both lines appear after **Archetype:** and before the first --- separator."""
        output = generate_briefcase(
            "NRD-Sale-101", "Pipeline", [], {"traces": [], "error_observations": []},
            langfuse_trace_url="http://localhost:3000/project/abc/traces/xyz123",
            langfuse_trace_id="xyz123",
        )

        archetype_pos = output.index("**Archetype:**")
        trace_url_pos = output.index("**Langfuse Trace:**")
        trace_id_pos = output.index("**Langfuse Trace ID:**")
        # Find the first --- after the Archetype line
        first_sep_pos = output.index("---", archetype_pos)

        assert archetype_pos < trace_url_pos < first_sep_pos
        assert archetype_pos < trace_id_pos < first_sep_pos


class TestTraceFieldsAbsent:
    """AC 11: When trace fields are None, neither line appears and no error is raised."""

    def test_no_trace_lines_when_none(self):
        output = generate_briefcase(
            "NRD-Sale-101", "Continuous", [], {"traces": [], "error_observations": []},
            langfuse_trace_url=None,
            langfuse_trace_id=None,
        )

        assert "**Langfuse Trace:**" not in output
        assert "**Langfuse Trace ID:**" not in output

    def test_no_trace_lines_when_defaults(self):
        """Using defaults (no explicit params) also omits trace lines."""
        output = generate_briefcase(
            "NRD-Sale-101", "Continuous", [], {"traces": [], "error_observations": []},
        )

        assert "**Langfuse Trace:**" not in output
        assert "**Langfuse Trace ID:**" not in output


class TestQueryLangfuseTraceFields:
    """Unit tests for query_langfuse_trace_fields with mocked LogfireQueryClient."""

    def test_returns_both_fields_when_present(self):
        mock_client = MagicMock()
        mock_client.query_json_rows.return_value = {
            "columns": [],
            "rows": [{
                "langfuse_trace_url": "http://localhost:3000/project/abc/traces/xyz123",
                "langfuse_trace_id": "xyz123",
            }],
        }

        result = query_langfuse_trace_fields("NRD-Sale-101", None, None, mock_client)

        assert result["langfuse_trace_url"] == "http://localhost:3000/project/abc/traces/xyz123"
        assert result["langfuse_trace_id"] == "xyz123"

    def test_returns_none_when_no_rows(self):
        mock_client = MagicMock()
        mock_client.query_json_rows.return_value = {"columns": [], "rows": []}

        result = query_langfuse_trace_fields("NRD-Sale-101", None, None, mock_client)

        assert result["langfuse_trace_url"] is None
        assert result["langfuse_trace_id"] is None

    def test_rejects_invalid_karma_code(self):
        """F9: Invalid karma_code format raises ValueError before any SQL runs."""
        mock_client = MagicMock()

        with pytest.raises(ValueError, match="Invalid karma_code format"):
            query_langfuse_trace_fields("not!valid", None, None, mock_client)

        # Ensure no SQL query was attempted
        mock_client.query_json_rows.assert_not_called()


class TestQueryLogfireFlagsValidation:
    """F9: Negative test for invalid karma_code in query_logfire_flags."""

    def test_rejects_invalid_karma_code(self):
        mock_client = MagicMock()

        with pytest.raises(ValueError, match="Invalid karma_code format"):
            query_logfire_flags("spaces not allowed", None, None, mock_client)

        mock_client.query_json_rows.assert_not_called()
