# BubMask JSON Contract

This contract is the first stable boundary between the Fiji Java command and
the Python Mask R-CNN worker.

## Request: `bubmask.request.v1`

```json
{
  "schema_version": "bubmask.request.v1",
  "source_title": "image.tif",
  "image_path": "validation/real_tiff_samples/example/image.tif",
  "model_package": "models/bubmask-maskrcnn-v1",
  "inference_mode": "bubmask_mask_rcnn",
  "preprocessing_profile": "conservative_denoise_model",
  "quality_gate_mode": "review_only",
  "measure_sharp_bubbles_only": false,
  "min_focus_score": 10.0,
  "min_diameter_px": 0,
  "max_diameter_px": 0,
  "calibration_status": "known",
  "calibration_source": "manual_px_per_mm",
  "px_per_mm": 184.528,
  "background_image_path": "C:/path/to/background.tif",
  "background_correction_mode": "absolute_difference",
  "background_offset": 0,
  "width_px": 2048,
  "height_px": 2048,
  "n_slices": 1,
  "n_frames": 1,
  "pixel_width": 0.5,
  "pixel_height": 0.5,
  "unit": "um",
  "confidence_threshold": 0.5,
  "run_output_dir": "artifacts/results_archive_20260601/bubmask_run_20260518_205503_image"
}
```

`image_path` and `model_package` are now supported by the Python worker. Paths
may be absolute or relative to the request JSON file's directory.
`run_output_dir` is optional. If supplied, the worker writes run artifacts into
that folder.

The worker supports three inference modes:

- `placeholder`: deterministic fake result for plumbing tests.
- `adaptive_threshold_baseline`: OpenCV baseline candidate detection.
- `bubmask_mask_rcnn`: trained Mask R-CNN inference using `mask_rcnn_bubble.h5`.

The worker now supports conservative preprocessing profiles:

- `raw_model`: no denoising; scientific baseline.
- `fov_flatfield_model`: FOV masking plus background/flat-field correction.
- `conservative_denoise_model`: FOV masking, flat-field correction, median blur,
  and small Gaussian blur.
- `classical_diagnostic`: conservative denoising plus CLAHE for threshold/debug
  diagnostics.

The worker also supports object-quality gating:

- `quality_gate_mode = review_only`: compute status/flags but preserve reviewed
  detections in histogram unless they are hard-rejected.
- `quality_gate_mode = filter_histogram`: include only `accepted_bubble`
  detections in the histogram-ready count.
- `quality_gate_mode = off`: preserve raw model detections.

Calibration policy:

- If `calibration_status = known`, physical units may be exported.
- If `px_per_mm > 0`, the worker converts to `pixel_width = 1 / px_per_mm`,
  `pixel_height = 1 / px_per_mm`, and `unit = mm`.
- If calibration is missing, the worker reports pixel units only and emits a
  warning. Physical diameter should not be trusted.

Background correction:

- `background_correction_mode = none`: no captured-background correction.
- `background_correction_mode = absolute_difference`: use
  `abs(image - background)` and normalize.
- `background_correction_mode = subtract_offset`: use
  `image - background + background_offset`, clip, and normalize.

Future large-image support may replace a single `image_path` with one of:

- a tile directory manifest,
- a shared-memory handle, or
- an encoded tensor reference.

For production, prefer file/tile manifests so large microscopy images do not
need to cross the Java/Python boundary as one large JSON payload.

## Response: `bubmask.inference.v1`

