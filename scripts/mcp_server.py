"""
Entry point for the Karma MCP Server.

Loads credentials from AgentManual/.env, then starts the Karma FastMCP server
over stdio. Designed to be invoked by MCP clients (Claude Code, Cursor) via:

    uv run python scripts/mcp_server.py

Claude Code config — add to ~/.claude.json under mcpServers:
    {
      "karma": {
        "type": "stdio",
        "command": "uv",
        "args": ["run", "python", "scripts/mcp_server.py"],
        "cwd": "/absolute/path/to/Karma"
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
