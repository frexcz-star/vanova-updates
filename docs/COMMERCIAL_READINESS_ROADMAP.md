# VANOVA 0.9.13 → 1.0

## Commercial Readiness, Security, Infrastructure, Agent Runtime & UX Hardening

## CONTEXTO

Estás trabajando sobre VANOVA 0.9.13, un AI Operating System / AI Command Center para pequeñas empresas.

La arquitectura actual incluye, entre otras piezas:

* Electron Desktop App
* Local Runtime
* VANOVA Cloud
* Connector
* Hermes como execution engine
* Dashboard Web UI
* SQLite local
* JWT authentication
* WebSocket
* Task Queue
* Agents
* Guardrails
* Autonomy configuration
* Integrations
* Shopify
* Files
* Automation
* Diagnostics
* Updater
* Installer

La base actual es buena y NO debe ser reemplazada.

El objetivo de esta tarea es llevar VANOVA desde un estado de prototipo avanzado / beta técnica a una base suficientemente sólida para:

1. ejecutar tareas de agentes realmente;
2. proteger correctamente el sistema;
3. persistir operaciones;
4. aplicar permisos y guardrails de verdad;
5. soportar múltiples usuarios/workspaces;
6. mejorar radicalmente la UX;
7. eliminar funcionalidades falsas/placeholders de la experiencia principal;
8. preparar VANOVA para clientes reales;
9. mantener compatibilidad con la arquitectura existente;
10. conservar todo lo que ya funciona.

---

# REGLA PRINCIPAL

NO REESCRIBAS VANOVA DESDE CERO.

NO cambies la arquitectura completa.

NO sustituyas Electron.

NO sustituyas Hermes.

NO sustituyas la arquitectura Cloud/Runtime/Connector salvo que una modificación concreta sea necesaria para solucionar un problema identificado.

Trabaja incrementalmente.

Antes de modificar una parte importante:

1. inspecciona el código existente;
2. identifica dependencias;
3. determina qué comportamiento actual debe conservarse;
4. implementa el cambio mínimo necesario;
5. ejecuta tests;
6. añade tests nuevos;
7. verifica que no se haya roto una funcionalidad existente.

---

# OBJETIVO FINAL

VANOVA 1.0 debe sentirse como un producto comercial real, no como una demo técnica.

El usuario debe poder:

INSTALL
→ FIRST RUN
→ CREATE/CONNECT WORKSPACE
→ CONNECT BUSINESS DATA
→ CONFIGURE AI
→ ACTIVATE AGENTS
→ ASK HERMES
→ CREATE TASK
→ AGENT EXECUTES
→ GUARDRAIL CHECK
→ HUMAN APPROVAL WHEN REQUIRED
→ ACTION EXECUTED
→ RESULT PERSISTED
→ USER SEES RESULT
→ AUDIT TRAIL

Todo este flujo debe funcionar realmente.

No queremos UI que diga que algo ocurrió cuando solamente se registró que ocurrió.

VANOVA debe seguir el principio:

> NEVER CLAIM AN ACTION HAPPENED UNLESS THE ACTION ACTUALLY HAPPENED.

---

# PHASE 0 — BASELINE Y AUDIT

Antes de cambiar código:

## 0.1 Crear baseline

Ejecuta:

* tests existentes
* typecheck
* lint
* build
* packaging si es posible
* Python compilation
* JavaScript syntax validation

Registra los resultados.

NO continúes si hay fallos existentes que no hayas identificado.

Crea un documento:

`docs/COMMERCIAL_READINESS_BASELINE.md`

con:

* tests existentes
* número de tests
* paquetes
* build status
* known issues
* architecture overview
* current security concerns

---

# PHASE 1 — SECRETOS Y RELEASE HYGIENE

Esta fase es P0.

## Problema

El proyecto contiene archivos como:

* `.env`
* bases de datos de desarrollo
* logs
* audit files
* credenciales/configuración de desarrollo

El instalador desktop también referencia recursos como:

`../cloud`

y

`../connector`.

No debemos permitir que secretos de desarrollo terminen en el instalador.

---

## 1.1 Eliminar secretos del repositorio

Buscar recursivamente:

* `.env`
* `.env.local`
* `.env.production`
* `.env.development`
* API keys
* JWT secrets
* passwords
* device keys
* cloud secrets
* Shopify secrets
* tokens
* private keys

NO imprimir los valores encontrados en terminal ni en archivos de documentación.

