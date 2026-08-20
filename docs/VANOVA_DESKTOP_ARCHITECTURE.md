# VANOVA Desktop Architecture

## 1. Current Architecture (Audit)

| Layer | Technology | Entry Point |
|-------|-----------|-------------|
| Frontend | Plain HTML/CSS/JS (no framework) | `web/dashboard.html` |
| Backend | FastAPI + uvicorn (Python 3.11) | `cloud/main.py` |
| Connector | Python asyncio + httpx | `connector/connector.py` |
| Database | SQLite (`maios_cloud.db`) | File in `cloud/` |
| Auth | JWT access + refresh, bcrypt | `/api/auth/*` |
| Realtime | WebSocket | `/ws/dashboard` |
| Package manager | pip (venv via `install_all.py`) | `.venv/` |
| Build (web) | None — static files copied to `web/dist/` | Manual |
| Startup | `start_all.bat` | Cloud :8000 + Connector |
| Hermes | External CLI at `127.0.0.1:8642` | Via Connector |

### Existing onboarding
- Web dashboard has 7-step setup (ADR-7)
- API: `/api/onboarding/status`, `/api/onboarding/complete`
- **Not replaced** — desktop adds a parallel first-run wizard

### What's ready for desktop
- Static frontend served by FastAPI (embeddable in webview)
- Localhost-only Cloud (127.0.0.1:8000)
- Connector outbound-only model
- `.env`-based configuration
- Audit logging (JSONL)

### What needed adaptation
- No native shell → added Electron wrapper
- No system analyzer → added `desktop/runtime/system_analyzer.py`
- No installer → added electron-builder NSIS
- Hermes manual setup → added `HermesService`
- No company profile for agents → added structured profile + Business Analyst

---

## 2. Proposed Architecture

```
VANOVA.exe (Electron shell)
    ├── Setup UI (desktop/ui/) — first-run wizard
    ├── Dashboard WebView → http://127.0.0.1:8000 (existing web/)
    └── Desktop Runtime API (:8765)
            ├── System Analyzer
            ├── Dependency Resolver
            ├── Smart Installer
            ├── Hermes Service
            ├── Process Manager (Cloud + Connector)
            ├── AI Provider Config
            ├── Company Profile
            ├── Business Analyst (agent recommendations)
            ├── Agent Architect
            ├── Task Queue
            ├── Health Monitor + Auto-recovery
            └── Updater
```

User data: `%LOCALAPPDATA%/VANOVA/` (config, logs, credentials)

Installed app: `%LOCALAPPDATA%/Programs/VANOVA/` (Electron default)

Bundled resources: `resources/maios/` (cloud, connector, shared, web, runtime)

---

## 3. Tauri vs Electron Decision

### Tauri (evaluated first)
| Pro | Con |
|-----|-----|
| Lightweight (~5 MB) | Requires Rust toolchain (not installed) |
| Reuses web frontend | Python sidecar bundling less mature on Windows |
| Native performance | Additional build complexity for this stack |

### Electron (chosen for v0.9.0)
| Pro | Con |
|-----|-----|
| Node.js already available | Larger bundle (~150 MB) |
| electron-builder → real NSIS `.exe` | Heavier memory footprint |
| Mature Windows installer (shortcuts, uninstall) | |
| Python subprocess spawning well-tested | |
| No changes to existing dashboard | |

**Decision: Electron for v0.9.0.** Tauri remains viable for v1.0 after Rust toolchain setup and sidecar validation.

---

## 4. Risks

| Risk | Mitigation |
|------|-----------|
| Parallel development on another PC | Incremental changes only; no dashboard replacement |
| Python not on client PC | Runtime creates venv on first setup; future: bundle embeddable Python |
| Hermes not installed | Analyzer detects; setup configures path; graceful offline state |
| Port conflicts (8000, 8765) | Bind to 127.0.0.1 only; health checks before start |
| Secret leakage | Credentials in separate file; logs redact secrets |
| Large installer size | Acceptable for enterprise desktop product v1 |

---

## 5. Files Added (not modified destructively)

```
desktop/
├── main.js, preload.js, package.json
├── ui/ (setup wizard)
├── runtime/ (Python services)
└── assets/ (icon)
version.json
scripts/generate-checksums.js
docs/VANOVA_DESKTOP*.md
release/VANOVA-Setup.exe
```

### Files intentionally NOT modified
- `web/dashboard.html` — preserved
- `cloud/main.py` — preserved (no breaking API changes)
- `connector/connector.py` — preserved
- `shared/` — preserved

---

## 6. Migration Strategy

1. **v0.9.0**: Electron shell + setup wizard + runtime services
2. **v0.9.x**: Bundle embeddable Python; improve Hermes auto-install
3. **v1.0**: Evaluate Tauri migration; signed releases; mandatory update channel
4. **Existing dev workflow**: `start_all.bat` still works unchanged
