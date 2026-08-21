# STRATI — SPEC: Detector de Oportunidades de Crecimiento

**Autor:** Strati (estrategia/producto)
**Para:** Nickx (dev) · QA (Mathew)
**Versión proyecto:** 3.0.8 · **Estado:** Propuesta aprobada por Boss — implementación pendiente
**Regla:** Documento de especificación. NO es código; no modifica el proyecto.

---

## 0. Resumen ejecutivo (por qué esto vende)

El empresario-cliente no paga por un diagnóstico de problemas que ya sospecha.
Paga por **dinero**: "esto te puede hacer ganar / recuperar X €". Hoy VANOVA detecta
problemas (6 hallazgos reales) y los prioriza por impacto en el Home, pero las
**oportunidades de crecimiento** están infra-surfaced: el motor ya emite varias
(`cross_sell`, `product_concentration`, `aov_multi_item_opportunity`,
`customer_concentration`, `low_revenue_high_margin`), pero:

1. **No se cuantifican en € de forma accionable** para el empresario (varias tienen
   `kind: "estimated"` con `marginPotential: None`, o impacto solo cualitativo).
2. **No hay una vista "Oportunidades" dedicada** que las agrupe como dinero a captar
   (se mezclan con problemas/riesgos en la lista general).
3. **No hay ROI visible** (sin UI de "recomendaciones seguidas", la medida no se ve).

Este spec **no crea un motor nuevo**: formaliza el "Detector de Oportunidades de
Crecimiento" como una **capa de producto** sobre el motor existente, con reglas de
evidencia estrictas (mismo espíritu `UNKNOWN ≠ 0`), un output en € comprensible y un
camino de prueba para QA. Es la pieza P0 nº1 de la hoja de ruta comercial.

---

## 2. Qué detecta y por qué genera valor/ventas

### 2.1 Las 5 oportunidades objetivo

| # | Oportunidad | Tipo de finding existente | Por qué vende |
|---|---|---|---|
| 1 | **Cross-selling** (pares de productos co-comprados) | `cross_sell` | Sube el ticket medio sin más tráfico — mensaje de venta directo |
| 2 | **Dependencia de producto único** (concentración) | `product_concentration` | Riesgo + palanca: diversificar o subir precio en el top |
| 3 | **Subir ticket medio / reactivar multiproducto** | `aov_multi_item_opportunity`, `aov_change` | Vincular la caída de ticket a una causa concreta (menos artículos/pedido) |
| 4 | **Cliente dormido reactivable / concentración de clientes** | `customer_concentration` (señal en company_model) | Retención y reactivación más baratas que captar nuevo |
| 5 | **Alto margen con bajo revenue (promoción potencial)** | `low_revenue_high_margin` | Producto infra-promocionado que puede crecer |

### 2.2 Por qué genera valor comercial
- Convierte "diagnóstico" en "recomendación de ingresos": el empresario ve €, no adjetivos.
- Crea el **"aha moment"** de venta: "importé mis datos y en 5 min veo una oportunidad de +X €".
- Hace el producto **retable y pagadero**: el diagnóstico gratis es teaser; la oportunidad
  con € y su seguimiento es lo que se paga (niveles de pricing).
- Respeta la honestidad que diferencia a VANOVA: `UNKNOWN ≠ 0`, nunca bajar umbrales
  para "aparentar" oportunidades.

---

## 3. Reglas concretas (entradas, lógica, umbrales)

> **Principio rector:** toda oportunidad requiere **evidencia mínima real** en los datos.
> Sin suficiente volumen o sin coste verificable → **NO se emite** o se marca
> `kind: "estimated"` / `impactKind: "not_quantifiable"`. Nunca un 0 € ni una cifra inventada.

### 3.1 Entradas (datos que consume — ya existen en el motor)
- `sales` (pedidos con `line_items`, `date`, `customer`/`customerName`, `total`).
- `products` (catálogo con `sku`, `rrp`, coste resuelto vía `product_identity.resolve_cost`
  — solo `costStatus` en `("verified","imported")`).
- `quality` (`ordersTotal`, `...` de `business_signals`).
- `ref` (fecha de referencia de los datos; ventanas desde `ref`, no desde "hoy").

