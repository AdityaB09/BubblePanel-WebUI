# runner.py

import argparse, os, yaml

from src.common.utils import ensure_dir, imread, imwrite, draw_boxes, save_json
from src.detectors.panels import detect_panels
from src.detectors.bubbles import detect_bubbles_in_panel
from src.ocr.ocr import ocr_bubbles


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--config", default="config.yaml")
    args = ap.parse_args()

    with open(args.config, 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f)

    ensure_dir(args.out)

    bgr = imread(args.image)
    name = os.path.splitext(os.path.basename(args.image))[0]

    panel_boxes = detect_panels(bgr, cfg)
    bubble_boxes = []
    for p in panel_boxes:
        bubble_boxes.extend(detect_bubbles_in_panel(bgr, p, cfg))

    overlay = draw_boxes(
        bgr,
        panel_boxes,
        tuple(cfg.get('panel_color', [0, 102, 255])),
        cfg.get('box_thickness', 2)
    )
    overlay = draw_boxes(
        overlay,
        bubble_boxes,
        tuple(cfg.get('bubble_color', [0, 200, 0])),
        cfg.get('box_thickness', 2)
    )

    imwrite(os.path.join(args.out, f"{name}_overlay.png"), overlay)
    save_json(
        os.path.join(args.out, f"{name}_panels.json"),
        {"image": os.path.basename(args.image), "panels": [{"box": list(b)} for b in panel_boxes]}
    )
    save_json(
        os.path.join(args.out, f"{name}_bubbles.json"),
        {"image": os.path.basename(args.image), "bubbles": [{"box": list(b)} for b in bubble_boxes]}
    )
    save_json(
        os.path.join(args.out, f"{name}_ocr.json"),
        {"image": os.path.basename(args.image), "ocr": ocr_bubbles(bgr, bubble_boxes, cfg)}
    )

    print("[✓] Wrote:", os.path.join(args.out, f"{name}_overlay.png"))


if __name__ == "__main__":
    main()
