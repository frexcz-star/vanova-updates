# BENCHMARK REPORT — FASE A (Business Value Challenge)

**Evaluación HONESTA revisada manualmente** sobre las 200 respuestas reales de
Hermes (40 por empresa) contra la GROUND TRUTH (que VANOVA nunca vio).

## Resumen ejecutivo

- **Problemas deliberados evaluados:** 24
- **✅ Detectados:** 2 · **🟡 Parciales:** 2 · **❌ No detectados:** 20
- **Recall (detectado+parcial):** 17%
- **Falsos negativos:** 83%
- **Falsos positivos:** 0 — el evaluador no cuenta como detectado nada que Hermes
  no haya identificado con datos reales (el matcher por palabras clave inicial
  inflaba resultados y fue descartado).
- **Hallazgo de infraestructura:** el motor de detección determinista
  (`detection_engine`) devolvió **0 findings** en las 5 empresas aunque los
  problemas existen en los datos (ver `snapshot.json`). Las pocas detecciones
  provienen de Hermes leyendo los datos, no del motor de detección.
- **Causa raíz de los no-detectados:** el contexto operativo de Hermes NO incluye
  stock por SKU, mapping/histórico de proveedores ni agregación por cliente.
  Hermes lo dice con honestidad ("no tengo ese dato"), pero no puede detectar
  problemas de inventario, proveedores ni clientes.

## Resultado por empresa

### empresa-1
- **P01** → ✅ DETECTADO
  - Evidencia: Q8: «LH-014 · Lámpara LED Nordic 60W — 590 uds, 73.987,95 €, margen 5,97% (coste 121,30 / PVD 129)»; Q29 «LA FUGA»; Q9 decisión: potenciar LH-007, no LH-014.
- **P02** → ❌ NO DETECTADO
  - Evidencia: Q7 lista top márgenes (LH-013, LH-005…) pero no destaca LH-031 Difusor Premium como oportunidad de baja rotación/alto margen.
- **P03** → ❌ NO DETECTADO
  - Evidencia: Q10: «necesito stock actual por SKU… NO DISPONIBLE». Hermes da velocidad de venta pero no puede calcular riesgo de agotamiento.
- **P04** → ❌ NO DETECTADO
  - Evidencia: Q16/Q17: «no hay datos a nivel de proveedor… no puedo afirmar que un coste haya subido». Q18 reinterpreta «renegociar» como coste de producto (LH-014) — dato real, pero no el problema introducido (SUP-LH-003 +60%).
- **P05** → ❌ NO DETECTADO
  - Evidencia: Q13/Q14/Q15: «no tengo agregación por cliente… no puedo nombrarte clientes sin inventar». No identifica al VIP ni al cliente que dejó de comprar.
- **P07** → 🟡 PARCIAL
  - Evidencia: Q4 detecta caída de ventas mensuales (Jun 41.636 → Ago 28.025, -21%) con caveat honesto sobre la ventana, pero NO identifica LH-048 Estantería Modular Oak como el producto en declive.

### empresa-2
- **M01** → ❌ NO DETECTADO
  - Evidencia: Q31/Q13: «no tengo agregación de rentabilidad por cliente». Q8 detecta productos de margen bajo (ID-014, ID-012) pero no al cliente grande.
- **M02** → ❌ NO DETECTADO
  - Evidencia: Q16/Q17: no hay datos de proveedor ni histórico; no detecta la dependencia de SUP-ID-001 (40 productos).
- **M03** → ❌ NO DETECTADO
  - Evidencia: Q10: ID-001 es la mayor rotación (587 uds) pero «stock actual NO está en los datos»; no detecta el riesgo de agotamiento.
- **M04** → ❌ NO DETECTADO
  - Evidencia: Q16/Q17: sin histórico de costes por proveedor; no detecta SUP-ID-004 +45%.

### empresa-3
- **I01** → ❌ NO DETECTADO
  - Evidencia: Q10/Q31: «niveles de stock NO están en el dataset… no puedo afirmar que te falte stock». No detecta TS-005 stock 0.
- **I02** → ❌ NO DETECTADO
  - Evidencia: Q32 llama a TS-077 «tu cable estrella» (al revés del sobrestock real de 8.400 uds); sin stock por SKU no detecta el exceso.
