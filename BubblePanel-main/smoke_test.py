# smoke_test.py
"""
End-to-end smoke runner for the manga pipeline + summarizers.

Pipeline per image:
  1) Panel detection  → debug overlay
  2) Bubble detection (first pass)
  3) Reconciliation with FULL-PAGE OCR (prints coverage; adds fallback bubbles)
  4) OCR each bubble (multi-backend, first non-empty wins)
  5) Print a clean transcript to the terminal (panel → bubble order)
  6) Save:
       - overlays: *_panels.png, *_bubbles.png
       - JSON per page with boxes, OCR and transcript
       - TXT transcript per page
  7) JSONL append with panel records (for summarizers)

Optional summarizers:
  - Panel-level:
      --summarize                → summaries_text.jsonl (LLM on bubbles)
      --summarize + --ollama-vlm → summaries_vlm.jsonl (VLM on bubbles; respect --vlm-no-image)
  - Page-level (paragraph scene):
      --page-summarize --paragraph
        • Text LLM               → summaries_page_text_paragraph.jsonl
        • VLM (text-only)        → summaries_page_vlm_paragraph.jsonl
        • Extractive (no model)  → summaries_page_extractive_paragraph.jsonl
        • Encoder-only           → summaries_page_encoder_paragraph.jsonl  (SentenceTransformer)
  - Page-level (novel style):
      --page-summarize --novel
        • Text LLM               → summaries_page_text_novel.jsonl
        • VLM (text-only)        → summaries_page_vlm_novel.jsonl
"""

import argparse
import glob
import json
import os
from typing import List, Dict

import cv2
import yaml

# --- project imports (existing) ---
from src.common.utils import ensure_dir, imread, imwrite, draw_boxes, save_json
from src.detectors.panels import detect_panels
from src.detectors.bubbles import detect_bubbles_in_panel
from src.pipeline.reconcile import reconcile_page
from src.ocr.ocr import ocr_bubbles
from src.common.transcript import make_transcript, save_transcript

# Summarizers (new/updated)
from src.llm.summarize import (
    summarize_text_jsonl,
    summarize_vlm_jsonl,                 # panel-level; now supports use_image=False
    summarize_text_pages_paragraph,       # page paragraphs (text LLM)
    summarize_vlm_pages_paragraph,        # page paragraphs (VLM text-only + text fallback)
    summarize_text_pages_novel,           # novel mode (text LLM)
    summarize_vlm_pages_novel,            # novel mode (VLM text-only)
)

# Optional: third & fourth strategies (import guarded, so script still runs if modules absent)
try:
    from src.llm.extractive import summarize_pages_extractive      # 3rd strategy (no model)
    _EXTRACTIVE_OK = True
except Exception:
    _EXTRACTIVE_OK = False

try:
    from src.llm.encoder_summarizer import summarize_pages_encoder  # 4th strategy (encoder-only)
    _ENCODER_OK = True
except Exception:
    _ENCODER_OK = False

# Optional helpers for ALL-OCR diagnostics (overlay + JSON). Guarded if missing.
try:
    from src.ocr.backends import run_backend           # returns List[{"box":[x,y,w,h],"text":str,"conf":float,"source":str}]
    from src.ocr.ensemble import merge_words, color_for_source
    _ALL_OCR_AVAILABLE = True
except Exception:
    _ALL_OCR_AVAILABLE = False


# -------------------- small helpers --------------------

def list_images(path_or_dir: str) -> List[str]:
    """Return a sorted list of image paths (or the single path if a file)."""
    if os.path.isdir(path_or_dir):
        files = []
        for ext in ("*.png", "*.jpg", "*.jpeg", "*.bmp", "*.tif", "*.tiff"):
            files.extend(glob.glob(os.path.join(path_or_dir, ext)))
        return sorted(files)
    return [path_or_dir]

