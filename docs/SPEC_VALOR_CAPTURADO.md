# STRATI — SPEC 2: UI de Cierre del Loop / "Valor Capturado"

**Autor:** Strati (estrategia/producto) · **Para:** Nickx (implementación), Mathew (QA), Boss (decisión)
**Versión proyecto:** 3.1.1 · **Estado:** Listo para implementación
**Regla:** El "Valor Capturado" sale SOLO de fuentes reales (deltas medidos del action-loop). Nunca inventado, nunca "0 €". Lo no medible se muestra honesto.

---

## 0. Objetivo

Mostrar al empresario el **ROI real** que VANOVA le aporta: el **€ capturado/ahorrado** demostrable con sus datos. No métricas vacías ("3 insights") sino **dinero que puede señalar**. Es la pantalla que convierte el valor técnico en "esto merece que pague".

**Principio rector:** el "Valor Capturado" se calcula desde los deltas reales de las recomendaciones `measured` con `outcome=improved` (mismo espíritu que `measure()` del action-loop). Nunca inventado, nunca "0 €".

---

## 1. Qué métricas exactas se muestran y de qué fuente salen

**Métricas (dinero real, no inventado):**

| Métrica | Definición | Fuente |
|---|---|---|
| **capturedEuro** | Σ deltas positivos de recomendaciones `measured` con `outcome=improved` | `recommendation_store` (`metricBefore`/`metricNow`, revenue o ahorro) |
| **capturedPct** | `capturedEuro / facturación del periodo` (si hay facturación real) → "% sobre facturación" | revenue real de la fuente de negocio |
| **improvedCount** | nº de recomendaciones que mejoraron | idem, `outcome=improved` |
| **noChangeCount** | nº sin cambio | idem, `outcome=no_change` |
| **worsenedCount** | nº que empeoró | idem, `outcome=worsened` |
| **unmeasurableCount** | nº sin dato comparable | idem, `outcome=unmeasurable` |
| **totalRecommendations** | total marcadas como hechas | idem |

**Tendencia (opcional, solo si hay datos):** un mini-gráfico de `capturedEuro` acumulado por mes (semana/mes) para mostrar el efecto compuesto. Sin datos → no se dibuja (o empty honesto), nunca una tendencia inventada.

**De dónde sale el €:** los deltas salen de la **fuente de negocio real** (Shopify/ERP/Excel/FacturaScripts) que alimenta `metricBefore`/`metricNow`. Nunca de una cifra inventada. Si la fuente no da delta comparable → `unmeasurable`, no un número.

**Tarjetas/gráficos del panel:**
- **Tarjeta principal (protagonista):** "€ capturado/recuperado" (grande, peso 700).
- **Tarjeta secundaria:** "X% sobre tu facturación" (si hay facturación real; si no, se omite).
- **Tarjeta de desglose:** nº mejoró / sin cambio / empeoró / sin dato (honesto).
- **Mini-gráfico de tendencia** (si hay histórico) → efecto compuesto.
- **Tarjeta de retorno neto** (si hay precio de VANOVA): "€ capturado − coste de VANOVA = retorno neto" — para que el empresario vea que VANOVA se paga sola. El coste de VANOVA es un dato real del plan (no inventado); si no está fijado, se muestra solo el € capturado.

## 1b. Decisión de negocio que toma el empresario con esta vista (copy de soporte)

- **Copy del titular (cuando hay valor):** "VANOVA te ha ayudado a recuperar X € este periodo." → refuerza retención.
- **Copy cuando hay retorno neto:** "Tu suscripción cuesta X € y VANOVA recuperó Y € → retorno neto de +Z €."
- **CTA de soporte:** "Marca otra recomendación como hecha para seguir midiendo" (siguiente paso, retención).
- **Base de upsell:** el € demostrado justifica el paso de Free → Pro.

---

## 2. Estados y vacíos

| Estado | Qué muestra | Copy |
|---|---|---|
| **0 datos** (nada medido) | empty honesto | "Marca una recomendación como hecha y verás aquí el impacto medido con tus datos." (nunca "0 €") |
| **Parcial** (algunas medidas, otras no) | titular con el € de lo medido + lista con cada estado honesto | el titular solo cuenta `improved` |
| **Completo** (todas con resultado) | titular + lista completa con deltas | idem |

**Regla de honestidad:** si no hay dato real, NO se muestra un número. Se muestra "sin dato comparable". Nunca un "0 €" inventado.

---

## 3. Pantalla (componentes + copy word-for-word)

**A. Home — titular de valor (arriba, protagonista):**
```
[Valor recuperado con VANOVA ≈ 214 €]
[de 3 recomendaciones que marcaste, 2 mejoraron · 1 sin cambio · medida con tu data]
```

