---
title: 'KARMA MCP Server'
slug: 'karma-mcp-server'
created: '2026-03-04'
status: 'completed'
stepsCompleted: [1, 2, 3, 4]
tech_stack:
  - Python 3.11+
  - mcp>=1.0.0 (FastMCP, Python MCP SDK)
  - karma/briefcase.py (existing engine)
  - karma/health.py (existing engine)
  - logfire.query_client.LogfireQueryClient
  - langfuse.api.client.FernLangfuse
  - python-dotenv
  - pytest + unittest.mock.MagicMock
files_to_modify:
  - pyproject.toml (add mcp>=1.0.0 dependency)
  - karma/utils.py (NEW - extract parse_since)
  - karma/mcp_server.py (NEW - FastMCP server)
  - scripts/mcp_server.py (NEW - entry point)
  - scripts/briefcase.py (replace inline parse_since with import)
  - scripts/health.py (replace inline parse_since with import)
  - tests/test_mcp_server.py (NEW - unit tests)
  - tests/test_utils.py (NEW - parse_since unit tests)
  - docs/KARMA_LOG.md (add Theme 6 entry)
code_patterns:
  - FastMCP decorator style - @mcp.tool(), @mcp.resource()
  - Quick-check layer wraps existing karma/ engine functions
  - Deep investigation layer calls LogfireQueryClient + FernLangfuse directly in mcp_server.py
  - karma_code validated via KARMA_CODE_PATTERN before any API call
  - Credentials via os.getenv() after load_dotenv in entry point
  - _get_langfuse_client() helper centralises FernLangfuse construction (used by 4 Langfuse tools)
  - Synchronous karma functions called directly from async MCP handlers
  - Never swallow exceptions - ValueError and EnvironmentError propagate to MCP client
test_patterns:
  - pytest with MagicMock patching karma.mcp_server module functions
  - patch("karma.mcp_server.query_logfire_flags", return_value=[...])
  - Never hit live Logfire or Langfuse in tests
  - Test happy path and error/empty cases per tool
---

# Tech-Spec: KARMA MCP Server

**Created:** 2026-03-04

## Overview

### Problem Statement

Dev AI tools (Claude Code, Cursor, etc.) have no direct programmatic access to Karma observability data. They must read flat files manually or invoke CLI scripts (`scripts/briefcase.py`, `scripts/health.py`) with shell commands. There is no MCP surface that accepts a `karma_code` and returns structured Karma data. An AI debugging a failing agent run must either grep through briefcase markdown files or construct shell invocations — neither is ergonomic for a machine consumer.

### Solution

Build a Python MCP server using the `mcp` SDK (FastMCP) over stdio with two layers:

**Quick-Check Layer (4 tools)** — wraps existing `karma/briefcase.py` and `karma/health.py` for fast answers: briefcase reports, health counters, flag queries, trace URLs.

**Deep Investigation Layer (5 tools)** — calls `LogfireQueryClient` and `FernLangfuse` directly for unrestricted browsing: all Logfire logs (not just flagged), Langfuse trace trees, individual observations with full prompt/completion text (no truncation).

**Playbook Resources (2)** — static investigation playbooks that teach the AI consumer the optimal tool-chaining sequence before it starts investigating.

A dev AI running in Claude Code or Cursor adds one stanza to its MCP config and gains a full investigation surface keyed by `karma_code` — no file system navigation, no CLI invocation, no guessing which tool to use.

### Scope

**In Scope:**
- `karma/utils.py` — extract shared `parse_since` utility (currently duplicated in both CLI scripts)
- `karma/mcp_server.py` — FastMCP server with 9 tools, 2 briefcase resources, 2 playbook resources
- `scripts/mcp_server.py` — thin entry point (env load + `mcp.run()`)
- `pyproject.toml` — add `mcp>=1.0.0` dependency
- `scripts/briefcase.py` + `scripts/health.py` — replace inline `parse_since` with import from `karma.utils`
- `tests/test_mcp_server.py` — unit tests for all 9 tools + resources (mocked)
- `tests/test_utils.py` — parse_since unit tests
- `docs/KARMA_LOG.md` — Theme 6 entry added to "What Your Instrumentation Unlocks" section

**Out of Scope:**
- SSE/HTTP/WebSocket transport (stdio only)
- Authentication on the MCP server itself (stdio is process-level isolated)
- Langfuse write operations (MCP is read-only)
- Health CSV appending from MCP — `get_health` returns JSON only; CSV writes remain the CLI's job
- Raw SQL exposure — `query_logfire` uses structured filters, not user-supplied SQL
- A web UI or dashboard plugin

---

## Context for Development

### Codebase Patterns

- **Package manager:** `uv` exclusively — `uv add mcp`, `uv run python scripts/mcp_server.py`
- **Scripts/ = entry points only.** All reusable logic goes in `karma/`. `scripts/mcp_server.py` is a thin wrapper that loads env and calls `mcp.run()`.
- **No classes unless clearly necessary.** FastMCP uses function decorators — fits project style perfectly.
- **`karma_code` validation:** Always `KARMA_CODE_PATTERN.match(karma_code)` from `karma/__init__.py` BEFORE any SQL or API call. Raise `ValueError("Invalid karma_code format: ...")` on failure.
- **Credentials pattern (from scripts/):**
  ```python
  _env_path = Path(__file__).parent.parent.parent / "AgentManual" / ".env"
  load_dotenv(_env_path)
  ```
  Entry point loads env. `karma/mcp_server.py` reads via `os.getenv()` — never calls `load_dotenv` itself.
- **Logfire query pattern:** `with LogfireQueryClient(read_token=os.getenv("LOGFIRE_READ_TOKEN")) as client:` — context manager per request.
- **Error handling:** Never swallow. ValueError and EnvironmentError propagate naturally from tool handlers to the MCP client as error responses.
- **Module docstrings:** Every new file gets a module-level docstring (one paragraph max).
- **Inline comments:** All non-trivial logic must have inline comments explaining "why."
- **Line length:** 100 chars (ruff config).
- **`parse_since` duplication:** Both scripts contain identical `parse_since()` with a `# SYNC:` comment. Extract to `karma/utils.py`. Delete the inline copies and the SYNC comments.
- **Async:** MCP tool handlers are `async def`. Karma module functions are synchronous — call directly from async handlers (no `await` needed, no event loop conflicts).
- **`_bmad-output/briefcases/` path:** Resolved in `karma/briefcase.py` as `Path(__file__).parent.parent / "_bmad-output" / "briefcases"`. MCP resource handlers use the same absolute resolution.

### Files to Reference

| File | Purpose |
| ---- | ------- |
| `karma/__init__.py` | `KARMA_CODE_PATTERN` — import for validation |
| `karma/briefcase.py` | Engine: `generate_briefcase`, `query_logfire_flags`, `query_langfuse_trace_fields`, `query_langfuse_context`, `write_briefcase` |
| `karma/health.py` | Engine: `query_logfire_health`, `query_langfuse_health`, `CSV_FIELDNAMES` |
| `scripts/briefcase.py` | `parse_since` reference implementation (lines 50–86) + orchestration pattern |
| `scripts/health.py` | Orchestration pattern for health queries |
| `tests/test_briefcase.py` | MagicMock patterns and test structure to follow |
| `_bmad-output/project-context.md` | All implementation rules — follow exactly |

### Technical Decisions

1. **FastMCP over low-level `Server`:** FastMCP is the standard Python MCP approach — cleaner decorator API, fits project's "prefer functions" rule.

2. **`get_briefcase` behavior:** Always generates fresh data. Writes .md file as side effect (same as CLI). Returns `{"content": str, "path": str}`.

3. **`get_health` behavior:** Returns structured JSON dict (all 13 health fields). Does NOT call `append_health_row` — MCP is a read surface; CSV appending is the CLI's permanent record job. Automated MCP calls during debugging must not pollute the health log.

