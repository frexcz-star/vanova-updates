# VANOVA_PRODUCT_8_AUDIT — Auditoría de producto: «Leap a 8/10»

Fecha: 2026-08-19 · Versión del proyecto: 3.0.0 · Benchmark congelado: FASE C (72% recall estricto / 96% con parciales / 0 FP) — intacto.

---

## 1. Estado antes (diagnóstico FASE 1)

La cadena **datos → comprensión → detección → razonamiento → oportunidad → recomendación → notificación → acción → seguimiento** estaba rota en 3 puntos, verificados ejecutando el motor sobre los **datos reales de producción** (461 productos / 100 ventas Shopify de la empresa tester):

| Eslabón | Estado antes | Evidencia |
|---|---|---|
| Motor de detección | ✅ Funcionaba | 6 findings sobre datos reales (0.10 s) |
| insights con dedup/lifecycle | ✅ Funcionaba | `sync_from_findings`, dedup por firma |
| Revenue por periodos | ✅ Funcionaba | `period_revenue` canónico (Hoy/Semana/Mes/Trimestre/Año/Total) |
| **Priorización real** | ❌ No existía | El Home mostraba prioridades genéricas de setup («X archivos detectados»), no del motor con score/impacto |
| **Hermes conectado al cerebro** | ❌ Roto | `build_operational_context()` NO recibía findings, prioridades ni company_model: «¿qué debería hacer?» se re-derivaba a mano desde datos crudos |
| **Action loop (recomendación→medición)** | ❌ No existía | Nada registraba «recomendé → actuaste → ¿funcionó?» |
| **Análisis recurrente** | ❌ No existía | Solo tras importación y manual |
| **Oportunidades** | ⚠️ 0 reales | Las señales legítimas existían (concentración 26.4% en un SKU) pero no se emitían como oportunidad priorizada |

Bug real adicional encontrado en esta auditoría: el bloque nuevo del contexto de Hermes reasignaba la variable `missing` (scopes de Shopify) con `dataMissing` del brain, corrompiendo la rama de permisos de Shopify y rompiendo `test_hermes_operational_context`. Corregido renombrando la variable local + test en verde.

---

## 2. Cambios implementados (FASE 2–8)

### 2.1 `desktop/runtime/prioritization.py` (NUEVO) — priorización real
- `score_finding(f)`: score determinista = severidad × confianza × impacto económico × cantidad de datos afectados.
- `build_priorities(findings, top=N)`: devuelve `{id, findingId, findingSignature, findingType, category, severity, confidence, label, title, whyItMatters, evidence, recommendedAction, impactEuro, impactKind, score}`.
- `persist(priorities, data=None)`: guarda en config.
- **UNKNOWN ≠ 0**: impacto no cuantificable → `impactEuro: None` + `impactKind: "estimated"/"not_quantifiable"` (nunca 0 €).

### 2.2 `desktop/runtime/command_center.py` — el Home recibe las prioridades reales
- `get_home_snapshot()` ahora incluye `priorities` (del motor) además de `revenuePeriods` y `proactiveInsights`.
- El frontend (`web/dashboard.html` / `index.html` / `web/dist`) carga `store.priorities` desde el snapshot y `priorityCard` renderiza el formato del motor: label, por qué importa, impacto €, acción recomendada.

### 2.3 `desktop/runtime/hermes_chat.py` — Hermes conectado al Business Brain
- Bloque nuevo en `build_operational_context()`:
  - `BUSINESS BRAIN`: ingresos, pedidos, ticket medio, productos, clientes, concentración de ventas, top productos, y **«Lo que NO sé de esta empresa»** (UNKNOWN ≠ 0).
  - `FINDINGS ACTIVOS DEL MOTOR`: top 5 por score con severidad, confianza, impacto € (si existe), evidencia y acción recomendada. Si no hay findings: «el motor no ha detectado hallazgos activos con los datos actuales» — nunca «no hay problemas».
  - El brain se construye **en fresco** (0.01–0.05 s) en cada contexto: un modelo persistido por una versión anterior puede estar desactualizado (bug real: el modelo almacenado decía «0 clientes» porque el build antiguo no leía `line_items`; el build fresco dice 88 clientes).
- Fix de la variable `missing` (ver §1).

