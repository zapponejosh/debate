# Post-Debate Audit Plan

## Context
After all four rounds + synthesis complete, a Claude Opus agent will be given this plan as a prompt along with access to all output and verification files. The agent will execute the audit autonomously and return a structured report. The plan must therefore be written as executable instructions — precise file references, clear scoring criteria, and specific output format requirements.

---

## Files the Agent Should Read

**Canonical debate record:**
- `outputs/canonical_record.md` — full debate transcript across all rounds

**Round outputs:**
- `outputs/round_1/` — all advocate opening statements + moderation report + round digest
- `outputs/round_2/` — questions, responses, moderation report, round digest
- `outputs/round_3/` — all seven-text responses per advocate + moderation report + round digest
- `outputs/round_4/` — all closing arguments + final moderation report
- `outputs/synthesis/` — moderator synthesis + advocate synthesis responses (if separate from canonical record)

**Citation and verification data:**
- `verification/citations/round_N_citations.json` — all extracted citations per round
- `verification/verifications/round_N_verifications.json` — verification verdicts per round
- `verification/citations/round_N_responses.json` — advocate DEFEND/WITHDRAW responses
- `verification/audit/round_N_worksheet.md` — human review worksheets

---

## Audit Dimensions & Scoring Instructions

### Dimension 1: Citation Integrity
**Weight: High**

Count and categorize all citations across all rounds. For each advocate, compute:
- Total citations
- Count and % by verdict: VERIFIED / LIKELY_ACCURATE / CONTESTED / UNVERIFIED / FABRICATION_RISK
- DEFEND vs. WITHDRAW rate for flagged citations
- Re-verification outcomes: DEFEND+new_source that passed vs. escalated to RETRACTED

**Score each advocate:**
- **Excellent:** FABRICATION_RISK rate < 5%; all flagged citations received a response
- **Adequate:** 5–10%; most received responses
- **Problematic:** > 10%; or flagged citations went without a response

**Also check:**
- Did any advocate who WITHDREW a citation quietly reintroduce the same argument with weaker/no sourcing in a later round?
- Did any FABRICATION_RISK citation persist uncorrected into Round 4?

---

### Dimension 2: Disciplinary Fidelity
**Weight: High**

Each advocate has a Statement of Limits. Read each Round 1 opening and confirm the Statement of Limits appears in the first 150 words.

Then, for each advocate, check whether they stayed inside their stated limits across all rounds — with the highest scrutiny on Round 4 closings (where the prompt asks for ecclesial conclusions that edge toward other disciplines).

**Known limits to check:**
- **Biblical Scholar:** Cannot build an ecclesiology alone; cannot adjudicate between defensible readings without a hermeneutical principle
- **Reception Historian:** Cannot establish that a reading is wrong because it has a certain history; cannot establish what texts originally mean
- **Hermeneutician:** Cannot determine which hermeneutical approach is correct; cannot adjudicate extra-hermeneutical commitments
- **Systematic Theologian:** Cannot establish specific text meanings; a coherent ecclesiology means nothing if not grounded exegetically
- **Pastoral Theologian:** Cannot establish that harm alone settles exegetical questions; fruitfulness is not the final criterion
- **Social Analyst:** Cannot establish that a reading is wrong because it emerged from a social context; not reductionist

**Score per advocate:**
- **Excellent:** 0 limit violations
- **Adequate:** 1–2 soft overreaches (caught and qualified by advocate or moderator)
- **Problematic:** Systematic overreach; stated limits ignored in R4

---

### Dimension 3: Cross-Disciplinary Engagement Quality
**Weight: High**

**Round 2 response scoring:** For each of the six responses, score as:
- **1 — Direct engagement:** Responding advocate addressed the actual question posed, engaged the questioner's disciplinary evidence
- **0.5 — Partial:** Engaged the topic but deflected the specific challenge
- **0 — Evasion:** Restated own position without engaging the questioner's evidence

**Round 3 & 4 cross-citation matrix:** Build a 6×6 matrix. For each advocate in R3 and R4, count how many times they explicitly cited or engaged a finding from each other discipline by name (e.g., "as the Reception Historian showed," "the Biblical Scholar's evidence on *authenteō*"). Sum per advocate.

**Concession count:** Scan canonical record for formal concessions (words: "concede," "acknowledge," "I was wrong," "I accept the correction," "I must revise"). A debate with zero concessions from any advocate is suspicious.

**Challenge engagement:** For each advocate in R4, check the mandatory component: "where your discipline found itself genuinely changed or challenged by another discipline." Rate as:
- **Credible:** Names a specific finding from a specific discipline that actually appeared in the debate
- **Formulaic:** Generic acknowledgment of complexity without naming what changed

---

### Dimension 4: Intellectual Development Across Rounds
**Weight: Medium**

