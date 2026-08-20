# VANOVA Desktop Application

## Overview

VANOVA Desktop is a Windows application that wraps the existing VANOVA Cloud + Connector stack with a premium setup experience and native shell.

## Quick Start (Development)

```powershell
cd C:\Users\Admin\maios\desktop
npm install
npm run desktop:dev
```

## Architecture

See [VANOVA_DESKTOP_ARCHITECTURE.md](./VANOVA_DESKTOP_ARCHITECTURE.md).

## Components

| Component | Port | Purpose |
|-----------|------|---------|
| Electron shell | — | Native window, setup UI, webview |
| Desktop Runtime API | 8765 | System analysis, install, Hermes, agents |
| VANOVA Cloud | 8000 | Dashboard + API (unchanged) |
| Hermes | 8642 | Agent runtime (external) |

## User Data Locations

| Path | Contents |
|------|----------|
| `%LOCALAPPDATA%\VANOVA\config\` | Company profile, AI config, agents |
| `%LOCALAPPDATA%\VANOVA\config\credentials.json` | Encrypted API keys |
| `%LOCALAPPDATA%\VANOVA\logs\` | Structured JSONL logs |

## Build Commands

```powershell
npm run desktop:dev        # Development mode
npm run desktop:build      # Build without installer
npm run desktop:installer  # Build VANOVA-Setup.exe
npm run release            # Installer + checksums.txt
```

## Design System

- Primary accent: `#DC2626` / `#B91C1C`
- Font: Inter
- Style: Liquid glass (moderate blur), minimal, enterprise
- No emojis in UI chrome

## Settings Structure

Settings are accessible from the dashboard (existing) plus desktop runtime:

- General, AI Providers, Hermes, Agents, Integrations
- Appearance, Updates, Security, Diagnostics

Diagnostics: `GET http://127.0.0.1:8765/api/diagnostics` (no secrets included)

## Version

Single source of truth: `version.json` at repo root.
