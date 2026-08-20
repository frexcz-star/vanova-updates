# FASE 16 — Prueba REAL de VANOVA con empresa ficticia (NOVA HOME & TECH SL)

**Fecha:** 2026-08-16 · **Objetivo:** intentar ROMPER VANOVA con un dataset sintético coherente
y medir si el producto detecta problemas empresariales reales de extremo a extremo
(import → normalización → reconciliación → calidad → detección → dashboard → Hermes).

**Regla de oro respetada:** la instalación real (BlisArtPaper) NO se tocó.
Se hizo backup autorizado antes, todo corrió en un sandbox aislado (`LOCALAPPDATA` temporal),
y el config real quedó byte-igual al backup al terminar (461 productos / 99 pedidos / 414 costes).

---

## 1. Archivos generados (en `synthetic-data/`, fuera del repo de release)

| Archivo | Registros |
|---|---|
| NOVA-HOME-TECH-productos.csv | 149 productos |
| NOVA-HOME-TECH-ventas.csv | 1.742 pedidos / 1.742 filas línea |
| NOVA-HOME-TECH-clientes.csv | 243 clientes |
| canonical-connector.json | 25 proveedores · 370 facturas (131 emitidas + 239 recibidas) · 239 líneas de factura · 278 movimientos de tesorería |
| MANIFEST.json | Documentación de anomalías y relaciones (no se importa como dato) |
| DETECCION.json | Salida del motor (integrity + quality + findings + timings) |
| HERMES.json | Respuestas reales del LLM a la batería de preguntas |

**Empresa ficticia:** NOVA HOME & TECH SL — e-commerce de hogar y tecnología.
Distribución realista tipo Zipf: pocos productos venden mucho, la cola vende poco pero estable.

---

## 2. Cómo resetear VANOVA a estado de primera ejecución (entorno aislado)

1. **Backup** de la instalación real (config + integraciones) — ya hecho en `release/synthetic-backups/VANOVA-REAL-BEFORE-SYNTHETIC`.
2. **Aislar**: `LOCALAPPDATA` apuntando a un directorio temporal → `paths.data_dir()` resuelve todo (config, integraciones, datos) al sandbox. Ningún módulo toca la instalación real.
3. **Shadow del bridge de credenciales** (H30): crear `sandbox/hermes/.env` VACÍO como primer candidato de `hermes_env_path()`. Sin esto, el bridge de Hermes lee el `.env` REAL de `~/.hermes/` e importa Shopify real al sandbox (ver H30).
4. **Importar** los CSV + inyectar el modelo canónico → sync → detección → dashboard → Hermes.
5. **Restaurar**: borrar el sandbox. La instalación real nunca se modificó.

---

## 3. Anomalías intencionadas vs findings reales de VANOVA

| ID | Anomalía | Finding esperado | Resultado |
|---|---|---|---|
| A1 | NH-0101/0102 en caída (-97%/-81%) | product_declining | ✅ **DETECTADA** (severity high, con evidencia de revenue y unidades) |
| A2 | NH-0103 crecimiento (+766%) | product_growing | ✅ **DETECTADA** |
| A6 | Ticket medio al alza (+42%) | aov_change | ✅ **DETECTADA** (dirección correcta: "al alza") |
| A13 | Gasto extraordinario 18.500€ | expenses_growing | ✅ **DETECTADA** (+42,9% agosto vs julio) |
| A14 | 8 pagos grandes agrupados próximos | upcoming_payments_concentration | ✅ **DETECTADA** (34.814€ vencimientos vs 47.248€ cobros = 73,7%) |
| A19 | SUP-005 encarece precios | expenses_growing (parcial) | ✅ **DETECTADA** (mismo finding que A13 — el detector no distingue proveedor) |
| A3/A7 | Robot NovaClean: top revenue con margen 5% | high_revenue_low_margin | ❌ **NO DETECTADA** → H26 |
| A8 | NH-0122 margen negativo, revenue alto | high_revenue_low_margin | ❌ **NO DETECTADA** → H26 |
| A4/A5/A9/A10/A15-A18 | clientes, dead stock, coste=precio, margen negativo, deuda creciente, stock, dependencia proveedor | (no hay detector) | ⚠️ GAPS documentados (sin detector) |