- **I03** → ❌ NO DETECTADO
  - Evidencia: Q36: «no tengo la fecha de la última venta de cada producto»; no detecta TS-120 VGA (dead stock 3.200 uds).
- **I04** → ❌ NO DETECTADO
  - Evidencia: Q10/Q31: sin stock por SKU no detecta TS-001 (stock 4, alta rotación).
- **I05** → ❌ NO DETECTADO
  - Evidencia: Q16/Q17: sin histórico por proveedor; Q18 reinterpreta como margen de producto. No detecta SUP-TS-006 +50%.

### empresa-4
- **F01** → ❌ NO DETECTADO
  - Evidencia: Q22: «no hay serie temporal de gastos… no se puede determinar qué gastos están creciendo». No detecta el alquiler 1800→2605 ni los servicios 600→1104.
- **F02** → 🟡 PARCIAL
  - Evidencia: Q21 detecta «riesgo financiero» general (concentración en PM-001, sin visibilidad de caja) pero NO la deuda creciente por facturas impagadas (Q33: FacturaScripts desconectado).
- **F03** → ❌ NO DETECTADO
  - Evidencia: Q16/Q17: sin mapping SKU→proveedor ni histórico; no detecta SUP-PM-002 +55%.
- **F04** → ❌ NO DETECTADO
  - Evidencia: Q11/Q12: sin stock por SKU no detecta PM-020 Abrigo (stock 220, demanda 0,5×).

### empresa-5
- **D01** → ❌ NO DETECTADO
  - Evidencia: Q32: «no hay productos duplicados». El CSV tenía MS-003 duplicado (47 filas) pero el import deduplicó a 46, así que el dato sucio no llegó al modelo.
- **D02** → ❌ NO DETECTADO
  - Evidencia: Q33: «los 46 productos tienen todos SKU». El producto sin referencia del CSV se perdió en la normalización (47→46).
- **D03** → ✅ DETECTADO
  - Evidencia: Q23: «77,3% del revenue con coste verificado, 9 productos sin coste MS-011..MS-018»; Q34: margen no calculable para el 22,7%; Q39 lista los productos sin coste.
- **D04** → ❌ NO DETECTADO
  - Evidencia: Q35: «no hay análisis de duplicados en los datos». El email duplicado del CSV (121→120 clientes) se deduplicó en el import; Hermes no puede detectarlo.
- **D05** → ❌ NO DETECTADO
  - Evidencia: Q36 flagga ORD-E5-00002 (9,50 €) y la numeración, pero NO el total incoherente ×2,3 del ORD-E5-00006; además solo ve 5 de 180 pedidos.

## Resultado por pregunta

Las 200 respuestas completas están en `benchmark-results/{empresa}/answers.json`
(40 por empresa). La clasificación por problema (arriba) se hizo leyendo el texto
completo de cada respuesta relevante (`benchmark-results/_review_dump.txt`).

## Problemas correctamente detectados

1. **P01 (E1) — ancla con margen 6%**: LH-014 identificado con cifras exactas
   (590 uds, 73.987,95 €, 5,97%) y decisión accionable (potenciar LH-007, renegociar LH-014).
2. **D03 (E5) — costes faltantes**: 77,3% de cobertura, 9 productos listados, margen
   correctamente bloqueado para el 22,7% restante.

## Problemas parcialmente detectados

1. **P07 (E1)**: detecta la caída de ventas mensuales (-21% jun→ago) con caveat honesto,
   pero no el producto específico en declive (LH-048).
2. **F02 (E4)**: señala riesgo financiero general (concentración, sin visibilidad de caja)
   pero no la deuda creciente por facturas impagadas.

## Problemas NO detectados (20)

Inventario (P03, M03, I01, I02, I03, I04, F04): Hermes no recibe stock por SKU.
Proveedores (P04, M02, M04, I05, F03): Hermes no recibe mapping ni histórico de proveedores.
Clientes (P05, M01, D04): Hermes no recibe agregación por cliente ni análisis de duplicados.
Gastos/tesorería (F01, F02): sin serie temporal de gastos ni FacturaScripts conectado.
Datos sucios (D01, D02, D05): el import deduplica silenciosamente (47→46 productos,
121→120 clientes), ocultando la suciedad antes de que la gobernanza pueda marcarla;
D05 se detectó un pedido raro distinto al introducido.

## Falsos positivos

0 con la evaluación manual. (El matcher automático inicial arrojaba varios, y fue
descartado por sobrecontar menciones de SKU como detecciones.)