def safe_dbg_dirs(input_path: str):
    """
    Build Windows-safe debug folder names near the input.
    If input is a folder: <parent>\<basename>_panels_dbg / _bubbles_dbg
    If input is a file:   <parent>\<file_stem>_panels_dbg / _bubbles_dbg
    """
    inp = input_path.rstrip("/\\")
    if os.path.isdir(inp):
        base_dir = os.path.dirname(inp) or "."
        base_name = os.path.basename(inp) or "input"
    else:
        base_dir = os.path.dirname(inp) or "."
        base_name = os.path.splitext(os.path.basename(inp))[0] or "input"
    return (
        os.path.join(base_dir, f"{base_name}_panels_dbg"),
        os.path.join(base_dir, f"{base_name}_bubbles_dbg"),
    )


# -------------------- core processing --------------------

def process_image(path: str, args, dbg_panels_dir: str, dbg_bubbles_dir: str, cfg: Dict) -> Dict:
    """
    Process one image and return a panel record dict for JSONL.
    """
    name = os.path.splitext(os.path.basename(path))[0]
    bgr = imread(path)
    if bgr is None:
        print(f"[!] Failed to read {path}")
        return {}

    # 1) Panel detection
    panel_boxes = detect_panels(bgr, cfg)
    overlay_panels = draw_boxes(
        bgr,
        panel_boxes,
        tuple(cfg.get("panel_color", [0, 102, 255])),
        int(cfg.get("box_thickness", 2)),
        labels=[f"P{i}" for i in range(len(panel_boxes))],
    )
    imwrite(os.path.join(dbg_panels_dir, f"{name}_panels.png"), overlay_panels)

    # 2) Bubble detection (first pass)
    bubble_boxes = []
    for p_box in panel_boxes:
        bubble_boxes.extend(detect_bubbles_in_panel(bgr, p_box, cfg))

    # 3) Reconcile with FULL-PAGE OCR (also does fallback words→bubbles)
    bubble_boxes = reconcile_page(bgr, panel_boxes, bubble_boxes, cfg, verbose=args.recon_verbose)

    # 4) Debug overlay for bubbles
    overlay_bubbles = draw_boxes(
        bgr,
        bubble_boxes,
        tuple(cfg.get("bubble_color", [0, 200, 0])),
        int(cfg.get("box_thickness", 2)),
        labels=[f"B{i}" for i in range(len(bubble_boxes))],
    )
    imwrite(os.path.join(dbg_bubbles_dir, f"{name}_bubbles.png"), overlay_bubbles)

    # 5) Optional: ALL-OCR diagnostics for the full page
    per_backend_json = {}
    merged_words = []
    if args.all_ocr:
        if not _ALL_OCR_AVAILABLE:
            print("[ALL-OCR] Skipped — backends/ensemble helpers not found.")
        else:
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            ocrc = cfg.get("ocr", {})
            backends = ocrc.get("backends", ["rapidocr", "paddleocr", "tesseract", "easyocr"])
            print(f"[ALL-OCR] backends={backends}")
            all_words = []
            for be in backends:
                try:
                    words = run_backend(gray, be, cfg, verbose=args.ocr_verbose) or []
                    print(f"[ALL-OCR] {be}: {len(words)} words")
                    per_backend_json[be] = words
                    all_words.extend(words)
                except Exception as e:
                    print(f"[ALL-OCR] {be}: ERROR {e}")

            if all_words:
                iou_thr = float(ocrc.get("merge_iou", 0.5))
                merged_words = merge_words(
                    all_words,
                    iou_thr=iou_thr,
                    prefer_longer_text=bool(ocrc.get("prefer_longer_text", True)),
                    conf_weighted_avg=bool(ocrc.get("conf_weighted_avg", True)),
                )
                # Save overlay
                merged_overlay = bgr.copy()
                for w in merged_words:
                    x, y, w_, h_ = w["box"]
                    color = color_for_source(str(w.get("source", "")))
                    cv2.rectangle(merged_overlay, (x, y), (x + w_, y + h_), color, 2)
                imwrite(os.path.join(args.out, f"{name}_allocr.png"), merged_overlay)
                # Save JSON
                save_json(os.path.join(args.out, f"{name}_allocr.json"), {
                    "image": os.path.basename(path),
                    "per_backend": per_backend_json,
                    "merged": merged_words,
                })

    # 6) OCR inside final bubbles
    ocr_res = []
    if not args.no_ocr:
        try:
            ocr_res = ocr_bubbles(bgr, bubble_boxes, cfg) or []
        except Exception as e:
            print(f"[WARN] OCR over bubbles failed ({e}); continuing without text.")
            ocr_res = []

    # 7) Build + print transcript (terminal) and save as TXT
    lines, text = make_transcript(panel_boxes, bubble_boxes, ocr_res)
    if text:
        print(f"[TEXT] {name} transcript:")
        for ln in lines:
            print("   " + ln)
    else:
        print(f"[TEXT] {name}: (no bubble text)")
    txt_path = save_transcript(args.out, name, text)

    # 8) Save JSON record (per page)
    outrec = {
        "image": os.path.basename(path),
        "page_id": name,
        "panels":  [{"box": list(map(int, b))} for b in panel_boxes],
        "bubbles": [{"box": list(map(int, b))} for b in bubble_boxes],
        "ocr":     ocr_res,
        "transcript": lines,
        "transcript_txt": os.path.basename(txt_path),
    }
    if merged_words:
        outrec["page_ocr_merged"] = merged_words
    if per_backend_json:
        outrec["page_ocr_per_backend_counts"] = {k: len(v) for k, v in per_backend_json.items()}
    save_json(os.path.join(args.out, f"{name}.json"), outrec)

    print(f"[-] {name}: panels={len(panel_boxes)}, bubbles={len(bubble_boxes)}")

    # Return a panel record list suitable for JSONL (one entry per panel)
    # For simplicity, we create one panel entry per page (joining bubbles) so page grouping works.
    # If your pipeline already writes true panel records elsewhere, adapt accordingly.
    panel_record = {
        "page_index": args._page_counter,
        "page_id": name,
        "panel_index": 0,
        "image_path": path,
        "panel_crop": None,  # if you save crops, set the path here
        "bubbles": [ln.strip(" -") for ln in lines if ln.strip().startswith("-")]
    }
    return panel_record


