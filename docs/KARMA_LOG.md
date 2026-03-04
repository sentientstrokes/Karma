<!-- KARMA_LOG: Read this before working in any Karma-instrumented project. This document orients an AI agent on what Karma is, how it works, and what it provides. For how to write compliant log entries, read docs/karma-log-standard.md. -->

# KARMA_LOG

**Last Updated:** 2026-03-04

<!-- CORE CLAIM: karma_code is the single correlation key. Everything else is elaboration. -->

## What Karma Is

Karma is observability glue. Its single mechanism is `karma_code` — a shared identifier passed to both Logfire and Langfuse on every agent run, making every app-level log entry and every AI trace jointly queryable by the same key. Karma has no AI layer. It is code glue, not an intelligent system.

Without `karma_code`, Logfire and Langfuse are two separate islands of data. Logfire holds structured application events. Langfuse holds deep AI trace data. Neither knows the other exists. With `karma_code` threaded through both, they form one investigation surface — a single key retrieves the full picture of any agent run across both tools.

---

<!-- ARCHITECTURE: Three-node triangle. Logfire + Langfuse + karma_code. Instrumenting only one tool produces a half-system. -->

## System Architecture

Three nodes form the system:

**Logfire** — structured application event logs. Every Karma field is stored as a JSON attribute in the `attributes` column, queryable via SQL. Logfire captures what happened at the application level: decisions made, tools called, flags raised, lifecycle events.

**Langfuse** — deep AI trace data. Prompts, completions, token counts, costs, latency breakdowns, nested observation trees. Langfuse captures what happened inside the AI reasoning layer.

**karma_code** — the shared key that bridges them. Every Logfire log entry carries it as a structured attribute. Every Langfuse trace carries it in metadata and as `session_id`.

An agent must instrument both tools with the same `karma_code` for the system to function. Instrumenting only one tool produces a half-system — you get application logs without AI context, or AI traces without application context. The correlation key only works when both sides carry it.

---

<!-- CONTEXT: Karma is one module in the AgentManual multi-repo system. -->

## Where Karma Lives

Karma is one module within the AgentManual multi-repo system. This document currently lives in `docs/` alongside `karma-log-standard.md` and will be relocated to the AgentManual root directory once the system matures, so it is accessible to all repos.

---

<!-- CONCEPTS: karma_code formats, archetypes, flags. The three things an instrumenter must understand before writing a single log line. -->

## Core Concepts

**karma_code** — Two formats exist, one per archetype. Continuous agents use `Agent-Type-SessionID`, where the agent shortcode leads because the agent is the primary identity. Pipeline agents use `Type-marker(-SubID)?`, where the pipeline Type leads because the pipeline is the primary identity. The marker segment's case distinguishes its role: UPPERCASE is a registered agent shortcode doing work, lowercase is a lifecycle or pipeline-specific function marker, and Title Case is reserved for `Connect` handoffs. Agent is a 2–3 character uppercase shortcode. Type is TitleCase. SessionID and SubID must not contain hyphens. Sub-agents inherit the parent's format and Type, replacing only the agent shortcode — this rule applies identically to both archetypes. The one exception: `Connect` is a reserved Type for handoffs between primary agents or between pipelines and agents, producing a 4-segment code (`SOURCE-Connect-TARGET-ID`). SOURCE and TARGET can each be either an agent shortcode (UPPERCASE) or a pipeline Type (Title Case) — the format is consistent regardless of whether the participants are agents or pipelines.

**Archetypes** — Every agent is one of two. `Pipeline` is an automation sequence — it starts, runs, and ends. Batch jobs, ETL processes, scheduled scripts, event-driven automations. `Continuous` is a long-running AI interaction driven by ongoing sessions — sales agents, support bots, design assistants. Not blendable within a single agent. A project may run agents of both archetypes.

**Flags** — Three states. `red` is a hard failure — the agent could not complete its task. `yellow` is a soft failure — the agent completed but something looks off. Omitted or `None` is normal operation — the default. Flags are machine-readable severity signals. They power the Briefcase debug report. They are independent of log message emojis.

---

<!-- REGISTRY: Pre-registration is a prerequisite action, not reference material. Both tables must be populated before any log is written. -->

## The Registry

