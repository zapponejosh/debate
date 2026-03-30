"""
Citation Verifier — Three-Pass Pipeline
========================================

Pass 1  Training knowledge only, batched (5 citations per call, no web search).
        Quick triage: does this book plausibly exist? Does the argument direction
        match what we know about this scholar? Catches obvious fabrications cheaply.

Pass 2  One targeted bibliographic search per citation, all citations, one at a time.
        Single web-search turn: find a publisher page, library record, or review that
        confirms the book exists. Every citation gets at least one external check.

Pass 3  Deep investigation, suspicious citations only, one at a time (2–3 searches).
        Runs on anything flagged FABRICATION_RISK in Pass 1, or bibliographically
        UNCONFIRMED in Pass 2. Full argument-direction and topical check.

merge_pass_results() combines the three passes into the final per-citation verdict
in the same format consumed by audit_worksheet and generate_moderator_input.
"""

import json
import re


# ---------------------------------------------------------------------------
# Pass 1 — training knowledge
# ---------------------------------------------------------------------------

PASS1_SYSTEM_PROMPT = """You are a citation triage agent for an academic theological debate. Your job is to perform a rapid first-pass check of citations using your training knowledge — NOT web search.

Be honest about the limits of your training knowledge. Do not confabulate details you are not confident about. Express genuine uncertainty.

For each citation check:

1. BIBLIOGRAPHIC PLAUSIBILITY
   Do you recognize this author as a real scholar who works in this field?
   Does the title sound like a real work? Does the publisher match this type of scholarship?
   Is the year plausible for this author's career?

2. ARGUMENT DIRECTION
   Based on what you know about this scholar's work and position, does the attributed
   argument align with their known stance? Or does it contradict their known position?

CRITICAL: You are checking plausibility from training knowledge only. You cannot confirm
specific page numbers, exact quotations, or arguments you do not specifically recall.
A citation can pass this check and still be wrong in its specifics.

OUTPUT FORMAT — respond with a JSON array, one object per citation:

[
  {
    "claim_id": "...",
    "pass": 1,
    "bibliographic_plausibility": "RECOGNIZED | PLAUSIBLE | UNCERTAIN | IMPLAUSIBLE",
    "bibliographic_note": "one sentence — what you know or don't know about this work",
    "argument_direction": "CONSISTENT | PLAUSIBLE | UNCLEAR | CONTRADICTS_KNOWN_POSITION",
    "argument_note": "one sentence — does this match what you know about this scholar's views",
    "suspicion_level": "LOW | MEDIUM | HIGH",
    "suspicion_reason": "one sentence if MEDIUM or HIGH, else null"
  }
]

suspicion_level guidance:
- LOW: recognized work, argument direction consistent
- MEDIUM: author/work recognized but argument unclear, or minor detail seems off
- HIGH: author doesn't work in this field, title doesn't exist, argument contradicts known position

Respond with ONLY the JSON array. No preamble."""


def build_pass1_prompts(citations: list[dict], batch_size: int = 5) -> list[str]:
    prompts = []
    for i in range(0, len(citations), batch_size):
        batch = citations[i:i + batch_size]
        citations_text = ""
        for c in batch:
            citations_text += f"""
---
CLAIM ID: {c['claim_id']}
ADVOCATE: {c['advocate']}
CLAIM: {c['claim']}
SOURCE: {c['source']}
ARGUMENT: {c['argument']}
ADVOCATE CONFIDENCE: {c['advocate_confidence']}
---
"""
        prompt = f"""Perform a training-knowledge triage check on the following {len(batch)} citations from a theological debate.

Do NOT use web search. Check only from your training knowledge.

{citations_text}

Respond with ONLY the JSON array."""
        prompts.append(prompt)
    return prompts


# ---------------------------------------------------------------------------
# Pass 2 — one bibliographic search
# ---------------------------------------------------------------------------

PASS2_SYSTEM_PROMPT = """You are a citation verification agent for an academic theological debate.

Your task for this citation is narrow and specific: perform ONE web search to find bibliographic confirmation that this book or article exists.

Search query to use: the author's name + the title + publisher (e.g. "Nijay Gupta Tell Her Story IVP Academic").

Look for: publisher page, library catalog entry, Amazon listing, Google Books entry, academic review.

You get ONE search. Use it well. Do not search for the argument or the content — just bibliographic existence.

After your search, respond with a single JSON object:

{
  "claim_id": "...",
  "pass": 2,
  "bibliographic_status": "CONFIRMED | UNCONFIRMED | CONFLICTING",
  "source_found": "URL or brief description of what you found, or null",
  "note": "one sentence summary of what the search returned"
}

CONFIRMED: you found a credible source (publisher, library, reputable review) confirming this book/article exists with approximately these publication details.
UNCONFIRMED: search returned nothing relevant, or results were too ambiguous to confirm.
CONFLICTING: you found the author and title but publication details (publisher, year) don't match what was cited.

Respond with ONLY the JSON object. No preamble."""


