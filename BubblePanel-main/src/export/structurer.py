# src/export/structurer.py
# Build per-panel JSONL records from your detected boxes + OCR results.
from __future__ import annotations
import os
from typing import List, Dict, Tuple, Any, Optional
import cv2
import numpy as np

def _center(box: Tuple[int,int,int,int]) -> Tuple[float,float]:
    x,y,w,h = box
    return (x + w/2.0, y + h/2.0)

def _contains(panel_box: Tuple[int,int,int,int], bubble_box: Tuple[int,int,int,int]) -> bool:
    px,py,pw,ph = panel_box
    bx,by,bw,bh = bubble_box
    return (bx >= px) and (by >= py) and (bx + bw <= px + pw) and (by + bh <= py + ph)

def _y_then_x_key(box: Tuple[int,int,int,int]):
    x,y,w,h = box
    return (y, x)

def _crop_and_save(bgr: np.ndarray, box: Tuple[int,int,int,int], out_dir: str, page_index: int, panel_index: int) -> str:
    x,y,w,h = box
    H,W = bgr.shape[:2]
    x = max(0, min(x, W-1)); y = max(0, min(y, H-1))
    w = max(1, min(w, W-x)); h = max(1, min(h, H-y))
    crop = bgr[y:y+h, x:x+w].copy()
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"page_{page_index:04d}_panel_{panel_index:02d}.png")
    cv2.imwrite(out, crop)
    return out

def _bubble_texts_for_panel(panel_box, bubble_boxes, ocr_res) -> List[str]:
    """Assign bubbles to panel via containment; order by top->down, left->right; collect OCR text."""
    pairs = []
    for i, b in enumerate(bubble_boxes):
        if _contains(panel_box, b):
            pairs.append((b, i))
    # order
    pairs.sort(key=lambda t: _y_then_x_key(t[0]))

    texts = []
    for _, idx in pairs:
        # ocr_res is a list aligned to bubble_boxes order (your ocr_bubbles returns in that order)
        text = ""
        if ocr_res and idx < len(ocr_res):
            # ocr_res[idx] may be {"text": "...", ...} or list of candidates; be defensive:
            rec = ocr_res[idx]
            if isinstance(rec, dict):
                text = (rec.get("text") or "").strip()
            elif isinstance(rec, str):
                text = rec.strip()
        if text:
            texts.append(text)
    return texts

def build_panel_records(
    image_path: str,
    page_index: int,
    page_id: str,
    bgr: np.ndarray,
    panel_boxes: List[Tuple[int,int,int,int]],
    bubble_boxes: List[Tuple[int,int,int,int]],
    ocr_res: List[Dict[str,Any]],
    save_crops: bool,
    crops_dir: Optional[str] = None,
) -> List[Dict[str,Any]]:
    """
    Returns list of dicts:
      {
        "page_index": int,
        "page_id": str,
        "panel_index": int,
        "image_path": str,
        "panel_box": [x,y,w,h],
        "panel_crop": str or None,
        "bubbles": [ "line1", "line2", ... ]  # ordered
      }
    """
    recs: List[Dict[str,Any]] = []
    for i, pbox in enumerate(panel_boxes, start=1):
        texts = _bubble_texts_for_panel(pbox, bubble_boxes, ocr_res)
        crop_path = None
        if save_crops and crops_dir:
            crop_path = _crop_and_save(bgr, pbox, crops_dir, page_index, i)

        recs.append({
            "page_index": page_index,
            "page_id": page_id,
            "panel_index": i,
            "image_path": image_path,
            "panel_box": list(map(int, pbox)),
            "panel_crop": crop_path,
            "bubbles": texts,
        })
    return recs
