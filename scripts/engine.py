"""
Inquiry Engine
Config-driven orchestrator for multi-agent inquiries.

Replaces the hardcoded round runners in conductor.py with generic dispatch
based on round type. Accepts an InquiryConfig and runs any inquiry.

Usage:
    from engine import run_inquiry, run_round
    from inquiry_schema import load_inquiry_config

    config = load_inquiry_config("my_config.json")
    run_inquiry(config, output_dir=Path("outputs/my_inquiry"))
"""

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

from inquiry_schema import (
    InquiryConfig, RoundConfig, RoundType, ModelChoice,
    resolve_model, load_inquiry_config,
)

console = Console()

# ---------------------------------------------------------------------------
# Global flags (set via CLI args)
# ---------------------------------------------------------------------------

FAST_MODE = False
FAST_MAX_TOKENS = 600
FAST_NOTE = "\n\n[FAST/TEST MODE: Respond in 250 words or fewer. Truncate freely. Structure matters more than completeness.]"
SKIP_HUMAN_REVIEW = False

# ---------------------------------------------------------------------------
# Audit logger
# ---------------------------------------------------------------------------

_audit_log_path: Path | None = None


def init_audit_log(output_dir: Path):
    global _audit_log_path
    _audit_log_path = output_dir / "audit_log.jsonl"
    _audit_log_path.parent.mkdir(parents=True, exist_ok=True)


