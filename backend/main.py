# backend/main.py  — ASYNC jobs version (implements POST /run and GET /run/{id})

import os, re, uuid, threading, time
from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.models import RunRequest
from backend.process import run_pipeline

# ------------------ paths & helpers ------------------

# Repo root for the BubblePanel scripts (smoke_test.py lives here)
BP_ROOT = Path(os.environ.get("BP_REPO_ROOT", str(Path.cwd() / "BubblePanel-main"))).resolve()

# Where uploads are stored on the server
UPLOAD_DIR = Path(os.environ.get("BP_UPLOAD_DIR", str(Path.cwd() / "uploads"))).resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")

def _safe_name(name: str) -> str:
    s = SAFE_RE.sub("_", name or "")
    return s or "upload"

def _map_ui_upload_path(p: str) -> Path:
    """
    Convert a UI path to a server filesystem path.
    - If UI sent '/app/uploads/<file>', map to UPLOAD_DIR/<file>
    - If absolute path, keep as-is
    - If relative, resolve relative to BP_ROOT
    """
    if not p:
        return Path("")
    p = p.strip()
    if p.startswith("/app/uploads/"):
        return (UPLOAD_DIR / Path(p).name).resolve()
    path = Path(p)
    if path.is_absolute():
        return path.resolve()
    # treat as repo-relative
    return (BP_ROOT / p.lstrip("./")).resolve()

def _normalize_paths(req: RunRequest) -> RunRequest:
    """Validate/normalize input/out/jsonl for the worker."""
    inp = _map_ui_upload_path(req.input)
    if not inp.exists():
        raise HTTPException(400, f"Input not found: {inp}")

    # Output directory (allow relative to BP_ROOT)
    out_dir = req.out or "./data/outputs/job"
    out_path = Path(out_dir)
    if not out_path.is_absolute():
        out_path = (BP_ROOT / out_path.as_posix().lstrip("./")).resolve()
    out_path.mkdir(parents=True, exist_ok=True)

    # jsonl (place inside out dir if relative)
    jsonl = req.jsonl or "panels.jsonl"
    jsonl_path = Path(jsonl)
    if not jsonl_path.is_absolute():
        jsonl_path = (out_path / jsonl_path.name).resolve()

    # If no real LLM host+model, disable summarizer so we don’t hit localhost:11434
    if not (req.engine == "llm" and req.host and req.ollama_text):
        req.page_summarize = False  # keep OCR-only unless an LLM is explicitly configured

    req.input = str(inp)
    req.out   = str(out_path)
    req.jsonl = str(jsonl_path)
    return req

# ------------------ FastAPI app ------------------

app = FastAPI(title="BubblePanel API", version="2.0-async")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # for prod, restrict to your Netlify origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"ok": True, "service": "bubblepanel-backend-async"}

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/status")
def status():
    script = os.environ.get("BP_SCRIPT", "smoke_test.py")
    return {
        "ok": True,
        "bp_root": str(BP_ROOT),
        "upload_dir": str(UPLOAD_DIR),
        "script": script,
        "script_exists": (BP_ROOT / script).is_file(),
    }

@app.get("/presets")
def presets():
    return {
        "encoder_paragraph": {
            "page_style": "paragraph",
            "engine": "encoder",
            "embed_model": "sentence-transformers/all-mpnet-base-v2",
            "mlm_refiner": False,
        },
        "llm_paragraph_qwen": {
            "page_style": "paragraph",
            "engine": "llm",
            "ollama_text": "qwen2.5:7b-instruct",
        },
        "llm_novel_qwen": {
            "page_style": "novel",
            "engine": "llm",
            "ollama_text": "qwen2.5:7b-instruct",
        },
    }

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / _safe_name(file.filename or "upload")
    with dest.open("wb") as f:
        f.write(await file.read())
    # UI-friendly path for subsequent /run
    return {"ok": True, "path": str(dest.resolve()), "ui_path": f"/app/uploads/{dest.name}", "filename": file.filename}

@app.get("/file")
def file_get(path: str):
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path)

# ------------------ ASYNC RUN: POST /run enqueues; GET /run/{id} polls ------------------

JOBS: Dict[str, Dict[str, Any]] = {}

def _job_worker(job_id: str, req: RunRequest):
    JOBS[job_id] = {"status": "running", "started": time.time()}
    try:
        result = run_pipeline(req)
        JOBS[job_id] = {"status": "done", "result": result.model_dump(), "ended": time.time()}
    except Exception as e:
        JOBS[job_id] = {"status": "error", "error": str(e), "ended": time.time()}

@app.post("/run")
def run_enqueue(req: RunRequest):
    req = _normalize_paths(req)
    job_id = uuid.uuid4().hex[:12]
    t = threading.Thread(target=_job_worker, args=(job_id, req), daemon=True)
    t.start()
    # returns immediately — Netlify won't 504
    return {"ok": True, "id": job_id}

@app.get("/run/{job_id}")
def run_status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Unknown job id")
    return job
