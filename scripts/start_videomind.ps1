[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$NonInteractive,
    [switch]$ValidateOnly,
    [ValidateRange(1, 65535)]
    [int]$BackendPort = 8000,
    [ValidateRange(1, 65535)]
    [int]$FrontendPort = 5173,
    [string]$RuntimeDirectory
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendRoot = Join-Path $ProjectRoot "backend"
$FrontendRoot = Join-Path $ProjectRoot "frontend"
$RuntimeRoot = if ([string]::IsNullOrWhiteSpace($RuntimeDirectory)) {
    Join-Path $ProjectRoot ".runtime"
} else {
    [System.IO.Path]::GetFullPath($RuntimeDirectory)
}
$BackendPidFile = Join-Path $RuntimeRoot "backend.pid"
$FrontendPidFile = Join-Path $RuntimeRoot "frontend.pid"
$BackendUrl = "http://127.0.0.1:$BackendPort"
$FrontendUrl = "http://127.0.0.1:$FrontendPort"
$StartupTimeoutSeconds = 60
$PollIntervalSeconds = 2

function Write-LauncherMessage {
    param([string]$Level, [string]$Message)
    Write-Host ("[{0}] {1}" -f $Level, $Message)
}

function Stop-WithError {
    param([string[]]$Message)
    foreach ($line in $Message) {
        Write-LauncherMessage "ERROR" $line
    }
    exit 1
}

function Get-ManagedProcess {
    param([string]$PidFile, [string]$Marker)

    if (-not (Test-Path -LiteralPath $PidFile -PathType Leaf)) {
        return $null
    }

    $storedPid = 0
    if (-not [int]::TryParse((Get-Content -LiteralPath $PidFile -Raw).Trim(), [ref]$storedPid)) {
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
        return $null
    }

    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $storedPid" -ErrorAction SilentlyContinue
    if ($null -eq $process -or $process.Name -notin @("cmd.exe", "cmd")) {
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
        return $null
    }
    if ([string]::IsNullOrWhiteSpace($process.CommandLine) -or $process.CommandLine -notlike "*$Marker*") {
        Write-LauncherMessage "WARNING" "Ignoring stale PID file because PID $storedPid is not a managed VideoMind-Agent process."
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
        return $null
    }
    return $process
}

function Test-PortInUse {
    param([int]$Port)
    return $null -ne (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1)
}

function Test-BackendReady {
    try {
        $health = Invoke-RestMethod -Uri "$BackendUrl/health" -TimeoutSec 2
        $schema = Invoke-RestMethod -Uri "$BackendUrl/openapi.json" -TimeoutSec 2
        return $health.status -eq "ok" -and $schema.info.title -eq "VideoMind-Agent"
    }
    catch {
        return $false
    }
}

function Test-FrontendReady {
    try {
        $response = Invoke-WebRequest -Uri $FrontendUrl -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -eq 200 -and $response.Content -match "VideoMind Agent"
    }
    catch {
        return $false
    }
}

function Wait-ServicesReady {
    $deadline = [DateTime]::UtcNow.AddSeconds($StartupTimeoutSeconds)
    $backendWasReady = $false
    $frontendWasReady = $false
    while ([DateTime]::UtcNow -lt $deadline) {
        if (-not $backendWasReady -and (Test-BackendReady)) {
            $backendWasReady = $true
            Write-LauncherMessage "OK" "Backend ready"
        }
        if (-not $frontendWasReady -and (Test-FrontendReady)) {
            $frontendWasReady = $true
            Write-LauncherMessage "OK" "Frontend ready"
        }
        if ($backendWasReady -and $frontendWasReady) {
            return @{ Backend = $true; Frontend = $true }
        }
        Start-Sleep -Seconds $PollIntervalSeconds
    }
    if (-not $backendWasReady) {
        Write-LauncherMessage "WARNING" "Backend startup timed out. Check the Backend terminal window for details."
    }
    if (-not $frontendWasReady) {
        Write-LauncherMessage "WARNING" "Frontend startup timed out. Check the Frontend terminal window for details."
    }
    return @{ Backend = $backendWasReady; Frontend = $frontendWasReady }
}

function Resolve-PythonCommand {
    $venvPython = Join-Path $BackendRoot "venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
        try {
            & $venvPython --version *> $null
            if ($LASTEXITCODE -eq 0) {
                return @{ FilePath = $venvPython; PrefixArguments = @(); DisplayName = "backend\venv\Scripts\python.exe" }
            }
        }
        catch {
            # Continue to the system Python candidates.
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($null -ne $python) {
        try {
            & $python.Source --version *> $null
            if ($LASTEXITCODE -eq 0) {
                return @{ FilePath = $python.Source; PrefixArguments = @(); DisplayName = "python" }
            }
        }
        catch {
            # Continue to the Python launcher candidate.
        }
    }

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($null -ne $py) {
        try {
            & $py.Source -3.11 -c "import sys; assert sys.version_info[:2] == (3, 11)" 2>$null
            if ($LASTEXITCODE -eq 0) {
                return @{ FilePath = $py.Source; PrefixArguments = @("-3.11"); DisplayName = "py -3.11" }
            }
        }
        catch {
            # The caller prints one consistent Python error below.
        }
    }
    return $null
}

function Test-DeepSeekConfiguration {
    $envFile = Join-Path $BackendRoot ".env"
    if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
        Write-LauncherMessage "WARNING" "backend\.env not found. Copy backend\.env.example to backend\.env before using AI features."
        return $false
    }

    $configured = $false
    foreach ($rawLine in Get-Content -LiteralPath $envFile -Encoding UTF8) {
        $line = $rawLine.Trim()
        if ($line -match '^DEEPSEEK_API_KEY\s*=\s*(.*)$') {
            $value = $Matches[1].Trim().Trim('"').Trim("'")
            $configured = -not [string]::IsNullOrWhiteSpace($value) -and $value -notmatch '^(your_api_key_here|your_deepseek_api_key|placeholder)$'
            break
        }
    }

    if (-not $configured) {
        Write-LauncherMessage "WARNING" "DEEPSEEK_API_KEY is not configured."
        Write-Host "          Whisper/local playback may still work, but Transcript Correction,"
        Write-Host "          Translation, Summary and Q&A may be unavailable."
    }
    return $configured
}

function Get-BackendEnvValue {
    param([string]$Name)
    $envFile = Join-Path $BackendRoot ".env"
    if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
        return $null
    }
    foreach ($rawLine in Get-Content -LiteralPath $envFile -Encoding UTF8) {
        $line = $rawLine.Trim()
        if ($line -match ('^' + [regex]::Escape($Name) + '\s*=\s*(.*)$')) {
            return $Matches[1].Trim().Trim('"').Trim("'")
        }
    }
    return $null
}

