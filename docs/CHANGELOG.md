# VANOVA — Changelog central (seguimiento de cambios)

> Este documento es el **registro único de todos los cambios** del proyecto.
> Cada sesión que publique una versión nueva DEBE añadir su entrada aquí
> (junto con `docs/UPDATES-PLAYBOOK.md`). No se publica sin entrada en el changelog.
>
> **REBRAND 2026-08-15**: el producto pasa de llamarse **MAIOS** a **VANOVA**
> (versión **2.0.0**). Todo lo anterior a 2.0.0 queda como historial de MAIOS.
>
> Última actualización: 2026-08-15 · Versión actual: **2.0.16 (VANOVA, stable)**

## ⚠️ SIGUIENTE PARCHE — PENDIENTE DE APROBACIÓN (NO PUBLICAR)

- **Insights persistentes**: aprobar, rechazar o descartar se conserva como una decisión única en runtime, cloud y UI; los informes de rutina no cambian de ID ni reaparecen después de un nuevo escaneo o reinicio. Los informes pendientes también aparecen en Inicio.

- **Tipografía**: se corrige el CSP de Electron que bloqueaba Google Fonts, cada preset incorpora un fallback local visualmente distinto y la preferencia se conserva en localStorage y en el runtime incluso si una instancia devuelve un valor antiguo tras reiniciar.
- **Hermes — legibilidad del chat**: las secciones de progreso, comandos y respuesta vuelven a apilarse con ancho completo; se elimina el layout flex que comprimía el texto en columnas de una sola letra.
- **Ajustes simplificados**: Diagnóstico queda en su propia vista, sin duplicarse dentro de Ajustes; se elimina el selector de acentos para que cada tema sea la única fuente de su paleta.
- **Seguridad de datos post-update**: el organizador ya no sustituye catálogos, pedidos o clientes normalizados cuando un archivo importado está offline, se ha movido o devuelve cero filas; conserva la fuente de verdad local y elimina únicamente artefactos históricos demostrados.
- **Backups completos**: las copias pre-update incluyen `maios.json`, stores JSON de Hermes/agentes, bases SQLite y sus sidecars WAL/SHM; también se genera un resumen de conteos para detectar una degradación.
- **Recuperación**: Diagnóstico lista las copias pre-update y ofrece restaurarlas mediante un endpoint con ID validado, sin aceptar rutas arbitrarias.
- **Sin truncado destructivo**: organización y sincronización Shopify ya no recortan los datasets persistidos a 500 filas.
- **Orden de arranque**: la copia diaria se crea antes de la organización automática para proteger también migraciones futuras.

---

## 📦 RELEASES

