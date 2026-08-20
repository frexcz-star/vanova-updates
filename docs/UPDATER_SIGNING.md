# VANOVA Updater — Code Signing Preparation

**Status:** Checksum verification implemented; Authenticode signing documented for release pipeline.

## Current behavior (1.0.0)

1. Manifest fetched from configured URL (`version.json` → `updateManifestUrl`).
2. Package downloaded with SHA-256 verification (`update_manager.verify_package()`).
3. If manifest includes `signature`, presence is logged; **full signature verification is deferred** to the release pipeline with a code-signing certificate.

## Release signing checklist

### Windows (NSIS installer)

1. Obtain an **Authenticode** certificate (EV recommended for SmartScreen reputation).
2. Sign the installer after `electron-builder`:

```powershell
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /a "release\VANOVA-Setup.exe"
```

3. Sign the unpacked `VANOVA.exe` if distributing portable builds.
4. Publish SHA-256 checksum in `release/latest.json` (use `scripts/generate-checksums.js`).

### Manifest fields

```json
{
  "version": "1.0.0",
  "sha256": "<hex digest of VANOVA-Setup.exe>",
  "signature": "<optional detached signature or CMS blob>",
  "url": "https://releases.moovingpaper.com/maios/VANOVA-Setup.exe"
}
```

### Future work (post-1.0.0)

- Implement manifest signature verification with embedded public key in runtime.
- Automated signing in CI with HSM-backed certificate.
- Notarization if macOS builds are added.

## Local testing

```powershell
cd C:\Users\Admin\maios
.\scripts\setup-local-updates.ps1
.\scripts\e2e-update-test.ps1
```
