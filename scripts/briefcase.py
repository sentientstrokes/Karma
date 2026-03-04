"""
CLI entry point for the Karma Briefcase Reporter.

Queries Logfire and Langfuse for a given karma_code, extracts red and yellow
flagged entries, and writes a structured Briefcase markdown file.

Usage:
    uv run python scripts/briefcase.py --karma-code NRD-Sale-101
    uv run python scripts/briefcase.py --karma-code NRD-Sale-101 --since 2h
    uv run python scripts/briefcase.py --karma-code NRD-Sale-101 --since 2026-03-03T09:00:00 --archetype Pipeline
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import logfire
from dotenv import load_dotenv
from logfire.query_client import LogfireQueryClient

# Load credentials from AgentManual/.env — never create a local .env
# Path is resolved relative to this script: scripts/ → Karma/ → AgentManual/
_env_path = Path(__file__).parent.parent.parent / "AgentManual" / ".env"
if not _env_path.exists():
    print(
        f"Warning: expected credentials at {_env_path} but file not found. "
        "Credentials may be missing — add AgentManual/.env before running.",
        file=sys.stderr,
    )
load_dotenv(_env_path)

from karma import KARMA_CODE_PATTERN
from karma.briefcase import (
    generate_briefcase,
    query_langfuse_context,
    query_langfuse_trace_fields,
    query_logfire_flags,
    write_briefcase,
)
from karma.utils import parse_since


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a Karma Briefcase for a given karma_code."
    )
    parser.add_argument(
        "--karma-code",
        required=True,
        help="The Karma Code to inspect, e.g. NRD-Sale-101",
    )
    parser.add_argument(
        "--since",
        default=None,
        help="Time window start: relative (2h, 30m, 1d) or ISO 8601 timestamp",
    )
    parser.add_argument(
        "--archetype",
        default=None,
        choices=["Pipeline", "Continuous"],
        help="Force archetype. If omitted, inferred from Logfire data or left empty.",
    )
    args = parser.parse_args()

    # Validate karma_code format BEFORE it touches any SQL string interpolation.
    # query_langfuse_trace_fields and query_logfire_flags both use .format(karma_code=karma_code).
    if not KARMA_CODE_PATTERN.match(args.karma_code):
        raise SystemExit(
            f"Invalid --karma-code format: '{args.karma_code}'. "
            "Expected: 2-4 hyphen-delimited segments of alphanumeric/underscore chars "
            "(e.g. NRD-Sale-101, Ingest-start, Ingest-INE-R01Row12)"
        )

    karma_code = args.karma_code
    since      = parse_since(args.since)

    # Single timestamp for the entire run — used as Logfire query cap (F14 fix)
    # and passed to generate/write so filename on disk matches body (F3 fix).
    briefcase_now = datetime.now(timezone.utc)

    # Logfire write token — used by logfire.configure() for any internal spans
    logfire.configure(token=os.getenv("LOGFIRE_WRITE_TOKEN"))

    logfire.info(
        "briefcase_run_start",
        karma_code=karma_code,
        event="BRIEFCASE_START",
        since=str(since) if since else "all-time",
    )

    # --- Query Logfire flags ---
    # LogfireQueryClient requires LOGFIRE_READ_TOKEN (separate from write token)
    # max_timestamp=briefcase_now caps the query to this run's start time (F14 fix).
    with LogfireQueryClient(read_token=os.getenv("LOGFIRE_READ_TOKEN")) as lf_client:
        # Both Logfire queries share the same client context and time window
        logfire_flags = query_logfire_flags(karma_code, since, briefcase_now, lf_client)
        trace_fields = query_langfuse_trace_fields(karma_code, since, briefcase_now, lf_client)  # Theme 4

    # --- Resolve archetype ---
    # CLI arg takes priority; fall back to first Logfire row; fall back to "" (honest unknown)
    if args.archetype:
        archetype = args.archetype
    elif logfire_flags:
        archetype = logfire_flags[0].get("archetype", "") or ""
        if not archetype:
            print(
                "Warning: archetype could not be determined from Logfire data. "
                "The Briefcase will have a blank Archetype field. "
                "Re-run with --archetype Pipeline or --archetype Continuous to fix this.",
                file=sys.stderr,
            )
    else:
        archetype = ""
        print(
            "Warning: no Logfire flags found and --archetype not provided. "
            "Archetype will be blank in the Briefcase. "
            "Re-run with --archetype Pipeline or --archetype Continuous to fix this.",
            file=sys.stderr,
        )

    # --- Query Langfuse context ---
    langfuse_context = query_langfuse_context(karma_code, since)

    # --- Generate and write Briefcase ---
    # Theme 4: warn if Pipeline archetype is missing trace fields (spec says mandatory)
    if archetype == "Pipeline" and not trace_fields["langfuse_trace_url"]:
        print(
            "Warning: Pipeline-archetype run has no Langfuse trace URL in Logfire. "
            "The Briefcase will not have a clickable Langfuse link. "
            "Ensure the pipeline entry point uses langfuse.start_as_current_span() "
            "and embeds langfuse_trace_url in the root Logfire span.",
            file=sys.stderr,
        )

    content = generate_briefcase(
        karma_code, archetype, logfire_flags, langfuse_context, now=briefcase_now,
        langfuse_trace_url=trace_fields["langfuse_trace_url"],   # Theme 4
        langfuse_trace_id=trace_fields["langfuse_trace_id"],     # Theme 4
    )
    output_path = write_briefcase(karma_code, content, now=briefcase_now)

    logfire.info(
        "briefcase_run_complete",
        karma_code=karma_code,
        event="BRIEFCASE_COMPLETE",
        output_path=str(output_path),
    )

    print(output_path)


# asyncio.run() then langfuse.flush() — flush MUST be called after asyncio.run() completes,
# not inside the async context, so Langfuse batched events are not silently dropped.
if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        # flush() MUST run even if main() crashes — Langfuse batches events silently
        # and will drop them if the process exits before flushing.
        from langfuse import get_client
        get_client().flush()
