"""System Analyzer — detects only VANOVA-relevant environment information."""
from __future__ import annotations

import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

from .logger import get_logger
from .paths import app_root, venv_dir

log = get_logger("maios.analyzer", "system-analyzer")


def analyze() -> dict[str, Any]:
    profile = {
        "system": _system_info(),
        "hardware": _hardware_info(),
        "dependencies": _dependency_info(),
        "network": _network_info(),
        "permissions": _permissions_info(),
        "recommendations": [],
        "readyToInstall": False,
    }
    profile["recommendations"] = _recommendations(profile)
    profile["readyToInstall"] = _is_ready(profile)
    log.info("System analysis complete — ready=%s", profile["readyToInstall"])
    return profile


def _system_info() -> dict[str, Any]:
    ver = platform.version()
    release = platform.release()
    return {
        "os": platform.system(),
        "osVersion": f"{platform.system()} {release}",
        "architecture": platform.machine(),
        "username": os.getenv("USERNAME", "user"),
        "compatible": platform.system() == "Windows" and platform.machine().endswith("64"),
        "status": "ok" if platform.system() == "Windows" else "unsupported",
    }


def _hardware_info() -> dict[str, Any]:
    ram_gb = _ram_gb()
    disk_gb = _disk_free_gb()
    return {
        "cpu": platform.processor() or "Unknown CPU",
        "ramGb": ram_gb,
        "ramStatus": "ok" if ram_gb >= 8 else ("warning" if ram_gb >= 4 else "critical"),
        "diskFreeGb": disk_gb,
        "diskStatus": "ok" if disk_gb >= 5 else "warning",
        "gpu": _gpu_name(),
        "status": "ok" if ram_gb >= 4 and disk_gb >= 2 else "warning",
    }


def _dependency_info() -> dict[str, Any]:
    deps: dict[str, dict] = {}

    py_path, py_detail, py_ok = _detect_python()
    deps["python"] = _check_dep("Python 3.11+", py_ok, "required", py_path)
    deps["python"]["detail"] = py_detail
    deps["python"]["ok"] = py_ok
    if py_ok:
        deps["python"]["status"] = "ok"
    elif py_path:
        deps["python"]["status"] = "warning"
        deps["python"]["message"] = "VANOVA will use bundled Python during setup"
    else:
        deps["python"]["status"] = "warning"
        deps["python"]["message"] = "VANOVA will install a bundled Python runtime during setup"

    hermes = shutil.which("hermes")
    deps["hermes"] = _check_dep("Hermes runtime", hermes is not None, "required", hermes or "")
    if not hermes:
        deps["hermes"]["status"] = "warning"
        deps["hermes"]["message"] = "Hermes will be configured during setup"

    node = shutil.which("node")
    deps["node"] = _check_dep("Node.js", node is not None, "optional", node or "")
    if not node:
        deps["node"]["status"] = "optional"
        deps["node"]["message"] = "Bundled in VANOVA Desktop"

    git = shutil.which("git")
    deps["git"] = _check_dep("Git", git is not None, "optional", git or "")
    if not git:
        deps["git"]["status"] = "optional"
        deps["git"]["message"] = "Not required for end users"

    docker = shutil.which("docker")
    deps["docker"] = _check_dep("Docker", docker is not None, "optional", docker or "")
    if not docker:
        deps["docker"]["status"] = "optional"
        deps["docker"]["message"] = "Optional — not required for VANOVA V1"
        deps["docker"]["ok"] = True

    return deps


def _detect_python() -> tuple[str, str, bool]:
    candidates: list[Path | str] = []
    bundled = app_root() / "python" / "python.exe"
    if bundled.exists():
        candidates.append(bundled)
    bundle_root = app_root() / "python-bundle" / "python.exe"
    if bundle_root.exists():
        candidates.append(bundle_root)
    venv_py = venv_dir() / "Scripts" / "python.exe"
    if venv_py.exists():
        candidates.append(venv_py)
    legacy = app_root() / ".venv" / "Scripts" / "python.exe"
    if legacy.exists():
        candidates.append(legacy)
    for name in ("python", "python3"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    candidates.append(sys.executable)

    seen: set[str] = set()
    for candidate in candidates:
        path = str(candidate)
        if path in seen:
            continue
        seen.add(path)
        detail, ok = _python_version_ok(path)
        if ok:
            return path, detail, True
        if detail:
            return path, detail, False
    return "", "Not detected", False


def _python_version_ok(python_path: str) -> tuple[str, bool]:
    try:
        out = subprocess.run(
            [python_path, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        detail = (out.stdout.strip() or out.stderr.strip() or "").strip()
        match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", detail)
        if not match:
            return detail, False
        major, minor = int(match.group(1)), int(match.group(2))
        return detail, (major, minor) >= (3, 11)
    except Exception:
        return "", False


def _network_info() -> dict[str, Any]:
    online = False
    https_ok = False
    try:
        socket.create_connection(("1.1.1.1", 443), timeout=3)
        online = True
    except OSError:
        pass
    try:
        urllib.request.urlopen("https://www.google.com", timeout=5)
        https_ok = True
    except Exception:
        pass
    return {
        "online": online,
        "https": https_ok,
        "status": "ok" if online and https_ok else ("warning" if online else "critical"),
    }


def _permissions_info() -> dict[str, Any]:
    local_app = os.getenv("LOCALAPPDATA", "")
    writable = False
    try:
        test = os.path.join(local_app, "VANOVA", ".perm_test")
        os.makedirs(os.path.dirname(test), exist_ok=True)
        with open(test, "w") as f:
            f.write("ok")
        os.remove(test)
        writable = True
    except OSError:
        pass
    return {"localAppDataWritable": writable, "status": "ok" if writable else "critical"}


def _recommendations(profile: dict) -> list[str]:
    recs = []
    if not profile["system"]["compatible"]:
        recs.append("VANOVA requires Windows 64-bit.")
    if profile["hardware"]["ramGb"] < 8:
        recs.append("8 GB RAM recommended for optimal performance.")
    if not profile["dependencies"].get("python", {}).get("ok"):
        recs.append("VANOVA will install a bundled Python runtime during setup.")
    if not profile["dependencies"].get("hermes", {}).get("ok"):
        recs.append("Hermes will be configured during setup.")
    if not profile["network"]["online"]:
        recs.append("Internet connection required for AI providers and updates.")
    return recs


def _is_ready(profile: dict) -> bool:
    return (
        profile["system"]["compatible"]
        and profile["permissions"]["localAppDataWritable"]
        and profile["network"]["online"]
        and profile["hardware"]["diskFreeGb"] >= 1
    )


def _check_dep(name: str, ok: bool, level: str, path: str) -> dict:
    return {"name": name, "ok": ok, "level": level, "path": path, "status": "ok" if ok else "missing"}


def _ram_gb() -> float:
    if platform.system() != "Windows":
        return 8.0
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(stat)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return round(stat.ullTotalPhys / (1024**3), 1)
    except Exception:
        return 8.0


def _disk_free_gb() -> float:
    try:
        import shutil as sh
        usage = sh.disk_usage(os.getenv("LOCALAPPDATA", "C:\\"))
        return round(usage.free / (1024**3), 1)
    except Exception:
        return 50.0


def _gpu_name() -> str:
    try:
        out = subprocess.run(
            ["wmic", "path", "win32_VideoController", "get", "name"],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        lines = [l.strip() for l in out.stdout.splitlines() if l.strip() and l.strip() != "Name"]
        return lines[0] if lines else "Unknown"
    except Exception:
        return "Unknown"
