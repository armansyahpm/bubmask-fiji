#!/usr/bin/env python3
"""BubMask inference worker.

This is the stable process boundary between Fiji/Java and the trained Mask
R-CNN implementation. It currently returns deterministic placeholder output so
the Java command, JSON schema, ResultsTable writing, and deployment mechanics
can be tested before model integration.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import traceback
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from bubmask_fiji.export.artifacts import export_run_artifacts
from bubmask_fiji.measurement.measurements import build_measurement, equivalent_diameter
from bubmask_fiji.preprocessing.denoise import (
    PreprocessingSettings,
    apply_background_image_correction,
    preprocess_image,
)
from bubmask_fiji.quality.scoring import QualitySettings, score_detection_quality, summarize_quality


REQUEST_SCHEMA = "bubmask.request.v1"
RESPONSE_SCHEMA = "bubmask.inference.v1"


def resolve_optional_path(value: str | None, request_dir: Path) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (request_dir / path).resolve()
    return path


def inspect_image(image_path: Path) -> dict[str, Any]:
    if not image_path.is_file():
        raise FileNotFoundError(f"Image path does not exist: {image_path}")
    with Image.open(image_path) as image:
        return {
            "path": str(image_path),
            "format": image.format,
            "mode": image.mode,
            "width_px": image.width,
            "height_px": image.height,
            "n_frames": getattr(image, "n_frames", 1),
        }


def load_image_array(image_path: Path) -> np.ndarray:
    with Image.open(image_path) as image:
        array = np.array(image)
    if array.ndim == 2:
        array = np.stack([array, array, array], axis=-1)
    elif array.ndim == 3 and array.shape[-1] > 3:
        array = array[..., :3]
    if array.dtype != np.uint8:
        low, high = np.percentile(array.astype(np.float32), [1, 99])
        if high > low:
            array = np.clip((array - low) * 255.0 / (high - low), 0, 255)
        array = array.astype(np.uint8)
    return array


def load_optional_image_array(image_path: Path | None) -> np.ndarray | None:
    if image_path is None:
        return None
    return load_image_array(image_path)


def inspect_model_package(model_package: Path | None) -> dict[str, Any]:
    if model_package is None:
        return {
            "name": "bubmask-placeholder",
            "hash": "not-trained-model",
            "runtime": "python-placeholder",
        }
    if not model_package.is_dir():
        raise FileNotFoundError(f"Model package directory does not exist: {model_package}")
    weights_path = model_package / "weights" / "mask_rcnn_bubble.h5"
    return {
        "name": model_package.name,
        "hash": "pending-runtime-load",
        "runtime": "python-placeholder",
        "package_path": str(model_package),
        "weights_path": str(weights_path),
        "weights_present": weights_path.is_file(),
    }


def request_bool(request: dict[str, Any], name: str, default: bool = False) -> bool:
    value = request.get(name, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def preprocessing_settings_from_request(request: dict[str, Any]) -> PreprocessingSettings:
    return PreprocessingSettings(
        profile=str(request.get("preprocessing_profile", "raw_model")),
        background_sigma_px=float(request.get("background_sigma_px", 0.0)),
        median_kernel=int(request.get("median_kernel", 3)),
        gaussian_kernel=int(request.get("gaussian_kernel", 3)),
        clahe_clip_limit=float(request.get("clahe_clip_limit", 2.0)),
        clahe_tile_grid_size=int(request.get("clahe_tile_grid_size", 8)),
        fov_min_fraction=float(request.get("fov_min_fraction", 0.10)),
        background_correction_mode=str(request.get("background_correction_mode", "none")),
    )


def quality_settings_from_request(request: dict[str, Any]) -> QualitySettings:
    return QualitySettings(
        gate_mode=str(request.get("quality_gate_mode", "review_only")),
        min_diameter_px=float(request.get("min_diameter_px", 0.0)),
        max_diameter_px=float(request.get("max_diameter_px", 0.0)),
        min_circularity=float(request.get("min_circularity", 0.06)),
        min_solidity=float(request.get("min_solidity", 0.20)),
        min_boundary_gradient=float(request.get("min_boundary_gradient", 2.0)),
        min_annular_contrast=float(request.get("min_annular_contrast", 0.015)),
        min_focus_score=float(request.get("min_focus_score", 0.0)),
        measure_sharp_bubbles_only=request_bool(request, "measure_sharp_bubbles_only", False),
    )


def apply_quality_scoring(
    measurement: dict[str, Any],
    mask: np.ndarray | None,
    quality_image: np.ndarray,
    settings: QualitySettings,
) -> dict[str, Any]:
    quality = score_detection_quality(measurement, mask, quality_image, settings)
    original_accepted = bool(measurement.get("accepted", True))
    quality["accepted_for_histogram"] = bool(quality["accepted_for_histogram"]) and original_accepted
    measurement.update(quality)
    existing_flags = list(measurement.get("flags", []))
    for flag in measurement.get("quality_flags", []):
        if flag not in existing_flags:
            existing_flags.append(flag)
    measurement["flags"] = existing_flags
    measurement["accepted"] = bool(measurement.get("accepted_for_histogram", original_accepted))
    return measurement


def calibration_info_from_request(request: dict[str, Any]) -> dict[str, Any]:
    pixel_width = float(request.get("pixel_width", 1.0))
    pixel_height = float(request.get("pixel_height", 1.0))
    unit = str(request.get("unit", "pixel") or "pixel")
    status = str(request.get("calibration_status", "") or "").strip().lower()
    source = str(request.get("calibration_source", "") or "").strip().lower()
    px_per_mm = float(request.get("px_per_mm", 0.0) or 0.0)
    if px_per_mm > 0:
        pixel_width = 1.0 / px_per_mm
        pixel_height = 1.0 / px_per_mm
        unit = "mm"
        status = "known"
        source = source or "manual_px_per_mm"
    if not status:
        if unit.lower() in {"pixel", "pixels", "px"}:
            status = "missing"
            source = source or "pixel_units_only"
        elif pixel_width > 0 and pixel_height > 0:
            status = "known"
            source = source or "imageplus_or_request"
        else:
            status = "missing"
            source = source or "invalid_pixel_size"
    if status != "known":
        pixel_width = 1.0
        pixel_height = 1.0
        unit = "pixel"
    return {
        "status": status,
        "source": source,
        "pixel_width": pixel_width,
        "pixel_height": pixel_height,
        "unit": unit,
        "px_per_mm": px_per_mm if px_per_mm > 0 else (
            1.0 / pixel_width if status == "known" and unit == "mm" and pixel_width > 0 else 0.0
        ),
    }


def apply_calibration_metadata(measurement: dict[str, Any], calibration: dict[str, Any]) -> None:
    measurement["calibration_status"] = calibration["status"]
    measurement["calibration_source"] = calibration["source"]
    measurement["pixel_width"] = calibration["pixel_width"]
    measurement["pixel_height"] = calibration["pixel_height"]
    if calibration["status"] != "known":
        measurement["physical_measurement_trusted"] = False
        measurement["diameter_unit"] = "pixel"
        if "missing_calibration" not in measurement.get("flags", []):
            measurement.setdefault("flags", []).append("missing_calibration")
    else:
        measurement["physical_measurement_trusted"] = True


def prepare_images_for_inference(
    image: np.ndarray,
    request: dict[str, Any],
    request_dir: Path,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any], np.ndarray | None]:
    background_path = resolve_optional_path(request.get("background_image_path"), request_dir)
    background_image = load_optional_image_array(background_path)
    preprocessing_settings = preprocessing_settings_from_request(request)
    background_corrected, background_diagnostics = apply_background_image_correction(
        image,
        background_image,
        preprocessing_settings.background_correction_mode,
        float(request.get("background_offset", 0.0)),
    )
    preprocessing_result = preprocess_image(background_corrected, preprocessing_settings)
    diagnostics = preprocessing_result["diagnostics"]
    diagnostics["background_image"] = {
        **background_diagnostics,
        "path": str(background_path) if background_path is not None else "",
    }
    return (
        preprocessing_result["image"],
        background_corrected,
        diagnostics,
        preprocessing_result["fov_mask"],
    )


def run_placeholder_inference(
    request: dict,
    request_dir: Path,
) -> dict:
    image_path = resolve_optional_path(request.get("image_path"), request_dir)
    model_package = resolve_optional_path(request.get("model_package"), request_dir)

    image_info = inspect_image(image_path) if image_path is not None else {}
    model_info = inspect_model_package(model_package)

    width = int(image_info.get("width_px", request.get("width_px", 0)))
    height = int(image_info.get("height_px", request.get("height_px", 0)))
    pixel_width = float(request.get("pixel_width", 1.0))
    pixel_height = float(request.get("pixel_height", 1.0))
    threshold = float(request.get("confidence_threshold", 0.5))

    diameter_px = max(1.0, min(width, height) * 0.10)
    radius_px = diameter_px / 2.0
    area_px = math.pi * radius_px * radius_px
    centroid_x = width / 2.0
    centroid_y = height / 2.0
    bbox = [
        max(0.0, centroid_x - radius_px),
        max(0.0, centroid_y - radius_px),
        diameter_px,
        diameter_px,
    ]

    return {
        "schema_version": RESPONSE_SCHEMA,
        "model": model_info,
        "request": {
            "source_title": request.get("source_title", ""),
            "image_path": str(image_path) if image_path is not None else "",
            "model_package": str(model_package) if model_package is not None else "",
            "confidence_threshold": threshold,
        },
        "image": image_info,
        "masks": [
            {
                "id": 1,
                "score": max(threshold, 0.5),
                "class_label": "bubble",
                "bbox": bbox,
                "area_px": area_px,
            }
        ],
        "measurements": [
            {
                "bubble_id": 1,
                "score": max(threshold, 0.5),
                "area_px": area_px,
                "diameter_eq_um": equivalent_diameter(area_px, pixel_width, pixel_height),
                "centroid_x_px": centroid_x,
                "centroid_y_px": centroid_y,
            }
        ],
        "warnings": [
            "Placeholder inference only. Replace run_placeholder_inference with trained Mask R-CNN execution."
        ],
    }


def measurement_from_area(
    bubble_id: int,
    score: float,
    area_px: float,
    bbox: list[float],
    pixel_width: float,
    pixel_height: float,
) -> dict[str, Any]:
    return build_measurement(
        bubble_id,
        score,
        area_px,
        bbox,
        pixel_width,
        pixel_height,
        "pixel",
        0,
        0,
        confidence_threshold=0.5,
    )


def run_adaptive_threshold_inference(
    request: dict,
    request_dir: Path,
) -> dict:
    from bubmask_fiji.segmentation.adaptive_threshold import (
        AdaptiveThresholdSettings,
        segment_adaptive_threshold,
    )

    image_path = resolve_optional_path(request.get("image_path"), request_dir)
    if image_path is None:
        raise ValueError("adaptive_threshold_baseline requires image_path")
    model_package = resolve_optional_path(request.get("model_package"), request_dir)
    image_info = inspect_image(image_path)
    image = load_image_array(image_path)
    inference_image, background_corrected_image, preprocessing_diagnostics, fov_mask = prepare_images_for_inference(
        image, request, request_dir)
    quality_settings = quality_settings_from_request(request)
    calibration = calibration_info_from_request(request)
    settings = AdaptiveThresholdSettings(
        block_size=int(request.get("adaptive_block_size", 51)),
        c=int(request.get("adaptive_c", 5)),
        min_area_px=int(request.get("min_area_px", 16)),
    )
    result = segment_adaptive_threshold(inference_image, settings)
    pixel_width = float(calibration["pixel_width"])
    pixel_height = float(calibration["pixel_height"])
    unit = str(calibration["unit"])
    threshold = float(request.get("confidence_threshold", 0.5))
    masks = []
    measurements = []
    for obj in result["objects"]:
        bubble_id = int(obj["id"])
        bbox = obj["bbox"]
        area_px = float(obj["area_px"])
        masks.append({
            "id": bubble_id,
            "score": 1.0,
            "class_label": "bubble_candidate",
            "bbox": bbox,
            "area_px": area_px,
        })
        label_mask = result["label_image"] == bubble_id
        measurement = build_measurement(
            bubble_id, 1.0, area_px, bbox, pixel_width, pixel_height, unit,
            int(image_info["width_px"]), int(image_info["height_px"]),
            mask=label_mask, image=image, confidence_threshold=threshold)
        apply_calibration_metadata(measurement, calibration)
        apply_quality_scoring(measurement, label_mask, inference_image, quality_settings)
        masks[-1]["measurement_status"] = measurement.get("measurement_status", "")
        masks[-1]["accepted_for_histogram"] = measurement.get("accepted_for_histogram", False)
        measurements.append(measurement)

    response = {
        "schema_version": RESPONSE_SCHEMA,
        "model": inspect_model_package(model_package),
        "request": {
            "source_title": request.get("source_title", ""),
            "image_path": str(image_path),
            "model_package": str(model_package) if model_package is not None else "",
            "confidence_threshold": float(request.get("confidence_threshold", 0.5)),
            "inference_mode": "adaptive_threshold_baseline",
            "preprocessing_profile": preprocessing_diagnostics["profile"],
            "quality_gate_mode": quality_settings.gate_mode,
            "calibration_status": calibration["status"],
            "calibration_source": calibration["source"],
        },
        "image": image_info,
        "masks": masks,
        "measurements": measurements,
        "warnings": [
            "Adaptive-threshold baseline only. Do not treat as validated BubMask Mask R-CNN output."
        ] + ([] if calibration["status"] == "known" else [
            "Pixel size is missing. BubMask can report pixel units only. Physical diameter cannot be trusted until calibration is provided."
        ]),
        "diagnostics": {
            "calibration": calibration,
            "preprocessing": preprocessing_diagnostics,
            "quality_summary": summarize_quality(measurements),
            "adaptive_threshold": {
                "settings": result["settings"],
                "object_count": result["object_count"],
            }
        },
    }
    output_dir = resolve_optional_path(request.get("run_output_dir"), request_dir)
    outputs = export_run_artifacts(
        response,
        image,
        output_dir,
        label_image=result["label_image"],
        background_corrected_image=background_corrected_image,
        preprocessed_image=inference_image,
        fov_mask=fov_mask,
    )
    if outputs:
        response["outputs"] = outputs
    return response


def run_bubmask_mask_rcnn_inference(
    request: dict,
    request_dir: Path,
) -> dict:
    image_path = resolve_optional_path(request.get("image_path"), request_dir)
    model_package = resolve_optional_path(request.get("model_package"), request_dir)
    if image_path is None:
        raise ValueError("bubmask_mask_rcnn requires image_path")
    if model_package is None:
        raise ValueError("bubmask_mask_rcnn requires model_package")

    image_info = inspect_image(image_path)
    model_info = inspect_model_package(model_package)
    weights_path = Path(model_info["weights_path"])
    if not weights_path.is_file():
        raise FileNotFoundError(f"BubMask weights not found: {weights_path}")

    import sys as _sys
    python_root = Path(__file__).resolve().parent
    if str(python_root) not in _sys.path:
        _sys.path.insert(0, str(python_root))

    from bubble_analyser.bubble.bubble import _InfConfig
    from bubble_analyser.mrcnn import model as modellib

    image = load_image_array(image_path)
    inference_image, background_corrected_image, preprocessing_diagnostics, fov_mask = prepare_images_for_inference(
        image, request, request_dir)
    quality_settings = quality_settings_from_request(request)
    calibration = calibration_info_from_request(request)
    pixel_width = float(calibration["pixel_width"])
    pixel_height = float(calibration["pixel_height"])
    unit = str(calibration["unit"])
    threshold = float(request.get("confidence_threshold", 0.5))
    logs_dir = model_package / "logs"
    logs_dir.mkdir(exist_ok=True)

    config = _InfConfig()
    config.DETECTION_MIN_CONFIDENCE = threshold
    model = modellib.MaskRCNN(mode="inference", model_dir=str(logs_dir), config=config)
    model.load_weights(str(weights_path), by_name=True)
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
        masks.append({
            "id": bubble_id,
            "score": score,
            "class_label": "bubble",
            "bbox": bbox,
            "area_px": area_px,
        })
        instance_mask = mask_stack[:, :, idx] if mask_stack is not None else None
        measurement = build_measurement(
            bubble_id, score, area_px, bbox, pixel_width, pixel_height, unit,
            int(image_info["width_px"]), int(image_info["height_px"]),
            mask=instance_mask, image=image, confidence_threshold=threshold)
        apply_calibration_metadata(measurement, calibration)
        apply_quality_scoring(measurement, instance_mask, inference_image, quality_settings)
        masks[-1]["measurement_status"] = measurement.get("measurement_status", "")
        masks[-1]["accepted_for_histogram"] = measurement.get("accepted_for_histogram", False)
        measurements.append(measurement)

    model_info["runtime"] = "tensorflow-keras-mask-rcnn"
    response = {
        "schema_version": RESPONSE_SCHEMA,
        "model": model_info,
        "request": {
            "source_title": request.get("source_title", ""),
            "image_path": str(image_path),
            "model_package": str(model_package),
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
    output_dir = resolve_optional_path(request.get("run_output_dir"), request_dir)
    outputs = export_run_artifacts(
        response,
        image,
        output_dir,
        instance_masks=mask_stack,
        background_corrected_image=background_corrected_image,
        preprocessed_image=inference_image,
        fov_mask=fov_mask,
    )
    if outputs:
        response["outputs"] = outputs
    return response


def load_request(path: Path) -> dict:
    request = json.loads(path.read_text(encoding="utf-8-sig"))
    schema = request.get("schema_version")
    if schema != REQUEST_SCHEMA:
        raise ValueError(f"Unsupported request schema: {schema!r}; expected {REQUEST_SCHEMA!r}")
    return request


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run BubMask inference for Fiji.")
    parser.add_argument("--input", required=True, help="Path to a BubMask JSON request.")
    parser.add_argument("--output", help="Optional output JSON path. Defaults to stdout.")
    args = parser.parse_args(argv)

    request_path = Path(args.input).resolve()
    try:
        request = load_request(request_path)
        mode = request.get("inference_mode", "placeholder")
        if mode == "bubmask_mask_rcnn":
            response = run_bubmask_mask_rcnn_inference(request, request_path.parent)
        elif mode == "adaptive_threshold_baseline":
            response = run_adaptive_threshold_inference(request, request_path.parent)
        else:
            response = run_placeholder_inference(request, request_path.parent)
        exit_code = 0
    except Exception as exc:
        response = {
            "schema_version": RESPONSE_SCHEMA,
            "status": "error",
            "error": {
                "type": exc.__class__.__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            },
            "request_path": str(request_path),
            "warnings": [
                "BubMask worker failed before producing valid measurements. Check image_path, model_package, Python environment, and model weights."
            ],
        }
        exit_code = 2
    text = json.dumps(response, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
