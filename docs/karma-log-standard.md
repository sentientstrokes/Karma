// KARMA LOG STANDARD: Reference this document before writing any log entry in a Karma-compliant project.

# Karma Log Standard

**Version:** 1.0 | **Last Updated:** 2026-03-02

This document is the single reference for how Karma-compliant log entries are structured, what fields are defined, and how agents and pipeline types are identified across projects. The primary reader is an AI Coding Agent — every section is written for machine comprehension first, human engineer second. Start with the Recipe section below — a complete working example — then use the remaining sections as field-by-field reference.

---

// RECIPE: This is what a valid Karma log entry looks like. All fields shown here are defined in the sections that follow.

## Recipe — Complete Example

**Read this first. Everything below explains what you see here.**

### Example 1 — Continuous Agent Log Entry (Logfire)

```python
logfire.info(
    '👤 Found Customer: Anshumann',
    karma_code='NRD-Sale-101',
    event='GET_CRM',
    archetype='Continuous',
    flag=None
)
```

**What Logfire stores (attributes JSON):**

```json
{
  "karma_code": "NRD-Sale-101",
  "event": "GET_CRM",
  "archetype": "Continuous"
}
```

`flag=None` is not stored — Logfire omits `None` attributes entirely. Omitting `flag` and passing `flag=None` produce identical results. See Flag Definitions for when to set it.

Logfire handles the timestamp natively. The message string becomes the primary log entry in the Logfire timeline. All other Karma fields are keyword attributes stored in the `attributes` column.

### Example 2 — Pipeline Agent Log Entry (Logfire)

```python
logfire.info(
    '✅ Batch ingestion complete: 1,204 records processed',
    karma_code='INA-Ingest-Run042',
    event='COMPLETE_BATCH',
    archetype='Pipeline',
    flag=None
)
```

**What Logfire stores:**

```json
{
  "karma_code": "INA-Ingest-Run042",
  "event": "COMPLETE_BATCH",
  "archetype": "Pipeline"
}
```

**Querying in Logfire:** Use SQL on the `attributes` column:

- `attributes->>'karma_code' = 'NRD-Sale-101'` — find all log entries for a session.
- `attributes->>'flag' = 'red'` — surface all hard failures.
- `attributes->>'flag' IS NOT NULL` — surface all flagged entries (yellow and red).

---

// REGISTRY: Check both tables before starting. Register your Agent shortcode and your pipeline Type. Sub-agents use the calling pipeline's Type.

## Agent + Type Registry

Register your agent shortcode and pipeline Type here **before writing any logs**. This is a prerequisite action — not reference material. Check existing entries to avoid collisions. Stale or abandoned entries remain until a human cleans them up — this preserves historic trace linkage in Logfire and Langfuse.

### Agent Registry

| Shortcode | Agent Name | Description | Owner | Date Registered |
|-----------|------------|-------------|-------|-----------------|
| ABC | Example Agent | Brief description of agent purpose | Your Name | YYYY-MM-DD |
| NRD | Narad Sales Agent | Handles WhatsApp customer conversations | Anshumann | 2026-03-01 |
| RSC | Research Sub-Agent | Global research utility called by any primary agent | Anshumann | 2026-03-01 |

_The NRD and RSC rows above are illustrative. Remove them when you add your first real entry._

**Shortcode rules:** 2–3 uppercase alphanumeric characters. Globally unique — no two agents share a shortcode.

---

#### How to Choose a Shortcode

Two types of agents exist, and they follow different shortcode conventions:

**Type 1 — Named Agents**

Some agents have a proper identity and name. The name IS the agent — it has a persona, a purpose, a reputation. When you say "Narad handled that call," you mean this specific agent by name. For these, shortcode the name.

- `NRD` = Narad (a sales agent with its own identity)
- `RSC` = Research (a shared utility agent with its own identity)
- `GRD` = Guardian (a monitoring agent with its own identity)

**Type 2 — Functional Agents**

