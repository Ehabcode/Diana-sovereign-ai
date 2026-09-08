[CmdletBinding()]
param(
    [string]$OutputRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) 'DianaOfflineBundle'),
    [switch]$IncludeVenv = $true,
    [switch]$IncludeNodeModules = $true,
    [switch]$IncludeOllamaModels = $true,
    [switch]$Zip = $true
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path $PSScriptRoot).Path
$BundleProject = Join-Path $OutputRoot 'DianaProject'
$ZipPath = Join-Path (Split-Path -Parent $OutputRoot) 'DianaProject_FULL_OFFLINE.zip'

function Copy-Tree([string]$Source, [string]$Destination) {
    if (-not (Test-Path $Source)) { Write-Warning "Missing: $Source"; return }
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    & robocopy $Source $Destination /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP /XD '__pycache__' '.git' 'node_modules' '.venv' 'data' | Out-Null
    if ($LASTEXITCODE -gt 7) { throw "robocopy failed for $Source with exit code $LASTEXITCODE" }
}

if (Test-Path $OutputRoot) { Remove-Item -Recurse -Force $OutputRoot }
New-Item -ItemType Directory -Force -Path $BundleProject | Out-Null

# Copy the complete source project while excluding only caches and generated local data.
Copy-Tree $ProjectRoot $BundleProject
foreach ($cache in @((Join-Path $BundleProject 'node_modules'), (Join-Path $BundleProject '.venv'), (Join-Path $BundleProject 'python\data'))) {
    if (Test-Path $cache) { Remove-Item -Recurse -Force $cache }
}

# Restore the intentionally large local runtimes when requested.
if ($IncludeNodeModules -and (Test-Path (Join-Path $ProjectRoot 'node_modules'))) {
    Copy-Tree (Join-Path $ProjectRoot 'node_modules') (Join-Path $BundleProject 'node_modules')
}
if ($IncludeVenv -and (Test-Path (Join-Path $ProjectRoot '.venv'))) {
    Copy-Tree (Join-Path $ProjectRoot '.venv') (Join-Path $BundleProject '.venv')
}

# Copy the real Ollama model store. OLLAMA_MODELS is respected if set.
$OllamaModels = $env:OLLAMA_MODELS
if (-not $OllamaModels) { $OllamaModels = Join-Path $HOME '.ollama\models' }
$OllamaStatus = 'not included'
if ($IncludeOllamaModels) {
    if (Test-Path $OllamaModels) {
        Copy-Tree $OllamaModels (Join-Path $OutputRoot 'ollama-models')
        $OllamaStatus = 'copied'
    } else {
        Write-Warning "Ollama model store not found: $OllamaModels"
        $OllamaStatus = 'missing'
    }
}
$OllamaList = @()
$OllamaExe = Get-Command ollama.exe -ErrorAction SilentlyContinue
if ($OllamaExe) {
    try { $OllamaList = @(ollama list 2>$null) } catch { Write-Warning 'Could not read ollama list.' }
} else { Write-Warning 'ollama.exe not found in PATH.' }

# Copy FFmpeg shared binaries used by torchcodec/XTTS when present.
$FfmpegBin = $env:FFMPEG_SHARED_BIN
if (-not $FfmpegBin) {
    $FfmpegBin = (Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Directory -Filter 'Gyan.FFmpeg.Shared_*' -ErrorAction SilentlyContinue |
        Get-ChildItem -Directory -Filter '*full_build-shared' -ErrorAction SilentlyContinue |
        ForEach-Object { Join-Path $_.FullName 'bin' } | Select-Object -First 1)
}
if (-not $FfmpegBin -and (Test-Path 'C:\ffmpeg\bin')) { $FfmpegBin = 'C:\ffmpeg\bin' }
if ($FfmpegBin -and (Test-Path $FfmpegBin)) {
    Copy-Tree $FfmpegBin (Join-Path $OutputRoot 'ffmpeg\bin')
} else { Write-Warning 'FFMPEG_SHARED_BIN was not found; XTTS audio may need FFmpeg installed.' }

$Manifest = [ordered]@{
    createdAt = (Get-Date).ToString('o')
    projectRoot = $ProjectRoot
    includeVenv = [bool]($IncludeVenv -and (Test-Path (Join-Path $BundleProject '.venv')))
    includeNodeModules = [bool]($IncludeNodeModules -and (Test-Path (Join-Path $BundleProject 'node_modules')))
    ollamaModelStore = $OllamaStatus
    ollamaModelsPath = $OllamaModels
    ollamaList = $OllamaList
    ffmpegIncluded = [bool]($FfmpegBin -and (Test-Path (Join-Path $OutputRoot 'ffmpeg\bin')))
}
$Manifest | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 (Join-Path $OutputRoot 'offline-manifest.json')

@"
Diana 2.5 beta — Full Offline Bundle

This bundle was assembled from the local Windows installation.
Run Diana from the project folder with:
  npm start

The model store is in ..\ollama-models. To use it, set:
  `$env:OLLAMA_MODELS = "`$PSScriptRoot\..\ollama-models"

The FFmpeg shared binaries are in ..\ffmpeg\bin. Before XTTS:
  `$env:FFMPEG_SHARED_BIN = "`$PSScriptRoot\..\ffmpeg\bin"
  `$env:Path = "`$env:FFMPEG_SHARED_BIN;`$env:Path"

This archive contains machine-specific runtimes. Do not distribute it publicly.
"@ | Set-Content -Encoding UTF8 (Join-Path $OutputRoot 'OFFLINE_README.txt')

if ($Zip) {
    if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
    $tar = Get-Command tar.exe -ErrorAction SilentlyContinue
    if ($tar) {
        & tar.exe -a -c -f $ZipPath -C (Split-Path -Parent $OutputRoot) (Split-Path -Leaf $OutputRoot)
        if ($LASTEXITCODE -ne 0) { throw "tar could not create the ZIP" }
    } else {
        Compress-Archive -Path (Join-Path $OutputRoot '*') -DestinationPath $ZipPath -CompressionLevel Optimal
    }
    Write-Host "Created: $ZipPath" -ForegroundColor Green
} else {
    Write-Host "Created folder: $OutputRoot" -ForegroundColor Green
}
Write-Host "Project: $BundleProject"
Write-Host "Review warnings above before calling this 100% offline."