| Versión | Fecha | Estado | Resumen |
|---|---|---|---|
| **2.0.16** | 2026-08-15 | ✅ **stable (VANOVA)** | **Hermes UX**: conversación activa visible, scroll preservado durante streaming y envío con Enter. **Hermes actividad**: eliminados duplicados y ruido de Shopify del chat. **Comercio en vivo**: polling coordinado actualiza Inicio, Ventas, Finanzas, Clientes y Productos. Suite completa: 251 tests correctos, 1 omitido. |
| **2.0.15** | 2026-08-15 | ✅ **stable (VANOVA)** | **Hermes en vivo**: respuesta, progreso, herramientas y comandos separados, legibles y persistentes. **Sincronización**: Inicio, Tareas, Actividad, Insights y Agentes comparten estado y polling; detalle de tareas en vivo. **Insights**: acciones persistentes e información importante disponible para agentes. **Personalización**: tarjetas de Inicio y tipografía desde Ajustes. Gate UX + 247 tests correctos (1 omitido por fixture local opcional). |
| **2.0.14** | 2026-08-15 | ✅ **stable (VANOVA)** | **Finanzas**: las tarjetas de Ingresos, Pedidos, Ticket medio y Margen bruto son clicables y abren su desglose contextual (periodo, origen y registros), sin añadir cuadros nuevos. **Datos normalizados**: clientes y pedidos ya no confunden provincia, país, actividad, NIF/CIF u otras columnas con el nombre/identificador principal; el mapeo exige encabezados compatibles y valida el contenido. **Scanner**: permite elegir primero la carpeta de empresa, analiza mejor el contenido y excluye archivos históricos del dashboard/MAIOS antiguo para no contaminar los datos actuales. **Migración**: limpia únicamente registros heredados ambiguos y conserva las fuentes válidas. **Runtime/UI**: el aviso falso de runtime no disponible deja de parpadear; el estado se reutiliza y la comprobación normal queda coordinada cada 30 segundos. Incluye los fixes de 2.0.13 y el gate UX de release. |
| **2.0.13** | 2026-08-15 | ✅ **stable (VANOVA)** | **Finanzas en tiempo real**: desglose "de dónde salen los números" (este mes / este año / histórico en ingresos y pedidos + ingresos por mes) y **margen bruto real** calculado desde el catálogo (PVP − coste). **Scanner**: el setup pregunta la carpeta de la empresa antes de escanear; análisis de contenido mucho más profundo (PDF, DOCX, ODS, XLS, DOC y más bytes por archivo, contenido analizado siempre, no solo nombres dudosos) y **actividad en tiempo real** en Inicio/Actividad (paso, % y barra, poll 2s). **Aprobaciones**: decidir quita la tarjeta al instante (optimista + feedback real de error). **Insights**: "marcar importante" ahora guarda para los agentes Y resuelve el insight; **bug raíz corregido** — los informes de rutina usan ID estable (agente+título) para que descartar/aprobar no se pierda al repetirse la rutina. **Licencias**: detección desde los nombres reales de los productos (Hello Kitty, Sanrio, Harry Potter, Disney…) en vez de las 6 fijas de MOOVING. **Login manual arreglado**: valida contra las credenciales reales del runtime (cloud.env) en vez de dar "credenciales incorrectas". **Hermes-as-tarea**: el Inicio ya filtra las tareas internas de Hermes igual que la vista Tareas. **Updater**: fixes de `Path(None)` (estado con packagePath null) y resume corrupto (solo 206; con 200 se descarta el .partial) |
| **2.0.12** | 2026-08-15 | ✅ **stable (VANOVA)** | **Hermes en tiempo real**: el chat de Hermes ahora muestra en vivo los pasos que ejecuta (comandos `$`, herramientas 🔎) y la respuesta entra en streaming línea a línea (ya no se ve solo el resultado final). Backend: `_run_hermes_cli` sin `--quiet` con callback de progreso que expone `progress.steps` + `progress.partial` + `statusText` en `/api/hermes/requests/{id}`; el frontend los pinta durante el polling (600ms). Verificado E2E: progreso 0→24 pasos en vivo con texto parcial, resumen final limpio. Incluye además todos los fixes de 2.0.11 (updater) y 2.0.10 (python-bundle portable) |
| **2.0.11** | 2026-08-15 | ✅ **stable (VANOVA)** | **Fix crítico del updater (UI se quedaba en "Instalando actualización...")**: el runtime lanzaba el updater con `DETACHED_PROCESS`, que rompe el spawn en Windows — el PowerShell arrancaba pero nunca ejecutaba el script → la actualización nunca se instalaba. Se reproduce y se aísla la flag culpable; ahora se usa solo `CREATE_NEW_PROCESS_GROUP \| CREATE_NO_WINDOW` (verificado: ejecuta bien y sin ventana). Canal ya por GitHub Releases |
| **2.0.10** | 2026-08-15 | ✅ **stable (VANOVA)** | **FIX CRÍTICO — runtime no arranca en clientes (exit 103)**: el `python-bundle` empaquetado era un *venv* cuyo `pyvenv.cfg` apuntaba al Python de `uv` de la máquina de build (`C:\Users\Admin\AppData\Roaming\uv\python\...`). En cualquier otro PC esa ruta no existe → `python.exe` moría al instante (código 103) → el runtime nunca arrancaba → el setup se quedaba en "Conectando..." para siempre. Ahora el bundle es un **CPython standalone completo y autocontenido** (sin venv, sin rutas de la máquina de build; verificado portable copiándolo a otra ruta), y la resolución de Python acepta `python-bundle/python.exe` (raíz). Afectaba a TODOS los instaladores anteriores; los clientes deben reinstalar con este instalador. **Canal estable migrado a GitHub Releases** (`frexcz-star/vanova-updates`): la 2.0.10 lleva la URL de GitHub grabada (`/releases/latest/download/latest.json`), estable e independiente de esta máquina — se acabó el "sin conexión" por cambio de túnel |
| **2.0.9** | 2026-08-15 | ✅ **stable (VANOVA)** | **Fix setup colgado en "Conectando con los servicios de VANOVA"**: en el primer arranque tras instalar (cliente lento/antivirus escaneando), el runtime tarda más de 30s en responder y Electron lo mataba y relanzaba en bucle sin dejarle terminar → el setup nunca conectaba. Ahora Electron **no mata el runtime mientras siga vivo** (espera extendida de 2.5 min por intento) y la pantalla de Environment Analysis espera hasta 10 min con contador en vivo y muestra el error real si falla (para diagnosticar en cliente). Rebuild 2.0.9 con URL del túnel nueva empaquetada |
| **2.0.8** | 2026-08-15 | ✅ **stable (VANOVA)** | **Recuperación del canal de updates**: el túnel cloudflared se cayó y la URL cambió (los clientes veían "sin conexión"); instalador reconstruido con la URL nueva grabada (`stocks-regular-automatic-tender`) para desatascar a los clientes — se sube a 2.0.8 para que el updater detecte la versión nueva aunque ya estén en 2.0.7 |
| **2.0.7** | 2026-08-15 | ✅ **stable (VANOVA)** | **Fix visual integraciones**: la tarjeta de Gmail mostraba "pendiente" aunque estuviera conectada (el estado no se cargaba: `store.gmail` faltaba en el loop de loadAppData) — ahora muestra Conectado; Drive y FacturaScript se unifican al mismo sistema de guardado local+cloud (antes solo cloud, fallaba en sesión local) y se normaliza `apiKey`→`api_key` para que la clave de FacturaScript se guarde |
| **2.0.6** | 2026-08-15 | ✅ **stable (VANOVA)** | **Fix integración Gmail**: la conexión siempre fallaba con "Error inesperado" porque `imaplib.IMAP4_SSL` no tiene `settimeout` (bug real de la librería usada) — ahora usa el timeout del socket, la prueba de conexión IMAP funciona de verdad y da errores claros de credenciales; guardado cifrado de contraseña de aplicación OK |
| **2.0.5** | 2026-08-15 | ✅ **stable (VANOVA)** | Fix detalle de tarea: botón ✕ ya cierra (el modal estaba fuera de la delegación de clics + id duplicado con "Nueva tarea"), cierre con clic fuera y Escape, y textos más grandes en el modal |
| **2.0.4** | 2026-08-15 | ✅ **stable (VANOVA)** | Selector de temas movido a Ajustes → Apariencia (se quita el botón flotante) + fixes visuales: elementos circulares ya no se rompen (acentos, dots, avatares), transiciones de tema suaves y limitadas a superficies |
| **2.0.3** | 2026-08-15 | ✅ **stable (VANOVA)** | 16 temas de interfaz (Ember se adapta solo al día/noche; selector flotante con preview), UI totalmente redondeada, logo VANOVA, botón "Importante" en tareas/insights (los agentes podrán usarlo), integraciones Gmail/Drive/FacturaScript con test de conexión real y botón "Que Hermes la conecte" (modo web y local) |
| **2.0.2** | 2026-08-15 | ✅ **stable (VANOVA)** | Fix crítico: diagnóstico "runtime no disponible" (probe del frontend) + botón de reinicio + strings/etiquetas de updates |
| **2.0.1** | 2026-08-15 | ✅ **stable (VANOVA)** | Fix: cloud viejo ya no secuestra la UI (probe de marca/versión) + strings visibles |
| **2.0.0** | 2026-08-15 | ✅ **stable (VANOVA)** | Rebrand completo MAIOS → VANOVA + migración de datos |

