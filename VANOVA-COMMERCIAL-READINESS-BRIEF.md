# MAIOS — Commercial Readiness Brief (v1.0.1)

**Purpose:** Context for external reviewers (ChatGPT, investors, security auditors) evaluating whether MAIOS is commercially marketable.

- **Product:** MAIOS — MOOVING AI Operating System
- **Publisher:** MOOVING PAPER / BlisArtPaper
- **Version:** `1.0.1` (`version.json`, `desktop/package.json`)
- **Platform:** Windows desktop (Electron + bundled Python runtime)
- **Workspace:** `C:\Users\Admin\maios`
- **Last updated:** 2026-08-13

---

## Executive Summary

MAIOS is a commercial desktop application that unifies an AI command center, local agent orchestration (Hermes), cloud-backed dashboard access, and Shopify e-commerce integration for small business owners. The product ships as a signed-ready NSIS installer built with Electron; user data lives in `%LOCALAPPDATA%\MAIOS\`, not inside the install directory.

**Assessment posture:** Core product functionality, security hardening, updater architecture, and automated test coverage are substantially complete. **Commercial launch blockers are primarily infrastructure:** CDN hosting, Authenticode code signing, and a full end-to-end update test on a real 1.0.0 → 1.0.1 upgrade path.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  MAIOS Desktop (Electron)                                       │
│  ├─ Web UI (dashboard.html, update-center.js)                   │
│  ├─ Python Runtime API :8765 (FastAPI-lite, local services)     │
│  │    ├─ Hermes chat / file upload / Shopify setup               │
│  │    ├─ Process manager (Cloud + Connector lifecycle)           │
│  │    ├─ Custom updater (UpdateManager)                          │
│  │    └─ Integrations store (encrypted tokens)                   │
│  └─ Bundled resources → %LOCALAPPDATA%\Programs\MAIOS\          │
└───────────────────────────┬─────────────────────────────────────┘
                            │ outbound HTTPS (no inbound ports)
┌───────────────────────────▼─────────────────────────────────────┐
│  MAIOS Cloud (FastAPI :8000) — hosted or local dev              │
│  ├─ JWT auth (access + refresh), bcrypt, rate-limit             │
│  ├─ SQLite (users, devices, activity, decisions, audit)         │
│  ├─ WebSocket /ws/dashboard (realtime push)                     │
│  └─ Serves web/dist static dashboard                            │
└───────────────────────────┬─────────────────────────────────────┘
                            │ outbound connection (device key)
┌───────────────────────────▼─────────────────────────────────────┐
│  MAIOS Connector (PC del dueño)                                 │
│  ├─ Heartbeat + push snapshots to Cloud                         │
│  ├─ Never opens inbound ports                                   │
│  └─ Bridges Hermes Agent (127.0.0.1:8642) data to Cloud         │
└─────────────────────────────────────────────────────────────────┘
```

### Key design decisions

| Area | Decision | Rationale |
|------|----------|-----------|
| Desktop shell | Electron + electron-builder (NSIS) | Native Windows installer, auto-update compatible |
| Local services | Bundled Python 3.11 runtime on port 8765 | Hermes integration, local API, updater orchestration |
| Cloud backend | Python FastAPI + SQLite | Portable, zero external DB dependency at launch |
| Remote access | Connector with **outbound-only** connection | PC owner never exposes local ports to Internet |
| Data layer | `web/data-services.js` → store pattern | UI never hardcodes data; honest `real` / `mock` / `empty` modes |
| User data | `%LOCALAPPDATA%\MAIOS\` | Survives app updates; separated from binaries |
| Updates | **Custom updater** (NOT electron-updater) | NSIS silent install, SHA-256 verify, rollback on failure |

---

## What's Implemented (1.0.1)

### Desktop & Runtime
- Electron app with hardened preload, CSP, and local API on `:8765`
- Python runtime: launcher, process manager, health monitor, diagnostics
- Config store, credential vault, integration token encryption
- File organizer, business scanner, backup service (WAL + retention)
- Observability: correlation IDs, JSONL structured logging

### Cloud & Connector
- FastAPI cloud: auth, RBAC, tenancy, rate limiting, audit log
- Connector: device registration, heartbeat, authenticated push
- WebSocket realtime dashboard updates
- Onboarding flow, command center, decisions/approvals engine

### Hermes Integration
- Hermes chat API with activity tracking
- File upload to Hermes workspace
- Hermes-guided Shopify setup conversation (`hermes_shopify_setup.py`)
- Token bridge: sync Shopify credentials from Hermes env → MAIOS integrations store

### Shopify Bridge
- Shopify sync lifecycle: disconnected → connected → syncing → partial → error → reauth_required
- Permission-denied and network-error classification
- Products empty state (errors no longer shown as fake product rows)
- Disconnect without losing URL metadata

### Custom Updater
- Full state machine: check → download → verify (SHA-256) → backup → install → restart → verify → rollback
- Spanish UI modal (~4s after startup), Settings → Actualizaciones panel
- Background auto-download, periodic check every 4h
- External `maios-updater.ps1` for NSIS silent install after app exit
- Manifest: `release/latest.json` (production), `release/latest.local.json` (dev)
- Publish script: `scripts/publish-update.ps1` → CDN staging bundle

### Security
- JWT access (60 min) + refresh (7 days), bcrypt passwords
- Integration tokens encrypted at rest
- CORS allowlist, runtime security tests, install-secrets audit
- SHA-256 integrity on update packages (Authenticode verification documented but not yet enforced)

### Tests
- **159 automated tests** (`python -m pytest tests/ -v`)
- Coverage includes: updater, cloud auth, RBAC, runtime security, Shopify bridge/setup, stabilization audit, E2E smoke, production hardening

---

## Recent Fixes (1.0.1 stabilization)

| Fix | Description | Key files |
|-----|-------------|-----------|
| Connector auth | Distinguishes running vs authenticated vs registered; backfills missing device key in connector.env | `process_manager.py`, `health_monitor.py` |
| Dashboard status | Connector labels: "conectado" / "requiere autenticación" / "desconectado" | `health_monitor.py`, `system-status.js` |
| Products empty state | Shopify permission errors no longer rendered as product entities | `file_organizer.py`, `shopify_sync.py` |
| Hermes file upload | Upload pipeline to Hermes workspace | `hermes_chat.py`, `hermes_activity.py` |
| Hermes Shopify setup chat | Conversational Shopify onboarding via Hermes | `hermes_shopify_setup.py` |
| Token bridge | Auto-sync Shopify credentials from Hermes `.env` to integrations store | `hermes_config.py`, `integrations_store.py` |

---

## Commercial Release Blockers

These are **external infrastructure / validation** items, not missing core product code:

| # | Blocker | Status | Notes |
|---|---------|--------|-------|
| 1 | **CDN upload** | Pending | Upload `release/publish/` → `https://releases.moovingpaper.com/maios/` |
| 2 | **Authenticode signing** | Pending | Sign `MAIOS-Setup-*.exe`; runtime signature verification not yet implemented |
| 3 | **E2E update test** | Pending | Full 1.0.0 → 1.0.1 on real installed baseline (Download → Install → Restart → verify) |
| 4 | **True 1.0.0 baseline** | Pending | Copying exe without rebuild doesn't change embedded `version.json`; need faithful baseline for E2E |

