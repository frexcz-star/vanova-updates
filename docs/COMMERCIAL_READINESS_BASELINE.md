# VANOVA 1.0 — Commercial Readiness Baseline

**Version audited:** 0.9.13  
**Audit date:** 2026-08-13  
**Phase:** 0 — Baseline y Audit  
**Auditor:** Automated baseline run + codebase inspection

This document records the state of VANOVA **before** any commercial-readiness changes. It is the reference point for Phases 1–37 defined in [`COMMERCIAL_READINESS_ROADMAP.md`](./COMMERCIAL_READINESS_ROADMAP.md).

---

## 1. Baseline Command Results

| Check | Command | Result | Notes |
|-------|---------|--------|-------|
| Python unit tests | `python -m pytest tests/ -v` | **PASS — 31/31** | `pytest` was not pre-installed in `.venv`; installed `pytest 9.1.1` for this run |
| JavaScript tests | *(none configured)* | **N/A** | No `test` script in `desktop/package.json`; no Jest/Mocha/Vitest config |
| Typecheck | *(none configured)* | **N/A** | No root `tsconfig.json`; project uses plain JS/HTML |
| Lint | *(none configured)* | **N/A** | No ESLint/Ruff/Flake8 config at repo root |
| Python compile | `python -m compileall desktop/runtime cloud connector shared` | **PASS** | All modules compile without syntax errors |
| JavaScript syntax | `node --check` on key files | **PASS** | `main.js`, `preload.js`, `web/data-services.js`, `web/system-status.js`, `web/update-center.js`, `desktop/ui/setup.js` |
| Desktop build | `npm run desktop:build` | **FAIL** | `electron-builder` failed: `release/win-unpacked/resources/app.asar` locked by another process (likely running VANOVA instance) |
| Prior build artifact | `release/build-0913/` | **EXISTS** | v0.9.13 unpacked build present from prior successful packaging |

### Test inventory (31 tests, 6 files)

| File | Tests | Focus |
|------|-------|-------|
| `tests/test_business_scanner.py` | 3 | Snapshot modes, imported files |
| `tests/test_config_store.py` | 4 | Setup state, atomic save, reset |
| `tests/test_file_organizer.py` | 3 | Classification, persistence |
| `tests/test_port_utils.py` | 5 | Port health, zombie recovery |
| `tests/test_update_failures.py` | 3 | Manifest rejection, checksum mismatch, cancel |
| `tests/test_update_system.py` | 13 | Semver, manifest, state machine, checksums |

**Coverage gaps (no tests today):** runtime API auth, CORS, Electron security, Cloud JWT/refresh, RBAC, task persistence, Hermes real execution, guardrails, approvals, Shopify integration, connector registration, path traversal, credential encryption.

---

## 2. Packages Overview

### Python (`.venv`, Python 3.11.15)

| Package | Location | Key dependencies |
|---------|----------|------------------|
| **VANOVA Cloud** | `cloud/` | FastAPI, uvicorn, python-jose, bcrypt, httpx, pydantic, python-dotenv |
| **Desktop Runtime** | `desktop/runtime/` | FastAPI/uvicorn (health), stdlib HTTP server on :8765, httpx, python-jose, bcrypt |
| **Connector** | `connector/` | httpx, python-dotenv, asyncio |
| **Shared** | `shared/` | Mock data, shared utilities |
| **Tests** | `tests/` | pytest (installed during baseline) |

### Node.js (`desktop/`)

| Package | Version | Purpose |
|---------|---------|---------|
| `electron` | ^33.2.0 (resolved 33.4.11) | Desktop shell |
| `electron-builder` | ^25.1.8 | NSIS installer / packaging |

### External runtime

| Component | Port | Notes |
|-----------|------|-------|
| Hermes Agent | 8642 | External CLI; not bundled |

### User data (runtime)

