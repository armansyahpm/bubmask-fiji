"""Quality-check Roboflow COCO bubble annotations before fine-tuning."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from bubmask_fiji.training.coco_dataset import decode_coco_rle, find_coco_annotation_file


def polygon_mask(segmentation: list[Any], height: int, width: int) -> np.ndarray:
    mask = np.zeros((height, width), dtype=np.uint8)
    for polygon in segmentation:
        if not isinstance(polygon, list) or len(polygon) < 6:
            continue
        pts = np.asarray(polygon, dtype=np.float32).reshape(-1, 2).round().astype(np.int32)
        cv2.fillPoly(mask, [pts], 1)
    return mask.astype(bool)


def annotation_mask(annotation: dict[str, Any], height: int, width: int) -> np.ndarray:
    segmentation = annotation.get("segmentation")
    if isinstance(segmentation, dict):
        return decode_coco_rle(segmentation)
    if isinstance(segmentation, list):
        return polygon_mask(segmentation, height, width)
    return np.zeros((height, width), dtype=bool)


def flags_for(mask: np.ndarray, bbox: list[float], image_width: int, image_height: int) -> tuple[list[str], dict[str, Any]]:
    x, y, w, h = [float(v) for v in bbox]
    bbox_area = max(w * h, 1.0)
    image_area = float(image_width * image_height)
    mask_area = int(mask.sum())
    aspect_ratio = max(w / max(h, 1.0), h / max(w, 1.0))
    fill_ratio = mask_area / bbox_area
    components, _ = cv2.connectedComponents(mask.astype(np.uint8), connectivity=8)
    connected_components = max(0, components - 1)

    flags: list[str] = []
    if mask_area < 20:
        flags.append("tiny_mask")
    if aspect_ratio > 4:
        flags.append("extreme_bbox_aspect")
    if aspect_ratio > 8:
        flags.append("possible_line_artifact")
    if fill_ratio < 0.15:
        flags.append("low_mask_to_bbox_fill")
    if connected_components > 1:
        flags.append("multi_component_instance")
    if bbox_area / image_area > 0.05:
        flags.append("very_large_bbox")
    if x <= 0 or y <= 0 or (x + w) >= image_width - 1 or (y + h) >= image_height - 1:
        flags.append("border_touching_bbox")

    metrics = {
        "mask_area_px": mask_area,
        "bbox_area_px": round(bbox_area, 3),
        "bbox_width_px": round(w, 3),
        "bbox_height_px": round(h, 3),
        "aspect_ratio": round(aspect_ratio, 4),
        "mask_to_bbox_fill": round(fill_ratio, 4),
        "connected_components": connected_components,
    }
    return flags, metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    dataset_dir = Path(args.dataset)
    output_dir = Path(args.output) if args.output else dataset_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    flag_counts: Counter[str] = Counter()
    split_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()

    for split_dir in sorted(path for path in dataset_dir.iterdir() if path.is_dir() and path.name in {"train", "valid", "test"}):
        coco = json.loads(find_coco_annotation_file(split_dir).read_text(encoding="utf-8"))
        category_by_id = {int(category["id"]): str(category.get("name", "")).strip().lower() for category in coco["categories"]}
        image_by_id = {int(image["id"]): image for image in coco["images"]}

        for annotation in coco["annotations"]:
            category = category_by_id.get(int(annotation.get("category_id", -1)), "")
            category_counts[category] += 1
            if category != "bubble":
                continue
            image = image_by_id[int(annotation["image_id"])]
            height = int(image["height"])
            width = int(image["width"])
            mask = annotation_mask(annotation, height, width)
            flags, metrics = flags_for(mask, annotation.get("bbox", [0, 0, 0, 0]), width, height)
            for flag in flags:
                flag_counts[flag] += 1
            split_counts[split_dir.name] += 1
            rows.append({
                "split": split_dir.name,
                "image_file": image["file_name"],
                "annotation_id": annotation["id"],
                "flags": ";".join(flags),
                "flag_count": len(flags),
                **metrics,
            })

    csv_path = output_dir / "label_qc_report.csv"
    fieldnames = [
        "split", "image_file", "annotation_id", "flags", "flag_count",
        "mask_area_px", "bbox_area_px", "bbox_width_px", "bbox_height_px",
        "aspect_ratio", "mask_to_bbox_fill", "connected_components",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    flagged = sum(1 for row in rows if row["flag_count"])
    severe = sum(
        1 for row in rows
        if "multi_component_instance" in row["flags"]
        or "possible_line_artifact" in row["flags"]
        or "low_mask_to_bbox_fill" in row["flags"]
    )
    summary = {
        "dataset": str(dataset_dir),
        "bubble_annotations_checked": len(rows),
        "flagged_annotations": flagged,
        "severe_or_review_annotations": severe,
        "split_counts": dict(split_counts),
        "category_counts": dict(category_counts),
        "flag_counts": dict(flag_counts),
        "csv": str(csv_path),
    }
    (output_dir / "label_qc_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    md_lines = [
        "# COCO Label QC Summary",
        "",
        f"- Bubble annotations checked: {len(rows)}",
        f"- Flagged annotations: {flagged}",
        f"- Severe/review annotations: {severe}",
        "",
        "## Flag Counts",
        "",
        "| Flag | Count |",
        "|---|---:|",
    ]
    for flag, count in sorted(flag_counts.items()):
        md_lines.append(f"| `{flag}` | {count} |")
    md_lines.extend([
        "",
        "## Interpretation",
        "",
        "`multi_component_instance`, `possible_line_artifact`, and `low_mask_to_bbox_fill` are the most important labels to review before long training. They often indicate one annotation contains multiple disconnected bubbles, a line-like artifact, or a bounding box much larger than the actual mask.",
        "",
        f"Full CSV: `{csv_path}`",
    ])
    (output_dir / "label_qc_summary.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
