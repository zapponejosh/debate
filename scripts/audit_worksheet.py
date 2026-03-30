"""
Audit Worksheet Generator
Produces a human-readable markdown audit worksheet from verification results.
Only includes claims that need human review.
"""

import json
from datetime import datetime


# Which verdicts route to human review
ALWAYS_REVIEW = {"FABRICATION_RISK", "NEEDS_HUMAN_REVIEW"}
CONDITIONAL_REVIEW = {"PARTIALLY_VERIFIED"}  # Only if advocate claimed HIGH confidence


def generate_audit_worksheet(
    citations: list[dict],
    verifications: list[dict],
    round_number: int,
    output_path: str
):
    """
    Generate the human audit worksheet.
    
    Args:
        citations: Original extracted citations (list of dicts)
        verifications: Verification results from the verifier agent (list of dicts)  
        round_number: Which debate round
        output_path: Where to write the markdown worksheet
    """
    # Build lookup from claim_id to citation and verification
    citation_map = {c["claim_id"]: c for c in citations}
    verification_map = {v["claim_id"]: v for v in verifications}
    
    # Determine which claims need human review
    review_items = []
    auto_resolved = []
    
    for cit in citations:
        cid = cit["claim_id"]
        ver = verification_map.get(cid)
        
        if ver is None:
            # Verification missing — always needs review
            review_items.append({
                "citation": cit,
                "verification": None,
                "priority": "MEDIUM",
                "reason": "No automated verification was produced for this citation."
            })
            continue
        
        verdict = ver.get("overall_verdict", "NEEDS_HUMAN_REVIEW")
        
        if verdict in ALWAYS_REVIEW:
            priority = "HIGH" if verdict == "FABRICATION_RISK" else "MEDIUM"
            review_items.append({
                "citation": cit,
                "verification": ver,
                "priority": priority,
                "reason": ver.get("summary", "Automated verification inconclusive.")
            })
        elif verdict in CONDITIONAL_REVIEW and cit.get("advocate_confidence") == "HIGH":
            review_items.append({
                "citation": cit,
                "verification": ver,
                "priority": "LOW",
                "reason": f"Advocate claimed HIGH confidence but verification returned {verdict}."
            })
        else:
            auto_resolved.append({
                "citation": cit,
                "verification": ver
            })
    
    # Sort review items: HIGH first, then MEDIUM, then LOW
    priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    review_items.sort(key=lambda x: priority_order.get(x["priority"], 3))
    
    # Generate the worksheet
    md = _build_worksheet_markdown(review_items, auto_resolved, round_number)
    
    with open(output_path, 'w') as f:
        f.write(md)
    
    print(f"Audit worksheet written to {output_path}")
    print(f"  Claims needing review: {len(review_items)}")
    print(f"  Auto-resolved: {len(auto_resolved)}")
    print(f"  HIGH priority: {sum(1 for x in review_items if x['priority'] == 'HIGH')}")
    
    return review_items, auto_resolved


