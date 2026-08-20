# INFORME COMPLETO MAIOS v1.0.2 — PARA EVALUACIÓN COMERCIAL

**Fecha:** 13 de agosto de 2026  
**Producto:** MAIOS — MOOVING AI Operating System  
**Editor:** MOOVING PAPER / BlisArtPaper  
**Versión:** 1.0.2  
**Plataforma:** Windows (Electron + Python embebido)  
**Tienda piloto:** blisartpaper.myshopify.com  

---

## 1. Resumen ejecutivo

MAIOS es un **sistema operativo de IA para desktop** orientado a PYMEs que venden online. Unifica en una sola aplicación Windows:

- Dashboard de negocio (productos, ventas, métricas)
- Orquestación de agentes IA locales (**Hermes**)
- Backend cloud con acceso remoto seguro (**Connector** solo saliente)
- Integración **Shopify** (sync productos/pedidos)
- Actualizaciones in-app (updater custom, no electron-updater)
- Diagnóstico, integraciones, archivos, aprobaciones, automatizaciones

**Estado actual:** El producto **funciona en producción piloto** con BlisArt Paper: Shopify conectado, ~50 productos/pedidos sincronizados, ~199–414 productos locales desde Excel, Connector healthy, Hermes operativo, 159+ tests automatizados pasando.

**Veredicto preliminar:** Funcionalidad core **comercializable en beta controlada**. Release 1.0.2 incluye endurecimiento comercial, validación updater 1.0.1→1.0.2 (automática + manual), e instalador real `MAIOS-Setup-1.0.2.exe`. **Pendiente para GA:** firma Authenticode y publicación CDN.

---

## 2. Qué es MAIOS

| Aspecto | Detalle |
|---------|---------|
| **Qué resuelve** | Dueños de negocio sin equipo técnico que necesitan IA + datos de Shopify + archivos locales en un solo lugar |
| **Usuario objetivo** | PYME e-commerce (papelería, retail, catálogos Excel + Shopify) |
| **Diferenciador** | Hermes (agentes locales) + bridge Shopify + Connector outbound-only + dashboard honesto (real/mock/empty) |
| **Modelo** | Desktop comercial (licencia/installer), datos locales del usuario |
| **Empresa** | BlisArtPaper / MOOVING PAPER |

---

## 3. Stack técnico

| Capa | Tecnología |
|------|------------|
| Shell desktop | Electron + electron-builder (NSIS) |
| Runtime local | Python 3.11 embebido, API en `:8765` |
| Cloud | FastAPI `:8000`, SQLite, JWT, WebSocket |
| Connector | Python, conexión saliente, heartbeat |
| Agentes | Hermes (CLI/servicio local `:8642`) |
| UI | HTML/JS (`web/dashboard.html`, `web/index.html`) |
| Datos UI | `web/data-services.js` → store pattern |
| Updates | UpdateManager custom + `maios-updater.ps1` |
| Tests | Python unittest/pytest, 159+ tests |

---

## 4. Arquitectura

```
MAIOS.exe (Electron)
  └─ Web UI (dashboard, Hermes chat, integraciones, diagnóstico)
  └─ Python Runtime :8765
       ├─ process_manager → arranca Cloud + Connector
       ├─ shopify_sync → sync productos/pedidos
       ├─ file_organizer → Excel/CSV → organizedProducts
       ├─ hermes_chat → chat + contexto MAIOS
       ├─ integrations_store → tokens cifrados + bridge Hermes .env
       └─ update/update_manager → actualizaciones in-app

Cloud :8000 (FastAPI)
  ├─ Auth JWT, RBAC, audit
  ├─ SQLite (usuarios, dispositivos, actividad)
  └─ Sirve dashboard + WebSocket

Connector (PC dueño)
  ├─ MAIOS_DEVICE_KEY + heartbeat
  └─ Push snapshots a Cloud (sin puertos entrantes)

Hermes (agente IA)
  ├─ Credenciales propias en %LOCALAPPDATA%\hermes\.env
  └─ Bridge → MAIOS integrations cuando misma tienda Shopify
```

### Puertos
- **8765** — Runtime MAIOS (API local)
- **8000** — Cloud MAIOS
- **8642** — Hermes (aprox.)