Crear:

`.env.example`

con placeholders.

Ejemplo:

```env
MAIOS_CLOUD_SECRET_KEY=
MAIOS_DEVICE_KEY=
MAIOS_DEMO_PASSWORD=
```

Nunca valores reales.

---

## 1.2 Gitignore

Asegurar que `.gitignore` excluye:

```text
.env
.env.*
!.env.example
*.db
*.sqlite
*.sqlite3
audit.jsonl
logs/
data/
secrets/
```

No excluir archivos fuente necesarios para producción.

---

## 1.3 Installer hygiene

Revisar:

`desktop/package.json`

y toda configuración de electron-builder.

El instalador NO debe empaquetar:

* `.env`
* development database
* development logs
* audit logs
* credentials
* test fixtures con secretos
* source-only secrets

Los recursos de producción deben contener únicamente aquello que VANOVA necesita para funcionar.

---

## 1.4 First-run secrets

Los secretos específicos de instalación deben generarse durante el primer arranque.

Por ejemplo:

```text
%LOCALAPPDATA%/VANOVA/config/
```

Generar:

* runtime authentication secret
* device identity
* local encryption key
* installation ID

Cada instalación debe tener valores únicos.

No utilizar un secreto global compartido entre todas las instalaciones.

---

## 1.5 Secret rotation

Crear mecanismo para rotar secretos locales.

Debe existir una función equivalente a:

```text
rotateRuntimeCredentials()
```

y no debe romper una instalación existente.

---

# PHASE 2 — LOCAL RUNTIME SECURITY

Esta fase es crítica.

El runtime local escucha aproximadamente en:

`127.0.0.1:8765`

Actualmente existen endpoints con capacidades importantes.

No debemos confiar únicamente en que localhost es seguro.

---

# 2.1 Runtime authentication

Crear un token generado por instalación:

`MAIOS_RUNTIME_TOKEN`

El token debe:

* ser criptográficamente aleatorio;
* tener suficiente entropía;
* almacenarse de forma segura;
* nunca aparecer en logs;
* nunca aparecer en UI;
* no estar hardcodeado.

Todos los endpoints mutantes deben requerir:

```http
Authorization: Bearer <runtime-token>
```

---

# 2.2 Clasificar endpoints

Separar endpoints en:

### READ

Ejemplos:

```text
GET /api/health
GET /api/status
GET /api/tasks
GET /api/activity
```

### MUTATION

Ejemplos:

```text
POST /api/tasks/run
POST /api/services/start
POST /api/services/stop
POST /api/hermes/restart
POST /api/install/run
POST /api/recovery
POST /api/files/add
POST /api/files/remove
POST /api/shopify/sync
POST /api/guardrails/decide
```

Todo endpoint mutante debe autenticarse.

No eliminar APIs existentes.

---

# 2.3 CORS

Eliminar:

```text
Access-Control-Allow-Origin: *
```

Usar una allowlist explícita.

Permitir únicamente:

* VANOVA Desktop origin
* trusted local dashboard origin
* desarrollo cuando NODE_ENV/development lo permita

No permitir wildcard en producción.

---

# 2.4 Request validation

Todos los endpoints deben validar inputs.

Nunca confiar en:

* IDs
* paths
* agentId
* taskId
* filenames
* URLs
* integration identifiers
* commands

Usar schemas de validación.

Preferiblemente centralizar con un sistema como Zod si el stack existente lo permite.

No introducir una dependencia nueva si el proyecto ya tiene una solución equivalente.

---

# 2.5 Path traversal

Especial atención a:

```text
/api/files/add
/api/files/remove
```

Nunca permitir que el usuario pueda utilizar:

```text
../
```

para escapar del workspace permitido.

Normalizar paths y comprobar que el resultado sigue dentro del directorio permitido.

---

# 2.6 Command execution

Cualquier endpoint que pueda ejecutar comandos del sistema debe:

* validar comandos;
* utilizar allowlists;
* evitar shell interpolation;
* evitar concatenación de strings;
* utilizar APIs seguras de subprocess;
* registrar la acción;
* requerir permisos adecuados.

Nunca hacer:

```text
exec(userInput)
```

---

# PHASE 3 — ELECTRON HARDENING

Revisar `desktop/main.js` y configuración relacionada.

Actualmente existen configuraciones demasiado permisivas como:

```javascript
webSecurity: false
allowRunningInsecureContent: true
sandbox: false
```

Eliminar estas configuraciones salvo que exista una dependencia técnicamente demostrable.

Objetivo:

```javascript
contextIsolation: true
nodeIntegration: false
sandbox: true
webSecurity: true
```

---

## 3.1 Preload

Todo acceso a:

* filesystem
* shell
* runtime
* OS
* process management

debe pasar por APIs explícitamente expuestas desde preload.

No exponer `ipcRenderer` completo.

No exponer `require`.

No exponer Node global.

Crear una API mínima:

```text
window.maios.runtime
window.maios.system
window.maios.updater
```

con métodos explícitos.

---

# PHASE 4 — CREDENTIAL SECURITY

Las credenciales de integraciones NO deben almacenarse en plaintext.

Esto incluye:

* Shopify tokens
* passwords
* API keys
* provider keys
* connector secrets

---

## Desktop

Utilizar almacenamiento seguro del sistema operativo cuando sea posible.

En Windows preferiblemente:

* DPAPI
* Windows Credential Manager

No almacenar secretos directamente en SQLite sin cifrar.

---

## Cloud

No guardar secretos directamente en plaintext.

Implementar encryption at rest.

La clave maestra debe estar fuera de la base de datos.

Nunca almacenar:

```text
secret + encryption key
```

en el mismo lugar.

---

# PHASE 5 — AUTH / SESSION SECURITY

Revisar el sistema JWT actual.

Implementar:

### Access token

Vida corta.

### Refresh token

* persistente
* hashed en DB
* rotation
* revocation
* expiry
* device/session association

Crear estructura equivalente a:

```text
refresh_tokens
----------------
id
user_id
token_hash
device_id
created_at
expires_at
revoked_at
last_used_at
```

---

## Logout

Implementar:

```text
Logout current session
Logout all sessions
Revoke device
```

---

## Passwords

Utilizar un algoritmo de password hashing seguro.

Nunca almacenar passwords plaintext.

---

# PHASE 6 — RATE LIMITING

Añadir rate limiting a:

```text
/login
/refresh
/password reset
/Hermes endpoints
/agent execution
```

Ejemplo conceptual:

```text
5 login attempts/minute/IP
```

No utilizar límites excesivamente agresivos que hagan imposible usar el producto.

---

# PHASE 7 — RBAC

Implementar roles reales.

Roles iniciales:

```text
owner
admin
operator
viewer
```

Crear permisos explícitos.

Ejemplo:

```text
workspace.read
workspace.update
members.read
members.manage

agents.read
agents.configure
agents.execute

tasks.read
tasks.create
tasks.cancel

approvals.read
approvals.decide

integrations.read
integrations.configure

billing.read
billing.manage

settings.read
settings.manage
```

El frontend NO debe ser la única capa que esconda botones.

El backend debe comprobar permisos.

---

# PHASE 8 — MULTI-TENANCY

Preparar Cloud para:

```text
User
Workspace
Membership
Device
Session
Agent
Task
TaskRun
Approval
Integration
Event
```

Cada recurso debe estar asociado a un workspace.

Nunca permitir:

```text
workspace A
→ acceder a recurso de workspace B
```

Todas las queries deben estar filtradas por workspace/tenant.

No confiar en IDs enviados por frontend.

---

# PHASE 9 — PERSISTENT TASK SYSTEM

Este es uno de los cambios más importantes.

Actualmente la task queue utiliza estructuras en memoria.

Eso significa que reiniciar el runtime puede perder:

* tareas
* historial
* estado

Implementar persistencia.

Crear modelos equivalentes a:

```text
Task
TaskRun
TaskEvent
Approval
AgentExecution
```

---

## Task

```text
id
workspace_id
agent_id
title
description
status
priority
created_at
updated_at
created_by
```

---

## TaskRun

```text
id
task_id
started_at
completed_at
status
result
error
```

---

## TaskEvent

```text
id
task_run_id
type
timestamp
payload
```

Tipos:

```text
created
queued
started
tool_called
approval_required
approved
denied
completed
failed
cancelled
```

---

# PHASE 10 — REAL HERMES EXECUTION

Este es el cambio funcional más importante.

NO marcar una tarea como ejecutada simplemente porque Hermes está healthy.

Actualmente existe una lógica equivalente a:

```text
if Hermes healthy:
    return "Task executed via Hermes"
```

Eso NO es suficiente.

