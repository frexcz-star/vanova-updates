# VANOVA Agent Architecture

## Concepts

```
Company Profile → Business Analysis → Agent Recommendations → Agent Creation
                                                                    ↓
Task Queue ← Scheduler / Events / Manual Triggers ← Agent Runtime (Hermes)
```

## Agent Definition Schema

```json
{
  "id": "marketing-agent",
  "name": "Marketing Agent",
  "description": "...",
  "responsibilities": [],
  "tools": [],
  "integrations": [],
  "triggers": ["schedule", "event", "manual"],
  "schedules": ["Daily 18:00"],
  "permissions": []
}
```

## Separation of Concerns

| Entity | Role |
|--------|------|
| **Agent** | Defined role with tools and permissions |
| **Task** | Single execution unit queued for an agent |
| **Trigger** | What initiates execution (schedule, event, manual) |
| **Schedule** | Cron-like timing |
| **Event** | Business event (new order, campaign, etc.) |

## Business Analyst

Located at `desktop/runtime/business_analyst.py`.

Input: `CompanyProfile` (channels, goals, description)

Output: Scored agent recommendations with human-readable reasons.

Example: Company uses Shopify + Instagram + Marketing goal → recommends Marketing Agent, Sales Analyst, Content Agent.

## Agent Architect

Located at `desktop/runtime/agent_architect.py`.

Creates agent configuration files stored in `%LOCALAPPDATA%\VANOVA\config\maios.json`.

## Task Queue

Located at `desktop/runtime/task_queue.py`.

- States: `queued`, `running`, `completed`, `failed`
- Supports retry and history
- Executes via Hermes when available

API: `POST /api/tasks/run` with `{ "agentId": "marketing-agent" }`

## Hermes as Runtime

VANOVA controls **what** runs; Hermes controls **how** it executes.

```
VANOVA (control plane)
  → Task Queue
    → Connector
      → Hermes CLI / API (127.0.0.1:8642)
```

HermesService (`desktop/runtime/hermes_service.py`) manages lifecycle independently of UI.

## Health & Recovery

`health_monitor.py` checks all components. Auto-recovery via `POST /api/recovery`:

```json
{ "component": "hermes" }
```

## Future (v1.0+)

- Event bus for Shopify/webhook triggers
- Persistent task queue in SQLite
- Agent permission enforcement
- Schedule sync with Hermes cronjobs
