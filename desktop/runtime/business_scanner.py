"""Business Scanner — deep local scan to populate the dashboard with real data."""
from __future__ import annotations

import os
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from . import agent_architect, business_analyst, config_store, hermes_service, system_analyzer


def _app_version() -> str:
    try:
        from shared.version_info import current_version

        return current_version()
    except Exception:
        return "0.0.0"
from .company_profile import load_profile
from .logger import get_logger
from .paths import config_dir

log = get_logger("maios.scanner", "business-scanner")

DATA_EXTENSIONS = {".xlsx", ".xls", ".csv", ".pdf", ".docx", ".doc", ".txt", ".json", ".xml", ".ods"}
DEFAULT_SCAN_DIRS = [
    Path.home() / "Documents",
    Path.home() / "Downloads",
    Path.home() / "Desktop",
    Path.home() / "OneDrive" if (Path.home() / "OneDrive").exists() else None,
]
MAX_SCAN_SECONDS = 120
MAX_FILES = 600
MAX_CANDIDATES = 300
MAX_DEPTH = 8


def scan_dirs() -> list[Path]:
    """Folders to scan: the business folder configured by the owner (if any)
    takes priority; otherwise the default user folders."""
    data = config_store.load()
    custom = data.get("scanFolders") or []
    if isinstance(custom, list):
        paths = [Path(str(p).strip()) for p in custom if str(p or "").strip()]
        existing = [p for p in paths if p.exists()]
        if existing:
            return existing
    return [p for p in DEFAULT_SCAN_DIRS if p is not None and p.exists()]

_scan_lock = threading.Lock()
_scan_running = False
_scan_progress: dict[str, Any] = {
    "status": "idle",
    "step": "",
    "percent": 0,
    "done": True,
    "error": None,
    "completedAt": None,
}


def scan_status() -> dict[str, Any]:
    return dict(_scan_progress)


def run_scan_async(on_complete: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    """Start a background deep scan. Returns immediately with started flag."""
    global _scan_running
    with _scan_lock:
        if _scan_running:
            return {"ok": True, "started": False, "message": "Scan already in progress"}
        _scan_running = True
        _scan_progress.update({
            "status": "running",
            "step": "Iniciando escaneo",
            "percent": 2,
            "done": False,
            "error": None,
        })

    def _run():
        global _scan_running
        try:
            snapshot = run_deep_scan(_report)
            save_scan_results(snapshot)
            _organize_after_scan()
            push_to_cloud(snapshot)
            _scan_progress.update({
                "status": "ok",
                "step": "Escaneo completado",
                "percent": 100,
                "done": True,
                "completedAt": _now(),
            })
            if on_complete:
                on_complete(snapshot)
        except Exception as exc:
            log.error("Deep scan failed: %s", exc)
            _scan_progress.update({
                "status": "error",
                "step": "Error en escaneo",
                "percent": 100,
                "done": True,
                "error": str(exc),
            })
        finally:
            with _scan_lock:
                _scan_running = False

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "started": True}


def run_deep_scan(progress: Callable[[str, int], None] | None = None) -> dict[str, Any]:
    """Run scan synchronously — must finish in ~30s."""
    started = time.monotonic()

    def report(step: str, pct: int):
        if progress:
            progress(step, pct)
        _scan_progress.update({"step": step, "percent": pct, "status": "running", "done": False})

    report("Analizando sistema", 8)
    system = system_analyzer.analyze()
    profile = load_profile()

    report("Escaneando archivos de negocio", 20)
    files = _scan_files(started)
    report("Detectando integraciones", 55)
    integrations = _detect_integrations(files)
    report("Generando perfil del dashboard", 75)
    agents = agent_architect.list_agents()
    recommendations = business_analyst.recommend(profile) if profile.identity.get("name") else []

    snapshot = build_dashboard_snapshot(
        system=system,
        profile=profile,
        files=files,
        integrations=integrations,
        agents=agents,
        recommendations=recommendations,
    )
    report("Guardando resultados", 95)
    return snapshot


