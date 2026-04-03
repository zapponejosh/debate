"""
Context Packager
Builds per-participant input context for each round.

For early rounds: straightforward — shared context + canonical record.
For late rounds with use_compressed_context: compressed — own outputs in full
    + Sonnet-generated summaries of the other participants + moderator synthesis.

Now config-driven: participant order and round structure derived from InquiryConfig
or legacy dict config.
"""

from pathlib import Path

SONNET = "claude-sonnet-4-6"

SUMMARY_PROMPT = """You are preparing a context summary for a structured multi-perspective inquiry.

Below are the outputs of one participant across all prior rounds.

Produce a 200–300 word summary structured exactly as follows:

**CORE CLAIMS (2–3 max):**
List each claim with enough precision that another participant could directly affirm, dispute, or respond to it. Use the participant's own language where possible. Do not paraphrase into abstractions.

**KEY DISAGREEMENT:**
Name one specific disagreement with one named other participant. State what the disagreement is about — not "they clash on methodology" but a specific substantive point.

**UNRESOLVED TENSION:**
One tension this participant is carrying that has not been resolved. Name the specific question or claim.

**POSITION SHIFTS:**
Any concessions or genuine shifts across rounds, or "None apparent."

Do not editorialize. Report what the participant argued.
Do not include retracted claims (see exclusion list if provided).

Participant: {PARTICIPANT_DISPLAY_NAME}
Role: {PARTICIPANT_ROLE}

---

{PARTICIPANT_OUTPUTS}"""


def _read_file(path: Path) -> str | None:
    if path.exists() and path.stat().st_size > 0:
        return path.read_text(encoding="utf-8")
    return None


def _collect_own_outputs(participant_id: str, config, output_dir: Path) -> str:
    """Collect all of a participant's prior outputs across all completed rounds."""
    parts = []

    # Get round keys in order from config
    if hasattr(config, "rounds"):
        # New-style InquiryConfig
        from inquiry_schema import RoundType
        for round_cfg in config.rounds:
            if round_cfg.use_compressed_context:
                # Don't include outputs from rounds that use compression (those are the late rounds)
                break
            round_dir = output_dir / round_cfg.key

            if round_cfg.type == RoundType.PAIRED_EXCHANGE:
                # Check for both question and response files
                for suffix, label_suffix in [("_question", "Question"), ("_response", "Response")]:
                    path = round_dir / f"{participant_id}{suffix}.md"
                    content = _read_file(path)
                    if content:
                        parts.append(f"### {round_cfg.title} — {label_suffix}\n\n{content.strip()}")
            elif round_cfg.type == RoundType.MODERATOR_SYNTHESIS:
                # Participant's synthesis response
                path = round_dir / f"{participant_id}_response.md"
                content = _read_file(path)
                if content:
                    parts.append(f"### {round_cfg.title} — Response\n\n{content.strip()}")
            else:
                path = round_dir / f"{participant_id}.md"
                content = _read_file(path)
                if content:
                    parts.append(f"### {round_cfg.title}\n\n{content.strip()}")
    else:
        # Legacy config — hardcoded round structure
        checks = [
            ("Pre-Debate Position Paper", output_dir / "predebate" / f"{participant_id}.md"),
            ("Round 1 — Opening Statement", output_dir / "round_1" / f"{participant_id}.md"),
            ("Round 2 — Question", output_dir / "round_2" / f"{participant_id}_question.md"),
            ("Round 2 — Response", output_dir / "round_2" / f"{participant_id}_response.md"),
            ("Round 3 — Required Texts", output_dir / "round_3" / f"{participant_id}.md"),
        ]
        for label, path in checks:
            content = _read_file(path)
            if content:
                parts.append(f"### {label}\n\n{content.strip()}")

    return "\n\n---\n\n".join(parts)


def _get_participant_info(participant_id: str, config) -> tuple[str, str]:
    """Get display_name and role/disciplinary_lead for a participant."""
    if hasattr(config, "participant_map"):
        # New-style InquiryConfig
        p = config.participant_map.get(participant_id)
        if p:
            return p.display_name, p.role
        return participant_id, ""
    else:
        # Legacy config
        agent = config.get("agents", {}).get(participant_id, {})
        return agent.get("display_name", participant_id), agent.get("disciplinary_lead", "")


def _get_participant_ids(config) -> list[str]:
    """Get ordered list of participant IDs from config."""
    if hasattr(config, "participant_ids"):
        return config.participant_ids
    # Legacy
    return [
        "biblical_scholar", "reception_historian", "hermeneutician",
        "systematic_theologian", "pastoral_theologian", "social_cultural_analyst",
    ]


def _get_temperature(config, key: str = "conductor_language_tasks") -> float:
    """Get temperature setting from config."""
    if hasattr(config, "settings"):
        return config.settings.temperature.language_tasks
    return config.get("notes", {}).get("temperature", {}).get(key, 0.3)


