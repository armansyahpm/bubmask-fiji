# BubMask Mask R-CNN UNSW Round 2 v1

This is a provisional UNSW fine-tuned BubMask model package.

## Purpose

Improve bubble detection on UNSW mineral engineering microbubble TIFF images,
especially high-contrast measurable bubbles, using the revised Roboflow Round 2
COCO segmentation labels.

## Training Source

- Base weights: `models/bubmask-maskrcnn-v1/weights/mask_rcnn_bubble.h5`
- Training dataset: `validation/phase3_unsw_validation/roboflow_coco_round2_training_clean`
- Raw validation/testing dataset: `validation/phase3_unsw_validation/roboflow_coco_round2_local_split`
- Training run: `training_runs/roboflow_round2_clean_heads1/bubble_unsw_conservative20260524T2336`

## Training Summary

| Item | Value |
|---|---:|
| Environment | Local CPU, Python 3.10, TensorFlow/Keras 2.10 patched legacy graph mode |
| Epochs | 1 |
| Steps per epoch | 19 |
| Validation steps | 4 |
| Augmentation | Off |
| Final training loss | 2.7567 |
| Final validation loss | 2.2351 |

This is a first-pass CPU fine-tune. It is useful for comparison inside Fiji, but
it should not yet be treated as a final production scientific model.

## Weights

The worker expects:

```text
weights/mask_rcnn_bubble.h5
```

That file is the Round 2 fine-tuned checkpoint copied from:

```text
training_runs/roboflow_round2_clean_heads1/bubble_unsw_conservative20260524T2336/mask_rcnn_bubble_unsw_conservative_0001.h5
```