def build_dashboard_snapshot(
    *,
    system: dict[str, Any],
    profile: Any,
    files: list[dict[str, Any]],
    integrations: list[dict[str, Any]],
    agents: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
) -> dict[str, Any]:
    company = profile.identity.get("name") or "Tu empresa"
    file_count = len(files)
    connected_sources = _build_sources(files, integrations, agents)
    connected_count = sum(1 for s in connected_sources if s.get("status") == "connected")

    overview = {
        "revenue": None,
        "revenueChange": None,
        "revenueUp": None,
        "orders": None,
        "ordersChange": None,
        "ordersUp": None,
        "grossMargin": None,
        "grossMarginChange": None,
        "grossMarginUp": None,
        "customers": None,
        "customersChange": None,
        "customersUp": None,
        "inventoryValue": None,
        "inventoryChange": None,
        "inventoryUp": None,
        # Scan-derived metrics (shown when revenue is unavailable)
        "filesScanned": file_count,
        "integrationsDetected": len(integrations),
        "agentsConfigured": len(agents),
        "agentsPending": max(0, len(recommendations) - len(agents)),
        "diskFreeGb": system.get("hardware", {}).get("diskFreeGb"),
        "ramGb": system.get("hardware", {}).get("ramGb"),
        "companyName": company,
    }

    priorities = _scan_priorities(company, files, integrations, agents, recommendations)
    hermes = hermes_service.status()
    from . import honest_state

    raw_mode = "real" if file_count > 0 or connected_count > 0 or agents else "partial"
    data_mode = honest_state.normalize_mode(raw_mode, has_local_files=file_count > 0)

    dashboard_agents = [
        {
            "id": a.get("id"),
            "name": a.get("name"),
            "short": (a.get("name") or "")[:2].upper(),
            "color": "#dc2626",
            "status": a.get("status", "idle"),
            "description": a.get("description", ""),
            "currentTask": a.get("statusReason", ""),
            "insightsGenerated": 0,
            "tasksCompleted": 0,
            "lastActivity": "—",
            "autonomyLevel": "auto",
        }
        for a in agents
    ]

    return {
        **honest_state.describe_mode(data_mode),
        "fetchedAt": _now(),
        "overview": overview,
        "priorities": priorities,
        "activity": [{
            "id": "scan-" + str(int(time.time())),
            "agent": "VANOVA Scanner",
            "action": f"Escaneo completado: {file_count} archivos, {len(integrations)} integraciones",
            "status": "completed",
            "timestamp": _now(),
        }],
        "agents": dashboard_agents,
        "decisions": [],
        "automations": [],
        "sources": connected_sources,
        "hermes": {
            "connected": hermes.get("healthy", False),
            "status": "online" if hermes.get("healthy") else "offline",
            "cli": hermes.get("path") or "",
        },
        "setupProgress": {
            "scanComplete": True,
            "agentsConfigured": len(agents) > 0,
            "agentsRecommended": len(recommendations),
            "sourcesConnected": connected_count,
        },
    }


def save_scan_results(snapshot: dict[str, Any]) -> None:
    """Persist scan metadata WITHOUT clobbering the business overview (H2).

    The `dashboardSnapshot` overview is owned by a single writer:
    file_organizer.sync_dashboard_overview() (file organize + Shopify sync).
    A scan must never overwrite synced business metrics with file-scan
    estimates, or the dashboard and Hermes would read two conflicting truths.
    The scan only records metadata and seeds an overview if none exists yet.
    """
    data = config_store.load()
    existing = data.get("dashboardSnapshot")
    if not isinstance(existing, dict):
        existing = {}
    existing["lastScan"] = {
        "completedAt": _now(),
        "dataMode": snapshot.get("dataMode"),
        "fileCount": snapshot.get("overview", {}).get("filesScanned", 0),
        "integrationCount": snapshot.get("overview", {}).get("integrationsDetected", 0),
    }
    if not existing.get("overview"):
        existing["overview"] = snapshot.get("overview") or {}
    if not existing.get("dataMode"):
        existing["dataMode"] = snapshot.get("dataMode")
    config_store.save({"lastScan": existing["lastScan"], "dashboardSnapshot": existing})


def load_local_dashboard() -> dict[str, Any] | None:
    data = config_store.load()
    snapshot = data.get("dashboardSnapshot")
    if isinstance(snapshot, dict) and snapshot.get("dataMode") not in (None, "empty", "mock"):
        return _enrich_snapshot(snapshot, data)
    live = _build_live_snapshot(data)
    return live