### 3.2 Constantes reales a reutilizar (NO duplicar)
Del `detection_engine.py` (documentadas, son las reglas de evidencia):

| Constante | Valor | Uso |
|---|---|---|
| `MIN_ORDERS_TOTAL` | 20 | Umbral mínimo de pedidos para analítica de producto |
| `MIN_ORDERS_WITH_A` | 10 | Pedidos mínimos que contienen A para cross-sell |
| `MIN_CO_OCCUR_FREQ` | 0.15 | Frecuencia mínima de co-aparición (15%) |
| `MIN_ORDERS_PER_PERIOD` | 10 | Pedidos mínimos por período para AOV/evolución |
| `CHANGE_PCT` | 0.30 | Variación mínima para caída/crecimiento de producto |
| `AOV_CHANGE_PCT` | 0.10 | Variación mínima para ticket medio |
| `HIGH_REV_SHARE` | 0.15 | Share de revenue para "mucho revenue" |
| `MARGIN_GAP_POINTS` | 10.0 | Puntos de margen por debajo del promedio |
| `COST_COVERAGE_MIN` | 0.6 | Fracción mínima de SKUs con coste para afirmar márgenes |

### 3.3 Lógica de la capa "Oportunidades" (propuesta)

Se construye como una **capa de presentación/agrupación** sobre los findings activos
de categoría `opportunity`, en `prioritization.py` o un módulo nuevo `opportunity_catalog.py`
(sin tocar `detection_engine.py` salvo que Nickx justifique). Paso:

1. **Filtrar** los findings activos con `category == "opportunity"`.
2. **Enriquecer €:** para cada oportunidad, derivar un **potencial en €** respetando la
   evidencia:
   - **Cross-sell (`cross_sell`):** si ambos SKU tienen coste verificado → estimar
     `upsideEuro = ticketsPotencial × margenPromedio`; si no hay coste → `upsideEuro = None`,
     `kind="estimated"` con explicación honesta ("requiere margen por SKU").
   - **Concentración (`product_concentration`):** usar `revenueAtRisk` ya calculado;
     añadir `upsideEuro` = potencial de diversificar sustitutos (con cambio ≥0) solo si
     hay evidencia, si no `None`.
   - **Ticket/AOV (`aov_multi_item_opportunity`, `aov_change`):** `upsideEuro` =
     (AOV_objetivo − AOV_actual) × pedidos_periodo, **solo** si el dato permite calcularlo;
     si no → `None`.
   - **Cliente reactivable (`customer_concentration` / ausencia de pedidos):** `upsideEuro`
     = (ticket medio del cliente) × (pedidos esperados recuperables), solo con historial real;
     si no → `None`.
   - **Margen/revenue (`low_revenue_high_margin`, `high_revenue_low_margin`):** usar
     `marginPotential` / `economicImpactEuro` cuando existan (ya los calcula el motor).
3. **Priorizar** con `score_finding` existente (impacto € log-scale × severidad × confianza)
   y devolver top-N (p. ej. 5) oportunidades enriquecidas.

### 3.4 Umbral de emisión (anti-ruido)
- Nunca emitir una oportunidad cuyo `upsideEuro` sea `< 25 €` (implica evidencia €
  mínima; evita ruido de cola larga — mismo espíritu que la FASE B del motor).
- Nunca afirmar una cifra si falta el dato (coste/stock): `None` + `kind:"estimated"`.
- No introducir umbrales nuevos que contradigan las constantes de `detection_engine.py`;
  la capa las **reutiliza**, no las redefine.

---

## 4. Output (qué ve el empresario)

### 4.1 Nueva vista "Oportunidades" (pestaña en Insights o Home)
Tarjeta por oportunidad con:
- **Título** accionable: "Cross-sell: [A] + [B]" / "Producto único concentra el 26.4% del revenue".
- **Impacto estimado (€)** en grande, o "Impacto no cuantificable" si `None` (nunca 0 €).
- **Evidencia** (1-3 líneas con nºs reales: pedidos, %, revenue, margen).
- **Acción recomendada** (del finding, ya existe).
- **CTA** "Marcar como hecha / Probar 14 días" que alimenta el action-loop (`measure()`).

