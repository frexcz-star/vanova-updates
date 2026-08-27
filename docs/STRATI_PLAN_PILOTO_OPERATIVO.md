# STRATI — PLAN DE PILOTO OPERATIVO (reclutamiento accionable)

**Autor:** Strati (estrategia/producto) · **Para:** Boss/Nico (ejecución) · **Referencia:** SPEC 3 (`STRATI_ESPEC_PILOTO.md`)
**Base:** v3.1.7, verificado contra código. **Regla:** NUNCA inventar €/métricas/citas; todo de fuente real con consentimiento.

Este plan es OPERATIVO (lo ejecuta Boss/Nico, no yo). El diseño de la prueba ya está en el SPEC 3; aquí está el cómo reclutar y ejecutar.

---

## 1. Perfil objetivo del piloto (criterio de selección)

| Criterio | Valor | Por qué |
|---|---|---|
| Sector | Ecommerce (Shopify preferido) | El conector real ya está (token/Dev Dashboard) |
| Tamaño | PYME, ≥20 pedidos/mes | Base mínima para detectar oportunidades |
| Coste | Que pueda cargar coste por SKU o declarar margen | Sin coste el € queda UNKNOWN (SPEC 1 §7b) |
| Decisor | El dueño (no delegado) | Es quien vive el "aha" y decide pagar |
| Dolor | No sabe su margen real / cree que "todo es margen X" | Esa brecha percepción→dato es la evidencia del valor (SPEC 3 §4c) |

**Nº de pilotos:** 1-2 (un piloto externo como mínimo viable).

---

## 2. Lista de 3-5 ecommerce reales cercanos (canal de reclutamiento)

> No invento nombres ni acuerdos. Esta es la lista de **canales donde buscar**, no empresas inventadas.

1. Red del equipo/coworking/comunidad local (ecommerce Shopify cercano).
2. Ecommerce de clientes/proveedores conocidos de MOOVING.
3. Comunidades de ecommerce locales (círculo emprendedor gallego).
4. Tiendas Shopify del entorno del dueño (no BlisArtPaper sin su permiso).
5. Redes sociales/foros de ecommerce regionales.

**Regla de honestidad:** cada candidato debe cumplir el perfil de la sección 1 y estar dispuesto a dar su € real con consentimiento. No se inventa una "empresa piloto".

---

## 2. Mensaje de invitación (listo para copiar, tono premium no-AI)

El guión completo está en `STRATI_CIERRE_PRODUCTO.md` §3.1. Resumen del tono (no se duplica el texto largo):

- Le explicamos en 1 frase qué es (AI OS que te muestra cuánto dinero pierdes/ganas).
- Le prometemos el "aha": ver su € real en <15 min.
- Le ofrecemos acceso gratis al piloto a cambio de usar el producto 30 días y darnos feedback.
- Sin compromiso ni pago durante el piloto.
- Consentimiento para usar su caso como testimonio (solo si firma; si no, anónimo).

**Timeline de reclutamiento (meta: ≥1 piloto externo en ≤10 días, objetivo 7):**

| Día | Acción | Responsable |
|---|---|---|
| 1 | Lista de 3-5 candidatos que cumplen el perfil + envío de invitación | Nico/Boss |
| 3 | Seguimiento (email/WhatsApp) | Nico/Boss |
| 7 | Cerrar el 1º que confirme | Nico/Boss |
| 7-10 | Arranque: demo guiada + consentimiento + conectar datos reales | Nico/Boss + Mathew (registro) |

**Si a los 14 días no hay ningún piloto:** es BLOQUEO de captación (no de producto) → replantear canal (ampliar comunidad, ofrecer incentivo, etc.). No se inventa un piloto.

---

## 3. Consentimiento (referencia)

El texto completo está en `STRATI_CIERRE_PRODUCTO.md` §3.2: se entrega al inicio de la demo (día 1); si lo firma, el caso puede usar su negocio con nombre; si no, reporte anónimo. Nunca compartir datos de clientes ni cifras que lo identifiquen sin autorización.

---

## 4. Timeline del piloto (30 días)

| Fase | Día | Qué ocurre | Qué se mide |
|---|---|---|---|
| Arranque | 1 | Demo guiada + consentimiento + conectar datos reales | Tiempo hasta ver € (<15 min), fricciones |
| Uso | 2-7 | El dueño usa el producto | 1ª oportunidad vista, 1ª recomendación marcada (pilot_events) |
| Mid-check | 7 | Checkpoint: ¿vio €? Si no → BLOQUEO corregir SPEC 1 | `metric_time_to_euro` |
| Uso | 8-29 | Loop activo: marcar → medir → ver € capturado | `capturedEuro`, uso diario |
| Cierre | 30 | Métricas finales + entrevista + caso | Validado vs No validado |

---

## 5. Plantilla de reporte de cierre Go/No-Go

| Bloque | Dato | Fuente (real, con consentimiento) |
|---|---|---|
| Aha | Tiempo hasta ver € | `metric_time_to_euro` (pilot_events) |
| Valor | € capturado real | `capturedEuro` (endpoint impact) |
| Uso | Días/mes que lo usó | pilot_events |
| Disposición | "¿Pagarías?" | Encuesta §7b SPEC 3 |
| Caso | Dato + cita textual + tiempo al € | Solo con consentimiento |

**Decisión:** VALIDADO (aha<15 + loop + uso≥5 días/mes + dice pagaría) → **escalar a venta**.
**NO VALIDADO** → BLOQUEO (no vio €) / PIVOT (no usa) / REVISAR PRECIO (no quiere pagar).

---

*Plan operativo generado por Strati. Solo propone/diseña; no ejecutó nada. Prioridad: destraba la venta.*
