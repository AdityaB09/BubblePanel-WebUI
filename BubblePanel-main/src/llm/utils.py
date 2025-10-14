# src/llm/utils.py
import json

def needs_vlm(text_paragraph_jsonl_path: str) -> bool:
    """
    Heuristic: trigger VLM only if any page paragraph is very short/empty.
    """
    try:
        with open(text_paragraph_jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                obj = json.loads(line)
                p = (obj.get("paragraph") or "").strip()
                if len(p) < 120:
                    return True
        return False
    except Exception:
        return True
