# STRATI — Estrategia de Valor por Tipo de Negocio

**Autor:** Strati (estrategia/producto)
**Para:** Boss (decisión) · Nickx (posible implementación) · Mathew (QA)
**Versión proyecto:** 3.0.8 · **Estado:** Propuesta — pendiente de revisión del usuario
**Regla:** Documento de estrategia. NO es código; NO modifica el proyecto.

---

## 0. Resumen ejecutivo

VANOVA aporta valor real cuando el empresario puede señalar una cifra en € que le ayude a
crecer o a vender más, con datos honestos (nunca € inventado). Este documento define, por
tipo de negocio, las "descubiertas" de mayor valor que VANOVA puede mostrar, cómo se
cuantifican y qué conectores se necesitan.

**Tipos priorizados (por el usuario):**
1. **TIENDA ONLINE (Shopify)** — ataque nº1, dato conectado y validado.
2. **EMPRESA B2B** — ataque nº 2, margen de venta alto, contabilidad/FacturaScripts.
3. **Propuestos por Strati (1–2 de alto valor común):**
   - **Distribuidor / venta por mayorista (B2B mayorista)** — tan B2B pero con palancas
     de volumen y precios por cliente distintas.
   - **PYME de servicios (studio/taller con facturación)** — el segmento con más
     penetración de facturación electrónica y el que menos usa analítica; gran vacío.

> Propongo no añadir más de 2 para no dispersar. Los 4 cubren el mercado que se ataca
> primero con ROI evidente.

---

## 1. TIENDA ONLINE (Shopify)

### 1.1 Perfil del negocio
- PYME ecommerce que vende por Shopify. Opera con catálogo de productos (SKU, precio,
  coste), pedidos con `line_items`, clientes y tráfico/contenido. Datos online + local
  (Excel de catálogo/costes).
- Datos reales que ya importa VANOVA: productos Shopify + Excel, pedidos/ventas con
  `line_items`, `date`, `customer`, `total`.

### 1.2 Las 5 descubiertas de MAYOR valor (lenguaje de empresario)
1. **"Estos 2 productos se compran juntos con frecuencia — cruza o haz pack y sube el ticket."** (cross-sell ya en motor)
2. **"Un solo producto concentra el 26% de tus ventas: si cae, caes tú. Diversifica o sube precio al top."** (product_concentration)
3. **"Tu ticket medio baja porque vendes menos artículos por pedido — ahí tienes la palanca."** (aov_change / aov_multi_item_opportunity)
4. **"Este cliente te compraba cada mes y lleva 45 días sin pedido: reactívalo."** (cliente dormido — señales existentes)
5. **"Estos productos con margen alto venden poco: dales visibilidad o bundle."** (low_revenue_high_margin)

### 1.3 Beneficio en € / impacto (cuantificación honesta)
- **Cross-sell:** upside = (pedidos extra potenciales) × (margen medio por pedido). Solo si hay margen por SKU verificado; si no → `no cuantificable` (nunca 0 €).
- **Concentración:** impacto = `revenueAtRisk` del producto dominante (ya lo calcula el motor) + potencial de diversificar sustitutos (solo con evidencia).
- **AOV:** upside = (AOV_objetivo − AOV_actual) × pedidos del periodo, solo con dato; si no → `UNKNOWN ≠ 0`.
- **Reactivar cliente:** upside = (ticket medio de ese cliente) × (pedidos recuperables estimados) solo con historial real.
- **Alto margen/poco revenue:** upside = (revenue del producto) × (potencial de subir visibilidad), solo con margen verificado.

### 1.4 Datos / conectores
- **Shopify API** (conectado y validado en producción: productos, pedidos, `line_items`, SKU, costes).
- **Excel/CSV** para catálogo y costes por SKU (clave: cargar precio de coste/venta — deja de medir a ciegas).
- (Opcional) **Instagram** para cruzar pico de pedidos con contenido publicado.

### 1.5 Cómo se mostraría
- Home: **"Total capturado ≈ X € este mes"** (titular de venta).
- Vista "Oportunidades": tarjeta con "Cross-sell A+B = +2.1% ticket" + CTA "Marcar como hecha".
- Insight: "El 80% de tu ingreso depende de 1 producto: estos son los sustitutos en crecimiento."

