"""Inspect a Roboflow COCO segmentation export for BubMask fine-tuning.

The script checks that images exist, annotations have usable segmentations,
and creates quick overlay images so humans can verify mask alignment before
training starts.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from bubmask_fiji.training.coco_dataset import decode_coco_rle


IMAGE_EXTENSIONS = {".bmp", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}


def _find_coco_files(dataset_dir: Path) -> list[Path]:
    files = list(dataset_dir.rglob("*annotations*.json")) + list(dataset_dir.rglob("*.coco.json"))
    return sorted({path.resolve(): path for path in files}.values())


def _polygon_points(segmentation: Any) -> list[list[tuple[float, float]]]:
    polygons: list[list[tuple[float, float]]] = []
    if not isinstance(segmentation, list):
        return polygons
    for polygon in segmentation:
        if not isinstance(polygon, list) or len(polygon) < 6:
            continue
        coords = [(float(polygon[i]), float(polygon[i + 1])) for i in range(0, len(polygon) - 1, 2)]
        polygons.append(coords)
    return polygons


def _locate_image(coco_path: Path, file_name: str) -> Path | None:
    candidates = [
        coco_path.parent / file_name,
        coco_path.parent / "images" / file_name,
        coco_path.parent.parent / file_name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    matches = list(coco_path.parent.rglob(Path(file_name).name))
    return matches[0] if matches else None


def _draw_overlay(image_path: Path, annotations: list[dict[str, Any]], output_path: Path) -> None:
    image = Image.open(image_path).convert("RGB")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    colors = [
        (32, 201, 151, 92),
        (255, 193, 7, 92),
        (0, 123, 255, 92),
        (220, 53, 69, 92),
        (111, 66, 193, 92),
    ]
    outlines = [(32, 201, 151, 230), (255, 193, 7, 230), (0, 123, 255, 230), (220, 53, 69, 230), (111, 66, 193, 230)]
    for idx, annotation in enumerate(annotations):
        color = colors[idx % len(colors)]
        outline = outlines[idx % len(outlines)]
        segmentation = annotation.get("segmentation")
        if isinstance(segmentation, dict):
            mask = decode_coco_rle(segmentation)
            mask_image = Image.fromarray((mask.astype(np.uint8) * 255), mode="L")
            color_image = Image.new("RGBA", image.size, color)
            overlay.alpha_composite(Image.composite(color_image, Image.new("RGBA", image.size, (0, 0, 0, 0)), mask_image))
        else:
            for polygon in _polygon_points(segmentation):
                draw.polygon(polygon, fill=color, outline=outline)
        bbox = annotation.get("bbox")
        if isinstance(bbox, list) and len(bbox) == 4:
            x, y, w, h = bbox
            draw.rectangle([x, y, x + w, y + h], outline=outline, width=2)
    result = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.save(output_path)


def inspect_dataset(dataset_dir: Path, sample_count: int, seed: int) -> dict[str, Any]:
    coco_files = _find_coco_files(dataset_dir)
    if not coco_files:
        raise FileNotFoundError(f"No COCO annotation JSON found under {dataset_dir}")

    report: dict[str, Any] = {
        "dataset_dir": str(dataset_dir),
        "coco_files": [],
        "total_images": 0,
        "total_annotations": 0,
        "trainable_bubble_annotations": 0,
        "ignored_nonbubble_annotations": 0,
        "total_categories": Counter(),
        "missing_image_files": [],
        "empty_segmentations": 0,
        "rle_segmentations": 0,
        "polygon_segmentations": 0,
        "annotations_without_bbox": 0,
        "annotations_per_image": {},
        "sanity_overlays": [],
    }

    rng = random.Random(seed)
    overlay_candidates: list[tuple[Path, list[dict[str, Any]], str]] = []

    for coco_path in coco_files:
        with coco_path.open("r", encoding="utf-8") as handle:
            coco = json.load(handle)

        images = coco.get("images", [])
        annotations = coco.get("annotations", [])
        categories = coco.get("categories", [])
        category_by_id = {category["id"]: category.get("name", str(category["id"])) for category in categories}
        ann_by_image: dict[int, list[dict[str, Any]]] = defaultdict(list)
        bubble_ann_by_image: dict[int, list[dict[str, Any]]] = defaultdict(list)

        for annotation in annotations:
            ann_by_image[int(annotation["image_id"])].append(annotation)
            category_name = category_by_id.get(annotation.get("category_id"), str(annotation.get("category_id")))
            report["total_categories"][category_name] += 1
            segmentation = annotation.get("segmentation")
            if not segmentation:
                report["empty_segmentations"] += 1
            elif isinstance(segmentation, dict):
                report["rle_segmentations"] += 1
            elif isinstance(segmentation, list):
                report["polygon_segmentations"] += 1
            if not annotation.get("bbox"):
                report["annotations_without_bbox"] += 1
            if category_name == "bubble":
                report["trainable_bubble_annotations"] += 1
                bubble_ann_by_image[int(annotation["image_id"])].append(annotation)
            else:
                report["ignored_nonbubble_annotations"] += 1

        split_name = coco_path.parent.name
        split_info = {
            "split": split_name,
            "annotation_file": str(coco_path),
            "images": len(images),
            "annotations": len(annotations),
            "categories": [category.get("name", str(category.get("id"))) for category in categories],
        }
        report["coco_files"].append(split_info)
        report["total_images"] += len(images)
        report["total_annotations"] += len(annotations)

        for image in images:
            image_id = int(image["id"])
            anns = ann_by_image.get(image_id, [])
            bubble_anns = bubble_ann_by_image.get(image_id, [])
            image_path = _locate_image(coco_path, image["file_name"])
            key = f"{split_name}/{image['file_name']}"
            report["annotations_per_image"][key] = len(anns)
            if image_path is None:
                report["missing_image_files"].append(key)
                continue
            if bubble_anns:
                overlay_candidates.append((image_path, bubble_anns, key))

    report["total_categories"] = dict(report["total_categories"])
    report["average_annotations_per_image"] = (
        report["total_annotations"] / report["total_images"] if report["total_images"] else 0.0
    )

    overlay_dir = dataset_dir / "sanity_overlays"
    rng.shuffle(overlay_candidates)
    for image_path, annotations, key in overlay_candidates[:sample_count]:
        output_name = Path(key).name
        output_path = overlay_dir / f"{Path(output_name).stem}_coco_overlay.png"
        _draw_overlay(image_path, annotations, output_path)
        report["sanity_overlays"].append(str(output_path))

    report_path = dataset_dir / "coco_inspection_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    md_lines = [
        "# Roboflow COCO Round 1 Inspection",
        "",
        f"- Dataset directory: `{dataset_dir}`",
        f"- COCO files found: {len(coco_files)}",
        f"- Images: {report['total_images']}",
        f"- Annotations: {report['total_annotations']}",
        f"- Trainable bubble annotations: {report['trainable_bubble_annotations']}",
        f"- Ignored non-bubble annotations: {report['ignored_nonbubble_annotations']}",
        f"- Average annotations/image: {report['average_annotations_per_image']:.2f}",
        f"- Categories: `{report['total_categories']}`",
        f"- Polygon segmentations: {report['polygon_segmentations']}",
        f"- RLE segmentations: {report['rle_segmentations']}",
        f"- Empty segmentations: {report['empty_segmentations']}",
        f"- Missing image files: {len(report['missing_image_files'])}",
        f"- Annotations without bbox: {report['annotations_without_bbox']}",
        "",
        "## Split Summary",
        "",
        "| Split | Images | Annotations | Categories |",
        "| --- | ---: | ---: | --- |",
    ]
    for item in report["coco_files"]:
        md_lines.append(
            f"| {item['split']} | {item['images']} | {item['annotations']} | {', '.join(item['categories'])} |"
        )
    md_lines.extend(["", "## Sanity Overlays", ""])
    for overlay in report["sanity_overlays"]:
        md_lines.append(f"- `{overlay}`")
    (dataset_dir / "coco_inspection_report.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, help="Path to extracted Roboflow COCO dataset")
    parser.add_argument("--sample-count", type=int, default=6, help="Number of sanity overlay PNGs to generate")
    parser.add_argument("--seed", type=int, default=13)
    args = parser.parse_args()

    report = inspect_dataset(Path(args.dataset), args.sample_count, args.seed)
    print(json.dumps(
        {
            "images": report["total_images"],
            "annotations": report["total_annotations"],
            "categories": report["total_categories"],
            "sanity_overlays": len(report["sanity_overlays"]),
            "missing_image_files": len(report["missing_image_files"]),
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
