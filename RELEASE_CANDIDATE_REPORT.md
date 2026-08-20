# RELEASE_CANDIDATE_REPORT — VANOVA 2.0.26-beta.2

**Fecha:** 2026-08-18 · **Build:** `release/VANOVA-Setup-2.0.26-beta.2.exe` · **Canal:** beta

---

## 1. QUÉ SE HA PROBADO

| Área | Resultado |
|---|---|
| Auditoría pre-build (FASE 1) | Cambios desde beta.1: fix B-01 de aislamiento entre empresas. Confirmado presente en `desktop/runtime/integrations_store.py` (guard `not_configured`/`shop_mismatch`), `tests/test_isolation_hermes_env.py` (10 tests) y `scripts/_b01_validate.py`. Sin cambios en benchmark, GROUND_TRUTH ni resultados históricos |
| Tests (FASE 2) | **515 passed, 1 skipped** (39 s); 10/10 tests de aislamiento B-01 en verde; benchmark congelado intacto (72 % estricto / 96 % parciales / 0 FP, hash `73e88ef1…` intacto) |
| Versionado (FASE 3) | `2.0.26-beta.2` en version.json, desktop/package.json y shared/version_info.py (sincronizado por `scripts/release.ps1`) |
| Build real (FASE 4) | `scripts/release.ps1 -Version 2.0.26-beta.2` → instalador nuevo (no reutiliza beta.1); verify-package OK; checksums regenerados; tests de update (28) OK |
| Validación empaquetada (FASE 5) | Runtime empaquetado (win-unpacked, python-bundle) probado con perfiles aislados: máquina limpia (0 datos, todo UNKNOWN, sin Shopify), máquina contaminada con `.hermes/.env` de otra empresa (bloqueado: `not_configured`, 0 credenciales, 0 datos, nada escrito), conexión explícita B (usa solo B; A rechazada con `shop_mismatch`), reinicio (mantiene B) → **RESULT=PASS** |
| Flujo normal empaquetado (FASE 5D) | setup → scan → organize (**461 productos / 99 pedidos**) → analyze (findings) → dashboard/signals → Hermes (responde con datos reales) → refresh idempotente (461/99, firmas estables) → restart (persiste) → **RESULT=PASS** |
| Update (FASE 6) | Semver `beta.1 → beta.2` correcto; manifest real (channel beta, producto VANOVA, SHA `e401c28e…`, size 107458299) verificado; E2E check desde beta.1 → `updateAvailable: True, target 2.0.26-beta.2`; guard de producto (MAIOS) y versión mínima (0.9.0) OK; checksum del instalador coincide con el manifest |
| Seguridad/regresión (FASE 7) | Bundle sin credenciales ni datos de benchmark/empresas (único match: placeholder de ejemplo en UI); logs del perfil aislado sin ERROR/CRITICAL ni tokens; instalación real de referencia intacta (461/100, cloud healthy en :8000, 4 procesos restaurados) |

## 2. MANIFEST / INTEGRIDAD

| Campo | Valor |
|---|---|
| version | 2.0.26-beta.2 |
| channel | beta |
| size | 107458299 |
| sha256 (instalador) | `e401c28ef2ac5033c44340fa3edf915d0597f75b8a8ad243418db099d51926e7` |
| sha256 (latest.json) | idéntico al instalador ✅ |
| minimumSupportedVersion | 0.9.0 |
| mandatory | false |
| releaseNotes | Aislamiento B-01 + suite 515 + benchmark intacto |

## 3. QUÉ HA PASADO ✅

- **B-01 resuelto y verificado en el build empaquetado**: una instalación nueva ya no hereda credenciales de `~/.hermes/.env` ni de `%LOCALAPPDATA%\hermes\.env`. La prueba con perfil contaminado demuestra que la empresa A nunca llega a la instalación (bridge no-op, nada escrito en disco, sync honesto "Shopify no conectado").
- **Conexión explícita funcional**: configurar Shopify para B en la máquina contaminada conecta solo B; el `.hermes/.env` de A no puede sustituirla (guard `shop_mismatch`) y tras reinicio se mantiene B.
- Flujo completo de cliente empaquetado: 461/99 con datos reales, Hermes responde con cifras del motor, refresh idempotente, restart persistente.
- Update beta.1 → beta.2: semver, manifest, checksum y guards correctos.
- Suite 515+1 en verde; benchmark congelado intacto; instalación real de referencia intacta y restaurada (cloud en :8000).

## 4. QUÉ HA FALLADO / LIMITACIONES ⚠️

| # | Problema | Severidad | Clasificación |
|---|---|---|---|
| 1 | `ventas.csv` exportado sin line items → cobertura de revenue 0 % (degradación honesta; el CSV real de un cliente con líneas sí las tiene) | Baja | LIMITACIÓN DE DATOS (formato) |
| 2 | Fichero de productos importado con nombre distinto (copia) → todos los SKU marcados duplicados y costes bloqueados como NEEDS_REVIEW | Baja | COMPORTAMIENTO ESPERADO (control de calidad FASE B); avisar al tester de no reimportar copias renombradas |
| 3 | Trazabilidad proveedor → producto → SKU no sobrevive al dataset/importación actual (M02 del benchmark) | Media | LIMITACIÓN DE DATOS |
| 4 | Hermes depende de un proveedor de IA configurado; sin credenciales responde que no puede | Baja | COMPORTAMIENTO ESPERADO |
| 5 | En máquinas con una instalación VANOVA anterior, instalar con parámetros `/D` de NSIS a otra carpeta desinstala la anterior (B-02 del tester externo) | Media | COMPORTAMIENTO NSIS — una instalación por máquina; documentado para el tester |

## 5. QUÉ QUEDA PENDIENTE

- Entrega del instalador beta.2 al tester (esta build).
- Validación de la actualización real en el equipo del tester (el mecanismo está verificado E2E; el update channel beta se activa con `MAIOS_UPDATE_CHANNEL=beta` o config `channel=beta`).
- Trazabilidad proveedor → producto → SKU (limitación del modelo de datos, fuera de beta.2).

## 6. VEREDICTO

### 🟢 GO — VANOVA 2.0.26-beta.2 LISTA PARA ENTREGAR AL TESTER (BETA PRIVADA)

- El blocker B-01 de aislamiento entre empresas está corregido en la causa raíz y verificado en el runtime empaquetado (máquina limpia, máquina contaminada, conexión explícita, reinicio).
- Suite completa 515+1 en verde; benchmark congelado intacto; instalación real de referencia intacta.
- Manifest e instalador coinciden exactamente (SHA-256 y tamaño); update beta.1 → beta.2 verificado E2E.
- No se ha publicado ninguna release pública; no se ha tocado benchmark, GROUND_TRUTH ni resultados históricos.

**Condición recomendada para el tester:** entregar junto con `TESTER_CHECKLIST.md` (beta.2) y recordar: importar siempre los ficheros originales sin renombrar, configurar el proveedor de IA para Hermes, y usar una instalación por máquina.
