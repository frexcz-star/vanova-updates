# VANOVA Remote Publish - genera latest.json apuntando a un host publico real (HTTPS).
# Uso:
#   .\scripts\publish-remote.ps1 -PublicUrl "https://mi-host.com/vanova"
#   .\scripts\publish-remote.ps1 -PublicUrl "https://abc-xyz.trycloudflare.com"
#   (la URL base debe servir VANOVA-Setup-<version>.exe y latest.json)
param(
    [Parameter(Mandatory=$true)][string]$PublicUrl,
    [string]$Version = "",
    # Transition mode: let the old tunnel announce an installer hosted on the
    # new stable GitHub Releases channel.
    [string]$DownloadUrl = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not $Version) {
    $Version = (Get-Content (Join-Path $Root "version.json") -Raw -Encoding UTF8 | ConvertFrom-Json).version
}

$PublicUrl = $PublicUrl.TrimEnd('/')
if (-not $PublicUrl.StartsWith("https://") -and -not $PublicUrl.StartsWith("http://")) {
    throw "PublicUrl debe empezar por https:// (el validador de VANOVA exige HTTPS en downloadUrl)"
}

$releaseDir = Join-Path $Root "release"
$setupSrc = Join-Path $releaseDir "VANOVA-Setup.exe"
$setupDest = Join-Path $releaseDir "VANOVA-Setup-$Version.exe"

if (-not (Test-Path $setupSrc)) { throw "No existe $setupSrc - primero ejecuta el build (npm run desktop:installer en desktop/) " }
if (-not (Test-Path $setupDest)) { Copy-Item -Force $setupSrc $setupDest }

Write-Host "Publicando VANOVA $Version en $PublicUrl" -ForegroundColor Cyan

# Checksums
node (Join-Path $Root "scripts\generate-checksums.js") | Out-Null

# Hash + size del instalador
$hash = (Get-FileHash $setupDest -Algorithm SHA256).Hash.ToLower()
$size = (Get-Item $setupDest).Length

# Notas: tomar del latest.json existente si ya tiene releaseNotes
$oldManifest = $null
$oldManifestPath = Join-Path $releaseDir "latest.json"
if (Test-Path $oldManifestPath) {
    try { $oldManifest = Get-Content $oldManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json } catch {}
}
$notes = @("VANOVA $Version release")
if ($oldManifest -and $oldManifest.releaseNotes -and $oldManifest.releaseNotes.Count) {
    $notes = @($oldManifest.releaseNotes)
}

$manifest = @{
    product = "VANOVA"
    channel = "stable"
    version = $Version
    minimumSupportedVersion = "0.9.0"
    mandatory = $false
    publishedAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    downloadUrl = if ($DownloadUrl) { $DownloadUrl.Trim() } else { "$PublicUrl/VANOVA-Setup-$Version.exe" }
    sha256 = $hash
    size = $size
    signature = ""
    releaseNotes = $notes
    requiredHermes = ">=1.0.0"
    dbSchemaVersion = 0
}

$json = $manifest | ConvertTo-Json -Depth 6
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText((Join-Path $releaseDir "latest.json"), $json, $utf8NoBom)

# latest.local.json: apuntar a file:// local (dev en esta maquina)
$localManifest = @{}
foreach ($key in $manifest.Keys) { $localManifest[$key] = $manifest[$key] }
$localManifest.downloadUrl = "file:///$($setupDest.Replace('\','/'))"
[System.IO.File]::WriteAllText((Join-Path $releaseDir "latest.local.json"), ($localManifest | ConvertTo-Json -Depth 6), $utf8NoBom)

Write-Host ""
Write-Host "OK. Verifica que el host sirve:" -ForegroundColor Green
Write-Host "  $PublicUrl/latest.json"
Write-Host "  $PublicUrl/VANOVA-Setup-$Version.exe"
Write-Host "  Download URL in manifest: $($manifest.downloadUrl)"
Write-Host "  SHA256: $hash"
Write-Host ""
Write-Host "Para el cliente (descarga del instalador), sube $setupDest a tmpfiles:"
Write-Host "  curl -F \"file=@$setupDest\" https://tmpfiles.org/api/v1/upload"
