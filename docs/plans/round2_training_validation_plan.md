# BubMask-Fiji Round 2 Training and Validation Plan

Date: 2026-05-24

## 1. Dataset Status

The revised Roboflow COCO Segmentation export is now the best available UNSW
ground-truth dataset.

Source ZIP:

```text
C:\Users\arman\Downloads\microbubble_size_measurement.coco-segmentation (3).zip
```

Imported dataset:

```text
validation/phase3_unsw_validation/roboflow_coco_round2
```

Local train/validation/test split:

```text
validation/phase3_unsw_validation/roboflow_coco_round2_local_split
```

Training-clean derivative:

```text
validation/phase3_unsw_validation/roboflow_coco_round2_training_clean
```

## 2. Round 2 COCO Audit

| Item | Value |
|---|---:|
| Images | 27 |
| Total annotations | 4,559 |
| Trainable bubble masks | 4,532 |
| Field-of-view helper masks | 27 |
| Missing images | 0 |

The `field-of-view` class is useful metadata, but it must not be trained as a
bubble. The BubMask-Fiji dataset loader maps only `bubble` annotations to the
single foreground class.

## 3. Split Strategy

Because there are only 27 labelled images, the split is image-level and
traceable:

| Split | Images | Bubble annotations | Purpose |
|---|---:|---:|---|
| `train` | 19 | 3,217 | Fine-tuning. |
| `valid` | 4 | 739 | Hyperparameter and threshold selection. |
| `test` | 4 | 576 | Final hold-out comparison. |

This is a small dataset by image count, but dense by object count. The main
risk is not the number of bubbles; it is the limited diversity of only 27 image
fields.

## 4. Label Quality Result

The revised dataset is improved compared with Round 1, but not perfect.

| QC item | Round 1 | Round 2 |
|---|---:|---:|
| Bubble masks | 4,528 | 4,532 |
| Flagged annotations | 539 | 519 |
| Severe/review annotations | 393 | 371 |
| Multi-component instances | 393 | 371 |
| Low mask-to-bbox fill | 173 | 160 |
| Possible line artefacts | 11 | 11 |

Interpretation: Round 2 is slightly cleaner and should replace Round 1.
However, serious training should not use the raw annotations blindly.

## 5. Training-Clean Dataset

Since the labelling tool is no longer available, a conservative filtered
training copy was created. It removes annotations with the following QC flags:

```text
multi_component_instance
possible_line_artifact
low_mask_to_bbox_fill
very_large_bbox
tiny_mask
```

It keeps border-touching bubbles because they can help the model learn edge
cases; the plugin can still flag them as `border_touching` during measurement.

Cleaned dataset result:

| Split | Images | Kept bubble annotations |
|---|---:|---:|
| `train` | 19 | 2,981 |
| `valid` | 4 | 646 |
| `test` | 4 | 527 |
| **Total** | **27** | **4,154** |

Post-filter QC:

| QC item | Count |
|---|---:|
| Bubble annotations checked | 4,154 |
| Severe/review annotations | 0 |
| Remaining flags | 141 border-touching boxes |

This is the recommended dataset for fine-tuning.

## 6. Local Smoke Training Result

Smoke command intent:

```text
dataset = roboflow_coco_round2_training_clean
weights = models/bubmask-maskrcnn-v1/weights/mask_rcnn_bubble.h5
epochs = 1
steps_per_epoch = 1
validation_steps = 1
augmentation = off
```

What now works:

- COCO import works.
- Train/valid/test split works.
- Bubble-only class mapping works.
- Polygon masks and compressed COCO RLE masks decode.
- Legacy Mask R-CNN training graph builds.
- Starting weights load.
- Checkpoint directory is created.
- Training reaches Keras `fit_generator` / `train_on_batch`.

Current blocker:

```text
AssertionError inside keras.backend.eager_learning_phase_scope
```

Interpretation:

The revised dataset is usable. The remaining problem is the legacy Matterport
Mask R-CNN training runtime. Fiji inference can continue in the current Python
3.10 / TensorFlow 2.10 environment, but model fine-tuning should use a separate
training runtime pinned for legacy Mask R-CNN training.

## 7. Recommended Training Strategy

### 7.1 Keep Two Environments

| Environment | Purpose | Status |
|---|---|---|
| Fiji inference environment | Run the plugin and current/future `.h5` weights. | Keep as-is. |
| Training environment | Fine-tune Mask R-CNN on Roboflow COCO masks. | Use GPU and legacy-compatible runtime. |

Do not destabilize the working Fiji plugin environment just to train the model.

### 7.2 Training Input

Primary training dataset:

```text
validation/phase3_unsw_validation/roboflow_coco_round2_training_clean
```

Starting weights:

```text
models/bubmask-maskrcnn-v1/weights/mask_rcnn_bubble.h5
```

Target output:

```text
models/bubmask-maskrcnn-unsw-round2-v1/weights/mask_rcnn_bubble_unsw_round2_v1.h5
```

### 7.3 Training Phases

| Phase | Layers | Epochs | Learning rate | Purpose |
|---|---|---:|---:|---|
| Smoke | heads | 1 | `1e-4` | Confirm runtime and dataset are trainable. |
| A | heads | 5-10 | `1e-4` | Adapt classifier, bbox, and mask heads to UNSW images. |
| B | upper backbone / `5+` | 10-20 | `1e-5` | Improve features for noisy/particle images. |
| C | optional all layers | 5-10 | `1e-6` | Only if validation improves without overfitting. |

