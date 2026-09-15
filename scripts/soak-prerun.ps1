# Phase-1 soak pre-run: batch inbox PDFs, gate verify, then zero-provider re-run.
#   powershell -ExecutionPolicy Bypass -File scripts\soak-prerun.ps1

$ErrorActionPreference = "Stop"

# --- configure these ---
$Repo = "D:\Repos\Solivagus"
$BatchDir = Join-Path $Repo "soak-inbox\prerun"
# Dedicated workspace avoids mixing with stale .solivagus/state.db in the repo root.
$Workspace = Join-Path $Repo "soak-workspace\prerun"
$EnvFile = Join-Path $Repo ".env"
$Profile = "conservative"
$OcrDevice = $env:SOLIVAGUS_OCR_DEVICE
if (-not $OcrDevice) { $OcrDevice = "gpu:0" }
# -----------------------

if (-not (Test-Path $BatchDir)) {
  Write-Error "BatchDir not found: $BatchDir"
}
New-Item -ItemType Directory -Force -Path $Workspace | Out-Null

Set-Location $Repo
$env:PYTHONIOENCODING = "utf-8"
$env:SOLIVAGUS_BATCH_DIR = $BatchDir
$env:SOLIVAGUS_WORKSPACE = $Workspace
$env:SOLIVAGUS_OCR_DEVICE = $OcrDevice
if (Test-Path $EnvFile) {
  $env:SOLIVAGUS_ENV_FILE = $EnvFile
}

$Solivagus = Join-Path $Repo ".venv\Scripts\solivagus.exe"
if (-not (Test-Path $Solivagus)) { $Solivagus = "solivagus" }
$Python = Join-Path $Repo ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }

$Pdfs = @(Get-ChildItem -Path $BatchDir -Filter *.pdf -File | Sort-Object Name)
if ($Pdfs.Count -lt 1) {
  Write-Error "Need at least 1 PDF in $BatchDir (found $($Pdfs.Count))."
}
Write-Host "Pre-run PDFs ($($Pdfs.Count)):" -ForegroundColor Cyan
$Pdfs | ForEach-Object { Write-Host "  - $($_.Name)" }

$Reports = Join-Path $Workspace ".solivagus\soak"
New-Item -ItemType Directory -Force -Path $Reports | Out-Null
$Snap = Join-Path $Reports "prerun-attempts.json"
$Verify1 = Join-Path $Reports "prerun-verify-1.json"
$Verify2 = Join-Path $Reports "prerun-verify-2.json"

Write-Host "== Phase 1a: batch pre-run ($Profile) ==" -ForegroundColor Cyan
& $Solivagus batch $BatchDir `
  --profile $Profile `
  --continue-on-error `
  --prevent-sleep `
  --recursive
if ($LASTEXITCODE -ne 0) {
  Write-Warning "batch exited $LASTEXITCODE — continuing to verify for partial diagnosis"
}

Write-Host "== Phase 1b: soak_verify + attempt snapshot ==" -ForegroundColor Cyan
& $Python (Join-Path $Repo "scripts\soak_verify.py") `
  --workspace $Workspace `
  --snapshot-attempts $Snap
& $Python (Join-Path $Repo "scripts\soak_verify.py") `
  --workspace $Workspace `
  --json-out $Verify1
$code1 = $LASTEXITCODE

Write-Host "== Phase 1c: re-run same batch (expect provider delta 0) ==" -ForegroundColor Cyan
& $Solivagus batch $BatchDir `
  --profile $Profile `
  --continue-on-error `
  --prevent-sleep `
  --recursive

& $Python (Join-Path $Repo "scripts\soak_verify.py") `
  --workspace $Workspace `
  --compare-attempts $Snap `
  --json-out $Verify2
$code2 = $LASTEXITCODE

& $Solivagus report

Write-Host ""
Write-Host "Pre-run verify exit: $code1 ; re-run/idempotency exit: $code2"
Write-Host "Reports under: $Reports"
if ($code1 -ne 0 -or $code2 -ne 0) { exit 1 }
exit 0