### Datos usuario vs aplicación
| Ubicación | Contenido |
|-----------|-----------|
| `%LOCALAPPDATA%\Programs\MAIOS\` | Binarios, app.asar, resources (se reemplazan en update) |
| `%LOCALAPPDATA%\MAIOS\` | config, DB, integraciones, updates, logs, backups |
| `%LOCALAPPDATA%\hermes\.env` | Token Shopify Admin API (fuente Hermes) |

---

## 5. Estructura del source

| Directorio | Función |
|------------|---------|
| `desktop/` | Electron (main.js, preload), runtime Python, updater PS1 |
| `desktop/runtime/` | API server, process manager, shopify, hermes, integrations, update |
| `cloud/` | Backend FastAPI (auth, RBAC, dashboard API) |
| `connector/` | Servicio Connector (heartbeat, registro dispositivo) |
| `web/` | UI dashboard + index (Hermes chat embebido) |
| `scripts/` | Build, release, sync-to-installed, create-source-zip |
| `tests/` | 159+ tests automatizados |
| `docs/` | Arquitectura, updates, release checklist |
| `release/` | latest.json, instalador .exe, publish/ |

---

## 6. Funcionalidades implementadas

### Dashboard y datos
- Command Center, Insights, Actividad
- Productos (Shopify + Excel local)
- Ventas / pedidos sincronizados
- Archivos (inventario, organización)
- Métricas dashboard (ingresos, pedidos, clientes)

### Hermes
- Chat embebido en MAIOS
- Contexto MAIOS inyectado (productos, Shopify, Connector)
- Subida de archivos (.xlsx, .csv, etc. → `/api/files/add`)
- Setup conversacional Shopify ("Configura Shopify")
- Respuestas rápidas contextuales

### Integraciones
- Shopify: connect, sync, reauth, lifecycle (connected/syncing/partial/error/reauth_required)
- Bridge automático Hermes `.env` → MAIOS `integrations.json`
- Drawer gestión: Sincronizar, Reconfigurar, Desconectar, Ver ventas

### Sistema
- Diagnóstico (Runtime, Cloud, Connector, Hermes, Shopify, Updates)
- Connector: estados separados (proceso / auth / registro / cloud)
- Actualizaciones in-app (modal, posponer, SHA-256, rollback)
- Aprobaciones, políticas, permisos deny-by-default
- Backup pre-update, startup recovery

---

## 7. Fixes recientes (sesión estabilización 1.0.1)

| # | Problema | Solución |
|---|----------|----------|
| 1 | Connector "sin autenticar" + recovery loop | Backfill `MAIOS_DEVICE_KEY`, estados UI claros, no auto-restart en auth failure |
| 2 | Dashboard no abría | Sync `python_runtime.py`, `startup_gate.py`, `startup_log.py` a instalación |
| 3 | Error Shopify como fila de producto | Empty state real + banner permisos separado |
| 4 | Excel no leía `.xlsx` | `file_organizer.py` parser xlsx → 199+ productos locales |
| 5 | Botones Integraciones Shopify rotos | Handler clics en `#drawer` además de `#content` |
| 6 | Dos tokens Shopify distintos | Bridge `hermes-env` + reimport si token cambia |
| 7 | Token nuevo shpat_a45a… | Validación live scopes, sync 50 productos + 50 pedidos OK |
| 8 | Hermes upload "baja" adjunto | `restoreHermesAttachmentUI()` + import real vía API |
| 9 | Config Shopify manual | Flujo chat Hermes paso a paso + import credenciales Hermes |
| 10 | Versión hardcodeada 0.9.0 en registro | `_app_version()` desde `version.json` |
| 11 | Hermes app vs MAIOS chat info dispar | Panel estado operativo (en progreso/mejorado) |

---

## 8. Sistema de actualización

**NO usa electron-updater.** Updater custom:

1. Check manifest (`latest.json` desde CDN o local)
2. Download instalador NSIS
3. Verificación SHA-256
4. Backup config/updates
5. `maios-updater.ps1` → install silencioso
6. Restart → `startup_recovery()` → rollback si falla

**Manifiesto 1.0.1:**
- URL: `https://releases.moovingpaper.com/maios/MAIOS-Setup-1.0.1.exe`
- SHA256: `0a4a7c7a897c13f01c26905a3443e2af958261d0208df7f2a4e98479225d4f44`
- Tamaño: 92.721.732 bytes
- `dbSchemaVersion: 0` (sin migraciones)

**Pendiente:** CDN upload, firma Authenticode, E2E real 1.0.0→1.0.1, rebuild installer con fixes actuales.

---

## 9. Seguridad

| Control | Estado |
|---------|--------|
| JWT access + refresh | Implementado |
| Passwords bcrypt | Implementado |
| Tokens integración cifrados | Implementado |
| Runtime API auth (Bearer) | Implementado |
| CORS production (no `*`) | Implementado |
| Permisos agentes deny-by-default | Implementado |
| Aprobaciones acciones críticas | Implementado |
| Update SHA-256 | Activo |
| Update firma Authenticode | **Pendiente** |
| Secrets en source | Excluidos (.env no commiteado) |

---

## 10. Tests automatizados

| Métrica | Valor |
|---------|-------|
| **Total** | 159+ |
| **Estado** | Todos pasando (última ejecución sesión) |

**Categorías:** updater, cloud auth, RBAC, runtime security, Shopify bridge/setup, stabilization audit, production hardening, file organizer xlsx, hermes shopify setup, approvals, policy engine.

---

## 11. Estado verificado en piloto (BlisArt Paper)

