# Citation Verification System
## Design Specification

---

## Overview

Citations in this debate fall into distinct categories that require different verification approaches. The system uses a **two-pass architecture**: an automated verifier agent handles what it can resolve with web search, then routes unresolved and high-risk claims to a human auditor with a structured worksheet.

The goal is not to verify every claim to academic standards — that would require access to every cited book. The goal is to **catch fabrications, flag contested claims, and give the human auditor an efficient path to the claims that actually need their attention.**

---

## What the Automated Verifier Can and Cannot Do

### Can do reliably:
- **Confirm a book exists** — author, title, publisher, year. Web search resolves this in one query.
- **Confirm a journal article exists** — author, title, journal, year. Searchable via Google Scholar or publisher sites.
- **Confirm an author's general scholarly position** — "Gupta argues for an egalitarian reading of the Pauline texts" is confirmable from reviews, interviews, and abstracts.
- **Detect obvious fabrications** — a book that doesn't exist, an author who didn't write on this topic, a journal article with a fabricated title.
- **Confirm freely available sources** — N.T. Wright's essay is online. The Alderwood document is online. Pliny's letter is widely reproduced.

### Cannot do reliably:
- **Confirm specific page numbers** — would require access to the physical or digital book.
- **Confirm specific argument attributions** — "Gupta argues on p. 170 that authenteo carries a negative connotation" requires reading p. 170. The verifier can confirm Gupta discusses authenteo generally but not the specific claim on that page.
- **Distinguish between an author's actual argument and a plausible-sounding paraphrase** — this is the hardest hallucination to catch. The model may attribute a reasonable-sounding argument to a real scholar who never made exactly that argument.
- **Resolve genuinely contested scholarly claims** — the verifier can flag that a claim is contested, but cannot determine which side is correct.

### The key insight:
The automated pass sorts claims into buckets. The human auditor only needs to look at the claims the automated pass couldn't resolve — and even then, they have structured guidance about what to look for.

---

## Claim Taxonomy

Every citation in the debate involves multiple sub-claims that can be verified independently:

| Component | Example | Auto-verifiable? |
|-----------|---------|-------------------|
| **Author exists and works in this field** | "Nijay Gupta, NT scholar" | Yes — high confidence |
| **Work exists with this title/publisher/year** | "Tell Her Story, IVP Academic, 2023" | Yes — high confidence |
| **Author addresses this topic in this work** | "Gupta discusses authenteo in Tell Her Story" | Usually yes — from reviews, TOCs, abstracts |
| **Author makes this specific argument** | "Gupta argues authenteo carries a negative connotation" | Partial — can confirm general direction, not specifics |
| **This argument appears on this page** | "p. 170" | No — requires the book |
| **This is the scholarly consensus** | "Scholarly consensus since Fitzmyer (1992)" | Partially — can find corroborating/dissenting sources |

---

## Automated Verifier Agent

### System Prompt (for the verifier — separate from the moderator)

```
You are a citation verification agent for an academic theological debate. Your job is to check citations made by debate participants, NOT to evaluate the theological arguments themselves.

For each citation you receive, perform the following checks using web search:

1. BIBLIOGRAPHIC CHECK: Does the cited work exist? Search for: author + title + publisher + year. Confirm or flag.

2. TOPICAL CHECK: Does the author address the claimed topic in this work? Search for: author + title + [key topic term]. Look for table of contents, reviews, abstracts, publisher descriptions.

3. ARGUMENT DIRECTION CHECK: Does the author's known position align with the attributed argument? Search for: author + [key claim]. Look for interviews, reviews, other scholars citing this work, the author's own blog/website.

4. CONSENSUS CHECK (if the claim asserts consensus): Search for dissenting scholarly voices. If you find serious dissenters, flag as CONTESTED rather than VERIFIED.

For each citation, produce a structured verdict. Be explicit about what you checked, what you found, and what you could not determine.

CRITICAL RULES:
- You CANNOT verify specific page numbers. Always mark page numbers as UNVERIFIABLE unless you found the exact page in a freely available source.
- You CANNOT verify specific argument wording. You can verify argument direction (the author generally argues X) but not that the author said exactly these words.
- When you find corroborating evidence that is not the original source (e.g., a blog post by the author, a book review, a secondary citation), note it as CORROBORATING EVIDENCE, not as VERIFICATION of the original claim.
- Express uncertainty. "I found evidence consistent with this claim but cannot confirm the specific attribution" is a required output pattern.
- Do not search for more than 3 queries per citation. If you cannot resolve it in 3 searches, mark as NEEDS_HUMAN_REVIEW with a note about what you tried.
```

