# EMPAQUETADO MVP — VANOVA para un empresario no-técnico

**Meta:** un empresario (sin Python, sin Node, sin saber qué es Hermes) instala
VANOVA en su PC y en pocos minutos ve el € de su negocio.

**Estado:** el empaquetado Electron ya está en gran parte construido (v3.0.8
publicada). Este documento describe qué hay hoy, qué falta y el flujo del
empresario.

---

## 1. Estado actual del empaquetado

| Pieza | Qué hace | Estado |
|---|---|---|
| **Instalador Electron** (`desktop/`, `scripts/release.ps1`) | Genera `VANOVA-Setup-X.exe` auto-contenido + `latest.json` | ✅ Listo (3.0.8 publicada) |
| **python-bundle** (`desktop/python-bundle/`) | CPython standalone completo (python.exe, python311.dll, Lib, DLLs) SIN venv ni rutas de build | ✅ Listo — el runtime no depende de Python del sistema |
| **Runtime local** (`desktop/runtime/`) | FastAPI en 127.0.0.1:8765 — arranca solo desde el bundle | ✅ Listo |
| **Cloud local** (`cloud/main.py`) | Sirve el dashboard en 127.0.0.1:8000 | ✅ Listo |
| **Wizard de setup** (`desktop/ui/setup.js`) | 9 pasos: análisis → empresa → canales → objetivos → IA → instalación → agentes → listo | ✅ Listo (rebrand a VANOVA hecho) |
| **Updater** (`desktop/updater/`) | Actualizaciones automáticas desde manifest | ✅ Listo |
| **Hermes por detrás** | VANOVA lo instala/arranca automáticamente (`hermes_service.py`) — el empresario NO lo ve | ✅ Listo (Ollama launch o standalone) |

**El empresario NO necesita saber** de Python (va embebido), Node (solo build),
ni Hermes (VANOVA lo gestiona por detrás y la experiencia es 100% VANOVA).

---

## 2. Lo que falta / mejora para el MVP

1. **Onboarding en ESPAÑOL** — el wizard (`setup.js`) está en inglés. Para el
   target (PYMEs hispanas, p.ej. MOOVING), el wizard debe estar en español.
2. **Importación guiada de datos** — el paso de "ver el €" es crítico. Hace
   falta un asistente que conecte Shopify/Excel y ejecute el detector, con el
   € destacado en pantalla.
3. **Verificación end-to-end en PC "stock"** — probar el instalador en una VM
   sin Python/Node/Hermes para confirmar el flujo completo.

---

## 3. Primer esbozo: cómo un empresario instala VANOVA en 5 pasos

1. **Descarga** el instalador de la web de VANOVA (solo un archivo `.exe`).
2. **Instala**: doble clic en `VANOVA-Setup.exe` → siguiente, siguiente,
   instalar. No aparece ningún terminal ni instalación de Python/Hermes.
3. **Primer arranque**: un asistente simple (en español) te pregunta:
   - "¿Cómo se llama tu empresa?"
   - "¿Qué vendes?" (canales: tienda online, marketplaces, Excel)
   - "¿Dónde están tus datos?" → conectar Shopify, o importar un Excel.
4. **Conecta tus datos**: elige tu tienda Shopify (o sube tus ventas en
   Excel/CSV) y VANOVA importa productos/pedidos solo.
5. **Ve tu negocio en €**: el dashboard muestra las oportunidades reales con
   su impacto en euros (cross-sell, margen, clientes en riesgo), y "Qué hacer
   hoy" con acciones concretas. Hermes trabaja por detrás, sin que tengas que
   saber que existe.

**Honestidad:** si no hay datos o costes suficientes, el dashboard lo dice
con claridad ("Impacto no cuantificable" / empty state honesto) — nunca
inventa un € que no se pueda calcular.
