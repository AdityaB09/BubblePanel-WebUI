import os, shlex, subprocess, glob
from pathlib import Path
from typing import List

from backend.models import RunRequest, RunResult
from backend.settings import BP_ROOT, PY_EXE, SCRIPT, norm

# Artifacts we list back to the UI
EXT_OVERLAYS = ("*_panels.png", "*_bubbles.png")
EXT_TEXTS    = ("*_text.txt",)
EXT_JSONLS   = ("*.jsonl",)

def _collect(out_dir: str, patterns: tuple[str, ...]) -> list[str]:
    found: list[str] = []
    for pat in patterns:
        found.extend(sorted(glob.glob(os.path.join(out_dir, pat))))
    return found

def _build_args(req: RunRequest) -> List[str]:
    args = [PY_EXE, SCRIPT, "--input", req.input, "--out", req.out, "--jsonl", req.jsonl]

    if req.page_summarize:
        args += ["--page-summarize"]
        args += ["--paragraph" if req.page_style == "paragraph" else "--novel"]

    if req.engine == "llm":
        # Only add Ollama flags if a model AND a host are provided
        if req.ollama_text and req.host:
            args += ["--ollama-text", req.ollama_text, "--host", req.host]
    else:
        args += ["--encoder", "--embed-model", req.embed_model]
        if req.mlm_refiner:
            args += ["--mlm-refiner"]

    if req.recon_verbose: args += ["--recon-verbose"]
    if req.save_crops:    args += ["--save-crops"]
    if req.all_ocr:       args += ["--all-ocr"]
    if req.ocr_verbose:   args += ["--ocr-verbose"]
    if req.no_ocr:        args += ["--no-ocr"]

    return args

def run_pipeline(req: RunRequest) -> RunResult:
    # Create out dir
    os.makedirs(req.out, exist_ok=True)

    args = _build_args(req)
    cmd_str = " ".join(shlex.quote(a) for a in args)

    # Force UTF-8 in child
    run_env = os.environ.copy()
    run_env.setdefault("PYTHONIOENCODING", "utf-8")
    run_env.setdefault("LC_ALL", "C.UTF-8")
    run_env.setdefault("LANG", "C.UTF-8")

    if req.dry_run:
        return RunResult(
            ok=True,
            command=cmd_str,
            stdout="(dry_run) would execute in {}".format(BP_ROOT),
            stderr="",
            out_dir=req.out,
            overlays=[],
            text_files=[],
            jsonls=[]
        )

    proc = subprocess.run(
        args,
        cwd=str(BP_ROOT),           # IMPORTANT: run inside BubblePanel-main/
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        env=run_env,
        timeout=120,                # keep requests bounded
    )

    overlays   = _collect(req.out, EXT_OVERLAYS)
    text_files = _collect(req.out, EXT_TEXTS)
    jsonls     = _collect(req.out, EXT_JSONLS)

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
