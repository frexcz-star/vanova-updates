# VANOVA Design System — v0.9.1

Single source of truth for visual tokens lives in `web/dashboard.html` `:root` and `desktop/ui/setup.css`.

## Principles

1. **Legibility over effects** — glass only on shell (sidebar, header, modals)
2. **One accent** — corporate red `#DC2626` / `#B91C1C` by default
3. **Consistent radius** — use scale only, never arbitrary values
4. **Honest UI** — status reflects real system state, never fake "active"

## Radius Scale

| Token | Value | Use |
|-------|-------|-----|
| `--radius-xs` | 6px | Badges, small chips |
| `--radius-sm` | 8px | Inputs, buttons, nav items |
| `--radius-md` | 12px | Cards, panels |
| `--radius-lg` | 16px | Modals, login card |
| `--radius-pill` | 999px | Status pills, tags |

## Spacing Scale

| Token | Value |
|-------|-------|
| `--space-1` | 4px |
| `--space-2` | 8px |
| `--space-3` | 12px |
| `--space-4` | 16px |
| `--space-5` | 24px |
| `--space-6` | 32px |

## Surfaces

| Token | Use |
|-------|-----|
| `--surface-solid` | Cards, forms, readable content |
| `--surface-glass` | Sidebar, header (with blur) |
| `--surface-2` / `--surface-3` | Nested elements, inputs |

## Status Indicators

| Class | Meaning |
|-------|---------|
| `.sys-ok` / `.sp-dot.ok` | Component healthy |
| `.sys-warn` / `.sp-dot.warn` | Degraded / partial |
| `.sys-err` / `.sp-dot.err` | Offline / critical |
| `.sys-checking` | Polling in progress |

## Real-time Status

`web/system-status.js` polls `http://127.0.0.1:8765/api/health/all` every 5s.

Header pill `#ai-status` → click opens `#status-pop` with component rows.

Recovery actions call `/api/recovery` on desktop runtime.

## Operation Feedback

`MAIOSSystemStatus.showOperation(msg)` — top progress bar + label  
`MAIOSSystemStatus.hideOperation()` — clears when done

Use for: dashboard load, Hermes queries, recovery, installs.

## Typography

- **Primary:** Inter 400/500/600/700
- **Mono:** Geist Mono (IDs, keys, timestamps)
- **Page title:** 26px / 700 / -0.8px tracking
- **Body:** 14px / 1.5 line-height
- **Labels:** 11px uppercase / 0.06em tracking

## Motion

- `--duration-fast` 120ms — hovers, toggles
- `--duration-normal` 180ms — panels, nav
- `--trans` — default easing `cubic-bezier(.4,0,.2,1)`
- Avoid continuous animation except: checking dot, operation bar

## Files

| File | Role |
|------|------|
| `web/dashboard.html` | Dashboard tokens + components |
| `web/system-status.js` | Live health UI |
| `desktop/ui/setup.css` | Setup wizard tokens |
| `docs/VANOVA_UI_AUDIT.md` | Known issues + roadmap |
