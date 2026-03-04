<!-- KARMA LOG STANDARD: Reference this document before writing any log entry in a Karma-compliant project. -->

# Karma Log Standard

**Version:** 2.0 | **Last Updated:** 2026-03-03

This document is the single reference for how Karma-compliant log entries are structured, what fields are defined, and how agents and pipeline types are identified across projects. The primary reader is an AI Coding Agent — every section is written for machine comprehension first, human engineer second. Start with the Recipe section below — a complete working example — then use the remaining sections as field-by-field reference.

---

<!-- RECIPE: This is what a valid Karma log entry looks like. All fields shown here are defined in the sections that follow. -->

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

### Example 2 — Pipeline Agent Log Entries (Logfire)

A Pipeline has lifecycle markers (`start`, `complete`), agent work in between, and optional SubIDs for shard-level identity.

```python
# 1. Pipeline begins — lifecycle marker, no SubID
logfire.info(
    '✅ Ingestion pipeline started',
    karma_code='Ingest-start',
    event='START_RUN',
    archetype='Pipeline',
)

# 2. Architect maps the schema — agent working (UPPERCASE marker)
logfire.info(
    '✅ Schema mapping complete for batch',
    karma_code='Ingest-INA',
    event='MAP_SCHEMA',
    archetype='Pipeline',
)

# 3. Extractor processes a shard — agent + SubID for shard identity
logfire.info(
    '⚠️ Row count mismatch in shard',
    karma_code='Ingest-INE-R01Row12',
    event='EXTRACT_ROW',
    archetype='Pipeline',
    flag='yellow'
)

# 4a. Pipeline completes normally — lifecycle marker
logfire.info(
    '✅ Ingestion pipeline complete',
    karma_code='Ingest-complete',
    event='COMPLETE_RUN',
    archetype='Pipeline',
)

# 4b. OR pipeline crashes — abort lifecycle marker (instead of complete)
logfire.info(
    '❌ Ingestion pipeline aborted: schema validation failed',
    karma_code='Ingest-abort',
    event='ABORT_RUN',
    archetype='Pipeline',
    flag='red'
)
```

**Key observations:**
- `start` and `complete` are lowercase (lifecycle markers, not agents)
- `INA` and `INE` are UPPERCASE (registered agent shortcodes)
- SubID (`R01Row12`) appears only when shard-level identity matters
- Full Pipeline flows with worked examples are in the Karma Code Format section

**What Logfire stores (for the Extractor entry):**

```json
{
  "karma_code": "Ingest-INE-R01Row12",
  "event": "EXTRACT_ROW",
  "archetype": "Pipeline",
  "flag": "yellow"
}
```

**Querying in Logfire:** Use SQL on the `attributes` column:

- `attributes->>'karma_code' = 'NRD-Sale-101'` — find all log entries for a session.
- `attributes->>'flag' = 'red'` — surface all hard failures.
- `attributes->>'flag' IS NOT NULL` — surface all flagged entries (yellow and red).

---

<!-- REGISTRY: Check both tables before starting. Register your Agent shortcode and your pipeline Type. Sub-agents use the calling pipeline's Type. -->

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
- If two words are unavoidable, use CamelCase with no spaces: `DataSync`, `BatchIngest`. This keeps the hyphen-delimited Karma Code parseable: `DataSync-start` (Pipeline) or `NRD-DataSync-101` (Continuous).
- Globally unique. A Type registered as `Sale` means the same sales pipeline concept everywhere. Different projects may share a Type — but it must reference the same pipeline concept.
- `Connect` is **reserved** for agent-to-agent handoffs. Never register it as a regular Type. See Karma Code Format section.

Sub-agents inherit the calling pipeline's Type — they do not register their own.

---

<!-- ARCHETYPES: Pick one per agent. Archetypes are strict — not blendable. A project can run agents of different archetypes. -->

## Archetype Definitions

Every agent is one of two archetypes. Pick one. They are not blendable within a single agent — but a project can absolutely run both (e.g., a Continuous sales agent AND a Pipeline batch sync in the same system).

### Pipeline

An automation sequence, batch job, or one-time script. It starts, does its job, and ends.

