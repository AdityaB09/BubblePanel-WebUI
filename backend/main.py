import os
import re
import shutil
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.settings import RunRequest          # ← change
from backend.process import run_pipeline

app = FastAPI(title="BubblePanel API", version="1.3")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten for prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/status")
def status():
    repo = os.environ.get("BP_REPO_ROOT", os.getcwd())
    script = os.environ.get("BP_SCRIPT", "smoke_test.py")
    pyexe = os.environ.get("BP_PYTHON", "python")
    return {
        "ok": True,
        "python": pyexe,
        "python_exists": shutil.which(pyexe) is not None,
        "repo_root": repo,
        "repo_exists": os.path.isdir(repo),
        "script": script,
        "script_exists": os.path.isfile(os.path.join(repo, script)),
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

@app.post("/run")
def run(req: RunRequest):
    # minimal guard so users can’t click Run before choosing a file
    if not (req.input and os.path.isabs(req.input)):
        raise HTTPException(status_code=400, detail="Input image path is empty. Upload an image first or provide an absolute path.")
    result = run_pipeline(req)
    return result.model_dump()

# ---------- serve output files (images / txt / jsonl) ----------
@app.get("/file")
def get_file(path: str):
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path)

# ---------- upload endpoint so the UI can choose a file ----------
_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")

def _safe_name(name: str) -> str:
    base = _SAFE_RE.sub("_", name)
    return base or "upload"

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    upload_root = os.environ.get("BP_UPLOAD_DIR", os.path.join(os.getcwd(), "uploads"))
    os.makedirs(upload_root, exist_ok=True)

    safe = _safe_name(file.filename or "upload")
    dest = os.path.join(upload_root, safe)

    try:
        with open(dest, "wb") as f:
            f.write(await file.read())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    return {"ok": True, "path": os.path.abspath(dest), "filename": file.filename}
