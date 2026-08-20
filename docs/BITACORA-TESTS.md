# BITÁCORA DE TESTS — VANOVA / MAIOS

> Método: cada prueba es un experimento con hipótesis medible. Se registra
> fecha, hipótesis, procedimiento, resultado y decisión. Principio rector:
> **si la prueba no ayuda al dueño de Vanova a vender más, no se hace.**
> Última actualización: 2026-08-15

---

## PRUEBA 1 — Delegar una tarea a cada agente

- **Fecha:** 2026-08-15
- **Estado:** EN CURSO
- **Objetivo:** verificar que el dueño puede delegar una tarea a cada uno de
  los 6 agentes instalados y que el agente ejecuta con datos reales y devuelve
  un resultado accionable (no fabricado).
- **Hipótesis:** si el bucle delegación → ejecución → resultado funciona para
  todos los agentes, el dueño puede confiar en MAIOS como equipo de trabajo y
  eso se traduce en decisiones de venta más rápidas.
- **Entorno:** runtime local `127.0.0.1:8765` OK · Hermes `127.0.0.1:8642`
  healthy (deepseek-v4-flash:cloud, warmed) · datos reales: 50 pedidos,
  249 productos.
- **Agentes instalados y habilitados (6):**
  | id | nombre | permisos |
  |----|--------|----------|
  | sales-analyst | Sales Analyst | read_orders, read_products |
  | marketing-agent | Marketing Agent | read_analytics, suggest_actions |
  | content-agent | Content Agent | generate_content, queue_review |
  | ceo-copilot | CEO Copilot | read_all |
  | inventory-agent | Inventory Agent | read_inventory |
  | support-agent | Customer Support Agent | read_tickets, draft_responses |

### Resultados por agente

| Agente | Tarea delegada | Estado | Resultado | Verificable? | Observaciones |
|--------|----------------|--------|-----------|--------------|---------------|
| marketing-agent | Analizar marketing y proponer 3 acciones de optimización | **completed** | No pudo revisar Gmail: no hay token de Google, ni himalaya, ni IMAP configurado. Ofrece 2 opciones: App Password (2 min) u OAuth Google (5 min) | ✅ Honesto: "no voy a inventarte una respuesta" | Cumple principio de honestidad. El Gmail no está conectado — bloqueante para el plan del marketing agent |
| sales-analyst | Analizar ventas 6 meses y proponer 3 productos para vuelta al cole | **running** (en curso) | — | — | Segunda tarea delegada; esperando resultado |
| content-agent | _no delegada (script interrumpido)_ | — | — | — | Repetir |
| ceo-copilot | _no delegada (script interrumpido)_ | — | — | — | Repetir |
| inventory-agent | _no delegada (script interrumpido)_ | — | — | — | Repetir |
| support-agent | _no delegada (script interrumpido)_ | — | — | — | Repetir |

### Hallazgo clave (bloqueante Gmail)

El Marketing Agent intentó revisar el Gmail y confirmó que **no hay acceso a correo configurado**: sin
`google_token.json`, sin himalaya, sin IMAP/SMTP. Ofrece dos caminos:
1. **App Password** (2 min, sin proyecto Google Cloud) — lectura/envío de correo.
2. **OAuth completo de Google** (5 min) — URL de autorización + código → Gmail + Calendar + Drive + Sheets.

### Hallazgo #2 — BUG: "Gmail Conectado" es un falso positivo (2026-08-15)

**Síntoma:** la UI de Integraciones muestra Gmail como **Conectado** (punto verde), pero el
Marketing Agent declara que **no tiene acceso a correo** y no puede revisar el Gmail.

**Evidencia (verificada en disco):**
- `%LOCALAPPDATA%/VANOVA/integrations.json` → `gmail: {connected: true, user: nicolojobesada@gmail.com, pass: SET}` (guardado 2026-08-15 08:40).
- El runtime devuelve `GET /api/integrations/gmail/config` → `{connected: true, passwordSet: true}`.
- Hermes: **no hay** `google_token.json`; el skill `email` solo tiene la herramienta `himalaya` sin credenciales; `config.yaml` solo tiene Telegram/dashboard/NVIDIA/Ollama — nada de email.

