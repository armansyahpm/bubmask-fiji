# Real TIFF Sample Intake

Put a small local set of representative real bubble images here for BubMask-Fiji
development.

Recommended initial size: **around 10 TIFF images**.

These files should represent the images that mineral engineering scientists
will actually process. The images are ignored by git, so this folder can hold
large or access-controlled research data without accidentally committing it.

## Preferred file type

Use this order of preference:

1. 16-bit OME-TIFF with calibration metadata.
2. 16-bit ImageJ TIFF with calibration metadata.
3. Plain TIFF plus explicit pixel-size metadata in the manifest.
4. 8-bit TIFF only if that is the only available camera/export option.

Avoid JPEG for validation or measurement work.

## Minimum starter set

Aim to include:

- 2 sparse bubble images;
- 2 dense bubble images;
- 2 images with overlapping bubbles;
- 1 image with strong specular highlights;
- 1 blurred or low-focus image;
- 1 uneven-illumination image;
- 1 typical "best case" image.

## Required companion metadata

Copy `sample_manifest_template.csv` to a project-specific manifest file and add
one row per image. BubMask-Fiji should eventually refuse calibrated diameter
outputs when pixel size is missing.
