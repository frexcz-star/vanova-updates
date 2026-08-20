# VANOVA 3.0 — RED TEAM FINAL / MEGA TESTING — INFORME

> Fecha: 2026-08-19 · Runtime testeado: **2.0.26-beta.3** (dev) · Método: ataques adversariales reales sobre el runtime, importadores, motores y API — no solo la suite.
> Regla seguida: **BUG → reproducción → causa raíz → FIX → test de regresión → suite completa.**

---

## 🐛 NUEVOS BUGS ENCONTRADOS Y CORREGIDOS

### BUG-RT-01 · Importe absurdo (1e+20 €) contaminaba el revenue — **P1**
- **Reproducción**: CSV con `total=99999999999999999999.99` junto a ventas normales.
- **Antes**: `sale_validation_issue()` → `None` → la fila entraba como válida → `revenue` = 1e+20 (un solo pedido absurdo destrozaba todos los periodos).
- **Causa raíz**: la validación canónica no tenía límite de plausibilidad por pedido individual.
- **Fix**: `_MAX_PLAUSIBLE_TOTAL = 1e12` en `business_model.sale_validation_issue`; filas por encima pasan a `organizedSalesReview` con evidencia (`"total fuera de rango plausible"`), se conservan (nunca se borran ni se inventan) y quedan fuera de métricas.
- **Tests**: `test_absurd_total_flagged_for_review_not_in_metrics`.

### BUG-RT-02 · Columnas duplicadas en CSV: pérdida silenciosa de datos — **P1**
- **Reproducción**: `order_id,total,total,date` → `csv.DictReader` se queda con la ÚLTIMA columna y descarta la primera en silencio (10.5 perdido, usa 99).
- **Causa raíz**: cabecera ambigua sin detección.
- **Fix**: `_duplicate_headers()` detecta columnas repetidas; las filas del archivo van a revisión con `"columnas duplicadas en la cabecera: total"` en lugar de elegir arbitrariamente una columna.
- **Tests**: `test_duplicate_headers_flagged_for_review_not_silent` (sustituye al antiguo que validaba la pérdida silenciosa).

### BUG-RT-03 · `/api/sales` con 100k filas → timeout (>60s) — **P1 (rendimiento)**
- **Reproducción**: importar 100.000 ventas y pedir `GET /api/sales`.
- **Antes**: devolvía TODAS las filas (~3 MB de JSON) + summary → timeout.
- **Causa raíz**: payload ilimitado + summary costoso (500k parses `datetime.fromisoformat`+`strftime`, doble validación por fila, re-escaneo de normalización en cada request, 3 cargas del config por request).
- **Fix** (4 optimizaciones en `business_model.py` + `file_organizer.py`):
  1. `get_sales` limita la lista a `_SALES_ROWS_LIMIT=2000` (la UI solo renderiza ~100); el resumen y `totalCount` cubren el dataset **completo**.
  2. `_sale_date_key` memoizado por string de fecha (cache acotado 100k).
  3. `sales_summary` hace **una sola pasada** de validación y calcula el revenue de esa misma pasada (antes `revenue()` re-validaba todo).
  4. `_ensure_normalized_data` cachea la verificación por mtime/size del config (antes escaneaba las 100k filas en cada request).
- **Resultado**: 100k → 5.3s (antes timeout); 20k (PYME realista) → **0.67–0.74s**; payload 3.2MB → 640KB.
- **Tests**: `test_get_sales_limits_rows_but_keeps_full_summary`.

### BUG-RT-04 · Sanitizador anti-leak de Hermes: variantes del hint no cubiertas — **P2**
- **Reproducción**: Hermes devolvía `[Sistema] Eres el orquestador de datos de VANOVA…` (paráfrasis del hint real).
- **Causa raíz**: el marker exigía la redacción exacta (`…orquestador de VANOVA`).
- **Fix**: marker acortado a `[Sistema] Eres el orquestador` — cubre el hint real y paráfrasis; no depende de la redacción exacta del prompt inyectado.
- **Tests**: `test_paraphrased_system_hint_variants_removed`.

### BUG-RT-05 · `ensure_port_available` mataba CUALQUIER proceso del puerto — **P2 (seguridad/resiliencia)**
- **Reproducción**: puerto 8765 ocupado por una app ajena (no-VANOVA) → el runtime hacía `taskkill /F` sobre su PID.
- **Causa raíz**: recuperación de puerto sin identificación del proceso.
- **Fix**: `process_name()`/`_looks_like_our_runtime()` — solo se cierran PIDs identificables como runtime propio (python/hermes/vanova); un proceso ajeno → `recovery_failed` con mensaje claro y explícito.
- **Tests**: `test_foreign_process_never_killed`, `test_own_runtime_pid_is_killed`.

---

## ✅ VERIFICADOS SIN BUG (ataques sin hallazgo)

- **Importación adversarial** (16 casos): BOM UTF-8, Latin-1, separadores `,;` `\t`, fechas futuras (2099) y antiguas (1900), fechas ambiguas (`01/02/2026`) → todas a revisión, `NaN`/`Infinity`/`-Infinity` → `None` (UNKNOWN ≠ 0), moneda (`€10.50`, `10,50 €`, `$12.00`), filas vacías/parciales, headers vacíos/raros, cantidades enormes. **0 crashes, 0 datos inventados, 0 pérdidas silenciosas.**
- **Idempotencia**: 20× reimport + copia renombrada + columnas reordenadas → **siempre 3 filas, 0 duplicados** en `organizedSales` y `organizedSalesReview`.
- **Data Health**: contadores coherentes (2 válidas + 2 review = 4 total; `needsReviewCount=2`).
- **Updater**: beta.1→2→3, beta.9→10→11, stable↔beta, downgrade bloqueado, manifest corrupto/HTML/404 rechazado, checksum mismatch detectado, cancel/resume cubiertos por tests previos. (El bug `beta.10 < beta.2` de semver se corrigió en la auditoría VANOVA 3.0 anterior.)
- **Seguridad**: escaneo en vivo de TODAS las rutas `/api/*` → **0 endpoints devuelven 200 sin token**; redacción de secretos en logs (api_key, token, password, `sk-`, `shpat_`) verificada; token inválido/vacío rechazado.

