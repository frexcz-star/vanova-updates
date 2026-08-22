# Changelog VANOVA

El formato sigue [Keep a Changelog](https://keepachangelog.com/es/1.1.0/).
Las versiones siguen [SemVer](https://semver.org/lang/es/).

## [3.1.2] — 2026-08-21

### Añadido — PRODUCTO (hacia el MVP vendible)

**Onboarding "aha" + flujo de costes simplificado**
- Panel "En juego este mes" en la Home: el momento "aha" (el € real del negocio al cargar), con titular + tarjeta de oportunidad cuantificada. (11ad4b1)
- Onboarding guiado al primer € con empty states graduados. (0654a06)
- **Margen global declarado**: el empresario puede indicar su margen en un solo campo y desbloquear el € sin coste por SKU. `estimated`, nunca `verified`. (0b11230)
- Margen global visible y editable desde la Home (badge + botón "Ajustar"). (23807eb, 52a41c7)
- Cross-sell cuantificado con margen global, distinguiendo `calculated` (coste real por SKU) de `estimated` (margen global declarado). (fe3e28d)

**UI "Valor Capturado" (cierre del loop)**
- Pantalla completa de Valor Capturado con contadores por outcome: mejoraron / sin cambio / empeoraron / sin dato. (a6e3d6b, b36b53b)
- Endpoint `GET /api/recommendations/impact` con `capturedEuro` + `capturedPct` (% sobre facturación real) + desglose honesto. (d6752dd)
- Empty state honesto: sin dato medible → "sin dato comparable", nunca un 0 € inventado.

**Empaquetado / operaciones**
- Autocontención del instalador verificada: el bundle Python embebido (3.11) arranca el runtime y el cloud por sí solo (HTTP 200), sin depender de Python/Node del sistema. (82004b0)
- Hermes degrada con gracia usando modelo `:cloud` si Ollama no está disponible (no fuerza descarga local). (01e7f30)
- `docs/EMPACADO_MVP.md` actualizado con el estado honesto del primer arranque.

### Corregido
- Aislamiento de tests: `test_proactivity_e2e` dejaba de depender del orden de ejecución (no filtraba insights por el archivo de acciones real). (426e6c5)
- `save_profile` hace merge en vez de sobrescribir (un PATCH parcial de `preferences` ya no borra identity/channels). (0b11230)

### Notas de honestidad
- El € y el "Valor Capturado" salen **solo** de fuentes reales (Shopify/ERP/Excel/FacturaScripts). Nunca se inventa un 0 € ni un KPI.
- `capturedPct` se calcula solo si hay facturación real; si no, es `None`.
- El retorno neto (€ capturado − coste VANOVA) se añadirá cuando se fije el precio del plan.

## [3.1.1] — 2026-08-21

### Corregido
- "cloud start failed": regeneración automática de la contraseña débil por defecto en `_ensure_env_files` (BUG-031).

## [3.0.9] — 2026-08-21

### Corregido
- Múltiples correcciones del ciclo QA→Dev (BUG-028 a BUG-034) incluyendo persistencia de archivos y costes.
