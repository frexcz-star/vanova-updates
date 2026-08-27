# PILOTO FÍSICO VANOVA — Guía para Nico

Objetivo: cerrar la Tarea 2 (empaquetado end-to-end) validando la instalación
del `.exe` en un PC "stock" real, sin Python/Node/Hermes del sistema, y
confirmar el primer arranque completo.

## Requisitos exactos del PC (ideal)
- Windows 10 u 11 (64 bits), en español o con teclado ES.
- **Sin** Python en PATH, **sin** Node.js, **sin** Hermes preinstalado (VANOVA lo instala/arranca por detrás).
- Conexión a internet (la primera vez: descarga del modelo Hermes / conexión de datos).
- ~2 GB de espacio libre en disco (el instalador ocupa ~107 MB; la instalación ~400 MB).
- 4 GB RAM mínimo, 8 GB recomendado (para correr runtime + cloud + Hermes).
- Opcional: una tienda Shopify real o un Excel/CSV de ventas de prueba para conectar datos.

## Cómo instalar (pasos exactos)
1. Descarga `VANOVA-Setup-3.1.2.exe` desde el manifest público:
   https://github.com/frexcz-star/vanova-updates/releases/latest/download/latest.json
   (o directamente el enlace `downloadUrl` del manifest).
2. Doble clic → asistente → "Siguiente" → "Instalar". No se abre ningún terminal.
   El instalador despliega `AppData/Local/Programs/VANOVA` con su propio
   `python-bundle` embebido (no toca el Python/Node del sistema).
3. Al terminar, se abre el wizard en **español**:
   - "Bienvenido" → nombre de la empresa → sector → canales.
   - Conectar datos: Shopify (OAuth) o subir Excel/CSV de ventas.
   - Coste o margen global (1 campo).
4. Debe aparecer el panel **"En juego este mes"** con el € real calculado.

## Primer arranque automático (lo que Nico debe verificar)
- El runtime local arranca solo en `127.0.0.1:8765` (sin que se abra ninguna
  ventana de Python/Hermes al empresario).
- El dashboard se sirve en `127.0.0.1:8000`.
- Hermes arranca por detrás con modelo `:cloud` (no fuerza descarga de un
  modelo local de Ollama). Si no hay Ollama local, degrada con gracia.

## Cómo reportar el resultado (formato para Nico)
Responder 4 preguntas con capturas/logs reales:
1. ¿La instalación del `.exe` terminó sin errores y abrió el wizard en español? (sí/no + captura)
2. ¿El primer arranque levantó runtime + dashboard sin pasos manuales? (sí/no + captura de `127.0.0.1:8000`)
3. ¿Se pudo conectar un dato real (Shopify/Excel) y ver un € en "En juego este mes"? (sí/no + captura del €)
4. ¿Algún paso falló o requirió intervención manual? (dónde exactamente + mensaje/error)

## Cómo reportar el log técnico
En el PC del piloto, buscar `%LOCALAPPDATA%/VANOVA/logs/` (o
`%LOCALAPPDATA%/Programs/VANOVA/.../logs`) y adjuntar el log más reciente si
algo falla. Esto permite diagnosticar sin depender de memoria.

---
*Documento de piloto preparado por Hermes (Developer). Ningún resultado de
prueba se afirma aquí; este es el plan verificable que Nico ejecutará y
reportará.*
