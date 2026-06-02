param(
    [string]$FijiPath = "",
    [string]$ProjectPath = "",
    [string]$ReleaseTag = "v0.1.0",
    [switch]$SkipPython,
    [switch]$SkipModels
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoOwner = "armansyahpm"
$RepoName = "bubmask-fiji"
$ReleaseBaseUrl = "https://github.com/$RepoOwner/$RepoName/releases/download/$ReleaseTag"

$ModelAssets = @(
    @{
        Package = "bubmask-maskrcnn-unsw-round2-v1"
        Asset = "bubmask-maskrcnn-unsw-round2-v1_mask_rcnn_bubble.h5"
        Sha256 = "1F2DBD4F042286CA8208896C2579E364846C5F3448B22AD471E13A8E08714ADC"
    },
    @{
        Package = "bubmask-maskrcnn-unsw-round3-v1"
        Asset = "bubmask-maskrcnn-unsw-round3-v1_mask_rcnn_bubble.h5"
        Sha256 = "4E8F251C0AF2F9025D37A83461A67090F79AF2B0A2B69574EE9B3FD6C0D51BE5"
    }
)

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "== $Message ==" -ForegroundColor Cyan
}

function Resolve-ProjectPath {
    if ([string]::IsNullOrWhiteSpace($ProjectPath)) {
        if ([string]::IsNullOrWhiteSpace($PSScriptRoot)) {
            return (Get-Location).Path
        }
        return (Resolve-Path -LiteralPath $PSScriptRoot).Path
    }
    return (Resolve-Path -LiteralPath $ProjectPath).Path
}

function Assert-ProjectRoot {
    param([string]$Root)
    $scriptFile = Join-Path $Root "src\main\fiji\BubMask.py"
    $workerFile = Join-Path $Root "src\main\python\bubmask_worker.py"
    if (-not (Test-Path -LiteralPath $scriptFile)) {
        throw "Cannot find Fiji script: $scriptFile"
    }
    if (-not (Test-Path -LiteralPath $workerFile)) {
        throw "Cannot find Python worker: $workerFile"
    }
}

function Resolve-FijiPath {
    param([string]$InputPath)
    if ([string]::IsNullOrWhiteSpace($InputPath)) {
        $InputPath = Read-Host "Enter your Fiji installation folder, e.g. C:\Users\you\Downloads\fiji-latest-win64-jdk\Fiji"
    }
    $resolved = (Resolve-Path -LiteralPath $InputPath).Path
    $scriptsDir = Join-Path $resolved "scripts"
    if (-not (Test-Path -LiteralPath $scriptsDir)) {
        New-Item -ItemType Directory -Path $scriptsDir -Force | Out-Null
    }
    return $resolved
}

function Install-FijiScript {
    param([string]$Root, [string]$FijiRoot)
    $source = Join-Path $Root "src\main\fiji\BubMask.py"
    $targetDir = Join-Path $FijiRoot "scripts\Plugins\UNSW"
    $target = Join-Path $targetDir "BubMask.py"
    New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $target -Force
    Write-Host "Installed Fiji script:"
    Write-Host $target
}

function Set-BubMaskEnvironment {
    param([string]$Root)
    [Environment]::SetEnvironmentVariable("BUBMASK_FIJI_PROJECT", $Root, "User")
    Write-Host "Set user environment variable:"
    Write-Host "BUBMASK_FIJI_PROJECT=$Root"
    Write-Host "Restart Fiji after installation so it sees the updated environment."
}

