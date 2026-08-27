# STRATI — SPEC: Capa de Vitalidad de Producto (filtro de señales)

**Autor:** Strati (estrategia/producto) · **Para:** Nickx (implementación), Mathew (QA), Boss (decisión)
**Versión proyecto:** 3.1.3 · **Estado:** Listo para implementación
**Dirección estratégica (Nico):** VANOVA se diferencia por INTELIGENCIA de detección, no por el dashboard. Una señal debe saber si es real (con contexto) o ruido, y descartarla explicando por qué. Este SPEC implementa la prioridad nº1: **capa de vitalidad de producto** para que no se generen señales falsas sobre productos muertos.

---

## 0. Objetivo

Evitar que VANOVA marque oportunidades/riesgos sobre productos **sin ventas recientes** (muertos/obsoletos), como en el caso de la "dependencia de un solo producto" sobre una agenda 2025 obsoleta. Un producto muerto no es una señal real. La capa de vitalidad decide, con datos reales, si un producto está "vivo" y merece generar señales.

---

## 1. Regla genérica de vitalidad

**Definición:** un producto es **VIVO** si tiene ventas reales en una ventana reciente; **NO-VIVO** (muerto/obsoleto) si no las tiene. Se calcula con datos reales de pedidos (`organizedSales`, campo `date`).

**Periodo (decidido):** `VITALITY_WINDOW_DAYS = 90` (90 días).
- **Razón:** 90 días cubre ~1 trimestre, suficiente para distinguir un producto vivo de uno estacional-muerto u obsoleto, sin ser tan corto que marque muerto un producto con estacionalidad anual fuerte. Para un ecommerce no-técnico es un periodo razonable y defendible.

**Cálculo (con datos reales):**
```
vitalidad(producto, sales):
    # fecha de referencia = la más reciente del dataset (no "hoy" inventado)
    ref = _reference_date(sales)
    ventas_en_ventana = [s for s in sales
                          si s.sku == producto.sku
                          y _as_date(s.date) >= ref - VITALITY_WINDOW_DAYS]
    es_vivo = len(ventas_en_ventana) > 0          # ≥1 pedido con ese SKU en la ventana
    días_desde_última = (ref - _as_date(max(ventas_en_ventana).date)).days   # solo si es_vivo
    return { "es_vivo": es_vivo, "ultima_venta_dias": días_desde_última, "ventas_en_ventana": len(...) }
```

**Nota de honestidad:** la ventana se mide contra la **fecha de referencia del dataset** (`_reference_date`), NO contra "hoy" del reloj. Si el dataset está desactualizado (más viejo que `STALE_DAYS=7`), el motor ya lo degrada en `data_quality()` — la capa de vitalidad no fabrica una "última venta" que no existe.

---

## 2. Cómo se integra como filtro (en TODOS los detectores)

**Principio:** antes de emitir un finding de *riesgo/oportunidad sobre un producto*, el detector consulta la vitalidad del SKU. El filtro es una capa transversal (no un detector nuevo).

**Reglas de filtrado por tipo de señal:**

| Tipo de señal | Si producto NO es vivo | Si producto es vivo |
|---|---|---|
| **Dependencia / concentración de producto** | **DESCARTAR** el riesgo (con explicación) | marcar con urgencia real (y ponderar por vitalidad) |
| **Cross-sell / oportunidad de venta** | **DESCARTAR** (no promover ventas de producto muerto) | evaluar normalmente |
| **Bajo margen / margen gap** | **DESCARTAR** (un muerto no pierde margen) | evaluar normalmente |
| **Stock-out / reposición** | **DESCARTAR** (no se repone lo que no vende) | evaluar con urgencia (si aplica stock) |
| **Caída / declive de producto** | evaluar solo si hubo ventas previas y ahora no (transición a muerto) → "producto en declive", no "muerto" | evaluar tendencia normal |

**Regla del "porqué en €" (diferencial de inteligencia):**
Cuando una señal se descarta por vitalidad, se **emite igualmente pero con `kind="no_signal"`** y una explicación en lenguaje de negocio + el dato de vitalidad que la descartó. Ejemplo:
```
[Descartada] Dependencia de "Agenda 2025" — no es un riesgo real
  Este producto no se vende en los últimos 90 días (última venta hace 214 días).
  Concentra revenue histórico, pero de algo que ya no se vende. Sin riesgo real en €.
```
Así el empresario ve que el sistema "piensa", no solo que no le muestra nada.

**Detección de "producto en declive → muerto":** si un producto tuvo ventas en el pasado (ventana más amplia, ej. 180 días) pero 0 en los últimos 90, es señal de "producto muriendo" (no "riesgo activo"): se emite como hallazgo informativo de **declive**, no como riesgo de dependencia. Evita el falso positivo del ejemplo.

---

## 3. Regla de honestidad (degradar, no inventar)

- Si NO hay datos de pedidos con fecha (`sales` vacío o sin `date`): **la capa no puede calcular vitalidad**. Comportamiento: **deshabilitar el filtro de descarte** y degradar el finding a `kind="estimated"` con nota "No hay suficientes datos de ventas para validar la vitalidad de este producto." **NUNCA se inventa una vida que no existe.**
- Si el dataset está desactualizado (`STALE_DAYS`, >7 días desde la última fecha): `data_quality()` ya degrada; la capa de vitalidad respeta ese estado.
- El "última venta" nunca se fabrica: sale del timestamp real de `date` del pedido.

---

## 4. Criterios de aceptación (para QA/Mathew)

- [ ] **Unidad vitalidad:** con un producto sin ventas en ≥90 días (dataset con fecha real), `es_vivo=False`; con ≥1 venta en la ventana, `es_vivo=True`.
- [ ] **Filtro de concentración:** dado un producto que concentra revenue histórico pero 0 ventas en 90 días, el motor **NO** emite "dependencia de un solo producto" como riesgo; en su lugar emite la señal descartada con explicación (`kind="no_signal"`).
- [ ] **Producto vivo:** con ventas recientes reales, la dependencia/concentración sí se emite (riesgo real).
- [ ] **Declive→muerte:** producto con ventas en 180d pero 0 en 90d se emite como "producto en declive" (no como riesgo de dependencia).
- [ ] **Degradación honesta:** si `sales` no tiene fecha (no se puede calcular vitalidad), NO se descarta; se degrada a `estimated` con nota.
- [ ] **Regresión:** la suite existente (`pytest`) sigue en verde; los tests de concentración previos se actualizan para cubrir el nuevo estado `no_signal`.

---

## 5. TAREAS PARA NICKX (priorizadas)

1. **P1 — Constante `VITALITY_WINDOW_DAYS = 90`** y función `product_vitality(sku, sales)` en `detection_engine.py` (usando `_reference_date` y ventana 90d).
2. **P1 — Aplicar el filtro en `detect_products`/concentración:** descartar dependencia sobre producto NO vivo, con emisión `no_signal` explicada.
3. **P1 — Señal de "producto en declive" (muere)**: cuando haya ventas previas (180d) y 0 en 90d.
4. **P2 — Integrar el filtro en cross-sell / margen / stock-out** (descarta los no vivos).
5. **P2 — Aplicar vitalidad como ponderador de urgencia** en la priorización (no solo filtro binario).
6. **P2 — Test unitarios** (`test_vitality.py`): los 5 casos de los criterios de aceptación.

---

**Decisión (Nico) → ya especificado.** Listo para que Nickx programe y Mathew valide.
