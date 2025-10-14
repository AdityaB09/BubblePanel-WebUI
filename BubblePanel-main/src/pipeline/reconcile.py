# src/pipeline/reconcile.py
"""
Reconcile missed bubbles by comparing bubble detections with FULL-PAGE OCR.

What it does
------------
1) Runs full-page OCR → list of word boxes (RapidOCR + PaddleOCR + optional EasyOCR + Tesseract).
2) For each panel, measures how many words fall inside any bubble (coverage).
3) If coverage < threshold, re-runs bubble detection on that panel with RELAXED settings.
4) If coverage still low (and enabled), FALL BACK to building bubble boxes directly
   from OCR words (dilate grouped words) — very reliable for manga balloons.
5) Merges new bubbles with old (NMS) and returns the final list.

Enable verbose logs from the caller:
    reconcile_page(..., verbose=True)
"""

from __future__ import annotations
from typing import List, Tuple, Dict
import copy

import cv2
import numpy as np

from src.detectors.bubbles import detect_bubbles_in_panel, nms_boxes

Box  = Tuple[int, int, int, int]     # (x, y, w, h)
Word = Dict[str, object]             # {"box":[x,y,w,h], "text":str, "conf":float, "source":str}

# ----------------------------- small helpers ----------------------------- #

def _dbg(verbose: bool, msg: str) -> None:
    if verbose:
        print(msg, flush=True)

def _center(b: Box) -> Tuple[float, float]:
    x, y, w, h = b
    return x + w / 2.0, y + h / 2.0

def _point_in_box(px: float, py: float, b: Box) -> bool:
    x, y, w, h = b
    return (x <= px <= x + w) and (y <= py <= y + h)

def _words_in_box(words: List[Word], scope: Box) -> List[Word]:
    sx, sy, sw, sh = scope
    out = []
    for w in words:
        x, y, ww, hh = w["box"]
        cx, cy = x + ww / 2.0, y + hh / 2.0
        if sx <= cx <= sx + sw and sy <= cy <= sy + sh:
            out.append(w)
    return out

def _coverage(words_in_panel: List[Word], bubbles: List[Box]) -> float:
    """Fraction of word centers that land inside at least one bubble."""
    if not words_in_panel:
        return 1.0
    covered = 0
    for w in words_in_panel:
        x, y, ww, hh = w["box"]
        cx, cy = x + ww / 2.0, y + hh / 2.0
        if any(_point_in_box(cx, cy, b) for b in bubbles):
            covered += 1
    return covered / float(len(words_in_panel))

def _relax_cfg(cfg: dict, verbose: bool=False) -> dict:
    """
    Make a slightly more permissive copy of the config for a re-try on a weak panel.
    """
    c = copy.deepcopy(cfg)
    recon = cfg.get("reconcile", {})
    c["text_group_merge_px"] = int(cfg.get("text_group_merge_px", 58)
                                   + recon.get("rerun_merge_px_add", 20))
    c["white_percentile"] = int(cfg.get("white_percentile", 83)
                                + recon.get("rerun_white_delta", -6))
    c["min_white_ratio"] = float(recon.get("rerun_min_white_ratio", 0.30))
    if "grow_iters" in cfg:
        c["grow_iters"] = int(cfg.get("grow_iters", 24) + 8)
    if verbose:
        _dbg(True, f"[RECON]   relax: merge_px={c['text_group_merge_px']} "
                   f"white_pct={c['white_percentile']} "
                   f"min_white_ratio={c['min_white_ratio']}"
                   + (f" grow_iters={c['grow_iters']}" if 'grow_iters' in c else ""))
    return c

# ----------------------------- OCR over full page ----------------------------- #

def _rect_from_quad(quad) -> Tuple[int, int, int, int]:
    xs = [int(p[0]) for p in quad]; ys = [int(p[1]) for p in quad]
    x, y = min(xs), min(ys)
    w, h = max(xs) - x, max(ys) - y
    return int(x), int(y), max(1, int(w)), max(1, int(h))

