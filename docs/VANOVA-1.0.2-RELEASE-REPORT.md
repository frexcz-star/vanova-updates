# VANOVA 1.0.2 RELEASE REPORT

**Fecha:** 13 de agosto de 2026  
**Build machine:** Windows 10 (Admin)  
**Instalador:** `release/VANOVA-Setup-1.0.2.exe` (92,746,834 bytes)  
**SHA-256:** `8b980f305326e893fd913b5a82ddf3b47f7352b8dcb9a638f5b9b941433a7d00`

---

## 1. Changes

- **Endurecimiento comercial:** auditoría de estabilización (`test_stabilization_audit.py`), seguridad runtime, validación de conectores y ciclo de vida de integraciones.
- **Panel paridad Hermes:** contexto operacional, chat mejorado, organización de archivos (`file_organizer`, `hermes_activity`).
- **Puente Shopify:** sincronización continua (`shopify_sync`), setup guiado (`hermes_shopify_setup`), store de integraciones.
- **Correcciones conector:** autenticación, heartbeat, registro de dispositivo con versión actual en payload.
- **Sistema de actualizaciones validado:** pruebas unitarias 1.0.1→1.0.2, rutas de fallo SHA-256/corrupción, script E2E reproducible.
- **Infraestructura release:** baseline 1.0.1 preservado en `release/baseline/`, `release.ps1` parsea notas por versión, `verify-package.ps1` corregido (ASCII), source zip 1.0.2 generado.

## 2. Bugs fixed

- `verify-package.ps1`: carácter Unicode (em dash) rompía parseo en PowerShell Windows.
- `release.ps1`: incluía todas las release notes históricas en `latest.json`; ahora solo la sección de la versión actual.
- `release.ps1`: tests de update se ejecutan **después** de generar manifiesto (evita fallo chicken-and-egg en version bump).
- `setup-local-updates.ps1`: instrucciones actualizadas para path 1.0.1→1.0.2.

## 3. Tests (total/passed/failed)

| Suite | Total | Passed | Failed |
|-------|-------|--------|--------|
| Full (`python -m unittest discover -s tests -p "test_*.py" -q`) | **170** | **170** | **0** |
| Update system (`test_update_system.py`) | 28 | 28 | 0 |
| Update failures (`test_update_failures.py`) | 6 | 6 | 0 |

Nuevos tests 1.0.2:
- `test_101_to_102_available`
- `test_latest_json_102_fields`
- `test_latest_json_101_baseline_fields`
- `test_postpone_102_skips_available`
- `test_auto_download_102_triggers_thread`
- `test_checksum_mismatch_stays_on_101`
- `test_corrupted_package_aborted`

## 4. Versioning audit

| Archivo | Versión | Estado |
|---------|---------|--------|
| `version.json` | 1.0.2 | OK |
| `desktop/package.json` | 1.0.2 | OK |
| `release/latest.json` | 1.0.2 | OK |
| `release/latest.local.json` | 1.0.2 | OK |
| `release/publish/latest.json` | 1.0.2 | OK |
| `desktop/runtime/process_manager.py` fallback | 1.0.2 | OK |
| `scripts/create-source-zip.ps1` default | 1.0.2 | OK |
| `release/VANOVA-Setup-1.0.1.exe` | preservado | OK (no sobrescrito) |
| `release/baseline/VANOVA-Setup-1.0.1.exe` | 92,721,732 bytes | OK |
| `release/baseline/latest-1.0.1.json` | frozen manifest | OK |
| Referencias históricas 1.0.0/1.0.1 en tests | intencionales | OK |

## 5. Update system audit

| Check | Resultado |
|-------|-----------|
| `UpdateManifestProvider.is_update_available("1.0.1", manifest_1.0.2)` | **TRUE** |
| `latest.json` SHA-256 coincide con `VANOVA-Setup-1.0.2.exe` | **PASS** |
| `latest.json` size coincide (92746834) | **PASS** |
| `publish-update.ps1 -Version 1.0.2` | **PASS** (bundle en `release/publish/`) |
| `setup-local-updates.ps1 -OfferVersion 1.0.2` | **PASS** |
| `scripts/test-update-e2e.ps1 -SkipApiCheck` | **AUTOMATED PASS** |
| Authenticode / firma digital | **NO** (signtool skipped) |
| CDN `releases.moovingpaper.com` | **NO PUBLICADO** (requiere upload externo) |