- **Examples:** A data ingestion job, a scheduled report generator, a one-off CRM sync, an ETL pipeline, a Gmail automation triggered by incoming mail.
- **Typically tracks:** Completion status, accuracy, duration, error count.
- **SubID is typically:** A Job ID, Run ID, Batch number, or entity identifier — or omitted entirely for stateless one-off jobs.
- **Type naming hint:** Name it after the job. E.g., `Ingest`, `Sync`, `Report`, `Mail`.
- **Karma Code format:** `Type-marker(-SubID)?` — Type leads because the pipeline IS the identity. See Karma Code Format section.
- **Karma Code examples:** `Ingest-INA` (Ingestion Architect working), `Ingest-start` (lifecycle marker), `Ingest-INE-R01Row12` (Extractor on shard Row12 of run R01), `Mail-trigger-1234nas5` (mail pipeline triggered by customer 1234nas5).

### Continuous

A long-running or streaming agent driven by ongoing AI interactions. It persists across multiple exchanges and sessions.

- **Examples:** A sales agent handling customer conversations, a graphic design assistant, a support bot, a creative writing agent.
- **Typically tracks:** Session count, interaction health, last active, response quality signals.
- **Session ID is typically:** A Customer ID, Conversation ID, or Project ID.
- **Type naming hint:** Name it after the domain. E.g., `Sale`, `Design`, `Support`.
- **Karma Code example:** `NRD-Sale-101` — Narad handling customer #101.

Metrics listed above are illustrative starting points. The project defines what "healthy" means for its specific agent.

---

<!-- KARMA CODE: Two formats exist — one per archetype. Continuous uses Agent-Type-SessionID (agent leads). Pipeline uses Type-marker(-SubID)? (pipeline leads). Connect is reserved for handoffs and is the only 4-segment pattern. -->

## Karma Code Format

Pipeline and Continuous archetypes use **different** karma code formats with **different** segment orders. This is by design — the leading segment always reflects the primary identity of the system.

**Foundational principle:** A karma code identifies WHERE in a system you are — not what happened there. Whether a log entry represents success, failure, retry, or any other outcome is handled by `flag`, `event`, and `emoji`. The karma code never encodes status or failure mode. It is the identifier of a log entry — the rest of the Karma fields (defined in later sections) handle everything else.

---

### Continuous Format: `Agent-Type-SessionID`

Agent leads because the agent IS the identity. When you say "Narad handled that call," Narad is the subject.

#### Segment Breakdown

- `Agent` — 2–3 character shortcode registered in the Agent Registry. Identifies who is acting. Always uppercase.
- `Type` — Pipeline context registered in the Type Registry. Identifies what pipeline is running. Always Title Case.
- `SessionID` — The session identifier. Project-defined — whatever uniquely identifies a session in that project's context (Customer ID, Conversation ID, etc.). **Must not contain hyphens** — hyphens are reserved as segment delimiters. Alphanumeric and underscores are safe.

#### Naming Rules

- **Agent:** Uppercase, 2–3 alphanumeric characters, registered before use.
- **Type:** Title Case, single word preferred (CamelCase if two words), globally unique, registered before use.
- **SessionID:** Project-defined, meaningful to the domain. No hyphens. E.g., `101`, `C101`, `51a9`, `job_99`.

#### Example

Narad handling customer 51a9: `NRD-Sale-51a9`

#### Sub-Agent Inheritance

Sub-agents inherit the parent's format and Type, replacing only the agent shortcode. They do NOT create a new pipeline or register a new Type. This rule applies identically to both archetypes.

**Continuous example:**
- Primary sales agent Narad starts: `NRD-Sale-51a9`
- Narad calls global Research sub-agent: `RSC-Sale-51a9` (same Type, same session)
- Research calls Review sub-agent: `RVW-Sale-51a9` (still same pipeline)

All three agents can be queried together with a single Logfire filter: `attributes->>'karma_code' LIKE '%-Sale-51a9'`.

---

### Pipeline Format: `Type-marker(-SubID)?`

Type leads because the pipeline IS the identity. Agents are workers within it — interchangeable parts of a larger process. When you say "the Ingestion pipeline ran," the pipeline is the subject, not which agent was processing at a given moment.

#### Segment Breakdown

