#!/usr/bin/env python3
"""Resumable batch runner for BubMask-Fiji Mask R-CNN measurements."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

PYTHON_ROOT = Path(__file__).resolve().parents[2]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from bubmask_fiji.histogram.histograms import (
    distribution_summary,
    export_histogram_artifacts,
    measurement_values,
)


REQUEST_SCHEMA = "bubmask.request.v1"
BATCH_SCHEMA = "bubmask.batch.v1"
IMAGE_EXTENSIONS = {".tif", ".tiff"}
METADATA_FIELDS = [
    "image_id",
    "image_path",
    "source_title",
    "run_dir",
    "condition",
    "pressure",
    "vent_geometry",
    "nominal_size",
    "flow_rate",
    "replicate_image",
]
GROUP_LEVELS = [
    ("all_images", []),
    ("by_condition", ["condition"]),
    ("by_flow_rate", ["flow_rate"]),
    ("by_pressure", ["pressure"]),
    ("by_vent_geometry", ["vent_geometry"]),
    ("by_replicate_image", ["replicate_image"]),
    ("by_condition_flow_pressure_vent", ["condition", "flow_rate", "pressure", "vent_geometry"]),
]


def python_root() -> Path:
    return Path(__file__).resolve().parents[2]


def project_root() -> Path:
    return Path(__file__).resolve().parents[5]


def default_model_package() -> Path:
    return project_root() / "models" / "bubmask-maskrcnn-unsw-round3-v1"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def safe_slug(value: str) -> str:
    slug = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:120] or "image"


def parse_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_decimal_token(token: str) -> str:
    if token.count("-") == 1:
        left, right = token.split("-", 1)
        if left.isdigit() and right.isdigit():
            return f"{left}.{right}"
    return token


def infer_metadata_from_path(path: Path) -> dict[str, str]:
    text = str(path).replace("\\", "/").lower()
    stem = path.stem.lower()
    metadata: dict[str, str] = {
        "condition": "unknown",
        "pressure": "",
        "vent_geometry": "",
        "nominal_size": "",
        "flow_rate": "",
        "replicate_image": path.stem,
    }
    if "without_particle" in text:
        metadata["condition"] = "without_particle"
    elif "with_particle" in text:
        metadata["condition"] = "with_particle"

    pressure = re.search(r"(\d+(?:-\d+)?)atm", stem)
    if pressure:
        metadata["pressure"] = f"{normalize_decimal_token(pressure.group(1))}atm"

    vent = re.search(r"(\d+)vent", stem)
    if vent:
        metadata["vent_geometry"] = f"{vent.group(1)}vent"

    nominal = re.search(r"(\d+(?:-\d+)?)mm", stem)
    if nominal:
        metadata["nominal_size"] = f"{normalize_decimal_token(nominal.group(1))}mm"

    flow = re.search(r"(\d+(?:-\d+)?)lpm", stem)
    if flow:
        metadata["flow_rate"] = f"{normalize_decimal_token(flow.group(1))}lpm"

    replicate = re.search(r"(s\d+)$", stem)
    if replicate:
        metadata["replicate_image"] = replicate.group(1).upper()
    else:
        trailing_number = re.search(r"(\d+)$", stem)
        if trailing_number:
            metadata["replicate_image"] = trailing_number.group(1)
    return metadata


def resolve_manifest_image(row: dict[str, str], manifest_path: Path) -> Path:
    raw = row.get("image_path") or row.get("path") or row.get("relative_path") or ""
    if not raw:
        raise ValueError("Manifest row is missing image_path, path, or relative_path")
    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    manifest_relative = (manifest_path.parent / candidate).resolve()
    if manifest_relative.is_file():
        return manifest_relative
    return (project_root() / candidate).resolve()


def merge_metadata(path: Path, row: dict[str, str] | None = None) -> dict[str, str]:
    metadata = infer_metadata_from_path(path)
    if row:
        for key, value in row.items():
            if value is not None and str(value).strip():
                metadata[key] = str(value).strip()
    metadata.setdefault("image_id", path.stem)
    metadata["image_id"] = metadata.get("image_id") or path.stem
    metadata["image_path"] = str(path)
    metadata["source_title"] = path.name
    return metadata


def discover_images(input_dir: Path) -> list[dict[str, Any]]:
    images = [
        path.resolve()
        for path in input_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    ]
    images.sort(key=lambda p: str(p).lower())
    return [{"image_path": path, "metadata": merge_metadata(path)} for path in images]


def load_manifest(manifest_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with manifest_path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            image_path = resolve_manifest_image(row, manifest_path)
            rows.append({"image_path": image_path, "metadata": merge_metadata(image_path, row)})
    rows.sort(key=lambda item: str(item["image_path"]).lower())
    return rows


def calibration_request_fields(metadata: dict[str, str], args: argparse.Namespace) -> dict[str, Any]:
    px_per_mm = parse_float(args.px_per_mm, 0.0)
    if px_per_mm <= 0:
        px_per_mm = parse_float(metadata.get("px_per_mm"), 0.0)
    if px_per_mm > 0:
        return {
            "calibration_status": "known",
            "calibration_source": args.calibration_source,
            "px_per_mm": px_per_mm,
        }

    pixel_width = parse_float(metadata.get("pixel_width"), 0.0)
    pixel_height = parse_float(metadata.get("pixel_height"), 0.0)
    unit = metadata.get("unit") or "pixel"
    if pixel_width > 0 and pixel_height > 0 and unit.lower() not in {"pixel", "pixels", "px"}:
        return {
            "calibration_status": "known",
            "calibration_source": metadata.get("calibration_source") or "manifest_pixel_size",
            "pixel_width": pixel_width,
            "pixel_height": pixel_height,
            "unit": unit,
        }

    return {
        "calibration_status": "missing",
        "calibration_source": "pixel_units_only",
        "pixel_width": 1.0,
        "pixel_height": 1.0,
        "unit": "pixel",
    }


def build_request(
    image_path: Path,
    run_dir: Path,
    metadata: dict[str, str],
    args: argparse.Namespace,
) -> dict[str, Any]:
    request = {
        "schema_version": REQUEST_SCHEMA,
        "source_title": image_path.name,
        "image_path": str(image_path),
        "model_package": str(Path(args.model_package).expanduser().resolve()),
        "inference_mode": "bubmask_mask_rcnn",
        "confidence_threshold": float(args.confidence_threshold),
        "preprocessing_profile": args.preprocessing_profile,
        "background_correction_mode": args.background_correction_mode,
        "quality_gate_mode": args.quality_gate_mode,
        "measure_sharp_bubbles_only": bool(args.measure_sharp_bubbles_only),
        "min_focus_score": float(args.min_focus_score),
        "min_diameter_px": float(args.min_diameter_px),
        "max_diameter_px": float(args.max_diameter_px),
        "run_output_dir": str(run_dir),
        "experiment_metadata": metadata,
    }
    request.update(calibration_request_fields(metadata, args))
    return request


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def completed_response(response_path: Path) -> bool:
    response = read_json(response_path)
    if not response or response.get("status") == "error":
        return False
    per_bubble = response.get("outputs", {}).get("per_bubble_csv")
    return bool(per_bubble and Path(per_bubble).is_file())


def append_progress(log_path: Path, message: str) -> None:
    line = f"{now_iso()} {message}"
    print(line, flush=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def run_worker(
    request_path: Path,
    response_path: Path,
    args: argparse.Namespace,
    log_path: Path,
) -> tuple[int, float]:
    worker_path = python_root() / "bubmask_worker.py"
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(python_root()) + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
    command = [
        str(Path(args.python_executable).expanduser()),
        str(worker_path),
        "--input",
        str(request_path),
        "--output",
        str(response_path),
    ]
    start = time.time()
    stdout_path = request_path.parent / "worker_stdout.log"
    stderr_path = request_path.parent / "worker_stderr.log"
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        try:
            process = subprocess.run(
                command,
                cwd=str(python_root()),
                env=env,
                stdout=stdout,
                stderr=stderr,
                timeout=float(args.timeout_sec) if float(args.timeout_sec) > 0 else None,
                check=False,
            )
            code = int(process.returncode)
        except subprocess.TimeoutExpired:
            append_progress(log_path, f"worker_timeout request={request_path}")
            code = 124
    return code, time.time() - start


def write_manifest(path: Path, records: list[dict[str, Any]]) -> None:
    fieldnames = [
        "index",
        "status",
        "image_id",
        "source_title",
        "image_path",
        "run_dir",
        "response_json",
        "per_bubble_csv",
        "elapsed_sec",
        "error",
        "condition",
        "pressure",
        "vent_geometry",
        "nominal_size",
        "flow_rate",
        "replicate_image",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({field: record.get(field, "") for field in fieldnames})


def csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_combined_measurements(path: Path, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        if record.get("status") not in {"worker_ok", "skipped_existing"}:
            continue
        per_bubble = record.get("per_bubble_csv")
        if not per_bubble:
            continue
        for row in csv_rows(Path(per_bubble)):
            combined = dict(row)
            for field in METADATA_FIELDS:
                combined[field] = record.get(field, "")
            rows.append(combined)

    base_fields = METADATA_FIELDS + [
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
        "accepted",
        "accepted_for_histogram",
        "measurement_status",
        "rejection_reason",
    ]
    extra_fields = sorted({key for row in rows for key in row.keys() if key not in base_fields})
    fieldnames = base_fields + extra_fields
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    return rows


def group_key(row: dict[str, Any], fields: list[str]) -> tuple[str, ...]:
    if not fields:
        return tuple()
    return tuple(str(row.get(field, "") or "unknown") for field in fields)


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    all_values, all_meta = measurement_values(rows, accepted_only=False)
    accepted_values, accepted_meta = measurement_values(rows, accepted_only=True)
    all_summary = distribution_summary(all_values)
    accepted_summary = distribution_summary(accepted_values)
    image_count = len({str(row.get("image_path", "")) for row in rows if row.get("image_path")})
    return {
        "image_count": image_count,
        "bubble_count_all": all_summary["count"],
        "bubble_count_accepted": accepted_summary["count"],
        "diameter_unit": accepted_meta.get("diameter_unit") or all_meta.get("diameter_unit") or "",
        "calibration_trusted": accepted_meta.get("calibration_trusted", False),
        "mean_diameter_all": all_summary["mean"],
        "median_diameter_all": all_summary["median"],
        "sauter_mean_diameter_all": all_summary["sauter_mean_diameter_d32"],
        "mean_diameter_accepted": accepted_summary["mean"],
        "median_diameter_accepted": accepted_summary["median"],
        "d10_accepted": accepted_summary["d10"],
        "d50_accepted": accepted_summary["d50"],
        "d90_accepted": accepted_summary["d90"],
        "sauter_mean_diameter_accepted": accepted_summary["sauter_mean_diameter_d32"],
    }


def write_experiment_summary(path: Path, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary_rows: list[dict[str, Any]] = []
    for level, fields in GROUP_LEVELS:
        grouped: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(group_key(row, fields), []).append(row)
        for key, group_rows in sorted(grouped.items(), key=lambda item: item[0]):
            output: dict[str, Any] = {
                "summary_level": level,
                "condition": "",
                "pressure": "",
                "vent_geometry": "",
                "nominal_size": "",
                "flow_rate": "",
                "replicate_image": "",
            }
            for field, value in zip(fields, key):
                output[field] = value
            output.update(summarize_rows(group_rows))
            summary_rows.append(output)

    fieldnames = [
        "summary_level",
        "condition",
        "pressure",
        "vent_geometry",
        "nominal_size",
        "flow_rate",
        "replicate_image",
        "image_count",
        "bubble_count_all",
        "bubble_count_accepted",
        "diameter_unit",
        "calibration_trusted",
        "mean_diameter_all",
        "median_diameter_all",
        "sauter_mean_diameter_all",
        "mean_diameter_accepted",
        "median_diameter_accepted",
        "d10_accepted",
        "d50_accepted",
        "d90_accepted",
        "sauter_mean_diameter_accepted",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in summary_rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    return summary_rows


def load_response_error(response_path: Path) -> str:
    response = read_json(response_path)
    error = response.get("error", {})
    return str(error.get("message", "")) if isinstance(error, dict) else ""


def process_images(items: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "batch_progress.log"
    records: list[dict[str, Any]] = []
    total = len(items)

    for index, item in enumerate(items, start=1):
        image_path: Path = item["image_path"]
        metadata: dict[str, str] = item["metadata"]
        run_dir = output_dir / f"{index:06d}_{safe_slug(image_path.stem)}"
        request_path = run_dir / "request.json"
        response_path = run_dir / "response.json"
        per_bubble_csv = ""
        status = "pending"
        elapsed = 0.0
        error = ""
        run_dir.mkdir(parents=True, exist_ok=True)

        request = build_request(image_path, run_dir, metadata, args)
        write_json(request_path, request)
        append_progress(log_path, f"image {index}/{total} start {image_path.name}")

        if args.dry_run:
            status = "dry_run"
        elif not args.force and not args.no_resume and completed_response(response_path):
            response = read_json(response_path)
            status = "skipped_existing"
            per_bubble_csv = response.get("outputs", {}).get("per_bubble_csv", "")
            append_progress(log_path, f"image {index}/{total} resume_skip {image_path.name}")
        else:
            code, elapsed = run_worker(request_path, response_path, args, log_path)
            response = read_json(response_path)
            per_bubble_csv = response.get("outputs", {}).get("per_bubble_csv", "")
            if code == 0 and response.get("status") != "error" and per_bubble_csv:
                status = "worker_ok"
            else:
                status = "worker_error"
                error = load_response_error(response_path) or f"worker_exit_code={code}"
            append_progress(log_path, f"image {index}/{total} {status} elapsed_sec={elapsed:.1f} {image_path.name}")

        record = {
            "index": index,
            "status": status,
            "image_id": metadata.get("image_id", image_path.stem),
            "source_title": image_path.name,
            "image_path": str(image_path),
            "run_dir": str(run_dir),
            "response_json": str(response_path),
            "per_bubble_csv": per_bubble_csv,
            "elapsed_sec": f"{elapsed:.3f}" if elapsed else "",
            "error": error,
            "condition": metadata.get("condition", ""),
            "pressure": metadata.get("pressure", ""),
            "vent_geometry": metadata.get("vent_geometry", ""),
            "nominal_size": metadata.get("nominal_size", ""),
            "flow_rate": metadata.get("flow_rate", ""),
            "replicate_image": metadata.get("replicate_image", ""),
        }
        records.append(record)
        write_manifest(output_dir / "batch_manifest.csv", records)
    return records


def finalize_batch(records: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    output_dir = Path(args.output_dir).expanduser().resolve()
    combined_csv = output_dir / "combined_per_bubble_measurements.csv"
    experiment_summary_csv = output_dir / "experiment_summary.csv"
    combined_rows = write_combined_measurements(combined_csv, records)
    experiment_summary_rows = write_experiment_summary(experiment_summary_csv, combined_rows)
    histogram_outputs = export_histogram_artifacts(
        combined_rows,
        output_dir,
        prefix="combined_diameter",
        image_id="batch_combined",
    )
    summary = {
        "schema_version": BATCH_SCHEMA,
        "created": now_iso(),
        "model_package": str(Path(args.model_package).expanduser().resolve()),
        "input_count": len(records),
        "worker_ok": sum(1 for record in records if record.get("status") == "worker_ok"),
        "skipped_existing": sum(1 for record in records if record.get("status") == "skipped_existing"),
        "worker_error": sum(1 for record in records if record.get("status") == "worker_error"),
        "combined_measurement_count": len(combined_rows),
        "experiment_summary_rows": len(experiment_summary_rows),
        "overlap_reconstruction": "skipped",
        "outputs": {
            "batch_manifest_csv": str(output_dir / "batch_manifest.csv"),
            "combined_per_bubble_measurements_csv": str(combined_csv),
            "experiment_summary_csv": str(experiment_summary_csv),
            **histogram_outputs,
        },
    }
    write_json(output_dir / "batch_summary.json", summary)
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run BubMask-Fiji over a folder or manifest of TIFF images.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input-dir", help="Folder of TIFF images to process recursively.")
    source.add_argument("--manifest", help="CSV manifest with image_path, path, or relative_path.")
    parser.add_argument("--output-dir", required=True, help="Batch output folder.")
    parser.add_argument("--model-package", default=str(default_model_package()), help="Model package directory.")
    parser.add_argument("--python-executable", default=sys.executable, help="Python executable for worker subprocesses.")
    parser.add_argument("--limit", type=int, default=0, help="Optional maximum number of images.")
    parser.add_argument("--confidence-threshold", type=float, default=0.10)
    parser.add_argument("--preprocessing-profile", default="raw_model")
    parser.add_argument("--background-correction-mode", default="none")
    parser.add_argument("--quality-gate-mode", default="review_only")
    parser.add_argument("--measure-sharp-bubbles-only", action="store_true")
    parser.add_argument("--min-focus-score", type=float, default=10.0)
    parser.add_argument("--min-diameter-px", type=float, default=0.0)
    parser.add_argument("--max-diameter-px", type=float, default=0.0)
    parser.add_argument("--px-per-mm", type=float, default=0.0, help="Optional calibration override.")
    parser.add_argument("--calibration-source", default="manual_px_per_mm")
    parser.add_argument("--timeout-sec", type=float, default=0.0, help="Optional per-image worker timeout.")
    parser.add_argument("--force", action="store_true", help="Re-run images even if response.json already exists.")
    parser.add_argument("--no-resume", action="store_true", help="Disable resume skip checks.")
    parser.add_argument("--dry-run", action="store_true", help="Write requests and manifests without running workers.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.input_dir:
        items = discover_images(Path(args.input_dir).expanduser().resolve())
    else:
        items = load_manifest(Path(args.manifest).expanduser().resolve())
    if args.limit and args.limit > 0:
        items = items[: args.limit]
    if not items:
        print("No TIFF images found for batch processing.", file=sys.stderr)
        return 2

    Path(args.output_dir).expanduser().resolve().mkdir(parents=True, exist_ok=True)
    records = process_images(items, args)
    summary = finalize_batch(records, args)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["worker_error"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
