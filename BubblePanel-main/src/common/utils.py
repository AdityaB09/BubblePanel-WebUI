# src/common/utils.py

"""
Utility helpers for I/O, drawing, and serialization.
- Unicode-safe imread/imwrite (works on Windows paths)
- Box drawing for debug overlays
- JSON save with UTF-8
"""

import os
import json
from typing import List, Tuple, Optional

import cv2
import numpy as np


def ensure_dir(path: str) -> None:
    """Create directory if it does not exist."""
    os.makedirs(path, exist_ok=True)


def imread(path: str) -> Optional[np.ndarray]:
    """
    Unicode-safe image read using imdecode.
    Returns BGR image or None if failed.
    """
    if not os.path.exists(path):
        return None
    data = np.fromfile(path, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    return img


def imwrite(path: str, img: np.ndarray) -> None:
    """
    Unicode-safe image write using imencode + tofile.
    Chooses encoder by extension; defaults to PNG if none.
    """
    ext = os.path.splitext(path)[1] or ".png"
    ok, buf = cv2.imencode(ext, img)
    if not ok:
        # fallback to PNG if the chosen encoder failed
        ok, buf = cv2.imencode(".png", img)
    buf.tofile(path)


def draw_boxes(
    img: np.ndarray,
    boxes: List[Tuple[int, int, int, int]],
    color: Tuple[int, int, int] = (0, 255, 0),
    thickness: int = 2,
    labels: Optional[List[str]] = None,
) -> np.ndarray:
    """
    Draws axis-aligned boxes (x, y, w, h) with optional string labels.
    Returns a copy with drawings (does not modify input).
    """
    out = img.copy()
    for i, (x, y, w, h) in enumerate(boxes):
        cv2.rectangle(out, (x, y), (x + w, y + h), color, thickness)
        if labels and i < len(labels):
            cv2.putText(
                out,
                str(labels[i]),
                (x, max(0, y - 5)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                1,
                cv2.LINE_AA,
            )
    return out


def save_json(path: str, data) -> None:
    """Save a Python object as pretty UTF-8 JSON."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