| Versión | Fecha | Estado | Resumen |
|---|---|---|---|
| **1.0.15** | 2026-08-15 | ✅ **stable (recomendada)** | Sin ventanas de terminal; todo lo anterior |
| 1.0.14 | 2026-08-15 | stable (sustituida por 1.0.15) | Agentes con datos reales + detalle de tarea |
| 1.0.13 | 2026-08-15 | stable (sustituida) | Insights vs Tareas, agentes en vivo, escaneo selectivo |
| 1.0.12 | 2026-08-15 | stable (sustituida) | Arranque rápido + setup arreglado + túnel nuevo |
| 1.0.11 | 2026-08-15 | stable (sustituida) | No auto-descarga de modelos Ollama locales |
| 1.0.10 | 2026-08-15 | PRUEBA | Ciclo completo de update confirmado en cliente real |
| 1.0.9 | 2026-08-15 | (sustituida) | Updater asíncrono, botones responden |
| 1.0.8 | 2026-08-15 | (sustituida) | Barra de progreso, fix Range, timeout 300s |
| 1.0.7 | 2026-08-14 | (sustituida) | Fixes intermedios del canal de updates |
| 1.0.6 | 2026-08-14 | (sustituida) | Pipeline de updates operativo (túnel + servidor) |

---

## 2.0.0 — REBRAND: VANOVA → VANOVA (2026-08-15)

