# VANOVA GitHub Releases publisher.
#
# The source code stays in the private project checkout. This repository contains
# only release assets (the installer and latest.json), so the app can update from
# a stable URL without depending on a local tunnel.
#
# Prepare files for manual upload:
#   powershell -ExecutionPolicy Bypass -File scripts/publish-github-release.ps1
#
# Upload automatically with a GitHub token:
#   $env:GITHUB_TOKEN = "..."
#   powershell -ExecutionPolicy Bypass -File scripts/publish-github-release.ps1 -Upload
param(
    [string]$Owner = "frexcz-star",
    [string]$Repository = "vanova-updates",
    [string]$Version = "",
    [switch]$Upload
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not $Version) {
    $Version = (Get-Content (Join-Path $Root "version.json") -Raw -Encoding UTF8 | ConvertFrom-Json).version
}

$releaseDir = Join-Path $Root "release"
$sourceInstaller = Join-Path $releaseDir "VANOVA-Setup.exe"
$versionedInstaller = Join-Path $releaseDir "VANOVA-Setup-$Version.exe"
if (-not (Test-Path $sourceInstaller) -and -not (Test-Path $versionedInstaller)) {
    throw "No existe el instalador. Ejecuta primero npm run desktop:installer en desktop/."
}
if (-not (Test-Path $versionedInstaller)) {
    Copy-Item -Force $sourceInstaller $versionedInstaller
}

$sha256 = (Get-FileHash $versionedInstaller -Algorithm SHA256).Hash.ToLower()
$size = (Get-Item $versionedInstaller).Length
$tag = "v.$Version"
$assetName = "VANOVA-Setup-$Version.exe"
$downloadUrl = "https://github.com/$Owner/$Repository/releases/download/$tag/$assetName"
$manifestUrl = "https://github.com/$Owner/$Repository/releases/latest/download/latest.json"

$notes = @("VANOVA $Version - canal estable de actualizaciones por GitHub Releases.")
$existingManifest = Join-Path $releaseDir "latest.json"
if (Test-Path $existingManifest) {
    try {
        $old = Get-Content $existingManifest -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($old.releaseNotes -and $old.releaseNotes.Count) {
            $notes = @($old.releaseNotes)
        }
    } catch {
        Write-Warning "No se pudieron reutilizar las release notes anteriores."
    }
}

$manifest = [ordered]@{
    product = "VANOVA"
    channel = "stable"
    version = $Version
    minimumSupportedVersion = "0.9.0"
    mandatory = $false
    publishedAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    downloadUrl = $downloadUrl
    sha256 = $sha256
    size = $size
    signature = ""
    releaseNotes = $notes
    requiredHermes = ">=1.0.0"
    dbSchemaVersion = 0
}

$preparedDir = Join-Path $releaseDir "github"
New-Item -ItemType Directory -Force -Path $preparedDir | Out-Null
$manifestPath = Join-Path $preparedDir "latest.json"
# Windows PowerShell's `Set-Content -Encoding UTF8` writes a BOM. The updater
# reads the public manifest as UTF-8, so always emit BOM-free UTF-8 JSON.
$manifestJson = $manifest | ConvertTo-Json -Depth 8
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($manifestPath, $manifestJson, $utf8NoBom)

Write-Host "VANOVA $Version preparado para GitHub Releases" -ForegroundColor Cyan
Write-Host "  Repositorio: https://github.com/$Owner/$Repository"
Write-Host "  Tag:         $tag"
Write-Host "  Installer:   $versionedInstaller"
Write-Host "  Manifest:    $manifestPath"
Write-Host "  SHA256:      $sha256"
Write-Host "  Tamano:      $size bytes"
Write-Host "  URL estable: $manifestUrl"
Write-Host ""