Implementar:

```text
VANOVA
 ↓
Task
 ↓
Policy Check
 ↓
Agent Permissions
 ↓
Guardrails
 ↓
Hermes Execution
 ↓
Tool Calls
 ↓
Result
 ↓
TaskRun persistence
 ↓
Activity
 ↓
UI
```

La tarea solo puede tener:

```text
completed
```

cuando la ejecución real haya finalizado correctamente.

---

# PHASE 11 — AGENT PERMISSIONS

Los campos:

```text
tools
integrations
triggers
schedules
permissions
```

deben dejar de ser solamente metadata.

Deben afectar realmente a la ejecución.

Ejemplo:

```text
Marketing Agent
permissions:
  instagram.read
  content.create
```

El agente NO puede ejecutar:

```text
shopify.delete
```

si no tiene permiso.

---

# PHASE 12 — GUARDRAIL ENGINE

Crear una policy engine central.

Conceptualmente:

```text
PolicyEngine.evaluate(action)
```

Debe recibir:

```text
workspace
user
agent
tool
integration
action
risk
```

y devolver:

```text
allow
deny
require_approval
```

---

## Ejemplo

Una acción de bajo riesgo:

```text
read Shopify analytics
```

→ allow.

Una acción sensible:

```text
publish Instagram post
```

→ require_approval.

Una acción peligrosa:

```text
delete products
```

→ deny o require explicit high-risk approval.

---

# PHASE 13 — APPROVALS

Crear sistema persistente de approvals.

Modelo:

```text
Approval
---------
id
workspace_id
task_run_id
agent_id
action
risk_level
reason
status
created_at
resolved_at
resolved_by
```

Estados:

```text
pending
approved
denied
expired
```

La ejecución debe quedar BLOQUEADA cuando:

```text
require_approval
```

No permitir que el agente continúe por detrás de la UI.

---

# PHASE 14 — AUDIT LOG

Toda acción importante debe producir un evento de auditoría.

Ejemplos:

```text
login
logout
agent_created
agent_updated
task_created
task_started
tool_called
approval_requested
approval_granted
approval_denied
integration_connected
integration_removed
credential_rotated
settings_changed
```

Nunca registrar:

* passwords
* API keys
* refresh tokens
* runtime tokens
* secretos

---

# PHASE 15 — HONEST STATE MODEL

Conservar y ampliar el concepto actual de:

```text
real
partial
mock
empty
```

Esto es una de las mejores decisiones actuales de VANOVA.

Aplicarlo a todo.

Nunca mostrar:

```text
SUCCESS
```

si la operación solo fue simulada.

Usar estados claros:

```text
Connected
Not connected
Demo
Partial
Pending
Running
Completed
Failed
Needs approval
```

---

# PHASE 16 — DASHBOARD / UX REDESIGN

No rehacer completamente el diseño visual.

Mantener:

* typography
* design tokens
* dark/light mode
* accent system
* cards
* sidebar
* spacing
* general visual language

Pero simplificar la información.

Actualmente existen demasiados módulos visibles.

Reducir la navegación principal.

---

# NUEVA NAVEGACIÓN PROPUESTA

## COMMAND CENTER

```text
Home
Insights
Activity
```

## WORK

```text
Tasks
Agents
Hermes
Approvals
```

## DATA

```text
Integrations
Files
```

## AUTOMATION

```text
Automations
```

## SYSTEM

```text
Diagnostics
Settings
```

No mostrar módulos todavía incompletos como páginas principales.

---

# PHASE 17 — REMOVE PLACEHOLDER SURFACES

No eliminar funcionalidades futuras del código.

Pero NO mostrar en navegación principal páginas que actualmente son placeholders.

Especialmente:

```text
Finance
Inventory
Production
Procurement
Logistics
Customers
Campaigns
Trends
```

si todavía no tienen funcionalidad real.

Pueden mantenerse:

* feature flags
* experimental routes
* development-only routes

pero no deben contaminar la experiencia comercial.

---

# PHASE 18 — COMMAND CENTER HOME

La Home debe responder inmediatamente:

> What needs my attention?

Orden recomendado:

## 1. Attention

```text
3 things need your attention
```

Ejemplos:

```text
2 approvals pending
1 integration disconnected
```

---

## 2. Running now

```text
3 agents running
2 tasks processing
```

---

## 3. AI recommendations

```text
VANOVA found 3 opportunities
```

---

