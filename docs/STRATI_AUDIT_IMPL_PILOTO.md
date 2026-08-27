# STRATI — AUDIT DE COHERENCIA + SECUENCIA MÍNIMA AL PILOTO + CHECKLIST DE RECLUTAMIENTO

**Autor:** Strati (estrategia/producto) · **Para:** Boss (decisión) → Nickx (implementación), Mathew (QA), Nico (reclutamiento)
**Versión:** 3.1.3 · **Fecha:** 2026-08-22 · **Regla:** Solo propuesta/diseño; el € sale solo de fuentes reales.

---

## 1. AUDIT DE COHERENCIA SPECS vs CÓDIGO 3.1.3

Verificado con grep/lectura del código. **No hay drift funcional que obligue a re-diseñar.** Los puntos que antes eran "dependencias delegadas" ya están implementados y coinciden con lo que mis SPECs definen:

| Punto | Código 3.1.3 (verificado) | Coincide con SPEC |
|---|---|---|
| `global_margin_pct` → enriquecimiento de oportunidades | `opportunity_catalog.py` lo recibe y lo usa en `_upside_for_cross_sell`/`resolve_cost` | ✅ Coincide con la corrección de Mathew (cross-sell se cuantifica `estimated`) |
| Botón "Declarar mi margen" en Home | `web/dashboard.html:2515` → `set-margin-quick` guarda `globalMarginPct` en `companyProfile.preferences` | ✅ Coincide con SPEC 1 Fase 4 (margen global como vía estimada) |
| Plantilla CSV de costes | `web/dashboard.html:2931` `prepareAction('cost_template')` | ✅ Coincide con SPEC 1 §7b.2 |
| Endpoint de impacto | `desktop/runtime/api_server.py:242` `/api/recommendations/impact` → `_recommendations_impact()` | ✅ Coincide con SPEC 2 |
| Shopify Dev Dashboard | `shopify_sync.py:29-53` intercambia `shpss_` (client secret) por `access_token` real vía OAuth grant | ✅ Coincide con SPEC 1 §7b.1 (token real, no manual) |
| `capturedEuro` UI | `web/dashboard.html:2882` `capturedEuro > 0` → "Valor capturado con VANOVA" | ✅ Coincide con SPEC 2 |

**Matiz de wording (NO drift funcional):** el SPEC 1 §3 decía "el margen global no llega a `detect_cross_selling`". Confirmado: `detection_engine.py` NO recibe `global_margin_pct` (0 hits), pero el enriquecimiento de € sí está en `opportunity_catalog.py`. La solución "propagar a la detección" que se propuso originalmente se resolvió de otra forma (en el catálogo de oportunidades), que es lo correcto. Ya corregido en el SPEC.

**Conclusión: NO hay drift que requiera re-diseñar.** Los SPECs 1, 2 y 3 son base válida y sin ambigüedad para Nickx.

---

## 2. SECUENCIA MÍNIMA VIABLE DE 1 SEMANA → PILOTO REAL (camino crítico)

Prioridad absoluta: llegar a que un piloto real vea su € real lo antes posible. Nada de backlog inflado.

| Día | Tarea (específica) | Espec | Quién |
|---|---|---|---|
| D1 | Conectar Shopify/Excel (fuente de ventas) + wizard multi-fase P0-P5 | SPEC 1 | Nickx |
| D1 | Verificar que "Declarar mi margen" (ya existe) deja el € visible en Home | SPEC 1 | Nickx |
| D2 | Alta manual de coste "una línea a la vez" (Pantalla 4b) → € actualiza en Home | SPEC 1 | Nickx |
| D2 | Procesar CSV de costes por SKU (cruce case-insensitive) | SPEC 1 | Nickx |
| D3 | Endpoint de impacto + tarjeta "€ capturado" en Home | SPEC 2 | Nickx |
| D3 | Vista "Recomendaciones seguidas" (pestaña propia) | SPEC 2 | Nickx |
| D4 | Registro de eventos del piloto + métrica "tiempo hasta el €" | SPEC 3 | Nickx |
| D4 | Verificación E2E: alta → conectar → margen/coste → € <15 min (Mathew) | 1,2,3 | Mathew |
| D5 | Puesta en marcha del piloto (reclutado por Boss/Nico) + demo guiada | SPEC 3 | Boss/Nico |

**Salida de la semana:** UN piloto real ha visto su € real en <15 min (o sabemos exactamente qué bloquea). Eso es el Go/No-Go del MVP.

---

## 3. DEFINICIÓN MÍNIMA DEL PILOTO — CHECKLIST OPERATIVA DE RECLUTAMIENTO

**Separación exacta: lo que es CONSTRUCCIÓN (Nickx) vs OPERATIVO (Boss/Nico).**

### 3.1 CONSTRUCCIÓN (Nickx) — ya está en los SPECs:
- [ ] Registro de eventos del piloto (log JSONL + timestamps)
- [ ] Métrica "tiempo hasta el €"
- [ ] (SPEC 2) Vista "Valor Capturado" y endpoint de impacto
- [ ] (SPEC 1) Onboarding + alta manual de coste

### 3.2 OPERATIVO (Boss/Nico) — NO se programa:

| Ítem | Qué se hace |
|---|---|
| **A quién** | 1 ecommerce Shopify con ≥20 pedidos/mes y coste por SKU (o dispuesto a cargarlo); dueño que decide pagar |
| **Qué se le dice** | Mensaje de invitación ya listo en `docs/STRATI_CIERRE_PRODUCTO.md` §3.1 ("prueba gratis 1 mes, ve tu € con tus datos, me das tu opinión honesta") |
| **Qué se le pide** | Cargar ventas reales + coste (o margen global), usar la app 5 días, dar feedback en 3 checkpoints, autorizar caso (o anónimo) |
| **Qué se le enseña** | Demo guiada de <15 min: conectar → margen/coste → ver € → marcar recomendación. Checklist de demo en SPEC 3 §5c |
| **Cómo se mide el €** | Tiempo hasta ver € (log), loop cerrado (recomendación marcada y medida), uso 30d, percepción + NPS simple + disposición a pagar |
| **Criterio de éxito** | VALIDADO = aha <15 min + loop cerrado + uso ≥5 días/mes + dice que pagaría. Se convierte en caso de venta (dato real + cita textual, con consentimiento) |

**Criterio "ready para escalar":** el piloto cumple TODOS los del VALIDADO. Si no, se itera sobre SPEC 1 (onboarding) o SPEC 2 (valor capturado) según la fricción.

---

*Documento de estrategia/producto de Strati. Solo propuesta; no ejecuté nada.*