## 6. 1.0.1 → 1.0.2 test result

**UPDATE TEST RESULT: 1.0.1 → 1.0.2 PARTIAL PASS**

| Fase | Resultado | Detalle |
|------|-----------|---------|
| Detección semver 1.0.1→1.0.2 | **PASS** | Unit + Python e2e-check |
| Manifiesto + SHA-256 + size | **PASS** | Verificado contra exe real |
| Descarga local (file:// URL) | **PASS** | Hash verificado |
| API runtime (`/api/updates/status`) | **SKIP** | VANOVA no en baseline 1.0.1 durante test |
| Instalar + reiniciar + verificar 1.0.2 | **NO TESTED** | Máquina ya tiene 1.0.2 instalado; requiere reinstalar baseline manualmente |

**Pasos manuales pendientes:**
1. Desinstalar o instalar `release/baseline/VANOVA-Setup-1.0.1.exe` sobre instalación actual.
2. `scripts\setup-local-updates.ps1 -OfferVersion 1.0.2 -ResetState`
3. Reiniciar VANOVA → modal 1.0.2 → Descargar → Instalar → Reiniciar.
4. Confirmar `version.json` = 1.0.2 y datos en `%LOCALAPPDATA%\VANOVA\data` intactos.

## 7. Failure-path results

| Escenario | Test | Resultado |
|-----------|------|-----------|
| SHA-256 incorrecto en paquete 1.0.2 | `test_checksum_mismatch_stays_on_101` | **PASS** → estado `failed`, paquete eliminado |
| Paquete corrupto/truncado | `test_corrupted_package_aborted` | **PASS** → estado `failed` |
| Manifiesto inválido | `test_invalid_manifest_rejected` | **PASS** → estado `offline` |
| SHA-256 incorrecto (legacy 0.9.1) | `test_checksum_mismatch` | **PASS** |
| Cancelar descarga | `test_cancel_download` | **PASS** |
| Rollback post-install | — | **NOT TESTABLE** en unit tests (requiere NSIS real) |

## 8. Data preservation result

| Check | Resultado |
|-------|-----------|
| Unit tests de backup/restore updater | Existentes, **PASS** en suite |
| E2E preservación datos post-update 1.0.1→1.0.2 | **NOT TESTED** (instalación manual pendiente) |
| NSIS `deleteAppDataOnUninstall: false` | Confirmado en `desktop/package.json` |

## 9. Remaining external actions (Authenticode, CDN)

1. **Authenticode:** Obtener certificado EV/OV y configurar `CSC_LINK` + `CSC_KEY_PASSWORD` para electron-builder.
2. **CDN upload:** Subir `release/publish/latest.json` y `VANOVA-Setup-1.0.2.exe` a `https://releases.moovingpaper.com/maios/`.
3. **E2E manual completo:** Ejecutar ciclo install 1.0.1 → update → restart → verify 1.0.2 en máquina limpia.
4. **`sync-to-installed.ps1`:** Ejecutar manualmente si se desea sincronizar módulos dev a instalación local sin reinstalar.

## 10. Remaining blockers

| Prioridad | Blocker | Impacto |
|-----------|---------|---------|
| **BLOCKER (GA)** | Sin firma Authenticode | SmartScreen warning en Windows |
| **BLOCKER (GA)** | CDN no publicado | Updates in-app no funcionan en producción |
| **HIGH** | E2E install+restart no ejecutado | Confianza en path real 1.0.1→1.0.2 |
| **LOW** | `sync-to-installed.ps1` no ejecutado en esta sesión | Dev local puede estar desincronizado |

---

**UPDATE TEST RESULT: 1.0.1 → 1.0.2 PARTIAL PASS**  
(Automatizado: PASS. Ciclo install+restart manual: pendiente.)

**Artefactos generados:**
- `release/VANOVA-Setup-1.0.2.exe`
- `release/latest.json` / `release/latest.local.json`
- `release/publish/` (CDN staging)
- `release/baseline/VANOVA-Setup-1.0.1.exe`
- `release/VANOVA-source-1.0.2.zip`
- `scripts/test-update-e2e.ps1`
- `scripts/e2e-check-update.py`
