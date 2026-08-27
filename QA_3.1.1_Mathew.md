# VANOVA 3.1.1 — QA Round (Mathew) — 2026-08-21

Versión probada: VANOVA 3.1.1
Commit repo: 212fd61 (rama main)
Suite: 738 passed, 1 skipped, 31 subtests, 109.35 s — VERDE (sin fallos)

---

## TAREA 1 — Suite completa (pytest)

Comando: `.venv/Scripts/python.exe -m pytest -q`
Resultado: **738 passed, 1 skipped, 31 subtests passed in 109.35 s** — ningún fallo.
Warnings (no bloqueantes): deprecación de `@app.on_event` en FastAPI (cloud/main.py:561) y
deprecación de `httpx`+`starlette.testclient` (test_ws_auth.py:18). Solo de deprecación, sin impacto funcional.

---

## TAREA 3 — Sincronización build en vivo vs repo + fixes BUG-031/032/033/034

**Resultado: código sincronizado (sin desync de BUG-003/025). Los 4 fixes están presentes en repo,
release/win-unpacked y la instalación E2E real. PERO la instalación REAL (Program Files) tiene
`version.json` STALE → NUEVO BUG (BUG-035).**

Checksums verificados repo == release/win-unpacked == E2E (`vanova-e2e-300`):
- `web/data-services.js` = 226e6d8904… (idéntico en repo, win-unpacked, E2E)
- `web/dashboard.html` = f1ad6b207… (idéntico)
- `desktop/runtime/shopify_sync.py` = a20e3a773… (idéntico; contiene `config_store.update(_mutate)` L456/L551 → BUG-034 presente)
- `desktop/runtime/facturascripts_sync.py` = 2bfcba51c… (idéntico; `articulos`/`_normalize_article` → BUG-033 presente)
- `cloud/main.py` = 1f13fe68d… (idéntico)
- `connector/connector.py` = 47f2b4324… (idéntico)
- `version.json` = 6dcf0fa93… (idéntico repo/win-unpacked/E2E)

Cloud en vivo (:8000) sirve: `{"status":"ok","app":"VANOVA Cloud","version":"3.1.1","maiosVersion":"3.1.1"}`
→ sirve el código del repo (sin desync).
Connector en vivo (PID 3788) corre desde `vanova-e2e-300` → código repo.

Fixes en E2E/real:
- BUG-031 (`process_manager` weak-password auto-regen): presente.
- BUG-032 (`data-services.js` filtra scanExclusions): presente.
- BUG-033 (`facturascripts_sync` articulos/preciocoste): presente.
- BUG-034 (`shopify_sync` backfill + variant identity via `config_store.update`): presente. Regression tests pasan (9 passed).

Regresión BUG-034 específica: `tests/test_shopify_backfill.py` → 9 passed (incluye
Bug034AtomicShopifyRmwTests: backfill + variant identity usan update). FIXED → READY FOR RETEST
CONFIRMADO y testado → se puede marcar RETEST PASS / CLOSED.

⚠️ Pero en la instalación REAL (`C:\Users\Admin\AppData\Local\Programs\VANOVA`) el
`version.json` reporta `2.0.26-beta.1` (stale), mientras el código interno ya es 3.1.1
(fixes BUG-031/032/033/034 presentes en el .py). No es desync de código, pero sí una
DISCREPANCIA de versión: el app instalada se reportará como 2.0.26-beta.1 ante el updater
y la UI. → BUG-035 (ver abajo).

---

## TAREA 4 — BUGS NUEVOS (templa BUG_TRACKER)

### BUG-035 — CRITICAL — Startup / Versión

Severity: HIGH
Area: Startup (versión reportada / updater)
Version: VANOVA 3.1.1 (instalación real desactualizada en version.json)

Preconditions:
- Instalación existente en `C:\Users\Admin\AppData\Local\Programs\VANOVA`.
- El `resources\vanova\version.json` NO se actualizó durante el update.

Steps:
1. Abrir VANOVA instalado (Program Files).
2. Consultar el reporte de versión del cliente/updater (UI "Sobre VANOVA", Diagnóstico o
   `version_bundle()`).

Expected:
- La versión mostrada debe ser la del binario instalado (3.1.1).

Actual:
- `C:\Users\Admin\AppData\Local\Programs\VANOVA\resources\vanova\version.json` contiene
  `"version": "2.0.26-beta.1"` (fecha 2026-08-18), mientras el código interno ya incluye los
  fixes de 3.1.1 (shopify_sync, facturascripts, process_manager present). El repo, release y
  E2E dicen 3.1.1. Discrepancia: el updater leería `current_version()` = 2.0.26-beta.1 y
  consideraría que hay una 3.1.1 disponible → ofrecerá (re)instalar 3.1.1 sobre sí misma,
  o la UI mostrará versión incorrecta (2.0.26-beta.1) mientras corre código 3.1.1.