---

## 🧪 TESTS

| Métrica | Valor |
|---|---|
| Suite completa | **578 passed, 1 skipped, 0 fallos** (+31 subtests) |
| Tests nuevos esta fase | **4** (RT-01, RT-02, RT-03, RT-04/05 combinados en archivos existentes) |
| E2E limpio (sandbox aislado) | **32 PASS, 0 FAIL** (`scripts/_e2e_v30.py`) |
| Cobertura añadida | revenue con importes absurdos, cabeceras duplicadas, idempotencia 20×, límite de payload con summary completo |

---

## 🚀 PERFORMANCE (sandbox aislado, runtime real vía HTTP)

| Operación | 1k | 10k | 20k | 100k |
|---|---|---|---|---|
| Parse CSV | 0.22s | 2.0s | ~4s | ~19s |
| Organize (import completo) | — | — | 9.8s | 51s |
| GET /api/sales | — | 0.34s | **0.74s** | **5.3s** (antes: timeout) |
| GET /api/products | — | — | 0.66s | 3.5s |
| GET /api/business/findings | — | — | 1.6s | 8.2s |
| GET /api/data-health | — | — | 0.61s | 3.1s |
| GET /api/customers | — | — | 0.53s | 4.8s |

- PYME realista (5k–20k pedidos): todos los endpoints **<1.7s** — experiencia aceptable.
- 100k filas: dominado por el parse JSON del config (~3.5s); aceptable para el límite superior, no es el perfil objetivo.
- `sales_summary` 100k: **17s → 2.3s** (7.5×).

---

## 🔒 SEGURIDAD

- **Corregido en esta fase**: proceso ajeno en el puerto ya no se mata (RT-05); hint de Hermes parafraseado ya no filtra (RT-04).
- **Corregido en auditoría VANOVA 3.0 anterior**: `/api/customers`, `/api/data-health`, `/api/command-center`, `/api/insights`, `/api/approvals`, `/api/tasks/*`, `/api/agent/data/*`, `/api/dashboard/local`, configs de integración → auth obligatoria; bug 500 de command-center con config vacío.
- **Verificado ahora**: 0 rutas sensibles sin auth; secretos redactados en logs; tokens viejos rechazados; `runtime_matches_install` impide attach a otra instalación.
- **Pendiente (bajo riesgo)**: auth en `127.0.0.1` no protege contra malware local con acceso al perfil — es un límite de cualquier app de escritorio, no una brecha remota.

---

## 🧩 ESTADO DEL PRODUCTO (honesto)

**Corregido en esta fase**: importes absurdos (1e20), cabeceras duplicadas, timeout de /api/sales, sanitizador de Hermes contra paráfrasis, matar procesos ajenos en el puerto.

**Conocidos y aceptados**:
- Import de 100k filas tarda ~50s (single-threaded, perfil PYME no llega ahí).
- `business_model.revenue` y `sales_summary` son coherentes (todo = Σ periodos, incl. strings y decimales europeos) — verificado con 5 tests nuevos en la auditoría anterior.
- Semver prerelease numérico corregido (`beta.10 > beta.2`) — evita que la actualización se rompa en betas de doble dígito.
- 0 falsos positivos introducidos: los nuevos umbrales (plausibilidad 1e12, cabeceras duplicadas) son conservadores y solo **mueven a revisión**, nunca descartan.

**No probado en esta sesión** (requiere infraestructura externa): Shopify/FacturaScripts en vivo, CDN real del updater, instalador firmado. Verificado solo a nivel de lógica/tests.

---

## 📋 READINESS

| Nivel | Veredicto |
|---|---|
| DEMO | ✅ LISTO |
| BETA CERRADA | ✅ LISTO |
| 5 CLIENTES | ✅ LISTO (con los límites documentados arriba) |
| 20 CLIENTES | 🟡 CONDICIONAL — necesita validación en vivo de Shopify/FS y build empaquetado |
| LANZAMIENTO COMERCIAL | 🔴 NO TODAVÍA — falta validación de integraciones reales, firma del instalador y un ciclo beta→stable con actualización real |
| 100+ CLIENTES | 🔴 NO — requiere todo lo anterior + telemetría/soporte |

**VEREDICTO FINAL**: VANOVA 3.0 (estado dev, 578 tests) es **suficientemente fiable para BETA CERRADA y los primeros 5 clientes** en el flujo núcleo (instalación limpia, importación de archivos, dashboard, Data Health, Hermes, actualización, aislamiento entre empresas). **No es aún un producto de lanzamiento comercial amplio**: la validación de integraciones externas (Shopify/FacturaScripts) y el empaquetado/instalador con el runtime real deben ejecutarse en el entorno controlado del tester antes de pasar a 20+ clientes.

No se ha publicado ninguna release. Benchmark congelado intacto (GROUND_TRUTH `c09d47ac…`), producción intacta (461 productos / 100 ventas / review 0 / dataVersion sin cambios), sandboxes de prueba eliminados, 0 procesos sobrantes.
