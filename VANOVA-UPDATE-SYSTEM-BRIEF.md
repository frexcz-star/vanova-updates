# MAIOS — Brief for ChatGPT

## Project

**MAIOS** is a commercial Electron desktop app (Windows) by MOOVING PAPER / BlisArtPaper. It bundles Python runtime, Cloud API, Connector, Hermes agents, and a web dashboard.

- **Workspace:** `C:\Users\Admin\maios`
- **Current source version:** `1.0.1` (`version.json`, `desktop/package.json`)
- **Upgrade path in scope:** `1.0.0` → `1.0.1` via **in-app updater** (no manual Setup.exe)

## Stack

- **Electron** + electron-builder (NSIS installer)
- **Python** desktop runtime on port `8765`
- **FastAPI** cloud on port `8000`
- **Web UI** in `web/` (served from `resources/maios/web/`)
- **SQLite** user DB in `%LOCALAPPDATA%\MAIOS\` (NOT in app install dir)

## Update system (custom — NOT electron-updater)

MAIOS uses a **custom update architecture** compatible with electron-builder NSIS installers:

```
UI (web/update-center.js)
  → Desktop Runtime API :8765
  → UpdateManager (desktop/runtime/update/update_manager.py)
  → Manifest fetch (latest.json)
  → Download + SHA-256 verify
  → External maios-updater.ps1 (NSIS silent install after MAIOS exits)
  → startup_recovery() verifies version + rollback on failure
```

### Key files

| Role | Path |
|------|------|
| Orchestrator | `desktop/runtime/update/update_manager.py` |
| Manifest | `desktop/runtime/update/manifest_provider.py` |
| States | `desktop/runtime/update/state_machine.py`, `state_store.py` |
| Download | `desktop/runtime/update/downloader.py` |
| Backup/rollback | `desktop/runtime/update/backup.py` |
| API facade | `desktop/runtime/updater.py` |
| API routes | `desktop/runtime/api_server.py` (`/api/updates/*`) |
| UI | `web/update-center.js` |
| External installer | `desktop/updater/maios-updater.ps1` |
| Production manifest | `release/latest.json` |
| Local test manifest | `release/latest.local.json` |
| Local test setup | `scripts/setup-local-updates.ps1` |
| Publish bundle | `scripts/publish-update.ps1` |
| Docs | `docs/VANOVA_UPDATES.md`, `docs/UPDATER_SIGNING.md` |

### API endpoints

- `GET /api/updates/status`
- `POST /api/updates/check` — `{ "force": true }`
- `POST /api/updates/download`
- `POST /api/updates/install`
- `POST /api/updates/cancel`
- `POST /api/updates/postpone` — `{ "version": "1.0.1", "hours": 24 }`
- `POST /api/updates/recovery`

### Update states

`idle`, `checking`, `available`, `up_to_date`, `downloading`, `downloaded`, `verifying`, `ready_to_install`, `backing_up`, `installing`, `restarting`, `verifying_install`, `completed`, `failed`, `cancelled`, `rollback`, `offline`

### User data (preserved on update)

All under `%LOCALAPPDATA%\MAIOS\`:

- `config/` — settings, credentials, Connector config
- `updates/` — update state, config, downloaded packages
- `backup/` — pre-update backups
- Hermes data, SQLite DB, workspaces, agents

App binaries only in `%LOCALAPPDATA%\Programs\MAIOS\`.

### Production manifest (1.0.1)

```json
{
  "version": "1.0.1",
  "downloadUrl": "https://releases.moovingpaper.com/maios/MAIOS-Setup-1.0.1.exe",
  "sha256": "0a4a7c7a897c13f01c26905a3443e2af958261d0208df7f2a4e98479225d4f44",
  "size": 92721732,
  "dbSchemaVersion": 0
}
```

## What's done

- Full custom updater (check, download, verify, install, rollback)
- Spanish UI: modal ~4s after startup, [Actualizar] / [Más tarde]
- Background auto-download (`autoDownload` in `updates-config.json`)
- Periodic check every 4h (`checkIntervalHours`)
- Manual check in Settings → Actualizaciones
- `release/latest.json` updated to 1.0.1
- `scripts/publish-update.ps1` for CDN staging bundle
- **123 tests passing** (including update system tests)

## What's pending (external infra)

1. **CDN upload** — `release/publish/` → `https://releases.moovingpaper.com/maios/`
2. **Authenticode signing** of installer + signature verification in runtime
3. **E2E test** on real 1.0.0 install (full Download → Install → Restart)
4. **True 1.0.0 baseline** for faithful E2E (copying exe without rebuild doesn't change embedded version.json)

## Local test procedure

```powershell
# From repo root, with MAIOS 1.0.0 installed:
scripts\setup-local-updates.ps1 -OfferVersion 1.0.1 -ResetState
scripts\sync-to-installed.ps1
# Restart MAIOS → wait ~4s → modal "MAIOS 1.0.1 disponible"
# Ajustes → Actualizaciones → Buscar / Descargar / Reiniciar ahora
```

Config written to: `%LOCALAPPDATA%\MAIOS\updates\updates-config.json`

Optional: `"autoDownload": true` for background download.

## Build commands

```powershell
npm run desktop:installer          # from repo or desktop/
scripts\release.ps1 -Version 1.0.1
scripts\publish-update.ps1 -Version 1.0.1
scripts\verify-package.ps1
```

## Database migrations

**None for 1.0.1.** `dbSchemaVersion: 0` in manifest.

## Security

- SHA-256 integrity check (required)
- HTTPS for production download URLs
- `signature` field present; Authenticode verification not yet implemented
- Never disable signature verification in production

## Do NOT

- Reimplement updater with electron-updater unless strictly necessary
- Store user data inside `app.asar` or install directory
- Fake updates by only changing version strings
- Commit `.env` files with secrets
