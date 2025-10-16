# backend/main.py
import os, re, uuid, threading, time
from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.models import RunRequest
from backend.process import run_pipeline
from backend.settings import (
    BP_ROOT,
    UPLOAD_DIR,
    map_ui_upload_path,
)

app = FastAPI(title="BubblePanel API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in prod: ["https://your-netlify-app.netlify.app"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- simple in-memory job store ----------
JOBS: Dict[str, Dict[str, Any]] = {}

def _worker(job_id: str, req: RunRequest):
    JOBS[job_id] = {"status": "running", "started": time.time()}
    try:
        res = run_pipeline(req)
        JOBS[job_id] = {
            "status": "done",
            "result": res.model_dump(),
            "ended": time.time(),
        }
    except Exception as e:
        JOBS[job_id] = {
            "status": "error",
            "error": str(e),
            "ended": time.time(),
        }

# ---------- health & status ----------
@app.get("/")
def root():
    return {"ok": True, "service": "bubblepanel-backend"}

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

# ---------- upload ----------
_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")

def _safe(name: str) -> str:
    s = _SAFE_RE.sub("_", name or "")
    return s or "upload"

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / _safe(file.filename)
    with dest.open("wb") as f:
        f.write(await file.read())
    return {"ok": True, "path": str(dest.resolve()), "ui_path": f"/app/uploads/{dest.name}", "filename": file.filename}

# ---------- serve output files ----------
@app.get("/file")
def get_file(path: str):
    if not os.path.isfile(path):
        raise HTTPException(404, "File not found")
    return FileResponse(path)

# ---------- async run + polling ----------
def _normalize_paths(req: RunRequest) -> RunRequest:
    """Normalize req.input/out/jsonl to absolute server paths."""
    # input can be absolute, /app/uploads/<name>, or relative to BP_ROOT
    inp = map_ui_upload_path(req.input)
    if not inp.exists():
        raise HTTPException(400, f"Input not found: {inp}")

    # out: allow relative under BP_ROOT
    out = req.out or "./data/outputs/job"
    out_path = Path(out)
    if not out_path.is_absolute():
        out_path = (BP_ROOT / out_path.as_posix().lstrip("./")).resolve()

    # jsonl: if relative, place inside out
    j = req.jsonl or "panels.jsonl"
    j_path = Path(j)
    if not j_path.is_absolute():
        j_path = (out_path / j_path.name).resolve()

    # LLM summarize guard:
    # Only allow page_summarize if they explicitly set engine=llm + provide host+ollama_text
    allow_summary = (req.engine == "llm" and bool(req.host) and bool(req.ollama_text))
    if not allow_summary:
        req.page_summarize = False  # avoid Ollama 127.0.0.1 failures

    req.input = str(inp)
    req.out   = str(out_path)
    req.jsonl = str(j_path)
    return req

@app.post("/run")
def run_async(req: RunRequest):
    """Start a job and return quickly with an id so Netlify won't 504."""
    req = _normalize_paths(req)

    # Respect caller-provided timeout or BP_TIMEOUT env
    if not req.timeout_seconds:
        try:
            req.timeout_seconds = int(os.getenv("BP_TIMEOUT", "600"))
        except Exception:
            req.timeout_seconds = 600

    job_id = uuid.uuid4().hex[:12]
    t = threading.Thread(target=_worker, args=(job_id, req), daemon=True)
    t.start()
    return {"ok": True, "id": job_id}

@app.get("/run/{job_id}")
def run_status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Unknown job id")
    return job
