"""
FastAPI server exposing the Layer 1 SafetyAgent as a streaming chat API.

Warm-loads SafetyAgent on startup (~3 min), then serves:
    GET  /manuals               -> {"manuals": [...], "current": "..."}
    POST /switch  {"name": ...} -> {"ok": True, "current": "..."}
    POST /chat    {"query": ...} -> SSE stream of {"token": "..."} events,
                                    terminated by {"done": True}.
    POST /upload  (multipart pdf) -> SSE stream of
                                    {"step": n, "total": 3, "name": "..."} events,
                                    terminated by {"done": True, "manual": "..."}.

Run from project root:
    uvicorn backend.api.server:app --host 0.0.0.0 --port 8001
"""

import asyncio
import json
import os
import re
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_PROJECT_ROOT / ".env")
os.environ.setdefault("LANCE_LOG", "ERROR")

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agents.safety_agent import SafetyAgent
from backend.ingestion import docling_parser, vision_captioner
from backend.storage import lancedb_client

_DB_DIR = _PROJECT_ROOT / "data" / "lancedb"
_DATA_DIR = _PROJECT_ROOT / "data"
_SENTINEL = object()
_chat_lock = asyncio.Lock()
_upload_lock = asyncio.Lock()
state: dict = {"agent": None, "current": None}


def _list_manuals() -> list[str]:
    if not _DB_DIR.is_dir():
        return []
    return sorted(t.name[:-6] for t in _DB_DIR.iterdir() if t.is_dir() and t.name.endswith(".lance"))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    manuals = _list_manuals()
    if not manuals:
        raise RuntimeError(f"No .lance tables found in {_DB_DIR}.")
    state["current"] = manuals[0]
    state["agent"] = SafetyAgent.open(_DB_DIR / f"{manuals[0]}.lance")
    try:
        yield
    finally:
        if state["agent"]:
            state["agent"].close()


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


class SwitchReq(BaseModel):
    name: str


class ChatReq(BaseModel):
    query: str
    k: int = 50
    top_n: int = 5


@app.get("/manuals")
def manuals():
    return {"manuals": _list_manuals(), "current": state["current"]}


@app.post("/switch")
def switch(req: SwitchReq):
    if req.name not in _list_manuals():
        raise HTTPException(404, f"Manual '{req.name}' not found")
    state["agent"].switch_table(_DB_DIR / f"{req.name}.lance")
    state["current"] = req.name
    return {"ok": True, "current": req.name}


@app.post("/chat")
async def chat(req: ChatReq):
    agent: SafetyAgent = state["agent"]
    loop = asyncio.get_event_loop()

    async def stream():
        async with _chat_lock:
            chunks = await loop.run_in_executor(None, agent.retrieve, req.query, req.k, req.top_n)
            yield f"data: {json.dumps({'phase': 'retrieved', 'count': len(chunks)})}\n\n"

            gen = agent.generate_stream(req.query, chunks)
            while True:
                token = await loop.run_in_executor(None, next, gen, _SENTINEL)
                if token is _SENTINEL:
                    break
                yield f"data: {json.dumps({'token': token})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# /upload — three-step ingest pipeline with SSE progress
#   1. docling_parser.process_pdf       -> manual.md + image_manifest.json
#   2. vision_captioner                 -> fill image descriptions
#   3. lancedb_client.ingest            -> chunk + embed + index
# ---------------------------------------------------------------------------

_SAFE_STEM_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_stem(filename: str) -> str:
    stem = Path(filename).stem
    stem = _SAFE_STEM_RE.sub("_", stem).strip("._-")
    return stem or "manual"


def _run_docling(pdf_path: Path, out_dir: Path) -> None:
    docling_parser.process_pdf(pdf_path, out_dir)


def _run_vision(out_dir: Path) -> None:
    manifest = vision_captioner.generate_image_descriptions(out_dir)
    vision_captioner.embed_descriptions_in_markdown(manifest, out_dir)


def _run_lancedb(out_dir: Path) -> str:
    lancedb_client.ingest(out_dir, embedder=state["agent"].embedder)
    return f"{out_dir.name}_lancedb"


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    filename = file.filename or "manual.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only .pdf files are accepted")

    stem = _safe_stem(filename)
    pdf_path = _DATA_DIR / f"{stem}.pdf"
    out_dir = _DATA_DIR / stem

    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    with pdf_path.open("wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)

    loop = asyncio.get_event_loop()

    async def stream():
        if _upload_lock.locked():
            yield f"data: {json.dumps({'error': 'Another upload is in progress'})}\n\n"
            return

        async with _upload_lock:
            steps = [
                ("Parsing PDF (Docling)", lambda: _run_docling(pdf_path, out_dir)),
                ("Captioning images (Vision LM)", lambda: _run_vision(out_dir)),
                ("Embedding & indexing chunks (LanceDB)", lambda: _run_lancedb(out_dir)),
            ]
            new_manual = None
            for i, (name, fn) in enumerate(steps, start=1):
                yield f"data: {json.dumps({'step': i, 'total': 3, 'name': name, 'phase': 'start'})}\n\n"
                try:
                    # serialize GPU-heavy step 3 against chat to prevent embedder contention
                    if i == 3:
                        async with _chat_lock:
                            result = await loop.run_in_executor(None, fn)
                    else:
                        result = await loop.run_in_executor(None, fn)
                except Exception as e:
                    yield f"data: {json.dumps({'step': i, 'total': 3, 'name': name, 'error': str(e)})}\n\n"
                    return
                if i == 3:
                    new_manual = result
                yield f"data: {json.dumps({'step': i, 'total': 3, 'name': name, 'phase': 'done'})}\n\n"

            if new_manual:
                state["agent"].switch_table(_DB_DIR / f"{new_manual}.lance")
                state["current"] = new_manual
                yield f"data: {json.dumps({'done': True, 'manual': new_manual})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
