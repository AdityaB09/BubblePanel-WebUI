# src/llm/ollama_client.py
# Minimal, robust Ollama client helpers for text (generate) and chat with optional image.
# No temperature/stream kwargs; return raw text. Callers handle JSON parsing.

import json
import base64
import requests
from typing import Optional

def _post_json(host: str, path: str, payload: dict) -> dict:
    url = host.rstrip("/") + path
    resp = requests.post(url, json=payload, timeout=600)
    resp.raise_for_status()
    # Ollama /api/generate streams by default unless stream=false; response may be one or many JSON lines
    text = resp.text.strip()
    if not text:
        return {}
    # Try parse last JSON object if streamed
    last = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            last = json.loads(line)
        except Exception:
            pass
    return last or {}

def generate(host: str, model: str, system: str, prompt: str) -> str:
    """
    Call /api/generate in non-stream mode.
    Returns model's text (string). Caller is responsible for JSON parsing if needed.
    """
    payload = {
        "model": model,
        "system": system,
        "prompt": prompt,
        "stream": False,
        # modest limits for latency; adjust if needed
        "options": {
            "num_predict": 300,
            "top_p": 0.9,
            "repeat_penalty": 1.1
        }
    }
    obj = _post_json(host, "/api/generate", payload)
    return (obj.get("response") or "").strip()

def chat_vlm(host: str, model: str, system: str, user_text: str, image_path: Optional[str] = None) -> str:
    """
    Call /api/chat. If image_path is None, sends text-only messages.
    Returns the assistant content (string).
    """
    messages = [{"role": "system", "content": system}]
    if image_path:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {"type": "image", "image": b64}
            ]
        })
    else:
        messages.append({"role": "user", "content": user_text})

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "num_predict": 300,
            "top_p": 0.9,
            "repeat_penalty": 1.1
        }
    }
    obj = _post_json(host, "/api/chat", payload)
    # /api/chat non-stream returns {"message":{"content":"..."}}
    if isinstance(obj.get("message"), dict):
        return (obj["message"].get("content") or "").strip()
    return (obj.get("response") or "").strip()