**Objetivo:** el producto deja de llamarse VANOVA (nombre del plan estratégico de
MOOVING PAPER) y pasa a **VANOVA** — nombre universal, comercializable, sin
colisión con el VANOVA original ni con la marca del cliente.

**Qué se cambió (todo el branding visible):**
- `productName` → **VANOVA**, `appId` → `com.vanova.os`, instalador →
  `VANOVA-Setup-<version>.exe`, accesos directos → VANOVA, título de ventana →
  VANOVA, `<title>` web → **VANOVA — AI Operating System** (se elimina el
  sufijo "MOOVING"), página de setup/error/loading → VANOVA, strings visibles
  del dashboard y del asistente → VANOVA, `version.json` productName/publisher
  → VANOVA, `cloud APP_NAME` → VANOVA Cloud, manifest de updates `product` →
  VANOVA, `installer.nsh` → VANOVA, `publish-remote.ps1` → VANOVA-Setup.
- `desktop/package.json` extraResources: `resources/maios/*` → `resources/vanova/*`
  (getAppRoot / updater / version.json en el empaquetado).

**Migración de datos (sin perder nada):**
- Los datos viven en `%LOCALAPPDATA%\VANOVA`; ahora la app usa
  `%LOCALAPPDATA%\VANOVA`. Migración automática en el primer arranque
  (idempotente): `main.js::migrateLegacyData()` + `paths.py::_migrate_legacy_data_dir()`
  copian config/maios.json (productos/precios), tasks.db, approvals.db, logs y
  backups, saltándose venv/updates/temp.
- El instalador `deleteAppDataOnUninstall: false` → la desinstalación nunca
  borra datos.

**Canal de updates con guard de producto:**
- `update_manager` ahora ignora manifests de OTRO producto (un VANOVA instalado
  nunca instalará un manifest VANOVA y viceversa) — cada producto tiene su canal.
- `UpdateManifest.product` default → "VANOVA".
- El guard evita que un VANOVA 1.0.15 instalado entre en bucle intentando
  instalar VANOVA 2.0.0 como si fuera su propia actualización.