**Causa raíz:** dos sistemas separados que no se sincronizan. `integrations.json` (VANOVA Desktop)
persiste credenciales y las marca `connected: true` sin verificar conexión real ni propagarlas al
runtime de Hermes. A diferencia de Shopify — que SÍ tiene un token bridge
(`sync_shopify_from_hermes_if_needed`) — **Gmail no tiene puente inverso**: guardar credenciales
en Integraciones no las instala en el skill de email de Hermes.

**En la UI:** `isApiIntegrationConnected('gmail')` devuelve `true` solo con el flag `connected`
(no exige URL ni token verificados, como sí hacen shopify/erp/drive/facturascript).

**Fix de producto recomendado (NO se aplicó — solo diagnóstico):**
1. Al guardar Gmail en Integraciones, verificar la conexión real (IMAP con App Password) y
   propagar las credenciales al skill de email de Hermes (puente inverso análogo a Shopify).
2. `isApiIntegrationConnected` no debe marcar Conectado solo por flag: exigir credenciales
   verificadas para todos los tipos de integración por igual.
3. El estado de Integraciones debería reflejar el estado real del skill en Hermes, no solo
   el store local.

### Hallazgo #3 — BUG: los datos actuales NO son los reales (vienen de un backup restaurado) (2026-08-15)

**Síntoma:** la app muestra 50 productos "Agenda 15x21" con `netPrice == rrp` (patrón de datos
demo), cuando los datos reales del negocio son 249 productos (p.ej. MAW Mania, `net=1.33` ≠
`rrp=3.72`) y ventas reales. El usuario lo notó al comparar con lo que Hermes mostraba antes.

**Evidencia (verificada en disco):**
- Config ACTUAL (`%LOCALAPPDATA%/VANOVA/config/maios.json`): `organizedProducts=50` (agendas,
  `net=rrp`), `organizedSales=50`. mtime 22:42 UTC.
- El config actual es **idéntico** al backup v2.0.15 (`backup/2026-08-15T22-21-44-671915-v2.0.15/`,
  creado 22:21 UTC, 36 s antes del mtime del config).
- Los datos correctos (249 productos reales) siguen intactos en: backups v2.0.7 / v2.0.10 /
  v2.0.12, backups clásicos (`20260814-034535`, `20260815-025748`) y legacy `MAIOS/config`.
- Logs (`maios-desktop.jsonl`): el updater hace ciclos `update → backup pre-update → restore`
  fallidos repetidos (22:06, 22:08, 22:14, 22:27, 22:30, 22:32, 22:34, 22:36, 22:38, 22:50 UTC).
- `fileOrganization` reciente: "Organizados 0 productos, 1 ventas … preservedExisting:
  {products: 0, sales: 0}". El scanner indexa `cat.xlsx`/`sales.csv` como rutas relativas sin
  resolver (no existen en Documents/Downloads/Desktop).

**Causa raíz:** el updater restaura un backup pre-update sobre el config de producción cuando un
update falla, y lo hace en bucle; una de esas restauraciones cargó un backup con datos demo/parciales
(50 agendas con `net=rrp`) y pisó los datos reales. El scanner además indexa archivos con rutas no
resolubles.

**Fix de producto recomendado (NO se aplicó — solo diagnóstico; NO restaurar datos manualmente):**
1. Restaurar los datos correctos desde un backup bueno (v2.0.12 o clásico con 249 productos).
2. El updater NO debe sobrescribir `organizedProducts`/`organizedSales` al restaurar un backup
   pre-update; y no debe reintentar en bucle cada ~2 min.
3. El scanner no debe aceptar archivos con rutas relativas no resueltas como fuentes reales.

### Hallazgo #4 — BUG: el sync de Shopify trunca el catálogo (462 reales, muestra 50) (2026-08-15)

**Síntoma:** el usuario nota que "los datos están mal" — la tienda real tiene más productos de los que muestra la app.