Before writing any Karma log, two registrations are required. Both are performed in the `## Agent + Type Registry` section of `docs/karma-log-standard.md`, which contains two tables — the Agent Registry and the Type Registry.

The Agent Registry requires a row with a 2–3 uppercase character shortcode, globally unique, no collisions with existing entries. The Type Registry requires a row with a TitleCase pipeline Type, globally unique, referencing the same pipeline concept across projects. Sub-agents do not register — they inherit the calling pipeline's Type and ID.

Both registrations are prerequisite actions, not reference material. They must exist before a single log line is written.

---

<!-- WORKFLOW: Five phases in order. Instrument → Run → Inspect → Health → Infinity Loop. Each phase produces a distinct artifact or system state. -->

## The Karma Workflow

**Instrument** — Add `karma_code` and Karma fields to Logfire calls. Start a Langfuse trace with `karma_code` in metadata and as `session_id`. This is the entry point — nothing else in the system works until instrumentation is in place.

**Run** — The agent executes. Logfire receives structured event logs with Karma fields as attributes. Langfuse receives deep AI trace data with `karma_code` as the session key. Both data streams are keyed by the same identifier.

**Inspect** — After a run, generate a Briefcase report: a structured markdown document surfacing all red and yellow flagged log entries, plus Langfuse trace summaries and errored observation detail, for a given `karma_code`. The output follows the naming convention `{karma_code}-briefcase-{YYYY-MM-DD}-{HHMMSS}.md` in `_bmad-output/briefcases/`.

**Health** — Capture aggregate vital signs — flag counts, token cost, latency, error observation count — as a single CSV row appended to `_bmad-output/health/health-log.csv`. Every run appends a new row. No data is overwritten. The file accumulates across all sessions over time.

**Infinity Loop** — Navigate bi-directionally between tools. The Langfuse trace URL and trace ID are embedded in the first Logfire span as structured attributes (`langfuse_trace_url` and `langfuse_trace_id`), making the Logfire-to-Langfuse path a direct link rather than a manual search.

---

<!-- NATIVE UI: Two investigation capabilities require no Karma code. They are baseline — what the tools give you for free. -->

## Native UI Features

Two investigation capabilities require no Karma code — they are native to the tools and available as soon as the tools are configured.

**Logfire Live View** — real-time log streaming with SQL filtering. Filter by `karma_code` to isolate any session instantly. This is the primary application-level investigation surface.

**Langfuse Trace Panel** — full AI reasoning inspection: prompt and completion text, token counts, latency breakdown, cost attribution, nested observation tree. This is the primary AI-level investigation surface.

These are the baseline. What Karma adds on top is described in the sections that follow.

---

<!-- MCP: The Karma MCP Server gives dev AI tools direct access to investigation capabilities without file reads or CLI invocations. -->

## The KARMA MCP Server

The Karma MCP Server is how a dev AI tool (Claude Code, Cursor, etc.) talks directly to Karma. Instead of reading files or running CLI scripts, the dev AI calls Karma tools through the Model Context Protocol — the same way it calls any other tool.

### What It Does

The MCP server exposes 9 tools and 4 resources over stdio transport. It is organized into two layers:

**Quick-Check Layer** — fast, lightweight queries for triage:
- `get_briefcase` — generate a Briefcase debug report for a `karma_code`
- `get_health` — fetch health vitals for a `karma_code`
- `query_flags` — find all red/yellow flags across recent runs
- `get_trace_url` — get the Langfuse trace URL for a `karma_code`

**Deep Investigation Layer** — detailed queries into Logfire and Langfuse:
- `query_logfire` — browse application logs with structured filters (no raw SQL)
- `list_langfuse_traces` — list all AI traces for a `karma_code`
- `get_langfuse_trace` — full trace detail including observation tree
- `get_langfuse_observation` — full prompt and completion text for a single observation
- `list_langfuse_observations` — list observations with optional level/type filters

**Resources** — static reference material served as MCP resources:
- `karma://briefcases` — list available Briefcase reports
- `karma://briefcases/{filename}` — read a specific Briefcase report
- `karma://playbook/investigation` — step-by-step investigation playbook (the YOLO loop)
- `karma://playbook/quick-check` — 3-call health check sequence

### How a Dev AI Uses It

A dev AI working in any Karma-instrumented project can query Karma directly. Example interaction:

> **You:** "The NRD-Sale-101 run looks wrong, can you check?"
>
> **Dev AI:** *calls `get_briefcase(karma_code="NRD-Sale-101")`* → sees yellow flag on retry
>
> **Dev AI:** *calls `get_langfuse_observation(observation_id="...")`* → reads the full prompt/completion
>
> **Dev AI:** "The retry was caused by a timeout on the CRM call. The model re-attempted with the same prompt and got a shorter response. Here's what I'd change..."

No file reads. No CLI. No copy-paste from browser UIs. The dev AI has direct access to the same data a human would see in Logfire and Langfuse dashboards.

### How It's Registered

The Karma MCP server is registered globally in Claude Code's `~/.claude.json`, making it available to every project:

```json
{
  "mcpServers": {
    "karma": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "python", "scripts/mcp_server.py"],
      "cwd": "/path/to/AgentManual/Karma"
    }
  }
}
```

The code lives in `Karma/karma/mcp_server.py`. The entry point is `Karma/scripts/mcp_server.py`, which loads credentials from `AgentManual/.env` before starting the server. Credentials required: `LOGFIRE_READ_TOKEN`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`.

### The Playbooks

The two playbook resources teach the dev AI how to chain tools effectively:

**Investigation Playbook** (`karma://playbook/investigation`): A full YOLO-style investigation loop. Start with `get_briefcase`, check flags, dive into Logfire for application context, pivot to Langfuse for AI reasoning, pull full observation detail on anything suspicious. Loop until root cause is found.

**Quick-Check Playbook** (`karma://playbook/quick-check`): A 3-call health check. `get_health` → `query_flags` → `get_trace_url`. Done in seconds. Enough to answer "is this run healthy?" without a deep dive.

---

<!-- TOOLSET: What your instrumentation unlocks — the payoff on top of the native UI baseline. -->

## What Your Instrumentation Unlocks

**Theme 1 — Karma Log Standard** (`docs/karma-log-standard.md`): The field vocabulary and logging protocol. Defines every Karma field, the Agent and Type Registry, archetype rules, the emoji shorthand map, and Logfire/Langfuse integration patterns. The instrumenter's primary reference. **[COMPLETE]**

**Theme 2 — The Briefcase**: Queries Logfire and Langfuse for a given `karma_code` and produces a structured markdown debug report. Red flags surface first, then yellow. Includes a Langfuse trace summary and errored observation detail. AI-readable by design. **[COMPLETE]**

**Theme 3 — Health Dashboard**: Captures a session's vital signs — flag counts, token cost, latency, error observation count — as a single CSV row appended to `_bmad-output/health/health-log.csv`. Accumulates over time. Trivially importable into any analytics tool. **[COMPLETE]**

**Theme 4 — Karma Infinity Loop**: Embeds the Langfuse trace URL and trace ID into the first Logfire span as structured attributes. Makes the Logfire-to-Langfuse path a direct link in the terminal and in the Briefcase report. No manual cross-tool search required. **[COMPLETE]**

**Theme 5 — Handbook** (`docs/KARMA_LOG.md`): This document. System context for AI agents working in any Karma-instrumented project. **[COMPLETE]**

**Theme 6 — KARMA MCP**: A full investigation surface for dev AI tools. 9 MCP tools (4 quick-check + 5 deep investigation) and 4 resources (briefcases + playbooks), all keyed by `karma_code`. Quick-check: `get_briefcase`, `get_health`, `query_flags`, `get_trace_url`. Deep investigation: `query_logfire` (browse all logs), `list_langfuse_traces`, `get_langfuse_trace`, `get_langfuse_observation` (full prompt/completion), `list_langfuse_observations`. Playbooks: `karma://playbook/investigation` (YOLO investigation loop), `karma://playbook/quick-check` (3-call health check). A dev AI adds one config stanza to Claude Code or Cursor and queries Karma directly — no file reads, no CLI invocations. **[COMPLETE]**

_This section reflects the system as of the Last Updated date above. Update it when themes ship._

---

<!-- NEXT STEP: KARMA_LOG gives context. karma-log-standard gives instructions. -->

## Next Step

Read `docs/karma-log-standard.md` before writing any log entries. It defines every Karma field, the Agent and Type Registry, the emoji shorthand map, and the Logfire and Langfuse integration patterns with working examples. That document is the instrumenter's implementation reference. This document is the system context.
