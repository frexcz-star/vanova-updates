# VANOVA Release Process

## Versioning

Single source of truth: `version.json`

```json
{
  "version": "0.9.0",
  "updateManifestUrl": "https://releases.moovingpaper.com/maios/manifest.json"
}
```

Synced to:
- `desktop/package.json` version field
- Electron app metadata
- Update manifest

## Build Release

```powershell
cd C:\Users\Admin\maios\desktop
npm install
npm run release
```

Output:
```
release/
├── VANOVA-Setup.exe      # NSIS installer
├── VANOVA-Setup.exe.blockmap
└── checksums.txt        # SHA-256 hashes
```

## Update Manifest (Remote)

Host at `updateManifestUrl`:

```json
{
  "version": "0.9.1",
  "mandatory": false,
  "downloadUrl": "https://releases.moovingpaper.com/maios/0.9.1/VANOVA-Setup.exe",
  "sha256": "...",
  "releaseNotes": ["Fixed Hermes recovery", "Improved setup wizard"]
}
```

VANOVA checks on startup via `desktop/runtime/updater.py`.

## Update Flow

1. **VANOVA-Setup.exe** — Initial installation only
2. **In-app updater** — Normal updates (download + verify SHA-256 + install)
3. Mandatory updates — Block dashboard until updated

## Integrity

- SHA-256 in `checksums.txt` for every release
- Future: code signing certificate for Windows SmartScreen

## Pre-release Checklist

- [ ] Bump `version.json`
- [ ] Sync `desktop/package.json` version
- [ ] Run full setup flow on clean VM
- [ ] Verify Hermes detection/recovery
- [ ] Confirm no secrets in logs/diagnostics
- [ ] Generate checksums
- [ ] Test uninstall/reinstall

## CI (Future)

```yaml
- npm ci --prefix desktop
- npm run release --prefix desktop
- upload release/VANOVA-Setup.exe
```
