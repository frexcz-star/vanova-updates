# STRATI — CHECKLIST DE DEMO DEL PILOTO (qué debe funcionar en la demo)

**Autor:** Strati (estrategia/producto) · **Para:** Boss/Nico (ejecución de la demo) · **Base:** v3.1.7, verificado contra código.
**Regla:** la demo se hace con datos reales del piloto conectados, nunca con mock presentado como real. El € sale solo de fuentes reales.

## ✅ YA LISTO (verificado en código)

| Elemento | Evidencia | Qué debe verse en la demo |
|---|---|---|
| Dashboard con datos reales | Conexión Shopify/Excel ya implementada (token manual + Dev Dashboard, `shopify_sync.py`) | Productos/pedidos/clientes reales del piloto, con badges real/sample |
| **Hero "Valor Capturado"** | `web/dashboard.html:1339` — "Valor Capturado por VANOVA" ya existe en el Home | El € capturado como protagonista |
| Botón "Declarar mi margen" | `set-margin-quick` en `web/dashboard.html:2515` — vía corta al "aha" | El titular "≈ X € en juego" aparece en <15 min |
| Endpoint impacto | `GET /api/recommendations/impact` (api_server.py:242, verificado HTTP 200) | € capturado real con deltas improved |
| Alertas/Insights | Vista Insights + "Riesgos activos" (dashboard.html:1348) | Riesgos/oportunidades con € |
| Recomendaciones | Pestaña propia "Recomendaciones" (ya decidida) | Cada una con su delta en € |
| Wizard con barra de progreso | `.s-step`/`.s-progress`/`.setup-step` (dashboard.html §638-698) | "Paso X de 5" visible |
| Contador notificaciones | Ya verificado por Nickx (BUG-057 cerrado, dashboard servido 3.1.7) | Badge correcto y actualizado |

## ❌ FALTA (bloqueos de la demo, en orden de desbloqueo)

| Elemento | Qué falta | Quién |
|---|---|---|
| **Datos reales de Shopify conectados** | Conectar la tienda del piloto REAL (no demo mock). Requiere: token del piloto + su consentimiento firmado | Boss/Nico + piloto |
| **Coste cargado (SKU o margen)** | Sin coste, el titular queda en UNKNOWN honesto. Pedir al piloto su margen global (vía corta) o su CSV de costes | Piloto + Nico |
| **Instalador en PC del piloto** | Verificar que instala y corre solo en su equipo (hardware débil OK) | Nickx/QA |
| **Precio Pro fijado** | Para mostrar el retorno neto en la demo (si no, solo € capturado) | Nico |

## ⚠️ Nota honesta

- La demo del día 1 con el teaser demo etiquetado "Ejemplo" está diseñada (SPEC 3 §5d) para el primer contacto ANTES de conectar datos reales. Pero la demo real del piloto debe ser con SUS datos.
- Si el piloto no trae datos a la demo: usar el teaser demo etiquetado (nunca como dato real) y agendar segunda sesión con sus datos conectados.

---

*Checklist de demo generado por Strati. Solo propone/diseña; no ejecutó nada.*