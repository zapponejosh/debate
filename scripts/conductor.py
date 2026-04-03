#!/usr/bin/env python3
"""
Debate Conductor
Orchestrates sequential API calls across all debate rounds.

Usage:
    python scripts/conductor.py --round 1 --advocate biblical_scholar --test
    python scripts/conductor.py --round 1 --test
    python scripts/conductor.py --round 1 --dry-run
    python scripts/conductor.py --all
"""

import argparse
import datetime
import json
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

load_dotenv()

ROOT = Path(__file__).parent.parent
CONFIG_PATH = ROOT / "system_prompts.json"
OUTPUT_DIR = ROOT / "outputs"
VERIFICATION_DIR = ROOT / "verification"

SONNET = "claude-sonnet-4-6"
OPUS = "claude-opus-4-6"

# Set to True by --fast flag. Caps output tokens and injects a brevity note so
# test runs consume ~25% of normal tokens without changing any other logic.
FAST_MODE = False
FAST_MAX_TOKENS = 600
FAST_NOTE = "\n\n[FAST/TEST MODE: Respond in 250 words or fewer. Truncate freely. Structure matters more than completeness.]"

# Set to True by --skip-human-review. Automated verifier always runs; only the
# "pause and wait for worksheet completion" step is skipped.
SKIP_HUMAN_REVIEW = False

ADVOCATE_ORDER = [
    "biblical_scholar",
    "reception_historian",
    "hermeneutician",
    "systematic_theologian",
    "pastoral_theologian",
    "social_cultural_analyst",
]
ADVOCATE_ORDER_R4 = list(reversed(ADVOCATE_ORDER))

ROUND_TITLES = {
    "predebate": "Pre-Debate Position Papers",
    "round_1": "Opening Statements",
    "round_2": "Cross-Disciplinary Examination",
    "round_3": "The Seven Required Texts",
    "synthesis": "Moderator Synthesis",
    "round_4": "Closing Arguments",
}

console = Console()


# ---------------------------------------------------------------------------
# Audit logger — records every API call to {output_dir}/audit_log.jsonl
# ---------------------------------------------------------------------------

_audit_log_path: Path | None = None


def init_audit_log(output_dir: Path):
    """Call once at startup with the resolved output_dir."""
    global _audit_log_path
    _audit_log_path = output_dir / "audit_log.jsonl"
    _audit_log_path.parent.mkdir(parents=True, exist_ok=True)


def _audit(entry: dict):
    """Append one JSON line to the audit log. No-ops if log is not initialised."""
    if _audit_log_path is None:
        return
    with open(_audit_log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Template filling
# ---------------------------------------------------------------------------

def fill_curly(template: str, variables: dict) -> str:
    """
    Replace {ALL_CAPS_VARS} placeholders using the provided dict.
    Uses regex so literal { } in JSON examples are left untouched.
    """
    def replacer(m):
        key = m.group(1)
        if key in variables:
            return str(variables[key])
        return m.group(0)  # leave unmatched placeholders as-is
    return re.sub(r'\{([A-Z_][A-Z0-9_]*)\}', replacer, template)


def fill_bracket(template: str, variables: dict) -> str:
    """
    Replace [ALL_CAPS_PLACEHOLDERS] with provided values.
    Only replaces keys present in the dict.
    """
    for key, value in variables.items():
        template = template.replace(f"[{key}]", value)
    return template


def fill_template(template: str, curly_vars: dict = None, bracket_vars: dict = None) -> str:
    """Fill both {CURLY} and [BRACKET] placeholders."""
    result = template
    if curly_vars:
        result = fill_curly(result, curly_vars)
    if bracket_vars:
        result = fill_bracket(result, bracket_vars)
    return result


# ---------------------------------------------------------------------------
# Output directory
# ---------------------------------------------------------------------------

def resolve_output_dir(test_mode: bool) -> Path:
    if test_mode:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        test_dir = OUTPUT_DIR / "tests" / timestamp
        test_dir.mkdir(parents=True, exist_ok=True)
        for sub in ["predebate", "round_1", "round_2", "round_3", "round_4", "synthesis"]:
            (test_dir / sub).mkdir(exist_ok=True)
        console.print(Panel(f"[yellow]TEST MODE[/yellow]\nOutput: {test_dir}", expand=False))
        return test_dir
    return OUTPUT_DIR


def write_output(text: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    console.print(f"  [green]✓[/green] wrote {path.relative_to(ROOT)}")


def read_output(path: Path) -> str | None:
    if path.exists() and path.stat().st_size > 0:
        return path.read_text(encoding="utf-8")
    return None


def should_skip(path: Path, force: bool) -> bool:
    """Return True if the file already exists and we should skip regenerating it."""
    if force:
        return False
    return path.exists() and path.stat().st_size > 0


# ---------------------------------------------------------------------------
# API call
# ---------------------------------------------------------------------------

def make_api_client():
    import anthropic
    return anthropic.Anthropic()


def _is_retryable(exc: BaseException) -> bool:
    """Only retry on rate limits and server errors, not billing/bad-request errors."""
    import anthropic
    if isinstance(exc, anthropic.RateLimitError):
        return True
    if isinstance(exc, anthropic.APIStatusError) and exc.status_code >= 500:
        return True
    if isinstance(exc, (anthropic.APIConnectionError, anthropic.APITimeoutError)):
        return True
    return False


@retry(retry=retry_if_exception(_is_retryable), stop=stop_after_attempt(6), wait=wait_exponential(min=30, max=120))
def call_api(
    client,
    model: str,
    system_prompt: str,
    human_message: str,
    temperature: float,
    max_tokens: int = 4096,
    label: str = "",
    bypass_fast: bool = False,
) -> str:
    if FAST_MODE and not bypass_fast:
        max_tokens = FAST_MAX_TOKENS
        human_message = human_message + FAST_NOTE
    console.print(f"  [dim]→ {model} | temp={temperature}{' | FAST' if (FAST_MODE and not bypass_fast) else ''} | {label}[/dim]")
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_prompt,
        messages=[{"role": "user", "content": human_message}],
    )
    tokens_used = response.usage.input_tokens + response.usage.output_tokens
    response_text = response.content[0].text
    console.print(f"  [dim]← {tokens_used:,} tokens total[/dim]")
    _audit({
        "timestamp": datetime.datetime.now().isoformat(),
        "label": label,
        "model": model,
        "temperature": temperature,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "system_prompt": system_prompt,
        "human_message": human_message,
        "response": response_text,
    })
    return response_text


def call_api_with_web_search(
    client,
    model: str,
    system_prompt: str,
    human_message: str,
    temperature: float,
    max_tokens: int = 4096,
    label: str = "",
    max_turns: int = 8,
) -> str:
    """
    API call with Anthropic's built-in web search tool enabled.
    Handles the multi-turn tool_use loop until end_turn.

    For web_search_20250305 (Anthropic's native server-side tool), no client-side
    tool results are needed — Anthropic executes the search and appends results to
    the context automatically. We just resend the conversation on each tool_use turn.
    """
    console.print(f"  [dim]→ {model} | temp={temperature} | web_search | {label}[/dim]")

    messages = [{"role": "user", "content": human_message}]
    tools = [{"type": "web_search_20250305", "name": "web_search"}]
    total_input = 0
    total_output = 0
    result_text = ""

    for turn in range(max_turns):
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            tools=tools,
            messages=messages,
        )
        total_input += response.usage.input_tokens
        total_output += response.usage.output_tokens

        if response.stop_reason == "end_turn":
            console.print(f"  [dim]← {total_input + total_output:,} tokens total ({turn + 1} turn(s))[/dim]")
            for block in response.content:
                if hasattr(block, "text"):
                    result_text = block.text
            _audit({
                "timestamp": datetime.datetime.now().isoformat(),
                "label": label,
                "model": model,
                "temperature": temperature,
                "turns": turn + 1,
                "input_tokens": total_input,
                "output_tokens": total_output,
                "system_prompt": system_prompt,
                "conversation": [
                    {"role": m["role"], "content": str(m["content"])[:2000]}
                    for m in messages
                ],
                "response": result_text,
            })
            return result_text

        if response.stop_reason == "tool_use":
            # For Anthropic's native web_search tool, the API executes the search
            # server-side. Simply append the assistant turn and call again — no
            # client-side tool_result injection needed (and providing empty results
            # would cause the model to believe its searches returned nothing).
            messages.append({"role": "assistant", "content": response.content})
            continue

        # Unexpected stop reason — return whatever text exists
        break

    # Exhausted turns without end_turn — nudge model to emit JSON now
    console.print(f"  [dim]← {total_input + total_output:,} tokens total (turn limit reached, forcing JSON)[/dim]")
    messages.append({"role": "assistant", "content": response.content})
    messages.append({"role": "user", "content": "You have reached the search limit. Now produce ONLY the JSON array with your findings so far. No preamble."})
    final = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=0.0,
        system=system_prompt,
        tools=tools,
        messages=messages,
    )
    total_input += final.usage.input_tokens
    total_output += final.usage.output_tokens
    console.print(f"  [dim]← {total_input + total_output:,} tokens total[/dim]")
    for block in final.content:
        if hasattr(block, "text"):
            result_text = block.text
    _audit({
        "timestamp": datetime.datetime.now().isoformat(),
        "label": label,
        "model": model,
        "temperature": temperature,
        "turns": max_turns + 1,
        "input_tokens": total_input,
        "output_tokens": total_output,
        "system_prompt": system_prompt,
        "conversation": [
            {"role": m["role"], "content": str(m["content"])[:2000]}
            for m in messages
        ],
        "response": result_text,
        "note": "turn_limit_reached_forced_json",
    })
    return result_text


