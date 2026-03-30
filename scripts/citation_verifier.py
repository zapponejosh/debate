"""
Citation Verifier Agent
System prompt and call logic for the automated verification pass.

This agent uses web search to verify citations. It runs as a separate 
Anthropic API call with web search enabled — NOT as part of the debate agents.
"""

VERIFIER_SYSTEM_PROMPT = """You are a citation verification agent for an academic theological debate. Your ONLY job is to check whether citations are accurate. You do not evaluate theological arguments.

For each citation you receive, perform these checks:

1. BIBLIOGRAPHIC CHECK
   Search for: author + title + publisher + year
   Confirm the book/article exists with these publication details.
   
2. TOPICAL CHECK  
   Search for: author + title + [key topic from the claim]
   Confirm the author addresses this topic in this work.
   Look for: table of contents, reviews, abstracts, publisher descriptions.

3. ARGUMENT DIRECTION CHECK
   Search for: author + [key claim term]
   Confirm the author's known position aligns with what's attributed to them.
   Look for: interviews, blog posts, reviews, other scholars citing this work, the author's own website.
   
4. CONSENSUS CHECK (only if the claim asserts or implies scholarly consensus)
   Search for dissenting scholarly voices on the specific claim.

CRITICAL RULES:
- You CANNOT verify specific page numbers. Mark all page numbers as UNVERIFIABLE unless you found the exact page in a freely available online source.
- You CANNOT verify exact wording of arguments. You can verify argument direction only.
- When you find corroborating evidence from secondary sources (a blog post, a book review, a lecture summary), report it as CORROBORATING — not as VERIFICATION of the original.
- Limit yourself to 3 web searches per citation. If unresolved after 3, mark NEEDS_HUMAN_REVIEW.
- Express uncertainty explicitly. "I found evidence consistent with this claim but cannot confirm the specific attribution" is required when applicable.

VERDICT CATEGORIES:
- VERIFIED: Bibliographic, topical, and argument direction all confirmed.
- LIKELY_ACCURATE: Bibliographic and topical confirmed. Argument direction consistent but specific attribution unconfirmed.
- LIKELY_ACCURATE_BUT_CONTESTED: Same as LIKELY_ACCURATE but the underlying scholarly claim is genuinely disputed.
- PARTIALLY_VERIFIED: Book/author confirmed but argument attribution unclear or ambiguous.
- NEEDS_HUMAN_REVIEW: Could not resolve after search attempts, or found conflicting information.
- FABRICATION_RISK: Book doesn't appear to exist, author doesn't work in this field, or attributed argument contradicts author's known position.

OUTPUT FORMAT:
For each citation, respond with a JSON object exactly matching this structure:

{
  "claim_id": "[from input]",
  "verification": {
    "bibliographic": {
      "status": "VERIFIED | UNVERIFIABLE | FAILED",
      "note": "what you found"
    },
    "topical": {
      "status": "VERIFIED | LIKELY | UNVERIFIABLE | FAILED", 
      "note": "what you found"
    },
    "argument_direction": {
      "status": "CONFIRMED | LIKELY | UNCLEAR | CONTRADICTED",
      "note": "what you found",
      "corroborating_evidence": ["URLs or descriptions of secondary sources found"]
    },
    "page_number": {
      "status": "UNVERIFIABLE | VERIFIED_ONLINE | NOT_CLAIMED",
      "note": "explanation"
    },
    "consensus_check": {
      "status": "NOT_APPLICABLE | CONSENSUS_CONFIRMED | CONTESTED | UNCLEAR",
      "note": "dissenting voices found, if any"
    }
  },
  "overall_verdict": "VERIFIED | LIKELY_ACCURATE | LIKELY_ACCURATE_BUT_CONTESTED | PARTIALLY_VERIFIED | NEEDS_HUMAN_REVIEW | FABRICATION_RISK",
  "human_review_needed": true/false,
  "human_review_priority": "HIGH | MEDIUM | LOW | null",
  "summary": "One-paragraph plain-language summary of findings"
}
"""


def build_verification_prompt(citations: list[dict], batch_size: int = 5) -> list[str]:
    """
    Build verification prompts for the verifier agent.
    
    Batches citations to keep each prompt manageable.
    Returns a list of prompt strings, each covering up to batch_size citations.
    """
    prompts = []
    
    for i in range(0, len(citations), batch_size):
        batch = citations[i:i + batch_size]
        
        citations_text = ""
        for c in batch:
            citations_text += f"""
---
CLAIM ID: {c['claim_id']}
ADVOCATE: {c['advocate']}
ROUND: {c['round']}
ADVOCATE'S CONFIDENCE: {c['advocate_confidence']}

CLAIM: {c['claim']}
SOURCE: {c['source']}
ARGUMENT: {c['argument']}

CONTEXT (surrounding text from the debate):
{c.get('context', 'N/A')}
---
"""
        
        prompt = f"""Verify the following {len(batch)} citations from a theological debate. 

For EACH citation, perform your bibliographic, topical, argument direction, and consensus checks using web search. Then produce the JSON verdict object.

Return your response as a JSON array containing one verdict object per citation, in the same order as presented.

CITATIONS TO VERIFY:
{citations_text}

Respond with ONLY the JSON array. No preamble, no markdown fencing."""

        prompts.append(prompt)
    
    return prompts


def parse_verification_response(response_text: str) -> list[dict]:
    """
    Parse the verifier's JSON response.
    Handles common issues like markdown fencing, preamble text, etc.
    """
    import json
    
    # Strip markdown fencing if present
    text = response_text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    
    # Try to find the JSON array
    start = text.find('[')
    end = text.rfind(']') + 1
    if start >= 0 and end > start:
        text = text[start:end]
    
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"WARNING: Could not parse verifier response as JSON: {e}")
        print(f"Response starts with: {text[:200]}")
        return []