def _build_worksheet_markdown(
    review_items: list[dict],
    auto_resolved: list[dict],
    round_number: int
) -> str:
    """Build the full markdown worksheet."""
    
    lines = []
    lines.append(f"# Citation Audit Worksheet — Round {round_number}")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Total citations this round:** {len(review_items) + len(auto_resolved)}")
    lines.append(f"- **Auto-resolved (no action needed):** {len(auto_resolved)}")
    lines.append(f"- **Needs human review:** {len(review_items)}")
    
    high = sum(1 for x in review_items if x["priority"] == "HIGH")
    medium = sum(1 for x in review_items if x["priority"] == "MEDIUM")
    low = sum(1 for x in review_items if x["priority"] == "LOW")
    lines.append(f"  - HIGH priority: {high}")
    lines.append(f"  - MEDIUM priority: {medium}")
    lines.append(f"  - LOW priority: {low}")
    lines.append("")
    lines.append("**Estimated audit time:** " + _estimate_time(high, medium, low))
    lines.append("")
    
    lines.append("---")
    lines.append("")
    lines.append("## How to Use This Worksheet")
    lines.append("")
    lines.append("For each claim below, the automated verifier has already checked what it can.")
    lines.append("Your job is to resolve what it couldn't. For each claim:")
    lines.append("")
    lines.append("1. Read the CLAIM, SOURCE, and the AUTOMATED RESULT")
    lines.append("2. Follow the SEARCH SUGGESTIONS if you need to investigate")
    lines.append("3. Fill in your VERDICT using one of the categories below")
    lines.append("4. Assess the IMPACT — how much does this claim matter to the argument?")
    lines.append("5. Recommend an ACTION if needed")
    lines.append("")
    lines.append("### Verdict Categories")
    lines.append("")
    lines.append("| Verdict | Meaning |")
    lines.append("|---------|---------|")
    lines.append("| **CONFIRMED** | Found in the original source or a direct reproduction of it |")
    lines.append("| **CONFIRMED_INDIRECT** | Not found in original, but corroborated by other reliable evidence (author's blog, book review, secondary citation, lecture). Specify the evidence. |")
    lines.append("| **PLAUSIBLE_BUT_UNCONFIRMED** | Consistent with the source's known content/position, but you cannot confirm this specific detail. No contradicting evidence found. |")
    lines.append("| **LIKELY_FABRICATED** | Evidence contradicts this specific claim, or no trace found despite thorough search. The detail appears to be LLM-generated. |")
    lines.append("| **CANNOT_DETERMINE** | Insufficient access or evidence to resolve either way |")
    lines.append("")
    
    # HIGH priority items
    if high > 0:
        lines.append("---")
        lines.append("")
        lines.append("## HIGH PRIORITY — Possible Fabrications")
        lines.append("")
        lines.append("*These claims have features suggesting the LLM may have fabricated details.*")
        lines.append("*Address these first.*")
        lines.append("")
        for item in review_items:
            if item["priority"] == "HIGH":
                lines.extend(_build_claim_card(item))
    
    # MEDIUM priority items
    if medium > 0:
        lines.append("---")
        lines.append("")
        lines.append("## MEDIUM PRIORITY — Needs Verification")
        lines.append("")
        lines.append("*The automated verifier could not resolve these claims.*")
        lines.append("")
        for item in review_items:
            if item["priority"] == "MEDIUM":
                lines.extend(_build_claim_card(item))
    
    # LOW priority items
    if low > 0:
        lines.append("---")
        lines.append("")
        lines.append("## LOW PRIORITY — Confidence Mismatch")
        lines.append("")
        lines.append("*The advocate claimed HIGH confidence but the verifier couldn't fully confirm.*")
        lines.append("*Review if time permits.*")
        lines.append("")
        for item in review_items:
            if item["priority"] == "LOW":
                lines.extend(_build_claim_card(item))
    
    # Auto-resolved summary
    lines.append("---")
    lines.append("")
    lines.append("## Auto-Resolved Claims (No Action Needed)")
    lines.append("")
    lines.append("These claims were resolved by the automated verifier. Listed for reference.")
    lines.append("")
    for item in auto_resolved:
        cit = item["citation"]
        ver = item["verification"]
        verdict = ver.get("overall_verdict", "?") if ver else "?"
        lines.append(f"- **{cit['claim_id']}** ({cit['advocate']}): {cit['claim'][:80]}... → {verdict}")
    
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Auditor Sign-Off")
    lines.append("")
    lines.append("Auditor name: ____________________")
    lines.append("")
    lines.append("Date completed: ____________________")
    lines.append("")
    lines.append("Total claims reviewed: ____________________")
    lines.append("")
    lines.append("Claims flagged for correction: ____________________")
    lines.append("")
    lines.append("Notes:")
    lines.append("")
    lines.append("")
    
    return "\n".join(lines)


