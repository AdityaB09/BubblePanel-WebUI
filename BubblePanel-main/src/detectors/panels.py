# src/detectors/panels.py

"""
Panel detection: Canny → dilate → external contours → filters.
Returns list of (x, y, w, h) in reading-ish order (top-to-bottom, left-to-right).
"""

from typing import List, Tuple

import cv2
import numpy as np


def detect_panels(bgr, cfg) -> List[Tuple[int, int, int, int]]:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    # bilateral to preserve edges but reduce speckle
    gray = cv2.bilateralFilter(gray, 7, 50, 50)

    e = cv2.Canny(
        gray,
        cfg.get("panel_canny1", 50),
        cfg.get("panel_canny2", 150),
    )
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    e = cv2.dilate(e, k, iterations=cfg.get("panel_dilate_iter", 2))

    contours, _ = cv2.findContours(e, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    boxes: List[Tuple[int, int, int, int]] = []
    min_area = int(cfg.get("panel_min_area", 5000))
    min_rectangularity = float(cfg.get("panel_min_rectangularity", 0.6))

    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w * h < min_area:
            continue
        area = cv2.contourArea(cnt)
        rect_area = float(w * h)
        rectangularity = area / (rect_area + 1e-6)
        if rectangularity < min_rectangularity:
            continue
        # avoid extreme skinny lines that aren't real panels
        aspect = max(w / max(h, 1), h / max(w, 1))
        if aspect > 15:
            continue
        boxes.append((x, y, w, h))

    # sort by rows (bucketed by y), then by x
    boxes = sorted(boxes, key=lambda b: (b[1] // 50, b[0]))
    return boxes
