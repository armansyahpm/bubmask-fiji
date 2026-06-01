# Histogram Layer

Responsible for generating bubble-size distributions from BubMask measurement
tables.

Implemented helper:

```text
histograms.py
```

Per worker run it writes:

- `diameter_histogram_all.csv` / `.png`;
- `diameter_histogram_accepted.csv` / `.png`;
- `diameter_histogram_raw_vs_reconstructed.csv` / `.png`;
- `diameter_histogram_summary.json`.

The histogram value is `equivalent_diameter_calibrated` only when the worker has
trusted physical calibration. Otherwise the histogram is explicitly reported in
pixel units from `equivalent_diameter_px`.

For Phase 8, overlapping-bubble reconstruction is intentionally skipped. The
raw-vs-reconstructed artifact is still written for workflow compatibility, but
the summary JSON records `skipped_raw_equals_reconstructed` and the
reconstructed distribution is identical to the raw mask distribution.