- `Type` — Pipeline name registered in the Type Registry. Always Title Case. E.g., `Ingest`, `Mail`, `Sync`.
- `marker` — Identifies what is happening at this point in the pipeline. **Case distinguishes its role:**
  - **UPPERCASE (2–3 chars)** = registered agent shortcode. The agent is doing work. E.g., `INA`, `INE`, `DSG`.
  - **lowercase** = lifecycle marker or pipeline-specific function. Not an agent — this is a pipeline-level event or a project-specific function. E.g., `start`, `complete`, `trigger`, `reply`.
  - **`Connect` (Title Case)** = handoff to/from another system. Reserved. See Handoffs section below.
- `SubID` — Optional. A run/shard/session identifier within the pipeline. Project-defined. **Must not contain hyphens.** Alphanumeric and underscores are safe.

#### Case Disambiguation Rule

This is the critical parsing rule for Pipeline karma codes. The second segment's case tells you exactly what it is:

| Case | Meaning | Example | Interpretation |
|------|---------|---------|----------------|
| UPPERCASE | Agent shortcode | `Ingest-INA` | Ingestion Architect is working |
| lowercase | Lifecycle/function marker | `Ingest-start` | Pipeline lifecycle event |
| Title Case | Reserved: `Connect` only | `Mail-Connect-NRD-1234nas5` | Handoff to agent NRD |

A machine parser checks the case of the second segment. Uppercase = agent. Lowercase = lifecycle/function. Title Case = Connect. No reserved word list is needed — the case convention alone is sufficient.

#### SubID Rules

- SubID is **optional**. Stateless one-off pipelines (or pipeline-level lifecycle markers) omit it: `Ingest-start`, `Ingest-complete`, `Ingest-abort`.
- When present, SubID scopes the karma code to a specific run, shard, or entity: `Ingest-INE-R01Row12`.
- **Collision handling:** If concurrent runs of the same pipeline can exist, the developer must encode a run identifier WITHIN the SubID. The Karma format does not enforce how — the developer defines the SubID structure for their project. Examples:
  - `R01Row12` — encodes run `R01` and shard `Row12` in a single SubID
  - `20260303R01Row12` — date-scoped run identifier with shard
  - `R01` — just a run number, no shard
  - These are illustrative reference patterns. Your project may use a completely different convention as long as the SubID contains no hyphens.
- Same rules as Continuous SessionID: no hyphens, alphanumeric and underscores safe.

#### Sub-Agent Inheritance

Sub-agents inherit the parent's Pipeline format and Type, replacing only the agent shortcode. The same principle as Continuous — the archetype format stays consistent from parent to child.

**Pipeline example:**
- Ingestion Extractor processes a shard: `Ingest-INE-R01Row12`
- Extractor calls a Cleaner sub-agent: `Ingest-CLN-R01Row12` (same Type, same SubID)
- Cleaner calls a Validator sub-agent: `Ingest-VLD-R01Row12` (still same pipeline)

All three agents can be queried together: `attributes->>'karma_code' LIKE 'Ingest-%-R01Row12'`.

---

#### Worked Example 1 — Ingestion Pipeline (Linear/Batch)

A document ingestion pipeline into a Neo4j knowledge graph. Four registered agents: INA (Ingestion Architect), INC (Ingestion Cartographer), INE (Ingestion Extractor), INB (Ingestion Builder).

```
Ingest-start                → Pipeline begins (lifecycle marker, no SubID — one start per run)
Ingest-INA                  → Ingestion Architect plans the schema
Ingest-INC                  → Ingestion Cartographer maps the graph structure
Ingest-INE-R01Row12         → Extractor processes shard Row12 of run R01
Ingest-INE-R01Row13         → Extractor processes shard Row13 of run R01 (async, parallel)
Ingest-INB-R01Row12         → Builder writes shard Row12 to Neo4j
Ingest-INB-R01Row13         → Builder writes shard Row13 to Neo4j
Ingest-complete             → Pipeline ends successfully (lifecycle marker)
Ingest-abort                → OR: Pipeline terminates early due to failure (lifecycle marker)
```

