# STRATI — Petición de datos reales a Pablo (MOOVING PAPER)

**Autor:** Strati (estrategia/producto) · **Para:** Boss (decisión) → Pablo (datos) → Nickx (importar) / Mathew (validar)
**Fecha:** 2026-08-22
**Estado:** Documento listo para enviar a Pablo. La demo del cliente NO puede demostrar el "aha del €" en vivo hasta que llegue este dato.
**Regla:** VANOVA solo muestra € reales. Sin datos reales de MOOVING, no se fabrica ni un número.

---

## 1. Por qué hace falta este dato (una sola frase para Pablo)

VANOVA convierte las ventas + el coste de tus productos en una cifra clara: cuánto ganas o pierdes por producto. Sin tus datos reales, no hay cifra que mostrar — y esa cifra es lo que demuestra el valor en menos de 15 minutos.

---

## 2. Qué necesitamos (mínimo para desbloquear el € del aha)

| # | Dato | Formato | Obligatorio |
|---|------|---------|-------------|
| 1 | **Ventas / pedidos** (últimos 6–12 meses) | Excel o CSV: fecha, cliente, producto (SKU), cantidad, total | Sí |
| 2 | **Catálogo de productos** | Excel o CSV: SKU, nombre, precio de venta | Sí |
| 3 | **Coste por producto** | Excel o CSV: SKU, coste de compra | Sí — es lo que desbloquea el margen |
| 4 | Clientes (histórico) | Excel o CSV: nombre, historial | No (opcional, pero valioso) |

> Con **solo ventas + catálogo + coste por SKU**, VANOVA ya puede señalar: producto que deja menos margen, cliente dormido, ticket medio a la baja, y oportunidades de cross-sell con su € real.

---

## 3. Formato exacto del CSV de costes (para importar sin fricción)

UTF-8, separador `;` o `,`, primera fila = cabecera. Máx. 10.000 filas.

```
sku;coste;precio_venta;unidades_mes
SKW-A5-001;0,85;3,50;200
MAW-A7-001;2,34;6,99;120
```

- `sku` — coincide con el del catálogo (no importa mayúsculas/minúsculas).
- `coste` — número con decimales (coma ES o punto).
- `precio_venta` — opcional (si falta se usa el del catálogo).
- `unidades_mes` — opcional.

---

## 4. Qué NO necesita Pablo (para no marearle)

- No necesita saber de tecnología: solo exportar sus Excel habituales de ventas, el catálogo y los costes de compra.
- No se pide la contabilidad completa: con ventas + catálogo + coste por SKU basta para empezar.
- La contabilidad la lleva él (dato real de Boss): el coste por producto es lo único imprescindible de su parte.

---

## 5. Cómo se le pide (mensaje listo)

> Pablo, para que el sistema muestre tu negocio real y las oportunidades en euros, necesito 3 archivos tuyos de MOOVING:
> 1) Ventas o pedidos de los últimos meses (con fecha, producto y total).
> 2) Catálogo de productos (código/SKU, nombre y precio).
> 3) El coste de compra de cada producto.
> Se los dejo a mí la importación; tú solo exporta tus Excel como siempre. Con esto te veré el margen y las oportunidades en 15 minutos.

---

## 6. Importación en VANOVA (paso siguiente, para Boss/Nickx)

1. Importar los archivos como fuente **MOOVING PAPER** (nunca como mock — regla de honestidad).
2. El Detector de Oportunidades genera los € reales (cross-sell, margen, ticket) desde estos datos.
3. El dashboard pasa a `dataMode=real` con ventas + margen visibles en el Home → se demuestra el `<15min`.
4. Actualizar `docs/CASO_REAL_MOOVING.md` con los resultados reales.

---

## 7. Decisión de Boss

¿Se envía esta petición a Pablo ahora, en paralelo a que @hermes fije el entorno demo? Es la única vía para que la demo del cliente muestre el € real en vivo — el entorno fijado sola no basta (la DB buena no tiene snapshot de ventas/margen).