| Path | Contents |
|------|----------|
| `%LOCALAPPDATA%/VANOVA/config/` | Company profile, AI config, agents, `integrations.json`, env files |
| `%LOCALAPPDATA%/VANOVA/logs/` | Structured JSONL logs |
| `%LOCALAPPDATA%/VANOVA/data/` | Organized products/sales, scan snapshots |

---

## 3. Build Status

| Artifact | Status |
|----------|--------|
| `release/build-0913/win-unpacked/` | Present — prior v0.9.13 build |
| `release/latest.json` | Present |
| `release/checksums.txt` | Present |
| Fresh `npm run desktop:build` | **Blocked** — file lock on `app.asar` |
| `npm run desktop:installer` | Not attempted (build prerequisite failed) |
| `npm run release` | Not attempted |

**Build configuration:** `desktop/package.json` → `electron-builder` bundles `cloud/`, `connector/`, `shared/`, `web/`, `desktop/runtime/`, `install_all.py`, updater scripts into `resources/maios/`.

**Installer hygiene concern:** Prior build at `release/build-0913/` includes `cloud/.env` and `connector/.env` inside packaged resources — dev secrets can ship in installer (Phase 1 target).

---

## 4. Architecture Overview

```
VANOVA.exe (Electron 33.x)
├── desktop/main.js          — Shell, spawns runtime, opens dashboard webview
├── desktop/preload.js       — contextBridge API (window.maios.*)
├── desktop/ui/              — First-run setup wizard
└── Bundled resources (resources/maios/)
    ├── web/                 — Dashboard UI (static HTML/CSS/JS)
    ├── cloud/               — FastAPI backend (:8000, SQLite)
    ├── connector/           — Outbound bridge to Cloud + Hermes proxy
    ├── shared/              — Shared mock/utilities
    └── desktop/runtime/     — Local Runtime API (:8765)
            ├── api_server.py       — HTTP API for desktop + dashboard
            ├── process_manager.py  — Starts Cloud + Connector subprocesses
            ├── hermes_service.py   — Hermes health/lifecycle
            ├── hermes_chat.py      — Chat interface to Hermes CLI
            ├── task_queue.py       — In-memory agent task queue
            ├── integrations_store.py — Shopify/ERP/etc. configs (JSON file)
            ├── shopify_sync.py     — Background Shopify pull
            ├── config_store.py     — Local JSON config (%LOCALAPPDATA%)
            ├── health_monitor.py   — Service health checks
            ├── updater/            — Update download/verify/install
            └── ...
```

### Service ports

| Service | Host | Port | Auth today |
|---------|------|------|------------|
| Desktop Runtime API | 127.0.0.1 | **8765** | None |
| VANOVA Cloud | 127.0.0.1 | **8000** | JWT (access + refresh) |
| Hermes Agent | 127.0.0.1 | **8642** | API key (env) |
| Connector | — | outbound only | Device key |

### Data stores

| Store | Technology | Location |
|-------|------------|----------|
| Cloud DB | SQLite (`maios_cloud.db`) | `cloud/` (dev) |
| Runtime config | JSON files | `%LOCALAPPDATA%/VANOVA/config/` |
| Integrations | JSON (`integrations.json`) | `%LOCALAPPDATA%/VANOVA/config/` |
| Task queue | **In-memory Python lists** | Lost on runtime restart |
| Audit | JSONL | `cloud/audit.jsonl` (when enabled) |

### Key flows

1. **Install → First run:** Electron setup wizard → runtime analyzes system → installs deps → configures AI/Hermes
2. **Dashboard:** WebView loads `http://127.0.0.1:8000` (Cloud) with fallback to runtime `:8765`
3. **Connector:** Outbound HTTPS + device key → Cloud heartbeat → proxies Hermes to Cloud WebSocket
4. **Tasks:** UI → runtime `/api/tasks/run` → in-memory queue → `_execute_task()` checks Hermes health only (does not verify real execution)
5. **Updates:** Manifest fetch → SHA-256 verify → external PowerShell updater → rollback via backup

