"""
Document Compiler
Assembles round output files into the canonical debate record (outputs/canonical_record.md).

The canonical record grows across all rounds. Each call to compile_full_record()
rebuilds it from scratch from whatever output files exist on disk.
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

ROUND_SECTIONS = [
    {
        "key": "predebate",
        "title": "Pre-Debate — Position Papers",
        "dir": "predebate",
        "files": [f"{a}.md" for a in ADVOCATE_ORDER],
        "advocate_labels": True,
        "has_moderation": False,
    },
    {
        "key": "round_1",
        "title": "Round 1 — Opening Statements",
        "dir": "round_1",
        "files": [f"{a}.md" for a in ADVOCATE_ORDER],
        "advocate_labels": True,
        "has_moderation": True,
    },
    {
        "key": "round_2",
        "title": "Round 2 — Cross-Disciplinary Examination",
        "dir": "round_2",
        "files": (
            [f"{a}_question.md" for a in ADVOCATE_ORDER] +
            [f"{a}_response.md" for a in ADVOCATE_ORDER]
        ),
        "advocate_labels": True,
        "has_moderation": True,
    },
    {
        "key": "round_3",
        "title": "Round 3 — The Seven Required Texts",
        "dir": "round_3",
        "files": [f"{a}.md" for a in ADVOCATE_ORDER],
        "advocate_labels": True,
        "has_moderation": True,
    },
    {
        "key": "synthesis",
        "title": "Moderator Synthesis",
        "dir": "synthesis",
        "files": ["moderator_synthesis.md"] + [f"{a}_response.md" for a in ADVOCATE_ORDER],
        "advocate_labels": True,
        "has_moderation": False,
    },
    {
        "key": "round_4",
        "title": "Round 4 — Closing Arguments",
        "dir": "round_4",
        "files": [f"{a}.md" for a in list(reversed(ADVOCATE_ORDER))],
        "advocate_labels": True,
        "has_moderation": True,
    },
]


def _advocate_label(filename: str, config: dict) -> str:
    """Derive a display label from a filename."""
    stem = Path(filename).stem
    # Handle question/response variants
    base = stem.replace("_question", " (Question)").replace("_response", " (Response)")

    # Look up display name for advocate IDs
    for advocate_id in ADVOCATE_ORDER:
        if base.startswith(advocate_id):
            display = config["agents"][advocate_id]["display_name"]
            suffix = base[len(advocate_id):]  # e.g. " (Question)"
            return display + suffix

    if stem == "moderator_synthesis":
        return "Moderator Synthesis"
    if stem == "moderation_report":
        return "Moderation Report"

    return stem.replace("_", " ").title()


def _read_file(path: Path) -> str | None:
    if path.exists() and path.stat().st_size > 0:
        return path.read_text(encoding="utf-8")
    return None


def compile_round_section(section: dict, output_dir: Path, config: dict) -> str | None:
    """
    Compile a single round into a markdown section.
    Returns None if no output files exist for this round yet.
    """
    round_dir = output_dir / section["dir"]
    parts = []

    for filename in section["files"]:
        file_path = round_dir / filename
        content = _read_file(file_path)
        if content is None:
            continue

        label = _advocate_label(filename, config)
        parts.append(f"## {label}\n\n{content.strip()}")

    if section["has_moderation"]:
        mod_path = round_dir / "moderation_report.md"
        mod_content = _read_file(mod_path)
        if mod_content:
            parts.append(f"## Moderation Report — {section['title']}\n\n{mod_content.strip()}")

    if not parts:
        return None

    return f"# {section['title']}\n\n" + "\n\n---\n\n".join(parts)


def compile_full_record(output_dir: Path, config: dict) -> str:
    """
    Rebuild the canonical record from all existing output files.
    Writes to output_dir/canonical_record.md and returns the full text.
    """
    sections = []

    for section in ROUND_SECTIONS:
        compiled = compile_round_section(section, output_dir, config)
        if compiled:
            sections.append(compiled)

    if not sections:
        return ""

    full_record = "\n\n---\n\n".join(sections)
    record_path = output_dir / "canonical_record.md"
    record_path.write_text(full_record, encoding="utf-8")
    return full_record


def get_section(section_key: str, output_dir: Path, config: dict) -> str | None:
    """Return just one section of the canonical record (e.g. 'round_1')."""
    for section in ROUND_SECTIONS:
        if section["key"] == section_key:
            return compile_round_section(section, output_dir, config)
    return None
