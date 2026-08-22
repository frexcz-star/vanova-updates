# IMPLEMENTATION PROGRESS — VANOVA (MVP vendible)

Registro honesto del progreso de producto. No inventa resultados; cada fila
refleja lo ejecutado/verificado con evidencia real.

## Estado general
- Versión: **3.1.3** (release publicada, manifest actualizado, updater detecta 3.1.3).
- Suite: **749 passed, 1 skipped** (verificado 2026-08-22).
- HEAD: `0cf22cb` (Tarea 1 — camino más corto al aha).

## Tarea 1 — Onboarding "aha" + flujo de costes simplificado ✅
| Sub-tarea | Estado | Evidencia |
|---|---|---|
| Conexión fuente ventas (Shopify OAuth/token + Excel/CSV) | ✅ | Estado real ≤60s |
| Wizard multi-fase con barra de progreso | ✅ | `SETUP_PHASES` + `s-step` |
| Pantalla de coste: detecta SKUs sin coste | ✅ | empty state "Te falta el dato que desbloquea el dinero" |
| Margen global de 1 campo | ✅ | `promptQuickMargin` + `global-margin-input` |
| Camino más corto al aha | ✅ | Botón "Declarar mi margen" (commit `0cf22cb`) |
| El AHA: "En juego este mes" | ✅ | Home con € real (calculated/estimated) |
| Honestidad | ✅ | calculated (coste real) vs estimated (margen global); nunca 0 €; UNKNOWN≠0 |

**Verificado end-to-end:** `promptQuickMargin` persiste el margen global y
conserva identity/channels (merge BUG-037). Evidencia real ejecutada:
cross-sell + margen 60% + 60 pedidos → 36 € estimated.

## Tarea 2 — Empaquetado end-to-end (PC stock) ✅ núcleo / ⏸ piloto
| Sub-tarea | Estado | Evidencia |
|---|---|---|
| Instalador Electron autocontenido | ✅ | python-bundle 3.11.15 embebido |
| Primer arranque runtime + cloud | ✅ | HTTP 200 real |
| Hermes/Ollama | ✅ | degrada con modelo `:cloud` (sin descarga local) |
| Wizard en español | ✅ | verificado en app.asar |
| Prueba .exe en PC stock físico | ⏸ BLOQUEADO | VM no viable (sin ISO, ~25GB); requiere piloto físico de Nico |

## Tarea 3 — UI "Valor Capturado" con datos reales ✅
| Sub-tarea | Estado | Evidencia |
|---|---|---|
| Endpoint `/api/recommendations/impact` | ✅ | HTTP 200 real |
| capturedEuro (Σ deltas measured/improved) | ✅ | deltas metricBefore/metricNow reales |
| capturedPct (% sobre facturación real) | ✅ | solo si facturación real; si no, None |
| Desglose honesto (mejoró/sin cambio/empeoró/sin dato) | ✅ | 4 contadores |
| Empty state honesto | ✅ | "sin dato comparable", nunca 0 € |
| Comparativa "se paga sola" | ⏸ | precio del plan no fijado (honesto) |

## Bloqueos que dependen de Nico/Mathew (no es código)
- Piloto físico en PC stock (Tarea 2) — docs/PILOTO_FISICO_NICO.md.
- Cliente real con ventas+costes para ROI en producción + fijar precio del plan.

## Registro de eventos del piloto (SPEC 3) ✅ — commit cfa44a2
| Sub-tarea | Estado | Evidencia |
|---|---|---|
| Log JSONL con timestamps de eventos del piloto | ✅ | `desktop/runtime/pilot_events.py` → `%LOCALAPPDATA%/VANOVA/logs/pilot_events.jsonl` |
| Métrica "tiempo hasta el €" (conexión OK → 1ª oportunidad € vista) | ✅ | `metric_time_to_euro()`; sin eventos reales → `unavailable` (nunca inventado); `target_lt_15min` para el Go/No-Go |
| Hooks en el runtime | ✅ | `source.connected` (Shopify OK), `opportunity.seen` (1ª con upsideEuro real), `recommendation.marked`, `measure.done` |
| Endpoint expuesto | ✅ | `GET /api/pilot/summary` verificado en vivo: HTTP 200 con recuentos reales |
| Tests de regresión | ✅ | 5 passed (suite completa 754 passed, 1 skipped) |

**Hueco #2 confirmado ya implementado:** "Recomendaciones" es pestaña propia en
la nav (`dashboard.html:1505`) con enlace "Ver recomendaciones" desde la tarjeta
de € capturado del Home (`dashboard.html:2917`).

**Hueco #3 (retorno neto):** solo aparece cuando capturedEuro > precio del plan
y el plan esté activo/fijado por Nico. Hasta entonces se muestra solo € capturado.