**Precision / Recall aproximados** (sobre las 9 anomalías con detector existente):
- **Detectadas:** 6 (A1, A2, A6, A13, A14, A19)
- **No detectadas:** 3 (A3, A7, A8 — todas bloqueadas por H26)
- **RECALL ≈ 67%** · Falsos positivos reales: ~10 caídas de SKU de bajo volumen (5-16u/período) que son ruido de muestreo legítimo — el gate de 5 unidades no filtra productos de volumen bajo-medio.

---

## 4. Hallazgos del producto (bugs reales que golpean a cualquier cliente)

### H24 — Import parcial silencioso de CSV >64KB (CORREGIDO)
- **Causa raíz:** la UI manda `contentPreview` truncado a 64KB (`text.slice(0,65536)`); el extractor usaba SOLO el preview e ignoraba el archivo en disco → los CSV grandes se importaban incompletos sin error.
- **Fix:** `_extract_products/_extract_sales/_extract_customers` leen SIEMPRE el archivo completo del disco cuando existe; el preview solo clasifica el tipo.
- **Regresión:** `test_truncated_preview_never_truncates_import` (3000 filas con preview de 64KB → se importan las 3000).

### H25 — Gate de caída/crecimiento comparaba euros contra "5 unidades" (CORREGIDO)
- **Causa raíz:** `prevRevenue >= MIN_PERIOD_UNITS * 1.0` (≥5€) en vez de exigir ≥5 unidades → cualquier producto con 1-2 unidades caras entraba al gate → decenas de falsos "en caída".
- **Fix:** exige unidades reales (`prevUnits >= MIN_PERIOD_UNITS`) — coherente con el comentario original "evita muestras diminutas".
- **Regresión:** `test_tiny_sample_never_flagged_as_trend` ya existía; se validó el gate con unidades.

### H26 — Umbral de margen inalcanzable en catálogos amplios (DOCUMENTADO, no corregido)
- `HIGH_REV_SHARE = 0.15` exige que un producto tenga ≥15% del revenue total. Con 149 productos, el top producto tiene 6,6% → el finding `high_revenue_low_margin` (A3/A7/A8) NUNCA dispara en catálogos reales.
- **Regla de FASE 16:** no cambiar umbrales para obtener findings → se documenta como limitación de diseño. Recomendación: umbral dinámico (p. ej. share ≥ 2-3% O top-N con margen < X% del promedio).

### H27 — Comparación de gastos mes completo vs mes en curso parcial (DOCUMENTADO)
- `_expense_metrics` compara el mes en curso PARCIAL (16 días) contra el mes completo anterior → un gasto extraordinario real puede no superar al mes anterior.
- Se documenta; el detector funciona cuando la diferencia es grande (A13 sí disparó con +42,9%).

### H28 — Umbrales porcentuales en fracciones vs puntos (CORREGIDO)
- **Causa raíz:** `AOV_CHANGE_PCT = 0.10` y `EXPENSE_GROWTH_PCT = 0.25` se comparaban contra valores en PUNTOS de porcentaje (-3.2, 42.9) → umbral efectivo de 0.1% y 0.25% → el AOV disparaba con -3,2% (cualquier variación) y los gastos con +0,3%.
- **Fix:** comparar contra `AOV_CHANGE_PCT * 100` y `EXPENSE_GROWTH_PCT * 100`.
- **Regresión:** 4 tests en `ThresholdUnitTests` (AOV -3,2% sin finding; +15% con finding; gastos +5% sin finding; +40% con finding).

### H30 — El bridge de credenciales de Hermes contamina entornos aislados (MITIGADO en test)
- `sync_shopify_from_hermes_if_needed()` lee el `.env` REAL de Hermes (`~/.hermes/.env` o `LOCALAPPDATA/hermes/.env`) y puede importar Shopify real en CUALQUIER config activa. Durante la prueba, el sandbox absorbió 461 productos + 99 pedidos reales.
- **Mitigación en el entorno aislado:** shadow `.env` vacío. En producción el comportamiento es deseado (credenciales de Hermes → VANOVA); pero se documenta el riesgo para entornos de test/CI.

### H31 — Hermes contradice al motor: niega tesorería que el motor ya analiza (CORREGIDO)
- **Causa raíz:** el contexto de Hermes declaraba tesorería/facturación "no disponible" basándose SOLO en capacidades de conectores en vivo (FacturaScripts desconectado), ignorando `organizedInvoices`/`organizedFinance` del modelo canónico que el `detection_engine` SÍ usa (A14 fue detectado desde esos datos).
- **Fix:** el bloque CAPACIDADES FALTANTES reconoce los datos canónicos existentes: *"ya hay N facturas y M movimientos en el modelo canónico; la integración en vivo no está conectada"*.
- **Verificado con LLM real:** Hermes ahora responde "hay 370 facturas y 278 movimientos" y aclara que no hay saldo bancario en tiempo real (sin inventar).
- **Regresión:** `test_canonical_invoices_recognized_even_without_live_connector`.