---

## 5. Known Issues (from codebase inspection)

### Updater

- **Signature verification is a placeholder** — `update_manager.py` logs "verification not yet implemented" when manifest has signature; only SHA-256 checked
- **Build lock failures** — `electron-builder` cannot rebuild when VANOVA is running (`app.asar` in use)
- **No Authenticode signing** — Windows installer not code-signed
- Update tests pass (13 tests) but cover manifest/state machine, not full install E2E on a live machine

### Shopify integration

- Tokens stored **plaintext** in `integrations.json` (`integrations_store.py`)
- **403 / scope errors** handled via `_parse_shopify_error()` with user-facing scope messages; common failure when app lacks `read_products` / `read_orders` approval
- Background sync thread can fail silently and persist error state in `config_store` under `shopifySync`
- Dashboard may show **mock data** when Cloud unreachable (`data-services.js` falls back to bundled mock labeled `dataMode: "mock"`)

### Connector

- Registration fails when `MAIOS_DEVICE_KEY` missing or Cloud credentials out of sync
- `process_manager.py` logs "Connector auth still failing — force-restarting Cloud to sync credentials"
- `connector.py` line 112: "Connector not registered — localhost recovery failed"
- Placeholder auth constant: `AUTH = "VANOVA-AUTH-TOKEN"`

### Task / agent execution

- **Fake completion:** `task_queue._execute_task()` returns `"Task executed via Hermes for {agentId}"` when Hermes health check passes — no actual tool invocation verified
- Queue and history are **in-memory** (`_queue`, `_history` lists) — lost on runtime restart
- No persistent TaskRun, Approval, or audit trail for agent actions

### Runtime / process management

- Port **8765** can be occupied by stale runtime; recovery scripts exist (`scripts/kill-stale-runtime-8765.ps1`)
- Cloud port **8000** similar zombie recovery in `port_utils.py`
- Multiple `.env` files: `cloud/.env`, `connector/.env` present in repo and in prior release bundle

### UX / honesty

- Many dashboard modules visible (Finance, Inventory, Production, etc.) may be placeholders
- Mock data fallback can make disconnected state look "connected" with sample record counts
- Honest state model (`real` / `partial` / `mock` / `empty`) exists in scanner but not uniformly enforced

### Git / secrets hygiene

- `.gitignore` covers `.env` and `*.db` but **not** `.env.*`, `logs/`, `data/`, `secrets/`, `*.sqlite*`
- `cloud/.env` and `connector/.env` exist on disk (values not documented here)
- No root `.env.example` with placeholders for all secret keys

---

## 6. Current Security Concerns

Priority aligned with Roadmap P0 items. **No secret values are listed below.**

### 6.1 Electron hardening (`desktop/main.js`)

```javascript
// Current webPreferences (both shell and dashboard):
contextIsolation: true      // ✓ good
nodeIntegration: false      // ✓ good
sandbox: false              // ✗ should be true
webSecurity: false          // ✗ should be true
allowRunningInsecureContent: true  // ✗ dashboard only
```

### 6.2 Runtime API — no authentication (`desktop/runtime/api_server.py`)

- Listens on `127.0.0.1:8765` with **zero auth** on any endpoint
- Mutating endpoints exposed without `Authorization` header:
  - `POST /api/tasks/run`, `/api/services/start`, `/api/services/stop`
  - `/api/hermes/restart`, `/api/install/run`, `/api/recovery`
  - `/api/files/add`, `/api/files/remove`, `/api/shopify/sync`
  - Integration config saves under `/api/integrations/{id}/config`
- **No `MAIOS_RUNTIME_TOKEN`** exists today

### 6.3 CORS wildcard (`desktop/runtime/api_server.py`)

```python
self.send_header("Access-Control-Allow-Origin", "*")
```

