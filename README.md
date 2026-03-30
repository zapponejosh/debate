# Women, Authority, and the Church: A Six-Discipline Debate System
## Project README

---

## What This Is

A structured multi-party debate system that uses LLM agents to model rigorous scholarly inquiry into the question of women in church leadership. Six disciplinary advocates — each powered by a separate LLM agent with a distinct identity, methodology, and source base — engage a shared anchor text (the Alderwood Community Church position document), cross-examine each other across four rounds, and arrive at ecclesial conclusions grounded in their disciplinary findings.

A seventh agent serves as moderator and fact-checker, independent from all advocates.

This is simultaneously:
- A **theological inquiry tool** — producing a genuine multi-disciplinary engagement with a contested question
- A **learning project** — exploring multi-agent LLM architecture, citation verification, persistent state management, and argument tracking
- A **template** — for applying the same architecture to other contested theological or ethical questions

The debate is not designed to produce a winner. It is designed to model what honest, disciplined, cross-disciplinary inquiry looks like.

---

## Anchor Text

**Alderwood Community Church**
*What Alderwood Teaches about Women in Church Leadership*
Available: https://alderwood.cc/wp-content/uploads/What-Alderwood-Teaches-about-Women-in-Church-Leadership-Finalized.pdf

Every advocate uses this document as a launching pad — not a target to defeat but a serious position to engage, affirm where their discipline affirms it, and push beyond where their discipline opens new ground.

---

## Repository Structure

```
/
├── README.md                          # This file
├── debate_framework.md                # Full debate design (V4 — the canonical plan)
├── system_prompts.json                # All agent system prompts + round prompt templates
├── scripts/
│   ├── conductor.py                   # Main orchestration — runs rounds sequentially
│   ├── document_compiler.py           # Compiles round outputs into canonical record
│   ├── context_packager.py            # Builds per-advocate input for each round
│   ├── citation_extractor.py          # Parses citation blocks from advocate outputs
│   ├── citation_verifier.py           # Automated verification agent (web search)
│   └── audit_worksheet.py             # Generates human audit worksheets
├── outputs/                           # All generated content (one run)
│   ├── predebate/                     # Position papers + source registers
│   ├── round_1/                       # One file per advocate + moderation report
│   ├── round_2/                       # Questions, responses + moderation report
│   ├── round_3/                       # Text responses + moderation report
│   ├── round_4/                       # Closing arguments + final moderation report
│   ├── synthesis/                     # Moderator synthesis + advocate responses
│   └── canonical_record.md            # Full compiled debate — the final artifact
├── verification/
│   ├── citations/                     # Extracted citation JSON per round
│   ├── verifications/                 # Automated verification results per round
│   ├── audit/                         # Human audit worksheets (generated + completed)
│   └── moderator_input/               # Compiled verification results for moderator
└── verification-system.md             # Citation verification system design spec
```

---

## The Six Advocates

| # | Advocate | Disciplinary Lead | Tagline |
|---|----------|------------------|---------|
| 1 | Biblical Scholar | Exegesis and canonical theology | *"The texts say more than the debate has heard — and less than both sides claim."* |
| 2 | Reception Historian | Reception history and history of interpretation | *"What the church has done with these texts is itself a form of evidence."* |
| 3 | Hermeneutician | Philosophy of interpretation | *"Everyone in this debate has a hermeneutic. Most of them haven't examined it."* |
| 4 | Systematic Theologian | Ecclesiology, ministry, and authority | *"The debate about who can lead assumes we know what the church is."* |
| 5 | Pastoral Theologian | Pastoral and practical theology | *"Doctrine is not tested in the library. It is tested in the lives of people."* |
| 6 | Social/Cultural Analyst | Social anthropology and sociology of religion | *"Every reading happens inside a social world. The question is whether you know which one."* |

Plus:

| # | Role | Function |
|---|------|----------|
| 7 | Moderator/Fact-Checker | Verification, synthesis, procedural management — no advocacy |

---

## Debate Structure

### Rounds

| Round | Purpose | Word Count |
|-------|---------|------------|
| Pre-debate | Position papers + source registers | Up to 1,500 words per advocate |
| Round 1 | Opening statements: disciplinary findings | 600–800 words per advocate |
| Round 2 | Cross-disciplinary examination | 400 words/question, 250 words/response |
| Round 3 | Seven required texts — all advocates respond to each | 1,750 words total per advocate (min 150 per text) |
| [Synthesis] | Moderator synthesis — map of convergence and divergence | 300–400 words |
| [Synthesis Response] | Each advocate responds to the synthesis | 100 words max per advocate |
| Round 4 | Closing arguments: what does faithful practice require? | 500–650 words per advocate |