Write-Host "================================================"
Write-Host "VideoMind-Agent Windows Launcher"
Write-Host "================================================"

$pythonCommand = Resolve-PythonCommand
if ($null -eq $pythonCommand) {
    Stop-WithError @("Python not found.", "Please install Python 3.11 or create backend\venv.")
}
Write-LauncherMessage "OK" ("Python: {0}" -f $pythonCommand.DisplayName)

$nodeCommand = Get-Command node -ErrorAction SilentlyContinue
$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if ($null -eq $nodeCommand -or $null -eq $npmCommand) {
    Stop-WithError @("Node.js/npm not found.", "Please install Node.js before starting VideoMind-Agent.")
}
& $nodeCommand.Source --version *> $null
if ($LASTEXITCODE -ne 0) {
    Stop-WithError @("Node.js/npm not found.", "Please install Node.js before starting VideoMind-Agent.")
}
& $npmCommand.Source --version *> $null
if ($LASTEXITCODE -ne 0) {
    Stop-WithError @("Node.js/npm not found.", "Please install Node.js before starting VideoMind-Agent.")
}
Write-LauncherMessage "OK" "Node.js and npm available"

$ffmpegCommand = Get-Command ffmpeg -ErrorAction SilentlyContinue
$ffprobeCommand = Get-Command ffprobe -ErrorAction SilentlyContinue
if ($null -eq $ffmpegCommand -or $null -eq $ffprobeCommand) {
    Stop-WithError @("FFmpeg/ffprobe not found in PATH.")
}
& $ffmpegCommand.Source -version *> $null
if ($LASTEXITCODE -ne 0) {
    Stop-WithError @("FFmpeg/ffprobe not found in PATH.")
}
& $ffprobeCommand.Source -version *> $null
if ($LASTEXITCODE -ne 0) {
    Stop-WithError @("FFmpeg/ffprobe not found in PATH.")
}
Write-LauncherMessage "OK" "FFmpeg and ffprobe available"

$demoSetting = Get-BackendEnvValue "COMPETITION_DEMO_MODE"
$competitionDemoMode = $demoSetting -match '^(1|true|yes|on)$'
$deepSeekConfigured = Test-DeepSeekConfiguration
if ($competitionDemoMode) {
    Write-LauncherMessage "INFO" "Competition Demo Mode enabled. The preloaded workspace can run without a DeepSeek API Key."
}

