# VANOVA — Playbook de Actualizaciones (cómo publicar updates)

> Documento operativo: cómo funciona el canal de updates y cómo publicar una
> versión nueva. Cualquier sesión futura debe leer esto antes de tocar el
> sistema de updates. Última verificación: 2026-08-15 (**VANOVA 2.0.16** —
>
> ✅ **CANAL ESTABLE = GITHUB RELEASES (activo desde 2.0.10).** Repositorio público
> `https://github.com/frexcz-star/vanova-updates`. La URL del manifest es
> `https://github.com/frexcz-star/vanova-updates/releases/latest/download/latest.json`
> (estable, no depende de esta máquina). `version.json` del repo ya apunta ahí, así que
> cada build empaqueta esa URL. Para publicar: `scripts/publish-github-release.ps1`
> (prepara `release/github/latest.json`) → subir los DOS assets a una release con tag
> `v.<version>`: `VANOVA-Setup-<version>.exe` + `latest.json` → verificar
> `releases/latest/download/latest.json`. El túnel queda solo como transición para
> clientes que aún apunten a él: `publish-remote.ps1 -PublicUrl <tunel> -DownloadUrl
> <url-github-del-instalador>` (publican el manifest y la descarga sale de GitHub).
>
> **Próximo parche pendiente (tipografía):** el CSP de Electron debe permitir `fonts.googleapis.com` y `fonts.gstatic.com`; los presets también llevan fallbacks locales para que cambien aunque el cliente no tenga acceso a Google Fonts. La preferencia se guarda en localStorage + `maios.json`, y la local gana frente a un valor de runtime antiguo tras un reinicio.
>
> **Próximo parche pendiente (Hermes):** las tarjetas de conversación deben mantener progreso, comandos y respuesta en una columna de ancho completo; no usar un contenedor flex horizontal para esas secciones porque comprime el texto a columnas ilegibles.
>
> **Próximo parche pendiente (Ajustes):** Diagnóstico vive únicamente en su vista propia; la apariencia se controla mediante temas completos y no mediante un segundo selector de colores de acento.
>
> **Próximo parche pendiente (Insights):** las decisiones de aprobar/rechazar/descartar se escriben en el runtime y se sincronizan con Cloud sin que una rutina posterior cambie el identificador. El filtro se aplica también a snapshots del scanner y los insights pendientes se muestran en Inicio; el gate debe probar una acción, un nuevo escaneo y un reinicio.
>
> **CRÍTICO 2.0.10 — python-bundle portable:** el bundle era un *venv* cuyo `pyvenv.cfg`
> apuntaba al Python de uv de la máquina de build → en clientes `python.exe` salía con
> código 103 al instante → runtime nunca arrancaba → setup colgado en "Conectando...".
> Todos los instaladores ≤2.0.9 estaban rotos para clientes (solo funcionaban en la máquina
> de build). Ahora `scripts/prepare-python-bundle.ps1` copia un CPython standalone completo
> (sin venv, sin rutas) y la resolución acepta `python-bundle/python.exe` (raíz).
> ⚠️ El instalador ahora pesa ~102 MB → **tmpfiles rechaza >100 MB (HTTP 413)** — para
> entregar a un cliente, usar el link directo del túnel (`<tunel>/VANOVA-Setup-<v>.exe`).
> (el túnel ya NO es el canal principal; ver docs/CHANGELOG.md).
>
> **INCIDENTE 15-ago (2.0.8):** el túnel `kings-bind-taught-oclc` se cayó y la URL cambió;
> los clientes vieron "sin conexión" porque su `version.json` apuntaba a la URL muerta y no hay
> autodescubrimiento (necesitarían consultar la URL muerta para enterarse de la nueva).
> Recuperación: relanzar `cloudflared` (nueva URL `stocks-regular-automatic-tender`), republicar
> manifest (`publish-remote.ps1 -PublicUrl <nueva-url>`), actualizar `version.json` (repo + instalada),
> y **subir de versión** (2.0.8) para que el updater de clientes ya instalados detecte la nueva
> aunque estén en la misma base — si se reconstruye la misma versión, el cliente no actualiza.
> Repetir el `start-update-host.ps1` en cada reinicio del PC o los clientes vuelven a quedarse sin canal.

---

## 0.1 INCIDENTE DE DATOS Y GATE OBLIGATORIO (parche siguiente)

Nunca se publica una update que no pruebe la conservación de datos. Antes de
organizar archivos o instalar una versión, el runtime debe crear una copia
completa fuera del directorio de instalación. La copia debe incluir:

- `config/maios.json` y todos los ficheros de configuración;
- stores JSON de Hermes/agentes/insights e integraciones;
- `tasks.db`, `approvals.db` y sidecars `-wal`/`-shm`;
- un manifiesto con versión, fecha y conteos de productos, pedidos, clientes y archivos.

El organizador **no puede reconstruir de forma destructiva**: si un archivo
importado está fuera de línea, movido, protegido o devuelve cero filas, se
conservan los registros normalizados ya aceptados. Solo se excluyen artefactos
internos de MAIOS/VANOVA identificados de forma explícita. No se aplican límites
silenciosos de 500 filas al almacenamiento local.

La UI de Diagnóstico muestra las copias previas a la actualización. Restaurar
solo acepta el identificador generado por VANOVA, nunca una ruta suministrada
por el usuario, y requiere reiniciar la app después. El gate de release debe
probar: backup completo, rescan con archivo inaccesible, restauración y conteos
idénticos antes/después.

## 1. CÓMO FUNCIONA (arquitectura en una frase)

Un VANOVA instalado lee la URL del manifest desde su `version.json` empaquetado,
descarga `latest.json`, compara versiones (semver), y si hay una más nueva
descarga el instalador por HTTPS (con **resume** vía Range), verifica **sha256**,
hace backup, instala en silencio, reinicia y, si algo falla, hace rollback.
La comprobación es automática cada 4h + botón "Buscar actualizaciones".

Flujo del canal actual (temporal, sin dominio propio):

```
Cliente VANOVA ──HTTPS──▶ https://<tunel>.trycloudflare.com  (cloudflared, sin cuenta)
                                   │  apunta a
                                   ▼
                    http://127.0.0.1:8137  (range-static-server.py)
                                   │  sirve
                                   ▼
                    C:\Users\Admin\maios\release\
                    ├── latest.json               ← manifest (versión, sha256, URL)
                    └── VANOVA-Setup-<versión>.exe ← instaladores
```

## 1.1 CANAL ESTABLE GRATUITO (pendiente — cuenta GitHub restringida)

Objetivo: repositorio público `https://github.com/nicolojobesada-spec/vanova-updates`
que contenga únicamente assets (instalador + `latest.json`), sin el código fuente
de VANOVA, para que el canal no dependa de esta máquina encendida.

**Estado 15-ago (2.0.2): PENDIENTE.** La release y el repositorio existen, pero
GitHub los oculta a visitantes anónimos (404): el perfil NO está privado y el
repo dice "public", pero GitHub devuelve 404 sin login — síntoma de cuenta
restringida por ser nueva. Por eso la 2.0.2 se publica por el TÚNEL (canal
anterior), y el `version.json` empaquetado apunta al túnel.

Cuando la cuenta se normalice (o se cree una nueva/org):

1. Subir los dos assets de la release (`VANOVA-Setup-<v>.exe` + `latest.json`).
2. Cambiar `version.json` → `updateManifestUrl`:
   `https://github.com/<owner>/<repo>/releases/latest/download/latest.json`
3. Rebuild + gate + publicación (ver §3).
4. Reconstruir la transición por túnel solo si quedan clientes 2.0.x antiguos.

**Preparar assets:** `powershell -File scripts/publish-github-release.ps1`
(genera `release/github/latest.json` y deja el instalador versionado). El script
admite `-Upload` con `GITHUB_TOKEN` local (permiso `Contents: write`); nunca
guardar ni compartir el token.

## 2. INFRAESTRUCTURA ACTUAL (14-ago-2026)

| Componente | Detalle |
|---|---|
| URL del túnel | `https://kings-bind-taught-oclc.trycloudflare.com` (cambió el 15-ago — si muere cloudflared vuelve a cambiar, ver 4b) |
| Servidor local | `scripts/range-static-server.py <release> 8137` (soporta Range/206) |
| Túnel | `"C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://127.0.0.1:8137 --no-autoupdate` |
| Watchdog | `scripts/watch-update-host.py` — comprueba cada 30s y relanza el servidor si muere |
| Manifest | `release/latest.json` (product `VANOVA`; el updater ignora manifests de otro producto) |
| Instaladores | `release/VANOVA-Setup-<versión>.exe` (el build genera `VANOVA-Setup.exe`) |
| Versión | `version.json` (raíz) + `desktop/package.json` + `shared/version_info.py` (`CLOUD_API_VERSION`) |
| Build | `cd desktop && npm run desktop:installer` (electron-builder NSIS, ~3 min incremental) |
| Tests | `pytest tests/` (217 OK) — `test_version_consistency` exige que `CLOUD_API_VERSION` == versión actual |

## 3. CÓMO PUBLICAR UNA VERSIÓN NUEVA (paso a paso)

```bash
# 1) Subir versión en los 3 sitios (¡los tres!):
#    - version.json            -> "version": "2.0.X"
#    - desktop/package.json    -> "version": "2.0.X"
#    - shared/version_info.py  -> CLOUD_API_VERSION = "2.0.X"

# 2) Build del instalador (desde desktop/)
cd desktop && npm run desktop:installer > build.log 2>&1
# Esperar a que termine (poll: mientras exista node.exe)

# 3) Verificar que el empaquetado tiene la versión correcta:
grep '"version"' release/win-unpacked/resources/maios/version.json

# 4) IMPORTANTE: sobrescribir el instalador con versión SIEMPRE antes de publicar.
#    publish-remote.ps1 solo copia si el destino NO existe -> con cp -f el sha256
#    del manifest coincide con el build fresco.
cp -f release/VANOVA-Setup.exe release/VANOVA-Setup-1.0.X.exe

# 4b) GATE OBLIGATORIO DE UX (¡NO SALTAR, NI EN RELEASES PEQUEÑAS!):
#     antes de publicar, el test automático debe pasar TODO (exit 0) y la
#     checklist manual debe estar completa.
python maios-ux-audit/ux_release_test.py          # empaquetado + canal + runtime en vivo
#     + completar docs/UX-CHECKLIST.md (lo visual: ventanas, botones, iconos, flujos)

# 5) Publicar el manifest del canal actual (túnel; Range + sha256)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/publish-remote.ps1 \
  -PublicUrl "https://<tunel-actual>.trycloudflare.com"
# (Cuando GitHub funcione: sustituir por publish-github-release.ps1 y ver §1.1.)

# 6) (Opcional) Poner notas de release claras en release/latest.json:
#    editar el campo "releaseNotes" y guardar (dejar sha256/size intactos).

# 7) Verificar el canal público:
curl -s https://<tunel-actual>.trycloudflare.com/latest.json   # version + sha256
curl -s -r 0-1023 -o /dev/null -w "%{http_code}\n" https://<tunel-actual>.trycloudflare.com/VANOVA-Setup-1.0.X.exe  # debe dar 206

# 8) (Opcional) Enlace de descarga manual para el cliente (caduca en 48h):
curl -s -m 300 -F "file=@release/VANOVA-Setup-1.0.X.exe" "https://tmpfiles.org/api/v1/upload?expires=172800"
```

Los clientes instalados detectan la versión nueva en ≤4h (check automático) o al
instante con **Ajustes → Centro de actualizaciones → Buscar actualizaciones**.

> **REGLA DE ORO (pedida por el cliente)**: toda release, por pequeña que sea,
> pasa por el test de UX antes de publicar: `ux_release_test.py` (automático,
> exit 0 obligatorio) + `docs/UX-CHECKLIST.md` (manual, visual).

## 4. RECUPERACIÓN (cuando algo se rompe)

### 4a. El túnel devuelve 502 / "Sin conexión" en el cliente
El servidor Python del 8137 murió (cloudflared sigue vivo). El watchdog
(`watch-update-host.py`) debería relanzarlo solo en <60s. Comprobar:
```bash
netstat -ano | grep ":8137 " | grep LISTENING          # ¿hay servidor?
tasklist | grep -i cloudflared                          # ¿vive el túnel?
curl -s -o /dev/null -w "%{http_code}\n" https://<tunel>/latest.json   # 200 = OK
tail -20 maios-ux-audit/range_server.log                # trazas
```
Manual: relanzar `range-static-server.py release 8137` (mismo puerto = misma URL).

### 4b. Cloudflared murió (el peor caso)
Un túnel quick de cloudflared **cambia de URL en cada arranque**. Los clientes ya
instalados tienen la URL VIEJA empaquetada y no podrían encontrar la nueva.
- Re-ejecutar `scripts/start-update-host.ps1` → arranca servidor + túnel + republish
  y **imprime el URL nuevo**.
- Repartir el URL nuevo a los clientes. **Sin reinstalar**, se puede re-apuntar un
  cliente concreto creando el archivo:
  `%LOCALAPPDATA%\VANOVA\updates\updates-config.json` con
  `{"manifestUrl": "https://<nuevo-tunel>/latest.json"}`
  (el updater lee este config antes que el version.json empaquetado).

### 4c. Probar el flujo en ESTA máquina
El VANOVA instalado aquí tiene un config de desarrollo que apunta a
`file:///.../release/latest.local.json` (por eso su status muestra file://).
Para probar contra el túnel real, usar el script de E2E:
`python maios-ux-audit/e2e_live_update.py` (descarga real de 92.8MB + sha256).
NOTA: ese script tiene una constante `INSTALLED` obsoleta (espera que 1.0.6 no
ofrezca update) — actualizarla a la versión actual antes de correr.

## 4d. TEST DE UX POR RELEASE (nuevo desde 1.0.13)

- `maios-ux-audit/ux_release_test.py` — gate automático: [A] integridad del
  empaquetado (versión, módulos nuevos, marcadores del frontend, web/dist
  sincronizado), [B] canal de updates (manifest por túnel, sha256, Range 206,
  detección de update), [C] runtime en vivo (health, version, agents, insights,
  tasks, files, candidates, command-center, updates/status). Exit 0 = listo.
- `docs/UX-CHECKLIST.md` — checklist manual visual (arranque, tareas/insights,
  agentes en vivo, escaneo/candidatos, updates, regresión).
- `maios-ux-audit/e2e_live_update.py` — E2E de update contra el host real
  (constante INSTALLED actualizada a la versión anterior; el paso 5 ahora
  verifica que la versión actual NO ofrece update).

## 5. FIXES QUE YA ESTÁN EN EL CÓDIGO (no romper)

- **1.0.8**: barra de progreso desde el primer segundo (poll antes del POST en
  `downloadUpdate()`), el modal de error ya se puede descartar con "Más tarde"
  (dismiss también en estado `failed`), bug de Range del servidor corregido
  (antes devolvía una tupla y tiraba AttributeError tras cada transferencia),
  timeout de descarga 60s → **300s**.
- **1.0.9**: `download_update()` es **asíncrono** (hilo en segundo plano, devuelve
  al instante con state `downloading`; antes bloqueaba la petición HTTP durante
  toda la descarga — por eso los botones parecían muertos). Guarda de concurrencia
  (doble clic no duplica la descarga). `install_update()` espera al hilo si el
  paquete no está listo.
- **1.0.10**: release de PRUEBA (notas "PRUEBA 1.0.10...") — confirmó el ciclo
  completo en el PC de un cliente real.
- **1.0.11**: VANOVA ya NO descarga modelos locales de Ollama por su cuenta
  (solo cloud `:cloud` por API; locales solo si ya están instalados).
- **1.0.12**: arranque mucho más rápido y asistente arreglado:
  - `_ensure_venv()` se salta la creación de venv + pip install en instalaciones
    empaquetadas (el `python-bundle` ya trae todas las deps y `resolve_python()`
    lo prefiere — el venv nunca se usaba). `verify_dependencies()` ahora es un
    solo probe de subprocess (~1s en vez de ~5).
  - `boot()` en `main.js`: la ventana de setup aparece AL INSTANTE y el runtime
    arranca en segundo plano (antes bloqueaba hasta 150s sin ventana). Para
    instalaciones con setup completo sigue esperando al runtime + cloud.
  - `ui/setup.js`: `api()` con timeout (60s) y check de `res.ok`; la pantalla
    Environment deja de reintentar en bucle infinito — tras ~60s muestra error
    claro con botón **Reintentar**.
  - ⚠️ El instalador 1.0.12 lleva la URL del túnel NUEVA empaquetada. Los
    clientes instalados con URL vieja (1.0.9-1.0.11) necesitan re-apuntarse (4b)
    o reinstalar el 1.0.12.
- **1.0.13**: sincronización de agentes + escaneo selectivo de archivos:
  - Las **rutinas automáticas** de los agentes se registran como **Insights**
    (`insight_store.py` + hook en `task_queue` al completar tareas scheduled);
    las **Tareas** quedan solo para las manuales del usuario. La vista Insights
    del dashboard lista rutinas + prioridades del negocio.
  - **Agentes en vivo**: `list_agents()` expone `currentActivity`, `progress`,
    `nextRoutine`, `lastReport` y `insights`; las tarjetas y el detalle del
    agente muestran qué está haciendo ahora.
  - **Escaneo selectivo** (`file_relevance.py` + `business_scanner` reescrito):
    poda carpetas irrelevantes (música, fotos, descargas, juegos...), puntúa
    carpetas → nombres → contenido, y solo importa archivos claramente de
    empresa; los dudosos van a `fileCandidates` → notificación en el dashboard
    con modal aprobar/rechazar (`/api/files/candidates` + `/api/files/candidates/decide`).
  - **Fix icono reloj gigante**: CSS base `svg{width:1em;height:1em}` en
    `web/dashboard.html` (sincronizado a `web/dist/`).
- **1.0.14**: arquitectura de datos para agentes (una única fuente de verdad):
  - **`agent_data_tools.py`** (nuevo): capa de datos que leen los agentes —
    `get_products`, `get_product_by_sku`, `get_product_prices` (coste+PVD+margen),
    `get_inventory`, `get_sales`/`get_orders`, `get_product_performance`,
    `get_uploaded_files`, `get_imported_dataset`, `data_availability`,
    `render_context_block`. Lee del MISMO `config_store` que el Dashboard
    (`organizedProducts`/`organizedSales`): Dashboard y agentes comparten fuente.
  - **Hermes recibe datos REALES** (SKU+precios+ventas), no solo contadores:
    `build_operational_context` inyecta `render_context_block()` en cada chat.
  - **Tareas con datos**: `_execute_task` añade bloque de datos específico y si
    el modelo dice que falta un dataset que sí existe, resuelve la herramienta
    y reintenta UNA vez con los datos reales (nunca pide re-subir archivos).
  - **Endpoints nuevos**: `GET /api/agent/data/tools`, `GET /api/agent/data/<tool>`,
    `GET /api/tasks/<id>`, `GET /api/tasks/<id>/events` (runtime_security OK).
  - **Detalle de tarea en la UI**: clic en una tarea → modal con payload,
    resultado, error, progreso y línea de eventos, actualizado en vivo (poll 3s).
- **1.0.15**: NO MÁS VENTANAS DE TERMINAL (cliente):
  - El updater ya NO usa `cmd /c start /MIN` (creaba una consola minimizada):
    `update_manager._spawn_updater` (Python) y `main.js spawnUpdaterProcess`
    (Electron) lanzan PowerShell directo con `CREATE_NO_WINDOW` / `windowsHide`.
  - Todos los probes de arranque (`python -c` en `python_runtime.py` y
    `startup_gate.py`, `wmic` en `system_analyzer.py`, `icacls` en
    `config_store.py`, venv/pip en `process_manager.py`) ahora llevan
    `creationflags=CREATE_NO_WINDOW` — antes hacían parpadear una consola.
- **2.0.0 — REBRAND A VANOVA** (nombre universal, listo para comercializar):
  - Todo el branding visible pasa a VANOVA: instalador `VANOVA-Setup-<v>.exe`,
    appId `com.vanova.os`, título, logo, asistente de instalación, web UI,
    manifest `product: VANOVA`, publicador. Los identificadores internos JS
    (`MAIOSUx` etc.) se mantienen (invisibles).
  - **Migración de datos automática**: el arranque migra
    `%LOCALAPPDATA%\VANOVA` → `%LOCALAPPDATA%\VANOVA` sin perder nada
    (productos, ventas, tareas, aprobaciones, credenciales) — en
    `main.js: migrateLegacyData()` y `paths.py: migrate_legacy_data()`.
  - **Guard de producto en el canal**: el updater valida `product == VANOVA`
    en el manifest; el VANOVA viejo NO auto-instala VANOVA (evita bucles).
  - Prueba real en esta máquina: instalación limpia 2.0.0 + datos migrados
    (249 productos, 50 ventas) + gate de UX completo en verde.
  - El instalador deja `%LOCALAPPDATA%\Programs\VANOVA\VANOVA.exe` (el
    VANOVA viejo queda intacto en `Programs\VANOVA` como respaldo).

## 5.5 · ÚLTIMAS RELEASES

- **2.0.16 — Hermes UX y comercio en vivo** (2026-08-15): conversación activa visible; scroll y Enter corregidos; duplicados de actividad y ruido Shopify eliminados; polling coordinado para ventas y estado Shopify. Suite completa: 251 tests correctos, 1 omitido.

- **2.0.15 — Hermes y sincronización operativa** (2026-08-15): progreso/comandos legibles en Hermes; estado unificado y polling para Inicio, Tareas, Actividad, Insights y Agentes; detalle de tarea en vivo; acciones de Insights persistentes; preferencias de tarjetas y tipografía guardadas. Gate UX + suite funcional ejecutados antes de publicar.

- **2.0.14 — Datos fiables y diagnóstico estable** (2026-08-15): tarjetas de Finanzas clicables con desglose contextual; normalización estricta de clientes/pedidos; exclusión de archivos históricos del dashboard antiguo; migración segura de registros ambiguos; elección de carpeta empresarial y análisis profundo del scanner; estado de runtime coordinado sin parpadeo. Release aprobada, pendiente únicamente de publicación en GitHub.


- **2.0.1 — FIX: cloud viejo (MAIOS) secuestrando la UI tras el rebrand**:
  - Síntoma: tras instalar/actualizar a VANOVA, al abrir la app sigue
    apareciendo "MAIOS" arriba a la izquierda y en el título de la ventana.
  - Causa: el cloud de la instalación anterior (MAIOS 1.0.x, o un cloud dev
    viejo) sigue vivo en el puerto 8000. `probe_cloud` solo comprobaba
    `status == ok` → VANOVA lo daba por válido y nunca lo reemplazaba, así que
    servía la UI vieja para siempre.
  - Fix: `port_utils.probe_cloud` ahora valida que el cloud del puerto 8000 sea
    de VANOVA (`app` contiene "vanova") y de la versión actual
    (`maiosVersion == version.json`). Si es un cloud de otra marca/versión → lo
    mata y arranca el suyo. La app se auto-cura al reiniciar.
  - Strings visibles restantes del rebrand limpiados (login-logo, subtítulo,
    Centro de Decisiones, página de setup).
  - Prueba E2E real: 2.0.0 cloud vivo → update 2.0.1 → el runtime reemplazó el
    cloud y la UI sirve VANOVA.
  - **Nota interna (próximo build)**: el guard de VERSIÓN de `probe_cloud` usa
    `from shared.version_info import current_version` (en el binario 2.0.1 el
    import salió como `..shared` y el guard de versión quedaba inerte — el guard
    de MARCA, que resuelve el bug real, sí funcionaba). El build 2.0.2+ ya
    incluye el import corregido; el runtime de este PC ya lo tiene aplicado
    directamente.

- **2.0.2 — FIX CRÍTICO: diagnóstico "runtime no disponible" + botón de reinicio**:
  - Síntoma: en Diagnóstico, "Runtime no disponible", tiempo real/hermes/connector
    en rojo, y el botón «Reiniciar runtime» no hace nada.
  - Causa: el rebrand cambió el health del runtime a
    `service: "vanova-desktop-runtime"`, pero el frontend (`system-status.js`)
    seguía esperando `"maios-desktop-runtime"` → la probe fallaba SIEMPRE → el
    dashboard creía el runtime caído aunque estaba vivo, y el botón no podía
    confirmar la recuperación (su `waitForHealthyRuntime` usaba la misma probe).
  - Fix: `system-status.js` acepta ambos nombres de servicio; el botón
    «Reiniciar runtime» (Electron IPC → kill + respawn) ya confirma la
    recuperación.
  - También: `update-center.js` — todos los strings visibles pasan a VANOVA
    ("VANOVA está actualizado", modal, overlay) y el historial de updates ahora
    muestra etiquetas legibles ("Instalada", "Instalando…") en vez del status
    crudo "installing".
  - Verificación: probe simulada contra runtime real (pasa), tests 227 en verde.

## 6. ADVERTENCIAS / PENDIENTES

- **El túnel depende de esta máquina encendida.** Si se apaga, "Sin conexión" en
  los clientes (nada se rompe, se retoma al volver).
- **El watchdog protege solo el servidor 8137, no cloudflared.** Si cloudflared
  muere, la URL cambia (ver 4b).
- **Incidente 15-ago**: al reiniciar Freebuff (la máquina de trabajo), TODOS los
  procesos en background mueren — incluido cloudflared. El túnel cambió de URL
  (arrive-cream-… → kings-bind-taught-oclc.…). Lección: tras cualquier reinicio
  de esta máquina hay que re-ejecutar `start-update-host.ps1` y re-apuntar a los
  clientes (4b). El watchdog tampoco sobrevive — relanzarlo también.
- **Solución permanente (recomendada)**: registrar `releases.moovingpaper.com`
  (hoy NO existe en el DNS) y servir `release/` en un hosting HTTPS con soporte
  Range (Cloudflare R2 / S3 / nginx). Luego `publish-remote.ps1 -PublicUrl
  https://releases.moovingpaper.com/vanova` y dejar de depender del túnel.
- Los enlaces de tmpfiles caducan (48h con `?expires=172800`).
- No tocar `web/dashboard.html` en paralelo a otros agentes (puede haber cambios
  concurrentes); re-sincronizar a `web/dist/` al editar web.
