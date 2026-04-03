"""
Citation Extractor
Parses advocate debate outputs and extracts structured [CLAIM][SOURCE][ARGUMENT][CONFIDENCE] blocks
and [CITATION_RESPONSE] correction acknowledgment blocks.
"""

import re
import json
from dataclasses import dataclass, asdict, field
from typing import Optional


@dataclass
class CitationResponse:
    """Structured response to a citation correction, using [CITATION_RESPONSE] blocks."""
    response_id: str            # e.g. "R2_BS_RESP_001"
    round: int
    advocate: str
    original_claim_id: str      # links to the Citation being responded to
    correction_received: str    # FABRICATION_RISK / HARD_CORRECTION / SOFT_FLAG
    advocate_position: str      # WITHDRAW / QUALIFY / DEFEND
    revised_claim: str
    revised_source: str         # empty string if no new source
    revised_confidence: str     # HIGH / MEDIUM / LOW / ""
    response_note: str
    downstream_status: str      # ACTIVE / RESTRICTED / RETRACTED
    raw_text: str

    def to_dict(self):
        return asdict(self)


@dataclass
class Citation:
    claim_id: str
    round: int
    advocate: str
    claim: str
    source: str
    argument: str
    advocate_confidence: str  # HIGH / MEDIUM / LOW
    raw_text: str  # The original block as it appeared in output
    context: str  # Surrounding sentence/paragraph for auditor reference
    _original_response_id: str = ""  # Set when citation is derived from a CITATION_RESPONSE block

    def to_dict(self):
        return asdict(self)


def extract_citations(
    advocate_output: str,
    advocate_id: str,
    round_number: int
) -> list[Citation]:
    """
    Extract all citation blocks from a single advocate's round output.
    
    Looks for blocks in this format:
    [CLAIM: ...]
    [SOURCE: ...]
    [ARGUMENT: ...]
    [CONFIDENCE: ...]
    
    Blocks may have whitespace variations and may not always have all four fields.
    """
    citations = []
    
    # Pattern matches a citation block: CLAIM followed by SOURCE, ARGUMENT, CONFIDENCE
    # in any order, allowing for line breaks and whitespace between fields
    block_pattern = re.compile(
        r'\[CLAIM:\s*(.+?)\]\s*'
        r'\[SOURCE:\s*(.+?)\]\s*'
        r'\[ARGUMENT:\s*(.+?)\]\s*'
        r'\[CONFIDENCE:\s*(.+?)\]',
        re.DOTALL
    )
    
    # Also try a more lenient pattern for blocks that might be on single lines
    # or have slightly different formatting
    lenient_pattern = re.compile(
        r'\[CLAIM:\s*(.+?)\].*?'
        r'\[SOURCE:\s*(.+?)\].*?'
        r'\[ARGUMENT:\s*(.+?)\].*?'
        r'\[CONFIDENCE:\s*(.+?)\]',
        re.DOTALL
    )
    
    matches = block_pattern.findall(advocate_output)
    if not matches:
        matches = lenient_pattern.findall(advocate_output)
    
    for i, match in enumerate(matches):
        claim_text = match[0].strip()
        source_text = match[1].strip()
        argument_text = match[2].strip()
        confidence_text = match[3].strip().upper()
        
        # Normalize confidence
        if confidence_text not in ("HIGH", "MEDIUM", "LOW"):
            # Try to extract just the level if there's extra text
            for level in ("HIGH", "MEDIUM", "LOW"):
                if level in confidence_text:
                    confidence_text = level
                    break
            else:
                confidence_text = "UNKNOWN"
        
        # Get context: find the citation block in the original text 
        # and grab the surrounding paragraph
        raw_block = f"[CLAIM: {match[0]}][SOURCE: {match[1]}][ARGUMENT: {match[2]}][CONFIDENCE: {match[3]}]"
        context = _get_surrounding_context(advocate_output, match[0][:50])
        
        claim_id = f"R{round_number}_{_advocate_abbrev(advocate_id)}_{i+1:03d}"
        
        citations.append(Citation(
            claim_id=claim_id,
            round=round_number,
            advocate=advocate_id,
            claim=claim_text,
            source=source_text,
            argument=argument_text,
            advocate_confidence=confidence_text,
            raw_text=raw_block,
            context=context
        ))
    
    return citations