4. **Time window parameters:** All tools accept optional `since` (ISO string like `"2026-03-03T09:00:00"` or relative shorthand `"2h"`, `"30m"`, `"1d"`) and optional `until` (ISO string; defaults to `datetime.now(timezone.utc)` if omitted). Parsed via `parse_since()` from `karma.utils`.

5. **Resource URI scheme:** `karma://briefcases` → JSON list of filenames; `karma://briefcases/{filename}` → file content as string. `karma://playbook/investigation` → YOLO investigation playbook. `karma://playbook/quick-check` → fast-path monitoring playbook.

6. **Server entry:** `uv run python scripts/mcp_server.py`. Claude Code config: `{"command": "uv", "args": ["run", "python", "scripts/mcp_server.py"], "cwd": "<abs-path-to-Karma>"}`.

7. **`parse_since` extraction:** New `karma/utils.py` exports `parse_since(value: str | None) -> datetime | None`. Both CLI scripts drop their inline copies and import from `karma.utils`.

8. **`LogfireQueryClient` import placement (F1):** `LogfireQueryClient` is imported inside each tool handler (not at module level) to simplify test patching via `patch("karma.mcp_server.LogfireQueryClient")`. Trade-off: a fresh import per call, acceptable for a debug-tooling server with low call frequency. If this is refactored to module-level in future, update test patches accordingly.

9. **`_BRIEFCASES_DIR` path assumption (F2):** `Path(__file__).parent.parent / "_bmad-output" / "briefcases"` resolves correctly only when the Karma package is run from the repo directory. MCP config **must** set `cwd` to the absolute path of the Karma repo root. This is documented in the `scripts/mcp_server.py` docstring. If cwd is wrong, the resource handler silently returns an empty list (directory not found — no crash, just no files).

10. **Two-layer architecture:** Quick-check tools (1–4) wrap existing karma/ functions. Deep investigation tools (5–9) call `LogfireQueryClient` and `FernLangfuse` directly inside `karma/mcp_server.py` — no new karma/ modules needed. The MCP server IS the orchestration layer for deep investigation.

11. **`_get_langfuse_client()` helper:** Centralises `FernLangfuse` construction (credential loading, base_url, auth). Used by `list_langfuse_traces`, `get_langfuse_trace`, `get_langfuse_observation`, and `list_langfuse_observations`. Raises `EnvironmentError` if credentials are missing.

12. **`query_logfire` — structured filters, not raw SQL:** Builds parameterised SQL from keyword arguments (`event`, `flag`, `message_contains`). The AI cannot inject arbitrary SQL. This is safer than raw SQL exposure and sufficient for investigation — the AI can filter by event, flag, message substring, and time window.

13. **Langfuse return shape — verified API types:**
    - `client.trace.get(trace_id)` returns `TraceWithFullDetails` — includes `observations` list, `latency` (seconds), `total_cost` (USD), `html_path`, `scores`.
    - `client.observations.get(observation_id)` returns `ObservationsView` — includes full `input`, `output` (Any — no truncation), `model`, `usage_details` (dict), `cost_details` (dict), `latency` (seconds), `time_to_first_token` (seconds), `level`, `status_message`, `parent_observation_id`.
    - Both confirmed in installed SDK at `.venv/lib/python3.13/site-packages/langfuse/api/`.

14. **Playbook resources — static investigation instructions:** Two `karma://playbook/` resources that teach an AI consumer the optimal tool-chaining sequence. Zero API calls, zero latency — just static strings returned by the MCP server. An AI reads the playbook before investigating, eliminating trial-and-error tool discovery.

---

## Implementation Plan

### Tasks

- [x] Task 1: Extract `parse_since` to `karma/utils.py` and update both scripts
- [x] Task 2: Add `mcp>=1.8.0` to `pyproject.toml`
- [x] Task 3: Create `karma/mcp_server.py` — Quick-Check Layer (4 tools + 2 briefcase resources)
- [x] Task 4: Create `karma/mcp_server.py` — Deep Investigation Layer (5 tools)
- [x] Task 5: Create `karma/mcp_server.py` — Playbook Resources (2 playbook resources)
- [x] Task 6: Create `scripts/mcp_server.py` (thin entry point)
- [x] Task 7: Create `tests/test_utils.py` (parse_since unit tests)
- [x] Task 8: Create `tests/test_mcp_server.py` (all 9 tools + resources unit tests)
- [x] Task 9: Update `docs/KARMA_LOG.md` (add Theme 6 entry)

---

Tasks ordered by dependency — implement top to bottom.

---

**Task 1 — Extract `parse_since` to `karma/utils.py` + update both scripts**

Three files, one atomic change. Do all three before moving on.

**1a. Create `karma/utils.py`** — copy `parse_since` verbatim from `scripts/briefcase.py` lines 50–86. No logic changes.

```python
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
```

**1b. Update `scripts/briefcase.py`** — replace the inline `parse_since` function body (lines ~50–86) with a single import. Delete the `# SYNC:` comment — it is no longer true. Check: `re` is also used for `KARMA_CODE_PATTERN` validation inline in `scripts/briefcase.py` — keep the `import re` line if so, remove if `parse_since` was its only use.

```python
from karma.utils import parse_since
```

**1c. Update `scripts/health.py`** — same change. Replace inline `parse_since` with the import. Delete `# SYNC:` comment. Check `import re` — remove if only used by `parse_since`.

---

**Task 2 — Update `pyproject.toml`**

Add `mcp>=1.0.0` to `[project.dependencies]`:

```toml
dependencies = [
    "logfire>=4.25.0",
    "langfuse>=3.14.5",
    "python-dotenv>=1.2.2",
    "mcp>=1.0.0",
]
```

---

**Task 3 — Create `karma/mcp_server.py` — Quick-Check Layer**

The MCP server module. Module-level docstring, then FastMCP instance, then 4 quick-check tool functions and 2 briefcase resource functions. No `load_dotenv` here — that's the entry point's job. Task 4 adds the deep investigation tools to the same file. Task 5 adds playbook resources.

