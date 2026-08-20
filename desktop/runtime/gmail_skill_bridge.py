"""Gmail Skill Bridge — connects VANOVA's integration store to Hermes' email skill.

Problem this solves (see docs/BITACORA-TESTS.md, Hallazgo #2):
  The UI can show "Gmail conectado" while Hermes has no usable email access,
  because saving credentials in integrations.json never provisions them to the
  Hermes email skill (himalaya). This module is the missing bridge.

Design rules (same discipline as integration_providers.py):
  - Every public function returns a structured dict {"ok": bool, ...} instead
    of raising, so the UI and Hermes always get a clear message.
  - Secrets are never logged or returned.
  - File writes are atomic (write temp + rename).
  - Imports from other runtime modules are lazy inside functions to avoid
    import cycles and keep one broken module from blocking the API.

The bridge has four responsibilities:
  1. Render + write the himalaya config.toml for a Gmail account.
  2. Ensure the himalaya CLI exists (auto-install from the official GitHub
     release when missing) so the skill is actually operable.
  3. Provision the skill: validate credentials (IMAP) then write the config.
  4. Report the REAL status of the skill (installed / configured / in sync).
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from .logger import get_logger

log = get_logger("maios.gmail", "gmail-skill-bridge")

GMAIL_IMAP_HOST = "imap.gmail.com"
GMAIL_IMAP_PORT = 993
GMAIL_SMTP_HOST = "smtp.gmail.com"
# Gmail SMTP implicit-TLS port. With the v2 `smtps://` scheme (TLS from the
# first byte) Gmail serves 465; 587 is STARTTLS, which would corrupt the
# handshake and fail account check.
GMAIL_SMTP_PORT = 465

# Official himalaya release used for auto-install when the CLI is missing.
HIMALAYA_VERSION = "v2.0.0"
HIMALAYA_ZIP_URL = (
    "https://github.com/pimalaya/himalaya/releases/download/"
    f"{HIMALAYA_VERSION}/himalaya.x86_64-windows.zip"
)

# Skill directory inside the Hermes install — the email skill ships with the
# himalaya tool; provisioning only needs to configure it.
HERMES_SKILL_EMAIL = "email"

# Agent -> skills the agent is allowed to use (Hermes skill names).
# This is the single source of truth for "what can this agent do" and is used
# by the UI and by Hermes-facing prompts.
AGENT_SKILLS: dict[str, list[str]] = {
    "marketing-agent": ["email/gmail", "instagram", "analytics"],
    "sales-analyst": ["shopify", "reports"],
    "content-agent": ["email/gmail", "instagram", "media"],
    "inventory-agent": ["shopify", "erp"],
    "support-agent": ["email/gmail", "communication"],
    "ceo-copilot": ["email/gmail", "shopify", "analytics", "reports"],
}


def himalaya_config_path() -> Path:
    """Resolve ~/.config/himalaya/config.toml on any OS."""
    home = Path(os.getenv("USERPROFILE") or os.getenv("HOME") or str(Path.home()))
    return home / ".config" / "himalaya" / "config.toml"


def himalaya_available() -> bool:
    """Whether the himalaya CLI is usable (on PATH or in the managed bin dir)."""
    if shutil.which("himalaya") is not None:
        return True
    return himalaya_bin_path().is_file()


def himalaya_bin_dir() -> Path:
    """Managed install dir for the himalaya CLI (~/.local/bin)."""
    home = Path(os.getenv("USERPROFILE") or os.getenv("HOME") or str(Path.home()))
    return home / ".local" / "bin"


def himalaya_bin_path() -> Path:
    """Full path of the managed himalaya binary."""
    name = "himalaya.exe" if os.name == "nt" else "himalaya"
    return himalaya_bin_dir() / name


def _toml_escape(value: str) -> str:
    """Escape a value for a TOML double-quoted string."""
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def render_himalaya_config(user: str, password: str) -> str:
    """Render the Gmail himalaya config.toml matching the skill reference.

    Reference: hermes/skills/email/himalaya/references/configuration.md
    (Gmail Configuration). App-passwords are stored as raw password auth;
    only the mailbox owner's own config file is written, so plaintext storage
    in the user's own profile mirrors what himalaya documents.
    """
    # Himalaya v2 config schema (the CLI this bridge installs). v2 moved to
    # URI-style backend blocks: imap.server/smtp.server with imap.sasl.plain.*
    # auth. The older v1 layout (backend.type = "imap") is not understood by
    # himalaya 2.x, so we must render the v2 schema or the skill cannot read
    # the mailbox even with a valid config file.
    u = str(user or "").strip()
    p = str(password or "")
    return (
        "[accounts.gmail]\n"
        f'imap.server = "imaps://{GMAIL_IMAP_HOST}:{GMAIL_IMAP_PORT}"\n'
        f'imap.sasl.plain.username = "{_toml_escape(u)}"\n'
        f'imap.sasl.plain.password.raw = "{_toml_escape(p)}"\n'
        f'smtp.server = "smtps://{GMAIL_SMTP_HOST}:{GMAIL_SMTP_PORT}"\n'
        f'smtp.sasl.plain.username = "{_toml_escape(u)}"\n'
        f'smtp.sasl.plain.password.raw = "{_toml_escape(p)}"\n'
        "\n"
        'mailbox.alias.inbox = "INBOX"\n'
        'mailbox.alias.sent = "[Gmail]/Sent Mail"\n'
        'mailbox.alias.drafts = "[Gmail]/Drafts"\n'
        'mailbox.alias.trash = "[Gmail]/Trash"\n'
        'mailbox.alias.archive = "[Gmail]/All Mail"\n'
    )


def write_himalaya_config(user: str, password: str) -> dict[str, Any]:
    """Atomically write the himalaya config for a Gmail account."""
    try:
        cfg_path = himalaya_config_path()
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cfg_path.with_suffix(".toml.tmp")
        tmp.write_text(render_himalaya_config(user, password), encoding="utf-8")
        tmp.replace(cfg_path)
        log.info("Himalaya config written for %s", _mask(user))
        return {"ok": True, "configPath": str(cfg_path)}
    except OSError as exc:
        log.warning("Could not write himalaya config: %s", exc)
        return {"ok": False, "error": "No se pudo escribir la configuración de correo", "detail": _safe(str(exc))}


def _mask(user: str) -> str:
    """Mask an email for logs: n***@gmail.com."""
    u = str(user or "")
    if "@" not in u:
        return "***"
    local, _, domain = u.partition("@")
    return f"{local[:1]}***@{domain}"


def _safe(detail: str) -> str:
    return (detail or "").strip()


def _ensure_on_path(bin_dir: str) -> bool:
    """Persist bin_dir in the user PATH (Windows HKCU Environment).

    Matches what the official himalaya installer does on Unix (PREFIX=~/.local);
    only affects the current user and is reversible. REG_EXPAND_SZ preserves
    existing %VAR% references in PATH.
    """
    if os.name != "nt":
        return True  # ~/.local/bin is usually already on Unix PATHs
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE
        )
        try:
            current, _ = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            current = ""
        current = str(current or "")
        entries = [e for e in current.split(";") if e]
        if bin_dir in entries:
            return True
        updated = ";".join(entries + [bin_dir])
        winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, updated)
        try:
            import ctypes

            HWND_BROADCAST = 0xFFFF
            WM_SETTINGCHANGE = 0x001A
            ctypes.windll.user32.SendMessageTimeoutW(
                HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment", 0, 2000, None
            )
        except Exception:
            pass
        return True
    except Exception as exc:
        log.warning("Could not add %s to user PATH: %s", bin_dir, exc)
        return False


def install_himalaya() -> dict[str, Any]:
    """Download the official himalaya binary and make it available.

    Returns a structured result; never raises. Steps:
      1. Download the official Windows zip from GitHub Releases.
      2. Extract himalaya.exe into ~/.local/bin (atomic write).
      3. Verify it runs (himalaya --version).
      4. Add ~/.local/bin to the user PATH (Windows) so new Hermes
         processes find the CLI.
    """
    try:
        import io
        import subprocess
        import urllib.request
        import zipfile

        bin_dir = himalaya_bin_dir()
        bin_dir.mkdir(parents=True, exist_ok=True)
        exe_path = himalaya_bin_path()
        tmp_path = exe_path.with_suffix(".exe.tmp")

        log.info("Downloading himalaya %s from GitHub Releases...", HIMALAYA_VERSION)
        with urllib.request.urlopen(HIMALAYA_ZIP_URL, timeout=120) as resp:
            data = resp.read()
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            member = "himalaya.exe" if os.name == "nt" else "himalaya"
            payload = zf.read(member)

        tmp_path.write_bytes(payload)
        tmp_path.replace(exe_path)

        check = subprocess.run(
            [str(exe_path), "--version"], capture_output=True, text=True, timeout=30
        )
        if check.returncode != 0:
            exe_path.unlink(missing_ok=True)
            return {
                "ok": False,
                "error": "El binario de himalaya descargado no es ejecutable",
                "detail": _safe(check.stderr.strip() or check.stdout.strip()),
            }

        on_path = _ensure_on_path(str(bin_dir))
        return {
            "ok": True,
            "error": None,
            "himalayaInstalled": True,
            "binPath": str(exe_path),
            "version": _safe(check.stdout.strip() or check.stderr.strip()),
            "onPath": on_path,
            "detail": "CLI de himalaya instalado",
        }
    except Exception as exc:
        log.warning("himalaya auto-install failed: %s", exc)
        return {
            "ok": False,
            "error": "No se pudo instalar el CLI de himalaya",
            "detail": _safe(str(exc)),
        }


def ensure_himalaya() -> dict[str, Any]:
    """Make the himalaya CLI available, installing it if missing."""
    if himalaya_available():
        return {"ok": True, "himalayaInstalled": True, "detail": "CLI de himalaya disponible"}
    return install_himalaya()


def validate_gmail_credentials(user: str, password: str) -> dict[str, Any]:
    """Validate Gmail credentials against IMAP (reuses integration_providers)."""
    from . import integration_providers

    return integration_providers.connect_gmail({"user": user, "app_password": password})


def provision_gmail_skill(user: str, password: str, *, validate: bool = True) -> dict[str, Any]:
    """Validate credentials and provision the Hermes email skill for Gmail.

    Returns a structured result; never raises. When ``validate`` is True the
    credentials are checked against Gmail IMAP before the config is written
    (the UI already validated on save, so callers may pass validate=False).
    """
    if not str(user or "").strip():
        return {"ok": False, "error": "Falta el correo de Gmail"}
    if not str(password or ""):
        return {"ok": False, "error": "Falta la contraseña de aplicación"}

    if validate:
        check = validate_gmail_credentials(user, password)
        if not check.get("ok"):
            return check

    written = write_himalaya_config(user, password)
    if not written.get("ok"):
        return written

    cli = ensure_himalaya()
    return {
        "ok": True,
        "error": None,
        "user": _mask(user),
        "validated": bool(validate),
        "himalayaInstalled": bool(cli.get("himalayaInstalled")),
        "himalayaVersion": cli.get("version"),
        "himalayaDetail": cli.get("detail"),
        "configPath": written.get("configPath"),
        "detail": (
            "Skill de correo configurado para Gmail"
            if cli.get("ok")
            else "Skill configurado pero el CLI de himalaya no está disponible"
        ),
    }


def gmail_skill_status() -> dict[str, Any]:
    """Report the REAL status of the Hermes email skill for Gmail.

    Combines: himalaya CLI availability, config presence, and whether the
    configured account matches the one stored in VANOVA's integration store.
    """
    from . import integrations_store

    stored = integrations_store.get_config("gmail")
    stored_connected = bool(stored.get("connected"))
    stored_user = str(stored.get("user") or "")

    cfg_path = himalaya_config_path()
    config_exists = cfg_path.is_file()
    config_user = ""
    config_valid = False
    if config_exists:
        try:
            text = cfg_path.read_text(encoding="utf-8-sig")
            for line in text.splitlines():
                line = line.strip()
                # v2 schema: account identity lives in imap.sasl.plain.username
                # (the older `email =` key was removed in himalaya 2.x).
                if line.startswith('imap.sasl.plain.username = "'):
                    config_user = line.split('"', 2)[1]
                    break
                if line.startswith('email = "'):
                    config_user = line.split('"', 2)[1]
                    break
            config_valid = bool(config_user)
        except OSError as exc:
            log.warning("Could not read himalaya config: %s", exc)

    synced = bool(stored_connected and config_valid and stored_user == config_user)
    return {
        "ok": True,
        "skill": HERMES_SKILL_EMAIL,
        "himalayaInstalled": himalaya_available(),
        "configExists": config_exists,
        "configUser": _mask(config_user) if config_user else None,
        "configValid": config_valid,
        "storedConnected": stored_connected,
        "storedUser": _mask(stored_user) if stored_user else None,
        "synced": synced,
        "detail": (
            "Operativo"
            if synced
            else ("Conectado en VANOVA pero sin skill operativo"
                  if stored_connected and not config_valid
                  else "Sin configurar")
        ),
    }


def sync_from_integrations_store() -> dict[str, Any]:
    """If Gmail is connected in VANOVA's store, provision the skill (idempotent).

    This is the inverse bridge that was missing (Shopify has one via
    sync_shopify_from_hermes_if_needed). Safe to call on every save: writing
    the same config twice is a no-op rename.
    """
    from . import integrations_store

    creds = integrations_store.get_gmail_credentials()
    if not creds.get("connected"):
        return {"ok": False, "error": "Gmail no está conectado en VANOVA", "detail": "not_connected"}
    user = str(creds.get("user") or "").strip()
    password = str(creds.get("pass") or creds.get("password") or "")
    if not user or not password:
        return {"ok": False, "error": "Faltan credenciales de Gmail en el store"}
    return provision_gmail_skill(user, password, validate=False)
