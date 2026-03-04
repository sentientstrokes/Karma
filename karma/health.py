"""
Karma Health Reporter.

Queries Logfire and Langfuse for a given karma_code and returns aggregated vital signs
for CSV output. No AI layer — this module counts, converts, and formats only.
"""

import csv
import os
from datetime import datetime, timezone
from pathlib import Path

from langfuse.api.client import FernLangfuse
from langfuse.api.resources.commons.types.observation_level import ObservationLevel
from logfire.query_client import LogfireQueryClient

from karma import KARMA_CODE_PATTERN

# Maximum pages to paginate when fetching Langfuse traces.
# Guards against infinite loops if meta.total_pages is permanently unavailable.
_MAX_PAGES = 100

# CSV column order — stable, will become Supabase column names. Do not rename.
# total_cost_usd and total_latency_ms are deliberately verbose for self-documenting schema.
CSV_FIELDNAMES = [
    "generated_at",
    "karma_code",
    "archetype",
    "window_from",
    "window_to",
    "red_flag_count",
    "yellow_flag_count",
    "trace_count",
    "total_tokens",
    "total_cost_usd",
    "total_latency_ms",
    "error_observation_count",
    "lifecycle_status",
    "session_turn_count",
]


# ---------------------------------------------------------------------------
# Logfire querying
# ---------------------------------------------------------------------------

def query_logfire_health(
    karma_code: str,
    since: datetime | None,
    until: datetime,
) -> dict:
    """
    Query Logfire for flagged entries and archetype-specific metrics for a given karma_code.

    Returns:
        {
            "red_flag_count": int,
            "yellow_flag_count": int,
            "archetype": str,          # "" if no flagged rows returned — never a hardcoded default
            "lifecycle_status": str,   # Pipeline only: "complete"/"aborted"/"incomplete"; "" otherwise
            "session_turn_count": str, # Continuous only: total entry count as string; "" otherwise
        }

    Note: For Pipeline archetypes, lifecycle markers (Ingest-start, Ingest-complete) use a
    different karma_code than agent entries (Ingest-INA). The lifecycle query extracts the Type
    (first segment) and queries for Type-start / Type-complete lifecycle marker codes.
    """
    if not KARMA_CODE_PATTERN.match(karma_code):
        raise ValueError(
            f"Invalid karma_code format: {karma_code!r}. "
            "Expected 2-4 hyphen-delimited segments (e.g. NRD-Sale-101, Ingest-start)"
        )

    read_token = os.getenv("LOGFIRE_READ_TOKEN")
    if not read_token:
        raise EnvironmentError(
            "Missing LOGFIRE_READ_TOKEN — add it to AgentManual/.env"
        )

    # --- All queries share one connection — avoids repeated SSL handshakes per query ---
    with LogfireQueryClient(read_token=read_token) as client:

        def _q(sql: str) -> list[dict]:
            result = client.query_json_rows(
                sql=sql,
                min_timestamp=since,
                max_timestamp=until,
            )
            return result.get("rows", [])

        # --- Query 1: all flagged entries for this karma_code ---
        # Must SELECT archetype explicitly — missing it causes KeyError in archetype fallback chain
        flag_sql = f"""
            SELECT
                attributes->>'flag'      AS flag,
                attributes->>'archetype' AS archetype,
                attributes->>'event'     AS event
            FROM records
            WHERE attributes->>'karma_code' = '{karma_code}'
              AND attributes->>'flag' IS NOT NULL
            ORDER BY start_timestamp ASC
        """
        rows = _q(flag_sql)

        # Count flags by value in Python — do not use SQL COUNT to preserve flexibility
        red_flag_count = sum(1 for r in rows if r.get("flag") == "red")
        yellow_flag_count = sum(1 for r in rows if r.get("flag") == "yellow")

        # Extract archetype from first flagged row — "" if no rows returned.
        # Never substitute a default value: "" is honest, a hardcoded fallback corrupts Supabase data.
        archetype = rows[0].get("archetype", "") if rows else ""

        # --- Archetype-specific second query (inside same connection) ---
        lifecycle_status = ""
        session_turn_count = ""

        if archetype == "Pipeline":
            # For Pipeline, lifecycle markers use different karma_code patterns:
            # Type-start (event=START_RUN), Type-complete (event=COMPLETE_RUN), Type-abort (event=ABORT_RUN)
            # Extract the Type from the first segment of the karma_code.
            pipeline_type = karma_code.split("-")[0]

            # Query for lifecycle marker entries — not restricted to flagged, since START_RUN
            # and COMPLETE_RUN are typically unflagged (only ABORT_RUN carries flag='red')
            lifecycle_sql = f"""
                SELECT attributes->>'event' AS event
                FROM records
                WHERE (
                      attributes->>'karma_code' = '{pipeline_type}-start'
                   OR attributes->>'karma_code' = '{pipeline_type}-complete'
                   OR attributes->>'karma_code' = '{pipeline_type}-abort'
                )
            """
            lifecycle_rows = _q(lifecycle_sql)
            events = {r.get("event", "") for r in lifecycle_rows}

            # Lifecycle precedence: COMPLETE_RUN wins if found; then ABORT_RUN; else incomplete
            if "COMPLETE_RUN" in events:
                lifecycle_status = "complete"
            elif "ABORT_RUN" in events:
                lifecycle_status = "aborted"
            else:
                # START_RUN found (or no lifecycle entries at all) — run did not finish normally
                lifecycle_status = "incomplete"

            # session_turn_count is not applicable for Pipeline archetype
            session_turn_count = ""

        elif archetype == "Continuous":
            # Count ALL log entries (not just flagged) — provides the denominator for flag density.
            # flag density = red_flag_count / session_turn_count — enables degradation trend analysis.
            count_sql = f"""
                SELECT COUNT(*) AS turn_count
                FROM records
                WHERE attributes->>'karma_code' = '{karma_code}'
            """
            count_rows = _q(count_sql)
            # COUNT(*) returns exactly one row; turn_count may be int or str depending on driver
            session_turn_count = str(count_rows[0].get("turn_count", 0)) if count_rows else "0"
            lifecycle_status = ""

        # archetype == "" (unknown): leave both as "" — do not guess

    return {
        "red_flag_count": red_flag_count,
        "yellow_flag_count": yellow_flag_count,
        "archetype": archetype,
        "lifecycle_status": lifecycle_status,
        "session_turn_count": session_turn_count,
    }