### Verifier Output Format

For each citation, the verifier produces:

```json
{
  "claim_id": "R1_BS_003",
  "round": 1,
  "advocate": "biblical_scholar",
  "original_citation": {
    "claim": "authenteo carried a negative connotation in first-century Greek usage",
    "source": "Nijay Gupta, Tell Her Story, IVP Academic, 2023, p. 170",
    "argument": "Gupta argues the word's rarity and pattern of use suggests abuse of power rather than neutral authority",
    "advocate_confidence": "MEDIUM"
  },
  "verification": {
    "bibliographic": {
      "status": "VERIFIED",
      "note": "Book confirmed: Gupta, Tell Her Story, IVP Academic, 2023. Found on publisher site and multiple retailers."
    },
    "topical": {
      "status": "VERIFIED", 
      "note": "Multiple reviews confirm Gupta discusses authenteo and 1 Timothy 2 extensively in this work."
    },
    "argument_direction": {
      "status": "LIKELY_ACCURATE",
      "note": "Gupta's published interviews and other writings confirm he argues for a negative/domineering reading of authenteo. Cannot confirm this specific formulation appears on p. 170.",
      "corroborating_evidence": [
        "Gupta blog post on Patheos discussing authenteo (URL)",
        "Christianity Today review of Tell Her Story mentioning his authenteo argument"
      ]
    },
    "page_number": {
      "status": "UNVERIFIABLE",
      "note": "Page 170 cannot be confirmed without access to the physical book."
    },
    "consensus_check": {
      "status": "CONTESTED",
      "note": "Al Wolters (JETS, 2006) and Köstenberger argue for neutral meaning. Both readings have serious defenders."
    }
  },
  "overall_verdict": "LIKELY_ACCURATE_BUT_CONTESTED",
  "human_review_needed": false,
  "human_review_priority": null,
  "summary": "Book and author verified. Argument direction confirmed from secondary sources. Specific page and exact wording unverifiable. The underlying claim about authenteo's connotation is genuinely contested in scholarship."
}
```

### Overall Verdict Categories

| Verdict | Meaning | Routes to human? |
|---------|---------|-------------------|
| **VERIFIED** | Bibliographic, topical, and argument direction all confirmed. No contest found. | No |
| **LIKELY_ACCURATE** | Bibliographic and topical confirmed. Argument direction consistent with author's known position but specific attribution unconfirmed. | No |
| **LIKELY_ACCURATE_BUT_CONTESTED** | Same as above, but the underlying claim is genuinely disputed among scholars. | No — but flagged in debate record |
| **PARTIALLY_VERIFIED** | Book/author confirmed but argument attribution could not be confirmed or is ambiguous. | Only if HIGH confidence was claimed |
| **NEEDS_HUMAN_REVIEW** | Could not resolve after 3 search attempts, or found conflicting information. | Yes |
| **FABRICATION_RISK** | Book doesn't appear to exist, author doesn't appear to work in this field, or the specific argument is contradicted by the author's known position. | Yes — HIGH priority |
| **UNVERIFIABLE** | Claim is too specific to verify without the physical source (e.g., specific page, specific wording). | Only if the claim is load-bearing for the argument |

---

## Human Audit Worksheet

After the automated pass, unresolved and flagged claims are compiled into a worksheet designed for efficient human review.

### Worksheet Structure

Each claim needing review gets a card:

