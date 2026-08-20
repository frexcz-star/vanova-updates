# Prepare portable Python bundle for VANOVA Windows installer (build machine only).
#
# SELF-CONTAINED: copies the full standalone CPython (uv build) - python.exe,
# python311.dll, Lib, DLLs, etc. - with NO venv and NO hardcoded build-machine
# paths. A venv here referenced the build machine's uv Python via pyvenv.cfg and
# crashed on clients with exit code 103 ("No python at ...uv/python/..."),
# because that base interpreter does not exist on other machines.
#
# The bundle is used at runtime as resources/vanova/python-bundle/python.exe.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Bundle = Join-Path $Root "desktop\python-bundle"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Build machine requires Python 3.11+ on PATH to create python-bundle"
}

# Resolve the REAL base interpreter (uv standalone build), not a venv redirector.
$basePy = python -c "import sys; print(sys._base_executable)"
if (-not $basePy -or -not (Test-Path $basePy)) { throw "Could not resolve base python: $basePy" }
$baseDir = Split-Path $basePy
$ver = & $basePy -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ([version]"$ver.0" -lt [version]"3.11.0") { throw "Python 3.11+ required, found $ver" }

Write-Host "Copying standalone Python $baseDir -> $Bundle" -ForegroundColor Cyan
if (Test-Path $Bundle) { Remove-Item -Recurse -Force $Bundle }
New-Item -ItemType Directory -Force -Path $Bundle | Out-Null
Copy-Item -Path (Join-Path $baseDir "*") -Destination $Bundle -Recurse -Force

# No venv config may reference the build machine.
$venvCfg = Join-Path $Bundle "pyvenv.cfg"
if (Test-Path $venvCfg) { Remove-Item -Force $venvCfg }

$Py = Join-Path $Bundle "python.exe"
if (-not (Test-Path $Py)) { throw "bundle copy failed: python.exe missing" }

& $Py -m pip install -q --upgrade pip
foreach ($req in @("cloud\requirements.txt", "connector\requirements.txt", "desktop\runtime\requirements.txt")) {
    Write-Host "Installing $req..."
    & $Py -m pip install -q --break-system-packages -r (Join-Path $Root $req)
}

# Verify imports and portability (prefix must be the bundle itself).
$out = & $Py -c "import sys, fastapi, uvicorn, httpx, bcrypt, jose; print(sys.prefix)"
if (-not $out) { throw "bundle verification failed" }
Write-Host "Python bundle ready: $Py" -ForegroundColor Green
Write-Host "  prefix: $out"
if ($out -ne $Bundle) {
    Write-Host "WARNING: prefix $out differs from $Bundle - bundle may not be relocatable" -ForegroundColor Yellow
}
