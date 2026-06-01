#!/usr/bin/env python3
"""Build the Phase 3 UNSW validation manifest from local TIFF samples.

This script inventories the real TIFF image pool, records the temporary
calibration assumption, and creates a stratified first-pass annotation subset.
It does not create ground truth; human-reviewed masks and boxes are still
required for validation.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from PIL import Image


LABELS = [
    ("bubble_valid", "Sharp measurable bubble; include in bubble-size validation."),
    ("bubble_blurred_ignore", "Likely bubble but too blurred for reliable sizing."),
    ("nonbubble_artifact", "Cloud, stain, dirt, optical shadow, or false texture."),
    ("bubble_border_partial", "Bubble touches image or field-of-view border."),
    ("bubble_overlap_reconstruct", "Bubble needs circle/ellipse reconstruction."),
    ("saturated_highlight", "Bright glare/highlight region that should be flagged."),
    ("particle", "Solid particle; not a bubble and not included in bubble-size histogram."),
    ("bubble_particle_overlap_review", "Bubble and particle overlap or touch; requires review."),
]


def safe_id(text: str) -> str:
    out = []
    for ch in text:
        if ch.isalnum():
            out.append(ch.lower())
        elif ch in {"-", "_", "."}:
            out.append("_")
        else:
            out.append("_")
    value = "".join(out)
    while "__" in value:
        value = value.replace("__", "_")
    return value.strip("_")


def flow_rate_from_text(text: str) -> str:
    match = re.search(r"_(\d+)-(\d+)lpm", text.lower())
    if not match:
        return ""
    return f"{match.group(1)}.{match.group(2)} LPM"


def pressure_from_text(text: str) -> str:
    match = re.search(r"bubble_(\d+)atm", text.lower())
    return f"{match.group(1)} atm" if match else ""


def vent_from_text(text: str) -> str:
    match = re.search(r"_(\d+)vent_", text.lower())
    return match.group(1) if match else ""


def aperture_from_text(text: str) -> str:
    match = re.search(r"_(\d+)-(\d+)mm_", text.lower())
    if not match:
        return ""
    return f"{match.group(1)}.{match.group(2)} mm"


def particle_condition_from_text(text: str) -> str:
    match = re.search(r"withparticle(\d+)-(\d+)", text.lower())
    if not match:
        return ""
    return f"{match.group(1)}.{match.group(2)}"


def particle_class_from_path(path: Path) -> str:
    parts = {part.lower() for part in path.parts}
    if "with_particle" in parts:
        return "with_particle"
    if "without_particle" in parts:
        return "without_particle"
    if "testing_old" in parts:
        return "testing_old"
    return "unknown"


def experiment_group_from_path(path: Path, source_dir: Path) -> str:
    rel_parts = path.relative_to(source_dir).parts
    if len(rel_parts) >= 2:
        return rel_parts[1]
    if len(rel_parts) == 1:
        return Path(rel_parts[0]).parent.name
    return ""


def read_image_size(path: Path) -> tuple[int, int, str, str]:
    with Image.open(path) as image:
        return image.width, image.height, str(image.mode), str(image.format)


def iter_tiffs(source_dir: Path) -> list[Path]:
    paths = sorted(source_dir.rglob("*.tif")) + sorted(source_dir.rglob("*.tiff"))
    return [
        path for path in paths
        if particle_class_from_path(path) in {"with_particle", "without_particle"}
    ]


def image_rows(source_dir: Path, project_root: Path, px_per_mm: float) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in iter_tiffs(source_dir):
        rel = path.resolve().relative_to(project_root.resolve()).as_posix()
        particle_class = particle_class_from_path(path)
        group = experiment_group_from_path(path, source_dir)
        combined_text = f"{group}_{path.name}"
        width, height, mode, image_format = read_image_size(path)
        image_id = safe_id(f"{particle_class}_{group}_{path.stem}")
        rows.append({
            "image_id": image_id,
            "relative_path": rel,
            "particle_class": particle_class,
            "experiment_group": group,
            "particle_condition": particle_condition_from_text(combined_text),
            "flow_rate": flow_rate_from_text(combined_text),
            "pressure": pressure_from_text(combined_text),
            "vent_count": vent_from_text(combined_text),
            "aperture": aperture_from_text(combined_text),
            "width_px": str(width),
            "height_px": str(height),
            "image_mode": mode,
            "image_format": image_format,
            "calibration_status": "assumed",
            "calibration_source": "temporary_project_assumption",
            "px_per_mm": f"{px_per_mm:g}",
            "pixel_width_mm": f"{1.0 / px_per_mm:.10f}",
            "pixel_height_mm": f"{1.0 / px_per_mm:.10f}",
            "background_image": "",
            "annotation_status": "not_started",
            "annotation_required": "boxes_and_masks",
            "target_annotation_count": "5 objects",
            "priority": "pool",
            "required_case_tags": (
                "sharp;blur;artifact;highlight;border;overlap;particle"
                if particle_class == "with_particle"
                else "sharp;blur;artifact;highlight;border;overlap"
            ),
            "notes": "Calibration px/mm is assumed for now and must be replaced by final ruler calibration.",
        })
    return rows


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def stratified_subset(rows: list[dict[str, str]], per_group: int) -> list[dict[str, str]]:
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        key = (row["particle_class"], row["experiment_group"])
        groups[key].append(row)
    selected: list[dict[str, str]] = []
    for key in sorted(groups):
        group_rows = groups[key]
        count = min(per_group, len(group_rows))
        if count <= 0:
            continue
        if count == 1:
            picks = [group_rows[0]]
        else:
            indexes = sorted({round(i * (len(group_rows) - 1) / (count - 1)) for i in range(count)})
            picks = [group_rows[int(idx)] for idx in indexes]
        for row in picks:
            out = dict(row)
            out["priority"] = "phase3_annotation_subset"
            out["target_annotation_count"] = "5 objects"
            selected.append(out)
    return selected


def annotation_tasks(selected_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in selected_rows:
        if row["particle_class"] == "with_particle":
            target_labels = (
                "bubble_valid;bubble_blurred_ignore;nonbubble_artifact;"
                "particle;bubble_particle_overlap_review;saturated_highlight"
            )
        else:
            target_labels = (
                "bubble_valid;bubble_blurred_ignore;nonbubble_artifact;"
                "bubble_border_partial;bubble_overlap_reconstruct;saturated_highlight"
            )
        rows.append({
            "image_id": row["image_id"],
            "relative_path": row["relative_path"],
            "particle_class": row["particle_class"],
            "experiment_group": row["experiment_group"],
            "target_objects": "5",
            "required_annotation_geometry": "box_and_mask",
            "target_labels": target_labels,
            "annotation_status": "not_started",
            "annotator": "",
            "reviewer": "",
            "notes": "Use model overlay as suggestion only; final label must be human-confirmed.",
        })
    return rows


def write_summary(path: Path, rows: list[dict[str, str]], selected: list[dict[str, str]], px_per_mm: float) -> None:
    counts: dict[str, int] = defaultdict(int)
    selected_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[f'{row["particle_class"]}::{row["experiment_group"]}'] += 1
    for row in selected:
        selected_counts[f'{row["particle_class"]}::{row["experiment_group"]}'] += 1
    summary = {
        "schema_version": "bubmask.phase3_validation_summary.v1",
        "px_per_mm_assumption": px_per_mm,
        "calibration_status": "assumed",
        "total_images": len(rows),
        "selected_annotation_images": len(selected),
        "target_objects_per_selected_image": 5,
        "estimated_first_pass_annotations": len(selected) * 5,
        "counts_by_group": dict(sorted(counts.items())),
        "selected_counts_by_group": dict(sorted(selected_counts.items())),
        "ground_truth_policy": "Model proposals are not ground truth; boxes and masks require human confirmation.",
    }
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".", help="bubmask-fiji project root")
    parser.add_argument(
        "--source-dir",
        default="validation/real_tiff_samples",
        help="Directory containing real TIFF samples",
    )
    parser.add_argument(
        "--output-dir",
        default="validation/phase3_unsw_validation",
        help="Phase 3 validation output directory",
    )
    parser.add_argument("--px-per-mm", type=float, default=183.0, help="Temporary calibration assumption")
    parser.add_argument("--subset-per-group", type=int, default=10, help="Selected annotation images per group")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    source_dir = (project_root / args.source_dir).resolve()
    output_dir = (project_root / args.output_dir).resolve()

    rows = image_rows(source_dir, project_root, args.px_per_mm)
    image_fields = [
        "image_id",
        "relative_path",
        "particle_class",
        "experiment_group",
        "particle_condition",
        "flow_rate",
        "pressure",
        "vent_count",
        "aperture",
        "width_px",
        "height_px",
        "image_mode",
        "image_format",
        "calibration_status",
        "calibration_source",
        "px_per_mm",
        "pixel_width_mm",
        "pixel_height_mm",
        "background_image",
        "annotation_status",
        "annotation_required",
        "target_annotation_count",
        "priority",
        "required_case_tags",
        "notes",
    ]
    write_csv(output_dir / "image_manifest.csv", image_fields, rows)

    selected = stratified_subset(rows, args.subset_per_group)
    write_csv(output_dir / "selected_validation_images.csv", image_fields, selected)

    task_fields = [
        "image_id",
        "relative_path",
        "particle_class",
        "experiment_group",
        "target_objects",
        "required_annotation_geometry",
        "target_labels",
        "annotation_status",
        "annotator",
        "reviewer",
        "notes",
    ]
    write_csv(output_dir / "annotation_tasks.csv", task_fields, annotation_tasks(selected))

    annotation_fields = [
        "annotation_id",
        "image_id",
        "label",
        "object_type",
        "x_px",
        "y_px",
        "width_px",
        "height_px",
        "mask_path",
        "mask_format",
        "has_box",
        "has_mask",
        "diameter_px_manual",
        "diameter_mm_manual",
        "annotator",
        "reviewer",
        "confidence",
        "notes",
    ]
    write_csv(output_dir / "object_annotations.csv", annotation_fields, [])

    label_rows = [{"label": label, "definition": definition} for label, definition in LABELS]
    write_csv(output_dir / "label_schema.csv", ["label", "definition"], label_rows)
    write_summary(output_dir / "dataset_summary.json", rows, selected, args.px_per_mm)

    print(f"Wrote {len(rows)} images to {output_dir / 'image_manifest.csv'}")
    print(f"Selected {len(selected)} images for first-pass annotation")
    print(f"Estimated first-pass object annotations: {len(selected) * 5}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