**Position comparison:** For each advocate, identify their central thesis from R1 and their central conclusion in R4. Note whether it is:
- **Evolved:** The R4 conclusion is a more precise, qualified, or reframed version of R1 — shaped by what happened in the debate
- **Unchanged:** R4 repeats R1 with more words; could have been written before Round 1 started
- **Regressed:** R4 is less precise or honest than R1 (overreach or defensive retrenchment)

**Canonical record usage:** In R3 and R4, advocates had access to the full canonical record. Check whether they actually reference earlier rounds, earlier arguments, or earlier corrections. Advocates who never cite the record are not engaging the debate as a running conversation.

**Central question reframing:** Was the governing question the same at the end as at the start? Did the debate produce any finding that shifted what the most important question is? Note any such reframings explicitly.

---

### Dimension 5: Verification System Performance
**Weight: High**

This evaluates the pipeline itself, not just its outputs.

**Pass 1 precision:** Of citations rated HIGH suspicion in Pass 1, what fraction ultimately received FABRICATION_RISK or NEEDS_HUMAN_REVIEW verdicts? (High precision = Pass 1 was a reliable early signal)

**Correction loop closure:** For every citation that received FABRICATION_RISK, verify there is a corresponding CITATION_RESPONSE in the next round's response file. Flag any gaps.

**False negative check:** Spot-check 10 citations marked VERIFIED across different advocates and rounds. Attempt to confirm the author, work title, and whether the attributed argument matches the scholar's known position. Flag any that appear suspicious.

**Recheck pipeline:** For DEFEND+new_source responses, were they re-verified? Did the recheck verifications exist and were outcomes logged?

---

### Dimension 6: Moderator/Synthesis Quality
**Weight: Medium**

**Correction accuracy:** Read every HARD CORRECTION the moderator issued. Evaluate whether each correction was accurate (the claim was genuinely false by scholarly consensus) or overcorrected (the claim was actually contested, not definitively wrong).

**Synthesis grounding:** For each item in the synthesis sections (CONVERGENCES, IRRECONCILABLE TENSIONS, ARGUMENTS PAST EACH OTHER), find the specific exchange in the canonical record it is describing. Rate as:
- **Grounded:** Points to a real, specific exchange
- **Generic:** Restates a theme without mapping to a specific moment in the debate

**Synthesis prohibited behaviors check:** Verify the synthesis did not award points, declare a winner, or treat the debate as a horse race.

**R4 follow-through:** The synthesis section "WHAT R4 MUST ADDRESS" named specific tensions. Check whether each advocate's R4 closing actually confronted those tensions or ignored them.

---

### Dimension 7: Architectural Assessment
**Weight: Medium**

**Voice distinctiveness:** Read all six Round 4 closings side by side. Assess:
- Do the six advocates use noticeably different vocabularies, framings, and argumentative styles?
- Are there shared phrases, metaphors, or sentence structures that appear across multiple advocates (evidence of single-model substrate showing through)?
- Which disciplinary voice contributed the most unique content that couldn't have come from any other discipline? Which contributed least?

**Prompt bleed:** Did any advocate reference their own system prompt constraints in ways that should be invisible to the debate (e.g., "as I stated in my Statement of Limits," treating their limits as external rules rather than their own disciplinary commitments)?

**Pairing gaps:** Were there significant disciplinary tensions that the fixed Round 2 pairings couldn't surface? Name any tension that should have been a Round 2 exchange but wasn't.

**Text avoidance:** For the seven required texts in Round 3, did any advocate give a substantially shorter or more superficial treatment to a text that cut against their preferred reading?

**Speaking order effect:** Did the reverse speaking order in R4 (Social Analyst first, Biblical Scholar last) produce a different dynamic than Round 1? Did the Biblical Scholar, speaking last, respond to what the Social Analyst opened with?

---

### Dimension 8: Substantive Value & Epistemic Yield
**Weight: High — this is the primary test of whether the system is worth the complexity**

This dimension measures whether the debate produced genuine insight that a reader couldn't have obtained from a single-discipline engagement with the question.

#### 8a: Cross-Disciplinary Yield
Identify findings in the debate that required at least three disciplines working together to produce. A finding qualifies if:
- Discipline A surfaced a textual or historical fact
- Discipline B identified the methodological implication
- Discipline C showed how it challenges a prior assumption

Example of what this looks like: The consistency problem (creation-order grounding in 1 Tim 2 vs. 1 Cor 11) is most powerful when the Biblical Scholar confirms the exegetical parallel, the Hermeneutician names the inconsistency, and the Reception Historian shows how tradition handled the divergence. No single discipline produces all three legs.

List all findings that meet this threshold. This is the core value-add of the multi-agent architecture.

#### 8b: Question Reframing
Did the debate change what the central question is by Round 4?

