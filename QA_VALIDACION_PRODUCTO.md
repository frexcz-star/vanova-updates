# QA — VALIDACIÓN DE PRODUCTO (VANOVA / MOOVING)

Fecha: 2026-08-22 (revalidado) · Release: 3.1.3 · HEAD: 1f19200 · Suite: 754 passed
Runtime: 127.0.0.1:8765 HTTP 200 · Cloud: 127.0.0.1:8000
Autor: Mathew (QA). Rol: validación, no construcción de código.

---

## 1) FLUJO DE COSTES → € REAL — ✅ FUNCIONA

**Evidencia real (ejecución del motor sobre HEAD 0cf22cb):**
- Con coste real por SKU → `5 con EUR (calc=5)`, impactKind `calculated` (41.26 / 39.18 / 36.91 €).
- Sin coste por SKU + margen global 40% → `3 con EUR (est=3)`, impactKind `estimated` (30.4 / 28.8 / 27.2 €).

**Camino completo (conexión → input de costes → cálculo → visualización):** conectar fuente → declarar margen global (1 campo) o cargar costes (CSV por SKU) → el motor emite findings → el catálogo cuantifica en €. No se atasca en ningún paso. **Nunca inventa 0 €**: los pares sin margen/coste quedan `not_quantifiable` (UNKNOWN honesto, guía a cargar lo que falta).

**Target <15 min:** sí. El cálculo es instantáneo; el único tiempo real es el del empresario cargando sus datos.

---

## 2) ONBOARDING "AHA" — ✅ FUNCIONA (no-técnico)

Wizard guiado en español (Empresa → Sector → Conexión → Coste → €). El commit nuevo `0cf22cb` añade el botón **"Declarar mi margen"** = camino más corto al € (un solo campo). Cada pantalla dice qué dato falta y ofrece el botón.

- ¿Se queda atascado en alguna pantalla? No.
- ¿Usable por un no-técnico (sin código/ERP)? Sí — no hay jerga técnica.
- ¿El momento "aha" (ver su €) llega? Sí — el panel "En juego este mes" muestra el € cuantificado al cargar coste o declarar margen.

---

## 3) UI CIERRE DEL LOOP / "VALOR CAPTURADO" — ⚠️ MECANISMO FUNCIONA / ROI real NO validado en producción

**Evidencia backend real (no mock/sintético):** con una recomendación `measured+improved` (delta +50) + una `no_change`, el endpoint devuelve:
`{"capturedEuro": 50.0, "improvedCount": 1, "noChangeCount": 1}` — el ciclo marcar-hecho → medir → delta € funciona con datos reales (deltas metricBefore/metricNow).

**En producción en vivo (endpoint real):**
```json
{"capturedEuro": 0.0, "capturedPct": null, "improvedCount": 0, "noChangeCount": 0,
 "worsenedCount": 0, "unmeasurableCount": 0, "total": 2}
```
`/api/opportunities` → `[]`.

Esto **no es mock ni dato sintético**: es el valor honesto (0.0) porque el entorno MOOVING no tiene ventas ni recomendaciones medidas. **El ROI real >0 € no se puede validar en producción** hasta que un cliente real conecte ventas+costes y cierre el loop. No lo maquillo.

---

## RESUMEN

| # | Función | Veredicto | Bloquea venta |
|---|---------|-----------|---------------|
| 1 | Flujo costes → € real | ✅ FUNCIONA | No |
| 2 | Onboarding "aha" | ✅ FUNCIONA | No |
| 3 | Valor capturado | ⚠️ Mecanismo listo; ROI real pendiente | Sí (parcial) |

**Veredicto:** VANOVA está lista para vender en las palancas 1 y 2 (empresario no-técnico conecta, declara margen/costes y ve su € en <15 min). La palanca 3 está implementada y honesta (vacío, no mock), pero el ROI real en producción solo se demuestra al conectar un cliente real que cierre el loop. **No se inventó ningún KPI ni dato.**

---

## Validación cruzada SPEC ↔ código (2026-08-22, en colaboración con Strati)

Se contrastaron los 3 SPECs (`STRATI_ESPEC_FLUJO_COSTES.md`, `STRATI_ESPEC_VALOR_CAPTURADO.md`, `STRATI_ESPEC_PILOTO.md`) contra el comportamiento real del código:

**Coherente (verificado):**
- SPEC 1 §3: `global_margin_pct` no llega al motor `detection_engine` (grep: 0 apariciones) — correcto.
- SPEC 2 §5/§9: endpoint `/api/recommendations/impact` HTTP 200, `capturedEuro: 0.0`, `capturedPct: None` en estado vacío honesto — idéntico a lo verificado en vivo.
- SPEC 2 §1/§13: `capturedEuro` solo de deltas `measured`+`improved` reales; `unmeasurable` no suma — coincide con el código (verificado `capturedEuro: 50.0` con una rec improved).

**Incoherencia detectada y CORREGIDA por Strati (SPEC 1 §3, líneas ~250 y ~256):**
- El SPEC original afirmaba que con margen global pero SIN coste por SKU, la oportunidad cross-sell queda en `upsideEuro=None` (no cuantificada).
- La ejecución real mostró que SÍ se cuantifica en € `estimated` (art-101+art-102 | 30.4 EUR | estimated) porque `_upsell_for_cross_sell` llama `resolve_cost(p, global_margin_pct)` que estima el coste con el margen global.
- Strati corrigió el SPEC a: "se cuantifica en € **estimated** (coste estimado con margen global); solo con coste por SKU real pasa a **calculated**". Mantiene la honestidad (nunca `calculated` sin coste real).
- Registrado en `REGISTRO_STRATI.md`. Sin otras incoherencias materiales.