### Speaking Order
- **Rounds 1, 2, 3:** Advocates 1 → 6
- **Round 4:** Advocates 6 → 1 (reversed)

### The Seven Required Texts (Round 3)
1. Genesis 2:18–23 — the *ezer* and creation sequence
2. 1 Timothy 2:11–14 — the central prohibition
3. 1 Corinthians 11:2–16 — women praying and prophesying
4. 1 Corinthians 14:33–35 — women keeping silent
5. Galatians 3:28 — neither male nor female
6. Romans 16 (selected) — the women Paul names
7. Judges 4–5 and 2 Kings 22 — Deborah and Huldah

---

## Architecture

### Design Principles

**Separation of concerns:** Each advocate is a fully independent agent. They do not share a conversation or context window with other advocates. They receive other advocates' outputs as compiled documents — the same way a real debate participant reads a position paper, not a live conversation feed.

**Fresh calls, not persistent conversations:** Each advocate makes a single API call per round with a carefully constructed input: system prompt + compiled prior outputs + round prompt. This gives total control over what the agent sees. Nothing hidden, nothing accumulated from prior reasoning.

**Disciplinary identity over harmonization:** The greatest risk in a single-LLM debate is that all positions harmonize toward the model's implicit priors. Separate agents with strong disciplinary system prompts resist this. The Biblical Scholar and the Social Analyst should disagree — that tension is the point. Each round prompt includes a re-anchoring instruction: "You are the [X]. Review your Statement of Limits. Respond from your discipline, not as a generalist."

**Structured citation protocol:** Every factual claim is tagged at point of output using a structured format. A dedicated verification agent (separate from the moderator) processes these tags with web search. Claims it can't resolve are routed to a human auditor via a structured worksheet.

**Persistent canonical record:** Every round output plus every moderation report is compiled into a canonical debate record that grows across the debate. This record — not raw conversation history — is what each agent receives as context for subsequent rounds.

**Context compression for later rounds:** By Round 4, the full canonical record exceeds 40,000 words. Rather than injecting everything, each advocate receives: their own prior outputs in full, a moderator-compiled summary of the other five advocates' key arguments and positions (not full text), the moderator synthesis and synthesis responses, and the Round 4 prompt. This cuts context by ~60% while preserving what matters — the advocate's own voice and a clear picture of where the debate stands.

**Explicit uncertainty:** Both advocates and the moderator are required to express uncertainty. "I cannot verify this citation" and "my discipline cannot establish this" are required outputs, not failures.

### System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    CONDUCTOR SCRIPT                       │
│  (Python — runs rounds sequentially, assembles inputs)   │
└─────────────┬───────────────────────────┬───────────────┘
              │                           │
    ┌─────────▼──────────┐     ┌──────────▼──────────────┐
    │   ADVOCATE AGENTS   │     │  MODERATOR AGENT        │
    │   (×6, per round)   │     │  (fact-check + synth)   │
    │                     │     │                         │
    │  Fresh API call     │     │  Receives:              │
    │  each round with:   │     │  - Verification results │
    │  - System prompt    │     │  - Round outputs        │
    │  - Re-anchoring     │     │  Produces:              │
    │  - Compiled record  │     │  - Fact-check report    │
    │  - Round prompt     │     │  - Synthesis            │
    └─────────┬──────────┘     └──────────┬──────────────┘
              │                           │
    ┌─────────▼───────────────────────────▼──────────────┐
    │              CANONICAL DEBATE RECORD                 │
    │  (Markdown — grows across all rounds)                │
    └─────────────────────┬──────────────────────────────┘
                          │
    ┌─────────────────────▼──────────────────────────────┐
    │          CITATION VERIFICATION SYSTEM                │
    │                                                      │
    │  Citation Extractor → Verifier Agent (web search)   │
    │       → Auto-resolved (logged)                       │
    │       → Human Audit Worksheet (flagged claims)       │
    │       → Completed audit → Moderator input            │
    └─────────────────────────────────────────────────────┘
