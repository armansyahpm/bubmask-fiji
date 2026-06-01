# Round 3 Held-Out Validation Analysis

Date: 2026-05-29  
Project: BubMask-Fiji, user-friendly ML-driven microbubble size measurement for mineral scientists

## Summary

This chapter evaluates whether the Round 3 fine-tuned Mask R-CNN model improved
BubMask-Fiji segmentation accuracy relative to the existing Round 2 model. The
analysis used the cleaned 350-image COCO segmentation dataset with a held-out
validation split of 52 images and a held-out test split of 53 images. Evaluation
was performed separately for the `with_particle` and `without_particle` image
groups.

The principal result is clear: against the current COCO masks, Round 2 strongly
outperformed Round 3 on every measured criterion. Round 2 achieved near-perfect
instance matching on both held-out splits, whereas Round 3 showed a substantial
loss of recall and a large increase in false negatives and false positives. The
Round 3 model should therefore remain provisional and should not be described as
scientifically more accurate than Round 2.

This conclusion must be interpreted with an important caveat. The current COCO
labels may be biased toward Round 2 because the active-learning workflow used
earlier Round 2 auto-label outputs as part of the labelling process. Therefore,
the validation is strong enough to reject an unsupported claim that Round 3 is
better, but it is not a fully independent proof that Round 2 is the true optimum
for all future manually corrected data.

## Evaluation Design

The evaluation used the cleaned Round 3 COCO dataset:

```text
validation/phase3_unsw_validation/roboflow_coco_round3_human350_training_clean_fast
```

Final outputs are stored in:

```text
validation/evaluations/coco_eval_round3_human350_full_valid_test_final_20260529
```

The evaluation compared:

- `round2`: `models/bubmask-maskrcnn-unsw-round2-v1`
- `round3_fiji`: the installed Fiji Round 3 package at
  `C:/Users/arman/Downloads/fiji-latest-win64-jdk/Fiji/models/bubmask-maskrcnn-unsw-round3-v1`

Inference used the same model packages and `raw_model` preprocessing profile
used by BubMask-Fiji. A cached in-process evaluator was used for stability and
speed. Its label-image matching was smoke-checked against the Fiji worker path
on one validation image before the full run.

## Metrics

Predicted instance masks were matched to COCO ground-truth instance masks using
intersection over union (IoU):

```text
IoU = area(predicted mask intersection ground-truth mask)
      / area(predicted mask union ground-truth mask)
```

An instance was counted as a true positive when the best unmatched ground-truth
mask exceeded the IoU threshold. Two thresholds were reported:

- IoU@0.50: permissive instance-level detection and approximate shape match.
- IoU@0.75: stricter mask localisation and shape agreement.

For each threshold:

```text
precision = TP / (TP + FP)
recall    = TP / (TP + FN)
F1        = 2 * precision * recall / (precision + recall)
```

## Overall Results

| Split | Model | Images | GT masks | Predictions | Precision@0.50 | Recall@0.50 | F1@0.50 | Precision@0.75 | Recall@0.75 | F1@0.75 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| valid | Round 2 | 52 | 4851 | 4820 | 0.9994 | 0.9930 | 0.9962 | 0.9988 | 0.9924 | 0.9956 |
| valid | Round 3 | 52 | 4851 | 4066 | 0.7634 | 0.6399 | 0.6962 | 0.5261 | 0.4409 | 0.4798 |
| test | Round 2 | 53 | 5419 | 5355 | 0.9998 | 0.9880 | 0.9939 | 0.9981 | 0.9863 | 0.9922 |
| test | Round 3 | 53 | 5419 | 4534 | 0.7578 | 0.6341 | 0.6904 | 0.5287 | 0.4423 | 0.4817 |

![Overall F1 comparison](figures/round3_validation/overall_f1_round2_vs_round3.png)

Round 2 remained extremely close to the current COCO labels at both IoU
thresholds. Its F1 score was 0.9962 on the validation split and 0.9939 on the
test split at IoU@0.50. At the stricter IoU@0.75 threshold, Round 2 still
maintained F1 scores above 0.99.

Round 3 performed substantially worse. At IoU@0.50, its F1 score was 0.6962 on
validation and 0.6904 on test. At IoU@0.75, its F1 score dropped to 0.4798 on
validation and 0.4817 on test. This drop at the stricter threshold indicates
that the Round 3 masks are not only missing instances, but also less well
aligned with the current ground-truth mask shapes.

## Particle-Stratified Results