---

## 2. EMPRESA B2B

### 2.1 Perfil del negocio
- PYME que vende a otras empresas: facturación recurrente, clientes concentrados, márgenes por cuenta, cobros/cobranza, stock B2B.
- Datos: contabilidad/facturación (FacturaScripts/ERP), Excel de clientes/pedidos, tesorería.

### 2.2 Las 5 descubiertas de MAYOR valor
1. **"El 60% de tu facturación son 3 clientes: si uno se va, caes. ¿Tienes plan?"** (concentración de clientes)
2. **"Estás vendiendo a pérdida en este cliente: el margen por producto no cubre el coste."** (margen por SKU/cliente con coste verificado)
3. **"Facturas en 60 días a 2 clientes grandes: aquí hay tesorería comprometida por X €."** (tesorería / pagos)
4. **"Un proveedor concentra el stock caro en 1 SKU: riesgo de rotura y de caja."** (stock/inventario)
5. **"Tienes gastos creciendo +25% sin más ingresos: revisa esta línea."** (expenses_growing ya en motor)

### 2.3 Beneficio en € / impacto
- **Concentración de clientes:** impacto = (facturación del cliente top) como **ingreso en riesgo**; con su historial y margen, upside de diversificar.
- **Margen por cliente:** impacto = (margen perdido/potencial) con coste verificado por SKU. UNKNOWN si no hay coste.
- **Tesorería:** impacto = (importe pendiente de cobro) × (coste de financiación del plazo) — solo con datos reales de facturas.
- **Stock:** impacto = (valor del inventario en el SKU crítico) como riesgo (inventoryValue ya en el motor).
- **Gastos:** impacto = (gasto creciente) a considerar como pérdida potencial; solo con números reales.

### 2.4 Datos / conectores
- **FacturaScripts** (conector existe; PENDIENTE de validar en vivo con servidor real).
- **ERP** (integrations_store lo contempla).
- **Excel/CSV** de clientes, pedidos, inventario y costes.
- **Email/Gmail** (skill bridge existe) para cobranza/proveedores.

### 2.5 Cómo se mostraría
- Dashboard financiero con "Ingresos a riesgo por concentración" y "Margen por cliente".
- Vista "Oportunidades": "Riesgo: cliente X = 60% de facturación → diversifica".
- Empty state honesto si no hay coste/cobros: "Conecta FacturaScripts para medir el margen real."

---

## 3. (Propuesta) DISTRIBUIDORA / VENTAS A MAYORISTA (B2B mayorista)

### 3.1 Perfil
- PYME mayorista que distribuye a retailers. Margen bajo por unidad pero volumen alto; la
  clave es la mezcla de producto (SKU que rota con margen) y la fuerza de la categoría.

### 3.2 Descubiertas de mayor valor
1. **"Estas 2 referencias se venden juntas en el canal: haz pack/beneficio por volumen."** (cross-sell)
2. **"El SKU A rota con margen de 40% y no le das stock: reordénalo antes de que pierdas venta."** (margen × rotación)
3. **"El 70% de tus reventas son 5 clientes mayoristas: plan de retención."** (concentración)
4. **"Tu margen por SKU cae por el coste del producto: revisa precio al canal."** (precio B2B)

### 3.3 Beneficio / impacto
- Idem B2B con foco en **rotación × margen por SKU**: upside = (rotación incremental estimada) × (margen unitario verificado).
- Concentración = ingreso a riesgo del top cliente.
- **Precio B2B:** impacto = (subir X% al top SKU) × (volumen) — solo con coste real.

### 3.4 Datos / conectores
- Excel de catálogo/rotación, FacturaScripts/ERP para clientes y facturas, Shopify si vende online también.

---

## 4. (Propuesta) PYME DE SERVICIOS / TALLER CON FACTURACIÓN

### 4.1 Perfil
- Negocio de servicios (taller, estudio, consultoría) que factura por horas/proyectos; datos en
  facturación electrónica + Excel. Casi no usa analítica — gran vacío a llenar.