## 4. Recent results

Resultados reales de tareas completadas.

---

## 5. Activity

Timeline.

---

Evitar llenar la Home con métricas que no generan decisiones.

---

# PHASE 19 — HERMES EXPERIENCE

Hermes debe sentirse como el motor inteligente de VANOVA.

No simplemente como un chatbot.

Ejemplo:

Usuario:

> "Analiza las ventas de esta semana y dime qué debería hacer."

Respuesta estructurada:

```text
ANALYSIS

Revenue: -8.4%

LIKELY CAUSE
...

RECOMMENDATION
...

ACTIONS

[Create task]
[Prepare campaign]
[Analyze products]
```

Las acciones deben generar operaciones reales de VANOVA.

---

# PHASE 20 — EMPTY STATES

Todos los estados vacíos deben explicar:

1. qué está vacío;
2. por qué;
3. qué puede hacer el usuario;
4. botón principal.

Malo:

```text
No data.
```

Bueno:

```text
Connect Shopify to let VANOVA analyze your sales.

[Connect Shopify]
```

---

# PHASE 21 — LOADING STATES

Todas las acciones asíncronas deben mostrar:

* loading
* progress cuando exista
* success
* failure
* retry

Nunca dejar al usuario preguntándose:

> "¿Está haciendo algo?"

---

# PHASE 22 — ERROR UX

No mostrar errores técnicos directamente.

En lugar de:

```text
ECONNREFUSED 127.0.0.1:8765
```

mostrar:

```text
VANOVA Runtime isn't responding.

Try restarting VANOVA Runtime.

[Restart Runtime]
[View diagnostics]
```

Los detalles técnicos pueden estar disponibles en diagnostics.

---

# PHASE 23 — ONBOARDING

Crear onboarding real.

Flujo:

```text
Welcome
 ↓
Create workspace
 ↓
Choose business type
 ↓
Connect AI provider
 ↓
Connect optional integrations
 ↓
Initialize Hermes
 ↓
Choose agents
 ↓
Set autonomy level
 ↓
Ready
```

No obligar a conectar todas las integraciones.

---

# PHASE 24 — AUTONOMY LEVEL

Definir niveles claros:

```text
Manual
Approval required
Supervised
Autonomous
```

Explicar claramente qué significa cada uno.

Nunca permitir autonomía completa sin policy checks.

---

# PHASE 25 — INTEGRATIONS

Crear lifecycle consistente:

```text
Disconnected
Connecting
Connected
Syncing
Connected
Error
Disconnected
```

Cada integración debe tener:

* connection status
* last sync
* permissions
* disconnect
* reconnect
* test connection

---

# PHASE 26 — SHOPIFY

Mantener la integración actual.

Pero asegurar:

```text
connect
test
sync
last_sync
error
disconnect
```

Los tokens nunca deben aparecer en frontend.

---

# PHASE 27 — OBSERVABILITY

Crear logs estructurados.

Separar:

```text
application logs
audit logs
agent execution logs
security logs
```

No escribir secretos.

Agregar correlation IDs:

```text
request_id
task_run_id
agent_execution_id
```

Esto permitirá seguir una acción completa:

```text
User request
→ Task
→ Agent
→ Hermes
→ Tool
→ Result
```

---

# PHASE 28 — DIAGNOSTICS

La página Diagnostics debe convertirse en una herramienta real.

Comprobar:

```text
VANOVA Runtime
Hermes
Cloud
Connector
Database
AI Provider
Integrations
Filesystem
Updater
```

Cada check debe devolver:

```text
healthy
warning
error
```

y explicación accionable.

---

# PHASE 29 — UPDATER

Conservar:

* manifest
* SHA-256
* download
* verification
* rollback/recovery

Pero añadir protección de autenticidad.

Preparar:

* Windows Authenticode
* signed installer
* signed update metadata si es viable

No considerar SHA-256 por sí solo suficiente para autenticidad.

---

# PHASE 30 — DATABASE

Para local:

SQLite está bien.

Pero:

* WAL mode
* foreign keys
* migrations
* indexes
* transactions
* backup/recovery

deben estar correctamente configurados.

Para Cloud:

preparar arquitectura PostgreSQL cuando se pase a escala multi-tenant.

No hacer la migración a PostgreSQL ahora si supone una reescritura innecesaria.

---

# PHASE 31 — BACKUPS

Crear:

```text
manual backup
automatic backup
restore
```