Applied to all JSON responses and OPTIONS preflight. Any local origin can call the runtime API.

### 6.4 Credential storage

- **Shopify tokens, ERP passwords, API keys** stored plaintext in `%LOCALAPPDATA%/VANOVA/config/integrations.json`
- Cloud secrets in `.env` files (dev copies in repo and release bundle)
- `process_manager.py` generates secrets on first run to user config dir (good pattern) but dev `.env` in repo remains a leak vector
- Documentation mentions `credentials.json` encrypted but integrations path is separate and unencrypted

### 6.5 In-memory task queue (`desktop/runtime/task_queue.py`)

- Tasks, history, and execution state not persisted
- Restart loses queued/running tasks
- Completion status not tied to real Hermes/tool results

### 6.6 Auth / session (Cloud)

- JWT access + refresh exist (`cloud/main.py`) but:
  - No refresh token rotation/revocation table
  - No rate limiting on `/login`
  - No RBAC enforcement on backend routes
  - Onboarding state partially in-memory

### 6.7 Input validation / path traversal

- Runtime endpoints accept JSON bodies without centralized schema validation
- File add/remove endpoints need path normalization audit (Phase 2.5)
- Subprocess usage in `process_manager.py`, `hermes_chat.py` — uses list args (good) but command paths come from config

### 6.8 Installer / release

- `extraResources` bundles entire `cloud/` and `connector/` trees with filter `!*.db` and `!audit.jsonl` only — **`.env` not excluded**
- No code signing on installer or update metadata
- SHA-256 alone used for update integrity

### 6.9 Connector

- Device key in env file; sync issues between Cloud and Connector env cause auth failures
- Localhost recovery endpoint (`/api/devices/register-local`) restricted to 127.0.0.1 (403 otherwise) — correct but dev-only pattern

---

## 7. Baseline Summary

| Area | Baseline status |
|------|-----------------|
| Unit tests | 31 passing, 0 failing |
| Python syntax | Clean |
| JS syntax (key files) | Clean |
| Typecheck / lint | Not configured |
| JS tests | Not configured |
| Fresh desktop build | Failed (file lock) |
| Prior v0.9.13 build | Present |
| Security posture | **Not commercial-ready** — see §6 |
| Agent execution | **Simulated** — Hermes health ≠ real execution |
| Task persistence | **None** — in-memory only |
| Secret hygiene | **At risk** — `.env` in repo and installer |

---

## 8. Next Steps

Proceed to **Phase 1 — Secret hygiene** per [`COMMERCIAL_READINESS_ROADMAP.md`](./COMMERCIAL_READINESS_ROADMAP.md):

1. Remove secrets from repository; add `.env.example`
2. Harden `.gitignore`
3. Exclude secrets from electron-builder `extraResources`
4. First-run secret generation (partially exists; extend for runtime token)
5. Secret rotation mechanism

**Rule for all subsequent phases:** Do not end any phase with fewer passing tests than this baseline (31/31).

---

*Generated during Phase 0 baseline audit. No application code was modified.*

---

## 9. Phase 1 — Secretos y Release Hygiene (2026-08-13)

**Status:** complete

### Changes

| Item | Result |
|------|--------|
| Root `.env.example` | Created with placeholders for Cloud, Connector, runtime, and AI keys (no real values) |
| `.gitignore` | Hardened: `.env.*`, `!.env.example`, `*.sqlite*`, `logs/`, `data/`, `secrets/` |
| `cloud/.env.example` | Demo password placeholder removed (empty values only) |
| `desktop/package.json` | electron-builder filters exclude `.env*`, dev DBs, audit logs, `logs/`, `data/`, `secrets/` |
| `desktop/runtime/install_secrets.py` | **New** — per-install secrets in `%LOCALAPPDATA%/VANOVA/config/install_secrets.json` |
| First-run secrets | `installationId`, `runtimeToken` (`MAIOS_RUNTIME_TOKEN`), `encryptionKeyFoundation`, `deviceIdentity` |
| Rotation | `rotateRuntimeCredentials()` in `install_secrets.py` + re-export from `config_store.py`; preserves install identity, grace-period previous tokens |
| Integration | Called from `launcher.py` (startup) and `process_manager._service_env()` (env injection) |