def ocr_fullpage_words(bgr, cfg: dict, verbose: bool=False) -> List[Word]:
    """
    Returns a list of words across the FULL page in a common format:
    [{"box":[x,y,w,h], "text":str, "conf":float(0..1), "source":"backend"}]

    Backends tried and UNIONed:
      - RapidOCR (ONNXRuntime)  — best recall on manga
      - PaddleOCR               — strong detector
      - EasyOCR                 — optional (if cfg['use_easyocr'])
      - Tesseract               — classic fallback
    """
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    words: List[Word] = []

    # RapidOCR
    try:
        from rapidocr_onnxruntime import RapidOCR
        rocr = RapidOCR()
        results, _ = rocr(gray)
        rapid = []
        for quad, text, score in (results or []):
            x, y, w, h = _rect_from_quad(quad)
            rapid.append({"box":[x,y,w,h], "text": text or "", "conf": float(score or 0.0), "source": "rapidocr"})
        words.extend(rapid)
        _dbg(verbose, f"[RECON] OCR backend: rapidocr   words={len(rapid)}")
    except Exception as e:
        _dbg(verbose, f"[RECON] RapidOCR unavailable ({e})")

    # PaddleOCR
    try:
        from paddleocr import PaddleOCR
        lang = cfg.get("ocr", {}).get("lang", "en")
        po = PaddleOCR(use_angle_cls=True, lang=lang, show_log=False)
        res = po.ocr(gray, cls=True)
        padd = []
        for line in (res or []):
            for det, (text, conf) in line:
                x, y, w, h = _rect_from_quad(det)
                padd.append({"box":[x,y,w,h], "text": text or "", "conf": float(conf or 0.0), "source":"paddleocr"})
        words.extend(padd)
        _dbg(verbose, f"[RECON] OCR backend: paddleocr  words={len(padd)}")
    except Exception as e:
        _dbg(verbose, f"[RECON] PaddleOCR unavailable ({e})")

    # EasyOCR (optional)
    if cfg.get("use_easyocr", False):
        try:
            import easyocr
            lang = cfg.get("ocr", {}).get("lang", "en")
            mapped = "en" if lang in ("en", "eng") else lang
            reader = easyocr.Reader([mapped], gpu=False, verbose=False)
            out = reader.readtext(gray)
            ewords = []
            for item in out:
                if not isinstance(item, (list, tuple)) or len(item) < 2:
                    continue
                quad, text, conf = item
                x, y, w, h = _rect_from_quad(quad)
                ewords.append({"box":[x,y,w,h], "text": text or "", "conf": float(conf or 0.0), "source":"easyocr"})
            words.extend(ewords)
            _dbg(verbose, f"[RECON] OCR backend: easyocr    words={len(ewords)}")
        except Exception as e:
            _dbg(verbose, f"[RECON] EasyOCR unavailable ({e})")

    # Tesseract (fallback / also union)
    try:
        import pytesseract
        tcmd = cfg.get("ocr", {}).get("tesseract_cmd") or cfg.get("tesseract_cmd")
        if tcmd:
            pytesseract.pytesseract.tesseract_cmd = tcmd
        langs = cfg.get("ocr", {}).get("tesseract_langs", ["eng"])
        lang_str = "+".join(langs) if langs else "eng"
        data = pytesseract.image_to_data(gray, lang=lang_str, config="--psm 6",
                                         output_type=pytesseract.Output.DICT)
        N = len(data.get("text", []))
        twords = []
        for i in range(N):
            txt = (data["text"][i] or "").strip()
            try:
                conf = float(data["conf"][i]) / 100.0
            except Exception:
                conf = 0.0
            x, y = int(data["left"][i]), int(data["top"][i])
            w, h = int(data["width"][i]), int(data["height"][i])
            if w*h <= 0: continue
            twords.append({"box":[x,y,w,h], "text": txt, "conf": conf, "source":"tesseract"})
        words.extend(twords)
        _dbg(verbose, f"[RECON] OCR backend: tesseract  words={len(twords)}")
    except Exception as e:
        _dbg(verbose, f"[RECON] Tesseract unavailable ({e})")

    _dbg(verbose, f"[RECON] TOTAL OCR words={len(words)}")
    return words

# ----------------------------- Fallback: words → bubbles ----------------------------- #

