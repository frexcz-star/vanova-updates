# VANOVA Release Process

How to publish a new VANOVA version (e.g. 0.9.0 → 0.9.1).

## Prerequisites

- Node.js 22+, Python 3.11+
- No VANOVA processes running (required for electron-builder)
- Working tree clean (recommended)

## Quick Release

```powershell
cd C:\Users\Admin\maios
.\scripts\release.ps1 -Version 0.9.1
```

This script:

1. Runs update unit tests
2. Bumps `version.json` and `desktop/package.json`
3. Builds `release/VANOVA-Setup.exe`
4. Copies to `release/VANOVA-Setup-0.9.1.exe`
5. Generates `release/checksums.txt`
6. Generates `release/latest.json` with SHA-256 and local download URL

## Output Structure

```
release/
├── VANOVA-Setup.exe          # Latest build (electron-builder default name)
├── VANOVA-Setup-0.9.1.exe    # Versioned artifact
├── latest.json              # Update manifest
├── checksums.txt            # SHA-256 for all .exe files
└── release-notes.md         # Human-readable notes (edit before release)
```

## Publishing to Production

1. Edit `release/release-notes.md` with actual changes
2. Run release script with target version
3. Upload artifacts to your storage (S3, R2, GitHub Releases, etc.)
4. Update remote `latest.json`:
   - Set `downloadUrl` to HTTPS CDN URL
   - Set correct `sha256` and `size`
5. Configure production manifest URL in `version.json`:

```json
{
  "updateManifestUrl": "https://releases.moovingpaper.com/maios/latest.json"
}
```

Do **not** use `local:` URLs in production manifests.

## Local End-to-End Test (0.9.0 → 0.9.1)

1. Install VANOVA 0.9.0 (or run dev with version 0.9.0 in `version.json`)
2. Build 0.9.1: `.\scripts\release.ps1 -Version 0.9.1`
3. Reset installed version to 0.9.0 in packaged `version.json` if needed for test
4. Set environment before launching VANOVA:

```powershell
$env:MAIOS_UPDATE_MANIFEST_URL = "local:release/latest.json"
```

5. Open **Settings → Updates → Check for updates**
6. Click **Update now**
7. Verify: download → verify → backup → install → restart → health check

## Code Signing (Future)

When a commercial code signing certificate is available:

1. Sign `VANOVA-Setup-<version>.exe` with `signtool`
2. Populate `signature` field in manifest (format TBD)
3. Implement Authenticode verification in `UpdateManager.verify_package()`

Until then, integrity relies on **HTTPS + SHA-256**.

## Version Bump Only (No Build)

```powershell
.\scripts\release.ps1 -Version 0.9.1 -SkipBuild
```

## Skip Tests (Emergency)

```powershell
.\scripts\release.ps1 -Version 0.9.1 -SkipTests
```

## Rollback Release

If a bad release is published:

1. Point `latest.json` back to previous version
2. Users on broken version: automatic rollback via post-install health check
3. Manual restore: `%LOCALAPPDATA%/VANOVA/backup/` contains pre-update snapshots
