# VANOVA External Updater - runs AFTER VANOVA exits to install updates safely.
param(
    [Parameter(Mandatory=$true)][string]$JobFile
)

$ErrorActionPreference = "Continue"

# Heartbeat log before anything else can fail (Electron waits for this line).
$LogDir = Join-Path $env:LOCALAPPDATA "VANOVA\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir "updater.log"
try {
    "$(Get-Date -Format o) VANOVA Updater launching (pid=$PID, job=$JobFile)" | Add-Content -Path $LogFile -Encoding UTF8
} catch { }

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProgressScript = Join-Path $ScriptDir "update-progress.ps1"
if (Test-Path $ProgressScript) {
    try {
        . $ProgressScript
    } catch {
        # Progress UI is optional — never block install
    }
}

$LogDir = Join-Path $env:LOCALAPPDATA "VANOVA\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir "updater.log"

function Log($msg) {
    $line = "$(Get-Date -Format o) $msg"
    try {
        Add-Content -Path $LogFile -Value $line -Encoding UTF8
    } catch { }
}

$MaiosInstallDir = Join-Path $env:LOCALAPPDATA "Programs\VANOVA"
$RuntimePort = 8765
$CloudPort = 8000

function Write-JsonNoBom($Path, $Object) {
    $json = $Object | ConvertTo-Json -Depth 8
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($Path, $json, $utf8NoBom)
}

function Resolve-AppExe($preferred) {
    if ($preferred -and (Test-Path $preferred)) { return $preferred }
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\VANOVA\VANOVA.exe"),
        (Join-Path ${env:ProgramFiles} "VANOVA\VANOVA.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "VANOVA\VANOVA.exe")
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { return $c }
    }
    return $preferred
}

function Read-InstalledVersion {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\VANOVA\resources\vanova\version.json"),
        (Join-Path ${env:ProgramFiles} "VANOVA\resources\vanova\version.json")
    )
    foreach ($vf in $candidates) {
        if (Test-Path $vf) {
            try {
                $data = Get-Content $vf -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($data.version) { return [string]$data.version }
            } catch { }
        }
    }
    return ""
}

function Get-PidsListeningOnPort([int]$Port) {
    $pids = New-Object System.Collections.Generic.HashSet[int]
    try {
        $out = netstat -ano 2>$null
        $needle = ":$Port"
        foreach ($line in $out) {
            if ($line -notmatch "LISTENING") { continue }
            if ($line -notmatch [regex]::Escape($needle)) { continue }
            $parts = ($line -split '\s+') | Where-Object { $_ -ne "" }
            if ($parts.Count -lt 1) { continue }
            $pidText = $parts[-1]
            if ($pidText -match '^\d+$') {
                [void]$pids.Add([int]$pidText)
            }
        }
    } catch { }
    return @($pids)
}

function Stop-ProcessTree([int]$ProcessId, [string]$Reason) {
    if ($ProcessId -le 0) { return $false }
    try {
        $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
        if (-not $proc) { return $false }
        Log "Stopping pid=$ProcessId ($($proc.ProcessName)) - $Reason"
        Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
        try {
            & taskkill /PID $ProcessId /F /T 2>$null | Out-Null
        } catch { }
        return $true
    } catch {
        return $false
    }
}

function Test-IsMaiosRelatedProcess($proc) {
    if (-not $proc) { return $false }
    $name = $proc.ProcessName
    if ($name -eq "VANOVA") { return $true }

    try {
        $cmd = $proc.CommandLine
    } catch {
        $cmd = ""
    }

    if (-not $cmd) {
        try {
            $wmi = Get-CimInstance Win32_Process -Filter "ProcessId=$($proc.Id)" -ErrorAction SilentlyContinue
            if ($wmi) { $cmd = $wmi.CommandLine }
        } catch { }
    }

    if (-not $cmd) { return $false }
    $lower = $cmd.ToLowerInvariant()
    if ($lower -match "launcher\.py") { return $true }
    if ($lower -match "\\vanova\\") { return $true }
    if ($lower -match "maios_app_root") { return $true }
    if ($lower -match "desktop\\runtime") { return $true }
    if ($lower -match "programs\\vanova") { return $true }
    return $false
}

function Stop-MaiosRuntimeProcesses {
    $stopped = 0
    foreach ($port in @($RuntimePort, $CloudPort)) {
        foreach ($procId in (Get-PidsListeningOnPort $port)) {
            if (Stop-ProcessTree $procId "port $port listener") { $stopped++ }
        }
    }

    $pythonNames = @("python", "pythonw", "python3")
    foreach ($name in $pythonNames) {
        Get-Process -Name $name -ErrorAction SilentlyContinue | ForEach-Object {
            if (Test-IsMaiosRelatedProcess $_) {
                if (Stop-ProcessTree $_.Id "VANOVA python runtime") { $stopped++ }
            }
        }
    }

    Get-Process -Name "electron" -ErrorAction SilentlyContinue | ForEach-Object {
        if (Test-IsMaiosRelatedProcess $_) {
            if (Stop-ProcessTree $_.Id "VANOVA electron child") { $stopped++ }
        }
    }

    return $stopped
}