```
═══════════════════════════════════════════════════
CLAIM ID: R1_RH_007
PRIORITY: HIGH — Fabrication risk
ADVOCATE: Reception Historian
ROUND: 1

CLAIM: "Epigraphic evidence from the Salona region documents 
       a woman presbytera in the 4th century"
SOURCE: Madigan & Osiek, Ordained Women in the Early Church, 
        Johns Hopkins, 2005
ARGUMENT: Documents inscriptional evidence of ordained women 
          including presbytera designation

ADVOCATE CONFIDENCE: HIGH

AUTOMATED RESULT: FABRICATION_RISK
REASON: Book verified. Authors verified. Madigan & Osiek do 
        document epigraphic evidence of women's ordination 
        generally. However, I could not find specific reference 
        to "Salona region" or "4th century presbytera" in any 
        review or summary of this work. The specificity of 
        "Salona region" raises fabrication risk — this may be 
        a plausible-sounding detail generated by the model.

WHAT TO CHECK: Does Madigan & Osiek specifically discuss 
               Salona? Does the epigraphic record include 
               this inscription?

SEARCH SUGGESTIONS:
  - "Madigan Osiek Salona presbytera"
  - "Salona inscription woman presbyter early church"
  - Check Madigan & Osiek table of contents / index if available

───────────────────────────────────────────────────
AUDITOR VERDICT: [                                ]

  ○ CONFIRMED — Found in source or reliable secondary source
  ○ CONFIRMED_INDIRECT — Not found in original but corroborated
    by other reliable sources (specify):
    Evidence: [                                    ]
  ○ PLAUSIBLE_BUT_UNCONFIRMED — Consistent with the source's
    known content but cannot confirm this specific detail
  ○ LIKELY_FABRICATED — Evidence contradicts this specific claim
    or no trace found despite thorough search
  ○ CANNOT_DETERMINE — Insufficient access to resolve

AUDITOR NOTES: [                                   ]

IMPACT ASSESSMENT:
  If this claim is wrong, does it materially affect the 
  advocate's argument?
  ○ Load-bearing — argument depends on this specific claim
  ○ Supporting — removes one piece of evidence but argument 
    stands on other grounds  
  ○ Illustrative — used as an example; argument doesn't 
    depend on it

ACTION:
  ○ No action needed
  ○ Flag for moderator to note in next round
  ○ Requires correction in canonical record
  ○ Advocate should be prompted to revise or remove

═══════════════════════════════════════════════════
```

### The "Confirmed Indirect" Category

This is the category you specifically asked about — "I don't have the source but I found a blog by the author about the same thing." The worksheet handles this with structured fields:

**CONFIRMED_INDIRECT** means: the original source was not consulted, but the claim is corroborated by other evidence that makes it very likely accurate.

When an auditor selects this, they must specify:

```
Type of indirect evidence:
  ○ Author's own writing elsewhere (blog, interview, lecture)
  ○ Another scholar citing this work and confirming this argument
  ○ Book review that discusses this specific point
  ○ A different work by the same author making the same argument
  ○ General scholarly consensus consistent with the attributed argument
  ○ Other (specify)

Source of indirect evidence: [URL or citation]

Confidence in indirect evidence:
  ○ Strong — directly corroborates the specific claim
  ○ Moderate — corroborates the general argument direction
  ○ Weak — consistent but doesn't specifically confirm
```

---

## Workflow

```
ROUND COMPLETES
      │
      ▼
CITATION EXTRACTOR ─── Parses all [CLAIM][SOURCE][ARGUMENT][CONFIDENCE] 
      │                 blocks from advocate outputs into structured JSON
      │
      ▼
AUTOMATED VERIFIER ─── For each citation:
      │                 1. Bibliographic check (web search)
      │                 2. Topical check (web search)  
      │                 3. Argument direction check (web search)
      │                 4. Consensus check if applicable
      │                 5. Assigns verdict
      │
      ├──── VERIFIED / LIKELY_ACCURATE ──────────► Logged. No human needed.
      │
      ├──── LIKELY_ACCURATE_BUT_CONTESTED ───────► Logged. Flagged as 
      │                                            SOFT in debate record.
      │
      ├──── PARTIALLY_VERIFIED ──────────────────► Human review only if 
      │                                            advocate claimed HIGH
      │                                            confidence.
      │
      ├──── NEEDS_HUMAN_REVIEW ──────────────────► Added to audit worksheet
      │
      └──── FABRICATION_RISK ────────────────────► Added to audit worksheet
                                                   as HIGH PRIORITY
      │
      ▼
AUDIT WORKSHEET GENERATED ─── Contains only claims that need human eyes,
      │                       pre-sorted by priority, with search 
      │                       suggestions and context
      │
      ▼
HUMAN AUDITOR ─── Works through worksheet. Typical time estimate:
      │            - 5-10 FABRICATION_RISK items per round: ~1 hour
      │            - 10-15 NEEDS_HUMAN_REVIEW items per round: ~1.5 hours
      │            - Total per round: ~2-3 hours
      │
      ▼
COMPLETED WORKSHEET ─── Verdicts compiled into:
      │
      ├──── VERIFICATION LOG (full JSON record of all claims)
      │
      ├──── MODERATOR INPUT (claims the moderator should flag 
      │     in the next round — corrections and contested claims)
      │
      └──── CANONICAL RECORD ANNOTATIONS (footnotes added to 
            the debate record marking corrected or contested claims)
```

