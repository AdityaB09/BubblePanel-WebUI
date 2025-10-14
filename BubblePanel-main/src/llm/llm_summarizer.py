from typing import List, Optional
from .ollama_client import OllamaClient

SYS_PROMPT = (
"You're a concise manga scene summarizer. "
"Given the current page’s dialogue and (optionally) brief prior page summaries, "
"write a 1–3 sentence narrative that captures who’s speaking to whom, the intent, "
"and any developing plot beats. Avoid quoting verbatim OCR noise; normalize casing."
)

def _build_prompt(page_dialogue: str, rolling_context: List[str], max_ctx: int) -> str:
    ctx = rolling_context[-max_ctx:] if max_ctx and max_ctx > 0 else rolling_context
    ctx_block = "\n".join(f"- {s}" for s in ctx) if ctx else "(none)"
    dlg = page_dialogue if page_dialogue.strip() else "(no dialogue found)"
    prompt = (
        f"{SYS_PROMPT}\n\n"
        f"Prior page summaries (most recent last):\n{ctx_block}\n\n"
        f"Current page dialogue lines:\n{dlg}\n\n"
        f"Now write the summary:"
    )
    return prompt

def summarize_llm(client: OllamaClient, model: str, page_dialogue: str,
                  rolling_context: List[str], max_ctx: int = 5) -> str:
    prompt = _build_prompt(page_dialogue, rolling_context, max_ctx)
    return client.generate(model=model, prompt=prompt)
