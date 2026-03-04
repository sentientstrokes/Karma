"""
CLI entry point for the Karma Health Reporter.

Queries Logfire and Langfuse for a given karma_code and appends a health snapshot
row to _bmad-output/health/health-log.csv.

Run with: uv run python scripts/health.py --karma-code NRD-Sale-101
"""

import argparse
import re
import sys
from datetime import datetime, timedelta, timezone
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

langfuse = get_client()


# ---------------------------------------------------------------------------
# Time window helper
# ---------------------------------------------------------------------------

def parse_since(value: str | None) -> datetime | None:
    # SYNC: This function is duplicated in scripts/briefcase.py. Keep both copies identical.
    # Divergence = silent behaviour difference.
    """
    Parse --since argument into a UTC-aware datetime, or None if not provided.

    Supported relative formats: 30m (minutes), 2h (hours), 1d (days).
    Supported absolute format: any ISO 8601 string.
    Raises ValueError for unrecognised formats.
    """
    if value is None:
        return None

    # Relative duration: number + unit suffix (m/h/d)
    match = re.fullmatch(r"(\d+)(m|h|d)", value.strip())
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        delta = {"m": timedelta(minutes=amount), "h": timedelta(hours=amount), "d": timedelta(days=amount)}[unit]
        return datetime.now(timezone.utc) - delta

    # Absolute ISO 8601 — attach UTC if no timezone info present
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        pass

    raise ValueError(
        "--since must be a relative duration (e.g. 2h, 30m, 1d) or ISO 8601 timestamp"
    )


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

    try:
        since = parse_since(args.since)
    except ValueError as e:
        print(str(e))
        sys.exit(1)

    until = datetime.now(timezone.utc)

    csv_path = Path(__file__).parent.parent / "_bmad-output" / "health" / "health-log.csv"

    try:
        logfire_data = query_logfire_health(args.karma_code, since, until)
        langfuse_data = query_langfuse_health(args.karma_code, since, until)

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
        langfuse.flush()


if __name__ == "__main__":
    main()
