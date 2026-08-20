# VANOVA Setup Guide

## End User Installation

1. Download `VANOVA-Setup.exe` from the release folder
2. Double-click to run the installer
3. Follow the setup wizard:
   - **Environment Analysis** — VANOVA checks your PC
   - **Company Setup** — Name, description, channels, goals
   - **AI Provider** — Select provider, enter API key, test connection
   - **Setup** — VANOVA installs runtime, services, and Hermes
   - **Agents** — Review and create recommended agents
   - **Ready** — Open dashboard

4. VANOVA opens automatically after setup

## What Gets Installed

- VANOVA application (`VANOVA.exe`)
- Desktop shortcut and Start Menu entry
- Bundled Cloud, Connector, and web dashboard
- User configuration in `%LOCALAPPDATA%\VANOVA\`

## Requirements

- Windows 10/11 64-bit
- 4 GB RAM minimum (8 GB recommended)
- 2 GB free disk space
- Internet connection (for AI providers and updates)
- Python 3.11+ (auto-configured during setup if not present)

## Hermes

Hermes is configured during setup if detected on the system. If not installed:

1. Install Hermes separately
2. Open VANOVA → Settings → Hermes
3. Set the path to `hermes.exe`

VANOVA will not download arbitrary scripts from the internet.

## Uninstall

Windows Settings → Apps → VANOVA → Uninstall

User data in `%LOCALAPPDATA%\VANOVA\` is preserved by default.

## Developer Setup (Existing Workflow)

The original workflow still works:

```powershell
python install_all.py
start_all.bat
# Open http://127.0.0.1:8000
```

## Troubleshooting

| Issue | Action |
|-------|--------|
| Setup stuck on "Analyzing" | Ensure port 8765 is free; restart VANOVA |
| Dashboard won't load | Check Cloud at http://127.0.0.1:8000/api/health |
| Hermes offline | Settings → Hermes → Restart |
| View logs | `%LOCALAPPDATA%\VANOVA\logs\maios-desktop.jsonl` |

Export diagnostics from Settings → Diagnostics or via API.
