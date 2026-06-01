$ErrorActionPreference = "Stop"

Set-Location "C:\Users\arman\tor_mere"
$env:PYTHONPATH = "C:\Users\arman\tor_mere\bubmask-fiji\src\main\python"

$stdoutLog = "C:\Users\arman\tor_mere\bubmask-fiji\validation\active_learning_round3\autolabel_round3_stdout.log"
$stderrLog = "C:\Users\arman\tor_mere\bubmask-fiji\validation\active_learning_round3\autolabel_round3_stderr.log"
$runnerLog = "C:\Users\arman\tor_mere\bubmask-fiji\validation\active_learning_round3\autolabel_round3_runner.log"

Add-Content -Path $runnerLog -Value ("===== BubMask Round 3 autolabel start " + (Get-Date).ToString("s") + " =====")

$arguments = @(
  "-m", "bubmask_fiji.validation.autolabel_lab_inventory",
  "--input-root", "C:\Users\arman\tor_mere\bubmask-fiji\validation\real_tiff_samples\with_particle",
  "--input-root", "C:\Users\arman\tor_mere\bubmask-fiji\validation\real_tiff_samples\without_particle",
  "--output-dir", "C:\Users\arman\tor_mere\bubmask-fiji\validation\active_learning_round3\autolabel_predictions",
  "--model-package", "C:\Users\arman\tor_mere\bubmask-fiji\models\bubmask-maskrcnn-unsw-round2-v1",
  "--model-label", "bubmask-maskrcnn-unsw-round2-v1",
  "--confidence-threshold", "0.10",
  "--preprocessing-profile", "raw_model",
  "--quality-gate-mode", "review_only",
  "--px-per-mm", "183"
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
Add-Content -Path $runnerLog -Value ("===== BubMask Round 3 autolabel finished " + (Get-Date).ToString("s") + " exit=" + $exitCode + " =====")
exit $exitCode
