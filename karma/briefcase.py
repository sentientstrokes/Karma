"""
Karma Briefcase Reporter.

Queries Logfire and Langfuse for a given karma_code, extracts flagged entries
(red and yellow), and writes a structured Briefcase markdown file for review.
No AI layer — this module filters, extracts, and formats only.
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from logfire.query_client import LogfireQueryClient
from langfuse.api.client import FernLangfuse
from langfuse.api.resources.commons.types.observation_level import ObservationLevel

from karma import KARMA_CODE_PATTERN


# ---------------------------------------------------------------------------
# Logfire querying
# ---------------------------------------------------------------------------

def query_logfire_flags(
    karma_code: str,
    since: datetime | None,
    until: datetime | None,
    client: LogfireQueryClient,
) -> list[dict]:
    """
    Query Logfire for all flagged entries (red and yellow) for a given karma_code.

    Returns a list of dicts, each containing:
        {timestamp, message, event, flag, archetype}

    The caller manages the LogfireQueryClient context — this function accepts
    an already-open client so it can be injected in tests without hitting live Logfire.

    Archetype is included in the SELECT so the caller can derive it from the first row
    without a separate query.
    """
    # Validate karma_code format before SQL interpolation — prevents injection
    if not KARMA_CODE_PATTERN.match(karma_code):
        raise ValueError(
            f"Invalid karma_code format: {karma_code!r}. "
            "Expected 2-4 hyphen-delimited segments (e.g. NRD-Sale-101, Ingest-start)"
        )

    # SQL safety: karma_code is validated above (alphanumeric + hyphens + underscores only).
    # Using .format() consistently across all query functions in this module.
    sql = """
        SELECT
            start_timestamp,
            message,
            attributes->>'event'     AS event,
            attributes->>'flag'      AS flag,
            attributes->>'karma_code' AS karma_code,
            attributes->>'archetype' AS archetype
        FROM records
        WHERE attributes->>'karma_code' = '{karma_code}'
          AND attributes->>'flag' IS NOT NULL
        ORDER BY start_timestamp ASC
    """.format(karma_code=karma_code)

    result = client.query_json_rows(
        sql=sql,
        min_timestamp=since,
        max_timestamp=until,
    )

    # result is a dict with 'columns' and 'rows' keys (confirmed: RowQueryResults TypedDict)
    rows = result.get("rows", [])

    # Normalise each row — strip any keys we don't need, keep only Karma fields
    entries = []
    for row in rows:
        entries.append({
            "timestamp": row.get("start_timestamp", ""),
            "message":   row.get("message", ""),
            "event":     row.get("event", ""),
            "flag":      row.get("flag", ""),
            "archetype": row.get("archetype", ""),
        })

    return entries


# ---------------------------------------------------------------------------
# Logfire querying — Langfuse trace fields (Theme 4: Karma Infinity Loop)
# ---------------------------------------------------------------------------

def query_langfuse_trace_fields(
    karma_code: str,
    since: datetime | None,
    until: datetime | None,
    client: LogfireQueryClient,
) -> dict:
    """Fetch Langfuse trace URL and trace ID from the root Logfire span for this karma_code.

    Returns a dict: {'langfuse_trace_url': str | None, 'langfuse_trace_id': str | None}.
    Both are None if this run predates Theme 4 adoption or the Langfuse span failed to open.

    Uses the same since/until time window as the other Logfire queries so that reused
    karma_codes return the trace URL from the current run, not the oldest run ever.

    SQL safety note: karma_code is validated at CLI entry (2-4 segment format, alphanumeric
    + hyphens + underscores only) before reaching this function — injection risk is negligible.
    Prefer parameterized queries if a future LogfireQueryClient version supports them.
    """
    # Validate karma_code format before SQL interpolation — prevents injection
    if not KARMA_CODE_PATTERN.match(karma_code):
        raise ValueError(
            f"Invalid karma_code format: {karma_code!r}. "
            "Expected 2-4 hyphen-delimited segments (e.g. NRD-Sale-101, Ingest-start)"
        )

    # Fetch both trace fields from the root span in a single query.
    # The root span is always earliest — ORDER BY start_timestamp ASC LIMIT 1 guarantees it.
    # min_timestamp / max_timestamp scope the query to the same window as --since / --until.
    result = client.query_json_rows(
        sql="""
            SELECT attributes->>'langfuse_trace_url' AS langfuse_trace_url,
                   attributes->>'langfuse_trace_id'  AS langfuse_trace_id
            FROM records
            WHERE attributes->>'karma_code' = '{karma_code}'
              AND attributes->>'langfuse_trace_url' IS NOT NULL
            ORDER BY start_timestamp ASC
            LIMIT 1
        """.format(karma_code=karma_code),
        min_timestamp=since,
        max_timestamp=until,
    )
    rows = result.get("rows", [])
    if rows:
        return {
            "langfuse_trace_url": rows[0].get("langfuse_trace_url"),
            "langfuse_trace_id": rows[0].get("langfuse_trace_id"),
        }
    return {"langfuse_trace_url": None, "langfuse_trace_id": None}


# ---------------------------------------------------------------------------
# Langfuse querying
# ---------------------------------------------------------------------------

def query_langfuse_context(
    karma_code: str,
    since: datetime | None,
) -> dict:
    """
    Query Langfuse for trace summaries and errored observations for a given karma_code.

    Returns a dict with two keys:
        traces:              list of {trace_name, duration_ms, total_tokens, total_cost}
        error_observations:  list of {obs_name, obs_type, input_summary, output_summary, status_message}

    Strategy:
    1. trace.list(session_id=karma_code) → get all traces for this session
    2. For each trace, observations.get_many(trace_id=..., level=ERROR) → errored observations

    Note: observations.get_many() has no session_id filter — we must go trace → observations.
    """
    public_key  = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key  = os.getenv("LANGFUSE_SECRET_KEY")
    host        = os.getenv("LANGFUSE_HOST", "http://localhost:3000")
    missing = [name for name, val in [
        ("LANGFUSE_PUBLIC_KEY", public_key),
        ("LANGFUSE_SECRET_KEY", secret_key),
    ] if not val]
    if missing:
        raise EnvironmentError(
            f"Missing Langfuse credentials: {', '.join(missing)} — add them to AgentManual/.env"
        )

    client = FernLangfuse(
        base_url=host,
        x_langfuse_public_key=public_key,
        # Langfuse HTTP Basic Auth convention: username = public key, password = secret key
        username=public_key,
        password=secret_key,
    )

    # --- Query 1: trace summaries ---
    traces_response = client.trace.list(
        session_id=karma_code,
        from_timestamp=since,
        fields="core,scores,metrics",
    )

    trace_summaries = []
    for trace in (traces_response.data or []):
        # latency / token / cost may not be native Trace fields — access safely
        trace_summaries.append({
            "trace_name":  trace.name or karma_code,
            # latency is in seconds on the Trace object when metrics are included
            "duration_ms": round(getattr(trace, "latency", None) * 1000, 1)
                           if getattr(trace, "latency", None) is not None else None,
            "total_tokens": getattr(trace, "total_tokens", None),
            "total_cost":   getattr(trace, "total_cost", None),
        })

    # --- Query 2: errored observations ---
    # Must iterate per trace — no session_id filter on observations endpoint
    error_observations = []
    for trace in (traces_response.data or []):
        obs_response = client.observations.get_many(
            trace_id=trace.id,
            level=ObservationLevel.ERROR,
        )
        for obs in (obs_response.data or []):
            # Truncate input/output to 300 chars — enough context without bloating the Briefcase
            raw_input  = str(obs.input  or "")
            raw_output = str(obs.output or "")
            error_observations.append({
                "obs_name":       obs.name or "",
                "obs_type":       obs.type or "",
                "input_summary":  raw_input[:300]  + ("…" if len(raw_input)  > 300 else ""),
                "output_summary": raw_output[:300] + ("…" if len(raw_output) > 300 else ""),
                "status_message": obs.status_message or "",
            })

    return {
        "traces":             trace_summaries,
        "error_observations": error_observations,
    }


# ---------------------------------------------------------------------------
# Briefcase markdown generation
# ---------------------------------------------------------------------------

def generate_briefcase(
    karma_code: str,
    archetype: str,
    logfire_flags: list[dict],
    langfuse_context: dict,
    now: datetime | None = None,
    langfuse_trace_url: str | None = None,   # Theme 4: clickable link for humans
    langfuse_trace_id: str | None = None,    # Theme 4: raw ID for dev AI programmatic access
) -> str:
    """
    Assemble and return the full Briefcase markdown string.

    Sections (in order):
      1. YAML frontmatter
      2. Visible header + archetype-specific summary line
      3. ## Red Flags
      4. ## Yellow Flags
      5. ## Human Findings (stub — populated manually during review)
      6. ## Langfuse Trace Summary
      7. ## Langfuse Errored Observations

    Red entries always appear before yellow entries (AC 1).

    `now` is accepted as a parameter so the caller can pass the same datetime
    instance to both generate_briefcase and write_briefcase — ensuring the
    filename embedded in the document body matches the actual file on disk.
    """
    if archetype not in ("", "Pipeline", "Continuous"):
        raise ValueError(
            f"Invalid archetype: {archetype!r}. Must be 'Pipeline', 'Continuous', or '' (unknown)."
        )

    # Use provided timestamp or generate one — caller should always pass this
    # to avoid a race condition with write_briefcase generating its own timestamp.
    if now is None:
        now = datetime.now(timezone.utc)
    generated_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    generated_display = now.strftime("%Y-%m-%d %H:%M UTC")
    filename_ts = now.strftime("%Y-%m-%d-%H%M%S")
    filename = f"{karma_code}-briefcase-{filename_ts}.md"

    # Derive time_window label from earliest flag timestamp if available
    if logfire_flags:
        time_from = logfire_flags[0]["timestamp"]
    else:
        time_from = generated_at
    time_window = f"{time_from} → {generated_at}"

    # --- Split flags by severity (red before yellow — AC 1) ---
    red_flags    = [e for e in logfire_flags if e["flag"] == "red"]
    yellow_flags = [e for e in logfire_flags if e["flag"] == "yellow"]

    # --- Theme 4: Langfuse trace fields in header ---
    # Conditionally render Langfuse trace fields — absent for legacy runs predating Theme 4.
    # langfuse_trace_url: clickable markdown link for humans
    # langfuse_trace_id: monospace ID for developer AI to use with langfuse.api.trace.get()
    trace_header_lines = ""
    if langfuse_trace_url:
        # Validate URL scheme before embedding in Markdown link — prevents broken syntax
        # or injection if the URL contains Markdown-hostile characters like ')'.
        if langfuse_trace_url.startswith(("http://", "https://")):
            trace_header_lines += f"**Langfuse Trace:** [View Trace]({langfuse_trace_url})\n"
        else:
            # Emit as plain text if URL scheme is unexpected — still useful, just not clickable
            trace_header_lines += f"**Langfuse Trace:** {langfuse_trace_url}\n"
    if langfuse_trace_id:
        trace_header_lines += f"**Langfuse Trace ID:** `{langfuse_trace_id}`\n"

    # --- Archetype-specific summary line ---
    # Pipeline: show run result (complete/aborted/incomplete based on lifecycle markers)
    # Continuous: show flag density
    # Unknown archetype: no summary line — never hardcode a fallback (AC 8)
    summary_line = _build_summary_line(archetype, logfire_flags, red_flags, yellow_flags)

    # --- Build sections ---
    red_section    = _build_flag_table(red_flags,    "red")
    yellow_section = _build_flag_table(yellow_flags, "yellow")
    trace_section  = _build_trace_table(langfuse_context.get("traces", []))
    obs_section    = _build_obs_table(langfuse_context.get("error_observations", []))

    # --- Assemble document ---
    doc = f"""---
