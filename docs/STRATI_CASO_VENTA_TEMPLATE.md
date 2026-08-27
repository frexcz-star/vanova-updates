# STRATI — PLANTILLA DE CASO DE VENTA (para rellenar con el primer piloto)

**Autor:** Strati (estrategia/producto) · **Para:** Boss/Nico (rellenar tras el piloto) · **Regla:** NUNCA inventar €, citas ni datos — todo de fuente real con consentimiento (si no hay consentimiento → caso anónimo).

Esta plantilla está lista para rellenar con el primer piloto real. Cada campo sale de una fuente verificada.

---

## CABECERA
- **Nombre del negocio (solo si firmó consentimiento; si no, "ecommerce anónimo")**
- **Sector / tipo de tienda:** ____________
- **Plataforma:** Shopify / Excel / Otro: ____________
- **Fecha del piloto:** ___ → ___

## 1. EL PROBLEMA (percepción del dueño ANTES, registrada en la entrevista)
- **"Creía que su margen era..."** → ____________
- **"No sabía / no medía..."** → ____________
- **Fuente:** nota de entrevista (SPEC 3 §4c, línea base percibida)

## 2. EL "AHA" (qué descubrió, con su € real)
- **Tiempo hasta ver su € (objetivo <15 min):** ______ min — **fuente:** `metric_time_to_euro` (pilot_events)
- **Titular que vio:** "≈ X € en juego" / "pierdes ≈ Z €/mes" — **fuente:** SPEC 1 §5 (Home, dato real)

## 3. LA ACCIÓN QUE TOMÓ
- **Recomendación marcada:** ________________
- **Fecha:** ________________

## 4. EL VALOR CAPTURADO (real, medido)
- **€ capturado:** ______ € — **fuente:** `capturedEuro` (endpoint /api/recommendations/impact), deltas `improved` reales
- **Comparación antes/después:** "Antes: X € → Ahora: Y € → delta +Z €" — **fuente:** `metricBefore`/`metricNow`

## 5. LA CITA (textual, del feedback del piloto)
> "________________________________" — [nombre, si firmó consentimiento; si no, anónimo]

**Fuente:** entrevista de cierre (SPEC 3 §7b, pregunta "¿Qué te ha aportado VANOVA que no supieras ya?")

## 6. EL NÚMERO DE CIERRE (para el titular del caso)
- **Tiempo al €:** ______ min (objetivo <15)
- **€ capturado real:** ______ €
- **Uso:** ______ días/mes
- **¿Pagaría?:** Sí / No (fuente: encuesta)

## 7. CONSENTIMIENTO
- [ ] Firmado (caso con nombre/negocio) — **fuente:** `STRATI_CIERRE_PRODUCTO.md` §3.2
- [ ] No firmado → caso ANÓNIMO (sin nombre/negocio, solo datos agregados)

---

## Cómo se usa este caso
1. Es el material de venta del MVP (SPEC 3 §7b.4): el siguiente empresario ve el caso y entiende el valor en €.
2. Se presenta en el dashboard / landing con los datos REALES + cita + tiempo al €.
3. **Nunca** se rellena con cifras inventadas ni citas que no son textuales.

---

*Plantilla de caso de venta generada por Strati. Solo propone/diseña; no ejecutó nada. Sin datos inventados: cada campo tiene fuente real + consentimiento.*
