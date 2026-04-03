"""
Document Compiler
Assembles round output files into the canonical debate record (outputs/canonical_record.md).

The canonical record grows across all rounds. Each call to compile_full_record()
rebuilds it from scratch from whatever output files exist on disk.

Now config-driven: round sections and participant order are derived from the
inquiry config rather than hardcoded.
"""

from pathlib import Path


def _read_file(path: Path) -> str | None:
    if path.exists() and path.stat().st_size > 0:
        return path.read_text(encoding="utf-8")
    return None


def _participant_label(filename: str, participant_map: dict) -> str:
    """Derive a display label from a filename using the participant map.

    participant_map: dict mapping participant_id -> display_name
    """
    stem = Path(filename).stem
    # Handle question/response variants
    base = stem.replace("_question", "").replace("_response", "")
    suffix = ""
    if "_question" in stem:
        suffix = " (Question)"
    elif "_response" in stem and base != "moderator_synthesis":
        suffix = " (Response)"

    # Look up display name
    if base in participant_map:
        return participant_map[base] + suffix

    if stem == "moderator_synthesis":
        return "Moderator Synthesis"
    if stem == "moderation_report":
        return "Moderation Report"

    return stem.replace("_", " ").title()


def build_round_sections(config) -> list[dict]:
    """Build ROUND_SECTIONS dynamically from an InquiryConfig.

    Each section dict has:
        key, title, dir, files, has_moderation
    """
    from inquiry_schema import RoundType

    sections = []
    participant_ids = config.participant_ids

    for round_cfg in config.rounds:
        section = {
            "key": round_cfg.key,
            "title": round_cfg.title,
            "dir": round_cfg.key,
            "has_moderation": round_cfg.run_moderation,
        }

        order = list(reversed(participant_ids)) if round_cfg.reversed_speaking_order else participant_ids

        if round_cfg.type == RoundType.PARALLEL_STATEMENTS:
            section["files"] = [f"{pid}.md" for pid in order]

        elif round_cfg.type == RoundType.PAIRED_EXCHANGE:
            section["files"] = (
                [f"{pid}_question.md" for pid in participant_ids]
                + [f"{pid}_response.md" for pid in participant_ids]
            )

        elif round_cfg.type == RoundType.MODERATOR_SYNTHESIS:
            section["files"] = ["moderator_synthesis.md"] + [
                f"{pid}_response.md" for pid in participant_ids
            ]
            section["has_moderation"] = False  # synthesis doesn't get a separate moderation

        elif round_cfg.type == RoundType.PANEL_QA:
            section["files"] = [f"{pid}.md" for pid in order]

        else:
            section["files"] = [f"{pid}.md" for pid in order]

        sections.append(section)

    return sections


def compile_round_section(section: dict, output_dir: Path, participant_map: dict) -> str | None:
    """
    Compile a single round into a markdown section.
    Returns None if no output files exist for this round yet.

    participant_map: dict mapping participant_id -> display_name
    """
    round_dir = output_dir / section["dir"]
    parts = []

    for filename in section["files"]:
        file_path = round_dir / filename
        content = _read_file(file_path)
        if content is None:
            continue

        label = _participant_label(filename, participant_map)
        parts.append(f"## {label}\n\n{content.strip()}")

    if section["has_moderation"]:
        mod_path = round_dir / "moderation_report.md"
        mod_content = _read_file(mod_path)
        if mod_content:
            parts.append(f"## Moderation Report — {section['title']}\n\n{mod_content.strip()}")

    if not parts:
        return None

    return f"# {section['title']}\n\n" + "\n\n---\n\n".join(parts)


def compile_full_record(output_dir: Path, config) -> str:
    """
    Rebuild the canonical record from all existing output files.
    Writes to output_dir/canonical_record.md and returns the full text.

    config: either an InquiryConfig object or a legacy dict config.
    """
    # Build participant map and round sections from config
    participant_map, round_sections = _resolve_config(config)

    sections = []
    for section in round_sections:
        compiled = compile_round_section(section, output_dir, participant_map)
        if compiled:
            sections.append(compiled)

    if not sections:
        return ""

    full_record = "\n\n---\n\n".join(sections)
    record_path = output_dir / "canonical_record.md"
    record_path.write_text(full_record, encoding="utf-8")
    return full_record


def get_section(section_key: str, output_dir: Path, config) -> str | None:
    """Return just one section of the canonical record (e.g. 'round_1')."""
    participant_map, round_sections = _resolve_config(config)

    for section in round_sections:
        if section["key"] == section_key:
            return compile_round_section(section, output_dir, participant_map)
    return None


def _resolve_config(config) -> tuple[dict[str, str], list[dict]]:
    """Handle both InquiryConfig objects and legacy dict configs.

    Returns (participant_map, round_sections).
    """
    # Check if it's a new-style InquiryConfig
    if hasattr(config, "participant_map") and hasattr(config, "rounds"):
        participant_map = {pid: p.display_name for pid, p in config.participant_map.items()}
        round_sections = build_round_sections(config)
        return participant_map, round_sections

    # Legacy dict config (system_prompts.json format)
    return _resolve_legacy_config(config)


def _resolve_legacy_config(config: dict) -> tuple[dict[str, str], list[dict]]:
    """Build participant_map and round_sections from the legacy system_prompts.json format."""
    LEGACY_ORDER = [
        "biblical_scholar",
        "reception_historian",
        "hermeneutician",
        "systematic_theologian",
        "pastoral_theologian",
        "social_cultural_analyst",
    ]

    participant_map = {}
    for aid in LEGACY_ORDER:
        if aid in config.get("agents", {}):
            participant_map[aid] = config["agents"][aid]["display_name"]

    round_sections = [
        {
            "key": "predebate",
            "title": "Pre-Debate — Position Papers",
            "dir": "predebate",
            "files": [f"{a}.md" for a in LEGACY_ORDER],
            "has_moderation": False,
        },
        {
            "key": "round_1",
            "title": "Round 1 — Opening Statements",
            "dir": "round_1",
            "files": [f"{a}.md" for a in LEGACY_ORDER],
            "has_moderation": True,
        },
        {
            "key": "round_2",
            "title": "Round 2 — Cross-Disciplinary Examination",
            "dir": "round_2",
            "files": (
                [f"{a}_question.md" for a in LEGACY_ORDER]
                + [f"{a}_response.md" for a in LEGACY_ORDER]
            ),
            "has_moderation": True,
        },
        {
            "key": "round_3",
            "title": "Round 3 — The Seven Required Texts",
            "dir": "round_3",
            "files": [f"{a}.md" for a in LEGACY_ORDER],
            "has_moderation": True,
        },
        {
            "key": "synthesis",
            "title": "Moderator Synthesis",
            "dir": "synthesis",
            "files": ["moderator_synthesis.md"] + [f"{a}_response.md" for a in LEGACY_ORDER],
            "has_moderation": False,
        },
        {
            "key": "round_4",
            "title": "Round 4 — Closing Arguments",
            "dir": "round_4",
            "files": [f"{a}.md" for a in list(reversed(LEGACY_ORDER))],
            "has_moderation": True,
        },
    ]

    return participant_map, round_sections
