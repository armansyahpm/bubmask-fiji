"""Conservative denoising and normalization profiles for BubMask-Fiji."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np


@dataclass(frozen=True)
class PreprocessingSettings:
    """Settings for deterministic preprocessing before inference."""

    profile: str = "raw_model"
    background_sigma_px: float = 0.0
    median_kernel: int = 3
    gaussian_kernel: int = 3
    clahe_clip_limit: float = 2.0
    clahe_tile_grid_size: int = 8
    fov_min_fraction: float = 0.10
    background_correction_mode: str = "none"


def as_uint8_grayscale(image: np.ndarray) -> np.ndarray:
    """Convert an image array to uint8 grayscale using robust percentiles."""
    if image.ndim == 3:
        gray = cv2.cvtColor(image[:, :, :3], cv2.COLOR_RGB2GRAY)
    else:
        gray = image
    if gray.dtype == np.uint8:
        return gray
    gray = gray.astype(np.float32)
    low, high = np.percentile(gray, [1, 99])
    if high <= low:
        return np.zeros(gray.shape, dtype=np.uint8)
    gray = np.clip((gray - low) * 255.0 / (high - low), 0, 255)
    return gray.astype(np.uint8)


def _odd_kernel(value: int, minimum: int = 3) -> int:
    value = max(minimum, int(value))
    if value % 2 == 0:
        value += 1
    return value


def _percentile_normalize(gray: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
    values = gray[mask] if mask is not None and mask.any() else gray.reshape(-1)
    low, high = np.percentile(values.astype(np.float32), [1, 99])
    if high <= low:
        return gray.astype(np.uint8, copy=False)
    out = np.clip((gray.astype(np.float32) - low) * 255.0 / (high - low), 0, 255)
    return out.astype(np.uint8)


def detect_fov_mask(gray: np.ndarray, min_fraction: float = 0.10) -> tuple[np.ndarray, dict[str, Any]]:
    """Detect the useful field of view by removing very dark border regions.

    The method is intentionally conservative. If no plausible single FOV
    component is found, it returns an all-true mask so preprocessing does not
    accidentally crop valid image content.
    """
    threshold = max(5, int(np.percentile(gray, 1) + 4))
    candidate = (gray > threshold).astype(np.uint8)
    kernel_size = max(9, _odd_kernel(min(gray.shape[:2]) // 80, 9))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    candidate = cv2.morphologyEx(candidate, cv2.MORPH_CLOSE, kernel)
    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(candidate, 8)
    total = gray.shape[0] * gray.shape[1]
    if count <= 1:
        mask = np.ones(gray.shape, dtype=bool)
        return mask, {
            "detected": False,
            "reason": "no_connected_component",
            "area_fraction": 1.0,
            "threshold": threshold,
        }
    areas = stats[1:, cv2.CC_STAT_AREA]
    largest = int(np.argmax(areas) + 1)
    area_fraction = float(stats[largest, cv2.CC_STAT_AREA] / total)
    if area_fraction < min_fraction:
        mask = np.ones(gray.shape, dtype=bool)
        return mask, {
            "detected": False,
            "reason": "largest_component_too_small",
            "area_fraction": area_fraction,
            "threshold": threshold,
        }
    mask = labels == largest
    mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, kernel).astype(bool)
    return mask, {
        "detected": True,
        "reason": "largest_non_dark_component",
        "area_fraction": float(mask.sum() / total),
        "threshold": threshold,
    }


def _fill_outside_fov(gray: np.ndarray, fov_mask: np.ndarray) -> np.ndarray:
    if fov_mask is None or not fov_mask.any() or fov_mask.all():
        return gray
    filled = gray.copy()
    fill_value = int(np.median(gray[fov_mask]))
    filled[~fov_mask] = fill_value
    return filled


def _background_correct(gray: np.ndarray, fov_mask: np.ndarray, sigma_px: float) -> np.ndarray:
    if sigma_px <= 0:
        sigma_px = max(15.0, min(gray.shape[:2]) / 35.0)
    filled = _fill_outside_fov(gray, fov_mask)
    background = cv2.GaussianBlur(filled, (0, 0), sigmaX=float(sigma_px), sigmaY=float(sigma_px))
    reference = float(np.median(background[fov_mask])) if fov_mask.any() else float(np.median(background))
    corrected = filled.astype(np.float32) - background.astype(np.float32) + reference
    corrected = np.clip(corrected, 0, 255).astype(np.uint8)
    return _percentile_normalize(corrected, fov_mask)


def _apply_clahe(gray: np.ndarray, settings: PreprocessingSettings) -> np.ndarray:
    tile = max(2, int(settings.clahe_tile_grid_size))
    clahe = cv2.createCLAHE(
        clipLimit=max(0.1, float(settings.clahe_clip_limit)),
        tileGridSize=(tile, tile),
    )
    return clahe.apply(gray)


def _to_rgb(gray: np.ndarray) -> np.ndarray:
    return np.stack([gray, gray, gray], axis=-1).astype(np.uint8)


def apply_background_image_correction(
    image: np.ndarray,
    background_image: np.ndarray | None,
    mode: str = "none",
    offset: float = 0.0,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Apply an optional captured-background correction image.

    The legacy Bubble Analyser classical branch used absolute difference for
    foreground/background separation. BubMask-Fiji keeps this explicit and
    logged because background correction changes the image seen by the model.
    """
    mode = (mode or "none").strip().lower()
    if background_image is None or mode == "none":
        return image, {
            "mode": "none",
            "applied": False,
            "reason": "no_background_image_or_disabled",
        }
    target_gray = as_uint8_grayscale(image)
    background_gray = as_uint8_grayscale(background_image)
    if background_gray.shape != target_gray.shape:
        background_gray = cv2.resize(
            background_gray,
            (target_gray.shape[1], target_gray.shape[0]),
            interpolation=cv2.INTER_AREA,
        )
    if mode == "absolute_difference":
        corrected = cv2.absdiff(target_gray, background_gray)
        corrected = _percentile_normalize(corrected)
    elif mode == "subtract_offset":
        corrected_float = target_gray.astype(np.float32) - background_gray.astype(np.float32) + float(offset)
        corrected = np.clip(corrected_float, 0, 255).astype(np.uint8)
        corrected = _percentile_normalize(corrected)
    else:
        return image, {
            "mode": mode,
            "applied": False,
            "reason": "unsupported_background_correction_mode",
        }
    return _to_rgb(corrected), {
        "mode": mode,
        "applied": True,
        "offset": float(offset),
        "background_shape": list(background_gray.shape),
    }


