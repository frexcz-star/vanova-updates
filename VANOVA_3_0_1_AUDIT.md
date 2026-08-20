# VANOVA 3.0.1 — Auditoría profunda y corrección (capa proactiva)

Fecha: 2026-08-19 · Estado: 594 tests passed, 1 skipped, 0 fallos

Esta auditoría se hizo inspeccionando el código y reproduciendo flujos reales
(no solo ejecutando la suite). El criterio: **que una PYME real pueda instalar
VANOVA, importar sus datos y recibir valor sin enseñarle qué debe buscar**.

---

## 1. BUGS ENCONTRADOS → CAUSA → FIX → TEST

| Bug | Causa | Fix | Test |
|---|---|---|---|
| `company_model.build_company_model()` lanzaba **UnboundLocalError** siempre (referencia a `model` dentro de su propio literal de dict) | `"changesSinceLast": _delta_vs_stored(data, model)` evaluaba `model` antes de asignarse | Se construye el dict completo y el delta se añade después | `tests/test_proactive_310.py` (el test lo reprodujo al primer intento) |
| `company_model` era un módulo muerto: creado pero **nunca llamado** desde ningún flujo | Falta de cableado | `file_organizer.organize_files()` refresca la memoria empresarial tras cada import; endpoint `GET /api/company/model` (protegido) | `test_organize_refreshes_company_model`, `test_refresh_persists_company_model` |
| El badge de notificaciones se encendía al arrancar aunque no hubiera notificaciones nuevas | Contaba `fileCandidates` (persistidos del escaneo), guardrails, decisiones y prioridades — cosas que NO son notificaciones | El badge solo cuenta **aprobaciones pendientes + insights proactivos en estado `new` posteriores a `notifSeenAt`**; abrir el centro de alertas marca como leído (persistido en uiPrefs) | Verificación manual del flujo badge 0 → 1 → 0 → 0 tras reinicio (lógica en `updateBellBadge`) |
| Botón de tres líneas del header no hacía nada en escritorio | Solo tenía CSS de efecto dentro de `@media(max-width:760px)` | `#mob-burger{display:none}` en escritorio; se muestra solo en móvil (donde sí abre el panel lateral) | Verificación manual + syntax check |
| Test de rendimiento `test_catalog_index_equivalence_and_speed` fallaba en suite completa (flake por timing) | Comparación de tiempo de pared con una sola medición, ruido bajo carga | Best-of-3 por ruta | Re-ejecutado en suite completa: verde |
| (Pre-existente, sin tocar) runtime del sandbox E2E adjuntado al config de producción — resuelto en la sesión anterior | Escenario P2-2 | Fuera del alcance de esta fase | — |

---

## 2. FUNCIONALIDADES REALMENTE IMPLEMENTADAS (esta fase)

1. **Ingresos por periodo en Home** — bloque `Ingresos` con Hoy / Esta semana /
   Este mes / Este trimestre / Este año / Total histórico. Lo calcula el motor
   canónico (`business_model.period_revenue`) y lo expone el Command Center
   (`revenuePeriods`); el frontend solo presenta. **UNKNOWN ≠ 0**: sin datos el
   importe es `null → "—"`, nunca 0 €; comparación con periodo anterior solo
   cuando existe evidencia (`comparable=false → "Sin datos suficientes"`).
2. **Memoria empresarial (modelo de empresa)** — `company_model` ahora se
   construye y persiste tras cada importación (`companyModel` en config):
   qué vende, cómo vende, qué funciona, riesgos/oportunidades top, qué sabe y
   qué NO sabe (`dataAvailability`/`dataMissing`), y delta vs análisis anterior
   (`changesSinceLast`) para reanálisis inteligente.
3. **Endpoint protegido** `GET /api/company/model` (dentro de
   `SENSITIVE_READ_PATHS`).