# ---------------------------------------------------------------------------
# Langfuse querying
# ---------------------------------------------------------------------------

def query_langfuse_health(
    karma_code: str,
    since: datetime | None,
    until: datetime,
) -> dict:
    """
    Query Langfuse for trace-level metrics and error observation count for a given karma_code.

    Returns:
        {
            "trace_count": int,
            "total_tokens": int,
            "total_cost_usd": float,
            "total_latency_ms": int,
            "error_observation_count": int,
        }
    """
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_HOST", "http://localhost:3000")

    missing = [
        name for name, val in [
            ("LANGFUSE_PUBLIC_KEY", public_key),
            ("LANGFUSE_SECRET_KEY", secret_key),
        ]
        if not val
    ]
    if missing:
        raise EnvironmentError(
            f"Missing Langfuse credentials: {', '.join(missing)} — add them to AgentManual/.env"
        )

    # base_url is the confirmed constructor kwarg (from briefcase.py: FernLangfuse(base_url=host, ...))
    client = FernLangfuse(
        base_url=host,
        x_langfuse_public_key=public_key,
        # HTTP Basic Auth convention: username = public key, password = secret key
        username=public_key,
        password=secret_key,
    )

    # --- Query 1: trace summaries with pagination ---
    # Paginate to handle sessions with many traces — default page size is ~50-100 results.
    # Not paginating causes silent undercount of all aggregated metrics (tokens, cost, latency).
    all_traces = []
    page = 1
    while page <= _MAX_PAGES:
        traces_response = client.trace.list(
            session_id=karma_code,
            from_timestamp=since,
            to_timestamp=until,
            page=page,
        )
        batch = traces_response.data or []
        all_traces.extend(batch)

        # Stop when meta indicates last page, or batch is smaller than typical page size
        meta = getattr(traces_response, "meta", None)
        if meta is not None:
            total_pages = getattr(meta, "total_pages", None)
            if total_pages is not None and page >= total_pages:
                break
        # Fallback: if batch < 50 (typical Langfuse default), assume we're on the last page
        if not batch or len(batch) < 50:
            break
        page += 1

    # Aggregate metrics across all pages.
    # None-guards on every field — Langfuse may return None for any metric on incomplete traces.
    trace_count = len(all_traces)
    total_tokens = sum((getattr(t, "total_tokens", None) or 0) for t in all_traces)
    total_cost_usd = sum((getattr(t, "total_cost", None) or 0.0) for t in all_traces)

    # latency is in seconds on the Trace object (confirmed from briefcase.py inline comment:
    # "latency is in seconds on the Trace object when metrics are included")
    # Convert to integer milliseconds: multiply by 1000, round, cast to int.
    def _to_ms(latency_sec) -> int:
        if latency_sec is None:
            return 0
        # round() first to avoid float precision drift (e.g. 1.0009999... → 1001)
        return int(round(latency_sec * 1000))

    total_latency_ms = sum(_to_ms(getattr(t, "latency", None)) for t in all_traces)

    # --- Query 2: errored observations per trace ---
    # The observations endpoint has no session_id filter — must iterate per trace.
    # Confirmed in briefcase.py: "Must iterate per trace — no session_id filter on observations endpoint"
    error_observation_count = 0
    for trace in all_traces:
        obs_response = client.observations.get_many(
            trace_id=trace.id,
            level=ObservationLevel.ERROR,
        )
        error_observation_count += len(obs_response.data or [])

    return {
        "trace_count": trace_count,
        "total_tokens": total_tokens,
        "total_cost_usd": total_cost_usd,
        "total_latency_ms": total_latency_ms,
        "error_observation_count": error_observation_count,
    }