**Key observations:**
- No natural session ID at the top level — this is a stateless batch job.
- SubID appears only at Extractor/Builder level where shard-level identity matters.
- `start`, `complete`, and `abort` are lowercase (lifecycle markers, not agents).
- `INA`, `INC`, `INE`, `INB` are UPPERCASE (registered agent shortcodes).
- Run identifier `R01` is encoded in SubID to prevent collision if concurrent runs exist.
- Querying all Extractor work across shards: `attributes->>'karma_code' LIKE 'Ingest-INE-%'`.
- Querying a specific shard across agents: `attributes->>'karma_code' LIKE 'Ingest-%-R01Row12'`.

---

#### Worked Example 2 — Mail Automation Pipeline (Event-Driven)

A Gmail automation triggered by incoming mail. The customer ID `1234nas5` is the natural session identifier.

```
Mail-trigger-1234nas5       → Incoming mail triggers pipeline (lifecycle marker)
Mail-Connect-NRD-1234nas5   → Pipeline hands off to Narad sales agent (Connect handoff)
NRD-Sale-1234nas5           → Narad runs sales conversation (Continuous format — agent leads)
NRD-Sale-1234nas5           → Narad looks up customer in CRM (event='GET_CRM')
NRD-Connect-Mail-1234nas5   → Narad hands back to Mail pipeline (Connect handoff)
Mail-Connect-DSG-1234nas5   → Pipeline hands off to Design agent
DSG-Design-1234nas5         → Design agent creates HTML email reply (Continuous format)
DSG-Connect-Mail-1234nas5   → Design hands back to Mail pipeline
Mail-reply-1234nas5         → Pipeline sends final reply (pipeline-specific function)
```

**Key observations:**
- Natural session ID (`1234nas5`) persists throughout the entire chain.
- **The chain crosses between Pipeline format and Continuous format.** `Mail-trigger-1234nas5` is Pipeline format (Type leads). `NRD-Sale-1234nas5` is Continuous format (Agent leads). This is allowed and expected when a Pipeline orchestrates Continuous agents.
- `trigger` and `reply` are lowercase — pipeline-specific functions, not agent shortcodes. `reply` is not a global lifecycle keyword — it is specific to the Mail pipeline. Any pipeline can define its own lowercase markers.
- Connect entries follow the 4-segment pattern (see Handoffs section).
- Querying the full session: `attributes->>'karma_code' LIKE '%-1234nas5'`.

---

### Agent-to-Agent Handoffs — The `Connect` Type

When control transfers between primary agents, or between a pipeline and an agent, use the reserved `Connect` type. Connect codes are always 4 segments. They create a visible bridge in the logs showing exactly where control transferred.

**Format:** `SOURCE-Connect-TARGET-ID`

Where SOURCE and TARGET can be either an agent shortcode (UPPERCASE) or a pipeline Type (Title Case).

#### Continuous-to-Continuous Handoff

A primary agent hands control to another primary agent:

```
NRD-Sale-51a9            → Narad starts sales session for customer 51a9
NRD-Connect-DSG-51a9     → Narad hands off to Design agent (4-segment Connect code)
DSG-Design-51a9          → Design agent takes over in its own pipeline
RSC-Design-51a9          → Research sub-agent called within Design (inherits Type + SessionID)
DSG-Design-51a9          → Design completes
DSG-Connect-NRD-51a9     → Design hands back to Narad (4-segment Connect code)
NRD-Sale-51a9            → Narad resumes
RVW-Sale-51a9            → Review sub-agent called within Sales
NRD-Sale-51a9            → Narad completes
```

#### Pipeline-to-Agent Handoff

A pipeline can hand off to an agent, and the agent can hand back. The pipeline Type occupies the source/target slot the same way an agent shortcode would:

```
Mail-Connect-NRD-1234nas5   → Mail pipeline hands off to Narad
NRD-Sale-1234nas5           → Narad works (Continuous format — agent leads)
NRD-Connect-Mail-1234nas5   → Narad hands back to Mail pipeline
```

The 4-segment pattern is consistent regardless of whether the participants are agents or pipelines.

The session ID persists across the entire chain. The Connect entries show the exact handoff points. The full story is readable from the log alone.

---

### Karma Code vs Event Field

The karma code and the `event` field serve different query axes. They may overlap at lifecycle boundaries — this is expected and correct.

