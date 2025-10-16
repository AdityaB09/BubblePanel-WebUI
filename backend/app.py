import os, re
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.models import RunRequest
from backend.app import run_pipeline
from backend.settings import (
    PROJECT_ROOT, BP_ROOT, UPLOAD_DIR, map_ui_upload_path, norm
)

app = FastAPI(title="BubblePanel API", version="1.4")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten to your Netlify origin in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"ok": True, "service": "bubblepanel-backend"}

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/status")
def status():
    script = os.environ.get("BP_SCRIPT", "smoke_test.py")
    pyexe  = os.environ.get("BP_PYTHON", "python")
    return {
        "ok": True,
        "python": pyexe,
        "python_exists": (os.system(f"which {pyexe} > /dev/null 2>&1") == 0),
        "project_root": str(PROJECT_ROOT),
        "bp_root": str(BP_ROOT),
        "upload_dir": str(UPLOAD_DIR),
        "script": script,
        "script_exists_under_bp_root": (BP_ROOT / script).is_file(),
    }

@app.get("/presets")
def presets():
    return {
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
        "encoder_paragraph_mpnet": {
            "page_style": "paragraph",
            "engine": "encoder",
            "embed_model": "sentence-transformers/all-mpnet-base-v2",
            "mlm_refiner": True,
        },
        "llm_paragraph_llama": {
            "page_style": "paragraph",
            "engine": "llm",
            "ollama_text": "llama3.1:latest",
        },
    }

# ---------- Upload ----------
_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")

def _safe_name(name: str) -> str:
    base = _SAFE_RE.sub("_", name or "")
    return base or "upload"

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / _safe_name(file.filename)
    with dest.open("wb") as f:
        f.write(await file.read())
    # Return both absolute and "UI" path
    return {
        "ok": True,
        "path": str(dest.resolve()),
        "ui_path": f"/app/uploads/{dest.name}",
        "filename": file.filename,
    }

# ---------- Run pipeline ----------
@app.post("/run")
def run(req: RunRequest):
    # Normalize paths from UI
    # input can be absolute, /app/uploads/<name>, or relative to BP_ROOT
    inp = map_ui_upload_path(req.input)
    if not inp.exists():
        raise HTTPException(status_code=400, detail=f"Input not found: {inp}")

    # Normalize output path: allow relative under BP_ROOT
    out_norm = norm(req.out) or "./data/outputs/job"
    out_path = Path(out_norm)
    if not out_path.is_absolute():
        out_path = (BP_ROOT / out_norm.lstrip("./")).resolve()

    # Normalize jsonl location the same way if it's relative
    jsonl_norm = norm(req.jsonl) or "panels.jsonl"
    if not Path(jsonl_norm).is_absolute():
        req.jsonl = str((out_path / Path(jsonl_norm).name).resolve())
    else:
        req.jsonl = jsonl_norm

    # rewrite req fields with normalized paths
    req.input = str(inp)
    req.out   = str(out_path)

    result = run_pipeline(req)
    return result.model_dump()

# ---------- Serve output artifacts ----------
@app.get("/file")
def get_file(path: str):
    # For convenience; lock down in prod
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path)
#