### 4.2 Formato € (reglas de display)
| Campo | Regla |
|---|---|
| `upsideEuro` | `Muestra "≈ X €"` cuando `kind="calculated"` (evidencia numérica) |
| `upsideEuro = None` | Muestra "**Impacto estimado: requiere coste por SKU**" — nunca "0 €" |
| Rango | Si hay mín/máx real (p. ej. reactivación), mostrar rango `X–Y €` con fuente |

### 4.3 Copy (ES, sin emojis de color; estilo corporate)
- Título sección: "**Oportunidades de crecimiento**".
- Subtítulo: "Lo que puedes capturar con los datos actuales. Cada oportunidad tiene un
  impacto estimado y una acción clara."
- Empty state honesto: "No hay oportunidades con evidencia mínima hoy. Si cargas costes y
  más pedidos, el detector puede darte más señales." (Enlace a "Conectar fuente".)

---

## 5. Requisitos para dev

### 5.1 Datos que necesita y dónde conectarlos
- **Origen:** `sales`, `products`, `quality` — los mismos que consume `run_detection`
  (flujo post-import y `/api/business/analyze` ya lo arman).
- **Coste por SKU:** `product_identity.resolve_cost()` (solo `verified`/`imported`).
- **Señal de cliente:** `company_model._customer_concentration()` ya existe; exponerla
  como `customer_concentration` finding si no está ya surfaceada.
- **Persistencia:** seguir el patrón `prioritization.persist` (config store inyectable).

### 5.2 Archivos candidatos (NO modificar nada aún; solo referencias)
- `desktop/runtime/detection_engine.py` — señales ya emiten (leer, no cambiar).
- `desktop/runtime/prioritization.py` — reutilizar `score_finding` / `build_priorities`.
- `desktop/runtime/company_model.py` — concentración de cliente.
- `web/dashboard.html` + `web/data-services.js` — nueva vista "Oportunidades".
- `web/dist/*` — sincronizar build (patrón BUG-003).

### 5.3 Decisiones que DEBE tomar Nickx (a confirmar con Boss)
- ¿Capa nueva en `prioritization.py` o módulo `opportunity_catalog.py`? (prefiero módulo
  nuevo por aislamiento de tests).
- ¿Nueva pestaña en Insights o tarjeta en Home? (prefiero Home para el "aha moment",
  con acceso desde Insights).
- Regla de persistencia y dedupe por firma (reutilizar firma estable `type:entity` de BUG-001).

---

## 6. Cómo se probaría (QA — Mathew)

### 6.1 Tests automáticos (patrón acumulativo del tracker)
- `tests/test_opportunity_catalog.py`:
  - Dado un dataset con concentración inyectada → emite `product_concentration` con `revenueAtRisk`.
  - Cross-sell con coste verificado → `upsideEuro` calculado; sin coste → `upsideEuro = None`, nunca 0.
  - `UNKNOWN ≠ 0`: sin costes → impacto `None`, no 0 €.
  - Anti-ruido: dataset sano sin anomalías → **0 oportunidades** (no FP).
  - `upsideEuro < 1` no se emite.
- Regression: suite completa en verde (hoy 671+ tests acumulativos).

### 6.2 QA manual (Mathew, checklist UX)
1. Conectar Shopify/Excel real → ver "Oportunidades" con € o estado honesto.
2. Sin costes cargados → oportunidades "requiere coste por SKU", nunca 0 €.
3. CTA "Marcar como hecha" → aparece en "Recomendaciones seguidas" (acción-loop).
4. Copy en español, sin emojis de color, responsive.

---

## 7. Prioridad y alcance
- **Alcance v1 (esta spec):** capa de oportunidades + enriquecimiento € + vista "Oportunidades"
  + 1 test del action-loop. Sin ejecución de acciones (eso es spec aparte P0/P1).
- **Fuera de alcance v1:** acciones autónomas, pricing dinámico, validación FacturaScripts.

---

*Documento de especificación generado por Strati. No modifica el proyecto. Aprobado por
Boss (2026-08-20); pendiente de review/decision de Nickx para implementación.*