| Axis | Field | Question it answers | Example |
|------|-------|---------------------|---------|
| Position | `karma_code` | "Where in the system am I?" | `Ingest-INE-R01Row12` |
| Action | `event` | "What happened here?" | `EXTRACT_ROW` |

A lifecycle marker like `Ingest-start` with `event='START_RUN'` has overlap — the karma code says "pipeline start position" and the event says "a run started." Both are correct and intentional. They serve different filtering patterns:

- Filter by karma code to see a single pipeline's full trace: `attributes->>'karma_code' LIKE 'Ingest-%'`.
- Filter by event to see all `START_RUN` events across all pipelines: `attributes->>'event' = 'START_RUN'`.

---

<!-- FIELDS: These 6 fields are the Karma vocabulary. Their meanings are locked. Use them when applicable — omit when not needed. Never repurpose them. -->

## Defined Fields

These 6 fields are Karma's vocabulary. Their meanings are fixed — when you use one, it must follow the rules below. Not every log line needs every field. A simple status log might only have `karma_code`, `event`, and `flag`. A detailed trace entry might use all 6. The rule is: if you use the word, use it correctly.

**The consequence of ignoring this:** Nothing explodes. Karma will still run. But inconsistent field usage degrades readability, breaks Logfire queries (filters return partial results), and makes the Detective's Briefcase unreliable. The debugging experience shifts from methodical investigation to guesswork.

| Field | Description |
|-------|-------------|
| `message` | The primary Logfire message string. Brief, plain English, present tense. ~100 characters recommended. Prepend the emoji for human scanning. E.g., `'👤 Found Customer: Anshumann'`, `'❌ Tool call failed: CRM unreachable'`. |
| `karma_code` | The session's full Karma Code. Format depends on archetype: `Agent-Type-SessionID` (Continuous) or `Type-marker(-SubID)?` (Pipeline). See Karma Code Format section. Always include this on every log line — it is the primary correlation key. |
| `event` | VERB_NOUN identifier in SCREAMING_SNAKE_CASE. See Event Naming section. E.g., `GET_CRM`, `COMPLETE_BATCH`, `SEND_MSG`. |
| `archetype` | `"Pipeline"` or `"Continuous"`. Matches the Archetype chosen at project setup. |
| `flag` | Omit or pass `None` for normal operation (not stored). `"yellow"` for soft failure. `"red"` for hard failure. Powers the Detective's Briefcase severity filter. Independent of the emoji used. |
| `extra` | A catch-all for additional structured data specific to this log entry. Pass as a dict. No schema enforced — project-defined. |

`karma_code` is the one field that should appear on every single Karma log line. It is the thread that ties everything together across Logfire and Langfuse.

### Example — Using `extra` for structured data

```python
logfire.info(
    '🛠️ Tool call returned null: CRM unreachable',
    karma_code='NRD-Sale-101',
    event='CALL_TOOL',
    archetype='Continuous',
    flag='red',
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
    '✅ Pipeline complete',
    karma_code='Ingest-complete',
    event='COMPLETE_RUN',
    archetype='Pipeline',
)
```

Not every log line needs all 6 fields. When a field is omitted, it simply isn't stored. The rule: if you include a field, follow its definition.

---

<!-- EVENT NAMES: VERB_NOUN in SCREAMING_SNAKE_CASE. Max 3 segments. Document new names in your project. This standard will evolve. -->

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

`GET_CRM`, `LOAD_MEM`, `SEND_MSG`, `RECEIVE_MSG`, `START_AI`, `CALL_TOOL`, `LOG_THINKING`

`LOG_THINKING` is a reserved event name for AI calls where extended thinking (chain-of-thought) is enabled. See the Chain of Thought — Extended Thinking Mandate section in Langfuse Integration.

### Example 2 — Pipeline Batch Agent Events

`START_BATCH`, `FETCH_DATA`, `PROCESS_RECORD`, `COMPLETE_BATCH`, `FAIL_BATCH`

---

<!-- EMOJI MAP: Tier 1 meanings are globally locked. Tier 2 is yours to define. Emojis are for human visual scanning — they are independent of the flag field. -->

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

<!-- LOGGING PHILOSOPHY: Log decision points and handoffs. Flag anomalies. Skip the noise. This is a guideline — nothing enforces it. -->

## Logging Philosophy

