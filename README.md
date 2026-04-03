# Inquiry Framework

A multi-agent system for running structured intellectual inquiries. Separate AI agents, each with a distinct disciplinary identity, examine a question together across structured rounds — with citation verification, moderation, and a full audit trail.

---

## Table of Contents

- [Overview](#overview)
- [Design Principles](#design-principles)
- [Architecture](#architecture)
- [Getting Started](#getting-started)
- [Using the Web App](#using-the-web-app)
- [Inquiry Config Schema](#inquiry-config-schema)
- [Round Types](#round-types)
- [Citation Protocol](#citation-protocol)
- [Repository Structure](#repository-structure)
- [Roadmap](#roadmap)
- [Origin: The Theology Debate](#origin-the-theology-debate)

---

## Overview

The framework runs structured multi-agent inquiries on any question where disciplinary perspective matters. You pick a question, configure a set of participants (each with a unique discipline, methodology, and epistemic limits), define a round structure, and the engine handles the rest — context management, citation verification, moderation, and output.

**What it produces:**
- A canonical record of the inquiry with each participant's contributions across all rounds
- Per-citation verification trail (3-pass: knowledge triage → bibliographic search → deep investigation)
- Moderator synthesis identifying convergence, divergence, and irreconcilable tensions
- Full audit trail in both markdown and structured database form

**It does not produce a winner.** The moderator synthesizes; it never adjudicates.

**Proven in the first run:** 6 advocates, 4 rounds, 114 citations verified, 1.75% fabrication rate (both caught), 5 cross-disciplinary findings meeting the 3-discipline threshold.

---

## Design Principles

**1. Agent isolation over persona simulation.**
Each participant is a separate API call with its own system prompt, context window, and temperature. Never multiple perspectives from one prompt — the harmonization pressure defeats the purpose.

**2. System prompts are first-class artifacts.**
The quality of the inquiry depends on well-crafted system prompts: disciplinary methodology, explicit epistemic limits ("you CAN establish X, you CANNOT establish Y"), citation expectations, and interaction style. The planning agent is designed to generate these at high quality.

**3. Context is controlled and intentional.**
Each agent sees only what it should — its own full history, compressed summaries of others, the shared question, and any grounding documents. Context compression kicks in for later rounds.

**4. Verification is visible, not hidden.**
The 3-pass citation pipeline is a key differentiator. Every claim's verification trail is preserved and surfaced in the UI.

**5. The moderator synthesizes, never adjudicates.**
Moderator output must identify irreconcilable tensions explicitly — not paper over them with a coherent-sounding narrative.

---

## Architecture

```
┌─────────────────────────────┐     HTTP/SSE     ┌──────────────────────┐
│      Next.js Web App        │ ◄──────────────► │   Python Engine      │
│  (planning, UI, results)    │                  │  (orchestration,     │
│                             │                  │   verification,      │
│  /          Home            │                  │   citation pipeline) │
│  /plan      Planning chat   │                  └──────────────────────┘
│  /inquiry   Live progress   │
│  /results   Results browser │          ▼
└─────────────────────────────┘     Supabase (Postgres)
                                    - Inquiry configs + metadata
                                    - Planning session history
                                    - Citation verification data
                                    - Run status
                                         ▼
                                    Filesystem
                                    - Markdown outputs (canonical record)
                                    - Round outputs as documents
```

**Stack:**
- **Engine:** Python + FastAPI + SSE. Config-driven orchestrator that accepts any `InquiryConfig` JSON.
- **Web:** Next.js (App Router) + Tailwind. Talks to the engine via HTTP. Planning agent backed by Claude API.
- **Storage:** Supabase (Postgres) for structured data; filesystem for document outputs.
- **Deployment:** Docker Compose (two containers + hosted Supabase). Runs on Fly.io, Railway, or any VPS.

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- A Supabase project (free tier works)
- `ANTHROPIC_API_KEY` in your environment

### Engine

```bash
# Install dependencies
pip install -r requirements.txt

# Start the engine (default port 8000)
python scripts/server.py

# Or with a custom port
python scripts/server.py --port 8000
```

### Web App

```bash
cd web
npm install
npm run dev   # http://localhost:3000
```

### Environment variables

Create `web/.env.local`:

```
ANTHROPIC_API_KEY=...
NEXT_PUBLIC_SUPABASE_URL=...
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
ENGINE_URL=http://localhost:8000
```

### CLI (no web app)

You can also run inquiries directly via CLI:

```bash
# Run all rounds of a config
python scripts/conductor.py --config configs/ai_regulation_debate.json --all

# Run a specific round
python scripts/conductor.py --config configs/ai_regulation_debate.json --round round_1

# Dry run (preview without API calls)
python scripts/conductor.py --config configs/ai_regulation_debate.json --round round_1 --dry-run

# Run one participant in one round
python scripts/conductor.py --config configs/ai_regulation_debate.json --round round_1 --participant economist
```

---

## Using the Web App

**Home (`/`)** — Enter a question and optionally upload a grounding document (paper, article, policy text). Click "Start Planning."

**Planning chat (`/plan`)** — Conversational planning agent that guides you from a raw question to a full config:
1. Asks 1-2 clarifying questions
2. Presents 2-3 structural approaches (Structured Debate, Expert Panel, Advisory Council) with trade-offs
3. Collaboratively builds out participants, rounds, and central question
4. Generates the full config JSON when you approve
5. Shows a live config preview sidebar as the design takes shape

**Inquiry dashboard (`/inquiry/[id]`)** — Live progress via SSE as the engine runs. Outputs appear as rounds complete.

**Results (`/results`)** — Browse completed inquiries and their outputs.

---

## Inquiry Config Schema

All inquiries are defined by an `InquiryConfig` JSON. The planning agent generates this; you can also write or edit one manually.

```json
{
  "version": "2.0",
  "inquiry": {
    "title": "Short display title",
    "question": "The full central question.",
    "format": "debate",
    "shared_context": "Optional context shown to all agents.",
    "grounding_document_label": "Optional label for an uploaded document"
  },
  "participants": [
    {
      "id": "economist",
      "display_name": "The Economist",
      "role": "Markets, incentives, and trade-offs",
      "system_prompt": "Full system prompt...",
      "position_direction": "neutral"
    }
  ],
  "moderator": {
    "system_prompt": "Full moderator system prompt...",
    "fact_check_prompt": "Optional per-round fact-check template"
  },
  "rounds": [
    {
      "key": "round_1_opening",
      "title": "Opening Statements",
      "type": "parallel_statements",
      "prompt_template": "Prompt shown to each participant.",
      "model": "sonnet",
      "word_limit": 400,
      "verify_citations": false,
      "run_moderation": false,
      "generate_digest": true,
      "generate_claim_ledger": false,
      "pairings": [],
      "required_texts": [],
      "reversed_speaking_order": false,
      "use_compressed_context": false
    }
  ],
  "settings": {
    "anti_convergence": true,
    "citation_protocol": true,
    "temperature": {
      "participants": 0.9,
      "moderator": 0.7,
      "verifier": 0.3,
      "language_tasks": 0.3
    }
  }
}
```

Valid values:
- `format`: `debate` | `panel`
- `position_direction`: `for` | `against` | `neutral`
- `model` (per round): `sonnet` | `opus`

Example configs: [`configs/theology_debate.json`](configs/theology_debate.json), [`configs/ai_regulation_debate.json`](configs/ai_regulation_debate.json)

---

## Round Types

| Type | Description | Notes |
|------|-------------|-------|
| `parallel_statements` | Each participant speaks independently | Opening statements, closing arguments |
| `paired_exchange` | Directed question + response pairs | Requires `pairings` array with `questioner`, `target`, `tension` |
| `moderator_synthesis` | Moderator synthesizes; participants respond | Requires `synthesis_prompt` and `response_prompt` |
| `panel_qa` | User poses a question; participants respond | Interactive; used in panel format |

**Standard debate structure (4 rounds):**
1. `parallel_statements` — opening statements
2. `paired_exchange` — cross-examination
3. `moderator_synthesis` — synthesis + participant responses
4. `parallel_statements` — closing arguments (`use_compressed_context: true`, `reversed_speaking_order: true`)

**Standard panel structure (2-3 rounds):**
1. `parallel_statements` — opening perspectives
2. `moderator_synthesis` — synthesis + responses
3. *(optional)* `panel_qa` — interactive Q&A

---

## Citation Protocol

Every claim that can be verified should be structured:

```
[CLAIM] The stated claim.
[SOURCE] Author, Title, Year, Page/Section.
[ARGUMENT] How this source supports the claim.
[CONFIDENCE] HIGH | MEDIUM | LOW
```

LOW confidence with no page number is more honest than HIGH confidence with a fabricated one — system prompts make this explicit.

**Verification pipeline (3 passes):**

1. **Training knowledge triage** — Does this source plausibly exist? Is the claim consistent with what the model knows about it?
2. **Bibliographic search** — Cross-reference against known bibliographic data. Flag mismatches.
3. **Deep investigation** — For suspicious citations only. Attempt to establish or refute the specific claim.

**Accountability loop:** When a citation is flagged, the finding goes back to the participant. In subsequent rounds they must respond with one of: `WITHDRAW` (claim removed from record), `QUALIFY` (claim narrowed), or `DEFEND` (maintained, optionally with new sourcing). Withdrawn claims are excluded from context summaries.

---

## Repository Structure

```
/
├── scripts/
│   ├── server.py              # FastAPI engine with SSE progress events
│   ├── engine.py              # Config-driven orchestrator (round execution)
│   ├── inquiry_schema.py      # Pydantic config schema (source of truth)
│   ├── conductor.py           # CLI entrypoint
│   ├── citation_extractor.py  # Citation parsing
│   ├── citation_verifier.py   # 3-pass verification pipeline
│   ├── context_packager.py    # Per-agent context assembly
│   ├── document_compiler.py   # Canonical record generation
│   └── migrate_config.py      # Legacy config migration tool
├── configs/
│   ├── theology_debate.json   # Original 6-advocate theology debate
│   └── ai_regulation_debate.json  # 4-participant AI regulation panel
├── web/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx               # Home
│   │   │   ├── plan/page.tsx          # Planning chat
│   │   │   ├── inquiry/[id]/page.tsx  # Live inquiry dashboard
│   │   │   ├── results/page.tsx       # Results browser
│   │   │   └── api/                   # Next.js API routes
│   │   ├── components/
│   │   │   └── planning/
│   │   │       └── ConfigPreview.tsx  # Live config sidebar
│   │   └── lib/
│   │       ├── planning-prompt.ts     # Planning agent system prompt
│   │       ├── normalize-config.ts    # Config normalization (agent output → schema)
│   │       └── engine-client.ts       # HTTP client for the Python engine
│   └── package.json
├── outputs/                   # Engine-written inquiry outputs (markdown)
├── requirements.txt
└── docker-compose.yml
```

---

## Roadmap

### Phase 3: Interactive Features

- **Post-inquiry analysis agent** — Chat interface loaded with the full canonical record. Ask "what were the main disagreements?" or "summarize what the economist argued."
- **Direct participant conversations** — Click any participant to open a 1:1 chat. They respond in character using their system prompt + full round history.
- **Panel Q&A** — Interactive rounds where users inject questions between structured rounds.
- **Between-round intervention** — `user_input` round type that pauses the engine and waits for a user question before resuming.

### Phase 4: Polish

- Cost estimation before starting (token estimate based on participant count, rounds, model)
- Resume on failure (engine already skips completed outputs — expose a resume button)
- Export canonical record as PDF
- Inquiry templates for common setups (3-person debate, 5-person panel, etc.)
- Multi-model support (different providers per participant to reduce single-model fingerprinting)

---

## Origin: The Theology Debate

The framework was built to run a single inquiry first: *"Should women hold all offices and exercise all forms of authority in the church?"*

Six disciplinary advocates (Biblical Scholar, Reception Historian, Hermeneutician, Systematic Theologian, Pastoral Theologian, Social/Cultural Analyst) plus a moderator ran four rounds against an anchor text from Alderwood Community Church. The system verified 114 citations (1.75% fabrication rate, both caught) and produced 5 cross-disciplinary findings.

That inquiry proved the core thesis — separate agent contexts with disciplinary identities produce genuine disagreement that a single multi-persona prompt cannot. Everything built since then generalizes what worked.

The original config is at [`configs/theology_debate.json`](configs/theology_debate.json). The full outputs and post-debate reports are in [`outputs/`](outputs/) and [`post-debate-reports/`](post-debate-reports/).