Reproducibility: 5/5 (version.json literalmente stale en disco).

Evidence:
- `sha256sum version.json <Program Files>/.../version.json` ≠ (6dcf0fa… vs 4663d3db…).
- `cat .../version.json` → version 2.0.26-beta.1.

Acceptance criteria:
- La instalación real reporta la misma versión que el código que ejecuta (3.1.1).
- `version.json` de la instalación real se sincroniza con repo al instalar/actualizar 3.1.1.

---

### BUG-036 — HIGH — FacturaScripts (pérdida de datos concurrente, patrón BUG-034 no cubierto)

Severity: HIGH (patrón de lost-update sobre datos financieros/productos)
Area: FacturaScripts (Connector/ERP) — persistencia
Version: VANOVA 3.1.1

Preconditions:
- FacturaScripts configurado (base_url + api_key).
- El runtime expone el API server (ThreadingHTTPServer, cada request en su hilo).

Steps:
- Dispara `sync_now()` de FacturaScripts (con el sync de fondo o manual).
- Durante la descarga HTTP de recursos (network, puede tardar), otro escritor persiste
  `organizedProducts` (p. ej. `cost_importer.apply_cost_plan`, un sync de Shopify, o un
  `removeFile`/otro mutador) sobre la lista vigente.
- FacturaScript `_persist(kind="article", ...)` termina con `config_store.save({"organizedProducts": existing})`.

Expected:
- La escritura concurrente durante el fetch no debe perderse (el fix de BUG-034 ya garantiza
  esto para Shopify backfill).

Actual:
- `desktop/runtime/facturascripts_sync.py::_persist` (L383-449) hace el patrón NO atómico
  exacto que BUG-006/015/019/021/027/034 eliminaron:  `data = config_store.load()` (L389)
  → merge en memoria → `config_store.save({"organizedProducts": existing})` (L449). NO usa
  `config_store.update()` (grep: 0 usos). Un sync FacturaScript concurrente con
  cost_importer / otro sync puede hacer lost-update sobre `organizedProducts` (y de forma
  similar `organizedInvoices`, `organizedInvoiceLines`, `organizedFinance`,
  `organizedSuppliers`, `organizedCustomers`, `organizedProducts` en las otras ramas del
  `_persist`). El guard de reentrada `_sync_lock` solo evita DOS syncs de FacturaScripts
  entre sí, NO una sync vs cost_importer (módulos distintos, locks distintos).

Reproducibility: No determinista; se reproduce bajo concurrencia (mismo patrón documentado en
BUG-034).

Evidence:
- `grep -c "config_store.save" facturascripts_sync.py` = 8; `grep -c "config_store.update"` = 0.
- `_persist` L383-419 (load→merge→save).
- cost_importer también persiste `organizedProducts` vía `config_store.save` (L228) —
  consumidor concurrente real.

Acceptance criteria:
- `_persist` (y `_save_state`) persisten con RMW atómico (`config_store.update(mutator)`).
- Regression test que demuestre que un sync de FacturaScripts no pisa un
  `organizedProducts` escrito concurrentemente por cost_importer.
- Suite completa sigue verde.

---

### BUG-037 — LOW/UX — Cloud API version discrepancy (minor, informativo)

Area: Cloud — `CLOUD_API_VERSION`
`shared/version_info.py` declara `CLOUD_API_VERSION = "3.1.1"` en duro, mientras `version.json`
del repo también es 3.1.1. No es inconsistente hoy, pero es un segundo punto de verdad (hardcoded)
que puede desincronizar en futuras versiones. No bloquea; nota de mantenimiento. (No lo elevo a
bug porque no produce error real en 3.1.1.)

---

## RESUMEN

- Suite: 738 passed (verde). ✅
- Build en vivo: código del repo sincronizado (sin desync BUG-003/025). ✅
- Fixes BUG-031/032/033/034 presentes en repo + E2E + real. ✅
- BUG-034 FIXED → **RETEST PASS** (regression tests pasan) → proponer CLOSED.
- Bugs nuevos:
  - BUG-035 (HIGH, Startup): version.json stale en la instalación real (2.0.26-beta.1 vs 3.1.1).
  - BUG-036 (HIGH, FacturaScripts): persistencia NO atómica (load→save) en `_persist`/`_save_state`
    — patrón de lost-update no cubierto por BUG-034 (pérdida de datos concurrente).

Orden de ataque (según severidad): BUG-035 (Startup) → BUG-036 (pérdida de datos) → BUG-037 (nota).