```json
{
  "schema_version": "bubmask.inference.v1",
  "model": {
    "name": "bubmask-maskrcnn-v1",
    "hash": "pending-runtime-load",
    "runtime": "python-placeholder",
    "package_path": "models/bubmask-maskrcnn-v1",
    "weights_path": "models/bubmask-maskrcnn-v1/weights/mask_rcnn_bubble.h5",
    "weights_present": true
  },
  "image": {
    "path": "validation/real_tiff_samples/example/image.tif",
    "format": "TIFF",
    "mode": "L",
    "width_px": 1024,
    "height_px": 1024,
    "n_frames": 1
  },
  "masks": [
    {
      "id": 1,
      "score": 0.5,
      "class_label": "bubble",
      "bbox": [100.0, 100.0, 20.0, 20.0],
      "area_px": 314.16
    }
  ],
  "measurements": [
    {
      "bubble_id": 1,
      "score": 0.5,
      "area_px": 314.16,
      "area_calibrated": 78.54,
      "equivalent_diameter_px": 20.0,
      "equivalent_diameter_calibrated": 10.0,
      "diameter_unit": "um",
      "calibration_status": "known",
      "calibration_source": "manual_px_per_mm",
      "physical_measurement_trusted": true,
      "pixel_width": 0.005419,
      "pixel_height": 0.005419,
      "centroid_x_px": 110.0,
      "centroid_y_px": 110.0,
      "bbox_x_px": 100.0,
      "bbox_y_px": 100.0,
      "bbox_width_px": 20.0,
      "bbox_height_px": 20.0,
      "touches_border": false,
      "contains_saturated_highlight": false,
      "saturated_highlight_fraction": 0.0,
      "low_confidence": false,
      "accepted": true,
      "measurement_status": "accepted_bubble",
      "accepted_for_histogram": true,
      "rejection_reason": "",
      "focus_score": 35.2,
      "boundary_gradient_score": 60.3,
      "annular_contrast": 0.12,
      "circularity": 0.91,
      "solidity": 0.98,
      "flags": []
    }
  ],
  "outputs": {
    "run_output_dir": "artifacts/results_archive_20260601/bubmask_run_20260518_205503_image",
    "per_bubble_csv": "artifacts/results_archive_20260601/bubmask_run_20260518_205503_image/per_bubble_measurements.csv",
    "overlay_png": "artifacts/results_archive_20260601/bubmask_run_20260518_205503_image/overlay_boxes.png",
    "overlay_tif": "artifacts/results_archive_20260601/bubmask_run_20260518_205503_image/overlay_boxes.tif",
    "overlay_masks_png": "artifacts/results_archive_20260601/bubmask_run_20260518_205503_image/overlay_masks.png",
    "overlay_masks_tif": "artifacts/results_archive_20260601/bubmask_run_20260518_205503_image/overlay_masks.tif",
    "instance_labels_tif": "artifacts/results_archive_20260601/bubmask_run_20260518_205503_image/instance_labels.tif",
    "preprocessed_png": "artifacts/results_archive_20260601/bubmask_run_20260518_205503_image/preprocessed_image.png",
    "preprocessed_tif": "artifacts/results_archive_20260601/bubmask_run_20260518_205503_image/preprocessed_image.tif",
    "fov_mask_tif": "artifacts/results_archive_20260601/bubmask_run_20260518_205503_image/fov_mask.tif",
    "summary_json": "artifacts/results_archive_20260601/bubmask_run_20260518_205503_image/summary_response.json"
  },
  "diagnostics": {
    "preprocessing": {
      "profile": "conservative_denoise_model",
      "steps": ["grayscale", "fov_mask", "background_flatfield_correction"],
      "background_image": {
        "applied": true,
        "mode": "absolute_difference",
        "path": "C:/path/to/background.tif"
      }
    },
    "calibration": {
      "status": "known",
      "source": "manual_px_per_mm",
      "px_per_mm": 184.528,
      "pixel_width": 0.005419,
      "pixel_height": 0.005419,
      "unit": "mm"
    },
    "quality_summary": {
      "accepted_bubble": 66,
      "review_bubble": 3,
      "rejected_nonbubble": 0,
      "accepted_for_histogram": 69
    }
  },
  "warnings": []
}
```

If the worker fails, it writes a structured error response when possible:

```json
{
  "schema_version": "bubmask.inference.v1",
  "status": "error",
  "error": {
    "type": "FileNotFoundError",
    "message": "BubMask weights not found: ...",
    "traceback": "developer-readable Python traceback"
  },
  "warnings": [
    "BubMask worker failed before producing valid measurements. Check image_path, model_package, Python environment, and model weights."
  ]
}
```

## Required production additions

- `model.version`
- `model.training_dataset_id`
- `model.weights_path`
- `model.input_normalization`
- `run_id`
- `tile_id`
- polygon, RLE, or label-image references for masks
- calibrated unit names for every calibrated measurement
- full error payload with `error.code`, `error.message`, and `error.trace`
- validation-derived defaults for preprocessing and quality thresholds
