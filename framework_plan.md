# Multi-Agent Inquiry Framework: Development Plan

## Context

The first experiment proved the core thesis: multi-agent LLM orchestration with separate contexts, citation verification, and structured rounds produces genuine cross-disciplinary findings that no single agent could generate. The system ran 6 advocates through 4 rounds, verified 114 citations (1.75% fabrication rate, both caught), and produced 5 cross-disciplinary findings meeting the 3-discipline threshold.

**What works and must be preserved:**
- Separate agents with isolated contexts (not personas in one prompt) - this is the heart of the system
- Well-crafted system prompts that create genuine disciplinary identity and controlled context windows
- Citation protocol with 3-pass verification loop, presented transparently to users
- Round-based structure with context accumulation and compression
- Moderator as synthesizer, not adjudicator
- Full audit trail

**What needs to change:**
- Everything was hardcoded for one theology topic (73KB system_prompts.json)
- No way for users to set up their own inquiries
- No interactive features (watch, explore, follow up)
- Only supported debate format; need panel/Q&A format too
- Python-only; user is most comfortable in JS/Next.js

**Target users:** Small group of friends exploring topics together. Needs a real web UI but can be rough around the edges.

**Stack decision:** Next.js app + Python engine running as a service. The Python orchestration code works and is complex enough that rewriting it would be a waste. Next.js handles the UI, planning agent, and user interaction. Python handles the actual inquiry execution. Communicate via HTTP. Deploy as Docker Compose (two containers) on Fly.io, Railway, or any VPS — no vendor lock-in.

**Storage decision: Hybrid filesystem + Supabase/Postgres.**
- **Filesystem** for inquiry outputs (markdown files, canonical record) — these are documents meant to be read, and the engine already writes them this way
- **Supabase (Postgres)** for structured data: inquiry configs, run status, verification verdicts, citation data, planning agent conversation history, post-inquiry chat history
- Why hybrid: verification data especially benefits from a DB — you can query across inquiries ("this source has been flagged in 3 debates"), track citation integrity trends, and power the verification UI. Conversation history needs persistence beyond the filesystem. Supabase free tier is $0, Postgres is portable if you leave.

---

## Core Design Principles

These are non-negotiable across all phases:

1. **Agent isolation over persona simulation.** Each participant is a separate API call with its own system prompt, context window, and temperature. Never collapse multiple perspectives into one prompt.

2. **System prompts are first-class artifacts.** The quality of the inquiry depends on well-crafted system prompts that create genuine disciplinary identity, not generic "act as an expert in X." The planning agent must generate prompts with: disciplinary methodology, epistemic boundaries (what this discipline can and cannot establish), citation expectations, and interaction style.

3. **Context is controlled and intentional.** Each agent sees only what it should: its own full history, compressed summaries of others, the shared question, and any grounding documents. No agent sees another's system prompt. Context compression kicks in for later rounds.

4. **Verification is visible, not hidden.** The 3-pass citation verification pipeline is a key differentiator. Users should see it working and be able to drill into any claim's verification trail. This builds trust in the output.

5. **The moderator synthesizes, never adjudicates.** No "winner." The moderator identifies convergence, divergence, and irreducible tensions. Participants maintain their disciplinary positions.

---

## Phase 1: Generalize the Engine ✅ Complete

**Goal:** The Python engine accepts a JSON config and runs any inquiry, not just the theology debate.