Some agents are defined by the role they play within a subsystem, not by a unique name. These are engineering constructs — "the Architect in the Ingestion pipeline," "the Extractor in the Ingestion pipeline." The problem: identical role names exist across different subsystems. If you registered `ARC` for Architect, you would immediately collide — an Ingestion Architect and a Sales Architect both want `ARC`. Registering generic role names leads to a polluted, ambiguous registry within weeks.

**The solution: subsystem-prefix shortcodes.**

Format: `[2-char subsystem prefix][1-char role initial]`

This encodes *which subsystem's instance of the role* — not just the role in the abstract.

**Example — an Ingestion system with multiple agents:**

| Shortcode | Agent | Reasoning |
|-----------|-------|-----------|
| `INC` | Ingestion Cartographer | `IN` (Ingestion) + `C` (Cartographer) |
| `INA` | Ingestion Architect | `IN` (Ingestion) + `A` (Architect) |
| `INE` | Ingestion Extractor | `IN` (Ingestion) + `E` (Extractor) |

If a Sales subsystem also has an Architect, it gets `SLA` — not `ARC`, not `INA`.

| Shortcode | Agent | Reasoning |
|-----------|-------|-----------|
| `SLA` | Sales Architect | `SL` (Sales) + `A` (Architect) |
| `SLR` | Sales Researcher | `SL` (Sales) + `R` (Researcher) |

No collisions. No ambiguity. The registry stays clean as the project scales.

**The test for which convention to use:**

> "Does this agent have a name you'd use in a sentence?" (e.g., "Narad picked up the call") → shortcode the name.
>
> "Is this agent a functional role in a system?" (e.g., "The Ingestion Architect mapped the schema") → use subsystem-prefix + role initial.

---

### Type Registry

| Type | Description | Archetype | Owner | Date Registered |
|------|-------------|-----------|-------|-----------------|
| Example | Your pipeline context | Pipeline or Continuous | Your Name | YYYY-MM-DD |
| Sale | Customer sales conversation pipeline | Continuous | Anshumann | 2026-03-01 |
| Ingest | Batch data ingestion job | Pipeline | Anshumann | 2026-03-01 |

_The Sale and Ingest rows above are illustrative. Remove them when you add your first real entry._

**Type label rules:**
- Title Case. Single word preferred. E.g., `Sale`, `Ingest`, `Design`, `Support`.
- If two words are unavoidable, use CamelCase with no spaces: `DataSync`, `BatchIngest`. This keeps the hyphen-delimited Karma Code parseable: `ETL-DataSync-Run01`.
- Globally unique. A Type registered as `Sale` means the same sales pipeline concept everywhere. Different projects may share a Type — but it must reference the same pipeline concept.
- `Connect` is **reserved** for agent-to-agent handoffs. Never register it as a regular Type. See Karma Code Format section.

Sub-agents inherit the calling pipeline's Type — they do not register their own.

---

// ARCHETYPES: Pick one per agent. Archetypes are strict — not blendable. A project can run agents of different archetypes.

## Archetype Definitions

Every agent is one of two archetypes. Pick one. They are not blendable within a single agent — but a project can absolutely run both (e.g., a Continuous sales agent AND a Pipeline batch sync in the same system).

### Pipeline

An automation sequence, batch job, or one-time script. It starts, does its job, and ends.

- **Examples:** A data ingestion job, a scheduled report generator, a one-off CRM sync, an ETL pipeline.
- **Typically tracks:** Completion status, accuracy, duration, error count.
- **Session ID is typically:** A Job ID, Run ID, or Batch number.
- **Type naming hint:** Name it after the job. E.g., `Ingest`, `Sync`, `Report`.
- **Karma Code example:** `INA-Ingest-Run042` — an Ingestion Architect running ingestion job #42.

### Continuous

A long-running or streaming agent driven by ongoing AI interactions. It persists across multiple exchanges and sessions.

