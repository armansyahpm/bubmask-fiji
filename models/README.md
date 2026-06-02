# BubMask-Fiji Model Packages

Each subfolder is a model package with metadata and a local `weights/` folder.

```text
bubmask-maskrcnn-v1/              Original BubMask baseline metadata.
bubmask-maskrcnn-unsw-round2-v1/  UNSW Round 2 model metadata.
bubmask-maskrcnn-unsw-round3-v1/  UNSW Round 3 provisional fine-tune metadata.
```

Large Mask R-CNN `.h5` weight files are intentionally ignored by git. Place the
required local file at:

```text
models/<model-package>/weights/mask_rcnn_bubble.h5
```

For release `v0.1.0`, only UNSW Round 2 and UNSW Round 3 weights are distributed
as GitHub Release assets. Original BubMask weights are not distributed.

Before public scientific claims, check the validation report in:

```text
docs/reports/round3_heldout_validation_analysis_2026-05-29.md
```

Current validation showed Round 2 outperforming Round 3 on the available
held-out COCO masks, so Round 3 should be treated as provisional.
