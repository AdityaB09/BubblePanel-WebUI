# backend/main.py  — ASYNC jobs version (POST /run enqueues; GET /run/{id} polls)

import os, re, uuid, threading, time
from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.models import RunRequest
from backend.process import run_pipeline

# ------------------ paths & helpers ------------------

BP_ROOT = Path(os.environ.get("BP_REPO_ROOT", str(Path.cwd() / "BubblePanel-main"))).resolve()
UPLOAD_DIR = Path(os.environ.get("BP_UPLOAD_DIR", str(Path.cwd() / "uploads"))).resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")

def _safe(name: str) -> str:
    s = _SAFE_RE.sub("_", name or "")
    return s or "upload"

def _map_ui_upload_path(p: str) -> Path:
    """
    Convert a UI path to a server filesystem path.
    - '/app/uploads/<file>' -> UPLOAD_DIR/<file>
    - absolute path         -> unchanged
    - relative              -> resolve under BP_ROOT
    """
    if not p:
        return Path("")
    p = p.strip()
    if p.startswith("/app/uploads/"):
        return (UPLOAD_DIR / Path(p).name).resolve()
    path = Path(p)
    if path.is_absolute():
        return path.resolve()
    return (BP_ROOT / p.lstrip("./")).resolve()

def _normalize_paths(req: RunRequest) -> RunRequest:
    inp = _map_ui_upload_path(req.input)
    if not inp.exists():
        raise HTTPException(400, f"Input not found: {inp}")

    out_dir = req.out or "./data/outputs/job"
    out_path = Path(out_dir)
    if not out_path.is_absolute():
        out_path = (BP_ROOT / out_path.as_posix().lstrip("./")).resolve()
    out_path.mkdir(parents=True, exist_ok=True)

    jsonl = req.jsonl or "panels.jsonl"
    jsonl_path = Path(jsonl)
    if not jsonl_path.is_absolute():
        jsonl_path = (out_path / jsonl_path.name).resolve()

    # If no real LLM host+model, keep OCR-only to avoid hitting localhost:11434
    if not (req.engine == "llm" and req.host and req.ollama_text):
        req.page_summarize = False

    req.input = str(inp)
    req.out   = str(out_path)
    req.jsonl = str(jsonl_path)
    return req

# ------------------ FastAPI app ------------------

app = FastAPI(title="BubblePanel API", version="2.0-async")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in prod
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

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    dest = UPLOAD_DIR / _safe(file.filename or "upload")
    with dest.open("wb") as f:
        f.write(await file.read())
    return {"ok": True, "path": str(dest.resolve()), "ui_path": f"/app/uploads/{dest.name}", "filename": file.filename}

@app.get("/file")
def get_file(path: str):
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path)

# ------------------ ASYNC RUN: POST /run (enqueue) + GET /run/{id} (poll) ------------------

JOBS: Dict[str, Dict[str, Any]] = {}

def _job_worker(job_id: str, req: RunRequest):
    JOBS[job_id] = {"status": "running", "started": time.time()}
    try:
        res = run_pipeline(req)
        JOBS[job_id] = {"status": "done", "result": res.model_dump(), "ended": time.time()}
    except Exception as e:
        JOBS[job_id] = {"status": "error", "error": str(e), "ended": time.time()}

@app.post("/run")
def run_enqueue(req: RunRequest):
    req = _normalize_paths(req)
    job_id = uuid.uuid4().hex[:12]
    threading.Thread(target=_job_worker, args=(job_id, req), daemon=True).start()
    return {"ok": True, "id": job_id}  # returns in <100ms (Netlify-safe)

@app.get("/run/{job_id}")
def run_status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Unknown job id")
    return job
