# Preprocessing Layer

Responsible for field-of-view masking, grayscale conversion, optional
background correction, and deterministic normalization before model inference.

Implemented module:

- `denoise.py`
- `synthetic_background.py`

Supported profiles:

| Profile | Purpose |
|---|---|
| `raw_model` | Preserve the original image as the scientific baseline. |
| `fov_flatfield_model` | Detect valid field-of-view and correct uneven illumination. |
| `conservative_denoise_model` | Add small median/Gaussian denoising after flat-field correction. |
| `classical_diagnostic` | Add CLAHE for threshold/debug diagnostics. |

Synthetic background generation:

`synthetic_background.py` creates a development-only background candidate from
a bubble image when a true captured background image is unavailable. It removes
dark bubble-like artifacts and saturated highlights by masking and inpainting,
then writes background PNG/TIFF files while preserving the camera field frame.

A true background image captured under the same lighting, microscope, and
camera settings remains the preferred scientific input for final measurements.