def _build_claim_card(item: dict) -> list[str]:
    """Build a single claim review card."""
    cit = item["citation"]
    ver = item.get("verification")
    
    lines = []
    lines.append("```")
    lines.append("═" * 60)
    lines.append(f"CLAIM ID: {cit['claim_id']}")
    lines.append(f"PRIORITY: {item['priority']}")
    lines.append(f"ADVOCATE: {cit['advocate']}")
    lines.append(f"ROUND: {cit['round']}")
    lines.append("")
    lines.append(f"CLAIM: {cit['claim']}")
    lines.append("")
    lines.append(f"SOURCE: {cit['source']}")
    lines.append("")
    lines.append(f"ARGUMENT ATTRIBUTED: {cit['argument']}")
    lines.append("")
    lines.append(f"ADVOCATE CONFIDENCE: {cit['advocate_confidence']}")
    lines.append("")
    
    if ver:
        lines.append(f"AUTOMATED VERDICT: {ver.get('overall_verdict', 'N/A')}")
        lines.append(f"REASON: {item['reason']}")
        lines.append("")
        
        # Show what the verifier found
        v = ver.get("verification", {})
        bib = v.get("bibliographic", {})
        lines.append(f"  Bibliographic: {bib.get('status', '?')} — {bib.get('note', '')}")
        top = v.get("topical", {})
        lines.append(f"  Topical: {top.get('status', '?')} — {top.get('note', '')}")
        arg = v.get("argument_direction", {})
        lines.append(f"  Argument: {arg.get('status', '?')} — {arg.get('note', '')}")
        
        # Show corroborating evidence if any
        corr = arg.get("corroborating_evidence", [])
        if corr:
            lines.append("")
            lines.append("  CORROBORATING EVIDENCE FOUND:")
            for e in corr:
                lines.append(f"    • {e}")
    else:
        lines.append("AUTOMATED VERDICT: No verification produced")
        lines.append(f"REASON: {item['reason']}")
    
    lines.append("")
    lines.append("SEARCH SUGGESTIONS:")
    lines.extend(_generate_search_suggestions(cit))
    lines.append("")
    lines.append("─" * 60)
    lines.append("AUDITOR VERDICT: [                              ]")
    lines.append("")
    lines.append("  ( ) CONFIRMED")
    lines.append("  ( ) CONFIRMED_INDIRECT")
    lines.append("      Type of indirect evidence:")
    lines.append("        ( ) Author's own writing elsewhere")
    lines.append("        ( ) Another scholar citing this work")
    lines.append("        ( ) Book review discussing this point")
    lines.append("        ( ) Different work by same author, same argument")
    lines.append("        ( ) General scholarly consensus consistent")
    lines.append("        ( ) Other: _______________")
    lines.append("      Source: [                              ]")
    lines.append("      Confidence: ( ) Strong  ( ) Moderate  ( ) Weak")
    lines.append("  ( ) PLAUSIBLE_BUT_UNCONFIRMED")
    lines.append("  ( ) LIKELY_FABRICATED")
    lines.append("  ( ) CANNOT_DETERMINE")
    lines.append("")
    lines.append("AUDITOR NOTES:")
    lines.append("[                                              ]")
    lines.append("")
    lines.append("IMPACT: How important is this claim to the argument?")
    lines.append("  ( ) Load-bearing — argument depends on this")
    lines.append("  ( ) Supporting — one piece of evidence among several")
    lines.append("  ( ) Illustrative — example only, argument stands without it")
    lines.append("")
    lines.append("ACTION:")
    lines.append("  ( ) No action needed")
    lines.append("  ( ) Flag for moderator to note in next round")
    lines.append("  ( ) Requires correction in canonical record")
    lines.append("  ( ) Advocate should revise or remove")
    lines.append("═" * 60)
    lines.append("```")
    lines.append("")
    
    return lines


