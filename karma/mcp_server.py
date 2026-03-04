"""
Karma MCP Server.

Exposes Karma observability data (Briefcase, Health, flags, trace URLs) as MCP tools
and resources, keyed by karma_code. A thin orchestration layer over karma/briefcase.py
and karma/health.py — no new query logic is written here.

Transport: stdio (standard for Claude Code and Cursor MCP integration).
Credentials: loaded from AgentManual/.env by scripts/mcp_server.py before import.
"""

import os
import re
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

# Regex for safe attribute value filtering (event names, etc.)
# Alphanumeric + underscores only — matches karma-log-standard.md Event Naming convention.
_SAFE_ATTR_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")


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
# Internal helper — Langfuse client construction (cached singleton)
# ---------------------------------------------------------------------------

# Cached FernLangfuse client — reused across tool calls to avoid leaking TCP connections.
# MCP stdio servers are long-running processes, so creating a new client per call would
# leak file descriptors. The client is created lazily on first use.
_langfuse_client = None


def _get_langfuse_client() -> "FernLangfuse":
    """Return a cached FernLangfuse client, creating one on first call.

    Raises ValueError if LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY is not set.
    Used by all Langfuse deep investigation tools to avoid repeating credential loading.
    """
    global _langfuse_client

    if _langfuse_client is not None:
        return _langfuse_client

    from langfuse.api.client import FernLangfuse

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_HOST", "http://localhost:3000")

    missing = [name for name, val in [
        ("LANGFUSE_PUBLIC_KEY", public_key),
        ("LANGFUSE_SECRET_KEY", secret_key),
    ] if not val]
    if missing:
        raise ValueError(
            f"Missing Langfuse credentials: {', '.join(missing)} — add them to AgentManual/.env"
        )

    _langfuse_client = FernLangfuse(
        base_url=host,
        x_langfuse_public_key=public_key,
        username=public_key,
        password=secret_key,
    )
    return _langfuse_client