**Evidencia (verificada con la API real de Shopify):**
- Llamada paginada a `products.json` (siguiendo header `Link`): **462 productos** reales.
- Llamada paginada a `orders.json?status=any`: **99 pedidos** reales.
- El sync actual (`shopify_sync.py`) pide `?limit=50` sin paginar → siempre guarda solo los 50 primeros.
- Además `_map_shopify_products` pone `netPrice = rrp = price` → precios siempre iguales (no reales).

**Causa raíz:** falta de paginación en el cliente REST de Shopify (nunca se sigue el cursor `page_info`
del header `Link`). El catálogo queda truncado a la primera página; los backups (249/50) también son
capturas de este truncamiento.

**Fix aplicado en el repo (`maios/desktop/runtime/shopify_sync.py`):**
- Nueva función `_shopify_get_all(url, token, path, limit=250)` que pagina hasta agotar el cursor
  (tope defensivo 50 páginas / 12 500 filas) y lanza errores con la misma clasificación.
- `_run_sync` usa `_shopify_get_all` para productos y pedidos.
- Verificado en vivo: 462 productos y 99 pedidos mapeados correctamente.

**Pendiente para que lo vea la app:** la app instalada (`Programs\VANOVA\resources\vanova\...`)
tiene su propia copia de `shopify_sync.py` con el bug. Copiar el archivo corregido a la instalación y
reiniciar VANOVA (o incluir el fix en el próximo release). NO se copió a la instalación para no
chocar con el updater que está operando otra instancia.

### Hallazgo #7 — Usuario sin Python: el setup pedía crear un entorno Python que ya estaba incluido

**Objetivo:** un usuario nuevo sin Python instalado debe poder ejecutar VANOVA con solo
instalar el setup y abrir la app.

**Auditoría (qué ya estaba bien):**
- El instalador empaqueta un Python 3.11 portable completo (`resources/vanova/python-bundle/`)
  con TODAS las dependencias de cloud+connector+runtime preinstaladas (fastapi, uvicorn, httpx,
  bcrypt, jose, pydantic, multipart, yaml, websockets, watchfiles, cryptography).
- `python_runtime.resolve_python()` en producción NUNCA cae a `python` del PATH — usa el bundle.
- `process_manager._ensure_venv()` en producción salta la creación del venv si el bundle tiene
  todas las deps (no hace `pip install` por internet en el primer arranque).
- Ningún script del runtime llama a `python` a secas (todos usan `resolve_python()`).

**Bug encontrado y corregido:** `dependency_resolver.py` comprobaba el intérprete bundled bajo
`python/` (que NO existe en el instalador) pero NO bajo `python-bundle/` (el que realmente se
empaqueta). Resultado: el wizard de setup le pedía a un usuario nuevo "crear un entorno Python"
aunque el runtime ya viniera incluido.

**Fix:** `dependency_resolver.py` ahora comprueba `python/` O `python-bundle/` → el plan marca
Python como "Already bundled or configured" (notRequired).

**Verificación end-to-end (simulando usuario sin Python):**
- `PATH=/c/Windows/System32` (sin python del sistema) + `python-bundle/python.exe launcher.py`
  → el runtime arranca y responde `{"status": "ok", "service": "vanova-desktop-runtime"}`.
- El puerto 8765 lo sirve exactamente `python-bundle\python.exe` (netstat + wmic).
- El Cloud (8000) también corre con el bundle. Skill Gmail: "Operativo".
- `verify_dependencies(bundle)` → NINGUNA faltante.

**Tests nuevos (`tests/test_no_python_installed.py`, 5):** preferencia del bundle en producción,
fallo cerrado si falta el bundle, plan del setup sin requerir Python, y verificación real de que
el bundle importa todos los módulos. Suite completa: **290 passed, 1 skipped**.

**Aplicado a la instalación** (`dependency_resolver.py`) — además se limpiaron los `__pycache__`
stale que hacían servir código viejo (importante al copiar archivos a la instalación).

### Hallazgo #5 — Sync del skill Gmail solo corría al guardar, no al arrancar

**Síntoma:** al pedirle al Marketing Agent que compruebe el acceso a Gmail, respondió "No, no he
podido entrar" (abrió el navegador, chocó con el login de Google). El sistema mostraba Gmail
conectado en Integraciones.

