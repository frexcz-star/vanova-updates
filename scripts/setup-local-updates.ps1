# Configure VANOVA in-app updates for local testing (no CDN required).
param(
    [string]$Root = (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)),
    [switch]$ResetState,
    [string]$OfferVersion = ""
)

$ErrorActionPreference = "Stop"

function Write-JsonNoBom($Path, $Object) {
    $json = $Object | ConvertTo-Json -Depth 10
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($Path, $json, $utf8NoBom)
}

$UpdatesDir = Join-Path $env:LOCALAPPDATA "VANOVA\updates"
New-Item -ItemType Directory -Force -Path $UpdatesDir | Out-Null

$releaseDir = Join-Path $Root "release"
$latestProd = Join-Path $releaseDir "latest.json"
$latestLocal = Join-Path $releaseDir "latest.local.json"

if (-not (Test-Path $latestProd)) {
    throw "Missing $latestProd. Run scripts\release.ps1 first."
}

$manifest = Get-Content $latestProd -Raw -Encoding UTF8 | ConvertFrom-Json
$version = if ($OfferVersion) { $OfferVersion } else { $manifest.version }
$setupExe = Join-Path $releaseDir "VANOVA-Setup-$version.exe"

if (-not (Test-Path $setupExe)) {
    $sourceExe = Join-Path $releaseDir "VANOVA-Setup-$($manifest.version).exe"
    if (-not (Test-Path $sourceExe)) {
        $sourceExe = Join-Path $releaseDir "VANOVA-Setup.exe"
    }
    if (Test-Path $sourceExe) {
        Copy-Item -Force $sourceExe $setupExe
        Write-Host "Prepared test installer: $setupExe (from $sourceExe)" -ForegroundColor Yellow
        Write-Host "  AVISO: copiar un .exe sin rebuild NO cambia version.json interno." -ForegroundColor Yellow
        Write-Host "  Para probar el flujo completo ejecuta: scripts\release.ps1 -Version $version" -ForegroundColor Yellow
    } else {
        throw "Installer not found: $setupExe"
    }
}

$hash = (Get-FileHash $setupExe -Algorithm SHA256).Hash.ToLower()
$size = (Get-Item $setupExe).Length
$fileUrl = "file:///$($setupExe.Replace('\','/'))"

$localManifest = @{
    product = "VANOVA"
    channel = "stable"
    version = $version
    minimumSupportedVersion = $manifest.minimumSupportedVersion
    mandatory = $false
    publishedAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    downloadUrl = $fileUrl
    sha256 = $hash
    size = $size
    signature = ""
    releaseNotes = if ($OfferVersion) {
        @("Local test update ($version) - in-app Refresh, Download, Install flow")
    } else {
        @($manifest.releaseNotes)
    }
    requiredHermes = $manifest.requiredHermes
    dbSchemaVersion = 0
}

Write-JsonNoBom $latestLocal $localManifest

$manifestUrl = "file:///$($latestLocal.Replace('\','/'))"
$configPath = Join-Path $UpdatesDir "updates-config.json"
$config = @{
    channel = "stable"
    autoCheck = $true
    autoDownload = $false
    checkIntervalHours = 4
    postponeHours = 24
    manifestUrl = $manifestUrl
    lastCheck = $null
    postponedVersion = $null
    postponedUntil = $null
}
Write-JsonNoBom $configPath $config

if ($ResetState) {
    $statePath = Join-Path $UpdatesDir "update-state.json"
    Write-JsonNoBom $statePath @{
        state = "idle"
        targetVersion = $null
        packagePath = $null
        error = $null
        postInstallPending = $false
    }
}

Write-Host ""
Write-Host "Local update testing configured:" -ForegroundColor Green
Write-Host "  Manifest: $manifestUrl"
Write-Host "  Installer: $fileUrl"
Write-Host "  Version:  $version"
Write-Host ""
Write-Host "How to test 1.0.1 -> 1.0.2 locally:"
Write-Host "  1. Install VANOVA 1.0.1 from release\baseline\VANOVA-Setup-1.0.1.exe"
Write-Host "  2. Run: scripts\setup-local-updates.ps1 -OfferVersion 1.0.2 -ResetState"
Write-Host "  3. Restart VANOVA"
Write-Host "  4. Wait ~4s for startup check; modal should offer VANOVA 1.0.2"
Write-Host "  5. Ajustes > Actualizaciones: Buscar / Descargar / Reiniciar ahora"
Write-Host ""
Write-Host "Legacy path 1.0.0 -> 1.0.1: use -OfferVersion 1.0.1 with baseline 1.0.0 installed."
Write-Host ""
Write-Host "Optional: set autoDownload=true in updates-config.json to background-download."
