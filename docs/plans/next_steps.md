# BubMask-Fiji Next Steps

Date: 2026-05-18  
Status reviewed: 2026-06-01

## 2026-06-01 Status Update

The core research-prototype objective is complete. This roadmap now mainly
represents production hardening and future model/packaging work. The current
operational baseline is documented in:

```text
README.md
docs\bubmask-fiji.md
docs\development\agent_handoff_memory.md
```

Current live Fiji entry:

```text
Plugins > UNSW > BubMask
```

Current installed/project SHA256:

```text
97DDF43E3A2A2E884962C7099177504E6B56667F6606326910DFB70D3FEC3882
```

This file is the working roadmap for moving BubMask-Fiji from the current
functional prototype toward a scientist-ready Fiji/ImageJ plugin for noisy
microbubble sizing.

## Current planning conclusion

The current prototype can run BubMask Mask R-CNN and draw bounding boxes, but a
fully functional scientific tool must add:

- full instance-mask overlays; **first saved overlay implementation completed
  2026-05-19**;
- saved label/mask images; **first `instance_labels.tif` implementation
  completed 2026-05-19**;
- circle or ellipse fitting for reconstruction;
- explicit handling of blurred bubbles and non-bubble artifacts; **first
  preprocessing and quality-scoring implementation completed 2026-05-19**;
- calibration enforcement; **first missing-calibration warning and manual
  `px/mm` route completed 2026-05-19**;
- validation on UNSW images before deciding whether to fine-tune/retrain.

## 1. Add true segmentation overlay

Replace or extend the current box-only overlay with:

- translucent per-bubble mask overlay; **completed for saved PNG/TIFF
  artifacts**;
- bubble id labels;
- optional circle/ellipse overlay;
- rejected-object overlay;
- saved `overlay_masks.png` and `overlay_masks.tif`; **completed**.

Expected outcome: a mineral scientist can visually verify exactly which pixels
were measured for each bubble.

## 2. Export masks for audit and validation

Save model outputs as:

- label image; **completed as `instance_labels.tif`**;
- per-instance binary masks or mask stack;
- mask metadata JSON.

Expected outcome: every result can be compared against hand masks and reviewed
outside Fiji.

## 3. Build the UNSW validation dataset

Annotate representative images from:

```text
validation/real_tiff_samples/
```

First Phase 3 scaffold completed 2026-05-20:

```text
validation/phase3_unsw_validation/
  README.md
  annotation_guidelines.md
  image_manifest.csv
  object_annotations.csv
  label_schema.csv
```

Phase 3 was rebuilt after full lab image import on 2026-05-20:

```text
validation/phase3_unsw_validation/
  image_manifest.csv              # 2520 TIFFs
  selected_validation_images.csv  # 50 first-pass annotation images
  annotation_tasks.csv            # 250 target object annotations
  object_annotations.csv          # empty human ground-truth table
  label_schema.csv                # bubble + particle labels
  dataset_summary.json
```

Current imported image pool:

- 501 `without_particle` images at 0.3 LPM;
- 509 `without_particle` images at 0.5 LPM;
- 510 `without_particle` images at 0.7 LPM;
- 500 `with_particle` images in `withparticle0-5`;
- 500 `with_particle` images in `withparticle1-0`.

Temporary calibration:

```text
px_per_mm = 183
calibration_status = assumed
```

Still needed from the research team:

- final `px/mm` calibration for each acquisition setup;
- true background images where available;
- human-reviewed object annotations with both boxes and masks.

Include explicit labels for:

- valid sharp bubbles;
- blurred bubbles to ignore;
- non-bubble artifacts;
- border-touching bubbles;
- overlapped bubbles needing reconstruction;
- saturated-highlight cases.
- particles in with-particle images;
- bubble-particle overlap/review cases.

Expected outcome: the team can quantify whether current BubMask weights are
valid for UNSW microbubble images.

## 4. Validate the current BubMask model

Before retraining or changing model architecture, measure:

