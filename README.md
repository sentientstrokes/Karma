# Karma ⚡ `v0.1.0-alpha`

> **Status:** Alpha — Log Standard is stable. Implementation tooling is in active development.

Karma is an observability standard for AI agent projects. It connects **Logfire** (application logs) and **Langfuse** (LLM traces) through a shared correlation key — the **Karma Code** — so you can navigate your agent's full execution story across both tools without losing the thread.

---

## What Karma Is

Karma is not a library. It is a **logging standard and a set of integration rules**.

- **Logfire** handles structured application logs — what happened, when, and whether it was flagged.
- **Langfuse** handles deep AI reasoning traces — prompts, completions, tool calls, token costs.
- **Karma** ties them together. Every log line and every trace shares the same `karma_code`. One code, one story, two tools.

Karma has **no AI layer**. It does not analyse, detect, or infer anything. It is code glue.

---

## The Karma Code

Format: `AGENT-Type-ID`

```
NRD-Sale-101        → Narad (sales agent) handling customer session #101
INA-Ingest-Run042   → Ingestion Architect running batch job #42
```

Every agent registers a shortcode. Every pipeline registers a Type. The ID is whatever uniquely identifies a session in your project's context. All three segments together form a globally unique, human-readable trace key.

---

## Core Document

| Document | Description |
|----------|-------------|
| [`docs/karma-log-standard.md`](docs/karma-log-standard.md) | **Read this first.** Defines the full log entry format, field vocabulary, Karma Code rules, Agent + Type Registry, emoji map, and Logfire/Langfuse integration patterns. |

---

## Adopting Karma in Your Project

1. Read `docs/karma-log-standard.md`
2. Register your agent shortcode and pipeline Type in the Agent + Type Registry tables
3. Follow the Logfire and Langfuse integration patterns in the same document
4. Use `karma_code` on every log line and trace — it is the primary correlation key

The registry lives in the document itself. Open a PR or edit directly to register your agent.

---

## Project Status

| Theme | Description | Status |
|-------|-------------|--------|
| Theme 1: Identity System | Karma Code, Log Standard, field definitions | ✅ Alpha complete |
| Theme 2: Inspection Tools | Detective's Briefcase, Digital Paper Trail, flags | 🔲 Planned |
| Theme 3: Health Dashboard | Vital Signs Monitor, Cost Tracker, Archetypes | 🔲 Planned |
| Theme 4: Karma Bridge | Infinity Loop, Flash Highlight, Clear Overlay | 🔲 Planned |
| Theme 5: Handbook | AI README / human onboarding doc | 🔲 Planned |

---

## Tech Stack

- **Language:** Python
- **Package manager:** `uv`
- **Application logger:** Logfire (Pydantic)
- **LLM observability:** Langfuse v3
- **LLM provider:** OpenRouter (OpenAI-compatible)
- **Testing:** pytest

---

*Karma is a personal project by [@sentientstrokes](https://github.com/sentientstrokes).*
