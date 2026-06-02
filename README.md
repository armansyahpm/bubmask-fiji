# BubMask Fiji

This project is the dedicated Fiji/ImageJ plugin surface for BubMask, a Mask
R-CNN based microbubble sizing workflow for the UNSW School of Mining and
Mineral Engineering.

The plugin is intentionally outside the Fiji distribution checkout. Fiji should
consume it later as a released artifact or update-site entry, rather than
embedding model/inference code in Fiji's launcher and compatibility layer.

## Current milestone

As of 2026-06-01, the research prototype objective is complete. The currently
tested user workflow is the local Fiji script entry:

```text
Plugins > UNSW > BubMask
```

Installed live script:

```text
C:\Users\arman\Downloads\fiji-latest-win64-jdk\Fiji\scripts\Plugins\UNSW\BubMask.py
```

Source copy in this repository:

```text
src/main/fiji/BubMask.py
```

Current installed/project SHA256:

```text
97DDF43E3A2A2E884962C7099177504E6B56667F6606326910DFB70D3FEC3882
```

The prototype now supports:

- Original BubMask, UNSW Round 2, and UNSW Round 3 model selection.
- Default microscope calibration of `183 px/mm`, editable by the user.
- Mask R-CNN inference through the Python worker.
- Box and mask overlay output.
- A separate Fiji overlay-review image for manual ROI marking.
- Manual bubble addition from current Fiji ROI or ROI Manager.
- Interactive histogram/data analysis with `OK` refresh.
- `BACK`, `NEXT`, `OK`, `CHANGE MODEL`, `FINISH PROCESSING`, and `CANCEL`
  navigation.
- Delayed output-file selection only after `FINISH PROCESSING`.
- Export of histogram PNG/CSV, Excel bubble table, overlay images, instance
  labels, and audit files according to the selected retention package.

Important validation note: the Round 3 model is installed for side-by-side
testing, but held-out validation showed Round 2 was scientifically stronger on
the evaluated validation/test splits. Do not claim Round 3 is more accurate
without additional validation.

## Expected build

```bash
mvn clean package
```

This machine did not expose `mvn` or `java` on PATH when the project was
created, so the first engineer with a configured Java/Maven environment should
run the build and adjust dependency versions if the local Fiji baseline requires
it.

## Suggested Fiji test

1. Download the repository:

```bash
git clone https://github.com/armansyahpm/bubmask-fiji.git
```

or use GitHub `Code > Download ZIP`.

2. Copy the Fiji script:

```text
bubmask-fiji/src/main/fiji/BubMask.py
```

to:

```text
Fiji/scripts/Plugins/UNSW/BubMask.py
```

3. Restart Fiji. On first run, BubMask asks for the downloaded `bubmask-fiji`
   project folder if `BUBMASK_FIJI_PROJECT` has not already been set.

4. Create the local Python environment from the repository root:

```powershell
py -3.10 -m venv .venv-bubmask
.\.venv-bubmask\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv-bubmask\Scripts\python.exe -m pip install -r src\main\python\requirements-bubmask-lock.txt
```

5. Add model weights locally:

```text
models/<model-package>/weights/mask_rcnn_bubble.h5
```

The public GitHub source release contains code and metadata. Large `.h5` model
weights must be distributed separately.

6. Open Fiji from:

```text
C:\Users\arman\Downloads\fiji-latest-win64-jdk\Fiji
```

7. Open a representative TIFF image.
8. Run `Plugins > UNSW > BubMask`.
9. Choose model/calibration settings.
10. Review the overlay image, optionally draw Fiji ROIs for missed bubbles, and
   add them from the review window.
11. Change histogram settings and press `OK` to verify the graph refreshes.
12. Press `FINISH PROCESSING`, then select the output files to keep.

## Production direction

Keep the Mask R-CNN model, Python dependencies, calibration tests, and packaging
logic in this repository. Only add this artifact to Fiji's `pom.xml` once the
plugin has a stable release and the team has chosen a deployment mechanism.

## Repository layout

```text
src/main/fiji/       Current Fiji/Jython research prototype script.
src/main/python/     Python worker, measurement, histogram, and export code.
src/main/java/       Java/SciJava plugin scaffold for future production work.
models/              Versioned model packages and metadata.
docs/                Source-of-truth report, references, plans, and figures.
validation/          Datasets, evaluation outputs, smoke tests, fixtures, logs.
results/             New local Fiji run outputs.
training_runs/       New local model-training outputs.
artifacts/           Local archived generated outputs from development.
```

Large generated artifacts and research data are ignored by git by default.
Model weights are also ignored because the Mask R-CNN `.h5` files are larger
than GitHub's normal source-file limits. Keep them in the local `models/*/weights/`
folders or publish them separately as release assets/model packages.

## Main documents

```text
docs/bubmask-fiji.md   Publication-stage research and development report.
docs/user_guide.md     End-user Fiji workflow guide.
docs/reports/          Validation and UI feature reports.
docs/reference/        Worker contracts and packaging notes.
```

## Real image intake

For BubMask development, keep a small representative TIFF intake set under:

```text
validation/real_tiff_samples/
```

Start with about 10 real microscope images that mineral engineering scientists
expect to process. Prefer 16-bit OME-TIFF or calibrated TIFF where possible.
The image files themselves are ignored by git because they may be large or
research-controlled, but the folder includes a manifest template so every image
has traceable acquisition and calibration metadata.

The first intake set should cover variation in:

- flow rate, pressure, vent geometry, and replicate number;
- sparse and dense bubble fields;
- small and large bubbles;
- overlapping bubbles;
- specular highlights;
- blurred/out-of-focus regions;
- uneven illumination and field-of-view border cases.
