# VANOVA_PRODUCT_LEAP_8 — Informe final (7 → 8/10)

Fecha: 2026-08-19 · Proyecto: 3.0.0 · Benchmark congelado intacto (FASE C: 72% / 96% / 0 FP)

---

## 0. Regla de oro cumplida

Antes de tocar nada audité la arquitectura real y ejecuté el motor sobre los **datos reales de la empresa tester** (461 productos / 100 ventas Shopify) en sandbox aislado. No se modificó producción (verificado byte a byte), no se tocó el benchmark ni GROUND_TRUTH, y no se publicó nada.

## 1. Bugs reales encontrados y corregidos

| Bug | Causa raíz | Fix | Test |
|---|---|---|---|
| `detect_aov` rompía con `NameError: sales` al añadir el razonamiento multiproducto | El detector no recibía las ventas | Firma `detect_aov(aov, quality, ref, sales)` + caller actualizado | `test_opportunity_engine.py` |
| Variable `missing` reasignada en Hermes (de la fase anterior) | El bloque BUSINESS BRAIN pisaba los scopes de Shopify | Renombrada a `brain_missing` | `test_hermes_operational_context` (ya cubría) |
| `mark_done` no medía | `recommendation_store` solo cambiaba estado | `set_status()` auto-mide al marcar realizada/resuelta | `test_set_status_lifecycle` |
| `web/dist` quedaba desincronizado | `cp` solo a `index.html` | Sincronización completa de `dist/` | — |

## 2. Opportunity Engine — lo que antes no existía

Ahora el motor emite oportunidades **con evidencia real** (nunca bajando umbrales; las constantes nuevas son mínimos de señal, no relajaciones):

| Detector nuevo | Tipo | Evidencia mínima | Resultado en datos reales |
|---|---|---|---|
| `product_concentration` | oportunidad | un SKU ≥ 25% del revenue + catálogo; sustitutos con crecimiento si existen; severidad alta si el dominante cae | ✅ **Dependencia de un solo producto: 51758206910795 — 842 € = 36% del revenue, con 3 sustitutos con crecimiento compatible** |
| `aov_multi_item_opportunity` | oportunidad | AOV cae ≥10% **y** los pedidos multiproducto caen ≥5 pp (causa demostrada) | ⚠️ No emitida en datos reales: sin causa multiproducto → silencio honesto |
| `customer_reactivation` | oportunidad | ≥3 clientes recurrentes inactivos ≥60 días con valor conjunto ≥1.000 € (un único finding agregado, anti-spam) | ⚠️ Sin masa crítica en datos reales → silencio honesto |
| `customer_declining` | problema | cliente ≥500 €, ≥2 pedidos, revenue 30d cae ≥50% | ⚠️ Sin señal en datos reales |

**Regla de honestidad verificada con test**: AOV cae pero los pedidos siguen siendo multiproducto → la oportunidad **NO** se emite (`test_aov_drop_without_multi_item_cause_no_opportunity`). UNKNOWN ≠ 0: sin evidencia, no hay conclusión.

## 3. Data quality → business intelligence

`missing_cost` ya no dice solo «47 productos sin coste»: ahora explica la **consecuencia empresarial** — sin coste no hay margen, por tanto VANOVA no puede determinar qué productos son rentables ni fundamentar decisiones de pricing, y la acción recomendada ofrece la plantilla (`missing_cost` con `whyItMatters` empresarial).

## 4. Home / Command Center

- `INGRESOS` (Hoy/Semana/Mes/Trimestre/Año/Total) ya visible vía `homeRevenueHTML()` (period_revenue canónico).
- «Prioridades de IA» del Home ahora son las prioridades reales del motor (con `whyItMatters`, evidencia e impacto € o «no cuantificable»).
- El Home muestra también los insights proactivos con evidencia (kind=finding).
- Nuevo nav **Recomendaciones** (Command Center) con la vista completa.

## 5. Recomendaciones seguidas (UI + backend)

