---
project_name: 'Karma'
user_name: 'Anshumann'
date: '2026-03-02'
sections_completed: ['technology_stack', 'language_rules', 'framework_rules', 'testing_rules', 'quality_rules', 'workflow_rules', 'anti_patterns']
status: 'complete'
rule_count: 38
optimized_for_llm: true
---

# Project Context for AI Agents

_This file contains critical rules and patterns that AI agents must follow when implementing code in this project. Focus on unobvious details that agents might otherwise miss._

---

## Technology Stack & Versions

- **Language:** Python 3.x (no minimum version constraint — use latest stable)
- **Package manager:** `uv` — not pip
- **Application logger:** Logfire (Pydantic) — latest, OpenTelemetry-based
- **LLM observability:** Langfuse v3 SDK — latest
- **LLM provider:** OpenRouter (OpenAI-compatible API)
- **Testing:** pytest
- **Linting/formatting:** ruff

---

## Critical Implementation Rules

### Python Rules

- **Package manager is `uv` exclusively.** Install: `uv add <pkg>`. Run: `uv run python scripts/<name>.py`. Sync: `uv sync`. Never use `pip install` directly.
- **Async entry point:** `asyncio.run(main())`. Call `langfuse.flush()` after `asyncio.run()` completes — not inside the async context.
- **Imports:** `from langfuse import get_client, propagate_attributes` (v3 API). Never use the old `Langfuse()` constructor pattern.
- **Type hints:** Casual — on function signatures only. No `mypy` enforcement.

---

### Logfire Integration Rules

- **Initialize once** at script entry point: `logfire.configure()` before any log calls.
- **Every log call must include `karma_code`** — it is the primary correlation key. A log without it is invisible to Karma.
- **Karma fields are keyword args** on `logfire.info(...)` — not nested dicts.
- **Spans for timed operations:** Wrap LLM calls and tool calls in `with logfire.span(...)`.
- **Do NOT pass a timestamp** — Logfire handles it natively. Adding one conflicts with OpenTelemetry.
- **Tags use `_tags` kwarg:** `logfire.info('...', _tags=['sales'])` — underscore prefix is Logfire-reserved.

---

### Langfuse Integration Rules

- **v3 API only.** `get_client()` — NOT `Langfuse()`.
- **Trace entry point:** `langfuse.start_as_current_span(name=karma_code)` as a context manager — this creates the outer trace container. Do NOT use `start_as_current_observation(as_type="trace", ...)` — that API form is incorrect.
- **Nested observations:** Use `langfuse.start_as_current_observation(name="...", as_type="generation"|"retriever")` for LLM calls and tool calls INSIDE the outer span.
- **Session propagation:** `propagate_attributes(session_id=karma_code, ...)` — `session_id` is a direct kwarg, NOT nested inside `metadata`.
- **Cross-tool correlation:** Also pass `metadata={"karma_code": karma_code}` on the trace for the Karma Infinity Loop.
- **Trace URL:** `langfuse.get_trace_url()` — call AFTER `start_as_current_span()` is open. Returns `None` if called outside an active span. Use this to embed the Langfuse trace URL into Logfire attributes.
- **Flush on exit:** `langfuse.flush()` after `asyncio.run()` in every script — Langfuse batches events silently.
- **OpenRouter instrumentation:** OpenRouter is OpenAI-compatible — use `langfuse.openai` wrapper for auto-instrumentation.

---

### Karma Field Rules

- `flag` values: `"yellow"` (soft failure), `"red"` (hard failure), `None` or omitted (normal). **No other values.**
- `archetype` values: `"Pipeline"` or `"Continuous"` (strings, not enums).
- `event` format: `VERB_NOUN` in SCREAMING_SNAKE_CASE, max 3 segments. E.g., `GET_CRM`, `CALL_TOOL_RETRY`.
- `karma_code` format: `AGENT-Type-ID`. AGENT uppercase, Type TitleCase, ID no hyphens.
- `Connect` is a reserved Type for agent-to-agent handoffs — 4-segment format: `AGENT-Connect-TARGET-ID`.
- Sub-agents inherit calling pipeline's Type and ID — they do NOT register their own.

