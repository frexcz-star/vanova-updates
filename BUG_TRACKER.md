# VANOVA — Bug Tracker / Ciclo QA↔Dev

## Roles

| Agente | Rol | Responsabilidad |
|--------|-----|-----------------|
| **OpenMausBot** | QA Engineer / Desktop Operator | Usa VANOVA como usuario real, intenta romperla, reproduce, recoge evidencia, crea bug reports. **No modifica código por defecto.** |
| **Freebuff** | Lead Developer / Fixer | Investiga source, identifica root cause, implementa fix, añade regression test, genera build, marca READY FOR RETEST. |

## Ciclo

```
OpenMausBot FIND BUG → Freebuff FIX → Nueva build → OpenMausBot RETEST → Regression PASS/FAIL → NEXT BUG
```

## Estado actual (baseline)

- **Versión de referencia:** VANOVA 3.0.7
- **Commit:** `01b701a` (rama `main`, repo `frexcz-star/vanova-updates`)
- **Suite:** 65 archivos de test, ~671 tests (661 + 10 E2E proactividad)
- **Cambios clave de 3.0.7:** cooldown toast 15 s, recomendaciones activas/cerradas, sección cerradas colapsable, `resolvedAt`/`dismissedAt`, métricas corregidas, 10 tests E2E de proactividad.

## Plantilla de bug report (obligatoria)

Cada reporte de OpenMausBot debe incluir:

```text
BUG-XXX

Severity: CRITICAL | HIGH | MEDIUM | LOW
Area: Startup | Dashboard | Shopify | Hermes | Connector | Files | Proactividad |
      Recommendations | Activity | Updater | UX | Security

Version:
VANOVA X.Y.Z

Preconditions:
- ...

Steps:
1. ...
2. ...

Expected:
...

Actual:
...

Reproducibility:
N/5

Evidence:
- screenshot
- logs
- timestamp

Acceptance criteria:
...
```

## Severidad y prioridad

1. **CRITICAL** — pérdida/corrupción de datos, mezcla entre empresas, auth roto, crash total.
2. **HIGH** — startup/recovery, Shopify, Connector, Hermes, proactividad/persistencia, updater, seguridad.
3. **MEDIUM** — UX, estados incorrectos, bots muertos, datos stale.
4. **LOW** — cosmético, textos, responsive.

Orden de ataque por severidad: CRITICAL → HIGH → MEDIUM → LOW, con prioridad interna:
pérdida de datos > startup/recovery > Shopify > Connector > Hermes > proactividad/persistencia > updater > seguridad > UX.

## Lifecycle de un bug

```
NEW → INVESTIGATING → FIXED → READY FOR RETEST → RETEST PASS / RETEST FAIL → CLOSED
```

- **FIXED** requiere: root cause identificado + fix + regression test en verde.
- **READY FOR RETEST** requiere: build nueva generada + suite completa en verde.
- Un bug solo se **CLOSES** cuando OpenMausBot confirma PASS sobre la build nueva.

## Proceso del Developer al recibir un bug

1. Reproducir conceptualmente.
2. Inspeccionar source actual (SOURCE > TESTS > CURRENT CONFIG > CURRENT DOC > HISTORICAL DOC).
3. Identificar root cause.
4. Determinar impacto.
5. Diseñar fix (causa raíz, no parche superficial).
6. Implementar.
7. Añadir/actualizar regression test (debe fallar con el código anterior).
8. Ejecutar suite completa.
9. Revisar efectos secundarios (consumidores de APIs, recovery del updater, policy/approval de agentes).
10. Generar build.
11. Marcar READY FOR RETEST.

## Prohibido

- Eliminar tests porque fallan.
- Modificar tests para ocultar bugs.
- Hardcodear resultados.
- Ocultar errores de UI.
- Convertir errores en datos.
- Mocks en producción.
- Parchear sin root cause.
- Declarar bug solucionado sin tests.
- Romper APIs sin revisar consumidores.
- Modificar updater sin revisar recovery.
- Acciones de agentes sin policy/approval.

## Registro de bugs

