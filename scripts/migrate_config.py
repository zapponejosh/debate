#!/usr/bin/env python3
"""
Migrate legacy system_prompts.json to the new inquiry_config.json format.

Usage:
    python scripts/migrate_config.py
    python scripts/migrate_config.py --input system_prompts.json --output configs/theology_debate.json
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from inquiry_schema import (
    InquiryConfig, InquiryDefinition, Participant, ModeratorConfig,
    RoundConfig, RoundType, ModelChoice, PositionDirection,
    Pairing, RequiredText, Settings, TemperatureSettings,
    save_inquiry_config,
)


def migrate(legacy_path: str, output_path: str, anchor_text_path: str | None = None):
    with open(legacy_path) as f:
        legacy = json.load(f)

    # Load anchor text
    grounding_doc = ""
    if anchor_text_path:
        grounding_doc = Path(anchor_text_path).read_text(encoding="utf-8").strip()
    elif legacy.get("anchor_text"):
        # Check if it's a path or inline text
        at = legacy["anchor_text"]
        if isinstance(at, str) and Path(at).exists():
            grounding_doc = Path(at).read_text(encoding="utf-8").strip()
        elif isinstance(at, str):
            grounding_doc = at

    # Build participants
    advocate_order = [
        "biblical_scholar", "reception_historian", "hermeneutician",
        "systematic_theologian", "pastoral_theologian", "social_cultural_analyst",
    ]
    participants = []
    for aid in advocate_order:
        agent = legacy["agents"][aid]
        participants.append(Participant(
            id=aid,
            display_name=agent["display_name"],
            role=agent.get("disciplinary_lead", ""),
            system_prompt=agent["system_prompt"],
            position_direction=PositionDirection.NEUTRAL,
        ))

    # Moderator
    mod_agent = legacy["agents"]["moderator"]
    moderator = ModeratorConfig(
        system_prompt=mod_agent["system_prompt"],
        fact_check_prompt=legacy["round_prompts"]["moderator_fact_check_round"]["prompt"],
    )

    # Build rounds
    rp = legacy["round_prompts"]
    rounds = []

    # Predebate
    rounds.append(RoundConfig(
        key="predebate",
        title="Pre-Debate — Position Papers",
        type=RoundType.PARALLEL_STATEMENTS,
        prompt_template=rp["predeabte_position_paper"]["prompt"],
        model=ModelChoice.SONNET,
        word_limit=1500,
        verify_citations=False,
        run_moderation=False,
        generate_digest=False,
    ))

    # Round 1
    rounds.append(RoundConfig(
        key="round_1",
        title="Round 1 — Opening Statements",
        type=RoundType.PARALLEL_STATEMENTS,
        prompt_template=rp["round_1"]["prompt"],
        model=ModelChoice.SONNET,
        word_limit=800,
        verify_citations=True,
        run_moderation=True,
        generate_digest=True,
    ))

    # Round 2
    pairings = [
        Pairing(
            questioner=p["questioner"],
            target=p["target"],
            tension=p.get("tension", ""),
        )
        for p in legacy["round_2_pairings"]
    ]
    rounds.append(RoundConfig(
        key="round_2",
        title="Round 2 — Cross-Disciplinary Examination",
        type=RoundType.PAIRED_EXCHANGE,
        prompt_template=rp["round_2_question"]["prompt"],
        # Store the response template in synthesis_prompt field (repurposed for paired exchanges)
        synthesis_prompt=rp["round_2_response"]["prompt"],
        model=ModelChoice.OPUS,
        word_limit=400,
        verify_citations=True,
        run_moderation=True,
        generate_digest=True,
        generate_claim_ledger=True,
        pairings=pairings,
    ))

    # Round 3
    required_texts = [
        RequiredText(
            order=t["order"],
            text_name=t["text_name"],
            passage=t.get("passage", ""),
            core_dispute=t.get("core_dispute", ""),
        )
        for t in legacy["required_texts_round_3"]
    ]
    rounds.append(RoundConfig(
        key="round_3",
        title="Round 3 — The Seven Required Texts",
        type=RoundType.PARALLEL_STATEMENTS,
        prompt_template=rp["round_3"]["prompt"],
        model=ModelChoice.SONNET,
        word_limit=1750,
        verify_citations=True,
        run_moderation=True,
        generate_digest=True,
        generate_claim_ledger=True,
        required_texts=required_texts,
    ))

    # Synthesis
    rounds.append(RoundConfig(
        key="synthesis",
        title="Moderator Synthesis",
        type=RoundType.MODERATOR_SYNTHESIS,
        prompt_template=rp["moderator_synthesis"]["prompt"],
        synthesis_prompt=rp["moderator_synthesis"]["prompt"],
        response_prompt=rp["synthesis_response"]["prompt"],
        model=ModelChoice.OPUS,
        verify_citations=False,
        run_moderation=False,
        generate_digest=False,
    ))

    # Round 4
    rounds.append(RoundConfig(
        key="round_4",
        title="Round 4 — Closing Arguments",
        type=RoundType.PARALLEL_STATEMENTS,
        prompt_template=rp["round_4"]["prompt"],
        model=ModelChoice.OPUS,
        word_limit=750,
        verify_citations=True,
        run_moderation=True,
        generate_digest=True,
        reversed_speaking_order=True,
        use_compressed_context=True,
    ))

    # Temperature settings
    temps = legacy.get("notes", {}).get("temperature", {})
    temperature = TemperatureSettings(
        participants=temps.get("advocates", 0.75),
        moderator=temps.get("moderator", 0.25),
        verifier=temps.get("verifier", 0.25),
        language_tasks=temps.get("conductor_language_tasks", 0.3),
    )

    # Build full config
    config = InquiryConfig(
        version="2.0",
        inquiry=InquiryDefinition(
            title="Women, Authority, and the Church: A Six-Discipline Inquiry",
            question=(
                "Women should be permitted to hold all offices and exercise all forms of "
                "authority in the church, including ordination as pastors and elders, on "
                "equal terms with men."
            ),
            format="debate",
            grounding_document=grounding_doc,
            grounding_document_label="Anchor Text — Alderwood Community Church: What Alderwood Teaches about Women in Church Leadership",
            shared_context=legacy["shared_context"]["content"],
        ),
        participants=participants,
        moderator=moderator,
        rounds=rounds,
        settings=Settings(
            anti_convergence=True,
            citation_protocol=True,
            temperature=temperature,
        ),
    )

    # Validate
    config.model_validate(config.model_dump())
    print(f"Config validated: {len(config.participants)} participants, {len(config.rounds)} rounds")

    # Save
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    save_inquiry_config(config, output_path)
    print(f"Saved to {output_path}")

    # Print summary
    print(f"\nInquiry: {config.inquiry.title}")
    print(f"Participants:")
    for p in config.participants:
        print(f"  - {p.display_name} ({p.role})")
    print(f"Rounds:")
    for r in config.rounds:
        print(f"  - {r.key}: {r.title} ({r.type.value})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate legacy config to new format")
    parser.add_argument("--input", default="system_prompts.json", help="Legacy config path")
    parser.add_argument("--output", default="configs/theology_debate.json", help="Output path")
    parser.add_argument("--anchor-text", default="alderwood_text.txt", help="Anchor text file")
    args = parser.parse_args()

    migrate(args.input, args.output, args.anchor_text)