- **Examples:** A sales agent handling customer conversations, a graphic design assistant, a support bot, a creative writing agent.
- **Typically tracks:** Session count, interaction health, last active, response quality signals.
- **Session ID is typically:** A Customer ID, Conversation ID, or Project ID.
- **Type naming hint:** Name it after the domain. E.g., `Sale`, `Design`, `Support`.
- **Karma Code example:** `NRD-Sale-101` — Narad handling customer #101.

Metrics listed above are illustrative starting points. The project defines what "healthy" means for its specific agent.

---

// KARMA CODE: Format is AGENT-Type-ID. Agent and Type must be registered. ID is project-defined and must not contain hyphens. Connect is reserved for agent-to-agent handoffs and is the only 4-segment exception.

## Karma Code Format

**Format:** `AGENT-Type-ID`

### Segment Breakdown

- `AGENT` — 2–3 character shortcode registered in the Agent Registry. Identifies who is acting. Always uppercase.
- `Type` — Pipeline context registered in the Type Registry. Identifies what pipeline is running. Always Title Case.
- `ID` — The session identifier. Project-defined — whatever uniquely identifies a session in that project's context (Customer ID, Job ID, Run number, etc.). **Must not contain hyphens** — hyphens are reserved as segment delimiters.

### Naming Rules

- **AGENT:** Uppercase, 2–3 alphanumeric characters, registered before use.
- **Type:** Title Case, single word preferred (CamelCase if two words), globally unique, registered before use.
- **ID:** Project-defined, meaningful to the domain. No hyphens. Alphanumeric and underscores are safe. E.g., `101`, `Run042`, `C101`, `job_99`.

### Examples

**Continuous agent:**
Narad handling customer 101: `NRD-Sale-101`

**Pipeline agent:**
Ingestion Architect running batch 42: `INA-Ingest-Run042`

### Sub-Agent Inheritance

Sub-agents inherit the calling pipeline's Type and session ID. They do NOT create a new pipeline or register a new Type.

- Primary sales agent Narad starts: `NRD-Sale-101`
- Narad calls global Research sub-agent: `RSC-Sale-101` (same Type, same session)
- Research calls Review sub-agent: `RVW-Sale-101` (still same pipeline)

All three agents can be queried together with a single Logfire filter: `attributes->>'karma_code' LIKE '%-Sale-101'`.

### Agent-to-Agent Handoffs — The `Connect` Type

When a primary agent hands control to another primary agent (not a sub-agent), use the reserved `Connect` Type.

**Format:** `AGENT-Connect-TARGET-ID`

This is the **only exception** to the 3-segment `AGENT-Type-ID` format. Connect codes are always 4 segments. They create a visible "bridge" in the logs showing exactly where control transferred between primary agents.

**Example chain — Sales agent hands off to Design agent:**

```
NRD-Sale-123            → Narad starts sales session for customer 123
NRD-Connect-DSG-123     → Narad hands off to Design agent (4-segment Connect code)
DSG-Design-123          → Design agent takes over in its own pipeline
RSC-Design-123          → Research sub-agent called within Design
DSG-Design-123          → Design completes
DSG-Connect-NRD-123     → Design hands back to Narad (4-segment Connect code)
NRD-Sale-123            → Narad resumes
```

The session ID (`123`) persists across the entire chain. The `Connect` entries show the exact handoff points. The full story is readable from the log alone.

---

// FIELDS: These 7 fields are the Karma vocabulary. Their meanings are locked. Use them when applicable — omit when not needed. Never repurpose them.

## Defined Fields

These 7 fields are Karma's vocabulary. Their meanings are fixed — when you use one, it must follow the rules below. Not every log line needs every field. A simple status log might only have `karma_code`, `event`, and `flag`. A detailed trace entry might use all 7. The rule is: if you use the word, use it correctly.

**The consequence of ignoring this:** Nothing explodes. Karma will still run. But inconsistent field usage degrades readability, breaks Logfire queries (filters return partial results), and makes the Detective's Briefcase unreliable. The debugging experience shifts from methodical investigation to guesswork.

