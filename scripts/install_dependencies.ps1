[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendRoot = Join-Path $ProjectRoot "backend"
$FrontendRoot = Join-Path $ProjectRoot "frontend"
$VenvPython = Join-Path $BackendRoot "venv\Scripts\python.exe"

function Resolve-SystemPython {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($null -ne $python) {
        try {
            & $python.Source --version *> $null
            if ($LASTEXITCODE -eq 0) {
                return @{ FilePath = $python.Source; PrefixArguments = @() }
            }
        } catch { }
    }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($null -ne $py) {
        try {
            & $py.Source -3.11 -c "import sys; assert sys.version_info[:2] == (3, 11)" 2>$null
            if ($LASTEXITCODE -eq 0) {
                return @{ FilePath = $py.Source; PrefixArguments = @("-3.11") }
            }
        } catch { }
    }
    return $null
}

Write-Host "================================================"
Write-Host "VideoMind-Agent Dependency Helper"
Write-Host "================================================"

if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
    $python = Resolve-SystemPython
    if ($null -eq $python) {
        Write-Host "[ERROR] Python not found. Install Python 3.11 first."
        exit 1
    }
    $prefixArguments = @($python.PrefixArguments)
    & $python.FilePath @prefixArguments -m venv (Join-Path $BackendRoot "venv")
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
        Write-Host "[ERROR] Failed to create backend\venv with Python 3.11."
        exit 1
    }
}

& $VenvPython -m pip install -r (Join-Path $BackendRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
if ($null -eq $npm) {
    Write-Host "[ERROR] Node.js/npm not found. Install Node.js first."
    exit 1
}
& $npm.Source install --prefix $FrontendRoot
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[OK] Backend and frontend dependencies installed."
Write-Host "[INFO] Whisper is only required for processing new videos."
Write-Host "       Install the project's Whisper package before using Full AI Mode."
