"""Synthetic background generation for bubble microscope images.

This module creates a deterministic background candidate from a bubble image by
detecting dark/bright bubble-like artifacts inside the microscope field of view,
inpainting them, and smoothing the result while preserving the circular camera
frame. It is intended for review and calibration experiments, not as a
replacement for a true captured background image.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw

from bubmask_fiji.preprocessing.denoise import as_uint8_grayscale, detect_fov_mask


def load_image(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        arr = np.array(image)
    if arr.ndim == 2:
        arr = np.stack([arr, arr, arr], axis=-1)
    elif arr.ndim == 3 and arr.shape[-1] > 3:
        arr = arr[..., :3]
    if arr.dtype != np.uint8:
        arr = arr.astype(np.float32)
        low, high = np.percentile(arr, [1, 99])
        if high > low:
            arr = np.clip((arr - low) * 255.0 / (high - low), 0, 255)
        arr = arr.astype(np.uint8)
    return arr


def _fill_outside_fov(gray: np.ndarray, fov_mask: np.ndarray) -> np.ndarray:
    filled = gray.copy()
    if fov_mask.any():
        filled[~fov_mask] = int(np.median(gray[fov_mask]))
    return filled


def _artifact_mask(gray: np.ndarray, fov_mask: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    """Detect dark bubbles, black spots, and saturated highlights."""
    filled = _fill_outside_fov(gray, fov_mask)
    sigma = max(18.0, min(gray.shape[:2]) / 28.0)
    background = cv2.GaussianBlur(filled, (0, 0), sigmaX=sigma, sigmaY=sigma)
    dark_residual = background.astype(np.int16) - filled.astype(np.int16)
    bright_residual = filled.astype(np.int16) - background.astype(np.int16)

    fov_values = gray[fov_mask] if fov_mask.any() else gray.reshape(-1)
    dark_values = dark_residual[fov_mask] if fov_mask.any() else dark_residual.reshape(-1)
    bright_values = bright_residual[fov_mask] if fov_mask.any() else bright_residual.reshape(-1)
    dark_threshold = max(9.0, float(np.percentile(dark_values, 72)))
    bright_threshold = max(28.0, float(np.percentile(bright_values, 98.5)))
    absolute_dark = float(np.percentile(fov_values, 18))

    mask = (
        ((dark_residual > dark_threshold) | (gray < absolute_dark))
        | (bright_residual > bright_threshold)
        | (gray >= 252)
    ) & fov_mask

    small = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    medium = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    mask_u8 = mask.astype(np.uint8)
    mask_u8 = cv2.morphologyEx(mask_u8, cv2.MORPH_OPEN, small)
    mask_u8 = cv2.morphologyEx(mask_u8, cv2.MORPH_CLOSE, medium)
    mask_u8 = cv2.dilate(mask_u8, medium, iterations=2)
    mask = (mask_u8 > 0) & fov_mask

    return mask, {
        "background_sigma_px": sigma,
        "dark_residual_threshold": dark_threshold,
        "bright_residual_threshold": bright_threshold,
        "absolute_dark_threshold": absolute_dark,
        "artifact_fraction_of_fov": float(mask.sum() / max(1, fov_mask.sum())),
    }


def _inpaint_and_smooth(gray: np.ndarray, artifact_mask: np.ndarray, fov_mask: np.ndarray) -> np.ndarray:
    working = _fill_outside_fov(gray, fov_mask)
    inpaint_mask = artifact_mask.astype(np.uint8) * 255
    inpainted = working.copy()
    for radius in (5, 9, 13):
        inpainted = cv2.inpaint(inpainted, inpaint_mask, radius, cv2.INPAINT_TELEA)
        inpaint_mask = cv2.erode(inpaint_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))

    smooth = cv2.medianBlur(inpainted, 9)
    smooth = cv2.GaussianBlur(smooth, (0, 0), sigmaX=10.0, sigmaY=10.0)
    large = cv2.GaussianBlur(smooth, (0, 0), sigmaX=max(25.0, min(gray.shape[:2]) / 32.0))
    blend = np.clip(0.35 * smooth.astype(np.float32) + 0.65 * large.astype(np.float32), 0, 255).astype(np.uint8)
    result = gray.copy()
    result[fov_mask] = blend[fov_mask]
    result[~fov_mask] = gray[~fov_mask]
    return result


def _homogenize_water_background(background_gray: np.ndarray, fov_mask: np.ndarray, original_gray: np.ndarray) -> np.ndarray:
    """Create a stronger low-frequency water/background candidate."""
    filled = _fill_outside_fov(background_gray, fov_mask)
    low = cv2.GaussianBlur(filled, (0, 0), sigmaX=24.0, sigmaY=24.0)
    very_low = cv2.GaussianBlur(filled, (0, 0), sigmaX=max(55.0, min(filled.shape[:2]) / 14.0))
    blend = np.clip(0.35 * low.astype(np.float32) + 0.65 * very_low.astype(np.float32), 0, 255)
    if fov_mask.any():
        median = float(np.median(blend[fov_mask]))
        blend = np.clip(median + 0.65 * (blend - median), 0, 255)
    result = original_gray.copy()
    result[fov_mask] = blend.astype(np.uint8)[fov_mask]
    result[~fov_mask] = original_gray[~fov_mask]
    return result


def create_synthetic_background(image: np.ndarray) -> dict[str, Any]:
    gray = as_uint8_grayscale(image)
    fov_mask, fov_diagnostics = detect_fov_mask(gray)
    artifact_mask, artifact_diagnostics = _artifact_mask(gray, fov_mask)
    background_gray = _inpaint_and_smooth(gray, artifact_mask, fov_mask)
    homogeneous_gray = _homogenize_water_background(background_gray, fov_mask, gray)
    background_rgb = np.stack([background_gray, background_gray, background_gray], axis=-1)
    homogeneous_rgb = np.stack([homogeneous_gray, homogeneous_gray, homogeneous_gray], axis=-1)
    return {
        "background_rgb": background_rgb,
        "background_gray": background_gray,
        "homogeneous_background_rgb": homogeneous_rgb,
        "homogeneous_background_gray": homogeneous_gray,
        "artifact_mask": artifact_mask,
        "fov_mask": fov_mask,
        "diagnostics": {
            "fov": fov_diagnostics,
            "artifact_detection": artifact_diagnostics,
            "warning": (
                "Synthetic background created from a bubble image. Prefer a true captured "
                "background image for final scientific analysis when possible."
            ),
        },
    }


def save_image_rgb(array: np.ndarray, path: Path) -> None:
    Image.fromarray(array.astype(np.uint8), mode="RGB").save(path)


def save_mask(mask: np.ndarray, path: Path) -> None:
    Image.fromarray((mask.astype(np.uint8) * 255), mode="L").save(path)


def save_comparison(original: np.ndarray, background: np.ndarray, mask: np.ndarray, path: Path) -> None:
    original_img = Image.fromarray(original.astype(np.uint8), mode="RGB")
    background_img = Image.fromarray(background.astype(np.uint8), mode="RGB")
    mask_rgb = np.zeros_like(background)
    mask_rgb[..., 0] = mask.astype(np.uint8) * 255
    mask_img = Image.fromarray(mask_rgb, mode="RGB")
    width, height = original_img.size
    canvas = Image.new("RGB", (width * 3, height + 34), "white")
    canvas.paste(original_img, (0, 34))
    canvas.paste(mask_img, (width, 34))
    canvas.paste(background_img, (width * 2, 34))
    draw = ImageDraw.Draw(canvas)
    draw.text((10, 10), "Original", fill=(0, 0, 0))
    draw.text((width + 10, 10), "Artifact mask", fill=(0, 0, 0))
    draw.text((width * 2 + 10, 10), "Synthetic background", fill=(0, 0, 0))
    canvas.save(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a synthetic BubMask background image.")
    parser.add_argument("--input", required=True, help="Input bubble image")
    parser.add_argument("--output-dir", required=True, help="Directory for generated files")
    parser.add_argument("--stem", default="", help="Output filename stem")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = args.stem or input_path.stem

    image = load_image(input_path)
    result = create_synthetic_background(image)

    png_path = output_dir / f"{stem}_synthetic_background.png"
    tif_path = output_dir / f"{stem}_synthetic_background.tif"
    homogeneous_png_path = output_dir / f"{stem}_homogeneous_background.png"
    homogeneous_tif_path = output_dir / f"{stem}_homogeneous_background.tif"
    mask_path = output_dir / f"{stem}_removed_artifact_mask.png"
    fov_path = output_dir / f"{stem}_fov_mask.png"
    comparison_path = output_dir / f"{stem}_background_generation_comparison.png"
    diagnostics_path = output_dir / f"{stem}_background_generation_diagnostics.json"

    save_image_rgb(result["background_rgb"], png_path)
    save_image_rgb(result["background_rgb"], tif_path)
    save_image_rgb(result["homogeneous_background_rgb"], homogeneous_png_path)
    save_image_rgb(result["homogeneous_background_rgb"], homogeneous_tif_path)
    save_mask(result["artifact_mask"], mask_path)
    save_mask(result["fov_mask"], fov_path)
    save_comparison(image, result["background_rgb"], result["artifact_mask"], comparison_path)
    diagnostics_path.write_text(json.dumps(result["diagnostics"], indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps({
        "png": str(png_path),
        "tif": str(tif_path),
        "homogeneous_png": str(homogeneous_png_path),
        "homogeneous_tif": str(homogeneous_tif_path),
        "artifact_mask": str(mask_path),
        "fov_mask": str(fov_path),
        "comparison": str(comparison_path),
        "diagnostics": str(diagnostics_path),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