| Split | Condition | Model | Images | GT masks | Predictions | F1@0.50 | F1@0.75 |
|---|---|---|---:|---:|---:|---:|---:|
| valid | with_particle | Round 2 | 38 | 3010 | 2988 | 0.9960 | 0.9960 |
| valid | with_particle | Round 3 | 38 | 3010 | 2502 | 0.7036 | 0.4739 |
| valid | without_particle | Round 2 | 14 | 1841 | 1832 | 0.9965 | 0.9948 |
| valid | without_particle | Round 3 | 14 | 1841 | 1564 | 0.6843 | 0.4893 |
| test | with_particle | Round 2 | 35 | 2927 | 2864 | 0.9888 | 0.9877 |
| test | with_particle | Round 3 | 35 | 2927 | 2436 | 0.6951 | 0.4691 |
| test | without_particle | Round 2 | 18 | 2492 | 2491 | 0.9998 | 0.9974 |
| test | without_particle | Round 3 | 18 | 2492 | 2098 | 0.6850 | 0.4963 |

![Condition F1 comparison](figures/round3_validation/condition_f1_iou50.png)

The Round 3 degradation was not confined to particle-containing images. Its
IoU@0.50 F1 score was similar for `with_particle` and `without_particle`
subsets, ranging from 0.6843 to 0.7036. This suggests a general model or
training/operating-point issue rather than a particle-specific failure alone.

Round 2 also showed a small condition effect on the test split: its
`with_particle` recall was 0.9781 compared with 0.9996 for `without_particle`.
That difference is scientifically plausible because particles and bubble
boundaries can create ambiguity. However, Round 2 still remained highly
accurate under the present label definition.

## Error Composition

![Error composition at IoU 0.50](figures/round3_validation/iou50_error_composition.png)

At IoU@0.50, Round 3 generated far more false negatives than Round 2:

- Validation split: Round 3 produced 1747 false negatives, compared with 34 for
  Round 2.
- Test split: Round 3 produced 1983 false negatives, compared with 65 for
  Round 2.

Round 3 also produced many more false positives:

- Validation split: 962 false positives for Round 3, compared with 3 for Round 2.
- Test split: 1098 false positives for Round 3, compared with 1 for Round 2.

The simultaneous increase in false positives and false negatives indicates that
Round 3 did not simply become more conservative. Instead, it changed the mask
set in a way that disagreed substantially with the current COCO mask definition.

![Precision-recall operating point](figures/round3_validation/precision_recall_iou50.png)

## Scientific Interpretation

The training loss for Round 3 improved across epochs, but the held-out instance
metrics show that lower training/validation loss did not translate into better
COCO mask agreement. This can happen when the optimisation objective, model
threshold, mask post-processing, or label distribution does not align with the
evaluation criterion used for scientific validation.

The most likely explanations are:

1. Round 2 label affinity. If a large fraction of the COCO labels originated
   from Round 2 auto-labels, then Round 2 is being evaluated partly against its
   own previous outputs. This makes the benchmark useful for regression testing
   but not fully independent.
2. Insufficient or poorly targeted Round 3 adaptation. The Round 3 training used
   a short heads-only fine-tuning schedule. This may have shifted the classifier
   and mask heads without improving the full instance-segmentation behaviour.
3. Threshold and calibration mismatch. Both models were evaluated at confidence
   threshold 0.10 using the `raw_model` preprocessing profile. Round 3 may
   require threshold tuning, although the large false-negative count indicates
   that threshold tuning alone is unlikely to recover the full gap.
4. Mask shape degradation. The strong decline at IoU@0.75 indicates that Round 3
   masks are less spatially consistent with the COCO ground truth, not merely
   fewer in number.

For a scientific microbubble measurement workflow, this matters because
segmentation errors propagate directly into bubble counts, equivalent diameter,
size distributions, and any interpretation of flotation operating conditions.
Therefore, Round 3 should not be used to generate final bubble-size
distributions unless visual review and additional independent validation show a
clear improvement.

## Recommendations

1. Keep Round 2 as the current quantitative reference model for scientific
   validation.
2. Keep Round 3 installed only as a provisional side-by-side model for visual
   inspection.
3. Do not report Round 3 as more accurate in the final report, presentation, or
   supervisor update.
4. Review representative overlays from both models, especially dense bubbles,
   boundary-touching bubbles, particle-rich images, and blurred images.
5. Before training a new model, confirm which COCO masks are fully
   human-corrected and which remain close to Round 2 auto-labels.
6. If another fine-tuning round is attempted, run validation after each
   checkpoint and select by held-out mask metrics, not only by training loss.

## Traceability

Key files:

```text
validation/evaluations/coco_eval_round3_human350_full_valid_test_final_20260529/coco_validation_summary.csv
validation/evaluations/coco_eval_round3_human350_full_valid_test_final_20260529/coco_validation_condition_summary.csv
validation/evaluations/coco_eval_round3_human350_full_valid_test_final_20260529/coco_validation_image_metrics.csv
validation/evaluations/coco_eval_round3_human350_full_valid_test_final_20260529/coco_validation_report.md
docs/figures/round3_validation/overall_f1_round2_vs_round3.png
docs/figures/round3_validation/condition_f1_iou50.png
docs/figures/round3_validation/iou50_error_composition.png
docs/figures/round3_validation/precision_recall_iou50.png
```
