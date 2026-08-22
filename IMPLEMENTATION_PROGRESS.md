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
