param(
  [switch]$SidecarOnly,
  [switch]$Cuda,
  [switch]$ForcePython
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

$StageArgs = @("scripts/prepare_sidecar_bundle.py")
if ($SidecarOnly) { $StageArgs += "--sidecar-only" }
if ($Cuda) { $StageArgs += "--cuda" }
if ($ForcePython) { $StageArgs += "--force-python" }

Write-Host "[satz-build] Staging sidecar & relocatable Python runtime..."
$PyExe = if (Test-Path "..\sgs\.venv\Scripts\python.exe") { "..\sgs\.venv\Scripts\python.exe" } else { "python" }
& $PyExe @StageArgs
if ($LASTEXITCODE -ne 0) { throw "prepare_sidecar_bundle.py failed ($LASTEXITCODE)" }

$KeyPath = Join-Path $env:USERPROFILE ".tauri\satz.key"
if ((Test-Path $KeyPath) -and -not $env:TAURI_SIGNING_PRIVATE_KEY) {
  $env:TAURI_SIGNING_PRIVATE_KEY = (Get-Content -Raw $KeyPath).Trim()
  if (-not $env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD) {
    $env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = ""
  }
}

Write-Host "[satz-build] Running Tauri release bundle..."
npx --no-install tauri build --config src-tauri/tauri.bundle.conf.json
if ($LASTEXITCODE -ne 0) { throw "tauri build failed ($LASTEXITCODE)" }
Write-Host "[satz-build] Done. Installers are under src-tauri/target/release/bundle/"
