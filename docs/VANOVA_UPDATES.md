# VANOVA Update System

Production-grade automatic update architecture for VANOVA Desktop on Windows.

## Architecture

```
VANOVA UI (Settings → Updates)
        ↓
Desktop Runtime API (:8765)
        ↓
UpdateManager
        ↓
UpdateManifestProvider  →  remote latest.json
UpdateDownloader        →  %LOCALAPPDATA%/VANOVA/temp/update/<version>/
Integrity (SHA-256)       →  compare manifest.sha256
Backup                    →  %LOCALAPPDATA%/VANOVA/backup/
External Updater (PS1)    →  wait exit → NSIS /S → relaunch
Post-install health check →  startup_recovery()
```

**Critical rule:** VANOVA never replaces its own files while running. The external `maios-updater.ps1` process handles installation after VANOVA exits.

## Components

| Component | Path |
|-----------|------|
| Update Manager | `desktop/runtime/update/update_manager.py` |
| State machine | `desktop/runtime/update/state_machine.py` |
| Manifest provider | `desktop/runtime/update/manifest_provider.py` |
| Downloader | `desktop/runtime/update/downloader.py` |
| Backup / rollback | `desktop/runtime/update/backup.py` |
| External updater | `desktop/updater/maios-updater.ps1` |
| UI | `web/update-center.js` |
| API routes | `desktop/runtime/api_server.py` |

## Update Manifest

Remote JSON served by `UpdateManifestProvider`:

```json
{
  "product": "VANOVA",
  "channel": "stable",
  "version": "0.10.0",
  "minimumSupportedVersion": "0.8.0",
  "mandatory": false,
  "publishedAt": "2026-08-12T00:00:00Z",
  "downloadUrl": "https://cdn.example.com/VANOVA-Setup-0.10.0.exe",
  "sha256": "...",
  "size": 123456789,
  "signature": "",
  "releaseNotes": ["Improved UI", "Bug fixes"],
  "requiredHermes": ">=1.5.0"
}
```

Configure manifest URL via:

- Environment: `MAIOS_UPDATE_MANIFEST_URL`
- `version.json` → `updateManifestUrl`
- `%LOCALAPPDATA%/VANOVA/config/updates.json`

For local testing: `MAIOS_UPDATE_MANIFEST_URL=local:release/latest.json`

Or run `scripts/setup-local-updates.ps1 -ResetState` which writes:

- `%LOCALAPPDATA%/VANOVA/updates/updates-config.json` → `manifestUrl` pointing to `release/latest.test.json` (file URL)
- Resets `update-state.json` to `idle` when `-ResetState` is passed
- Optional `-OfferVersion X.Y.Z` to simulate an update when already on the latest build

**Restart VANOVA** after running the setup script so the runtime reloads config.

## In-app update flow (no manual EXE)

Users on 0.9.7+ should never run `VANOVA-Setup-*.exe` manually:

1. Open VANOVA → **Updates** (Dashboard widget or Settings)
2. **Refresh** — checks for updates only (does not download)
3. When available: **Descargar** — downloads and verifies the package
4. When ready: **Instalar y reiniciar** — launches the silent installer and relaunches VANOVA

Progress is shown during download. The installer is stored under `%LOCALAPPDATA%/VANOVA/temp/update/<version>/`.

## Production manifest

When `manifestUrl` in `updates-config.json` is empty (default after install), the runtime uses:

1. `version.json` → `updateManifestUrl` (CDN: `https://releases.moovingpaper.com/maios/latest.json`)
2. Fallback: same CDN URL

Once the CDN serves `latest.json` plus the matching `VANOVA-Setup-<version>.exe`, users only need **Refresh** in the app.

## Update States

Explicit state machine: `idle` → `checking` → `available` → `downloading` → `verifying` → `ready_to_install` → `backing_up` → `installing` → `restarting` → `verifying_install` → `completed`

Failure paths: `failed`, `rollback`, `cancelled`, `offline`

Persistent state: `%LOCALAPPDATA%/VANOVA/updates/update-state.json`

## Integrity Verification

1. Download to temp directory (never over install dir)
2. Compute SHA-256
3. Compare with manifest
4. On mismatch: delete package, abort install

Code signing architecture is prepared (`signature` field) but commercial Authenticode verification is not yet implemented.

## User Data Preservation

Updates only replace application files via NSIS installer. **Never touched:**

- `%LOCALAPPDATA%/VANOVA/config/` — credentials, company profile
- `%LOCALAPPDATA%/VANOVA/updates/` — update config/history
- `%LOCALAPPDATA%/VANOVA/backup/` — pre-update backups
- Hermes data directories

Pre-update backup copies `config/` and `updates/` to `backup/<timestamp>-v<version>/`.

## Hermes Compatibility

Manifest may include `requiredHermes` (semver range). Before install, UpdateManager logs compatibility requirements. Hermes binaries and data are never deleted during VANOVA updates.

## Rollback

If post-install health check fails (`postInstallPending` in state):

1. State → `rollback`
2. Restore from backup directory
3. Mark history as `failed — rolled back`

## Process Management

External updater:

1. Waits up to 60s for `VANOVA.exe` to exit
2. Force-kills remaining VANOVA processes (own processes only)
3. Runs installer silently (`/S`)
4. Relaunches VANOVA
5. Sets `verifying_install` state

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/updates/status` | Current update state |
| GET | `/api/updates/manifest` | Local dev manifest |
| POST | `/api/updates/check` | Check for updates |
| POST | `/api/updates/download` | Download + verify |
| POST | `/api/updates/install` | Launch external updater |
| POST | `/api/updates/cancel` | Cancel download |
| POST | `/api/updates/postpone` | Postpone update (`{ "version": "1.0.1", "hours": 24 }`) |

## Real-time Events

Emitted internally: `update.checking`, `update.progress`, `update.verifying`, `update.installing`, `update.completed`, `update.failed`, `update.rollback`

UI polls `/api/updates/status` every 2 seconds in Settings → Updates.

## Troubleshooting

| Issue | Check |
|-------|-------|
| Unable to check updates | Network, manifest URL, `%LOCALAPPDATA%/VANOVA/logs/updater.log` |
| Checksum failed | Regenerate manifest with `scripts/release.ps1` |
| Updater not found | Verify `desktop/updater/maios-updater.ps1` in packaged resources |
| Incomplete update | Delete stale state or retry from Settings → Updates |

Logs: `%LOCALAPPDATA%/VANOVA/logs/updater.log`, `electron-load.log`
