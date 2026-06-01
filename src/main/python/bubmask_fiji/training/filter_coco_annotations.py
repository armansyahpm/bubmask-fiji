"""Create a conservative COCO training copy by removing suspicious annotations.

This does not modify the original Roboflow export. It creates a derivative
dataset for high-confidence bubble-only fine-tuning when the labelling tool is
no longer available.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

from bubmask_fiji.training.coco_dataset import find_coco_annotation_file
from bubmask_fiji.training.quality_check_coco_labels import annotation_mask, flags_for


DEFAULT_EXCLUDE_FLAGS = {
    "multi_component_instance",
    "possible_line_artifact",
    "low_mask_to_bbox_fill",
    "very_large_bbox",
    "tiny_mask",
}


def read_qc_flags(path: Path | None) -> dict[tuple[str, str], list[str]]:
    if path is None:
        return {}
    flags_by_annotation: dict[tuple[str, str], list[str]] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            split = str(row.get("split", "")).strip()
            annotation_id = str(row.get("annotation_id", "")).strip()
            flags = [flag for flag in str(row.get("flags", "")).split(";") if flag]
            if split and annotation_id:
                flags_by_annotation[(split, annotation_id)] = flags
    return flags_by_annotation


def copy_split(
    source_split: Path,
    output_split: Path,
    exclude_flags: set[str],
    qc_flags_by_annotation: dict[tuple[str, str], list[str]] | None = None,
) -> dict[str, Any]:
    output_split.mkdir(parents=True, exist_ok=True)
    coco = json.loads(find_coco_annotation_file(source_split).read_text(encoding="utf-8"))
    category_by_id = {int(category["id"]): str(category.get("name", "")).strip().lower() for category in coco["categories"]}
    image_by_id = {int(image["id"]): image for image in coco["images"]}

    kept_annotations = []
    removed_annotations = []
    flag_counts: Counter[str] = Counter()

    for image in coco["images"]:
        image_name = Path(image["file_name"]).name
        source_image = source_split / image_name
        if not source_image.exists():
            matches = list(source_split.rglob(image_name))
            if not matches:
                raise FileNotFoundError(f"Cannot find image {image_name} under {source_split}")
            source_image = matches[0]
        shutil.copy2(source_image, output_split / image_name)
        image["file_name"] = image_name

    next_annotation_id = 1
    for annotation in coco["annotations"]:
        category_name = category_by_id.get(int(annotation.get("category_id", -1)), "")
        if category_name != "bubble":
            removed_annotations.append({"id": annotation.get("id"), "reason": "non_bubble_category"})
            continue

        if qc_flags_by_annotation:
            flags = qc_flags_by_annotation.get((source_split.name, str(annotation.get("id"))), [])
            metrics = {}
        else:
            image = image_by_id[int(annotation["image_id"])]
            mask = annotation_mask(annotation, int(image["height"]), int(image["width"]))
            flags, metrics = flags_for(
                mask,
                annotation.get("bbox", [0, 0, 0, 0]),
                int(image["width"]),
                int(image["height"]),
            )
        for flag in flags:
            flag_counts[flag] += 1

        matching_exclusions = sorted(set(flags) & exclude_flags)
        if matching_exclusions:
            removed_annotations.append({
                "id": annotation.get("id"),
                "image_file": image["file_name"],
                "flags": flags,
                "excluded_by": matching_exclusions,
                **metrics,
            })
            continue

        kept = dict(annotation)
        kept["id"] = next_annotation_id
        kept["category_id"] = 1
        kept_annotations.append(kept)
        next_annotation_id += 1

    filtered_coco = {
        "info": coco.get("info", {}),
        "licenses": coco.get("licenses", []),
        "categories": [{"id": 1, "name": "bubble", "supercategory": "bubble"}],
        "images": coco["images"],
        "annotations": kept_annotations,
    }
    (output_split / "_annotations.coco.json").write_text(json.dumps(filtered_coco), encoding="utf-8")
    return {
        "split": source_split.name,
        "images": len(coco["images"]),
        "kept_bubble_annotations": len(kept_annotations),
        "removed_annotations": len(removed_annotations),
        "flag_counts": dict(flag_counts),
        "removed_preview": removed_annotations[:20],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="Input local split COCO dataset")
    parser.add_argument("--output", required=True, help="Output filtered COCO dataset")
    parser.add_argument(
        "--exclude-flags",
        default=",".join(sorted(DEFAULT_EXCLUDE_FLAGS)),
        help="Comma-separated QC flags to exclude from the training copy",
    )
    parser.add_argument(
        "--qc-report",
        default=None,
        help="Optional label_qc_report.csv to reuse precomputed flags instead of decoding every mask again.",
    )
    args = parser.parse_args()

    source = Path(args.source)
    output = Path(args.output)
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    exclude_flags = {flag.strip() for flag in args.exclude_flags.split(",") if flag.strip()}
    qc_flags_by_annotation = read_qc_flags(Path(args.qc_report)) if args.qc_report else {}

    split_summaries = []
    for split in ["train", "valid", "test"]:
        split_dir = source / split
        if split_dir.exists():
            split_summaries.append(copy_split(split_dir, output / split, exclude_flags, qc_flags_by_annotation))

    summary = {
        "source": str(source),
        "output": str(output),
        "excluded_flags": sorted(exclude_flags),
        "splits": split_summaries,
    }
    (output / "filter_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    md_lines = [
        "# Filtered COCO Dataset Summary",
        "",
        f"- Source: `{source}`",
        f"- Output: `{output}`",
        f"- Excluded flags: `{', '.join(sorted(exclude_flags))}`",
        "",
        "| Split | Images | Kept bubble annotations | Removed annotations |",
        "|---|---:|---:|---:|",
    ]
    for item in split_summaries:
        md_lines.append(
            f"| {item['split']} | {item['images']} | {item['kept_bubble_annotations']} | {item['removed_annotations']} |"
        )
    (output / "filter_summary.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