def build_pass2_prompt(citation: dict) -> str:
    return f"""Find bibliographic confirmation for this citation from a theological debate.

CLAIM ID: {citation['claim_id']}
SOURCE: {citation['source']}
CLAIM (for context): {citation['claim']}

Perform ONE web search to confirm this source exists. Return your JSON verdict."""


# ---------------------------------------------------------------------------
# Pass 3 — deep investigation (suspicious citations only)
# ---------------------------------------------------------------------------

PASS3_SYSTEM_PROMPT = """You are a citation verification agent for an academic theological debate.

This citation has been flagged for deep investigation — either it could not be bibliographically confirmed, or it showed signs of possible fabrication. Your job is to investigate thoroughly.

You may perform up to 3 web searches. Use them strategically:
1. If bibliographic existence is still unconfirmed: search for the book/article again with different terms
2. Search for the author's known positions on this topic (blog posts, interviews, other scholars citing them)
3. Search for whether other scholars dispute or confirm this specific claim

CRITICAL RULES:
- Page numbers are unverifiable unless you find the exact page in a freely accessible online source
- "I found a review that says this author argues X" is CORROBORATING, not VERIFIED
- If you find evidence that directly contradicts the attributed argument, flag it clearly
- Express uncertainty explicitly throughout

After your searches, respond with a single JSON object:

{
  "claim_id": "...",
  "pass": 3,
  "bibliographic_status": "CONFIRMED | UNCONFIRMED | CONFLICTING",
  "bibliographic_source": "what you found or null",
  "argument_status": "CORROBORATED | PLAUSIBLE | UNCLEAR | CONTRADICTED",
  "argument_evidence": "what secondary sources you found, or null",
  "overall_verdict": "LIKELY_ACCURATE | LIKELY_ACCURATE_BUT_CONTESTED | PARTIALLY_VERIFIED | NEEDS_HUMAN_REVIEW | FABRICATION_RISK",
  "human_review_priority": "HIGH | MEDIUM | LOW",
  "summary": "two-sentence plain-language summary of what you found"
}

Respond with ONLY the JSON object. No preamble."""


def build_pass3_prompt(citation: dict) -> str:
    return f"""This citation requires deep investigation. It was flagged because bibliographic confirmation was not found, or Pass 1 identified a high suspicion level.

CLAIM ID: {citation['claim_id']}
ADVOCATE: {citation['advocate']}
CLAIM: {citation['claim']}
SOURCE: {citation['source']}
ARGUMENT: {citation['argument']}
ADVOCATE CONFIDENCE: {citation['advocate_confidence']}

Perform up to 3 targeted searches and return your JSON verdict."""


# ---------------------------------------------------------------------------
# Result merging
# ---------------------------------------------------------------------------