function Stop-MaiosProcesses {
    param([int]$WaitSeconds = 5)

    Log "Stopping VANOVA-related processes (wait up to ${WaitSeconds}s)..."
    $deadline = (Get-Date).AddSeconds($WaitSeconds)

    do {
        $vanova = @(Get-Process -Name "VANOVA" -ErrorAction SilentlyContinue)
        if ($vanova.Count -eq 0) { break }

        foreach ($p in $vanova) {
            Stop-ProcessTree $p.Id "VANOVA.exe"
        }
        try { Set-UpdateProgressStep -StepIndex 1 -Detail "Cerrando VANOVA..." } catch { }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $deadline)

    $remaining = @(Get-Process -Name "VANOVA" -ErrorAction SilentlyContinue)
    if ($remaining.Count -gt 0) {
        Log "Force-killing $($remaining.Count) remaining VANOVA.exe process(es)"
        $remaining | Stop-Process -Force -ErrorAction SilentlyContinue
        foreach ($p in $remaining) {
            try { & taskkill /PID $p.Id /F /T 2>$null | Out-Null } catch { }
        }
    }

    $runtimeStopped = Stop-MaiosRuntimeProcesses
    Log "Stopped $runtimeStopped runtime-related process(es)"

    Start-Sleep -Milliseconds 400

    $stillMaios = @(Get-Process -Name "VANOVA" -ErrorAction SilentlyContinue)
    $stillRuntime = Stop-MaiosRuntimeProcesses
    if ($stillMaios.Count -gt 0 -or $stillRuntime -gt 0) {
        Log "Second pass: VANOVA=$($stillMaios.Count) runtime=$stillRuntime"
        Start-Sleep -Milliseconds 300
        Stop-MaiosRuntimeProcesses | Out-Null
    }
}

function Remove-PendingInstallJob($JobPath) {
    if (-not $JobPath) { return }
    if (Test-Path $JobPath) {
        try {
            Remove-Item -Force $JobPath
            Log "Removed pending install job: $JobPath"
        } catch {
            Log "Could not remove pending install job: $($_.Exception.Message)"
        }
    }
}

function Set-FailedUpdateState($StateFile, $ExitCode, $InstalledVersion, $TargetVersion) {
    if (-not (Test-Path $StateFile)) { return }
    try {
        $state = Get-Content $StateFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $state.state = "failed"
        $state.postInstallPending = $false
        if ($ExitCode -eq 2) {
            $state.message = "No se pudieron reemplazar archivos (VANOVA aun en ejecucion). Cierra VANOVA manualmente e intenta de nuevo."
            $state.error = "Installer exit code 2 - files locked"
        } elseif ($ExitCode -eq -1) {
            $state.message = "Error inesperado durante la instalacion. Vuelve a intentarlo desde Ajustes."
            $state.error = "Updater exception"
        } else {
            $state.message = "El instalador fallo (codigo $ExitCode). Vuelve a intentarlo desde Ajustes."
            $state.error = "Installer exit code $ExitCode"
        }
        if ($InstalledVersion) {
            $state.installedVersion = $InstalledVersion
        }
        if ($TargetVersion) {
            $state.targetVersion = $TargetVersion
        }
        Write-JsonNoBom $StateFile $state
    } catch {
        Log "Could not write failed update state: $($_.Exception.Message)"
    }
}

function Stop-MaiosRuntime {
    Stop-MaiosProcesses -WaitSeconds 8
}

function Safe-ProgressStep {
    param([int]$StepIndex, [string]$Detail)
    try {
        if (Get-Command Set-UpdateProgressStep -ErrorAction SilentlyContinue) {
            Set-UpdateProgressStep -StepIndex $StepIndex -Detail $Detail
        }
    } catch { }
}

function Test-MaiosAlreadyRunning {
    $procs = @(Get-Process -Name "VANOVA" -ErrorAction SilentlyContinue)
    return ($procs.Count -gt 0)
}

function Launch-Maios($appExe) {
    $appExe = Resolve-AppExe $appExe
    if (-not (Test-Path $appExe)) {
        Log "VANOVA.exe not found at $appExe"
        return $false
    }
    if (Test-MaiosAlreadyRunning) {
        Log "VANOVA already running — skipping launch (pids: $((Get-Process -Name VANOVA -ErrorAction SilentlyContinue | ForEach-Object { $_.Id }) -join ', '))"
        return $true
    }
    try {
        Start-Process -FilePath $appExe -WorkingDirectory (Split-Path $appExe -Parent)
        Log "VANOVA launched successfully from $appExe"
        return $true
    } catch {
        Log "Failed to launch VANOVA: $($_.Exception.Message)"
        return $false
    }
}

