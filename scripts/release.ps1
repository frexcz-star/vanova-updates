# VANOVA Release Script - reproducible build + manifest generation
param(
    [Parameter(Mandatory=$true)][string]$Version,
    [switch]$SkipBuild,
    [switch]$SkipTests,
    [switch]$ForE2E
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Write-JsonNoBom($Path, $Object) {
    $json = $Object | ConvertTo-Json -Depth 10
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($Path, $json, $utf8NoBom)
}

Write-Host "VANOVA Release $Version" -ForegroundColor Cyan

$versionJson = Join-Path $Root "version.json"
$vj = Get-Content $versionJson -Raw -Encoding UTF8 | ConvertFrom-Json
$vj.version = $Version
Write-JsonNoBom $versionJson $vj

$pkgJson = Join-Path $Root "desktop\package.json"
$pkg = Get-Content $pkgJson -Raw -Encoding UTF8 | ConvertFrom-Json
$pkg.version = $Version
Write-JsonNoBom $pkgJson $pkg

# Keep CLOUD_API_VERSION in shared/version_info.py in sync so the version
# consistency tests pass after every release (they assert cloud == maios).
$versionInfoPy = Join-Path $Root "shared\version_info.py"
$viContent = Get-Content $versionInfoPy -Raw -Encoding UTF8
$viContent = $viContent -replace 'CLOUD_API_VERSION = "[^"]*"', ('CLOUD_API_VERSION = "' + $Version + '"')
$viUtf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($versionInfoPy, $viContent, $viUtf8NoBom)

# Electron loads http://127.0.0.1:8000/ which serves index.html (StaticFiles html=True).
# Keep index.html in sync with dashboard.html so UI fixes appear in the app.
Write-Host "Syncing web/dist from dashboard and JS assets..."
$webDist = Join-Path $Root "web\dist"
$dashboardHtml = Join-Path $Root "web\dashboard.html"
Copy-Item -Force $dashboardHtml (Join-Path $Root "web\index.html")
Copy-Item -Force $dashboardHtml (Join-Path $webDist "index.html")
Copy-Item -Force $dashboardHtml (Join-Path $webDist "dashboard.html")
foreach ($asset in @("data-services.js", "system-status.js", "update-center.js", "ux-helpers.js")) {
    $src = Join-Path $Root "web\$asset"
    if (Test-Path $src) { Copy-Item -Force $src (Join-Path $webDist $asset) }
}

Write-Host "Preparing Python bundle (build machine)..."
$bundleScript = Join-Path $Root "scripts\prepare-python-bundle.ps1"
if (Test-Path $bundleScript) {
    & $bundleScript
}

if (-not $SkipBuild) {
    Write-Host "Building installer..."
    Get-Process -Name "VANOVA" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    Push-Location (Join-Path $Root "desktop")
    npm run desktop:installer
    if ($LASTEXITCODE -ne 0) { Pop-Location; throw "Build failed" }
    Pop-Location
}

Write-Host "Verifying package contents..."
& (Join-Path $Root "scripts\verify-package.ps1")

$releaseDir = Join-Path $Root "release"
New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null

$setupSrc = Join-Path $releaseDir "VANOVA-Setup.exe"
$setupDest = Join-Path $releaseDir "VANOVA-Setup-$Version.exe"
if (-not (Test-Path $setupSrc)) { throw "Installer not found at $setupSrc" }
Copy-Item -Force $setupSrc $setupDest

Write-Host "Generating checksums..."
node (Join-Path $Root "scripts\generate-checksums.js")

$hash = (Get-FileHash $setupDest -Algorithm SHA256).Hash.ToLower()
$size = (Get-Item $setupDest).Length

$notesPath = Join-Path $releaseDir "release-notes.md"
if (-not (Test-Path $notesPath)) {
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($notesPath, "# VANOVA $Version`n`n- Improved update system`n- Bug fixes`n", $utf8NoBom)
}

$notes = @()
$notesRaw = [System.IO.File]::ReadAllText($notesPath, [System.Text.UTF8Encoding]::new($false))
$inSection = $false
foreach ($line in ($notesRaw -split "`r?`n")) {
    if ($line -match "^#\s+VANOVA\s+$([regex]::Escape($Version))\s*$") {
        $inSection = $true
        continue
    }
    if ($inSection -and $line -match '^#\s+VANOVA\s+') { break }
    if ($inSection -and $line -match '^\s*[-*]\s+(.+)') {
        $notes += $Matches[1].Trim()
    }
}
if (-not $notes.Count) {
    $notes = @("VANOVA $Version release")
}

$downloadUrl = if ($ForE2E) {
    "file:///$($Root.Replace('\','/'))/release/VANOVA-Setup-$Version.exe"
} else {
    "https://releases.moovingpaper.com/vanova/VANOVA-Setup-$Version.exe"
}

$manifest = @{
    product = "VANOVA"
    channel = "stable"
    version = $Version
    minimumSupportedVersion = "0.9.0"
    mandatory = $false
    publishedAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    downloadUrl = $downloadUrl
    sha256 = $hash
    size = $size
    signature = ""
    releaseNotes = @($notes)
    requiredHermes = ">=1.0.0"
    dbSchemaVersion = 0
}

Write-JsonNoBom (Join-Path $releaseDir "latest.json") $manifest

$localManifest = @{}
foreach ($key in $manifest.Keys) { $localManifest[$key] = $manifest[$key] }
$localManifest.downloadUrl = "file:///$($setupDest.Replace('\','/'))"
Write-JsonNoBom (Join-Path $releaseDir "latest.local.json") $localManifest

Write-Host ""
Write-Host "Release artifacts:" -ForegroundColor Green
Write-Host "  $setupDest"
Write-Host "  $(Join-Path $releaseDir 'latest.json')"
Write-Host "  $(Join-Path $releaseDir 'latest.local.json')"
Write-Host "  SHA256: $hash"

if (-not $SkipTests) {
    Write-Host "Running update unit tests..."
    python -m unittest tests.test_update_system tests.test_update_failures -v
    if ($LASTEXITCODE -ne 0) { throw "Tests failed" }
}
