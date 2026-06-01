"""Create visual diagnostics for BubMask-Fiji worker smoke outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image


def load_gray(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        arr = np.array(image)
    if arr.ndim == 3:
        arr = arr[:, :, 0]
    return arr


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def draw_boxes(ax, detections, color, limit=None, linewidth=0.8):
    for idx, det in enumerate(detections):
        if limit is not None and idx >= limit:
            break
        x, y, w, h = det["bbox"]
        rect = plt.Rectangle((x, y), w, h, fill=False, edgecolor=color, linewidth=linewidth)
        ax.add_patch(rect)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--adaptive", required=True)
    parser.add_argument("--maskrcnn", required=True)
    parser.add_argument("--outdir", required=True)
    args = parser.parse_args()

    image_path = Path(args.image)
    adaptive = load_json(Path(args.adaptive))
    maskrcnn = load_json(Path(args.maskrcnn))
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    image = load_gray(image_path)
    adaptive_masks = adaptive.get("masks", [])
    maskrcnn_masks = maskrcnn.get("masks", [])

    fig, axes = plt.subplots(1, 3, figsize=(18, 6), constrained_layout=True)
    for ax in axes:
        ax.imshow(image, cmap="gray")
        ax.set_axis_off()

    axes[0].set_title("Original TIFF")
    axes[1].set_title(f"Adaptive threshold candidates: {len(adaptive_masks)}")
    axes[2].set_title(f"BubMask Mask R-CNN detections: {len(maskrcnn_masks)}")

    draw_boxes(axes[1], adaptive_masks, color="yellow", limit=250, linewidth=0.45)
    draw_boxes(axes[2], maskrcnn_masks, color="lime", limit=None, linewidth=1.1)
    axes[1].text(
        8,
        image.shape[0] - 12,
        "Showing first 250 boxes to avoid total visual saturation",
        color="yellow",
        fontsize=9,
        bbox={"facecolor": "black", "alpha": 0.55, "pad": 4},
    )
    fig.savefig(outdir / "adaptive_vs_maskrcnn_overview.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 8), constrained_layout=True)
    ax.imshow(image, cmap="gray")
    ax.set_axis_off()
    ax.set_title(f"Adaptive threshold: first 250 / {len(adaptive_masks)} candidate boxes")
    draw_boxes(ax, adaptive_masks, color="yellow", limit=250, linewidth=0.5)
    fig.savefig(outdir / "adaptive_threshold_candidates_first250.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 8), constrained_layout=True)
    ax.imshow(image, cmap="gray")
    ax.set_axis_off()
    ax.set_title(f"BubMask Mask R-CNN: {len(maskrcnn_masks)} detection boxes")
    draw_boxes(ax, maskrcnn_masks, color="lime", limit=None, linewidth=1.1)
    fig.savefig(outdir / "maskrcnn_detections.png", dpi=180)
    plt.close(fig)

    print(outdir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
