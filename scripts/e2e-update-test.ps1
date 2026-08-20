# VANOVA E2E Update Test - 0.9.0 to 0.9.1
$ErrorActionPreference = "Stop"
Remove-Item Env:MAIOS_UPDATE_MANIFEST_URL -ErrorAction SilentlyContinue
$Root = "C:\Users\Admin\maios"
$MaiosExe = "$env:LOCALAPPDATA\Programs\VANOVA\VANOVA.exe"
$UpdatesDir = "$env:LOCALAPPDATA\VANOVA\updates"
$LogFile = "$env:LOCALAPPDATA\VANOVA\logs\e2e-update-test.log"

function Log($msg) {
    $line = "$(Get-Date -Format o) $msg"
    Add-Content $LogFile $line
    Write-Host $line
}

New-Item -ItemType Directory -Force -Path (Split-Path $LogFile) | Out-Null
New-Item -ItemType Directory -Force -Path $UpdatesDir | Out-Null

@{
    channel = "stable"
    autoCheck = $true
    autoDownload = $false
    manifestUrl = "file:///$($Root.Replace('\','/'))/release/latest.json"
} | ConvertTo-Json | ForEach-Object {
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText("$UpdatesDir\updates-config.json", $_, $utf8NoBom)
}

@{
    state = "idle"
    message = ""
    postInstallPending = $false
} | ConvertTo-Json | ForEach-Object {
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText("$UpdatesDir\update-state.json", $_, $utf8NoBom)
}

Log "=== E2E Update Test Start ==="

# Kill stale runtime on 8765
Get-Process -Name "VANOVA" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
$pids = Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue | Select-Object -Expand OwningProcess -Unique
foreach ($procId in $pids) { Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2
Remove-Item "$env:LOCALAPPDATA\VANOVA\logs\updater.log" -ErrorAction SilentlyContinue

$verBefore = (Get-Content "$env:LOCALAPPDATA\Programs\VANOVA\resources\vanova\version.json" -Raw -Encoding UTF8 | ConvertFrom-Json).version
Log "Installed version before: $verBefore"
if ($verBefore -ne "0.9.0") { throw "Expected 0.9.0 installed base, got $verBefore" }

Get-Process -Name "VANOVA" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

Log "Starting VANOVA..."
Start-Process -FilePath $MaiosExe | Out-Null

$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $r = Invoke-RestMethod "http://127.0.0.1:8765/api/health" -TimeoutSec 2
        if ($r.status -eq "ok") { $ready = $true; break }
    } catch {}
    Start-Sleep -Seconds 2
}
if (-not $ready) { throw "Runtime API not ready" }
Log "Runtime API ready"

Log "Step 1: Check for updates"
$check = Invoke-RestMethod "http://127.0.0.1:8765/api/updates/check" -Method POST -ContentType "application/json" -Body "{}"
Log "  state=$($check.state) available=$($check.updateAvailable) target=$($check.targetVersion)"
if (-not $check.updateAvailable) { throw "No update available" }

Log "Step 2: Download and verify"
$dl = Invoke-RestMethod "http://127.0.0.1:8765/api/updates/download" -Method POST -ContentType "application/json" -Body "{}"
Log "  state=$($dl.state) message=$($dl.message)"
if ($dl.state -ne "ready_to_install") { throw "Download/verify failed: $($dl.message)" }

Log "Step 3: Install - launching external updater"
$install = Invoke-RestMethod "http://127.0.0.1:8765/api/updates/install" -Method POST -ContentType "application/json" -Body "{}"
Log "  state=$($install.state)"

Log "Quitting VANOVA..."
Get-Process -Name "VANOVA" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

Log "Waiting for updater to complete..."
$deadline = (Get-Date).AddMinutes(5)
$updaterDone = $false
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 3
    if (Test-Path "$env:LOCALAPPDATA\VANOVA\logs\updater.log") {
        $logText = Get-Content "$env:LOCALAPPDATA\VANOVA\logs\updater.log" -Raw -ErrorAction SilentlyContinue
        if ($logText -match "Updater finished OK") { $updaterDone = $true; Log "Updater log: finished OK"; break }
        if ($logText -match "Updater failed") { throw "Updater failed - see updater.log" }
    }
}
if (-not $updaterDone) { throw "Updater did not complete within timeout - no updater.log success" }

Start-Sleep -Seconds 5

$verFile = "$env:LOCALAPPDATA\Programs\VANOVA\resources\vanova\version.json"
$newVer = (Get-Content $verFile -Raw -Encoding UTF8 | ConvertFrom-Json).version
Log "Installed version after update: $newVer"

$ready2 = $false
for ($i = 0; $i -lt 45; $i++) {
    try {
        $r = Invoke-RestMethod "http://127.0.0.1:8765/api/health" -TimeoutSec 2
        if ($r.status -eq "ok") { $ready2 = $true; break }
    } catch {}
    Start-Sleep -Seconds 2
}

if ($ready2) {
    Log "Step 4: Post-update health check"
    Start-Sleep -Seconds 5
    $health = Invoke-RestMethod "http://127.0.0.1:8765/api/health/all" -TimeoutSec 20
    Log "  overall=$($health.overall)"
    $status = Invoke-RestMethod "http://127.0.0.1:8765/api/updates/status"
    Log "  update state=$($status.state) message=$($status.message)"
    if ($status.state -ne "completed") {
        Log "  triggering startup recovery..."
        Invoke-RestMethod "http://127.0.0.1:8765/api/updates/recovery" -Method POST -ContentType "application/json" -Body "{}" | Out-Null
        Start-Sleep -Seconds 3
        $status = Invoke-RestMethod "http://127.0.0.1:8765/api/updates/status"
        Log "  after recovery: state=$($status.state) message=$($status.message)"
    }
} else {
    Log "WARNING: Runtime not up after restart"
}

Log "=== E2E RESULT ==="
$finalState = "unknown"
try { $finalState = (Invoke-RestMethod "http://127.0.0.1:8765/api/updates/status").state } catch {}
if ($newVer -eq "0.9.1" -and $finalState -eq "completed") {
    Log "SUCCESS: Automatic update 0.9.0 -> 0.9.1 completed"
    exit 0
} elseif ($newVer -eq "0.9.1") {
    Log "PARTIAL: Version 0.9.1 but update state=$finalState"
    exit 1
} else {
    Log "FAILED: Expected 0.9.1, got $newVer"
    exit 1
}
