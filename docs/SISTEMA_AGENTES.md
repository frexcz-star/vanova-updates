# SISTEMA DE AGENTES — VANOVA MVP

**Objetivo:** que el empresario no-técnico cree y gestione sus propios agentes de
IA (ventas, contabilidad, stock…) **dentro de VANOVA**, sin saber código, con
Hermes como motor de fondo.

---

## 1. Sistema actual (revisado)

El sistema de agentes ya existía, construido antes de la actualización de bots
de Hermes:

| Componente | Qué hace | Estado |
|---|---|---|
| `agent_architect.py` | Catálogo de agentes + crear/añadir/ejecutar + lista enriquecida con estado real | ✅ |
| `agent_scheduler.py` | Programación recurrente (Daily/Weekly) + análisis proactivo 6h | ✅ |
| `agent_data_tools.py` | 20+ tools de lectura de datos reales (productos, ventas, clientes, facturas) | ✅ |
| `agent_permissions.py` | Gate de permisos por agente | ✅ |
| `business_analyst.py` | `AGENT_CATALOG` (6 agentes predefinidos) + recomendación por perfil | ✅ |
| `task_queue.py` | Cola de ejecución: permiso → política → aprobación → Hermes CLI | ✅ |
| Vista Agents (`dashboard.html`) | Ver agentes, añadir del catálogo, ejecutar ahora, detalle | ✅ |

**Cómo se ejecuta un agente hoy:** el agente (definición declarativa) se encola
en `task_queue`, y la tarea se resuelve **una consulta one-shot a Hermes CLI**
(`hermes chat -q`), con los datos reales de VANOVA inyectados en el contexto.

**La brecha que el usuario señaló:** los agentes de VANOVA son *definiciones +
tareas puntuales* de Hermes. No son **bots persistentes** de Hermes (perfil
propio, canal de mensajería, conversación continua). La infraestructura de bots
de Hermes (profiles, bot-mode) es más potente pero está poco aprovechada.

---

## 2. Diseño de la migración (a medio plazo)

**Fase A — MVP (implementada ahora):** el empresario crea sus propios agentes
desde la UI sin código.
- Nuevo endpoint `POST /api/agents/custom` (`agent_architect.create_custom_agent`).
- El empresario da **nombre + área/rol** (ventas/contabilidad/stock/marketing/
  soporte/CEO/general).
- El rol se traduce a **permisos de solo lectura seguros** (`_CUSTOM_ROLE_PERMISSIONS`).
- El agente se guarda idempotente y se ejecuta igual que el resto (task_queue → Hermes).
- UI: botón "Crear agente" en la vista Agents + modal sin código.

**Fase B — bots persistentes de Hermes (en curso, por pasos):** cada agente
VANOVA → un **perfil Hermes real** (bot) con su propia identidad, memoria,
skills y canal. La ejecución pasa de one-shot a persistente/rutina.

---

## 2b. FASE B — Migración completa: agente VANOVA → bot Hermes persistente

### 2b.1 Qué es un bot de Hermes (verificado en esta instalación)

Un bot de Hermes **es un perfil** (`~/.hermes/profiles/<name>/`). No hay
primitiva nueva. Cada bot tiene:
- `SOUL.md` — la personalidad e instrucciones permanentes del agente.
- `memories/MEMORY.md` + `memories/USER.md` — memoria propia y persistente.
- `config.yaml` — su propio modelo/proveedor, skills, toolsets.
- Un **Bot Chat** canónico y persistente (conversación continua).
- **Routines** = cron jobs namespaced `[bot:<name>] …` (ver `hermes cron list`).
- Canal/mensajería opcional (Telegram/Discord/…).

Crear un bot desde CLI:
```
hermes profile create <nombre> [--clone] [--no-alias]
# luego escribir su SOUL.md
```
Y es visible en el **Hermes desktop** (pestaña Bots) y en CLI con
`hermes -p <nombre> chat`.

### 2b.2 Mapeo agente VANOVA → perfil Hermes