| Field | Description |
|-------|-------------|
| `message` | The primary Logfire message string. Brief, plain English, present tense. ~100 characters recommended. Prepend the emoji for human scanning. E.g., `'👤 Found Customer: Anshumann'`, `'❌ Tool call failed: CRM unreachable'`. |
| `karma_code` | The session's full Karma Code. Format: `AGENT-Type-ID`. Always include this on every log line — it is the primary correlation key. |
| `event` | VERB_NOUN identifier in SCREAMING_SNAKE_CASE. See Event Naming section. E.g., `GET_CRM`, `COMPLETE_BATCH`, `SEND_MSG`. |
| `archetype` | `"Pipeline"` or `"Continuous"`. Matches the Archetype chosen at project setup. |
| `flag` | Omit or pass `None` for normal operation (not stored). `"yellow"` for soft failure. `"red"` for hard failure. Powers the Detective's Briefcase severity filter. Independent of the emoji used. |
| `emoji` | Optional: store the emoji as a separate attribute in addition to prepending it to the message. Single emoji from the Karma Emoji Map. E.g., `emoji='👤'`, `emoji='❌'`. Prepending to the message string is the primary approach — this field is for projects that also want the emoji queryable in Logfire. |
| `extra` | A catch-all for additional structured data specific to this log entry. Pass as a dict. No schema enforced — project-defined. |

`karma_code` is the one field that should appear on every single Karma log line. It is the thread that ties everything together across Logfire and Langfuse.

### Example — Using `emoji` and `extra` as separate fields

```python
logfire.info(
    '🛠️ Tool call returned null: CRM unreachable',
    karma_code='NRD-Sale-101',
    event='CALL_TOOL',
    archetype='Continuous',
    flag='red',
    emoji='🛠️',                                          # also stored as queryable attribute
    extra={
        'tool_name': 'crm_lookup',
        'customer_id': 101,
        'error': 'connection_timeout'
    }
)
```

### Example — Minimal log entry (only required fields)

```python
logfire.info(
    '✅ Session complete',
    karma_code='INA-Ingest-Run042',
    event='COMPLETE_BATCH',
    archetype='Pipeline',
)
```

Not every log line needs all 7 fields. When a field is omitted, it simply isn't stored. The rule: if you include a field, follow its definition.

---

// EVENT NAMES: VERB_NOUN in SCREAMING_SNAKE_CASE. Max 3 segments. Document new names in your project. This standard will evolve.

## Event Naming Convention

- **Pattern:** `VERB_NOUN` — the verb first describes the action, the noun describes the target. E.g., `GET_CRM`, `SEND_MSG`, `START_AI`, `CALL_TOOL`, `COMPLETE_BATCH`.
- **Case:** SCREAMING_SNAKE_CASE always. No spaces, no lowercase.
- **Length:** Max 3 underscore-separated segments. `CALL_TOOL_RETRY` = acceptable. `CUSTOMER_CRM_DATA_FETCH_RETRY` = not.
- **Scope:** Event names are defined per project but should be intuitive and consistent. A future version of this standard will define a canonical event library. Until then:
  - Be consistent within your project.
  - Use intuitive VERB_NOUN pairs.
  - Document your project's event names in your project README.
  - When the canonical library is published, existing event names can be mapped if needed.

### Example 1 — Continuous Sales Agent Events

`GET_CRM`, `LOAD_MEM`, `SEND_MSG`, `RECEIVE_MSG`, `START_AI`, `CALL_TOOL`

### Example 2 — Pipeline Batch Agent Events

`START_BATCH`, `FETCH_DATA`, `PROCESS_RECORD`, `COMPLETE_BATCH`, `FAIL_BATCH`

---

// EMOJI MAP: Tier 1 meanings are globally locked. Tier 2 is yours to define. Emojis are for human visual scanning — they are independent of the flag field.