def _bubbles_from_words(words_in_panel: List[Word], panel_box: Box, cfg: dict) -> List[Box]:
    """Build bubble boxes from OCR words by dilating their rectangles (no extra deps)."""
    if not words_in_panel:
        return []
    px, py, pw, ph = panel_box

    # mask of panel; draw each word rect on it
    mask = np.zeros((ph, pw), np.uint8)
    heights = []
    for w in words_in_panel:
        x, y, ww, hh = map(int, w["box"])
        heights.append(hh)
        # shift into panel-local coords
        x0 = max(0, x - px); y0 = max(0, y - py)
        x1 = min(pw, x0 + ww); y1 = min(ph, y0 + hh)
        if x1 > x0 and y1 > y0:
            cv2.rectangle(mask, (x0, y0), (x1, y1), 255, -1)

    # dilation size ~ text size
    med_h = int(np.median(heights)) if heights else 12
    k = max(5, int(0.9 * med_h))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
    dil = cv2.dilate(mask, kernel, iterations=1)

    # connected components → boxes
    cnts, _ = cv2.findContours(dil, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    pad = int(cfg.get("bubble_expand_px", 18))
    out = []
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        # expand & clip to panel
        x0 = max(px, px + x - pad)
        y0 = max(py, py + y - pad)
        x1 = min(px + pw, px + x + w + pad)
        y1 = min(py + ph, py + y + h + pad)
        if x1 - x0 > 10 and y1 - y0 > 10:
            out.append((int(x0), int(y0), int(x1 - x0), int(y1 - y0)))
    return out

# ----------------------------- public API ----------------------------- #

def reconcile_page(bgr, panel_boxes: List[Box], bubble_boxes: List[Box],
                   cfg: dict, verbose: bool=False) -> List[Box]:
    """
    Run full-page OCR, compute per-panel word coverage, and selectively re-run
    bubble detection with relaxed settings. Optionally fall back to words→bubbles.
    """
    recon_cfg = cfg.get("reconcile", {})
    if not recon_cfg.get("enable", True):
        _dbg(verbose, "[RECON] Reconciliation disabled.")
        return bubble_boxes

    words = ocr_fullpage_words(bgr, cfg, verbose=verbose)
    if not words:
        _dbg(verbose, "[RECON] No OCR words — skipping reconciliation.")
        return bubble_boxes

    cov_thresh   = float(recon_cfg.get("coverage_thresh", 0.70))
    max_passes   = int(recon_cfg.get("max_passes", 2))
    do_fallback  = bool(recon_cfg.get("fallback_from_words", True))

    final_bubbles = list(bubble_boxes)

    for pidx, p in enumerate(panel_boxes, start=1):
        pb = [b for b in final_bubbles if _point_in_box(*_center(b), p)]
        w_in = _words_in_box(words, p)
        cov = _coverage(w_in, pb)
        _dbg(verbose, f"[RECON] panel#{pidx} words={len(w_in):>3}  bubbles={len(pb):>2}  coverage={cov:.2f}")

        passes = 0
        cfg_try = cfg
        while cov < cov_thresh and passes < max_passes:
            passes += 1
            _dbg(verbose, f"[RECON]   retry {passes}…")
            cfg_try = _relax_cfg(cfg_try, verbose=verbose)
            new = detect_bubbles_in_panel(bgr, p, cfg_try)
            panel_new = [b for b in new if _point_in_box(*_center(b), p)]

            before = len(final_bubbles)
            final_bubbles.extend(panel_new)
            final_bubbles[:] = nms_boxes(final_bubbles, iou_thresh=0.3)
            added = len(final_bubbles) - before

            pb = [b for b in final_bubbles if _point_in_box(*_center(b), p)]
            cov = _coverage(w_in, pb)
            _dbg(verbose, f"[RECON]     added_bubbles={added}  new_coverage={cov:.2f}")

        # Fallback if still low coverage
        if do_fallback and cov < cov_thresh:
            fb = _bubbles_from_words(w_in, p, cfg)
            if fb:
                before = len(final_bubbles)
                final_bubbles.extend(fb)
                final_bubbles[:] = nms_boxes(final_bubbles, iou_thresh=0.3)
                pb = [b for b in final_bubbles if _point_in_box(*_center(b), p)]
                cov = _coverage(w_in, pb)
                added = len(final_bubbles) - before
                _dbg(verbose, f"[RECON]   fallback words→bubbles={added}  new_coverage={cov:.2f}")

    final_bubbles = nms_boxes(final_bubbles, iou_thresh=0.3)
    _dbg(verbose, f"[RECON] done. total_bubbles={len(final_bubbles)}")
    return final_bubbles
