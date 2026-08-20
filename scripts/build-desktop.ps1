# VANOVA Desktop Build Scripts

param(
    [ValidateSet("dev", "build", "installer", "release")]
    [string]$Target = "installer"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Desktop = Join-Path $Root "desktop"

Push-Location $Desktop
try {
    if (-not (Test-Path "node_modules")) {
        Write-Host "Installing npm dependencies..."
        npm install
        if (Test-Path "node_modules\electron\install.js") {
            node node_modules\electron\install.js
        }
    }

    switch ($Target) {
        "dev"       { npm run desktop:dev }
        "build"     { npm run desktop:build }
        "installer" { npm run desktop:installer }
        "release"   { npm run release }
    }
} finally {
    Pop-Location
}

if ($Target -eq "installer" -or $Target -eq "release") {
    $setup = Join-Path $Root "release\VANOVA-Setup.exe"
    if (Test-Path $setup) {
        Write-Host ""
        Write-Host "============================================"
        Write-Host " VANOVA-Setup.exe ready:"
        Write-Host " $setup"
        Write-Host "============================================"
    }
}
