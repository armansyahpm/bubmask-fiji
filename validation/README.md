# BubMask Validation Dataset

This directory defines the validation data contract. The real microscopy data
and hand masks should be added by the UNSW project team because they are
research data, not generic source code fixtures.

## Layout

- `fixtures/raw/`: small synthetic or placeholder input images.
- `real_tiff_samples/`: local real TIFF intake set for project development.
  Start with around 10 representative images. Files in this folder are ignored
  by git; document them in `sample_manifest_template.csv` or a copied manifest.
- `fixtures/hand_masks/`: hand-labeled masks or ROI zip files corresponding to
  images.
- `fixtures/expected/expected_measurements.csv`: expected calibrated
  measurements and tolerances.
- `evaluations/`: generated validation/evaluation outputs.
- `smoke_tests/`: smoke-test inputs and generated outputs.
- `scripts/`: validation runner scripts.
- `logs/`: local validation logs.
- `manifest.json`: dataset-level metadata, model version, calibration policy,
  and acceptance rules.

## Acceptance rule

A BubMask release candidate passes validation when:

- every required image has a matching hand mask,
- every predicted bubble can be matched to a hand-labeled object or rejected
  under a documented QC rule,
- equivalent diameter error is within the tolerance declared in
  `fixtures/expected/expected_measurements.csv`,
- every result records model name, model hash, request schema, response schema,
  input image id, and pixel calibration.

## Real TIFF intake rule

The real intake images should be used to design and stress-test the plugin UI
before the final validation dataset is locked. They are not automatically
"ground truth" until each image has a corresponding hand mask, calibration
record, and expected measurement row.

Use TIFF naming that encodes experiment context without spaces, for example:

```text
unsw_bubble_3atm_4vent_1p5mm_0p5lpm_rep01.tif
```

For each image, record at minimum:

- image id;
- relative file path;
- acquisition date;
- pressure;
- vent count or geometry;
- nominal aperture/needle/vent size;
- flow rate;
- pixel width and unit;
- bit depth;
- whether it is OME-TIFF, ImageJ TIFF, or plain TIFF;
- whether hand annotation exists;
- notes on highlights, blur, overlap, or illumination problems.
