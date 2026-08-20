# VANOVA UI Audit — v0.9.0

Audit date: 2026-08-12  
Scope: `web/dashboard.html`, `web/data-services.js`, `desktop/ui/*`

---

## Executive Summary

VANOVA already has a solid design foundation (Inter, red corporate accent, CSS variables, glass on sidebar/header). The main gaps are **honest real-time feedback**, **status popover bugs**, and **visual density** in some views—not a missing design system from scratch.

Priority: **legibility, trust, live status** over decorative changes.

---

## What Works Well

| Area | Assessment |
|------|------------|
| Typography | Inter + Geist Mono, clear hierarchy in page titles |
| Color system | Red corporate accent, semantic success/warning/danger |
| CSS variables | Spacing, radius, shadows centralized in `:root` |
| Login | Clean, minimal, branded |
| Sidebar | Collapsible, grouped nav, glass treatment controlled |
| Data honesty | REAL / DEV SAMPLE / empty badges |
| Post-setup overlay | Step list + progress bar (real state checks) |
| Command palette | Keyboard-driven, professional pattern |

---

## Critical Issues (P0)

### 1. System status not real-time
- Header pill shows data mode only after load; no live Cloud/Hermes/Connector polling.
- `updateSystemStatus()` assumes Cloud OK because dashboard loaded—misleading when Connector/Hermes offline.
- **Fix:** Poll desktop runtime `GET /api/health/all` every 5s; reflect in header + popover.

### 2. Status popover DOM bug
- `set('sp-cloud', …)` targets `#sp-cloud` (`.sp-val`) but applies `.sp-dot` classes to it.
- Dot indicators never update correctly.
- **Fix:** Separate dot vs value element IDs.

### 3. App appears frozen during long operations
- Hermes ask, install, data load have no global progress indicator.
- User cannot tell if VANOVA is working or stuck.
- **Fix:** Global operation bar + button loading states.

### 4. Fake "AI System Active" copy
- Implies everything works when it may not.
- **Fix:** Replace with honest labels: System healthy / Degraded / Offline / Checking…

---

## High Issues (P1)

### Layout & density
- Command Center uses 5-column metric grid—dense on smaller screens (partially responsive).
- Some pages stack many `.card` blocks without section breathing room.
- **Recommendation:** Max 3 KPIs above fold; defer secondary metrics.

### Component inconsistency
- Border radius mix: 6px, 7px, 8px, 14px, 16px, 999px without documented scale.
- Button heights vary (34px header icons vs 44px `.btn`).
- **Recommendation:** Enforce `--radius-sm/md/lg/pill` only.

### Glass overuse on cards
- `.card` glass + blur on all cards reduces legibility on busy pages.
- **Recommendation:** Glass on shell (sidebar/header); solid `--surface` for content cards.

### Empty states
- Generic "empty" divs—functional but not actionable.
- **Recommendation:** Empty state + single CTA (Connect source / Run agent).

---

## Medium Issues (P2)

| Issue | Location | Notes |
|-------|----------|-------|
| Duplicate nav labels | Sidebar | Some groups overlap conceptually |
| Large page file | dashboard.html ~3350 lines | Acceptable for v0.9; extract JS later |
| Settings scattered | Multiple integration pages | OK for MVP |
| Mobile header hides status | `@media` line 420 | Expected; add status to drawer on mobile |
| Purple accent option | `[data-accent="purple"]` | Keep for user choice; default red |

---

## Anti-patterns Found (AI-generated look)

- [ ] Too many metric cards on home (5-up grid)
- [x] Purple not default (good)
- [ ] Gradient buttons on primary (subtle, acceptable)
- [ ] Large numbers without context in some metrics (shows "—" when null—good)
- [x] Glass on every card (reduce)
- [ ] Generic "AI System Active" (fixing)

---

## Design System Gaps

Existing tokens in `:root` cover most needs. Missing:

```css
--radius-pill: 999px;
--space-1: 4px; --space-2: 8px; --space-3: 12px; --space-4: 16px; --space-5: 24px; --space-6: 32px;
--surface-solid: var(--surface);
--surface-glass: rgba(18,18,21,.55);
--duration-fast: .12s;
--duration-normal: .18s;
```

Component variants needed:
- Status pill: `healthy | degraded | critical | checking`
- Operation bar: indeterminate progress
- Button: `loading` state with spinner

---

## Real-time Status Architecture (proposed)

```
Dashboard UI
    ↓ poll 5s
Desktop Runtime :8765 /api/health/all
    ↓
health_monitor.check_all()
    → VANOVA, Cloud, Connector, Hermes, AI Provider, Network

Dashboard also:
    ↓
Cloud :8000 /api/health (fallback if runtime unavailable)
```

UI surfaces:
1. Header status pill (click → popover)
2. Popover rows with dot + label + value
3. Optional recovery actions (restart Hermes) via `/api/recovery`

---

## Incremental Refinement Plan

| Phase | Work | Risk |
|-------|------|------|
| 0.9.1 | Real-time status + popover fix + op bar | Low |
| 0.9.2 | Card solid surfaces, radius scale | Low |
| 0.9.3 | Empty state CTAs, mobile status | Medium |
| 1.0 | Extract dashboard JS modules | Medium |

---

## Files to Modify (0.9.1)

- `web/system-status.js` (new)
- `web/dashboard.html` (header, popover, CSS, init)
- `web/dist/*` (sync)
- `desktop/runtime/api_server.py` (verify endpoint)
- `desktop/ui/setup.css`, `loading.html` (polish)

**Not modifying:** Cloud API routes, connector logic, page content structure.