**NOTAS de migración para clientes:**
- Los clientes con VANOVA instalado NO reciben VANOVA por el canal automático
  (producto distinto por diseño). Se instala VANOVA 2.0.0 manualmente y la
  primera apertura migra sus datos.
- El repo/carpeta del proyecto sigue llamándose `maios` (ruta de desarrollo,
  no es parte de la marca).

## 1.0.15 — Sin ventanas de terminal (2026-08-15)

**Objetivo:** que el cliente nunca vea consolas de Windows al usar VANOVA.

- **Updater (runtime + Electron)**: se eliminó `cmd /c start "" /MIN` (creaba una
  consola minimizada visible). Ahora se lanza PowerShell directo con
  `CREATE_NO_WINDOW` / `windowsHide: true`.
  - `desktop/runtime/update/update_manager.py::_spawn_updater`
  - `desktop/main.js::spawnUpdaterProcess`
- **Probes de arranque** que parpadeaban una consola, ahora con
  `creationflags=CREATE_NO_WINDOW`:
  - `python_runtime.py` (verify_python, check_dependency, verify_dependencies)
  - `startup_gate.py::_python_version`
  - `system_analyzer.py::_gpu_name` (wmic)
  - `config_store.py` (icacls)
  - `process_manager.py` (venv + pip install)
- Verificado dentro del empaquetado + gate de UX en verde.
- `docs/UPDATES-PLAYBOOK.md` actualizado.

## 1.0.14 — Agentes con datos reales + detalle de tarea (2026-08-15)

**Objetivo:** corregir el bug de contexto — los agentes de IA decían "no tengo
precios" cuando los datos ya estaban en VANOVA. Fix de arquitectura (una única
fuente de verdad), NO parche de prompt.

- **Nuevo `desktop/runtime/agent_data_tools.py`**: capa de datos que consultan
  los agentes, leyendo el mismo `config_store` que el Dashboard:
  `get_products`, `get_product_by_sku`, `get_product_prices` (coste+PVD+margen),
  `get_inventory`, `get_sales`/`get_orders` (filtro fechas),
  `get_product_performance`, `get_uploaded_files`, `get_imported_dataset`,
  `data_availability`, `render_context_block` (inyección en prompt).
- **Hermes recibe datos REALES** (filas SKU/precio/ventas), no solo contadores:
  `hermes_chat.build_operational_context` inyecta `render_context_block()`.
- **Tareas con 2ª pasada** (`task_queue._execute_task`): si el modelo dice que
  falta un dataset que sí existe, VANOVA resuelve la herramienta y reintenta una
  vez con los datos reales. Nunca pide re-subir archivos.
- **Endpoints nuevos** (con runtime_security):
  - `GET /api/agent/data/tools`
  - `GET /api/agent/data/<herramienta>?params`
  - `GET /api/tasks/<id>` y `GET /api/tasks/<id>/events`
- **Frontend**: tarjetas de tarea clicables → modal de detalle en vivo (payload,
  progreso, resultado, error, línea de eventos; poll 3s). `web/dist` sincronizado.
- **Prueba de aceptación real** (249 productos, 50 pedidos): cuántos productos,
  SKUs con coste, PVD por SKU, top márgenes — todo respondido desde los datos
  reales. Dato que falta de verdad: los pedidos no llevan SKU por línea.
- Tests: +10 nuevos (`tests/test_agent_data_tools.py`) → 227 passed.

## 1.0.13 — Insights, agentes en vivo, escaneo selectivo (2026-08-15)

**Objetivo:** separar tareas de insights, más info en tiempo real de agentes y
escaneo de archivos preciso (mejor 1 archivo bueno que 1000 con 2 útiles).

- **Tareas ≠ Insights**: las rutinas automáticas de agentes se registran como
  **Insights** (`insight_store.py` + hook en `task_queue`); Tareas queda solo
  para lo manual del usuario. Vista Insights en el dashboard.