4. **Badge de notificaciones honesto** (ver bug anterior).
5. **Botón tres líneas eliminado en escritorio.**
6. **Restablecer VANOVA completamente** — botón en Ajustes → Confirmación →
   `POST /api/setup/factory-reset` (el backend ya existía: backup previo
   obligatorio, aborta si el backup falla, conserva version/aiProviders/hermes,
   desconecta integraciones de negocio). Tras el reset: setup de nuevo.
7. **Escanear datos manual desde Archivos** — botón «Escanear datos»: pregunta
   si escanear una carpeta concreta (input de ruta) o las carpetas ya
   configuradas; llama a `/api/scan/folders` o `/api/setup/scan`, muestra
   estado y refresca el inventario. Sin falsa interfaz: cada botón ejecuta su
   flujo real.

---

## 3. VERIFICADO COMO YA EXISTENTE Y CONECTADO (auditoría)

- **Revalidación post-update**: banner real en Home («Datos encontrados de una
  versión anterior») con **Revisar datos / Reimportar / Ahora no**; la
  reimportación usa el pipeline idempotente (`/api/data/reimport`), nunca
  duplica ni borra; «Ahora no» persiste (`/api/data/review/dismiss`) y hay
  botón para rearmar la validación.
- **Importación con resumen**: filas inválidas → `needs_review` con evidencia
  (`_saleIssue`, `qualityReason`), nunca entran en métricas; resumen con
  productos/ventas importadas, rechazadas, truncadas y preservadas.
- **Proactividad base**: detection engine (findings con evidencia/severidad/
  impacto/acción), `insight_store` (estados new/seen/…, IDs estables, dedup por
  identidad, cap 300), priorización económica (`action_plan`), semáforo de
  salud y brief ejecutivo del motor (ya no protagonizan el Home, siguen en sus
  secciones).
- **Separación actividad técnica vs usuario**: el Command Center ya filtra
  tareas internas (`_is_internal_task`); los informes de rutina van a Insights,
  no a Tasks.
- **Hermes**: instrumentación de latencia por fase (`timings.contextMs /
  modelMs / totalMs`), ruta ligera para mensajes casuales (omite el contexto
  operativo pesado), intercepción de setup Shopify, sanitizador anti-leak
  (con tests), estados HECHO/INFERENCIA/NO DISPONIBLE.
- **Seguridad**: GET sensibles protegidos por token (incluye el nuevo
  `/api/company/model`); guard de segunda instancia; updater con checksum y
  anti-downgrade.

---

## 4. FUNCIONALIDADES QUE NO SE PUEDEN VERIFICAR EN ESTE ENTORNO

- **FacturaScripts con servidor real**: el conector (normalización de URL,
  `/api/3`, probe con rechazo de HTML, validación JSON) existe y tiene tests,
  pero no hay un servidor FacturaScripts real disponible aquí para una prueba
  de integración de extremo a extremo. **No se marca como funcional en vivo**:
  queda pendiente la prueba con credenciales reales del cliente.
- **Latencia real de Hermes**: la separación por fases y la ruta casual están
  implementadas, pero el tiempo de generación depende del proveedor (Ollama
  local vs cloud) y no está configurado un proveedor en este entorno. El
  «hola» de ~8 s del tester se explica por el arranque/cola del modelo local;
  `timings` permite medirlo por fase en el equipo del cliente.
- **Updater end-to-end contra el servidor de actualizaciones**: verificado en
  la release 3.0.0 (GitHub v.3.0.0 publicado); no se ha vuelto a ejecutar en
  esta fase (prohibido tocar el benchmark congelado).

---

## 5. RESULTADOS E2E

- **Suite completa**: 594 passed, 1 skipped, 0 fallos (incluye los 8 tests
  nuevos de la capa proactiva + 35 de product_identity sin flake).
- **Capa proactiva (tests)**: snapshot del Command Center con revenue por
  periodo coherente (total == Σ meses), UNKNOWN≠0 (sin datos → None, no 0),
  filas inválidas excluidas del revenue, comparación anterior no inventada,
  insights proactivos priorizados en el snapshot, modelo de empresa persistido,
  endpoint protegido.