if (-not $Upload) {
    Write-Host "Subida manual (sin subir codigo fuente):" -ForegroundColor Yellow
    Write-Host "  1. Abre https://github.com/$Owner/$Repository/releases/new"
    Write-Host "  2. Tag: $tag"
    Write-Host "  3. Sube estos DOS archivos como assets:"
    Write-Host "       $versionedInstaller"
    Write-Host "       $manifestPath"
    Write-Host "  4. Publica la release (no marques Draft ni Pre-release)."
    Write-Host ""
    Write-Host "Despues verifica: $manifestUrl"
    exit 0
}

$token = ""
if ($env:GITHUB_TOKEN) {
    $token = $env:GITHUB_TOKEN.Trim()
}
# setx stores the token in the Windows user environment. A long-running
# desktop shell may not have inherited that refreshed environment yet, so use
# the user scope as a safe fallback without ever printing the token.
if (-not $token) {
    $token = [Environment]::GetEnvironmentVariable("GITHUB_TOKEN", "User")
    if ($token) { $token = $token.Trim() }
}
if (-not $token) {
    throw "-Upload necesita GITHUB_TOKEN con permiso Contents: write. No pongas el token en el codigo ni lo compartas por chat."
}

$api = "https://api.github.com/repos/$Owner/$Repository"
$headers = @{
    Authorization = "Bearer $token"
    Accept = "application/vnd.github+json"
    "X-GitHub-Api-Version" = "2022-11-28"
    "User-Agent" = "VANOVA-release-publisher"
}

$release = $null
try {
    $release = Invoke-RestMethod -Method Get -Uri "$api/releases/tags/$tag" -Headers $headers
} catch {
    $bodyJson = @{
        tag_name = $tag
        name = "VANOVA $Version"
        body = ($notes -join "`n")
        draft = $false
        prerelease = $false
    } | ConvertTo-Json -Depth 5
    # Windows PowerShell 5.1 can send a string body as UTF-16; GitHub then
    # reports "Problems parsing JSON". Send explicit UTF-8 bytes instead.
    $bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($bodyJson)
    $release = Invoke-RestMethod -Method Post -Uri "$api/releases" -Headers $headers -ContentType "application/json; charset=utf-8" -Body $bodyBytes
}

$assets = @(Invoke-RestMethod -Method Get -Uri "$api/releases/$($release.id)/assets" -Headers $headers)
# Windows PowerShell 5.1 can adapt a JSON array as one object whose `name`
# and `id` properties are arrays. Iterate by index so replacement uploads do
# not fail with GitHub's already_exists response.
$assetIds = @($assets.id)
$assetNames = @($assets.name)
for ($i = 0; $i -lt $assetIds.Count; $i++) {
    if ($assetNames[$i] -in @($assetName, "latest.json")) {
        Invoke-RestMethod -Method Delete -Uri "$api/releases/assets/$($assetIds[$i])" -Headers $headers | Out-Null
    }
}

foreach ($file in @($versionedInstaller, $manifestPath)) {
    $name = Split-Path -Leaf $file
    $uploadUrl = "https://uploads.github.com/repos/$Owner/$Repository/releases/$($release.id)/assets?name=$([uri]::EscapeDataString($name))"
    # Read with FileShare.ReadWrite: an installer can be inspected by Windows
    # Defender or an open setup process while it is being published.
    $stream = New-Object System.IO.FileStream($file, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
    try {
        $bytes = New-Object byte[] ([int]$stream.Length)
        $offset = 0
        while ($offset -lt $bytes.Length) {
            $read = $stream.Read($bytes, $offset, $bytes.Length - $offset)
            if ($read -le 0) { throw "No se pudo leer completamente $file" }
            $offset += $read
        }
    } finally {
        $stream.Dispose()
    }
    Invoke-WebRequest -Method Post -Uri $uploadUrl -Headers $headers -ContentType "application/octet-stream" -Body $bytes -UseBasicParsing | Out-Null
    Remove-Variable bytes -ErrorAction SilentlyContinue
    Write-Host "Subido: $name" -ForegroundColor Green
}

Write-Host "Release publicada: https://github.com/$Owner/$Repository/releases/tag/$tag" -ForegroundColor Green
Write-Host "Manifest estable: $manifestUrl" -ForegroundColor Green