function Invoke-CommandChecked {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )
    Write-Host "> $FilePath $($Arguments -join ' ')"
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE`: $FilePath $($Arguments -join ' ')"
    }
}

function Get-Python310Command {
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($null -ne $pyLauncher) {
        & $pyLauncher.Source -3.10 --version | Out-Null
        if ($LASTEXITCODE -eq 0) {
            return @{
                FilePath = $pyLauncher.Source
                Prefix = @("-3.10")
            }
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($null -ne $python) {
        $versionOutput = & $python.Source -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        if ($LASTEXITCODE -eq 0 -and "$versionOutput".Trim() -eq "3.10") {
            return @{
                FilePath = $python.Source
                Prefix = @()
            }
        }
    }

    throw @"
BubMask-Fiji requires Python 3.10 for the current TensorFlow/Keras Mask R-CNN stack.

Install Python 3.10, then rerun this installer.
Python 3.11/3.12 are not supported by this release.
"@
}

function Ensure-PythonEnvironment {
    param([string]$Root)
    $venvPython = Join-Path $Root ".venv-bubmask\Scripts\python.exe"
    $requirements = Join-Path $Root "src\main\python\requirements-bubmask-lock.txt"

    if (-not (Test-Path -LiteralPath $venvPython)) {
        $python310 = Get-Python310Command
        Invoke-CommandChecked -FilePath $python310.FilePath -Arguments ($python310.Prefix + @("-m", "venv", ".venv-bubmask"))
    }

    $venvVersion = & $venvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    if ($LASTEXITCODE -ne 0 -or "$venvVersion".Trim() -ne "3.10") {
        throw "Existing .venv-bubmask uses Python $venvVersion. Delete .venv-bubmask and rerun installer with Python 3.10."
    }

    Invoke-CommandChecked -FilePath $venvPython -Arguments @("-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel")
    Invoke-CommandChecked -FilePath $venvPython -Arguments @("-m", "pip", "install", "-r", $requirements)
}

function Download-ModelWeights {
    param([string]$Root)
    foreach ($model in $ModelAssets) {
        $packageDir = Join-Path $Root ("models\" + $model.Package)
        $weightsDir = Join-Path $packageDir "weights"
        $target = Join-Path $weightsDir "mask_rcnn_bubble.h5"
        $url = "$ReleaseBaseUrl/$($model.Asset)"

        New-Item -ItemType Directory -Path $weightsDir -Force | Out-Null

        $needsDownload = $true
        if (Test-Path -LiteralPath $target) {
            $existingHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $target).Hash.ToUpperInvariant()
            if ($existingHash -eq $model.Sha256) {
                Write-Host "$($model.Package) weights already present and verified."
                $needsDownload = $false
            } else {
                Write-Host "$($model.Package) weights exist but checksum differs; redownloading."
            }
        }

        if ($needsDownload) {
            Write-Host "Downloading $($model.Package) weights from:"
            Write-Host $url
            Invoke-WebRequest -Uri $url -OutFile $target -UseBasicParsing
        }

        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $target).Hash.ToUpperInvariant()
        if ($hash -ne $model.Sha256) {
            throw "Checksum failed for $target. Expected $($model.Sha256), got $hash"
        }
        Write-Host "Verified $($model.Package): $hash"
    }
}

$ProjectRoot = Resolve-ProjectPath
Assert-ProjectRoot -Root $ProjectRoot

Write-Step "Installing BubMask-Fiji from $ProjectRoot"
$ResolvedFijiPath = Resolve-FijiPath -InputPath $FijiPath
Install-FijiScript -Root $ProjectRoot -FijiRoot $ResolvedFijiPath
Set-BubMaskEnvironment -Root $ProjectRoot

if (-not $SkipPython) {
    Write-Step "Setting up Python environment"
    Push-Location $ProjectRoot
    try {
        Ensure-PythonEnvironment -Root $ProjectRoot
    } finally {
        Pop-Location
    }
} else {
    Write-Host "Skipping Python environment setup."
}

if (-not $SkipModels) {
    Write-Step "Downloading UNSW Round 2 and Round 3 model weights"
    Download-ModelWeights -Root $ProjectRoot
} else {
    Write-Host "Skipping model downloads."
}

Write-Step "Installation complete"
Write-Host "Open Fiji, then run Plugins > UNSW > BubMask."
Write-Host "Default model in the current UI is UNSW Round 3 fine-tune (provisional)."
