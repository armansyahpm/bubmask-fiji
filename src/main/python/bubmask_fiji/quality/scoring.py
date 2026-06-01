"""Per-detection quality scoring for BubMask-Fiji."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from bubmask_fiji.preprocessing.denoise import as_uint8_grayscale


@dataclass(frozen=True)
class QualitySettings:
    """Settings for accepted/review/rejected bubble decisions."""

    gate_mode: str = "review_only"
    min_diameter_px: float = 0.0
    max_diameter_px: float = 0.0
    min_circularity: float = 0.06
    min_solidity: float = 0.20
    min_boundary_gradient: float = 2.0
    min_annular_contrast: float = 0.015
    min_focus_score: float = 0.0
    measure_sharp_bubbles_only: bool = False


def _bbox_slices(bbox: list[float], shape: tuple[int, int], pad: int = 4) -> tuple[slice, slice]:
    x, y, w, h = bbox
    height, width = shape
    x0 = max(0, int(np.floor(x)) - pad)
    y0 = max(0, int(np.floor(y)) - pad)
    x1 = min(width, int(np.ceil(x + w)) + pad)
    y1 = min(height, int(np.ceil(y + h)) + pad)
    return slice(y0, y1), slice(x0, x1)


def _mask_geometry(mask: np.ndarray | None, bbox: list[float], area_px: float) -> dict[str, float]:
    if mask is None or not mask.any():
        x, y, w, h = bbox
        perimeter = 2.0 * (w + h) if w > 0 and h > 0 else 0.0
        circularity = float(4.0 * np.pi * area_px / (perimeter * perimeter)) if perimeter > 0 else 0.0
        aspect_ratio = float(w / h) if h > 0 else 0.0
        return {
            "perimeter_px": perimeter,
            "circularity": circularity,
            "solidity": 1.0,
            "eccentricity": 0.0,
            "bbox_aspect_ratio": aspect_ratio,
        }

    mask_u8 = mask.astype(np.uint8)
    contours, _hierarchy = cv2.findContours(mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return {
            "perimeter_px": 0.0,
            "circularity": 0.0,
            "solidity": 0.0,
            "eccentricity": 0.0,
            "bbox_aspect_ratio": 0.0,
        }
    contour = max(contours, key=cv2.contourArea)
    perimeter = float(cv2.arcLength(contour, True))
    contour_area = float(cv2.contourArea(contour))
    circularity = float(4.0 * np.pi * area_px / (perimeter * perimeter)) if perimeter > 0 else 0.0
    hull = cv2.convexHull(contour)
    hull_area = float(cv2.contourArea(hull))
    solidity = float(contour_area / hull_area) if hull_area > 0 else 0.0
    ys, xs = np.nonzero(mask)
    if xs.size >= 3:
        coords = np.column_stack([xs.astype(np.float32), ys.astype(np.float32)])
        cov = np.cov(coords, rowvar=False)
        eigvals = np.sort(np.linalg.eigvalsh(cov))
        if eigvals[-1] > 0:
            eccentricity = float(np.sqrt(max(0.0, 1.0 - eigvals[0] / eigvals[-1])))
        else:
            eccentricity = 0.0
    else:
        eccentricity = 0.0
    x, y, w, h = bbox
    aspect_ratio = float(w / h) if h > 0 else 0.0
    return {
        "perimeter_px": perimeter,
        "circularity": circularity,
        "solidity": solidity,
        "eccentricity": eccentricity,
        "bbox_aspect_ratio": aspect_ratio,
    }


def _focus_score(gray: np.ndarray, bbox: list[float]) -> float:
    ys, xs = _bbox_slices(bbox, gray.shape, pad=4)
    crop = gray[ys, xs]
    if crop.size < 9:
        return 0.0
    return float(cv2.Laplacian(crop, cv2.CV_64F).var())


def _boundary_gradient_score(gray: np.ndarray, mask: np.ndarray | None) -> float:
    if mask is None or not mask.any():
        return 0.0
    mask_u8 = mask.astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    dilated = cv2.dilate(mask_u8, kernel)
    eroded = cv2.erode(mask_u8, kernel)
    boundary = dilated.astype(bool) & ~eroded.astype(bool)
    if not boundary.any():
        return 0.0
    grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = cv2.magnitude(grad_x, grad_y)
    return float(np.mean(magnitude[boundary]))


def _annular_contrast(gray: np.ndarray, mask: np.ndarray | None) -> float:
    if mask is None or not mask.any():
        return 0.0
    mask_u8 = mask.astype(np.uint8)
    inner_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    outer_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    eroded = cv2.erode(mask_u8, inner_kernel).astype(bool)
    inner = eroded if eroded.any() else mask.astype(bool)
    outer = cv2.dilate(mask_u8, outer_kernel).astype(bool) & ~mask.astype(bool)
    if not outer.any():
        return 0.0
    object_median = float(np.median(gray[inner]))
    outer_median = float(np.median(gray[outer]))
    return abs(object_median - outer_median) / 255.0


def score_detection_quality(
    measurement: dict[str, Any],
    mask: np.ndarray | None,
    image: np.ndarray,
    settings: QualitySettings | None = None,
) -> dict[str, Any]:
    """Return scientific quality status and diagnostic features for a detection."""
    settings = settings or QualitySettings()
    gray = as_uint8_grayscale(image)
    bbox = [
        float(measurement.get("bbox_x_px", 0.0)),
        float(measurement.get("bbox_y_px", 0.0)),
        float(measurement.get("bbox_width_px", 0.0)),
        float(measurement.get("bbox_height_px", 0.0)),
    ]
    area_px = float(measurement.get("area_px", 0.0))
    diameter_px = float(measurement.get("equivalent_diameter_px", 0.0))
    geometry = _mask_geometry(mask, bbox, area_px)
    focus = _focus_score(gray, bbox)
    boundary_gradient = _boundary_gradient_score(gray, mask)
    annular = _annular_contrast(gray, mask)

    reject_reasons: list[str] = []
    review_reasons: list[str] = []
    if measurement.get("low_confidence", False):
        review_reasons.append("low_confidence")
    if measurement.get("touches_border", False):
        review_reasons.append("border_touching")
    if measurement.get("contains_saturated_highlight", False):
        review_reasons.append("saturated_highlight")
    if settings.min_diameter_px > 0 and diameter_px < settings.min_diameter_px:
        reject_reasons.append("below_min_diameter")
    if settings.max_diameter_px > 0 and diameter_px > settings.max_diameter_px:
        reject_reasons.append("above_max_diameter")
    if (
        geometry["circularity"] < settings.min_circularity
        and geometry["solidity"] < settings.min_solidity
    ):
        reject_reasons.append("too_irregular")
    elif geometry["circularity"] < settings.min_circularity:
        review_reasons.append("low_circularity")
    elif geometry["solidity"] < settings.min_solidity:
        review_reasons.append("low_solidity")
    if boundary_gradient < settings.min_boundary_gradient:
        review_reasons.append("low_boundary_gradient")
    if annular < settings.min_annular_contrast:
        review_reasons.append("low_annular_contrast")
    if settings.measure_sharp_bubbles_only and focus < settings.min_focus_score:
        review_reasons.append("blurred")

    gate_mode = settings.gate_mode or "review_only"
    if gate_mode == "off":
        status = "raw_model_detection"
        accepted_for_histogram = not bool(measurement.get("low_confidence", False))
    elif reject_reasons:
        status = "rejected_nonbubble"
        accepted_for_histogram = False
    elif review_reasons:
        status = "review_bubble"
        accepted_for_histogram = gate_mode != "filter_histogram"
    else:
        status = "accepted_bubble"
        accepted_for_histogram = True

    quality_flags = reject_reasons + review_reasons
    return {
        "measurement_status": status,
        "accepted_for_histogram": accepted_for_histogram,
        "rejection_reason": ";".join(quality_flags),
        "quality_flags": quality_flags,
        "focus_score": focus,
        "boundary_gradient_score": boundary_gradient,
        "annular_contrast": annular,
        **geometry,
        "quality_gate_mode": gate_mode,
        "quality_thresholds": {
            "min_diameter_px": settings.min_diameter_px,
            "max_diameter_px": settings.max_diameter_px,
            "min_circularity": settings.min_circularity,
            "min_solidity": settings.min_solidity,
            "min_boundary_gradient": settings.min_boundary_gradient,
            "min_annular_contrast": settings.min_annular_contrast,
            "min_focus_score": settings.min_focus_score,
            "measure_sharp_bubbles_only": settings.measure_sharp_bubbles_only,
        },
    }


def summarize_quality(measurements: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "accepted_bubble": 0,
        "review_bubble": 0,
        "rejected_nonbubble": 0,
        "raw_model_detection": 0,
        "accepted_for_histogram": 0,
    }
    for row in measurements:
        status = str(row.get("measurement_status", "raw_model_detection"))
        counts[status] = counts.get(status, 0) + 1
        if bool(row.get("accepted_for_histogram", row.get("accepted", False))):
            counts["accepted_for_histogram"] += 1
    return counts
