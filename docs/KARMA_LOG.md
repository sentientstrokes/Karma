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

These are the baseline. What Karma adds on top is described in the next section.

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
