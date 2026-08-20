# Sync runtime + web fixes to installed VANOVA (no full rebuild).
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$Install = Join-Path $env:LOCALAPPDATA "Programs\VANOVA"
$MaiosDst = Join-Path $Install "resources\vanova"
$AsarPath = Join-Path $Install "resources\app.asar"

if (-not (Test-Path $MaiosDst)) {
  Write-Error "Installed VANOVA not found: $MaiosDst"
}

# Python runtime
$runtimeFiles = @(
  "desktop\runtime\runtime_security.py",
  "desktop\runtime\credential_vault.py",
  "desktop\runtime\rate_limit.py",
  "desktop\runtime\task_store.py",
  "desktop\runtime\task_queue.py",
  "desktop\runtime\agent_architect.py",
  "desktop\runtime\agent_scheduler.py",
  "desktop\runtime\agent_permissions.py",
  "desktop\runtime\policy_engine.py",
  "desktop\runtime\approval_store.py",
  "desktop\runtime\audit_log.py",
  "desktop\runtime\honest_state.py",
  "desktop\runtime\command_center.py",
  "desktop\runtime\autonomy_config.py",
  "desktop\runtime\observability.py",
  "desktop\runtime\diagnostics_service.py",
  "desktop\runtime\backup_service.py",
  "desktop\runtime\integrations_lifecycle.py",
  "desktop\runtime\logger.py",
  "desktop\runtime\updater.py",
  "desktop\runtime\launcher.py",
  "desktop\runtime\config_store.py",
  "desktop\runtime\integrations_store.py",
  "desktop\runtime\install_secrets.py",
  "desktop\runtime\port_utils.py",
  "desktop\runtime\api_server.py",
  "desktop\runtime\hermes_service.py",
  "desktop\runtime\hermes_config.py",
  "desktop\runtime\hermes_chat.py",
  "desktop\runtime\hermes_shopify_setup.py",
  "desktop\runtime\hermes_activity.py",
  "desktop\runtime\hermes_sessions.py",
  "desktop\runtime\process_manager.py",
  "desktop\runtime\python_runtime.py",
  "desktop\runtime\startup_gate.py",
  "desktop\runtime\startup_log.py",
  "desktop\runtime\health_monitor.py",
  "desktop\runtime\ai_providers.py",
  "desktop\runtime\business_scanner.py",
  "desktop\runtime\file_inventory.py",
  "desktop\runtime\file_organizer.py",
  "desktop\runtime\shopify_sync.py",
  "connector\connector.py",
  "cloud\main.py",
  "cloud\auth_session.py",
  "cloud\rbac.py",
  "cloud\tenancy.py",
  "shared\version_info.py",
  "desktop\runtime\integrations_store.py",
  "desktop\runtime\update\update_manager.py",
  "desktop\runtime\update\manifest_provider.py",
  "desktop\runtime\update\state_store.py",
  "desktop\runtime\update\downloader.py",
  "desktop\runtime\update\backup.py",
  "desktop\runtime\update\semver.py",
  "desktop\runtime\update\state_machine.py"
)
foreach ($rel in $runtimeFiles) {
  $src = Join-Path $Root $rel
  $dst = Join-Path $MaiosDst $rel
  if (Test-Path $src) {
    Copy-Item -Force $src $dst
    Write-Host "OK $rel"
  }
}

# Version manifest (UI + updater read resources/vanova/version.json)
$versionSrc = Join-Path $Root "version.json"
if (Test-Path $versionSrc) {
  Copy-Item -Force $versionSrc (Join-Path $MaiosDst "version.json")
  Write-Host "OK version.json"
}

# Web UI (dist)
$webFiles = @("system-status.js", "dashboard.html", "index.html", "data-services.js", "update-center.js", "ux-helpers.js")
$webSrc = Join-Path $Root "web\dist"
$webDst = Join-Path $MaiosDst "web\dist"
foreach ($f in $webFiles) {
  $from = Join-Path $webSrc $f
  if (-not (Test-Path $from)) { $from = Join-Path $Root "web\$f" }
  if (Test-Path $from) {
    Copy-Item -Force $from (Join-Path $webDst $f)
    Copy-Item -Force $from (Join-Path $MaiosDst "web\$f") -ErrorAction SilentlyContinue
    Write-Host "OK web/$f"
  }
}

