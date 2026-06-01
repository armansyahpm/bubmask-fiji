from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def truthy(value: object) -> bool:
    return str(value).strip().lower() not in {"", "0", "false", "no", "none"}


def read_diameters(path: Path) -> tuple[list[float], str]:
    values: list[float] = []
    unit = "pixel"
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            accepted = row.get("accepted_for_histogram", row.get("accepted", "True"))
            if not truthy(accepted):
                continue
            unit = row.get("diameter_unit") or row.get("unit") or unit
            text = (
                row.get("diameter")
                or row.get("equivalent_diameter_calibrated")
                or row.get("equivalent_diameter_px")
                or ""
            )
            try:
                value = float(text)
            except Exception:
                continue
            if math.isfinite(value) and value > 0:
                values.append(value)
    return values, unit


def percentile(values: np.ndarray, q: float) -> float:
    if values.size == 0:
        return float("nan")
    return float(np.percentile(values, q))


def moment_diameter(values: np.ndarray, p: int, q: int) -> float:
    if values.size == 0:
        return float("nan")
    numerator = float(np.sum(values ** p))
    denominator = float(np.sum(values ** q))
    if denominator <= 0:
        return float("nan")
    if p == q:
        return float("nan")
    return (numerator / denominator) ** (1.0 / float(p - q))


def stats(values: np.ndarray) -> dict[str, float]:
    if values.size == 0:
        return {
            "count": 0,
            "mean": float("nan"),
            "median_d50": float("nan"),
            "d10": float("nan"),
            "d90": float("nan"),
            "d32_sauter": float("nan"),
            "d43_volume_mean": float("nan"),
            "min": float("nan"),
            "max": float("nan"),
        }
    return {
        "count": float(values.size),
        "mean": float(np.mean(values)),
        "median_d50": percentile(values, 50),
        "d10": percentile(values, 10),
        "d90": percentile(values, 90),
        "d32_sauter": moment_diameter(values, 3, 2),
        "d43_volume_mean": moment_diameter(values, 4, 3),
        "min": float(np.min(values)),
        "max": float(np.max(values)),
    }


def write_stats(path: Path, data: dict[str, float], unit: str) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value", "unit"])
        for key, value in data.items():
            writer.writerow([key, value, "" if key == "count" else unit])


def write_histogram(path: Path, values: np.ndarray, bins: int, plot_range: tuple[float, float] | None) -> None:
    counts, edges = np.histogram(values, bins=bins, range=plot_range)
    total = float(np.sum(counts))
    density, _ = np.histogram(values, bins=bins, range=plot_range, density=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["bin_index", "bin_start", "bin_end", "bin_midpoint", "count", "fraction", "pdf_density"])
        for idx, count in enumerate(counts, start=1):
            start = float(edges[idx - 1])
            end = float(edges[idx])
            midpoint = (start + end) / 2.0
            writer.writerow([
                idx,
                start,
                end,
                midpoint,
                int(count),
                float(count) / total if total else 0.0,
                float(density[idx - 1]) if np.isfinite(density[idx - 1]) else 0.0,
            ])


def plot(
    path: Path,
    values: np.ndarray,
    unit: str,
    bins: int,
    plot_range: tuple[float, float] | None,
    hist_by: str,
    show_pdf: bool,
    show_cdf: bool,
    show_d32: bool,
    show_mean: bool,
    show_d23: bool,
) -> None:
    fig, ax = plt.subplots(figsize=(12, 7), dpi=120)
    weights = None
    ylabel = "Bubble count"
    if hist_by == "fraction":
        weights = np.ones_like(values) / float(values.size)
        ylabel = "Fraction"
    elif hist_by == "density":
        ylabel = "Probability density"

    density = hist_by == "density"
    counts, edges, _ = ax.hist(
        values,
        bins=bins,
        range=plot_range,
        density=density,
        weights=weights,
        color="#2f80ed",
        edgecolor="#1f4e79",
        alpha=0.9,
        label=hist_by,
    )
    mids = (edges[:-1] + edges[1:]) / 2.0
    if show_pdf:
        pdf_counts, pdf_edges = np.histogram(values, bins=bins, range=plot_range, density=True)
        pdf_mids = (pdf_edges[:-1] + pdf_edges[1:]) / 2.0
        ax.plot(pdf_mids, pdf_counts, color="#c0392b", linewidth=2, label="PDF")
    if show_cdf:
        ax2 = ax.twinx()
        xs = np.sort(values)
        ys = np.arange(1, values.size + 1) / float(values.size)
        ax2.plot(xs, ys, color="#27ae60", linewidth=2, label="CDF")
        ax2.set_ylabel("Cumulative probability")
        ax2.set_ylim(0, 1.03)

    summary = stats(values)
    ymax = float(np.nanmax(counts)) if len(counts) else 1.0
    if show_mean and math.isfinite(summary["mean"]):
        ax.axvline(summary["mean"], color="#8e44ad", linestyle="--", linewidth=2, label="mean")
    if show_d32 and math.isfinite(summary["d32_sauter"]):
        ax.axvline(summary["d32_sauter"], color="#e67e22", linestyle="-.", linewidth=2, label="D32")
    if show_d23 and math.isfinite(summary["d32_sauter"]):
        ax.axvline(summary["d32_sauter"], color="#34495e", linestyle=":", linewidth=2, label="D23/D32")

    ax.set_title("Bubble equivalent diameter distribution")
    ax.set_xlabel(f"Equivalent diameter ({unit})")
    ax.set_ylabel(ylabel)
    ax.grid(True, axis="y", alpha=0.35)
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description="Interactive BubMask histogram/statistics export.")
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--prefix", default="histogram_analysis")
    parser.add_argument("--bins", type=int, default=15)
    parser.add_argument("--xmin", type=float, default=0.0)
    parser.add_argument("--xmax", type=float, default=0.0)
    parser.add_argument("--hist-by", choices=["count", "fraction", "density"], default="count")
    parser.add_argument("--show-pdf", action="store_true")
    parser.add_argument("--show-cdf", action="store_true")
    parser.add_argument("--show-d32", action="store_true")
    parser.add_argument("--show-mean", action="store_true")
    parser.add_argument("--show-d23", action="store_true")
    args = parser.parse_args()

    input_csv = Path(args.input_csv)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    values, unit = read_diameters(input_csv)
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        raise SystemExit("No valid histogram diameters found.")

    plot_range = None
    if args.xmax > args.xmin:
        plot_range = (args.xmin, args.xmax)
        arr = arr[(arr >= args.xmin) & (arr <= args.xmax)]
    if arr.size == 0:
        raise SystemExit("No diameters remain inside the selected x-axis limits.")

    bins = max(1, int(args.bins))
    graph_path = output_dir / f"{args.prefix}.png"
    hist_path = output_dir / f"{args.prefix}.csv"
    stats_path = output_dir / f"{args.prefix}_statistics.csv"
    json_path = output_dir / f"{args.prefix}_summary.json"

    plot(
        graph_path,
        arr,
        unit,
        bins,
        plot_range,
        args.hist_by,
        args.show_pdf,
        args.show_cdf,
        args.show_d32,
        args.show_mean,
        args.show_d23,
    )
    write_histogram(hist_path, arr, bins, plot_range)
    summary = stats(arr)
    write_stats(stats_path, summary, unit)
    json_path.write_text(json.dumps({"unit": unit, "statistics": summary}, indent=2), encoding="utf-8")
    print(graph_path)
    print(hist_path)
    print(stats_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
