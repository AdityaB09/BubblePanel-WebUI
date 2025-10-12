import os
import shlex
import subprocess
import glob
from typing import List

from settings import RunRequest, RunResult

# You can override these via environment variables:
#   BP_PYTHON, BP_SCRIPT, BP_REPO_ROOT
PY_EXE = os.environ.get("BP_PYTHON", "python")
SCRIPT = os.environ.get("BP_SCRIPT", "smoke_test.py")
REPO_ROOT = os.environ.get("BP_REPO_ROOT", os.getcwd())

# Utility to find common output artifacts for gallery
EXT_OVERLAYS = ("*_panels.png", "*_bubbles.png")
EXT_TEXTS = ("*_text.txt",)
EXT_JSONLS = ("*.jsonl",)


def build_args(req: RunRequest) -> List[str]:
    args = [PY_EXE, SCRIPT, "--input", req.input, "--out", req.out, "--jsonl", req.jsonl]

    if req.page_summarize:
        args += ["--page-summarize"]
        args += ["--paragraph" if req.page_style == "paragraph" else "--novel"]

    if req.engine == "llm":
        if req.ollama_text:
            args += ["--ollama-text", req.ollama_text, "--host", req.host]
    else:
        args += ["--encoder", "--embed-model", req.embed_model]
        if req.mlm_refiner:
            args += ["--mlm-refiner"]

    # Advanced toggles
    if req.recon_verbose:
        args += ["--recon-verbose"]
    if req.save_crops:
        args += ["--save-crops"]
    if req.all_ocr:
        args += ["--all-ocr"]
    if req.ocr_verbose:
        args += ["--ocr-verbose"]
    if req.no_ocr:
        args += ["--no-ocr"]

    return args


def collect_paths(out_dir: str, patterns: tuple[str, ...]) -> list[str]:
    found: list[str] = []
    for pat in patterns:
      found.extend(sorted(glob.glob(os.path.join(out_dir, pat))))
    return found


def run_pipeline(req: RunRequest) -> RunResult:
    args = build_args(req)
    cmd_str = " ".join(shlex.quote(a) for a in args)

    # Ensure output directory exists
    os.makedirs(req.out, exist_ok=True)

    # ---- Force UTF-8 for the child process (fixes cp1252 UnicodeEncodeError on Windows) ----
    run_env = os.environ.copy()
    run_env.setdefault("PYTHONIOENCODING", "utf-8")
    # also helps in some environments:
    run_env.setdefault("LC_ALL", "C.UTF-8")
    run_env.setdefault("LANG", "C.UTF-8")
    # ----------------------------------------------------------------------------------------

    proc = subprocess.run(
        args,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",      # decode stdout/stderr as UTF-8
        errors="replace",      # never crash on odd bytes; replace with �
        shell=False,
        env=run_env,
    )

    overlays = collect_paths(req.out, EXT_OVERLAYS)
    text_files = collect_paths(req.out, EXT_TEXTS)
    jsonls = collect_paths(req.out, EXT_JSONLS)

    return RunResult(
        ok=(proc.returncode == 0),
        command=cmd_str,
        stdout=proc.stdout[-50_000:],
        stderr=proc.stderr[-50_000:],
        out_dir=req.out,
        overlays=overlays,
        text_files=text_files,
        jsonls=jsonls,
    )