# ---------------------------------------------------------------------------
# Context assembly helpers
# ---------------------------------------------------------------------------

def build_shared_context(config: dict) -> str:
    base = config["shared_context"]["content"]
    alderwood_path = ROOT / "alderwood_text.txt"
    if alderwood_path.exists():
        alderwood = alderwood_path.read_text(encoding="utf-8").strip()
        return (
            base
            + "\n\n---\n\n"
            + "## ANCHOR TEXT — Alderwood Community Church\n"
            + "*What Alderwood Teaches about Women in Church Leadership*\n\n"
            + alderwood
        )
    console.print("  [yellow]Warning: alderwood_text.txt not found — anchor text not injected[/yellow]")
    return base


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

# Which advocate files must exist for each round to be considered complete
_ROUND_REQUIRED_FILES: dict[str, list[str]] = {
    "predebate": [f"predebate/{a}.md" for a in ADVOCATE_ORDER],
    "round_1":   [f"round_1/{a}.md" for a in ADVOCATE_ORDER],
    "round_2":   [f"round_2/{a}_question.md" for a in ADVOCATE_ORDER] +
                 [f"round_2/{a}_response.md" for a in ADVOCATE_ORDER],
    "round_3":   [f"round_3/{a}.md" for a in ADVOCATE_ORDER],
    "synthesis": ["synthesis/moderator_synthesis.md"],
    "round_4":   [f"round_4/{a}.md" for a in ADVOCATE_ORDER],
}

# What each round requires to be complete beforehand
_ROUND_PREREQUISITES: dict[str, list[str]] = {
    "predebate": [],
    "round_1":   [],          # pre-debate is optional
    "round_2":   ["round_1"],
    "round_3":   ["round_2"],
    "synthesis": ["round_3"],
    "round_4":   ["round_3", "synthesis"],
}


def check_round_complete(round_key: str, output_dir: Path) -> list[str]:
    """Return a list of missing file paths for a given round. Empty = complete."""
    missing = []
    for rel_path in _ROUND_REQUIRED_FILES.get(round_key, []):
        if not (output_dir / rel_path).exists():
            missing.append(rel_path)
    return missing


def validate_prerequisites(round_key: str, output_dir: Path, force: bool = False) -> bool:
    """
    Check that all prerequisite rounds are complete before running round_key.
    Prints warnings for missing files.
    Returns True if safe to proceed, False if prerequisites are missing.
    Force overrides the check (with a warning).
    """
    prereqs = _ROUND_PREREQUISITES.get(round_key, [])
    all_ok = True

    for prereq in prereqs:
        missing = check_round_complete(prereq, output_dir)
        if missing:
            all_ok = False
            console.print(f"\n[bold red]Prerequisite incomplete: {prereq}[/bold red]")
            console.print(f"  Missing {len(missing)} file(s):")
            for f in missing[:6]:
                console.print(f"  [red]✗[/red] {f}")
            if len(missing) > 6:
                console.print(f"  ... and {len(missing) - 6} more")

    if not all_ok:
        if force:
            console.print("\n[yellow]--force set: proceeding despite missing prerequisites. Output may be degraded.[/yellow]")
            return True
        console.print("\n[red]Aborting. Run prerequisite rounds first, or use --force to proceed anyway.[/red]")
        return False

    return True


def warn_incomplete_round(round_key: str, output_dir: Path):
    """Warn if a round is missing any advocate outputs before running moderation/digest."""
    missing = check_round_complete(round_key, output_dir)
    if missing:
        console.print(f"\n[yellow]Warning: {round_key} is incomplete — {len(missing)} file(s) missing:[/yellow]")
        for f in missing:
            console.print(f"  [yellow]![/yellow] {f}")
        console.print(f"  [yellow]Moderation and digest will run on partial data.[/yellow]")


def read_canonical_record(output_dir: Path) -> str:
    record_path = output_dir / "canonical_record.md"
    if record_path.exists() and record_path.stat().st_size > 0:
        return record_path.read_text(encoding="utf-8")
    return ""


def build_round_3_texts_block(config: dict) -> str:
    """Build the full 7-texts block for Round 3."""
    parts = []
    for t in config["required_texts_round_3"]:
        parts.append(
            f"TEXT {t['order']}: {t['text_name']}\n"
            f"PASSAGE: {t['passage']}\n"
            f"CORE DISPUTE: {t['core_dispute']}"
        )
    return "\n\n---\n\n".join(parts)


def build_advocate_outputs_block(round_outputs: dict[str, str], config: dict) -> str:
    """Format all advocate outputs as a labeled block (for moderator input)."""
    parts = []
    for advocate_id in ADVOCATE_ORDER:
        if advocate_id not in round_outputs:
            continue
        display = config["agents"][advocate_id]["display_name"]
        parts.append(f"## {display}\n\n{round_outputs[advocate_id]}")
    return "\n\n---\n\n".join(parts)


def read_round_outputs(round_dir: Path, suffix: str = "") -> dict[str, str]:
    """Read all advocate output files from a round directory."""
    outputs = {}
    for advocate_id in ADVOCATE_ORDER:
        filename = f"{advocate_id}{suffix}.md"
        path = round_dir / filename
        text = read_output(path)
        if text:
            outputs[advocate_id] = text
    return outputs


# ---------------------------------------------------------------------------
# Citation extraction
# ---------------------------------------------------------------------------