karma_code: '{karma_code}'
archetype: '{archetype}'
generated_at: '{generated_at}'
time_window: '{time_window}'
source_tools: ['Logfire', 'Langfuse']
filename: '{filename}'
---

# Briefcase: {karma_code}

**File:** `{filename}`
**Generated:** {generated_display}
**Covers:** {time_window}
**Archetype:** {archetype}
{trace_header_lines}{summary_line}
---

## Red Flags (Hard Failures)

<!-- Auto-populated by karma/briefcase.py — entries where flag='red', ordered chronologically -->

{red_section}

---

## Yellow Flags (Soft Failures / Warnings)

<!-- Auto-populated by karma/briefcase.py — entries where flag='yellow', ordered chronologically -->

{yellow_section}

---

## Human Findings

<!-- MANUAL SECTION: Add human observations here directly during review. No automated tooling populates this section. -->
<!-- Suggested format for a finding:

### Finding {{n}}
**Comment:** "{{your observation}}"

**Flagged Entries (condensed):**
| Time | Message | Event | Flag |
|------|---------|-------|------|
| ... | ... | ... | ... |

-->

_This section is for manually recorded human observations during review. Add findings here directly when reviewing a run. No automated tooling will populate this section._

---

## Langfuse Trace Summary

<!-- Auto-populated by karma/briefcase.py — trace.list(session_id=karma_code) -->