# ---------------------------------------------------------------------------
# Quick-Check Tools
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
    until_dt = parse_since(until) if until else datetime.now(timezone.utc)

    # Capture now ONCE — pass to both generate_briefcase and write_briefcase to ensure
    # the filename embedded in the document body matches the actual file on disk.
    briefcase_now = datetime.now(timezone.utc)

    from logfire.query_client import LogfireQueryClient

    with LogfireQueryClient(read_token=os.getenv("LOGFIRE_READ_TOKEN")) as lf_client:
        logfire_flags  = query_logfire_flags(karma_code, since_dt, until_dt, lf_client)
        trace_fields   = query_langfuse_trace_fields(karma_code, since_dt, until_dt, lf_client)

    # Infer archetype from first flagged row — "" if no flagged rows (honest unknown)
    archetype = logfire_flags[0].get("archetype", "") if logfire_flags else ""

    # query_langfuse_context accepts ONLY two args: (karma_code, since).
    # It does NOT accept until_dt — do NOT add a third argument here.
    langfuse_context = query_langfuse_context(karma_code, since_dt)

    content = generate_briefcase(
        karma_code, archetype, logfire_flags, langfuse_context,
        langfuse_trace_url=trace_fields["langfuse_trace_url"],
        langfuse_trace_id=trace_fields["langfuse_trace_id"],
        now=briefcase_now,
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
    """
    _validate_karma_code(karma_code)

    since_dt = parse_since(since)
    until_dt = parse_since(until) if until else datetime.now(timezone.utc)

    from logfire.query_client import LogfireQueryClient

    with LogfireQueryClient(read_token=os.getenv("LOGFIRE_READ_TOKEN")) as lf_client:
        return query_langfuse_trace_fields(karma_code, since_dt, until_dt, lf_client)


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
        flag: Optional — filter by flag value ("red", "yellow"). Omit to include all entries.
        message_contains: Optional — substring match on the log message (case-sensitive).
        limit: Max rows to return (default 50, max 200).
        since: Optional time window start. Relative (2h, 30m, 1d) or ISO 8601 string.
        until: Optional time window end. ISO 8601 string ONLY. Defaults to now.

    Returns:
        List of log entry dicts with full Karma attributes.
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
        # Escape LIKE-special characters and single quotes to prevent SQL injection.
        # Order matters: backslash first (it's the escape char), then wildcards, then quotes.
        safe_msg = message_contains.replace("\\", "\\\\")
        safe_msg = safe_msg.replace("%", "\\%")
        safe_msg = safe_msg.replace("_", "\\_")
        safe_msg = safe_msg.replace("'", "''")
        where_clauses.append(f"message LIKE '%{safe_msg}%' ESCAPE '\\'")

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
        raise ValueError("LOGFIRE_READ_TOKEN is not set — add it to AgentManual/.env")

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

    Shows which traces exist, their duration, token usage, and cost. Use the returned
    trace_id values with get_langfuse_trace() to drill deeper.

    Args:
        karma_code: The Karma Code (= Langfuse session_id).
        since: Optional time window start.
        until: Optional time window end. Defaults to now.

    Returns:
        List of trace summary dicts.
    """
    _validate_karma_code(karma_code)

    since_dt = parse_since(since)
    until_dt = parse_since(until) if until else datetime.now(timezone.utc)

    client = _get_langfuse_client()

    # Fetch up to 100 traces per page, paginate until exhausted.
    # Guards against sessions with many traces (e.g. long-running Continuous agents).
    all_traces = []
    page = 1
    while True:
        traces_response = client.trace.list(
            session_id=karma_code,
            from_timestamp=since_dt,
            to_timestamp=until_dt,
            page=page,
        )
        batch = traces_response.data or []
        if not batch:
            break
        all_traces.extend(batch)
        # Stop if we got fewer than a full page (last page) or hit a safety cap
        if len(batch) < 100 or page >= 10:
            break
        page += 1

    summaries = []
    for trace in all_traces:
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
    events) in the trace, ordered by start time.

    Args:
        trace_id: The Langfuse trace ID (from list_langfuse_traces results).

    Returns:
        Dict with trace metadata and observations list.
    """
    if not trace_id or not trace_id.strip():
        raise ValueError("trace_id must be a non-empty string")

    client = _get_langfuse_client()
    trace = client.trace.get(trace_id)

    # Build observation summaries — enough to navigate, not full content.
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

    Unlike the Briefcase (which truncates to 300 chars), this tool returns the complete
    input and output content.

    Args:
        observation_id: The observation ID (from get_langfuse_trace results).
        max_content_length: Optional — truncate input/output to this many characters.
                            Omit for full content (default).

    Returns:
        Dict with full observation details including input/output.
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
        level: Optional — filter: "ERROR", "WARNING", "DEFAULT", "DEBUG".
        type: Optional — filter: "GENERATION", "SPAN", "EVENT".
        limit: Max observations to return (default 50, max 200).

    Returns:
        List of observation summary dicts.
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

    from langfuse.api.resources.commons.types.observation_level import ObservationLevel

    kwargs = {"trace_id": trace_id}
    if level is not None:
        kwargs["level"] = ObservationLevel(level)
    if type is not None:
        kwargs["type"] = type

    # Pass limit to API call — avoids fetching more data than needed.
    # Also paginate: if the API returns a full page, fetch more until we have enough.
    kwargs["limit"] = min(limit, 100)
    all_obs = []
    page = 1
    while len(all_obs) < limit:
        kwargs["page"] = page
        obs_response = client.observations.get_many(**kwargs)
        batch = obs_response.data or []
        if not batch:
            break
        all_obs.extend(batch)
        if len(batch) < kwargs["limit"] or page >= 10:
            break
        page += 1

    summaries = []
    for obs in all_obs[:limit]:
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