---

### Testing Rules

- **pytest only.** File naming: `test_*.py`. Mirror source file structure.
- **Mock external calls** with `pytest-mock` or `monkeypatch` — never hit live Logfire or Langfuse in tests.
- **Primary test type:** Scenario tests — given a described agent situation, assert the produced `logfire.info()` call has correct `karma_code` format, valid `event` name, and correct `archetype` string.
- Use `pytest.mark.parametrize` for scenario variations — keeps test code DRY.
- No coverage metric enforced — quality over percentage.

---

### Code Quality & Style Rules

- **Formatting:** `ruff` for linting and formatting. Configure in `pyproject.toml`.
- **File naming:** `snake_case` for all Python files and directories.
- **No classes unless clearly necessary** — prefer functions. Avoid premature OOP.
- **Constants:** `UPPER_SNAKE_CASE`. E.g., `ARCHETYPE_CONTINUOUS = "Continuous"`.
- **Karma field values are plain strings** — not Enum wrappers.
- **Every script must have a module-level docstring** (one paragraph max): agent name, archetype, karma_code format used.
- **All non-trivial logic must have inline comments** explaining the "why" — especially Karma field construction steps.

### Document Style Rules (`.md` files)

- Every major section opens with a `//` AI-anchor line (one-line machine summary).
- Recipe-first: complete working example before any explanation.
- Two examples minimum per major concept.
- AI Coding Agent is the primary reader — write for machine comprehension first.

---

### Development Workflow Rules

- **Project structure:**
  ```
  Karma/
  ├── pyproject.toml
  ├── docs/              # Karma Log Standard and reference docs
  ├── karma/             # Shared helper modules (package dir)
  ├── scripts/           # Runnable entry points only
  └── tests/             # pytest test files
  ```
- **`scripts/` contains only runnable entry points** — no shared logic. Helpers go in `karma/`.
- **Credentials:** Load from global `.env` at `AgentManual/.env`. Use `load_dotenv` with the absolute or relative path. Never create a local `.env` inside Karma.
- **Karma lives in its own GitHub repo** (`sentientstrokes/Karma`). The `docs/` folder is the canonical reference for all Karma-compliant projects — treat commits to `docs/karma-log-standard.md` as releases.
- `langfuse.flush()` required before any `sys.exit()` or script completion.

---

### Critical Don't-Miss Rules

// DON'T-MISS: These are the rules AI agents most commonly violate. Read before writing any code.

**Never do these:**
- `flag=False`, `flag=0`, `flag="none"` — only `"yellow"`, `"red"`, `None`, or omitted
- Pass a custom `timestamp` to Logfire — it conflicts with OpenTelemetry native handling
- Write a Logfire call without `karma_code`
- Register a Type named `Connect` — permanently reserved
- Let a sub-agent register its own Type
- Use the old `Langfuse()` constructor — v3 uses `get_client()`
- Nest `session_id` inside `metadata` in `propagate_attributes()` — it's a direct kwarg
- Run scripts with bare `python` — always `uv run python scripts/<name>.py`
- Hardcode Logfire or Langfuse credentials — load from `AgentManual/.env`
- Add an AI layer to Karma — it is code glue, not an intelligent system

**Error handling:**
- Never swallow exceptions silently. If caught: set `flag='red'` on the log entry and re-raise, or handle deliberately with a clearly flagged log. A neutral log message on a failed operation is a hidden bug.

---

## Usage Guidelines

**For AI Agents:**
- Read this file before implementing any code in this project
- Follow ALL rules exactly as documented
- When in doubt, prefer the more restrictive option
- Reference `docs/karma-log-standard.md` for full field definitions, registry, and integration examples

**For Humans:**
- Update when technology stack changes or new patterns emerge
- Keep rules specific and actionable — remove anything that becomes obvious
- Add new Karma field rules here when the Log Standard is updated

_Last Updated: 2026-03-02_