# ---------------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------------

def append_health_row(
    karma_code: str,
    archetype: str,
    since: datetime | None,
    until: datetime,
    logfire_data: dict,
    langfuse_data: dict,
    csv_path: Path,
) -> Path:
    """
    Assemble and append a single health row to the CSV file.

    Creates the CSV with header if it does not exist or is empty.
    Appends on every call — never overwrites.
    Returns the path of the CSV file.
    """
    # Ensure the output directory exists before any file operations
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    # Header detection: check BEFORE opening the file in append mode.
    # file.tell() == 0 in append mode can return non-zero on Windows for a newly created empty file.
    # stat().st_size == 0 is reliable cross-platform.
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0

    # window_from: empty cell (not the string "None") when since is not provided.
    # Two consecutive commas in raw CSV = empty cell = correct for Supabase nullable column.
    window_from = since.isoformat() if since is not None else ""

    # Assemble row — all 14 columns in the exact order specified in CSV_FIELDNAMES.
    # Type-cast numeric values to prevent TypeError from unexpected non-numeric returns.
    row = {
        "generated_at":            datetime.now(timezone.utc).isoformat(),
        "karma_code":              karma_code,
        "archetype":               archetype,
        "window_from":             window_from,
        "window_to":               until.isoformat(),
        "red_flag_count":          int(logfire_data["red_flag_count"]),
        "yellow_flag_count":       int(logfire_data["yellow_flag_count"]),
        "trace_count":             int(langfuse_data["trace_count"]),
        "total_tokens":            int(langfuse_data["total_tokens"]),
        # Fixed-precision string for cost — prevents non-deterministic float repr.
        # f"{0.0032:.6f}" → "0.003200" (stable value for Supabase column type inference)
        # NOT round(x, 6) — Python's str(float) is non-deterministic at low precision.
        "total_cost_usd":          f"{langfuse_data['total_cost_usd']:.6f}",
        "total_latency_ms":        int(langfuse_data["total_latency_ms"]),
        "error_observation_count": int(langfuse_data["error_observation_count"]),
        # Archetype-specific columns: empty string for the non-applicable archetype
        "lifecycle_status":        logfire_data.get("lifecycle_status", ""),
        "session_turn_count":      logfire_data.get("session_turn_count", ""),
    }

    # newline='' is required by the csv module on all platforms to prevent double newlines
    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        if write_header:
            writer.writeheader()
        writer.writerow(row)

    return csv_path
