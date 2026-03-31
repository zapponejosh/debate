"""
Context Packager
Builds per-advocate input context for each round.

For Rounds 1–3: straightforward — shared context + canonical record.
For Round 4:    compressed — own outputs in full + Sonnet-generated summaries
                of the other 5 advocates + moderator synthesis.
"""

from pathlib import Path

ADVOCATE_ORDER = [
    "biblical_scholar",
    "reception_historian",
    "hermeneutician",
    "systematic_theologian",
    "pastoral_theologian",
    "social_cultural_analyst",
]

SONNET = "claude-sonnet-4-6"

SUMMARY_PROMPT = """You are preparing a context summary for a structured theological debate.

Below are the outputs of one advocate across all debate rounds.

Produce a 200–300 word summary structured exactly as follows:

**CORE CLAIMS (2–3 max):**
List each claim with enough precision that another advocate could directly affirm, dispute, or respond to it. Use the advocate's own language where possible. Do not paraphrase into abstractions.

**KEY DISAGREEMENT:**
Name one specific disagreement with one named other advocate. State what the disagreement is about — not "they clash on hermeneutics" but "The Hermeneutician argues that the creation-order principle in 1 Tim 2:13 is applied inconsistently elsewhere; this advocate disputes that consistency is the relevant criterion."

**UNRESOLVED TENSION ENTERING ROUND 4:**
One tension this advocate is carrying into Round 4 that has not been resolved. Name the specific question or claim.

**POSITION SHIFTS:**
Any concessions or genuine shifts across rounds, or "None apparent."

Do not editorialize. Report what the advocate argued.
Do not include retracted claims (see exclusion list if provided).

Advocate: {ADVOCATE_DISPLAY_NAME}
Disciplinary Lead: {DISCIPLINARY_LEAD}

---

{ADVOCATE_OUTPUTS}"""


def _read_file(path: Path) -> str | None:
    if path.exists() and path.stat().st_size > 0:
        return path.read_text(encoding="utf-8")
    return None


def _collect_own_outputs(advocate_id: str, output_dir: Path) -> str:
    """Collect all of an advocate's prior outputs across all rounds."""
    parts = []
    checks = [
        ("Pre-Debate Position Paper", output_dir / "predebate" / f"{advocate_id}.md"),
        ("Round 1 — Opening Statement", output_dir / "round_1" / f"{advocate_id}.md"),
        ("Round 2 — Question", output_dir / "round_2" / f"{advocate_id}_question.md"),
        ("Round 2 — Response", output_dir / "round_2" / f"{advocate_id}_response.md"),
        ("Round 3 — Required Texts", output_dir / "round_3" / f"{advocate_id}.md"),
    ]
    for label, path in checks:
        content = _read_file(path)
        if content:
            parts.append(f"### {label}\n\n{content.strip()}")

    return "\n\n---\n\n".join(parts)


def _generate_advocate_summary(client, advocate_id: str, output_dir: Path, config: dict,
                                retracted_claims: set | None = None) -> str:
    """
    Generate a 200–300 word summary of one advocate's outputs via a Sonnet call.
    Used for Round 4 context compression.
    """
    from tenacity import retry, stop_after_attempt, wait_exponential

    agent = config["agents"][advocate_id]
    advocate_outputs = _collect_own_outputs(advocate_id, output_dir)

    if not advocate_outputs:
        return f"[No outputs found for {agent['display_name']}]"

    retraction_note = ""
    if retracted_claims:
        retraction_note = (
            "\n\nIMPORTANT: The following claims were formally retracted by this advocate "
            "and must NOT appear in your summary or be treated as part of their position: "
            + ", ".join(sorted(retracted_claims))
            + "\n"
        )

    prompt = SUMMARY_PROMPT.format(
        ADVOCATE_DISPLAY_NAME=agent["display_name"],
        DISCIPLINARY_LEAD=agent["disciplinary_lead"],
        ADVOCATE_OUTPUTS=retraction_note + advocate_outputs,
    )

    @retry(stop=stop_after_attempt(20), wait=wait_exponential(min=15, max=300))
    def _call():
        response = client.messages.create(
            model=SONNET,
            max_tokens=512,
            temperature=config["notes"]["temperature"]["conductor_language_tasks"],
            system="You are a neutral summarizer for a structured academic debate. Summarize clearly and faithfully.",
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    return _call()


def _collect_claim_ledger(output_dir: Path) -> str:
    """Load the final claim ledger (after Round 3) if it exists."""
    path = output_dir / "synthesis" / "claim_ledger.md"
    if path.exists() and path.stat().st_size > 0:
        return "# Claim Ledger — Contested Arguments Across Rounds 1–3\n\n" + path.read_text(encoding="utf-8").strip()
    return ""


def _collect_synthesis_section(output_dir: Path, config: dict) -> str:
    """Build the synthesis section: moderator synthesis + all advocate responses."""
    parts = []

    synthesis = _read_file(output_dir / "synthesis" / "moderator_synthesis.md")
    if synthesis:
        parts.append(f"## Moderator Synthesis\n\n{synthesis.strip()}")

    for advocate_id in ADVOCATE_ORDER:
        response = _read_file(output_dir / "synthesis" / f"{advocate_id}_response.md")
        if response:
            display = config["agents"][advocate_id]["display_name"]
            parts.append(f"## {display} — Synthesis Response\n\n{response.strip()}")

    if not parts:
        return ""
    return "# Moderator Synthesis and Responses\n\n" + "\n\n---\n\n".join(parts)


def build_r4_context(
    advocate_id: str,
    config: dict,
    output_dir: Path,
    client,
    retracted_claims: set | None = None,
) -> str:
    """
    Build compressed context for Round 4.

    Returns a string to be injected as [COMPRESSED_CANONICAL_RECORD] in the Round 4 prompt.

    Structure:
      1. This advocate's own outputs (full text, all rounds)
      2. Summaries of the other 5 advocates (200-300 words each)
      3. Moderator synthesis + synthesis responses
    """
    from rich.console import Console
    console = Console()

    agent = config["agents"][advocate_id]
    sections = []

    # 1. Own outputs
    own_outputs = _collect_own_outputs(advocate_id, output_dir)
    if own_outputs:
        sections.append(
            f"# Your Prior Outputs — {agent['display_name']}\n\n{own_outputs}"
        )

    # 2. Summaries of other advocates
    other_summaries = []
    for other_id in ADVOCATE_ORDER:
        if other_id == advocate_id:
            continue
        other_agent = config["agents"][other_id]
        console.print(f"  [dim]Summarizing {other_agent['display_name']}...[/dim]")
        # Only pass retracted claims that belong to this advocate
        if retracted_claims:
            from citation_extractor import _advocate_abbrev
            abbrev = _advocate_abbrev(other_id).upper()
            advocate_retracted = {cid for cid in retracted_claims if f"_{abbrev}_" in cid}
        else:
            advocate_retracted = None
        summary = _generate_advocate_summary(client, other_id, output_dir, config,
                                              retracted_claims=advocate_retracted or None)
        other_summaries.append(
            f"### {other_agent['display_name']} ({other_agent['disciplinary_lead']})\n\n{summary}"
        )

    if other_summaries:
        sections.append(
            "# Other Advocates — Position Summaries\n\n"
            + "\n\n---\n\n".join(other_summaries)
        )

    # 3. Synthesis
    synthesis_section = _collect_synthesis_section(output_dir, config)
    if synthesis_section:
        sections.append(synthesis_section)

    # 4. Claim ledger
    ledger = _collect_claim_ledger(output_dir)
    if ledger:
        sections.append(ledger)

    return "\n\n===\n\n".join(sections)
