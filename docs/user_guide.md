# BubMask-Fiji User Guide

Version: research prototype, 2026-06-02

BubMask-Fiji is a Fiji/ImageJ workflow for measuring microbubble size
distributions from microscope images. It combines Mask R-CNN bubble
segmentation with Fiji overlays, manual ROI correction, calibrated diameter
measurement, histogram analysis, and exportable result files.

This guide is written for mineral-engineering users who want to run the tool,
inspect the masks, correct missed bubbles, and export traceable outputs.

---

## 1. Before You Start

### Required Software

- Fiji/ImageJ.
- The BubMask Fiji script installed under `Plugins > UNSW > BubMask`.
- A local BubMask Python environment with the required Mask R-CNN dependencies.
- BubMask model package files stored under the local `models/` directory.

The currently tested local Fiji script is:

```text
src/main/fiji/BubMask.py
```

The live installed script should be copied to:

```text
Fiji/scripts/Plugins/UNSW/BubMask.py
```

### Input Images

Use microscope images in TIFF or another Fiji-readable image format. For
scientific reporting, record the experimental context for each image:

- flow rate;
- pressure;
- vent geometry;
- replicate number;
- calibration in pixels per millimetre;
- sample notes such as particles, blur, uneven illumination, or strong
  highlights.

### Calibration

BubMask-Fiji uses `183 px/mm` as the default calibration when no user value is
entered. Confirm this before using millimetre-scale measurements. If your image
has a different microscope calibration, enter the correct value in the settings
window.

---

## 2. Starting BubMask

1. Open Fiji.
2. Open the image to analyse.
3. Go to `Plugins > UNSW > BubMask`.
4. Choose the model package and measurement settings.
5. Press `NEXT` or `OK` to start processing.

The tool writes a temporary run folder while processing. Final output files are
only retained after the user confirms the export choices at the end.

---

## 3. Main Settings

### Model Package

The prototype supports:

| Model | Purpose |
| --- | --- |
| Original BubMask | Baseline model from the original BubMask workflow |
| UNSW Round 2 | Current strongest held-out validation performance in this project |
| UNSW Round 3 | Provisional fine-tune for side-by-side testing |

Important scientific note: Round 3 is installed for comparison, but the
held-out validation/test results showed Round 2 was stronger on the available
COCO masks. Do not claim Round 3 is more accurate without further validation.

### Confidence Threshold

The confidence threshold controls which model detections are retained. A higher
threshold usually reduces false positives but may miss weaker bubbles. A lower
threshold usually finds more candidates but may include more incorrect masks.

### More Options

Advanced options are grouped under `MORE OPTIONS` so routine users do not need
to edit them. These settings include preprocessing profile, background
correction, quality gates, and preview behaviour. Use them only when testing a
specific image-processing condition.

---

## 4. Reviewing the Overlay

After inference, BubMask-Fiji opens review outputs showing:

- box overlay;
- mask overlay;
- bubble measurement table;
- histogram and statistics tabs;
- output file selection;
- run log.

The box overlay is useful for checking candidate locations. The mask overlay is
the most important scientific review image because it shows the segmented bubble
area used for measurement.

Green overlays indicate normal retained bubbles. Yellow overlays indicate
bubbles that need review or have quality warnings. All bubbles are treated as
ordinary bubbles in the final measurement table; manual bubbles are not reported
as a separate scientific class.

---

## 5. Adding Missed Bubbles Manually

If BubMask misses a bubble, add it using Fiji ROI tools:

1. In the review step, choose `ADD MANUAL BUBBLE`.
2. Use Fiji's ROI tools on the overlay review image.
3. Draw the bubble boundary or region of interest.
4. Return to the BubMask review window.
5. Press the button to add the current ROI or ROI Manager selections.
6. Press `REFRESH MASK OVERLAY` to update the displayed mask image.

The bubble table updates with the new bubble measurement. After addition, the
manual bubble contributes to the same histogram and statistics as all other
bubbles.

If a bubble was added incorrectly, use the delete/remove option in the manual
bubbles table, then refresh the overlay again.

---

## 6. Histogram and Data Analysis

The histogram tab allows the user to inspect the bubble equivalent diameter
distribution before exporting results.

Available controls include:

- histogram by count;
- PDF display;
- CDF display;
- number of bins;
- x-axis minimum and maximum;
- Sauter mean diameter, reported as `D32` or `D[3,2]`;
- arithmetic mean diameter;
- graph and CSV filename prefix.

When changing histogram settings, press `OK` to refresh the graph. Use `BACK`
to return to manual bubble editing or model selection. Use `FINISH PROCESSING`
only when the masks, measurements, and histogram settings are ready for export.

---

## 7. Exporting Results

After `FINISH PROCESSING`, BubMask-Fiji asks which files to keep. The simplified
scientific output package focuses on:

| Output | File type | Purpose |
| --- | --- | --- |
| Histogram | PNG and CSV | Reportable size-distribution graph and bin data |
| Bubble table | Excel-compatible table | Per-bubble area, equivalent diameter, position, score, and notes |
| Overlay pictures | PNG/TIFF | Visual audit of boxes and masks on the source image |
| Instance-label mask | TIFF | Pixel-level instance map for reproducibility and later review |
| Run summary/log | TXT or JSON | Model, calibration, settings, and export audit trail |

The user chooses the output folder. If the user chooses not to save outputs,
temporary files should be removed after the run.

---

## 8. Scientific Interpretation

BubMask-Fiji should be reported as a segmentation-assisted measurement workflow,
not as a fully autonomous measurement instrument. The user must inspect overlays
and confirm calibration before using the results in a scientific analysis.

When reporting results, include:

- model package name;
- confidence threshold;
- calibration in px/mm;
- number of bubbles;
- histogram bin settings;
- whether manual correction was used;
- mean diameter and Sauter mean diameter;
- any image-quality limitations.

For mineral-processing experiments, summarize results by flow rate, pressure,
vent geometry, and replicate image when those metadata are available.

---

## 9. Troubleshooting

### BubMask does not appear in Fiji

Check that `BubMask.py` is installed in:

```text
Fiji/scripts/Plugins/UNSW/BubMask.py
```

Restart Fiji after copying the script.

### BubMask runs but no files are produced

Check the log tab and confirm that the Python worker environment is available.
Also confirm that the selected model package has the required local weights
file.

### The overlay looks wrong

Confirm that the correct model package and calibration were selected. If the
image has unusual illumination, try the advanced preprocessing options under
`MORE OPTIONS`.

### The histogram does not change

After changing bins, axis limits, PDF/CDF, or statistics overlays, press `OK`
inside the histogram tab to refresh the graph.

### Manual ROI bubbles do not appear

Make sure the ROI is active on the overlay review image or stored in Fiji's ROI
Manager, then press the manual-add button and refresh the mask overlay.

---

## 10. Current Prototype Limits

- Model weights are not included in the public GitHub source release because
  they are large binary files.
- Round 3 is provisional and should not be treated as the best scientific
  model.
- Inter-user repeatability of manual correction still needs formal testing.
- The current UI is a Fiji/Jython research prototype. A polished Java/SciJava
  production plugin remains future work.
- Overlapping-bubble reconstruction is intentionally not implemented in the
  current research objective.

---

## 11. Where to Read More

Primary technical report:

```text
docs/bubmask-fiji.md
```

Validation report:

```text
docs/reports/round3_heldout_validation_analysis_2026-05-29.md
```

UI feature report:

```text
docs/reports/ui_feature_explanation_report.md
```

JSON worker contract:

```text
docs/reference/json_contract.md
```
