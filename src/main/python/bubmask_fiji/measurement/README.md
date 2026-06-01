# Measurement Layer

Responsible for converting instance masks into bubble area, equivalent diameter,
centroid, border flags, and calibrated units.

Current implemented helper:

```text
measurements.py
```

It converts each detected bubble into:

- actual mask area in pixels;
- calibrated area when `pixel_width` and `pixel_height` are known;
- equivalent diameter in pixels and calibrated units;
- centroid;
- bounding box;
- quality flags for border contact, saturated highlights, and low confidence.

This layer should stay independent of Fiji UI code so the same measurements can
be used by the script prototype, Java/SciJava command, batch runner, and
validation tools.
