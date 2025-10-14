from __future__ import annotations
"""
ROI-level OCR utilities used by the manga pipeline.

- Tries multiple backends on each bubble ROI (order is configurable).
- Returns the FIRST non-empty text found together with the backend name.
- Defensive against backends returning None / odd shapes.

Backends supported (install as you like):
  - rapidocr-onnxruntime
  - paddleocr (and paddlepaddle)
  - pytesseract  (plus native Tesseract binary)
  - easyocr      (requires torch/torchvision)
"""

from typing import Dict, List, Tuple
import cv2
import numpy as np

Box = Tuple[int, int, int, int]  # (x, y, w, h)


# ----------------------- small helpers -----------------------

def _to_gray(img: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img

def _clean_text(s: str) -> str:
    s = (s or "").replace("\n", " ")
    return " ".join(s.split())


# ----------------------- individual backends (ROI) -----------------------

def _ocr_tesseract(roi_bgr: np.ndarray, cfg: dict) -> Tuple[str, str]:
    try:
        import pytesseract
    except Exception:
        return "", "tesseract(unavailable)"

    tcmd = cfg.get("ocr", {}).get("tesseract_cmd") or cfg.get("tesseract_cmd")
    if tcmd:
        pytesseract.pytesseract.tesseract_cmd = tcmd

    langs = cfg.get("ocr", {}).get("tesseract_langs", ["eng"])
    lang_str = "+".join(langs) if langs else "eng"

    gray = _to_gray(roi_bgr)
    thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    try:
        txt = pytesseract.image_to_string(thr, lang=lang_str, config="--psm 6")
    except Exception:
        return "", "tesseract(error)"
    return _clean_text(txt), "tesseract"


def _ocr_easyocr(roi_bgr: np.ndarray, cfg: dict) -> Tuple[str, str]:
    try:
        import easyocr
    except Exception:
        return "", "easyocr(unavailable)"

    lang = cfg.get("ocr", {}).get("lang", "en")
    mapped = "en" if lang in ("en", "eng") else lang
    try:
        reader = easyocr.Reader([mapped], gpu=False, verbose=False)
        out = reader.readtext(_to_gray(roi_bgr)) or []   # guard
    except Exception:
        return "", "easyocr(error)"

    parts: List[str] = []
    for item in out:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        _, text, _ = item
        if (text or "").strip():
            parts.append(str(text))
    return _clean_text(" ".join(parts)), "easyocr"


def _ocr_rapidocr(roi_bgr: np.ndarray, cfg: dict) -> Tuple[str, str]:
    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception:
        return "", "rapidocr(unavailable)"
    try:
        rocr = RapidOCR()
        results, _ = rocr(_to_gray(roi_bgr))
        results = results or []   # guard
    except Exception:
        return "", "rapidocr(error)"

    parts: List[str] = []
    for item in results:
        if not item or len(item) < 3:
            continue
        _, text, _ = item
        if (text or "").strip():
            parts.append(str(text))
    return _clean_text(" ".join(parts)), "rapidocr"


def _ocr_paddleocr(roi_bgr: np.ndarray, cfg: dict) -> Tuple[str, str]:
    try:
        from paddleocr import PaddleOCR
    except Exception:
        return "", "paddleocr(unavailable)"

    lang = cfg.get("ocr", {}).get("lang", "en")
    try:
        ocr = PaddleOCR(use_angle_cls=True, lang=lang, show_log=False)
        res = ocr.ocr(_to_gray(roi_bgr), cls=True) or []   # guard
    except Exception:
        return "", "paddleocr(error)"

    parts: List[str] = []
    for line in res:
        if not line:
            continue
        for tup in (line or []):
            if not tup or len(tup) < 2:
                continue
            _, (text, _conf) = tup
            if (text or "").strip():
                parts.append(str(text))
    return _clean_text(" ".join(parts)), "paddleocr"


# ----------------------- dispatcher (ROI) -----------------------

def _ocr_roi_multibackend(roi_bgr: np.ndarray, cfg: dict) -> Tuple[str, str]:
    order = cfg.get("ocr", {}).get(
        "backends", ["rapidocr", "paddleocr", "tesseract", "easyocr"]
    )
    for be in order:
        if be == "rapidocr":
            txt, tag = _ocr_rapidocr(roi_bgr, cfg)
        elif be == "paddleocr":
            txt, tag = _ocr_paddleocr(roi_bgr, cfg)
        elif be == "tesseract":
            txt, tag = _ocr_tesseract(roi_bgr, cfg)
        elif be == "easyocr":
            txt, tag = _ocr_easyocr(roi_bgr, cfg)
        else:
            continue
        if txt:
            return txt, tag
    return "", "none"


# ----------------------- public API -----------------------

def ocr_bubbles(bgr: np.ndarray, bubble_boxes: List[Box], cfg: dict) -> List[Dict]:
    """
    OCR each bubble ROI using multiple backends in order (first non-empty wins).

    Returns:
      [
        {"box":[x,y,w,h], "text":"...", "backend":"rapidocr|paddleocr|tesseract|easyocr|none"},
        ...
      ]
    """
    results: List[Dict] = []
    for box in (bubble_boxes or []):
        x, y, w, h = map(int, box)
        if w <= 1 or h <= 1:
            results.append({"box":[x,y,w,h], "text":"", "backend":"none"})
            continue
        roi = bgr[y:y+h, x:x+w].copy()
        text, backend = _ocr_roi_multibackend(roi, cfg)
        results.append({"box":[x,y,w,h], "text": text, "backend": backend})
    return results
