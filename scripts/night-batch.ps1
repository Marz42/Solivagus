# Overnight Solivagus batch (edit paths before use)
$ErrorActionPreference = "Stop"

# --- configure these ---
$Repo = "D:\Repos\Solivagus"
$BatchDir = "E:\papers\inbox"   # REQUIRED: overnight PDF folder
$Workspace = Join-Path $Repo "soak-workspace\overnight"  # dedicated; avoid repo-root stale state
$EnvFile = Join-Path $Repo ".env"
$Profile = "balanced"
# -----------------------

Set-Location $Repo
$env:SOLIVAGUS_BATCH_DIR = $BatchDir
$env:SOLIVAGUS_WORKSPACE = $Workspace
if (Test-Path $EnvFile) {
  $env:SOLIVAGUS_ENV_FILE = $EnvFile
}

# Prefer venv solivagus if present
$Solivagus = Join-Path $Repo ".venv\Scripts\solivagus.exe"
if (-not (Test-Path $Solivagus)) {
  $Solivagus = "solivagus"
}

& $Solivagus batch $BatchDir `
  --profile $Profile `
  --continue-on-error `
  --prevent-sleep `
  --recursive

$code = $LASTEXITCODE
& $Solivagus report
exit $code
