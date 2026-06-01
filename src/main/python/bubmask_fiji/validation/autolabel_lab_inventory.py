"""Auto-label the unlabelled UNSW lab TIFF inventory for active learning.

The script runs the current fine-tuned BubMask model over many TIFF images and
creates one self-contained review folder per image:

```
image.tif
request.json
response.json
overlay_masks.png
instance_labels.tif
per_bubble_measurements.csv
```

It is resumable. If a run folder already contains ``response.json`` and the
expected review artifacts, the image is skipped unless ``--overwrite`` is used.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
import time
import traceback
from pathlib import Path
from typing import Any

import numpy as np

from bubmask_worker import (
    RESPONSE_SCHEMA,
    apply_calibration_metadata,
    apply_quality_scoring,
    calibration_info_from_request,
    inspect_image,
    inspect_model_package,
    load_image_array,
    prepare_images_for_inference,
    quality_settings_from_request,
)
from bubmask_fiji.export.artifacts import export_run_artifacts
from bubmask_fiji.measurement.measurements import build_measurement
from bubmask_fiji.quality.scoring import summarize_quality


def discover_images(input_roots: list[Path]) -> list[Path]:
    images: list[Path] = []
    for root in input_roots:
        if root.is_file() and root.suffix.lower() in {".tif", ".tiff"}:
            images.append(root.resolve())
        elif root.is_dir():
            images.extend(path.resolve() for path in root.rglob("*.tif"))
            images.extend(path.resolve() for path in root.rglob("*.tiff"))
    return sorted(set(images), key=lambda path: str(path).lower())


def read_input_list(path: Path) -> list[Path]:
    images: list[Path] = []
    with path.open(encoding="utf-8-sig") as handle:
        for line in handle:
            value = line.strip()
            if not value or value.startswith("#"):
                continue
            image_path = Path(value).expanduser().resolve()
            if image_path.suffix.lower() in {".tif", ".tiff"}:
                images.append(image_path)
    return images


def infer_condition(path: Path) -> str:
    parts = {part.lower() for part in path.parts}
    if "with_particle" in parts:
        return "with_particle"
    if "without_particle" in parts:
        return "without_particle"
    return "unknown_condition"


def safe_slug(value: str, max_len: int = 90) -> str:
    text = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)
    while "__" in text:
        text = text.replace("__", "_")
    text = text.strip("_")
    if len(text) > max_len:
        text = text[:max_len].rstrip("_")
    return text or "image"


def run_folder_name(index: int, image_path: Path) -> str:
    digest = hashlib.sha1(str(image_path).encode("utf-8")).hexdigest()[:10]
    condition = infer_condition(image_path)
    stem = safe_slug(image_path.stem, max_len=70)
    return f"{index:05d}_{condition}_{stem}_{digest}"


def hardlink_or_copy_image(source: Path, destination: Path, overwrite: bool = False) -> str:
    if destination.exists():
        if not overwrite:
            return "existing"
        destination.unlink()
    try:
        os.link(source, destination)
        return "hardlink"
    except OSError:
        shutil.copy2(source, destination)
        return "copy"


def expected_artifacts_exist(run_dir: Path) -> bool:
    required = [
        "response.json",
        "overlay_masks.png",
        "instance_labels.tif",
        "per_bubble_measurements.csv",
    ]
    return all((run_dir / name).is_file() for name in required)


def write_request(path: Path, request: dict[str, Any]) -> None:
    path.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_request(args: argparse.Namespace, image_path: Path, run_dir: Path) -> dict[str, Any]:
    return {
        "schema_version": "bubmask.request.v1",
        "source_title": image_path.name,
        "image_path": str(run_dir / "image.tif"),
        "source_image_path": str(image_path),
        "model_package": str(args.model_package),
        "model_package_label": args.model_label,
        "inference_mode": "bubmask_mask_rcnn",
        "confidence_threshold": args.confidence_threshold,
        "preprocessing_profile": args.preprocessing_profile,
        "background_correction_mode": args.background_correction_mode,
        "quality_gate_mode": args.quality_gate_mode,
        "measure_sharp_bubbles_only": args.measure_sharp_bubbles_only,
        "min_focus_score": args.min_focus_score,
        "min_diameter_px": args.min_diameter_px,
        "max_diameter_px": args.max_diameter_px,
        "calibration_status": "known" if args.px_per_mm > 0 else "missing",
        "calibration_source": "active_learning_px_per_mm" if args.px_per_mm > 0 else "missing",
        "px_per_mm": args.px_per_mm,
        "run_output_dir": str(run_dir),
    }


def run_inference(
    model: Any,
    config: Any,
    request: dict[str, Any],
    request_dir: Path,
    model_info: dict[str, Any],
) -> dict[str, Any]:
    image_path = Path(request["image_path"])
    image_info = inspect_image(image_path)
    image = load_image_array(image_path)
    inference_image, background_corrected_image, preprocessing_diagnostics, fov_mask = prepare_images_for_inference(
        image,
        request,
        request_dir,
    )
    quality_settings = quality_settings_from_request(request)
    calibration = calibration_info_from_request(request)
    pixel_width = float(calibration["pixel_width"])
    pixel_height = float(calibration["pixel_height"])
    unit = str(calibration["unit"])
    threshold = float(request.get("confidence_threshold", 0.5))

    result = model.detect([inference_image], verbose=int(request.get("verbose", 0)))[0]

    masks = []
    measurements = []
    rois = result.get("rois", [])
    scores = result.get("scores", [])
    mask_stack = result.get("masks")
    for idx, roi in enumerate(rois):
        y1, x1, y2, x2 = [float(v) for v in roi]
        bbox = [x1, y1, max(0.0, x2 - x1), max(0.0, y2 - y1)]
        score = float(scores[idx]) if idx < len(scores) else 0.0
        area_px = float(mask_stack[:, :, idx].sum()) if mask_stack is not None else bbox[2] * bbox[3]
        bubble_id = idx + 1
        instance_mask = mask_stack[:, :, idx] if mask_stack is not None else None
        measurement = build_measurement(
            bubble_id,
            score,
            area_px,
            bbox,
            pixel_width,
            pixel_height,
            unit,
            int(image_info["width_px"]),
            int(image_info["height_px"]),
            mask=instance_mask,
            image=image,
            confidence_threshold=threshold,
        )
        apply_calibration_metadata(measurement, calibration)
        apply_quality_scoring(measurement, instance_mask, inference_image, quality_settings)
        masks.append({
            "id": bubble_id,
            "score": score,
            "class_label": "bubble",
            "bbox": bbox,
            "area_px": area_px,
            "measurement_status": measurement.get("measurement_status", ""),
            "accepted_for_histogram": measurement.get("accepted_for_histogram", False),
        })
        measurements.append(measurement)

    response = {
        "schema_version": RESPONSE_SCHEMA,
        "status": "worker_ok",
        "model": model_info,
        "request": {
            "source_title": request.get("source_title", ""),
            "image_path": str(image_path),
            "source_image_path": request.get("source_image_path", ""),
            "model_package": str(request.get("model_package", "")),
            "model_package_label": request.get("model_package_label", ""),
            "confidence_threshold": threshold,
            "inference_mode": "bubmask_mask_rcnn",
            "preprocessing_profile": preprocessing_diagnostics["profile"],
            "quality_gate_mode": quality_settings.gate_mode,
            "calibration_status": calibration["status"],
            "calibration_source": calibration["source"],
        },
        "image": image_info,
        "masks": masks,
        "measurements": measurements,
        "warnings": [] if calibration["status"] == "known" else [
            "Pixel size is missing. BubMask can report pixel units only. Physical diameter cannot be trusted until calibration is provided."
        ],
        "diagnostics": {
            "calibration": calibration,
            "detection_count": len(masks),
            "preprocessing": preprocessing_diagnostics,
            "quality_summary": summarize_quality(measurements),
            "config": {
                "IMAGE_MIN_DIM": config.IMAGE_MIN_DIM,
                "IMAGE_MAX_DIM": config.IMAGE_MAX_DIM,
                "IMAGE_RESIZE_MODE": config.IMAGE_RESIZE_MODE,
                "DETECTION_MIN_CONFIDENCE": config.DETECTION_MIN_CONFIDENCE,
            },
        },
    }
    outputs = export_run_artifacts(
        response,
        image,
        request_dir,
        instance_masks=mask_stack,
        background_corrected_image=background_corrected_image,
        preprocessed_image=inference_image,
        fov_mask=fov_mask,
    )
    if outputs:
        response["outputs"] = outputs
    return response


def load_existing_response(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {"status": "invalid_response_json"}


def manifest_row(
    index: int,
    image_path: Path,
    run_dir: Path,
    response: dict[str, Any],
    elapsed_sec: float,
    action: str,
    link_mode: str = "",
) -> dict[str, Any]:
    diagnostics = response.get("diagnostics", {}) if isinstance(response, dict) else {}
    quality = diagnostics.get("quality_summary", {}) if isinstance(diagnostics, dict) else {}
    outputs = response.get("outputs", {}) if isinstance(response, dict) else {}
    error = response.get("error", {}) if isinstance(response, dict) else {}
    return {
        "index": index,
        "condition": infer_condition(image_path),
        "source_image": str(image_path),
        "run_dir": str(run_dir),
        "action": action,
        "status": response.get("status", ""),
        "error_type": error.get("type", ""),
        "error_message": error.get("message", ""),
        "elapsed_sec": f"{elapsed_sec:.2f}",
        "detections": diagnostics.get("detection_count", ""),
        "accepted_bubble": quality.get("accepted_bubble", ""),
        "review_bubble": quality.get("review_bubble", ""),
        "rejected_nonbubble": quality.get("rejected_nonbubble", ""),
        "accepted_for_histogram": quality.get("accepted_for_histogram", ""),
        "image_copy_mode": link_mode,
        "overlay_masks": outputs.get("overlay_masks_png", ""),
        "instance_labels": outputs.get("instance_labels_tif", ""),
        "per_bubble_csv": outputs.get("per_bubble_csv", ""),
        "response_json": str(run_dir / "response.json"),
    }


def write_manifest(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Auto-label lab TIFF inventory with the fine-tuned BubMask model.")
    parser.add_argument("--input-root", action="append", default=[], help="Folder or TIFF path. Repeatable.")
    parser.add_argument("--input-list", action="append", default=[], help="Text file with one TIFF path per line. Repeatable.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--model-package", required=True)
    parser.add_argument("--model-label", default="bubmask-maskrcnn-unsw-round2-v1")
    parser.add_argument("--confidence-threshold", type=float, default=0.10)
    parser.add_argument("--preprocessing-profile", default="raw_model")
    parser.add_argument("--background-correction-mode", default="none")
    parser.add_argument("--quality-gate-mode", default="review_only")
    parser.add_argument("--measure-sharp-bubbles-only", action="store_true")
    parser.add_argument("--min-focus-score", type=float, default=10.0)
    parser.add_argument("--min-diameter-px", type=float, default=0.0)
    parser.add_argument("--max-diameter-px", type=float, default=0.0)
    parser.add_argument("--px-per-mm", type=float, default=183.0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--manifest-every", type=int, default=5)
    args = parser.parse_args(argv)

    input_roots = [Path(value).expanduser().resolve() for value in args.input_root]
    input_lists = [Path(value).expanduser().resolve() for value in args.input_list]
    if not input_roots and not input_lists:
        raise SystemExit("At least one --input-root or --input-list is required.")
    output_dir = Path(args.output_dir).expanduser().resolve()
    args.model_package = Path(args.model_package).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    images = discover_images(input_roots)
    for input_list in input_lists:
        images.extend(read_input_list(input_list))
    images = sorted(set(images), key=lambda path: str(path).lower())
    if args.limit > 0:
        images = images[:args.limit]
    manifest_path = output_dir / "autolabel_manifest.csv"
    summary_path = output_dir / "autolabel_summary.json"

    print(f"Discovered {len(images)} TIFF images.", flush=True)
    print(f"Output: {output_dir}", flush=True)
    print(f"Model package: {args.model_package}", flush=True)
    print(f"Confidence threshold: {args.confidence_threshold}", flush=True)

    model_info = inspect_model_package(args.model_package)
    weights_path = Path(model_info["weights_path"])
    if not weights_path.is_file():
        raise FileNotFoundError(weights_path)

    from bubble_analyser.bubble.bubble import _InfConfig
    from bubble_analyser.mrcnn import model as modellib

    config = _InfConfig()
    config.DETECTION_MIN_CONFIDENCE = args.confidence_threshold
    logs_dir = args.model_package / "logs"
    logs_dir.mkdir(exist_ok=True)
    model = modellib.MaskRCNN(mode="inference", model_dir=str(logs_dir), config=config)
    model.load_weights(str(weights_path), by_name=True)
    model_info["runtime"] = "tensorflow-keras-mask-rcnn"
    model_info["active_learning_threshold"] = args.confidence_threshold

    rows: list[dict[str, Any]] = []
    completed = 0
    skipped = 0
    failed = 0
    started_at = time.time()
    for position, image_path in enumerate(images, start=args.start_index):
        run_dir = output_dir / run_folder_name(position, image_path)
        run_dir.mkdir(parents=True, exist_ok=True)
        response_path = run_dir / "response.json"
        if not args.overwrite and expected_artifacts_exist(run_dir):
            response = load_existing_response(response_path)
            rows.append(manifest_row(position, image_path, run_dir, response, 0.0, "skipped_existing"))
            skipped += 1
            continue

        print(f"[{position}/{len(images)}] {infer_condition(image_path)} | {image_path.name}", flush=True)
        start = time.perf_counter()
        link_mode = ""
        try:
            link_mode = hardlink_or_copy_image(image_path, run_dir / "image.tif", overwrite=True)
            (run_dir / "source_image_path.txt").write_text(str(image_path) + "\n", encoding="utf-8")
            request = build_request(args, image_path, run_dir)
            write_request(run_dir / "request.json", request)
            response = run_inference(model, config, request, run_dir, model_info)
            response_path.write_text(json.dumps(response, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            elapsed = time.perf_counter() - start
            rows.append(manifest_row(position, image_path, run_dir, response, elapsed, "processed", link_mode))
            completed += 1
        except Exception as exc:
            elapsed = time.perf_counter() - start
            failed += 1
            response = {
                "schema_version": RESPONSE_SCHEMA,
                "status": "error",
                "error": {
                    "type": exc.__class__.__name__,
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                },
            }
            response_path.write_text(json.dumps(response, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            rows.append(manifest_row(position, image_path, run_dir, response, elapsed, "failed", link_mode))
            print(f"ERROR: {image_path}: {exc}", file=sys.stderr, flush=True)

        if len(rows) % max(1, args.manifest_every) == 0:
            write_manifest(manifest_path, rows)
            summary_path.write_text(json.dumps({
                "total_images": len(images),
                "completed": completed,
                "skipped": skipped,
                "failed": failed,
                "elapsed_sec": time.time() - started_at,
                "last_position": position,
            }, indent=2), encoding="utf-8")

    write_manifest(manifest_path, rows)
    summary = {
        "total_images": len(images),
        "completed": completed,
        "skipped": skipped,
        "failed": failed,
        "elapsed_sec": time.time() - started_at,
        "output_dir": str(output_dir),
        "manifest": str(manifest_path),
        "model_package": str(args.model_package),
        "confidence_threshold": args.confidence_threshold,
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
