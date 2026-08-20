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
| BUG-006 | MEDIUM | Hermes | 3.0.7 | FIXED → READY FOR RETEST | `desktop/runtime/config_store.py`, `desktop/runtime/agent_architect.py` | `test_bug006_update_is_atomic_read_modify_write` + `test_bug006_add_agents_uses_atomic_update` | Lost-update en read-modify-write de `agent_architect.add_agents` (y otros mutadores de listas). Root cause: el API server usa `ThreadingHTTPServer` (cada request en su hilo); `add_agents` hacía `load()` → modificar → `save()` sin serializar el RMW completo (load/save tienen lock individual, pero no el ciclo). Fix: nueva primitiva `config_store.update(mutator)` que ejecuta load→modify→save bajo un SOLO lock; `add_agents` refactorizado para usarla. Regression tests verificados: `update()` es función nueva (falla con AttributeError sin fix), `add_agents` persiste ambos agentes. Suite completa en verde (677 passed). |
| BUG-007 | LOW | Connector | 3.0.7 | FIXED → READY FOR RETEST | `connector/connector.py` | — | Código duplicado en `connector.py:_build_heartbeat_snapshot` (L413 y L415 idénticas: `cfg_path = Path(os.getenv("LOCALAPPDATA","")) / "VANOVA" / "maios.json"`). No es bug funcional (el fallback es redundante), pero es defecto de calidad. Fix: eliminada la línea duplicada. |

_La suite de regresión es acumulativa: cada bug corregido añade un test que toda build futura debe pasar._
