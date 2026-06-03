# BubMask-Fiji Installation Guide

Release target: `v0.1.0`

This guide installs BubMask-Fiji from the public GitHub repository into a local
Fiji/ImageJ installation. It is designed for Windows users.

Important Python requirement: this release requires **Python 3.10**. Python
3.11/3.12 are not supported by the current TensorFlow/Keras Mask R-CNN
dependency stack.

It is fine if a PC already has Python 3.11, 3.12, or newer installed. Do not
remove them. Install Python 3.10 side-by-side; BubMask-Fiji creates its own
`.venv-bubmask` virtual environment using Python 3.10.

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

If Python 3.10 is not available, the installer stops with a clear error message.

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

## Troubleshooting and FAQ

### Installer says Python 3.10 is not available

This is the most common first-time setup issue. BubMask-Fiji requires Python
3.10 for the current TensorFlow/Keras Mask R-CNN dependency stack. Python 3.11,
3.12, or newer can stay installed, but Python 3.10 must also be installed
side-by-side.

Check installed Python versions:

```powershell
py --list
```

If Python 3.10 is missing, install it:

```powershell
winget install Python.Python.3.10
```

Then rerun the BubMask-Fiji installer from the repository folder:

```powershell
.\install_bubmask_fiji.ps1 -FijiPath "C:\path\to\Fiji"
```

Expected version check after installation:

```powershell
py -3.10 --version
```

### I already have Python 3.12. Should I remove it?

No. Do not remove newer Python versions. BubMask-Fiji uses a private virtual
environment named `.venv-bubmask`, created specifically from Python 3.10. Other
Python versions on the same PC do not prevent BubMask-Fiji from working.

### BubMask does not appear under Plugins > UNSW

Check that the script was copied into the Fiji installation you are actually
launching:

```text
Fiji/scripts/Plugins/UNSW/BubMask.py
```

If the computer has multiple Fiji folders, this is easy to mix up. For example,
installing into a Fiji folder under `C:\Users\you\Downloads\...` and launching a
different Fiji folder under `D:\Downloads\...` will make the command appear
missing. Rerun the installer with the exact Fiji folder you intend to open, then
restart Fiji.

You can also use Fiji Quick Search and type:

```text
bub
```

### Fiji opens BubMask, but the project folder cannot be found

The installer sets the user environment variable:

```text
BUBMASK_FIJI_PROJECT
```

On Windows, changes made with `setx` are visible only to new terminals and newly
started applications. Close Fiji completely and open it again. If BubMask still
asks for a folder, select the downloaded `bubmask-fiji` project folder manually.
Fiji will save that selection for later runs.

Advanced users can set the variable in the current PowerShell session before
launching Fiji:

```powershell
$env:BUBMASK_FIJI_PROJECT = "C:\path\to\bubmask-fiji"
Start-Process "C:\path\to\Fiji\fiji-windows-x64.exe"
```

### The model weights are missing

The installer should download and verify the UNSW Round 2 and UNSW Round 3
weights automatically. If installing manually, place the files exactly here:

```text
models/bubmask-maskrcnn-unsw-round2-v1/weights/mask_rcnn_bubble.h5
models/bubmask-maskrcnn-unsw-round3-v1/weights/mask_rcnn_bubble.h5
```

The public release does not distribute Original BubMask weights. They are not
required for the public UNSW Round 2/Round 3 workflow.

### Which model should I choose?

The current Fiji interface defaults to:

```text
UNSW Round 3 fine-tune (provisional)
```

Round 2 is also installed for comparison. The project validation report found
Round 2 scientifically stronger on the available held-out labelled validation
and test images, while Round 3 remains the current user-tested UI default. For
scientific reporting, always record which model package was used.

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
