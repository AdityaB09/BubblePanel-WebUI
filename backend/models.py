from pydantic import BaseModel
from typing import Literal, Optional, List

class RunRequest(BaseModel):
    # IO
    input: str
    out: str
    jsonl: str = "panels.jsonl"

    # LLM host (only used if engine=="llm")
    host: Optional[str] = None

    # Summary mode
    page_summarize: bool = True
    page_style: Literal["paragraph", "novel"] = "paragraph"

    # Engines
    engine: Literal["llm", "encoder"] = "encoder"   # safe default = NO Ollama
    ollama_text: Optional[str] = None               # e.g. "qwen2.5:7b-instruct"

    # Encoder options
    embed_model: str = "sentence-transformers/all-mpnet-base-v2"
    mlm_refiner: bool = False

    # Advanced toggles
    recon_verbose: bool = False
    save_crops: bool = False
    all_ocr: bool = False
    ocr_verbose: bool = False
    no_ocr: bool = False

    # Utility
    dry_run: bool = False


class RunResult(BaseModel):
    ok: bool
    command: str
    stdout: str
    stderr: str
    out_dir: str
    overlays: List[str]
    text_files: List[str]
    jsonls: List[str]