### 2.4 `desktop/runtime/file_organizer.py` — análisis proactivo post-import
- Tras organizar: `build_company_model` (memoria) → `run_detection` → `sync_from_findings` (insights) → `build_priorities` + `persist` → `recommendation_store.record_finding` (memoria de recomendaciones). Todo con store inyectado (aislamiento de tests/instalaciones).
- **El usuario no necesita pulsar nada**: importar ya analiza y surfacea.

### 2.5 `desktop/runtime/api_server.py` — `POST /api/business/analyze`
- Ahora también sincroniza insights, persiste prioridades y registra recomendaciones (top 5, dedup por firma).

### 2.6 `desktop/runtime/recommendation_store.py` (NUEVO) — action loop (FASE 8)
- `record_finding(finding, data)`: ID estable por firma → re-analizar el mismo finding NO crea otra recomendación; solo actualiza la métrica actual.
- `mark_done(id, data)` + `measure(id, data)`: relee la métrica canónica de la entidad y responde `no_change / improved / worsened / unmeasurable` (nunca afirma «funcionó» sin datos comparables).
- **Conectado de verdad** al flujo post-import y a `/api/business/analyze` (no es código muerto).

### 2.7 `desktop/runtime/agent_scheduler.py` — análisis recurrente (FASE 5)
- Tick proactivo cada 6 h: re-ejecuta el motor, dedup por firma, solo notifica novedad real.
- **Guard de aislamiento**: solo se ejecuta con el scheduler real arrancado (`start()`); una llamada directa a `_tick()` (tests/scripts) nunca toca el config de otra instalación. Tests dedicados de aislamiento.

---

## 3. E2E real ejecutado (datos reales, sandbox aislado)

```
IMPORT (461 productos / 100 ventas) →
MODELO (0.016 s → revenue 3.187,64 €, 100 pedidos, ticket 31,88 €, 88 clientes) →
DETECCIÓN (0.097 s → 6 findings) →
INSIGHTS (11, dedup estable entre pasadas) →
PRIORIDADES (3, score económico, persistidas) →
COMMAND CENTER (revenuePeriods: today/week/month/quarter/year/total · priorities: 3 · proactiveInsights: 6 en estado new) →
HERMES contexto (BUSINESS BRAIN ✅ + FINDINGS ACTIVOS ✅)
```

Ejemplos reales en el contexto de Hermes:

```
- BUSINESS BRAIN … · Ingresos totales 3187.64 € · 100 pedidos · ticket medio 31.88 € · 461 productos · 88 clientes
- FINDINGS ACTIVOS DEL MOTOR:
  · Productos sin coste verificable [severidad high, confianza high] — impacto no cuantificable.
    Evidencia: 47 productos con costStatus=missing; …
  · Pedido con total incoherente: #1082 [severidad medium, confianza high] — Total 29.60€ vs líneas 37.00€; Registro preservado (no borrado). …
```

---

## 4. Business Benchmark (Nivel 3) — `tests/test_business_benchmark.py`

Dataset realista generado (PYME ecommerce con anomalías conocidas: 1.200 pedidos, concentración de ventas en SKU-TOP, productos sin coste, pedidos con total incoherente). Verifica:
- precision/recall del motor sobre los problemas inyectados;
- priorización: el finding high-severity con más datos afectados sale primero;
- UNKNOWN ≠ 0: sin costes → impacto `None`, no 0 €;
- dedup de insights y ausencia de FP cuando no hay anomalías.

---

## 5. Red team / hardening verificado

- **Aislamiento de la suite**: snapshot byte-a-byte de `config/maios.json` antes/después de la suite completa → **idéntico** (SHA `c43ed3a13e35…`). Ningún test escribe en producción.
- **Scheduler**: test explícito de que `_tick()` sin `start()` no analiza ni guarda.
- **Hermes**: contexto sin leaks (sanitizador intacto), brain fresco, findings con evidencia.
- **Datos corruptos/incompletos**: cubiertos por la suite previa (filas inválidas → `needs_review` preservadas, nunca borradas; revenue solo de ventas válidas).
- **Sin FP introducidos**: 616 passed / 1 skipped, 0 fallos.

---

## 6. Rendimiento / latencia Hermes (medido en sandbox con datos reales)