- **Backend**: `GET /api/recommendations`, `POST /api/recommendations/status` (estados Nueva/En curso/Realizada/No realizada/Resuelta; al marcar realizada/resuelta **auto-mide**), ambos protegidos (GET añadido a `SENSITIVE_READ_PATHS`).
- **UI**: vista «Recomendaciones» con estado editable, métrica antes → ahora, resultado (🟢 Mejoró / 🔴 Empeoró / 🟡 Sin cambio / ⚪ No medible), y fecha. Renderizado verificado con smoke test de nodo (con 2 recomendaciones y con estado vacío).
- El flujo post-import y `/api/business/analyze` registran las recomendaciones top-5 (dedup por firma).

## 6. Action loop seguro (preview → confirmar → auditar)

Nuevo módulo **`action_center.py`**: acciones PREPARADAS, solo lectura, con audit trail (`audit_log.record`):

- `cost_template`: CSV de los productos sin coste (en datos reales: **47 filas**, `vanova-costes-pendientes.csv`) con columna cost vacía para rellenar e importar por el flujo normal.
- `reactivation_segment`: CSV del segmento de clientes inactivos por valor histórico.
- `POST /api/actions/prepare` (con auth de mutación). **Nunca envía emails, no cambia precios, no escribe fuera de VANOVA.**

## 7. Hermes conectado a todo

El contexto operacional ahora incluye, además de BUSINESS BRAIN + FINDINGS:
- **OPORTUNIDADES DEL MOTOR** (top 3 con evidencia y acción; si no hay: «ninguna con evidencia suficiente — no inventes una»).
- **RECOMENDACIONES SEGUIDAS** (estado + resultado + métrica antes/ahora) — Hermes puede responder «¿qué hiciste y funcionó?».

Verificado en el E2E real: contexto de 15.481 caracteres en 4,0 s frío (~0 s cálido) con los 4 bloques presentes.

## 8. Análisis recurrente y notificaciones

- El scheduler proactivo (cada 6 h) sigue con dedup por firma y `createdAt` estable → re-análisis silencioso.
- El badge de la campana solo cuenta hallazgos nuevos (kind=finding posteriores a `notifSeenAt`) + aprobaciones pendientes; la actividad técnica de agentes nunca genera notificación fantasma.

## 9. E2E real ejecutado (sandbox aislado, datos de la empresa)

```
461 productos / 100 ventas → DETECCIÓN (0.1 s: 6 problemas + 1 oportunidad)
→ INSIGHTS (dedup) → PRIORIDADES (3, score económico) → RECOMENDACIONES (3, open)
→ ACTION CENTER (CSV de 47 costes pendientes)
→ HOME (3 prioridades + 6 insights proactivos + revenuePeriods)
→ HERMES contexto (BRAIN + FINDINGS + OPORTUNIDADES + RECOMENDACIONES, 4.0 s frío)
```

Oportunidad real mostrada al usuario (datos reales): «Dependencia de un solo producto: 51758206910795 — 842,00 € = 36% del total — Sustitutos con crecimiento compatible: 50317615333707, 50317627752779, 55792498213195».

## 10. Business Benchmark (Nivel 3) ampliado

Nuevo dataset con caída de AOV + causa multiproducto, clientes inactivos recuperables y cliente de alto valor en declive: el motor encuentra las 3 señales con evidencia (recall) y no inventa (sin falsos positivos). Todo finding verificado con evidencia + acción + impacto.

## 11. Tests

- **632 passed, 1 skipped, 0 fallos** (antes: 616). Nuevos: `tests/test_opportunity_engine.py` (11), 3 de scheduler proactivo, `set_status` lifecycle, 4 del OpportunityBenchmark.
- Producción byte-idéntica tras la suite (SHA `c43ed3a13e35…`).
- Benchmark congelado intacto (GROUND_TRUTH md5 `01be6228…`).

## 12. Integraciones — estado honesto