Use early stopping: stop if validation AP and false-positive rate no longer
improve.

### 7.4 Augmentation Policy

Start with no augmentation for the first smoke and baseline run. Then add only
moderate augmentations:

| Augmentation | Use? | Reason |
|---|---|---|
| horizontal/vertical flips | yes | Bubble orientation is not physically fixed. |
| small rotation | yes | Microscope image orientation is arbitrary. |
| mild brightness/contrast | yes | Helps lighting variation. |
| heavy blur | no | The goal is to ignore blurred objects, not teach them as positives. |
| aggressive noise | no initially | Can make artefacts look like bubbles. |

## 8. Validation Strategy

Validation must answer two questions:

1. Does fine-tuning improve bubble detection?
2. Does it improve scientific measurement reliability?

### 8.1 Model Comparison

Compare at least two models:

| Model | Meaning |
|---|---|
| `mask_rcnn_bubble.h5` | Current original BubMask weights. |
| `mask_rcnn_bubble_unsw_round2_v1.h5` | Fine-tuned UNSW model. |

Evaluate both on:

| Dataset | Purpose |
|---|---|
| Round 2 clean valid/test | High-confidence measurement benchmark. |
| Round 2 raw valid/test | Realistic robustness benchmark. |
| Full unlabelled 2,520 lab TIFF inventory | Qualitative production stress test. |

### 8.2 Metrics

Detection metrics:

```text
AP50
AP75
mAP across IoU thresholds
precision
recall
F1
false positives per image
false negatives per image
```

Measurement metrics:

```text
equivalent diameter error
median diameter difference
Sauter mean diameter shift
histogram distance
accepted/review/rejected object count
```

Operational metrics:

```text
runtime per image
GPU/CPU memory use
failure rate
number of detections requiring review
```

## 9. Acceptance Criteria

The fine-tuned model should only replace the current model if:

1. It improves AP50 or AP75 on the clean test set.
2. It does not increase false positives on with-particle images.
3. It produces visually better overlays on noisy UNSW images.
4. It improves histogram stability for repeated experimental conditions.
5. It still runs through the Fiji worker contract and returns JSON, CSV, mask
   overlay, and label-image artifacts.

## 10. Execution Status

The first Round 2 training cycle has been executed locally on CPU. A dedicated
GPU runtime is still recommended for longer training, but it is no longer a
hard blocker for proving the training path.

| Step | Status | Evidence |
|---|---|---|
| Use `roboflow_coco_round2_training_clean` for training. | Done | Training script consumed the cleaned COCO split. |
| Keep `roboflow_coco_round2_local_split` for honest validation/testing. | Done | Raw split remains separate and is referenced in model metadata. |
| Set up separate legacy Mask R-CNN training behavior. | Done locally | Training entry point uses graph mode while Fiji inference remains unchanged. |
| Train from `mask_rcnn_bubble.h5`. | Done | Checkpoint initialized from `models/bubmask-maskrcnn-v1/weights/mask_rcnn_bubble.h5`. |
| Import new `.h5` into Fiji model layer. | Done | `models/bubmask-maskrcnn-unsw-round2-v1/weights/mask_rcnn_bubble.h5`. |
| Compare old vs new on identical TIFFs. | Done | `validation/evaluations/model_comparison_round2_heads1`. |

First training run:

```text
training_runs/roboflow_round2_clean_heads1/bubble_unsw_conservative20260524T2336
```

Imported model package:

```text
models/bubmask-maskrcnn-unsw-round2-v1
```

Comparison artifacts:

```text
validation/evaluations/model_comparison_round2_heads1/model_comparison_summary.csv
validation/evaluations/model_comparison_round2_heads1/model_comparison_summary.md
validation/evaluations/model_comparison_round2_heads1/model_comparison_contact_sheet.png
```

Initial TIFF comparison:

| Image | Original detections | UNSW Round 2 detections |
|---|---:|---:|
| `bubble_3atm_4vent_1-5mm_0-3lpm_S0001.tif` | 38 | 70 |
| `bubble_3atm_4vent_1-5mm_0-5lpm_S0001.tif` | 42 | 78 |
| `Buble Image 1000001.tif` with particle | 6 | 39 |

Interpretation:

```text
The UNSW Round 2 fine-tune is more sensitive on the tested TIFFs. This is
promising for missed sharp bubbles, but it can only become the default model
after quantitative validation confirms precision and false-positive behavior.
```

## 11. Immediate Next Engineering Steps

1. Run quantitative old-vs-new evaluation on the Round 2 `valid` and `test`
   splits using COCO masks and IoU metrics.
2. Review the old-vs-new contact sheet visually and mark obvious false
   positives, especially in the with-particle image.
3. Run a longer heads-only training job on GPU or overnight CPU if validation
   suggests the first model is moving in the right direction.
4. Add a Fiji UI option for selecting `bubmask-maskrcnn-v1` versus
   `bubmask-maskrcnn-unsw-round2-v1` before changing the default model.
5. Keep all histogram and reporting outputs tagged with the model package name
   and weights version.

## 12. Fallback Path

If legacy Mask R-CNN training remains too fragile, keep the Fiji plugin
architecture but train a modern instance segmentation model separately
(`YOLO-seg`, Detectron2 Mask R-CNN, or SAM-assisted segmentation). This is a
Phase-D fallback. The immediate scientific priority remains validating whether
fine-tuned BubMask Mask R-CNN is good enough.