def _enrich_snapshot(snapshot: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    """Merge live file/integration counts into saved snapshot."""
    out = dict(snapshot)
    files = data.get("scanFiles") or []
    products = data.get("organizedProducts") or []
    sales = data.get("organizedSales") or []
    overview = dict(out.get("overview") or {})
    if files:
        overview["filesScanned"] = len(files)
    if products:
        overview["productsOrganized"] = len(products)
    if sales:
        overview["orders"] = len(sales)
    out["overview"] = overview
    sources = list(out.get("sources") or [])
    if files and not any(s.get("id") == "files" for s in sources):
        sources.append({
            "id": "files", "name": "Archivos del PC", "status": "connected",
            "source": "Importación local", "recordCount": len(files), "dataMode": "real",
        })
    try:
        from .integrations_store import get_config
        if get_config("shopify").get("connected"):
            found = False
            for s in sources:
                if s.get("id") == "shopify":
                    s["status"] = "connected"
                    s["source"] = "Shopify API"
                    found = True
            if not found:
                sources.append({
                    "id": "shopify", "name": "Shopify", "status": "connected",
                    "source": "Shopify API", "recordCount": len(products), "dataMode": "real",
                })
    except Exception:
        pass
    out["sources"] = sources
    try:
        from . import insight_actions
        actioned = insight_actions.load_all()
        out["priorities"] = [
            p for p in (out.get("priorities") or [])
            if str(p.get("id") or "").strip() not in actioned
        ]
    except Exception:
        pass
    connected = sum(1 for s in sources if s.get("status") == "connected")
    sp = dict(out.get("setupProgress") or {})
    sp["sourcesConnected"] = connected
    out["setupProgress"] = sp
    if files or products or sales or connected:
        out["dataMode"] = "real"
    return out


def _build_live_snapshot(data: dict[str, Any]) -> dict[str, Any] | None:
    files = data.get("scanFiles") or []
    products = data.get("organizedProducts") or []
    sales = data.get("organizedSales") or []
    shopify_ok = False
    try:
        from .integrations_store import get_config
        shopify_ok = bool(get_config("shopify").get("connected"))
    except Exception:
        pass
    if not files and not products and not sales and not shopify_ok:
        return None
    sources: list[dict[str, Any]] = []
    if files:
        sources.append({
            "id": "files", "name": "Archivos del PC", "status": "connected",
            "source": "Importación local", "recordCount": len(files), "dataMode": "real",
        })
    if shopify_ok:
        sources.append({
            "id": "shopify", "name": "Shopify", "status": "connected",
            "source": "Shopify API", "recordCount": len(products), "dataMode": "real",
        })
    if products:
        sources.append({
            "id": "products", "name": "Productos organizados", "status": "connected",
            "source": "Hermes organizer", "recordCount": len(products), "dataMode": "real",
        })
    if sales:
        sources.append({
            "id": "sales", "name": "Ventas organizadas", "status": "connected",
            "source": "Hermes organizer", "recordCount": len(sales), "dataMode": "real",
        })
    return {
        "dataMode": "real",
        "fetchedAt": _now(),
        "overview": {
            "filesScanned": len(files),
            "productsOrganized": len(products),
            "orders": len(sales),
            "integrationsDetected": len(sources),
        },
        "sources": sources,
        "setupProgress": {
            "scanComplete": bool(files),
            "sourcesConnected": sum(1 for s in sources if s.get("status") == "connected"),
        },
    }


def push_to_cloud(snapshot: dict[str, Any]) -> bool:
    try:
        import httpx
    except ImportError:
        log.warning("httpx not installed — cloud push skipped")
        return False
    env = _load_env(config_dir() / "connector.env")
    device_key = env.get("MAIOS_DEVICE_KEY", "")
    owner_token = env.get("MAIOS_OWNER_TOKEN", "")
    cloud_url = env.get("MAIOS_CLOUD_URL", "http://127.0.0.1:8000").rstrip("/")
    if not device_key:
        log.warning("No device key — skipping cloud push")
        return False
    try:
        with httpx.Client(timeout=15.0) as client:
            headers = {"Authorization": f"Device {device_key}"}
            if not _device_online(client, cloud_url, headers, device_key, owner_token):
                log.warning("Device not registered — cloud push skipped (local snapshot saved)")
                return False
            r = client.post(f"{cloud_url}/api/connector/push", json=snapshot, headers=headers)
            if r.status_code == 200:
                log.info("Dashboard snapshot pushed to cloud (dataMode=%s)", snapshot.get("dataMode"))
                files = _files_from_snapshot(snapshot)
                if files:
                    client.post(
                        f"{cloud_url}/api/connector/files",
                        json={"files": files[:200], "count": len(files)},
                        headers=headers,
                    )
                return True
            log.warning("Cloud push failed: HTTP %s", r.status_code)
    except Exception as exc:
        log.warning("Cloud push error: %s", exc)
    return False


def _device_online(client: Any, cloud_url: str, headers: dict[str, str], device_key: str, owner_token: str) -> bool:
    r = client.post(f"{cloud_url}/api/connector/heartbeat", headers=headers)
    if r.status_code == 200:
        return True
    if not owner_token:
        return False
    import socket
    reg = client.post(
        f"{cloud_url}/api/devices/register",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"deviceKey": device_key, "name": socket.gethostname(), "os": "windows", "version": _app_version()},
    )
    if reg.status_code not in (200, 201):
        return False
    check = client.post(f"{cloud_url}/api/connector/heartbeat", headers=headers)
    return check.status_code == 200


