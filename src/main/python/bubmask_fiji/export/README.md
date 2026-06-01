# Export Layer

Responsible for writing ResultsTable-compatible data, CSV, JSON audit files,
mask images, overlays, histograms, and run folders.

Current implemented helper:

```text
artifacts.py
```

For a worker response and source image it can write:

- `per_bubble_measurements.csv`;
- `overlay_boxes.png`;
- `overlay_boxes.tif`;
- `overlay_masks.png`;
- `overlay_masks.tif`;
- `instance_labels.tif`;
- `diameter_histogram_all.csv` / `.png`;
- `diameter_histogram_accepted.csv` / `.png`;
- `diameter_histogram_raw_vs_reconstructed.csv` / `.png`;
- `diameter_histogram_summary.json`;
- `summary_response.json`.

The box overlay is for location/debugging. The mask overlay and label image are
for scientific review and validation: they show which pixels were counted for
each bubble.

For the Phase 8 histogram implementation, overlapping-bubble reconstruction is
not applied. The raw-vs-reconstructed files are emitted as an explicit identity
comparison so downstream batch reports have a stable schema while the
reconstruction step remains skipped.
