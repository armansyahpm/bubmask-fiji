$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Users\arman\tor_mere\bubmask-fiji"
$Python = Join-Path $ProjectRoot ".venv-bubmask\Scripts\python.exe"
$Dataset = Join-Path $ProjectRoot "validation\phase3_unsw_validation\roboflow_coco_round3_human350_training_clean_fast"
$OutputDir = Join-Path $ProjectRoot "validation\coco_eval_round3_human350_full_valid_test_cached_v2"
$StdoutLog = Join-Path $ProjectRoot "validation\round3_full_valid_test_cached_validation_stdout.log"
$StderrLog = Join-Path $ProjectRoot "validation\round3_full_valid_test_cached_validation_stderr.log"
$RunnerLog = Join-Path $ProjectRoot "validation\round3_full_valid_test_cached_validation_runner.log"
$TranscriptLog = Join-Path $ProjectRoot "validation\round3_full_valid_test_cached_validation_transcript.log"

Set-Location $ProjectRoot
$env:PYTHONPATH = Join-Path $ProjectRoot "src\main\python"

"===== BubMask Round 3 cached full valid/test validation start $(Get-Date -Format o) =====" | Out-File -FilePath $RunnerLog -Encoding utf8
"Python=$Python exists=$(Test-Path $Python)" | Add-Content -Path $RunnerLog -Encoding utf8
"Dataset=$Dataset exists=$(Test-Path $Dataset)" | Add-Content -Path $RunnerLog -Encoding utf8

Start-Transcript -Path $TranscriptLog -Force | Out-Null
try {
  $PreviousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  & $Python -m bubmask_fiji.validation.evaluate_model_packages_on_coco `
    --reuse-model `
    --dataset $Dataset `
    --split valid `
    --split test `
    --model "round2=$ProjectRoot\models\bubmask-maskrcnn-unsw-round2-v1" `
    --model "round3_fiji=C:\Users\arman\Downloads\fiji-latest-win64-jdk\Fiji\models\bubmask-maskrcnn-unsw-round3-v1" `
    --output-dir $OutputDir `
    --confidence-threshold 0.10 `
    --preprocessing-profile raw_model `
    --px-per-mm 183 `
    1> $StdoutLog 2> $StderrLog
  $ErrorActionPreference = $PreviousErrorActionPreference

  $ExitCode = $LASTEXITCODE
  "===== BubMask Round 3 cached full valid/test validation finish $(Get-Date -Format o) exit=$ExitCode =====" | Add-Content -Path $RunnerLog -Encoding utf8
  exit $ExitCode
} catch {
  "ERROR $(Get-Date -Format o): $($_.Exception.GetType().FullName): $($_.Exception.Message)" | Add-Content -Path $RunnerLog -Encoding utf8
  $_ | Out-String | Add-Content -Path $RunnerLog -Encoding utf8
  exit 1
} finally {
  Stop-Transcript | Out-Null
}