### 4.2 Descubiertas de mayor valor
1. **"Estás infra-facturando este tipo de trabajo: el precio por hora de tu 'Servicio X' está por debajo de tu coste real."** (precio/margen de servicio)
2. **"El 80% de tu ingreso son 2 clientes: riesgo y palanca de diversificación."** (concentración)
3. **"Facturas 45 días tarde en estos 2 clientes: cash flow en riesgo."** (tesorería)
4. **"Tu gasto fijo crece +25% sin más clientes: revisa la estructura."** (gastos)

### 4.3 Beneficio / impacto
- **Margen por servicio:** upside = (precio correcto − precio actual) × (horas anuales) — solo con coste/hora real.
- **Concentración:** ingreso a riesgo del top cliente.
- **Tesorería:** importe pendiente × plazo.
- **Gastos:** gasto creciente como pérdida potencial.

### 4.4 Datos / conectores
- Facturación electrónica (FacturaScripts/ERP), Excel de horas/proyectos y gastos, Gmail para
  facturas/cobranza.

---

## 5. PRIORIZACIÓN (qué descubierta da el ROI más evidente primero)

| Orden | Descubierta | Tipo | ROI evidente | Esfuerzo |
|---|---|---|---|---|
| 1 | **Cross-sell / packs (subir ticket)** | Shopify + Distribuidora | ALTO — visible en € al instante | BAJO (motor listo, falta UI BUG-017) |
| 2 | **Concentración de producto/cliente (riesgo)** | Todos | ALTO — "esto puede caer" | BAJO |
| 3 | **Cliente dormido / reactivación** | Shopify, B2B | Alto — retención barata | MEDIO (nueva señal) |
| 4 | **Margen por SKU/cliente (pérdida real)** | B2B, Distribuidora, Servicios | Alto — requiere coste cargado | MEDIO (necesita coste verificado) |
| 5 | **Tesorería / cobros pendientes** | B2B, Servicios | Medio — desbloquea FacturaScripts | MEDIO (requiere validación FacturaScripts) |
| 6 | **AOV / multiproducto** | Shopify | Medio | BAJO (BUG-018 activarlo) |

**Regla de impacto:** las 3 primeras (cross-sell, concentración, cliente dormido) dan el ROI
más evidente y con el dato que ya existe (motor). Las de margen/tesorería requieren conector
validado (FacturaScripts) o coste cargado, así que se atacan tras validar.

---

## 6. CÓMO SE MUESTRA AL EMPRESARIO (qué le hace decir "esto vale")

- **Titular de €:** "Total capturado ≈ X € este mes" — el número que vende solo.
- **Tarjeta de oportunidad con €:** "Cross-sell A+B = +2.1% ticket" + CTA "€".
- **Un "Qué hacer hoy" de 3 items con su €** — acción, no panel.
- **Empty state honesto:** "Conecta Shopify/FacturaScripts para medir el margen real" —
  nunca un "0 €" inventado.
- **Cierre del loop:** marcar "Realizada" → el sistema mide y muestra si funcionó con tu data.

---

## 7. CONECTORES REALES (lo que ya existe en el repo)
De `desktop/runtime/integrations_store.py` (`VALID_IDS`): **shopify, erp, mcp, email,
instagram, gmail, drive, facturascript**. El dashboard ya lista Shopify (conectado y
validado), Excel/CSV (import local), FacturaScript, Drive, MCP, Email, Instagram.

**Gap honesto:** FacturaScripts NO está validado end-to-end con servidor real (pendiente);
Shopify sí está validado. Esto condiciona la prioridad: **Shopify (online) puede monetizarse
ya; B2B requiere validar el conector de facturación.**

---

## 8. NOTA DE CONTROL (regla del usuario)
Este documento es **solo propuesta**. No modifica el proyecto ni da órdenes a Nickx. El
usuario/Boss decide qué se implementa. Para actuar, priorizar:
1. BUG-017 (UI de oportunidades) + BUG-018 (activa `_upside_for_aov`) — destapan el € en Shopify ya.
2. Señal de "cliente reactivable" (nueva) para Shopify/B2B.
3. Validar FacturaScripts en vivo — desbloquea B2B/Servicios.
4. UI de Recomendaciones/Impacto + titular "Total capturado".

---

*Documento generado por Strati. No modifica el proyecto. Revisado por Boss y el usuario antes
de decidir implementación.*