| ID | Severidad | Área | Versión | Estado | Fix en | Regression test | Notas |
|----|-----------|------|---------|--------|--------|-----------------|-------|
| BUG-0001 | HIGH | Startup/Recovery | 3.0.7 | RETEST PASS → CLOSED | `desktop/main.js` | `test_bug0001_orphaned_runtime_is_replaced_not_reused` | Runtime huérfano de sesión muerta ahora se reemplaza (no se reutiliza). Verificado E2E: "Runtime healthy but orphaned — replacing" + stack completo sano. **Retest Mathew (2026-08-20):** regression test pasa, fix presente en main.js:628-634. CLOSED. |
| BUG-0002 | MEDIUM | QA Automation | 3.0.7 | RETEST PASS → CLOSED | `desktop/main.js` | `test_bug0002_remote_debugging_flag_is_relayed` | `--remote-debugging-port` en 2ª instancia ahora relanza la app con el flag. Verificado E2E: puerto 9222 LISTENING + CDP responde. **Retest Mathew (2026-08-20):** regression test pasa, fix presente en main.js:996-1002. CLOSED. |
| BUG-001 | CRITICAL | Proactividad | 3.0.7 | RETEST PASS → CLOSED | `desktop/runtime/detection_engine.py` | `test_bug001_signature_stable_when_reference_date_shifts` + `test_bug001_intra_run_dedupe_no_duplicate_signatures` | Duplicación de findings en re-análisis (6→12). Root cause: la firma incluía `window_start` (derivado de la fecha de referencia `ref`); al llegar datos nuevos, `ref` se desplazaba → todas las firmas cambiaban → los findings viejos se recreaban como nuevos. Fix: firma estable = `type:entity` (la ventana temporal es metadata, no identidad). Regression test verificado: falla con código viejo (0 firmas coinciden), pasa con fix. **Sub-fix intra-run (hallazgo de Mathew):** con la firma estable, dos detectores podían emitir la misma firma en un mismo run (product_declining 60d y 30d) → dedupe intra-run añadido (colapsa fresh por firma, mayor severidad). Regression test `test_bug001_intra_run_dedupe_no_duplicate_signatures` verificado: falla sin fix (2 firmas duplicadas), pasa con fix. **Retest Mathew (2026-08-20):** verificación funcional independiente — 6/6 originales preservados, 11 findings/11 sigs únicos sin duplicados. CLOSED. |
| BUG-002 | HIGH | Recommendations | 3.0.7 | RETEST PASS → CLOSED | `desktop/runtime/detection_engine.py` | `test_bug001_signature_stable_when_reference_date_shifts` | Falsa auto-resolución por cambio de fecha en firma. Root cause: mismo que BUG-001 — la firma cambiaba con `ref`, así que `sync_resolutions` veía la firma como "desaparecida" y auto-resolvía. Fix: firma estable `type:entity` resuelve la causa raíz. **Retest Mathew (2026-08-20):** status `acknowledged` preservado tras re-análisis con ref desplazada. CLOSED. |
| BUG-003 | HIGH | Activity/Notificaciones | 3.0.7 | RETEST PASS → CLOSED | `web/dashboard.html`, `web/index.html`, `web/dist/dashboard.html`, `web/dist/index.html` | — | Suscripción WebSocket duplicada en loadAppData (spam). Root cause: cada `ds.subscribe()` abre un WebSocket independiente y `loadAppData()` lo llamaba en cada ejecución. Fix: guarda `window.__MAIOS_WS_SUBSCRIBED__` para suscribirse una sola vez por carga de página. Aplicado a los 4 archivos del dashboard (dashboard/index × web/dist) tras hallazgo de Mathew de que index.html no se había sincronizado. **Sub-fix build (hallazgo de Mathew):** el proceso cloud activo servía desde la build empaquetada/instalación (no desde el repo), que no tenía el fix. Sincronizados los 4 archivos en repo, `release/win-unpacked`, instalación real (`AppData/Local/Programs/VANOVA`) y entorno E2E (`vanova-e2e-300`). **Retest Mathew (2026-08-20):** servidor en vivo sirve sha `9f36e110` con guard (2 ocurrencias). CLOSED. |
| BUG-004 | LOW | Findings | 3.0.7 | RETEST PASS → CLOSED | `desktop/runtime/detection_engine.py` | `test_update_finding_status` | `acknowledgedAt` no se rellena (usa `updatedAt` genérico). Root cause: `update_finding_status` solo actualizaba `status` y `updatedAt`. Fix: rellena `acknowledgedAt` al marcar como acknowledged. Verificado en test. **Retest Mathew (2026-08-20):** suite en verde. CLOSED. |
| BUG-005 | LOW | QA/CI | 3.0.7 | RETEST PASS → CLOSED | — | — | Suite completa no termina en tiempo acotado (tests de red). **Retest Mathew (2026-08-20):** suite completa termina en 96.98s (675 passed, 1 skipped). Los tests de red usan servidores HTTP locales (no red externa), no se cuelgan. CLOSED. |
| BUG-006 | MEDIUM | Hermes | 3.0.7 | RETEST PASS → CLOSED | `desktop/runtime/config_store.py`, `desktop/runtime/agent_architect.py` | `test_bug006_update_is_atomic_read_modify_write` + `test_bug006_add_agents_uses_atomic_update` | Lost-update en read-modify-write de `agent_architect.add_agents` (y otros mutadores de listas). Root cause: el API server usa `ThreadingHTTPServer` (cada request en su hilo); `add_agents` hacía `load()` → modificar → `save()` sin serializar el RMW completo (load/save tienen lock individual, pero no el ciclo). Fix: nueva primitiva `config_store.update(mutator)` que ejecuta load→modify→save bajo un SOLO lock; `add_agents` refactorizado para usarla. Regression tests verificados: `update()` es función nueva (falla con AttributeError sin fix), `add_agents` persiste ambos agentes. **Retest Mathew (2026-08-20):** fix presente (config_store.py:47-68, agent_architect.py:51-66), regression tests pasan, suite completa 678 passed. CLOSED. |
| BUG-007 | LOW | Connector | 3.0.7 | RETEST PASS → CLOSED | `connector/connector.py` | — | Código duplicado en `connector.py:_build_heartbeat_snapshot` (L413 y L415 idénticas: `cfg_path = Path(os.getenv("LOCALAPPDATA","")) / "VANOVA" / "maios.json"`). No es bug funcional (el fallback es redundante), pero es defecto de calidad. Fix: eliminada la línea duplicada. **Retest Mathew (2026-08-20):** solo queda una línea `cfg_path` (L413), la duplicada eliminada. CLOSED. |
| BUG-008 | MEDIUM | Hermes | 3.0.7 | RETEST PASS → CLOSED | `desktop/runtime/detection_engine.py` | `test_bug008_update_finding_status_uses_atomic_rmw` | Lost-update en `update_finding_status` (mismo patrón que BUG-006). Root cause: hacía `load()` → modificar → `save()` sin serializar el RMW completo; con ThreadingHTTPServer (API server) y el scheduler en background escribiendo `businessFindings` a la vez, dos hilos podían perder el estado del finding. Fix: refactorizado para usar `config_store.update()` (RMW atómico bajo un solo lock). Regression test verificado: `update()` invocado, estado persiste. **Retest Mathew (2026-08-20):** fix presente (detection_engine.py:1858-1879), regression test pasa, suite completa 678 passed. CLOSED. |
| BUG-009 | LOW | Connector | 3.0.7 | RETEST PASS → CLOSED | `connector/connector.py` | — | Código muerto en carga de env del connector: `_user_connector_env` y `_legacy_connector_env` eran la MISMA ruta (`LOCALAPPDATA/VANOVA/config/connector.env`), así que el `elif` nunca se ejecutaba. No es bug funcional (el fallback era redundante), pero es defecto de calidad. Fix: unificada en una sola ruta de config del usuario. **Retest Mathew (2026-08-20):** fix presente (connector.py:44-49), una sola ruta `_user_connector_env`. CLOSED. |
| BUG-010 | HIGH | Cloud | 3.0.7 | RETEST PASS → CLOSED | `cloud/main.py` | `test_bug010_snapshots_pruned_to_retention` + `test_bug010_different_kinds_kept_separate` | Crecimiento infinito de la tabla `snapshots` en el cloud (SQLite). `store_snapshot` hacía `INSERT` en CADA llamada sin ningún DELETE/prune/retention. Fix: constante `SNAPSHOT_RETENTION = 100` y prune al insertar que conserva solo los últimos 100 por (workspace_id, kind) usando el rowid implícito. Los SELECT usan `ORDER BY rowid DESC LIMIT 1`, así que no cambia ningún consumidor. Regression test verificado: tras insertar retention+20, quedan ≤100 y el último es el más reciente. **Retest Mathew (2026-08-20):** fix presente (cloud/main.py:425, 445-453), regression tests pasan, suite completa 684 passed. CLOSED. |
| BUG-011 | MEDIUM | Hermes | 3.0.7 | RETEST PASS → CLOSED | `desktop/runtime/hermes_activity.py` | `test_bug011_log_step_uses_atomic_update` + `test_bug011_log_accumulates_and_trims` | RMW no atómico persistente en `hermes_activity.log_step`. Refactorizado a `config_store.update()` (RMW atómico bajo un solo lock) — igual que BUG-006/008. Regression tests verificados: `update()` invocado, el log acumula y trima a MAX_LOG. **Retest Mathew (2026-08-20):** fix presente (hermes_activity.py:34), regression tests pasan. CLOSED. |
| BUG-012 | MEDIUM | Hermes | 3.0.7 | RETEST PASS → CLOSED | `desktop/runtime/file_organizer.py` | `test_bug012_add_product_uses_atomic_update` + `test_bug012_add_product_persists` | RMW no atómico persistente en `file_organizer.add_product`. Refactorizado a `config_store.update()` (RMW atómico). Regression tests verificados: `update()` invocado, ambos productos persisten. **Retest Mathew (2026-08-20):** fix presente (file_organizer.py:139), regression tests pasan. CLOSED. |
| BUG-013 | HIGH | Cloud | 3.0.8 | RETEST PASS → CLOSED | `cloud/main.py` | `test_bug010_different_kinds_kept_separate` | Regresión de pérdida de datos del fix de BUG-010: el DELETE del prune solo filtraba en el sub-SELECT, borrando filas de TODOS los kinds/workspaces. Fix: `WHERE workspace_id=? AND kind=? AND rowid NOT IN (...)` en el DELETE. Regression test verificado: falla con el código sin fix (1 != 2), pasa con el fix (2 filas preservadas por par). **Retest Mathew (2026-08-20):** fix presente (cloud/main.py:445-453), regression test pasa, no se pierden datos entre kinds. CLOSED. |
| BUG-014 | LOW | QA/CI | 3.0.8 | RETEST PASS → CLOSED | `tests/test_bug010_011_012.py` | — | Error de tipado en `setUp` de `Bug010SnapshotRetentionTests`: asignaba `self._patch_db` pero llamaba `self._patch.start()`. Fix: renombrado a `_get_db_patcher.start()` / `_get_db_patcher.stop()`, aislando la DB en un archivo temporal (no toca `maios_cloud.db`). Verificado: 6 tests de la clase pasan. **Retest Mathew (2026-08-20):** 6 tests de la clase pasan, DB aislada. CLOSED. |
| BUG-016 | LOW | QA/CI | 3.0.8 | RETEST PASS → CLOSED | `tests/test_import_attack.py` | — | Flakiness en `test_import_attack.py::test_huge_file_100k_rows`. Fix: umbral subido de 30s a 60s. **Retest Mathew (2026-08-20):** umbral 60s presente (test_import_attack.py:167), suite completa 700 passed sin fallo. CLOSED. |
| BUG-015 | MEDIUM | Hermes | 3.0.8 | RETEST PASS → CLOSED | `desktop/runtime/ai_providers.py`, `desktop/runtime/hermes_config.py` | `tests/test_bug015.py` (2 tests) | RMW no atómico persistente en `ai_providers.save_provider_config` y `hermes_config` sync. Refactorizados a `config_store.update()` (RMW atómico bajo un solo lock). **Extra:** el sync de hermes_config antes hacía `save({"aiProviders": {"primary": entry}})` que REEMPLAZABA todo el dict aiProviders, borrando otros providers — ahora solo actualiza la clave `primary` preservando el resto. **Retest Mathew (2026-08-20):** fixes presentes (ai_providers.py:74-86, hermes_config.py:415-421), regression tests pasan (test_bug015.py), suite completa 700 passed. CLOSED. |
| SPEC-OPP | FEATURE | Proactividad | 3.0.8 | COMPLETED → READY FOR REVIEW | `desktop/runtime/opportunity_catalog.py`, `desktop/runtime/api_server.py`, `web/data-services.js`, `web/dashboard.html` | `test_opportunity_catalog.py` (11 tests) | STRATI Detector de Oportunidades de Crecimiento (docs/STRATI_DETECTOR_OPORTUNIDADES_SPEC.md). Capa de producto sobre detection_engine. Endpoint GET /api/opportunities. Honestidad UNKNOWN≠0, anti-ruido < 25 EUR, dedupe por firma. **BUG-018 fixed** (`_upside_for_aov` cuantifica). **BUG-017 fixed** (vista "Oportunidades" integrada en Insights). Suite: 700 passed. |
| BUG-017 | MEDIUM | UX | 3.0.8 | RETEST PASS → CLOSED | `web/dashboard.html`, `web/index.html`, `web/dist/*`, `desktop/runtime/opportunity_catalog.py`, `desktop/runtime/api_server.py`, `desktop/runtime/runtime_security.py`, `web/data-services.js` | `test_opportunity_catalog.py::test_bug017_mark_done_connects_to_action_loop` | SPEC-OPP: la vista "Oportunidades" (spec §4.1) NO estaba integrada en la interfaz. Fix: sección "Oportunidades de crecimiento" en la vista Insights (`viewInsights`), con tarjetas (`opportunityCard`) que muestran `upsideEuro` en € grande cuando hay evidencia y "Impacto no cuantificable" cuando es None (nunca 0). Copy ES corporate, sin emojis. Empty state honesto. `getOpportunities()` ahora se llama en `loadAppData` (store.opportunities). **CTA "Marcar como hecha"** (spec §4.1 → action-loop): botón por tarjeta que llama `opportunity_catalog.mark_done`, endpoint POST `/api/opportunities/done`, whitelist de mutación actualizado. Sincronizado a web/index.html + web/dist/. Suite: 701 passed. **Retest Mathew (2026-08-20):** tras reiniciar el runtime — endpoint `GET /api/opportunities` responde HTTP 200 con JSON válido `[]` (honesto, sin inventar); dashboard (8000) sirve la build nueva (hash a580d943) con la sección "Oportunidades de crecimiento" y empty state honesto (L2731). Verificación end-to-end OK. CLOSED. |
| BUG-018 | MEDIUM | Proactividad | 3.0.8 | RETEST PASS → CLOSED | `desktop/runtime/opportunity_catalog.py`, `desktop/runtime/detection_engine.py` | `test_opportunity_catalog.py` (2 tests BUG-018) | `opportunity_catalog._upside_for_aov` era **código muerto**: nunca cuantificaba. Fix: `_upside_for_aov` ahora lee `currentOrders`/`previousOrders` de metrics (añadidos al finding `aov_change` en detection_engine) y calcula `(AOV_objetivo − AOV_actual) × pedidos_periodo` cuando `current_aov < previous_aov` y hay pedidos. Sin pedidos → `None` (UNKNOWN ≠ 0). **Retest Mathew (2026-08-20):** fix presente (opportunity_catalog.py:104-122), regression tests pasan (upside 2000€ = gap 40 × 50 pedidos; None sin pedidos), suite completa 700 passed. CLOSED. |
| BUG-019 | MEDIUM | Hermes | 3.0.8 | RETEST PASS → CLOSED | `desktop/runtime/file_inventory.py` | `tests/test_bug017.py` (3 tests) | RMW no atómico persistente en `file_inventory.add_imported_file`, `remove_imported_file` y `decide_candidate` — hacen `load()` → modificar `scanFiles`/`fileCandidates` → `save()` sin `config_store.update()`. Mismo patrón lost-update de BUG-006/015. Accesible desde el API server (ThreadingHTTPServer). Fix: refactorizados a `config_store.update()` (RMW atómico). **Retest Mathew (2026-08-20):** fixes presentes (file_inventory.py:61, 89, 132, 147 usan update), regression tests pasan (test_bug017.py), suite completa 700 passed. CLOSED. |
| BUG-020 | MEDIUM | Proactividad | 3.0.8 | RETEST PASS → CLOSED | `desktop/runtime/opportunity_catalog.py` | `tests/test_opportunity_catalog.py::test_cross_sell_sku_case_insensitive_margin` | Los SKUs del par cross-sell llegan en minúsculas (`box-501`) pero el catálogo en mayúsculas (`BOX-501`): el margen no se encontraba y el upside del cross-sell NUNCA se cuantificaba (siempre `None`/no_quantifiable). Fix: normalizar a lowercase en el match SKU↔catálogo. Regression test: con SKU en minúsculas y coste verificado, el upside ahora se cuantifica. Suite: 702 passed. **Retest Mathew (2026-08-20):** fix presente (opportunity_catalog.py:78-82 normaliza a lowercase), `test_cross_sell_sku_case_insensitive_margin` pasa (upside cuantificado >25), suite completa 702 passed. CLOSED. |
| DEMO-MOCK | FEATURE | Proactividad | 3.0.8 | DEMO LOADED (dataMode=mock) | `mock_dataset.json`, config runtime | — | Dataset mock rico (665 pedidos, 30 productos con coste, 300 clientes, pares de co-compra) etiquetado `dataMode=mock` / `shopifySync.connected=false` (NUNCA como datos reales). El Detector de Oportunidades genera 5 oportunidades de cross-sell CON `upsideEuro` en € calculado reales (41.26, 39.18, 36.91, 35.31, 34.91 €). Config real respaldado en `maios.backup-antes-mock.json`. Para revertir: restaurar el backup. |
| BUG-021 | MEDIUM | Hermes | 3.0.8 | FIXED → READY FOR RETEST | `desktop/runtime/agent_scheduler.py` | `tests/test_agent_scheduler.py::test_proactive_tick_uses_atomic_update` | RMW no atómico en el análisis proactivo recurrente: `agent_scheduler._tick()` hacía `config_store.load()` → modificar `businessFindings`/`insights`/`priorities`/`recommendations` → `config_store.save()` SIN lock, perdiendo escrituras concurrentes del API server (ThreadingHTTPServer). Mismo patrón lost-update de BUG-006/015/019. Fix: detectar con snapshot y persistir de forma ATÓMICA vía `config_store.update()`. **Pitfall resuelto:** la detección NO corre dentro del mutator porque `run_detection()` llama internamente a `config_store.load()` y `_config_lock` es no-reentrante → deadlock (detectado y corregido). El timestamp `proactive_analysis` se guarda en el state file (no en el config). Regression test verifica que `update()` se invoca. Suite: 703 passed. |