def _audit(entry: dict):
    if _audit_log_path is None:
        return
    with open(_audit_log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Template filling (unchanged from conductor.py)
# ---------------------------------------------------------------------------

def fill_curly(template: str, variables: dict) -> str:
    def replacer(m):
        key = m.group(1)
        if key in variables:
            return str(variables[key])
        return m.group(0)
    return re.sub(r'\{([A-Z_][A-Z0-9_]*)\}', replacer, template)


def fill_bracket(template: str, variables: dict) -> str:
    for key, value in variables.items():
        template = template.replace(f"[{key}]", value)
    return template


def fill_template(template: str, curly_vars: dict = None, bracket_vars: dict = None) -> str:
    result = template
    if curly_vars:
        result = fill_curly(result, curly_vars)
    if bracket_vars:
        result = fill_bracket(result, bracket_vars)
    return result


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def write_output(text: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    console.print(f"  [green]✓[/green] wrote {path}")


def read_output(path: Path) -> str | None:
    if path.exists() and path.stat().st_size > 0:
        return path.read_text(encoding="utf-8")
    return None


def should_skip(path: Path, force: bool) -> bool:
    if force:
        return False
    return path.exists() and path.stat().st_size > 0


# ---------------------------------------------------------------------------
# API calls (unchanged from conductor.py)
# ---------------------------------------------------------------------------

def make_api_client():
    import anthropic
    return anthropic.Anthropic()


def _is_retryable(exc: BaseException) -> bool:
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
            messages.append({"role": "assistant", "content": response.content})
            continue

        break

    # Exhausted turns — nudge model to emit JSON
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
# Context assembly
# ---------------------------------------------------------------------------

def build_shared_context(config: InquiryConfig) -> str:
    """Build the shared context block from the inquiry config."""
    parts = []
    if config.inquiry.shared_context:
        parts.append(config.inquiry.shared_context)
    if config.inquiry.grounding_document:
        label = config.inquiry.grounding_document_label or "Grounding Document"
        parts.append(f"## {label}\n\n{config.inquiry.grounding_document}")
    return "\n\n---\n\n".join(parts) if parts else ""


def read_canonical_record(output_dir: Path) -> str:
    record_path = output_dir / "canonical_record.md"
    if record_path.exists() and record_path.stat().st_size > 0:
        return record_path.read_text(encoding="utf-8")
    return ""


def build_participant_outputs_block(
    round_outputs: dict[str, str],
    config: InquiryConfig,
) -> str:
    """Format all participant outputs as a labeled block (for moderator input)."""
    parts = []
    for pid in config.participant_ids:
        if pid not in round_outputs:
            continue
        p = config.participant_map[pid]
        parts.append(f"## {p.display_name}\n\n{round_outputs[pid]}")
    return "\n\n---\n\n".join(parts)


def build_required_texts_block(round_cfg: RoundConfig) -> str:
    """Build the required texts block for a round."""
    parts = []
    for t in round_cfg.required_texts:
        text_parts = [f"TEXT {t.order}: {t.text_name}"]
        if t.passage:
            text_parts.append(f"PASSAGE: {t.passage}")
        if t.core_dispute:
            text_parts.append(f"CORE DISPUTE: {t.core_dispute}")
        parts.append("\n".join(text_parts))
    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def compute_required_files(config: InquiryConfig) -> dict[str, list[str]]:
    """Compute required output files for each round from config."""
    required = {}
    for round_cfg in config.rounds:
        files = []
        pids = config.participant_ids

        if round_cfg.type == RoundType.PARALLEL_STATEMENTS:
            files = [f"{round_cfg.key}/{pid}.md" for pid in pids]
        elif round_cfg.type == RoundType.PAIRED_EXCHANGE:
            files = (
                [f"{round_cfg.key}/{pid}_question.md" for pid in pids]
                + [f"{round_cfg.key}/{pid}_response.md" for pid in pids]
            )
        elif round_cfg.type == RoundType.MODERATOR_SYNTHESIS:
            files = [f"{round_cfg.key}/moderator_synthesis.md"]
        elif round_cfg.type == RoundType.PANEL_QA:
            files = [f"{round_cfg.key}/{pid}.md" for pid in pids]

        required[round_cfg.key] = files
    return required


def check_round_complete(round_key: str, output_dir: Path, config: InquiryConfig) -> list[str]:
    """Return missing file paths for a round. Empty = complete."""
    required = compute_required_files(config)
    missing = []
    for rel_path in required.get(round_key, []):
        if not (output_dir / rel_path).exists():
            missing.append(rel_path)
    return missing


def validate_prerequisites(round_key: str, output_dir: Path, config: InquiryConfig, force: bool = False) -> bool:
    """Check that all prerequisite rounds are complete."""
    prereqs = config.prerequisites_for(round_key)
    all_ok = True

    for prereq in prereqs:
        missing = check_round_complete(prereq, output_dir, config)
        if missing:
            all_ok = False
            console.print(f"\n[bold red]Prerequisite incomplete: {prereq}[/bold red]")
            console.print(f"  Missing {len(missing)} file(s):")
            for f in missing[:6]:
                console.print(f"  [red]✗[/red] {f}")

    if not all_ok:
        if force:
            console.print("\n[yellow]--force set: proceeding despite missing prerequisites.[/yellow]")
            return True
        console.print("\n[red]Aborting. Run prerequisite rounds first, or use --force.[/red]")
        return False

    return True


# ---------------------------------------------------------------------------
# Citation pipeline helpers (delegates to existing modules)
# ---------------------------------------------------------------------------

def _verification_dirs(output_dir: Path) -> dict[str, Path]:
    dirs = {
        "citations": output_dir / "verification" / "citations",
        "verifications": output_dir / "verification" / "verifications",
        "audit": output_dir / "verification" / "audit",
        "moderator_input": output_dir / "verification" / "moderator_input",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


RETRACTED_CLAIMS_FILE = "retracted_claims.json"


def load_retracted_claims(output_dir: Path) -> set[str]:
    path = output_dir / RETRACTED_CLAIMS_FILE
    if not path.exists():
        return set()
    return set(json.loads(path.read_text(encoding="utf-8")))


def update_retracted_claims(output_dir: Path, new_ids: list[str]) -> None:
    if not new_ids:
        return
    existing = load_retracted_claims(output_dir)
    merged = sorted(existing | set(new_ids))
    (output_dir / RETRACTED_CLAIMS_FILE).write_text(
        json.dumps(merged, indent=2), encoding="utf-8"
    )
    console.print(f"  [dim]retracted_claims.json updated: {len(merged)} total[/dim]")


def load_all_verifications(output_dir: Path, through_round_index: int, config: InquiryConfig) -> list[dict]:
    """Load verifications from all rounds up to (but not including) through_round_index."""
    dirs = _verification_dirs(output_dir)
    all_vers = []
    for i, round_cfg in enumerate(config.rounds):
        if i >= through_round_index:
            break
        path = dirs["verifications"] / f"{round_cfg.key}_verifications.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            for v in data:
                v.setdefault("_round_key", round_cfg.key)
            all_vers.extend(data)
    return all_vers


def extract_and_save_citations(
    round_outputs: dict[str, str], round_key: str, round_number: int, output_dir: Path,
) -> Path | None:
    from citation_extractor import extract_all_round_citations, save_citations

    citations = extract_all_round_citations(round_outputs, round_number)
    if not citations:
        console.print("  [dim]No citations found in round outputs.[/dim]")
        return None

    dirs = _verification_dirs(output_dir)
    out_path = dirs["citations"] / f"{round_key}_citations.json"
    save_citations(citations, str(out_path))
    console.print(f"  [green]✓[/green] {len(citations)} citations → {out_path}")
    return out_path


def build_corrections_block(participant_id: str, verifications: list[dict]) -> str:
    """Build citation corrections injection block for a participant."""
    from citation_extractor import _advocate_abbrev

    abbrev = _advocate_abbrev(participant_id)
    flagged = []

    for v in verifications:
        cid = v.get("claim_id", "")
        verdict = v.get("overall_verdict", "")
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
        claim_text = v.get("claim", v.get("claim_text", ""))
        source_text = v.get("source", v.get("source_cited", ""))
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


def run_verification_pipeline(
    client,
    citations_path: Path | None,
    round_key: str,
    round_number: int,
    output_dir: Path,
    force: bool = False,
    skip_pause: bool = False,
    citation_responses: list | None = None,
    _recheck_suffix: str = "",
) -> str:
    """Run the full citation verification pipeline for one round.
    Returns the moderator input string."""
    from citation_verifier import (
        PASS1_SYSTEM_PROMPT, PASS2_SYSTEM_PROMPT, PASS3_SYSTEM_PROMPT,
        build_pass1_prompts, build_pass2_prompt, build_pass3_prompt,
        merge_pass_results, parse_json_response,
    )
    from citation_extractor import load_citations
    from audit_worksheet import generate_audit_worksheet, generate_moderator_input

    if citations_path is None or not citations_path.exists():
        console.print("  [dim]No citations to verify.[/dim]")
        return ""

    dirs = _verification_dirs(output_dir)
    ver_path = dirs["verifications"] / f"{round_key}{_recheck_suffix}_verifications.json"
    worksheet_path = dirs["audit"] / f"{round_key}{_recheck_suffix}_worksheet.md"
    mod_input_path = dirs["moderator_input"] / f"{round_key}{_recheck_suffix}.md"

    citations = load_citations(str(citations_path))
    citation_dicts = [c.to_dict() for c in citations]

    if not should_skip(ver_path, force):
        console.print(f"\n[bold]Citation Verifier — {round_key} (3-pass)[/bold]")
        import anthropic as _anthropic
        from tenacity import retry as _retry, stop_after_attempt as _stop, wait_exponential as _wait

        sonnet_model = resolve_model(ModelChoice.SONNET)

        def _with_retry(fn, label):
            @_retry(stop=_stop(4), wait=_wait(multiplier=2, min=30, max=180), reraise=True)
            def _inner():
                return fn()
            try:
                return _inner()
            except _anthropic.RateLimitError as exc:
                console.print(f"  [red]Rate limit exhausted for {label}: {exc}[/red]")
                return None

        def _repair_json(broken_text: str, label: str) -> str | None:
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
            console.print(f"  [yellow]JSON parse failed for {label} — attempting repair[/yellow]")
            try:
                return call_api(
                    client, sonnet_model,
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

        # Pass 1
        console.print("  [bold]Pass 1[/bold] — training knowledge triage")
        pass1_results: dict[str, dict] = {}
        for i, prompt in enumerate(build_pass1_prompts(citation_dicts, batch_size=5)):
            response = _with_retry(
                lambda p=prompt: call_api(
                    client, sonnet_model,
                    system_prompt=PASS1_SYSTEM_PROMPT,
                    human_message=p,
                    temperature=0.2,
                    max_tokens=2048,
                    label=f"verifier/{round_key}/pass1/batch_{i+1}",
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

        # Pass 2
        console.print("  [bold]Pass 2[/bold] — bibliographic search (all citations)")
        pass2_results: dict[str, dict] = {}
        for idx, c in enumerate(citation_dicts):
            cid = c["claim_id"]
            if idx > 0:
                time.sleep(15)
            response = _with_retry(
                lambda c=c: call_api_with_web_search(
                    client, sonnet_model,
                    system_prompt=PASS2_SYSTEM_PROMPT,
                    human_message=build_pass2_prompt(c),
                    temperature=0.2,
                    max_tokens=1024,
                    max_turns=3,
                    label=f"verifier/{round_key}/pass2/{cid}",
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

        # Pass 3
        suspicious = [
            c for c in citation_dicts
            if (pass1_results.get(c["claim_id"], {}).get("suspicion_level") == "HIGH")
            or (pass2_results.get(c["claim_id"], {}).get("bibliographic_status") in ("UNCONFIRMED", "CONFLICTING"))
        ]
        console.print(f"  [bold]Pass 3[/bold] — deep investigation ({len(suspicious)} suspicious)")
        pass3_results: dict[str, dict] = {}
        for idx, c in enumerate(suspicious):
            cid = c["claim_id"]
            if idx > 0:
                time.sleep(30)
            response = _with_retry(
                lambda c=c: call_api_with_web_search(
                    client, sonnet_model,
                    system_prompt=PASS3_SYSTEM_PROMPT,
                    human_message=build_pass3_prompt(c),
                    temperature=0.2,
                    max_tokens=2048,
                    max_turns=8,
                    label=f"verifier/{round_key}/pass3/{cid}",
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

        # Merge
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

        ver_path.write_text(json.dumps(all_verifications, indent=2), encoding="utf-8")
        console.print(f"  [green]✓[/green] {len(all_verifications)} verifications → {ver_path}")
    else:
        console.print(f"  [dim]skip verification (exists)[/dim]")
        all_verifications = json.loads(ver_path.read_text())

    # Audit worksheet
    if not should_skip(worksheet_path, force):
        review_items, auto_resolved = generate_audit_worksheet(
            citation_dicts, all_verifications, round_key, str(worksheet_path)
        )
        console.print(f"  [green]✓[/green] worksheet → {worksheet_path}")
        needs_review = len(review_items)
        high = sum(1 for x in review_items if x["priority"] == "HIGH")
    else:
        console.print(f"  [dim]skip worksheet (exists)[/dim]")
        needs_review = 0
        high = 0

    # Human review pause
    if needs_review > 0 and not SKIP_HUMAN_REVIEW and not skip_pause:
        console.print(f"\n[bold yellow]⚠  Human audit required.[/bold yellow]")
        console.print(f"   {needs_review} claim(s) need review ({high} HIGH priority)")
        console.print(f"   Worksheet: {worksheet_path}")
        console.print(f"\n   Complete the worksheet, then press Enter to continue...")
        input()
    elif needs_review > 0 and (SKIP_HUMAN_REVIEW or skip_pause):
        console.print(
            f"  [yellow]Human audit skipped. "
            f"{needs_review} claim(s) unreviewed ({high} HIGH priority).[/yellow]"
        )

    # Moderator input
    mod_input = generate_moderator_input(
        citation_dicts, all_verifications, audit_results=None,
        citation_responses=citation_responses if not _recheck_suffix else None,
        round_number=round_key,
    )
    if SKIP_HUMAN_REVIEW and needs_review > 0:
        mod_input = (
            f"**NOTE: Human audit was skipped ({needs_review} claim(s) unreviewed).**\n\n"
            + mod_input
        )

    mod_input_path.write_text(mod_input, encoding="utf-8")
    console.print(f"  [green]✓[/green] moderator input → {mod_input_path}")
    return mod_input


def parse_and_process_responses(
    round_outputs: dict[str, str],
    round_key: str,
    round_number: int,
    output_dir: Path,
    client,
    config: InquiryConfig,
    force: bool = False,
) -> list:
    """Extract citation responses, update retracted claims, re-verify DEFEND responses."""
    from citation_extractor import extract_all_round_responses, save_citation_responses, _advocate_abbrev

    if not round_outputs:
        return []

    all_responses = extract_all_round_responses(round_outputs, round_number)
    if not all_responses:
        return []

    dirs = _verification_dirs(output_dir)
    resp_path = dirs["citations"] / f"{round_key}_responses.json"
    save_citation_responses(all_responses, str(resp_path))
    console.print(f"  [green]✓[/green] {len(all_responses)} citation responses → {resp_path}")

    retracted_ids = [r.original_claim_id for r in all_responses if r.downstream_status == "RETRACTED"]
    if retracted_ids:
        update_retracted_claims(output_dir, retracted_ids)
        console.print(f"  [yellow]Retracted {len(retracted_ids)} claim(s): {retracted_ids}[/yellow]")

    # Re-verify DEFEND responses with new sources
    defend_with_new_source = [
        r for r in all_responses
        if r.advocate_position == "DEFEND" and r.revised_source.strip()
    ]
    if defend_with_new_source:
        console.print(f"  [dim]Re-verifying {len(defend_with_new_source)} DEFEND+new_source response(s)...[/dim]")
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

        recheck_path = dirs["citations"] / f"{round_key}_recheck_citations.json"
        recheck_path.write_text(json.dumps(synthetic_citations, indent=2), encoding="utf-8")

        run_verification_pipeline(
            client, recheck_path, round_key, round_number,
            output_dir=output_dir, force=force, skip_pause=True,
            _recheck_suffix="_recheck",
        )

        recheck_ver_path = dirs["verifications"] / f"{round_key}_recheck_verifications.json"
        if recheck_ver_path.exists():
            recheck_vers = json.loads(recheck_ver_path.read_text(encoding="utf-8"))
            resp_by_recheck_id = {
                f"R{round_number}_{_advocate_abbrev(r.advocate)}_RECHECK_{i + 1:03d}": r
                for i, r in enumerate(defend_with_new_source)
            }
            for rv in recheck_vers:
                if rv.get("overall_verdict") == "FABRICATION_RISK":
                    orig_resp = resp_by_recheck_id.get(rv["claim_id"])
                    if orig_resp:
                        orig_resp.downstream_status = "RETRACTED"
                        update_retracted_claims(output_dir, [orig_resp.original_claim_id])
                        console.print(f"  [red]DEFEND re-verification failed → {orig_resp.original_claim_id} RETRACTED[/red]")
            save_citation_responses(all_responses, str(resp_path))

    return all_responses


# ---------------------------------------------------------------------------
# Digest and summary generation
# ---------------------------------------------------------------------------

ROUND_DIGEST_PROMPT = """You are producing a brief round digest for a structured multi-perspective inquiry.

Below are the outputs from {ROUND_TITLE}. Produce a digest of exactly this structure:

**{ROUND_TITLE} Digest**

*One sentence per participant on their main argument this round:*
{PARTICIPANT_BULLETS}

*Key tension this round:* [One sentence identifying the sharpest point of disagreement.]

*Notable concessions or agreements:* [One sentence, or "None apparent."]

Keep the entire digest under 250 words. Be precise — name specific claims, not general themes."""


FINAL_SUMMARY_PROMPT = """You are producing a final summary of a completed multi-perspective inquiry.

The inquiry: "{INQUIRY_TITLE}"

You will receive the full canonical record and a citation audit summary. Produce a summary in two clearly labelled sections:

---

## Inquiry Summary

In 400–500 words, covering:
- How each participant's position evolved or sharpened across the rounds
- The two or three most significant tensions that ran through the whole inquiry
- What the inquiry clarified that wasn't clear at the start
- What remained genuinely unresolved at the close
- One sentence on what a reader should take away

## Citation Audit Summary

Using the verification data provided, produce a structured summary:
- Total citations across all rounds
- Breakdown by automated verdict
- Any FABRICATION_RISK claims — name them specifically
- Overall citation quality assessment in one sentence

Keep the audit summary factual and specific. Do not soften fabrication risks."""


def generate_round_digest(
    client,
    config: InquiryConfig,
    round_cfg: RoundConfig,
    round_outputs: dict[str, str],
    output_dir: Path,
    force: bool = False,
) -> str:
    out_path = output_dir / round_cfg.key / "round_digest.md"
    if should_skip(out_path, force):
        console.print(f"  [dim]skip round digest (exists)[/dim]")
        return read_output(out_path) or ""

    console.print(f"\n[bold]{round_cfg.title} Digest[/bold]")
    outputs_block = build_participant_outputs_block(round_outputs, config)

    # Build participant bullet template
    bullets = "\n".join(
        f"- **{config.participant_map[pid].display_name}:** ..."
        for pid in config.participant_ids
    )

    prompt = ROUND_DIGEST_PROMPT.format(
        ROUND_TITLE=round_cfg.title,
        PARTICIPANT_BULLETS=bullets,
    )
    human_message = "\n\n---\n\n".join([outputs_block, prompt])

    text = call_api(
        client, resolve_model(ModelChoice.SONNET),
        system_prompt="You are a neutral summarizer for a structured multi-perspective inquiry.",
        human_message=human_message,
        temperature=0.3,
        max_tokens=512,
        label=f"{round_cfg.key}/digest",
    )
    write_output(text, out_path)
    console.print(Panel(text, title=f"{round_cfg.title} Digest", expand=False))
    return text


def _aggregate_verification_stats(output_dir: Path, config: InquiryConfig) -> str:
    """Load all verification JSON files and produce a plain-text audit summary."""
    dirs = _verification_dirs(output_dir)
    ver_base = dirs["verifications"]

    all_verifications = []
    for round_cfg in config.rounds:
        ver_file = ver_base / f"{round_cfg.key}_verifications.json"
        if ver_file.exists():
            try:
                data = json.loads(ver_file.read_text())
                for v in data:
                    v["_round_key"] = round_cfg.key
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
            lines.append(f"  - {v['claim_id']} ({v.get('_round_key', '?')}): {v.get('summary', '')[:120]}")
    else:
        lines.append("FABRICATION_RISK claims: none")

    return "\n".join(lines)


def generate_final_summary(
    client,
    config: InquiryConfig,
    output_dir: Path,
    force: bool = False,
) -> str:
    out_path = output_dir / "synthesis" / "final_summary.md"
    if should_skip(out_path, force):
        console.print(f"  [dim]skip final summary (exists)[/dim]")
        return read_output(out_path) or ""

    console.rule("[bold]Final Summary[/bold]")
    canonical_record = read_canonical_record(output_dir)
    audit_stats = _aggregate_verification_stats(output_dir, config)

    prompt = FINAL_SUMMARY_PROMPT.format(INQUIRY_TITLE=config.inquiry.title)

    human_message = "\n\n---\n\n".join(filter(None, [
        canonical_record,
        f"## Verification Data\n\n{audit_stats}",
        prompt,
    ]))

    text = call_api(
        client, resolve_model(ModelChoice.SONNET),
        system_prompt="You are a neutral summarizer for a structured multi-perspective inquiry.",
        human_message=human_message,
        temperature=0.3,
        max_tokens=1024,
        label="final_summary",
    )
    write_output(text, out_path)
    console.print(Panel(text, title="Final Summary", expand=False))
    return text


def generate_claim_ledger(
    client,
    config: InquiryConfig,
    round_cfg: RoundConfig,
    round_outputs: dict[str, str],
    output_dir: Path,
    previous_ledger_key: str | None = None,
    force: bool = False,
) -> str:
    """Generate or update the claim ledger after a round."""
    out_path = output_dir / "synthesis" / f"claim_ledger_{round_cfg.key}.md"
    if should_skip(out_path, force):
        console.print(f"  [dim]skip claim ledger (exists)[/dim]")
        return read_output(out_path) or ""

    console.print(f"\n[bold]Claim Ledger — {round_cfg.title}[/bold]")
    outputs_block = build_participant_outputs_block(round_outputs, config)

    bracket_vars = {"ROUND_OUTPUTS": outputs_block}
    if previous_ledger_key:
        prev_path = output_dir / "synthesis" / f"claim_ledger_{previous_ledger_key}.md"
        existing = read_output(prev_path) or "[No prior ledger found]"
        bracket_vars["EXISTING_LEDGER"] = existing

    # Use a generic prompt for claim ledger
    prompt = (
        "Extract and track all contested claims from the round outputs below. "
        "For each claim, note: the claim itself, which participant made it, "
        "which participants contest it and why, and whether it is ACTIVE, QUALIFIED, or RETRACTED.\n\n"
        "[ROUND_OUTPUTS]"
    )
    if previous_ledger_key:
        prompt = (
            "Update the existing claim ledger with new information from this round.\n\n"
            "EXISTING LEDGER:\n[EXISTING_LEDGER]\n\n"
            "NEW ROUND OUTPUTS:\n[ROUND_OUTPUTS]"
        )

    human_message = fill_template(prompt, bracket_vars=bracket_vars)

    text = call_api(
        client, resolve_model(ModelChoice.SONNET),
        system_prompt="You are a neutral summarizer for a structured multi-perspective inquiry. Extract and track contested claims faithfully.",
        human_message=human_message,
        temperature=0.25,
        max_tokens=2048,
        label=f"synthesis/claim_ledger_{round_cfg.key}",
    )
    write_output(text, out_path)
    return text


# ---------------------------------------------------------------------------
# Generic round runners (dispatch by round type)
# ---------------------------------------------------------------------------

def _run_parallel_statements(
    client,
    config: InquiryConfig,
    round_cfg: RoundConfig,
    output_dir: Path,
    force: bool = False,
    dry_run: bool = False,
    participant_filter: str | None = None,
) -> dict[str, str]:
    """Run a round where each participant speaks independently."""
    shared_context = build_shared_context(config)
    canonical_record = read_canonical_record(output_dir)
    model = resolve_model(round_cfg.model)
    temperature = config.settings.temperature.participants

    # Determine participant order
    pids = config.participant_ids
    if round_cfg.reversed_speaking_order:
        pids = list(reversed(pids))
    if participant_filter:
        pids = [participant_filter]

    # Load prior verifications for corrections
    round_index = config.round_keys.index(round_cfg.key)
    prior_verifications = load_all_verifications(output_dir, round_index, config) if round_index > 0 else []

    # Load prior round outputs for context injection
    prior_round_keys = config.prerequisites_for(round_cfg.key)
    prior_outputs_block = ""
    if prior_round_keys:
        # Read outputs from the most recent prior round for context
        for prev_key in reversed(prior_round_keys):
            prev_dir = output_dir / prev_key
            if prev_dir.exists():
                prev_outputs = {}
                for pid in config.participant_ids:
                    text = read_output(prev_dir / f"{pid}.md")
                    if text:
                        prev_outputs[pid] = text
                if prev_outputs:
                    prior_outputs_block = build_participant_outputs_block(prev_outputs, config)
                    break

    # Build required texts block if this round has them
    required_texts_block = ""
    if round_cfg.required_texts:
        required_texts_block = build_required_texts_block(round_cfg)

    outputs = {}

    for pid in pids:
        p = config.participant_map[pid]
        out_path = output_dir / round_cfg.key / f"{pid}.md"

        if should_skip(out_path, force):
            console.print(f"  [dim]skip {pid} (exists)[/dim]")
            outputs[pid] = read_output(out_path)
            continue

        corrections_block = build_corrections_block(pid, prior_verifications) if prior_verifications else ""

        # Build compressed context if needed
        context_block = canonical_record
        if round_cfg.use_compressed_context:
            from context_packager import build_compressed_context
            retracted_claims = load_retracted_claims(output_dir)
            context_block = build_compressed_context(
                pid, config, output_dir, client, retracted_claims=retracted_claims,
            )

        human_message = "\n\n---\n\n".join(filter(None, [
            shared_context,
            fill_template(
                round_cfg.prompt_template,
                curly_vars={
                    "PARTICIPANT_DISPLAY_NAME": p.display_name,
                    "PARTICIPANT_ROLE": p.role,
                    # Legacy aliases
                    "ADVOCATE_DISPLAY_NAME": p.display_name,
                    "DISCIPLINARY_LEAD": p.role,
                },
                bracket_vars={
                    "CANONICAL_RECORD_TO_DATE": context_block,
                    "COMPRESSED_CANONICAL_RECORD": context_block,
                    "COMPILED_POSITION_PAPERS": prior_outputs_block,
                    "REQUIRED_TEXTS": required_texts_block,
                    "CITATION_CORRECTIONS": corrections_block,
                },
            ),
        ]))

        console.print(f"\n[bold]{p.display_name}[/bold]")

        if dry_run:
            console.print(Panel(human_message[:800] + "\n...[truncated]", title="DRY RUN", expand=False))
            continue

        text = call_api(
            client, model,
            system_prompt=p.system_prompt,
            human_message=human_message,
            temperature=temperature,
            max_tokens=4096,
            label=f"{round_cfg.key}/{pid}",
        )
        write_output(text, out_path)
        outputs[pid] = text

    return outputs


def _run_paired_exchange(
    client,
    config: InquiryConfig,
    round_cfg: RoundConfig,
    output_dir: Path,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[dict[str, str], dict[str, str]]:
    """Run a paired exchange round (questions then responses)."""
    shared_context = build_shared_context(config)
    canonical_record = read_canonical_record(output_dir)
    model = resolve_model(round_cfg.model)
    temperature = config.settings.temperature.participants

    # Build pairing lookups
    pairing_by_questioner = {p.questioner: p for p in round_cfg.pairings}
    pairing_by_target = {p.target: p for p in round_cfg.pairings}

    question_outputs = {}
    response_outputs = {}

    # Phase A: Questions
    console.print("\n[underline]Phase A — Questions[/underline]")

    # The prompt_template is for the question phase
    q_template = round_cfg.prompt_template

    for pid in config.participant_ids:
        if pid not in pairing_by_questioner:
            continue
        pairing = pairing_by_questioner[pid]
        target_id = pairing.target
        questioner = config.participant_map[pid]
        target = config.participant_map[target_id]

        out_path = output_dir / round_cfg.key / f"{pid}_question.md"

        if should_skip(out_path, force):
            console.print(f"  [dim]skip {pid}_question (exists)[/dim]")
            question_outputs[pid] = read_output(out_path)
            continue

        human_message = "\n\n---\n\n".join(filter(None, [
            shared_context,
            canonical_record,
            fill_template(q_template, curly_vars={
                "PARTICIPANT_DISPLAY_NAME": questioner.display_name,
                "PARTICIPANT_ROLE": questioner.role,
                "ADVOCATE_DISPLAY_NAME": questioner.display_name,
                "DISCIPLINARY_LEAD": questioner.role,
                "TARGET_ADVOCATE": target.display_name,
                "TARGET_PARTICIPANT": target.display_name,
                "TENSION_DESCRIPTION": pairing.tension,
            }),
        ]))

        console.print(f"\n[bold]{questioner.display_name} → {target.display_name}[/bold]")

        if dry_run:
            console.print(Panel(human_message[:600] + "\n...[truncated]", title="DRY RUN", expand=False))
            continue

        text = call_api(
            client, model,
            system_prompt=questioner.system_prompt,
            human_message=human_message,
            temperature=temperature,
            label=f"{round_cfg.key}/{pid}_question",
        )
        write_output(text, out_path)
        question_outputs[pid] = text

    if dry_run:
        return {}, {}

    # Phase B: Responses
    console.print("\n[underline]Phase B — Responses[/underline]")

    # Load prior verifications for corrections
    round_index = config.round_keys.index(round_cfg.key)
    prior_verifications = load_all_verifications(output_dir, round_index, config) if round_index > 0 else []

    # Build context block with all questions
    all_questions_block = "\n\n---\n\n".join(
        f"Question from {config.participant_map[qid].display_name} to "
        f"{config.participant_map[pairing_by_questioner[qid].target].display_name}:\n\n{text}"
        for qid, text in question_outputs.items()
    )

    # Use the response_prompt from the round config, or a generic one
    r_template = round_cfg.synthesis_prompt or round_cfg.prompt_template  # reuse field for response template

    for pid in config.participant_ids:
        if pid not in pairing_by_target:
            continue
        pairing = pairing_by_target[pid]
        questioner_id = pairing.questioner
        target = config.participant_map[pid]
        questioner = config.participant_map[questioner_id]
        question_text = question_outputs.get(questioner_id, "")

        out_path = output_dir / round_cfg.key / f"{pid}_response.md"

        if should_skip(out_path, force):
            console.print(f"  [dim]skip {pid}_response (exists)[/dim]")
            response_outputs[pid] = read_output(out_path)
            continue

        corrections_block = build_corrections_block(pid, prior_verifications)

        human_message = "\n\n---\n\n".join(filter(None, [
            shared_context,
            canonical_record,
            f"[All {round_cfg.title} Questions for Context]\n\n{all_questions_block}",
            fill_template(r_template, curly_vars={
                "QUESTIONING_ADVOCATE": questioner.display_name,
                "QUESTIONING_PARTICIPANT": questioner.display_name,
            }, bracket_vars={
                "QUESTION_TEXT": question_text,
                "CITATION_CORRECTIONS": corrections_block,
            }),
        ]))

        console.print(f"\n[bold]{target.display_name} (responding)[/bold]")

        text = call_api(
            client, model,
            system_prompt=target.system_prompt,
            human_message=human_message,
            temperature=temperature,
            label=f"{round_cfg.key}/{pid}_response",
        )
        write_output(text, out_path)
        response_outputs[pid] = text

    return question_outputs, response_outputs


def _run_moderator_synthesis(
    client,
    config: InquiryConfig,
    round_cfg: RoundConfig,
    output_dir: Path,
    force: bool = False,
    dry_run: bool = False,
) -> None:
    """Run moderator synthesis + participant responses."""
    shared_context = build_shared_context(config)
    canonical_record = read_canonical_record(output_dir)

    # Moderator synthesis
    synth_path = output_dir / round_cfg.key / "moderator_synthesis.md"
    synthesis_text = read_output(synth_path)

    if not synthesis_text or force:
        console.print("\n[bold]Moderator — Synthesis[/bold]")

        human_message = "\n\n---\n\n".join(filter(None, [
            shared_context,
            canonical_record,
            round_cfg.synthesis_prompt or round_cfg.prompt_template,
        ]))

        if not dry_run:
            synthesis_text = call_api(
                client, resolve_model(round_cfg.model),
                system_prompt=config.moderator.system_prompt,
                human_message=human_message,
                temperature=config.settings.temperature.moderator,
                label=f"{round_cfg.key}/moderator",
            )
            write_output(synthesis_text, synth_path)
        else:
            console.print(Panel(human_message[:600] + "\n...[truncated]", title="DRY RUN", expand=False))
            return

    # Participant responses
    console.print("\n[underline]Participant Synthesis Responses[/underline]")
    response_template = round_cfg.response_prompt or round_cfg.prompt_template

    for pid in config.participant_ids:
        p = config.participant_map[pid]
        out_path = output_dir / round_cfg.key / f"{pid}_response.md"

        if should_skip(out_path, force):
            console.print(f"  [dim]skip {pid}_response (exists)[/dim]")
            continue

        console.print(f"\n[bold]{p.display_name}[/bold]")

        human_message = "\n\n---\n\n".join(filter(None, [
            shared_context,
            fill_template(response_template, curly_vars={
                "PARTICIPANT_DISPLAY_NAME": p.display_name,
                "PARTICIPANT_ROLE": p.role,
                "ADVOCATE_DISPLAY_NAME": p.display_name,
                "DISCIPLINARY_LEAD": p.role,
            }, bracket_vars={
                "MODERATOR_SYNTHESIS_TEXT": synthesis_text,
            }),
        ]))

        text = call_api(
            client, resolve_model(ModelChoice.SONNET),
            system_prompt=p.system_prompt,
            human_message=human_message,
            temperature=config.settings.temperature.participants,
            label=f"{round_cfg.key}/{pid}_response",
        )
        write_output(text, out_path)


def _run_moderation(
    client,
    config: InquiryConfig,
    round_cfg: RoundConfig,
    round_outputs: dict[str, str],
    output_dir: Path,
    force: bool = False,
    verification_input: str = "",
) -> str | None:
    """Run moderator fact-check for a round."""
    out_path = output_dir / round_cfg.key / "moderation_report.md"

    if should_skip(out_path, force):
        console.print(f"  [dim]skip moderation report (exists)[/dim]")
        return read_output(out_path)

    console.print(f"\n[bold]Moderator — {round_cfg.title} Fact-Check[/bold]")
    shared_context = build_shared_context(config)
    outputs_block = build_participant_outputs_block(round_outputs, config)

    verification_block = (
        f"\n\n## Automated Verification Results\n\n{verification_input}"
        if verification_input
        else ""
    )

    fact_check_prompt = config.moderator.fact_check_prompt or (
        "Review the round outputs below for factual accuracy, disciplinary boundary violations, "
        "and quality of engagement. Produce a moderation report.\n\n[ROUND_OUTPUTS]"
    )

    human_message = "\n\n---\n\n".join(filter(None, [
        shared_context,
        fill_template(
            fact_check_prompt,
            curly_vars={"ROUND_NUMBER": round_cfg.key, "ROUND_TITLE": round_cfg.title},
            bracket_vars={"ROUND_OUTPUTS": outputs_block + verification_block},
        ),
    ]))

    text = call_api(
        client, resolve_model(ModelChoice.SONNET),
        system_prompt=config.moderator.system_prompt,
        human_message=human_message,
        temperature=config.settings.temperature.moderator,
        label=f"{round_cfg.key}/moderation",
    )
    write_output(text, out_path)
    return text


# ---------------------------------------------------------------------------
# Compile canonical record
# ---------------------------------------------------------------------------

def compile_canonical_record(output_dir: Path, config: InquiryConfig):
    from document_compiler import compile_full_record
    compile_full_record(output_dir, config)
    console.print(f"  [green]✓[/green] canonical_record.md updated")


# ---------------------------------------------------------------------------
# Main round dispatcher
# ---------------------------------------------------------------------------

def run_round(
    client,
    config: InquiryConfig,
    round_cfg: RoundConfig,
    output_dir: Path,
    force: bool = False,
    dry_run: bool = False,
    participant_filter: str | None = None,
) -> dict[str, str]:
    """
    Run a single round, dispatching to the appropriate handler based on round type.
    Returns the round outputs dict.
    """
    console.rule(f"[bold]{round_cfg.title}[/bold]")

    if not validate_prerequisites(round_cfg.key, output_dir, config, force):
        return {}

    # Ensure output directory exists
    (output_dir / round_cfg.key).mkdir(parents=True, exist_ok=True)

    round_index = config.round_keys.index(round_cfg.key)
    # Round number for citation IDs (1-based index, skipping synthesis-type rounds)
    round_number = sum(
        1 for r in config.rounds[:round_index + 1]
        if r.type != RoundType.MODERATOR_SYNTHESIS
    )

    # Dispatch by round type
    if round_cfg.type == RoundType.PARALLEL_STATEMENTS:
        outputs = _run_parallel_statements(client, config, round_cfg, output_dir, force, dry_run, participant_filter)

    elif round_cfg.type == RoundType.PAIRED_EXCHANGE:
        q_outputs, r_outputs = _run_paired_exchange(client, config, round_cfg, output_dir, force, dry_run)
        outputs = {**q_outputs, **r_outputs}

    elif round_cfg.type == RoundType.MODERATOR_SYNTHESIS:
        _run_moderator_synthesis(client, config, round_cfg, output_dir, force, dry_run)
        return {}

    elif round_cfg.type == RoundType.PANEL_QA:
        outputs = _run_parallel_statements(client, config, round_cfg, output_dir, force, dry_run, participant_filter)

    else:
        console.print(f"[red]Unknown round type: {round_cfg.type}[/red]")
        return {}

    if dry_run or not outputs:
        return outputs

    # Post-round pipeline: citations, verification, moderation, digest
    if round_cfg.verify_citations and config.settings.citation_protocol:
        console.print("\n[bold]Extracting citations...[/bold]")
        citations_path = extract_and_save_citations(outputs, round_cfg.key, round_number, output_dir)

        console.print("\n[bold]Parsing citation responses...[/bold]")
        citation_responses = parse_and_process_responses(
            outputs, round_cfg.key, round_number, output_dir,
            client=client, config=config, force=force,
        )

        verification_input = run_verification_pipeline(
            client, citations_path, round_cfg.key, round_number,
            output_dir=output_dir, force=force,
            skip_pause=bool(participant_filter),
            citation_responses=citation_responses,
        )
    else:
        verification_input = ""

    if round_cfg.run_moderation and not participant_filter:
        _run_moderation(client, config, round_cfg, outputs, output_dir, force, verification_input)

    if round_cfg.generate_claim_ledger and not participant_filter:
        # Find previous ledger key
        prev_ledger_key = None
        for prev_cfg in config.rounds:
            if prev_cfg.key == round_cfg.key:
                break
            if prev_cfg.generate_claim_ledger:
                prev_ledger_key = prev_cfg.key
        generate_claim_ledger(client, config, round_cfg, outputs, output_dir, prev_ledger_key, force)

    if round_cfg.generate_digest and not participant_filter:
        generate_round_digest(client, config, round_cfg, outputs, output_dir, force)

    return outputs


def run_inquiry(
    config: InquiryConfig,
    output_dir: Path,
    force: bool = False,
    dry_run: bool = False,
    round_filter: str | None = None,
    participant_filter: str | None = None,
) -> None:
    """
    Run an entire inquiry (or a single round) from a config.

    Args:
        config: The inquiry configuration
        output_dir: Where to write outputs
        force: Re-run even if outputs exist
        dry_run: Print prompts without calling API
        round_filter: If set, only run this round key
        participant_filter: If set, only run this participant
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    if not dry_run:
        init_audit_log(output_dir)
    client = None if dry_run else make_api_client()

    # Save config to output dir for reproducibility
    config_path = output_dir / "inquiry_config.json"
    if not config_path.exists():
        from inquiry_schema import save_inquiry_config
        save_inquiry_config(config, config_path)

    rounds_to_run = config.rounds
    if round_filter:
        round_cfg = config.get_round(round_filter)
        if not round_cfg:
            console.print(f"[red]Unknown round: {round_filter}[/red]")
            console.print(f"Available rounds: {', '.join(config.round_keys)}")
            return
        rounds_to_run = [round_cfg]

    for round_cfg in rounds_to_run:
        run_round(client, config, round_cfg, output_dir, force, dry_run, participant_filter)
        if not dry_run and round_cfg.type != RoundType.MODERATOR_SYNTHESIS:
            compile_canonical_record(output_dir, config)

    # Generate final summary after the last round (if running all)
    if not round_filter and not dry_run:
        generate_final_summary(client, config, output_dir, force)

    console.print("\n[bold green]Done.[/bold green]")