para datos locales importantes.

Nunca incluir secretos plaintext en backups.

---

# PHASE 32 — TESTING

Actualmente existen tests que deben seguir pasando.

REGLA:

> No terminar ninguna fase con menos tests pasando que al comenzar.

Añadir tests para:

### Security

* unauthorized runtime request
* invalid token
* expired token
* CORS
* path traversal
* permission denied

### Auth

* login
* refresh
* rotation
* logout
* revoke

### RBAC

* owner
* admin
* operator
* viewer

### Tasks

* create
* queue
* execution
* failure
* cancellation
* persistence

### Guardrails

* allow
* deny
* approval
* approval resolution

### Agents

* permissions
* tools
* integrations

---

# PHASE 33 — E2E TEST

Crear al menos un flujo E2E crítico:

```text
Fresh install
→ Launch
→ First-run setup
→ Create workspace
→ Configure AI
→ Initialize Hermes
→ Create agent
→ Create task
→ Policy check
→ Execute
→ Persist result
→ Display result
```

Debe funcionar sin intervención manual de desarrollo.

---

# PHASE 34 — PRODUCT POLISH

Revisar todos los textos.

Evitar:

```text
Lorem
Coming soon
TODO
Demo
Mock
```

en superficies comerciales salvo que realmente sea necesario.

Usar lenguaje consistente:

```text
Agent
Task
Run
Approval
Integration
Workspace
Automation
```

No mezclar nombres para el mismo concepto.

---

# PHASE 35 — PERFORMANCE

Revisar:

* initial load
* dashboard rendering
* unnecessary requests
* WebSocket lifecycle
* polling
* memory leaks
* process spawning
* database queries

No optimizar prematuramente.

Medir primero.

---

# PHASE 36 — DOCUMENTATION

Crear:

```text
docs/
├── ARCHITECTURE.md
├── SECURITY.md
├── AUTH.md
├── AGENTS.md
├── TASKS.md
├── GUARDRAILS.md
├── MULTI_TENANCY.md
├── DEPLOYMENT.md
├── RELEASE.md
└── COMMERCIAL_READINESS.md
```

La documentación debe describir la implementación REAL.

No documentar funcionalidades que todavía no existen.

---

# PHASE 37 — RELEASE CHECKLIST

Crear:

`docs/RELEASE_CHECKLIST.md`

Debe comprobar:

```text
[ ] No secrets in repository
[ ] No secrets in installer
[ ] Production environment variables configured
[ ] Runtime authentication enabled
[ ] Electron hardened
[ ] CSP enabled
[ ] RBAC enforced
[ ] Refresh tokens secure
[ ] Rate limiting enabled
[ ] Credentials encrypted
[ ] Tasks persistent
[ ] Hermes execution real
[ ] Guardrails enforced
[ ] Approvals persistent
[ ] Audit logging active
[ ] E2E passing
[ ] Unit tests passing
[ ] Typecheck passing
[ ] Build passing
[ ] Installer tested
[ ] Update tested
[ ] Recovery tested
```

---

# IMPORTANT — NO FAKE COMPLETION

No marques una fase como completa si solamente existe:

* UI
* placeholder
* mocked response
* fake success
* local optimistic state

Una feature se considera completa únicamente si:

```text
UI
+
API
+
Backend
+
Persistence
+
Error handling
+
Security
+
Tests
```

están implementados cuando corresponda.

---

# IMPORTANT — NO OVERENGINEERING

No introducir:

* microservices
* Kubernetes
* Redis
* Kafka
* GraphQL
* nuevas bases de datos
* nuevos frameworks

simplemente porque "un SaaS debería tenerlos".

VANOVA debe seguir siendo simple.

Primero:

```text
Electron
Runtime
Cloud
Connector
Hermes
SQLite/Postgres
```

y únicamente añadir infraestructura cuando exista una necesidad real.

---

# ORDEN DE IMPLEMENTACIÓN OBLIGATORIO

Implementa en este orden:

## P0

1. Secret hygiene
2. Runtime authentication
3. CORS
4. Electron hardening
5. Credential encryption
6. Input validation
7. Path traversal protection
8. Command execution security
9. Auth/session hardening

## P1

10. RBAC
11. Multi-tenancy
12. Persistent tasks
13. Real Hermes execution
14. Agent permissions
15. Guardrail engine
16. Approval system
17. Audit logging

## P2

