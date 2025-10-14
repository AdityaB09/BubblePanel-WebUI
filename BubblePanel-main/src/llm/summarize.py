# src/llm/summarize.py
import json
import os
import re
from typing import Dict, List, Tuple

from src.export.jsonl_writer import write_jsonl
from src.llm.ollama_client import generate, chat_vlm
from src.llm.prompts import (
    SYSTEM_TEXT, USER_TEXT_TEMPLATE, SYSTEM_VLM, USER_VLM_TEMPLATE,
    PARA_SYSTEM_TEXT, PARA_USER_TEXT_TEMPLATE, PARA_SYSTEM_VLM, PARA_USER_VLM_TEMPLATE,
    NOVEL_SYSTEM_TEXT, NOVEL_USER_TEXT_TEMPLATE, NOVEL_SYSTEM_VLM, NOVEL_USER_VLM_TEMPLATE,
    REPAIR_SYSTEM, REPAIR_USER_TEMPLATE,
)

FALLBACK_TEXT_MODEL = os.getenv("BUBBLEPANEL_TEXT_LLM", "qwen2.5:7b-instruct")

# ---------------- Utilities ----------------

def _read_jsonl(path: str) -> List[Dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows

def _safe_json(text: str) -> Dict:
    m = re.search(r"\{.*\}", text or "", flags=re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return {"warnings": ["model_return_not_json"], "raw": (text or "").strip()}

def _ascii_ratio(s: str) -> float:
    if not s:
        return 1.0
    ascii_chars = sum(1 for ch in s if ord(ch) < 128)
    return ascii_chars / len(s)

def _alpha_ratio(s: str) -> float:
    if not s:
        return 0.0
    return sum(ch.isalpha() for ch in s) / len(s)

def _sanitize_sentence(s: str) -> str:
    # collapse whitespace and dots
    s = re.sub(r"\s+", " ", s)
    s = s.replace("..", "…").replace("— —", "—").strip()
    # remove stray non-ascii control chunks
    s = re.sub(r"[^\x20-\x7E]{1,}", "", s)
    # micro-fixes
    for a, b in {"l'm":"I'm","gmamal":"game","Plaedts":"Played","D'as":"D' as"}.items():
        s = s.replace(a, b)
    return s.strip()

def _clean_bubbles(bubbles: List[str]) -> List[str]:
    """Strong cleaner (for novel)."""
    cleaned, prev = [], None
    for t in bubbles or []:
        s = _sanitize_sentence((t or "").strip())
        if not s:
            continue
        letters = sum(ch.isalpha() for ch in s)
        non_alnum = sum(1 for ch in s if not (ch.isalnum() or ch.isspace() or ch in ".,?!'\"-…:;()[]"))
        if letters < 3 or non_alnum / max(1, len(s)) > 0.35:
            continue
        # numeric-heavy junk like "11.1 SO"
        digits = sum(ch.isdigit() for ch in s)
        if digits >= 3 and digits / len(s) > 0.25:
            continue
        # trim repeated clauses
        s = re.sub(r"\b(\w.+?)(?:\s*,?\s*\1\b)+", r"\1", s, flags=re.I)
        key = s.lower()
        if key == prev:
            continue
        cleaned.append(s)
        prev = key
    return cleaned

def _clean_bubbles_soft(bubbles: List[str]) -> List[str]:
    """Softer cleaner (for paragraph)."""
    cleaned, seen = [], set()
    for t in bubbles or []:
        s = _sanitize_sentence((t or "").strip())
        if not s:
            continue
        letters = sum(ch.isalpha() for ch in s)
        non_alnum = sum(1 for ch in s if not (ch.isalnum() or ch.isspace() or ch in ".,?!'\"-…:;()[]"))
        if letters < 2 or non_alnum / max(1, len(s)) > 0.45:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(s)
    return cleaned

def _assign_speakers(lines: List[str]) -> List[str]:
    if not lines:
        return []
    merged = []
    for s in lines:
        s = s.strip()
        if merged and (s[:1].islower() or s.startswith("...") or merged[-1].endswith(",")):
            merged[-1] = merged[-1].rstrip() + " " + s.lstrip(". ").strip()
        else:
            merged.append(s)
    out, sp = [], 1
    for s in merged:
        out.append(f'Speaker {sp}: "{s}"')
        sp = 2 if sp == 1 else 1
    return out

# --------- Dialogue/quote validation ----------

_BAD_TOKENS = {"uegetabile", "p!p", "tomoTrow", "SO...", "a |", "DN", "el"}
_BAD_PAT = re.compile(r"(?:[^\w\s'\",.!?\-\u2013\u2014]|_{2,}|\d{3,})")

def _is_valid_quote(q: str) -> bool:
    q = _sanitize_sentence(q or "")
    if not (4 <= len(q) <= 160):
        return False
    if _alpha_ratio(q) < 0.65:
        return False
    if _BAD_PAT.search(q):
        return False
    if any(bad.lower() in q.lower() for bad in _BAD_TOKENS):
        return False
    # must look like a clause, not a label
    if not re.search(r"[A-Za-z]{3,}.*[A-Za-z]{2,}", q):
        return False
    return True

def _valid_quotes_from_lines(lines: List[str]) -> List[str]:
    vals = []
    for s in lines or []:
        s1 = s.strip().strip('"')
        if _is_valid_quote(s1):
            vals.append(s1)
    # keep at most 4 candidates; de-dup case-insensitive
    uniq, seen = [], set()
    for s in vals:
        k = s.lower()
        if k not in seen:
            uniq.append(s); seen.add(k)
    return uniq[:4]

def _extract_quotes(paragraph: str) -> List[str]:
    return re.findall(r'"([^"]{1,260})"', paragraph or "")

def _cleaned_text_variants(cleaned_dialogue: List[str]) -> List[str]:
    allowed = []
    for line in cleaned_dialogue or []:
        m = re.search(r'^Speaker\s+\d+:\s*"(.+)"\s*$', line)
        if m:
            allowed.append(m.group(1).strip())
        else:
            s = re.sub(r"^Speaker\s+\d+:\s*", "", line).strip().strip('"')
            if s:
                allowed.append(s)
    uniq, seen = [], set()
    for s in allowed:
        k = s.lower()
        if k not in seen:
            uniq.append(s); seen.add(k)
    return uniq

def _strip_unverified_quotes(paragraph: str, allowed_quotes: List[str]) -> Tuple[str, List[str]]:
    allowed_set = {q for q in allowed_quotes}
    used: List[str] = []
    def repl(m):
        q = m.group(1)
        if q in allowed_set:
            used.append(q)
            return f'"{q}"'
        return q
    new_para = re.sub(r'"([^"]{1,260})"', repl, paragraph or "")
    new_para = re.sub(r"\s{2,}", " ", new_para).strip()
    return new_para, used

def _sanitize_paragraph_block(p: str) -> str:
    # remove sentences that look corrupted
    sents = re.split(r"(?<=[.!?…])\s+", p or "")
    good = []
    for s in sents:
        s0 = _sanitize_sentence(s)
        if not s0:
            continue
        if _alpha_ratio(s0) < 0.6:
            continue
        if _BAD_PAT.search(s0):
            continue
        good.append(s0)
    text = " ".join(good).strip()
    # normalize spaces and quotes
    text = re.sub(r"\s{2,}", " ", text)
    return text

def _quality_bad(paragraph: str, cleaned_dialogue: List[str]) -> bool:
    if not paragraph:
        return True
    s = paragraph.strip()
    if len(s) < 140 or len(s) > 1600:
        return True
    if _ascii_ratio(s) < 0.9:
        return True
    if re.search(r"[‘’“”]|…{3,}|_{2,}|[^\x20-\x7E]", s):
        return True
    dlg = " ".join(cleaned_dialogue).lower()
    common = sum(1 for w in set(re.findall(r"[a-z]{3,}", s.lower())) if w in dlg)
    vocab = max(1, len(set(re.findall(r"[a-z]{3,}", s.lower()))))
    if vocab > 0 and (common / vocab) > 0.9:
        return True
    return False

def _repair_paragraph(host: str, model: str, cleaned_dialogue: List[str], draft: str) -> str:
    joined = "\n".join(cleaned_dialogue)
    user = REPAIR_USER_TEMPLATE.format(joined=joined, draft=draft)
    fixed = generate(host=host, model=model, system=REPAIR_SYSTEM, prompt=user)
    fixed = (fixed or "").strip()
    if len(fixed) >= 160 and _ascii_ratio(fixed) >= 0.95:
        return fixed
    return draft

def _group_panels_by_page(panels: List[Dict]) -> List[Dict]:
    pages: Dict[str, Dict] = {}
    for p in panels or []:
        key = f"{p.get('page_index','')}-{p.get('page_id','')}"
        if key not in pages:
            pages[key] = {
                "page_index": p.get("page_index"),
                "page_id": p.get("page_id"),
                "bubbles": [],
                "panels": [],
            }
        pages[key]["panels"].append(p.get("panel_index"))
        pages[key]["bubbles"].extend(p.get("bubbles", []))
    return sorted(pages.values(), key=lambda r: (r.get("page_index") or 0))

# ---------------- PANEL LEVEL (short) ----------------

def summarize_text_jsonl(jsonl_in: str, jsonl_out: str, model: str, host: str):
    panels = _read_jsonl(jsonl_in)
    out = []
    for p in panels:
        payload = {
            "page_index": p.get("page_index"),
            "panel_index": p.get("panel_index"),
            "bubbles": p.get("bubbles", []),
        }
        user = USER_TEXT_TEMPLATE.format(payload=json.dumps(payload, ensure_ascii=False))
        js = _safe_json(generate(host=host, model=model, system=SYSTEM_TEXT, prompt=user))
        out.append({
            **p,
            "summary_text_model": model,
            "summary_text": js.get("panel_summary", js.get("raw", "")),
            "ordered_bubbles_text": js.get("ordered_bubbles", p.get("bubbles", [])),
            "warnings_text": js.get("warnings", []),
        })
    write_jsonl(jsonl_out, out)

def summarize_vlm_jsonl(jsonl_in: str, jsonl_out: str, model: str, host: str, use_image: bool = True):
    """
    Panel-level summaries via 'VLM' interface.

    If use_image=False, never sends images (text-only prompt).
    This keeps behavior consistent with --vlm-no-image in smoke_test.py.
    """
    panels = _read_jsonl(jsonl_in)
    out = []
    for p in panels:
        # Build a plain text prompt from bubbles
        joined = "\n".join(f"{i+1}) {t}" for i, t in enumerate(p.get("bubbles", [])))
        user = USER_VLM_TEMPLATE.format(joined=joined)

        # Choose whether to send an image (panel crop preferred; else full image) or none
        image_path = p.get("panel_crop") or p.get("image_path")
        if not use_image:
            image_path = None

        js = _safe_json(
            chat_vlm(
                host=host,
                model=model,
                system=SYSTEM_VLM,
                user_text=user,
                image_path=image_path
            )
        )

        out.append({
            **p,
            "summary_vlm_model": model,
            "summary_vlm": js.get("panel_summary", js.get("raw", "")),
            "ordered_bubbles_vlm": js.get("ordered_bubbles", p.get("bubbles", [])),
            "warnings_vlm": js.get("warnings", []),
        })

    write_jsonl(jsonl_out, out)

# ---------------- PAGE LEVEL (paragraph mode w/ dialog filter) ----------------

def _paragraph_payload(page: Dict, bubbles: List[str]) -> Dict:
    # Decide whether quotes are allowed and collect valid quote candidates
    # We will allow at most 2 quotes later via the prompt rules.
    valid_candidates = _valid_quotes_from_lines(bubbles)
    allow_quotes = bool(valid_candidates)
    return {
        "page_index": page["page_index"],
        "page_id": page["page_id"],
        "bubbles": bubbles,
        "allow_quotes": allow_quotes,
        "valid_quotes": valid_candidates[:2],  # pass up to two
    }

def _finalize_paragraph(paragraph: str, cleaned_dialogue: List[str], allow_quotes: bool, valid_quotes: List[str]) -> Tuple[str, List[str]]:
    # sanitize and enforce quote policy
    paragraph = _sanitize_paragraph_block(paragraph or "")
    if not paragraph:
        return "", []
    if allow_quotes and valid_quotes:
        # Only keep quotes that are both in valid_quotes and present in dialogue variants
        allowed_from_dialogue = _cleaned_text_variants([f'Speaker 1: "{q}"' for q in valid_quotes])
        paragraph, used = _strip_unverified_quotes(paragraph, allowed_from_dialogue)
        # cap to 2 used quotes by removing excess quotes' marks
        if len(used) > 2:
            keep = set(used[:2])
            def repl(m):
                q = m.group(1)
                return f'"{q}"' if q in keep else q
            paragraph = re.sub(r'"([^"]{1,260})"', repl, paragraph)
            used = used[:2]
        return paragraph, used
    else:
        # Remove any quoted text marks entirely (keep inner text)
        paragraph = re.sub(r'"([^"]{1,260})"', r"\1", paragraph)
        return paragraph, []

def summarize_text_pages(jsonl_in: str, jsonl_out: str, model: str, host: str):
    panels = _read_jsonl(jsonl_in)
    pages = _group_panels_by_page(panels)
    out = []
    for page in pages:
        bubbles = _clean_bubbles_soft(page["bubbles"])
        payload = _paragraph_payload(page, bubbles)
        user = PARA_USER_TEXT_TEMPLATE.format(payload=json.dumps(payload, ensure_ascii=False))
        js = _safe_json(generate(host=host, model=model, system=PARA_SYSTEM_TEXT, prompt=user))
        raw_para = js.get("paragraph", js.get("raw", "")).strip()

        paragraph, used = _finalize_paragraph(raw_para, _assign_speakers(bubbles), payload["allow_quotes"], payload["valid_quotes"])
        if _quality_bad(paragraph, _assign_speakers(bubbles)):
            paragraph = _repair_paragraph(host, model, _assign_speakers(bubbles), paragraph)
            paragraph, used = _finalize_paragraph(paragraph, _assign_speakers(bubbles), payload["allow_quotes"], payload["valid_quotes"])

        out.append({
            **page,
            "model": model,
            "paragraph": paragraph,
            "summary_text_model": model,
            "summary_text": paragraph,
            "ordered_bubbles_text": bubbles,
            "used_quotes": used,
            "warnings_text": js.get("warnings", []),
        })
    write_jsonl(jsonl_out, out)

def summarize_vlm_pages(jsonl_in: str, jsonl_out: str, model: str, host: str):
    """VLM paragraph with validation and optional text fallback."""
    def _as_list(x):
        if x is None: return []
        if isinstance(x, list): return x
        return [x]

    panels = _read_jsonl(jsonl_in)
    pages = _group_panels_by_page(panels)
    out = []
    for page in pages:
        bubbles = _clean_bubbles_soft(page["bubbles"])
        payload = _paragraph_payload(page, bubbles)

        # Primary: VLM (text-only for paragraph mode)
        joined = "\n".join(f"{i+1}) {t}" for i, t in enumerate(bubbles))
        user = PARA_USER_VLM_TEMPLATE.format(joined=joined)
        # Sneak in the JSON policy as the "ALSO SEE" block requirement:
        user = user.replace("true_or_false", "true" if payload["allow_quotes"] else "false")
        user = user.replace("[...]", json.dumps(payload["valid_quotes"], ensure_ascii=False))

        js_vlm = _safe_json(chat_vlm(host=host, model=model, system=PARA_SYSTEM_VLM, user_text=user, image_path=None))
        raw_para = (js_vlm.get("paragraph", js_vlm.get("raw", "")) or "").strip()
        warnings_vlm = _as_list(js_vlm.get("warnings"))

        paragraph, used = _finalize_paragraph(raw_para, _assign_speakers(bubbles), payload["allow_quotes"], payload["valid_quotes"])
        if _quality_bad(paragraph, _assign_speakers(bubbles)):
            # Fallback: regenerate with text LLM
            js_text = _safe_json(generate(host=host, model=FALLBACK_TEXT_MODEL, system=PARA_SYSTEM_TEXT,
                                          prompt=PARA_USER_TEXT_TEMPLATE.format(payload=json.dumps(payload, ensure_ascii=False))))
            raw2 = (js_text.get("paragraph", js_text.get("raw", "")) or "").strip()
            paragraph, used = _finalize_paragraph(raw2, _assign_speakers(bubbles), payload["allow_quotes"], payload["valid_quotes"])
            warnings_vlm.append(f"vlm_paragraph_refined_with_text_llm:{FALLBACK_TEXT_MODEL}")

        out.append({
            **page,
            "model": model,
            "paragraph": paragraph,
            "summary_vlm_model": model,
            "summary_vlm": paragraph,
            "ordered_bubbles_vlm": bubbles,
            "used_quotes_vlm": used,
            "warnings_vlm": warnings_vlm,
        })
    write_jsonl(jsonl_out, out)

# Aliases kept for CLI flags
def summarize_text_pages_paragraph(jsonl_in: str, jsonl_out: str, model: str, host: str):
    return summarize_text_pages(jsonl_in=jsonl_in, jsonl_out=jsonl_out, model=model, host=host)

def summarize_vlm_pages_paragraph(jsonl_in: str, jsonl_out: str, model: str, host: str):
    return summarize_vlm_pages(jsonl_in=jsonl_in, jsonl_out=jsonl_out, model=model, host=host)

# ---------------- NOVEL MODE (unchanged, still grounded) ----------------

def summarize_text_pages_novel(jsonl_in: str, jsonl_out: str, model: str, host: str):
    panels = _read_jsonl(jsonl_in)
    pages = _group_panels_by_page(panels)
    out = []
    for page in pages:
        raw = page["bubbles"]
        bubbles = _clean_bubbles(raw)
        dialogue_lines = _assign_speakers(bubbles)
        payload = {"page_index": page["page_index"], "page_id": page["page_id"], "bubbles": bubbles}
        user = NOVEL_USER_TEXT_TEMPLATE.format(payload=json.dumps(payload, ensure_ascii=False))
        js = _safe_json(generate(host=host, model=model, system=NOVEL_SYSTEM_TEXT, prompt=user))
        cleaned_dialogue = js.get("cleaned_dialogue", dialogue_lines or bubbles)
        if cleaned_dialogue and not cleaned_dialogue[0].lower().startswith("speaker"):
            cleaned_dialogue = _assign_speakers(cleaned_dialogue)
        paragraph = (js.get("scene_paragraph", js.get("raw", "")) or "").strip()
        paragraph = _sanitize_paragraph_block(paragraph)
        out.append({
            **page,
            "novel_model": model,
            "cleaned_dialogue": cleaned_dialogue,
            "scene_paragraph": paragraph,
            "warnings": js.get("warnings", []),
        })
    write_jsonl(jsonl_out, out)

def summarize_vlm_pages_novel(jsonl_in: str, jsonl_out: str, model: str, host: str):
    panels = _read_jsonl(jsonl_in)
    pages = _group_panels_by_page(panels)
    out = []
    for page in pages:
        raw = page["bubbles"]
        bubbles = _clean_bubbles(raw)
        dialogue_lines = _assign_speakers(bubbles)
        joined = "\n".join(f"{i+1}) {t}" for i, t in enumerate(bubbles))
        user = NOVEL_USER_VLM_TEMPLATE.format(joined=joined)
        js = _safe_json(chat_vlm(host=host, model=model, system=NOVEL_SYSTEM_VLM, user_text=user, image_path=None))
        cleaned_dialogue = js.get("cleaned_dialogue", dialogue_lines or bubbles)
        if cleaned_dialogue and not cleaned_dialogue[0].lower().startswith("speaker"):
            cleaned_dialogue = _assign_speakers(cleaned_dialogue)
        paragraph = (js.get("scene_paragraph", js.get("raw", "")) or "").strip()
        paragraph = _sanitize_paragraph_block(paragraph)
        out.append({
            **page,
            "novel_model": model,
            "cleaned_dialogue": cleaned_dialogue,
            "scene_paragraph": paragraph,
            "warnings": js.get("warnings", []),
        })
    write_jsonl(jsonl_out, out)
