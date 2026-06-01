# BubMask-Fiji User Interface and Feature Explanation Report

Date: 2026-05-12  
Project: BubMask-Fiji-UNSW  
Audience: software engineers, mineral engineering scientists, and supervisors

---

## 1. Why This Report Exists

The project decision is whether BubMask should become:

1. a standalone desktop application, or
2. a Fiji/ImageJ plugin.

After studying DeepImageJ, the stronger direction for BubMask-Fiji is to build a
**Fiji plugin with a domain-specific user interface**. The goal is not to clone
DeepImageJ. The goal is to learn from its architecture: it uses Fiji/ImageJ as
the scientist-facing environment, while hiding the deep-learning runtime behind
plugin commands, model packages, and reproducible model metadata.

For BubMask-Fiji, the user should experience one clear scientific workflow:

```text
Open image in Fiji
  -> launch BubMask
  -> confirm calibration and field-of-view
  -> run model
  -> inspect masks
  -> export bubble measurements and histogram
```

---

## 2. How DeepImageJ Connects to Fiji/ImageJ

DeepImageJ is best understood as a **plugin plus supporting layers**, not merely
one button inside Fiji.

The public DeepImageJ site describes it as a plugin that allows pre-trained
neural networks to be used in ImageJ and Fiji without deep-learning or
programming expertise. DeepImageJ 3.0 also connects Fiji with the BioImage Model
Zoo, supports multiple deep-learning frameworks through JDLL, and uses ImgLib2
to handle larger images.

The DeepImageJ website describes four modules:

- **DeepImageJ Run**: applies a neural network to an input image;
- **DeepImageJ Install Model**: installs compatible models from the BioImage
  Model Zoo, URL, or local path;
- **DeepImageJ Validate**: compares model output with ground truth;
- **DeepImageJ Releases**: release/distribution channel.

That means the architecture is layered:

```text
User
 |
 v
Fiji/ImageJ GUI
menus, active image, overlays, ResultsTable, macro recorder
 |
 v
DeepImageJ plugin commands
Run model, install model, validate model
 |
 v
Model management layer
models folder, BioImage Model Zoo model package, metadata
 |
 v
Runtime bridge
JDLL / TensorFlow / PyTorch / ONNX / framework-specific engines
 |
 v
Image processing layer
ImgLib2/ImageJ image objects, tiling, tensor conversion
 |
 v
Model output
output images, masks, probability maps, validation outputs
```

So yes, DeepImageJ is a plugin, but functionally it behaves like a small
platform inside Fiji.

---

## 3. What This Means for BubMask-Fiji

BubMask-Fiji should also be layered, but narrower and more domain-specific.

```text
Mineral engineering scientist
 |
 v
Fiji/ImageJ
open image, calibration, ROI tools, overlays, ResultsTable
 |
 v
BubMask-Fiji plugin
Plugins > UNSW > BubMask Bubble Analyzer
 |
 v
Preflight layer
calibration check, field-of-view check, image quality check
 |
 v
Preprocessing layer
FOV masking, optional background correction, model normalization
 |
 v
Inference layer
Python worker + Matterport Mask R-CNN + mask_rcnn_bubble.h5
 |
 v
Postprocessing layer
instance masks, calibrated diameters, area, centroid, confidence
 |
 v
Output layer
overlay, ResultsTable, histogram, CSV, JSON, masks, audit report
```

The important design principle is:

> The scientist should operate inside Fiji, but the engineering complexity
> should live behind the plugin boundary.

---

## 4. Plugin vs Standalone Decision

### 4.1 Option A: Fiji/ImageJ Plugin

The plugin approach means BubMask is installed into Fiji and appears in the
Fiji menu system.

```text
Fiji
  Plugins
    UNSW
      BubMask Bubble Analyzer
```

The plugin uses Fiji's existing image handling, calibration, ROI, overlay,
ResultsTable, macro, and batch-processing ecosystem.

### 4.2 Option B: Standalone Application

The standalone approach means building a separate desktop application with its
own image viewer, calibration tools, batch processing, and export system.

