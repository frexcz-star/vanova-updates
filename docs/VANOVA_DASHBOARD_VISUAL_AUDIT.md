# VANOVA Dashboard Visual Audit

**Date:** 2026-08-12  
**Scope:** `web/dashboard.html` (canonical), synced copies in `web/index.html` and `web/dist/`  
**Reference direction:** Intelly-style principles — clean, calm, structured, premium (not literal copy)

---

## 1. Executive Summary

The current VANOVA dashboard is functionally rich but visually dense. It follows a dark enterprise aesthetic (Vercel/Linear-inspired) with corporate red accent, glassmorphism on main surfaces, ambient gradient orbs, and many small competing cards. The home screen alone presents **12+ distinct visual blocks** before scrolling. Typography, spacing, and color are inconsistent with a calm premium product feel. A redesign should reduce visual noise, establish clear hierarchy, adopt a soft pastel palette with generous whitespace, and reserve liquid glass exclusively for overlays.

---

## 2. Current Architecture Map

| Layer | Location | Notes |
|-------|----------|-------|
| Design tokens | Inline `<style>` in `dashboard.html` `:root` | Dark-first, red accent, glass vars |
| Views | JS render functions (`viewHome`, `viewAgents`, …) | 25+ screens, all inline HTML strings |
| Navigation | `NAV` array + `buildNav()` | 7 groups, 28 items |
| Data | `store` + `loadAppData()` via `data-services.js` | Real/mock/empty modes |
| Health | `system-status.js` → `#ai-status`, `#status-pop` | Polling :8765 |
| Updates | `update-center.js` → `#maios-dashboard-update`, `#maios-update-center`, `#hdr-update` | Desktop API :8765 |
| Build marker | `<!-- VANOVA-UI-BUILD: 20260812 -->` | Cache bust on JS |

---

## 3. Screen Inventory

| Screen | Renderer | Primary issues |
|--------|----------|----------------|
| **Home / Command Center** | `viewHome` | 5 KPI metrics + pulse + update + Hermes + priorities + autonomy + activity + CEO banner = too many blocks |
| **Insights** | `viewInsights` | Duplicate priority card pattern; large badges |
| **Activity** | `viewActivity` | Card wrapping timeline; large status badges |
| **Decisions** | `viewDecisions` | OK structure; accent borders heavy |
| **Agents** | `viewAgents` | 12 cards × nested meta boxes = visual noise |
| **Agent Detail** | `viewAgentDetail` | Nested cards with tables inside tables |
| **Hermes** | `viewHermes` | Multiple cards; orchestration nodes use red gradients |
| **Automation** | `viewAutomation` | Nested p-meta inside cards |
| **Data Lake** | `viewLake` | Gradient core block; accent-heavy outputs |
| **CEO Brief** | `viewCeo` | 5 metrics again + nested tables in card |
| **Settings** | `viewSettings` | 6 cards in 2-col grid; updates section OK |
| **Integrations** | `viewIntegrations` | 11 integration cards — acceptable but dense |
| **System Map** | `viewMap` | Accent-filled nodes |
| **Approvals** | `viewApprovals` | Large danger badges |
| **Files** | `viewFiles` | Table-in-card pattern |
| **Business views** | `noData` / `genericTable` | Generic "No data available" empty states |
| **Onboarding** | `#setup-modal` | Glass box + gradient orbs (acceptable for overlay) |
| **Login** | `#login` | Glow orb + gradient logo |

---

## 4. Home Screen — Block Analysis

### Current layout (top to bottom)

1. **Page head** — greeting, sub-stats (opportunities/risks/decisions), freshness bar
2. **Two-column grid (280px | 1fr)**
   - Left column: VANOVA Pulse, Update widget, Hermes CTA
   - Right column: **5 metric cards** (Revenue, Orders, Gross Margin, Customers, Inventory)
3. **AI Priorities** — 2-column grid of full priority cards (each with meta grid, actions, reason)
4. **Two-column grid**
   - Autonomy model (3 aut-items + 6 chips)
   - Activity preview (5 items)
5. **CEO Daily Brief banner** — gradient header, duplicate CTA to ceobrief

### Problems

| Issue | Severity |
|-------|----------|
| 5 KPI metrics compete with Pulse for attention | High |
| Autonomy model duplicates Settings content | Medium |
| CEO banner repeats nav item "Informe CEO" | Medium |
| Left sidebar column (280px) creates unbalanced layout on wide screens | Medium |
| Priority cards show 3 meta boxes + 3 action buttons each — too dense for overview | High |
| Metric cards use 24px bold values — KPI cliché | Medium |

### Recommended home composition (4–6 blocks)