- **Agentes en vivo**: `agent_architect.list_agents()` expone `currentActivity`,
  `progress`, `nextRun`, `lastInsight`, `insightsGenerated`; tarjetas y detalle
  muestran qué hace cada agente ahora.
- **Escaneo selectivo**: nuevo `file_relevance.py` + `business_scanner` reescrito
  (carpetas → nombres → contenido). Poda carpetas irrelevantes (música, fotos,
  descargas, juegos…), descarta archivos personales, importa solo lo claramente
  de empresa. Los dudosos → `fileCandidates` → notificación con modal
  Aprobar/Rechazar (`/api/files/candidates` + `/api/files/candidates/decide`).
- **Fix icono reloj gigante**: CSS base `svg{display:block;width:1em;height:1em}`.
- Tests: +8 → 217 passed.

## 1.0.12 — Arranque rápido + setup arreglado (2026-08-15)

- `_ensure_venv()` se salta venv + pip install en instalaciones empaquetadas
  (el `python-bundle` ya trae todas las deps y `resolve_python()` lo prefiere;
  el venv nunca se usaba). `verify_dependencies()` = 1 probe (~1s).
- `boot()` en `main.js`: la ventana de setup aparece AL INSTANTE, runtime en
  segundo plano (antes bloqueaba hasta 150s sin ventana).
- `ui/setup.js`: `api()` con timeout (60s) + `res.ok`; la pantalla Environment
  deja de reintentar en bucle infinito → error claro con botón **Reintentar**.
- ⚠️ El instalador 1.0.12 lleva la URL del túnel NUEVA empaquetada (los clientes
  con URL vieja 1.0.9-1.0.11 necesitan re-apuntarse o reinstalar).

## 1.0.11 — Sin auto-descarga de modelos Ollama locales (2026-08-15)

- VANOVA ya NO descarga modelos locales de Ollama por su cuenta. Cloud (`:cloud`)
  sigue funcionando (por API, no descarga nada local). Locales solo si ya están
  instalados; si no, avisa con el comando manual (`ollama pull <modelo>`).

## 1.0.10 — PRUEBA del ciclo completo (2026-08-15)

- Release de PRUEBA que confirmó de punta a punta el pipeline de updates en el
  PC real de un cliente: manifest → descarga 92.8 MB → sha256 → instalación
  silenciosa → reinicio automático → 1.0.10. ✅

## 1.0.9 — Updater asíncrono (2026-08-15)

- `download_update()` es asíncrono (hilo en segundo plano; antes bloqueaba la
  petición HTTP durante toda la descarga → botones muertos). Guard de
  concurrencia (doble clic no duplica). `install_update()` espera al hilo.

## 1.0.8 — Progreso y fixes de descarga (2026-08-15)

- Barra de progreso desde el primer segundo; modal de error descartable con
  "Más tarde" (también en estado `failed`); fix del bug de Range del servidor
  (AttributeError tras cada transferencia); timeout de descarga 60s → 300s.

## 1.0.7 / 1.0.6 — Canal de updates operativo (2026-08-14)

- Pipeline completo: cliente → túnel cloudflared → servidor estático 8137 con
  Range → `release/` (manifest + instalador). Comprobación cada 4h + botón
  "Buscar actualizaciones". El cliente lee la URL desde `version.json`
  empaquetado, con override por `%LOCALAPPDATA%\VANOVA\updates\updates-config.json`.

---

## 🏗️ INFRAESTRUCTURA (canal de updates)

| Componente | Detalle |
|---|---|
| URL del túnel | `https://kings-bind-taught-oclc.trycloudflare.com` (cambia si muere cloudflared — ver playbook 4b) |
| Servidor | `scripts/range-static-server.py release 8137` (Range/206) |
| Túnel | `cloudflared tunnel --url http://127.0.0.1:8137 --no-autoupdate` |
| Watchdog | `scripts/watch-update-host.py` (relanza el 8137 si muere) |
| Manifest | `release/latest.json` (+ `latest.local.json` para dev de esta máquina) |
| Publicar | `scripts/publish-remote.ps1 -PublicUrl <url>` (o generar manifest con python) |
| Build | `cd desktop && npm run desktop:installer` (~9 min; el proceso muere tras el blockmap si se corta — el exe ya está generado, solo falta renombrar) |