---

## Integration with the Moderator

The moderator agent is NOT the verifier. They have different jobs:

- **Verifier:** Did this citation check out? Is this book real? Does this author make this argument?
- **Moderator:** Given the verification results, what does the debate need to know? Which flags affect the arguments? What corrections need to be entered into the record?

The moderator receives the verification log as input and uses it to produce the human-readable fact-check report. This separation means:
1. The verifier can be mechanical and thorough without worrying about debate dynamics
2. The moderator can focus on what matters for the argument rather than checking every bibliographic detail
3. The human auditor's corrections flow into the moderator's input, not directly into the debate

---

## Cost and Effort Estimates

### Automated Pass (per round)
- Expected citations per round: 30-60 (six advocates, 5-10 citations each)
- Web searches per citation: 2-3
- Total searches per round: ~60-180
- Verifier agent calls: 1 per citation (batch if possible) or 1 call with all citations
- Estimated cost: ~$2-5 per round in API + search costs
- Time: ~5-10 minutes

### Human Audit (per round)
- Expected items routed to human: 15-25 (roughly 30-50% of citations)
- Priority items (fabrication risk): 3-8
- Estimated time: 2-3 hours per round for a thorough audit
- Total across 4 rounds + pre-debate: 10-15 hours

### Total Across Full Debate
- Automated: ~$10-25, ~30-60 minutes of compute
- Human: ~10-15 hours of focused audit work
- This is the real cost of citation quality — and it's worth it for a single high-quality run

---

## What Gets Annotated in the Final Record

The canonical debate record — the final artifact — gets footnotes for three categories:

1. **[CORRECTED]** — Claim was found to be factually incorrect. The correction is noted.
   > Example: "¹ [CORRECTED: The advocate cited Madigan & Osiek for epigraphic evidence from the Salona region. Auditor found no reference to Salona in this work. The inscription referenced is likely from Tropea, not Salona. See Eisen, Women Officeholders, p. 132.]"

2. **[CONTESTED]** — Claim is genuinely disputed among scholars. Both sides noted.
   > Example: "² [CONTESTED: The meaning of authenteo is actively disputed. Gupta and Westfall argue for a negative connotation. Wolters and Köstenberger argue for neutral meaning. Neither reading commands consensus.]"

3. **[UNVERIFIED]** — Claim could not be confirmed or denied. Noted for transparency.
   > Example: "³ [UNVERIFIED: This specific argument attribution to Walton (Lost World, p. 84) could not be confirmed. The general direction is consistent with Walton's published position.]"

Claims that passed verification cleanly get no annotation. The absence of a footnote signals that the citation checked out.

---

## File Formats

### Citation Extract (input to verifier)
`citations/round_1_citations.json` — array of citation objects extracted from advocate outputs

### Verification Log (output from verifier)  
`verification/round_1_verification.json` — array of verdict objects

### Audit Worksheet (for human)
`audit/round_1_audit.md` — markdown worksheet with the card format shown above

### Completed Audit
`audit/round_1_audit_completed.md` — same worksheet with auditor verdicts filled in

### Moderator Input
`verification/round_1_moderator_input.md` — human-readable summary of all flags, corrections, and contested claims for the moderator agent

### Annotated Canonical Record
`debate_record/canonical_record_annotated.md` — the final debate record with footnotes