The initial question is framed around Alderwood's complementarian position — who has authority to teach and lead. Assess whether the debate, through cross-disciplinary engagement, revealed that a prior or deeper question must be answered first (e.g., "what is the nature of church authority" before "who can hold it"; or "what marks a principle as transcultural" before "is this principle transcultural").

Rate: **Reframed** (the central question shifted), **Sharpened** (same question, but the terms are now more precisely defined), or **Unchanged** (same question, more arguments, no new framing).

#### 8c: Reader Value-Add Test
A serious reader has read the Alderwood document and one scholarly response to it (say, a single article arguing the complementarian position is exegetically defensible). What does this debate give them that they didn't have?

Assess concretely:
- What arguments were made that the reader wouldn't have encountered in a single-discipline treatment?
- What concessions were made by advocates that a single-advocate treatment would never include?
- What uncertainties were named honestly that a single-advocate would have glossed over?
- What tensions were mapped that require all six disciplines to even see clearly?

Rate the value-add as: **High** (reader gains substantial new understanding), **Medium** (reader gains some nuance but no structural reorientation), **Low** (reader gets sophisticated-sounding content but nothing they couldn't have gotten from a well-written single essay).

---

---

### Dimension 9: Persona Impact Assessment
**Weight: High — tests practical value of the debate for real audiences**

This dimension measures whether the debate moves the needle, informs, or fails specific types of readers. The agent should simulate each persona's reading of the debate and assess its impact honestly, flagging where the simulation may be unreliable due to model bias.

**Important instruction to agent:** For each persona, explicitly note where your simulation of their response may be unreliable. The model has known tendencies (e.g., toward progressive framings of gender questions) that may distort how it simulates the conservative personas. Flag this rather than paper over it.

---

#### Persona 1: Woman at Alderwood, Believes She May Be Called
**Profile:** A member of Alderwood Community Church. She takes the church's authority seriously, loves her community, and hasn't left — but she has a persistent sense that she is called to teach or preach in ways the church's position forecloses. She is not an academic. She has read the Alderwood document and accepts its sincerity but not its conclusion. She is looking for either: (a) a reason to trust the restriction she's living under, or (b) a framework for understanding why it may be wrong that she can articulate to herself and others.

**Assess:**
- Does the debate give her language for her own experience — or does it remain abstract?
- Does the Pastoral Theologian's voice (formation, harm, calling) speak to her situation specifically?
- Does the debate help her understand the strongest version of the complementarian argument well enough to respect it even if she rejects it?
- Does the mandatory R4 component — "what happens to a woman who believes she's called to a role the position restricts" — get answered honestly by any advocate? Does any answer help her?
- Does she finish the debate with more clarity, more tools, or just more complexity?

**Rate:** Significantly moved / Somewhat informed / Unchanged / Potentially harmful (if the debate models her experience inaccurately or dismissively)

---

#### Persona 2: Male Alderwood Congregant, Young Daughters, Conservative Upbringing
**Profile:** Mid-30s, married, two or three young daughters. Grew up in a conservative evangelical context where complementarianism was assumed, not argued. Not trained in theology or biblical studies. He never had reason to question the framework until his daughters were born — now the question is becoming personal. He genuinely cares about getting this right. He is not looking to confirm a conclusion; he is trying to figure out where the weight of the evidence actually falls, and what faithfulness to scripture actually requires.

**Assess:**
- Is the debate accessible to someone without theological training, or does it assume too much?
- Does the debate help him understand *why* the question is hard — not just that smart people disagree, but what specific things have to be resolved to make progress?
- Does the hermeneutical consistency challenge (creation-order in 1 Tim 2 vs. 1 Cor 11) land for a non-expert, or is it too technical?
- Does the debate give him anything to bring home — a framework, a question, a way of thinking — that helps him parent his daughters with integrity regardless of where he lands?
- Does the multi-disciplinary structure help or overwhelm a non-specialist reader?

**Rate:** Significantly moved / Somewhat informed / Unchanged / Potentially harmful

---

#### Persona 3: Theologically Serious Christian Egalitarian
**Profile:** A Christian who takes scripture seriously and reads it differently than Alderwood. They are familiar with the standard egalitarian arguments (Galatians 3:28, Junia, Phoebe, redemptive-movement hermeneutic, *authenteō* debate) and have read some scholarship. They are not hostile to complementarians as people but believe the position is exegetically indefensible. They come in with a thesis and will be testing whether the debate engages the strongest version of their arguments or a weakened version.

**Assess:**
- Does the debate engage the egalitarian position at its strongest, or does it steelman complementarianism while presenting a softer egalitarian challenge?
- Does the Hermeneutician's consistency challenge land with full force, or is it deflected?
- Does the Biblical Scholar's treatment of Junia, Phoebe, and the canonical breadth argument meet the level of scholarship this reader expects?
- Is the Alderwood position represented fairly — neither strawmanned nor let off the hook?
- Does the debate give this reader anything they didn't already have, or does it just confirm their existing position with more apparatus?

**Rate:** Significantly moved / Somewhat informed / Unchanged / Potentially harmful

---

#### Persona 4: Intellectually Honest Complementarian Pastor
**Profile:** Pastor at a complementarian church, confident in the position, but not defensive about it. Has read Wayne Grudem and Thomas Schreiner. Believes the complementarian reading is exegetically correct and is prepared to defend it. But is genuinely interested in engaging the strongest objections — not to defeat them rhetorically but to understand them. Tests whether the debate deepens his understanding or just rehearses the same arguments in more academic language.

**Assess:**
- Does the debate present a complementarian position he would recognize as his own, or a weakened version?
- Does the hermeneutical consistency challenge (the 1 Cor 11 problem) get a fair answer from any advocate? Does any complementarian-leaning voice engage it seriously?
- Does the debate introduce any argument or consideration he hadn't encountered before?
- Does the Systematic Theologian's ecclesiological framing (what IS the church; where does authority come from) add anything to how he thinks about the question?
- Does the debate leave him more or less confident? More or less nuanced? Does he finish with any acknowledged uncertainty that he didn't have before?

**Rate:** Significantly moved / Somewhat informed / Unchanged / Potentially harmful

---

#### Persona 5: Undecided Church Leadership Team
**Profile:** A pastoral staff or elder team at a church that has avoided the question or has a temporary informal position but knows they need to decide formally. They are practitioners, not academics. They need to land somewhere institutional. They want to know: what does faithfulness actually require, what is genuinely uncertain, and what would we be committing to if we went one direction or the other? They are testing whether the debate gives them a *usable* map.

**Assess:**
- Does the debate produce a clear picture of what is genuinely settled vs. genuinely contested? Can a leadership team walk away knowing where the real decision points are?
- Does the synthesis "WHAT R4 MUST ADDRESS" and the R4 closings actually give decision-makers the specific questions they need to answer?
- Does any advocate directly address the institutional question — not just what is true but what a church should *do* given remaining uncertainty?
- Does the mandatory R4 component — "what is required, what is permitted, what must be repented of" — give a leadership team traction, or does it remain in the register of scholarship rather than practice?
- Would this team finish the debate better equipped to make a decision, or better equipped to explain why the decision is hard?

**Rate:** Decision-ready (high practical utility) / Clarifying (good map, still needs pastoral discernment) / Academic (intellectually valuable but not institutionally actionable) / Confusing (added complexity without clarity)

---

#### Persona Assessment Output Format

For each persona, the agent should produce:
1. **2–3 sentence profile summary** (to confirm the persona was understood correctly)
2. **What the debate gave them** — specific moments, arguments, or framings from the actual debate outputs that would land for this reader
3. **What the debate failed to give them** — gaps, evasions, or register mismatches
4. **The needle movement rating** with a one-paragraph justification
5. **One specific change** to the debate structure, prompt design, or advocate framing that would make the debate more valuable for this reader

The agent should conclude the persona section with a **cross-persona pattern** observation: what does the pattern of impact across all five personas reveal about who this debate is actually for, and whether that matches the intended audience?

---

## Output Format

The agent should produce a report with the following sections:

### 1. Executive Summary (200–300 words)
Overall assessment: is the system producing what it was designed to produce? What are the top 2–3 findings?

### 2. Dimension Scores
A table with scores for all 8 dimensions (Excellent / Adequate / Problematic) with a 1–2 sentence justification for each.

### 3. Citation Integrity Report
Per-advocate table: total citations, FABRICATION_RISK count and %, DEFEND/WITHDRAW counts, any uncorrected fabrications or re-introduced withdrawn claims.

### 4. Cross-Disciplinary Contact Matrix
6×6 table showing how many times each advocate explicitly engaged each other discipline's findings in R3 and R4.

### 5. Top 5 Cross-Disciplinary Findings
List the five strongest findings that required multiple disciplines working together. For each: which disciplines contributed, what the finding is, and why it couldn't have been produced by a single discipline.

### 6. Weaknesses & Failure Modes
List of places where the system did not produce what it was designed to produce. Be specific: which advocate, which round, which design choice failed.

### 7. Improvement Opportunities
Ranked list of changes to prompts, round structure, pairing design, verification pipeline, or agent architecture that would improve results in a future run. Focus on the highest-leverage changes.

### 8. Architectural Verdict
One-paragraph honest assessment: does the multi-agent debate architecture earn its complexity? Would the same prompt given to a single agent with instructions to consider all six perspectives produce substantially worse results? What is the irreducible value of the separate-agent design?
