# BubMask Mask R-CNN UNSW Round 3 v1

This is the Round 3 UNSW fine-tuned BubMask model package for Fiji/ImageJ
testing.

## Purpose

Improve microbubble instance segmentation on UNSW mineral engineering images
using the 350-image human-corrected COCO Segmentation dataset exported from
Roboflow.

## Training Source

- Source ZIP: `C:/Users/arman/Downloads/microbubble_size_measurement2.coco-segmentation.zip`
- Base weights: `models/bubmask-maskrcnn-unsw-round2-v1/weights/mask_rcnn_bubble.h5`
- Training dataset: `validation/phase3_unsw_validation/roboflow_coco_round3_human350_training_clean_fast`
- Raw validation/testing dataset: `validation/phase3_unsw_validation/roboflow_coco_round3_human350_local_split`
- Training run: `training_runs/roboflow_round3_human350_heads3/bubble_unsw_conservative20260528T0420`

## Dataset Summary

| Item | Value |
|---|---:|
| Images | 350 |
| Raw bubble annotations | 34,258 |
| Train / valid / test images | 245 / 52 / 53 |
| Kept annotations after QC cleaning | 34,249 |
| Removed annotations after QC cleaning | 9 |

## Training Summary

| Item | Value |
|---|---:|
| Environment | Local CPU, Python 3.10, TensorFlow/Keras 2.10 patched legacy graph mode |
| Epochs | 3 |
| Steps per epoch | 245 |
| Validation steps | 52 |
| Augmentation | On |
| Epoch 1 validation loss | 1.4899 |
| Epoch 2 validation loss | 1.4599 |
| Epoch 3 validation loss | 1.4288 |
| Selected checkpoint | `mask_rcnn_bubble_unsw_conservative_0003.h5` |

The validation loss improved each epoch, so the Fiji package uses the epoch 3
checkpoint.

## Weights

The worker expects:

```text
weights/mask_rcnn_bubble.h5
```

That file was copied from:

```text
training_runs/roboflow_round3_human350_heads3/bubble_unsw_conservative20260528T0420/mask_rcnn_bubble_unsw_conservative_0003.h5
```

## Status

This package is installed and ready for Fiji/BubMask side-by-side testing, but
it is not the preferred scientific model based on the 2026-05-29 held-out COCO
validation below. Do not claim that Round 3 is more accurate than Round 2.

## Held-Out COCO Validation

Full valid/test validation was completed on 2026-05-29 against the cleaned
350-image COCO dataset:

```text
validation/coco_eval_round3_human350_full_valid_test_final_20260529
docs/round3_heldout_validation_analysis_2026-05-29.md
```

Overall metrics:

| Split | Model | Precision@0.50 | Recall@0.50 | F1@0.50 | Precision@0.75 | Recall@0.75 | F1@0.75 |
|---|---|---:|---:|---:|---:|---:|---:|
| valid | round2 | 0.9994 | 0.9930 | 0.9962 | 0.9988 | 0.9924 | 0.9956 |
| valid | round3_fiji | 0.7634 | 0.6399 | 0.6962 | 0.5261 | 0.4409 | 0.4798 |
| test | round2 | 0.9998 | 0.9880 | 0.9939 | 0.9981 | 0.9863 | 0.9922 |
| test | round3_fiji | 0.7578 | 0.6341 | 0.6904 | 0.5287 | 0.4423 | 0.4817 |

Condition-level results for `with_particle` and `without_particle` are in:

```text
validation/coco_eval_round3_human350_full_valid_test_final_20260529/coco_validation_condition_summary.csv
```

Caveat: these COCO labels may be biased toward Round 2 because the
active-learning labels were partly derived from earlier auto-label outputs.
Even with that caveat, Round 3 remains provisional and should be visually
reviewed before any further scientific use.