This can give full UI control, but it also means rebuilding a lot of what
Fiji/ImageJ already provides.

---

## 5. SWOT Analysis

### 5.1 Fiji Plugin Strategy

| Category | Analysis |
|---|---|
| Strengths | Fiji already has a large scientific imaging user base; users know how to open images, calibrate scale, draw ROIs, inspect overlays, and export ResultsTables. Plugin distribution can use Fiji update sites or jar deployment. BubMask can focus on bubble-specific intelligence instead of rebuilding an image-analysis platform. |
| Weaknesses | UI must respect Fiji/ImageJ conventions. Advanced custom UI is harder than in a standalone app. Python/TensorFlow packaging inside Fiji requires careful environment management. Fiji installations differ between labs and machines. |
| Opportunities | BubMask can become a reusable academic tool for mineral engineering labs. It can interoperate with other Fiji tools, macros, batch workflows, Bio-Formats, ROIs, and measurement tables. It can later learn from DeepImageJ/BioImage.IO model packaging. |
| Threats | Dependency conflicts may frustrate non-programmers. If installation is not simple, users may abandon the plugin. If the model is too domain-specific, users may misuse it on unsupported images and trust bad histograms. |

### 5.2 Standalone Application Strategy

| Category | Analysis |
|---|---|
| Strengths | Full control over the UI, model runtime, installer, environment, and workflow. Easier to design a polished single-purpose bubble-analysis interface. Python model integration may be simpler because the whole application can be Python-first. |
| Weaknesses | Requires building image viewer, calibration, ROI, overlay, measurement table, batch processing, export, and file-format handling. Fewer Fiji users will immediately adopt it. More long-term maintenance burden. |
| Opportunities | Could become a lab-specific production tool with a very clean user experience. Easier to bundle model/runtime into a single installer if designed carefully. |
| Threats | Reinventing Fiji/ImageJ features may consume the project. Scientific users may distrust or avoid a new platform. Bio-Formats, TIFF metadata, scale calibration, and image display edge cases can become major work. |

### 5.3 Recommendation

Build BubMask as a **Fiji plugin first**.

Reasons:

1. The target user already benefits from Fiji's image-analysis ecosystem.
2. BubMask's novelty is bubble segmentation and sizing, not general image
   viewing.
3. DeepImageJ proves that deep-learning workflows can be productized inside
   Fiji.
4. Fiji-native outputs such as overlays, ROIs, ResultsTable, CSV, and macros are
   valuable for scientists.
5. A standalone application can still be considered later if installation or
   runtime packaging becomes impossible inside Fiji.

---

## 6. Proposed BubMask-Fiji Menu Structure

```text
Plugins
  UNSW
    BubMask Bubble Analyzer...
    BubMask Batch Process...
    BubMask Model Manager...
    BubMask Validate Dataset...
    BubMask Help / About...
```

### Command roles

| Menu item | Purpose |
|---|---|
| BubMask Bubble Analyzer | Main interactive workflow for the active image. |
| BubMask Batch Process | Folder/manifest-driven processing for experiments. |
| BubMask Model Manager | Select, install, validate, or update model package. |
| BubMask Validate Dataset | Compare predictions against hand masks/expected measurements. |
| BubMask Help / About | Show version, citation, model details, and documentation links. |

---

## 7. Main User Interface Mockup

The main interface should be a compact dialog or panel, not a landing page.
Scientists should be able to scan it quickly and run the analysis.

