# VANOVA 1.0.3 Client Release Report

**Date:** 2026-08-13  
**Version:** 1.0.3  
**Channel:** stable  
**Build machine:** Windows 10 (local)

---

## Executive summary

VANOVA 1.0.3 client hardening is **code-complete**, **test-verified**, and **built locally**. Eight release priorities are implemented. This session fixed a task-queue deadlock (RLock), test isolation for the task sweeper, and three failing tests. The unsigned installer and manifests are ready for upload; Authenticode signing, CDN publish, and live E2E update validation remain operator tasks.

---

## Hardening priorities (8/8)

| # | Priority | Status | Implementation | Verification |
|---|----------|--------|----------------|--------------|
| 1 | **WebSocket auth** | Done | `cloud/main.py` — `_validate_ws_access_token()`, `/ws/dashboard` rejects missing/expired/refresh tokens with `auth_failed` | `tests/test_ws_auth.py` (4 tests) |
| 2 | **Task heartbeat / stale detection** | Done | `task_queue.py` — 30s heartbeat loop, stale reconcile (120s starting / 30m running), retry; **RLock** fix for nested lock during load | `tests/test_task_stale.py` (3 tests) |
| 3 | **Version health** | Done | `health_monitor._check_maios()` uses `updater.current_version()`; `shared/version_info.py` bundle | `tests/test_version_consistency.py` (4 tests) |
| 4 | **Approvals UI** | Done | `web/dashboard.html` — `viewApprovals()`, nav badge, approve/deny actions, empty state | Manual + `tests/test_approvals.py` |
| 5 | **CEO dynamic date** | Done | `ceoBanner()` and CEO brief use `fmtLocaleDate(new Date())` | `web/dashboard.html` |
| 6 | **Config write reduction** | Done | `config_store._write_atomic()` skips identical JSON; `hermes_config.sync_maios_from_hermes()` debounces via `_SYNC_MIN_INTERVAL_SEC` and equality check | `tests/test_config_store.py::test_save_skips_unchanged_payload` |
| 7 | **UTF-8 consistency** | Done | `utf-8-sig` reads, `utf-8` writes across config, Hermes, release script (`Write-JsonNoBom`); JS `TextDecoder('utf-8')` | Version/update tests, `hermes_config.py`, `release.ps1` |
| 8 | **Diagnostics overall status** | Done | `diagnostics_service._CORE_CRITICAL_IDS` — only runtime/cloud/port failures mark **critical**; Shopify/connector warnings → **degraded** | `tests/test_diagnostics_overall.py`, `test_e2e_smoke.py` |

### Fixes applied during release hardening (this session)

- **Task queue deadlock:** `_ensure_loaded()` held `threading.Lock` while calling `_reconcile_stale_active_tasks()` which re-acquired the same lock → switched to `threading.RLock()`.
- **Test isolation:** `MAIOS_DISABLE_TASK_SWEEPER=1` now also suppresses auto-start of queued task processing on load (prevents Hermes CLI hangs in CI/local test runs).
- **Heartbeat guard:** `_execute_task()` skips `touch_heartbeat` when task dict has no `id` (unit-test safety).
- **Test fixes:** `test_business_scanner`, `test_e2e_smoke`, `test_update_system` (dynamic manifest version).

---

## Test results

**Command:** `python -m unittest discover -s tests -p "test_*.py" -q`  
**Environment:** `MAIOS_DISABLE_TASK_SWEEPER=1` (recommended for local runs)

| Metric | Result |
|--------|--------|
| **Total tests** | 182 |
| **Passed** | 181 |
| **Skipped** | 1 (`test_extract_products_from_xlsx_when_file_exists` — optional MOOVING catalog xlsx) |
| **Failed** | 0 |
| **Duration** | ~44 s |

**1.0.3-specific test modules:**

- `tests/test_ws_auth.py`
- `tests/test_task_stale.py`
- `tests/test_version_consistency.py`

---

## Build artifacts

Built with: `scripts/release.ps1 -Version 1.0.3 -SkipTests`  
Build log: `release/build-1.0.3.log`

| Artifact | Path | Size | SHA-256 |
|----------|------|------|---------|
| Installer (versioned) | `release/VANOVA-Setup-1.0.3.exe` | 92,760,063 bytes (~88.5 MB) | `a018fa2d44a21bdc543e6a8ff2447ff534f7ad78c0305ebc69aab86cb8afd395` |
| Installer (latest copy) | `release/VANOVA-Setup.exe` | same | same |
| Update manifest (CDN) | `release/latest.json` | — | version 1.0.3 |
| Local manifest | `release/latest.local.json` | — | file:// URL for dev |
| Checksums | `release/checksums.txt` | — | includes 1.0.3 |
| Unpacked app | `release/win-unpacked/` | — | package verify OK |

**Manifest excerpt (`release/latest.json`):**

- `downloadUrl`: `https://releases.moovingpaper.com/maios/VANOVA-Setup-1.0.3.exe`
- `minimumSupportedVersion`: `0.9.0`
- `signature`: *(empty — Authenticode pending)*

---

## Remaining blockers (operator / infra)

| Blocker | Owner | Notes |
|---------|-------|-------|
| **Authenticode signing** | Release ops | electron-builder skipped signing (`no signing info identified`). Sign `VANOVA-Setup-1.0.3.exe` before wide distribution. |
| **CDN upload** | Release ops | Upload `VANOVA-Setup-1.0.3.exe` to `releases.moovingpaper.com/maios/` and publish `latest.json`. |
| **E2E update test** | QA | Validate 1.0.2 → 1.0.3 (or 1.0.1 → 1.0.3) in-app update using `latest.local.json` or staging CDN. Not run in this session. |
| **Release notes content** | Product | `release/release-notes.md` has placeholder bullet for 1.0.3; expand before public announcement. |

---

## Recommended publish checklist

1. Expand `# VANOVA 1.0.3` section in `release/release-notes.md`.
2. Sign `release/VANOVA-Setup-1.0.3.exe` (Authenticode).
3. Upload installer + `latest.json` to CDN; confirm SHA-256 matches manifest.
4. Smoke-install on clean VM; verify version shows 1.0.3 in diagnostics.
5. Run E2E update from previous stable (1.0.2) if available.
6. Monitor WebSocket auth, task stale timeout, and approvals flow in production.

---

## Version consistency

| Source | Version |
|--------|---------|
| `version.json` | 1.0.3 |
| `desktop/package.json` | 1.0.3 |
| `shared/version_info.current_version()` | 1.0.3 |
| `release/latest.json` | 1.0.3 |

---

*Generated as part of VANOVA 1.0.3 client release hardening.*
