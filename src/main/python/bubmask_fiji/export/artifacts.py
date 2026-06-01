"""Artifact export helpers for BubMask-Fiji worker runs."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw


def ensure_output_dir(path: str | Path | None) -> Path | None:
    if not path:
        return None
    outdir = Path(path).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    return outdir


def save_measurements_csv(measurements: list[dict[str, Any]], path: Path) -> None:
    base_fields = [
        "bubble_id",
        "score",
        "area_px",
        "area_calibrated",
        "equivalent_diameter_px",
        "equivalent_diameter_calibrated",
        "diameter_unit",
        "calibration_status",
        "calibration_source",
        "physical_measurement_trusted",
        "pixel_width",
        "pixel_height",
        "centroid_x_px",
        "centroid_y_px",
        "bbox_x_px",
        "bbox_y_px",
        "bbox_width_px",
        "bbox_height_px",
        "touches_border",
        "contains_saturated_highlight",
        "saturated_highlight_fraction",
        "low_confidence",
        "accepted",
        "measurement_status",
        "accepted_for_histogram",
        "rejection_reason",
        "focus_score",
        "boundary_gradient_score",
        "annular_contrast",
        "circularity",
        "solidity",
        "eccentricity",
        "bbox_aspect_ratio",
        "perimeter_px",
        "quality_gate_mode",
        "flags",
        "quality_flags",
    ]
    extra_fields = sorted({
        key
        for row in measurements
        for key in row.keys()
        if key not in base_fields and not isinstance(row.get(key), (dict, list))
    })
    fields = base_fields + extra_fields
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in measurements:
            out = {field: row.get(field, "") for field in fields}
            out["flags"] = ";".join(row.get("flags", []))
            out["quality_flags"] = ";".join(row.get("quality_flags", []))
            writer.writerow(out)


def image_to_rgb(image: np.ndarray) -> Image.Image:
    if image.ndim == 2:
        arr = np.stack([image, image, image], axis=-1)
    else:
        arr = image[:, :, :3]
    if arr.dtype != np.uint8:
        arr = np.clip(arr, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, mode="RGB")


def color_for_label(label: int) -> tuple[int, int, int]:
    """Return a stable bright color for a one-based instance label."""
    palette = [
        (46, 204, 113),
        (52, 152, 219),
        (241, 196, 15),
        (231, 76, 60),
        (155, 89, 182),
        (26, 188, 156),
        (230, 126, 34),
        (149, 165, 166),
        (255, 99, 132),
        (99, 255, 132),
        (132, 99, 255),
        (255, 159, 64),
    ]
    return palette[(label - 1) % len(palette)]


def color_for_status(status: str, label: int) -> tuple[int, int, int]:
    """Return an overlay color that exposes quality status."""
    if status == "accepted_bubble":
        return (46, 204, 113)
    if status == "review_bubble":
        return (241, 196, 15)
    if status == "rejected_nonbubble":
        return (231, 76, 60)
    return color_for_label(label)


def measurement_status_map(measurements: list[dict[str, Any]] | None) -> dict[int, str]:
    if not measurements:
        return {}
    mapping: dict[int, str] = {}
    for row in measurements:
        try:
            bubble_id = int(row.get("bubble_id", 0))
        except (TypeError, ValueError):
            continue
        if bubble_id > 0:
            mapping[bubble_id] = str(row.get("measurement_status", ""))
    return mapping


def label_image_from_instance_masks(instance_masks: np.ndarray | None) -> np.ndarray | None:
    if instance_masks is None:
        return None
    if instance_masks.ndim != 3 or instance_masks.shape[2] == 0:
        return None
    labels = np.zeros(instance_masks.shape[:2], dtype=np.uint16)
    for idx in range(instance_masks.shape[2]):
        labels[instance_masks[:, :, idx].astype(bool)] = idx + 1
    return labels


def save_overlay_images(
    image: np.ndarray,
    masks: list[dict[str, Any]],
    measurements: list[dict[str, Any]] | None,
    png_path: Path,
    tif_path: Path,
) -> None:
    overlay = image_to_rgb(image)
    draw = ImageDraw.Draw(overlay)
    statuses = measurement_status_map(measurements)
    for item in masks:
        x, y, w, h = item["bbox"]
        label = int(item.get("id", 0) or 0)
        score = float(item.get("score", 0.0))
        status = statuses.get(label, "")
        color = color_for_status(status, label) if status else ((0, 255, 0) if score >= 0.5 else (255, 220, 0))
        draw.rectangle([x, y, x + w, y + h], outline=color, width=2)
        draw.text((x, max(0, y - 10)), str(item.get("id", "")), fill=color)
    overlay.save(png_path)
    overlay.save(tif_path)


def save_mask_overlay_images(
    image: np.ndarray,
    label_image: np.ndarray | None,
    measurements: list[dict[str, Any]] | None,
    png_path: Path,
    tif_path: Path,
    alpha: float = 0.42,
) -> bool:
    if label_image is None or label_image.size == 0 or int(label_image.max()) == 0:
        return False
    base = np.asarray(image_to_rgb(image)).astype(np.float32)
    overlay = base.copy()
    statuses = measurement_status_map(measurements)
    for label in range(1, int(label_image.max()) + 1):
        region = label_image == label
        if not region.any():
            continue
        color = np.array(color_for_status(statuses.get(label, ""), label), dtype=np.float32)
        overlay[region] = (1.0 - alpha) * overlay[region] + alpha * color
    out = Image.fromarray(np.clip(overlay, 0, 255).astype(np.uint8), mode="RGB")
    draw = ImageDraw.Draw(out)
    for label in range(1, int(label_image.max()) + 1):
        ys, xs = np.nonzero(label_image == label)
        if xs.size == 0:
            continue
        color = color_for_status(statuses.get(label, ""), label)
        x0, x1 = int(xs.min()), int(xs.max())
        y0, y1 = int(ys.min()), int(ys.max())
        draw.rectangle([x0, y0, x1, y1], outline=color, width=1)
        draw.text((x0, max(0, y0 - 10)), str(label), fill=color)
    out.save(png_path)
    out.save(tif_path)
    return True


def save_label_image(label_image: np.ndarray | None, path: Path) -> bool:
    if label_image is None or label_image.size == 0:
        return False
    labels = label_image.astype(np.uint16, copy=False)
    Image.fromarray(labels, mode="I;16").save(path)
    return True


def save_image_array(image: np.ndarray | None, path: Path) -> bool:
    if image is None:
        return False
    image_to_rgb(image).save(path)
    return True


def _captioned_tile(image: np.ndarray | None, title: str, width: int, height: int) -> Image.Image:
    tile = Image.new("RGB", (width, height + 24), (245, 245, 245))
    draw = ImageDraw.Draw(tile)
    draw.text((8, 6), title, fill=(20, 20, 20))
    if image is None:
        inner = Image.new("RGB", (width, height), (220, 220, 220))
        ImageDraw.Draw(inner).text((12, 12), "not available", fill=(80, 80, 80))
    else:
        inner = image_to_rgb(image)
        inner.thumbnail((width, height))
        framed = Image.new("RGB", (width, height), (0, 0, 0))
        framed.paste(inner, ((width - inner.width) // 2, (height - inner.height) // 2))
        inner = framed
    tile.paste(inner, (0, 24))
    return tile


def _mask_preview(mask: np.ndarray | None) -> np.ndarray | None:
    if mask is None:
        return None
    return (mask.astype(np.uint8) * 255)


def save_processing_preview(
    original_image: np.ndarray,
    background_corrected_image: np.ndarray | None,
    preprocessed_image: np.ndarray | None,
    fov_mask: np.ndarray | None,
    path: Path,
) -> bool:
    tile_w = 320
    tile_h = 320
    tiles = [
        _captioned_tile(original_image, "1. Original image", tile_w, tile_h),
        _captioned_tile(background_corrected_image, "2. After background correction", tile_w, tile_h),
        _captioned_tile(preprocessed_image, "3. After preprocessing profile", tile_w, tile_h),
        _captioned_tile(_mask_preview(fov_mask), "4. Field-of-view mask", tile_w, tile_h),
    ]
    canvas = Image.new("RGB", (tile_w * 2, (tile_h + 24) * 2), (255, 255, 255))
    for idx, tile in enumerate(tiles):
        x = (idx % 2) * tile_w
        y = (idx // 2) * (tile_h + 24)
        canvas.paste(tile, (x, y))
    canvas.save(path)
    return True


def save_fov_mask(fov_mask: np.ndarray | None, path: Path) -> bool:
    if fov_mask is None:
        return False
    arr = (fov_mask.astype(np.uint8) * 255)
    Image.fromarray(arr, mode="L").save(path)
    return True


def save_summary_json(response: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(response, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def export_run_artifacts(
    response: dict[str, Any],
    image: np.ndarray,
    output_dir: str | Path | None,
    label_image: np.ndarray | None = None,
    instance_masks: np.ndarray | None = None,
    background_corrected_image: np.ndarray | None = None,
    preprocessed_image: np.ndarray | None = None,
    fov_mask: np.ndarray | None = None,
) -> dict[str, str]:
    outdir = ensure_output_dir(output_dir)
    if outdir is None:
        return {}
    if label_image is None:
        label_image = label_image_from_instance_masks(instance_masks)
    csv_path = outdir / "per_bubble_measurements.csv"
    overlay_png = outdir / "overlay_boxes.png"
    overlay_tif = outdir / "overlay_boxes.tif"
    mask_overlay_png = outdir / "overlay_masks.png"
    mask_overlay_tif = outdir / "overlay_masks.tif"
    label_tif = outdir / "instance_labels.tif"
    background_corrected_png = outdir / "background_corrected_image.png"
    background_corrected_tif = outdir / "background_corrected_image.tif"
    preprocessed_png = outdir / "preprocessed_image.png"
    preprocessed_tif = outdir / "preprocessed_image.tif"
    processing_preview_png = outdir / "processing_preview.png"
    fov_mask_tif = outdir / "fov_mask.tif"
    summary_json = outdir / "summary_response.json"
    measurements = response.get("measurements", [])
    save_measurements_csv(measurements, csv_path)
    save_overlay_images(image, response.get("masks", []), response.get("measurements", []), overlay_png, overlay_tif)
    has_mask_overlay = save_mask_overlay_images(
        image, label_image, response.get("measurements", []), mask_overlay_png, mask_overlay_tif)
    has_label_image = save_label_image(label_image, label_tif)
    has_background_corrected_png = save_image_array(background_corrected_image, background_corrected_png)
    has_background_corrected_tif = save_image_array(background_corrected_image, background_corrected_tif)
    has_preprocessed_png = save_image_array(preprocessed_image, preprocessed_png)
    has_preprocessed_tif = save_image_array(preprocessed_image, preprocessed_tif)
    has_processing_preview = save_processing_preview(
        image, background_corrected_image, preprocessed_image, fov_mask, processing_preview_png)
    has_fov_mask = save_fov_mask(fov_mask, fov_mask_tif)
    outputs = {
        "run_output_dir": str(outdir),
        "per_bubble_csv": str(csv_path),
        "overlay_png": str(overlay_png),
        "overlay_tif": str(overlay_tif),
        "summary_json": str(summary_json),
    }
    try:
        from bubmask_fiji.histogram.histograms import export_histogram_artifacts

        outputs.update(export_histogram_artifacts(
            measurements,
            outdir,
            image_id=str(response.get("request", {}).get("source_title", "")),
        ))
    except Exception as exc:
        response.setdefault("warnings", []).append(f"Histogram artifact export failed: {exc}")
    if has_mask_overlay:
        outputs["overlay_masks_png"] = str(mask_overlay_png)
        outputs["overlay_masks_tif"] = str(mask_overlay_tif)
    if has_label_image:
        outputs["instance_labels_tif"] = str(label_tif)
    if has_background_corrected_png:
        outputs["background_corrected_png"] = str(background_corrected_png)
    if has_background_corrected_tif:
        outputs["background_corrected_tif"] = str(background_corrected_tif)
    if has_preprocessed_png:
        outputs["preprocessed_png"] = str(preprocessed_png)
    if has_preprocessed_tif:
        outputs["preprocessed_tif"] = str(preprocessed_tif)
    if has_processing_preview:
        outputs["processing_preview_png"] = str(processing_preview_png)
    if has_fov_mask:
        outputs["fov_mask_tif"] = str(fov_mask_tif)
    response["outputs"] = outputs
    save_summary_json(response, summary_json)
    return outputs