- **Log decision points and handoffs.** The moments where something was decided, delegated, or passed between systems. These are the clues a detective needs.
- **Flag anomalies as you go.** Set `flag='yellow'` or `flag='red'` on the log entry when something looks wrong. The Detective's Briefcase surfaces flagged entries first. An unflagged anomaly buried in 200 log lines is invisible.
- **Do not log every breath.** Repetitive steps, internal loops, variable assignments, and intermediate calculations are noise. If a human doesn't need it to understand what happened — skip the log line entirely. Do not log sparse/partial entries with missing fields — either log a complete, meaningful entry or don't log at all.
- **Nothing enforces this.** Karma will still run if you ignore this philosophy. But noisy, unflagged logs make the Detective's Briefcase harder to use, slower to read, and more likely to hide the thing you're actually looking for.

---

<!-- FLAGS: Machine-readable severity for the Detective's Briefcase. Independent of emojis. Set when something is wrong or unusual. -->

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

<!-- LOGFIRE: Pass Karma fields as keyword attributes on logfire.info() calls. Logfire stores them in the attributes JSON column, queryable via SQL. -->

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

### Reading Karma Data Back (Programmatic Query)

The write path above covers instrumentation. Karma tooling (Briefcase, Health Dashboard) reads data back using `LogfireQueryClient` — a separate read client with its own credential.

```python
import os
from logfire.query_client import LogfireQueryClient

# Requires LOGFIRE_READ_TOKEN — a read-only token separate from the write token.
# Generate from Logfire web UI → Settings → Read Tokens.
with LogfireQueryClient(read_token=os.getenv('LOGFIRE_READ_TOKEN')) as client:
    result = client.query_json_rows(
        sql="""
            SELECT start_timestamp, message,
                   attributes->>'event' AS event,
                   attributes->>'flag' AS flag,
                   attributes->>'karma_code' AS karma_code,
                   attributes->>'archetype' AS archetype
            FROM records
            WHERE attributes->>'karma_code' = 'NRD-Sale-101'
              AND attributes->>'flag' IS NOT NULL
            ORDER BY start_timestamp ASC
        """,
        min_timestamp=since_datetime,  # datetime or None
        max_timestamp=until_datetime,  # datetime or None
    )
    rows = result['rows']  # list of dicts
```

**Credentials:** `LOGFIRE_READ_TOKEN` must be present in your `.env` file. It is distinct from the write token (`LOGFIRE_TOKEN`) used for `logfire.info()` calls.

---

<!-- LANGFUSE: Pass karma_code as trace metadata. This enables the Karma Infinity Loop — cross-tool correlation between Logfire and Langfuse. -->

## Langfuse Integration

### How It Works

Langfuse (v3 SDK) traces capture deep AI reasoning — prompts, completions, tool calls, token costs. The `karma_code` is passed as trace metadata, linking every Langfuse trace to its corresponding Logfire log entries.

### Creating a Trace with karma_code

```python
from langfuse import get_client

langfuse = get_client()

# Create a trace — use karma_code as the span name for cross-tool correlation
with langfuse.start_as_current_span(
    name="NRD-Sale-101",
    metadata={"karma_code": "NRD-Sale-101"},
    tags=["sales", "continuous"]
):
    # All nested observations (spans, generations) automatically nest under this trace
    # Use langfuse.get_trace_url() inside this block to get the clickable Langfuse URL
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

### Chain of Thought — Extended Thinking Mandate

When the model supports extended thinking (e.g., Claude with `thinking={"type": "enabled", "budget_tokens": N}`), the full response — including thinking blocks — **must** be passed through to Langfuse. Stripping `<thinking>` content before logging reduces the trace to inputs and final answers. The reasoning chain is lost. The Briefcase can no longer answer "why."

This is a hard requirement, not a suggestion. Karma's primary value for debugging AI decisions is inspectability. Extended thinking is the highest-fidelity signal of AI reasoning available — discarding it defeats the purpose of the entire system.

**Compliance by integration path:**

| Path | Required action |
|------|-----------------|
| `langfuse.anthropic` wrapper | None — the wrapper captures the full response including thinking blocks automatically |
| Direct API call + manual Langfuse logging | Include the complete `content` array (thinking blocks + text blocks) in the observation output. Do not filter to text-only. |

**Logfire signal:** Use `event='LOG_THINKING'` on any Logfire span covering an AI call where extended thinking was enabled. This makes CoT-active calls queryable in Logfire independently of Langfuse:

```python
logfire.info(
    '🧠 Extended thinking active',
    karma_code='NRD-Sale-101',
    event='LOG_THINKING',
    archetype='Continuous',
)
```

The thinking content itself lives in Langfuse. The Logfire entry signals its presence and makes it findable via `attributes->>'event' = 'LOG_THINKING'`.

---

### Reading Karma Data Back (Programmatic Query)

The write path above covers instrumentation. Karma tooling (Briefcase, Health Dashboard) reads Langfuse data back using `FernLangfuse` — a low-level client separate from `get_client()` used for instrumentation. Both can coexist in the same script.

```python
import os
from langfuse.client import FernLangfuse