{trace_section}

---

## Langfuse Errored Observations

<!-- Auto-populated by karma/briefcase.py — observations.get_many(trace_id=..., level=ERROR) per trace -->
<!-- Input/output truncated to 300 chars. -->

{obs_section}
"""
    return doc.strip()


def _build_summary_line(
    archetype: str,
    all_flags: list[dict],
    red_flags: list[dict],
    yellow_flags: list[dict],
) -> str:
    """Return the archetype-specific summary line (with trailing newline), or empty string."""
    if archetype == "Pipeline":
        # Derive run result from lifecycle markers in the flag data
        events = {e["event"] for e in all_flags}
        if "COMPLETE_RUN" in events:
            result = "complete"
        elif "ABORT_RUN" in events:
            result = "aborted"
        else:
            result = "incomplete"
        return f"\n**Run Result:** {result}\n"

    elif archetype == "Continuous":
        total = len(all_flags)
        return (
            f"\n**Session Health:** {len(red_flags)} red, "
            f"{len(yellow_flags)} yellow across {total} entries\n"
        )

    # Unknown archetype — no summary line. Do not guess.
    return ""


def _build_flag_table(flags: list[dict], colour: str) -> str:
    """Render a flag list as a markdown table, or an empty-state message."""
    if not flags:
        return f"_No {colour} flags detected in this window._"

    lines = [
        "| Time | Message | Event | Source |",
        "|------|---------|-------|--------|",
    ]
    for entry in flags:
        ts  = entry["timestamp"]
        msg = entry["message"].replace("|", "\\|")
        evt = (entry["event"] or "—").replace("|", "\\|")
        lines.append(f"| {ts} | {msg} | {evt} | Logfire |")

    return "\n".join(lines)


def _build_trace_table(traces: list[dict]) -> str:
    """Render Langfuse trace summaries as a markdown table."""
    if not traces:
        return "_No Langfuse traces found for this session._"

    lines = [
        "| Trace | Duration | Tokens | Cost |",
        "|-------|----------|--------|------|",
    ]
    for t in traces:
        name     = t["trace_name"].replace("|", "\\|")
        duration = f"{t['duration_ms']} ms" if t["duration_ms"] is not None else "—"
        tokens   = str(t["total_tokens"]) if t["total_tokens"] is not None else "—"
        cost     = f"${t['total_cost']:.4f}" if t["total_cost"] is not None else "—"
        lines.append(f"| {name} | {duration} | {tokens} | {cost} |")

    return "\n".join(lines)


def _build_obs_table(observations: list[dict]) -> str:
    """Render errored Langfuse observations as a markdown table."""
    if not observations:
        return "_No errored observations found._"

    lines = [
        "| Observation | Type | Input (truncated) | Output (truncated) | Error |",
        "|-------------|------|-------------------|--------------------|-------|",
    ]
    for obs in observations:
        name   = (obs["obs_name"] or "—").replace("|", "\\|")
        otype  = (obs["obs_type"] or "—").replace("|", "\\|")
        inp    = (obs["input_summary"]  or "—").replace("|", "\\|")
        out    = (obs["output_summary"] or "—").replace("|", "\\|")
        status = (obs["status_message"] or "—").replace("|", "\\|")
        lines.append(f"| {name} | {otype} | {inp} | {out} | {status} |")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# File writing
# ---------------------------------------------------------------------------

def write_briefcase(karma_code: str, content: str, now: datetime | None = None) -> Path:
    """
    Write the Briefcase markdown to _bmad-output/briefcases/{filename}.

    `now` should be the same datetime instance passed to generate_briefcase so
    the filename on disk matches the filename embedded in the document body.
    If omitted, a new timestamp is generated (acceptable only in tests).

    Returns the Path of the written file.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    filename_ts = now.strftime("%Y-%m-%d-%H%M%S")
    filename = f"{karma_code}-briefcase-{filename_ts}.md"

    # Resolve output directory relative to this file's project root
    # karma/briefcase.py → project root is two levels up
    project_root = Path(__file__).parent.parent
    output_dir = project_root / "_bmad-output" / "briefcases"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / filename
    output_path.write_text(content, encoding="utf-8")

    return output_path
