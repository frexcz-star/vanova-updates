"""Integration Providers — real connection logic for Gmail, Google Drive and
FacturaScript (web API or local files).

Only stdlib + httpx are used: Gmail goes through imaplib/smtplib, Drive and
FacturaScript through httpx against their public REST APIs. Every function
returns a structured dict ({"ok": bool, "error": str|None, ...}) instead of
raising, so the UI and Hermes always get a clear message.
"""
from __future__ import annotations

import imaplib
import os
import ssl
from pathlib import Path
from typing import Any

import httpx

from .logger import get_logger

log = get_logger("maios.integrations", "integration-providers")

GMAIL_IMAP_HOST = "imap.gmail.com"
GMAIL_IMAP_PORT = 993
GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587

DRIVE_API = "https://www.googleapis.com/drive/v3"

# FASE 4: la API REST de FacturaScripts vive en /api/3 y se autentica con el
# header `Token` (verificado contra la documentación oficial). Las rutas
# antiguas se conservan solo como fallback de detección.
FACTURASCRIPT_API_PATHS = (
    "/api/3/",
    "/api/v1/status",
    "/api/v1/info",
    "/index.php",
    "/",
)


def get_providers() -> list[dict[str, Any]]:
    """Metadata of the connectable integrations."""
    return [
        {
            "id": "gmail",
            "nombre": "Gmail",
            "descripcion": "Correo electrónico: leer bandeja, buscar facturas y pedidos, responder con plantillas.",
            "tipo": "email",
            "requiereOauth": False,
            "modoWeb": True,
            "modoLocal": False,
            "campos": [
                {"key": "user", "label": "Correo de Gmail", "placeholder": "tu.correo@gmail.com", "type": "email"},
                {"key": "app_password", "label": "Contraseña de aplicación", "placeholder": "xxxx xxxx xxxx xxxx", "type": "password"},
            ],
            "ayuda": "Activa la verificación en 2 pasos en Google y crea una contraseña de aplicación en myaccount.google.com/apppasswords.",
        },
        {
            "id": "drive",
            "nombre": "Google Drive",
            "descripcion": "Almacenamiento en la nube: indexar archivos de la empresa, hojas de cálculo y documentos.",
            "tipo": "cloud",
            "requiereOauth": True,
            "modoWeb": True,
            "modoLocal": False,
            "campos": [
                {"key": "access_token", "label": "Access token de Google", "placeholder": "ya29...", "type": "password"},
            ],
            "ayuda": "Genera un token con un proyecto de Google Cloud (Drive API activada) o pide a Hermes que te guíe.",
        },
        {
            "id": "facturascript",
            "nombre": "FacturaScript",
            "descripcion": "ERP de facturación: clientes, albaranes, facturas y proveedores. Soporta la API web self-hosted o la base de datos local.",
            "tipo": "erp",
            "requiereOauth": False,
            "modoWeb": True,
            "modoLocal": True,
            "campos": [
                {"key": "base_url", "label": "URL de la instalación (web)", "placeholder": "https://facturas.miempresa.com", "type": "url"},
                {"key": "api_key", "label": "API key", "placeholder": "Clave de la API REST", "type": "password"},
                {"key": "db_path", "label": "Ruta de la base local (opcional)", "placeholder": "C:\\facturascript\\db", "type": "text"},
            ],
            "ayuda": "En FacturaScript activa la API REST (panel → API) y genera una clave. Para modo local indica la carpeta de la instalación.",
        },
    ]


def _provider_meta(integration_id: str) -> dict[str, Any] | None:
    iid = str(integration_id or "").strip().lower()
    for p in get_providers():
        if p["id"] == iid:
            return p
    return None