1. **Header** — greeting + freshness (keep)
2. **Metrics strip** — 4 key metrics in one calm row (drop Inventory to secondary)
3. **Primary row** — AI Priorities (left, 2-up) + Activity timeline (right)
4. **Secondary row** — System pulse + subtle update widget + Hermes entry
5. Remove autonomy block and CEO banner from home

---

## 5. Design System Inconsistencies

### Color

- Default `data-theme="dark"` + `data-accent="red"` — opposite of requested pastel calm
- `body::before` ambient gradients include **purple** (`rgba(124,58,237,.10)`) — AI-dashboard cliché
- Three fixed `.orb` divs with accent/purple glows
- Glass on sidebar, header, AND cards (lines 707–747)
- `--accent-glow` used on primary buttons with breathing animation
- Hardcoded `#dc2626` / `#DC2626` in JS-rendered HTML and `update-center.js` styles

### Radius

- Tokens: xs 6px → lg 16px; user target is **24–32px feel** for cards
- Mixed inline radii (7px, 8px, 10px, 11px) in components

### Shadows

- `--shadow-md` includes 1px border ring + drop shadow — doubles with `border: 1px solid`
- Hover lifts on agent-card, int-card with `translateY(-2px)` + large shadow

### Typography hierarchy

| Level | Current | Target |
|-------|---------|--------|
| Page title | 26px/700 | 28–32px/600, more whitespace below |
| Section title | 15px/600 | 18px/600 |
| Card title | Mixed 14–15px | 16px/600 |
| Body | 13–14px | 14px/1.55 |
| Metadata | 9–11px uppercase | 12px regular, no excessive uppercase |

### Spacing

- Content padding `28px 32px` — OK
- Grid gaps `16px` — should be `20–24px` for calm feel
- Section margin `32px` — OK

---

## 6. Component Audit

### Sidebar

- Glass background + frosted blur
- Active state: accent-soft fill + 3px left bar (good pattern, needs softer colors)
- Group headers uppercase 12px — noisy
- Collapsed mode OK functionally

### Header

- 60px glass bar with many controls: burger, back, title, workspace, search, bell, theme, status pill, Hermes, user
- Status pill `#ai-status` — appropriate size
- `#hdr-update` injected by JS — not in HTML template

### Cards (`.card`, `.metric`, `.priority`, `.agent-card`)

- **Nested cards:** priority cards contain `.p-meta-item` boxes; agent cards contain `.am` boxes — violates "no nested cards"
- All use `--radius-md` (12px) — too small for target aesthetic
- Hover shadow on every card type

### Badges (`.badge`)

- Large pill badges with background fills — user wants **small dot indicators** (● Healthy)
- Used for agent status, activity status, integration status

### Activity (`.act-item`)

- Structure OK (timeline-like)
- Status uses full `.badge` — should be dot + text
- Wrapped in `.card.card-pad` on Activity screen — unnecessary nesting

### Agents (`.agent-card`)

- Shows: avatar, name, desc, insights/tasks meta grid, current task box, status badge, autonomy tag
- User wants: **Name, Purpose, Status first** — hide insights/tasks/current on list view

### Update widget

- `#maios-dashboard-update` in left column — good placement
- Current copy: "Version X" + long status text — target: **"VANOVA X.X.X ● Up to date" + Refresh**
- Styled as bordered box — should be more subtle/inline

### Empty states (`.empty`, `.state-box`)

- Generic copy: "No data available", "No hay prioridades activas"
- Need human-designed messages with icon + action link (partially present in `noData`)

### Tables

- Used in Agent Detail, CEO Brief, Products, Files — dense for activity; timeline preferred where possible

---

## 7. Redundant / Duplicate Information

| Duplication | Locations |
|-------------|-----------|
| 5 KPI metrics | Home + CEO Brief |
| Opportunity/risk/decision counts | Home subtitle + Pulse widget |
| Autonomy explanation | Home card + Settings + Agent Detail |
| CEO brief teaser | Home banner + ceobrief nav + CEO Copilot agent |
| Hermes entry | Sidebar + header button + home CTA |
| System health | Pulse + header status pill + status popover |
| Activity preview | Home + Activity screen |

---

## 8. JavaScript Hook Inventory (must preserve)

### update-center.js

| ID / Selector | Purpose |
|---------------|---------|
| `#maios-dashboard-update` | Dashboard compact widget |
| `#maios-dashboard-update-host` | Mount container |
| `#maios-dash-refresh` | Refresh button |
| `#maios-dash-restart-update` | Install button |
| `#maios-update-center` | Settings full panel |
| `#settings-updates-host` | Settings mount |
| `#maios-check-updates`, `#maios-install-update`, `#maios-cancel-update` | Settings actions |
| `#hdr-update` | Header indicator (injected) |
| `[data-nav="settings"]` | Nav badge — **MISSING in buildNav** (uses `data-view` only) |
| `.maios-dash-update`, `.maios-dash-update-*` | Widget classes |
| `.update-badge` | Nav dot |

