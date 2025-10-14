from __future__ import annotations
from typing import List, Tuple, Dict
import os

Box = Tuple[int, int, int, int]  # (x,y,w,h)

def _center(b: Box):
    x, y, w, h = b
    return x + w / 2.0, y + h / 2.0

def _inside(b: Box, scope: Box) -> bool:
    cx, cy = _center(b)
    x, y, w, h = scope
    return (x <= cx <= x + w) and (y <= cy <= y + h)

def _sort_reading_order(boxes: List[Box]) -> List[Box]:
    # top→bottom, then left→right
    return sorted(boxes, key=lambda b: (b[1], b[0]))

def make_transcript(panel_boxes: List[Box],
                    bubble_boxes: List[Box],
                    ocr_res: List[Dict]):
    """
    Build (lines, text) transcript for a page.

    Returns:
      lines: List[str] like "Panel 1: HOW ARE YOU?"
      text:  single string joined by newlines
    """
    lines: List[str] = []
    # map bubble box -> its OCR text/backend
    text_by_box = {}
    for r in (ocr_res or []):
        text_by_box[tuple(r["box"])] = (r.get("text", ""), r.get("backend", ""))

    # sort panels in a stable reading order
    panels_ord = _sort_reading_order(panel_boxes)

    for p_idx, p in enumerate(panels_ord, 1):
        # bubbles that belong to this panel
        in_panel = [b for b in bubble_boxes if _inside(b, p)]
        in_panel = _sort_reading_order(in_panel)
        if not in_panel:
            continue
        lines.append(f"[Panel {p_idx}]")
        for b in in_panel:
            txt, backend = text_by_box.get(tuple(b), ("", ""))
            txt = (txt or "").strip()
            if not txt:
                continue
            lines.append(f"- {txt}  (via {backend})")
        lines.append("")  # blank line between panels

    text = "\n".join(lines).rstrip()
    return lines, text

def save_transcript(out_dir: str, page_name: str, text: str):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{page_name}_text.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text + ("\n" if text else ""))
    return path
