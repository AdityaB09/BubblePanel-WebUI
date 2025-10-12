from pydantic import BaseModel
from typing import Literal, Optional, List

class RunRequest(BaseModel):
    input: str
    out: str
    jsonl: str = "panels.jsonl"
    host: str = "http://127.0.0.1:11434"

    # summary mode
    page_summarize: bool = True
    page_style: Literal["paragraph", "novel"] = "paragraph"

    # engines
    engine: Literal["llm", "encoder"] = "llm"
    ollama_text: Optional[str] = "qwen2.5:7b-instruct"

    # encoder options
    embed_model: str = "sentence-transformers/all-mpnet-base-v2"
    mlm_refiner: bool = False

    # advanced toggles
    recon_verbose: bool = False
    save_crops: bool = False
    all_ocr: bool = False
    ocr_verbose: bool = False
    no_ocr: bool = False


class RunResult(BaseModel):
    ok: bool
    command: str
    stdout: str
    stderr: str
    out_dir: str
    overlays: List[str]
    text_files: List[str]
    jsonls: List[str]