```python
"""
Karma MCP Server.

Exposes Karma observability data (Briefcase, Health, flags, trace URLs) as MCP tools
and resources, keyed by karma_code. A thin orchestration layer over karma/briefcase.py
and karma/health.py — no new query logic is written here.

Transport: stdio (standard for Claude Code and Cursor MCP integration).
Credentials: loaded from AgentManual/.env by scripts/mcp_server.py before import.
"""

import os
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from karma import KARMA_CODE_PATTERN
from karma.briefcase import (
    generate_briefcase,
    query_langfuse_context,
    query_langfuse_trace_fields,
    query_logfire_flags,
    write_briefcase,
)
from karma.health import query_langfuse_health, query_logfire_health
from karma.utils import parse_since

# ---------------------------------------------------------------------------
# Server instance — name shown in MCP client tool listings
# ---------------------------------------------------------------------------

mcp = FastMCP("karma")

# Path to briefcases directory — resolved relative to this file's package root.
# karma/mcp_server.py → karma/ → Karma/ → _bmad-output/briefcases/
_BRIEFCASES_DIR = Path(__file__).parent.parent / "_bmad-output" / "briefcases"


# ---------------------------------------------------------------------------
# Internal validation helper
# ---------------------------------------------------------------------------

def _validate_karma_code(karma_code: str) -> None:
    """Raise ValueError if karma_code does not match KARMA_CODE_PATTERN."""
    if not KARMA_CODE_PATTERN.match(karma_code):
        raise ValueError(
            f"Invalid karma_code format: {karma_code!r}. "
            "Expected 2-4 hyphen-delimited segments of alphanumeric/underscore chars "
            "(e.g. NRD-Sale-101, Ingest-start, Ingest-INE-R01Row12)"
        )


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_briefcase(
    karma_code: str,
    since: str | None = None,
    until: str | None = None,
) -> dict:
    """
    Generate a Karma Briefcase report for the given karma_code.

    Queries Logfire for red/yellow flagged entries and Langfuse for trace summaries
    and errored observations. Always generates fresh data — does not cache.
    Writes the Briefcase .md file to _bmad-output/briefcases/ as a side effect.

    Args:
        karma_code: The Karma Code to inspect (e.g. NRD-Sale-101).
        since: Optional time window start. Relative (2h, 30m, 1d) or ISO 8601 string.
        until: Optional time window end. ISO 8601 string ONLY — do NOT pass relative
               shorthand (e.g. "2h") for until, as parse_since treats relative values
               as "N units in the past", which is wrong for an upper bound. Defaults to now.

    Returns:
        {"content": str, "path": str} — Briefcase markdown and absolute file path.
    """
    _validate_karma_code(karma_code)

    since_dt = parse_since(since)
    # until uses parse_since for ISO parsing only. Relative shorthand (e.g. "2h") is
    # semantically incorrect for an upper bound — it would produce a datetime in the past.
    # Callers should always pass an ISO string or omit until entirely (defaults to now).
    until_dt = parse_since(until) if until else datetime.now(timezone.utc)

    # Capture now ONCE — pass to both generate_briefcase and write_briefcase to ensure
    # the filename embedded in the document body matches the actual file on disk.
    # If now is not passed, each function computes its own datetime.now() independently,
    # and calls straddling a second boundary produce a mismatched filename. (F5 fix)
    briefcase_now = datetime.now(timezone.utc)

    from logfire.query_client import LogfireQueryClient

    with LogfireQueryClient(read_token=os.getenv("LOGFIRE_READ_TOKEN")) as lf_client:
        logfire_flags  = query_logfire_flags(karma_code, since_dt, until_dt, lf_client)
        trace_fields   = query_langfuse_trace_fields(karma_code, since_dt, until_dt, lf_client)

    # Infer archetype from first flagged row — "" if no flagged rows (honest unknown)
    archetype = logfire_flags[0].get("archetype", "") if logfire_flags else ""

    # query_langfuse_context accepts ONLY two args: (karma_code, since).
    # It does NOT accept until_dt — do NOT add a third argument here.
    # It constructs its own FernLangfuse client internally — mock via
    # patch("karma.briefcase.query_langfuse_context", return_value=...) in tests.
    langfuse_context = query_langfuse_context(karma_code, since_dt)

    content = generate_briefcase(
        karma_code, archetype, logfire_flags, langfuse_context,
        langfuse_trace_url=trace_fields["langfuse_trace_url"],
        langfuse_trace_id=trace_fields["langfuse_trace_id"],
        now=briefcase_now,   # F5: same now for generate + write ensures filename consistency
    )
    output_path = write_briefcase(karma_code, content, now=briefcase_now)

    return {"content": content, "path": str(output_path)}


@mcp.tool()
def get_health(
    karma_code: str,
    since: str | None = None,
    until: str | None = None,
) -> dict:
    """
    Return health vital signs for the given karma_code as structured JSON.

    Queries Logfire for flag counts and archetype-specific metrics, and Langfuse
    for trace-level metrics and error observation count.

    NOTE: This tool does NOT append to health-log.csv. That is the CLI's job.
    MCP is a read surface — use `uv run python scripts/health.py` to record a
    permanent health snapshot.

    Args:
        karma_code: The Karma Code to inspect.
        since: Optional time window start. Relative (2h, 30m, 1d) or ISO 8601 string.
        until: Optional time window end. ISO 8601 string. Defaults to now.

    Returns:
        Dict with 13 health fields: karma_code, archetype, red_flag_count,
        yellow_flag_count, trace_count, total_tokens, total_cost_usd,
        total_latency_ms, error_observation_count, lifecycle_status,
        session_turn_count, window_from, window_to.
        Note: `generated_at` from CSV_FIELDNAMES is intentionally omitted — it is a
        record-write timestamp relevant only to the CSV sink, not to a query result.
    """
    _validate_karma_code(karma_code)

    since_dt = parse_since(since)
    until_dt = parse_since(until) if until else datetime.now(timezone.utc)

    logfire_data  = query_logfire_health(karma_code, since_dt, until_dt)
    langfuse_data = query_langfuse_health(karma_code, since_dt, until_dt)

    archetype = logfire_data.get("archetype", "")

    return {
        "karma_code":              karma_code,
        "archetype":               archetype,
        "window_from":             since_dt.isoformat() if since_dt else "",
        "window_to":               until_dt.isoformat(),
        "red_flag_count":          logfire_data["red_flag_count"],
        "yellow_flag_count":       logfire_data["yellow_flag_count"],
        "trace_count":             langfuse_data["trace_count"],
        "total_tokens":            langfuse_data["total_tokens"],
        "total_cost_usd":          langfuse_data["total_cost_usd"],
        "total_latency_ms":        langfuse_data["total_latency_ms"],
        "error_observation_count": langfuse_data["error_observation_count"],
        "lifecycle_status":        logfire_data.get("lifecycle_status", ""),
        "session_turn_count":      logfire_data.get("session_turn_count", ""),
    }


@mcp.tool()
def query_flags(
    karma_code: str,
    flag: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """
    Query Logfire for flagged log entries for the given karma_code.

    Args:
        karma_code: The Karma Code to inspect.
        flag: Optional filter — "red" for hard failures only, "yellow" for soft only.
              Omit to return all flagged entries (red + yellow).
        since: Optional time window start. Relative (2h, 30m, 1d) or ISO 8601 string.
        until: Optional time window end. ISO 8601 string. Defaults to now.

    Returns:
        List of flag entry dicts: [{timestamp, message, event, flag, archetype}, ...]
    """
    _validate_karma_code(karma_code)

    if flag is not None and flag not in ("red", "yellow"):
        raise ValueError("flag must be 'red', 'yellow', or None")

    since_dt = parse_since(since)
    until_dt = parse_since(until) if until else datetime.now(timezone.utc)

    from logfire.query_client import LogfireQueryClient

    with LogfireQueryClient(read_token=os.getenv("LOGFIRE_READ_TOKEN")) as lf_client:
        entries = query_logfire_flags(karma_code, since_dt, until_dt, lf_client)

    # Filter by flag value in Python — Logfire query already returns all flagged entries
    if flag is not None:
        entries = [e for e in entries if e.get("flag") == flag]

    return entries


@mcp.tool()
def get_trace_url(
    karma_code: str,
    since: str | None = None,
    until: str | None = None,
) -> dict:
    """
    Retrieve the Langfuse trace URL and trace ID embedded in Logfire for the given karma_code.

    These fields are set by the Karma Infinity Loop pattern — the pipeline entry point
    embeds langfuse_trace_url and langfuse_trace_id into the first Logfire span.

    Args:
        karma_code: The Karma Code to inspect.
        since: Optional time window start.
        until: Optional time window end. Defaults to now.

    Returns:
        {"langfuse_trace_url": str | None, "langfuse_trace_id": str | None}
        Both are None if the pipeline did not embed trace fields (Infinity Loop not active).
    """
    _validate_karma_code(karma_code)

    since_dt = parse_since(since)
    until_dt = parse_since(until) if until else datetime.now(timezone.utc)

    from logfire.query_client import LogfireQueryClient

    with LogfireQueryClient(read_token=os.getenv("LOGFIRE_READ_TOKEN")) as lf_client:
        return query_langfuse_trace_fields(karma_code, since_dt, until_dt, lf_client)


# ---------------------------------------------------------------------------
# Resources — expose _bmad-output/briefcases/ as a browsable resource set
# ---------------------------------------------------------------------------

@mcp.resource("karma://briefcases")
def list_briefcases() -> str:
    """
    List all Briefcase files in _bmad-output/briefcases/.

    Returns a JSON array of filenames, sorted by modification time (newest first).
    Returns an empty array if the directory does not exist yet.
    """
    import json

    if not _BRIEFCASES_DIR.exists():
        return json.dumps([])

    files = sorted(
        _BRIEFCASES_DIR.glob("*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,   # newest first
    )
    return json.dumps([f.name for f in files])


@mcp.resource("karma://briefcases/{filename}")
def read_briefcase_file(filename: str) -> str:
    """
    Read the content of a specific Briefcase file.

    Args:
        filename: The .md filename (e.g. NRD-Sale-101-briefcase-2026-03-04-120000.md).

    Returns:
        Full markdown content of the Briefcase file.

    Raises:
        FileNotFoundError if the file does not exist.
    """
    file_path = (_BRIEFCASES_DIR / filename).resolve()

    # Path traversal guard — reject filenames like "../../karma/__init__.py".
    # resolve() expands ".." segments; is_relative_to() ensures the result stays
    # inside _BRIEFCASES_DIR. Raises ValueError on escape attempts. (F7 fix)
    if not file_path.is_relative_to(_BRIEFCASES_DIR.resolve()):
        raise ValueError(
            f"Invalid filename: {filename!r}. "
            "Filename must not contain path traversal sequences."
        )

    if not file_path.exists():
        raise FileNotFoundError(
            f"Briefcase file not found: {filename}. "
            f"Use the karma://briefcases resource to list available files."
        )
    return file_path.read_text(encoding="utf-8")
```