## Emoji Shorthand Map

Emojis are the human eye's first filter on a log line. Before reading a word, a glance at the emoji tells the reader what kind of event they're looking at. Tier 1 ensures critical signals (success, failure, retry, AI call) mean the same thing everywhere.

### Tier 1 — Mandatory (Meaning Globally Locked)

"Mandatory" means the *meaning* is locked. You are not required to use them on every log line — but if they appear in your logs, they must mean exactly what is written here. Using them for anything else corrupts your debug trail, breaks cross-project readability, and makes the Detective's Briefcase surface misleading clues. Debugging with corrupted emojis is like reading a map where "north" means something different on every page.

| Emoji | Meaning |
|-------|---------|
| ✅ | Success — task completed successfully |
| ❌ | Hard failure — unrecoverable error |
| 🔄 | Retry — any retry attempt |
| 🧠 | AI call — LLM reasoning start |
| ⚠️ | Warning — soft failure or unusual condition |
| 🔗 | Cross-tool trace link — Langfuse reference |

### Tier 2 — Extended (Suggested Defaults — Full Developer Autonomy)

Use them, repurpose them, or invent your own. Document project-specific emojis wherever makes sense.

| Emoji | Suggested Meaning |
|-------|-------------------|
| 📱 | Incoming message / trigger |
| 📤 | Outgoing message / response |
| 🗄️ | Memory / storage read |
| 👤 | CRM / contact lookup |
| 🛠️ | Tool call / MCP call |
| 💀 | Background heartbeat / scheduled tick |

---

// LOGGING PHILOSOPHY: Log decision points and handoffs. Flag anomalies. Skip the noise. This is a guideline — nothing enforces it.

## Logging Philosophy

- **Log decision points and handoffs.** The moments where something was decided, delegated, or passed between systems. These are the clues a detective needs.
- **Flag anomalies as you go.** Set `flag='yellow'` or `flag='red'` on the log entry when something looks wrong. The Detective's Briefcase surfaces flagged entries first. An unflagged anomaly buried in 200 log lines is invisible.
- **Do not log every breath.** Repetitive steps, internal loops, variable assignments, and intermediate calculations are noise. If a human doesn't need it to understand what happened — skip the log line entirely. Do not log sparse/partial entries with missing fields — either log a complete, meaningful entry or don't log at all.
- **Nothing enforces this.** Karma will still run if you ignore this philosophy. But noisy, unflagged logs make the Detective's Briefcase harder to use, slower to read, and more likely to hide the thing you're actually looking for.

---

// FLAGS: Machine-readable severity for the Detective's Briefcase. Independent of emojis. Set when something is wrong or unusual.

## Flag Definitions

Flags are a machine-readable severity field. They power the Detective's Briefcase — when you open a debug report, flagged entries surface first. Flags are independent of emojis — emojis are for human eyes scanning log lines, flags are for the machine filtering system.

### Red — `flag='red'`

A hard failure. The agent could not complete its task. Needs attention.

Example triggers: unhandled exception, tool returned null when a value was required, message failed to send, external service unreachable.

### Yellow — `flag='yellow'`

A soft failure or unusual condition. The agent completed but something looks off. Worth a human glance.

Example triggers: retry detected, response time exceeded threshold, reasoning loop repeated more than twice, fallback path taken, unexpected input.

### Omitted / None — Normal Operation (Default)

Everything ran as expected. No flag needed. Omit the `flag` field entirely, or pass `flag=None` — both are equivalent. Logfire does not store `None` attributes, so neither produces a stored `flag` entry. Most log entries will be in this state.

**Key behavior:** `attributes->>'flag' IS NOT NULL` correctly surfaces only yellow and red entries.

---

// LOGFIRE: Pass Karma fields as keyword attributes on logfire.info() calls. Logfire stores them in the attributes JSON column, queryable via SQL.

## Logfire Integration

### How It Works

