"""
CLI entry point for the Karma Health Reporter.

Queries Logfire and Langfuse for a given karma_code and appends a health snapshot
row to _bmad-output/health/health-log.csv.

Run with: uv run python scripts/health.py --karma-code NRD-Sale-101
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import os

# Load credentials from AgentManual/.env before importing any SDK that reads env vars.
# Resolve relative to this file so the script works from any working directory.
# Never create a local .env inside Karma — credentials live in the parent AgentManual dir.
from dotenv import load_dotenv

_env_path = Path(__file__).parent.parent.parent / "AgentManual" / ".env"
load_dotenv(_env_path)

import logfire
from langfuse import get_client

from karma.health import CSV_FIELDNAMES, append_health_row, query_langfuse_health, query_logfire_health
from karma.utils import parse_since

langfuse = get_client()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    logfire.configure(token=os.getenv("LOGFIRE_WRITE_TOKEN"))

    parser = argparse.ArgumentParser(description="Karma Health Reporter")
    parser.add_argument(
        "--karma-code",
        required=True,
        help="Karma Code to query (e.g. NRD-Sale-101)",
    )
    parser.add_argument(
        "--since",
        default=None,
        help="Look-back window: relative (e.g. 2h, 30m, 1d) or ISO 8601 timestamp",
    )
    parser.add_argument(
        "--archetype",
        default=None,
        help="Override archetype (Pipeline or Continuous). If omitted, falls back to Logfire data.",
    )
    args = parser.parse_args()

    # Parse --since before entering the try/finally — argparse errors should exit cleanly
    try:
        since = parse_since(args.since)
    except ValueError as e:
        print(str(e))
        sys.exit(1)

    # until is always now — use timezone.utc (datetime.utcnow() is deprecated Python 3.12, removed 3.13)
    until = datetime.now(timezone.utc)

    # CSV path must be absolute, computed relative to this file.
    # Path('_bmad-output/...') would silently write to the wrong location if cwd ≠ repo root.
    csv_path = Path(__file__).parent.parent / "_bmad-output" / "health" / "health-log.csv"

    try:
        logfire_data = query_logfire_health(args.karma_code, since, until)
        langfuse_data = query_langfuse_health(args.karma_code, since, until)

        # Archetype priority: CLI arg → Logfire row → "" (empty, honest)
        # Never default to "Pipeline" — would silently corrupt data for other archetypes
        archetype = args.archetype or logfire_data.get("archetype") or ""

        append_health_row(
            karma_code=args.karma_code,
            archetype=archetype,
            since=since,
            until=until,
            logfire_data=logfire_data,
            langfuse_data=langfuse_data,
            csv_path=csv_path,
        )

        print(f"Health snapshot written → {csv_path}")
        print(f"  karma_code:      {args.karma_code}")
        print(f"  red_flags:       {logfire_data['red_flag_count']}")
        print(f"  yellow_flags:    {logfire_data['yellow_flag_count']}")
        print(f"  total_cost_usd:  {langfuse_data['total_cost_usd']:.4f}")
        print(f"  total_tokens:    {langfuse_data['total_tokens']}")
        print(f"  error_obs:       {langfuse_data['error_observation_count']}")

    finally:
        # Always flush — Langfuse batches events silently. Must run even if exception raised above.
        langfuse.flush()


if __name__ == "__main__":
    main()