**Delivered:**
- `scripts/inquiry_schema.py` — Pydantic config schema. Defines `InquiryConfig`, `Participant`, `RoundConfig`, etc. Validates any config the planning agent generates.
- `scripts/engine.py` — Config-driven orchestrator. Generic `run_round()` dispatches on 4 round types: `parallel_statements`, `paired_exchange`, `moderator_synthesis`, `panel_qa`. Full citation pipeline, verification, moderation, digests.
- `scripts/server.py` — FastAPI HTTP API with SSE progress events. Endpoints for creating, listing, monitoring inquiries and serving outputs.
- `scripts/migrate_config.py` — Converts legacy `system_prompts.json` to new format.
- `configs/theology_debate.json` — Migrated theology debate config (validated).
- `configs/ai_regulation_debate.json` — Second topic: 4 participants (Technologist, Legal Scholar, Economist, Ethicist), 4 rounds. Validates generalization.
- `conductor.py` updated — `--config path` flag routes to engine; legacy mode preserved.
- `citation_extractor.py` — Dynamic abbreviation generation (legacy IDs preserved for backward compat).
- `document_compiler.py`, `context_packager.py` — Config-driven; handle both new and legacy configs.

**Round types (finite set):**
- `parallel_statements` — each participant speaks independently
- `paired_exchange` — directed question + response pairs
- `moderator_synthesis` — moderator synthesizes, participants respond
- `panel_qa` — user poses question, participants respond (interactive)

**CLI usage:**
```bash
# New config-driven mode
python scripts/conductor.py --config configs/ai_regulation_debate.json --all
python scripts/conductor.py --config configs/ai_regulation_debate.json --round round_1 --dry-run
python scripts/conductor.py --config configs/ai_regulation_debate.json --round round_1 --participant economist

# Legacy mode still works
python scripts/conductor.py --round 1 --advocate biblical_scholar

# HTTP API
python scripts/server.py --port 8000
```

---

## Phase 2: Next.js Web App + Planning Agent

**Goal:** Users enter a question in a browser, plan the inquiry conversationally, run it, and browse results.

### 2A. Next.js project setup

**Key directory:** new `web/` directory

- Next.js App Router
- Tailwind for styling (fast, no design system needed)
- Supabase client for structured data (inquiry metadata, verification results, chat history)
- Calls Python engine via HTTP (localhost in dev, internal network in Docker)

### 2B. Planning agent (the core UX)

A chat interface backed by Claude API calls (using `@anthropic-ai/sdk` from Next.js API routes). Not a complex agent framework — just a well-prompted multi-turn conversation that stays focused on building the inquiry.

**The planning agent's conversation flow:**

1. User enters a question + optional grounding document
2. Agent asks 1-2 clarifying questions to understand intent
3. **Agent presents 2-3 high-level approaches in plain language:**
   - e.g., "Structured Debate (5 advocates, 4 rounds with cross-examination) — best for surfacing deep disagreements"
   - e.g., "Expert Panel (3 experts you can question directly) — best for exploring a topic you have specific questions about"
   - e.g., "Advisory Council (4 experts building a shared recommendation) — best for actionable output"
4. User picks a direction (or asks to mix/adjust)
5. Agent builds out the details collaboratively: suggests specific participants with disciplines relevant to the topic, proposes round structure, refines the central question
6. User approves, agent generates the full config JSON
7. Config is validated against schema, inquiry is created

**Critical planning agent behaviors:**
- Always suggest multiple approaches, never jump straight to building one
- Willing to engage in back-and-forth to refine, but doesn't get sidetracked into debating the topic itself
- Generates high-quality system prompts for each participant (disciplinary methodology, epistemic boundaries, citation expectations) — this is where the quality of the whole inquiry is determined
- Explains trade-offs: more participants = richer but slower/costlier; more rounds = deeper but longer

**Planning agent conversation history:** stored in Supabase so users can return to an inquiry and see how it was set up.

### 2C. Pages

1. **Home** — text input for question, file upload for optional grounding doc, "Start Planning" button
2. **Planning Chat** — chat with planning agent, sidebar shows emerging config preview (participants, rounds, format)
3. **Inquiry Dashboard** — progress view while running (SSE from Python engine). Outputs appear as rounds complete. Shows verification status inline.
4. **Results Browser** — two views:
   - **Reading view:** Canonical record as a scrollable document with inline citation annotations (green = verified, yellow = needs review, red = flagged). Hover/click for verification details.
   - **Overview:** Summary dashboard with aggregate verification stats, cross-citation matrix, key findings. Drill-down into any citation's full 3-pass verification trail.

