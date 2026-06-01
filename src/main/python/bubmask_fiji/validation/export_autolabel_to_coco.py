"""Export BubMask auto-label predictions as a Roboflow COCO Segmentation import.

Input is the Round 3 autolabel manifest plus one review folder per image. The
export is intentionally a *pre-labelled review dataset*, not final ground truth:
Roboflow should be used to add missed bubbles, reshape masks, and delete false
positives before the next training round.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from bubmask_worker import load_image_array


def read_manifest(path: Path, limit: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if str(row.get("status", "")).strip() != "worker_ok":
                continue
            rows.append(row)
            if limit > 0 and len(rows) >= limit:
                break
    return rows


def safe_slug(value: str, max_len: int = 120) -> str:
    text = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)
    while "__" in text:
        text = text.replace("__", "_")
    text = text.strip("_")
    if len(text) > max_len:
        text = text[:max_len].rstrip("_")
    return text or "image"


def save_png_from_tif(source: Path, destination: Path) -> tuple[int, int]:
    image = load_image_array(source)
    Image.fromarray(image, mode="RGB").save(destination)
    height, width = image.shape[:2]
    return int(width), int(height)


def load_measurement_metadata(path: Path) -> dict[int, dict[str, str]]:
    if not path.is_file():
        return {}
    rows: dict[int, dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            try:
                bubble_id = int(float(row.get("bubble_id", "0")))
            except ValueError:
                continue
            if bubble_id > 0:
                rows[bubble_id] = row
    return rows


def polygon_from_contour(contour: np.ndarray, epsilon_px: float) -> list[float] | None:
    if epsilon_px > 0:
        contour = cv2.approxPolyDP(contour, epsilon_px, True)
    points = contour.reshape(-1, 2)
    if points.shape[0] < 3:
        return None
    polygon: list[float] = []
    for x, y in points:
        polygon.extend([float(x), float(y)])
    return polygon if len(polygon) >= 6 else None


def mask_to_polygons(mask: np.ndarray, epsilon_px: float) -> list[list[float]]:
    contours, _hierarchy = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    polygons: list[list[float]] = []
    for contour in contours:
        if cv2.contourArea(contour) < 3:
            continue
        polygon = polygon_from_contour(contour, epsilon_px)
        if polygon is not None:
            polygons.append(polygon)
    return polygons


def mask_bbox(mask: np.ndarray) -> list[float]:
    ys, xs = np.nonzero(mask)
    if xs.size == 0:
        return [0.0, 0.0, 0.0, 0.0]
    x0 = int(xs.min())
    y0 = int(ys.min())
    x1 = int(xs.max()) + 1
    y1 = int(ys.max()) + 1
    return [float(x0), float(y0), float(x1 - x0), float(y1 - y0)]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def zip_directory(source_dir: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in source_dir.rglob("*"):
            if path.is_file() and path != zip_path:
                archive.write(path, path.relative_to(source_dir.parent))


def export(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = Path(args.manifest).resolve()
    output_dir = Path(args.output_dir).resolve()
    if output_dir.exists() and args.overwrite:
        shutil.rmtree(output_dir)
    train_dir = output_dir / "train"
    train_dir.mkdir(parents=True, exist_ok=True)

    rows = read_manifest(manifest_path, args.limit)
    images: list[dict[str, Any]] = []
    annotations: list[dict[str, Any]] = []
    mapping_rows: list[dict[str, Any]] = []
    annotation_id = 1
    skipped_missing = 0
    skipped_empty_masks = 0

    for image_id, row in enumerate(rows, start=1):
        run_dir = Path(row["run_dir"])
        source_image = run_dir / "image.tif"
        labels_path = Path(row["instance_labels"])
        measurements_path = Path(row["per_bubble_csv"])
        if not source_image.is_file() or not labels_path.is_file():
            skipped_missing += 1
            continue

        file_name = f"{int(row['index']):05d}_{safe_slug(row['condition'])}_{safe_slug(source_image.stem, 70)}.png"
        png_path = train_dir / file_name
        width, height = save_png_from_tif(source_image, png_path)

        images.append({
            "id": image_id,
            "file_name": file_name,
            "width": width,
            "height": height,
            "source_image": row.get("source_image", ""),
            "autolabel_run_dir": str(run_dir),
            "condition": row.get("condition", ""),
        })

        labels = np.array(Image.open(labels_path))
        label_values = [int(value) for value in np.unique(labels) if int(value) > 0]
        if not label_values:
            skipped_empty_masks += 1
        measurements = load_measurement_metadata(measurements_path)

        image_annotation_count = 0
        for label_value in label_values:
            mask = labels == label_value
            area = int(mask.sum())
            if area < args.min_area_px:
                continue
            polygons = mask_to_polygons(mask, args.polygon_epsilon_px)
            if not polygons:
                continue
            metadata = measurements.get(label_value, {})
            annotation = {
                "id": annotation_id,
                "image_id": image_id,
                "category_id": 1,
                "segmentation": polygons,
                "area": float(area),
                "bbox": mask_bbox(mask),
                "iscrowd": 0,
                "source": "bubmask_autolabel_round3",
                "model_score": float(metadata.get("score", 0.0) or 0.0),
                "measurement_status": metadata.get("measurement_status", ""),
                "accepted_for_histogram": str(metadata.get("accepted_for_histogram", "")).lower() in {"true", "1"},
            }
            annotations.append(annotation)
            annotation_id += 1
            image_annotation_count += 1

        mapping_rows.append({
            "image_id": image_id,
            "file_name": file_name,
            "condition": row.get("condition", ""),
            "source_image": row.get("source_image", ""),
            "run_dir": row.get("run_dir", ""),
            "autolabel_detections": row.get("detections", ""),
            "coco_annotations": image_annotation_count,
            "overlay_masks": row.get("overlay_masks", ""),
        })

    coco = {
        "info": {
            "description": "BubMask-Fiji Round 3 auto-label predictions for Roboflow human review",
            "version": "round3_autolabel_250",
            "year": datetime.now().year,
            "date_created": datetime.now().isoformat(timespec="seconds"),
            "note": "Machine-generated candidate masks. Human review required before training.",
        },
        "licenses": [{"id": 1, "name": "UNSW internal research dataset", "url": ""}],
        "categories": [{"id": 1, "name": "bubble", "supercategory": "microbubble"}],
        "images": images,
        "annotations": annotations,
    }

    annotation_path = train_dir / "_annotations.coco.json"
    annotation_path.write_text(json.dumps(coco, indent=2), encoding="utf-8")
    write_csv(output_dir / "source_manifest_for_review.csv", mapping_rows)
    readme = output_dir / "README.md"
    readme.write_text(
        "\n".join([
            "# BubMask-Fiji Round 3 Roboflow Import",
            "",
            "This is a pre-labelled COCO Segmentation dataset generated from BubMask-Fiji auto-label predictions.",
            "It is intended for Roboflow human review: add missed bubbles, reshape masks, and delete false positives.",
            "",
            "Upload the ZIP to a Roboflow Instance Segmentation project as COCO Segmentation.",
            "",
            f"Images exported: {len(images)}",
            f"Annotations exported: {len(annotations)}",
            f"Skipped missing artifacts: {skipped_missing}",
            f"Images with empty masks: {skipped_empty_masks}",
            "",
            "Important: these are not final ground-truth masks until reviewed by a human.",
            "",
        ]),
        encoding="utf-8",
    )
    (output_dir / "labelmap.txt").write_text("0: background\n1: bubble\n", encoding="utf-8")
    (train_dir / "labelmap.txt").write_text("background\nbubble\n", encoding="utf-8")

    zip_path = output_dir.with_suffix(".zip")
    if args.zip:
        zip_directory(output_dir, zip_path)

    summary = {
        "images_requested": len(rows),
        "images_exported": len(images),
        "annotations_exported": len(annotations),
        "skipped_missing_artifacts": skipped_missing,
        "images_with_empty_masks": skipped_empty_masks,
        "output_dir": str(output_dir),
        "annotation_path": str(annotation_path),
        "zip_path": str(zip_path) if args.zip else "",
    }
    (output_dir / "export_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export auto-labelled masks to Roboflow COCO Segmentation.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--limit", type=int, default=250)
    parser.add_argument("--min-area-px", type=int, default=4)
    parser.add_argument("--polygon-epsilon-px", type=float, default=1.0)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--zip", action="store_true")
    args = parser.parse_args(argv)
    summary = export(args)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
