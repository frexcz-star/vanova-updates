# VANOVA 1.0.0 — Release Checklist

Use this checklist before tagging **1.0.0** or any production release.

## Pre-release

- [ ] All tests green: `python -m pytest tests/ -v`
- [ ] Version synced: `version.json`, `desktop/package.json`, dashboard cache-bust query strings
- [ ] `docs/IMPLEMENTATION_PROGRESS.md` updated
- [ ] No raw secrets in repo or logs
- [ ] Electron build succeeds: `cd desktop && npm run desktop:installer`

## Security

- [ ] Runtime auth enforced on all mutation POST paths
- [ ] CORS allowlist verified (`tests/test_runtime_security.py`)
- [ ] Integration tokens encrypted (`tests/test_integrations_encryption.py`)
- [ ] Review `docs/SECURITY.md`

## Functional smoke

- [ ] Fresh install → setup wizard completes
- [ ] Home Command Center loads (attention, running-now, recent results)
- [ ] Hermes ask + structured response
- [ ] Task enqueue → policy → execution or approval
- [ ] Diagnostics page shows real checks (ports, health, DB, Shopify, backups)
- [ ] Shopify connect → sync → products/sales visible
- [ ] Backup created (Diagnostics or startup daily)

## Updates

- [ ] `release/latest.json` generated with SHA-256
- [ ] Installer signed per `docs/UPDATER_SIGNING.md`
- [ ] Update check/download/install tested locally

## Deploy

```powershell
cd C:\Users\Admin\maios
.\.venv\Scripts\python.exe -m pytest tests/ -v
powershell -ExecutionPolicy Bypass -File scripts\sync-to-installed.ps1
# Close and reopen VANOVA.exe
```

## Post-release

- [ ] Monitor `%LOCALAPPDATA%/VANOVA/logs/maios-desktop.jsonl`
- [ ] Verify correlation IDs in logs for support tickets
- [ ] Tag git release `v1.0.0` when repository is initialized

## Definition of Done (1.0.0)

| Area | Requirement |
|------|-------------|
| Security P0/P1 | Complete with regression tests |
| Command Center UX | Home, Hermes, tasks, approvals |
| Onboarding + autonomy | Wizard + settings |
| Integrations | Shopify lifecycle + disconnect/resync |
| Observability | Structured JSON logs + correlation IDs |
| Diagnostics | Real multi-check panel |
| Backups | WAL checkpoint + daily + manual |
| Documentation | SECURITY, RELEASE, UPDATER_SIGNING |
| Tests | ≥100 automated tests passing |