**Incidentes registrados:**
- **15-ago**: al reiniciar Freebuff (máquina de trabajo) TODOS los procesos en
  background mueren — incluido cloudflared → el túnel cambió de URL
  (`arrive-cream-…` → `kings-bind-taught-oclc.…`). Los clientes con la URL vieja
  empaquetada ven "Sin conexión" hasta re-apuntarse (4b) o reinstalar.
- **15-ago**: el instalador de updates mata procesos python del sistema (mató el
  servidor 8137 varias veces durante las actualizaciones de prueba) — el
  watchdog lo relanza, pero si murió hay que levantarlo a mano tras cada update.

**Pendiente recomendado:** dominio permanente `releases.moovingpaper.com`
(Cloudflare R2/S3 con Range) — elimina la dependencia de esta máquina encendida
y el cambio de URL al reiniciar.

---

## ✅ PROCESOS (calidad por release)

- **`maios-ux-audit/ux_release_test.py`** — GATE OBLIGATORIO antes de publicar
  cualquier versión (exit 0 o no se publica): [A] integridad del empaquetado,
  [B] canal de updates (manifest, sha256, Range 206, detección), [C] runtime en
  vivo (health, version, agents, insights, tasks, files, candidates,
  command-center, updates/status). Correr con `PYTHONIOENCODING=utf-8` (consola
  cp1252) y `--skip-live` si no hay runtime.
- **`docs/UX-CHECKLIST.md`** — checklist manual visual (arranque, tareas vs
  insights, agentes en vivo, escaneo/candidatos, updates, regresión).
- **`maios-ux-audit/e2e_live_update.py`** — E2E de update contra el host real
  (descarga completa + sha256). Fuerza el túnel vía `MAIOS_UPDATE_MANIFEST_URL`
  (si no, `fetch()` relee el override local de esta máquina).
- **Tests**: `pytest tests/` → **227 passed, 1 skipped**.
- **Regla de oro**: toda release, por pequeña que sea, pasa por el gate de UX +
  checklist manual + entrada en este changelog.

---

## 🧠 ARQUITECTURA (fuente de verdad única)

```
Archivos importados → Hermes procesa → filas normalizadas (config_store:
organizedProducts / organizedSales / scanFiles / fileCandidates)
        ↓
  agent_data_tools (capa de datos) ──→ Dashboard (Productos/Ventas/Archivos)
        ↓
  Contexto de agentes (render_context_block) + herramientas /api/agent/data/*
        ↓
  Hermes (chat, tareas, rutinas) — 2ª pasada si pide datos que ya existen
```

Reglas:
- El Dashboard y los agentes leen el MISMO almacén → nunca se contradicen.
- Los agentes nunca piden re-subir un archivo que VANOVA ya tiene importado.
- Si un dato no existe de verdad (p. ej. ventas por SKU, stock), el agente lo
  dice con precisión — `data_availability()` es la fuente de esa distinción.

---

## ⚠️ CAVEATS CONOCIDOS

1. El túnel depende de esta máquina encendida (dominio permanente = solución).
2. Clientes instalados con URL vieja (1.0.9-1.0.11) ven "Sin conexión" hasta
   re-apuntarlos (`updates-config.json`) o reinstalar.
3. El instalador mata procesos python al actualizar → relanzar el servidor 8137
   + watchdog tras cada update de prueba.
4. Enlaces tmpfiles caducan a las 48h.
5. `web/dashboard.html` y `web/dist/` deben ir SIEMPRE sincronizados (copiar
   ambos al editar; el empaquetado sirve desde los recursos).
