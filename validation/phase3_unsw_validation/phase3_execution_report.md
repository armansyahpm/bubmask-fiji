# Phase 3 Validation Execution Report

Date: 2026-05-20  
Project: BubMask-Fiji

## What Was Executed

The Phase 3 validation scaffold was rebuilt using the newly imported lab TIFF
image set.

## Image Intake

| Image class | Experiment group | TIFF count |
|---|---|---:|
| `without_particle` | `bubble_3atm_4vent_1-5mm_0-3lpm` | 501 |
| `without_particle` | `bubble_3atm_4vent_1-5mm_0-5lpm` | 509 |
| `without_particle` | `bubble_3atm_4vent_1-5mm_0-7lpm` | 510 |
| `with_particle` | `bubble_3atm_4vent_1-5mm_0-3lpm_withparticle0-5` | 500 |
| `with_particle` | `bubble_3atm_4vent_1-5mm_0-3lpm_withparticle1-0` | 500 |
| **Total** |  | **2520** |

## Temporary Calibration

All imported images were assigned the temporary development calibration:

```text
px_per_mm = 183
pixel_width_mm = 0.0054644809
pixel_height_mm = 0.0054644809
calibration_status = assumed
```

This is acceptable for organizing the dataset and prototyping histogram
generation. It must be replaced by final ruler calibration before physical
diameters are reported.

## First-Pass Annotation Subset

A stratified first-pass subset was generated:

```text
10 images per experiment group
50 images total
5 target objects per image
250 target annotations
required geometry = box_and_mask
```

The selected images are listed in:

```text
selected_validation_images.csv
annotation_tasks.csv
```

## Ground-Truth Labels

The current labels are:

```text
bubble_valid
bubble_blurred_ignore
nonbubble_artifact
bubble_border_partial
bubble_overlap_reconstruct
saturated_highlight
particle
bubble_particle_overlap_review
```

## Current Status

Phase 3 is now ready for human annotation. Accuracy metrics are not available
yet because `object_annotations.csv` is intentionally empty. Model predictions
can be used as annotation suggestions, but they cannot be treated as ground
truth.

## Next Action

Use `annotation_tasks.csv` to annotate the first 50 selected images. For each
object, create both:

- a bounding box;
- an object mask.

Once the first annotations exist, BubMask-Fiji can compute precision, recall,
false-positive rate, mask IoU/Dice, and bubble diameter error.
