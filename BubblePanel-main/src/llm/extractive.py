# src/llm/extractive.py
import json, math, re
from typing import Dict, List
from src.export.jsonl_writer import write_jsonl
from src.llm.summarize import _read_jsonl, _group_panels_by_page

_WORD = re.compile(r"[A-Za-z']{2,}")

def _sanitize(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace("..", "…").replace("--", "—")
    s = re.sub(r"[^\x20-\x7E]{1,}", "", s)
    return s

def _clean_soft(lines: List[str]) -> List[str]:
    out, seen = [], set()
    for t in lines or []:
        s = _sanitize(t or "")
        if not s: continue
        letters = sum(ch.isalpha() for ch in s)
        non_alnum = sum(1 for ch in s if not (ch.isalnum() or ch.isspace() or ch in ".,?!'\"-…:;()[]"))
        if letters < 2 or non_alnum / max(1, len(s)) > 0.45:
            continue
        k = s.lower()
        if k in seen: continue
        seen.add(k); out.append(s)
    return out

def _sent_split(texts: List[str]) -> List[str]:
    # treat each bubble as a sentence; also split on obvious end marks
    sents = []
    for t in texts:
        parts = re.split(r"(?<=[.!?…])\s+", t)
        for p in parts:
            p = _sanitize(p)
            if len(p) >= 4:
                sents.append(p)
    return sents

def _tf(sent: str) -> Dict[str, float]:
    words = [w.lower() for w in _WORD.findall(sent)]
    n = len(words) or 1
    d = {}
    for w in words:
        d[w] = d.get(w, 0) + 1.0 / n
    return d

def _idf(corpus: List[List[str]]) -> Dict[str, float]:
    df = {}
    for words in corpus:
        for w in set(words):
            df[w] = df.get(w, 0) + 1
    N = len(corpus) or 1
    return {w: math.log((N + 1) / (df[w] + 0.5)) + 1.0 for w in df}

def _score_sentences(sents: List[str]) -> List[float]:
    corp = [[w.lower() for w in _WORD.findall(s)] for s in sents]
    idf = _idf(corp)
    scores = []
    for s, words in zip(sents, corp):
        tf = {}
        for w in words:
            tf[w] = tf.get(w, 0) + 1.0 / (len(words) or 1)
        score = sum(tf[w] * idf.get(w, 1.0) for w in tf)
        scores.append(score)
    return scores

def _select_indices(scores: List[float], k: int) -> List[int]:
    idxs = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
    return sorted(idxs)  # keep original order for readability

def _compose_paragraph(sents: List[str], target_min=90, target_max=140) -> str:
    text = " ".join(sents).strip()
    if len(text) < target_min:
        # add more sentences if available (caller will pass enough)
        return text
    if len(text) > target_max:
        # truncate at sentence boundary
        parts = re.split(r"(?<=[.!?…])\s+", text)
        out, cur = [], 0
        for p in parts:
            if cur + len(p) + 1 > target_max: break
            out.append(p); cur += len(p) + 1
        return " ".join(out).strip()
    return text

def summarize_pages_extractive(jsonl_in: str, jsonl_out: str):
    panels = _read_jsonl(jsonl_in)
    pages = _group_panels_by_page(panels)
    out = []
    for page in pages:
        bubbles = _clean_soft(page.get("bubbles", []))
        sents = _sent_split(bubbles)
        if not sents:
            out.append({**page, "model": "extractive:v1", "paragraph": ""})
            continue
        scores = _score_sentences(sents)
        # pick top 4–6 sentences depending on length
        k = 4 if len(sents) <= 8 else 6
        chosen = [sents[i] for i in _select_indices(scores, k)]
        # no quotes: extractive stays prose
        para = _compose_paragraph(chosen, 90, 140)
        out.append({
            **page,
            "model": "extractive:v1",
            "paragraph": _sanitize(para),
            "ordered_bubbles_text": bubbles,
            "warnings": [],
        })
    write_jsonl(jsonl_out, out)