Log "VANOVA Updater started (pid=${PID}, job=$JobFile)"

$job = $null
$appExe = $null
try {
    if (-not (Test-Path $JobFile)) {
        Log "Job file not found: $JobFile"
        exit 1
    }

    $job = Get-Content $JobFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $installer = $job.installer
    $version = $job.version
    $appExe = Resolve-AppExe $job.appExe

    Log "Job version=$version installer=$installer appExe=$appExe"

    try {
        Start-UpdateProgressWindow -Version $version
        Set-UpdateProgressStep -StepIndex 0 -Detail "Preparando actualizacion..."
    } catch {
        Log "Progress window failed to start: $($_.Exception.Message)"
    }

    if (-not (Test-Path $installer)) {
        Log "Installer not found: $installer"
        try { Close-UpdateProgressWindow } catch { }
        $stateFile = Join-Path $env:LOCALAPPDATA "VANOVA\updates\update-state.json"
        Remove-PendingInstallJob $JobFile
        Set-FailedUpdateState $stateFile 1 (Read-InstalledVersion) $version
        exit 1
    }

    try { Set-UpdateProgressStep -StepIndex 1 -Detail "Esperando a que VANOVA se cierre..." } catch { }
    Stop-MaiosProcesses -WaitSeconds 12

    try { Set-UpdateProgressStep -StepIndex 2 -Detail "Instalando actualizacion..." } catch { }
    $installDir = Split-Path $appExe -Parent
    Log "Running installer silently: $installer (dir=$installDir)"
    $exitCode = -1
    try {
        # NSIS assisted installer requires /D= as the last argument (unquoted).
        $proc = Start-Process -FilePath $installer -ArgumentList "/S", "/D=$installDir" -Wait -PassThru
        $exitCode = if ($proc) { $proc.ExitCode } else { -1 }
    } catch {
        Log "Installer exception: $($_.Exception.Message)"
        $exitCode = -1
    }
    Log "Installer exit code: $exitCode"

    Start-Sleep -Milliseconds 500
    $installedVersion = Read-InstalledVersion
    Log "Installed version after setup: $installedVersion (target=$version)"

    $stateFile = Join-Path $env:LOCALAPPDATA "VANOVA\updates\update-state.json"
    $versionOk = ($installedVersion -eq $version)

    Remove-PendingInstallJob $JobFile

    if ($exitCode -ne 0) {
        Log "Installer failed (exit $exitCode) - relaunching VANOVA so user is not stranded"
        try { Close-UpdateProgressWindow } catch { }
        Set-FailedUpdateState $stateFile $exitCode $installedVersion $version
        Launch-Maios $appExe | Out-Null
        exit $exitCode
    }

    if (-not $versionOk) {
        Log "Version mismatch after install - expected $version got $installedVersion - relaunching VANOVA"
        try { Close-UpdateProgressWindow } catch { }
        if (Test-Path $stateFile) {
            $state = Get-Content $stateFile -Raw -Encoding UTF8 | ConvertFrom-Json
            $state.state = "failed"
            $state.postInstallPending = $false
            $state.message = "La instalacion no aplico la version $version (sigue en $installedVersion). Vuelve a descargar e instalar."
            $state.error = "Version mismatch after install"
            Write-JsonNoBom $stateFile $state
        }
        Launch-Maios $appExe | Out-Null
        exit 3
    }

    try { Set-UpdateProgressStep -StepIndex 3 -Detail "Reiniciando VANOVA..." } catch { }
    Log "Installer completed - version $installedVersion verified - launching VANOVA once"
    Launch-Maios $appExe | Out-Null
    try { Close-UpdateProgressWindow } catch { }

    if (Test-Path $stateFile) {
        $state = Get-Content $stateFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $state.postInstallPending = $true
        $state.state = "verifying_install"
        $state.message = "Verificando instalacion..."
        $state.error = $null
        Write-JsonNoBom $stateFile $state
    }

    Log "Updater finished OK"
    exit 0
} catch {
    Log "Updater failed: $($_.Exception.Message)"
    try { Close-UpdateProgressWindow } catch { }
    $stateFile = Join-Path $env:LOCALAPPDATA "VANOVA\updates\update-state.json"
    Remove-PendingInstallJob $JobFile
    Set-FailedUpdateState $stateFile -1 (Read-InstalledVersion) ($job.version)
    Launch-Maios (Resolve-AppExe $appExe) | Out-Null
    exit 1
}
