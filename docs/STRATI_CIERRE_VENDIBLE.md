# STRATI — CIERRE VENDIBLE: resumen congelado de los 3 SPECs para Nickx

**Autor:** Strati (estrategia/producto) · **Para:** Nickx (implementación), Mathew (QA), Boss (decisión), Nico (decisión de negocio)
**Fecha:** 2026-08-23 · **Regla:** el € sale SOLO de fuentes reales; nunca inventado, nunca "0 €". Solo diseño/propuesta; Strati no ejecuta.

---

## 1. Estado de los 3 SPECs (verificado en disco, 2026-08-23)

| SPEC | Estado | Qué contiene (1 línea) |
|---|---|---|
| **STRATI_ESPEC_FLUJO_COSTES.md** | **LISTO** | Onboarding P0-P6 + state-machine, empty states con copy ES, titular € real <15 min (fórmula verificada en `dashboard.html:2527`), bloqueos del aha (§14), umbrales (§12), test de aceptación (§15). Fuentes reales, `UNKNOWN≠0`. |
| **STRATI_ESPEC_VALOR_CAPTURADO.md** | **LISTO** | capturedEuro/ahorro reales de `measure()` (contrato del endpoint verificado en `api_server.py:1046`), nunca "0 €", vista hoy/7d/30d, retorno neto (si plan activo), honestidad. |
| **STRATI_ESPEC_PILOTO.md** | **LISTO** | Criterios de piloto (PYME ecommerce + coste por SKU + dueño), métricas de éxito ANTES (VALIDADO vs NO), timeline 30d + plan 1 semana, señal "ready para escalar", separación construible vs operativo (§7c), entregables operativos incrustados. |

**Sin gaps de diseño.** No se detectó ningún hueco de diseño abierto en ninguno de los 3.

---

## 2. LISTO para programar (lo que Nickx puede construir hoy)

**SPEC 1 — Onboarding "aha" + flujo de costes:**
- Wizard multi-fase P0-P6 con state-machine (§1f) y transición P4→P5 por caso (coste SKU `calculated` / margen global `estimated` / "Más tarde" UNKNOWN honesto).
- Botón "Declarar mi margen" (ya implementado en `dashboard.html:2515`).
- Alta manual de coste "una línea a la vez" (Pantalla 4b) + plantilla CSV.
- Test de aceptación del aha (§15): `t_aha ≤ 15 min`.

**SPEC 2 — UI Valor Capturado:**
- Tarjeta protagonista "€ capturado" + % sobre facturación + retorno neto (si plan activo).
- Vista por ventana hoy/7d/30d (solo datos reales).
- Desglose honesto: mejoró/sin cambio/empeoró/sin dato.
- Contrato del endpoint `GET /api/recommendations/impact` documentado.

**SPEC 3 — Registro de eventos del piloto:**
- `pilot_events.py` expone `source.connected` / `opportunity.seen` y `metric_time_to_euro()`.
- Métrica "tiempo hasta el €" (objetivo <15 min).

---

## 3. PENDIENTES de ejecución/operativo (NO son diseño — son los que identificamos)

| Pendiente | Dueño | Impacto |
|---|---|---|
| **Conseguir el piloto real (1-2 PYME ecommerce + coste por SKU)** | Boss/Nico | Sin piloto, el € real no se muestra en vivo; bloquea la venta |
| **Fijar el precio del plan Pro (29 €/mes)** | Nico | Activa la tarjeta de retorno neto (€ capturado − coste) |
| **Verificar el instalador en PC stock** | Nickx/QA | Que el piloto pueda instalarlo solo |

---

## 4. ORDEN CRÍTICO PARA NICKX hasta el piloto (recuérdalo)

1. **SPEC 1**: conectar Shopify/Excel (fuente de ventas) + wizard P0-P6.
2. **SPEC 1**: "Declarar mi margen" / alta manual de coste → el € aparece en Home.
3. **SPEC 2**: endpoint de impacto + tarjeta "€ capturado" en Home.
4. **SPEC 3**: `pilot_events.py` registra `source.connected` + `opportunity.seen` y mide `tiempo al €`.
5. **Boss/Nico**: reclutar el piloto real → que vea su € real en <15 min → Go/No-Go.

**Salida de la semana:** UN piloto real ve su € real en <15 min (o sabemos exactamente qué bloquea).

---

*Documento de cierre generado por Strati. Solo propuesta/diseño; no ejecutó nada. Listo para despacho a Nico (valida) y Nickx (implementa).*