| Componente | Estado |
|------------|--------|
| Runtime :8765 | healthy |
| Cloud :8000 | healthy |
| Connector | conectado (post backfill device key) |
| Shopify | Conectado vía Hermes, blisartpaper.myshopify.com |
| Sync Shopify | 50 productos, 50 pedidos, ~1.756€ ingresos |
| Productos Excel | 199–414 según fuente (organizados vs catálogo completo) |
| Hermes chat | Responde, sync, contexto operativo |
| Updates | Código listo; E2E no validado en producción |

---

## 12. Blockers comerciales

| Severidad | Item |
|-----------|------|
| **BLOCKER** | E2E update 1.0.0→1.0.1 no probado con baseline real |
| **BLOCKER** | Instalador .exe sin rebuild con fixes recientes (sync manual usado en dev) |
| **HIGH** | Authenticode signing + verificación firma updates |
| **HIGH** | CDN `releases.moovingpaper.com` no publicado con 1.0.1 |
| **MEDIUM** | Paridad info Hermes app vs MAIOS chat (mejora en curso) |
| **MEDIUM** | Playwright E2E browser en CI |
| **LOW** | macOS build, PostgreSQL opcional escala |

---

## 13. Matriz tests manuales

| Test | Resultado |
|------|-----------|
| Abrir MAIOS / dashboard | PASS (post fix python_runtime) |
| Diagnóstico Connector | PASS |
| Productos sin permisos Shopify | PASS (empty state, no fila falsa) |
| Productos Excel | PASS (~199) |
| Productos Shopify sync | PASS (~50) |
| Hermes "Hola" | PASS |
| Hermes + Shopify | PASS (con token correcto) |
| Integraciones botones | PASS |
| Hermes upload archivo | PASS (post fix) |
| Config Shopify por chat | PASS |
| Update 1.0.0→1.0.1 E2E | **NO TESTED** (infra) |
| Firma installer | **PENDING** |

---

## 14. Preguntas para ChatGPT (evaluación comercial)

1. **¿Es MAIOS v1.0.1 comercialmente vendible hoy?** ¿Beta cerrada, early access, o esperar blockers?
2. **¿Qué riesgos de soporte** tiene el updater custom vs electron-updater?
3. **¿SQLite + Connector outbound** es suficiente para PYMEs o falta PostgreSQL/multi-tenant?
4. **¿159 tests** son suficientes sin E2E browser automatizado?
5. **¿El bridge Hermes↔MAIOS** (dos .env) es deuda técnica aceptable o hay que unificar?
6. **¿Qué pricing/modelo** encaja: licencia perpetua, suscripción, por tienda Shopify?
7. **¿Qué falta para GA (General Availability)?** Prioriza los 4 blockers.
8. **Comparación:** ¿Cómo se posiciona vs Zapier + Shopify Admin + ChatGPT desktop?
9. **Seguridad:** ¿Lanzar con SHA-256 only (sin firma) es aceptable en beta?
10. **Roadmap 90 días:** ¿Qué 5 entregables maximizan readiness comercial?

---

## 15. Archivos clave del source (referencia)

```
version.json
desktop/package.json
desktop/main.js
desktop/runtime/api_server.py
desktop/runtime/process_manager.py
desktop/runtime/shopify_sync.py
desktop/runtime/integrations_store.py
desktop/runtime/hermes_chat.py
desktop/runtime/hermes_shopify_setup.py
desktop/runtime/update/update_manager.py
desktop/updater/maios-updater.ps1
cloud/main.py
connector/connector.py
web/dashboard.html
web/index.html
web/update-center.js
web/system-status.js
tests/test_stabilization_audit.py
tests/test_update_system.py
release/latest.json
scripts/release.ps1
scripts/publish-update.ps1
scripts/sync-to-installed.ps1
```

---

## 16. Comandos build/verify

```powershell
cd C:\Users\Admin\maios
python -m unittest discover -s tests -p "test_*.py" -q
scripts\release.ps1 -Version 1.0.2
scripts\publish-update.ps1 -Version 1.0.2
scripts\setup-local-updates.ps1 -OfferVersion 1.0.2 -ResetState
scripts\test-update-e2e.ps1 -SkipApiCheck
scripts\create-source-zip.ps1
```

---

## 17. Conclusión para el evaluador

MAIOS 1.0.2 es un **producto desktop funcional** con endurecimiento comercial, instalador real rebuild, y validación updater automatizada. **Recomendación:** apto para **beta comercial controlada**; **no declarar GA** hasta firma Authenticode, CDN updates, y E2E install+restart manual completo.

**NO incluye secretos:** tokens Shopify, JWT, device keys omitidos de este informe.

---

*Documento generado para copy-paste a ChatGPT. Source ZIP: `release/VANOVA-source-1.0.2.zip` (~0.55 MB, 191 archivos). Ver `docs/VANOVA-1.0.2-RELEASE-REPORT.md`.*