def _generate_search_suggestions(citation: dict) -> list[str]:
    """Generate search suggestions based on the citation content."""
    suggestions = []
    source = citation.get("source", "")
    claim = citation.get("claim", "")
    
    # Parse author from source
    author = source.split(",")[0].strip() if "," in source else source.split(" ")[0]
    
    # Parse title (usually between first and second comma)
    parts = source.split(",")
    title = parts[1].strip() if len(parts) > 1 else ""
    
    # Extract key terms from the claim
    key_terms = _extract_key_terms(claim)
    
    suggestions.append(f'  - "{author} {title}" (confirm book exists)')
    if key_terms:
        suggestions.append(f'  - "{author} {key_terms[0]}" (check author\'s position)')
    if len(key_terms) > 1:
        suggestions.append(f'  - "{key_terms[0]} {key_terms[1]} scholarly debate" (check consensus)')
    suggestions.append(f'  - Check Google Scholar for: {author} + key claim terms')
    
    return suggestions


def _extract_key_terms(claim: str) -> list[str]:
    """Extract likely important terms from a claim for search suggestions."""
    # Simple approach: take capitalized words and theological/technical terms
    technical_terms = {
        "authenteo", "kephale", "ezer", "diakonos", "prostatis", "apostolos",
        "haustafeln", "ministrae", "presbytera", "transcultural",
        "complementarian", "egalitarian", "ordination", "ecclesiology"
    }
    
    words = claim.lower().split()
    found = [w for w in words if w in technical_terms]
    
    # Also grab any quoted or emphasized terms
    import re
    quoted = re.findall(r'["\'](.+?)["\']', claim)
    found.extend(quoted)
    
    # If we didn't find technical terms, grab the longest non-common words
    if not found:
        common = {"the", "a", "an", "is", "was", "are", "in", "of", "to", "for", 
                  "and", "that", "this", "with", "from", "not", "but", "by", "as"}
        found = sorted(
            [w for w in words if w not in common and len(w) > 4],
            key=len, reverse=True
        )[:2]
    
    return found[:3]


def _estimate_time(high: int, medium: int, low: int) -> str:
    """Rough time estimate for the human auditor."""
    # HIGH items: ~10 min each (need careful investigation)
    # MEDIUM items: ~5 min each  
    # LOW items: ~3 min each
    minutes = high * 10 + medium * 5 + low * 3
    if minutes < 60:
        return f"~{minutes} minutes"
    hours = minutes / 60
    return f"~{hours:.1f} hours"


def generate_moderator_input(
    citations: list[dict],
    verifications: list[dict],
    audit_results: list[dict] | None = None,
    round_number: int = 1
) -> str:
    """
    Generate the moderator's input document from verification and audit results.
    
    This is what the moderator agent receives to produce the fact-check report
    for inclusion in the canonical debate record.
    """
    lines = []
    lines.append(f"# Verification Results — Round {round_number}")
    lines.append(f"## For Moderator Use")
    lines.append("")
    
    # Corrections needed
    corrections = []
    contested = []
    unverified = []
    clean = []
    
    ver_map = {v["claim_id"]: v for v in verifications}
    audit_map = {}
    if audit_results:
        audit_map = {a["claim_id"]: a for a in audit_results}
    
    for cit in citations:
        cid = cit["claim_id"]
        ver = ver_map.get(cid, {})
        aud = audit_map.get(cid, {})
        
        verdict = ver.get("overall_verdict", "UNVERIFIED")
        audit_verdict = aud.get("auditor_verdict", None)
        
        # Determine final status
        if audit_verdict == "LIKELY_FABRICATED":
            corrections.append({"citation": cit, "verification": ver, "audit": aud})
        elif verdict == "FABRICATION_RISK" and audit_verdict is None:
            corrections.append({"citation": cit, "verification": ver, "audit": aud})
        elif "CONTESTED" in verdict:
            contested.append({"citation": cit, "verification": ver, "audit": aud})
        elif verdict in ("NEEDS_HUMAN_REVIEW", "UNVERIFIED") and audit_verdict is None:
            unverified.append({"citation": cit, "verification": ver, "audit": aud})
        else:
            clean.append({"citation": cit, "verification": ver, "audit": aud})
    
    lines.append(f"### Claims Needing Correction ({len(corrections)})")
    lines.append("")
    for item in corrections:
        cit = item["citation"]
        lines.append(f"- **{cit['claim_id']}** ({cit['advocate']}): {cit['claim']}")
        lines.append(f"  Source cited: {cit['source']}")
        aud = item.get("audit", {})
        if aud.get("auditor_notes"):
            lines.append(f"  Auditor note: {aud['auditor_notes']}")
        lines.append("")
    
    lines.append(f"### Contested Claims — Flag as SOFT ({len(contested)})")
    lines.append("")
    for item in contested:
        cit = item["citation"]
        ver = item.get("verification", {})
        cc = ver.get("verification", {}).get("consensus_check", {})
        lines.append(f"- **{cit['claim_id']}** ({cit['advocate']}): {cit['claim']}")
        if cc.get("note"):
            lines.append(f"  Dissenting voices: {cc['note']}")
        lines.append("")
    
    lines.append(f"### Unverified Claims ({len(unverified)})")
    lines.append("")
    for item in unverified:
        cit = item["citation"]
        lines.append(f"- **{cit['claim_id']}** ({cit['advocate']}): {cit['claim']}")
        lines.append(f"  Source cited: {cit['source']}")
        lines.append("")
    
    lines.append(f"### Clean Claims ({len(clean)})")
    lines.append(f"*{len(clean)} citations verified or confirmed. No action needed.*")
    lines.append("")
    
    return "\n".join(lines)


