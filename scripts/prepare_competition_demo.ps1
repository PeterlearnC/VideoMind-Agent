[CmdletBinding()]
param([switch]$NonInteractive)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendRoot = Join-Path $ProjectRoot "backend"
$Target = Join-Path $BackendRoot ".env"
$Template = Join-Path $BackendRoot ".env.competition.example"

Write-Host "================================================"
Write-Host "VideoMind-Agent Competition Demo Preparation"
Write-Host "================================================"

if (-not (Test-Path -LiteralPath $Template -PathType Leaf)) {
    Write-Host "[ERROR] Safe Competition Demo template is missing."
    exit 1
}

if (Test-Path -LiteralPath $Target -PathType Leaf) {
    Write-Host "[INFO] backend\.env already exists and was not overwritten."
    Write-Host "       Ensure COMPETITION_DEMO_MODE=true for the preloaded Demo."
} else {
    Copy-Item -LiteralPath $Template -Destination $Target
    Write-Host "[OK] Created backend\.env from the safe Competition Demo template."
    Write-Host "     No DeepSeek API Key was written."
}

Write-Host "[OK] Preparation complete. Run start_videomind.bat."