- precision, recall, F1;
- AP50/AP75;
- mask IoU/Dice;
- equivalent diameter error;
- small/medium/large bubble recall;
- false positives on non-bubble objects;
- false positives on blurred objects;
- overlap-specific error.

Expected outcome: a data-driven decision on whether current
`mask_rcnn_bubble.h5` is good enough, needs fine-tuning, or should be benchmarked
against alternatives.

## 5. Add noisy-image quality controls

Add preflight and per-object quality signals:

- field-of-view mask; **first export completed as `fov_mask.tif`**;
- flat-field/illumination correction; **implemented as
  `fov_flatfield_model` and `conservative_denoise_model` profiles**;
- focus/blur proxy; **implemented as `focus_score`**;
- saturation/highlight flag;
- minimum/maximum diameter filter;
- border exclusion policy.

Expected outcome: poor images or poor objects are flagged before the user trusts
the histogram.

Current implementation status:

```text
preprocessed_image.png / .tif
fov_mask.tif
measurement_status
accepted_for_histogram
focus_score
boundary_gradient_score
annular_contrast
circularity
solidity
```

Remaining work: tune the thresholds against manually reviewed UNSW labels.

## 6. Add shape reconstruction

Implement reconstruction as a separate, auditable measurement path:

1. raw mask area and equivalent diameter;
2. minimum enclosing circle diameter;
3. optional ellipse/spline fit;
4. overlap/reconstruction flag;
5. raw-vs-reconstructed diameter comparison in CSV and histogram.

Expected outcome: overlapping or partially visible bubbles can be measured with
an explicit reconstruction policy rather than hidden assumptions.

## 6A. Enforce calibration and background image policy

Implemented first pass:

- read Fiji/ImagePlus calibration;
- allow manual `px/mm` entry from a ruler measurement;
- force pixel-only outputs when calibration is missing;
- write `calibration_status`, `calibration_source`, and
  `physical_measurement_trusted` into CSV/JSON;
- allow optional background image with `absolute_difference` or
  `subtract_offset` correction.

Remaining work:

- add a dedicated ruler-line helper command inside Fiji;
- add manifest-supplied calibration for batch runs;
- validate whether background correction improves Mask R-CNN accuracy on UNSW
  images.

## 7. Add calibrated histogram and experiment summaries

Generate:

- per-image bubble size histogram;
- accepted-only histogram;
- rejected/reconstructed object summary;
- combined experiment CSV grouped by flow rate, pressure, and vent geometry;
- Sauter mean diameter where calibration permits.

Expected outcome: outputs are useful for mineral-engineering interpretation, not
only computer-vision debugging.

Execution note added 2026-05-20:

Histogram generation can proceed before full Phase 3 validation if it is
treated as a **prototype visualization feature**, not as a validated scientific
result. The histogram should clearly state:

- calibration status;
- whether physical units are trusted;
- whether the model has been validated on the current image class;
- whether the histogram includes accepted-only objects or all detected objects.

This is useful because it lets the team inspect the expected final workflow
early. The risk is that an attractive histogram can make unvalidated detections
look authoritative. Until Phase 3 labels are reviewed, histograms should be
marked as exploratory.

## 8. Decide whether to fine-tune or benchmark alternatives

After validation:

- fine-tune Mask R-CNN if domain shift is moderate;
- benchmark YOLO-seg/ATS-YOLO-style models if speed or tiny-bubble recall is
  limiting;
- benchmark SplineDist/StarDist if round/overlapped bubble shape is the main
  issue;
- investigate SAM/BubSAM only as a research extension for shape reconstruction.

Expected outcome: model choice is based on UNSW evidence, not assumptions.

## 9. Promote the script prototype into the Java/SciJava plugin

Once the worker contract, overlays, validation, and output folders stabilize,
move the user workflow from the script prototype into the main Java/SciJava
plugin command.

Expected outcome: a cleaner Fiji menu command suitable for distribution.

## 10. Package for non-programming users

Choose a deployment method:

- local lab install package;
- release ZIP with plugin, Python worker, model package, and environment file;
- Fiji update site once stable.

Expected outcome: mineral engineering scientists can install and run
BubMask-Fiji without using the terminal.