# username = public_key, password = secret_key (HTTP Basic Auth convention)
client = FernLangfuse(
    x_langfuse_public_key=os.getenv('LANGFUSE_PUBLIC_KEY'),
    username=os.getenv('LANGFUSE_PUBLIC_KEY'),
    password=os.getenv('LANGFUSE_SECRET_KEY'),
    base_url=os.getenv('LANGFUSE_HOST', 'http://localhost:3000'),
)

# Fetch trace summaries for a session (karma_code = session_id)
traces = client.trace.list(
    session_id='NRD-Sale-101',
    fields='core,scores,metrics',
)
# traces.data = list of trace objects with .latency, .total_tokens, .total_cost, .name

# Fetch errored observations (generation-level failures)
error_obs = client.observations.list(
    session_id='NRD-Sale-101',
    level='ERROR',
    fields='core,basic,io',
)
# error_obs.data = list of observation objects with .name, .type, .input, .output, .status_message
```

**Credentials:** `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_HOST` must be present in your `.env` file.

### The Karma Infinity Loop

With `karma_code` in Logfire (as a structured attribute) and in Langfuse (as trace metadata and/or session_id), you can navigate bi-directionally:

1. **Logfire → Langfuse:** See a log entry in Logfire → copy the `karma_code` → search Langfuse traces by `metadata.karma_code` or `session_id`.
2. **Langfuse → Logfire:** See a trace in Langfuse → copy the `karma_code` → filter Logfire with `attributes->>'karma_code' = '...'`.

This bi-directional linking is what makes Karma's cross-tool correlation work.

**Note:** Langfuse metadata values are limited to 200 characters. Karma Codes are short by design — this is never a concern.

---

<!-- KARMA INFINITY LOOP: Embed the Langfuse trace URL and trace ID into Logfire at pipeline start. Two mandatory fields. Strict sequence required. -->

## Langfuse Trace URL — Karma Infinity Loop Fields

These two fields close the Karma Infinity Loop. They give any reader of a Logfire log — human or developer AI — a direct one-hop path into the matching Langfuse trace. No manual searching. No copy-paste. One attribute, one click, full AI trace.

### The Two Fields

| Field | Type | Where set | Description |
|-------|------|-----------|-------------|
| `langfuse_trace_url` | `str` | First Logfire span of any pipeline run | Full URL to the Langfuse trace UI. Format: `http://localhost:3000/project/{id}/traces/{trace_id}`. Clickable in terminal (Cmd+click) and rendered as a hyperlink in the Briefcase report. |
| `langfuse_trace_id` | `str` | First Logfire span of any pipeline run | Raw Langfuse trace ID (no host or path). Enables a developer AI to call `langfuse.api.trace.get(trace_id)` and read all observations as structured data — without URL parsing. This is the most powerful field for automated debugging workflows. |

**These fields are mandatory for all Pipeline-archetype runs.** Continuous agents that have a matching Langfuse trace should also emit them. If a run has no Langfuse trace (e.g. a non-LLM utility script), omit both fields — do not pass `None` explicitly.

---

### Recipe — Complete Pattern (Script Entry Point)

**Read this before writing any pipeline entry point. Shows the full async + flush pattern required by project-context.md.**

