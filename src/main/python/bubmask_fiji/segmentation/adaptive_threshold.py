"""Adaptive-threshold baseline segmentation for BubMask-Fiji."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np


@dataclass(frozen=True)
class AdaptiveThresholdSettings:
    block_size: int = 51
    c: int = 5
    min_area_px: int = 16
    blur_kernel: int = 5


def _as_uint8_grayscale(image: np.ndarray) -> np.ndarray:
    if image.ndim == 3:
        image = cv2.cvtColor(image[:, :, :3], cv2.COLOR_RGB2GRAY)
    if image.dtype == np.uint8:
        return image
    image = image.astype(np.float32)
    low, high = np.percentile(image, [1, 99])
    if high <= low:
        return np.zeros(image.shape, dtype=np.uint8)
    image = np.clip((image - low) * 255.0 / (high - low), 0, 255)
    return image.astype(np.uint8)


def segment_adaptive_threshold(
    image: np.ndarray,
    settings: AdaptiveThresholdSettings | None = None,
) -> dict[str, Any]:
    """Return candidate bubble labels and measurements.

    This is a transparent baseline/fallback method, not the primary BubMask
    Mask R-CNN production path.
    """
    settings = settings or AdaptiveThresholdSettings()
    block_size = settings.block_size
    if block_size % 2 == 0:
        block_size += 1
    block_size = max(3, block_size)

    gray = _as_uint8_grayscale(image)
    if settings.blur_kernel > 1:
        kernel = settings.blur_kernel + (settings.blur_kernel + 1) % 2
        gray = cv2.medianBlur(gray, kernel)

    binary = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        block_size,
        settings.c,
    )
    element = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, element)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, element)

    count, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, 8)
    objects: list[dict[str, Any]] = []
    kept = np.zeros_like(labels, dtype=np.int32)
    next_id = 1
    for component_id in range(1, count):
        area = int(stats[component_id, cv2.CC_STAT_AREA])
        if area < settings.min_area_px:
            continue
        x = int(stats[component_id, cv2.CC_STAT_LEFT])
        y = int(stats[component_id, cv2.CC_STAT_TOP])
        w = int(stats[component_id, cv2.CC_STAT_WIDTH])
        h = int(stats[component_id, cv2.CC_STAT_HEIGHT])
        cx, cy = centroids[component_id]
        kept[labels == component_id] = next_id
        objects.append({
            "id": next_id,
            "area_px": float(area),
            "bbox": [float(x), float(y), float(w), float(h)],
            "centroid_x_px": float(cx),
            "centroid_y_px": float(cy),
        })
        next_id += 1

    return {
        "method": "adaptive_threshold_baseline",
        "settings": {
            "block_size": block_size,
            "c": settings.c,
            "min_area_px": settings.min_area_px,
            "blur_kernel": settings.blur_kernel,
        },
        "object_count": len(objects),
        "objects": objects,
        "label_image": kept,
    }
