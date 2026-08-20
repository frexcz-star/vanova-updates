# Create a clean VANOVA source ZIP for sharing (ChatGPT, reviewers).
param(
    [string]$Root = "",
    [string]$Version = "1.0.2",
    [string]$OutputZip = ""
)

$ErrorActionPreference = "Stop"
if (-not $Root) { $Root = Split-Path -Parent (Split-Path -Parent $PSCommandPath) }
if (-not $OutputZip) { $OutputZip = Join-Path $Root "release\VANOVA-source-$Version.zip" }

$excludeDirNames = @(
    "node_modules", ".git", "__pycache__", ".venv", ".pytest_cache",
    ".cursor", "python-bundle", "win-unpacked", "dist", "build"
)
$excludeFilePatterns = @("*.pyc", "*.pyo", "*.exe", "*.asar", "*.db", "audit.jsonl")
$excludeFileNames = @(".env")

function Should-Exclude([string]$RelativePath, [bool]$IsDir) {
    $parts = $RelativePath -split '[\\/]'
    foreach ($part in $parts) {
        if ($excludeDirNames -contains $part) { return $true }
    }
    $name = Split-Path $RelativePath -Leaf
    if ($excludeFileNames -contains $name) { return $true }
    if (-not $IsDir) {
        foreach ($pat in $excludeFilePatterns) {
            if ($name -like $pat) { return $true }
        }
        # Exclude .env anywhere
        if ($name -eq ".env") { return $true }
    }
    return $false
}

$staging = Join-Path $env:TEMP "vanova-source-zip-$Version"
if (Test-Path $staging) { Remove-Item -Recurse -Force $staging }
New-Item -ItemType Directory -Force -Path $staging | Out-Null

$topItems = @(
    "desktop", "cloud", "connector", "web", "scripts", "tests", "docs", "shared",
    "version.json", "README.md", "DEPLOY.md", "ARCHITECTURE_DECISIONS.md",
    "VANOVA-UPDATE-SYSTEM-BRIEF.md", "VANOVA-COMMERCIAL-READINESS-BRIEF.md",
    ".env.example", ".gitignore",
    "clear_setup.py", "ingest_catalog.py", "install_all.py", "run_all.bat", "start_all.bat"
)

function Copy-TreeFiltered($Src, $Dst) {
    New-Item -ItemType Directory -Force -Path $Dst | Out-Null
    foreach ($item in Get-ChildItem -LiteralPath $Src -Force) {
        $rel = $item.Name
        if (Should-Exclude $rel $item.PSIsContainer) { continue }
        $destPath = Join-Path $Dst $item.Name
        if ($item.PSIsContainer) {
            Copy-TreeFiltered $item.FullName $destPath
        } else {
            Copy-Item -Force $item.FullName $destPath
        }
    }
}

foreach ($item in $topItems) {
    $src = Join-Path $Root $item
    if (-not (Test-Path $src)) { continue }
    $dst = Join-Path $staging $item
    if ((Get-Item $src).PSIsContainer) {
        Copy-TreeFiltered $src $dst
    } else {
        Copy-Item -Force $src $dst
    }
}

# release/ — selective copy
$releaseStaging = Join-Path $staging "release"
New-Item -ItemType Directory -Force -Path $releaseStaging | Out-Null
Copy-Item -Force (Join-Path $Root "release\SOURCE-ZIP-README.txt") $releaseStaging
foreach ($f in @("latest.json", "latest.local.json")) {
    $p = Join-Path $Root "release\$f"
    if (Test-Path $p) { Copy-Item -Force $p $releaseStaging }
}
$publishSrc = Join-Path $Root "release\publish"
if (Test-Path $publishSrc) {
    $publishDst = Join-Path $releaseStaging "publish"
    New-Item -ItemType Directory -Force -Path $publishDst | Out-Null
    foreach ($f in @("latest.json", "checksums.json")) {
        $p = Join-Path $publishSrc $f
        if (Test-Path $p) { Copy-Item -Force $p $publishDst }
    }
}

# Count files
$fileCount = (Get-ChildItem $staging -Recurse -File).Count
$totalBytes = (Get-ChildItem $staging -Recurse -File | Measure-Object -Property Length -Sum).Sum

if (Test-Path $OutputZip) { Remove-Item -Force $OutputZip }
New-Item -ItemType Directory -Force -Path (Split-Path $OutputZip) | Out-Null
Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $OutputZip -CompressionLevel Optimal

Remove-Item -Recurse -Force $staging

$zipSize = (Get-Item $OutputZip).Length
Write-Host ""
Write-Host "Source ZIP created:" -ForegroundColor Green
Write-Host "  Path:  $OutputZip"
Write-Host "  Size:  $([math]::Round($zipSize / 1MB, 2)) MB"
Write-Host "  Files: $fileCount (before compression)"
Write-Host "  Uncompressed: $([math]::Round($totalBytes / 1MB, 2)) MB"
