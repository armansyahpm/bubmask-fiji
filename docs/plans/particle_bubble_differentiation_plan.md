# Particle vs Bubble Differentiation Plan

Date: 2026-05-20  
Project stage: Phase 3 validation and future with-particle model upgrade

## Why This Plan Exists

The original BubMask model was trained for bubble instance segmentation. The
new `with_particle` images introduce a second visual object class: solid
particles. These may be mistakenly segmented as bubbles if the model only knows
"bubble" versus "background".

The goal is not only to detect bubbles, but to prevent particles from entering
the bubble-size histogram.

## Current Data State

Current imported TIFF pool:

| Class | Experiment group | Count |
|---|---|---:|
| without particle | 0.3 LPM | 501 |
| without particle | 0.5 LPM | 509 |
| without particle | 0.7 LPM | 510 |
| with particle | withparticle0-5 | 500 |
| with particle | withparticle1-0 | 500 |

Temporary calibration:

```text
px_per_mm = 183
calibration_status = assumed
```

## Visual Definition

| Object | Expected image behavior | Measurement policy |
|---|---|---|
| Bubble | Rounded object with rim/annular contrast and physically plausible diameter. | Candidate for bubble histogram if sharp and calibrated. |
| Blurred bubble | Bubble-like but low focus or weak boundary. | Review or ignore for sizing. |
| Particle | Solid object, often darker/irregular/textured, without gas-bubble rim structure. | Exclude from bubble histogram. |
| Bubble-particle overlap | Bubble and particle touch or occlude each other. | Review; may need separate masks. |
| Cloud/artifact | Diffuse non-object texture, stain, shadow, or black spot. | Reject. |

## Recommended Algorithmic Path

### Stage 1: No-Retrain Particle Guard

Use current Mask R-CNN bubble detections as proposals, then score every object
with additional features:

| Feature | Why useful |
|---|---|
| Annular contrast | Bubbles often have rim/interior/background pattern; particles may not. |
| Boundary gradient | Sharp bubble edges should have coherent boundary transitions. |
| Circularity/eccentricity | Bubbles are usually round/elliptical; particles may be irregular. |
| Solidity | Particles/clouds may create ragged or fragmented masks. |
| Interior texture variance | Solid particles can have texture not typical of bubble interiors. |
| Focus score | Helps separate measurable bubbles from blurred non-measurements. |
| Saturated highlight fraction | Prevents glare from becoming a bubble measurement. |

Output should become:

```text
bubble_accepted
bubble_review
particle_rejected
nonbubble_rejected
overlap_review
```

This is fast to implement and can improve user trust, but it is not enough for
final scientific accuracy.

### Stage 2: Human Ground Truth For With-Particle Images

The Phase 3 annotation set now includes particle labels:

```text
particle
bubble_particle_overlap_review
```

For each selected with-particle image, annotate both boxes and masks:

- bubble masks;
- particle masks;
- overlapping bubble/particle review cases;
- clear non-bubble artifacts.

This creates the evidence needed to decide whether a retrained model is
required.

### Stage 3: Multi-Class Model Upgrade

If validation shows many particles are detected as bubbles, the production
model should move from binary bubble segmentation to multi-class instance
segmentation:

```text
class 1: bubble
class 2: particle
class 3: artifact/review object, optional
```

Two implementation options:

| Option | Description | Pros | Cons |
|---|---|---|---|
| Fine-tune Mask R-CNN as multi-class | Retrain current architecture with bubble and particle masks. | Best continuity with current pipeline. | Needs curated masks and training runtime. |
| Add second-stage classifier | Keep current bubble proposals, classify each crop as bubble/particle/artifact. | Faster to prototype; can use fewer labels. | Still depends on proposal quality. |

Recommended order:

1. Run current model on selected with-particle images.
2. Compare detections against human labels.
3. If particles frequently become bubbles, build second-stage classifier first.
4. If errors remain high, fine-tune Mask R-CNN as multi-class.

## Validation Metrics

For with-particle images, measure:

- bubble precision and recall;
- particle false-positive rate as bubble;
- bubble diameter error after particle rejection;
- overlap/review rate;
- mask IoU for bubbles;
- mask IoU for particles if a multi-class model is trained.

## Fiji UI Implication

The final with-particle UI should expose:

```text
Object class overlay:
  green = accepted bubble
  yellow = review bubble / overlap
  red = rejected artifact
  blue = particle

Histogram policy:
  include accepted bubbles only
  exclude particles
  exclude uncalibrated physical units
```

## Decision Rule

If particle-containing images have acceptable bubble precision after the
no-retrain particle guard, keep current Mask R-CNN for Phase 4 histogram
prototype. If particles are often counted as bubbles, do not use with-particle
histograms scientifically until either the second-stage classifier or
multi-class fine-tuned model is implemented.