# Restart helper next to install
$restartScript = Join-Path $Root "scripts\restart-vanova-runtime.ps1"
$restartDst = Join-Path $MaiosDst "scripts\restart-vanova-runtime.ps1"
New-Item -ItemType Directory -Force -Path (Split-Path $restartDst) | Out-Null
Copy-Item -Force $restartScript $restartDst
Write-Host "OK scripts/restart-vanova-runtime.ps1"

# Updater scripts
$updaterDir = Join-Path $MaiosDst "desktop\updater"
New-Item -ItemType Directory -Force -Path $updaterDir | Out-Null
foreach ($f in @("vanova-updater.ps1", "update-progress.ps1")) {
  Copy-Item -Force (Join-Path $Root "desktop\updater\$f") (Join-Path $updaterDir $f)
  Write-Host "OK desktop/updater/$f"
}

# Patch app.asar (main.js + preload.js) for restart-runtime IPC + keep setup UI in sync
$desktopFiles = @("main.js", "preload.js", "ui\index.html", "ui\setup.css", "ui\setup.js", "ui\loading.html", "ui\error.html")
foreach ($uf in @("ui\index.html", "ui\setup.css", "ui\setup.js", "ui\loading.html", "ui\error.html")) {
  $srcUi = Join-Path $Root ("desktop\" + $uf)
  $dstUi = Join-Path $MaiosDst ("desktop\" + $uf)
  if (Test-Path $srcUi) {
    New-Item -ItemType Directory -Force -Path (Split-Path $dstUi) | Out-Null
    Copy-Item -Force $srcUi $dstUi
    Write-Host "OK desktop/$uf"
  }
}
$asarTmp = Join-Path $env:TEMP "vanova-asar-patch"
if (Test-Path $asarTmp) { Remove-Item -Recurse -Force $asarTmp }
New-Item -ItemType Directory -Force -Path $asarTmp | Out-Null

Push-Location $Root
$extractOk = $false
try {
  # Prefer the local @electron/asar (already installed in desktop/node_modules); fall back to npx.
  $asarCli = Join-Path $Root "desktop\node_modules\@electron\asar\bin\asar.js"
  $hasLocal = Test-Path $asarCli
  $extractCmd = if ($hasLocal) { "node `"$asarCli`" extract `"$AsarPath`" `"$asarTmp`"" } else { "npx --yes @electron/asar extract `"$AsarPath`" `"$asarTmp`"" }
  Invoke-Expression $extractCmd 2>$null
  if ($LASTEXITCODE -eq 0 -and (Test-Path (Join-Path $asarTmp "main.js"))) { $extractOk = $true }
  if (-not $extractOk -and -not $hasLocal) {
    npx --yes asar extract $AsarPath $asarTmp 2>$null
    if ($LASTEXITCODE -eq 0 -and (Test-Path (Join-Path $asarTmp "main.js"))) { $extractOk = $true }
  }
  if (-not $extractOk) {
    Write-Warning "app.asar patch skipped (extract failed) - run manual asar pack or reinstall VANOVA"
  } else {
    foreach ($f in $desktopFiles) {
      Copy-Item -Force (Join-Path $Root "desktop\$f") (Join-Path $asarTmp $f)
      Write-Host "OK asar/$f"
    }
    $bak = "$AsarPath.bak"
    if (-not (Test-Path $bak)) { Copy-Item $AsarPath $bak }
    $packOk = $false
    $packCmd = if ($hasLocal) { "node `"$asarCli`" pack `"$asarTmp`" `"$AsarPath`"" } else { "npx --yes @electron/asar pack `"$asarTmp`" `"$AsarPath`"" }
    Invoke-Expression $packCmd 2>$null
    if ($LASTEXITCODE -eq 0) { $packOk = $true }
    if (-not $packOk -and -not $hasLocal) {
      npx --yes asar pack $asarTmp $AsarPath 2>$null
      if ($LASTEXITCODE -eq 0) { $packOk = $true }
    }
    if (-not $packOk) {
      Write-Warning "app.asar repack failed - Electron may still use old quit-for-update logic"
    }
  }
} catch {
  Write-Warning "app.asar patch error: $($_.Exception.Message)"
} finally {
  Pop-Location
  Remove-Item -Recurse -Force $asarTmp -ErrorAction SilentlyContinue
}

Write-Host "Sync complete. Close and reopen VANOVA.exe (or use restart-vanova-runtime.ps1)."
