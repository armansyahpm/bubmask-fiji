# BubMask-Fiji Python Modules

This package contains the domain-specific Python code that will sit between the
Fiji Java command and the imported BubMask Mask R-CNN runtime.

The copied `bubble_analyser` package beside this folder is treated as vendor
runtime code. New Fiji-specific logic should go in `bubmask_fiji`.

## Planned module responsibilities

- `io`: image loading, temporary file conventions, JSON request/response IO.
- `preprocessing`: field-of-view masking, grayscale conversion, normalization.
- `quality`: saturation, illumination, focus, and calibration checks.
- `segmentation`: BubMask model invocation and mask conversion.
- `overlap`: overlapping/merged bubble flags and postprocessing policies.
- `measurement`: area, equivalent diameter, centroid, border flags.
- `histogram`: calibrated bubble-size distribution generation.
- `export`: CSV, JSON, mask, overlay, and report outputs.
- `validation`: comparison against hand masks and expected measurements.
