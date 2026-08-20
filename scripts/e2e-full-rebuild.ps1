# Full E2E rebuild: install clean 0.9.0, build 0.9.1 target, run automatic update test
$ErrorActionPreference = "Stop"
$Root = "C:\Users\Admin\maios"

function Stop-MaiosAll {
    Get-Process -Name "VANOVA" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    $pids = Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue | Select-Object -Expand OwningProcess -Unique
    foreach ($procId in $pids) {
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 3
}

Write-Host "=== Full E2E Rebuild ===" -ForegroundColor Cyan

Stop-MaiosAll

Write-Host "[1/4] Building and installing VANOVA 0.9.0..."
& "$Root\scripts\release.ps1" -Version "0.9.0" -SkipTests
$setup090 = "$Root\release\VANOVA-Setup-0.9.0.exe"
Copy-Item "$Root\release\VANOVA-Setup.exe" $setup090 -Force
$proc = Start-Process -FilePath $setup090 -ArgumentList "/S" -Wait -PassThru
if ($proc.ExitCode -ne 0) { throw "0.9.0 install failed: $($proc.ExitCode)" }
$ver = (Get-Content "$env:LOCALAPPDATA\Programs\VANOVA\resources\vanova\version.json" -Raw -Encoding UTF8 | ConvertFrom-Json).version
Write-Host "  Installed: $ver"
if ($ver -ne "0.9.0") { throw "Expected 0.9.0 after install, got $ver" }

Write-Host "[2/4] Building VANOVA 0.9.1 update target..."
& "$Root\scripts\release.ps1" -Version "0.9.1" -SkipTests -ForE2E

Write-Host "[3/4] Resetting repo version.json to 0.9.0..."
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText("$Root\version.json", @'
{
  "version": "0.9.0",
  "productName": "VANOVA",
  "publisher": "MOOVING PAPER",
  "updateManifestUrl": "https://releases.moovingpaper.com/vanova/latest.json",
  "minSupportedVersion": "0.9.0"
}
'@.Trim(), $utf8NoBom)

Stop-MaiosAll
Remove-Item "$env:LOCALAPPDATA\VANOVA\logs\updater.log" -ErrorAction SilentlyContinue

Write-Host "[4/4] Running automatic E2E update test..."
& "$Root\scripts\e2e-update-test.ps1"
exit $LASTEXITCODE