| Agente VANOVA (Fase A) | Perfil Hermes (Fase B) |
|---|---|
| `id` (`custom-ventas`) | `profile_name` → `vanova-ventas` (namespaced) |
| `name` | título/descripción del bot |
| `role` (ventas/contabilidad/stock/…) | SOUL.md (personalidad + responsabilidades) |
| `permissions` (solo lectura) | toolsets restringidos del perfil |
| datos reales de VANOVA | inyectados vía `agent_data_tools` en el contexto de cada run |
| `schedules` (agent_scheduler) | rutina cron `[bot:<name>]` |
| ejecución one-shot (task_queue→CLI) | ejecución persistente (bot + cron) |

### 2b.3 Mecanismo de sincronización (paso a paso)

**Paso 1 — Generador de perfil bot.** Nuevo módulo
`desktop/runtime/agent_hermes_bot.py` con:
- `sync_agent_to_bot(agent)` → crea/actualiza el perfil Hermes del agente:
  1. `hermes profile create vanova-<slug> --no-alias` (si no existe).
  2. Escribe `SOUL.md` desde `name` + `role` + `description` + `responsibilities`
     (personalidad del agente, en español, con las reglas de honestidad de VANOVA).
  3. Escribe `memories/` inicial (rol, empresa, regla "usa datos reales, nunca € inventado").
  4. Opcional: pin modelo (igual que el activo) y skills/toolsets solo lectura.
- `ensure_bot(agent)` — idempotente: si el perfil existe, solo actualiza SOUL.md.
- `remove_bot(agent)` — borra el perfil al eliminar el agente (coherente).

**Paso 2 — Coexistencia.** Fase A sigue intacta. `create_custom_agent` llama
`sync_agent_to_bot` como efecto secundario opcional (si Hermes está disponible).
El agente sigue ejecutándose por `task_queue`; **además** existe como bot.

**Paso 3 — Ejecución persistente.** Para agentes con `schedules` (rutina), crear
un cron job Hermes namespaced `[bot:<name>] <rutina>` (vía `hermes cron create`)
que ejecute la tarea del bot con los datos reales de VANOVA (`agent_data_tools`).
El bot pasa de "consulta one-shot" a "rutina recurrente en su propio chat".

**Paso 4 — Canal.** Opcional: conectar el bot a un canal de mensajería
(Telegram, etc.) para que el empresario pueda hablarlo fuera de VANOVA. Fuera
del alcance del MVP inicial; se documenta como siguiente nivel.

### 2b.4 Datos reales y honestidad
El bot lee los datos **reales** de VANOVA (`agent_data_tools`, la misma fuente
que el dashboard). Sus `SOUL.md`/memorias incluyen la regla de honestidad: nunca
inventa un € ni afirma un resultado sin métrica comparable (`UNKNOWN ≠ 0`).

### 2b.5 Orden de implementación (sólido, sin romper Fase A)
1. [ ] `agent_hermes.py` — `sync_agent_to_bot` / `remove_bot` (perfil + SOUL.md).
2. [ ] Enchufar a `create_custom_agent` (sincroniza bot si Hermes disponible).
3. [ ] Rutina cron por agente con `schedules` (`[bot:<name>]`).
4. [ ] Vista en dashboard: indicador "Bot de Hermes activo" + link a verlo.
5. [ ] Tests: creación de perfil idempotente, SOUL.md generado, borrado coherente.

---

## 3. Primera versión funcional (MVP) — implementada

- **Backend:** `agent_architect.create_custom_agent(name, role, description)`.
  - Genera id estable (`custom-<slug>`), traduce el rol a permisos seguros,
    persiste con `add_agents` (RMW atómico BUG-006).
  - Endpoint `POST /api/agents/custom` + whitelist de mutación actualizada.
- **Frontend:** botón "Crear agente" en vista Agents + modal (nombre, área, descripción).
  `DataServices.createCustomAgent()`.
- **Tests:** 3 regression tests (nombre obligatorio, permisos por rol, idempotencia).
  Suite: **711 passed, 1 skipped**.

## 4. Cómo se verifica
1. Vista Agents → "Crear agente".
2. Nombre "Agente de Ventas", área "Ventas" → se crea con `read_orders`/`read_products`.
3. "Ejecutar" → se encola y se resuelve contra Hermes con los datos reales.

## Honestidad
Los agentes se ejecutan con **datos reales** de VANOVA y permisos de **solo
lectura** según su rol. No inventan cifras: usan `agent_data_tools` (la misma
fuente que el dashboard).
