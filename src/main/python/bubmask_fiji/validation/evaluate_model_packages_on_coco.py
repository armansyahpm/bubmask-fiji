"""Evaluate BubMask model packages against COCO segmentation masks.

This script runs the same ``bubmask_worker.py`` process used by Fiji, then
compares the exported instance label image with Roboflow COCO ground-truth
masks. It reports operational precision/recall at IoU 0.50 and 0.75.

The intent is honest model comparison, not a replacement for a full COCO mAP
benchmark. The worker confidence threshold still applies.
"""

from __future__ import annotations

import argparse
import csv
import gc
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from bubmask_fiji.training.coco_dataset import BubbleCocoDataset


def parse_model(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("Model must be provided as name=path")
    name, path = value.split("=", 1)
    return name.strip(), Path(path).expanduser().resolve()


def safe_slug(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value).strip("_") or "item"


def condition_from_name(value: str) -> str:
    lowered = value.lower()
    if "without_particle" in lowered:
        return "without_particle"
    if "with_particle" in lowered:
        return "with_particle"
    return "unknown"


def load_dataset(dataset_dir: Path, split: str) -> BubbleCocoDataset:
    dataset = BubbleCocoDataset()
    dataset.load_bubble_coco(dataset_dir, split)
    dataset.prepare()
    return dataset


def build_request(
    image_path: Path,
    model_package: Path,
    run_output_dir: Path,
    args: argparse.Namespace,
) -> dict[str, Any]:
    return {
        "schema_version": "bubmask.request.v1",
        "source_title": image_path.name,
        "image_path": str(image_path),
        "model_package": str(model_package),
        "inference_mode": "bubmask_mask_rcnn",
        "confidence_threshold": args.confidence_threshold,
        "preprocessing_profile": args.preprocessing_profile,
        "background_correction_mode": "none",
        "quality_gate_mode": "review_only",
        "measure_sharp_bubbles_only": False,
        "min_focus_score": 10.0,
        "min_diameter_px": 0.0,
        "max_diameter_px": 0.0,
        "calibration_status": "known",
        "calibration_source": "evaluation_px_per_mm",
        "px_per_mm": args.px_per_mm,
        "run_output_dir": str(run_output_dir),
    }


def write_request(
    path: Path,
    image_path: Path,
    model_package: Path,
    run_output_dir: Path,
    args: argparse.Namespace,
) -> None:
    request = build_request(image_path, model_package, run_output_dir, args)
    path.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_response(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def mask_bbox(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    ys, xs = np.nonzero(mask)
    if xs.size == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def boxes_intersect(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def union_bbox(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    return min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])


def predictions_from_label_image(labels: np.ndarray | None, scores_by_id: dict[int, float]) -> list[dict[str, Any]]:
    if labels is None:
        return []
    predictions = []
    for label in sorted(int(v) for v in np.unique(labels) if int(v) > 0):
        mask = labels == label
        bbox = mask_bbox(mask)
        if bbox is not None:
            predictions.append({
                "id": label,
                "score": float(scores_by_id.get(label, 0.0)),
                "mask": mask,
                "bbox": bbox,
            })
    return predictions


def load_predicted_masks(label_path: str | None, scores_by_id: dict[int, float]) -> list[dict[str, Any]]:
    if not label_path:
        return []
    path = Path(label_path)
    if not path.is_file():
        return []
    return predictions_from_label_image(np.array(Image.open(path)), scores_by_id)


def predictions_from_mask_rcnn_result(result: dict[str, Any]) -> list[dict[str, Any]]:
    mask_stack = result.get("masks")
    if mask_stack is None or getattr(mask_stack, "ndim", 0) != 3:
        return []
    scores = result.get("scores", [])
    predictions = []
    for idx in range(mask_stack.shape[-1]):
        mask = mask_stack[:, :, idx].astype(bool)
        bbox = mask_bbox(mask)
        if bbox is not None:
            predictions.append({
                "id": idx + 1,
                "score": float(scores[idx]) if idx < len(scores) else 0.0,
                "mask": mask,
                "bbox": bbox,
            })
    return predictions


def masks_from_dataset(dataset: BubbleCocoDataset, image_id: int) -> list[dict[str, Any]]:
    mask_stack, _class_ids = dataset.load_mask(image_id)
    if mask_stack.ndim != 3:
        return []
    masks = []
    for idx in range(mask_stack.shape[-1]):
        mask = mask_stack[:, :, idx].astype(bool)
        bbox = mask_bbox(mask)
        if bbox is not None:
            masks.append({"id": idx + 1, "mask": mask, "bbox": bbox})
    return masks


def compute_iou(pred: dict[str, Any], gt: dict[str, Any]) -> float:
    if not boxes_intersect(pred["bbox"], gt["bbox"]):
        return 0.0
    x0, y0, x1, y1 = union_bbox(pred["bbox"], gt["bbox"])
    pred_crop = pred["mask"][y0:y1, x0:x1]
    gt_crop = gt["mask"][y0:y1, x0:x1]
    intersection = np.logical_and(pred_crop, gt_crop).sum()
    union = np.logical_or(pred_crop, gt_crop).sum()
    return float(intersection / union) if union else 0.0


def match_image(
    predictions: list[dict[str, Any]],
    gt_masks: list[np.ndarray],
    threshold: float,
) -> tuple[int, int, int, list[dict[str, Any]]]:
    matched_gt: set[int] = set()
    rows = []
    tp = 0
    fp = 0
    for prediction in sorted(predictions, key=lambda item: item["score"], reverse=True):
        best_iou = 0.0
        best_index = -1
        for gt_index, gt_mask in enumerate(gt_masks):
            if gt_index in matched_gt:
                continue
            if not boxes_intersect(prediction["bbox"], gt_mask["bbox"]):
                continue
            iou = compute_iou(prediction, gt_mask)
            if iou > best_iou:
                best_iou = iou
                best_index = gt_index
        is_tp = best_iou >= threshold and best_index >= 0
        if is_tp:
            matched_gt.add(best_index)
            tp += 1
        else:
            fp += 1
        rows.append({
            "score": prediction["score"],
            "iou": best_iou,
            "tp": 1 if is_tp else 0,
            "fp": 0 if is_tp else 1,
        })
    fn = len(gt_masks) - len(matched_gt)
    return tp, fp, fn, rows


def precision_recall_f1(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def empty_totals() -> dict[str, float | int]:
    return {
        "images": 0,
        "gt": 0,
        "pred": 0,
        "tp50": 0,
        "fp50": 0,
        "fn50": 0,
        "tp75": 0,
        "fp75": 0,
        "fn75": 0,
        "elapsed_sec": 0.0,
    }


def add_to_totals(
    totals: dict[str, float | int],
    gt_count: int,
    prediction_count: int,
    tp50: int,
    fp50: int,
    fn50: int,
    tp75: int,
    fp75: int,
    fn75: int,
    elapsed: float,
) -> None:
    totals["images"] = int(totals["images"]) + 1
    totals["gt"] = int(totals["gt"]) + gt_count
    totals["pred"] = int(totals["pred"]) + prediction_count
    totals["tp50"] = int(totals["tp50"]) + tp50
    totals["fp50"] = int(totals["fp50"]) + fp50
    totals["fn50"] = int(totals["fn50"]) + fn50
    totals["tp75"] = int(totals["tp75"]) + tp75
    totals["fp75"] = int(totals["fp75"]) + fp75
    totals["fn75"] = int(totals["fn75"]) + fn75
    totals["elapsed_sec"] = float(totals["elapsed_sec"]) + elapsed


def summary_from_totals(
    split: str,
    model_name: str,
    condition: str,
    totals: dict[str, float | int],
) -> dict[str, Any]:
    p50, r50, f50 = precision_recall_f1(int(totals["tp50"]), int(totals["fp50"]), int(totals["fn50"]))
    p75, r75, f75 = precision_recall_f1(int(totals["tp75"]), int(totals["fp75"]), int(totals["fn75"]))
    return {
        "split": split,
        "model_name": model_name,
        "condition": condition,
        "images": int(totals["images"]),
        "ground_truth": int(totals["gt"]),
        "predictions": int(totals["pred"]),
        "tp50": int(totals["tp50"]),
        "fp50": int(totals["fp50"]),
        "fn50": int(totals["fn50"]),
        "precision50": f"{p50:.4f}",
        "recall50": f"{r50:.4f}",
        "f1_50": f"{f50:.4f}",
        "tp75": int(totals["tp75"]),
        "fp75": int(totals["fp75"]),
        "fn75": int(totals["fn75"]),
        "precision75": f"{p75:.4f}",
        "recall75": f"{r75:.4f}",
        "f1_75": f"{f75:.4f}",
        "elapsed_sec": f"{float(totals['elapsed_sec']):.2f}",
    }


def evaluate_split(
    dataset: BubbleCocoDataset,
    split: str,
    model_name: str,
    model_package: Path,
    output_dir: Path,
    args: argparse.Namespace,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    python_root = Path(__file__).resolve().parents[2]
    worker_path = python_root / "bubmask_worker.py"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(python_root) + os.pathsep + env.get("PYTHONPATH", "")

    image_rows: list[dict[str, Any]] = []
    totals = empty_totals()
    totals_by_condition = {
        "with_particle": empty_totals(),
        "without_particle": empty_totals(),
        "unknown": empty_totals(),
    }

    image_ids = list(dataset.image_ids)
    if args.start_index > 0:
        image_ids = image_ids[args.start_index :]
    if args.max_images > 0:
        image_ids = image_ids[: args.max_images]

    for position, image_id in enumerate(image_ids, start=1):
        info = dataset.image_info[image_id]
        image_path = Path(info["path"]).resolve()
        print(f"[{split} | {model_name}] {position}/{len(image_ids)} {image_path.name}", flush=True)
        run_dir = output_dir / split / safe_slug(model_name) / safe_slug(image_path.stem)
        run_dir.mkdir(parents=True, exist_ok=True)
        request_path = run_dir / "request.json"
        response_path = run_dir / "response.json"
        write_request(request_path, image_path, model_package, run_dir, args)

        start = time.perf_counter()
        completed = subprocess.run(
            [sys.executable, str(worker_path), "--input", str(request_path), "--output", str(response_path)],
            cwd=str(python_root),
            env=env,
            check=False,
        )
        elapsed = time.perf_counter() - start

        response = load_response(response_path)
        condition = condition_from_name(image_path.name)
        outputs = response.get("outputs", {}) if isinstance(response, dict) else {}
        scores_by_id = {
            int(mask.get("id", 0)): float(mask.get("score", 0.0))
            for mask in response.get("masks", [])
            if isinstance(mask, dict)
        }
        predictions = load_predicted_masks(outputs.get("instance_labels_tif"), scores_by_id)
        gt_masks = masks_from_dataset(dataset, image_id)

        tp50, fp50, fn50, _rows50 = match_image(predictions, gt_masks, 0.50)
        tp75, fp75, fn75, _rows75 = match_image(predictions, gt_masks, 0.75)
        p50, r50, f50 = precision_recall_f1(tp50, fp50, fn50)
        p75, r75, f75 = precision_recall_f1(tp75, fp75, fn75)

        add_to_totals(
            totals, len(gt_masks), len(predictions), tp50, fp50, fn50,
            tp75, fp75, fn75, elapsed)
        add_to_totals(
            totals_by_condition.setdefault(condition, empty_totals()),
            len(gt_masks), len(predictions), tp50, fp50, fn50, tp75, fp75, fn75,
            elapsed)

        image_rows.append({
            "split": split,
            "model_name": model_name,
            "condition": condition,
            "image": image_path.name,
            "worker_return_code": completed.returncode,
            "elapsed_sec": f"{elapsed:.2f}",
            "ground_truth": len(gt_masks),
            "predictions": len(predictions),
            "tp50": tp50,
            "fp50": fp50,
            "fn50": fn50,
            "precision50": f"{p50:.4f}",
            "recall50": f"{r50:.4f}",
            "f1_50": f"{f50:.4f}",
            "tp75": tp75,
            "fp75": fp75,
            "fn75": fn75,
            "precision75": f"{p75:.4f}",
            "recall75": f"{r75:.4f}",
            "f1_75": f"{f75:.4f}",
            "overlay_masks": outputs.get("overlay_masks_png", ""),
            "response_json": str(response_path),
        })

    summary_rows = [summary_from_totals(split, model_name, "all", totals)]
    for condition in ["with_particle", "without_particle", "unknown"]:
        condition_totals = totals_by_condition.get(condition, empty_totals())
        if int(condition_totals["images"]) > 0:
            summary_rows.append(summary_from_totals(split, model_name, condition, condition_totals))
    del model
    try:
        from tensorflow.keras import backend as keras_backend
        keras_backend.clear_session()
    except Exception:
        pass
    gc.collect()
    return image_rows, summary_rows


def load_cached_inference_model(
    model_package: Path,
    confidence_threshold: float,
) -> tuple[Any, Any]:
    python_root = Path(__file__).resolve().parents[2]
    if str(python_root) not in sys.path:
        sys.path.insert(0, str(python_root))

    from bubmask_worker import inspect_model_package
    from bubble_analyser.bubble.bubble import _InfConfig
    from bubble_analyser.mrcnn import model as modellib

    model_info = inspect_model_package(model_package)
    weights_path = Path(model_info["weights_path"])
    if not weights_path.is_file():
        raise FileNotFoundError(f"BubMask weights not found: {weights_path}")

    logs_dir = model_package / "logs"
    logs_dir.mkdir(exist_ok=True)
    config = _InfConfig()
    config.DETECTION_MIN_CONFIDENCE = confidence_threshold
    model = modellib.MaskRCNN(mode="inference", model_dir=str(logs_dir), config=config)
    model.load_weights(str(weights_path), by_name=True)
    return model, config


def evaluate_split_cached(
    dataset: BubbleCocoDataset,
    split: str,
    model_name: str,
    model_package: Path,
    output_dir: Path,
    args: argparse.Namespace,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    python_root = Path(__file__).resolve().parents[2]
    if str(python_root) not in sys.path:
        sys.path.insert(0, str(python_root))

    from bubmask_fiji.export.artifacts import label_image_from_instance_masks
    from bubmask_worker import load_image_array, prepare_images_for_inference

    image_rows: list[dict[str, Any]] = []
    totals = empty_totals()
    totals_by_condition = {
        "with_particle": empty_totals(),
        "without_particle": empty_totals(),
        "unknown": empty_totals(),
    }

    image_ids = list(dataset.image_ids)
    if args.start_index > 0:
        image_ids = image_ids[args.start_index :]
    if args.max_images > 0:
        image_ids = image_ids[: args.max_images]

    model, config = load_cached_inference_model(model_package, args.confidence_threshold)
    for position, image_id in enumerate(image_ids, start=1):
        info = dataset.image_info[image_id]
        image_path = Path(info["path"]).resolve()
        print(f"[{split} | {model_name} | cached] {position}/{len(image_ids)} {image_path.name}", flush=True)
        run_dir = output_dir / split / safe_slug(model_name) / safe_slug(image_path.stem)
        run_dir.mkdir(parents=True, exist_ok=True)
        request_path = run_dir / "request.json"
        response_path = run_dir / "cached_response.json"
        request = build_request(image_path, model_package, run_dir, args)
        request_path.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        start = time.perf_counter()
        image = load_image_array(image_path)
        inference_image, _background_corrected_image, preprocessing_diagnostics, _fov_mask = prepare_images_for_inference(
            image, request, request_path.parent)
        result = model.detect([inference_image], verbose=int(request.get("verbose", 0)))[0]
        elapsed = time.perf_counter() - start

        condition = condition_from_name(image_path.name)
        scores_by_id = {
            idx + 1: float(result.get("scores", [])[idx])
            for idx in range(len(result.get("scores", [])))
        }
        label_image = label_image_from_instance_masks(result.get("masks"))
        predictions = predictions_from_label_image(label_image, scores_by_id)
        gt_masks = masks_from_dataset(dataset, image_id)

        tp50, fp50, fn50, _rows50 = match_image(predictions, gt_masks, 0.50)
        tp75, fp75, fn75, _rows75 = match_image(predictions, gt_masks, 0.75)
        p50, r50, f50 = precision_recall_f1(tp50, fp50, fn50)
        p75, r75, f75 = precision_recall_f1(tp75, fp75, fn75)

        response = {
            "schema_version": "bubmask.cached_coco_eval.v1",
            "model_package": str(model_package),
            "image_path": str(image_path),
            "confidence_threshold": args.confidence_threshold,
            "preprocessing": preprocessing_diagnostics,
            "config": {
                "IMAGE_MIN_DIM": config.IMAGE_MIN_DIM,
                "IMAGE_MAX_DIM": config.IMAGE_MAX_DIM,
                "IMAGE_RESIZE_MODE": config.IMAGE_RESIZE_MODE,
                "DETECTION_MIN_CONFIDENCE": config.DETECTION_MIN_CONFIDENCE,
            },
            "masks": [
                {
                    "id": prediction["id"],
                    "score": prediction["score"],
                    "bbox": list(prediction["bbox"]),
                    "area_px": int(prediction["mask"].sum()),
                }
                for prediction in predictions
            ],
        }
        response_path.write_text(json.dumps(response, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        add_to_totals(
            totals, len(gt_masks), len(predictions), tp50, fp50, fn50,
            tp75, fp75, fn75, elapsed)
        add_to_totals(
            totals_by_condition.setdefault(condition, empty_totals()),
            len(gt_masks), len(predictions), tp50, fp50, fn50, tp75, fp75, fn75,
            elapsed)

        image_rows.append({
            "split": split,
            "model_name": model_name,
            "condition": condition,
            "image": image_path.name,
            "worker_return_code": 0,
            "elapsed_sec": f"{elapsed:.2f}",
            "ground_truth": len(gt_masks),
            "predictions": len(predictions),
            "tp50": tp50,
            "fp50": fp50,
            "fn50": fn50,
            "precision50": f"{p50:.4f}",
            "recall50": f"{r50:.4f}",
            "f1_50": f"{f50:.4f}",
            "tp75": tp75,
            "fp75": fp75,
            "fn75": fn75,
            "precision75": f"{p75:.4f}",
            "recall75": f"{r75:.4f}",
            "f1_75": f"{f75:.4f}",
            "overlay_masks": "",
            "response_json": str(response_path),
        })

    summary_rows = [summary_from_totals(split, model_name, "all", totals)]
    for condition in ["with_particle", "without_particle", "unknown"]:
        condition_totals = totals_by_condition.get(condition, empty_totals())
        if int(condition_totals["images"]) > 0:
            summary_rows.append(summary_from_totals(split, model_name, condition, condition_totals))
    return image_rows, summary_rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_report(path: Path, summary_rows: list[dict[str, Any]], args: argparse.Namespace) -> None:
    lines = [
        "# BubMask COCO Validation",
        "",
        "This report uses COCO masks as ground truth.",
        "",
        "Inference mode: cached in-process model reuse." if args.reuse_model else
        "Inference mode: same Python worker process boundary used by Fiji.",
        "",
        "## Settings",
        "",
        f"- Dataset: `{args.dataset}`",
        f"- Splits: `{', '.join(args.split)}`",
        f"- Confidence threshold: `{args.confidence_threshold}`",
        f"- Preprocessing profile: `{args.preprocessing_profile}`",
        "",
        "## Summary",
        "",
        "| Split | Model | Condition | Images | GT masks | Predictions | Precision@0.50 | Recall@0.50 | F1@0.50 | Precision@0.75 | Recall@0.75 | F1@0.75 |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summary_rows:
        lines.append(
            "| {split} | {model_name} | {condition} | {images} | {ground_truth} | {predictions} | "
            "{precision50} | {recall50} | {f1_50} | {precision75} | {recall75} | {f1_75} |".format(**row)
        )
    lines.extend([
        "",
        "## Interpretation Rules",
        "",
        "- Higher recall means the model finds more labelled bubbles.",
        "- Higher precision means fewer predicted masks fail to match a labelled bubble.",
        "- If the fine-tuned model increases recall but reduces precision, it should remain provisional until quality gates or more training improve false positives.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate BubMask model packages on COCO splits.")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--split", action="append", default=[], help="Split to evaluate. Repeatable.")
    parser.add_argument("--model", action="append", type=parse_model, required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--confidence-threshold", type=float, default=0.5)
    parser.add_argument("--preprocessing-profile", default="raw_model")
    parser.add_argument("--px-per-mm", type=float, default=183.0)
    parser.add_argument("--start-index", type=int, default=0, help="Optional zero-based image offset within the split.")
    parser.add_argument("--max-images", type=int, default=0, help="Optional subset size per split for quick smoke metrics.")
    parser.add_argument(
        "--reuse-model",
        action="store_true",
        help="Load each Mask R-CNN model once per split instead of launching the Fiji worker for every image.",
    )
    args = parser.parse_args(argv)
    if not args.split:
        args.split = ["valid"]

    dataset_dir = Path(args.dataset).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    image_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    for split in args.split:
        dataset = load_dataset(dataset_dir, split)
        for model_name, model_package in args.model:
            if args.reuse_model:
                rows, summaries = evaluate_split_cached(dataset, split, model_name, model_package, output_dir, args)
            else:
                rows, summaries = evaluate_split(dataset, split, model_name, model_package, output_dir, args)
            image_rows.extend(rows)
            summary_rows.extend(summaries)

    write_csv(output_dir / "coco_validation_image_metrics.csv", image_rows)
    write_csv(output_dir / "coco_validation_summary.csv", summary_rows)
    write_csv(
        output_dir / "coco_validation_condition_summary.csv",
        [row for row in summary_rows if row.get("condition") != "all"],
    )
    write_report(output_dir / "coco_validation_report.md", summary_rows, args)
    print(f"Wrote {output_dir / 'coco_validation_summary.csv'}")
    print(f"Wrote {output_dir / 'coco_validation_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
