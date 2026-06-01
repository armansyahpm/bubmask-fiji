# Phase 3 Annotation Guidelines

These guidelines define the first human validation pass for BubMask-Fiji.

## What You Need To Do

You do not need to manually label every bubble in every image yet. For the
first validation pass, annotate 100 to 300 representative objects across the
available experiment conditions.

The annotator should inspect the original TIFF and the BubMask overlay together
and decide whether each object belongs in the scientific bubble-size histogram.

## Labels

| Label | Use when... | Histogram policy |
|---|---|---|
| `bubble_valid` | The bubble has a clear measurable boundary and is not dominated by blur, glare, border clipping, or overlap. | Include. |
| `bubble_blurred_ignore` | The object is probably a real bubble, but its boundary is too soft for reliable sizing. | Exclude or review. |
| `nonbubble_artifact` | The object is a cloud, stain, shadow, black spot, dirt, texture patch, or other false object. | Exclude. |
| `bubble_border_partial` | The bubble touches the camera/FOV/image border and is incomplete. | Exclude or review. |
| `bubble_overlap_reconstruct` | A bubble is partly hidden by another bubble or neighboring object and may need circle/ellipse reconstruction. | Review/reconstruct. |
| `saturated_highlight` | The object is mainly glare or a bright saturated spot rather than the bubble boundary. | Exclude or flag. |
| `particle` | A solid particle in the liquid phase, not a gas bubble. | Exclude from bubble histogram; use for particle-vs-bubble training. |
| `bubble_particle_overlap_review` | Bubble and particle touch, overlap, or obscure each other. | Review; may need separate masks for bubble and particle. |

## How To Annotate

Minimum information per object:

- `image_id`
- `label`
- bounding box: `x_px`, `y_px`, `width_px`, `height_px`
- object mask path: `mask_path`
- `has_box = true`
- `has_mask = true`
- optional manual diameter in pixels or mm
- annotator name
- confidence: `high`, `medium`, or `low`
- notes for difficult cases

Preferred annotation shape:

- mask or polygon for final validation;
- bounding box in addition to the mask;
- manual diameter is useful where a clear rim exists.

## First Selection Strategy

Start with the generated `annotation_tasks.csv`:

- 10 images from each available experiment group;
- 5 target objects per selected image;
- about 250 first-pass object annotations total;
- both box and mask annotation for every object.

Make sure the labels include easy positives and hard negatives. A dataset with
only clear bubbles will overestimate model accuracy.

## Who Should Label?

The model can propose boxes/masks, and Codex can help create overlays and CSV
templates, but final ground truth should be confirmed by a human familiar with
the experiment. This is especially important for blurred bubbles, non-bubble
clouds, particles, and particle-containing images.

## Temporary Calibration

For the current Phase 3 scaffold, all imported images are assigned:

```text
px_per_mm = 183
pixel_width_mm = 1 / 183
pixel_height_mm = 1 / 183
calibration_status = assumed
```

This is suitable for development and first-pass validation organization, but
must be replaced by final ruler calibration before reporting physical bubble
diameters.