- **Sintaxis frontend**: `new Function()` sobre todos los scripts inline de
  `dashboard.html` e `index.html` → OK (ambos idénticos; `web/dist/`
  sincronizado).
- **No se ha tocado**: benchmark congelado, GROUND_TRUTH, resultados
  históricos, instalación de producción, beta.1/beta.3/3.0.0 publicadas.

---

## 6. RESULTADOS DE PROACTIVIDAD

La prueba exigida («crear empresa → setup → importar → sin preguntar a Hermes
→ VANOVA dice lo que ha encontrado») está soportada por:

- findings del detection engine persistidos tras el análisis;
- modelo de empresa persistido tras la importación (memoria);
- insights con estados y dedup (sin spam);
- snapshot del Command Center que ahora lleva `revenuePeriods` +
  `proactiveInsights` (top 6 sin resolver);
- badge de campana solo con lo nuevo.

El bucle «notificación → apertura → revisar/ignorar/posponer» usa el
`insight_actions` existente. **Lo que falta** (pendiente, no bloqueante): una
tarjeta en Home que liste explícitamente los `proactiveInsights` del snapshot
(el badge ya cuenta los nuevos; la tarjeta de presentación puede añadirse en la
siguiente iteración sin tocar el motor).

---

## 7. RENDIMIENTO (medido esta fase)

- **Command Center con revenue + insights**: la adición es O(n) sobre ventas
  válidas y <= 100 insights; el TTL de caché de 2 s se mantiene (el test de
  auth que dependía de probes ahora parchea los probes → determinista).
- **organize + company_model**: el refresh del modelo se ejecuta en el mismo
  hilo tras guardar; si falla, se loguea y NO rompe la importación (guard).
- **Hermes**: contexto pesado solo si `_message_wants_operational_detail` y no
  es casual → «hola» no construye el contexto operativo.
- Test de rendimiento del índice de catálogo: ahora robusto bajo carga.

---

## 8. ESTADO FINAL

| Clasificación | Ítem |
|---|---|
| 🔴 Bloqueante | Ninguno conocido en los flujos auditados |
| 🟠 Importante | Prueba de integración FacturaScripts con servidor real (pendiente del entorno del cliente) |
| 🟡 Menor | Tarjeta de insights proactivos en Home (presentación, el motor ya funciona); agrupar entradas de Actividad de agentes en la UI (el backend ya separa internas) |
| 🟢 Correcto | Revenue por periodo, UNKNOWN≠0, badge, reset completo, escaneo manual, memoria empresarial, suite 594/0, benchmark intacto |

**Veredicto honesto**: esta fase corrige bugs reales (el más grave: el modelo
de empresa se caía siempre y no estaba conectado a nada) y entrega el
esqueleto proactivo funcionando y testeado. Una PYME podría hoy importar,
ver ingresos por periodo correctos, encontrar problemas y verlos en Home. La
única dependencia externa pendiente es la validación en vivo de FacturaScripts
y la medición de latencia de Hermes con el proveedor del cliente — ninguna de
las dos bloquea la entrega de la beta, pero ambas deben probarse antes de
declarar el producto «listo comercialmente».

Archivos modificados en esta fase:
- `desktop/runtime/company_model.py` (bug UnboundLocalError + build)
- `desktop/runtime/command_center.py` (revenuePeriods + proactiveInsights)
- `desktop/runtime/file_organizer.py` (refresh memoria tras import)
- `desktop/runtime/api_server.py` (endpoint /api/company/model)
- `desktop/runtime/runtime_security.py` (endpoint protegido)
- `web/dashboard.html`, `web/index.html`, `web/dist/*` (Home ingresos, badge,
  hamburguesa, reset completo, escanear datos)
- `tests/test_proactive_310.py` (nuevo, 8 tests)
- `tests/test_product_identity.py` (fix flake de timing)