### 2D. Verification UI

The verification system is a key differentiator and needs to be presented well:

**Summary dashboard (default landing):**
- Aggregate stats bar: "94% verified | 2 flagged | 1 needs review"
- Per-participant breakdown table
- Flagged citations highlighted with one-click drill-down

**Inline in reading view:**
- Citations color-coded: green (verified), yellow (needs review), red (flagged)
- Click any citation to expand the full verification trail: Pass 1 (training knowledge triage), Pass 2 (bibliographic search), Pass 3 (deep investigation)
- Show how flagged citations were handled: WITHDRAWN, QUALIFIED, or DEFENDED in subsequent rounds

**Verification data stored in Supabase** for querying across inquiries.

### 2E. Deployment

Docker Compose with three services:
- `web` — Next.js app (Node)
- `engine` — Python engine with HTTP API
- Supabase hosted (free tier) or self-hosted Postgres

Deploy on Fly.io or Railway. Or any VPS with Docker.

### Phase 2 deliverable
A working web app where you enter a question, plan the inquiry with an AI assistant, start it, watch progress, and browse results with full verification transparency. Shareable with friends via a URL.

---

## Phase 3: Interactive Features

**Goal:** Move from "watch and read" to "participate and explore."

### 3A. Post-inquiry analysis agent

A chat interface loaded with the full canonical record + verification data. Users ask:
- "What were the main disagreements?"
- "Summarize what the economist argued"
- "Which citations were flagged and why?"
- "Where did everyone agree?"

Implementation: Claude call with canonical record in context. Standard multi-turn chat from Next.js API route. Chat history persisted in Supabase.

### 3B. Direct participant conversations

Click on any participant to open a 1:1 chat. Their system prompt + all their debate outputs loaded as context. They respond in character, "remembering" the full inquiry. The participant maintains their disciplinary identity and can elaborate on any of their arguments.

### 3C. Panel/Q&A format

The `panel_qa` round type (already in engine schema):
- User poses a question to all participants or specific ones
- Participants respond from their expertise
- User can follow up, drill deeper, redirect
- More conversational, less structured than debate
- Can be used standalone or mixed into a debate (e.g., user injects a question between rounds)

### 3D. Between-round user intervention

Add a `user_input` round type. When the engine hits this round, it pauses (status: `waiting_for_input`). The web UI shows a prompt. User submits their question/direction, engine resumes. This lets users steer the inquiry mid-flight.

### Phase 3 deliverable
Users can have conversations with the analysis agent and individual participants, run Q&A panels, and inject their own questions mid-inquiry.

---

## Phase 4: Polish

- **Cost estimation** before starting (estimate tokens based on participant count, rounds, models)
- **Resume on failure** (engine already skips completed outputs — just expose a resume button in the UI)
- **Export** canonical record as PDF
- **Inquiry templates** for common setups (3-person debate, 5-person panel, etc.) that the planning agent can start from
- **Better anti-convergence** via a "dissent agent" whose role is to challenge emerging consensus
- **Multi-model support** (different providers per participant to reduce single-model fingerprints)

---

## Key Architecture Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Keep Python engine | Yes | 2000+ lines of working orchestration; rewriting in JS gains nothing |
| Web layer | Next.js | User's strongest stack, handles planning agent + UI well |
| Communication | HTTP (engine) + SSE (progress) | Simple; no WebSocket complexity for a long-running process |
| Storage | Hybrid: filesystem (outputs) + Supabase (structured data) | Outputs are documents; verification/config/chat need queryability |
| Planning agent | Multi-turn Claude chat, high-level-first | Present 2-3 approaches, refine collaboratively, don't get sidetracked |
| Verification UX | Summary dashboard + inline annotations | Both views serve different needs; verification is a key differentiator |
| Deployment | Docker Compose | Two containers + hosted Supabase; deploy anywhere, no vendor lock-in |