### Optional post-launch
- Playwright browser E2E in CI
- macOS build + notarization
- Manifest signature verification with embedded public key

---

## Data & Privacy

- User DB, config, credentials, Hermes workspaces: `%LOCALAPPDATA%\MAIOS\`
- App binaries: `%LOCALAPPDATA%\Programs\MAIOS\`
- Secrets only in `.env` files (excluded from source ZIP; `.env.example` included)
- No user data stored inside `app.asar` or install directory

---

## Key Files for Reviewers

| Area | Path |
|------|------|
| Version | `version.json` |
| Electron config | `desktop/package.json` |
| Local API | `desktop/runtime/api_server.py` |
| Updater orchestrator | `desktop/runtime/update/update_manager.py` |
| Updater UI | `web/update-center.js` |
| Cloud entry | `cloud/main.py` |
| Connector | `connector/connector.py` |
| Hermes Shopify setup | `desktop/runtime/hermes_shopify_setup.py` |
| Token bridge | `desktop/runtime/integrations_store.py` |
| Dashboard UI | `web/dashboard.html` |
| Test suite | `tests/` (159 tests) |
| Update docs | `docs/VANOVA_UPDATES.md`, `docs/UPDATER_SIGNING.md` |
| Architecture ADRs | `ARCHITECTURE_DECISIONS.md` |
| Release checklist | `docs/RELEASE_CHECKLIST.md` |

---

## Build & Verify Commands

```powershell
cd C:\Users\Admin\maios

# Run all tests
.\.venv\Scripts\python.exe -m pytest tests/ -v

# Build installer
scripts\release.ps1 -Version 1.0.1

# Stage CDN bundle
scripts\publish-update.ps1 -Version 1.0.1

# Local update test (requires MAIOS 1.0.0 installed)
scripts\setup-local-updates.ps1 -OfferVersion 1.0.1 -ResetState
scripts\sync-to-installed.ps1
```

---

## Questions for Commercial Evaluation

1. Is the outbound-only Connector architecture sufficient for SMB security expectations?
2. Is SQLite adequate for initial commercial scale, or should PostgreSQL be a launch requirement?
3. Are 159 unit/integration tests sufficient pre-launch, given no full browser E2E yet?
4. Is shipping without Authenticode verification (SHA-256 only) acceptable for v1.0.1, with signing as a fast-follow?
5. Is the custom updater (vs electron-updater) a support risk or a maintainability win?
6. Does the Shopify + Hermes integration provide enough differentiated value for the target market?

---

## Related Documents

- `VANOVA-UPDATE-SYSTEM-BRIEF.md` — Detailed updater architecture for ChatGPT
- `docs/VANOVA_UPDATES.md` — Full update flow documentation
- `docs/IMPLEMENTATION_PROGRESS.md` — Phase-by-phase implementation log
- `docs/COMMERCIAL_READINESS_ROADMAP.md` — Original roadmap (if present)
- `release/SOURCE-ZIP-README.txt` — What's included/excluded in this source ZIP
