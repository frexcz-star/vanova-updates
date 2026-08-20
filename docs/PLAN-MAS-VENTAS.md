# VANOVA — Plan para conseguir más ventas

**Empresa:** MOOVING PAPER
**Fecha:** 2026-08-14
**Fuente:** Datos reales sincronizados en VANOVA (dataMode: real) + insights internos del CEO Copilot/Inventory Agent
**Filosofía:** No inventar datos. Medir primero, crecer después. Cero cifras fabricadas.

---

## 1. Estado real verificado (no estimado)

| Dato | Valor |
|------|-------|
| dataMode | real (conectado) |
| Productos totales | 414 SKUs (199 local/Excel + 50 online) |
| Con precio de coste/venta cargado | 0 de 414 |
| Con stock cargado | 0 |
| Pedidos online sincronizados | 50 |
| Ingresos online (según reporte 1.0.2) | ~1.756€ |
| Pedidos locales capturados | 0 |
| Licencia MAW Mania | 113 SKUs (~27% del catálogo) |

### Diagnóstico del sistema
- El **CEO Copilot ya marcó (high)** que hay "falta de conexión de datos reales de ventas: pricing a ciegas". Sin margen real por SKU no se puede optimizar ni precio ni mezcla.
- El **Inventory Agent** confirma: 414 SKUs, 0 stock, 0 precio → sin alertas de reposición ni reorders con datos reales.
- Conclusión honesta: hoy el freno no es marketing, es que VANOVA no mide márgenes por SKU ni rotación por licencia.

---

## 2. Fase A — Medir (desbloqueador, prioridad 1)

**Objetivo:** saber qué series/licencias dejan margen de verdad.

1. Cargar precios de coste + venta por SKU (fuente ERP o Excel).
   - 0/414 SKUs tienen precio hoy. Sin esto, todo lo demás es a ciegas.
2. Segmentar el reporte por SKU + licencia/colección.
3. Calcular margen de contribución por serie (no solo por unidad).
4. Con los 50 pedidos online, identificar:
   - Las 2–3 series que más rotan.
   - Las 2–3 que más margen dejan (pueden no coincidir).
5. Priorizar stock y publicidad SOLO en esas 2–3. Recortar o replantear baja rotación.

> Nota interna VANOVA: en papelería con licencia, el 80–90% del margen bruto suele concentrarse en la marca licenciada. El papel casi no deja diferencial. (Insight ejecutivo ya cargado.)

---

## 3. Fase B — Crecer (palancas de bajo coste)

### B1. Monetizar la licencia MAW Mania (activo diferencial)
- 113 de 414 SKUs son de MAW Mania (27%).
- Agrupar por personaje/colección; detectar cuál concentra más pedidos.
- Crear packs/kits "colección" (ya existen bases: Kit 2 en 1, Glass Magnets, Clip dispenser, sets de señaladores).
- Objetivo: subir unidades por pedido sin más tráfico.

### B2. Subir ticket medio y frecuencia
- **Cross-sell:** combinar cuadernos (64 SKUs) + señaladores/marcadores MAW Mania de la misma colección.
- **Packs de estudio / vuelta al cole** (relevante en contexto gallego y temporada PAU).
- **Recompra:** papelería escolar es recurrente → recordatorio de reposición por colección (más barato que captar cliente nuevo).

### B3. Conectar contenido a ventas
- Cruzar cada pico de pedidos con el Reel/colección publicado esa semana.
- Duplicar el formato que más convierta, no el que más vistas dé.
- El dato de pedidos decide el contenido, no el instinto.

---

## 4. Acciones automáticas lanzadas

- **Cronjob semanal** de ranking de SKUs/series más vendidos desde los datos sincronizados en VANOVA, para arrancar la medición en curso.
- Se generará ranking por unidades y (cuando haya precios) por margen.

---

## 5. Próximo paso crítico

**Cargar precios de coste/venta por SKU** (ERP o Excel). Es la única dependencia que no se puede automatizar sin la fuente. El resto del plan se sostiene sobre ese dato.

---

*Documento generado por el orquestador VANOVA. Sin cifras inventadas: todo lo anterior es dato real o palanca estructural del sector.*