def merge_pass_results(
    citation: dict,
    pass1: dict | None,
    pass2: dict | None,
    pass3: dict | None,
) -> dict:
    """
    Combine results from all three passes into the final verdict format
    consumed by audit_worksheet and generate_moderator_input.
    """
    claim_id = citation["claim_id"]

    # Determine overall verdict from available passes
    overall_verdict = "NEEDS_HUMAN_REVIEW"
    human_review_needed = True
    human_review_priority = "MEDIUM"
    summary_parts = []

    p1_suspicion = (pass1 or {}).get("suspicion_level", "MEDIUM")
    p2_status = (pass2 or {}).get("bibliographic_status", "UNCONFIRMED")
    p3_verdict = (pass3 or {}).get("overall_verdict")

    # Fabrication risk takes priority
    if p1_suspicion == "HIGH" or p3_verdict == "FABRICATION_RISK":
        overall_verdict = "FABRICATION_RISK"
        human_review_needed = True
        human_review_priority = "HIGH"
    elif p3_verdict in ("LIKELY_ACCURATE", "LIKELY_ACCURATE_BUT_CONTESTED", "PARTIALLY_VERIFIED"):
        overall_verdict = p3_verdict
        human_review_needed = p3_verdict not in ("LIKELY_ACCURATE",)
        human_review_priority = "LOW" if p3_verdict == "LIKELY_ACCURATE" else "MEDIUM"
    elif p2_status == "CONFIRMED" and p1_suspicion == "LOW":
        overall_verdict = "LIKELY_ACCURATE"
        human_review_needed = False
        human_review_priority = None
    elif p2_status == "CONFIRMED" and p1_suspicion == "MEDIUM":
        overall_verdict = "PARTIALLY_VERIFIED"
        human_review_needed = True
        human_review_priority = "MEDIUM"
    elif p2_status == "CONFLICTING":
        overall_verdict = "NEEDS_HUMAN_REVIEW"
        human_review_needed = True
        human_review_priority = "HIGH"
    else:
        overall_verdict = "NEEDS_HUMAN_REVIEW"
        human_review_needed = True
        human_review_priority = "MEDIUM"

    # Build summary
    if pass1:
        summary_parts.append(
            f"Pass 1 (training): bibliographic={pass1.get('bibliographic_plausibility')}, "
            f"argument={pass1.get('argument_direction')}, suspicion={p1_suspicion}."
        )
        if pass1.get("suspicion_reason"):
            summary_parts.append(f"Suspicion: {pass1['suspicion_reason']}")
    if pass2:
        summary_parts.append(
            f"Pass 2 (bibliographic search): {p2_status}. "
            + (f"Source: {pass2['source_found']}." if pass2.get("source_found") else "No source found.")
        )
    if pass3:
        summary_parts.append(
            f"Pass 3 (deep): {p3_verdict}. {pass3.get('summary', '')}"
        )

    return {
        "claim_id": claim_id,
        "verification": {
            "bibliographic": {
                "status": _bib_status(pass1, pass2, pass3),
                "note": (pass2 or {}).get("note") or (pass1 or {}).get("bibliographic_note") or "",
            },
            "topical": {
                "status": "VERIFIED" if p2_status == "CONFIRMED" else "UNVERIFIABLE",
                "note": (pass3 or {}).get("argument_evidence") or "",
            },
            "argument_direction": {
                "status": _arg_status(pass1, pass3),
                "note": (pass3 or {}).get("argument_evidence") or (pass1 or {}).get("argument_note") or "",
                "corroborating_evidence": [pass2["source_found"]] if pass2 and pass2.get("source_found") else [],
            },
            "page_number": {
                "status": "UNVERIFIABLE",
                "note": "Page numbers are not verifiable through automated checks.",
            },
            "consensus_check": {
                "status": "NOT_APPLICABLE",
                "note": "",
            },
        },
        "overall_verdict": overall_verdict,
        "human_review_needed": human_review_needed,
        "human_review_priority": human_review_priority,
        "summary": " ".join(summary_parts),
        "_passes": {
            "pass1": pass1,
            "pass2": pass2,
            "pass3": pass3,
        },
    }


def _bib_status(p1, p2, p3) -> str:
    p2s = (p2 or {}).get("bibliographic_status", "")
    p3s = (p3 or {}).get("bibliographic_status", "")
    if "CONFIRMED" in (p2s, p3s):
        return "VERIFIED"
    if "CONFLICTING" in (p2s, p3s):
        return "FAILED"
    p1b = (p1 or {}).get("bibliographic_plausibility", "")
    if p1b == "RECOGNIZED":
        return "LIKELY"
    return "UNVERIFIABLE"


def _arg_status(p1, p3) -> str:
    p3s = (p3 or {}).get("argument_status", "")
    if p3s == "CORROBORATED":
        return "CONFIRMED"
    if p3s == "CONTRADICTED":
        return "CONTRADICTED"
    p1a = (p1 or {}).get("argument_direction", "")
    if p1a == "CONSISTENT":
        return "LIKELY"
    if p1a == "CONTRADICTS_KNOWN_POSITION":
        return "CONTRADICTED"
    return "UNCLEAR"


# ---------------------------------------------------------------------------
# JSON parsing helper (used for all three passes)
# ---------------------------------------------------------------------------

def parse_json_response(response_text: str, expect_array: bool = True):
    """
    Parse a verifier JSON response. Returns list (Pass 1) or dict (Pass 2/3).
    Handles markdown fencing and preamble text.
    """
    text = response_text.strip()

    # Strip markdown fencing
    text = re.sub(r'^```json\s*', '', text)
    text = re.sub(r'^```\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    text = text.strip()

    if expect_array:
        start = text.find('[')
        end = text.rfind(']') + 1
        if start >= 0 and end > start:
            text = text[start:end]
    else:
        start = text.find('{')
        end = text.rfind('}') + 1
        if start >= 0 and end > start:
            text = text[start:end]

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"WARNING: Could not parse verifier response as JSON: {e}")
        print(f"Response starts with: {text[:200]}")
        return [] if expect_array else {}


# ---------------------------------------------------------------------------
# Legacy shim — keeps existing callers working during transition
# ---------------------------------------------------------------------------

VERIFIER_SYSTEM_PROMPT = PASS3_SYSTEM_PROMPT


def build_verification_prompt(citations: list[dict], batch_size: int = 5) -> list[str]:
    return build_pass1_prompts(citations, batch_size)


def parse_verification_response(response_text: str) -> list[dict]:
    result = parse_json_response(response_text, expect_array=True)
    return result if isinstance(result, list) else []
