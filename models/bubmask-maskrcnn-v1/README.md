# BubMask Mask R-CNN v1 Model Package

This directory packages the trained BubMask model assets for BubMask-Fiji.

The current weights file is expected at:

```text
weights/mask_rcnn_bubble.h5
```

The `.h5` file is ignored by git because it is large. Keep it locally for
development and distribute it through a controlled model package or release
artifact when the deployment strategy is decided.

## Current provenance

- Source copied from local `bubble_analyser` project.
- Original local source path:
  `C:\Users\arman\tor_mere\bubble_analyser\bubble_analyser\weights\mask_rcnn_bubble.h5`
- SHA256:
  `C33BD33D4B97DD54B4B8E6C916B1A5114FC06A88AC4A989EA89ACAF6650E95F3`

## Intended use

Fiji calls the Java plugin command. The Java command calls the Python worker.
The Python worker loads this model package and returns bubble instance masks and
measurements.
