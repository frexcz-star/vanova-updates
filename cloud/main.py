"""VANOVA Cloud — public API server.

VANOVA Cloud is the public-facing backend. It is deployable on ANY hosting
provider (portable): it runs on uvicorn, uses SQLite for storage (no external
DB required), and speaks REST + WebSocket.

Responsibilities:
- Authentication (JWT, bcrypt)
- Workspace isolation
- Device registration + heartbeat (VANOVA Connector registers here)
- REST API for dashboard data
- WebSocket realtime channel (pushes activity to browsers)
- Audit log

Security model:
- Connector establishes an OUTBOUND, authenticated connection to Cloud.
  Cloud never needs the owner PC's local ports; it only talks to devices that
  connect out to it.
- No business API keys live in this repository. All secrets come from env vars.
"""
from __future__ import annotations

import os
import sys
import json
import sqlite3
import secrets
import uuid
import hashlib
import hmac
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from jose import JWTError, jwt
import bcrypt

from dotenv import load_dotenv

from cloud.auth_session import (
    ACCESS_TOKEN_EXPIRE_MINUTES as AUTH_ACCESS_MINUTES,
    check_login_rate_limit,
    ensure_refresh_tokens_table,
    issue_refresh_token,
    login_response_fields,
    revoke_all_user_tokens,
    revoke_device_tokens,
    revoke_refresh_token,
    rotate_refresh_token,
)
from cloud.rbac import has_permission, list_permissions, normalize_role
from cloud.tenancy import assert_row_in_workspace, ensure_memberships_table, sync_membership_from_user

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
# Make shared/ importable (parent of cloud/)
sys.path.insert(0, str(BASE_DIR.parent))
load_dotenv(BASE_DIR / ".env", override=True)

APP_NAME = "VANOVA Cloud"
from shared.version_info import CLOUD_API_VERSION, current_version as _maios_version

VERSION = CLOUD_API_VERSION
VANOVA_VERSION = _maios_version()

SECRET_KEY = os.getenv("MAIOS_CLOUD_SECRET_KEY", secrets.token_urlsafe(48))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("MAIOS_TOKEN_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("MAIOS_REFRESH_DAYS", "7"))
DB_PATH = os.getenv("MAIOS_DB", str(BASE_DIR / "maios_cloud.db"))
AUDIT_LOG_PATH = os.getenv("MAIOS_AUDIT_LOG", str(BASE_DIR / "audit.jsonl"))
# Comma-separated trusted origins; required in production (MAIOS_ENV=production)
MAIOS_ENV = os.getenv("MAIOS_ENV", "development").strip().lower()
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("MAIOS_ALLOWED_ORIGINS", "").split(",") if o.strip()]
_DEFAULT_PRODUCTION_ORIGINS = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://127.0.0.1:8765",
    "http://localhost:8765",
]

if MAIOS_ENV == "production":
    if not ALLOWED_ORIGINS:
        ALLOWED_ORIGINS = list(_DEFAULT_PRODUCTION_ORIGINS)
    _cors_origins = ALLOWED_ORIGINS
    _cors_credentials = True
else:
    _cors_origins = ALLOWED_ORIGINS if ALLOWED_ORIGINS else ["*"]
    _cors_credentials = bool(ALLOWED_ORIGINS)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

app = FastAPI(title=APP_NAME, version=VERSION)


class NoCacheStaticMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path == "/" or path.endswith((".html", ".js", ".css")):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
        return response