**Causa raíz:** el bridge (2.0.17) solo provisionaba el skill al **guardar** la integración
(`integrations_store._trigger_gmail_skill_sync`). Las credenciales guardadas ANTES del fix nunca
se propagaban → `~/.config/himalaya/config.toml` no existía → el agente no tenía credenciales.
Cualquier cliente que actualice con Gmail ya conectado tiene el mismo problema.

**Fix (en repo + instalación):**
- `launcher.py`: nuevo `gmail_skill_loop` al arranque (mismo patrón que el `shopify_loop`) que llama
  a `gmail_skill_bridge.sync_from_integrations_store()`.
- Test de regresión `test_launcher_provisions_skill_at_startup` (falla con el código viejo).

### Hallazgo #6 — himalaya v2 cambió el formato del config (el skill no podía operar)

**Síntoma:** config `~/.config/himalaya/config.toml` escrito correctamente según la doc del skill,
pero `himalaya account check` fallaba: `No backend matching 'auto' is configured`.

**Causa raíz:** el binario oficial actual es **himalaya v2.0.0**, que **eliminó el esquema v1**
(`backend.type = "imap"`, `backend.auth.raw = ...`) y usa esquema URI:
`imap.server = "imaps://..."`, `imap.sasl.plain.username/password.raw`, `smtp.server`,
`mailbox.alias.*`. El skill de Hermes documenta el formato v1 → cualquier config generado por la
v1 no funciona con el binario v2 que instala el bridge.

**Fix (en repo + instalación):**
- `render_himalaya_config()` reescrito al esquema v2 (verificado con `account check` real).
- SMTP usa `smtps://smtp.gmail.com:465` (TLS implícito; 587 es STARTTLS y corrompía el handshake).
- `gmail_skill_status()` lee `imap.sasl.plain.username` (la clave `email =` ya no existe en v2).
- Tests actualizados a v2 + 5 tests nuevos (auto-instalación, formato v2, endpoint).

### Fix completo de producto (2.0.18) — skills de agentes

Implementado y verificado en vivo:
1. **Auto-instalación de himalaya** (`install_himalaya`/`ensure_himalaya`): si el CLI falta,
   descarga el binario oficial (GitHub Releases v2.0.0), lo verifica con `--version` y lo añade al
   PATH del usuario (HKCU Environment, reversible). Probado real: `himalaya v2.0.0` en
   `~/.local/bin/himalaya.exe`.
2. **Endpoint `GET /api/gmail/skill/status`** en `api_server.py` → estado REAL del skill
   (binario, config, sync con la cuenta guardada).
3. **UI**: tarjeta Gmail en Integraciones muestra el estado del skill
   ("Skill operativo — correo disponible" / "Conectado — falta configurar skill").
4. **Launcher**: sync del skill al arrancar (Hallazgo #5).

**Verificación end-to-end (datos reales):**
- `himalaya account check -a gmail` → `imap: OK, smtp: OK`.
- `himalaya envelope list -a gmail` → lee la bandeja real (Genshin, Starbucks, Artlist, Ollama,
  pablo lojo). El Marketing Agent YA puede acceder al correo.

**Aplicado a la instalación** (`Programs\VANOVA\resources\vanova\...`) con backups
(`*.bak-20260815*`): bridge v2, api_server, launcher, version_info, web/dist (dashboard, index,
data-services.js). Suite completa: **285 passed, 1 skipped**.

### Decisiones

- [x] Hallazgo #2: fix completo (bridge + auto-instalación + endpoint + UI) — probado end-to-end con Gmail real.
- [x] Hallazgo #5: sync del skill al arrancar — aplicado y testeado.
- [x] Hallazgo #6: formato v2 de himalaya — corregido y verificado con `account check`.
- [x] Hallazgo #4: `shopify_sync.py` corregido copiado a la instalación (backup `shopify_sync.py.bak-20260815`).
- [ ] Publicar 2.0.18 con los fixes de skills + version consistency (CLOUD_API_VERSION).
- [ ] Reiniciar VANOVA y verificar el estado del skill en Integraciones (UI).

---