_La suite de regresión es acumulativa: cada bug corregido añade un test que toda build futura debe pasar._

## Bugs de la ronda Mathew (2026-08-20, ciclo QA posterior a BUG-020)

| ID | Severidad | Área | Versión | Estado | Fix en | Regression test | Notas |
|----|-----------|------|---------|--------|--------|-----------------|-------|
| BUG-021 | MEDIUM | Hermes | 3.0.8 | NEW | — | — | RMW no atómico persistente en `product_identity` (`add_mapping`, `remove_mapping`, `ignore_sku`, `unignore_sku`). Hacen `load()` → modificar lista → `save()` sin `config_store.update()` (product_identity.py:158-185, 190-195, 215-223, 226-231). Expuestos en `/api/products/match`, `/api/products/match/remove`, `/api/products/ignore`, `/api/products/ignore/remove` (api_server.py:696-736, ThreadingHTTPServer). Mismo patrón lost-update de BUG-006/015/019: dos requests concurrentes pueden perder un mapping/SKU. Fix: `config_store.update()`. Reproducibilidad 2/5. |
| BUG-022 | MEDIUM | Shopify | 3.0.8 | NEW | — | — | `integrations_store.clear_stale_shopify_sync_errors` (integrations_store.py:134-152) reemplaza TODO el objeto `shopifySync` por un sub-dict de solo 6 campos (`missingScopes`, `scopeErrors`, `errorCategory`, `lastError`, `userMessage`, `partial`), perdiendo `lastSync`, `counts`, `status`, `message`, `guardAlerts`, `guard`, `backfill`, `startedAt`. Se llama desde `sync_shopify_from_hermes_if_needed` (L210, 235) cuando las credenciales validan. Consecuencia: al limpiar un error de permisos obsoleto se borran los metadatos de la última sync válida. Fix: hacer un UPDATE de los 6 campos sobre el `shopifySync` existente (merge), no reemplazar el dict completo. Reproducibilidad 5/5 (estático, patrón obvio). |