Logfire is built on OpenTelemetry and accepts structured keyword arguments on all log calls. Karma fields are passed as keyword arguments — Logfire stores them in the `attributes` JSON column of the records table.

### Passing Karma Fields

```python
import logfire

logfire.info(
    '👤 Found Customer: Anshumann',    # message with emoji prepended
    karma_code='NRD-Sale-101',          # the session Karma Code
    event='GET_CRM',                    # VERB_NOUN event name
    archetype='Continuous',             # agent archetype
                                        # flag omitted — normal operation
)
```

### What Logfire Stores

- The message string becomes the primary log entry in the Logfire timeline.
- All keyword arguments (except those set to `None`) are stored as structured JSON in the `attributes` column.
- Logfire handles the timestamp natively — do not pass a custom timestamp.

### Querying Karma Fields in Logfire

Use the SQL filter in the Logfire Live view:

- Find all entries for a session: `attributes->>'karma_code' = 'NRD-Sale-101'`
- Find all hard failures: `attributes->>'flag' = 'red'`
- Find all flagged entries: `attributes->>'flag' IS NOT NULL`
- Find all entries for an archetype: `attributes->>'archetype' = 'Pipeline'`
- Combine: `attributes->>'karma_code' = 'NRD-Sale-101' AND attributes->>'flag' IS NOT NULL`

### Using Spans for Operations

For operations that take time (AI calls, tool calls), wrap in a Logfire span:

```python
with logfire.span('🧠 AI reasoning', karma_code='NRD-Sale-101', event='START_AI', archetype='Continuous') as span:
    result = call_llm(prompt)
    if result.retried:
        span.set_attribute('flag', 'yellow')
```

### Tags for Categorization

Use Logfire tags to group related entries:

```python
logfire.info('📤 Sent response', karma_code='NRD-Sale-101', event='SEND_MSG', _tags=['sales', 'customer-facing'])
```

---

// LANGFUSE: Pass karma_code as trace metadata. This enables the Karma Infinity Loop — cross-tool correlation between Logfire and Langfuse.

## Langfuse Integration

### How It Works

Langfuse (v3 SDK) traces capture deep AI reasoning — prompts, completions, tool calls, token costs. The `karma_code` is passed as trace metadata, linking every Langfuse trace to its corresponding Logfire log entries.

### Creating a Trace with karma_code

```python
from langfuse import get_client

langfuse = get_client()

# Create a trace — karma_code goes in metadata for cross-tool correlation
with langfuse.start_as_current_observation(
    as_type="trace",
    name="narad-sales-conversation",
    metadata={"karma_code": "NRD-Sale-101"},
    tags=["sales", "continuous"]
):
    # All nested observations (spans, generations) automatically nest under this trace
    run_agent_logic()
```

### Propagating Session Context to Child LLM Calls

Use `propagate_attributes` to automatically attach session identity to all nested LLM calls made through Langfuse-integrated SDKs (e.g., `langfuse.openai`, `langfuse.anthropic`):

```python
from langfuse import get_client, propagate_attributes

langfuse = get_client()

with propagate_attributes(
    session_id="NRD-Sale-101",    # karma_code doubles as session_id — enables direct Langfuse filtering
    tags=["sales", "continuous"],
):
    # All LLM calls within this block inherit session_id automatically
    response = call_llm(prompt)
```

### The Karma Infinity Loop

With `karma_code` in Logfire (as a structured attribute) and in Langfuse (as trace metadata and/or session_id), you can navigate bi-directionally:

1. **Logfire → Langfuse:** See a log entry in Logfire → copy the `karma_code` → search Langfuse traces by `metadata.karma_code` or `session_id`.
2. **Langfuse → Logfire:** See a trace in Langfuse → copy the `karma_code` → filter Logfire with `attributes->>'karma_code' = '...'`.

This bi-directional linking is what makes Karma's cross-tool correlation work.

**Note:** Langfuse metadata values are limited to 200 characters. Karma Codes are short by design — this is never a concern.