**B. Vista "Recomendaciones seguidas" — lista/timeline por recomendación:**

```
● Mejoró   · Reactiva al cliente dormido      [+38 €]
   "Marcaste hacerla el 12/08. Sus ingresos pasaron de 120 € a 158 € en 30d."
─────────────────────────────────────────────
● Sin cambio · Haz pack de A+B                [—]
   "Marcaste hacerla el 20/08. Sin diferencia medible en este periodo."
─────────────────────────────────────────────
● Sin dato   · Sube el precio del top         [—]
   "Sin métrica comparable para medir el impacto (no se inventa)."
─────────────────────────────────────────────
```

**C. Estilo (premium dark, corporativo VANOVA):**
- **Paleta:** fondo oscuro premium (`--surface-solid` oscuro), acento rojo corporate
  (`#DC2626`/`#B91C1C`), superficies `glass` en sidebar/header. Igual que el resto de VANOVA.
- **Tipografía:** Inter; el € del titular en peso 700 para que destaque.
- **Iconos:** SVG (sin emojis de color) — ej. un icono "cheque" o "tendencia" para "mejoró".
- **Jerarquía:** titular € arriba (protagonista) → lista de recomendaciones debajo.
- **Estados:** dot + label (● verde=mejoró, ● ámbar=sin cambio, ● gris=sin dato).

**Reglas visuales:**
- Delta € con formato ES (`+38 €`), solo cuando `calculated`.
- `Sin dato` → "sin métrica comparable", NUNCA "0 €".
- Estados con dot + label (●), no badges gigantes.
- Total solo cuenta `improved`.

---

## 4. Conexión con el SPEC 1 (cierre del loop)

- **SPEC 1** (onboarding) lleva al usuario a la 1ª oportunidad → Pantalla 6 "Marcar como hecha".
- Esa marca alimenta el `recommendation_store`, que **mide** (`measure_all`) con la fuente real.
- La medición rellena esta pantalla de **Valor Capturado**.
- **Loop cerrado:** ve coste → ve valor (SPEC 1) → marca → esta pantalla muestra el € medido → repite. Sin el SPEC 1 no hay marca; sin esta pantalla no hay "prueba".

**Enlace con la vista de margen/beneficio:**
- Cada recomendación "mejoró" muestra, además del delta €, un enlace "Ver en margen/beneficio" que lleva a la métrica subyacente (p. ej. el margen del producto o el revenue del cliente) — así el empresario conecta "capturé este coste → esto me ahorra/gana X €" con el dato concreto.

## 4b. Frecuencia de actualización y fuentes

- **Frecuencia:** el "Valor Capturado" se recalcula en cada re-análisis (proactividad 6h) y cuando el usuario marca una recomendación como hecha (auto-medición). No requiere botón manual.
- **Fuentes (nunca inventadas):** Shopify, ERP, Excel, FacturaScripts — vía `metricBefore`/`metricNow` reales. Si la fuente no da delta comparable → `unmeasurable`, se muestra honesto, no un número.

---

## 5. Reglas de honestidad (qué NO mostrar)

- **NO** mostrar un "0 €" cuando no hay dato → "sin dato comparable".
- **NO** sumar `no_change`/`worsened`/`unmeasurable` al `capturedEuro`.
- **NO** afirmar "funcionó" sin métrica comparable.
- **NO** inventar una fuente; todo sale de Shopify/ERP/Excel con evidencia.

---

## 6. Criterios de aceptación verificables

- [ ] Con ≥1 `improved`, el titular muestra "≈ X €" = suma de deltas positivos (formato ES).
- [ ] `no_change`/`worsened`/`unmeasurable` NO suman y se muestran con su etiqueta honesta.
- [ ] Sin medición → empty honesto, nunca "0 €".
- [ ] El € sale de `metricBefore`/`metricNow` reales.
- [ ] Responsive: las tarjetas se apilan bien en móvil.

---

## 7. PENDIENTES (dato que no tengo confirmado)

- [PENDIENTE: endpoint `GET /api/recommendations/impact` — ¿existe ya?]. Si `recommendation_store` expone `list_recommendations()` con `outcome`/`metricBefore`/`metricNow`, el frontend calcula sin endpoint nuevo.
- [PENDIENTE: distinción exacta revenue vs ahorro en el delta por `findingType` — la define Nickx].
- [PENDIENTE: ubicación de la vista "Recomendaciones seguidas" — ¿dentro de Insights o pestaña propia? Decisión Nickx/Boss].

---

*Documento de SPEC generado por Strati. Listo para que Nickx programe y Mathew testee.*