### system-status.js

| ID | Purpose |
|----|---------|
| `#ai-status` | Header health pill |
| `#status-pop` | Popover |
| `#sp-dot-*`, `#sp-val-*` | Component rows |
| `#sp-restart-cloud`, `#sp-restart-hermes` | Recovery |
| `#maios-op-bar`, `#maios-op-text` | Operation feedback |

### dashboard.html core

| ID / attr | Purpose |
|-----------|---------|
| `#content`, `#side-nav`, `.nav-item[data-view]` | Navigation |
| `#cmd`, `#cmd-input`, `#cmd-list` | Command palette |
| `#drawer`, `#drawer-*` | Detail drawer |
| `#setup-modal`, `#setup-loading` | Onboarding |
| `#login`, `#app` | Auth shell |
| `#theme-toggle`, `data-theme`, `data-accent` | Appearance |
| `#hermes-q`, `#orch-wrap`, `#hermes-sessions` | Hermes |
| `data-go`, `data-act`, `data-priority-id` | Event delegation |

---

## 9. Anti-Patterns Present (to remove)

1. Purple gradient orb (`rgba(124,58,237,.18)`) — AI cliché
2. Glass on sidebar, header, cards — move glass to overlays only
3. `btn-primary` breathing glow animation
4. Continuous pulse on all green dots
5. Card stagger fade-in animation (8 nth-child rules)
6. `translateY(-2px)` hover on all interactive cards
7. Linear gradient on primary buttons
8. Dark theme as default for a "calm pastel" product
9. Giant KPI values (24px bold metrics)
10. Uppercase micro-labels everywhere

---

## 10. Responsive Behavior

- Breakpoints at 1200px, 900px, 600px, 760px — functional
- Home grid `280px 1fr` forced via inline style — breaks on mobile (partial fix at 760px)
- Sidebar mobile overlay OK

---

## 11. Recommended Design System (post-redesign)

### Tokens

```
Colors: cream bg (#F7F6F3), white surfaces, pastel semantic blocks
        (yellow/pink/green/blue/lavender) for meaningful grouping
Radius: sm 12px, md 20px, lg 28px, xl 32px, pill 999px
Spacing: 4/8/12/16/24/32/48
Shadows: minimal — sm only on hover, none on rest
Typography: Inter — page 30px, section 18px, card 16px, body 14px, meta 12px
Glass: cmd palette, drawer, modals, setup wizard, status-pop only
```

### Components to consolidate

- `DashboardCard` → `.dash-card`
- `StatusIndicator` → `.status-dot` + `.status-label`
- `SectionHeader` → `.section-head` (existing, refine)
- `Metric` → `.metric` (simplify)
- `ActivityItem` → `.act-item` (dot status)
- `AgentCard` → `.agent-card` (simplified)
- `EmptyState` → `.state-box` (human copy)

---

## 12. Implementation Priority

1. **P0 — Tokens + shell:** `:root`, remove orbs/glass from main, sidebar, header redesign
2. **P0 — Home:** Reduce to 4–6 blocks, simplify metrics and priorities
3. **P1 — Agents + Activity:** Simpler cards, timeline status dots
4. **P1 — Agent Detail:** Flatten nested structure
5. **P2 — Settings, Integrations, CEO Brief:** Apply new tokens
6. **P2 — Empty states:** Human copy pass
7. **P3 — Login/onboarding:** Soft pastel, keep glass (overlay context)
8. **Fix:** Add `data-nav="settings"` to settings nav item for update badge

---

## 13. Files to Sync After Changes

- `web/dashboard.html` → `web/index.html`
- `web/dashboard.html` → `web/dist/dashboard.html`
- `web/dashboard.html` → `web/dist/index.html`
- Update build marker and `?v=` on `update-center.js`

---

## 14. QA Checklist

- [ ] All nav items route correctly
- [ ] Command palette (⌘K) works
- [ ] Hermes send/receive flow
- [ ] Update widget refresh + settings panel
- [ ] System status popover + recovery buttons
- [ ] Theme toggle + accent swatches
- [ ] Sidebar collapse + mobile overlay
- [ ] Agent card → detail navigation
- [ ] Priority actions (review/approve/dismiss)
- [ ] Onboarding wizard still readable
- [ ] Responsive at 1280, 900, 600px widths
