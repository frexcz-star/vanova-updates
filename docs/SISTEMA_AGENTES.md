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

**Fase B — bots persistentes de Hermes (futuro):** aprovechar `hermes profile`
para dar a cada agente un perfil Hermes real (memoria, skills, canal propio).
Cada agente VANOVA → un perfil Hermes con su SOUL.md/personalidad, delegando la
ejecución persistente a un bot en lugar de una consulta one-shot.

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
