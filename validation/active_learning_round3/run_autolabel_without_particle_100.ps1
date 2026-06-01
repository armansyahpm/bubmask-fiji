$ErrorActionPreference = "Stop"

Set-Location "C:\Users\arman\tor_mere"
$env:PYTHONPATH = "C:\Users\arman\tor_mere\bubmask-fiji\src\main\python"

$round3Dir = "C:\Users\arman\tor_mere\bubmask-fiji\validation\active_learning_round3"
$stdoutLog = Join-Path $round3Dir "autolabel_without_particle_100_stdout.log"
$stderrLog = Join-Path $round3Dir "autolabel_without_particle_100_stderr.log"
$runnerLog = Join-Path $round3Dir "autolabel_without_particle_100_runner.log"

Add-Content -Path $runnerLog -Value ("===== BubMask without-particle 100 autolabel start " + (Get-Date).ToString("s") + " =====")

$arguments = @(
  "-m", "bubmask_fiji.validation.autolabel_lab_inventory",
  "--input-list", "C:\Users\arman\tor_mere\bubmask-fiji\validation\active_learning_round3\without_particle_100_input_paths.txt",
  "--output-dir", "C:\Users\arman\tor_mere\bubmask-fiji\validation\active_learning_round3\autolabel_predictions_without_particle_100",
  "--model-package", "C:\Users\arman\tor_mere\bubmask-fiji\models\bubmask-maskrcnn-unsw-round2-v1",
  "--model-label", "bubmask-maskrcnn-unsw-round2-v1",
  "--confidence-threshold", "0.10",
  "--preprocessing-profile", "raw_model",
  "--quality-gate-mode", "review_only",
  "--px-per-mm", "183",
  "--manifest-every", "1"
)

Remove-Item -LiteralPath $stdoutLog -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $stderrLog -Force -ErrorAction SilentlyContinue

$process = Start-Process `
  -FilePath "C:\Users\arman\tor_mere\bubmask-fiji\.venv-bubmask\Scripts\python.exe" `
  -ArgumentList $arguments `
  -WorkingDirectory "C:\Users\arman\tor_mere" `
  -RedirectStandardOutput $stdoutLog `
  -RedirectStandardError $stderrLog `
  -WindowStyle Hidden `
  -PassThru `
  -Wait

$exitCode = $process.ExitCode
Add-Content -Path $runnerLog -Value ("===== BubMask without-particle 100 autolabel finished " + (Get-Date).ToString("s") + " exit=" + $exitCode + " =====")
exit $exitCode