def test_connection(integration_id: str, config: dict[str, Any], mode: str = "web") -> dict[str, Any]:
    """Test a connection with the given config without persisting anything."""
    # Excluded from pytest collection (name looks like a test).
    test_connection.__test__ = False  # type: ignore[attr-defined]
    iid = str(integration_id or "").strip().lower()
    cfg = config if isinstance(config, dict) else {}
    mode = str(mode or "web").strip().lower()

    if iid == "gmail":
        res = connect_gmail(cfg)
    elif iid == "drive":
        res = connect_drive(cfg)
    elif iid == "facturascript":
        res = connect_facturascript(cfg, mode=mode)
    else:
        return {"ok": False, "error": f"Integración desconocida: {iid}", "detail": ""}
    return res


def _safe(detail: str) -> str:
    return (detail or "").strip()


# ---------------------------------------------------------------------------
# Gmail (IMAP/SMTP — contraseña de aplicación u OAuth2)
# ---------------------------------------------------------------------------
def connect_gmail(config: dict[str, Any]) -> dict[str, Any]:
    user = str(config.get("user") or config.get("email") or "").strip()
    app_password = str(config.get("app_password") or config.get("password") or "").strip()
    access_token = str(config.get("access_token") or "").strip()

    if not user:
        return {"ok": False, "error": "Falta el correo de Gmail", "detail": "user"}
    if not app_password and not access_token:
        return {"ok": False, "error": "Falta la contraseña de aplicación o el access token", "detail": "app_password"}

    try:
        ctx = ssl.create_default_context()
        mail = imaplib.IMAP4_SSL(GMAIL_IMAP_HOST, GMAIL_IMAP_PORT, ssl_context=ctx)
        if getattr(mail, "sock", None) is not None:
            try:
                mail.sock.settimeout(20)
            except Exception:
                pass
        try:
            if access_token:
                # XOAUTH2: user + access token (sin dependencias externas).
                auth_string = f"user={user}\x01auth=Bearer {access_token}\x01\x01"
                mail.authenticate("XOAUTH2", lambda x: auth_string.encode("utf-8"))
            else:
                mail.login(user, app_password)
            mail.select("INBOX", readonly=True)
            typ, data = mail.list()
            folders: list[str] = []
            if typ == "OK":
                for item in data or []:
                    raw = item.decode("utf-8", "replace") if isinstance(item, bytes) else str(item)
                    # The folder name is the last quoted segment.
                    if '"' in raw:
                        folders.append(raw.rsplit('"', 2)[-2])
                    else:
                        folders.append(raw.strip())
            mail.logout()
            return {
                "ok": True,
                "error": None,
                "detail": "Login IMAP correcto en Gmail",
                "folders": folders[:20] or ["INBOX"],
                "host": GMAIL_IMAP_HOST,
            }
        except imaplib.IMAP4.error as exc:
            mail.logout()
            msg = str(exc)
            if "Application-specific password" in msg or "Invalid credentials" in msg:
                return {
                    "ok": False,
                    "error": "Credenciales de Gmail incorrectas. Revisa que uses una contraseña de aplicación, no la normal.",
                    "detail": _safe(msg),
                }
            if "Authentication" in msg or "login" in msg.lower():
                return {
                    "ok": False,
                    "error": "Gmail rechazó la autenticación. Activa la verificación en 2 pasos y genera una contraseña de aplicación.",
                    "detail": _safe(msg),
                }
            return {"ok": False, "error": "Error de autenticación con Gmail", "detail": _safe(msg)}
    except (ssl.SSLError, OSError) as exc:
        return {"ok": False, "error": "No se pudo conectar con el servidor de Gmail", "detail": _safe(str(exc))}
    except Exception as exc:
        return {"ok": False, "error": "Error inesperado conectando con Gmail", "detail": _safe(str(exc))}