def preprocess_image(
    image: np.ndarray,
    settings: PreprocessingSettings | None = None,
) -> dict[str, Any]:
    """Apply a named preprocessing profile and return image plus diagnostics."""
    settings = settings or PreprocessingSettings()
    profile = settings.profile or "raw_model"
    if profile == "raw_model":
        return {
            "image": image,
            "fov_mask": np.ones(image.shape[:2], dtype=bool),
            "diagnostics": {
                "profile": profile,
                "steps": ["raw_model_no_preprocessing"],
                "fov": {
                    "detected": False,
                    "reason": "not_requested",
                    "area_fraction": 1.0,
                },
            },
        }

    gray = as_uint8_grayscale(image)
    fov_mask, fov_diagnostics = detect_fov_mask(gray, settings.fov_min_fraction)
    steps = ["grayscale", "fov_mask"]
    processed = _background_correct(gray, fov_mask, settings.background_sigma_px)
    steps.append("background_flatfield_correction")

    if profile in {"conservative_denoise_model", "classical_diagnostic"}:
        median_kernel = _odd_kernel(settings.median_kernel)
        processed = cv2.medianBlur(processed, median_kernel)
        steps.append(f"median_blur_{median_kernel}")
        gaussian_kernel = _odd_kernel(settings.gaussian_kernel)
        processed = cv2.GaussianBlur(processed, (gaussian_kernel, gaussian_kernel), 0)
        steps.append(f"gaussian_blur_{gaussian_kernel}")

    if profile == "classical_diagnostic":
        processed = _apply_clahe(processed, settings)
        steps.append("clahe")

    processed = _fill_outside_fov(processed, fov_mask)
    return {
        "image": _to_rgb(processed),
        "fov_mask": fov_mask,
        "diagnostics": {
            "profile": profile,
            "steps": steps,
            "fov": fov_diagnostics,
            "settings": {
                "background_sigma_px": settings.background_sigma_px,
                "median_kernel": settings.median_kernel,
                "gaussian_kernel": settings.gaussian_kernel,
                "clahe_clip_limit": settings.clahe_clip_limit,
                "clahe_tile_grid_size": settings.clahe_tile_grid_size,
                "fov_min_fraction": settings.fov_min_fraction,
            },
        },
    }
