"""Diameter histogram and distribution summaries for BubMask-Fiji."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path
from typing import Any, Iterable

import numpy as np


HISTOGRAM_SCHEMA = "bubmask.histogram.v1"
RECONSTRUCTION_MODE_SKIPPED = "skipped_raw_equals_reconstructed"


def parse_bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_float(value: Any, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if math.isfinite(out):
        return out
    return default


def is_pixel_unit(unit: Any) -> bool:
    return str(unit or "").strip().lower() in {"", "pixel", "pixels", "px"}


def diameter_value(row: dict[str, Any]) -> dict[str, Any] | None:
    """Return the diameter value BubMask should histogram for one measurement."""
    trusted = parse_bool(row.get("physical_measurement_trusted"), False)
    unit = str(row.get("diameter_unit") or "pixel")
    calibrated = parse_float(row.get("equivalent_diameter_calibrated"))
    if trusted and calibrated is not None and calibrated > 0 and not is_pixel_unit(unit):
        return {
            "value": calibrated,
            "unit": unit,
            "calibration_trusted": True,
            "source": "equivalent_diameter_calibrated",
        }

    pixel = parse_float(row.get("equivalent_diameter_px"))
    if pixel is None or pixel <= 0:
        return None
    return {
        "value": pixel,
        "unit": "px",
        "calibration_trusted": False,
        "source": "equivalent_diameter_px",
    }


def measurement_values(
    rows: Iterable[dict[str, Any]],
    *,
    accepted_only: bool = False,
) -> tuple[list[float], dict[str, Any]]:
    values: list[float] = []
    units: set[str] = set()
    sources: set[str] = set()
    trusted_flags: set[bool] = set()
    considered = 0

    for row in rows:
        considered += 1
        if accepted_only and not parse_bool(row.get("accepted_for_histogram", row.get("accepted")), False):
            continue
        record = diameter_value(row)
        if record is None:
            continue
        values.append(float(record["value"]))
        units.add(str(record["unit"]))
        sources.add(str(record["source"]))
        trusted_flags.add(bool(record["calibration_trusted"]))

    unit = next(iter(units)) if len(units) == 1 else ("mixed" if units else "")
    source = next(iter(sources)) if len(sources) == 1 else ("mixed" if sources else "")
    return values, {
        "rows_considered": considered,
        "rows_used": len(values),
        "diameter_unit": unit,
        "diameter_source": source,
        "calibration_trusted": len(trusted_flags) == 1 and True in trusted_flags,
        "mixed_units": len(units) > 1,
    }


def percentile(sorted_values: list[float], q: float) -> float | None:
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    q = max(0.0, min(100.0, q))
    position = (len(sorted_values) - 1) * (q / 100.0)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def sauter_mean_diameter(values: list[float]) -> float | None:
    if not values:
        return None
    denominator = sum(v * v for v in values if v > 0)
    if denominator <= 0:
        return None
    numerator = sum(v * v * v for v in values if v > 0)
    return numerator / denominator


def distribution_summary(values: list[float]) -> dict[str, Any]:
    values = [float(v) for v in values if math.isfinite(float(v)) and float(v) > 0]
    if not values:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "standard_deviation": None,
            "minimum": None,
            "maximum": None,
            "d10": None,
            "d50": None,
            "d90": None,
            "sauter_mean_diameter_d32": None,
        }
    sorted_values = sorted(values)
    return {
        "count": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(sorted_values),
        "standard_deviation": statistics.pstdev(values) if len(values) > 1 else 0.0,
        "minimum": sorted_values[0],
        "maximum": sorted_values[-1],
        "d10": percentile(sorted_values, 10),
        "d50": percentile(sorted_values, 50),
        "d90": percentile(sorted_values, 90),
        "sauter_mean_diameter_d32": sauter_mean_diameter(values),
    }


def histogram_rows(values: list[float], bins: int = 30) -> list[dict[str, Any]]:
    values = [float(v) for v in values if math.isfinite(float(v)) and float(v) > 0]
    if not values:
        return []

    bins = max(1, int(bins))
    low = min(values)
    high = max(values)
    if math.isclose(low, high):
        pad = max(low * 0.05, 0.5)
        low = max(0.0, low - pad)
        high = high + pad
        bins = 1

    counts, edges = np.histogram(np.asarray(values, dtype=np.float64), bins=bins, range=(low, high))
    total = int(counts.sum())
    rows: list[dict[str, Any]] = []
    for idx, count in enumerate(counts):
        start = float(edges[idx])
        end = float(edges[idx + 1])
        rows.append({
            "bin_index": idx + 1,
            "bin_start": start,
            "bin_end": end,
            "bin_midpoint": (start + end) / 2.0,
            "count": int(count),
            "fraction": (int(count) / total) if total else 0.0,
        })
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def load_measurements_csv(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).expanduser().resolve().open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_histogram_csv(
    path: Path,
    rows: list[dict[str, Any]],
    *,
    diameter_unit: str,
    scope: str,
) -> None:
    output_rows = []
    for row in rows:
        output_rows.append({
            **row,
            "diameter_unit": diameter_unit,
            "scope": scope,
        })
    write_csv(
        path,
        output_rows,
        ["scope", "diameter_unit", "bin_index", "bin_start", "bin_end", "bin_midpoint", "count", "fraction"],
    )


def write_raw_vs_reconstructed_csv(
    path: Path,
    raw_rows: list[dict[str, Any]],
    reconstructed_rows: list[dict[str, Any]],
    *,
    diameter_unit: str,
    reconstruction_mode: str,
) -> None:
    rows: list[dict[str, Any]] = []
    count = max(len(raw_rows), len(reconstructed_rows))
    for idx in range(count):
        raw = raw_rows[idx] if idx < len(raw_rows) else {}
        rec = reconstructed_rows[idx] if idx < len(reconstructed_rows) else {}
        start = raw.get("bin_start", rec.get("bin_start", ""))
        end = raw.get("bin_end", rec.get("bin_end", ""))
        midpoint = raw.get("bin_midpoint", rec.get("bin_midpoint", ""))
        rows.append({
            "diameter_unit": diameter_unit,
            "reconstruction_mode": reconstruction_mode,
            "bin_index": idx + 1,
            "bin_start": start,
            "bin_end": end,
            "bin_midpoint": midpoint,
            "raw_count": raw.get("count", 0),
            "reconstructed_count": rec.get("count", 0),
            "raw_fraction": raw.get("fraction", 0.0),
            "reconstructed_fraction": rec.get("fraction", 0.0),
        })
    write_csv(
        path,
        rows,
        [
            "diameter_unit",
            "reconstruction_mode",
            "bin_index",
            "bin_start",
            "bin_end",
            "bin_midpoint",
            "raw_count",
            "reconstructed_count",
            "raw_fraction",
            "reconstructed_fraction",
        ],
    )


def _plot_histogram_png(
    path: Path,
    rows: list[dict[str, Any]],
    *,
    title: str,
    diameter_unit: str,
) -> bool:
    if not rows:
        return False
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False

    starts = [float(row["bin_start"]) for row in rows]
    ends = [float(row["bin_end"]) for row in rows]
    counts = [int(row["count"]) for row in rows]
    widths = [end - start for start, end in zip(starts, ends)]
    fig, ax = plt.subplots(figsize=(7.0, 4.2), dpi=160)
    ax.bar(starts, counts, width=widths, align="edge", color="#2f80ed", edgecolor="#1b3a57", linewidth=0.8)
    ax.set_title(title)
    ax.set_xlabel(f"Equivalent diameter ({diameter_unit})")
    ax.set_ylabel("Bubble count")
    ax.grid(axis="y", color="#d8d8d8", linewidth=0.6)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    return path.is_file()


def _plot_raw_vs_reconstructed_png(
    path: Path,
    raw_rows: list[dict[str, Any]],
    reconstructed_rows: list[dict[str, Any]],
    *,
    diameter_unit: str,
    reconstruction_mode: str,
) -> bool:
    if not raw_rows and not reconstructed_rows:
        return False
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False

    rows = raw_rows if raw_rows else reconstructed_rows
    starts = [float(row["bin_start"]) for row in rows]
    ends = [float(row["bin_end"]) for row in rows]
    widths = [end - start for start, end in zip(starts, ends)]
    raw_counts = [int(row.get("count", 0)) for row in raw_rows]
    rec_counts = [int(row.get("count", 0)) for row in reconstructed_rows]

    fig, ax = plt.subplots(figsize=(7.0, 4.2), dpi=160)
    ax.bar(starts, raw_counts, width=widths, align="edge", color="#2f80ed", alpha=0.45, label="Raw masks")
    ax.step(
        starts + [ends[-1]],
        rec_counts + ([rec_counts[-1]] if rec_counts else [0]),
        where="post",
        color="#d12f2f",
        linewidth=1.6,
        label="Reconstructed",
    )
    subtitle = "overlap reconstruction skipped" if reconstruction_mode == RECONSTRUCTION_MODE_SKIPPED else reconstruction_mode
    ax.set_title(f"Raw vs reconstructed diameters ({subtitle})")
    ax.set_xlabel(f"Equivalent diameter ({diameter_unit})")
    ax.set_ylabel("Bubble count")
    ax.grid(axis="y", color="#d8d8d8", linewidth=0.6)
    ax.legend()
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    return path.is_file()


def export_histogram_artifacts(
    measurements: Iterable[dict[str, Any]],
    output_dir: str | Path,
    *,
    prefix: str = "diameter",
    bins: int = 30,
    image_id: str = "",
    reconstruction_mode: str = RECONSTRUCTION_MODE_SKIPPED,
) -> dict[str, str]:
    """Write per-run histogram CSV/PNG/JSON artifacts and return output paths."""
    outdir = Path(output_dir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    rows = list(measurements)

    all_values, all_meta = measurement_values(rows, accepted_only=False)
    accepted_values, accepted_meta = measurement_values(rows, accepted_only=True)
    diameter_unit = str(accepted_meta.get("diameter_unit") or all_meta.get("diameter_unit") or "px")
    if diameter_unit == "mixed":
        diameter_unit = str(all_meta.get("diameter_unit") or "mixed")

    all_hist = histogram_rows(all_values, bins=bins)
    accepted_hist = histogram_rows(accepted_values, bins=bins)
    reconstructed_values = list(all_values)
    reconstructed_hist = histogram_rows(reconstructed_values, bins=bins)

    all_csv = outdir / f"{prefix}_histogram_all.csv"
    accepted_csv = outdir / f"{prefix}_histogram_accepted.csv"
    raw_vs_reconstructed_csv = outdir / f"{prefix}_histogram_raw_vs_reconstructed.csv"
    all_png = outdir / f"{prefix}_histogram_all.png"
    accepted_png = outdir / f"{prefix}_histogram_accepted.png"
    raw_vs_reconstructed_png = outdir / f"{prefix}_histogram_raw_vs_reconstructed.png"
    summary_json = outdir / f"{prefix}_histogram_summary.json"

    write_histogram_csv(all_csv, all_hist, diameter_unit=diameter_unit, scope="all")
    write_histogram_csv(accepted_csv, accepted_hist, diameter_unit=diameter_unit, scope="accepted_for_histogram")
    write_raw_vs_reconstructed_csv(
        raw_vs_reconstructed_csv,
        all_hist,
        reconstructed_hist,
        diameter_unit=diameter_unit,
        reconstruction_mode=reconstruction_mode,
    )

    output_paths: dict[str, str] = {
        f"{prefix}_histogram_all_csv": str(all_csv),
        f"{prefix}_histogram_accepted_csv": str(accepted_csv),
        f"{prefix}_histogram_raw_vs_reconstructed_csv": str(raw_vs_reconstructed_csv),
        f"{prefix}_histogram_summary_json": str(summary_json),
    }
    if _plot_histogram_png(all_png, all_hist, title="Bubble equivalent diameter histogram", diameter_unit=diameter_unit):
        output_paths[f"{prefix}_histogram_all_png"] = str(all_png)
    if _plot_histogram_png(
        accepted_png,
        accepted_hist,
        title="Accepted bubble equivalent diameter histogram",
        diameter_unit=diameter_unit,
    ):
        output_paths[f"{prefix}_histogram_accepted_png"] = str(accepted_png)
    if _plot_raw_vs_reconstructed_png(
        raw_vs_reconstructed_png,
        all_hist,
        reconstructed_hist,
        diameter_unit=diameter_unit,
        reconstruction_mode=reconstruction_mode,
    ):
        output_paths[f"{prefix}_histogram_raw_vs_reconstructed_png"] = str(raw_vs_reconstructed_png)

    summary = {
        "schema_version": HISTOGRAM_SCHEMA,
        "image_id": image_id,
        "diameter_unit": diameter_unit,
        "all": {
            **all_meta,
            **distribution_summary(all_values),
        },
        "accepted_for_histogram": {
            **accepted_meta,
            **distribution_summary(accepted_values),
        },
        "raw_vs_reconstructed": {
            "reconstruction_mode": reconstruction_mode,
            "note": (
                "Overlapping bubble reconstruction was explicitly skipped for this phase; "
                "reconstructed diameters are identical to raw mask equivalent diameters."
            ),
            "raw": distribution_summary(all_values),
            "reconstructed": distribution_summary(reconstructed_values),
        },
        "outputs": output_paths,
    }
    summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export BubMask diameter histogram artifacts from a measurement CSV.")
    parser.add_argument("--measurements-csv", required=True, help="Input per-bubble measurement CSV.")
    parser.add_argument("--output-dir", required=True, help="Output directory for histogram artifacts.")
    parser.add_argument("--prefix", default="diameter", help="Output filename prefix.")
    parser.add_argument("--bins", type=int, default=30, help="Number of histogram bins.")
    parser.add_argument("--image-id", default="", help="Image or run identifier recorded in summary JSON.")
    args = parser.parse_args(argv)

    rows = load_measurements_csv(args.measurements_csv)
    outputs = export_histogram_artifacts(
        rows,
        args.output_dir,
        prefix=args.prefix,
        bins=args.bins,
        image_id=args.image_id,
    )
    print(json.dumps(outputs, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