# ---------------------------------------------------------------------------
# Google Drive (REST API v3)
# ---------------------------------------------------------------------------
def connect_drive(config: dict[str, Any]) -> dict[str, Any]:
    token = str(config.get("access_token") or "").strip()
    refresh_token = str(config.get("refresh_token") or "").strip()
    client_id = str(config.get("client_id") or "").strip()
    client_secret = str(config.get("client_secret") or "").strip()

    if not token and not (refresh_token and client_id and client_secret):
        return {
            "ok": False,
            "error": "Falta el access token (o refresh token + client id/secret) de Google",
            "detail": "access_token",
        }

    try:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        with httpx.Client(timeout=15) as client:
            if not token:
                # Refresh the token with the OAuth2 token endpoint.
                r = client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": client_id,
                        "client_secret": client_secret,
                    },
                )
                if r.status_code != 200:
                    return {
                        "ok": False,
                        "error": "No se pudo renovar el token de Google (refresh token inválido)",
                        "detail": _safe(r.text[:200]),
                    }
                token = str((r.json() or {}).get("access_token") or "")
                headers = {"Authorization": f"Bearer {token}"}

            about = client.get(f"{DRIVE_API}/about", params={"fields": "user,storageQuota"}, headers=headers)
            if about.status_code == 401:
                return {"ok": False, "error": "El token de Google ha caducado o no es válido", "detail": "HTTP 401"}
            if about.status_code != 200:
                return {"ok": False, "error": "Google Drive rechazó la petición", "detail": f"HTTP {about.status_code}: {_safe(about.text[:200])}"}

            files_resp = client.get(
                f"{DRIVE_API}/files",
                params={"pageSize": 20, "fields": "files(id,name,mimeType,size,modifiedTime)", "orderBy": "modifiedTime desc"},
                headers=headers,
            )
            files: list[dict[str, Any]] = []
            if files_resp.status_code == 200:
                for f in (files_resp.json() or {}).get("files", []):
                    files.append(
                        {
                            "id": f.get("id", ""),
                            "name": f.get("name", ""),
                            "mimeType": f.get("mimeType", ""),
                            "size": f.get("size"),
                            "modifiedTime": f.get("modifiedTime", ""),
                        }
                    )
            info = (about.json() or {}).get("user") or {}
            quota = (about.json() or {}).get("storageQuota") or {}
            return {
                "ok": True,
                "error": None,
                "detail": "Token de Google válido",
                "user": info.get("displayName") or info.get("emailAddress") or "",
                "email": info.get("emailAddress") or "",
                "files": files,
                "quota": quota,
            }
    except httpx.ConnectError as exc:
        return {"ok": False, "error": "No se pudo conectar con Google Drive (red)", "detail": _safe(str(exc))}
    except Exception as exc:
        return {"ok": False, "error": "Error inesperado conectando con Google Drive", "detail": _safe(str(exc))}


# ---------------------------------------------------------------------------
# FacturaScript (web API self-hosted o base de datos local)
# ---------------------------------------------------------------------------
def connect_facturascript(config: dict[str, Any], mode: str = "web") -> dict[str, Any]:
    mode = str(mode or "web").strip().lower()
    if mode == "local":
        return _connect_facturascript_local(config)
    return _connect_facturascript_web(config)