```

### Citation Verification System

A two-pass architecture separates automated verification from human judgment:

**Pass 1 — Automated Verifier Agent:** A dedicated LLM call with web search enabled. For each citation: confirms the book exists (bibliographic check), confirms the author addresses the topic (topical check), confirms the author's known position aligns with the attributed argument (argument direction check), and checks for dissenting voices if consensus is claimed. Limited to 3 web searches per citation to control cost. Produces structured verdicts: VERIFIED, LIKELY_ACCURATE, LIKELY_ACCURATE_BUT_CONTESTED, PARTIALLY_VERIFIED, NEEDS_HUMAN_REVIEW, or FABRICATION_RISK.

**Pass 2 — Human Audit Worksheet:** Claims the verifier couldn't resolve are compiled into a structured markdown worksheet, pre-sorted by priority, with the automated findings and search suggestions already attached. The auditor assigns one of five verdicts:
- **CONFIRMED** — found in the original source
- **CONFIRMED_INDIRECT** — corroborated by other reliable evidence (author's blog, book review, secondary citation), with structured fields for evidence type, source, and confidence
- **PLAUSIBLE_BUT_UNCONFIRMED** — consistent with known content, no contradicting evidence
- **LIKELY_FABRICATED** — evidence contradicts the claim or no trace found
- **CANNOT_DETERMINE** — insufficient access to resolve

Each claim also receives an impact assessment (load-bearing, supporting, or illustrative) and an action recommendation. Completed worksheets flow into the moderator's input for the fact-check report.

See `verification-system.md` for the full specification.

### Model Selection

Quality is the priority; cost is managed by matching model capability to round demands:

| Round | Model | Rationale |
|-------|-------|-----------|
| Pre-debate position papers | Sonnet 4.6 | Structured output from detailed prompts — Sonnet handles this well |
| Round 1 openings | Sonnet 4.6 | Constrained, prompted, single-discipline output |
| Round 2 cross-examination | **Opus** | Requires understanding another discipline's argument well enough to challenge it |
| Round 3 text responses | Sonnet 4.6 | Short, constrained per-text responses |
| Moderator fact-checking | Sonnet 4.6 | Pattern matching against training knowledge + verification input |
| Moderator synthesis | **Opus** | Must hold six disciplines' findings simultaneously |
| Synthesis responses | Sonnet 4.6 | 100-word constrained responses |
| Round 4 closing arguments | **Opus** | Deep reasoning, cross-disciplinary integration, ecclesial conclusions |
| Verifier agent | Sonnet 4.6 | Bibliographic verification — doesn't need Opus reasoning |

Temperature: 0.75 for advocates (disciplinary character without incoherence), 0.25 for moderator and verifier (consistency over creativity).

---

## Technology Stack

### Core
- **Language:** Python 3.11+
- **LLM:** Anthropic API (Claude)
- **Primary model:** Opus for cross-examination (Round 2), synthesis, and closing arguments (Round 4)
- **Secondary model:** Sonnet 4.6 for constrained-output rounds (1, 3, pre-debate), fact-checking, and verification
- **Web search:** Anthropic web search tool (for citation verification agent)

### Key Dependencies
```
anthropic>=0.40.0
python-dotenv
rich              # For readable terminal output during runs
tenacity          # For API retry logic
```

### Environment Variables
```
ANTHROPIC_API_KEY=
DEBATE_OUTPUT_DIR=       # Where to write the canonical record
LOG_LEVEL=INFO
```

---

## Citation Protocol

All advocate outputs must follow this tagging format for factual claims:

```
[CLAIM: brief statement of the claim being made]
[SOURCE: Author, Title, Publisher, Year, p. XX if available]
[ARGUMENT: the specific argument being attributed to this source]
[CONFIDENCE: HIGH / MEDIUM / LOW — advocate's own assessment]
```

Example:
```
[CLAIM: authenteo carried a negative connotation in first-century Greek]
[SOURCE: Nijay Gupta, Tell Her Story, IVP Academic, 2023, p. 170]
[ARGUMENT: Gupta argues the word's rarity and pattern of use in ancient sources suggests it describes an abuse of power rather than neutral exercise of authority]
[CONFIDENCE: MEDIUM — lexical debate is genuinely contested]
```

The moderator processes all tagged claims and returns:
```json
{
  "claim_id": "R1_BS_001",
  "round": 1,
  "advocate": "biblical_scholar",
  "claim": "authenteo carried a negative connotation in first-century Greek",
  "source_cited": "Gupta, Tell Her Story, 2023, p. 170",
  "verification_status": "CONTESTED",
  "moderator_note": "Gupta's argument exists and is accurately attributed. The claim itself is contested — Al Wolters (JETS, 2006) argues for neutral meaning. Both readings have serious scholarly defenders.",
  "search_result": "Confirmed: Gupta makes this argument. Westfall (Paul and Gender, 2016) concurs. Wolters and Köstenberger dispute it.",
  "flag_type": "SOFT"
}
```

---

## Project Phases

### Phase 1 — Single High-Quality Run (current)
Run this debate once at the highest quality achievable. The conductor script orchestrates API calls sequentially, the citation verification system catches fabrications, and a human auditor resolves what the automated verifier can't. The canonical debate record is the deliverable.

### Phase 2 — Reusable Framework
Make the system topic-agnostic. Given a question and a set of disciplines, generate: the motion, the advocate identities and system prompts, the required texts/evidence, and the cross-examination pairings. This is primarily a prompt-generation problem — Claude generating the debate configuration, which then drives the same conductor script.

### Phase 3 — Web Tool (Beta)
A web application wrapping the conductor. Users select from curated topics, the system generates the debate configuration and runs it. Key challenges: cost management (a full debate run is expensive), job queue (runs take time), and output presentation (the canonical record must be readable). Limited to pre-curated topics initially.

### Enhancement Options (for any phase)
These are available but not required for Phase 1:

- **Web search for advocates:** Allow advocates to use web search during Round 2 cross-examination. Adds citation richness but increases cost significantly.
- **Vector store for source material:** Load key books/articles into a vector database for the verification pipeline. Dramatically improves citation accuracy. High setup cost.
- **Iterative position refinement:** After Round 2, allow each advocate one revision of their Round 1 opening. Models intellectual responsiveness to challenge.
- **Multi-run consensus:** Run the full debate 3 times with different temperatures and compare. Flags where conclusions are model-stable vs. temperature-sensitive.
- **Human-in-the-loop moderation:** Route flagged claims to a human before the moderation report is finalized. Highest accuracy, requires active participation during the run.

---

## Known Limitations and Risks

### LLM Hallucination
The most serious risk. LLMs generate plausible-sounding citations that may be inaccurate, misattributed, or entirely fabricated. The citation verification system (automated verifier + human audit worksheet) mitigates this but does not eliminate it. **All citations in the final canonical record must be independently verified before the record is treated as authoritative.** Estimated human audit time: 10–15 hours across the full debate.

### Disciplinary Drift
Even with strong system prompts, advocates may drift from their disciplinary identity across long runs — the Biblical Scholar may start arguing like the Pastoral Theologian by Round 4. Mitigations built into the architecture: fresh API calls each round (no accumulated conversation context), re-anchoring instructions in every round prompt ("You are the [X]. Review your Statement of Limits."), and each advocate's own prior outputs given more prominence than the compiled record of other advocates.

### Harmonization Pressure
All agents are ultimately the same underlying model. Despite separate contexts and system prompts, they share the same training priors. The most genuinely contested questions — where the model has a strong implicit lean — will show harmonization pressure. This is a known limitation of single-model multi-agent debate and cannot be fully resolved without using different base models for different advocates. The system prompts build genuine methodological tension between disciplines (e.g., the Reception Historian and the Hermeneutician should disagree about whether the history of a reading is evidence about the reading's validity).

### Citation Confidence Overstatement
LLMs express more confidence about citations than is warranted, especially for page numbers and specific argument attributions. The [CONFIDENCE] tag surfaces this, and the shared context instructs advocates to default to MEDIUM or LOW for specific page numbers and to HIGH only for author, work, and general argument direction. The automated verifier marks all page numbers as UNVERIFIABLE by default.

### Context Window Management
The canonical debate record grows to approximately 40,000–60,000 words by Round 4. For Round 4 specifically, the context packager compresses the record: each advocate receives their own prior outputs in full plus a moderator-compiled summary of the other five advocates' positions (not full text). This keeps the input manageable while preserving what matters. Rounds 1–3 receive the full compiled record since it's still within comfortable context limits.

---

## The Debate Is Not Designed to Produce a Winner

This bears stating explicitly in the README because it shapes every design decision.

The goal is a demonstration of what it looks like when multiple disciplines engage a contested question honestly — including acknowledging limits, engaging inconvenient evidence, and arriving at provisional conclusions that are genuinely grounded in disciplinary findings rather than pre-formed positions.

The canonical record is the output. Not a verdict.

---

## Implementation Plan

### Build Order

**Critical: build incrementally. Each step validates the one before it. Do not build the entire system in one pass.**

1. **Set up the output directory structure first** — create `outputs/predebate/`, `outputs/round_1/` through `outputs/round_4/`, `outputs/synthesis/`, `verification/citations/`, `verification/verifications/`, `verification/audit/`, `verification/moderator_input/` before running anything. File-not-found errors are annoying when the interesting problem is prompt quality.

2. **Finalize system prompts** — they are the foundation. Test each advocate's system prompt independently with a single-round test before building the multi-agent pipeline.

3. **Build the conductor script** — sequential round execution, input assembly, output storage. Start simple: read system prompts from JSON, make API calls, write outputs to files.

4. **Build the document compiler** — assembles round outputs into the canonical record. Markdown with clear section headers and advocate labels. Decide the format before any agents run.

5. **Build the context packager** — the most important piece for quality. Handles: full record for Rounds 1–3, compressed record for Round 4 (own outputs in full, summaries of others), re-anchoring instructions injected at every round boundary.

6. **Run Round 1 alone** — generate all six opening statements and the first moderation report. Evaluate: are the disciplinary voices distinct? Are citations well-formed? Is the moderator catching real issues? Adjust prompts before proceeding.

7. **Integrate the citation verification system** — run the extractor, verifier, and audit worksheet generator after Round 1. Complete the human audit. Feed results into the moderator for the Round 1 fact-check report.

8. **Run Rounds 2–4** — once Round 1 validates the architecture, run the remaining rounds. Human audit after each round before proceeding to the next.

### Implementation Details That Matter

**Round 3 word allocation:** The conductor should send all seven texts to each advocate in a single prompt, not one text at a time. The advocate needs to see all seven to decide where to go deep (1,750 words total, 150 minimum per text). A per-text loop with word tracking is more complex and produces worse results because the advocate can't plan allocation across texts. Send them all at once.

**Template variable injection:** The round prompts in `system_prompts.json` contain injection points: `{ADVOCATE_DISPLAY_NAME}`, `{DISCIPLINARY_LEAD}`, `{TARGET_ADVOCATE}`, `{TENSION_DESCRIPTION}`, `{TEXT_NAME}`, `{TEXT_PASSAGE}`, `{TEXT_DISPUTE}`. The conductor must map these from the `system_prompts.json` agent data and `required_texts_round_3` data — do not hardcode them. Build a general template-filling function that takes a prompt template and a dict of variables.

**Round 4 context compression:** This is the highest-value piece of code in the system. The compressed record must preserve each advocate's own prior outputs verbatim while summarizing the other five advocates' positions. The summarization is a specific prompt to the Sonnet coordination model — not truncation, not mechanical extraction. The prompt should instruct Sonnet to produce a 200–300 word summary of each advocate's key arguments and positions across Rounds 1–3, preserving their specific claims and any concessions made. The advocate then receives: their full outputs + five summaries + the moderator synthesis + synthesis responses.

**Round 2 tension descriptions:** The pairings and tension descriptions are in the framework document, not in `system_prompts.json`. The conductor needs to map each advocate to their target and inject the correct `{TENSION_DESCRIPTION}` from the framework's Round 2 table. Consider adding the pairings to `system_prompts.json` as structured data to make this cleaner.

### Temperature Settings
- Advocates: 0.75
- Moderator: 0.25
- Verifier: 0.25
- Conductor language tasks (formatting, compilation): 0.3

### Key Design Decision: Canonical Record Format
Markdown with this structure per round:

```markdown
# Round N — [Round Title]

## Advocate 1: Biblical Scholar
[output]

## Advocate 2: Reception Historian  
[output]

...

## Moderation Report — Round N
[fact-check summary]
[flagged claims]
```

This is parseable by both the document compiler (for assembly) and by the context packager (for extracting individual advocate outputs).

---

*Project initialized: 2026*
*Framework version: 4.0*
*Status: System prompts and verification system complete. Conductor script next.*