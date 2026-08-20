# VANOVA Security Overview

**Version:** 1.0.0  
**Last updated:** 2026-08-13

## Architecture

VANOVA Desktop runs locally (Electron + Python runtime on port 8765). Sensitive data stays on the user's machine unless explicitly connected to VANOVA Cloud.

## Authentication

- **Runtime mutations** require a Bearer token issued at install time (`install_secrets.py`).
- **Cloud API** uses session tokens with refresh rotation and rate-limited login.
- **No wildcard CORS** in production builds — only allowlisted origins.

## Secrets

- Integration tokens (Shopify, ERP, etc.) are encrypted at rest via `credential_vault.py`.
- Logs and audit entries redact API keys, tokens, and passwords.
- Never commit `.env`, `secrets/`, or live tokens to source control.

## Authorization

- Cloud RBAC: owner / admin / operator / viewer roles (`cloud/rbac.py`).
- Multi-tenancy workspace isolation (`cloud/tenancy.py`).
- Agent permissions and policy engine enforce allow / deny / require_approval before task execution.

## Data protection

- SQLite databases use **WAL mode** with daily automatic backups to `%LOCALAPPDATA%/VANOVA/backups/`.
- Manual backup via Diagnostics → **Crear copia ahora** or `POST /api/backups/run`.

## Electron hardening

- `sandbox: true`, `webSecurity: true`, CSP headers in `desktop/main.js`.
- Preload exposes minimal IPC surface.

## Reporting issues

Report security issues to MOOVING PAPER engineering. Do not disclose publicly before a fix is available.
