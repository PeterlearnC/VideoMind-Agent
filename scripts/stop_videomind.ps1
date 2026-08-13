[CmdletBinding()]
param(
    [switch]$NonInteractive,
    [string]$RuntimeDirectory
)

$ErrorActionPreference = "Continue"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RuntimeRoot = if ([string]::IsNullOrWhiteSpace($RuntimeDirectory)) {
    Join-Path $ProjectRoot ".runtime"
} else {
    [System.IO.Path]::GetFullPath($RuntimeDirectory)
}

function Stop-ManagedProcess {
    param([string]$Name, [string]$PidFile, [string]$Marker)

    if (-not (Test-Path -LiteralPath $PidFile -PathType Leaf)) {
        Write-Host ("[INFO] No managed {0} PID file found." -f $Name)
        return
    }

    $storedPid = 0
    if (-not [int]::TryParse((Get-Content -LiteralPath $PidFile -Raw).Trim(), [ref]$storedPid)) {
        Write-Host ("[WARNING] Removing invalid {0} PID file." -f $Name)
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
        return
    }

    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $storedPid" -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        Write-Host ("[INFO] {0} PID {1} is no longer running; removing stale PID file." -f $Name, $storedPid)
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
        return
    }

    if ($process.Name -notin @("cmd.exe", "cmd") -or [string]::IsNullOrWhiteSpace($process.CommandLine) -or $process.CommandLine -notlike "*$Marker*") {
        Write-Host ("[WARNING] PID {0} is not the managed VideoMind-Agent {1}; it will not be stopped." -f $storedPid, $Name)
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
        return
    }

    Write-Host ("[INFO] Stopping {0} process tree (PID {1})..." -f $Name, $storedPid)
    & taskkill.exe /PID $storedPid /T 2>$null | Out-Null
    Start-Sleep -Milliseconds 800
    if ($null -ne (Get-Process -Id $storedPid -ErrorAction SilentlyContinue)) {
        Write-Host ("[WARNING] {0} did not stop gracefully; forcing only its managed process tree." -f $Name)
        & taskkill.exe /PID $storedPid /T /F 2>$null | Out-Null
    }
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
}

Write-Host "================================================"
Write-Host "VideoMind-Agent Stop"
Write-Host "================================================"

Stop-ManagedProcess -Name "Backend" -PidFile (Join-Path $RuntimeRoot "backend.pid") -Marker "VideoMind-Agent Backend"
Stop-ManagedProcess -Name "Frontend" -PidFile (Join-Path $RuntimeRoot "frontend.pid") -Marker "VideoMind-Agent Frontend"

Write-Host "VideoMind-Agent stopped."
Write-Host "User videos, subtitles, performance reports, .env, Summary and Q&A data were not modified."