18. Dashboard simplification
19. Command Center redesign
20. Hermes UX
21. Onboarding
22. Integration lifecycle
23. Diagnostics
24. Error/loading states

## P3

25. E2E tests
26. updater signing
27. backups
28. documentation
29. performance
30. release hardening

---

# CRITICAL DEVELOPMENT RULES

## Rule 1

No destructive migrations without backup.

## Rule 2

No deleting existing functionality unless explicitly approved.

## Rule 3

No breaking API changes unless backwards compatibility is preserved.

## Rule 4

No secrets in source code.

## Rule 5

No fake success states.

## Rule 6

No frontend-only authorization.

## Rule 7

No direct command execution from untrusted input.

## Rule 8

No wildcard CORS in production.

## Rule 9

No disabling browser security to make something work.

## Rule 10

Every security fix must receive a regression test.

## Rule 11

Every major feature must receive at least one integration test.

## Rule 12

Do not modify unrelated code.

---

# DEFINITION OF DONE

VANOVA 1.0 is NOT complete merely because it builds.

It is complete when:

### SECURITY

* no secrets are distributed;
* runtime requires authentication;
* Electron is hardened;
* credentials are encrypted;
* authorization is enforced server-side.

### AGENTS

* agents execute real tasks;
* permissions are enforced;
* tools are actually invoked;
* Hermes execution is real;
* results are persisted.

### OPERATIONS

* tasks survive restart;
* approvals survive restart;
* audit history survives restart;
* failures are recoverable.

### UX

* user understands VANOVA immediately;
* primary workflow is obvious;
* no misleading placeholder pages;
* errors are actionable;
* loading states are clear;
* Home focuses on attention/action.

### SaaS

* users belong to workspaces;
* workspace isolation is enforced;
* RBAC works;
* sessions can be revoked;
* integrations are scoped correctly.

### QUALITY

* existing tests remain green;
* new security tests pass;
* E2E critical path passes;
* production build succeeds;
* installer succeeds;
* updater/recovery are tested.

---

# FINAL INSTRUCTION TO CURSOR

Do NOT attempt to implement all of the above in one giant uncontrolled edit.

Work phase by phase.

After each phase:

1. summarize changed files;
2. summarize architectural changes;
3. run tests;
4. report test results;
5. report remaining issues;
6. verify no unrelated regressions;
7. stop and wait before starting the next major phase if the change is large.

For every change, prefer the smallest robust implementation compatible with the existing VANOVA architecture.

At the end of each phase, provide:

```text
PHASE:
STATUS:

FILES CHANGED:

FUNCTIONAL CHANGES:

SECURITY CHANGES:

TESTS:
passed:
failed:

KNOWN LIMITATIONS:

NEXT PHASE:
```

Do not claim "production ready" until the Definition of Done above has actually been verified.

The ultimate goal is not to make VANOVA look like a commercial product.

The goal is to make VANOVA **behave like one**.

---

# BACKLOG DE PRODUCTO — POST-PILOTO (mejoras futuras, NO se ejecutan ahora)

> Registro de ideas de producto validadas como futuras (después de que el piloto real valide el MVP y la capa de inteligencia). No son prioridad actual; solo quedan anotadas para no perderlas.

## Idea 1 — Acceso móvil por código de conexión (pairing) [POST-PILOTO]

**Origen:** propuesta de Nico. **Estado:** aprobada como mejora futura de retención. **No se ejecuta ahora.**

- **Qué es:** el PC genera un código de conexión (tipo pairing de TV/Spotify); el usuario introduce ese código en su móvil/web para acceder a su panel VANOVA.
- **Modelo de datos:** los datos SIGUEN en el PC (no se suben a la nube). Respeta la regla de datos locales y que Hermes no se expone (el acceso móvil solo sirve el dashboard, no el chat/agente).
- **Fases:** (1) red local primero (el móvil accede mientras esté en la misma red que el PC); (2) por internet con relay outbound (el PC es el servidor y debe estar encendido) como segunda fase.
- **Seguridad:** el código es una contraseña corta — limitar intentos, expirar, revocar; token HTTPS corto; relay outbound (no abrir puertos).
- **Decisión:** post-piloto, cuando el MVP valide. No bloquear el roadmap actual (piloto real + capa de inteligencia).
- **Detalle técnico/estratégico completo:** ver `STRATI_DETALLE...` (análisis de Nico), registro en REGISTRO_STRATI.md.
