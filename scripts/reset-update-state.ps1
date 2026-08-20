# Reset VANOVA update state to idle (fixes stuck update after failed 0.9.3 flow)
param([switch]$WhatIf)

$statePath = Join-Path $env:LOCALAPPDATA "VANOVA\updates\update-state.json"
$dir = Split-Path $statePath -Parent

if (-not (Test-Path $dir)) {
    Write-Host "No updates directory: $dir"
    exit 0
}

$idle = @{
    state = "idle"
    targetVersion = $null
    packagePath = $null
    error = $null
    postInstallPending = $false
} | ConvertTo-Json -Depth 5

if ($WhatIf) {
    Write-Host "Would write idle state to: $statePath"
    Write-Host $idle
    exit 0
}

try {
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($statePath, $idle, $utf8NoBom)
    Write-Host "Update state reset to idle: $statePath"
} catch {
    Write-Warning "Could not reset update state: $_"
    exit 1
}