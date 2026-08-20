# Kill processes listening on port 8765 (stale VANOVA runtime). Run as admin if access denied.
$ErrorActionPreference = "Continue"
$port = 8765
$conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if (-not $conns) {
  Write-Host "No listener on port $port."
  exit 0
}
$pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { $_ -gt 0 }
foreach ($procId in $pids) {
  $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
  $name = if ($proc) { $proc.ProcessName } else { "?" }
  Write-Host "Stopping PID $procId ($name) on port $port..."
  Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 1
$left = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($left) { Write-Warning "Port $port still in use. Close VANOVA.exe manually and retry." }
else { Write-Host "Port $port is free. Start VANOVA.exe again." }
