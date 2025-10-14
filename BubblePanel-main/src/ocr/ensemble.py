# src/ocr/ensemble.py
from __future__ import annotations
from typing import Dict, List, Tuple
import numpy as np

Word = Dict[str, object]  # {"box":[x,y,w,h], "text":str, "conf":float, "source":str}

def _iou(a, b) -> float:
    ax,ay,aw,ah = a; bx,by,bw,bh = b
    ax2, ay2 = ax+aw, ay+ah
    bx2, by2 = bx+bw, by+bh
    inter_w = max(0, min(ax2, bx2) - max(ax, bx))
    inter_h = max(0, min(ay2, by2) - max(ay, by))
    inter = inter_w * inter_h
    if inter == 0: return 0.0
    union = aw*ah + bw*bh - inter + 1e-6
    return inter / union

def merge_words(all_words: List[Word], iou_thr: float=0.5,
                prefer_longer_text: bool=True, conf_weighted_avg: bool=True) -> List[Word]:
    """Greedy IoU merge across engines into a single list."""
    if not all_words: return []
    # sort by confidence desc
    words = sorted(all_words, key=lambda w: float(w.get("conf", 0.0)), reverse=True)
    merged: List[Word] = []
    used = [False]*len(words)

    for i, wi in enumerate(words):
        if used[i]: continue
        group = [wi]
        used[i] = True
        for j in range(i+1, len(words)):
            if used[j]: continue
            wj = words[j]
            if _iou(wi["box"], wj["box"]) >= iou_thr:
                used[j] = True
                group.append(wj)

        # merge group
        if conf_weighted_avg:
            confs = np.array([float(w.get("conf",0.0)) for w in group], dtype=float)
            confs = np.clip(confs, 1e-6, None)
            xs = np.array([w["box"][0] for w in group], dtype=float)
            ys = np.array([w["box"][1] for w in group], dtype=float)
            ws = np.array([w["box"][2] for w in group], dtype=float)
            hs = np.array([w["box"][3] for w in group], dtype=float)
            wavg = lambda arr: float(np.sum(arr*confs)/np.sum(confs))
            box = [int(round(wavg(xs))), int(round(wavg(ys))),
                   int(round(wavg(ws))), int(round(wavg(hs)))]
            conf = float(np.max(confs))
        else:
            box = group[0]["box"]; conf = float(group[0].get("conf",0.0))

        # choose text
        texts = [str(w.get("text","")) for w in group if str(w.get("text","")).strip()]
        if prefer_longer_text and texts:
            text = max(texts, key=len)
        else:
            text = texts[0] if texts else ""

        merged.append({"box": box, "text": text, "conf": conf, "source": "+".join(sorted(set([w["source"] for w in group])))})
    return merged

def color_for_source(src: str) -> Tuple[int,int,int]:
    """BGR color to draw different backends."""
    if "rapidocr" in src:  return (0,255,0)
    if "paddleocr" in src: return (0,165,255)
    if "tesseract" in src: return (255,0,0)
    if "easyocr" in src:   return (180,0,180)
    return (0,200,200)
