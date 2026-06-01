"""Measurement helpers for BubMask-Fiji detections."""

from __future__ import annotations

import math
from typing import Any

import numpy as np


def equivalent_diameter(area: float, pixel_width: float, pixel_height: float) -> float:
    area_calibrated = area * pixel_width * pixel_height
    return 2.0 * math.sqrt(area_calibrated / math.pi)


def bbox_touches_border(bbox: list[float], width: int, height: int, margin: float = 1.0) -> bool:
    x, y, w, h = bbox
    return x <= margin or y <= margin or (x + w) >= (width - margin) or (y + h) >= (height - margin)


def saturated_highlight_fraction(
    image: np.ndarray,
    mask: np.ndarray | None,
    threshold: int = 250,
) -> float:
    if mask is None or mask.size == 0 or not mask.any():
        return 0.0
    if image.ndim == 3:
        gray = image[:, :, 0]
    else:
        gray = image
    values = gray[mask.astype(bool)]
    if values.size == 0:
        return 0.0
    return float((values >= threshold).sum() / values.size)


def mask_centroid(mask: np.ndarray | None, bbox: list[float]) -> tuple[float, float]:
    if mask is not None and mask.size > 0 and mask.any():
        ys, xs = np.nonzero(mask)
        return float(xs.mean()), float(ys.mean())
    x, y, w, h = bbox
    return x + w / 2.0, y + h / 2.0


def build_measurement(
    bubble_id: int,
    score: float,
    area_px: float,
    bbox: list[float],
    pixel_width: float,
    pixel_height: float,
    unit: str,
    image_width: int,
    image_height: int,
    mask: np.ndarray | None = None,
    image: np.ndarray | None = None,
    confidence_threshold: float = 0.5,
) -> dict[str, Any]:
    cx, cy = mask_centroid(mask, bbox)
    area_calibrated = area_px * pixel_width * pixel_height
    diameter = equivalent_diameter(area_px, pixel_width, pixel_height)
    touches_border = bbox_touches_border(bbox, image_width, image_height)
    highlight_fraction = saturated_highlight_fraction(image, mask) if image is not None else 0.0
    contains_highlight = highlight_fraction > 0.01
    low_confidence = score < confidence_threshold
    flags: list[str] = []
    if touches_border:
        flags.append("touches_border")
    if contains_highlight:
        flags.append("contains_saturated_highlight")
    if low_confidence:
        flags.append("low_confidence")

    return {
        "bubble_id": bubble_id,
        "score": score,
        "area_px": area_px,
        "area_calibrated": area_calibrated,
        "equivalent_diameter_px": 2.0 * math.sqrt(area_px / math.pi) if area_px > 0 else 0.0,
        "equivalent_diameter_calibrated": diameter,
        "diameter_unit": unit,
        "centroid_x_px": cx,
        "centroid_y_px": cy,
        "bbox_x_px": bbox[0],
        "bbox_y_px": bbox[1],
        "bbox_width_px": bbox[2],
        "bbox_height_px": bbox[3],
        "touches_border": touches_border,
        "contains_saturated_highlight": contains_highlight,
        "saturated_highlight_fraction": highlight_fraction,
        "low_confidence": low_confidence,
        "accepted": not low_confidence,
        "flags": flags,
    }
