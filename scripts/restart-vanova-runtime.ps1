# Restart VANOVA Desktop runtime (port 8765) without reinstalling the app.
$ErrorActionPreference = "Continue"

$port = 8765
$installRoot = Join-Path $env:LOCALAPPDATA "Programs\VANOVA"
$vanovaRoot = Join-Path $installRoot "resources\vanova"
$launcher = Join-Path $vanovaRoot "desktop\runtime\launcher.py"
$logs = Join-Path $env:LOCALAPPDATA "VANOVA\logs"
$runtimeLog = Join-Path $logs "runtime-launcher.log"

function Write-Step($msg) { Write-Host "[VANOVA] $msg" }

Write-Step "Stopping stray VANOVA launcher.py processes..."
Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*launcher.py*' } |
  ForEach-Object {
    Write-Step "Stopping launcher PID $($_.ProcessId)..."
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
  }
Start-Sleep -Seconds 1

Write-Step "Clearing listeners on port $port..."
$conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
$killFailed = $false
if ($conns) {
  $procIds = $conns | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { $_ -gt 0 }
  foreach ($procId in $procIds) {
    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
    $name = if ($proc) { $proc.ProcessName } else { "?" }
    Write-Step "Stopping PID $procId ($name)..."
    try {
      Stop-Process -Id $procId -Force -ErrorAction Stop
    } catch {
      $killFailed = $true
      Write-Step "Could not stop PID $procId — cierra VANOVA Desktop por completo y vuelve a ejecutar este script."
    }
  }
  Start-Sleep -Seconds 1
}
if ($killFailed) {
  Write-Error "No se pudo liberar el puerto $port. Cierra VANOVA Desktop (VANOVA.exe) y ejecuta de nuevo."
  exit 3
}

$python = Join-Path $vanovaRoot "python\python.exe"
if (-not (Test-Path $python)) { $python = Join-Path $vanovaRoot ".venv\Scripts\python.exe" }
if (-not (Test-Path $python)) {
  $hermesPy = Join-Path $env:LOCALAPPDATA "hermes\hermes-agent\venv\Scripts\python.exe"
  if (Test-Path $hermesPy) { $python = $hermesPy }
}
if (-not (Test-Path $python)) { $python = "python" }
Write-Step "Using Python: $python"

if (-not (Test-Path $launcher)) { Write-Error "Launcher not found: $launcher"; exit 1 }

New-Item -ItemType Directory -Force -Path $logs | Out-Null
Write-Step "Starting runtime via $launcher"
$env:MAIOS_APP_ROOT = $vanovaRoot
$env:MAIOS_RESOURCES = $vanovaRoot
$env:MAIOS_EXE = Join-Path $installRoot "VANOVA.exe"
$env:MAIOS_APP_EXE = $env:MAIOS_EXE
$env:PYTHONPATH = $vanovaRoot

Start-Process -FilePath $python -ArgumentList @($launcher) -WorkingDirectory $vanovaRoot -WindowStyle Hidden `
  -RedirectStandardOutput $runtimeLog -RedirectStandardError ($runtimeLog + ".err") | Out-Null

Write-Step "Waiting for http://127.0.0.1:$port/api/health ..."
$deadline = (Get-Date).AddSeconds(30)
$ok = $false
while ((Get-Date) -lt $deadline) {
  try {
    $resp = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/health" -TimeoutSec 2
    if ($resp.service -eq "vanova-desktop-runtime") { $ok = $true; break }
  } catch {}
  Start-Sleep -Milliseconds 500
}

if ($ok) {
  Write-Step "Runtime OK on port $port"
  try {
    $setup = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/setup/status" -TimeoutSec 5
    if (-not $setup.configPath) { Write-Error "Runtime stale: setup/status lacks configPath"; exit 2 }
    $files = Invoke-WebRequest -Uri "http://127.0.0.1:$port/api/files" -TimeoutSec 5 -UseBasicParsing
    if ($files.StatusCode -ne 200) { Write-Error "Runtime stale: /api/files HTTP $($files.StatusCode)"; exit 2 }
    Write-Step "Files API OK (configPath present)"
    $insights = Invoke-WebRequest -Uri "http://127.0.0.1:$port/api/insight-actions" -TimeoutSec 5 -UseBasicParsing
    if ($insights.StatusCode -ne 200) { Write-Error "Runtime stale: /api/insight-actions HTTP $($insights.StatusCode)"; exit 2 }
    Write-Step "Insight-actions API OK"
    $shopifyCfg = Invoke-WebRequest -Uri "http://127.0.0.1:$port/api/integrations/shopify/config" -TimeoutSec 5 -UseBasicParsing
    if ($shopifyCfg.StatusCode -ne 200) { Write-Error "Runtime stale: /api/integrations/shopify/config HTTP $($shopifyCfg.StatusCode)"; exit 2 }
    Write-Step "Integrations API OK"
    $all = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/health/all" -TimeoutSec 5
    Write-Step ("Overall health: " + $all.overall)
    $ports = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/health/ports" -TimeoutSec 5
    Write-Step ("Ports API: runtime=" + $ports.runtime.status)
  } catch { Write-Step ("Post-start check warning: " + $_.Exception.Message) }
  exit 0
}
Write-Error "Runtime did not respond. Check $runtimeLog"
exit 1