## Alucinaciones

No se observaron cifras inventadas. Hermes respondió consistentemente con la política
HECHO / INFERENCIA / NO DISPONIBLE y rechazó inventar stock, deudas o tendencias.

## Datos que VANOVA consideró fiables cuando no debía

- En E5, Hermes afirmó «no hay productos duplicados» y «todos tienen SKU» porque el
  import ya había deduplicado el catálogo (47→46). La afirmación es coherente con lo
  que ve, pero oculta un problema real de calidad en el archivo original.

## Datos que VANOVA rechazó correctamente

- Margen global en E5 (bloqueado: 22,7% sin coste).
- Deudas/tesorería en E4 (FacturaScripts desconectado → «no puedo determinarlo»).
- Stock y rotación en E1–E4 (dato ausente → no lo convierte en 0).
- Aumentos de coste de proveedor en todas (sin histórico → no afirma tendencia).

## Decisiones empresariales útiles

1. P01: «potencia LH-007, no LH-014; renegocia el coste de LH-014» (cifra el impacto: +5.900 €).
2. E1 Q30: oportunidad de +10 €/ud sobre 590 uds = +5.900 € de margen.
3. D03: lista exacta de productos a los que falta coste (acción: cargar coste real).

## Decisiones empresariales incorrectas

- E3 I02: llamar a TS-077 «tu cable estrella» (es el producto con 8.400 uds de sobrestock) —
  no es un consejo falso, pero omite por completo el problema de capital inmovilizado.

## Limitaciones de VANOVA detectadas

1. **El motor de detección no dispara** (`findings: 0` en las 5 empresas): no detecta
   churn, dead stock, sobrestock, dependencia de proveedor ni gastos por categoría.
2. **El contexto operativo de Hermes no incluye stock, proveedores ni clientes** —
   por eso los problemas de esas dimensiones no se detectan aunque existan en los datos.
3. **El import deduplica silenciosamente** (E5 47→46 productos, 121→120 clientes),
   ocultando duplicados antes de que la gobernanza pueda marcarlos.
4. Hermes solo ve top-10 de productos en contexto; problemas en la cola larga (dead stock,
   baja rotación) quedan invisibles.

## Problemas de UX / integración / Hermes

- **UX**: Hermes a menudo responde «¿quieres que consulte get_X?» pidiendo permiso en vez de
  ejecutar la tool — buena honestidad, pero UX lenta para el empresario.
- **Integración**: el flujo de benchmark no pasó stock/inventario ni proveedores al modelo
  (el conector canónico de prueba no los exporta a Hermes); FacturaScripts sigue bloqueado.
- **Hermes**: la ruta ligera responde «no tengo datos en este turno» en preguntas ambiguas,
  aunque los datos existan (falta de routing a la ruta completa).

## Métricas

- **% de respuestas correctas:** las respuestas factuales (revenue, top productos, cobertura)
  fueron correctas en las 200; el % de problemas detectados es {round(detected/total*100)}%.
- **% de problemas detectados (recall):** 17%
- **% de falsos positivos:** 0%
- **% de falsos negativos:** 83%
- **% de respuestas accionables:** alto en las preguntas de producto/margen (P01, D03);
  bajo en inventario/proveedores/clientes (se devuelve «no tengo el dato»).
- **% que reconocen falta de datos:** alto — Hermes lo hace explícitamente en stock,
  proveedores, tesorería y deudas (comportamiento honesto, sin inventar).

## Conclusión

VANOVA **responde con honestidad y precisión sobre lo que ve** (revenue, top productos,
márgenes, cobertura de costes) y **nunca inventa** — eso es real y valioso. Pero su
**valor de detección empresarial automática es bajo hoy**: el motor determinista dio 0
findings y los problemas de inventario, proveedores y clientes no se detectan porque esos
datos no llegan al contexto de Hermes. La mayoría de problemas solo emergen si el
empresario hace la pregunta exacta, y aun así muchos quedan en «no tengo ese dato».

**Veredicto del experimento ciego:** VANOVA es un lector honesto de datos, no todavía un
detector proactivo de problemas de negocio. Recomendación prioritaria: alimentar el
contexto con stock/proveedores/clientes y reactivar el motor de detección con los
detectores que faltan (churn, dead stock, sobrestock, dependencia de proveedor, gastos).
