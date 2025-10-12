import os
import shutil
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from settings import RunRequest
from process import run_pipeline

app = FastAPI(title="BubblePanel API", version="1.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # lock down for production
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
    result = run_pipeline(req)
    return result.model_dump()
