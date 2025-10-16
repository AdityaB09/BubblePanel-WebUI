from pydantic import BaseModel
from typing import Literal, Optional, List


class RunRequest(BaseModel):
    # IO
    input: str                     # server-side path or /app/uploads/<file>
    out: str                       # output dir (relative to BubblePanel-main or absolute)
    jsonl: str = "panels.jsonl"    # will be placed under 'out' if relative

    # LLM (only if engine == "llm")
    host: Optional[str] = None
    ollama_text: Optional[str] = None

    # Summary / layout
    page_summarize: bool = True
    page_style: Literal["paragraph", "novel"] = "paragraph"

    # Engines
    engine: Literal["llm", "encoder"] = "encoder"     # safe default: no Ollama
    embed_model: str = "sentence-transformers/all-mpnet-base-v2"
    mlm_refiner: bool = False

    # Advanced toggles
    recon_verbose: bool = False
    save_crops: bool = False
    all_ocr: bool = False
    ocr_verbose: bool = False
    no_ocr: bool = False

    # Execution control
    dry_run: bool = False
    timeout_seconds: Optional[int] = None             # override per-request timeout


class RunResult(BaseModel):
    ok: bool
    command: str
    stdout: str
    stderr: str
    out_dir: str
    overlays: List[str]
    text_files: List[str]
    jsonls: List[str]