```python
import asyncio
import logfire
from langfuse import get_client, propagate_attributes

langfuse = get_client()

async def run_pipeline(karma_code: str):
    # Step 1: Open the Langfuse trace container FIRST
    with langfuse.start_as_current_span(name=karma_code) as lf_span:

        # Step 2: Get trace URL and ID immediately — must be INSIDE the active span.
        # Returns None if called before start_as_current_span() opens.
        langfuse_trace_url = langfuse.get_trace_url()
        langfuse_trace_id  = langfuse.get_current_trace_id()

        # Step 2a: Handle the None case — log yellow and continue without URL
        if langfuse_trace_url is None:
            logfire.info(
                '⚠️ Langfuse trace URL unavailable — Infinity Loop broken for this run',
                karma_code=karma_code,
                event='SKIP_TRACE_URL',   # VERB_NOUN: SKIP = action, TRACE_URL = target
                archetype='Pipeline',
                flag='yellow',
            )
            # langfuse_trace_url and langfuse_trace_id remain None.
            # Logfire omits None attributes. Briefcase will omit the link gracefully.

        # Step 3: Propagate session context to all nested LLM observations
        with propagate_attributes(
            session_id=karma_code,                       # karma_code = session_id in Langfuse
            metadata={"karma_code": karma_code},         # cross-tool correlation key
        ):
            # Step 4: Open the root Logfire span — embed both trace fields here
            with logfire.span(
                '🔗 Pipeline start: {karma_code}',
                karma_code=karma_code,
                event='START_PIPELINE',
                archetype='Pipeline',
                langfuse_trace_url=langfuse_trace_url,   # None is omitted by Logfire automatically
                langfuse_trace_id=langfuse_trace_id,     # None is omitted by Logfire automatically
            ):
                # Step 5: Print to terminal — Cmd+clickable in VS Code / iTerm2
                if langfuse_trace_url:
                    print(f"[KARMA] 🔗 Langfuse trace: {langfuse_trace_url}")

                # Step 6: All pipeline work happens here inside both contexts
                await run_agent_logic(karma_code)

# Entry point — asyncio.run() and langfuse.flush() are MANDATORY at this level.
# flush() must be called after asyncio.run() completes — not inside the async context.
if __name__ == "__main__":
    # Replace with your actual karma_code source (e.g. sys.argv[1] or argparse)
    my_karma_code = "NRD-Sale-101"
    asyncio.run(run_pipeline(my_karma_code))
    langfuse.flush()   # Langfuse batches events — flush ensures none are lost on exit
```

**Sequence is strict. Do not reorder steps 1–4.** If `get_trace_url()` is called before `start_as_current_span()` opens, it returns `None`.

---

### What Each Access Point Gives You

| Who uses it | How | What they get |
|-------------|-----|---------------|
| Human developer | Cmd+click the terminal URL | Full Langfuse trace UI — every nested AI call, prompt, output, cost |
| Human developer | Click the link in the Briefcase report | Same trace UI, from the packaged case file |
| Developer AI (debugging) | Read `langfuse_trace_id` from Briefcase header → call `langfuse.api.trace.get(trace_id)` | All observations as structured data — inputs, outputs, tokens, cost, errors — no UI needed |

The URL is for humans. The `trace_id` is for machines. Both are stored in the same Logfire span and surfaced in the Briefcase.

---

### Emoji Convention

Use the `🔗` emoji on the Logfire span that carries `langfuse_trace_url`. This emoji is Tier 1 locked to "Cross-tool trace link — Langfuse reference" — see the Emoji Shorthand Map section.

```python
logfire.span('🔗 Pipeline start: {karma_code}', karma_code=karma_code, ..., langfuse_trace_url=url)
```

---

### Querying the Trace Fields in Logfire SQL

```sql
-- Retrieve both Langfuse fields for a given karma_code (returns the root span's values)
SELECT attributes->>'langfuse_trace_url' AS langfuse_trace_url,
       attributes->>'langfuse_trace_id'  AS langfuse_trace_id,
       start_timestamp
FROM records
WHERE attributes->>'karma_code' = 'NRD-Sale-101'
  AND attributes->>'langfuse_trace_url' IS NOT NULL
ORDER BY start_timestamp ASC
LIMIT 1
```

This query is used by the Briefcase Reporter (karma/briefcase.py) to populate both fields in the Briefcase header.
