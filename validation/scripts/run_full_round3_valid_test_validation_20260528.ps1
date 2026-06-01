$ErrorActionPreference = "Stop"

Set-Location "C:\Users\arman\tor_mere\bubmask-fiji"
$env:PYTHONPATH = "C:\Users\arman\tor_mere\bubmask-fiji\src\main\python"

$validationRoot = "C:\Users\arman\tor_mere\bubmask-fiji\validation"
$stdoutLog = Join-Path $validationRoot "round3_full_valid_test_validation_stdout.log"
$stderrLog = Join-Path $validationRoot "round3_full_valid_test_validation_stderr.log"
$runnerLog = Join-Path $validationRoot "round3_full_valid_test_validation_runner.log"

Add-Content -Path $runnerLog -Value ("===== BubMask Round 3 full valid/test validation start " + (Get-Date).ToString("s") + " =====")

$arguments = @(
  "-m", "bubmask_fiji.validation.evaluate_model_packages_on_coco",
  "--dataset", "validation\phase3_unsw_validation\roboflow_coco_round3_human350_training_clean_fast",
  "--split", "valid",
  "--split", "test",
  "--model", "round2=models\bubmask-maskrcnn-unsw-round2-v1",
  "--model", "round3_fiji=C:\Users\arman\Downloads\fiji-latest-win64-jdk\Fiji\models\bubmask-maskrcnn-unsw-round3-v1",
  "--output-dir", "validation\coco_eval_round3_human350_full_valid_test",
  "--confidence-threshold", "0.10",
  "--preprocessing-profile", "raw_model",
  "--px-per-mm", "183"
)

Remove-Item -LiteralPath $stdoutLog -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $stderrLog -Force -ErrorAction SilentlyContinue

$process = Start-Process `
  -FilePath "C:\Users\arman\tor_mere\bubmask-fiji\.venv-bubmask\Scripts\python.exe" `
  -ArgumentList $arguments `
  -WorkingDirectory "C:\Users\arman\tor_mere\bubmask-fiji" `
  -RedirectStandardOutput $stdoutLog `
  -RedirectStandardError $stderrLog `
  -WindowStyle Hidden `
  -PassThru `
  -Wait

$exitCode = $process.ExitCode
Add-Content -Path $runnerLog -Value ("===== BubMask Round 3 full valid/test validation finished " + (Get-Date).ToString("s") + " exit=" + $exitCode + " =====")
exit $exitCode