def _generate_participant_summary(client, participant_id: str, output_dir: Path, config,
                                   retracted_claims: set | None = None) -> str:
    """
    Generate a 200–300 word summary of one participant's outputs via a Sonnet call.
    Used for compressed context in late rounds.
    """
    from tenacity import retry, stop_after_attempt, wait_exponential

    display_name, role = _get_participant_info(participant_id, config)
    participant_outputs = _collect_own_outputs(participant_id, config, output_dir)

    if not participant_outputs:
        return f"[No outputs found for {display_name}]"

    retraction_note = ""
    if retracted_claims:
        retraction_note = (
            "\n\nIMPORTANT: The following claims were formally retracted by this participant "
            "and must NOT appear in your summary or be treated as part of their position: "
            + ", ".join(sorted(retracted_claims))
            + "\n"
        )

    prompt = SUMMARY_PROMPT.format(
        PARTICIPANT_DISPLAY_NAME=display_name,
        PARTICIPANT_ROLE=role,
        PARTICIPANT_OUTPUTS=retraction_note + participant_outputs,
    )

    temperature = _get_temperature(config)

    @retry(stop=stop_after_attempt(20), wait=wait_exponential(min=15, max=300))
    def _call():
        response = client.messages.create(
            model=SONNET,
            max_tokens=512,
            temperature=temperature,
            system="You are a neutral summarizer for a structured multi-perspective inquiry. Summarize clearly and faithfully.",
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    return _call()


def _collect_claim_ledger(output_dir: Path) -> str:
    """Load the final claim ledger if it exists."""
    # Try the canonical location first, then the R2 version
    for filename in ["claim_ledger.md", "claim_ledger_r2.md"]:
        path = output_dir / "synthesis" / filename
        if path.exists() and path.stat().st_size > 0:
            return "# Claim Ledger — Contested Arguments\n\n" + path.read_text(encoding="utf-8").strip()
    return ""


def _collect_synthesis_section(output_dir: Path, config) -> str:
    """Build the synthesis section: moderator synthesis + all participant responses."""
    parts = []
    participant_ids = _get_participant_ids(config)

    # Find the synthesis round directory
    synthesis_dir = None
    if hasattr(config, "rounds"):
        from inquiry_schema import RoundType
        for round_cfg in config.rounds:
            if round_cfg.type == RoundType.MODERATOR_SYNTHESIS:
                synthesis_dir = output_dir / round_cfg.key
                break
    if synthesis_dir is None:
        synthesis_dir = output_dir / "synthesis"

    synthesis = _read_file(synthesis_dir / "moderator_synthesis.md")
    if synthesis:
        parts.append(f"## Moderator Synthesis\n\n{synthesis.strip()}")

    for pid in participant_ids:
        response = _read_file(synthesis_dir / f"{pid}_response.md")
        if response:
            display_name, _ = _get_participant_info(pid, config)
            parts.append(f"## {display_name} — Synthesis Response\n\n{response.strip()}")

    if not parts:
        return ""
    return "# Moderator Synthesis and Responses\n\n" + "\n\n---\n\n".join(parts)


def build_compressed_context(
    participant_id: str,
    config,
    output_dir: Path,
    client,
    retracted_claims: set | None = None,
) -> str:
    """
    Build compressed context for late rounds.

    Returns a string to be injected as context in the round prompt.

    Structure:
      1. This participant's own outputs (full text, all prior rounds)
      2. Summaries of the other participants (200-300 words each)
      3. Moderator synthesis + synthesis responses
      4. Claim ledger (if exists)
    """
    from rich.console import Console
    console = Console()

    display_name, role = _get_participant_info(participant_id, config)
    participant_ids = _get_participant_ids(config)
    sections = []

    # 1. Own outputs
    own_outputs = _collect_own_outputs(participant_id, config, output_dir)
    if own_outputs:
        sections.append(
            f"# Your Prior Outputs — {display_name}\n\n{own_outputs}"
        )

    # 2. Summaries of other participants
    other_summaries = []
    for other_id in participant_ids:
        if other_id == participant_id:
            continue
        other_display, other_role = _get_participant_info(other_id, config)
        console.print(f"  [dim]Summarizing {other_display}...[/dim]")
        # Only pass retracted claims that belong to this participant
        if retracted_claims:
            from citation_extractor import _advocate_abbrev
            abbrev = _advocate_abbrev(other_id).upper()
            participant_retracted = {cid for cid in retracted_claims if f"_{abbrev}_" in cid}
        else:
            participant_retracted = None
        summary = _generate_participant_summary(
            client, other_id, output_dir, config,
            retracted_claims=participant_retracted or None,
        )
        other_summaries.append(
            f"### {other_display} ({other_role})\n\n{summary}"
        )

    if other_summaries:
        sections.append(
            "# Other Participants — Position Summaries\n\n"
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


# Backward-compatible alias
build_r4_context = build_compressed_context