if __name__ == "__main__":
    # Test with sample data
    sample_citations = [
        {
            "claim_id": "R1_BS_001",
            "round": 1,
            "advocate": "biblical_scholar",
            "claim": "The Hebrew word ezer carries no connotation of subordination",
            "source": "Victor Hamilton, The Book of Genesis, NICOT, Eerdmans, 1990",
            "argument": "Hamilton demonstrates ezer is used of God in Psalm 121 and Exodus 18:4",
            "advocate_confidence": "HIGH",
            "raw_text": "",
            "context": ""
        },
        {
            "claim_id": "R1_RH_003",
            "round": 1,
            "advocate": "reception_historian",
            "claim": "Epigraphic evidence from the Salona region documents a woman presbytera",
            "source": "Madigan & Osiek, Ordained Women in the Early Church, Johns Hopkins, 2005",
            "argument": "Documents inscriptional evidence of ordained women",
            "advocate_confidence": "HIGH",
            "raw_text": "",
            "context": ""
        }
    ]
    
    sample_verifications = [
        {
            "claim_id": "R1_BS_001",
            "overall_verdict": "VERIFIED",
            "verification": {
                "bibliographic": {"status": "VERIFIED", "note": "Book confirmed"},
                "topical": {"status": "VERIFIED", "note": "Hamilton discusses ezer"},
                "argument_direction": {"status": "CONFIRMED", "note": "Consistent with Hamilton's known position", "corroborating_evidence": []},
                "page_number": {"status": "NOT_CLAIMED", "note": ""},
                "consensus_check": {"status": "NOT_APPLICABLE", "note": ""}
            },
            "human_review_needed": False,
            "human_review_priority": None,
            "summary": "Verified."
        },
        {
            "claim_id": "R1_RH_003",
            "overall_verdict": "FABRICATION_RISK",
            "verification": {
                "bibliographic": {"status": "VERIFIED", "note": "Book confirmed"},
                "topical": {"status": "VERIFIED", "note": "Madigan & Osiek document ordained women"},
                "argument_direction": {"status": "UNCLEAR", "note": "Could not confirm Salona specifically", "corroborating_evidence": []},
                "page_number": {"status": "NOT_CLAIMED", "note": ""},
                "consensus_check": {"status": "NOT_APPLICABLE", "note": ""}
            },
            "human_review_needed": True,
            "human_review_priority": "HIGH",
            "summary": "Book verified. Salona detail could not be confirmed — possible fabrication."
        }
    ]
    
    generate_audit_worksheet(
        sample_citations,
        sample_verifications,
        round_number=1,
        output_path="/home/claude/test_audit_worksheet.md"
    )