def _advocate_abbrev(advocate_id: str) -> str:
    """Short abbreviation for claim IDs.

    Generates a 2-3 letter abbreviation from any advocate_id by taking the first
    letter of each word (snake_case segments). Falls back to first two characters.
    Legacy hardcoded abbreviations are preserved for backward compatibility with
    existing claim IDs from the theology debate.
    """
    _LEGACY_ABBREVS = {
        "biblical_scholar": "BS",
        "reception_historian": "RH",
        "hermeneutician": "HM",
        "systematic_theologian": "ST",
        "pastoral_theologian": "PT",
        "social_cultural_analyst": "SA",
    }
    if advocate_id in _LEGACY_ABBREVS:
        return _LEGACY_ABBREVS[advocate_id]
    # Generate from snake_case: "legal_scholar" -> "LS", "economist" -> "EC"
    parts = advocate_id.split("_")
    if len(parts) >= 2:
        return "".join(p[0].upper() for p in parts if p)
    return advocate_id[:2].upper()


def _get_surrounding_context(text: str, search_fragment: str, context_chars: int = 300) -> str:
    """Get surrounding text for auditor context."""
    pos = text.find(search_fragment)
    if pos == -1:
        return ""
    start = max(0, pos - context_chars)
    end = min(len(text), pos + len(search_fragment) + context_chars)
    context = text[start:end]
    if start > 0:
        context = "..." + context
    if end < len(text):
        context = context + "..."
    return context


def extract_all_round_citations(
    round_outputs: dict[str, str],
    round_number: int
) -> list[Citation]:
    """
    Extract citations from all advocates in a round.
    
    Args:
        round_outputs: dict mapping advocate_id -> their output text
        round_number: which round
    
    Returns:
        All citations from all advocates, ordered by advocate then sequence
    """
    all_citations = []
    for advocate_id, output in round_outputs.items():
        citations = extract_citations(output, advocate_id, round_number)
        all_citations.extend(citations)
    return all_citations


def save_citations(citations: list[Citation], output_path: str):
    """Save extracted citations to JSON."""
    data = [c.to_dict() for c in citations]
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)


def load_citations(input_path: str) -> list[Citation]:
    """Load citations from JSON."""
    with open(input_path, 'r') as f:
        data = json.load(f)
    return [Citation(**d) for d in data]


