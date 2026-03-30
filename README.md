# Women, Authority, and the Church: A Six-Discipline Debate System

---

## Table of Contents

- [Overview](#overview)
- [The Research Question](#the-research-question)
- [Anchor Text](#anchor-text)
- [Design Philosophy](#design-philosophy)
- [The Six Advocates](#the-six-advocates)
  - [Agent Identities and Disciplinary Boundaries](#agent-identities-and-disciplinary-boundaries)
  - [The Statements of Limits](#the-statements-of-limits)
- [Debate Structure](#debate-structure)
  - [Rounds and Word Counts](#rounds-and-word-counts)
  - [The Seven Required Texts](#the-seven-required-texts)
  - [Round 2 Cross-Examination Pairings](#round-2-cross-examination-pairings)
  - [Speaking Order](#speaking-order)
- [System Architecture](#system-architecture)
  - [Core Design Decisions](#core-design-decisions)
  - [Technical Architecture](#technical-architecture)
  - [Model Selection](#model-selection)
  - [Context Management Strategy](#context-management-strategy)
- [Citation Protocol](#citation-protocol)
- [Citation Response Protocol](#citation-response-protocol)
- [Citation Verification System](#citation-verification-system)
  - [Pass 1 — Training Knowledge Triage](#pass-1--training-knowledge-triage)
  - [Pass 2 — Bibliographic Search (All Citations)](#pass-2--bibliographic-search-all-citations)
  - [Pass 3 — Deep Investigation (Suspicious Only)](#pass-3--deep-investigation-suspicious-only)
  - [Pass 4 — Human Audit Worksheet](#pass-4--human-audit-worksheet)
  - [Verification Verdict Types](#verification-verdict-types)
- [Repository Structure](#repository-structure)
- [Known Limitations and Risks](#known-limitations-and-risks)
- [What This System Can and Cannot Produce](#what-this-system-can-and-cannot-produce)
- [Usage Guide](#usage-guide)
  - [Setup](#setup)
  - [Running the Debate](#running-the-debate)
  - [Flags](#flags)
  - [Advocate IDs](#advocate-ids)
  - [Output Structure](#output-structure)
  - [Human Audit Workflow](#human-audit-workflow)
  - [Recommended Run Order](#recommended-run-order)
- [Project Phases](#project-phases)

---

## Overview

A structured multi-party debate system that uses separate LLM agents to model rigorous scholarly inquiry into the question of women in church leadership. Six disciplinary advocates — each powered by an independent agent with a distinct identity, methodology, and explicit statement of limits — engage a shared anchor text, cross-examine each other across four rounds, and arrive at conclusions grounded in their disciplinary findings rather than pre-formed positions.

A seventh agent serves as moderator and fact-checker, independent from all advocates.

This is simultaneously:
- A **theological inquiry tool** — producing genuine multi-disciplinary engagement with a historically contested question
- An **architecture experiment** — exploring multi-agent LLM design for structured argument, citation verification, and persistent state management across long runs
- A **template** — for applying the same architecture to other contested theological or ethical questions where disciplinary method matters

**The debate is not designed to produce a winner. It is designed to model what honest, disciplined, cross-disciplinary inquiry looks like.**

---

## The Research Question

**Motion:** *"Women should be permitted to hold all offices and exercise all forms of authority in the church, including ordination as pastors and elders, on equal terms with men."*

This question was selected because:

1. **It is genuinely contested among serious scholars.** Unlike many theological debates that are effectively settled by broad consensus, this one has careful scholars on both sides working the same evidence and reaching different conclusions. It is a genuine hard case.

2. **It involves multiple disciplines that speak to different aspects of the question.** Exegesis, hermeneutics, systematic theology, reception history, pastoral theology, and social/cultural analysis each have legitimate and distinct contributions — and they do not always point in the same direction. A single-discipline answer to this question is structurally incomplete.

3. **The anchor text (the Alderwood document) is an unusually careful complementarian position paper.** It does not rely solely on proof-texting; it engages hermeneutical questions. This makes it a more interesting target for cross-disciplinary engagement than a less careful document would be.

4. **It tests the architecture.** A question where all disciplines converge trivially would not reveal whether the multi-agent design actually produces disciplinary diversity.

---

## Anchor Text

**Alderwood Community Church**
*What Alderwood Teaches about Women in Church Leadership*
Available: https://alderwood.cc/wp-content/uploads/What-Alderwood-Teaches-about-Women-in-Church-Leadership-Finalized.pdf

Every advocate uses this document as a launching pad — not a target to defeat but a serious position to engage, affirm where their discipline affirms it, and push beyond where their discipline opens new ground. The document is injected as full text into every agent's context at the start of each round.

The choice to use an actual church document (rather than a generic "complementarian position") grounds the debate in a real ecclesial artifact and tests whether the system can engage a real document on its own terms rather than a caricature.

---

## Design Philosophy

### Why Multiple Agents, Not Multiple Personas from One Agent

The most natural approach to a "multi-perspective" debate is to use a single LLM with prompts like "now respond as a feminist theologian." This has a structural problem: all the perspectives are generated by the same model in the same context window, with the accumulated weight of each previous response present. Genuine disagreement is epistemically difficult when you are also the person you are disagreeing with.

Separate agents with separate contexts and separate system prompts resist this in several ways:
- Each agent's round input is constructed independently — it does not know what the other agents said before they said it
- Each agent has a disciplinary identity that constrains what counts as a good argument from its position
- The agents share the same underlying model but receive fundamentally different framing that activates different patterns of reasoning

The architecture does not claim to eliminate the harmonization problem — it cannot — but it is structured to resist it.

### Why Explicit Statements of Limits

Each advocate is required to read a "Statement of Limits" at the start of Round 1. This is a methodological constraint, not a rhetorical device. The Statement of Limits forces each advocate to articulate:
- What their discipline can genuinely establish
- What their discipline cannot establish on its own
- Where they depend on other disciplines

This has two effects: (1) it disciplines the agent against overreach — the Biblical Scholar should not be building ecclesiology from exegetical findings alone — and (2) it creates the conditions for genuine cross-disciplinary engagement, since each advocate knows what they need from the others.

### Why Structured Citations

LLMs generate plausible-sounding citations at a rate that makes any unchecked debate record unreliable. The citation protocol (`[CLAIM]`, `[SOURCE]`, `[ARGUMENT]`, `[CONFIDENCE]`) serves two purposes: it makes the model's confidence explicit at the point of generation, and it creates a structured format that can be parsed by an automated verification pipeline. A LOW confidence tag with no page number is more honest and more useful than a HIGH confidence tag with a fabricated page number — the system prompt makes this explicit.

### Why Citation Accountability Loops Back to the Advocate

When the verification pipeline flags a citation as fabricated or problematic, that finding must reach the advocate who made the claim — not just the moderator. Starting in Round 2, each advocate receives a `[CITATION_CORRECTIONS]` block in their prompt listing any verified problems with their prior citations. They must respond with a structured `[CITATION_RESPONSE]` block before their substantive content, taking one of three positions: `WITHDRAW` (claim removed from the record), `QUALIFY` (claim narrowed), or `DEFEND` (claim maintained, optionally with new sourcing). This creates a feedback loop: citation quality in one round has direct consequences in the next. Withdrawn and retracted claims are tracked in a persistent registry and excluded from Round 4 context summaries.

### Why the Synthesis Must Name Irreconcilable Tensions

A synthesis that maps convergence and divergence toward a coherent narrative is almost as misleading as no synthesis at all — it creates the impression that the disciplines have a unified answer when they may not. The moderator synthesis is structured to require a section on *irreconcilable tensions*: positions the disciplines hold that cannot both be true, with an explicit statement of the extra-disciplinary commitment that would be required to resolve the tension. If there are no genuinely irreconcilable tensions, the moderator must say so explicitly. The synthesis also identifies *arguments past each other* — cases where disciplines appeared to engage but were actually answering different questions — which are distinct from genuine disagreements.

### Why the Debate Does Not Produce a Verdict

The moderator synthesizes but does not adjudicate. The Round 4 closing arguments ask each advocate to address what "faithful practice" requires — not who wins. This is deliberate. The goal is a high-quality canonical record of how the disciplines engage the question, not a machine-generated verdict on a contested theological question.

---

## The Six Advocates

| # | Advocate | Disciplinary Lead | Tagline |
|---|----------|------------------|---------|
| 1 | The Biblical Scholar | Exegesis and canonical theology | *"The texts say more than the debate has heard — and less than both sides claim."* |
| 2 | The Reception Historian | Reception history and history of interpretation | *"What the church has done with these texts is itself a form of evidence."* |
| 3 | The Hermeneutician | Philosophy of interpretation | *"Everyone in this debate has a hermeneutic. Most of them haven't examined it."* |
| 4 | The Systematic Theologian | Ecclesiology, ministry, and authority | *"The debate about who can lead assumes we know what the church is."* |
| 5 | The Pastoral Theologian | Pastoral and practical theology | *"Doctrine is not tested in the library. It is tested in the lives of people."* |
| 6 | The Social and Cultural Analyst | Social anthropology and sociology of religion | *"Every reading happens inside a social world. The question is whether you know which one."* |

Plus:

| # | Role | Function |
|---|------|----------|
| 7 | The Moderator/Fact-Checker | Verification, synthesis, procedural management — no advocacy |

### Agent Identities and Disciplinary Boundaries

**The Biblical Scholar** works the full canon in the original languages. The agent is trained to resist the gravitational pull of the "Pauline problem texts" and insist on giving the Old Testament its full canonical weight — Deborah, Huldah, and the women named in Romans 16 are not treated as marginal. The agent engages disputed terms (*authentein*, *kephale*, *ezer*, *diakonos*, *prostatis*, *apostolos*) as genuine lexical problems requiring lexical evidence. It is not assigned an egalitarian or complementarian position; it is assigned an obligation to say what the texts actually establish, including where the finding is inconclusive.

**The Reception Historian** does not ask what texts mean — it asks what they have been made to mean. What have the restriction texts authorized and prohibited across the history of the church? How have interpretive traditions been shaped by forces other than pure exegesis — political interests, social pressures, doctrinal priorities, power arrangements? The agent brings specific examples: the patristic period, the medieval church, Reformation debates, twentieth-century evangelical shifts. It is specifically prompted to resist both the move that treats reception history as definitive evidence of correct reading, and the move that dismisses it as irrelevant.

**The Hermeneutician** asks the methodological questions that every other advocate assumes but rarely defends. What hermeneutical principle governs the move from first-century instruction to twenty-first century application? Is the creation-order argument in 1 Timothy 2:13 applied consistently elsewhere, or selectively? The agent is assigned the role of identifying inconsistency, interrogating method, and asking what hermeneutical principle is being used — not to adjudicate between readings but to expose where the principle itself requires defense.

**The Systematic Theologian** asks what doctrines are actually at stake beneath the surface of the debate. The question of who holds authority in the church requires a doctrine of the church, of ministry, and of authority. Both sides of the debate imply ecclesiologies — and those ecclesiologies can be interrogated. The agent brings new creation ecclesiology to bear and asks what the church's nature as an eschatological community implies for its governance structures.

**The Pastoral Theologian** brings fieldwork: what actually happens in communities formed by restriction versus permission? The agent draws on case studies, narrative accounts, and empirical research on the effects of women's exclusion from church leadership — on women, on congregations, and on mission. It is specifically prompted to resist two failure modes: ignoring human cost entirely, and treating human cost as the only thing that matters. Pastoral evidence is real data; it is not the final criterion.

**The Social and Cultural Analyst** brings two lenses: (1) ancient cultural anthropology applied to the first-century Mediterranean world — honor/shame dynamics, *haustafeln*, patronage networks, the social significance of public speech by women in Greco-Roman contexts; and (2) contemporary sociology of religion — how institutional interests, organizational dynamics, and cultural context shape church practice today. The agent is prompted to resist its own most common failure mode: explaining everything sociologically and thereby adjudicating nothing.

### The Statements of Limits

Each advocate reads their Statement of Limits at the start of Round 1. These are core to the design and are reproduced in `system_prompts.json`.

**Biblical Scholar:** Exegesis can establish what texts mean within their canonical context. It cannot determine how much weight a first-century cultural situation should carry in a twenty-first century church; build an ecclesiology from its findings without assistance from systematic theology; or adjudicate between two exegetically defensible readings without a hermeneutical principle that itself requires defense.

**Reception Historian:** Reception history can show that a reading has a history, has served certain interests, and has changed over time. It cannot show that a reading is therefore wrong. It cannot establish what the texts mean or what doctrine the church should build from them.

**Hermeneutician:** Hermeneutics can expose inconsistency and interrogate method. It cannot determine which hermeneutical approach is ultimately correct — that requires theological and philosophical commitments that go beyond hermeneutics itself.

**Systematic Theologian:** Systematics can clarify what is at stake and expose hidden assumptions. It cannot determine the meaning of specific texts or the weight of historical evidence without the biblical scholar and reception historian.

**Pastoral Theologian:** Pastoral theology can show that a position has harmful effects or good fruit, but fruitfulness is not the final criterion for theological truth. It cannot establish what Scripture requires or what the doctrine actually is.

**Social and Cultural Analyst:** Social analysis can show that a reading emerged in a particular social context and serves particular social interests. It cannot show that the reading is therefore wrong. If all readings are socially conditioned, that fact alone cannot adjudicate between them.

---

## Debate Structure

### Rounds and Word Counts

| Round | Purpose | Word Count |
|-------|---------|------------|
| Pre-debate | Position papers + source registers | Up to 1,500 words per advocate |
| Round 1 | Opening statements: disciplinary findings on the anchor text | 600–800 words per advocate (incl. 150-word Statement of Limits) |
| Round 2 | Cross-disciplinary examination — directed challenges | 400 words/question, 300 words/response |
| Round 3 | Seven required texts — all advocates engage each one | 1,750 words total per advocate (min 150 per text) |
| [Synthesis] | Moderator synthesis — structured map with four required sections | 300–400 words |
| [Synthesis Response] | Each advocate responds to the moderator synthesis | 100 words max per advocate |
| Round 4 | Closing arguments: what does faithful practice require? | 600–750 words per advocate |

**Note on word counts:** `[CITATION_RESPONSE]` blocks (see below) are exempt from all word limits. They are procedural overhead, not substantive argument.

### The Seven Required Texts

Round 3 is structured around seven texts that both sides of this debate must engage. Every advocate addresses all seven in a single response (not one text at a time) — the advocate needs to see all seven to plan their allocation. Minimum 150 words per text.

| Text | Passage | Core Dispute |
|------|---------|-------------|
| **1. Genesis 2:18–23** | The *ezer* and creation sequence | Does the ordering of creation establish a hierarchy of authority? What does *ezer* actually establish — and what does it not? How does the ANE context affect the creation-sequence-implies-hierarchy argument? |
| **2. 1 Timothy 2:11–14** | The central prohibition | What does *authentein* mean and why does the decision matter? Does Paul's appeal to creation in v.13 make the prohibition transcultural? Is that hermeneutical principle applied consistently elsewhere? |
| **3. 1 Corinthians 11:2–16** | Women praying and prophesying | Paul assumes women pray and prophesy in the gathered assembly. What does this establish? What is the head-covering argument actually doing? Does *kephale* mean source or authority? |
| **4. 1 Corinthians 14:33–35** | Women commanded to be silent | Is this a Corinthian slogan that Paul refutes in v.36 (Peppiatt), a restriction on disruptive questioning, or a universal Pauline command? How do we hold this text alongside 1 Corinthians 11:5? |
| **5. Galatians 3:28** | Neither male nor female | Is this soteriological only, or does it carry ecclesiological weight? Does "no male and female" quote Genesis 1:27, and what follows from that quotation? What determines how much ecclesiological weight to assign? |
| **6. Romans 16 (selected)** | Phoebe, Priscilla, Junia | Phoebe as *diakonos* and *prostatis*; Junia as *en tois apostolois*; Priscilla named before Aquila. What do these designations establish? What is the burden of proof for reading them restrictively rather than expansively? |
| **7. Judges 4–5 and 2 Kings 22** | Deborah and Huldah | What kind of authority do these women actually exercise? What does their presence in the canon establish — precedent, exception, or something that resists that binary? How do we decide? |

### Round 2 Cross-Examination Pairings

Each advocate poses a directed challenge to one other advocate. The pairings are designed to create genuine methodological tensions — not rhetorical disputes but substantive disagreements between disciplines about what counts as evidence and how arguments should work.

| Questioner | Target | Methodological Tension |
|-----------|--------|----------------------|
| Hermeneutician | Biblical Scholar | The gap between lexical evidence and hermeneutical principle: exegesis can establish a range of defensible readings, but it cannot choose between them without a hermeneutical principle that the biblical scholar has not yet defended. |
| Biblical Scholar | Reception Historian | The relationship between the history of a reading and its validity: does a long history of misreading — if that is what it was — make the correct reading more or less accessible now? |
| Reception Historian | Social/Cultural Analyst | The limits of social-location analysis: if social context shapes all reading, can any reading genuinely transcend its social location? Or does this argument dissolve itself? |
| Social/Cultural Analyst | Systematic Theologian | The social conditioning of first principles: systematic theology claims to reason from foundations, but those foundations were articulated in specific social contexts. Has the systematician accounted for this? |
| Systematic Theologian | Pastoral Theologian | The relationship between fruitfulness and truth: pastoral evidence of harm or flourishing is real data — but fruitfulness is not the criterion for theological truth. What exactly is the pastoral theologian's argument? |
| Pastoral Theologian | Hermeneutician | The gap between method and practice: hermeneutical rigor is valuable, but churches must make decisions now, with real people, under the constraints of real traditions. At what point does methodological scruple become pastoral evasion? |

### Speaking Order

- **Rounds 1, 2, 3:** Advocates 1 → 6 (Biblical Scholar through Social/Cultural Analyst)
- **Round 4:** Advocates 6 → 1 (reversed — the Social/Cultural Analyst speaks first, the Biblical Scholar last)

The reversed order in Round 4 gives the disciplines that were asked to lead with the most empirical claims the opportunity to close, and gives the exegetical discipline the final word on what the texts establish after hearing all other perspectives.

---

## System Architecture

### Core Design Decisions

**Separation of concerns — independent agents, not personas.** Each advocate is a fully independent agent. They do not share a conversation or context window with other advocates. They receive other advocates' outputs as compiled documents — the same way a real debate participant reads a position paper, not a live conversation feed.

**Fresh calls, not persistent conversations.** Each advocate makes a single API call per round with a carefully constructed input: system prompt + compiled prior outputs + round prompt. This gives total control over what the agent sees. Nothing is hidden; nothing accumulates from prior reasoning within a round.

**Disciplinary identity over harmonization.** The greatest risk in a single-LLM debate is that all positions harmonize toward the model's implicit priors. Separate agents with strong disciplinary system prompts resist this. The Biblical Scholar and the Social Analyst should disagree — that tension is the point. Each round prompt includes a re-anchoring instruction: *"You are the [X]. Review your Statement of Limits. Respond from your discipline, not as a generalist."*

**Structured citation protocol.** Every factual claim is tagged at point of output using a structured format. A dedicated verification agent (separate from the moderator) processes these tags with web search. Claims it cannot resolve are routed to a human auditor via a structured worksheet.

**Persistent canonical record.** Every round output and moderation report is compiled into a canonical debate record that grows across the debate. This record — not raw conversation history — is what each agent receives as context for subsequent rounds. The record is rebuilt from disk after each round via `document_compiler.py`.

**Context compression for Round 4.** By Round 4, the full canonical record exceeds 40,000 words. Rather than injecting the full record, each advocate receives a four-section compressed context: (1) their own prior outputs in full, (2) Sonnet-generated structured summaries of the other five advocates (200–300 words each, structured as CORE CLAIMS / KEY DISAGREEMENT / UNRESOLVED TENSION / POSITION SHIFTS), (3) the moderator synthesis and synthesis responses, and (4) the claim ledger — a structured cross-round tracker of the most contested arguments, their citation status, and how each discipline engaged them. This cuts context by ~60% while preserving the advocate's own voice and a precise picture of where unresolved tensions sit.

**Disciplinary boundary enforcement.** The moderator fact-check report includes a DISCIPLINARY BOUNDARY REPORT after each round. The moderator checks each advocate's outputs against their Statement of Limits and flags explicit overreach — a Biblical Scholar drawing a doctrine of ministry from lexical findings alone, a Pastoral Theologian treating harm evidence as decisive without acknowledging limits. Disciplinary sharpness is not flagged; only conclusions that cross into another discipline's territory without acknowledgment.

**Explicit uncertainty.** Both advocates and the moderator are required to express uncertainty. "I cannot verify this citation" and "my discipline cannot establish this" are required outputs, not failures.

### Technical Architecture

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

### Model Selection

Quality is the priority; cost is managed by matching model capability to round demands:

| Round | Model | Rationale |
|-------|-------|-----------|
| Pre-debate position papers | Sonnet 4.6 | Structured output from detailed prompts |
| Round 1 openings | Sonnet 4.6 | Constrained, prompted, single-discipline output |
| Round 2 cross-examination | **Opus 4.6** | Requires understanding another discipline's argument well enough to challenge it at the methodological level |
| Round 3 text responses | Sonnet 4.6 | Short, constrained per-text responses with word limits |
| Moderator fact-checking | Sonnet 4.6 | Pattern matching against training knowledge + structured verification input |
| Moderator synthesis | **Opus 4.6** | Must hold six disciplines' findings simultaneously and map genuine convergence and divergence |
| Synthesis responses | Sonnet 4.6 | 100-word constrained responses |
| Round 4 closing arguments | **Opus 4.6** | Deep reasoning, cross-disciplinary integration, ecclesial conclusions — the most demanding cognitive task in the debate |
| Citation verifier | Sonnet 4.6 | Bibliographic verification with web search — pattern matching more than reasoning |
| Context summarization (Round 4 prep) | Sonnet 4.6 | Summarizing advocate outputs for context compression |

**Temperature settings:**
- Advocates: 0.75 (disciplinary character without incoherence)
- Moderator and verifier: 0.25 (consistency over creativity)
- Conductor language tasks (formatting, compilation, summarization): 0.30

### Context Management Strategy

Each round's human message is constructed as:

```
[shared_context — debate rules, citation protocol, Alderwood anchor text full PDF]

---

[canonical_record_so_far — all prior round outputs, compiled Markdown]

---

[round_prompt — specific instructions for this round, with {TEMPLATE_VARS} filled]
```

For Round 4, the canonical record section is replaced with the compressed context from `context_packager.py`:

```
[own prior outputs — all rounds, full text]

===

[other advocates — structured 200–300 word summaries of each:
 CORE CLAIMS / KEY DISAGREEMENT / UNRESOLVED TENSION / POSITION SHIFTS]

===

[moderator synthesis + all synthesis responses]

===

[claim ledger — contested arguments across rounds 1–3,
 with citation status, per-discipline responses, and load-bearing flags]
```

Template variable injection uses two mechanisms:
- `{CURLY_BRACE_VARS}` for per-round variables like `{ADVOCATE_DISPLAY_NAME}`, `{DISCIPLINARY_LEAD}`, `{TARGET_ADVOCATE}` — substituted via regex that only matches `ALL_CAPS` patterns, leaving JSON examples untouched
- `[BRACKET_VARS]` for structural substitutions in the Round 3 texts block

---

## Citation Protocol

All advocate outputs must follow this tagging format for factual claims:

```
[CLAIM: brief statement of the claim being made]
[SOURCE: Author, Title, Publisher, Year, page if available]
[ARGUMENT: the specific argument being attributed to this source]
[CONFIDENCE: HIGH / MEDIUM / LOW — advocate's own assessment]
```

**Confidence levels:**
- **HIGH** — confident the author, work, and argument are accurately stated
- **MEDIUM** — confident about the author and work but less certain about the specific argument or page
- **LOW** — working from general knowledge of the scholar's position; cannot confirm specifics

Advocates are explicitly instructed not to fabricate page numbers. A LOW confidence tag with no page number is treated as more honest and more useful than a HIGH confidence tag with a fabricated number. The system prompt states this directly.

**Example:**
```
[CLAIM: authentein carried a negative or domineering connotation in first-century Greek]
[SOURCE: Philip Payne, Man and Woman, One in Christ, Zondervan, 2009]
[ARGUMENT: Payne surveys pre-New Testament and contemporary uses of authentein and argues the
negative or domineering sense is better attested in the relevant period than the neutral
"to have authority" reading favored by complementarian translations]
[CONFIDENCE: HIGH]
```

---

## Citation Response Protocol

Starting in Round 2, advocates receive a `[CITATION_CORRECTIONS]` block in their prompt listing any verified problems with their prior citations. Before writing substantive content, they must respond to each flagged citation using this structured format:

```
[CITATION_RESPONSE: {claim_id}]
[CORRECTION_RECEIVED: FABRICATION_RISK / HARD_CORRECTION / SOFT_FLAG]
[ADVOCATE_POSITION: WITHDRAW / QUALIFY / DEFEND]
[REVISED_CLAIM: ...]          ← required if QUALIFY or DEFEND
[REVISED_SOURCE: ...]         ← required if DEFEND with new sourcing
[REVISED_CONFIDENCE: ...]     ← required if QUALIFY or DEFEND
[RESPONSE_NOTE: one sentence]
[DOWNSTREAM_STATUS: ACTIVE / RESTRICTED / RETRACTED]
```

**Rules enforced at parse time:**
- `WITHDRAW` → `DOWNSTREAM_STATUS: RETRACTED`. The claim is removed from the debate record and excluded from all future context.
- `QUALIFY` → `DOWNSTREAM_STATUS: RESTRICTED`. Revised claim must be narrower than the original.
- `DEFEND` without new source → `REVISED_CONFIDENCE` forced to `LOW`, `DOWNSTREAM_STATUS: RESTRICTED`.
- `DEFEND` with new source → subject to immediate re-verification. `DOWNSTREAM_STATUS: ACTIVE` pending result.

Only `FABRICATION_RISK` and high-impact `NEEDS_HUMAN_REVIEW` corrections require a response. Low-impact partial verifications do not.

**Retracted claims** are tracked in `retracted_claims.json` and excluded from the Round 4 context summaries generated for each advocate. An advocate cannot use a retracted claim in their closing argument — it will not appear in the summary of their position that other advocates receive.

`[CITATION_RESPONSE]` blocks do not count toward word limits.

---

## Citation Verification System

A four-pass architecture separates automated verification from human judgment. The goal is not to eliminate hallucination — that is not achievable — but to make it visible, route it to human resolution, and feed findings back to the advocates who made the claims.

Every citation gets at least two automated checks. Suspicious citations get a third. Unresolved citations reach a human auditor.

### Pass 1 — Training Knowledge Triage

A dedicated Sonnet 4.6 call with no web search. All citations are processed in batches of 5. For each citation, the verifier assesses from training knowledge:
- Is this author a real scholar working in this field?
- Does this title plausibly exist with this publisher and year?
- Does the attributed argument direction align with what is known about this scholar's position?

Produces a `suspicion_level` (LOW / MEDIUM / HIGH) and flags obvious fabrications cheaply, without web search. Honest about the limits of training knowledge — a citation can pass this check and still be wrong in its specifics.

### Pass 2 — Bibliographic Search (All Citations)

Every citation — regardless of Pass 1 outcome — receives one targeted web search. The verifier searches for the author name + title + publisher and looks for a publisher page, library catalog entry, Amazon listing, or academic review confirming the work exists.

One citation per API call, `max_turns=3`. Produces `CONFIRMED / UNCONFIRMED / CONFLICTING` for each citation. A secondhand corroboration (review, publisher description) is reported as corroborating evidence, not verification of the specific argument.

### Pass 3 — Deep Investigation (Suspicious Only)

Citations flagged `HIGH` suspicion in Pass 1, or `UNCONFIRMED / CONFLICTING` bibliographically in Pass 2, receive deep investigation. One citation per API call, up to 3 searches, `max_turns=8`. Checks:
1. Bibliographic existence (with different search terms if Pass 2 failed)
2. Author's known position on the specific claim (blog posts, interviews, secondary citations)
3. Whether other scholars dispute or confirm the argument direction

### Verification Verdict Types

| Verdict | Meaning |
|---------|---------|
| `LIKELY_ACCURATE` | Bibliographic confirmed (Pass 2) + Pass 1 direction consistent |
| `LIKELY_ACCURATE_BUT_CONTESTED` | Confirmed but the scholarly position is genuinely disputed |
| `PARTIALLY_VERIFIED` | Book/author confirmed; argument attribution unclear |
| `NEEDS_HUMAN_REVIEW` | Could not resolve after all automated passes |
| `FABRICATION_RISK` | Pass 1 HIGH suspicion, or Pass 3 found contradicting evidence |

Page numbers are never verified by automated means — all page numbers are treated as unverifiable unless found in a freely accessible online source.

### Pass 4 — Human Audit Worksheet

Claims the automated pipeline could not resolve (`NEEDS_HUMAN_REVIEW` or `FABRICATION_RISK`) are compiled into a structured Markdown worksheet. The worksheet pre-sorts claims by priority (fabrication risks first) and attaches the automated findings from all three passes. A human auditor assigns one of five verdicts per claim:

| Verdict | Meaning |
|---------|---------|
| **CONFIRMED** | Found in the original source — exact or substantially accurate |
| **CONFIRMED_INDIRECT** | Corroborated by reliable secondary evidence (author's blog, peer review, known position) — with structured fields for evidence type, source URL, and confidence |
| **PLAUSIBLE_BUT_UNCONFIRMED** | Consistent with known content; no contradicting evidence found; primary source not accessed |
| **LIKELY_FABRICATED** | Evidence contradicts the claim or no trace found in the expected source |
| **CANNOT_DETERMINE** | Insufficient access to resolve |

Each claim also receives:
- An **impact assessment** (load-bearing, supporting, or illustrative — what happens to the argument if this citation is wrong?)
- An **action recommendation** (accept as-is, qualify, flag for moderator, or remove)

Completed worksheets are compiled into moderator input files. The moderator fact-check report is generated with the verification results injected directly into the prompt, not as a separate document the moderator "reads."

The final debate summary (generated after Round 4) includes an aggregated citation audit report: total citations, verdicts by category, fabrication risk count, claims awaiting human review.

---

## Repository Structure

```
/
├── README.md                          # This file
├── debate-framework.md                # Full debate design (V4 — the canonical plan)
├── system_prompts.json                # All agent system prompts + round prompt templates
│                                      # (Pass this file alongside the README to reviewers)
├── scripts/
│   ├── conductor.py                   # Main orchestration — runs rounds sequentially
│   ├── document_compiler.py           # Compiles round outputs into canonical record
│   ├── context_packager.py            # Builds per-advocate input context for each round
│   ├── citation_extractor.py          # Parses [CLAIM][SOURCE][ARGUMENT][CONFIDENCE] blocks
│   ├── citation_verifier.py           # Automated verification agent (web search)
│   └── audit_worksheet.py             # Generates human audit worksheets
├── outputs/                           # Generated content (real runs)
│   ├── predebate/                     # Position papers — one .md per advocate
│   ├── round_1/                       # One .md per advocate + moderation_report.md
│   │                                  # + round_digest.md
│   ├── round_2/                       # {advocate}_question.md + {advocate}_response.md
│   │                                  # + moderation_report.md + round_digest.md
│   ├── round_3/                       # One .md per advocate + moderation_report.md
│   │                                  # + round_digest.md
│   ├── synthesis/                     # moderator_synthesis.md + {advocate}_response.md
│   │                                  # + claim_ledger_r2.md (after Round 2)
│   │                                  # + claim_ledger.md (after Round 3 — canonical for Round 4)
│   │                                  # + final_summary.md (after Round 4)
│   ├── round_4/                       # One .md per advocate + moderation_report.md
│   ├── canonical_record.md            # Full compiled debate — rebuilt after each round
│   ├── audit_log.jsonl                # Every API call: label, model, messages, response, tokens
│   └── retracted_claims.json          # Persistent registry of RETRACTED citation claims
├── verification/
│   ├── citations/                     # round_{N}_citations.json — extracted citation blocks
│   ├── verifications/                 # round_{N}_verifications.json — merged 3-pass verdicts
│   ├── audit/                         # round_{N}_worksheet.md — human audit worksheets
│   └── moderator_input/               # round_{N}.md — verification summary for moderator
├── alderwood_text.txt                 # Extracted anchor text (generated from PDF)
└── outputs/tests/                     # Test run outputs (timestamped, isolated)
    └── {YYYY-MM-DD_HHMMSS}/           # Same structure as outputs/
```

**Note for reviewers:** The primary artifacts for evaluating the approach are `system_prompts.json` (all agent identities, round prompt templates, pairing data, and required texts) and this README. The `scripts/` directory contains the orchestration code that constructs inputs, manages state, and calls the API.

---

## Known Limitations and Risks

### LLM Hallucination

The most serious risk. LLMs generate plausible-sounding citations that may be inaccurate, misattributed, or entirely fabricated. The citation verification system (automated verifier + human audit worksheet) makes this visible and routes unresolved claims to human judgment — it does not eliminate the problem. **All citations in the final canonical record must be independently verified before the record is treated as authoritative.** Estimated human audit time: 10–15 hours across the full debate.

The citation confidence tags are a partial mitigation. The system is explicit that LOW confidence is honest and HIGH confidence is a claim that should be checked. The verifier treats all page numbers as unverifiable by automated means.

### Disciplinary Drift

Even with strong system prompts, advocates may drift from their disciplinary identity across long runs — the Biblical Scholar may start arguing like the Pastoral Theologian by Round 4. Mitigations built into the architecture: fresh API calls each round (no accumulated conversation context), re-anchoring instructions in every round prompt, and each advocate's own prior outputs given more prominence than the compiled record of other advocates. The moderator's DISCIPLINARY BOUNDARY REPORT (generated after each round) flags explicit overreach — claims that step into another discipline's territory without acknowledgment. How well this combination of constraints works in practice is an open empirical question.

### Harmonization Pressure

All agents are ultimately the same underlying model. Despite separate contexts and system prompts, they share the same training priors. The most genuinely contested questions — where the model has a strong implicit lean — will show harmonization pressure. The system prompts build genuine methodological tension between disciplines (the Reception Historian and the Hermeneutician should disagree about whether the history of a reading is evidence about the reading's validity), but whether the outputs actually reflect that tension or resolve it prematurely is something a reviewer would need to assess by reading the canonical record.

### Citation Confidence Overstatement

LLMs express more confidence about citations than is warranted, especially for page numbers and specific argument attributions. The `[CONFIDENCE]` tag surfaces this; the shared context explicitly instructs advocates to default to MEDIUM or LOW for page numbers and to HIGH only for author, work, and general argument direction. The automated verifier marks all page numbers as UNVERIFIABLE by default.

### Context Window and Round 4 Compression

The canonical debate record grows to approximately 40,000–60,000 words by Round 4. The context compression strategy (own outputs in full + structured summaries of other advocates + claim ledger) is a practical necessity. The quality of the Round 4 arguments depends significantly on the quality of those summaries. Each summary is structured into four required sections — CORE CLAIMS, KEY DISAGREEMENT, UNRESOLVED TENSION ENTERING ROUND 4, POSITION SHIFTS — to prevent the common failure mode of thematic compression that loses argument structure. The claim ledger provides a cross-round tracker of the most contested specific claims. How faithfully these represent the actual debate is something the compressed context itself should be checked against when reviewing a run.

### What It Cannot Produce

This system cannot produce scholarship. It can produce a structured record of how LLM agents, disciplined by carefully designed prompts, engage a contested theological question. That record may be useful as a starting point, as a map of the argumentative terrain, or as a demonstration of what multi-disciplinary engagement looks like when it is structured well. It is not a substitute for human scholars doing this work.

---

## What This System Can and Cannot Produce

**What it can produce:**
- A structured, disciplinarily organized engagement with a contested theological question
- A map of where the disciplines converge and diverge
- Well-formed arguments from multiple disciplinary perspectives, with explicit claims and sources
- A citation record that, after human audit, provides a partially verified bibliography
- A demonstration of the architecture for application to other contested questions

**What it cannot produce:**
- Authoritative scholarship — all claims require independent verification
- Genuine disagreement between agents that is not ultimately traceable to prompt differences
- Arguments that go beyond the model's training data on this question
- A resolution to the underlying theological question

**What makes this run valuable:**
The value is in the structure and the process, not the verdict. A well-executed run produces a canonical record that maps the argumentative terrain of a hard question with more disciplinary rigor and more explicit uncertainty than most popular treatments of the same question. Whether that map is accurate — whether the disciplinary voices are genuinely distinct, whether the citations are reliable, whether the arguments engage each other — is what a review should assess.

---

## Usage Guide

### Setup

**1. Create a virtual environment and install dependencies:**
```bash
python3 -m venv .venv
.venv/bin/pip install anthropic python-dotenv rich tenacity pymupdf
```

**2. Create a `.env` file at the project root:**
```
ANTHROPIC_API_KEY=sk-ant-...
```

**3. Extract the anchor text (required before any run):**
```bash
.venv/bin/python -c "
import fitz
doc = fitz.open('What-Alderwood-Teaches-about-Women-in-Church-Leadership-Finalized.pdf')
open('alderwood_text.txt', 'w').write(''.join(p.get_text() for p in doc))
"
```
This creates `alderwood_text.txt`, which the conductor injects into every agent's context automatically.

---

### Running the Debate

All commands run from the project root:

```bash
.venv/bin/python scripts/conductor.py [options]
```

**Run a specific round:**
```bash
.venv/bin/python scripts/conductor.py --round predebate
.venv/bin/python scripts/conductor.py --round 1
.venv/bin/python scripts/conductor.py --round 2
.venv/bin/python scripts/conductor.py --round 3
.venv/bin/python scripts/conductor.py --round synthesis
.venv/bin/python scripts/conductor.py --round 4
```

**Run all rounds sequentially:**
```bash
.venv/bin/python scripts/conductor.py --all
```

The conductor validates prerequisites before each round — it will error if you attempt to run Round 2 before Round 1 is complete, rather than silently producing bad output.

---

### Flags

| Flag | Effect |
|------|--------|
| `--test` | Write all outputs to `outputs/tests/{timestamp}/` instead of `outputs/`. Nothing touches the real outputs directory. |
| `--fast` | Cap each API call at 600 output tokens and inject a brevity note. Use for architecture testing when output quality doesn't matter — roughly 25% of normal cost. |
| `--advocate {id}` | Run only one advocate. Useful for prompt testing. Moderation is skipped (needs all 6); verification and citation extraction still run. |
| `--skip-human-review` | Skip the human audit pause after each round. The automated verifier still runs and the worksheet is still generated for later review. Unreviewed claims are flagged to the moderator. |
| `--dry-run` | Print assembled prompts without calling the API. Useful for verifying template variable injection. |
| `--force` | Re-run even if output files already exist. Without this flag, the conductor skips existing files, allowing partial runs to be resumed. |

**Flags can be combined:**
```bash
# Architecture test — fast, isolated, no pause
.venv/bin/python scripts/conductor.py --round 1 --test --fast --skip-human-review

# Single advocate prompt test
.venv/bin/python scripts/conductor.py --round 1 --advocate biblical_scholar --test --fast

# Full round with verification, no human pause
.venv/bin/python scripts/conductor.py --round 1 --skip-human-review

# Real run
.venv/bin/python scripts/conductor.py --round 1
```

---

### Advocate IDs

| ID | Display Name |
|----|-------------|
| `biblical_scholar` | The Biblical Scholar |
| `reception_historian` | The Reception Historian |
| `hermeneutician` | The Hermeneutician |
| `systematic_theologian` | The Systematic Theologian |
| `pastoral_theologian` | The Pastoral Theologian |
| `social_cultural_analyst` | The Social and Cultural Analyst |

---

### Output Structure

**Real runs** write to `outputs/`:
```
outputs/
  predebate/          {advocate_id}.md per advocate
  round_1/            {advocate_id}.md per advocate + moderation_report.md + round_digest.md
  round_2/            {advocate_id}_question.md + {advocate_id}_response.md
                      + moderation_report.md + round_digest.md
  round_3/            {advocate_id}.md per advocate + moderation_report.md + round_digest.md
  synthesis/          moderator_synthesis.md + {advocate_id}_response.md per advocate
                      + claim_ledger_r2.md  (claim ledger after Round 2)
                      + claim_ledger.md     (updated claim ledger after Round 3 — used in Round 4)
                      + final_summary.md    (generated after Round 4)
  round_4/            {advocate_id}.md per advocate + moderation_report.md + round_digest.md
  canonical_record.md Full compiled debate record — rebuilt after each round
  audit_log.jsonl     Every API call logged: label, model, temperature, full messages, response, tokens
  retracted_claims.json Persistent registry of RETRACTED citation claim IDs

verification/
  citations/          round_{N}_citations.json — extracted citation blocks per round
  verifications/      round_{N}_verifications.json — merged 3-pass verifier verdicts per round
  audit/              round_{N}_worksheet.md — human audit worksheets
  moderator_input/    round_{N}.md — verification summary injected into moderator prompt
```

**Test runs** (`--test`) write to `outputs/tests/{timestamp}/` with the same structure.

**Round digests** are brief (~200 word) summaries printed to the terminal and saved to disk after each full round — an overview of what the round established and where the key tensions are.

**The final summary** (generated after Round 4) includes: a narrative summary of the debate's arc, the major points of convergence and divergence, and an aggregated citation audit report showing total citations, verdicts by category, and unresolved claims.

---

### Human Audit Workflow

After each round (without `--skip-human-review`), the conductor pauses if any citations need review:

1. The automated verifier runs and assigns verdicts to all citations
2. Claims flagged as `FABRICATION_RISK` or `NEEDS_HUMAN_REVIEW` are written to `verification/audit/round_{N}_worksheet.md`
3. The conductor prints the worksheet path and pauses for input
4. Open the worksheet, complete the verdict checkboxes for each claim
5. Press Enter to continue — the moderator runs with the completed audit results injected into its prompt

**If you skip human review** (`--skip-human-review`): the worksheet is still generated for async reference. The moderator receives the automated verdicts with a note that human audit was skipped. `FABRICATION_RISK` claims are surfaced to the moderator as explicit corrections.

---

### Recommended Run Order

For a full high-quality debate:

1. **Test single advocate**: `--round 1 --advocate biblical_scholar --test --fast`
   Verify prompt quality and citation formatting before committing to a full run.

2. **Test full Round 1**: `--round 1 --test --skip-human-review`
   Check that all 6 voices are disciplinarily distinct and the moderation report is substantive.

3. **Run pre-debate** (optional but recommended): `--round predebate`
   Position papers give advocates richer context for Round 1 and produce a source register useful for verifying Round 1 citations.

4. **Run Round 1 for real**: `--round 1`
   Complete the human audit before proceeding to Round 2.

5. **Continue rounds 2 → synthesis → 4** sequentially, completing the human audit after each round.

---

## Project Phases

### Phase 1 — Single High-Quality Run (current)
Run this debate once at the highest quality achievable. The conductor script orchestrates API calls sequentially, the citation verification system catches fabrications, and a human auditor resolves what the automated verifier cannot. The canonical debate record is the deliverable.

### Phase 2 — Reusable Framework
Make the system topic-agnostic. Given a question and a set of disciplines, generate: the motion, the advocate identities and system prompts, the required texts or evidence, and the cross-examination pairings. This is primarily a prompt-generation problem — Claude generating the debate configuration, which then drives the same conductor script.

### Phase 3 — Web Tool (Beta)
A web application wrapping the conductor. Users select from curated topics, the system generates the debate configuration and runs it. Key challenges: cost management (a full debate run is expensive), job queue (runs take time), and output presentation (the canonical record must be readable). Limited to pre-curated topics initially.

### Enhancement Options
- **Web search for advocates:** Allow advocates to use web search during Round 2 cross-examination. Adds citation richness; increases cost significantly.
- **Vector store for source material:** Load key books/articles into a vector database for the verification pipeline. Dramatically improves citation accuracy; high setup cost.
- **Iterative position refinement:** After Round 2, allow each advocate one revision of their Round 1 opening. Models intellectual responsiveness to challenge.
- **Multi-run consensus:** Run the full debate 3× with different temperatures and compare. Flags where conclusions are model-stable versus temperature-sensitive.
- **Human-in-the-loop moderation:** Route flagged claims to a human before the moderation report is finalized. Highest accuracy; requires active participation during the run.
- **Different base models per advocate:** Assign a different model family to each advocate to reduce harmonization pressure. Currently not implemented; would require non-Anthropic models.

---

*Project initialized: 2026 | Framework version: 4.1 | Status: Fully implemented — ready for first full run*
