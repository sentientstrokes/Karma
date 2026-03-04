import re

# Valid karma_code pattern — supports all archetypes:
#   Continuous: Agent-Type-SessionID (3 segments, e.g. NRD-Sale-101)
#   Pipeline:   Type-marker (2 segments) or Type-marker-SubID (3 segments)
#   Connect:    Source-Connect-Target-ID (4 segments)
# Enforced before any SQL interpolation to prevent injection.
# Imported by karma/briefcase.py, karma/health.py, and scripts/*.py.
KARMA_CODE_PATTERN = re.compile(r"^[A-Za-z0-9_]+-[A-Za-z0-9_]+(-[A-Za-z0-9_]+){0,2}$")