| Paso | Tiempo |
|---|---|
| `build_company_model` | 0.016 s |
| `run_detection` (motor completo) | 0.097 s |
| Contexto Hermes (frío, con sondas de servicios en paralelo + normalización) | ~4.9 s |
| Contexto Hermes (cálido, cacheado) | ~0.0 s |

El tiempo restante del chat es la llamada al modelo (depende del proveedor; esperado 15–40 s). La separación por fases (`timings: contextMs/modelMs/totalMs`) permite medirlo en el equipo del cliente.

---

## 7. Integraciones — estado honesto

| Integración | Estado |
|---|---|
| Shopify | ✅ Validada con **datos reales** de la empresa tester (461 productos / 100 pedidos, `line_items`, SKUs, coberturas, sync status en contexto de Hermes) |
| FacturaScripts | ⚠️ **NO VALIDADA end-to-end**: el conector existe y está testeado (normalización URL, `/api/3`, probe, rechazo de HTML), pero no hay servidor real disponible en este entorno. Pendiente de validación con las credenciales del cliente |
| Hermes | ✅ Pipeline real, contexto estructurado, anti-leak, HECHO/INFERENCIA/NO DISPONIBLE |

---

## 8. Tests

- Suite completa: **616 passed, 1 skipped, 0 fallos** (antes de esta fase: 601).
- Nuevos: `tests/test_prioritization.py` (score, ranking, UNKNOWN ≠ 0, determinismo), `tests/test_business_benchmark.py` (business evaluation Nivel 3), `tests/test_agent_scheduler.py` (3 nuevos: tick proactivo aislado, dedup, guard `_started`).
- Benchmark congelado intacto: GROUND_TRUTH md5 `01be6228…`, resultados A/B/C no modificados.

---

## 9. Qué puede hacer VANOVA ahora de forma autónoma

1. Importar/organizar → construir el modelo de empresa (88 clientes reales, no 0).
2. Ejecutar el motor (6 problemas reales detectados) y surfacear insights con dedup/lifecycle.
3. Priorizar los hallazgos por impacto y mostrarlos en el Home (Command Center).
4. Inyectar BUSINESS BRAIN + FINDINGS en el contexto de Hermes (cifras coinciden con el motor).
5. Re-analizar de forma recurrente (cada 6 h) sin spam.
6. Registrar la memoria de recomendaciones para medir su evolución (action loop).

## 10. Qué NO puede hacer todavía

- **Oportunidades reales (cross-sell/pricing/crecimiento)**: con los datos actuales ninguna señal supera el umbral de evidencia (29 pedidos multi-SKU, ningún par alcanza el 15%). Es UNKNOWN correcto — no he bajado thresholds para aparentar.
- **FacturaScripts end-to-end**: sin servidor real.
- **Ejecución de acciones** (cambiar precios, enviar emails): requiere permisos/integraciones — solo está la memoria de recomendaciones.
- **Medición automática visible en UI**: `measure()` existe y está testeado, pero no hay pantalla de «recomendaciones seguidas» todavía.

## 11. Puntuación honesta

- **Producto antes: 6/10** — motor y detección reales, pero la cadena se rompía en priorización, contexto de Hermes y seguimiento.
- **Producto después: 7/10** — la cadena completa está conectada y demostrada con datos reales (priorización, brain en Hermes, proactividad recurrente, action loop, aislamiento verificado). No es 8/10 porque: (a) el motor aún no emite oportunidades con la evidencia disponible (honesto, pero limita el valor percibido); (b) FacturaScripts no está validado en vivo; (c) la medición de recomendaciones no tiene UI; (d) no hay ejecución de acciones con permiso.
- **Evidencia**: E2E real §3, suite 616 ✅, producción byte-idéntica, benchmark congelado intacto.

## 12. Para llegar a 8/10 (orden sugerido)

1. Detector de oportunidades con evidencia mínima real (concentración de clientes/productos, AOV por periodo, reactivación de clientes perdidos) sin bajar umbrales.
2. UI de «recomendaciones seguidas»: hecho/no hecho + resultado medido.
3. Validación FacturaScripts con servidor real del cliente.
4. Acciones ejecutables con preview + confirmación + audit trail (p. ej. actualizar costes desde CSV).