---

## 5. Hermes — batería real (LLM) sobre el dataset sintético

| Pregunta | Tiempo total | Resultado |
|---|---|---|
| hola | 8,0 s | Respuesta casual correcta (ruta ligera, sin datos) |
| ¿Cuántos pedidos tengo? | 19,0 s | **1.742 pedidos** — coincide EXACTO con el canónico |
| ¿Cuánto he vendido? | 16,7 s | **264.003,13 € / 1.742 pedidos / ticket 151,55 €** — coincide EXACTO |
| ¿Qué productos venden más? | 15,5 s | Top 10 por revenue, cifras idénticas al canónico |
| ¿Qué problemas tiene mi empresa? | 15,7 s | Problemas con números reales, sin inventar |
| ¿Cuál es nuestro margen? | 17,4 s | Explica 96,1% con coste real y 3,9% sin → no inventa margen |
| ¿Cómo está nuestra tesorería? | 11,1 s | **H31 fix:** reconoce 370 facturas + 278 movimientos, integración viva desconectada, sin saldo inventado |
| ¿Cuál es nuestro saldo bancario? | 13,1 s | **No-alucinación PASS:** "no tengo saldo bancario real, no lo invento" |
| ¿Cuánto hemos facturado? | 11,9 s | Distingue facturación formal (no disponible) de ventas reales (sí) |

**Consistencia Hermes ↔ Dashboard:** los números de Hermes (1.742 pedidos, 264.003,13 €, ticket 151,55 €,
top productos) son idénticos a los datos canónicos que renderiza el dashboard — misma fuente, mismos valores.

**Matiz documentado:** en "¿Cuál es nuestro margen?" Hermes dice "margen NO calculable" cuando el 96,1% del
revenue SÍ tiene coste. La respuesta más honesta sería *"el margen calculable cubre el 96,1% del revenue"*
(regla de FASE 12). Se documenta como matiz de redacción, no como invención de datos.

**Latencia:** el LLM externo domina (11-24s). La ruta ligera FASE 15 funciona ("hola" no carga contexto).

---

## 6. Resultados clave

- **Integrity:** 0 issues (149 productos / 1.742 pedidos / 243 clientes / 370 facturas / 278 movimientos).
- **Calidad de datos:** costCoverage 89,9% · identityCoverage 100% · canAnalyze* = true.
- **Detección:** 14 problemas · 10 oportunidades · 13 positivos (37 findings).
- **Tests:** **423 passed, 1 skipped** (+6 regresiones: H24, H28×4, H31).
- **Config real:** intacto (461/99/414, idéntico al backup).

## 7. Problemas encontrados en el producto (resumen)

1. H24 (fijo): CSV >64KB se importaban parciales y silenciosos.
2. H25 (fijo): gate de tendencia con unidades mal → falsos declinantes.
3. H26 (diseño): high_revenue_low_margin inalcanzable con catálogos amplios.
4. H27 (diseño): gastos mes parcial vs completo.
5. H28 (fijo): umbrales porcentuales en fracciones vs puntos.
6. H30 (mitigado): bridge de credenciales contamina entornos de test.
7. H31 (fijo): Hermes negaba tesorería que el motor ya analizaba.

## 8. Recomendaciones prioritarias

1. **H26:** umbral dinámico de revenue share para margen (o top-N con margen < promedio - X puntos). Es el mayor hueco de detección en catálogos reales.
2. **Detectores faltantes** (A4/A5/A10/A15-A18): clientes que dejan de comprar, dead stock, margen negativo, deuda creciente por cliente, stock bajo/sobrestock, dependencia de proveedor. Son los gaps que el manifest esperaba y VANOVA aún no cubre.
3. **H27:** comparar gastos por período equivalente (mismo número de días), no mes natural.
4. **Matiz de margen:** cuando la cobertura es alta pero no total, Hermes debería decir "margen calculable para el X%" en vez de "no calculable".
5. **H30:** aislar el bridge de credenciales detrás de una bandera para entornos de test/CI.
