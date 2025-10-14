# src/llm/encoder_summarizer.py
import json, re, math, torch
from typing import List, Dict
from pathlib import Path

# ---- local, model-light summarizer using encoder-only models ----
# Dependencies: sentence-transformers, transformers (for optional MLM refiner)

# ----------------- small utils -----------------
_WORD = re.compile(r"[A-Za-z']{2,}")

def _read_jsonl(path: str) -> List[Dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows

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

def _sanitize_sentence(s: str) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    s = s.replace("..", "…").replace("--", "—")
    s = re.sub(r"[^\x20-\x7E]{1,}", "", s)  # drop non-ascii artifacts
    # micro-fixes
    for a, b in {"l'm":"I'm","gmamal":"game","Plaedts":"Played","D'as":"D' as"}.items():
        s = s.replace(a, b)
    return s.strip()

def _clean_soft(lines: List[str]) -> List[str]:
    out, seen = [], set()
    for t in lines or []:
        s = _sanitize_sentence(t)
        if not s: continue
        letters = sum(ch.isalpha() for ch in s)
        non_alnum = sum(1 for ch in s if not (ch.isalnum() or ch.isspace() or ch in ".,?!'\"-…:;()[]"))
        if letters < 2 or non_alnum / max(1, len(s)) > 0.45:
            continue
        k = s.lower()
        if k in seen: continue
        seen.add(k); out.append(s)
    return out

def _sentences_from_bubbles(bubbles: List[str]) -> List[str]:
    sents = []
    for t in bubbles:
        parts = re.split(r"(?<=[.!?…])\s+", t)
        for p in parts:
            p = _sanitize_sentence(p)
            if len(p) >= 4:
                sents.append(p)
    return sents

def _compose_paragraph(sents: List[str], target_min=90, target_max=140) -> str:
    text = " ".join(sents).strip()
    if len(text) < target_min:
        return text
    if len(text) > target_max:
        parts = re.split(r"(?<=[.!?…])\s+", text)
        out, cur = [], 0
        for p in parts:
            if cur + len(p) + 1 > target_max: break
            out.append(p); cur += len(p) + 1
        return " ".join(out).strip()
    return text

def _write_jsonl(path: str, rows: List[Dict]):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

# ----------------- encoder scorer -----------------
def _rank_sentences(sents: List[str], embeddings) -> List[int]:
    import numpy as np
    X = embeddings  # (n, d)
    if X.shape[0] == 0:
        return []
    centroid = X.mean(axis=0, keepdims=True)  # (1, d)
    # cosine similarity to centroid
    denom = (np.linalg.norm(X, axis=1) * np.linalg.norm(centroid, axis=1)[0] + 1e-8)
    cos = (X @ centroid.T)[:, 0] / denom
    # small position prior (earlier gets slight boost)
    pos_bonus = np.linspace(0.12, 0.0, num=len(sents))
    score = cos + pos_bonus
    # pick top-k, then restore original order
    k = 4 if len(sents) <= 8 else 6
    idxs = np.argsort(-score)[:k].tolist()
    return sorted(idxs)

# ----------------- optional MLM refiner -----------------
def _refine_with_mlm(paragraph: str, mlm_pipeline=None) -> str:
    """Very light polish via masked-LM: fix short odd tokens by masking and filling."""
    if not paragraph or mlm_pipeline is None:
        return paragraph
    txt = paragraph

    # cheap passes: replace lone weird tokens by mask and fill a few times
    odd_tokens = re.findall(r"\b[a-z]{1,2}\b", txt)
    odd_tokens = [t for t in odd_tokens if t not in {"a","i","an","to","of","in","on","it"}]
    odd_tokens = list(dict.fromkeys(odd_tokens))[:4]
    for tok in odd_tokens:
        masked = re.sub(rf"\b{re.escape(tok)}\b", "[MASK]", txt, count=1)
        try:
            preds = mlm_pipeline(masked)  # returns list of candidates for first mask
            best = preds[0]["token_str"].strip() if preds else tok
            txt = masked.replace("[MASK]", best, 1)
        except Exception:
            pass

    # normalize spaces
    txt = re.sub(r"\s{2,}", " ", txt).strip()
    return txt

# ----------------- main entry -----------------
def summarize_pages_encoder(
    jsonl_in: str,
    jsonl_out: str,
    embed_model_name: str = "sentence-transformers/all-mpnet-base-v2",
    use_mlm_refiner: bool = False,
    mlm_model_name: str = "distilroberta-base",
    device: str = None
):
    """
    Summarize each page via encoder-only semantic selection; optional MLM polish.
    Writes jsonl with {"page_index","page_id","model":"encoder:<name>","paragraph":...}
    """
    from sentence_transformers import SentenceTransformer
    from transformers import pipeline as hf_pipeline, AutoModelForMaskedLM, AutoTokenizer

    panels = _read_jsonl(jsonl_in)
    pages = _group_panels_by_page(panels)

    # device selection
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    encoder = SentenceTransformer(embed_model_name, device=device)
    mlm = None
    if use_mlm_refiner:
        tok = AutoTokenizer.from_pretrained(mlm_model_name)
        mdl = AutoModelForMaskedLM.from_pretrained(mlm_model_name)
        mlm = hf_pipeline("fill-mask", model=mdl, tokenizer=tok, top_k=1, device=0 if device == "cuda" else -1)

    out = []
    for page in pages:
        bubbles = _clean_soft(page.get("bubbles", []))
        sents = _sentences_from_bubbles(bubbles)
        if not sents:
            out.append({**page, "model": f"encoder:{embed_model_name}", "paragraph": "", "ordered_bubbles_text": bubbles})
            continue

        embeddings = encoder.encode(sents, convert_to_numpy=True, normalize_embeddings=True)
        keep_idxs = _rank_sentences(sents, embeddings)
        chosen = [sents[i] for i in keep_idxs]
        paragraph = _compose_paragraph(chosen, target_min=90, target_max=140)

        if use_mlm_refiner:
            paragraph = _refine_with_mlm(paragraph, mlm_pipeline=mlm)

        out.append({
            **page,
            "model": f"encoder:{embed_model_name}",
            "paragraph": paragraph,
            "ordered_bubbles_text": bubbles,
            "warnings": [],
        })

    _write_jsonl(jsonl_out, out)
