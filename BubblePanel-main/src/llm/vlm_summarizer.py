from typing import List, Optional
from .ollama_client import OllamaClient

SYS_PROMPT = (
"You are a visual + dialogue manga summarizer. "
"Use the page’s dialogue and (if provided) the image to infer who speaks and what’s happening. "
"Be robust to OCR noise; normalize typos. Keep it to 1–3 sentences."
)

def _build_prompt(page_dialogue: str, rolling_context: List[str], max_ctx: int) -> str:
    ctx = rolling_context[-max_ctx:] if max_ctx and max_ctx > 0 else rolling_context
    ctx_block = "\n".join(f"- {s}" for s in ctx) if ctx else "(none)"
    dlg = page_dialogue if page_dialogue.strip() else "(no dialogue found)"
    return (
        f"{SYS_PROMPT}\n\n"
        f"Prior page summaries (most recent last):\n{ctx_block}\n\n"
        f"Current page dialogue lines:\n{dlg}\n\n"
        f"Write the summary:"
    )

def summarize_vlm(client: OllamaClient, model: str, page_dialogue: str,
                  rolling_context: List[str], image_path: Optional[str] = None,
                  max_ctx: int = 5) -> str:
    prompt = _build_prompt(page_dialogue, rolling_context, max_ctx)

    images_b64 = None
    if image_path:
        try:
            images_b64 = [client.encode_image_to_base64(image_path)]
        except Exception:
            images_b64 = None  # proceed without image if read fails

    return client.generate(model=model, prompt=prompt, images=images_b64)
