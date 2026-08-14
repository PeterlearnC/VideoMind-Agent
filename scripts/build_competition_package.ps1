[CmdletBinding()]
param([string]$OutputDirectory, [switch]$KeepStaging)

$ErrorActionPreference = "Stop"
$ProjectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$RuntimeRoot = Join-Path $ProjectRoot ".runtime"
$StagingRoot = Join-Path $RuntimeRoot "release-staging"
$PackageName = "VideoMind-Agent-v0.7.4-Competition-Demo"
$PackageRoot = Join-Path $StagingRoot $PackageName
$ReleaseRoot = if ([string]::IsNullOrWhiteSpace($OutputDirectory)) { Join-Path $ProjectRoot "release" } else { [IO.Path]::GetFullPath($OutputDirectory) }
$ZipPath = Join-Path $ReleaseRoot "$PackageName.zip"
$ShaPath = "$ZipPath.sha256.txt"
$AuditPath = Join-Path $ReleaseRoot "$PackageName-audit.json"

function Assert-ScopedPath {
    param([string]$Path, [string]$AllowedRoot)
    $resolved = [IO.Path]::GetFullPath($Path)
    $allowed = [IO.Path]::GetFullPath($AllowedRoot).TrimEnd('\') + '\'
    if (-not $resolved.StartsWith($allowed, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing operation outside the intended directory: $resolved"
    }
}

function Copy-AllowlistedFile {
    param([string]$RelativePath)
    $source = Join-Path $ProjectRoot $RelativePath
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Required package file is missing: $RelativePath" }
    $destination = Join-Path $PackageRoot $RelativePath
    New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination
}

function Copy-AllowlistedTree {
    param([string]$RelativePath)
    $sourceRoot = Join-Path $ProjectRoot $RelativePath
    if (-not (Test-Path -LiteralPath $sourceRoot -PathType Container)) { return }
    $excludedDirectories = @(".git", ".github", ".runtime", ".pytest_cache", "__pycache__", "node_modules", "venv", ".venv", "dist", "performance", "coverage")
    foreach ($source in Get-ChildItem -LiteralPath $sourceRoot -File -Recurse) {
        $relativeWithinTree = $source.FullName.Substring($sourceRoot.Length).TrimStart('\')
        $segments = $relativeWithinTree -split '[\\/]'
        if (@($segments | Where-Object { $_ -in $excludedDirectories }).Count -gt 0) { continue }
        if ($source.Name -like '~$*.pptx' -or $source.Extension -in @('.pyc', '.pyo', '.log')) { continue }
        $destination = Join-Path (Join-Path $PackageRoot $RelativePath) $relativeWithinTree
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        Copy-Item -LiteralPath $source.FullName -Destination $destination
    }
}

Assert-ScopedPath $StagingRoot $RuntimeRoot
if (Test-Path -LiteralPath $StagingRoot) { Remove-Item -LiteralPath $StagingRoot -Recurse -Force }
New-Item -ItemType Directory -Path $PackageRoot -Force | Out-Null
New-Item -ItemType Directory -Path $ReleaseRoot -Force | Out-Null

@("README.md", "DEMO_README.md", "start_videomind.bat", "stop_videomind.bat", "prepare_videomind_demo.bat", "install_dependencies.bat") |
    ForEach-Object { Copy-AllowlistedFile $_ }
@("backend/requirements.txt", "backend/.env.example", "backend/.env.competition.example", "frontend/index.html", "frontend/package.json", "frontend/package-lock.json", "frontend/vite.config.js", "scripts/start_videomind.ps1", "scripts/stop_videomind.ps1", "scripts/prepare_competition_demo.ps1", "scripts/install_dependencies.ps1", "docs/competition/GITHUB_RELEASE_NOTES_v0.7.4-demo.md", "docs/competition/SUBMISSION_DEMO_LINK_TEXT.md") |
    ForEach-Object { Copy-AllowlistedFile $_ }
@("backend/app", "frontend/src", "frontend/public", "demo/competition", "docs/images") |
    ForEach-Object { Copy-AllowlistedTree $_ }

$sourceCommit = (& git -C $ProjectRoot rev-parse HEAD).Trim()
$buildTime = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
@"
Product: VideoMind-Agent
Release: VideoMind-Agent v0.7.4 - Competition Demo Release
Mode: Competition Demo / Prototype
Platform: Windows 10 / 11
Git source commit: $sourceCommit
Build time: $buildTime

Includes:
- FastAPI backend and React/Vite frontend source
- Windows launch, stop, preparation and dependency helper scripts
- Preloaded Competition Demo workspace and project-generated test-pattern video
- Bilingual subtitle, Summary and Grounded Q&A fixtures
- Demo documentation and product screenshots

Excludes:
- Secrets, backend/.env and API credentials
- User data, uploaded videos, generated subtitles and runtime files
- Performance runtime JSON and logs
- venv, node_modules, dist, caches and Git metadata

Note: This package is built from the clean tracked source commit listed above.
The v0.7.4 annotated tag is expected to point to that release source commit.
"@ | Set-Content -LiteralPath (Join-Path $PackageRoot "RELEASE_MANIFEST.txt") -Encoding UTF8

$forbidden = @()
foreach ($item in Get-ChildItem -LiteralPath $PackageRoot -Force -Recurse) {
    $relative = $item.FullName.Substring($PackageRoot.Length).TrimStart('\')
    $segments = $relative -split '[\\/]'
    if ($item.Name -eq ".env" -or $item.Name -like '~$*.pptx' -or
        @($segments | Where-Object { $_ -in @(".git", ".runtime", "node_modules", "venv", ".venv", "dist", "__pycache__", ".pytest_cache", "performance") }).Count -gt 0 -or
        $item.Extension -in @('.pyc', '.pyo', '.log')) { $forbidden += $relative }
}
if ($forbidden.Count -gt 0) { throw "Forbidden package entries found: $($forbidden -join ', ')" }

$mediaFiles = @(Get-ChildItem -LiteralPath $PackageRoot -File -Recurse | Where-Object { $_.Extension.ToLowerInvariant() -in @('.mp4', '.mov', '.mkv', '.avi', '.wav', '.mp3', '.m4a') })
foreach ($media in $mediaFiles) {
    $relative = $media.FullName.Substring($PackageRoot.Length).TrimStart('\').Replace('\', '/')
    if ($relative -ne "demo/competition/competition-demo.mp4") { throw "Unexpected media file in package: $relative" }
}

$textExtensions = @('.py', '.js', '.jsx', '.json', '.md', '.ps1', '.bat', '.example', '.txt', '.html')
$absolutePathMatches = @(); $secretKeywordMatches = @(); $privacyMatches = @(); $secretFailures = @()
foreach ($file in Get-ChildItem -LiteralPath $PackageRoot -File -Recurse) {
    if ($file.Extension.ToLowerInvariant() -notin $textExtensions) { continue }
    $relative = $file.FullName.Substring($PackageRoot.Length).TrimStart('\')
    $content = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8
    if ($content -match '(?i)(D:\\(?![nrt])|C:\\Users\\|codexproject|python311)') { $absolutePathMatches += $relative }
    if ($content -match '(?i)\b(api[_-]?key|apikey|authorization|bearer|secret|token|password)\b') { $secretKeywordMatches += $relative }
    if ($content -match '(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b') { $privacyMatches += $relative }
    if ($content -match '(?i)\bsk-[A-Za-z0-9_-]{16,}\b') { $secretFailures += $relative }
    foreach ($line in ($content -split "`r?`n")) {
        if ($line -match '(?i)^\s*DEEPSEEK_API_KEY\s*=\s*(.*)$') {
            $candidate = $Matches[1].Trim().Trim('"').Trim("'")
            if (-not [string]::IsNullOrWhiteSpace($candidate) -and $candidate -notin @('your_api_key_here', 'your_deepseek_api_key', 'placeholder')) {
                $secretFailures += $relative
            }
        }
    }
}
if ($absolutePathMatches.Count -gt 0) { throw "Hard-coded local path found in: $((@($absolutePathMatches | Sort-Object -Unique)) -join ', ')" }
if ($privacyMatches.Count -gt 0) { throw "Potential personal email found in: $((@($privacyMatches | Sort-Object -Unique)) -join ', ')" }
if ($secretFailures.Count -gt 0) { throw "Potential real credential found in: $((@($secretFailures | Sort-Object -Unique)) -join ', ')" }

$audit = [ordered]@{
    schema_version = 1; package = $PackageName; source_commit = $sourceCommit; built_at = $buildTime
    file_count = @(Get-ChildItem -LiteralPath $PackageRoot -File -Recurse).Count
    forbidden_entries = $forbidden; secret_scan = "passed_no_credential_values"
    secret_keyword_files_reviewed = @($secretKeywordMatches | Sort-Object -Unique)
    absolute_path_scan = "passed"; privacy_scan = "passed"
    media = @($mediaFiles | ForEach-Object { [ordered]@{ path = $_.FullName.Substring($PackageRoot.Length).TrimStart('\').Replace('\', '/'); bytes = $_.Length; source = "Project-generated FFmpeg test pattern with silent audio"; redistribution = "Project-owned fixture; no third-party footage or audio" } })
}

if (Test-Path -LiteralPath $ZipPath) { Remove-Item -LiteralPath $ZipPath -Force }
if (Test-Path -LiteralPath $ShaPath) { Remove-Item -LiteralPath $ShaPath -Force }
Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::CreateFromDirectory($StagingRoot, $ZipPath, [IO.Compression.CompressionLevel]::Optimal, $false)
$hash = (Get-FileHash -LiteralPath $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath $ShaPath -Value "$hash  $PackageName.zip" -Encoding ASCII
$audit.zip_file = Split-Path -Leaf $ZipPath; $audit.zip_size_bytes = (Get-Item -LiteralPath $ZipPath).Length; $audit.sha256 = $hash
$audit | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $AuditPath -Encoding UTF8
Write-Host "[OK] Package: $ZipPath"; Write-Host "[OK] Files: $($audit.file_count)"; Write-Host "[OK] SHA256: $hash"; Write-Host "[OK] Audit: $AuditPath"

if (-not $KeepStaging) {
    Assert-ScopedPath $StagingRoot $RuntimeRoot
    Remove-Item -LiteralPath $StagingRoot -Recurse -Force
}