```text
+--------------------------------------------------------------------------+
| UNSW BubMask Bubble Analyzer                                      [?]    |
+--------------------------------------------------------------------------+
| Input Image                                                              |
|  Active image: bubble_3atm_4vent_1p5mm_0p5lpm.tif                        |
|  Size: 2048 x 2048 px     Type: 16-bit TIFF     Slices: 1                |
|  Calibration: 2.10 um/px  [Change...]                                    |
|                                                                          |
| Field of View                                                            |
|  (x) Auto-detect circular microscope field                               |
|  ( ) Use current Fiji ROI                                                |
|  [Preview FOV]     Valid area: 63.0%     Border bubbles: flag            |
|                                                                          |
| Model                                                                    |
|  Model: BubMask Mask R-CNN v1.0     Status: Ready                        |
|  Runtime: Python/TensorFlow CPU/GPU     [Model Manager...]               |
|                                                                          |
| Detection Settings                                                       |
|  Confidence threshold: [-----|------] 0.50                               |
|  Minimum diameter:      [  ] um                                           |
|  Maximum diameter:      [  ] um                                           |
|  Background correction: [x] Enabled                                      |
|  Highlight robustness:  [x] Flag saturated cores                         |
|                                                                          |
| Outputs                                                                  |
|  [x] Overlay masks on image                                               |
|  [x] ResultsTable                                                        |
|  [x] Diameter histogram                                                   |
|  [x] CSV measurements                                                     |
|  [x] JSON audit file                                                      |
|  [ ] Save binary/label masks                                              |
|                                                                          |
| Quality Precheck                                                         |
|  Calibration: OK        FOV: OK        Saturation: Warning                |
|  Illumination: Warning  Focus: OK      Model package: OK                 |
|                                                                          |
|                         [Run BubMask] [Batch...] [Cancel]                |
+--------------------------------------------------------------------------+
```

---

## 8. Results View Mockup

After inference, the user should get ImageJ-native outputs plus a concise
summary panel.

```text
+--------------------------------------------------------------------------+
| BubMask Results: bubble_3atm_4vent_1p5mm_0p5lpm.tif                      |
+--------------------------------------------------------------------------+
| Summary                                                                  |
|  Detected bubbles: 384                                                    |
|  Accepted bubbles: 361                                                    |
|  Rejected/flagged: 23                                                     |
|  Mean equivalent diameter: 0.82 mm                                        |
|  Median equivalent diameter: 0.74 mm                                      |
|  Valid FOV area: 63.0%                                                    |
|                                                                          |
| Quality Flags                                                            |
|  - 12 bubbles touch field border                                          |
|  - 8 bubbles contain saturated highlights                                 |
|  - illumination correction applied                                        |
|                                                                          |
| Outputs created                                                          |
|  [Open ResultsTable] [Open Histogram] [Save Package] [View JSON]          |
+--------------------------------------------------------------------------+
```

Fiji should also show:

- the original image with colored instance-mask overlays;
- optional label mask image;
- ResultsTable with one row per bubble;
- histogram window or saved histogram plot.

---

## 9. Feature Explanation

| Feature | User value | Engineering requirement |
|---|---|---|
| Active image detection | User opens image as usual in Fiji. | Read active `ImagePlus`; reject missing image. |
| Calibration check | Prevents invalid physical diameters. | Read `ImagePlus.getCalibration()`; warn/block missing pixel size. |
| FOV detection | Excludes black circular microscope border. | Compute FOV mask or accept current Fiji ROI. |
| Model manager | Avoids hard-coded weight paths. | Store model package path, version, hash, and runtime config. |
| Confidence threshold | Lets user tune detection strictness. | Pass threshold to Python worker and record in JSON. |
| Diameter filters | Removes irrelevant detections. | Apply calibrated min/max filters after inference. |
| Background correction | Handles uneven illumination. | Deterministic preprocessing profile recorded in JSON. |
| Highlight flagging | Prevents bright cores from confusing measurement trust. | Detect saturated regions inside masks and flag bubbles. |
| Overlay masks | Lets scientists visually inspect segmentation. | Create ImageJ overlay/ROI or label image. |
| ResultsTable | Familiar Fiji measurement output. | One row per bubble with calibrated measurements. |
| Histogram | Main scientific output for bubble size distribution. | Bin equivalent diameter using calibrated unit. |
| CSV export | Supports Excel, MATLAB, R, Python. | Save per-bubble table and summary table. |
| JSON audit | Supports reproducibility and engineering debugging. | Save input metadata, model version, params, warnings. |
| Batch mode | Processes experiment folders. | Manifest or folder runner with consistent settings. |
| Validation mode | Quantifies model reliability. | Compare predictions to hand masks and expected diameters. |

---

