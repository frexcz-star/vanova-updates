# Publish VANOVA update manifest + installer to production CDN staging folder.
# Upload the output directory to https://releases.moovingpaper.com/vanova/
param(
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$Root = "",
    [string]$OutputDir = "",
    [switch]$SkipVerify
)

$ErrorActionPreference = "Stop"
if (-not $Root) {
    $Root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
}

function Write-JsonNoBom($Path, $Object) {
    $json = $Object | ConvertTo-Json -Depth 10
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($Path, $json, $utf8NoBom)
}

$releaseDir = Join-Path $Root "release"
$setupExe = Join-Path $releaseDir "VANOVA-Setup-$Version.exe"
$latestJson = Join-Path $releaseDir "latest.json"

if (-not (Test-Path $setupExe)) {
    throw "Installer not found: $setupExe. Run scripts\release.ps1 -Version $Version first."
}

if (-not (Test-Path $latestJson)) {
    throw "Manifest not found: $latestJson. Run scripts\release.ps1 -Version $Version first."
}

$manifest = Get-Content $latestJson -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.version -ne $Version) {
    throw "latest.json version ($($manifest.version)) does not match -Version $Version"
}

$hash = (Get-FileHash $setupExe -Algorithm SHA256).Hash.ToLower()
$size = (Get-Item $setupExe).Length
if ($manifest.sha256 -ne $hash) {
    throw "SHA256 mismatch. Manifest=$($manifest.sha256) File=$hash. Regenerate with scripts\release.ps1"
}
if ([int]$manifest.size -ne $size) {
    throw "Size mismatch. Manifest=$($manifest.size) File=$size. Regenerate with scripts\release.ps1"
}

if (-not $SkipVerify) {
    Write-Host "Verifying package contents..."
    & (Join-Path $Root "scripts\verify-package.ps1")
}

$publishRoot = if ($OutputDir) { $OutputDir } else { Join-Path $releaseDir "publish" }
New-Item -ItemType Directory -Force -Path $publishRoot | Out-Null

Copy-Item -Force $setupExe (Join-Path $publishRoot "VANOVA-Setup-$Version.exe")
Copy-Item -Force $latestJson (Join-Path $publishRoot "latest.json")

$checksums = @{
    version = $Version
    files   = @(
        @{
            name   = "VANOVA-Setup-$Version.exe"
            sha256 = $hash
            size   = $size
        }
    )
}
Write-JsonNoBom (Join-Path $publishRoot "checksums.json") $checksums

Write-Host ""
Write-Host "Publish bundle ready:" -ForegroundColor Green
Write-Host "  $publishRoot"
Write-Host "  latest.json -> version $Version"
Write-Host "  VANOVA-Setup-$Version.exe ($size bytes)"
Write-Host "  SHA256: $hash"
Write-Host ""
Write-Host "Upload to CDN:" -ForegroundColor Cyan
Write-Host "  https://releases.moovingpaper.com/vanova/latest.json"
Write-Host "  https://releases.moovingpaper.com/vanova/VANOVA-Setup-$Version.exe"
Write-Host ""
Write-Host "NOTE: Code signing and CDN upload require external infrastructure."
