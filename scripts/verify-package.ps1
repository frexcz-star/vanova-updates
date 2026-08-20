# Verify packaged VANOVA installer contains critical resources.
param(
    [string]$UnpackedDir = ""
)

$ErrorActionPreference = "Stop"
if (-not $UnpackedDir) {
    $Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
    $UnpackedDir = Join-Path $Root "release\win-unpacked\resources\vanova"
}

if (-not (Test-Path $UnpackedDir)) {
    throw "Package not found: $UnpackedDir - run electron-builder first"
}

$required = @(
    "version.json",
    "cloud\main.py",
    "connector\connector.py",
    "desktop\runtime\launcher.py",
    "desktop\runtime\api_server.py",
    "web\index.html"
)

$missing = @()
foreach ($rel in $required) {
    $p = Join-Path $UnpackedDir $rel
    if (-not (Test-Path $p)) { $missing += $rel }
}

$hasPython = (Test-Path (Join-Path $UnpackedDir "python\python.exe")) -or
             (Test-Path (Join-Path $UnpackedDir "python-bundle\python.exe")) -or
             (Test-Path (Join-Path $UnpackedDir "python-bundle\Scripts\python.exe"))

if ($missing.Count) {
    throw "Missing critical resources: $($missing -join ', ')"
}

Write-Host "Package verification:" -ForegroundColor Green
Write-Host "  Root: $UnpackedDir"
Write-Host "  Bundled Python: $(if ($hasPython) { 'YES' } else { 'NO (first-run venv via runtime)' })"
Write-Host "  Required files: OK"
