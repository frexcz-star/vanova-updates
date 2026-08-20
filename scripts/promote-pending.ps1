# Promote pending fixes (release/PENDING.md) into release-notes.md for a new version.
#
# Flow:
#   1. Reads every "- [ ]" item in release/PENDING.md.
#   2. Writes a "# VANOVA <Version>" section at the top of release/release-notes.md
#      with those items (as "- ..." bullets, ready for the manifest).
#   3. Marks the promoted items as "- [x]" in PENDING.md.
#
# release.ps1 already picks up the "# VANOVA <Version>" section for the
# manifest's releaseNotes, so after this you can run:
#   powershell -File scripts/release.ps1 -Version <Version> -SkipTests
#
param(
    [Parameter(Mandatory = $true)][string]$Version
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$pendingPath = Join-Path $Root "release\PENDING.md"
$notesPath = Join-Path $Root "release\release-notes.md"
if (-not (Test-Path $pendingPath)) { throw "release\PENDING.md no existe" }

$utf8NoBom = New-Object System.Text.UTF8Encoding $false

$lines = Get-Content $pendingPath -Encoding UTF8
$bullets = @()
$newLines = @()
foreach ($line in $lines) {
    if ($line -match '^\s*- \[ \]\s+(.+)$') {
        $bullets += "- " + $Matches[1].Trim()
        $newLines += $line -replace '^\s*- \[ \]\s+', '- [x] '
    } else {
        $newLines += $line
    }
}

if (-not $bullets.Count) {
    Write-Host "No hay fixes pendientes en release\PENDING.md - nada que promover."
    exit 0
}

$section = @("# VANOVA $Version", "") + $bullets + @("")
$existing = ""
if (Test-Path $notesPath) {
    $existing = Get-Content $notesPath -Raw -Encoding UTF8
}
[System.IO.File]::WriteAllText(
    $notesPath,
    ($section -join "`n") + "`n" + $existing,
    $utf8NoBom
)
[System.IO.File]::WriteAllText($pendingPath, ($newLines -join "`n"), $utf8NoBom)

Write-Host "Promovidos $($bullets.Count) fixes a release-notes.md para VANOVA $Version"
foreach ($b in $bullets) { Write-Host ("  " + $b) }
