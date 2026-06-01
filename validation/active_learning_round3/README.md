# BubMask-Fiji Active Learning Round 3

This folder contains the Round 3 human-in-the-loop autolabelling run.

## Purpose

The 27 Roboflow-labelled images were enough to fine-tune a better Round 2
model, but the full lab inventory is much larger. Round 3 uses the fine-tuned
model to pre-label the unlabelled TIFF inventory so humans can correct masks
instead of drawing every bubble from scratch.

## Current Autolabelling Run

The full run targets the active lab TIFF folders:

```text
validation/real_tiff_samples/with_particle
validation/real_tiff_samples/without_particle
```

The old `testing_OLD` folder is not part of this active-learning run.

Output folder:

```text
validation/active_learning_round3/autolabel_predictions
```

Each processed image folder should contain:

```text
image.tif
request.json
response.json
overlay_masks.png
overlay_masks.tif
instance_labels.tif
per_bubble_measurements.csv
summary_response.json
```

Run settings:

| Setting | Value |
|---|---|
| Model | `bubmask-maskrcnn-unsw-round2-v1` |
| Confidence threshold | `0.10` |
| Preprocessing | `raw_model` |
| Quality gate | `review_only` |
| Calibration | `183 px/mm` temporary assumption |

## Monitoring

Watch live progress:

```powershell
Get-Content C:\Users\arman\tor_mere\bubmask-fiji\validation\active_learning_round3\autolabel_round3_stdout.log -Tail 30 -Wait
```

Check the latest summary:

```powershell
Get-Content C:\Users\arman\tor_mere\bubmask-fiji\validation\active_learning_round3\autolabel_predictions\autolabel_summary.json
```

Count completed review folders:

```powershell
(Get-ChildItem C:\Users\arman\tor_mere\bubmask-fiji\validation\active_learning_round3\autolabel_predictions -Directory).Count
```

Inspect the manifest:

```powershell
Import-Csv C:\Users\arman\tor_mere\bubmask-fiji\validation\active_learning_round3\autolabel_predictions\autolabel_manifest.csv |
  Select-Object -Last 10 index,condition,status,detections,accepted_bubble,review_bubble,elapsed_sec |
  Format-Table -AutoSize
```

Check scheduled task status:

```powershell
schtasks /Query /TN BubMaskRound3Autolabel /FO LIST
```

Stop the run if needed:

```powershell
schtasks /End /TN BubMaskRound3Autolabel
```

Restart/resume the run:

```powershell
C:\Users\arman\tor_mere\bubmask-fiji\validation\active_learning_round3\run_autolabel_round3.ps1
```

The autolabeller is resumable. Existing image folders with complete
`response.json`, `overlay_masks.png`, `instance_labels.tif`, and
`per_bubble_measurements.csv` are skipped unless the script is run with
`--overwrite`.

## Human Review Use

Humans should review the generated `overlay_masks.png` and correct the masks in
Roboflow or another annotation tool. The priority images should be selected
from the manifest using:

```text
with_particle cases
high review_bubble count
many detections
low visual quality
obvious particle false positives
overlapping/dense bubbles
```

The corrected masks become the Round 3 training dataset.

## Roboflow Import Package: First 250 Images

The first official 250 completed auto-labelled images were exported as a
Roboflow-ready COCO Segmentation package.

Folder:

```text
validation/active_learning_round3/roboflow_import_250_autolabel
```

ZIP:

```text
validation/active_learning_round3/roboflow_import_250_autolabel.zip
```

Export contents:

| Item | Count |
|---|---:|
| Images | 250 |
| COCO bubble annotations | 20,176 |
| Missing artifacts | 0 |
| Images with empty masks | 0 |

Roboflow workflow:

1. Create or open an **Instance Segmentation** project.
2. Upload `roboflow_import_250_autolabel.zip`.
3. Choose/import as **COCO Segmentation**.
4. Review each image: add missed bubbles, reshape weak masks, and delete false
   positives.
5. Export the corrected dataset again as **COCO Segmentation** for Round 3
   fine-tuning.

Important:

```text
These masks are auto-label predictions, not final ground truth.
They should be corrected before being used as a training dataset.
```

## Roboflow Import Package: 100 Without-Particle Images

A separate 100-image without-particle auto-labelled package was generated after
the first 250-image export was found to contain only with-particle images.

Selection:

| Source folder | Images |
|---|---:|
| `without_particle/bubble_3atm_4vent_1-5mm_0-3lpm` | 34 |
| `without_particle/bubble_3atm_4vent_1-5mm_0-5lpm` | 33 |
| `without_particle/bubble_3atm_4vent_1-5mm_0-7lpm` | 33 |
| **Total** | **100** |

Auto-label output:

```text
validation/active_learning_round3/autolabel_predictions_without_particle_100
```

Selection records:

```text
validation/active_learning_round3/without_particle_100_input_paths.txt
validation/active_learning_round3/without_particle_100_selection_manifest.csv
```

Roboflow-ready folder and ZIP:

```text
validation/active_learning_round3/roboflow_import_100_without_particle_autolabel
validation/active_learning_round3/roboflow_import_100_without_particle_autolabel.zip
```

Export contents:

| Item | Count |
|---|---:|
| Images | 100 |
| COCO bubble annotations | 13,588 |
| Missing artifacts | 0 |
| Images with empty masks | 0 |

The ZIP includes both root-level and `train/` `labelmap.txt` files for
Roboflow import:

```text
0: background
1: bubble
```

## Round 3 Trained Model Package

The corrected 350-image COCO Segmentation export was used for a new local
fine-tune on 2026-05-28.

Fiji-ready package:

```text
models/bubmask-maskrcnn-unsw-round3-v1
```

Selected weights:

```text
models/bubmask-maskrcnn-unsw-round3-v1/weights/mask_rcnn_bubble.h5
```

Training source:

```text
validation/phase3_unsw_validation/roboflow_coco_round3_human350_training_clean_fast
```

Training summary:

| Item | Value |
|---|---:|
| Images | 350 |
| Kept annotations | 34,249 |
| Epochs | 3 |
| Best validation loss | 1.4288 |

Functional validation artifacts:

```text
validation/coco_eval_round3_human350_smoke_valid1
validation/coco_eval_round3_human350_compare_valid3
```

Important: this package is ready for Fiji/BubMask testing, but it remains
provisional for scientific reporting until fuller held-out validation and
visual overlay review are complete.