def _files_from_snapshot(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    stored = config_store.load().get("scanFiles")
    if isinstance(stored, list):
        return stored
    return []


def _scan_files(started: float) -> list[dict[str, Any]]:
    """Selective scan: folders -> files -> content. Only clearly business files
    are returned; uncertain ones become approval *candidates*."""
    from . import file_relevance

    found: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    # BUG-028: cargar exclusiones para no reintroducir archivos que el usuario
    # eliminó de la vista de Archivos (persisten en scanExclusions).
    _data = config_store.load()
    exclusions = set(
        str(x or "").strip().lower()
        for x in (_data.get("scanExclusions") or [])
        if isinstance(x, str)
    )

    def _record(p: Path, folder_score: int, file_score: int, content_score: int) -> dict[str, Any]:
        try:
            st = p.stat()
        except OSError:
            return {}
        return {
            "path": str(p),
            "name": p.name,
            "ext": p.suffix.lower().lstrip("."),
            "size": st.st_size,
            "modified": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
            "folderScore": folder_score,
            "fileScore": file_score,
            "contentScore": content_score,
        }

    for base in scan_dirs():
        if not base or not base.exists():
            continue
        if time.monotonic() - started > MAX_SCAN_SECONDS:
            break
        try:
            for dirpath, dirnames, filenames in os.walk(base):
                if time.monotonic() - started > MAX_SCAN_SECONDS or len(found) >= MAX_FILES:
                    break
                depth = len(Path(dirpath).relative_to(base).parts)
                if depth > MAX_DEPTH:
                    dirnames.clear()
                    continue
                # Folder pass: prune clearly non-business subtrees, keep the rest.
                kept_dirs = []
                for d in dirnames:
                    if d.startswith("."):
                        continue
                    if file_relevance.score_folder(d) < 0:
                        continue
                    kept_dirs.append(d)
                dirnames[:] = kept_dirs
                folder_score = min(2, file_relevance.score_folder(Path(dirpath).name))

                for name in filenames:
                    if len(found) >= MAX_FILES or time.monotonic() - started > MAX_SCAN_SECONDS:
                        break
                    p = Path(dirpath) / name
                    if p.suffix.lower() not in DATA_EXTENSIONS:
                        continue
                    # BUG-028: saltar archivos que el usuario excluyó (eliminó
                    # de la vista de Archivos). Un scan no debe reintroducirlos.
                    if str(p).strip().lower() in exclusions:
                        continue
                    legacy_reason = file_relevance.legacy_app_artifact({"name": name, "path": str(p)})
                    if legacy_reason:
                        continue
                    key = str(p).lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    file_score = file_relevance.score_file(name)
                    if file_score < 0:
                        continue
                    # Content pass: ALWAYS peek at the file content, even when
                    # the name looks decisive, so business files with neutral
                    # names are still recognized and non-business files with
                    # business-looking names are rejected.
                    snippet = _read_content_snippet(p, p.suffix.lower().lstrip("."))
                    content_score = file_relevance.score_content(snippet)
                    # A clearly non-business name + zero content signals -> skip.
                    if file_score == 0 and content_score == 0:
                        continue
                    record = _record(p, folder_score, file_score, content_score)
                    if not record:
                        continue
                    verdict = file_relevance.classify_scan_record(record)
                    if verdict == "confident":
                        found.append(record)
                    elif verdict == "candidate" and len(candidates) < MAX_CANDIDATES:
                        candidates.append(record)
        except (PermissionError, OSError):
            continue

    _save_scan_files(found)
    _save_candidates(candidates)
    log.info(
        "Scan finished: %d confident file(s), %d candidate(s) for approval",
        len(found),
        len(candidates),
    )
    return found


def _save_scan_files(found: list[dict[str, Any]]) -> None:
    """Persist scanFiles, preserving manual imports and approved candidates."""
    existing = config_store.load().get("scanFiles") or []
    if not isinstance(existing, list):
        existing = []
    preserved = [
        e
        for e in existing
        if isinstance(e, dict)
        and (str(e.get("source") or "") in ("import", "approved") or e.get("userAdded"))
    ]
    by_path = {str(e.get("path") or "").lower(): e for e in found}
    merged = []
    for e in preserved:
        if str(e.get("path") or "").lower() not in by_path:
            merged.append(e)
    merged.extend(found)
    config_store.save({"scanFiles": merged})


def _save_candidates(candidates: list[dict[str, Any]]) -> None:
    """Persist pending file candidates (for the approval flow)."""
    existing = config_store.load().get("fileCandidates") or []
    if not isinstance(existing, list):
        existing = []
    # Fresh candidate list each scan, but never re-surface a path already decided.
    state_by_path = {str(c.get("path") or "").lower(): c.get("decision") for c in existing if isinstance(c, dict)}
    merged = []
    for c in candidates:
        row = dict(c)
        decision = state_by_path.get(str(c.get("path") or "").lower())
        if decision:
            continue  # already decided (approved/rejected)
        row["status"] = "pending"
        row["foundAt"] = _now()
        merged.append(row)
    config_store.save({"fileCandidates": merged})


def _read_content_snippet(path: Path, ext: str, max_bytes: int = 8192) -> str:
    """Content peek for relevance scoring across common business formats.

    Reads more formats (xlsx/xls/csv/ods/pdf/docx/txt/json) and a larger
    window so borderline files get a proper content decision instead of being
    skipped or misclassified.
    """
    try:
        if not path.exists() or not path.is_file():
            return ""
        size = path.stat().st_size
        if size > 12 * 1024 * 1024:
            return ""
        if ext in {"csv", "tsv", "txt"}:
            return path.read_text(encoding="utf-8", errors="ignore")[:max_bytes]
        if ext in {"json", "xml"}:
            return path.read_text(encoding="utf-8", errors="ignore")[:max_bytes]
        if ext in {"xlsx", "xls"}:
            return _peek_xlsx_headers(path, max_chars=max_bytes)
        if ext == "ods":
            return _peek_ods_content(path, max_chars=max_bytes)
        if ext == "docx":
            return _peek_docx_content(path, max_chars=max_bytes)
        if ext == "pdf":
            return _peek_pdf_content(path, max_chars=max_bytes)
        if ext in {"doc"}:
            return _peek_doc_binary(path, max_chars=max_bytes)
    except OSError:
        return ""
    return ""


def _peek_ods_content(path: Path, max_chars: int = 8192) -> str:
    """Read text from an ODS (zip of XML) for relevance scoring."""
    import zipfile
    import xml.etree.ElementTree as ET

    try:
        with zipfile.ZipFile(path, "r") as zf:
            if "content.xml" not in zf.namelist():
                return ""
            raw = zf.read("content.xml")
        root = ET.fromstring(raw)
        texts = [
            (el.text or "").strip()
            for el in root.iter()
            if el.tag.endswith("}text:p") or el.tag.endswith("}text:h")
        ]
        return " | ".join(t for t in texts if t)[:max_chars]
    except Exception:
        return ""


def _peek_docx_content(path: Path, max_chars: int = 8192) -> str:
    """Read text from a DOCX (zip of document.xml) for relevance scoring."""
    import zipfile
    import xml.etree.ElementTree as ET

    try:
        with zipfile.ZipFile(path, "r") as zf:
            if "word/document.xml" not in zf.namelist():
                return ""
            raw = zf.read("word/document.xml")
        root = ET.fromstring(raw)
        texts = []
        for el in root.iter():
            if el.tag.endswith("}t") and el.text:
                texts.append(el.text)
        return " ".join(texts)[:max_chars]
    except Exception:
        return ""


def _peek_pdf_content(path: Path, max_chars: int = 8192) -> str:
    """Extract raw text streams from a PDF (stdlib-only) for scoring."""
    import re

    try:
        raw = path.read_bytes()[:2 * 1024 * 1024]
        # Extract text between parentheses in content streams (best-effort).
        tokens = re.findall(rb"\(([^()]{2,120})\)", raw)
        decoded = []
        for t in tokens[:200]:
            try:
                decoded.append(t.decode("latin-1"))
            except Exception:
                continue
        return " ".join(decoded)[:max_chars]
    except OSError:
        return ""


def _peek_doc_binary(path: Path, max_chars: int = 8192) -> str:
    """Best-effort text extraction from legacy .doc binary files."""
    try:
        raw = path.read_bytes()
        # Skip the OLE header; pull printable ASCII/UTF-8 runs.
        printable = re.findall(rb"[\x20-\x7E]{4,}", raw[512:])
        decoded = " ".join(p.decode("latin-1", errors="ignore") for p in printable[:300])
        return decoded[:max_chars]
    except OSError:
        return ""


def _peek_xlsx_headers(path: Path, max_chars: int = 8192) -> str:
    """Read the shared strings of an xlsx — where column headers usually live."""
    import zipfile

    try:
        with zipfile.ZipFile(path, "r") as zf:
            if "xl/sharedStrings.xml" not in zf.namelist():
                return ""
            raw = zf.read("xl/sharedStrings.xml")
        import xml.etree.ElementTree as ET

        root = ET.fromstring(raw)
        ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        texts = []
        for si in root.findall(".//m:si", ns):
            parts = [t.text or "" for t in si.findall(".//m:t", ns)]
            texts.append("".join(parts))
        return " ".join(texts)[:max_chars]
    except Exception:
        return ""


def _detect_integrations(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    detected: list[dict[str, Any]] = []
    profile = load_profile()
    channels = {c.lower() for c in profile.channels}

    checks = [
        ("shopify", "Shopify", ["shopify", "shopify.exe"], channels),
        ("instagram", "Instagram", ["instagram"], channels),
        ("email", "Email", ["outlook", "thunderbird"], channels),
        ("erp", "ERP / SAP", ["sap", "facturascript"], channels),
        ("drive", "Google Drive", ["google drive"], set()),
        ("mcp", "MCP Servers", ["mcp"], channels),
    ]

    program_dirs = [
        Path(os.getenv("ProgramFiles", "C:\\Program Files")),
        Path(os.getenv("ProgramFiles(x86)", "C:\\Program Files (x86)")),
    ]

    for int_id, label, keywords, hint_channels in checks:
        found_path = ""
        for prog_dir in program_dirs:
            if not prog_dir.exists():
                continue
            try:
                for entry in prog_dir.iterdir():
                    name_lower = entry.name.lower()
                    if any(k in name_lower for k in keywords):
                        found_path = str(entry)
                        break
            except OSError:
                continue
            if found_path:
                break

        file_hint = any(k in f.get("name", "").lower() or k in f.get("path", "").lower() for f in files for k in keywords)
        channel_hint = bool(hint_channels & {int_id}) or int_id in hint_channels
        if found_path or file_hint or channel_hint:
            detected.append({
                "id": int_id,
                "name": label,
                "status": "connected" if found_path else "detected",
                "source": found_path or "archivos locales",
                "recordCount": sum(1 for f in files if any(k in f.get("name", "").lower() for k in keywords)),
                "dataMode": "real",
            })

    if shutil.which("hermes"):
        detected.append({
            "id": "hermes",
            "name": "Hermes Agent",
            "status": "connected" if hermes_service.status().get("healthy") else "detected",
            "source": "local",
            "recordCount": 0,
            "dataMode": "real",
        })

    if files:
        detected.append({
            "id": "files",
            "name": "Archivos del PC",
            "status": "connected",
            "source": "Escaneo local",
            "recordCount": len(files),
            "dataMode": "real",
        })

    return detected


def _build_sources(
    files: list[dict[str, Any]],
    integrations: list[dict[str, Any]],
    agents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    sources = list(integrations)
    if files and not any(s.get("id") == "files" for s in sources):
        sources.append({
            "id": "files",
            "name": "Archivos del PC",
            "status": "connected",
            "source": "Escaneo local",
            "recordCount": len(files),
            "dataMode": "real",
        })
    if not agents:
        sources.append({
            "id": "agents",
            "name": "Agentes de IA",
            "status": "needs_configuration",
            "source": "",
            "recordCount": 0,
            "dataMode": "empty",
        })
    return sources


def _scan_priorities(
    company: str,
    files: list[dict[str, Any]],
    integrations: list[dict[str, Any]],
    agents: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    priorities: list[dict[str, Any]] = []
    now = _now()

    if files:
        by_ext: dict[str, int] = {}
        for f in files:
            ext = f.get("ext", "other")
            by_ext[ext] = by_ext.get(ext, 0) + 1
        top_ext = max(by_ext, key=by_ext.get) if by_ext else "csv"
        priorities.append({
            "id": "scan-files",
            "agent": "VANOVA Scanner",
            "type": "recommendation",
            "priority": "medium",
            "title": f"{len(files)} archivos de negocio detectados en este PC",
            "description": f"Se encontraron datos en formatos {', '.join(sorted(by_ext.keys())[:5])}. "
                           f"El tipo más frecuente es .{top_ext} ({by_ext.get(top_ext, 0)} archivos).",
            "impact": "—",
            "confidence": "100%",
            "recommendation": "Conecta estas fuentes en Integraciones para que los agentes las analicen.",
            "status": "open",
            "createdAt": now,
            "provenance": "OBSERVED",
        })

    if integrations:
        names = ", ".join(i["name"] for i in integrations[:4])
        priorities.append({
            "id": "scan-integrations",
            "agent": "VANOVA Scanner",
            "type": "opportunity",
            "priority": "low",
            "title": f"Integraciones detectadas: {names}",
            "description": "VANOVA identificó software y fuentes locales que pueden alimentar el data lake.",
            "impact": "—",
            "confidence": "—",
            "recommendation": "Revisa Integraciones y confirma la conexión de cada fuente.",
            "status": "open",
            "createdAt": now,
            "provenance": "OBSERVED",
        })

    if not agents and recommendations:
        top = recommendations[0]
        priorities.append({
            "id": "scan-agents",
            "agent": "Agent Architect",
            "type": "recommendation",
            "priority": "high",
            "title": "Configura tus primeros agentes de IA",
            "description": f"Recomendamos empezar con {top.get('name', 'un agente')} según tu perfil de empresa.",
            "impact": "—",
            "confidence": "—",
            "recommendation": top.get("reason", "Completa la configuración de agentes en el asistente."),
            "status": "open",
            "createdAt": now,
            "provenance": "OBSERVED",
        })

    # Scanner priorities are insights too. Apply the same durable action store
    # before exposing the snapshot so a later scan cannot resurrect a decision.
    try:
        from . import insight_actions
        actioned = insight_actions.load_all()
        priorities = [
            p for p in priorities
            if str(p.get("id") or "").strip() not in actioned
        ]
    except Exception:
        # A broken action file must not take down the business scan; the UI will
        # still apply its defensive action-map filter.
        pass
    return priorities


def _report(step: str, pct: int) -> None:
    _scan_progress.update({"step": step, "percent": pct, "status": "running", "done": False})


def _load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def _organize_after_scan() -> None:
    try:
        from . import file_organizer

        file_organizer.organize_files()
    except Exception as exc:
        log.warning("Post-scan file organization failed: %s", exc)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_imported_files() -> dict[str, Any]:
    from .file_inventory import list_imported_files as _list

    return _list()


def add_imported_file(entry: dict[str, Any]) -> dict[str, Any]:
    from .file_inventory import add_imported_file as _add

    return _add(entry)


def remove_imported_file(path: str) -> dict[str, Any]:
    from .file_inventory import remove_imported_file as _remove

    return _remove(path)
