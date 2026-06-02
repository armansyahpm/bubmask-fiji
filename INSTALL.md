# BubMask-Fiji Installation Guide

Release target: `v0.1.0`

This guide installs BubMask-Fiji from the public GitHub repository into a local
Fiji/ImageJ installation. It is designed for Windows users.

Repository:

```text
https://github.com/armansyahpm/bubmask-fiji
```

---

## What Is Included

The public repository includes:

- Fiji/Jython user-interface script;
- Python worker and measurement/export code;
- Java/SciJava scaffold for future production packaging;
- documentation, validation reports, and user guide;
- model metadata for UNSW Round 2 and UNSW Round 3.

The GitHub release assets include:

| Model package | Release asset | Default in UI |
| --- | --- | --- |
| `bubmask-maskrcnn-unsw-round2-v1` | `bubmask-maskrcnn-unsw-round2-v1_mask_rcnn_bubble.h5` | No |
| `bubmask-maskrcnn-unsw-round3-v1` | `bubmask-maskrcnn-unsw-round3-v1_mask_rcnn_bubble.h5` | Yes |

Original BubMask weights are not distributed in this release.

---

## One-Command Installer

1. Download or clone the repository.

```powershell
git clone https://github.com/armansyahpm/bubmask-fiji.git
cd bubmask-fiji
```

2. Run the installer from PowerShell.

```powershell
.\install_bubmask_fiji.ps1 -FijiPath "C:\path\to\Fiji"
```

Example:

```powershell
.\install_bubmask_fiji.ps1 -FijiPath "C:\Users\you\Downloads\fiji-latest-win64-jdk\Fiji"
```

If PowerShell blocks script execution, run this once for the current terminal:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

The installer will:

1. copy `src/main/fiji/BubMask.py` to `Fiji/scripts/Plugins/UNSW/BubMask.py`;
2. set the user environment variable `BUBMASK_FIJI_PROJECT`;
3. create `.venv-bubmask`;
4. install Python requirements;
5. download UNSW Round 2 and UNSW Round 3 model weights from GitHub Releases;
6. verify SHA256 checksums;
7. leave Original BubMask weights absent.

Restart Fiji after the installer completes.

---

## Running BubMask in Fiji

1. Open Fiji.
2. Open a microscope image.
3. Run:

```text
Plugins > UNSW > BubMask
```

The default model is:

```text
UNSW Round 3 fine-tune (provisional)
```

Round 2 remains available for comparison and validation checks.

---

## Manual Installation

If you do not want to use the installer:

1. Copy:

```text
src/main/fiji/BubMask.py
```

to:

```text
Fiji/scripts/Plugins/UNSW/BubMask.py
```

2. Create the Python environment:

```powershell
py -3.10 -m venv .venv-bubmask
.\.venv-bubmask\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv-bubmask\Scripts\python.exe -m pip install -r src\main\python\requirements-bubmask-lock.txt
```

3. Download the UNSW model weights from the `v0.1.0` GitHub release.

4. Place them as:

```text
models/bubmask-maskrcnn-unsw-round2-v1/weights/mask_rcnn_bubble.h5
models/bubmask-maskrcnn-unsw-round3-v1/weights/mask_rcnn_bubble.h5
```

5. Set the environment variable:

```powershell
setx BUBMASK_FIJI_PROJECT "C:\path\to\bubmask-fiji"
```

Restart Fiji after setting the environment variable.

---

## Model Checksums

| Model | SHA256 |
| --- | --- |
| UNSW Round 2 | `1F2DBD4F042286CA8208896C2579E364846C5F3448B22AD471E13A8E08714ADC` |
| UNSW Round 3 | `4E8F251C0AF2F9025D37A83461A67090F79AF2B0A2B69574EE9B3FD6C0D51BE5` |

---

## Scientific Note

The interface defaults to Round 3 because that is the current user-tested Fiji
workflow. Held-out validation in the project documentation showed Round 2 had
stronger mask-agreement metrics on the available labelled validation/test sets.
For publication, report which model was used and do not claim Round 3 is more
accurate unless supported by new validation.
