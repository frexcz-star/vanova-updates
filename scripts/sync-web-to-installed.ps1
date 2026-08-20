# Sync web/dist to installed VANOVA (no exe rebuild).
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$Src = Join-Path $Root "web\dist"
$Dst = Join-Path $env:LOCALAPPDATA "Programs\VANOVA\resources\vanova\web\dist"
if (-not (Test-Path $Dst)) {
  Write-Error "Installed VANOVA not found: $Dst"
}
$files = @("system-status.js", "index.html", "dashboard.html", "data-services.js", "update-center.js")
foreach ($f in $files) {
  $from = Join-Path $Src $f
  if (Test-Path $from) {
    Copy-Item -Force $from (Join-Path $Dst $f)
    Write-Host "OK $f"
  }
}
Write-Host "Done. Restart VANOVA.exe to pick up UI changes."
