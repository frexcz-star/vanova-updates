# VANOVA Update Host - arranca el servidor de actualizaciones publico
# (servidor estatico con Range + tunel cloudflared) y publica el manifest.
#
# IMPORTANTE: mientras este proceso corra, cualquier VANOVA instalado podra
# buscar/descargar actualizaciones. Si la maquina se apaga, el tunel cambia
# de URL y hay que re-ejecutar este script + republish (ver abajo).
#
# Uso:
#   .\scripts\start-update-host.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Port = 8137
$ReleaseDir = Join-Path $Root "release"
$LogDir = Join-Path $Root "release\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$VenPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenPy)) { throw "No hay .venv - usa el entorno de build" }

# 1) Servidor estatico con soporte Range (necesario para reanudar descargas)
$server = Start-Process -FilePath $VenPy -ArgumentList @(
    (Join-Path $Root "scripts\range-static-server.py"), $ReleaseDir, "$Port"
) -WindowStyle Hidden -RedirectStandardOutput (Join-Path $LogDir "range-server.log") -PassThru
Start-Sleep -Seconds 2

# 2) Tunel cloudflared (sin cuenta, URL https://xxx.trycloudflare.com)
$cf = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
if (-not (Test-Path $cf)) { $cf = "cloudflared" }
$tunnel = Start-Process -FilePath $cf -ArgumentList @(
    "tunnel", "--url", "http://127.0.0.1:$Port", "--no-autoupdate"
) -WindowStyle Hidden -RedirectStandardOutput (Join-Path $LogDir "tunnel.log") -RedirectStandardError (Join-Path $LogDir "tunnel.err.log") -PassThru

Write-Host "Esperando URL del tunel..."
$url = ""
for ($i = 0; $i -lt 30 -and -not $url; $i++) {
    Start-Sleep -Seconds 2
    $m = Select-String -Path (Join-Path $LogDir "tunnel.log") -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -ErrorAction SilentlyContinue
    if ($m) { $url = ($m.Matches[0].Value) }
}
if (-not $url) { throw "No se obtuvo URL del tunel - revisa release\logs\tunnel.log" }

Write-Host ""
Write-Host "TUNEL ACTIVO: $url" -ForegroundColor Green
Write-Host "  PIDs: range-server=$($server.Id) cloudflared=$($tunnel.Id)"
Write-Host ""

# 3) Publicar manifest con la URL real
& (Join-Path $Root "scripts\publish-remote.ps1") -PublicUrl $url

Write-Host ""
Write-Host "RESUMEN" -ForegroundColor Cyan
Write-Host "  Manifest:   $url/latest.json"
Write-Host "  Instalador: $url/VANOVA-Setup-<version>.exe"
Write-Host ""
Write-Host "PARA EL CLIENTE (descarga directa del instalador):" -ForegroundColor Yellow
Write-Host "  curl -F \"file=@$ReleaseDir\VANOVA-Setup-<version>.exe\" -F \"expire=172800\" https://tmpfiles.org/api/v1/upload"