| Integración | Estado |
|---|---|
| Shopify | ✅ Validada con datos reales (461 productos / 100 pedidos) |
| FacturaScripts | ⚠️ **NO VALIDADA end-to-end**: conector testeado, sin servidor real disponible en este entorno |
| Hermes | ✅ Contexto estructurado + anti-leak + HECHO/INFERENCIA/NO DISPONIBLE |

## 13. Respuestas a las preguntas del criterio de terminado

- **¿Qué puede hacer ahora que antes no podía?** Emitir oportunidades con evidencia (concentración razonada con sustitutos), explicar la causa multiproducto del AOV, agregar clientes recuperables como oportunidad, seguir recomendaciones en UI, preparar entregables CSV con audit, y que Hermes responda con oportunidades + recomendaciones + resultados.
- **¿Qué oportunidad real detectó en el benchmark?** Concentración del 36% en un SKU con 3 sustitutos; en el dataset sintético además la caída de AOV con causa multiproducto y la reactivación de 4 clientes inactivos.
- **¿Qué evidencia mostró?** Revenue, %, sustitutos, periodos, líneas de venta, evolución 30d — todo numérico.
- **¿Qué recomendación generó?** «Prioriza la diversificación: impulsa los sustitutos con crecimiento compatible» / «Prueba un bundle 14 días y mide AOV» / «Prepara una campaña de reactivación segmentada por valor histórico».
- **¿Puede seguirse?** Sí: la recomendación aparece en la vista Recomendaciones con estado editable.
- **¿Puede medirse su resultado?** Sí: al marcarla realizada/resuelta se re-mide la métrica y clasifica (mejoró/empeoró/sin cambio/no medible).
- **¿Qué acciones puede ejecutar?** Preparar plantilla de costes y segmento de reactivación (solo lectura + audit). No ejecuta cambios externos por diseño.
- **¿Qué integraciones están validadas?** Shopify (real). FacturaScripts NO validada end-to-end.
- **¿Qué sigue sin funcionar?** Ejecución externa de acciones (requiere permisos + confirmación explícita), medición automática programada de recomendaciones en el tiempo, y la validación real de FacturaScripts.
- **¿Qué NO he podido demostrar?** Una oportunidad de cross-sell con la evidencia de esta empresa (29 pedidos multi-SKU, ningún par alcanza el 15% — honesto), y el ciclo completo «ejecutar → medir → reportar» en vivo con un servidor real.

## 14. Puntuación honesta

- **Antes: 7/10** → **Después: 7.5/10** (no 8/10).
- **Evidencia**: la cadena completa está conectada y demostrada con datos reales (motor → oportunidad → prioridad → insight → recomendación → acción preparada → medición), con tests de producto (632 ✅) y producción intacta. Sigo sin darle 8/10 porque: (a) con los datos actuales de la empresa el motor solo emite 1 oportunidad (concentración) — las demás requieren más datos o más evolución temporal; (b) FacturaScripts sigue sin validación end-to-end; (c) la ejecución externa de acciones con confirmación no está operativa; (d) el ciclo «recomendación → medición en el tiempo» depende de que el usuario marque la acción como realizada.

## 15. Archivos modificados

- `desktop/runtime/detection_engine.py` (4 detectores nuevos + razonamiento AOV + missing_cost empresarial + constantes)
- `desktop/runtime/recommendation_store.py` (set_status + auto-medición + VALID_STATUSES)
- `desktop/runtime/action_center.py` (NUEVO)
- `desktop/runtime/hermes_chat.py` (OPORTUNIDADES + RECOMENDACIONES en contexto)
- `desktop/runtime/api_server.py` (GET /api/recommendations, POST /api/recommendations/status, POST /api/actions/prepare)
- `desktop/runtime/runtime_security.py` (protección GET /api/recommendations)
- `web/data-services.js` + `web/dashboard.html` + `web/index.html` + `web/dist/*` (nav, vista Recomendaciones, acciones, handlers, badge intacto)
- `tests/test_opportunity_engine.py` (NUEVO), `tests/test_business_benchmark.py` (ampliado), `tests/test_prioritization.py` (actualizado + nuevo), `tests/test_agent_scheduler.py` (3 nuevos)