app.add_middleware(NoCacheStaticMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def init_db():
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS workspaces (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            username TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'owner',
            created_at TEXT NOT NULL,
            UNIQUE(workspace_id, username),
            FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
        );
        CREATE TABLE IF NOT EXISTS devices (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            name TEXT,
            device_key_hash TEXT NOT NULL,
            status TEXT DEFAULT 'offline',
            os TEXT,
            version TEXT,
            last_heartbeat TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
        );
        CREATE TABLE IF NOT EXISTS activity (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            agent TEXT NOT NULL,
            action TEXT NOT NULL,
            status TEXT NOT NULL,
            result TEXT,
            timestamp TEXT NOT NULL,
            FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
        );
        CREATE TABLE IF NOT EXISTS decisions (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            title TEXT NOT NULL,
            recommendation TEXT,
            impact TEXT,
            confidence TEXT,
            autonomy_level TEXT,
            status TEXT DEFAULT 'pending',
            agent TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
        );
        CREATE TABLE IF NOT EXISTS insights (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            agent TEXT NOT NULL,
            type TEXT,
            priority TEXT,
            title TEXT NOT NULL,
            description TEXT,
            impact TEXT,
            confidence TEXT,
            recommendation TEXT,
            status TEXT DEFAULT 'open',
            created_at TEXT,
            FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
        );
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            detail TEXT
        );
        CREATE TABLE IF NOT EXISTS snapshots (
            workspace_id TEXT,
            kind TEXT,
            data TEXT,
            ts TEXT
        );
        CREATE TABLE IF NOT EXISTS kv (
            workspace_id TEXT,
            key TEXT,
            value TEXT,
            PRIMARY KEY(workspace_id, key)
        );
        CREATE TABLE IF NOT EXISTS hermes_requests (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            conversation_id TEXT,
            message TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            result TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            processed_at TEXT,
            FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
        );
        CREATE TABLE IF NOT EXISTS hermes_conversations (
            conversation_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            hermes_session_id TEXT,
            title TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
        );
        CREATE TABLE IF NOT EXISTS insight_actions (
            insight_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            action TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
        );
        CREATE TABLE IF NOT EXISTS guardrails (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            agent TEXT NOT NULL,
            action TEXT NOT NULL,
            target TEXT,
            risk TEXT DEFAULT 'high',
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            decided_at TEXT,
            FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
        );
        """
    )
    # Migration: add conversation_id to hermes_requests if the table pre-existed
    cols = [r[1] for r in conn.execute("PRAGMA table_info(hermes_requests)").fetchall()]
    if "conversation_id" not in cols:
        conn.execute("ALTER TABLE hermes_requests ADD COLUMN conversation_id TEXT")
    ensure_refresh_tokens_table(conn)
    ensure_memberships_table(conn)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------
def audit(actor: str, action: str, detail: str = ""):
    entry = {"ts": datetime.now(timezone.utc).isoformat(), "actor": actor, "action": action, "detail": detail}
    try:
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
    try:
        conn = get_db()
        conn.execute("INSERT INTO audit_log (timestamp, actor, action, detail) VALUES (?,?,?,?)",
                     (entry["ts"], actor, action, detail))
        conn.commit()
        conn.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: str, workspace_id: str, role: str) -> str:
    expire = datetime.now(timezone.utc).timestamp() + ACCESS_TOKEN_EXPIRE_MINUTES * 60
    payload = {"sub": user_id, "ws": workspace_id, "role": role, "exp": expire, "typ": "access"}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: str, workspace_id: str) -> str:
    """Legacy JWT refresh — prefer issue_refresh_token() for new sessions."""
    expire = datetime.now(timezone.utc).timestamp() + REFRESH_TOKEN_EXPIRE_DAYS * 86400
    payload = {"sub": user_id, "ws": workspace_id, "exp": expire, "typ": "refresh"}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host or "unknown"
    return "unknown"


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")


def _validate_ws_access_token(token: str) -> dict | None:
    """Validate JWT for WebSocket — same rules as HTTP access token."""
    if not (token or "").strip():
        return None
    try:
        payload = jwt.decode(token.strip(), SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
    if payload.get("typ") != "access":
        return None
    if not payload.get("sub") or not payload.get("ws"):
        return None
    return payload


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    payload = _decode_token(token)
    if payload.get("typ") != "access":
        raise HTTPException(status_code=401, detail="Se requiere access token")
    role = normalize_role(payload.get("role"))
    return {"user_id": payload.get("sub"), "workspace_id": payload.get("ws"), "role": role}


def require_perm(permission: str):
    def checker(user: dict = Depends(get_current_user)):
        if not has_permission(user.get("role"), permission):
            raise HTTPException(status_code=403, detail="Permiso denegado")
        return user

    return checker


# ---------------------------------------------------------------------------
# Data source abstraction (the "VANOVA Data Layer")
# ---------------------------------------------------------------------------
class DataSource:
    """Base data source. Subclasses implement get_dashboard()."""

    mode = "empty"

    def get_dashboard(self) -> dict:
        raise NotImplementedError


class MockSource(DataSource):
    mode = "mock"

    def __init__(self):
        from shared.mock_data import get_mock_dashboard
        self._get = get_mock_dashboard

    def get_dashboard(self) -> dict:
        return self._get()


class CloudDataSource(DataSource):
    """Real data pulled through the connected VANOVA Connector.

    In production, Cloud receives dashboard snapshots from the Connector
    (which talks to real business systems / Hermes). Until a connector is
    online, this source reports empty.
    """

    mode = "real"

    def __init__(self, workspace_id: str):
        self.workspace_id = workspace_id

    def get_dashboard(self) -> dict:
        # Cloud stores the latest snapshot the Connector pushed.
        conn = get_db()
        row = conn.execute(
            "SELECT data FROM snapshots WHERE workspace_id=? AND kind='dashboard' ORDER BY rowid DESC LIMIT 1",
            (self.workspace_id,),
        ).fetchone()
        conn.close()
        if row:
            data = json.loads(row["data"])
            # CAUSA RAÍZ CONTADOR (BUG-036 residual): el snapshot del Connector
            # puede traer decisions=[] aunque haya decisiones reales pendientes
            # en la tabla 'decisions' del cloud. El badge y el drawer cuentan
            # store.decisions, que salía siempre vacío -> el contador no
            # reflejaba las decisiones pendientes reales. Enriquecer con las
            # decisiones reales del workspace (no solo las del snapshot).
            try:
                c2 = get_db()
                drows = c2.execute(
                    "SELECT * FROM decisions WHERE workspace_id=? ORDER BY rowid DESC",
                    (self.workspace_id,),
                ).fetchall()
                c2.close()
                data["decisions"] = [dict(r) for r in drows]
            except Exception:
                pass
            return data
        return {"dataMode": "empty", "overview": {}, "priorities": [], "activity": [], "agents": [], "decisions": [], "sources": []}


# Store latest snapshots pushed by connectors
# BUG-010 FIX: retention — la tabla snapshots crecía SIN LÍMITE (un INSERT por
# llamada, ~2880 filas/día/workspace con heartbeats de 30s). Se conservan solo
# los últimos SNAPSHOT_RETENTION por (workspace_id, kind) usando el rowid
# implícito de SQLite. Los SELECT usan "ORDER BY rowid DESC LIMIT 1", así que
# mantener los N más recientes preserva la lectura sin cambiar ningún consumidor.
SNAPSHOT_RETENTION = 100


def store_snapshot(workspace_id: str, kind: str, data: dict):
    conn = get_db()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS snapshots (
            workspace_id TEXT, kind TEXT, data TEXT, ts TEXT
        )"""
    )
    conn.execute(
        "INSERT INTO snapshots (workspace_id, kind, data, ts) VALUES (?,?,?,?)",
        (workspace_id, kind, json.dumps(data, ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
    )
    # Prune: conservar solo los SNAPSHOT_RETENTION más recientes por par
    # (workspace_id, kind). SQLite expone un rowid implícito en las filas.
    # BUG-013 FIX: el DELETE también debe filtrar por (workspace_id, kind); antes
    # solo filtraba en el sub-SELECT, así que el DELETE borraba filas de OTROS
    # kinds/workspaces (p.ej. insertar el 1er snapshot de 'products' borraba los
    # de 'dashboard').
    conn.execute(
        """DELETE FROM snapshots
           WHERE workspace_id = ? AND kind = ? AND rowid NOT IN (
               SELECT rowid FROM snapshots
               WHERE workspace_id = ? AND kind = ?
               ORDER BY rowid DESC LIMIT ?
           )""",
        (workspace_id, kind, workspace_id, kind, SNAPSHOT_RETENTION),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Realtime (WebSocket) connection manager
# ---------------------------------------------------------------------------
class ConnectionManager:
    def __init__(self):
        self.active: dict[str, set[WebSocket]] = {}  # workspace_id -> sockets

    async def connect(self, ws: WebSocket, workspace_id: str, *, already_accepted: bool = False):
        if not already_accepted:
            await ws.accept()
        self.active.setdefault(workspace_id, set()).add(ws)

    def disconnect(self, ws: WebSocket, workspace_id: str):
        self.active.get(workspace_id, set()).discard(ws)

    async def broadcast(self, workspace_id: str, message: dict):
        for ws in list(self.active.get(workspace_id, set())):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(ws, workspace_id)


manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Onboarding state (in-memory + persisted flag)
# ---------------------------------------------------------------------------
def workspace_configured(workspace_id: str) -> bool:
    conn = get_db()
    row = conn.execute(
        "SELECT value FROM kv WHERE workspace_id=? AND key='configured'", (workspace_id,)
    ).fetchone()
    conn.close()
    return bool(row)


def mark_configured(workspace_id: str):
    conn = get_db()
    conn.execute(
        "CREATE TABLE IF NOT EXISTS kv (workspace_id TEXT, key TEXT, value TEXT, PRIMARY KEY(workspace_id, key))"
    )
    conn.execute(
        "INSERT INTO kv (workspace_id, key, value) VALUES (?, 'configured', '1') "
        "ON CONFLICT(workspace_id, key) DO UPDATE SET value='1'",
        (workspace_id,),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Bootstrap demo workspace (owner)
# ---------------------------------------------------------------------------
KNOWN_WEAK_PASSWORDS = frozenset({"mooving2026", "password", "admin", "123456", "ceo"})


def bootstrap():
    init_db()
    conn = get_db()
    username = os.getenv("MAIOS_DEMO_USER", "ceo")
    password = os.getenv("MAIOS_DEMO_PASSWORD", "")
    if not password:
        password = secrets.token_urlsafe(16)
        log_bootstrap_password = True
    else:
        log_bootstrap_password = False
    if MAIOS_ENV == "production" and password.lower() in KNOWN_WEAK_PASSWORDS:
        raise RuntimeError(
            "Production bootstrap rejected: MAIOS_DEMO_PASSWORD is a known weak/default credential. "
            "Set a strong random password via cloud.env."
        )
    ws = conn.execute("SELECT id FROM workspaces LIMIT 1").fetchone()
    if not ws:
        ws_id = str(uuid.uuid4())
        owner_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("INSERT INTO workspaces (id, name, created_at) VALUES (?,?,?)",
                     (ws_id, "MOOVING PAPER", now))
        conn.execute("INSERT INTO users (id, workspace_id, username, password_hash, role, created_at) VALUES (?,?,?,?,?,?)",
                     (owner_id, ws_id, username, hash_password(password), "owner", now))
        user_row = conn.execute("SELECT * FROM users WHERE id=?", (owner_id,)).fetchone()
        if user_row:
            sync_membership_from_user(conn, user_row)
        conn.commit()
        audit("bootstrap", "workspace_created", ws_id)
        if log_bootstrap_password and MAIOS_ENV != "production":
            audit("bootstrap", "demo_password_generated", username)
    else:
        row = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if row and os.getenv("MAIOS_DEMO_PASSWORD"):
            conn.execute(
                "UPDATE users SET password_hash=? WHERE id=?",
                (hash_password(password), row["id"]),
            )
            user_row = conn.execute("SELECT * FROM users WHERE id=?", (row["id"],)).fetchone()
            if user_row:
                sync_membership_from_user(conn, user_row)
            conn.commit()
    conn.close()


@app.on_event("startup")
async def on_startup():
    bootstrap()


# ---------------------------------------------------------------------------
# Routes — auth
# ---------------------------------------------------------------------------
class LoginIn(BaseModel):
    username: str
    password: str


class OnboardingCompleteIn(BaseModel):
    company: str = ""
    company_key: str = ""


@app.post("/api/auth/login")
async def login(request: Request, form: OAuth2PasswordRequestForm = Depends()):
    client_ip = _client_ip(request)
    check_login_rate_limit(f"login:{client_ip}:{form.username}")
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username=?", (form.username,)).fetchone()
    if not user or not verify_password(form.password, user["password_hash"]):
        conn.close()
        audit(form.username, "login_failed")
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    device_id = request.headers.get("x-maios-device-id") or ""
    refresh = issue_refresh_token(conn, user["id"], device_id)
    conn.commit()
    conn.close()
    audit(user["username"], "login_success")
    return {
        "access_token": create_access_token(user["id"], user["workspace_id"], user["role"]),
        "refresh_token": refresh,
        **login_response_fields(user["role"]),
    }


@app.post("/api/auth/refresh")
async def refresh_token_endpoint(request: Request):
    check_login_rate_limit(f"refresh:{_client_ip(request)}")
    body = await request.json()
    raw = body.get("refresh_token", "")
    if not raw:
        raise HTTPException(status_code=401, detail="Refresh token requerido")
    conn = get_db()
    try:
        new_refresh, row = rotate_refresh_token(conn, raw)
        user = conn.execute("SELECT * FROM users WHERE id=?", (row["user_id"],)).fetchone()
        conn.commit()
    except HTTPException:
        conn.close()
        raise
    except Exception:
        conn.close()
        raise HTTPException(status_code=401, detail="Refresh token inválido o expirado")
    conn.close()
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    return {
        "access_token": create_access_token(user["id"], user["workspace_id"], user["role"]),
        "refresh_token": new_refresh,
        "token_type": "bearer",
        "expires_in": AUTH_ACCESS_MINUTES * 60,
    }


class LogoutIn(BaseModel):
    refresh_token: str = ""


@app.post("/api/auth/logout")
async def logout(body: LogoutIn, user: dict = Depends(get_current_user)):
    if not body.refresh_token:
        raise HTTPException(status_code=400, detail="refresh_token requerido")
    conn = get_db()
    revoked = revoke_refresh_token(conn, body.refresh_token)
    conn.commit()
    conn.close()
    audit(user["user_id"], "logout", "session" if revoked else "unknown_token")
    return {"ok": True, "revoked": revoked}


@app.post("/api/auth/logout-all")
async def logout_all(user: dict = Depends(get_current_user)):
    conn = get_db()
    count = revoke_all_user_tokens(conn, user["user_id"])
    conn.commit()
    conn.close()
    audit(user["user_id"], "logout_all", str(count))
    return {"ok": True, "revoked": count}


class RevokeDeviceIn(BaseModel):
    device_id: str


@app.post("/api/auth/revoke-device")
async def revoke_device(body: RevokeDeviceIn, user: dict = Depends(get_current_user)):
    if not body.device_id:
        raise HTTPException(status_code=400, detail="device_id requerido")
    conn = get_db()
    count = revoke_device_tokens(conn, user["user_id"], body.device_id)
    conn.commit()
    conn.close()
    audit(user["user_id"], "revoke_device", body.device_id)
    return {"ok": True, "revoked": count}

@app.get("/api/me")
async def me(user: dict = Depends(get_current_user)):
    conn = get_db()
    u = conn.execute("SELECT id, username, role FROM users WHERE id=?", (user["user_id"],)).fetchone()
    conn.close()
    return {
        "username": u["username"],
        "role": user["role"],
        "workspace": user["workspace_id"],
        "permissions": list_permissions(user["role"]),
    }


@app.get("/api/onboarding/status")
async def onboarding_status(user: dict = Depends(get_current_user)):
    return {"configured": workspace_configured(user["workspace_id"])}


# ---------------------------------------------------------------------------
# Routes — devices (Connector registration)
# ---------------------------------------------------------------------------
class RegisterDeviceIn(BaseModel):
    deviceKey: str
    name: str = "VANOVA Connector"
    os: str = ""
    version: str = ""


def _device_key_hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


@app.post("/api/devices/register")
async def register_device(body: RegisterDeviceIn, user: dict = Depends(require_perm("members.manage"))):
    if not body.deviceKey or len(body.deviceKey) < 24:
        raise HTTPException(status_code=400, detail="deviceKey debe tener al menos 24 caracteres")
    device_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    conn.execute(
        "INSERT INTO devices (id, workspace_id, name, device_key_hash, status, os, version, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (device_id, user["workspace_id"], body.name, _device_key_hash(body.deviceKey), "offline", body.os, body.version, now),
    )
    conn.commit()
    conn.close()
    audit("user:" + user["user_id"], "device_registered", device_id)
    return {"device_id": device_id, "status": "registered"}


@app.post("/api/devices/register-local")
async def register_device_local(body: RegisterDeviceIn, request: Request):
    """Localhost-only device registration for desktop auto-recovery (no JWT required)."""
    host = (request.client.host if request.client else "") or ""
    if host not in ("127.0.0.1", "::1"):
        raise HTTPException(status_code=403, detail="Solo disponible en localhost")
    if not body.deviceKey or len(body.deviceKey) < 24:
        raise HTTPException(status_code=400, detail="deviceKey debe tener al menos 24 caracteres")
    conn = get_db()
    ws = conn.execute("SELECT id FROM workspaces LIMIT 1").fetchone()
    if not ws:
        conn.close()
        raise HTTPException(status_code=503, detail="Workspace no inicializado")
    key_hash = _device_key_hash(body.deviceKey)
    existing = conn.execute("SELECT id FROM devices WHERE device_key_hash=?", (key_hash,)).fetchone()
    now = datetime.now(timezone.utc).isoformat()
    if existing:
        conn.execute("UPDATE devices SET status='offline', name=?, os=?, version=? WHERE id=?", (body.name, body.os, body.version, existing["id"]))
        device_id = existing["id"]
    else:
        device_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO devices (id, workspace_id, name, device_key_hash, status, os, version, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (device_id, ws["id"], body.name, key_hash, "offline", body.os, body.version, now),
        )
    conn.commit()
    conn.close()
    audit("local-recovery", "device_registered", device_id)
    return {"device_id": device_id, "status": "registered"}


@app.get("/api/devices")
async def list_devices(user: dict = Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute("SELECT * FROM devices WHERE workspace_id=?", (user["workspace_id"],)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# Connector outbound channel: heartbeat + authenticated push.
# The connector uses a device key in Authorization to identify itself.
def _auth_device(authorization: str) -> dict:
    if not authorization or not authorization.startswith("Device "):
        raise HTTPException(status_code=401, detail="Credencial de dispositivo requerida")
    key = authorization[7:]
    key_hash = _device_key_hash(key)
    conn = get_db()
    dev = conn.execute("SELECT * FROM devices WHERE device_key_hash=?", (key_hash,)).fetchone()
    if not dev:
        conn.close()
        raise HTTPException(status_code=401, detail="Dispositivo no reconocido")
    return dict(dev)


@app.post("/api/connector/heartbeat")
async def connector_heartbeat(request: Request):
    dev = _auth_device(request.headers.get("authorization", ""))
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    conn.execute("UPDATE devices SET status='online', last_heartbeat=? WHERE id=?", (now, dev["id"]))
    conn.commit()
    conn.close()
    return {"status": "online", "ts": now}


@app.post("/api/connector/push")
async def connector_push(request: Request):
    """Connector pushes dashboard snapshot + activity into the workspace.
    P0-9: a partial snapshot (e.g. heartbeat-only, no business metrics) must NOT
    overwrite existing business data. We merge per-domain: only domains present
    in the incoming snapshot are updated."""
    dev = _auth_device(request.headers.get("authorization", ""))
    body = await request.json()
    # Read the last dashboard snapshot to merge business metrics.
    conn = get_db()
    row = conn.execute(
        "SELECT data FROM snapshots WHERE workspace_id=? AND kind='dashboard' ORDER BY rowid DESC LIMIT 1",
        (dev["workspace_id"],),
    ).fetchone()
    merged = json.loads(row["data"]) if row else {}
    # Update dataMode only if the incoming snapshot explicitly sets it.
    if "dataMode" in body:
        merged["dataMode"] = body["dataMode"]
    # Update only the domains the connector actually reported (non-empty).
    for domain in ["hermes", "sources", "priorities", "automations"]:
        if domain in body:
            merged[domain] = body[domain]
    # overview is only updated when the connector truly reports business metrics
    # (a heartbeat-only snapshot has empty overview and must not wipe real data).
    if "overview" in body and body["overview"]:
        merged["overview"] = body["overview"]
    if "agents" in body:
        merged["agents"] = body["agents"]
    # Activity is append-only via the realtime feed (handled below), not merged here.
    store_snapshot(dev["workspace_id"], "dashboard", merged)
    conn.close()
    # Persist activity into realtime feed
    for act in body.get("activity", []):
        conn = get_db()
        conn.execute(
            "INSERT INTO activity (id, workspace_id, agent, action, status, result, timestamp) VALUES (?,?,?,?,?,?,?)",
            (act.get("id", str(uuid.uuid4())), dev["workspace_id"], act.get("agent", ""), act.get("action", ""),
             act.get("status", "completed"), act.get("result"), act.get("timestamp", datetime.now(timezone.utc).isoformat())),
        )
        conn.commit()
        conn.close()
    audit("device:" + dev["name"], "data_pushed", f"{len(body.get('activity', []))} activity events")
    await manager.broadcast(dev["workspace_id"], {"type": "activity_update", "data": body.get("activity", [])})
    return {"status": "ok"}


@app.post("/api/connector/insight-event")
async def connector_insight_event(request: Request):
    """Persist an insight as a durable business event so it survives snapshot
    churn (P0-9: a later heartbeat must not destroy it)."""
    dev = _auth_device(request.headers.get("authorization", ""))
    body = await request.json()
    conn = get_db()
    conn.execute(
        "CREATE TABLE IF NOT EXISTS insights ("
        " id TEXT PRIMARY KEY, workspace_id TEXT, agent TEXT, type TEXT, priority TEXT, "
        " title TEXT, description TEXT, source TEXT, status TEXT, created_at TEXT)"
    )
    # Ensure legacy tables (created before 'source' existed) get the column.
    cols = [r[1] for r in conn.execute("PRAGMA table_info(insights)").fetchall()]
    if "source" not in cols:
        conn.execute("ALTER TABLE insights ADD COLUMN source TEXT")
    if "created_at" not in cols:
        conn.execute("ALTER TABLE insights ADD COLUMN created_at TEXT")
    conn.execute(
        "INSERT OR REPLACE INTO insights (id, workspace_id, agent, type, priority, title, description, source, status, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (body.get("id", str(uuid.uuid4())), dev["workspace_id"], body.get("agent", "CEO Copilot"),
         body.get("type", "recommendation"), body.get("priority", "medium"),
         body.get("title", ""), body.get("description", ""), body.get("source", "Hermes Agent"),
         body.get("status", "open"), body.get("createdAt", datetime.now(timezone.utc).isoformat())),
    )
    conn.commit()
    conn.close()
    audit("device:" + dev["name"], "insight_event", body.get("id", ""))
    await manager.broadcast(dev["workspace_id"], {"type": "insight_update", "data": body})
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Routes — data
# ---------------------------------------------------------------------------
@app.get("/api/dashboard")
async def get_dashboard(user: dict = Depends(get_current_user)):
    source = CloudDataSource(user["workspace_id"])
    data = source.get_dashboard()
    if not data.get("dataMode") or data["dataMode"] == "empty":
        # No real data available -> return an honest empty state. NEVER fall back
        # to the dev mock in production (it would misrepresent data as real).
        return {
            "dataMode": "empty",
            "overview": {},
            "priorities": [],
            "activity": [],
            "agents": [],
            "decisions": [],
            "sources": [],
            "automations": [],
        }
    return data


@app.get("/api/products")
async def get_products(user: dict = Depends(get_current_user)):
    conn = get_db()
    row = conn.execute(
        "SELECT data FROM snapshots WHERE workspace_id=? AND kind='products' ORDER BY rowid DESC LIMIT 1",
        (user["workspace_id"],),
    ).fetchone()
    conn.close()
    if not row:
        return {"dataMode": "empty", "products": [], "count": 0}
    data = json.loads(row["data"])
    return {"dataMode": data.get("dataMode", "real"), "products": data.get("products", []), "count": data.get("count", 0)}


class ProductAddIn(BaseModel):
    name: str = ""
    sku: str = ""
    netPrice: float | None = None
    rrp: float | None = None


@app.post("/api/products/add")
async def add_product(body: ProductAddIn, user: dict = Depends(require_perm("tasks.create"))):
    name = (body.name or "").strip()
    if not name:
        return {"ok": False, "error": "El nombre del producto es obligatorio"}
    conn = get_db()
    row = conn.execute(
        "SELECT data FROM snapshots WHERE workspace_id=? AND kind='products' ORDER BY rowid DESC LIMIT 1",
        (user["workspace_id"],),
    ).fetchone()
    data = json.loads(row["data"]) if row else {"dataMode": "real", "products": []}
    products = list(data.get("products") or [])
    product = {
        "name": name,
        "sku": (body.sku or "").strip(),
        "netPrice": body.netPrice,
        "rrp": body.rrp,
        "source": "manual",
    }
    key = (product.get("sku") or product.get("name") or "").lower()
    products = [p for p in products if (p.get("sku") or p.get("name") or "").lower() != key]
    products.append(product)
    payload = {"dataMode": data.get("dataMode", "real"), "products": products, "count": len(products)}
    store_snapshot(user["workspace_id"], "products", payload)
    conn.close()
    return {"ok": True, "product": product, "count": len(products), "products": products}


class FilesIn(BaseModel):
    files: list = []
    count: int = 0


@app.post("/api/connector/files")
async def connector_files(body: FilesIn, request: Request):
    dev = _auth_device(request.headers.get("authorization", ""))
    store_snapshot(dev["workspace_id"], "files", {"files": body.files, "count": body.count})
    return {"ok": True, "count": body.count}


@app.get("/api/files")
async def get_files(user: dict = Depends(get_current_user)):
    conn = get_db()
    row = conn.execute(
        "SELECT data FROM snapshots WHERE workspace_id=? AND kind='files' ORDER BY rowid DESC LIMIT 1",
        (user["workspace_id"],),
    ).fetchone()
    conn.close()
    if not row:
        return {"files": [], "count": 0}
    data = json.loads(row["data"])
    return {"files": data.get("files", []), "count": data.get("count", 0)}


class FileAddIn(BaseModel):
    name: str = ""
    ext: str = ""
    size: int = 0
    path: str = ""


@app.post("/api/files/add")
async def add_file(body: FileAddIn, user: dict = Depends(get_current_user)):
    conn = get_db()
    row = conn.execute(
        "SELECT data FROM snapshots WHERE workspace_id=? AND kind='files' ORDER BY rowid DESC LIMIT 1",
        (user["workspace_id"],),
    ).fetchone()
    files = json.loads(row["data"]).get("files", []) if row else []
    new_file = {
        "name": body.name or "archivo",
        "ext": body.ext or "xlsx",
        "size": body.size or 0,
        "path": body.path or body.name or "archivo",
        "modified": datetime.now(timezone.utc).isoformat(),
    }
    files.append(new_file)
    store_snapshot(user["workspace_id"], "files", {"files": files, "count": len(files)})
    conn.close()
    return {"ok": True, "count": len(files), "file": new_file}


class FileRemoveIn(BaseModel):
    path: str = ""


@app.post("/api/files/remove")
async def remove_file(body: FileRemoveIn, user: dict = Depends(get_current_user)):
    conn = get_db()
    row = conn.execute(
        "SELECT data FROM snapshots WHERE workspace_id=? AND kind='files' ORDER BY rowid DESC LIMIT 1",
        (user["workspace_id"],),
    ).fetchone()
    files = json.loads(row["data"]).get("files", []) if row else []
    files = [f for f in files if f.get("path") != body.path]
    store_snapshot(user["workspace_id"], "files", {"files": files, "count": len(files)})
    conn.close()
    return {"ok": True, "count": len(files)}


@app.get("/api/insight-actions")
async def get_insight_actions(user: dict = Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute(
        "SELECT insight_id, action FROM insight_actions WHERE workspace_id=?",
        (user["workspace_id"],),
    ).fetchall()
    conn.close()
    return {r["insight_id"]: r["action"] for r in rows}


# ---------------------------------------------------------------------------
# Guardrails — destructive agent actions require human approval
# ---------------------------------------------------------------------------
class GuardrailIn(BaseModel):
    agent: str
    action: str
    target: str = ""
    risk: str = "high"


@app.post("/api/guardrails")
async def create_guardrail(body: GuardrailIn, user: dict = Depends(require_perm("agents.execute"))):
    gid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    conn.execute(
        "INSERT INTO guardrails (id, workspace_id, agent, action, target, risk, status, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (gid, user["workspace_id"], body.agent, body.action, body.target, body.risk, "pending", now),
    )
    conn.commit()
    conn.close()
    audit("agent:" + body.agent, "guardrail_request", body.action + ":" + body.target)
    return {"id": gid, "status": "pending"}


@app.get("/api/guardrails")
async def list_guardrails(user: dict = Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM guardrails WHERE workspace_id=? AND status='pending' ORDER BY rowid DESC",
        (user["workspace_id"],),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


class GuardrailDecisionIn(BaseModel):
    id: str
    decision: str  # approve | deny


@app.post("/api/guardrails/decide")
async def decide_guardrail(body: GuardrailDecisionIn, user: dict = Depends(require_perm("approvals.decide"))):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    assert_row_in_workspace(
        conn,
        table="guardrails",
        resource_id=body.id,
        workspace_id=user["workspace_id"],
    )
    conn.execute(
        "UPDATE guardrails SET status=?, decided_at=? WHERE id=? AND workspace_id=?",
        (body.decision, now, body.id, user["workspace_id"]),
    )
    conn.commit()
    conn.close()
    audit("user:" + user["user_id"], "guardrail_" + body.decision, body.id)
    return {"ok": True}


class FacturaScriptConfigIn(BaseModel):
    url: str = ""
    user: str = ""
    password: str = ""


@app.post("/api/facturascript/config")
async def save_facturascript_config(body: FacturaScriptConfigIn, user: dict = Depends(require_perm("integrations.configure"))):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO kv (workspace_id, key, value) VALUES (?,?,?)",
        (user["workspace_id"], "facturascript_config",
         json.dumps({"url": body.url, "user": body.user, "pass": body.password, "connected": True}, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()
    audit("user:" + user["user_id"], "facturascript_config", body.url)
    return {"ok": True, "connected": True}


@app.get("/api/facturascript/config")
async def get_facturascript_config(user: dict = Depends(get_current_user)):
    conn = get_db()
    row = conn.execute(
        "SELECT value FROM kv WHERE workspace_id=? AND key='facturascript_config'",
        (user["workspace_id"],),
    ).fetchone()
    conn.close()
    if not row:
        return {"connected": False}
    data = json.loads(row["value"])
    return {"connected": True, "url": data.get("url", ""), "user": data.get("user", "")}


class DriveConfigIn(BaseModel):
    url: str = ""


@app.post("/api/drive/config")
async def save_drive_config(body: DriveConfigIn, user: dict = Depends(require_perm("integrations.configure"))):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO kv (workspace_id, key, value) VALUES (?,?,?)",
        (user["workspace_id"], "drive_config",
         json.dumps({"url": body.url, "connected": True}, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()
    audit("user:" + user["user_id"], "drive_config", body.url)
    return {"ok": True, "connected": True}


@app.get("/api/drive/config")
async def get_drive_config(user: dict = Depends(get_current_user)):
    conn = get_db()
    row = conn.execute(
        "SELECT value FROM kv WHERE workspace_id=? AND key='drive_config'",
        (user["workspace_id"],),
    ).fetchone()
    conn.close()
    if not row:
        return {"connected": False}
    data = json.loads(row["value"])
    return {"connected": True, "url": data.get("url", "")}


class IntegrationConfigIn(BaseModel):
    url: str = ""
    token: str = ""
    user: str = ""
    password: str = ""


@app.post("/api/integrations/{integration}/config")
async def save_integration_config(integration: str, body: IntegrationConfigIn, user: dict = Depends(require_perm("integrations.configure"))):
    conn = get_db()
    payload = {"connected": True}
    if body.url: payload["url"] = body.url
    if body.token: payload["token"] = body.token
    if body.user: payload["user"] = body.user
    if body.password: payload["pass"] = body.password
    conn.execute(
        "INSERT OR REPLACE INTO kv (workspace_id, key, value) VALUES (?,?,?)",
        (user["workspace_id"], f"{integration}_config",
         json.dumps(payload, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()
    audit("user:" + user["user_id"], f"{integration}_config", body.url or body.token)
    return {"ok": True, "connected": True}


@app.get("/api/integrations/{integration}/config")
async def get_integration_config(integration: str, user: dict = Depends(get_current_user)):
    conn = get_db()
    row = conn.execute(
        "SELECT value FROM kv WHERE workspace_id=? AND key=?",
        (user["workspace_id"], f"{integration}_config"),
    ).fetchone()
    conn.close()
    if not row:
        return {"connected": False}
    data = json.loads(row["value"])
    return {"connected": True, **{k: v for k, v in data.items() if k != "pass"}}





class InsightActionIn(BaseModel):
    insight_id: str
    action: str  # approved | rejected | dismissed


@app.post("/api/insight-actions")
async def set_insight_action(body: InsightActionIn, user: dict = Depends(require_perm("approvals.decide"))):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO insight_actions (insight_id, workspace_id, action, created_at) VALUES (?,?,?,?)",
        (body.insight_id, user["workspace_id"], body.action, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()
    audit("user:" + user["user_id"], "insight_action", body.insight_id + ":" + body.action)
    return {"ok": True}


@app.get("/api/activity")
async def get_activity(limit: int = 30, user: dict = Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM activity WHERE workspace_id=? ORDER BY rowid DESC LIMIT ?", (user["workspace_id"], limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/decisions")
async def get_decisions(user: dict = Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM decisions WHERE workspace_id=? ORDER BY rowid DESC", (user["workspace_id"],)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


class DecisionAction(BaseModel):
    decision_id: str
    action: str  # approve | reject | investigate


@app.post("/api/decisions/action")
async def decision_action(body: DecisionAction, user: dict = Depends(require_perm("approvals.decide"))):
    status_map = {"approve": "approved", "reject": "rejected", "investigate": "investigating"}
    if body.action not in status_map:
        raise HTTPException(status_code=400, detail="Acción inválida")
    conn = get_db()
    assert_row_in_workspace(
        conn,
        table="decisions",
        resource_id=body.decision_id,
        workspace_id=user["workspace_id"],
    )
    cur = conn.execute(
        "UPDATE decisions SET status=? WHERE id=? AND workspace_id=?",
        (status_map[body.action], body.decision_id, user["workspace_id"]),
    )
    conn.commit()
    conn.close()
    audit("user:" + user["user_id"], "decision_" + body.action, body.decision_id)
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Decisión no encontrada")
    return {"ok": True, "status": status_map[body.action]}


# ---------------------------------------------------------------------------
# Routes — onboarding / data sources
# ---------------------------------------------------------------------------
@app.post("/api/onboarding/complete")
async def complete_onboarding(body: OnboardingCompleteIn, user: dict = Depends(require_perm("workspace.update"))):
    mark_configured(user["workspace_id"])
    # Persist the configured company so the Connector can generate on-brand insights.
    if body.company or body.company_key:
        conn = get_db()
        conn.execute(
            "INSERT INTO kv (workspace_id, key, value) VALUES (?, 'company_name', ?) "
            "ON CONFLICT(workspace_id, key) DO UPDATE SET value=excluded.value",
            (user["workspace_id"], body.company),
        )
        conn.execute(
            "INSERT INTO kv (workspace_id, key, value) VALUES (?, 'company_key', ?) "
            "ON CONFLICT(workspace_id, key) DO UPDATE SET value=excluded.value",
            (user["workspace_id"], body.company_key),
        )
        conn.commit()
        conn.close()
    audit("user:" + user["user_id"], "onboarding_completed")
    return {"ok": True}


@app.get("/api/company")
async def get_company(user: dict = Depends(get_current_user)):
    conn = get_db()
    name = conn.execute("SELECT value FROM kv WHERE workspace_id=? AND key='company_name'", (user["workspace_id"],)).fetchone()
    key = conn.execute("SELECT value FROM kv WHERE workspace_id=? AND key='company_key'", (user["workspace_id"],)).fetchone()
    conn.close()
    return {
        "company": (name[0] if name else "MOOVING PAPER"),
        "company_key": (key[0] if key else "MOOVING"),
    }


@app.get("/api/connector/company")
async def connector_company(request: Request):
    """Device-authenticated company lookup so the Connector can generate on-brand
    insights for the workspace the device belongs to."""
    dev = _auth_device(request.headers.get("authorization", ""))
    conn = get_db()
    name = conn.execute("SELECT value FROM kv WHERE workspace_id=? AND key='company_name'", (dev["workspace_id"],)).fetchone()
    key = conn.execute("SELECT value FROM kv WHERE workspace_id=? AND key='company_key'", (dev["workspace_id"],)).fetchone()
    conn.close()
    return {
        "company": (name[0] if name else "MOOVING PAPER"),
        "company_key": (key[0] if key else "MOOVING"),
    }


@app.get("/api/sources")
async def list_sources(user: dict = Depends(get_current_user)):
    data = CloudDataSource(user["workspace_id"]).get_dashboard()
    return data.get("sources", [])


# ---------------------------------------------------------------------------
# Hermes request queue — the dashboard asks Hermes; the Connector picks it up,
# runs it against local Hermes CLI, and posts the result back.
# ---------------------------------------------------------------------------
class HermesRequestIn(BaseModel):
    message: str
    conversation_id: str = ""


@app.post("/api/hermes/ask")
async def hermes_ask(body: HermesRequestIn, user: dict = Depends(require_perm("agents.execute"))):
    """Queue a question for Hermes. Returns the request id (status pending)."""
    if not body.message or not body.message.strip():
        raise HTTPException(status_code=400, detail="Mensaje vacío")
    req_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conv_id = body.conversation_id or req_id
    conn = get_db()
    # Ensure the conversation exists
    row = conn.execute(
        "SELECT hermes_session_id FROM hermes_conversations WHERE conversation_id=? AND workspace_id=?",
        (conv_id, user["workspace_id"]),
    ).fetchone()
    if not row:
        conn.execute(
            "INSERT INTO hermes_conversations (conversation_id, workspace_id, hermes_session_id, title, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (conv_id, user["workspace_id"], None, body.message.strip()[:60], now, now),
        )
    else:
        conn.execute(
            "UPDATE hermes_conversations SET updated_at=? WHERE conversation_id=? AND workspace_id=?",
            (now, conv_id, user["workspace_id"]),
        )
    conn.execute(
        "INSERT INTO hermes_requests (id, workspace_id, conversation_id, message, status, created_at) VALUES (?,?,?,?,?,?)",
        (req_id, user["workspace_id"], conv_id, body.message.strip(), "pending", now),
    )
    conn.commit()
    conn.close()
    audit("user:" + user["user_id"], "hermes_ask", req_id)
    return {"id": req_id, "status": "pending", "message": body.message.strip(), "conversation_id": conv_id}


@app.get("/api/hermes/conversations")
async def hermes_conversations(user: dict = Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute(
        "SELECT conversation_id, title, created_at, updated_at, "
        "(SELECT COUNT(*) FROM hermes_requests r WHERE r.conversation_id=c.conversation_id AND r.workspace_id=c.workspace_id) AS messages "
        "FROM hermes_conversations c WHERE workspace_id=? ORDER BY updated_at DESC LIMIT 50",
        (user["workspace_id"],),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/hermes/conversations/{conv_id}/messages")
async def hermes_conversation_messages(conv_id: str, user: dict = Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute(
        "SELECT id, message, status, result, error, created_at FROM hermes_requests "
        "WHERE conversation_id=? AND workspace_id=? ORDER BY rowid ASC",
        (conv_id, user["workspace_id"]),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/hermes/requests")
async def hermes_requests(limit: int = 20, user: dict = Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM hermes_requests WHERE workspace_id=? ORDER BY rowid DESC LIMIT ?",
        (user["workspace_id"], limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/hermes/requests/{req_id}")
async def hermes_request_status(req_id: str, user: dict = Depends(get_current_user)):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM hermes_requests WHERE id=? AND workspace_id=?",
        (req_id, user["workspace_id"]),
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Petición no encontrada")
    return dict(row)


# Connector endpoints: pick up pending requests and post results
@app.get("/api/connector/requests/pending")
async def connector_pending_requests(request: Request):
    dev = _auth_device(request.headers.get("authorization", ""))
    conn = get_db()
    rows = conn.execute(
        "SELECT r.id, r.message, r.conversation_id, c.hermes_session_id "
        "FROM hermes_requests r LEFT JOIN hermes_conversations c ON c.conversation_id=r.conversation_id AND c.workspace_id=r.workspace_id "
        "WHERE r.workspace_id=? AND r.status='pending' ORDER BY r.rowid ASC LIMIT 5",
        (dev["workspace_id"],),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


class ConnectorResultIn(BaseModel):
    request_id: str
    result: str = ""
    error: str = ""
    hermes_session_id: str = ""


@app.post("/api/connector/requests/result")
async def connector_request_result(body: ConnectorResultIn, request: Request):
    dev = _auth_device(request.headers.get("authorization", ""))
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    if body.error:
        conn.execute(
            "UPDATE hermes_requests SET status='error', error=?, processed_at=? WHERE id=? AND workspace_id=?",
            (body.error, now, body.request_id, dev["workspace_id"]),
        )
    else:
        conn.execute(
            "UPDATE hermes_requests SET status='completed', result=?, processed_at=? WHERE id=? AND workspace_id=?",
            (body.result, now, body.request_id, dev["workspace_id"]),
        )
    # Store the Hermes session id on the conversation so future messages resume it
    if body.hermes_session_id:
        conn.execute(
            "UPDATE hermes_conversations SET hermes_session_id=?, updated_at=? "
            "WHERE conversation_id=(SELECT conversation_id FROM hermes_requests WHERE id=?) AND workspace_id=?",
            (body.hermes_session_id, now, body.request_id, dev["workspace_id"]),
        )
    conn.commit()
    conn.close()
    # Broadcast to any connected dashboard
    await manager.broadcast(dev["workspace_id"], {"type": "hermes_result", "request_id": body.request_id})
    return {"ok": True}


# ---------------------------------------------------------------------------
# WebSocket realtime
# ---------------------------------------------------------------------------
@app.websocket("/ws/dashboard")
async def ws_dashboard(ws: WebSocket):
    token = ws.query_params.get("token") or ""
    payload = _validate_ws_access_token(token)
    # Starlette returns HTTP 403 if the handler exits without accept().
    await ws.accept()
    if not payload:
        await ws.send_json({"type": "auth_failed", "message": "Token inválido o expirado"})
        await ws.close(code=4401, reason="Token inválido o expirado")
        return
    workspace_id = str(payload["ws"])
    await manager.connect(ws, workspace_id, already_accepted=True)
    await ws.send_json({"type": "connected", "workspaceId": workspace_id})
    try:
        while True:
            # Ping/pong keepalive; client may send {"type":"ping"}
            data = await ws.receive_text()
            if data and "ping" in data:
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(ws, workspace_id)
    except Exception:
        manager.disconnect(ws, workspace_id)


@app.get("/api/audit")
async def list_audit(limit: int = 50, user: dict = Depends(require_perm("settings.read"))):
    conn = get_db()
    rows = conn.execute(
        "SELECT timestamp, actor, action, detail FROM audit_log ORDER BY rowid DESC LIMIT ?",
        (min(limit, 200),),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "app": APP_NAME,
        "version": VERSION,
        "maiosVersion": VANOVA_VERSION,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Static frontend (when deployed together) — MUST be registered LAST so that
# all /api routes above take priority over the catch-all static mount.
# ---------------------------------------------------------------------------
_static_dir = os.getenv("MAIOS_STATIC_DIR", str(BASE_DIR.parent / "web" / "dist"))
# Resolve relative paths against the project root (BASE_DIR.parent), so it
# works whether the Cloud is launched from the root or from cloud/.
if not os.path.isabs(_static_dir):
    _static_dir = str((BASE_DIR.parent / _static_dir).resolve())
if os.path.isdir(_static_dir):
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
