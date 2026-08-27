# STRATI — HANDOFF DE EJECUCIÓN (estrategia → Nickx/Boss/Nico)

**Autor:** Strati (estrategia/producto) · **Para:** Boss (decisión), Nickx (implementación), Mathew (QA), Nico (decisión de negocio)
**Versión proyecto:** 3.1.1 · **Estado:** Handoff de ejecución — lo único pendiente es técnico (Nickx) y operativo (conseguir piloto). No queda diseño/producto abierto.
**Regla:** Solo propuesta/diseño. Nada de código. Datos honestos, nunca inventados. Español.

---

## 1. TABLA DE HANDOFF (ordenada por lo que DESBLOQUEA al piloto primero)

| # | Hueco pendiente | Dueño | Dependencia / bloqueador | Criterio de aceptación mínimo (del SPEC) |
|---|---|---|---|---|
| 1 | Captación de 1 piloto externo (ecommerce Shopify, ≥20 pedidos/mes + coste por SKU) | **Boss/Nico** | Contacto real; invitación ya en `STRATI_CIERRE_PRODUCTO.md` §3.1 | El piloto acepta y arranca (día 1: conexión + coste + ver €) |
| 2 | Consentimiento de testimonio del piloto | **Boss/Nico** | Que el piloto firme (texto en `STRATI_CIERRE_PRODUCTO.md` §3.2); si no, caso anónimo | Formulario firmado o flag "anónimo" |
| 3 | Instalador en PC stock (que el piloto use solo) | **Nickx** | Build/empaquetado funciona de forma autónoma | El piloto instala y abre VANOVA sin pasos manuales |
| 4 | Método de conexión Shopify (OAuth/link mágico vs token manual) | **Nickx** | UI actual; si hay OAuth usarlo, si no token manual con ayuda (SPEC 1 §7b.1) | Pantalla 2 conecta la tienda y trae datos en ≤60 s |
| 5 | Plantilla CSV de costes por SKU | **Nickx** | Crear/reutilizar con columnas de `STRATI_CIERRE_PRODUCTO.md` §1 | El no-técnico la descarga y la rellena (SPEC 1 §7b.2) |
| 6 | Mapa del coste desde FacturaScripts (`articulos.preciocoste`, BUG-033) | **Nickx** | Formato real del campo; conversión si procede (SPEC 1 §7b.3) | El coste llega al catálogo por SKU automáticamente |
| 7 | Endpoint de impacto (`GET /api/recommendations/impact`) o cálculo en frontend desde `recommendation_store` | **Nickx** | Store expone outcome/metricBefore/metricNow | `capturedEuro` = Σ deltas `improved` reales; NO suma no_change/worsened/unmeasurable (SPEC 2) |
| 8 | Fijar el precio del plan Pro 29 €/mes para el retorno neto | **PENDIENTE-NICO** | Decisión de negocio del precio; hasta que se fije, mostrar solo € capturado (SPEC 2) | Cuando `capturedEuro > 29 €` se muestra "retorno neto +Z €/mes" (si está fijado) |

---

## 2. SECUENCIA CRÍTICA para llegar al piloto (máx 10 pasos)

1. **Hoy-D1 (Boss/Nico):** enviar invitación al piloto externo 1 (`STRATI_CIERRE_PRODUCTO.md` §3.1) + conseguir su consentimiento (§3.2).
2. **D1-D2 (Nickx):** confirmar/crear la plantilla CSV de costes (§5) y el método Shopify (§4).
3. **D2-D3 (Nickx):** garantizar que el instalador abre en PC stock sin pasos manuales (§3).
4. **D2-D4 (Nickx):** verificar el endpoint de impacto (o que el frontend lo calcule desde el store) (§7).
5. **D3 (Boss/Nico):** si no hay consentimiento firmado → marcar caso como anónimo.
6. **Día de arranque del piloto (Día 1 del piloto):** acompañar la conexión (Shopify/Excel) + carga de coste por SKU; registrar timestamp "conexión OK → 1ª oportunidad vista".
7. **Mismo día:** si ve € real en <15 min → registrar "aha". Si no → fricción, ajustar SPEC 1 antes de seguir.
8. **Día 3 del piloto:** comprobar que marca ≥1 recomendación como hecha y que el sistema la mide.
9. **Día 15:** ver "Valor Capturado" con deltas reales (SPEC 2).
10. **Día 30:** métricas finales + señal "ready para escalar" (ve € <15 min + loop cerrado + uso ≥5 días/mes + dice que pagaría). Go/No-Go.

---

## 3. QUÉ PUEDE PRODUCIR ESTRATEGIA AHORA que destrabe

**Nada de producto pendiente en mi competencia que no dependa de Nickx/Boss.** Los 3 SPECs están detallados, cerrados y auditados. Lo que destraba es:
- **Operativo (Boss/Nico):** conseguir el piloto (tabla §1 #1 y #2; secuencia §2 paso 1).
- **Técnico (Nickx):** los ítems §1 #3-#7.
- **Pendiente-Nico:** el precio del plan Pro (es una decisión de negocio, no de diseño).

Por tanto, el trabajo de estrategia/producto está **completo**. El siguiente cuello de botella real es la **captación del piloto**, que es operativo de Boss/Nico, no de diseño.

---

## 4. Notas

- Toda la referencia de copy, plantillas y consentimiento está en `docs/STRATI_CIERRE_PRODUCTO.md`.
- Ningún número de € se inventa: el piloto y el sistema producen datos reales; si no hay dato, se muestra vacío honesto o "sin cuantificar".

*Documento de handoff de ejecución, generado por Strati. Solo plan/propuesta; no ejecuté nada.*
