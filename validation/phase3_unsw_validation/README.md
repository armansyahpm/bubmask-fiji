# Phase 3 UNSW Validation Dataset

Goal: determine whether the current `mask_rcnn_bubble.h5` model is valid for
UNSW microbubble images before claiming accuracy or retraining the model.

This folder separates **image intake** from **ground truth**. Model detections
can be used as pre-label suggestions, but they are not ground truth until a
human annotator or reviewer accepts them.

## Current Dataset State

Current local intake after the 2026-05-20 import:

- 2520 TIFF images in `validation/real_tiff_samples/`
- 1520 `without_particle` TIFFs
- 1000 `with_particle` TIFFs
- temporary calibration assumption: `183 px/mm` for all imported images

Still needed from the research team:

- final ruler-derived `px/mm` calibration for each acquisition setup
- true captured background images where available
- human-reviewed object labels

## Files

| File | Purpose |
|---|---|
| `image_manifest.csv` | One row per validation image, including flow condition, particle class, and calibration status. |
| `selected_validation_images.csv` | Stratified first-pass subset selected from the full image pool. |
| `annotation_tasks.csv` | Human annotation worklist. |
| `object_annotations.csv` | Human ground-truth object labels. Starts empty because model output is not ground truth. |
| `label_schema.csv` | Approved validation labels and definitions. |
| `annotation_guidelines.md` | How to label bubbles, blur, artifacts, border cases, highlights, and overlap. |
| `dataset_summary.json` | Machine-readable summary of image counts and annotation target. |

## Required Labels

Use only these labels for the first validation pass:

- `bubble_valid`
- `bubble_blurred_ignore`
- `nonbubble_artifact`
- `bubble_border_partial`
- `bubble_overlap_reconstruct`
- `saturated_highlight`
- `particle`
- `bubble_particle_overlap_review`

## Minimum Annotation Target

First milestone created by the manifest builder:

- 50 selected images;
- 5 target objects per selected image;
- approximately 250 object annotations;
- both bounding boxes and masks required;
- all three no-particle flow rates included;
- both particle-containing folders included.

Practical starting plan:

- label the images in `annotation_tasks.csv`;
- draw a bounding box and a mask for each selected object;
- use `particle` and `bubble_particle_overlap_review` on particle-containing
  images.

## Human Labeling Policy

You do not need to manually label every bubble in every image at the beginning.
For the first validation milestone, label a representative set of objects:

- clear accepted bubbles;
- blurred objects that should not enter the histogram;
- non-bubble clouds or black artifacts;
- border-touching objects;
- overlapping bubbles needing reconstruction;
- saturated highlights.

The software team can generate pre-label overlays and candidate boxes/masks,
but a human reviewer should confirm the final labels. Otherwise, the validation
set only repeats the model's own mistakes.
