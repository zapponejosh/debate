#!/usr/bin/env python3
"""
Inquiry Engine HTTP API
Thin wrapper around engine.py for the Next.js web app to call.

Usage:
    python scripts/server.py
    python scripts/server.py --port 8080

Endpoints:
    POST /inquiries              - Create + start an inquiry from config JSON
    GET  /inquiries              - List all inquiries
    GET  /inquiries/{id}         - Get inquiry status and metadata
    GET  /inquiries/{id}/outputs/{path} - Serve an output file
    GET  /inquiries/{id}/events  - SSE stream of progress events
    POST /inquiries/{id}/resume  - Resume a failed/stopped inquiry
"""

import asyncio
import json
import uuid
import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, PlainTextResponse
from pydantic import BaseModel

import sys
sys.path.insert(0, str(Path(__file__).parent))

from inquiry_schema import InquiryConfig, load_inquiry_config, save_inquiry_config

app = FastAPI(title="Inquiry Engine API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# State management (in-memory for now, Supabase later)
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

# In-memory tracking of running inquiries
_inquiries: dict[str, dict] = {}
# SSE event queues per inquiry
_event_queues: dict[str, list[asyncio.Queue]] = {}


def _load_persisted_inquiries():
    """Reload inquiry metadata from disk on startup so restarts don't lose history."""
    for meta_path in DATA_DIR.glob("*/meta.json"):
        try:
            meta = json.loads(meta_path.read_text())
            inquiry_id = meta.get("id")
            if not inquiry_id:
                continue
            # Any inquiry that was 'running' when the server died is now 'failed'
            if meta.get("status") == "running":
                meta["status"] = "failed"
                meta["error"] = "Engine restarted while inquiry was running"
                meta_path.write_text(json.dumps(meta, indent=2))
            _inquiries[inquiry_id] = meta
        except Exception:
            pass


_load_persisted_inquiries()


class InquiryStatus(BaseModel):
    id: str
    title: str
    status: str  # "planning" | "running" | "completed" | "failed" | "waiting_for_input"
    current_round: Optional[str] = None
    current_participant: Optional[str] = None
    created_at: str
    output_dir: str
    error: Optional[str] = None


def _load_all_inquiries() -> dict[str, dict]:
    """Load inquiry metadata from disk on startup."""
    inquiries = {}
    if not DATA_DIR.exists():
        return inquiries
    for inquiry_dir in DATA_DIR.iterdir():
        if not inquiry_dir.is_dir():
            continue
        meta_path = inquiry_dir / "meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
            inquiries[meta["id"]] = meta
    return inquiries


def _save_meta(inquiry_id: str):
    """Persist inquiry metadata to disk."""
    if inquiry_id not in _inquiries:
        return
    meta = _inquiries[inquiry_id]
    meta_path = Path(meta["output_dir"]) / "meta.json"
    meta_path.write_text(json.dumps(meta, indent=2))


def _emit_event(inquiry_id: str, event_type: str, data: dict):
    """Push an SSE event to all listeners for this inquiry."""
    if inquiry_id not in _event_queues:
        return
    event_data = json.dumps({"type": event_type, **data})
    for queue in _event_queues[inquiry_id]:
        queue.put_nowait(event_data)


# ---------------------------------------------------------------------------
# Background inquiry runner
# ---------------------------------------------------------------------------

def _run_inquiry_background(inquiry_id: str, config: InquiryConfig, output_dir: Path, force: bool = False):
    """Run an inquiry in a background thread. Updates status and emits SSE events."""
    import engine

    meta = _inquiries[inquiry_id]
    meta["status"] = "running"
    _save_meta(inquiry_id)
    _emit_event(inquiry_id, "started", {"title": config.inquiry.title})

    try:
        # Monkey-patch engine's console to emit SSE events
        original_print = engine.console.print

        def _intercepting_print(*args, **kwargs):
            original_print(*args, **kwargs)
            # Extract useful info from print calls
            text = str(args[0]) if args else ""
            if "bold" in text and any(p.display_name in text for p in config.participants):
                for p in config.participants:
                    if p.display_name in text:
                        meta["current_participant"] = p.id
                        _emit_event(inquiry_id, "participant_started", {
                            "round": meta.get("current_round", ""),
                            "participant": p.id,
                            "display_name": p.display_name,
                        })
                        break
            if "✓" in text and "wrote" in text:
                _emit_event(inquiry_id, "file_written", {"text": text})

        engine.console.print = _intercepting_print

        # Patch run_round to track current round
        original_run_round = engine.run_round

        def _tracking_run_round(client, cfg, round_cfg, *args, **kwargs):
            meta["current_round"] = round_cfg.key
            _save_meta(inquiry_id)
            _emit_event(inquiry_id, "round_started", {
                "round": round_cfg.key,
                "title": round_cfg.title,
            })
            result = original_run_round(client, cfg, round_cfg, *args, **kwargs)
            _emit_event(inquiry_id, "round_completed", {
                "round": round_cfg.key,
                "title": round_cfg.title,
            })
            return result

        engine.run_round = _tracking_run_round

        engine.run_inquiry(
            config=config,
            output_dir=output_dir,
            force=force,
        )

        meta["status"] = "completed"
        meta["current_round"] = None
        meta["current_participant"] = None
        _save_meta(inquiry_id)
        _emit_event(inquiry_id, "completed", {})

        # Restore patches
        engine.console.print = original_print
        engine.run_round = original_run_round

    except Exception as e:
        meta["status"] = "failed"
        meta["error"] = str(e)
        _save_meta(inquiry_id)
        _emit_event(inquiry_id, "error", {"error": str(e)})
        raise


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

class CreateInquiryRequest(BaseModel):
    config: dict  # Raw inquiry config JSON
    force: bool = False


@app.on_event("startup")
async def startup():
    global _inquiries
    _inquiries = _load_all_inquiries()


@app.post("/inquiries")
async def create_inquiry(request: CreateInquiryRequest, background_tasks: BackgroundTasks):
    """Create and start a new inquiry."""
    try:
        config = InquiryConfig(**request.config)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid config: {e}")

    inquiry_id = str(uuid.uuid4())[:8]
    output_dir = DATA_DIR / inquiry_id

    _inquiries[inquiry_id] = {
        "id": inquiry_id,
        "title": config.inquiry.title,
        "status": "running",
        "current_round": None,
        "current_participant": None,
        "created_at": datetime.datetime.now().isoformat(),
        "output_dir": str(output_dir),
    }

    # Save config
    output_dir.mkdir(parents=True, exist_ok=True)
    save_inquiry_config(config, output_dir / "inquiry_config.json")
    _save_meta(inquiry_id)

    # Start in background
    background_tasks.add_task(
        _run_inquiry_background, inquiry_id, config, output_dir, request.force
    )

    return {"id": inquiry_id, "status": "running", "output_dir": str(output_dir)}


@app.get("/inquiries")
async def list_inquiries():
    """List all inquiries."""
    return sorted(_inquiries.values(), key=lambda x: x.get("created_at", ""), reverse=True)


@app.get("/inquiries/{inquiry_id}")
async def get_inquiry(inquiry_id: str):
    """Get inquiry status and metadata."""
    if inquiry_id not in _inquiries:
        raise HTTPException(status_code=404, detail="Inquiry not found")
    return _inquiries[inquiry_id]


@app.get("/inquiries/{inquiry_id}/outputs/{path:path}")
async def get_output(inquiry_id: str, path: str):
    """Serve an output file."""
    if inquiry_id not in _inquiries:
        raise HTTPException(status_code=404, detail="Inquiry not found")

    output_dir = Path(_inquiries[inquiry_id]["output_dir"])
    file_path = output_dir / path

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    if not file_path.is_relative_to(output_dir):
        raise HTTPException(status_code=403, detail="Access denied")

    if file_path.suffix == ".json":
        return FileResponse(file_path, media_type="application/json")
    elif file_path.suffix == ".md":
        return PlainTextResponse(file_path.read_text(encoding="utf-8"))
    else:
        return FileResponse(file_path)


@app.get("/inquiries/{inquiry_id}/files")
async def list_output_files(inquiry_id: str):
    """List all output files for an inquiry."""
    if inquiry_id not in _inquiries:
        raise HTTPException(status_code=404, detail="Inquiry not found")

    output_dir = Path(_inquiries[inquiry_id]["output_dir"])
    if not output_dir.exists():
        return []

    files = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and path.name != "meta.json":
            files.append({
                "path": str(path.relative_to(output_dir)),
                "size": path.stat().st_size,
                "modified": datetime.datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
            })
    return files


@app.get("/inquiries/{inquiry_id}/events")
async def events(inquiry_id: str):
    """SSE stream of progress events for an inquiry."""
    if inquiry_id not in _inquiries:
        raise HTTPException(status_code=404, detail="Inquiry not found")

    queue: asyncio.Queue = asyncio.Queue()
    if inquiry_id not in _event_queues:
        _event_queues[inquiry_id] = []
    _event_queues[inquiry_id].append(queue)

    async def event_generator():
        try:
            # Send current status as first event
            yield f"data: {json.dumps(_inquiries[inquiry_id])}\n\n"

            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield f": keepalive\n\n"

                # Check if inquiry is done
                status = _inquiries.get(inquiry_id, {}).get("status", "")
                if status in ("completed", "failed"):
                    yield f"data: {json.dumps({'type': 'done', 'status': status})}\n\n"
                    break
        finally:
            if inquiry_id in _event_queues:
                _event_queues[inquiry_id].remove(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/inquiries/{inquiry_id}/resume")
async def resume_inquiry(inquiry_id: str, background_tasks: BackgroundTasks):
    """Resume a failed or stopped inquiry."""
    if inquiry_id not in _inquiries:
        raise HTTPException(status_code=404, detail="Inquiry not found")

    meta = _inquiries[inquiry_id]
    if meta["status"] == "running":
        raise HTTPException(status_code=409, detail="Inquiry is already running")

    output_dir = Path(meta["output_dir"])
    config = load_inquiry_config(output_dir / "inquiry_config.json")

    meta["status"] = "running"
    meta["error"] = None
    _save_meta(inquiry_id)

    background_tasks.add_task(
        _run_inquiry_background, inquiry_id, config, output_dir
    )

    return {"id": inquiry_id, "status": "running"}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Inquiry Engine API Server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port)