def _connect_facturascript_web(config: dict[str, Any]) -> dict[str, Any]:
    from .facturascripts_sync import normalize_fs_base_url

    base_url = normalize_fs_base_url(str(config.get("base_url") or ""))
    api_key = str(config.get("api_key") or "").strip()

    if not base_url:
        return {"ok": False, "error": "Falta la URL de la instalación de FacturaScript", "detail": "base_url"}

    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            last = None
            for path in FACTURASCRIPT_API_PATHS:
                url = base_url + path
                headers = {}
                if api_key:
                    # FASE 4: contrato real — header `Token`. Se conservan los
                    # antiguos como fallback para instalaciones legacy.
                    headers["Token"] = api_key
                    headers["X-API-KEY"] = api_key
                    headers["Authorization"] = f"Bearer {api_key}"
                try:
                    r = client.get(url, headers=headers)
                except httpx.ConnectError as exc:
                    return {"ok": False, "error": "No se pudo conectar con FacturaScript (red o URL incorrecta)", "detail": _safe(str(exc))}
                if r.status_code in (200, 201):
                    # Anti-falso-positivo: solo una respuesta JSON de la API
                    # cuenta como conexión. La homepage HTML de la instalación
                    # devuelve 200 pero NO es la API REST.
                    ctype = r.headers.get("content-type", "")
                    is_json = "application/json" in ctype or r.text.lstrip().startswith(("{", "["))
                    if is_json:
                        try:
                            data = r.json()
                            info = "API JSON accesible"
                            if isinstance(data, dict):
                                info = " · ".join(str(k) + "=" + str(v)[:40] for k, v in list(data.items())[:4])
                            elif isinstance(data, list):
                                info = f"lista de {len(data)} registros"
                        except Exception:
                            info = _safe(r.text[:300])
                        return {"ok": True, "error": None, "detail": f"FacturaScript responde ({r.status_code})", "info": info, "endpoint": path}
                    last = r.status_code
                    continue
                if r.status_code == 401 or r.status_code == 403:
                    return {
                        "ok": False,
                        "error": "FacturaScript rechazó la API key. Revisa que la API REST esté activada y la clave sea correcta.",
                        "detail": f"HTTP {r.status_code} en {path}",
                    }
                last = r.status_code
            return {
                "ok": False,
                "error": "No se encontró una API válida en esa URL. Comprueba que (1) la URL es la instalación de FacturaScript (sin /api/3 — se añade automáticamente), (2) la API REST está activada en Panel de control → Activar API, y (3) la API key tiene acceso completo.",
                "detail": f"Última respuesta: HTTP {last or 'sin respuesta'}",
            }
    except Exception as exc:
        return {"ok": False, "error": "Error inesperado conectando con FacturaScript", "detail": _safe(str(exc))}


def _connect_facturascript_local(config: dict[str, Any]) -> dict[str, Any]:
    db_path = str(config.get("db_path") or "").strip()
    if not db_path:
        return {"ok": False, "error": "Falta la ruta de la instalación local de FacturaScript", "detail": "db_path"}
    p = Path(db_path)
    if not p.exists():
        return {"ok": False, "error": f"No existe la ruta: {db_path}", "detail": "not_found"}
    if p.is_file():
        return {"ok": True, "error": None, "detail": "Fichero local encontrado", "info": str(p), "tipo": "fichero"}
    # Directory — look for typical FacturaScript markers (database files, config).
    hints = []
    for pat in ("*.sqlite", "*.db", "config", "facturascripts"):
        try:
            hits = list(p.glob(pat))[:5] if "*" in pat else [p / pat]
            for h in hits:
                if h.exists():
                    hints.append(str(h))
        except OSError:
            continue
    if hints:
        return {
            "ok": True,
            "error": None,
            "detail": "Instalación local de FacturaScript encontrada",
            "info": "; ".join(hints[:5]),
            "tipo": "directorio",
        }
    return {
        "ok": False,
        "error": "La ruta existe pero no parece una instalación de FacturaScript (sin base de datos ni config)",
        "detail": str(p),
    }


# ---------------------------------------------------------------------------
# Hermes helper — prompt to ask Hermes to connect an integration
# ---------------------------------------------------------------------------
def to_hermes_prompt(integration_id: str, config: dict[str, Any], mode: str = "web") -> str:
    iid = str(integration_id or "").strip().lower()
    meta = _provider_meta(iid) or {}
    name = meta.get("nombre") or iid
    mode_label = "modo web (API REST)" if mode != "local" else "modo local"
    campos = meta.get("campos") or []
    campos_txt = ", ".join(f"{c.get('label')}" for c in campos) if campos else "las credenciales correspondientes"

    return (
        f"[Sistema] El usuario quiere conectar la integración **{name}** de VANOVA "
        f"({mode_label}). Ayúdale a hacerlo: explica en pasos claros qué necesita "
        f"({campos_txt}), dónde obtenerlo (páginas de configuración de {name}), "
        f"y qué errores comunes evitar. Si puedes obtener o generar las credenciales "
        f"por ti (archivos locales, configuraciones ya presentes), hazlo y descríbelo. "
        f"Al final resume qué falta exactamente para que la conexión funcione.]"
    )
