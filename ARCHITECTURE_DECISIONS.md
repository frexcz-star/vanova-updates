# VANOVA — MOOVING AI Operating System
## Decisiones Técnicas (Architecture Decision Records)

Este documento registra las decisiones técnicas tomadas al convertir el prototipo
visual en un sistema funcional. Cada decisión explica el *qué*, el *por qué* y las
alternativas consideradas.

---

## ADR-1: Stack del backend — Python / FastAPI

**Contexto**: El proyecto tenía dos candidatos: un spec Node/Express (nunca implementado)
y un backend FastAPI Python real (`maios-prototype-pwa/backend/main.py`).

**Decisión**: Reutilizar **Python 3.11 + FastAPI + uvicorn**.

**Razones**:
- Coherente con el backend real existente (no se reimplementa algo que ya funciona).
- FastAPI da auth (OAuth2/JWT), WebSocket y validación de schemas (Pydantic) de serie.
- Python ya está en el equipo (3.11.15) y `uv` gestiona el venv.
- El stack de Hermes Agent ya es Python, facilitando la integración futura.

**Alternativas descartadas**: Node/Express (spec viejo, sin código); Docker (no instalado).

---

## ADR-2: Topología Cloud + Connector (conexión saliente) en lugar de túnel

**Contexto**: El spec antiguo proponía exponer el backend local vía Cloudflare/ngrok
(`localhost:3000` → `127.0.0.1:8642`). El nuevo brief lo rechaza explícitamente.

**Decisión**: Arquitectura de **VANOVA Cloud público + VANOVA Connector local con
conexión saliente autenticada**. El Cloud **nunca** se conecta a puertos del PC del
dueño; es el Connector quien inicia la conexión hacia el Cloud.

**Razones**:
- El PC del dueño no abre ningún puerto a Internet (mitiga exposición a ataques).
- El dueño puede usar VANOVA desde el móvil sin estar en la misma red.
- Reintento/reconexión automática ante pérdida de red (heartbeat + push).

**Alternativas descartadas**: túnel Cloudflare/ngrok al backend local (exponía el
puerto y violaba el requisito de seguridad).

---

## ADR-3: Base de datos — SQLite (portable) en lugar de asumir proveedor de hosting

**Contexto**: VANOVA debe ser portable a cualquier proveedor de hosting y no debe
asumir infraestructura.

**Decisión**: **SQLite** para el Cloud (workspaces, usuarios, devices, activity,
decisions, insights, audit).

**Razones**:
- Cero configuración externa; funciona en Vercel/Railway/Fly/self-hosted por igual.
- Suficiente para un solo workspace (MOOVING PAPER) y volúmenes modestos.
- El brief exige "arquitectura portable" y "NO asumas el proveedor todavía".
- Migrable a PostgreSQL/cloud DB más adelante sin cambiar la lógica de acceso.

---

## ADR-4: Separación UI / Data (Data Services Layer)

**Contexto**: El prototipo hardcodeaba todos los datos en el HTML.

**Decisión**: Crear `web/data-services.js` como **única capa de acceso a datos**.
Las vistas leen de un `store` poblado por `DataServices`. La UI conserva exactamente
su lenguaje visual (no se rediseña).

**Proveniencia de datos** (`dataMode`):
- `real` — datos reales (pusheados por el Connector desde Hermes/fuentes).
- `mock` — datos de desarrollo, **siempre etiquetados** ("DEV SAMPLE" en la UI).
- `empty` — fuente no conectada; se muestra "Not connected", nunca se inventa.

---

## ADR-5: Autenticación — JWT access + refresh, bcrypt, rate-limit

**Decisión**:
- `POST /api/auth/login` → access token (60 min) + refresh (7 días).
- `POST /api/auth/refresh` → renueva access token sin reloguear.
- Contraseñas con bcrypt; secretos SOLO en `.env` (nunca en código).
- CORS restringible vía `MAIOS_ALLOWED_ORIGINS` (vacío = mismo origen en prod).
- Audit log de acciones importantes (login, device, decisiones).

**Seguridad no negociable**: ninguna API key, credencial de Hermes ni puerto local
se expone al frontend.

---

## ADR-6: Realtime — WebSocket autenticado por token

**Decisión**: `WS /ws/dashboard?token=<access_token>` para push de actividad.
El Connector hace push a Cloud (`/api/connector/push`), Cloud lo persiste y
broadcasta a los navegadores conectados del workspace. El frontend se reconecta
automáticamente.

---

## ADR-7: Onboarding premium como flujo de primer arranque

**Decisión**: Si el workspace no está configurado (`/api/onboarding/status` →
`configured: false`), el dashboard redirige a una pantalla de setup en 7 pasos
(Connector → Hermes → Discovery → Sources → Data Lake → Agents → Ready).
Cada paso refleja el **estado real** de conexión; no inventa avances.

---

## ADR-8: Honestidad de datos (REAL/MOCK/EMPTY)

**Regla central**: Nunca se presentan datos ficticios como reales de MOOVING PAPER.
Si una fuente no está conectada → `not_connected` / `needs_configuration`. Si Hermes
no corre → el Connector pushea `dataMode: empty` y el dashboard cae a mock etiquetado
o a estado vacío según `DATA_MODE`.

---

## Stack de despliegue previsto

```
maios.moovingpaper.com
        ↓  (HTTPS)
VANOVA Cloud  (FastAPI + SQLite, portable)
        ↓  (conexión saliente autenticada, WSS/HTTPS)
VANOVA Connector  (Python, en el PC del dueño)
        ↓  (solo local)
Hermes Agent  (127.0.0.1:8642) + sistemas de negocio
```

## Estructura del repositorio

```
maios/
├── shared/            # contratos de datos (contracts.py) + mock_data.py
├── cloud/             # VANOVA Cloud (FastAPI): main.py, requirements.txt, .env.example
├── connector/         # VANOVA Connector: connector.py, .env.example
└── web/               # dashboard.html + data-services.js (+ dist/ servido por Cloud)
```