---

**Task 4 — Create `karma/mcp_server.py` — Deep Investigation Layer**

Add these 5 tools and the `_get_langfuse_client` helper to the same `karma/mcp_server.py` file, after the quick-check tools and before the resource handlers.

```python
# ---------------------------------------------------------------------------
# Internal helper — Langfuse client construction
# ---------------------------------------------------------------------------

def _get_langfuse_client() -> "FernLangfuse":
    """Construct a FernLangfuse client from environment credentials.

    Raises EnvironmentError if LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY is not set.
    Used by all Langfuse deep investigation tools to avoid repeating credential loading.
    """
    from langfuse.api.client import FernLangfuse

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_HOST", "http://localhost:3000")

    missing = [name for name, val in [
        ("LANGFUSE_PUBLIC_KEY", public_key),
        ("LANGFUSE_SECRET_KEY", secret_key),
    ] if not val]
    if missing:
        raise EnvironmentError(
            f"Missing Langfuse credentials: {', '.join(missing)} — add them to AgentManual/.env"
        )

    return FernLangfuse(
        base_url=host,
        x_langfuse_public_key=public_key,
        username=public_key,
        password=secret_key,
    )


# ---------------------------------------------------------------------------
# Deep Investigation Tools — Logfire
# ---------------------------------------------------------------------------

@mcp.tool()
def query_logfire(
    karma_code: str,
    event: str | None = None,
    flag: str | None = None,
    message_contains: str | None = None,
    limit: int = 50,
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """
    Browse ALL Logfire log entries for a karma_code — not just flagged ones.

    This is the deep investigation tool. Unlike query_flags (which only returns red/yellow
    entries), this tool returns every log entry matching the filters, with full attribute payloads.

    Args:
        karma_code: The Karma Code to inspect.
        event: Optional — filter by event name (exact match, e.g. "GET_CRM", "START_RUN").
        flag: Optional — filter by flag value ("red", "yellow"). Omit to include all entries
              (flagged and unflagged).
        message_contains: Optional — substring match on the log message (case-sensitive).
        limit: Max rows to return (default 50, max 200). Higher limits are slower.
        since: Optional time window start. Relative (2h, 30m, 1d) or ISO 8601 string.
        until: Optional time window end. ISO 8601 string ONLY. Defaults to now.

    Returns:
        List of log entry dicts: [{timestamp, message, event, flag, archetype, karma_code,
        agent, type, sub_id, tool_name, ...all Karma attributes}, ...]
    """
    _validate_karma_code(karma_code)

    if flag is not None and flag not in ("red", "yellow"):
        raise ValueError("flag must be 'red', 'yellow', or None")

    # Cap limit to prevent huge result sets that blow up MCP response size
    limit = min(max(1, limit), 200)

    since_dt = parse_since(since)
    until_dt = parse_since(until) if until else datetime.now(timezone.utc)

    # Build WHERE clauses dynamically from provided filters.
    # karma_code is already validated by KARMA_CODE_PATTERN — safe for .format().
    where_clauses = [f"attributes->>'karma_code' = '{karma_code}'"]

    if event is not None:
        # event names are alphanumeric + underscores (per karma-log-standard.md Event Naming)
        if not _SAFE_ATTR_PATTERN.match(event):
            raise ValueError(f"Invalid event filter: {event!r}. Must be alphanumeric/underscores.")
        where_clauses.append(f"attributes->>'event' = '{event}'")

    if flag is not None:
        where_clauses.append(f"attributes->>'flag' = '{flag}'")

    if message_contains is not None:
        # Escape single quotes in message_contains to prevent SQL injection
        safe_msg = message_contains.replace("'", "''")
        where_clauses.append(f"message LIKE '%{safe_msg}%'")

    where = " AND ".join(where_clauses)

    sql = f"""
        SELECT
            start_timestamp,
            message,
            attributes->>'event'      AS event,
            attributes->>'flag'       AS flag,
            attributes->>'archetype'  AS archetype,
            attributes->>'karma_code' AS karma_code,
            attributes->>'agent'      AS agent,
            attributes->>'type'       AS type,
            attributes->>'sub_id'     AS sub_id,
            attributes->>'tool_name'  AS tool_name,
            attributes->>'langfuse_trace_url' AS langfuse_trace_url,
            attributes->>'langfuse_trace_id'  AS langfuse_trace_id
        FROM records
        WHERE {where}
        ORDER BY start_timestamp ASC
        LIMIT {limit}
    """

    from logfire.query_client import LogfireQueryClient

    read_token = os.getenv("LOGFIRE_READ_TOKEN")
    if not read_token:
        raise EnvironmentError("LOGFIRE_READ_TOKEN is not set — add it to AgentManual/.env")

    with LogfireQueryClient(read_token=read_token) as client:
        result = client.query_json_rows(
            sql=sql,
            min_timestamp=since_dt,
            max_timestamp=until_dt,
        )

    rows = result.get("rows", [])

    # Normalise rows — keep all selected fields, strip None values for cleaner output
    entries = []
    for row in rows:
        entry = {
            "timestamp":          row.get("start_timestamp", ""),
            "message":            row.get("message", ""),
            "event":              row.get("event"),
            "flag":               row.get("flag"),
            "archetype":          row.get("archetype"),
            "karma_code":         row.get("karma_code"),
            "agent":              row.get("agent"),
            "type":               row.get("type"),
            "sub_id":             row.get("sub_id"),
            "tool_name":          row.get("tool_name"),
            "langfuse_trace_url": row.get("langfuse_trace_url"),
            "langfuse_trace_id":  row.get("langfuse_trace_id"),
        }
        # Remove None values — keeps output clean for the AI consumer
        entries.append({k: v for k, v in entry.items() if v is not None})

    return entries


# Regex for safe attribute value filtering (event names, etc.)
# Alphanumeric + underscores only — matches karma-log-standard.md Event Naming convention.
import re
_SAFE_ATTR_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")


# ---------------------------------------------------------------------------
# Deep Investigation Tools — Langfuse
# ---------------------------------------------------------------------------

@mcp.tool()
def list_langfuse_traces(
    karma_code: str,
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """
    List all Langfuse traces for a karma_code session.

    This is the "table of contents" for AI investigation — shows which traces exist,
    their duration, token usage, and cost. Use the returned trace_id values with
    get_langfuse_trace() to drill deeper.

    Args:
        karma_code: The Karma Code (= Langfuse session_id).
        since: Optional time window start.
        until: Optional time window end. Defaults to now.

    Returns:
        List of trace summary dicts: [{trace_id, name, created_at, latency_ms,
        total_tokens, total_cost_usd, tags, html_path}, ...]
    """
    _validate_karma_code(karma_code)

    since_dt = parse_since(since)
    until_dt = parse_since(until) if until else datetime.now(timezone.utc)

    client = _get_langfuse_client()

    traces_response = client.trace.list(
        session_id=karma_code,
        from_timestamp=since_dt,
        to_timestamp=until_dt,
    )

    summaries = []
    for trace in (traces_response.data or []):
        latency_sec = getattr(trace, "latency", None)
        summaries.append({
            "trace_id":       trace.id,
            "name":           trace.name or karma_code,
            "created_at":     trace.timestamp.isoformat() if trace.timestamp else None,
            "latency_ms":     round(latency_sec * 1000, 1) if latency_sec is not None else None,
            "total_tokens":   getattr(trace, "total_tokens", None),
            "total_cost_usd": getattr(trace, "total_cost", None),
            "tags":           trace.tags or [],
            "html_path":      getattr(trace, "html_path", None),
        })

    return summaries


@mcp.tool()
def get_langfuse_trace(trace_id: str) -> dict:
    """
    Get full details for a Langfuse trace, including its nested observation tree.

    Returns the trace metadata plus a flat list of all observations (spans, generations,
    events) in the trace, ordered by start time. Use observation IDs from the returned
    list with get_langfuse_observation() to read full prompt/completion content.

    Args:
        trace_id: The Langfuse trace ID (from list_langfuse_traces results).

    Returns:
        {
            "trace_id", "name", "session_id", "created_at", "latency_ms",
            "total_tokens", "total_cost_usd", "input", "output", "tags", "metadata",
            "observations": [
                {"id", "name", "type", "level", "status_message", "start_time",
                 "end_time", "latency_ms", "model", "tokens", "cost_usd",
                 "parent_observation_id"},
                ...
            ]
        }
    """
    if not trace_id or not trace_id.strip():
        raise ValueError("trace_id must be a non-empty string")

    client = _get_langfuse_client()
    trace = client.trace.get(trace_id)

    # Build observation summaries — enough to navigate, not full content.
    # Use get_langfuse_observation(obs_id) for full input/output.
    obs_list = []
    for obs in (trace.observations or []):
        latency_sec = getattr(obs, "latency", None)
        usage = getattr(obs, "usage_details", {}) or {}
        cost = getattr(obs, "cost_details", {}) or {}
        obs_list.append({
            "id":                    obs.id,
            "name":                  obs.name or "",
            "type":                  obs.type or "",
            "level":                 str(getattr(obs, "level", "")),
            "status_message":        getattr(obs, "status_message", None),
            "start_time":            obs.start_time.isoformat() if obs.start_time else None,
            "end_time":              obs.end_time.isoformat() if getattr(obs, "end_time", None) else None,
            "latency_ms":            round(latency_sec * 1000, 1) if latency_sec is not None else None,
            "model":                 getattr(obs, "model", None),
            "tokens":                usage.get("total", getattr(getattr(obs, "usage", None), "total", None)),
            "cost_usd":              cost.get("total", getattr(getattr(obs, "usage", None), "total_cost", None)),
            "parent_observation_id": getattr(obs, "parent_observation_id", None),
        })

    # Sort by start_time for chronological reading
    obs_list.sort(key=lambda o: o.get("start_time") or "")

    latency_sec = getattr(trace, "latency", None)
    return {
        "trace_id":       trace.id,
        "name":           trace.name or "",
        "session_id":     trace.session_id or "",
        "created_at":     trace.timestamp.isoformat() if trace.timestamp else None,
        "latency_ms":     round(latency_sec * 1000, 1) if latency_sec is not None else None,
        "total_tokens":   getattr(trace, "total_tokens", None),
        "total_cost_usd": getattr(trace, "total_cost", None),
        "input":          trace.input,
        "output":         trace.output,
        "tags":           trace.tags or [],
        "metadata":       trace.metadata,
        "observations":   obs_list,
    }


@mcp.tool()
def get_langfuse_observation(
    observation_id: str,
    max_content_length: int | None = None,
) -> dict:
    """
    Get full details for a single Langfuse observation — including FULL prompt and completion text.

    This is the microscope. Unlike the Briefcase (which truncates to 300 chars), this tool
    returns the complete input and output content. Use this to read the actual prompt that
    caused a failure, the full completion text, or the retriever query/result.

    Args:
        observation_id: The observation ID (from get_langfuse_trace results).
        max_content_length: Optional — truncate input/output to this many characters.
                            Omit for full content (default). Set to e.g. 1000 if the
                            content is enormous and you only need a preview.

    Returns:
        {
            "id", "trace_id", "name", "type", "level", "status_message",
            "start_time", "end_time", "latency_ms", "time_to_first_token_ms",
            "model", "model_parameters",
            "input", "output",
            "usage_details", "cost_details",
            "parent_observation_id", "metadata",
            "prompt_name", "prompt_version"
        }
    """
    if not observation_id or not observation_id.strip():
        raise ValueError("observation_id must be a non-empty string")

    client = _get_langfuse_client()
    obs = client.observations.get(observation_id)

    # Convert input/output to string for consistent truncation handling.
    # Langfuse stores these as Any (could be dict, list, string, None).
    raw_input = obs.input
    raw_output = obs.output

    if max_content_length is not None and max_content_length > 0:
        input_str = str(raw_input) if raw_input is not None else None
        output_str = str(raw_output) if raw_output is not None else None
        if input_str and len(input_str) > max_content_length:
            raw_input = input_str[:max_content_length] + f"... [truncated, {len(input_str)} chars total]"
        if output_str and len(output_str) > max_content_length:
            raw_output = output_str[:max_content_length] + f"... [truncated, {len(output_str)} chars total]"

    latency_sec = getattr(obs, "latency", None)
    ttft_sec = getattr(obs, "time_to_first_token", None)

    return {
        "id":                    obs.id,
        "trace_id":              obs.trace_id,
        "name":                  obs.name or "",
        "type":                  obs.type or "",
        "level":                 str(getattr(obs, "level", "")),
        "status_message":        getattr(obs, "status_message", None),
        "start_time":            obs.start_time.isoformat() if obs.start_time else None,
        "end_time":              obs.end_time.isoformat() if getattr(obs, "end_time", None) else None,
        "latency_ms":            round(latency_sec * 1000, 1) if latency_sec is not None else None,
        "time_to_first_token_ms": round(ttft_sec * 1000, 1) if ttft_sec is not None else None,
        "model":                 getattr(obs, "model", None),
        "model_parameters":      getattr(obs, "model_parameters", None),
        "input":                 raw_input,
        "output":                raw_output,
        "usage_details":         dict(obs.usage_details) if obs.usage_details else {},
        "cost_details":          dict(obs.cost_details) if obs.cost_details else {},
        "parent_observation_id": getattr(obs, "parent_observation_id", None),
        "metadata":              obs.metadata,
        "prompt_name":           getattr(obs, "prompt_name", None),
        "prompt_version":        getattr(obs, "prompt_version", None),
    }


@mcp.tool()
def list_langfuse_observations(
    trace_id: str,
    level: str | None = None,
    type: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """
    Browse observations within a Langfuse trace — filter by level or type.

    Returns observation summaries (not full content). Use get_langfuse_observation()
    with a specific observation_id to read full prompt/completion text.

    Args:
        trace_id: The Langfuse trace ID.
        level: Optional — filter by observation level: "ERROR", "WARNING", "DEFAULT", "DEBUG".
        type: Optional — filter by observation type: "GENERATION", "SPAN", "EVENT".
        limit: Max observations to return (default 50, max 200).

    Returns:
        List of observation summary dicts: [{id, name, type, level, status_message,
        start_time, latency_ms, model, tokens, cost_usd}, ...]
    """
    if not trace_id or not trace_id.strip():
        raise ValueError("trace_id must be a non-empty string")

    valid_levels = {"ERROR", "WARNING", "DEFAULT", "DEBUG"}
    if level is not None and level not in valid_levels:
        raise ValueError(f"level must be one of {valid_levels} or None")

    valid_types = {"GENERATION", "SPAN", "EVENT"}
    if type is not None and type not in valid_types:
        raise ValueError(f"type must be one of {valid_types} or None")

    limit = min(max(1, limit), 200)

    client = _get_langfuse_client()

    # Build kwargs dynamically — FernLangfuse.observations.get_many() accepts
    # trace_id, level, type as optional filters.
    from langfuse.api.resources.commons.types.observation_level import ObservationLevel

    kwargs = {"trace_id": trace_id}
    if level is not None:
        kwargs["level"] = ObservationLevel(level)
    if type is not None:
        kwargs["type"] = type

    obs_response = client.observations.get_many(**kwargs)

    summaries = []
    for obs in (obs_response.data or [])[:limit]:
        latency_sec = getattr(obs, "latency", None)
        usage = getattr(obs, "usage_details", {}) or {}
        cost = getattr(obs, "cost_details", {}) or {}
        summaries.append({
            "id":             obs.id,
            "name":           obs.name or "",
            "type":           obs.type or "",
            "level":          str(getattr(obs, "level", "")),
            "status_message": getattr(obs, "status_message", None),
            "start_time":     obs.start_time.isoformat() if obs.start_time else None,
            "latency_ms":     round(latency_sec * 1000, 1) if latency_sec is not None else None,
            "model":          getattr(obs, "model", None),
            "tokens":         usage.get("total", getattr(getattr(obs, "usage", None), "total", None)),
            "cost_usd":       cost.get("total", getattr(getattr(obs, "usage", None), "total_cost", None)),
        })

    return summaries
```