### Secret audit (values not recorded)

| Finding | Mitigation |
|---------|------------|
| `cloud/.env`, `connector/.env` on dev disk | Already gitignored; remain local-only dev files |
| Prior release bundles ship `.env` | Fixed for future builds via electron-builder excludes; rebuild required |
| `cloud/main.py` demo password fallback | Unchanged (Phase 5 auth hardening) |
| `MAIOS_RUNTIME_TOKEN` not enforced on API yet | Generated and stored; enforcement is Phase 2 |

### Tests after Phase 1

| Check | Result |
|-------|--------|
| `python -m pytest tests/ -v` | **PASS — 35/35** (31 baseline + 4 new `test_install_secrets.py`) |

### Known limitations

- Runtime API still accepts unauthenticated requests (Phase 2).
- Existing installed build under `%LOCALAPPDATA%/Programs/VANOVA` needs restart/rebuild to pick up `install_secrets.py`.
- Dev `.env` files on disk were not deleted (local dev convenience; not committed).

**Next phase:** Phase 2 — Local runtime security (Bearer auth, CORS, endpoint classification).

---

## 10. Phase 2 — Local Runtime Security (2026-08-13)

**Status:** complete

### Changes

| Item | Result |
|------|--------|
| `desktop/runtime/runtime_security.py` | **New** — CORS allowlist, READ/MUTATION classification, Bearer validation, input validators |
| `desktop/runtime/api_server.py` | All POST mutations require `Authorization: Bearer <runtimeToken>`; CORS `*` removed; JSON/body validation |
| `desktop/runtime/file_inventory.py` | Path normalization; rejects `..` traversal on add/remove |
| `desktop/preload.js` + `desktop/main.js` | IPC `getRuntimeAuthHeaders` reads token from `%LOCALAPPDATA%/VANOVA/config/install_secrets.json` (never logged) |
| `web/data-services.js`, `system-status.js`, `update-center.js` | Mutating runtime calls send Bearer via preload |
| `desktop/ui/setup.js`, `web/index.html`, `web/dashboard.html` | Setup/onboarding mutations authenticated |
| `tests/test_runtime_security.py` | **New** — 10 regression tests (401, invalid token, grace period, CORS, path traversal, recovery allowlist) |

### Security decisions

| Topic | Decision |
|-------|----------|
| READ endpoints | GET health, status, tasks, files, etc. remain **open** (localhost diagnostics / dashboard polling) |
| MUTATION endpoints | All POST routes require Bearer token (includes `/api/integrations/{id}/config`) |
| Grace period | `rotateRuntimeCredentials()` previous tokens accepted via `validate_runtime_token()` |
| CORS | Allowlist: `127.0.0.1:8000`, `127.0.0.1:8765`, `localhost` variants, `Origin: null` (Electron file://); optional dev ports when `MAIOS_DEV=1` |
| Command execution | `/api/recovery` component restricted to allowlist; subprocess paths unchanged (list args, no shell) |

### Tests after Phase 2

| Check | Result |
|-------|--------|
| `python -m pytest tests/ -v` | **PASS — 45/45** (35 after Phase 1 + 10 new security tests) |

### Known limitations

- Token available to renderer via preload IPC (required for dashboard mutations); not displayed in UI/logs
- Electron hardening (`webSecurity`, `sandbox`) deferred to Phase 3
- Cloud API auth/RBAC unchanged (Phase 5+)
- app.asar patch may require manual repack if npx asar extract fails (preload/main IPC still in repo)

**Next phase:** Phase 3 — Electron hardening.

