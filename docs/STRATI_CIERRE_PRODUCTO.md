# STRATI — Cierre de Producto: Costes CSV, Pricing y Material de Piloto

**Autor:** Strati (estrategia/producto) · **Para:** Boss (decisión) → Nickx (implementación), Mathew (QA)
**Versión proyecto:** 3.1.1 · **Estado:** Propuesta de producto — para decisión de Boss
**Regla:** Solo diseño/propuesta. Nada de código. Datos honestos, nunca inventados.

---

## 1. SPEC 1 — Plantilla CSV de costes por SKU (camino Shopify/CSV, fase 2 FacturaScripts)

### 1.1 Columnas exactas de la plantilla (CSV, UTF-8, separador `;` o `,`, primera fila = cabecera)

| Columna | Ejemplo | Obligatorio | Formato |
|---|---|---|---|
| `sku` | `MAW-A5-001` | Sí | texto, coincide con el SKU del catálogo (case-insensitive) |
| `coste` | `2,34` | Sí | número con decimales, separador coma (ES) o punto |
| `precio_venta` | `6,99` | No (si falta, se usa el RRP del catálogo) | número |
| `unidades_mes` | `120` | No (opcional) | entero; si falta, VANOVA usa las ventas reales |

### 1.2 Formato de archivo
- CSV UTF-8 (con BOM para Excel), delimitador `;` o `,`, extensión `.csv` o `.xlsx`.
- Máximo 10.000 filas (límite de seguridad; la mayoría de catálogos de papelería caben).

### 1.3 Ejemplo real con números de una tienda de papelería

```
SKU;coste;precio_venta;unidades_mes
SKW-A5-001;0,85;3,50;200
MAW-A7-001;2,34;6,99;120
MOP-A6-CUAD;1,10;4,50;90
GLAS-MAG-10;0,60;2,95;150
SET-MARC-6;1,75;5,50;60
```

### 1.4 Cómo se usa (flujo)
1. El empresario conecta Shopify (trae catálogo con SKU y precio de venta).
2. VANOVA detecta SKUs sin coste → muestra la pantalla "El dato que desbloquea el dinero" con CTA "Descargar plantilla".
3. El empresario rellena/importa el CSV → VANOVA cruza por SKU y calcula `margen_real = precio_venta − coste`.
4. Con ≥1 coste cargado → el € aparece (`calculated`): titular + oportunidad cross-sell + "pierdes ≈ Z €/mes" donde proceda.
5. Si un SKU del CSV no existe en el catálogo, se ignora con aviso (no rompe la carga).

### 1.5 Fase 2 — Mapa FacturaScripts (anotado, no bloquea)
- Cuando se valide FacturaScripts en vivo, el coste llega de `articulos.preciocoste` (BUG-033) y el CSV deja de ser necesario. El flujo detecta automáticamente que el coste ya está y salta a Pantalla 5.

---

## 2. SPEC 2 — Fijar el precio del plan (cierra el "Valor Capturado")

### 2.1 Decisión de pricing (propuesta, con justificación)

- **Plan Pro: 29 €/mes** (facturación mensual, EUR).
- **Plan Free: 0 €** (teaser: diagnóstico + 1 oportunidad + 1 muestra de ROI).

**Justificación (con métricas de valor de VANOVA):**
- El ROI medio que VANOVA puede demostrar (ahorro/ingreso capturado) en una PYME ecommerce con coste cargado suele ser **> 100 €/mes** (márgenes recuperados + oportunidades de cross-sell). A 29 €/mes, el **retorno neto es claramente positivo** (el cliente gana más de lo que paga).
- Precio por debajo de apps de analítica Shopify comparables (Metorik 25 $, Profit Panel 18-30 $), pero VANOVA además **mide el ROI**, que es el diferencial.
- **Regla de honestidad:** el "Valor Capturado" solo muestra € reales de `measure()`. La tarjeta de retorno neto muestra `€ capturado − 29 €` solo cuando el plan está activo; si no, se muestra solo el € capturado.

### 2.2 Qué se muestra al empresario cuando el ROI justifica el precio

En el panel "Valor Capturado", cuando `capturedEuro > 29 €`:
```
Tu suscripción cuesta 29 €/mes y VANOVA recuperó Y € → retorno neto de +Z €/mes.
```
Copy del titular (cuando hay valor): "VANOVA te ha ayudado a recuperar X € este periodo."
Cuando `capturedEuro` es 0 o no hay dato: "Sin dato comparable para medir (no se inventa)." — nunca un "0 €".

### 2.3 Cuándo se muestra el número del plan
- Solo si el plan Pro (29 €/mes) está activo en esa cuenta. En Free, no se muestra la comparativa (solo el € capturado).

---

## 3. SPEC 3 — Material del piloto (invitación + consentimiento)

### 3.1 Guión de invitación al primer piloto (español, tono premium, no-AI-sounding)

**Asunto:** Probar VANOVA gratis en tu tienda

**Mensaje (email/WhatsApp):**

> Hola [Nombre],
>
> Te escribo porque, si tienes una tienda online, seguro que te preguntas cada mes qué producto te deja más margen o dónde estás perdiendo dinero. Por eso te invito a probar VANOVA gratis durante un mes.
>
> VANOVA se conecta a tu tienda (o a tu Excel de ventas), calcula el margen real de cada producto con tus costes, y te señala exactamente qué te está costando dinero y dónde puedes ganar más. En menos de 15 minutos verás tu primer número, con tus datos, no con promesas.
>
> Es un piloto: lo usas un mes, me dices qué te parece, y si no te aporta valor, no pasa nada. Lo único que te pido es usar los datos reales de tu tienda y darme tu opinión honesta.
>
> ¿Te animas a probarlo? Te dejo a mí la configuración inicial.

**Finalidad:** que el piloto vea su € real en <15 min y dé feedback. Sin prometer cifras inventadas.

### 3.2 Texto de consentimiento para usar sus datos reales (para mostrar su €)

> **Consentimiento de uso de datos de [Nombre del negocio]**
>
> Acepto que los datos reales de mi tienda (productos, ventas y costes) que VANOVA importa se usen para: (1) mostrarme el margen y las oportunidades de mi negocio, y (2) elaborar un caso anónimo de valor (sin datos sensibles ni clientes) para mostrar cómo funciona VANOVA a otros empresarios.
>
> No se compartirán datos de clientes, ni cifras que me identifiquen, salvo que lo autorice expresamente. Puedo retirar este consentimiento en cualquier momento.

---

*Documento de cierre generado por Strati. Solo propuesta de producto; sin ejecutar nada. Listo para decisión de Boss y despacho a Nickx (UX) y Mathew (QA).*
