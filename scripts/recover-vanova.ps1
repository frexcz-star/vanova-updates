# Recover VANOVA after a failed/interrupted in-app update.
$ErrorActionPreference = "Continue"
$Root = Split-Path $PSScriptRoot -Parent

Write-Host "[VANOVA Recover] Resetting stuck update state..."
$stateFile = Join-Path $env:LOCALAPPDATA "VANOVA\updates\update-state.json"
if (Test-Path $stateFile) {
    try {
        $state = Get-Content $stateFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $pkg = $state.packagePath
        $state.state = "ready_to_install"
        $state.message = "Instalacion interrumpida — cierra todas las ventanas VANOVA e intenta de nuevo"
        $state.error = $null
        $state.postInstallPending = $false
        $utf8NoBom = New-Object System.Text.UTF8Encoding $false
        [System.IO.File]::WriteAllText($stateFile, ($state | ConvertTo-Json -Depth 8), $utf8NoBom)
        Write-Host "[VANOVA Recover] Update state -> ready_to_install"
        if ($pkg -and (Test-Path $pkg)) {
            Write-Host "[VANOVA Recover] Package still available: $pkg"
        }
    } catch {
        Write-Host "[VANOVA Recover] Could not reset update state: $($_.Exception.Message)"
    }
}

Write-Host "[VANOVA Recover] Restarting runtime..."
& (Join-Path $Root "scripts\restart-vanova-runtime.ps1")
if ($LASTEXITCODE -ne 0) {
    Write-Host "[VANOVA Recover] Runtime restart had issues (exit $LASTEXITCODE)"
}

$vanovaExe = Join-Path $env:LOCALAPPDATA "Programs\VANOVA\VANOVA.exe"
if (Test-Path $vanovaExe) {
    $running = @(Get-Process -Name "VANOVA" -ErrorAction SilentlyContinue)
    if ($running.Count -eq 0) {
        Write-Host "[VANOVA Recover] Launching VANOVA..."
        Start-Process -FilePath $vanovaExe -WorkingDirectory (Split-Path $vanovaExe -Parent)
    } else {
        Write-Host "[VANOVA Recover] VANOVA already running ($($running.Count) process(es))"
    }
} else {
    Write-Host "[VANOVA Recover] VANOVA.exe not found at $vanovaExe"
}

Write-Host "[VANOVA Recover] Done. Open VANOVA and press Ctrl+Shift+R to refresh."