def _verification_dirs(output_dir: Path) -> dict[str, Path]:
    """Return the three verification subdirectories, routing by test vs. real run."""
    if "tests" in str(output_dir):
        base = output_dir
    else:
        base = VERIFICATION_DIR
    dirs = {
        "citations":       base / "citations",
        "verifications":   base / "verifications",
        "audit":           base / "audit",
        "moderator_input": base / "moderator_input",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


def extract_and_save_citations(
    round_outputs: dict[str, str], round_number: int, output_dir: Path
) -> Path | None:
    """Extract citations from round outputs and save to citations dir. Returns the saved path."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from citation_extractor import extract_all_round_citations, save_citations

    citations = extract_all_round_citations(round_outputs, round_number)
    if not citations:
        console.print("  [dim]No citations found in round outputs.[/dim]")
        return None

    dirs = _verification_dirs(output_dir)
    out_path = dirs["citations"] / f"round_{round_number}_citations.json"
    save_citations(citations, str(out_path))
    console.print(f"  [green]✓[/green] {len(citations)} citations → {out_path.relative_to(ROOT)}")
    return out_path


RETRACTED_CLAIMS_FILE = "retracted_claims.json"


def load_retracted_claims(output_dir: Path) -> set[str]:
    """Load the set of retracted claim_ids for this run."""
    path = output_dir / RETRACTED_CLAIMS_FILE
    if not path.exists():
        return set()
    import json as _json
    return set(_json.loads(path.read_text(encoding="utf-8")))


def update_retracted_claims(output_dir: Path, new_ids: list[str]) -> None:
    """Add new claim_ids to the retracted claims registry."""
    if not new_ids:
        return
    import json as _json
    existing = load_retracted_claims(output_dir)
    merged = sorted(existing | set(new_ids))
    (output_dir / RETRACTED_CLAIMS_FILE).write_text(
        _json.dumps(merged, indent=2), encoding="utf-8"
    )
    console.print(f"  [dim]retracted_claims.json updated: {len(merged)} total[/dim]")


def load_all_verifications(output_dir: Path, through_round: int) -> list[dict]:
    """Load and merge verifications from rounds 1 through through_round."""
    import json as _json
    dirs = _verification_dirs(output_dir)
    all_vers = []
    for n in range(1, through_round + 1):
        path = dirs["verifications"] / f"round_{n}_verifications.json"
        if path.exists():
            data = _json.loads(path.read_text(encoding="utf-8"))
            # Tag each with round number for traceability
            for v in data:
                v.setdefault("_round", n)
            all_vers.extend(data)
    return all_vers


def _advocate_id_from_claim_id(claim_id: str) -> str | None:
    """
    Reverse-map a claim_id abbreviation back to an advocate_id.
    claim_id format: R{round}_{ABBREV}_{seq}
    """
    abbrev_map = {
        "BS": "biblical_scholar",
        "RH": "reception_historian",
        "HM": "hermeneutician",
        "ST": "systematic_theologian",
        "PT": "pastoral_theologian",
        "SA": "social_cultural_analyst",
    }
    parts = claim_id.split("_")
    if len(parts) >= 2:
        return abbrev_map.get(parts[1].upper())
    return None


def build_corrections_block(
    advocate_id: str,
    verifications: list[dict],
) -> str:
    """
    Build the CITATION CORRECTIONS injection block for an advocate's round prompt.

    Includes only:
    - FABRICATION_RISK claims (always)
    - NEEDS_HUMAN_REVIEW claims (always — impact filtering happens at worksheet level)

    Returns empty string if no corrections apply to this advocate.
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from citation_extractor import _advocate_abbrev

    abbrev = _advocate_abbrev(advocate_id)
    flagged = []

    for v in verifications:
        cid = v.get("claim_id", "")
        verdict = v.get("overall_verdict", "")
        # Match this advocate by abbrev in claim_id
        parts = cid.split("_")
        if len(parts) < 2 or parts[1].upper() != abbrev.upper():
            continue
        if verdict in ("FABRICATION_RISK", "NEEDS_HUMAN_REVIEW"):
            flagged.append(v)

    if not flagged:
        return ""

    lines = [
        "CITATION CORRECTIONS — REQUIRED RESPONSE:",
        "The following citation(s) from your prior outputs have been flagged and require a formal response.",
        "Respond to each using the [CITATION_RESPONSE] format BEFORE your substantive content.",
        "",
    ]
    for v in flagged:
        cid = v.get("claim_id", "?")
        summary = v.get("summary", "")
        # Try to get original claim text from verification details
        claim_text = ""
        source_text = ""
        for key in ("claim", "claim_text"):
            if v.get(key):
                claim_text = v[key]
                break
        for key in ("source", "source_cited"):
            if v.get(key):
                source_text = v[key]
                break
        verdict = v.get("overall_verdict", "?")
        lines.append(f"Claim ID: {cid}")
        if claim_text:
            lines.append(f"Your claim: {claim_text}")
        if source_text:
            lines.append(f"Source cited: {source_text}")
        lines.append(f"Correction type: {verdict}")
        if summary:
            lines.append(f"Details: {summary}")
        lines.append("")

    return "\n".join(lines)


def parse_and_process_responses(
    round_outputs: dict[str, str],
    round_number: int,
    output_dir: Path,
    client,
    config: dict,
    force: bool = False,
) -> list:
    """
    Extract [CITATION_RESPONSE] blocks from round outputs, update the retracted_claims
    registry, and re-verify any DEFEND responses that introduce a new source.

    Returns a flat list of CitationResponse objects.
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from citation_extractor import extract_all_round_responses, save_citation_responses, Citation

    if not round_outputs:
        return []

    all_responses = extract_all_round_responses(round_outputs, round_number)
    if not all_responses:
        return []

    # Save response records
    dirs = _verification_dirs(output_dir)
    resp_path = dirs["citations"] / f"round_{round_number}_responses.json"
    save_citation_responses(all_responses, str(resp_path))
    console.print(f"  [green]✓[/green] {len(all_responses)} citation responses → {resp_path.relative_to(ROOT)}")

    # Update retracted_claims registry
    retracted_ids = [r.original_claim_id for r in all_responses if r.downstream_status == "RETRACTED"]
    if retracted_ids:
        update_retracted_claims(output_dir, retracted_ids)
        console.print(f"  [yellow]Retracted {len(retracted_ids)} claim(s): {retracted_ids}[/yellow]")

    # Re-verify DEFEND responses that introduce a new source
    defend_with_new_source = [
        r for r in all_responses
        if r.advocate_position == "DEFEND" and r.revised_source.strip()
    ]
    if defend_with_new_source:
        console.print(f"  [dim]Re-verifying {len(defend_with_new_source)} DEFEND+new_source response(s)...[/dim]")
        # Build synthetic Citation dicts for re-verification
        import json as _json
        from citation_extractor import _advocate_abbrev

        synthetic_citations = []
        for i, resp in enumerate(defend_with_new_source):
            abbrev = _advocate_abbrev(resp.advocate)
            synthetic_citations.append({
                "claim_id": f"R{round_number}_{abbrev}_RECHECK_{i + 1:03d}",
                "round": round_number,
                "advocate": resp.advocate,
                "claim": resp.revised_claim or resp.response_note,
                "source": resp.revised_source,
                "argument": resp.revised_claim,
                "advocate_confidence": resp.revised_confidence or "LOW",
                "raw_text": resp.raw_text,
                "context": "",
                "_original_response_id": resp.response_id,
            })

        # Save synthetic citations and run through verifier
        recheck_path = dirs["citations"] / f"round_{round_number}_recheck_citations.json"
        recheck_path.write_text(_json.dumps(synthetic_citations, indent=2), encoding="utf-8")

        recheck_ver_input = run_verification_pipeline(
            client, recheck_path, round_number,
            output_dir=output_dir, force=force, skip_pause=True,
            _recheck_suffix="_recheck",
        )

        # Escalate any that came back FABRICATION_RISK
        recheck_ver_path = dirs["verifications"] / f"round_{round_number}_recheck_verifications.json"
        if recheck_ver_path.exists():
            recheck_vers = _json.loads(recheck_ver_path.read_text(encoding="utf-8"))
            escalated = []
            resp_by_recheck_id = {
                f"R{round_number}_{_advocate_abbrev(r.advocate)}_RECHECK_{i + 1:03d}": r
                for i, r in enumerate(defend_with_new_source)
            }
            for rv in recheck_vers:
                if rv.get("overall_verdict") == "FABRICATION_RISK":
                    orig_resp = resp_by_recheck_id.get(rv["claim_id"])
                    if orig_resp:
                        orig_resp.downstream_status = "RETRACTED"
                        escalated.append(orig_resp.original_claim_id)
                        console.print(f"  [red]DEFEND re-verification failed → escalating {orig_resp.original_claim_id} to RETRACTED[/red]")
            if escalated:
                update_retracted_claims(output_dir, escalated)
                # Re-save responses with updated statuses
                save_citation_responses(all_responses, str(resp_path))

    return all_responses


def run_verification_pipeline(
    client,
    citations_path: Path | None,
    round_number: int,
    output_dir: Path,
    force: bool = False,
    skip_pause: bool = False,
    citation_responses: list | None = None,
    _recheck_suffix: str = "",
) -> str:
    """
    Run the full citation verification pipeline for one round.

    Steps:
      1. Automated verifier (Sonnet + web search) — always runs
      2. Audit worksheet generation — always runs
      3. Human review pause — skipped if SKIP_HUMAN_REVIEW is True
      4. Generate moderator input string — returned to caller

    citation_responses: optional CitationResponse objects from this round (rounds 2+),
    included in the moderator input to show advocate acknowledgments.

    Returns the moderator input string (empty string if no citations).
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from citation_verifier import (
        PASS1_SYSTEM_PROMPT, PASS2_SYSTEM_PROMPT, PASS3_SYSTEM_PROMPT,
        build_pass1_prompts, build_pass2_prompt, build_pass3_prompt,
        merge_pass_results, parse_json_response,
    )
    from citation_extractor import load_citations
    from audit_worksheet import generate_audit_worksheet, generate_moderator_input
    import anthropic as _anthropic

    if citations_path is None or not citations_path.exists():
        console.print("  [dim]No citations to verify.[/dim]")
        return ""

    dirs = _verification_dirs(output_dir)
    ver_path = dirs["verifications"] / f"round_{round_number}{_recheck_suffix}_verifications.json"
    worksheet_path = dirs["audit"] / f"round_{round_number}{_recheck_suffix}_worksheet.md"
    mod_input_path = dirs["moderator_input"] / f"round_{round_number}{_recheck_suffix}.md"

    citations = load_citations(str(citations_path))
    citation_dicts = [c.to_dict() for c in citations]

    if not should_skip(ver_path, force):
        console.print(f"\n[bold]Citation Verifier — Round {round_number} (3-pass)[/bold]")
        import json as _json
        from tenacity import retry as _retry, stop_after_attempt as _stop, wait_exponential as _wait

        def _with_retry(fn, label):
            """Run fn() with exponential backoff on rate limit errors."""
            @_retry(stop=_stop(4), wait=_wait(multiplier=2, min=30, max=180), reraise=True)
            def _inner():
                return fn()
            try:
                return _inner()
            except _anthropic.RateLimitError as exc:
                console.print(f"  [red]Rate limit exhausted for {label}: {exc}[/red]")
                return None

        def _repair_json(broken_text: str, label: str) -> str | None:
            """One cheap call to recover valid JSON from a malformed response."""
            system = (
                "You are a JSON repair assistant. "
                "Return ONLY the corrected JSON object with no prose, no markdown fencing, "
                "no explanation, and no trailing text. "
                "Do not add, remove, or infer any fields — only fix encoding/syntax errors."
            )
            human = (
                "The following text was supposed to be a valid JSON object but failed to parse. "
                "Strip any invisible characters, fix encoding issues, and return ONLY valid JSON:\n\n"
                f"{broken_text}"
            )
            console.print(f"  [yellow]JSON parse failed for {label} — attempting cheap repair call[/yellow]")
            try:
                return call_api(
                    client, SONNET,
                    system_prompt=system,
                    human_message=human,
                    temperature=0.0,
                    max_tokens=2048,
                    label=f"{label}/json_repair",
                    bypass_fast=True,
                )
            except Exception as exc:
                console.print(f"  [red]JSON repair call failed for {label}: {exc}[/red]")
                return None

        # ── Pass 1: training knowledge, batched ──────────────────────────────
        console.print("  [bold]Pass 1[/bold] — training knowledge triage")
        pass1_results: dict[str, dict] = {}
        for i, prompt in enumerate(build_pass1_prompts(citation_dicts, batch_size=5)):
            response = _with_retry(
                lambda p=prompt: call_api(
                    client, SONNET,
                    system_prompt=PASS1_SYSTEM_PROMPT,
                    human_message=p,
                    temperature=0.2,
                    max_tokens=2048,
                    label=f"verifier/round_{round_number}/pass1/batch_{i+1}",
                    bypass_fast=True,
                ),
                label=f"pass1/batch_{i+1}",
            )
            if response:
                results = parse_json_response(response, expect_array=True)
                if isinstance(results, list):
                    for r in results:
                        if isinstance(r, dict) and "claim_id" in r:
                            pass1_results[r["claim_id"]] = r
        console.print(f"  [dim]Pass 1 complete: {len(pass1_results)}/{len(citation_dicts)} citations triaged[/dim]")

        # ── Pass 2: one bibliographic search per citation, all citations ─────
        console.print("  [bold]Pass 2[/bold] — bibliographic search (all citations)")
        pass2_results: dict[str, dict] = {}
        for idx, c in enumerate(citation_dicts):
            cid = c["claim_id"]
            if idx > 0:
                time.sleep(15)  # small gap; each call is ~1 search turn, low token count
            response = _with_retry(
                lambda c=c: call_api_with_web_search(
                    client, SONNET,
                    system_prompt=PASS2_SYSTEM_PROMPT,
                    human_message=build_pass2_prompt(c),
                    temperature=0.2,
                    max_tokens=1024,
                    max_turns=3,
                    label=f"verifier/round_{round_number}/pass2/{cid}",
                ),
                label=f"pass2/{cid}",
            )
            if response:
                result = parse_json_response(response, expect_array=False)
                if result == {} and response.strip():
                    repaired = _repair_json(response, label=f"pass2/{cid}")
                    if repaired:
                        result = parse_json_response(repaired, expect_array=False)
                if isinstance(result, dict) and result:
                    result["claim_id"] = result.get("claim_id", cid)
                    pass2_results[cid] = result
        console.print(f"  [dim]Pass 2 complete: {len(pass2_results)}/{len(citation_dicts)} citations searched[/dim]")

        # ── Pass 3: deep investigation, suspicious only ───────────────────────
        suspicious = [
            c for c in citation_dicts
            if (pass1_results.get(c["claim_id"], {}).get("suspicion_level") == "HIGH")
            or (pass2_results.get(c["claim_id"], {}).get("bibliographic_status") in ("UNCONFIRMED", "CONFLICTING"))
        ]
        console.print(f"  [bold]Pass 3[/bold] — deep investigation ({len(suspicious)} suspicious citations)")
        pass3_results: dict[str, dict] = {}
        for idx, c in enumerate(suspicious):
            cid = c["claim_id"]
            if idx > 0:
                time.sleep(30)
            response = _with_retry(
                lambda c=c: call_api_with_web_search(
                    client, SONNET,
                    system_prompt=PASS3_SYSTEM_PROMPT,
                    human_message=build_pass3_prompt(c),
                    temperature=0.2,
                    max_tokens=2048,
                    max_turns=8,
                    label=f"verifier/round_{round_number}/pass3/{cid}",
                ),
                label=f"pass3/{cid}",
            )
            if response:
                result = parse_json_response(response, expect_array=False)
                if result == {} and response.strip():
                    repaired = _repair_json(response, label=f"pass3/{cid}")
                    if repaired:
                        result = parse_json_response(repaired, expect_array=False)
                if isinstance(result, dict) and result:
                    result["claim_id"] = result.get("claim_id", cid)
                    pass3_results[cid] = result
        console.print(f"  [dim]Pass 3 complete: {len(pass3_results)} citations investigated[/dim]")

        # ── Merge passes into final verdicts ──────────────────────────────────
        all_verifications = []
        for c in citation_dicts:
            cid = c["claim_id"]
            merged = merge_pass_results(
                citation=c,
                pass1=pass1_results.get(cid),
                pass2=pass2_results.get(cid),
                pass3=pass3_results.get(cid),
            )
            all_verifications.append(merged)

        ver_path.write_text(_json.dumps(all_verifications, indent=2), encoding="utf-8")
        console.print(f"  [green]✓[/green] {len(all_verifications)} verifications → {ver_path.relative_to(ROOT)}")
    else:
        import json as _json
        console.print(f"  [dim]skip verification (exists)[/dim]")
        all_verifications = _json.loads(ver_path.read_text())

    # --- Step 2: Audit worksheet ---
    if not should_skip(worksheet_path, force):
        review_items, auto_resolved = generate_audit_worksheet(
            citation_dicts, all_verifications, round_number, str(worksheet_path)
        )
        console.print(f"  [green]✓[/green] worksheet → {worksheet_path.relative_to(ROOT)}")
        needs_review = len(review_items)
        high = sum(1 for x in review_items if x["priority"] == "HIGH")
    else:
        console.print(f"  [dim]skip worksheet (exists)[/dim]")
        needs_review = 0
        high = 0

    # --- Step 3: Human review pause ---
    if needs_review > 0 and not SKIP_HUMAN_REVIEW and not skip_pause:
        console.print(f"\n[bold yellow]⚠  Human audit required before continuing.[/bold yellow]")
        console.print(f"   {needs_review} claim(s) need review ({high} HIGH priority)")
        console.print(f"   Worksheet: {worksheet_path}")
        console.print(f"\n   Complete the worksheet, then press Enter to continue...")
        input()
    elif needs_review > 0 and (SKIP_HUMAN_REVIEW or skip_pause):
        console.print(
            f"  [yellow]Human audit skipped (--skip-human-review). "
            f"{needs_review} claim(s) unreviewed ({high} HIGH priority).[/yellow]"
        )

    # --- Step 4: Moderator input ---
    mod_input = generate_moderator_input(
        citation_dicts, all_verifications, audit_results=None,
        citation_responses=citation_responses if not _recheck_suffix else None,
        round_number=round_number
    )
    if SKIP_HUMAN_REVIEW and needs_review > 0:
        mod_input = (
            f"**NOTE: Human audit was skipped for this round ({needs_review} claim(s) unreviewed).**\n\n"
            + mod_input
        )

    mod_input_path.write_text(mod_input, encoding="utf-8")
    console.print(f"  [green]✓[/green] moderator input → {mod_input_path.relative_to(ROOT)}")
    return mod_input


# ---------------------------------------------------------------------------
# Round runners
# ---------------------------------------------------------------------------

def run_predebate(client, config: dict, output_dir: Path, force: bool = False, dry_run: bool = False, advocate_filter: str | None = None):
    console.rule("[bold]Pre-Debate: Position Papers[/bold]")
    shared_context = build_shared_context(config)
    prompt_template = config["round_prompts"]["predeabte_position_paper"]["prompt"]

    advocates = [advocate_filter] if advocate_filter else ADVOCATE_ORDER
    outputs = {}

    for advocate_id in advocates:
        agent = config["agents"][advocate_id]
        out_path = output_dir / "predebate" / f"{advocate_id}.md"

        if should_skip(out_path, force):
            console.print(f"  [dim]skip {advocate_id} (exists)[/dim]")
            outputs[advocate_id] = read_output(out_path)
            continue

        human_message = "\n\n---\n\n".join([
            shared_context,
            fill_template(prompt_template, curly_vars={
                "ADVOCATE_DISPLAY_NAME": agent["display_name"],
                "DISCIPLINARY_LEAD": agent["disciplinary_lead"],
            }),
        ])

        console.print(f"\n[bold]{agent['display_name']}[/bold]")

        if dry_run:
            console.print(Panel(human_message[:800] + "\n...[truncated]", title="DRY RUN", expand=False))
            continue

        text = call_api(
            client, SONNET,
            system_prompt=agent["system_prompt"],
            human_message=human_message,
            temperature=config["notes"]["temperature"]["advocates"],
            label=f"predebate/{advocate_id}",
        )
        write_output(text, out_path)
        outputs[advocate_id] = text

    return outputs


def run_round_1(
    client,
    config: dict,
    output_dir: Path,
    force: bool = False,
    dry_run: bool = False,
    advocate_filter: str | None = None,
):
    console.rule("[bold]Round 1: Opening Statements[/bold]")
    if not validate_prerequisites("round_1", output_dir, force):
        return {}
    shared_context = build_shared_context(config)
    prompt_template = config["round_prompts"]["round_1"]["prompt"]

    # Load pre-debate position papers if they exist
    predebate_dir = output_dir / "predebate"
    predebate_outputs = read_round_outputs(predebate_dir)
    compiled_position_papers = build_advocate_outputs_block(predebate_outputs, config) if predebate_outputs else ""

    advocates = [advocate_filter] if advocate_filter else ADVOCATE_ORDER
    outputs = {}

    for advocate_id in advocates:
        agent = config["agents"][advocate_id]
        out_path = output_dir / "round_1" / f"{advocate_id}.md"

        if should_skip(out_path, force):
            console.print(f"  [dim]skip {advocate_id} (exists)[/dim]")
            outputs[advocate_id] = read_output(out_path)
            continue

        human_message = "\n\n---\n\n".join(filter(None, [
            shared_context,
            fill_template(
                prompt_template,
                curly_vars={
                    "ADVOCATE_DISPLAY_NAME": agent["display_name"],
                    "DISCIPLINARY_LEAD": agent["disciplinary_lead"],
                },
                bracket_vars={"COMPILED_POSITION_PAPERS": compiled_position_papers},
            ),
        ]))

        console.print(f"\n[bold]{agent['display_name']}[/bold]")

        if dry_run:
            console.print(Panel(human_message[:800] + "\n...[truncated]", title="DRY RUN", expand=False))
            continue

        text = call_api(
            client, SONNET,
            system_prompt=agent["system_prompt"],
            human_message=human_message,
            temperature=config["notes"]["temperature"]["advocates"],
            label=f"round_1/{advocate_id}",
        )
        write_output(text, out_path)
        outputs[advocate_id] = text

    if dry_run or not outputs:
        return outputs

    # Citation extraction + verification pipeline (runs even for single-advocate tests)
    console.print("\n[bold]Extracting citations...[/bold]")
    citations_path = extract_and_save_citations(outputs, round_number=1, output_dir=output_dir)
    verification_input = run_verification_pipeline(
        client, citations_path, round_number=1, output_dir=output_dir, force=force,
        skip_pause=bool(advocate_filter),  # single-advocate runs never pause
    )

    # Moderator fact-check + digest — skip for single-advocate runs
    if not advocate_filter:
        warn_incomplete_round("round_1", output_dir)
        _run_moderation(client, config, output_dir, round_number=1, round_outputs=outputs, force=force, verification_input=verification_input)
        generate_round_digest(client, config, round_number=1, round_outputs=outputs, output_dir=output_dir, force=force)

    return outputs


def _run_moderation(
    client,
    config: dict,
    output_dir: Path,
    round_number: int,
    round_outputs: dict[str, str],
    force: bool = False,
    verification_input: str = "",
):
    round_key = f"round_{round_number}"
    out_path = output_dir / round_key / "moderation_report.md"

    if should_skip(out_path, force):
        console.print(f"  [dim]skip moderation report (exists)[/dim]")
        return read_output(out_path)

    console.print(f"\n[bold]Moderator — Round {round_number} Fact-Check[/bold]")
    prompt_template = config["round_prompts"]["moderator_fact_check_round"]["prompt"]
    shared_context = build_shared_context(config)
    outputs_block = build_advocate_outputs_block(round_outputs, config)

    verification_block = (
        f"\n\n## Automated Verification Results\n\n{verification_input}"
        if verification_input
        else ""
    )

    human_message = "\n\n---\n\n".join(filter(None, [
        shared_context,
        fill_template(
            prompt_template,
            curly_vars={"ROUND_NUMBER": str(round_number)},
            bracket_vars={"ROUND_OUTPUTS": outputs_block + verification_block},
        ),
    ]))

    text = call_api(
        client, SONNET,
        system_prompt=config["agents"]["moderator"]["system_prompt"],
        human_message=human_message,
        temperature=config["notes"]["temperature"]["moderator"],
        label=f"round_{round_number}/moderation",
    )
    write_output(text, out_path)
    return text


def run_round_2(
    client,
    config: dict,
    output_dir: Path,
    force: bool = False,
    dry_run: bool = False,
):
    console.rule("[bold]Round 2: Cross-Disciplinary Examination[/bold]")
    if not validate_prerequisites("round_2", output_dir, force):
        return {}, {}
    shared_context = build_shared_context(config)
    canonical_record = read_canonical_record(output_dir)
    pairings = config["round_2_pairings"]

    # Build lookup: questioner_id -> pairing
    pairing_by_questioner = {p["questioner"]: p for p in pairings}
    # Build lookup: target_id -> pairing
    pairing_by_target = {p["target"]: p for p in pairings}

    question_outputs = {}
    response_outputs = {}

    # --- Phase A: Questions ---
    console.print("\n[underline]Phase A — Questions[/underline]")
    q_template = config["round_prompts"]["round_2_question"]["prompt"]

    for questioner_id in ADVOCATE_ORDER:
        if questioner_id not in pairing_by_questioner:
            continue
        pairing = pairing_by_questioner[questioner_id]
        target_id = pairing["target"]
        questioner_agent = config["agents"][questioner_id]
        target_agent = config["agents"][target_id]

        out_path = output_dir / "round_2" / f"{questioner_id}_question.md"

        if should_skip(out_path, force):
            console.print(f"  [dim]skip {questioner_id}_question (exists)[/dim]")
            question_outputs[questioner_id] = read_output(out_path)
            continue

        human_message = "\n\n---\n\n".join(filter(None, [
            shared_context,
            canonical_record,
            fill_template(q_template, curly_vars={
                "ADVOCATE_DISPLAY_NAME": questioner_agent["display_name"],
                "DISCIPLINARY_LEAD": questioner_agent["disciplinary_lead"],
                "TARGET_ADVOCATE": target_agent["display_name"],
                "TENSION_DESCRIPTION": pairing["tension"],
            }),
        ]))

        console.print(f"\n[bold]{questioner_agent['display_name']} → {target_agent['display_name']}[/bold]")

        if dry_run:
            console.print(Panel(human_message[:600] + "\n...[truncated]", title="DRY RUN", expand=False))
            continue

        text = call_api(
            client, OPUS,
            system_prompt=questioner_agent["system_prompt"],
            human_message=human_message,
            temperature=config["notes"]["temperature"]["advocates"],
            label=f"round_2/{questioner_id}_question",
        )
        write_output(text, out_path)
        question_outputs[questioner_id] = text

    if dry_run:
        return {}, {}

    # --- Phase B: Responses ---
    console.print("\n[underline]Phase B — Responses[/underline]")
    r_template = config["round_prompts"]["round_2_response"]["prompt"]

    # Load R1 verifications for corrections injection
    r1_verifications = load_all_verifications(output_dir, through_round=1)

    # Build a block of all questions for context
    all_questions_block = "\n\n---\n\n".join(
        f"Question from {config['agents'][qid]['display_name']} to "
        f"{config['agents'][pairing_by_questioner[qid]['target']]['display_name']}:\n\n{text}"
        for qid, text in question_outputs.items()
    )

    for target_id in ADVOCATE_ORDER:
        if target_id not in pairing_by_target:
            continue
        pairing = pairing_by_target[target_id]
        questioner_id = pairing["questioner"]
        target_agent = config["agents"][target_id]
        questioner_agent = config["agents"][questioner_id]
        question_text = question_outputs.get(questioner_id, "")

        out_path = output_dir / "round_2" / f"{target_id}_response.md"

        if should_skip(out_path, force):
            console.print(f"  [dim]skip {target_id}_response (exists)[/dim]")
            response_outputs[target_id] = read_output(out_path)
            continue

        corrections_block = build_corrections_block(target_id, r1_verifications)

        human_message = "\n\n---\n\n".join(filter(None, [
            shared_context,
            canonical_record,
            f"[All Round 2 Questions for Context]\n\n{all_questions_block}",
            fill_template(r_template, curly_vars={
                "QUESTIONING_ADVOCATE": questioner_agent["display_name"],
            }, bracket_vars={
                "QUESTION_TEXT": question_text,
                "CITATION_CORRECTIONS": corrections_block,
            }),
        ]))

        console.print(f"\n[bold]{target_agent['display_name']} (responding)[/bold]")

        text = call_api(
            client, OPUS,
            system_prompt=target_agent["system_prompt"],
            human_message=human_message,
            temperature=config["notes"]["temperature"]["advocates"],
            label=f"round_2/{target_id}_response",
        )
        write_output(text, out_path)
        response_outputs[target_id] = text

    # Citation extraction + response parsing + verification pipeline
    all_r2_outputs = {**question_outputs, **response_outputs}
    console.print("\n[bold]Extracting citations...[/bold]")
    citations_path = extract_and_save_citations(all_r2_outputs, round_number=2, output_dir=output_dir)

    console.print("\n[bold]Parsing citation responses...[/bold]")
    citation_responses = parse_and_process_responses(
        response_outputs, round_number=2, output_dir=output_dir,
        client=client, config=config, force=force,
    )

    verification_input = run_verification_pipeline(
        client, citations_path, round_number=2, output_dir=output_dir, force=force,
        citation_responses=citation_responses,
    )

    # Moderation
    warn_incomplete_round("round_2", output_dir)
    _run_moderation(client, config, output_dir, round_number=2, round_outputs=all_r2_outputs, force=force, verification_input=verification_input)
    generate_claim_ledger(client, config, all_r2_outputs, output_dir, round_number=2, force=force)
    generate_round_digest(client, config, round_number=2, round_outputs=all_r2_outputs, output_dir=output_dir, force=force)

    return question_outputs, response_outputs


def run_round_3(
    client,
    config: dict,
    output_dir: Path,
    force: bool = False,
    dry_run: bool = False,
    advocate_filter: str | None = None,
):
    console.rule("[bold]Round 3: The Seven Required Texts[/bold]")
    if not validate_prerequisites("round_3", output_dir, force):
        return {}
    shared_context = build_shared_context(config)
    canonical_record = read_canonical_record(output_dir)
    prompt_template = config["round_prompts"]["round_3"]["prompt"]

    # Build the all-7-texts block and substitute it into the template
    texts_block = build_round_3_texts_block(config)
    # The template has singular {TEXT_NAME}/{TEXT_PASSAGE}/{TEXT_DISPUTE} — replace
    # the entire section with the multi-text block before per-advocate filling
    texts_section_pattern = r"TEXT: \{TEXT_NAME\}\nPASSAGE: \{TEXT_PASSAGE\}\nCORE DISPUTE: \{TEXT_DISPUTE\}"
    base_prompt = re.sub(texts_section_pattern, texts_block, prompt_template)

    advocates = [advocate_filter] if advocate_filter else ADVOCATE_ORDER
    outputs = {}

    # Load prior verifications for corrections injection (R1 + R2)
    prior_verifications = load_all_verifications(output_dir, through_round=2)

    for advocate_id in advocates:
        agent = config["agents"][advocate_id]
        out_path = output_dir / "round_3" / f"{advocate_id}.md"

        if should_skip(out_path, force):
            console.print(f"  [dim]skip {advocate_id} (exists)[/dim]")
            outputs[advocate_id] = read_output(out_path)
            continue

        corrections_block = build_corrections_block(advocate_id, prior_verifications)

        prompt = fill_template(base_prompt, curly_vars={
            "ADVOCATE_DISPLAY_NAME": agent["display_name"],
            "DISCIPLINARY_LEAD": agent["disciplinary_lead"],
        }, bracket_vars={
            "CANONICAL_RECORD_TO_DATE": canonical_record,
            "CITATION_CORRECTIONS": corrections_block,
        })

        human_message = "\n\n---\n\n".join(filter(None, [
            shared_context,
            prompt,
        ]))

        console.print(f"\n[bold]{agent['display_name']}[/bold]")

        if dry_run:
            console.print(Panel(human_message[:800] + "\n...[truncated]", title="DRY RUN", expand=False))
            continue

        text = call_api(
            client, SONNET,
            system_prompt=agent["system_prompt"],
            human_message=human_message,
            temperature=config["notes"]["temperature"]["advocates"],
            max_tokens=4096,
            label=f"round_3/{advocate_id}",
        )
        write_output(text, out_path)
        outputs[advocate_id] = text

    if dry_run or not outputs:
        return outputs

    console.print("\n[bold]Extracting citations...[/bold]")
    citations_path = extract_and_save_citations(outputs, round_number=3, output_dir=output_dir)

    console.print("\n[bold]Parsing citation responses...[/bold]")
    citation_responses = parse_and_process_responses(
        outputs, round_number=3, output_dir=output_dir,
        client=client, config=config, force=force,
    )

    verification_input = run_verification_pipeline(
        client, citations_path, round_number=3, output_dir=output_dir, force=force,
        skip_pause=bool(advocate_filter),
        citation_responses=citation_responses,
    )
    if not advocate_filter:
        warn_incomplete_round("round_3", output_dir)
        _run_moderation(client, config, output_dir, round_number=3, round_outputs=outputs, force=force, verification_input=verification_input)
        generate_claim_ledger(client, config, outputs, output_dir, round_number=3, force=force)
        generate_round_digest(client, config, round_number=3, round_outputs=outputs, output_dir=output_dir, force=force)

    return outputs


def run_synthesis(
    client,
    config: dict,
    output_dir: Path,
    force: bool = False,
    dry_run: bool = False,
):
    console.rule("[bold]Synthesis: Moderator Synthesis + Responses[/bold]")
    if not validate_prerequisites("synthesis", output_dir, force):
        return
    shared_context = build_shared_context(config)
    canonical_record = read_canonical_record(output_dir)

    # --- Moderator synthesis ---
    synth_path = output_dir / "synthesis" / "moderator_synthesis.md"
    synthesis_text = read_output(synth_path)

    if not synthesis_text or force:
        console.print("\n[bold]Moderator — Synthesis[/bold]")
        synth_prompt = config["round_prompts"]["moderator_synthesis"]["prompt"]

        human_message = "\n\n---\n\n".join(filter(None, [
            shared_context,
            canonical_record,
            synth_prompt,
        ]))

        if not dry_run:
            synthesis_text = call_api(
                client, OPUS,
                system_prompt=config["agents"]["moderator"]["system_prompt"],
                human_message=human_message,
                temperature=config["notes"]["temperature"]["moderator"],
                label="synthesis/moderator",
            )
            write_output(synthesis_text, synth_path)
        else:
            console.print(Panel(human_message[:600] + "\n...[truncated]", title="DRY RUN", expand=False))
            return

    # --- Synthesis responses ---
    console.print("\n[underline]Advocate Synthesis Responses[/underline]")
    response_template = config["round_prompts"]["synthesis_response"]["prompt"]

    for advocate_id in ADVOCATE_ORDER:
        agent = config["agents"][advocate_id]
        out_path = output_dir / "synthesis" / f"{advocate_id}_response.md"

        if should_skip(out_path, force):
            console.print(f"  [dim]skip {advocate_id}_response (exists)[/dim]")
            continue

        console.print(f"\n[bold]{agent['display_name']}[/bold]")

        human_message = "\n\n---\n\n".join(filter(None, [
            shared_context,
            fill_template(response_template, curly_vars={
                "ADVOCATE_DISPLAY_NAME": agent["display_name"],
                "DISCIPLINARY_LEAD": agent["disciplinary_lead"],
            }, bracket_vars={
                "MODERATOR_SYNTHESIS_TEXT": synthesis_text,
            }),
        ]))

        text = call_api(
            client, SONNET,
            system_prompt=agent["system_prompt"],
            human_message=human_message,
            temperature=config["notes"]["temperature"]["advocates"],
            label=f"synthesis/{advocate_id}_response",
        )
        write_output(text, out_path)


def run_round_4(
    client,
    config: dict,
    output_dir: Path,
    force: bool = False,
    dry_run: bool = False,
    advocate_filter: str | None = None,
):
    console.rule("[bold]Round 4: Closing Arguments[/bold]")
    if not validate_prerequisites("round_4", output_dir, force):
        return {}
    shared_context = build_shared_context(config)
    prompt_template = config["round_prompts"]["round_4"]["prompt"]

    # Import context packager for compressed context
    sys.path.insert(0, str(ROOT / "scripts"))
    from context_packager import build_r4_context

    advocates = [advocate_filter] if advocate_filter else ADVOCATE_ORDER_R4
    outputs = {}

    # Load prior verifications and retracted claims for corrections injection
    prior_verifications = load_all_verifications(output_dir, through_round=3)
    retracted_claims = load_retracted_claims(output_dir)

    for advocate_id in advocates:
        agent = config["agents"][advocate_id]
        out_path = output_dir / "round_4" / f"{advocate_id}.md"

        if should_skip(out_path, force):
            console.print(f"  [dim]skip {advocate_id} (exists)[/dim]")
            outputs[advocate_id] = read_output(out_path)
            continue

        console.print(f"\n[bold]{agent['display_name']}[/bold]")

        compressed_record = build_r4_context(
            advocate_id=advocate_id,
            config=config,
            output_dir=output_dir,
            client=client,
            retracted_claims=retracted_claims,
        )

        corrections_block = build_corrections_block(advocate_id, prior_verifications)

        prompt = fill_template(
            prompt_template,
            curly_vars={
                "ADVOCATE_DISPLAY_NAME": agent["display_name"],
                "DISCIPLINARY_LEAD": agent["disciplinary_lead"],
            },
            bracket_vars={
                "COMPRESSED_CANONICAL_RECORD": compressed_record,
                "CITATION_CORRECTIONS": corrections_block,
            },
        )

        human_message = "\n\n---\n\n".join(filter(None, [
            shared_context,
            prompt,
        ]))

        if dry_run:
            console.print(Panel(human_message[:800] + "\n...[truncated]", title="DRY RUN", expand=False))
            continue

        text = call_api(
            client, OPUS,
            system_prompt=agent["system_prompt"],
            human_message=human_message,
            temperature=config["notes"]["temperature"]["advocates"],
            max_tokens=4096,
            label=f"round_4/{advocate_id}",
        )
        write_output(text, out_path)
        outputs[advocate_id] = text

    if dry_run or not outputs:
        return outputs

    console.print("\n[bold]Extracting citations...[/bold]")
    citations_path = extract_and_save_citations(outputs, round_number=4, output_dir=output_dir)

    console.print("\n[bold]Parsing citation responses...[/bold]")
    citation_responses = parse_and_process_responses(
        outputs, round_number=4, output_dir=output_dir,
        client=client, config=config, force=force,
    )

    verification_input = run_verification_pipeline(
        client, citations_path, round_number=4, output_dir=output_dir, force=force,
        skip_pause=bool(advocate_filter),
        citation_responses=citation_responses,
    )
    if not advocate_filter:
        warn_incomplete_round("round_4", output_dir)
        _run_moderation(client, config, output_dir, round_number=4, round_outputs=outputs, force=force, verification_input=verification_input)
        generate_round_digest(client, config, round_number=4, round_outputs=outputs, output_dir=output_dir, force=force)
        generate_final_summary(client, config, output_dir=output_dir, force=force)

    return outputs


# ---------------------------------------------------------------------------
# Round digest and final summary
# ---------------------------------------------------------------------------

ROUND_DIGEST_PROMPT = """You are producing a brief round digest for a structured theological debate.

Below are the outputs from Round {ROUND_NUMBER} — {ROUND_TITLE}. Produce a digest of exactly this structure:

**Round {ROUND_NUMBER} Digest — {ROUND_TITLE}**

*One sentence per advocate on their main argument this round:*
- **Biblical Scholar:** ...
- **Reception Historian:** ...
- **Hermeneutician:** ...
- **Systematic Theologian:** ...
- **Pastoral Theologian:** ...
- **Social and Cultural Analyst:** ...

*Key tension this round:* [One sentence identifying the sharpest point of disagreement.]

*Notable concessions or agreements:* [One sentence, or "None apparent."]

Keep the entire digest under 250 words. Be precise — name specific claims, not general themes."""

FINAL_SUMMARY_PROMPT = """You are producing a final summary of a completed multi-round theological debate.

The debate: "Women, Authority, and the Church: A Six-Discipline Inquiry"

You will receive the full canonical debate record and a citation audit summary. Produce a summary in two clearly labelled sections:

---

## Debate Summary

In 400–500 words, covering:
- How each discipline's position evolved or sharpened across the rounds
- The two or three most significant tensions that ran through the whole debate
- What the debate clarified that wasn't clear at the start
- What remained genuinely unresolved at the close
- One sentence on what a reader should take away from the debate as a whole

## Citation Audit Summary

Using the verification data provided, produce a structured summary:
- Total citations across all rounds
- Breakdown by automated verdict (VERIFIED, LIKELY_ACCURATE, PARTIALLY_VERIFIED, NEEDS_HUMAN_REVIEW, FABRICATION_RISK)
- How many were flagged for human review; how many of those were reviewed vs. skipped
- Any FABRICATION_RISK claims that were not resolved by human audit — name them specifically (claim_id and advocate)
- Overall citation quality assessment in one sentence

Keep the audit summary factual and specific. Do not soften fabrication risks."""


def generate_round_digest(
    client,
    config: dict,
    round_number: int,
    round_outputs: dict[str, str],
    output_dir: Path,
    force: bool = False,
) -> str:
    """Generate and save a ~200-word digest of a completed round. Also prints to console."""
    out_path = output_dir / f"round_{round_number}" / "round_digest.md"
    if should_skip(out_path, force):
        console.print(f"  [dim]skip round digest (exists)[/dim]")
        return read_output(out_path) or ""

    console.print(f"\n[bold]Round {round_number} Digest[/bold]")
    outputs_block = build_advocate_outputs_block(round_outputs, config)
    title = ROUND_TITLES.get(f"round_{round_number}", f"Round {round_number}")

    prompt = ROUND_DIGEST_PROMPT.format(ROUND_NUMBER=round_number, ROUND_TITLE=title)
    human_message = "\n\n---\n\n".join([outputs_block, prompt])

    text = call_api(
        client, SONNET,
        system_prompt="You are a neutral summarizer for a structured academic debate.",
        human_message=human_message,
        temperature=0.3,
        max_tokens=512,
        label=f"round_{round_number}/digest",
    )
    write_output(text, out_path)
    console.print(Panel(text, title=f"Round {round_number} Digest", expand=False))
    return text


def generate_claim_ledger(
    client,
    config: dict,
    round_outputs: dict[str, str],
    output_dir: Path,
    round_number: int,
    force: bool = False,
) -> str:
    """
    Generate or update the claim ledger after Round 2 or Round 3.

    Round 2: creates synthesis/claim_ledger_r2.md (initial ledger).
    Round 3: creates synthesis/claim_ledger.md (canonical version for Round 4),
             using the Round 2 ledger as a base if it exists.
    """
    if round_number == 2:
        out_path = output_dir / "synthesis" / "claim_ledger_r2.md"
        prompt_key = "claim_ledger_initial"
    else:
        out_path = output_dir / "synthesis" / "claim_ledger.md"
        prompt_key = "claim_ledger_update"

    if should_skip(out_path, force):
        console.print(f"  [dim]skip claim ledger (exists)[/dim]")
        return read_output(out_path) or ""

    console.print(f"\n[bold]Claim Ledger — Round {round_number}[/bold]")

    prompt_template = config["round_prompts"][prompt_key]["prompt"]
    outputs_block = build_advocate_outputs_block(round_outputs, config)

    # For Round 3 update, inject the existing Round 2 ledger
    bracket_vars = {"ROUND_OUTPUTS": outputs_block}
    if round_number == 3:
        r2_ledger_path = output_dir / "synthesis" / "claim_ledger_r2.md"
        existing_ledger = read_output(r2_ledger_path) or "[No Round 2 ledger found]"
        bracket_vars["EXISTING_LEDGER"] = existing_ledger

    human_message = fill_template(prompt_template, curly_vars={}, bracket_vars=bracket_vars)

    text = call_api(
        client, SONNET,
        system_prompt="You are a neutral summarizer for a structured academic debate. Extract and track contested claims faithfully.",
        human_message=human_message,
        temperature=0.25,
        max_tokens=2048,
        label=f"synthesis/claim_ledger_r{round_number}",
    )
    write_output(text, out_path)
    return text


def _aggregate_verification_stats(output_dir: Path) -> str:
    """Load all verification JSON files and produce a plain-text audit summary."""
    import json

    if "tests" in str(output_dir):
        ver_base = output_dir / "verifications"
    else:
        ver_base = VERIFICATION_DIR / "verifications"

    all_verifications = []
    for round_num in range(1, 5):
        ver_file = ver_base / f"round_{round_num}_verifications.json"
        if ver_file.exists():
            try:
                data = json.loads(ver_file.read_text())
                for v in data:
                    v["_round"] = round_num
                all_verifications.extend(data)
            except Exception:
                pass

    if not all_verifications:
        return "No verification data found."

    from collections import Counter
    verdict_counts = Counter(v.get("overall_verdict", "UNKNOWN") for v in all_verifications)
    needs_review = [v for v in all_verifications if v.get("human_review_needed")]
    fabrication = [v for v in all_verifications if v.get("overall_verdict") == "FABRICATION_RISK"]

    lines = [
        f"Total citations verified: {len(all_verifications)}",
        "",
        "Verdict breakdown:",
    ]
    for verdict, count in sorted(verdict_counts.items(), key=lambda x: -x[1]):
        lines.append(f"  {verdict}: {count}")
    lines.append("")
    lines.append(f"Flagged for human review: {len(needs_review)}")
    if fabrication:
        lines.append(f"FABRICATION_RISK claims ({len(fabrication)}):")
        for v in fabrication:
            lines.append(f"  - {v['claim_id']} ({v.get('_round', '?')}): {v.get('summary', '')[:120]}")
    else:
        lines.append("FABRICATION_RISK claims: none")

    return "\n".join(lines)


def generate_final_summary(
    client,
    config: dict,
    output_dir: Path,
    force: bool = False,
) -> str:
    """Generate and save a final debate summary + citation audit after Round 4."""
    out_path = output_dir / "synthesis" / "final_summary.md"
    if should_skip(out_path, force):
        console.print(f"  [dim]skip final summary (exists)[/dim]")
        return read_output(out_path) or ""

    console.rule("[bold]Final Debate Summary[/bold]")
    canonical_record = read_canonical_record(output_dir)
    audit_stats = _aggregate_verification_stats(output_dir)

    human_message = "\n\n---\n\n".join(filter(None, [
        canonical_record,
        f"## Verification Data\n\n{audit_stats}",
        FINAL_SUMMARY_PROMPT,
    ]))

    text = call_api(
        client, SONNET,
        system_prompt="You are a neutral summarizer for a structured academic debate.",
        human_message=human_message,
        temperature=0.3,
        max_tokens=1024,
        label="final_summary",
    )
    write_output(text, out_path)
    console.print(Panel(text, title="Final Summary", expand=False))
    return text


# ---------------------------------------------------------------------------
# Document compiler integration
# ---------------------------------------------------------------------------

def compile_canonical_record(output_dir: Path, config: dict):
    """Rebuild the canonical record from all completed round outputs."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from document_compiler import compile_full_record
    compile_full_record(output_dir, config)
    console.print(f"  [green]✓[/green] canonical_record.md updated")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="Debate Conductor / Inquiry Engine")

    # New config-driven mode
    parser.add_argument("--config", type=str,
                        help="Path to inquiry_config.json (new config-driven mode)")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--round", type=str,
                       help="Run a specific round (legacy: predebate/1/2/3/synthesis/4, or any round key)")
    group.add_argument("--all", action="store_true", help="Run all rounds sequentially")

    parser.add_argument("--advocate", "--participant", type=str, dest="advocate",
                        help="Run only this participant (for single-participant testing)")
    parser.add_argument("--test", action="store_true",
                        help="Write outputs to outputs/tests/{timestamp}/ instead of outputs/")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print assembled prompts without calling the API")
    parser.add_argument("--force", action="store_true",
                        help="Re-run even if output files already exist")
    parser.add_argument("--fast", action="store_true",
                        help="Cap output at 600 tokens per call (~25%% of normal). For architecture testing.")
    parser.add_argument("--skip-human-review", action="store_true",
                        help="Skip the human audit pause. Automated verifier still runs.")
    parser.add_argument("--output-dir", type=str,
                        help="Override output directory (for config-driven mode)")
    return parser.parse_args()


def main():
    global FAST_MODE, SKIP_HUMAN_REVIEW
    args = parse_args()

    if args.fast:
        FAST_MODE = True
        console.print("[yellow]FAST MODE — output capped at 600 tokens per call[/yellow]")

    if args.skip_human_review:
        SKIP_HUMAN_REVIEW = True
        console.print("[yellow]Human audit pauses skipped — automated verdicts only[/yellow]")

    # ── New config-driven mode ──────────────────────────────────────────────
    if args.config:
        from inquiry_schema import load_inquiry_config
        import engine

        inquiry_config = load_inquiry_config(args.config)
        console.print(f"[bold]Inquiry:[/bold] {inquiry_config.inquiry.title}")
        console.print(f"[dim]Participants: {', '.join(p.display_name for p in inquiry_config.participants)}[/dim]")
        console.print(f"[dim]Rounds: {', '.join(r.title for r in inquiry_config.rounds)}[/dim]")

        # Propagate flags to engine
        engine.FAST_MODE = FAST_MODE
        engine.SKIP_HUMAN_REVIEW = SKIP_HUMAN_REVIEW

        # Resolve output dir
        if args.output_dir:
            out = Path(args.output_dir)
        elif args.test:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
            out = OUTPUT_DIR / "tests" / timestamp
        else:
            # Use a slug of the inquiry title
            slug = re.sub(r'[^a-z0-9]+', '_', inquiry_config.inquiry.title.lower()).strip('_')[:50]
            out = OUTPUT_DIR / slug

        engine.run_inquiry(
            config=inquiry_config,
            output_dir=out,
            force=args.force,
            dry_run=args.dry_run,
            round_filter=args.round if not args.all else None,
            participant_filter=args.advocate,
        )
        return

    # ── Legacy mode (original system_prompts.json) ──────────────────────────
    config = load_config()
    output_dir = resolve_output_dir(args.test)
    if not args.dry_run:
        init_audit_log(output_dir)
    client = None if args.dry_run else make_api_client()

    round_map = {
        "predebate": lambda: run_predebate(client, config, output_dir, args.force, args.dry_run, args.advocate),
        "1":         lambda: run_round_1(client, config, output_dir, args.force, args.dry_run, args.advocate),
        "2":         lambda: run_round_2(client, config, output_dir, args.force, args.dry_run),
        "3":         lambda: run_round_3(client, config, output_dir, args.force, args.dry_run, args.advocate),
        "synthesis": lambda: run_synthesis(client, config, output_dir, args.force, args.dry_run),
        "4":         lambda: run_round_4(client, config, output_dir, args.force, args.dry_run, args.advocate),
    }

    if args.all:
        rounds_to_run = ["predebate", "1", "2", "3", "synthesis", "4"]
    else:
        rounds_to_run = [args.round]

    for round_key in rounds_to_run:
        if round_key not in round_map:
            console.print(f"[red]Unknown legacy round: {round_key}. Use --config for custom round keys.[/red]")
            sys.exit(1)
        round_map[round_key]()
        if not args.dry_run and round_key != "synthesis":
            compile_canonical_record(output_dir, config)

    console.print("\n[bold green]Done.[/bold green]")


if __name__ == "__main__":
    main()
