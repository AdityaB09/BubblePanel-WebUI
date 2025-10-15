import os, re
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.models import RunRequest
from backend.process import run_pipeline
from backend.settings import BP_ROOT, UPLOAD_DIR, map_ui_upload_path, norm

app = FastAPI(title="BubblePanel API", version="1.5")

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
        "llm_paragraph_qwen": {"page_style": "paragraph", "engine": "llm", "ollama_text": "qwen2.5:7b-instruct"},
        "llm_novel_qwen":     {"page_style": "novel",     "engine": "llm", "ollama_text": "qwen2.5:7b-instruct"},
        "encoder_paragraph":  {"page_style": "paragraph", "engine": "encoder", "embed_model": "sentence-transformers/all-mpnet-base-v2", "mlm_refiner": True},
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

# ---------- run ----------
@app.post("/run")
def run(req: RunRequest):
    # normalize input path from UI
    inp = map_ui_upload_path(req.input)
    if not inp.exists():
        raise HTTPException(400, f"Input not found: {inp}")

    # normalize out and jsonl under BP_ROOT if relative
    out = norm(req.out) or "./data/outputs/job"
    out_path = Path(out)
    if not out_path.is_absolute():
        out_path = (BP_ROOT / out_path.as_posix().lstrip("./")).resolve()

    j = norm(req.jsonl) or "panels.jsonl"
    j_path = Path(j)
    if not j_path.is_absolute():
        j_path = (out_path / j_path.name).resolve()

    # write normalized values back to req
    req.input = str(inp)
    req.out   = str(out_path)
    req.jsonl = str(j_path)

    result = run_pipeline(req)
    return result.model_dump()

# ---------- serve files ----------
@app.get("/file")
def file(path: str):
    if not os.path.isfile(path):
        raise HTTPException(404, "File not found")
    return FileResponse(path)