def extract_citation_responses(
    advocate_output: str,
    advocate_id: str,
    round_number: int
) -> list[CitationResponse]:
    """
    Extract all [CITATION_RESPONSE] blocks from an advocate's round output.

    Format:
    [CITATION_RESPONSE: claim_id]
    [CORRECTION_RECEIVED: ...]
    [ADVOCATE_POSITION: WITHDRAW / QUALIFY / DEFEND]
    [REVISED_CLAIM: ...]
    [REVISED_SOURCE: ...]
    [REVISED_CONFIDENCE: ...]
    [RESPONSE_NOTE: ...]
    [DOWNSTREAM_STATUS: ACTIVE / RESTRICTED / RETRACTED]
    """
    responses = []

    # Match the full block — all fields after CITATION_RESPONSE up to DOWNSTREAM_STATUS
    block_pattern = re.compile(
        r'\[CITATION_RESPONSE:\s*(.+?)\]\s*'
        r'\[CORRECTION_RECEIVED:\s*(.+?)\]\s*'
        r'\[ADVOCATE_POSITION:\s*(.+?)\]\s*'
        r'(?:\[REVISED_CLAIM:\s*(.*?)\]\s*)?'
        r'(?:\[REVISED_SOURCE:\s*(.*?)\]\s*)?'
        r'(?:\[REVISED_CONFIDENCE:\s*(.*?)\]\s*)?'
        r'(?:\[RESPONSE_NOTE:\s*(.*?)\]\s*)?'
        r'\[DOWNSTREAM_STATUS:\s*(.+?)\]',
        re.DOTALL
    )

    abbrev = _advocate_abbrev(advocate_id)

    for i, m in enumerate(block_pattern.finditer(advocate_output)):
        original_claim_id = m.group(1).strip()
        correction_received = m.group(2).strip().upper()
        advocate_position = m.group(3).strip().upper()
        revised_claim = (m.group(4) or "").strip()
        revised_source = (m.group(5) or "").strip()
        revised_confidence = (m.group(6) or "").strip().upper()
        response_note = (m.group(7) or "").strip()
        downstream_status = m.group(8).strip().upper()

        # Enforce rules
        if advocate_position == "WITHDRAW":
            downstream_status = "RETRACTED"
        elif advocate_position == "DEFEND" and not revised_source:
            revised_confidence = "LOW"
            if downstream_status == "ACTIVE":
                downstream_status = "RESTRICTED"
        elif advocate_position == "QUALIFY":
            if downstream_status == "ACTIVE":
                downstream_status = "RESTRICTED"

        # Normalize downstream_status
        if downstream_status not in ("ACTIVE", "RESTRICTED", "RETRACTED"):
            downstream_status = "RESTRICTED"

        response_id = f"R{round_number}_{abbrev}_RESP_{i + 1:03d}"

        responses.append(CitationResponse(
            response_id=response_id,
            round=round_number,
            advocate=advocate_id,
            original_claim_id=original_claim_id,
            correction_received=correction_received,
            advocate_position=advocate_position,
            revised_claim=revised_claim,
            revised_source=revised_source,
            revised_confidence=revised_confidence,
            response_note=response_note,
            downstream_status=downstream_status,
            raw_text=m.group(0),
        ))

    return responses


def extract_all_round_responses(
    round_outputs: dict[str, str],
    round_number: int
) -> list[CitationResponse]:
    """Extract citation responses from all advocates in a round."""
    all_responses = []
    for advocate_id, output in round_outputs.items():
        responses = extract_citation_responses(output, advocate_id, round_number)
        all_responses.extend(responses)
    return all_responses


def save_citation_responses(responses: list[CitationResponse], output_path: str):
    """Save extracted citation responses to JSON."""
    data = [r.to_dict() for r in responses]
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)


def load_citation_responses(input_path: str) -> list[CitationResponse]:
    """Load citation responses from JSON."""
    with open(input_path, 'r') as f:
        data = json.load(f)
    return [CitationResponse(**d) for d in data]


if __name__ == "__main__":
    # Quick test with example output
    test_output = """
The creation narrative establishes something the debate has not fully reckoned with.

[CLAIM: The Hebrew word ezer, used of the woman in Genesis 2:18, carries no connotation of subordination]
[SOURCE: Victor Hamilton, The Book of Genesis, NICOT, Eerdmans, 1990]
[ARGUMENT: Hamilton demonstrates that ezer is used of God himself in Psalm 121:1-2 and Exodus 18:4, making a subordination reading untenable]
[CONFIDENCE: HIGH]

This is significant because the word establishes the woman as a corresponding strength, not an assistant.

[CLAIM: authenteo is an extremely rare word in ancient Greek, occurring only once in the entire NT]
[SOURCE: Nijay Gupta, Tell Her Story, IVP Academic, 2023, p. 170]
[ARGUMENT: Gupta argues the word's rarity and pattern of use in ancient sources suggests it describes an abuse of power rather than neutral exercise of authority]
[CONFIDENCE: MEDIUM — lexical debate is genuinely contested]
"""
    
    citations = extract_citations(test_output, "biblical_scholar", 1)
    for c in citations:
        print(f"\n{c.claim_id}: {c.claim[:80]}...")
        print(f"  Source: {c.source}")
        print(f"  Confidence: {c.advocate_confidence}")
