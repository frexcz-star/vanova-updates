# Reproducible E2E update validation: 1.0.2 (baseline) -> 1.0.3 (target).
# Automated steps where possible; install+restart requires manual user action.
param(
    [string]$Root = (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)),
    [string]$BaselineVersion = "1.0.2",
    [string]$TargetVersion = "1.0.3",
    [switch]$SkipApiCheck,
    [switch]$ConfigureOnly
)

$ErrorActionPreference = "Stop"

function Write-Step($n, $msg) {
    Write-Host ""
    Write-Host "[$n] $msg" -ForegroundColor Cyan
}

$baselineExe = Join-Path $Root "release\baseline\VANOVA-Setup-$BaselineVersion.exe"
$targetExe = Join-Path $Root "release\VANOVA-Setup-$TargetVersion.exe"
$latestJson = Join-Path $Root "release\latest.json"
$localJson = Join-Path $Root "release\latest.local.json"

Write-Host "VANOVA Update E2E: $BaselineVersion -> $TargetVersion" -ForegroundColor Green
Write-Host "Root: $Root"

Write-Step 1 "Verify baseline installer exists"
if (-not (Test-Path $baselineExe)) {
    Write-Host "  MISSING: $baselineExe" -ForegroundColor Red
    Write-Host "  Build baseline: scripts\release.ps1 -Version $BaselineVersion -SkipTests" -ForegroundColor Yellow
    Write-Host "  Then copy to: release\baseline\VANOVA-Setup-$BaselineVersion.exe" -ForegroundColor Yellow
    exit 1
}
Write-Host "  OK: $baselineExe ($((Get-Item $baselineExe).Length) bytes)"

Write-Step 2 "Verify target installer exists"
if (-not (Test-Path $targetExe)) {
    Write-Host "  MISSING: $targetExe" -ForegroundColor Red
    Write-Host "  Build target: scripts\release.ps1 -Version $TargetVersion" -ForegroundColor Yellow
    exit 1
}
Write-Host "  OK: $targetExe ($((Get-Item $targetExe).Length) bytes)"

Write-Step 3 "Verify installed version (manual if VANOVA not running from baseline)"
$installedVersionJson = Join-Path $env:LOCALAPPDATA "Programs\VANOVA\resources\vanova\version.json"
$altVersionJson = Join-Path $env:ProgramFiles "VANOVA\resources\vanova\version.json"
$found = $false
foreach ($vj in @($installedVersionJson, $altVersionJson)) {
    if (Test-Path $vj) {
        $v = (Get-Content $vj -Raw -Encoding UTF8 | ConvertFrom-Json).version
        Write-Host "  Installed version at ${vj}: $v"
        if ($v -ne $BaselineVersion) {
            Write-Host "  WARN: expected $BaselineVersion - install baseline first:" -ForegroundColor Yellow
            Write-Host "    $baselineExe" -ForegroundColor Yellow
        } else {
            Write-Host "  OK: baseline $BaselineVersion detected" -ForegroundColor Green
        }
        $found = $true
        break
    }
}
if (-not $found) {
    Write-Host "  VANOVA not detected in standard paths." -ForegroundColor Yellow
    Write-Host "  Install baseline: $baselineExe" -ForegroundColor Yellow
}

Write-Step 4 "Configure local update offer ($TargetVersion)"
& (Join-Path $Root "scripts\setup-local-updates.ps1") -OfferVersion $TargetVersion -ResetState -Root $Root
if ($ConfigureOnly) { exit 0 }

Write-Step 5 "Verify manifest and SHA-256"
$manifest = Get-Content $latestJson -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.version -ne $TargetVersion) {
    Write-Host "  FAIL: latest.json version=$($manifest.version), expected $TargetVersion" -ForegroundColor Red
    exit 1
}
$fileHash = (Get-FileHash $targetExe -Algorithm SHA256).Hash.ToLower()
$fileSize = (Get-Item $targetExe).Length
if ($manifest.sha256 -ne $fileHash) {
    Write-Host "  FAIL: SHA256 mismatch" -ForegroundColor Red
    Write-Host "    manifest: $($manifest.sha256)"
    Write-Host "    file:     $fileHash"
    exit 1
}
if ([int]$manifest.size -ne $fileSize) {
    Write-Host "  FAIL: size mismatch manifest=$($manifest.size) file=$fileSize" -ForegroundColor Red
    exit 1
}
Write-Host "  OK: manifest version, SHA256, size match" -ForegroundColor Green

Write-Step 6 "Simulate UpdateManager detection (Python)"
python (Join-Path $Root "scripts\e2e-check-update.py") $BaselineVersion $latestJson
if ($LASTEXITCODE -ne 0) {
    Write-Host "  FAIL: UpdateManager would not offer $TargetVersion from $BaselineVersion" -ForegroundColor Red
    exit 1
}
Write-Host "  OK: update available from $BaselineVersion to $TargetVersion" -ForegroundColor Green

if (-not $SkipApiCheck) {
    Write-Step 7 "Check update via runtime API (requires VANOVA running on 8765)"
    try {
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/updates/status" -TimeoutSec 5
        Write-Host "  API state: $($resp.state) current=$($resp.currentVersion) target=$($resp.targetVersion)"
        if ($resp.updateAvailable -and $resp.targetVersion -eq $TargetVersion) {
            Write-Host "  OK: API reports update to $TargetVersion" -ForegroundColor Green
        } else {
            Write-Host "  INFO: API did not report update (restart VANOVA after setup-local-updates)" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "  SKIP: VANOVA runtime not reachable on :8765 ($($_.Exception.Message))" -ForegroundColor Yellow
    }
}

Write-Step 8 "Download verification (local file URL)"
$localManifest = Get-Content $localJson -Raw -Encoding UTF8 | ConvertFrom-Json
$dlPath = $localManifest.downloadUrl -replace '^file:///', '' -replace '/', '\'
if (-not (Test-Path $dlPath)) {
    Write-Host "  FAIL: download URL points to missing file: $dlPath" -ForegroundColor Red
    exit 1
}
$dlHash = (Get-FileHash $dlPath -Algorithm SHA256).Hash.ToLower()
if ($dlHash -ne $localManifest.sha256) {
    Write-Host "  FAIL: local manifest SHA256 does not match installer" -ForegroundColor Red
    exit 1
}
Write-Host "  OK: download target exists and SHA256 verified" -ForegroundColor Green

Write-Host ""
Write-Host "=== AUTOMATED CHECKS: PASS ===" -ForegroundColor Green
Write-Host ""
Write-Host "MANUAL STEPS (require user to close VANOVA):" -ForegroundColor Yellow
Write-Host "  1. Ensure VANOVA $BaselineVersion is installed and running"
Write-Host "  2. Restart VANOVA (setup-local-updates already configured)"
Write-Host "  3. Wait ~4s - modal should offer VANOVA $TargetVersion"
Write-Host "  4. Ajustes > Actualizaciones > Descargar > Instalar > Reiniciar ahora"
Write-Host "  5. After restart, verify version.json shows $TargetVersion"
Write-Host "  6. Confirm user data preserved (%LOCALAPPDATA%\VANOVA\data)"