---

**Task 5 — Create `karma/mcp_server.py` — Playbook Resources**

Add these 2 playbook resource handlers to `karma/mcp_server.py`, after the briefcase resource handlers.

```python
# ---------------------------------------------------------------------------
# Resources — Investigation Playbooks
# ---------------------------------------------------------------------------

_INVESTIGATION_PLAYBOOK = """# Karma Investigation Playbook

You have 9 Karma MCP tools. This playbook tells you which ones to use and in what order.

## Step 1 — Quick Triage

Start here. These tell you if something is wrong and how bad it is.

```
query_flags(karma_code)          → What broke? Red = hard failure, yellow = soft.
get_health(karma_code)           → Vital signs: flag counts, tokens, cost, latency, errors.
```

If no red flags and health looks normal → done. Session is clean.

## Step 2 — Logfire Deep Dive

Something looks wrong. Browse the raw application logs.

```
query_logfire(karma_code, limit=100)                → See everything that happened.
query_logfire(karma_code, event="GET_CRM")           → Zoom in on a specific event.
query_logfire(karma_code, message_contains="timeout") → Search by error message.
query_logfire(karma_code, flag="red")                 → Same as query_flags but with full attributes.
```

Look at timestamps. Look at event sequences. Find the moment things went wrong.

## Step 3 — Langfuse Trace Inspection

Now look at what the AI did internally.

```
list_langfuse_traces(karma_code)     → Which traces exist? How long? How much cost?
get_langfuse_trace(trace_id)         → Full observation tree — the map of AI execution.
```

Read the observation tree. Find ERRORs. Find slow observations. Note the observation IDs.

## Step 4 — Microscope

Drill into the specific observation that failed or looks suspicious.

```
get_langfuse_observation(observation_id)                 → Full prompt + completion. No truncation.
get_langfuse_observation(observation_id, max_content_length=2000) → Preview if content is huge.
list_langfuse_observations(trace_id, level="ERROR")      → All errored observations in one trace.
list_langfuse_observations(trace_id, type="GENERATION")  → All LLM calls in the trace.
```

## Step 5 — Cross-Reference

Connect Logfire app events with Langfuse AI events.

```
get_trace_url(karma_code)   → Get the Langfuse trace URL embedded in Logfire.
get_briefcase(karma_code)   → Generate a full formatted report for the record.
```

## Decision Tree

```
Start → query_flags()
  ├─ No flags → get_health() → Done (clean session)
  ├─ Yellow flags → query_logfire() → investigate soft issues
  └─ Red flags → query_logfire(flag="red") → find the failure point
       └─ list_langfuse_traces() → get_langfuse_trace()
            └─ Find ERROR observations → get_langfuse_observation()
                 └─ Read full prompt/completion → root cause identified
