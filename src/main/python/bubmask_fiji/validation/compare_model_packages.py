"""Compare two or more BubMask model packages on the same TIFF images.

This is intentionally a thin orchestration layer around ``bubmask_worker.py``.
It writes one request/response folder per image/model pair, then accumulates a
CSV and Markdown summary so Fiji-facing model changes can be reviewed without
mixing them into the main plugin workflow.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def parse_model(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("Model must be provided as name=path")
    name, path = value.split("=", 1)
    name = name.strip()
    if not name:
        raise argparse.ArgumentTypeError("Model name cannot be empty")
    return name, Path(path).expanduser().resolve()


def safe_slug(value: str) -> str:
    allowed = []
    for char in value:
        if char.isalnum() or char in {"-", "_"}:
            allowed.append(char)
        else:
            allowed.append("_")
    return "".join(allowed).strip("_") or "item"


def write_request(
    request_path: Path,
    image_path: Path,
    model_package: Path,
    run_output_dir: Path,
    args: argparse.Namespace,
) -> dict[str, Any]:
    calibration_known = args.px_per_mm > 0
    request: dict[str, Any] = {
        "schema_version": "bubmask.request.v1",
        "source_title": image_path.name,
        "image_path": str(image_path),
        "model_package": str(model_package),
        "inference_mode": "bubmask_mask_rcnn",
        "confidence_threshold": args.confidence_threshold,
        "preprocessing_profile": args.preprocessing_profile,
        "background_correction_mode": args.background_correction_mode,
        "quality_gate_mode": args.quality_gate_mode,
        "measure_sharp_bubbles_only": args.measure_sharp_bubbles_only,
        "min_focus_score": args.min_focus_score,
        "min_diameter_px": args.min_diameter_px,
        "max_diameter_px": args.max_diameter_px,
        "calibration_status": "known" if calibration_known else "missing",
        "calibration_source": "comparison_px_per_mm" if calibration_known else "missing",
        "px_per_mm": args.px_per_mm,
        "run_output_dir": str(run_output_dir),
    }
    request_path.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return request


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def summarize_response(
    image_path: Path,
    model_name: str,
    model_package: Path,
    response_path: Path,
    request_path: Path,
    return_code: int,
    elapsed_sec: float,
) -> dict[str, Any]:
    response = load_json(response_path)
    diagnostics = response.get("diagnostics", {}) if isinstance(response, dict) else {}
    quality = diagnostics.get("quality_summary", {}) if isinstance(diagnostics, dict) else {}
    outputs = response.get("outputs", {}) if isinstance(response, dict) else {}
    error = response.get("error", {}) if isinstance(response, dict) else {}
    return {
        "image": image_path.name,
        "image_path": str(image_path),
        "model_name": model_name,
        "model_package": str(model_package),
        "return_code": return_code,
        "worker_status": response.get("status", "worker_ok" if return_code == 0 else "worker_failed"),
        "error_type": error.get("type", ""),
        "error_message": error.get("message", ""),
        "elapsed_sec": f"{elapsed_sec:.2f}",
        "detections": diagnostics.get("detection_count", ""),
        "accepted_bubble": quality.get("accepted_bubble", ""),
        "review_bubble": quality.get("review_bubble", ""),
        "rejected_nonbubble": quality.get("rejected_nonbubble", ""),
        "accepted_for_histogram": quality.get("accepted_for_histogram", ""),
        "calibration_status": diagnostics.get("calibration", {}).get("status", ""),
        "px_per_mm": diagnostics.get("calibration", {}).get("px_per_mm", ""),
        "overlay_masks": outputs.get("overlay_masks_png", ""),
        "overlay_boxes": outputs.get("overlay_boxes_png", ""),
        "per_bubble_csv": outputs.get("per_bubble_csv", ""),
        "request_json": str(request_path),
        "response_json": str(response_path),
    }


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(rows: list[dict[str, Any]], path: Path, args: argparse.Namespace) -> None:
    lines = [
        "# BubMask Model Package Comparison",
        "",
        "This report compares model packages on identical TIFF inputs using the same worker request settings.",
        "",
        "## Settings",
        "",
        f"- Confidence threshold: `{args.confidence_threshold}`",
        f"- Preprocessing profile: `{args.preprocessing_profile}`",
        f"- Background correction mode: `{args.background_correction_mode}`",
        f"- Quality gate: `{args.quality_gate_mode}`",
        f"- Manual calibration: `{args.px_per_mm}` px/mm",
        "",
        "## Summary",
        "",
        "| Image | Model | Status | Detections | Accepted | Review | Rejected | Histogram | Overlay |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        overlay = row.get("overlay_masks", "")
        overlay_text = Path(overlay).name if overlay else ""
        lines.append(
            "| {image} | {model_name} | {worker_status} | {detections} | "
            "{accepted_bubble} | {review_bubble} | {rejected_nonbubble} | "
            "{accepted_for_histogram} | {overlay} |".format(
                **row,
                overlay=overlay_text,
            )
        )
    lines.extend([
        "",
        "## Notes",
        "",
        "- This comparison is a functional and visual sanity check, not a final accuracy claim.",
        "- Use the raw Round 2 split for honest validation/testing; do not evaluate accuracy on images used for training.",
        "- Review the generated overlay PNG/TIFF files side by side before choosing a default model package.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare BubMask model packages on matched TIFF inputs.")
    parser.add_argument("--image", action="append", required=True, help="TIFF image path. Repeat for multiple images.")
    parser.add_argument("--model", action="append", type=parse_model, required=True, help="Model as name=path.")
    parser.add_argument("--output-dir", required=True, help="Directory for comparison artifacts.")
    parser.add_argument("--confidence-threshold", type=float, default=0.5)
    parser.add_argument("--preprocessing-profile", default="raw_model")
    parser.add_argument("--background-correction-mode", default="none")
    parser.add_argument("--quality-gate-mode", default="review_only")
    parser.add_argument("--measure-sharp-bubbles-only", action="store_true")
    parser.add_argument("--min-focus-score", type=float, default=10.0)
    parser.add_argument("--min-diameter-px", type=float, default=0.0)
    parser.add_argument("--max-diameter-px", type=float, default=0.0)
    parser.add_argument("--px-per-mm", type=float, default=183.0)
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    python_root = Path(__file__).resolve().parents[2]
    worker_path = python_root / "bubmask_worker.py"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(python_root) + os.pathsep + env.get("PYTHONPATH", "")

    rows: list[dict[str, Any]] = []
    for image_value in args.image:
        image_path = Path(image_value).expanduser().resolve()
        image_dir = output_dir / safe_slug(image_path.stem)
        image_dir.mkdir(parents=True, exist_ok=True)
        for model_name, model_package in args.model:
            run_dir = image_dir / safe_slug(model_name)
            run_dir.mkdir(parents=True, exist_ok=True)
            request_path = run_dir / "request.json"
            response_path = run_dir / "response.json"
            write_request(request_path, image_path, model_package, run_dir, args)

            command = [
                sys.executable,
                str(worker_path),
                "--input",
                str(request_path),
                "--output",
                str(response_path),
            ]
            start = time.perf_counter()
            completed = subprocess.run(command, cwd=str(python_root), env=env, check=False)
            elapsed = time.perf_counter() - start
            rows.append(
                summarize_response(
                    image_path,
                    model_name,
                    model_package,
                    response_path,
                    request_path,
                    completed.returncode,
                    elapsed,
                )
            )

    write_csv(rows, output_dir / "model_comparison_summary.csv")
    write_markdown(rows, output_dir / "model_comparison_summary.md", args)
    print(f"Wrote {output_dir / 'model_comparison_summary.csv'}")
    print(f"Wrote {output_dir / 'model_comparison_summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