# -------------------- CLI --------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Folder with page images OR a single image path")
    ap.add_argument("--out", required=True, help="Output folder (overlays + JSON + TXT)")
    ap.add_argument("--config", default="config.yaml", help="YAML config file")

    # pipeline toggles
    ap.add_argument("--no-ocr", action="store_true", help="Skip OCR over detected bubbles")
    ap.add_argument("--recon-verbose", action="store_true", help="Verbose logs for page-level reconciliation")
    ap.add_argument("--all-ocr", action="store_true", help="Run full-page ALL-OCR diagnostics (if helpers exist)")
    ap.add_argument("--ocr-verbose", action="store_true", help="Verbose per-backend logs for --all-ocr")

    # summarizer toggles
    ap.add_argument("--jsonl", default="panels.jsonl", help="Filename for panels JSONL")
    ap.add_argument("--save-crops", action="store_true", help="(Optional) Save panel crops for VLMs")

    ap.add_argument("--summarize", action="store_true", help="Run PANEL-level summaries (text + optional VLM)")
    ap.add_argument("--ollama-text", dest="ollama_text", default="qwen2.5:7b-instruct", help="Text LLM model name")
    ap.add_argument("--ollama-vlm",  dest="ollama_vlm",  default=None, help="VLM model name")
    ap.add_argument("--host", default="http://127.0.0.1:11434", help="Ollama host base URL")

    ap.add_argument("--vlm-no-image", action="store_true",
                    help="Do NOT send images to the VLM (panel-level too).")

    # page-level modes
    ap.add_argument("--page-summarize", action="store_true", help="Also produce page-level summaries from panels JSONL")
    ap.add_argument("--paragraph", action="store_true", help="Write page summaries as a scene paragraph")
    ap.add_argument("--novel", action="store_true", help="Write page summaries as a cinematic novel paragraph")

    # 3rd strategy (extractive, no model)
    ap.add_argument("--extractive", action="store_true",
                    help="Run fast extractive page paragraphs (no model).")

    # 4th strategy (encoder-only)
    ap.add_argument("--encoder", action="store_true",
                    help="Run encoder-based semantic page paragraphs (SentenceTransformer).")
    ap.add_argument("--embed-model", default="sentence-transformers/all-mpnet-base-v2",
                    help="SentenceTransformer model name for encoder summarizer.")
    ap.add_argument("--mlm-refiner", action="store_true",
                    help="Enable optional masked-LM polish for encoder summarizer.")
    ap.add_argument("--mlm-model", default="distilroberta-base",
                    help="Masked language model name (used only with --mlm-refiner).")

    args = ap.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    ensure_dir(args.out)
    dbg_panels_dir, dbg_bubbles_dir = safe_dbg_dirs(args.input)
    ensure_dir(dbg_panels_dir)
    ensure_dir(dbg_bubbles_dir)

    images = list_images(args.input)
    if not images:
        print(f"[!] No images found in {args.input}")
        return

    # Process images → per-page JSON and gather panel records for JSONL
    args._page_counter = 0
    panel_rows: List[Dict] = []
    for p in images:
        print(f"[+] Processing {p}")
        rec = process_image(p, args, dbg_panels_dir, dbg_bubbles_dir, cfg)
        if rec:
            panel_rows.append(rec)
        args._page_counter += 1

    # Write panels.jsonl
    jsonl_path = os.path.join(args.out, args.jsonl)
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for row in panel_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"[√] JSONL → {jsonl_path}")

    # -------------- PANEL-LEVEL SUMMARIES --------------
    host = args.host
    ollama_text = args.ollama_text
    ollama_vlm  = args.ollama_vlm

    if args.summarize:
        # Text LLM panel summaries
        out_text = os.path.join(args.out, "summaries_text.jsonl")
        print("[summarize] starting PANEL TEXT summaries…")
        summarize_text_jsonl(jsonl_in=jsonl_path, jsonl_out=out_text, model=ollama_text, host=host)
        print(f"[√] Text summaries → {out_text}")

        # VLM panel summaries (respect --vlm-no-image)
        if ollama_vlm:
            out_vlm = os.path.join(args.out, "summaries_vlm.jsonl")
            print("[summarize] starting PANEL VLM summaries (image if available)…")
            summarize_vlm_jsonl(jsonl_in=jsonl_path, jsonl_out=out_vlm,
                                model=ollama_vlm, host=host, use_image=not args.vlm_no_image)
            print(f"[√] VLM summaries → {out_vlm}")

    # -------------- PAGE-LEVEL SUMMARIES --------------
    if args.page_summarize:
        # Paragraph mode
        if args.paragraph:
            # TEXT paragraphs
            out_para_text = os.path.join(args.out, "summaries_page_text_paragraph.jsonl")
            print("[summarize] starting TEXT page paragraphs…")
            summarize_text_pages_paragraph(jsonl_in=jsonl_path, jsonl_out=out_para_text,
                                           model=ollama_text, host=host)
            print(f"[√] Page TEXT paragraphs → {out_para_text}")

            # VLM paragraphs (text-only; includes fallback to text LLM if needed)
            if ollama_vlm:
                out_para_vlm = os.path.join(args.out, "summaries_page_vlm_paragraph.jsonl")
                print("[summarize] starting VLM page paragraphs (text-only)…")
                summarize_vlm_pages_paragraph(jsonl_in=jsonl_path, jsonl_out=out_para_vlm,
                                              model=ollama_vlm, host=host)
                print(f"[√] Page VLM (text-only) paragraphs → {out_para_vlm}")

            # 3rd strategy (extractive)
            if args.extractive:
                if not _EXTRACTIVE_OK:
                    print("[extractive] SKIPPED (module not available)")
                else:
                    out_para_extr = os.path.join(args.out, "summaries_page_extractive_paragraph.jsonl")
                    print("[summarize] starting EXTRACTIVE page paragraphs…")
                    summarize_pages_extractive(jsonl_in=jsonl_path, jsonl_out=out_para_extr)
                    print(f"[√] Page EXTRACTIVE paragraphs → {out_para_extr}")

            # 4th strategy (encoder-only)
            if args.encoder:
                if not _ENCODER_OK:
                    print("[encoder] SKIPPED (module not available)")
                else:
                    out_para_enc = os.path.join(args.out, "summaries_page_encoder_paragraph.jsonl")
                    print("[summarize] starting ENCODER page paragraphs…")
                    summarize_pages_encoder(
                        jsonl_in=jsonl_path,
                        jsonl_out=out_para_enc,
                        embed_model_name=args.embed_model,
                        use_mlm_refiner=args.mlm_refiner,
                        mlm_model_name=args.mlm_model,
                    )
                    print(f"[√] Page ENCODER paragraphs → {out_para_enc}")

            # Terminal preview (TEXT + VLM paragraphs if present)
            def _preview(path: str, label: str):
                if not os.path.exists(path): return
                print(f"\n[PAGE OUTPUT] {os.path.basename(path)}")
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        for i, line in enumerate(f):
                            if i >= 12: break
                            obj = json.loads(line)
                            mid = obj.get("model", "?")
                            pid = obj.get("page_id", "?")
                            para = (obj.get("paragraph", "") or "").strip()
                            print(f" - {pid} [{mid}]: {para[:300]}")
                except Exception:
                    pass

            _preview(out_para_text, "TEXT")
            if ollama_vlm:
                _preview(out_para_vlm, "VLM")
            if args.extractive and _EXTRACTIVE_OK:
                _preview(out_para_extr, "EXTRACTIVE")
            if args.encoder and _ENCODER_OK:
                _preview(out_para_enc, "ENCODER")

        # Novel mode
        if args.novel:
            out_novel_text = os.path.join(args.out, "summaries_page_text_novel.jsonl")
            print("[summarize] starting TEXT page NOVEL…")
            summarize_text_pages_novel(jsonl_in=jsonl_path, jsonl_out=out_novel_text,
                                       model=ollama_text, host=host)
            print(f"[√] Page TEXT NOVEL → {out_novel_text}")

            if args.ollama_vlm:
                out_novel_vlm = os.path.join(args.out, "summaries_page_vlm_novel.jsonl")
                print("[summarize] starting VLM page NOVEL (text-only)…")
                summarize_vlm_pages_novel(jsonl_in=jsonl_path, jsonl_out=out_novel_vlm,
                                          model=args.ollama_vlm, host=host)
                print(f"[√] Page VLM NOVEL (text-only) → {out_novel_vlm}")

            # Preview
            def _preview_novel(path: str):
                if not os.path.exists(path): return
                print(f"\n[PAGE OUTPUT NOVEL] {os.path.basename(path)}")
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        for i, line in enumerate(f):
                            if i >= 8: break
                            obj = json.loads(line)
                            pid = obj.get("page_id", "?")
                            mid = obj.get("novel_model", "?")
                            dlg = obj.get("cleaned_dialogue", []) or []
                            para = (obj.get("scene_paragraph", "") or "").strip()
                            for d in dlg[:4]:
                                print(f"    • {d}")
                            print(f"    ¶ {para[:260]}\n")
                except Exception:
                    pass

            _preview_novel(out_novel_text)
            if args.ollama_vlm:
                _preview_novel(out_novel_vlm)

    print(f"[√] Done. Outputs → {args.out}")
    print(f"Panels dbg → {dbg_panels_dir}")
    print(f"Bubbles dbg → {dbg_bubbles_dir}")


if __name__ == "__main__":
    main()