## 10. Planned ResultsTable Columns

```text
bubble_id
image_id
score
area_px
area_calibrated
equivalent_diameter_px
equivalent_diameter_calibrated
centroid_x_px
centroid_y_px
bbox_x
bbox_y
bbox_width
bbox_height
touches_fov_border
contains_saturated_highlight
accepted
rejection_reason
model_name
model_version
model_hash
preprocessing_profile
pixel_width
pixel_height
unit
```

---

## 11. Batch Workflow Mockup

```text
+--------------------------------------------------------------------------+
| UNSW BubMask Batch Process                                               |
+--------------------------------------------------------------------------+
| Input                                                                    |
|  Folder: validation/real_tiff_samples/              [Browse...]          |
|  Manifest: sample_manifest.csv                      [Browse...]          |
|                                                                          |
| Settings                                                                 |
|  Model: BubMask Mask R-CNN v1.0                                          |
|  Use same detection settings as current analyzer preset: [Default v1]    |
|                                                                          |
| Outputs                                                                  |
|  Output folder: artifacts/results_archive_20260601/bubmask_run_2026_05_12       [Browse...]         |
|  [x] Per-image CSV                                                        |
|  [x] Combined CSV                                                         |
|  [x] Per-image overlays                                                   |
|  [x] Histograms                                                           |
|  [x] JSON audit files                                                     |
|                                                                          |
| Run                                                                      |
|  Progress: 3 / 10 images                                                  |
|  Current: unsw_bubble_3atm_4vent_1p5mm_0p5lpm_rep03.tif                  |
|                                                                          |
|                     [Start] [Pause] [Open Output Folder] [Cancel]        |
+--------------------------------------------------------------------------+
```

---

## 12. Validation Workflow Mockup

```text
+--------------------------------------------------------------------------+
| UNSW BubMask Validate Dataset                                            |
+--------------------------------------------------------------------------+
| Dataset manifest: validation/manifest.json            [Browse...]        |
| Model: BubMask Mask R-CNN v1.0                                           |
|                                                                          |
| Checks                                                                   |
|  [x] Mask overlap / IoU                                                   |
|  [x] Equivalent diameter error                                            |
|  [x] False positives and missed bubbles                                   |
|  [x] Border and highlight failure cases                                   |
|                                                                          |
| Acceptance                                                               |
|  Diameter relative error max: 5%                                          |
|  Area relative error max: 10%                                             |
|  Minimum confidence: 0.50                                                 |
|                                                                          |
|                         [Run Validation] [Export Report] [Cancel]        |
+--------------------------------------------------------------------------+
```

---

## 13. Implementation Priorities

### P0: First useful plugin

- active image reader;
- calibration check;
- temporary image export;
- Python worker call;
- real model path configuration;
- ResultsTable output;
- overlay output.

### P1: Scientist-ready analysis

- field-of-view detection/ROI selection;
- diameter histogram;
- CSV and JSON export;
- highlight and border flags;
- batch mode.

### P2: Research-grade validation

- real TIFF intake set;
- hand masks;
- expected measurement tolerances;
- validation report;
- model-card and citation support.

### P3: Distribution

- local lab install package;
- Fiji update site;
- model package manager;
- environment installer/checker.

---

## 14. Architecture Decision

The recommended architecture is:

```text
BubMask-Fiji = Fiji plugin + managed model/runtime layer
```

Do not build the first version as a standalone application unless Fiji runtime
packaging becomes impossible. A plugin gives the project a better scientific
starting point because Fiji already provides the image-analysis environment
that mineral engineering scientists need.

The standalone path should remain a fallback, not the main route.

---

## 15. References

1. DeepImageJ website: https://deepimagej.github.io/
2. DeepImageJ About page: https://deepimagej.github.io/about.html
3. DeepImageJ plugin source repository: https://github.com/deepimagej/deepimagej-plugin
4. DeepImageJ IJ2 plugin release notes and installation notes: https://github.com/deepimagej/deepImagej-ij2-plugin
5. BioImage Model Zoo specification repository: https://github.com/bioimage-io/spec-bioimage-io