```
""".strip()


_QUICK_CHECK_PLAYBOOK = """# Karma Quick-Check Playbook

Fast path for monitoring — not debugging. Use when you just need to check if a session is healthy.

## The 3-Call Check

```
1. query_flags(karma_code)    → Any red or yellow flags?
2. get_health(karma_code)     → Token count, cost, latency, error count normal?
3. get_trace_url(karma_code)  → Trace link for the record.
```

If all clear → session is clean. Report "no issues" and move on.
If flags present → switch to the Investigation Playbook (karma://playbook/investigation).
""".strip()


@mcp.resource("karma://playbook/investigation")
def get_investigation_playbook() -> str:
    """
    The Karma YOLO Investigation Playbook.

    Read this BEFORE investigating a karma_code. It tells you which tools to use,
    in what order, and how to chain them for maximum investigation depth.
    """
    return _INVESTIGATION_PLAYBOOK


@mcp.resource("karma://playbook/quick-check")
def get_quick_check_playbook() -> str:
    """
    The Karma Quick-Check Playbook.

    Fast-path monitoring — 3 calls to determine if a session is healthy.
    If issues are found, switch to the Investigation Playbook.
    """
    return _QUICK_CHECK_PLAYBOOK
```

---

**Task 6 — Create `scripts/mcp_server.py`**  <!-- renumbered -->

Thin entry point. Loads env, then imports and runs the MCP server.

```python
"""
Entry point for the Karma MCP Server.

Loads credentials from AgentManual/.env, then starts the Karma FastMCP server
over stdio. Designed to be invoked by MCP clients (Claude Code, Cursor) via:

    uv run python scripts/mcp_server.py

Claude Code config — global: ~/.claude/settings.json  OR  project: .claude/settings.json
    {
      "mcpServers": {
        "karma": {
          "command": "uv",
          "args": ["run", "python", "scripts/mcp_server.py"],
          "cwd": "/absolute/path/to/Karma"
        }
      }
    }

Cursor config (.cursor/mcp.json in project root):
    {
      "mcpServers": {
        "karma": {
          "command": "uv",
          "args": ["run", "python", "scripts/mcp_server.py"],
          "cwd": "/absolute/path/to/Karma"
        }
      }
    }

NOTE: cwd MUST be the absolute path to the Karma repo root. The server resolves
_bmad-output/briefcases/ relative to the package location — wrong cwd = empty resource list.
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

# Load credentials from AgentManual/.env BEFORE importing any karma module
# that touches os.getenv(). Resolves relative to scripts/ → Karma/ → AgentManual/
_env_path = Path(__file__).parent.parent.parent / "AgentManual" / ".env"
if not _env_path.exists():
    print(
        f"Warning: expected credentials at {_env_path} but file not found. "
        "Credentials may be missing — add AgentManual/.env before running.",
        file=sys.stderr,
    )
load_dotenv(_env_path)

from karma.mcp_server import mcp  # noqa: E402 — must import after load_dotenv

if __name__ == "__main__":
    mcp.run()
```