$requiredImports = if ($competitionDemoMode -and -not $deepSeekConfigured) {
    "import fastapi, uvicorn"
} else {
    "import fastapi, uvicorn, whisper"
}
$importArguments = @($pythonCommand.PrefixArguments) + @("-c", $requiredImports)
& $pythonCommand.FilePath @importArguments 2>$null
if ($LASTEXITCODE -ne 0) {
    Stop-WithError @("Backend dependencies are incomplete.", "Run install_dependencies.bat or install the dependencies described in DEMO_README.md.")
}
Write-LauncherMessage "OK" "Backend imports available"

if ($competitionDemoMode -and -not $deepSeekConfigured) {
    $whisperArguments = @($pythonCommand.PrefixArguments) + @("-c", "import whisper")
    $whisperAvailable = $true
    try {
        & $pythonCommand.FilePath @whisperArguments 2>$null
        $whisperAvailable = $LASTEXITCODE -eq 0
    }
    catch {
        $whisperAvailable = $false
    }
    if (-not $whisperAvailable) {
        Write-LauncherMessage "WARNING" "Whisper is not installed. The preloaded Demo still works; new video processing is unavailable."
    }
}

if (-not (Test-Path -LiteralPath (Join-Path $FrontendRoot "node_modules") -PathType Container)) {
    Stop-WithError @("Frontend dependencies are not installed.", "Run:", "cd frontend", "npm install")
}
Write-LauncherMessage "OK" "Frontend node_modules found"

if ($ValidateOnly) {
    Write-LauncherMessage "OK" "Preflight validation completed; no services were started."
    exit 0
}

New-Item -ItemType Directory -Path $RuntimeRoot -Force | Out-Null
$backendProcess = Get-ManagedProcess -PidFile $BackendPidFile -Marker "VideoMind-Agent Backend"
$frontendProcess = Get-ManagedProcess -PidFile $FrontendPidFile -Marker "VideoMind-Agent Frontend"
$backendReady = Test-BackendReady
$frontendReady = Test-FrontendReady

if ((Test-PortInUse $BackendPort) -and -not $backendReady) {
    Stop-WithError @("Port $BackendPort is already in use by an unknown service.")
}
if ((Test-PortInUse $FrontendPort) -and -not $frontendReady) {
    Stop-WithError @("Port $FrontendPort is already in use by an unknown service.")
}

if ($null -ne $backendProcess) {
    Write-LauncherMessage "INFO" "Backend already running."
}
elseif ($backendReady) {
    Write-LauncherMessage "INFO" "Backend already running (not managed by this launcher)."
}
else {
    $pythonParts = @('"' + $pythonCommand.FilePath + '"') + $pythonCommand.PrefixArguments
    $backendCommand = 'title VideoMind-Agent Backend & ' + (($pythonParts + @("-m", "uvicorn", "app.main:app", "--reload", "--port", [string]$BackendPort)) -join " ")
    $backendProcess = Start-Process -FilePath $env:ComSpec -ArgumentList @("/d", "/k", $backendCommand) -WorkingDirectory $BackendRoot -PassThru
    Set-Content -LiteralPath $BackendPidFile -Value $backendProcess.Id -Encoding ASCII
    Write-LauncherMessage "INFO" ("Backend started with managed PID {0}." -f $backendProcess.Id)
}

if ($null -ne $frontendProcess) {
    Write-LauncherMessage "INFO" "Frontend already running."
}
elseif ($frontendReady) {
    Write-LauncherMessage "INFO" "Frontend already running (not managed by this launcher)."
}
else {
    $frontendCommand = "title VideoMind-Agent Frontend & npm.cmd run dev -- --port $FrontendPort"
    $frontendProcess = Start-Process -FilePath $env:ComSpec -ArgumentList @("/d", "/k", $frontendCommand) -WorkingDirectory $FrontendRoot -PassThru
    Set-Content -LiteralPath $FrontendPidFile -Value $frontendProcess.Id -Encoding ASCII
    Write-LauncherMessage "INFO" ("Frontend started with managed PID {0}." -f $frontendProcess.Id)
}

$readiness = Wait-ServicesReady
$backendReady = $readiness.Backend
$frontendReady = $readiness.Frontend

if ($backendReady -and $frontendReady) {
    Write-Host "================================================"
    Write-Host "VideoMind-Agent"
    Write-Host "Backend:  $BackendUrl"
    Write-Host "Frontend: $FrontendUrl"
    Write-Host ("Mode:     {0}" -f $(if ($competitionDemoMode) { "Competition Demo" } else { "Normal" }))
    Write-Host "================================================"
    if (-not $NoBrowser) {
        Start-Process $FrontendUrl
    }
}
else {
    Write-LauncherMessage "WARNING" "Service startup timed out. Check the Backend / Frontend terminal windows for details."
}

if (-not $NonInteractive) {
    Write-Host "Backend and Frontend will continue running after this launcher closes."
}