---

**Task 7 — Create `tests/test_utils.py`**  <!-- renumbered -->

Unit tests for `karma/utils.py` — `parse_since` has real logic and must be independently tested.

```python
"""
Tests for karma/utils.py — shared utilities.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

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
```

---

**Task 8 — Create `tests/test_mcp_server.py`**  <!-- renumbered -->

Unit tests for all 9 tools and resources. All external calls mocked. The quick-check tool tests below are from the original spec. Deep investigation tool tests follow after.

```python
"""
Tests for karma/mcp_server.py — KARMA MCP Server.

All external calls (Logfire, Langfuse) are mocked. Tests never hit live services.
Tool functions are called directly (not via MCP protocol) to keep tests fast and simple.
"""

from unittest.mock import MagicMock, patch
import pytest

from karma.mcp_server import get_briefcase, get_health, get_trace_url, list_briefcases, query_flags


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
    @patch("karma.mcp_server.LogfireQueryClient")
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
    def test_does_not_call_append_health_row(self, mock_lf, mock_lang):
        """MCP get_health must never append to CSV.

        Patch karma.health.append_health_row directly — mcp_server does NOT import it,
        so patching karma.mcp_server.append_health_row would fail silently.
        Also verify the result dict has no csv_path key (belt-and-suspenders).
        """
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
    @patch("karma.mcp_server.LogfireQueryClient")
    def test_returns_all_flags_when_no_filter(self, mock_client, mock_flags):
        mock_client.return_value.__enter__ = lambda s: MagicMock()
        mock_client.return_value.__exit__ = MagicMock(return_value=False)
        result = query_flags("NRD-Sale-101")
        assert len(result) == 3

    @patch("karma.mcp_server.query_logfire_flags", return_value=_mock_flags(red=2, yellow=1))
    @patch("karma.mcp_server.LogfireQueryClient")
    def test_filters_to_red_only(self, mock_client, mock_flags):
        mock_client.return_value.__enter__ = lambda s: MagicMock()
        mock_client.return_value.__exit__ = MagicMock(return_value=False)
        result = query_flags("NRD-Sale-101", flag="red")
        assert all(e["flag"] == "red" for e in result)
        assert len(result) == 2

    @patch("karma.mcp_server.query_logfire_flags", return_value=_mock_flags(red=2, yellow=1))
    @patch("karma.mcp_server.LogfireQueryClient")
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
    @patch("karma.mcp_server.LogfireQueryClient")
    def test_returns_both_fields(self, mock_client, mock_tf):
        mock_client.return_value.__enter__ = lambda s: MagicMock()
        mock_client.return_value.__exit__ = MagicMock(return_value=False)
        result = get_trace_url("NRD-Sale-101")
        assert result["langfuse_trace_url"] == "http://localhost:3000/traces/abc"
        assert result["langfuse_trace_id"] == "abc"

    @patch("karma.mcp_server.query_langfuse_trace_fields",
           return_value={"langfuse_trace_url": None, "langfuse_trace_id": None})
    @patch("karma.mcp_server.LogfireQueryClient")
    def test_returns_none_when_no_trace(self, mock_client, mock_tf):
        mock_client.return_value.__enter__ = lambda s: MagicMock()
        mock_client.return_value.__exit__ = MagicMock(return_value=False)
        result = get_trace_url("NRD-Sale-101")
        assert result["langfuse_trace_url"] is None

    def test_invalid_karma_code_raises(self):
        with pytest.raises(ValueError, match="Invalid karma_code format"):
            get_trace_url("!bad")


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

class TestListBriefcases:
    def test_returns_empty_list_when_no_directory(self, tmp_path, monkeypatch):
        import json
        import karma.mcp_server as mcp_mod
        # Use monkeypatch.setattr — safe for parallel test execution (no global mutation)
        monkeypatch.setattr(mcp_mod, "_BRIEFCASES_DIR", tmp_path / "briefcases")  # does not exist
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


# ---------------------------------------------------------------------------
# Deep Investigation Tools — query_logfire
# ---------------------------------------------------------------------------

class TestQueryLogfire:
    @patch("karma.mcp_server.LogfireQueryClient")
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
        result = query_logfire("NRD-Sale-101")
        assert len(result) == 2
        # Unflagged entry is included (unlike query_flags which only returns flagged)
        assert result[0]["event"] == "GET_CRM"
        assert result[0].get("flag") is None  # None values stripped from output

    @patch("karma.mcp_server.LogfireQueryClient")
    def test_event_filter(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = lambda s: mock_client
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.query_json_rows.return_value = {"columns": [], "rows": []}
        query_logfire("NRD-Sale-101", event="GET_CRM")
        # Verify the SQL contains the event filter
        sql_arg = mock_client.query_json_rows.call_args[1]["sql"]
        assert "attributes->>'event' = 'GET_CRM'" in sql_arg

    def test_invalid_karma_code_raises(self):
        with pytest.raises(ValueError, match="Invalid karma_code format"):
            query_logfire("not valid!")

    def test_invalid_event_filter_raises(self):
        with pytest.raises(ValueError, match="Invalid event filter"):
            query_logfire("NRD-Sale-101", event="DROP TABLE")

    def test_limit_capped_at_200(self):
        """Requesting limit > 200 gets capped silently."""
        # This test just verifies no error — actual cap is in the SQL LIMIT clause
        with patch("karma.mcp_server.LogfireQueryClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__ = lambda s: mock_client
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.query_json_rows.return_value = {"columns": [], "rows": []}
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
```

Add the new tool imports at the top of the test file:

```python
from karma.mcp_server import (
    get_briefcase, get_health, get_trace_url, list_briefcases, query_flags,
    # Deep investigation tools
    query_logfire, list_langfuse_traces, get_langfuse_trace,
    get_langfuse_observation, list_langfuse_observations,
    # Playbook resources
    get_investigation_playbook, get_quick_check_playbook,
)
```

---

**Task 9 — Update `docs/KARMA_LOG.md`**

In the `## What Your Instrumentation Unlocks` section, add Theme 6 entry. Append:

```markdown
**Theme 6 — KARMA MCP**: A full investigation surface for dev AI tools. 9 MCP tools (4 quick-check + 5 deep investigation) and 4 resources (briefcases + playbooks), all keyed by `karma_code`. Quick-check: `get_briefcase`, `get_health`, `query_flags`, `get_trace_url`. Deep investigation: `query_logfire` (browse all logs), `list_langfuse_traces`, `get_langfuse_trace`, `get_langfuse_observation` (full prompt/completion), `list_langfuse_observations`. Playbooks: `karma://playbook/investigation` (YOLO investigation loop), `karma://playbook/quick-check` (3-call health check). A dev AI adds one config stanza to Claude Code or Cursor and queries Karma directly — no file reads, no CLI invocations. **[COMPLETE]** ← update to this after implementation
```

Also update the `**Last Updated:**` date to `2026-03-04`.

---

### Acceptance Criteria

- [ ] AC0: Given `parse_since` is called with `None`, when executed, then returns `None` with no error
- [ ] AC1: Given `parse_since` is called with `"2h"`, when executed, then returns a UTC datetime approximately 2 hours ago (within 2-second tolerance)
- [ ] AC2: Given `parse_since` is called with a valid ISO 8601 string without timezone, when executed, then returns a UTC-aware datetime (tzinfo attached)
- [ ] AC3: Given `parse_since` is called with an unrecognised format (e.g. `"yesterday"`), when executed, then raises `ValueError` matching `"since/until"`
- [ ] AC4: Given a valid karma_code and mocked Logfire + Langfuse, when `get_briefcase(karma_code)` is called, then returns a dict with non-empty `"content"` string and `"path"` string ending in `.md`
- [ ] AC5: Given an invalid karma_code (e.g. `"not valid!"`), when `get_briefcase` is called, then raises `ValueError("Invalid karma_code format: ...")` before any Logfire or Langfuse call is made
- [ ] AC6: Given valid karma_code and mocked data, when `get_health(karma_code)` is called, then returned dict contains all 13 keys: `karma_code`, `archetype`, `red_flag_count`, `yellow_flag_count`, `trace_count`, `total_tokens`, `total_cost_usd`, `total_latency_ms`, `error_observation_count`, `lifecycle_status`, `session_turn_count`, `window_from`, `window_to`
- [ ] AC7: Given any call to `get_health`, when executed, then `karma.health.append_health_row` is never invoked and result dict contains no `"csv_path"` key
- [ ] AC8: Given Logfire returns 2 red + 1 yellow entries, when `query_flags(karma_code)` is called with no `flag` argument, then all 3 entries are returned
- [ ] AC9: Given Logfire returns 2 red + 1 yellow entries, when `query_flags(karma_code, flag="red")` is called, then exactly 2 entries are returned and all have `flag == "red"`
- [ ] AC10: Given Logfire returns 2 red + 1 yellow entries, when `query_flags(karma_code, flag="yellow")` is called, then exactly 1 entry is returned with `flag == "yellow"`
- [ ] AC11: Given `flag="orange"` (not a valid Karma flag value), when `query_flags` is called, then `ValueError` is raised before any Logfire call
- [ ] AC12: Given Logfire has a trace URL embedded for the karma_code, when `get_trace_url(karma_code)` is called, then returns dict with non-None `langfuse_trace_url` and `langfuse_trace_id`
- [ ] AC13: Given no trace URL exists in Logfire (Infinity Loop not active), when `get_trace_url(karma_code)` is called, then returns dict with both fields as `None` and no exception is raised
- [ ] AC14: Given any invalid karma_code (spaces or invalid chars), when any of the 9 tools that accept karma_code is called, then `ValueError("Invalid karma_code format: ...")` is raised before any API call
- [ ] AC15: Given `_BRIEFCASES_DIR` does not exist, when `list_briefcases()` is called, then returns JSON string `"[]"` with no exception
- [ ] AC16: Given two `.md` files with different modification times in `_BRIEFCASES_DIR`, when `list_briefcases()` is called, then the newer file appears first in the returned JSON array
- [ ] AC17: Given a `.md` file exists in `_BRIEFCASES_DIR`, when `read_briefcase_file(filename)` is called, then the full file content is returned as a string
- [ ] AC18: Given a filename that does not exist in `_BRIEFCASES_DIR`, when `read_briefcase_file(filename)` is called, then `FileNotFoundError` is raised with a descriptive message mentioning `karma://briefcases`

**Deep Investigation Layer ACs:**

- [ ] AC19: Given Logfire has 5 log entries (3 unflagged + 2 flagged) for a karma_code, when `query_logfire(karma_code)` is called, then all 5 entries are returned (not just flagged)
- [ ] AC20: Given `query_logfire` is called with `event="GET_CRM"`, when executed, then the generated SQL includes `attributes->>'event' = 'GET_CRM'` in the WHERE clause
- [ ] AC21: Given `query_logfire` is called with `event="DROP TABLE"` (invalid chars), when executed, then `ValueError("Invalid event filter")` is raised before any SQL query
- [ ] AC22: Given `query_logfire` is called with `limit=500`, when executed, then the SQL LIMIT is capped at 200
- [ ] AC23: Given a karma_code with Langfuse traces, when `list_langfuse_traces(karma_code)` is called, then returns a list of dicts each containing `trace_id`, `name`, `latency_ms`, `total_tokens`, `total_cost_usd`
- [ ] AC24: Given a valid trace_id, when `get_langfuse_trace(trace_id)` is called, then returns a dict with `observations` list where each observation has `id`, `name`, `type`, `level`, `model`
- [ ] AC25: Given an empty string trace_id, when `get_langfuse_trace("")` is called, then `ValueError("trace_id")` is raised
- [ ] AC26: Given a valid observation_id, when `get_langfuse_observation(observation_id)` is called with no `max_content_length`, then `input` and `output` fields contain FULL content (no truncation)
- [ ] AC27: Given a valid observation_id with 5000-char input, when `get_langfuse_observation(observation_id, max_content_length=100)` is called, then `input` is truncated and includes `"truncated"` and `"5000 chars total"` in the suffix
- [ ] AC28: Given a valid trace_id, when `list_langfuse_observations(trace_id, level="ERROR")` is called, then only ERROR-level observations are returned and no `input`/`output` fields are present (summaries only)
- [ ] AC29: Given `list_langfuse_observations` is called with `level="CRITICAL"` (not a valid Langfuse level), then `ValueError` is raised listing the valid levels

**Playbook Resource ACs:**

- [ ] AC30: Given `get_investigation_playbook()` is called, then the returned string contains all 9 tool names: `query_flags`, `query_logfire`, `get_health`, `get_briefcase`, `get_trace_url`, `list_langfuse_traces`, `get_langfuse_trace`, `get_langfuse_observation`, `list_langfuse_observations`
- [ ] AC31: Given `get_quick_check_playbook()` is called, then the returned string contains `query_flags`, `get_health`, `get_trace_url` and references the investigation playbook URI

---

## Additional Context

### Dependencies

- `mcp>=1.0.0` — Python MCP SDK (FastMCP). Install: `uv add mcp`

### Testing Strategy

- `tests/test_utils.py` — covers `parse_since` independently: None, relative, absolute, invalid
- `tests/test_mcp_server.py` — covers all 9 tools + 4 resources via direct function calls (not MCP protocol)
- Quick-check tools patched via `patch("karma.mcp_server.<function>", return_value=...)`
- Deep investigation Langfuse tools patched via `patch("karma.mcp_server._get_langfuse_client")`
- Deep investigation Logfire tool patched via `patch("karma.mcp_server.LogfireQueryClient")`
- `append_health_row` invariant: patch `karma.health.append_health_row` (not mcp_server — it doesn't import it)
- Resource tests use `tmp_path` fixture + `monkeypatch` on `_BRIEFCASES_DIR` for filesystem isolation
- Playbook resource tests assert tool name presence in returned strings
- Run: `uv run pytest tests/test_utils.py tests/test_mcp_server.py -v`

### Notes

- MCP server does not call `logfire.configure()` — it is not a Logfire instrumented service; it is a read-only query interface.
- `scripts/mcp_server.py` loads `.env` before importing `karma.mcp_server` (critical — `from karma.mcp_server import mcp` must come after `load_dotenv`).
- `LogfireQueryClient` is imported inside each tool handler (not at module level) to avoid issues during test patching.
- After Theme 6 ships, update `docs/KARMA_LOG.md` Theme 6 marker from "ready-for-dev" to `[COMPLETE]` and update `**Last Updated:**`.
- **[F11 — mcp version sensitivity]** `mcp>=1.0.0` sets only a lower bound. The `from mcp.server.fastmcp import FastMCP` import path is version-specific and may change in future releases. After `uv add mcp`, run `python -c "from mcp.server.fastmcp import FastMCP"` to verify the import resolves before writing any tool code. If it fails, check the installed version's module layout and update the import path accordingly.
- **[F12 — LOGFIRE_READ_TOKEN guard]** `LogfireQueryClient(read_token=None)` will silently construct a client but fail at query time with an opaque error. Each tool handler that calls `LogfireQueryClient` should raise `EnvironmentError("LOGFIRE_READ_TOKEN is not set")` before entering the context manager if `os.getenv("LOGFIRE_READ_TOKEN")` is None.
