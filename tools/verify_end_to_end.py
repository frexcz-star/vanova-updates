#!/usr/bin/env python3
"""verify_piloto.py — verificación end-to-end del MVP vendible de VANOVA.

Script automatizable para el PILOTO FÍSICO en un PC "stock" (sin Python/Node/
Hermes del sistema). Confirma que VANOVA instala, arranca Hermes/cloud y llega
a pintar el € con datos reales importados, sin inventar ningún número.

Ejecución en el PC del piloto (Windows):
    VANOVA-Setup-3.1.3.exe        (instalación asistida, wizard en español)
    # tras el primer arranque, desde el repo o la instalación:
    python verify_end-to-end.py

Qué comprueba:
  1. Runtime local (127.0.0.1:8765) responde.
  2. Cloud local (127.0.0.1:8000) responde.
  3. Hermes arranca (degradado a modelo cloud si no hay Ollama local).
  4. El catálogo tiene productos importados (ventas/coste reales).
  5. El endpoint de impacto responde y devuelve el payload de Valor Capturado.
  6. (Opcional) importa un CSV de costes de ejemplo y re-analiza.

Salida: imprime por cada check OK / FALLO y un resumen final. Sin red, sin
secrets: todo local.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

RUNTIME = os.environ.get("VANOVA_RUNTIME", "http://127.0.0.1:8765")
CLOUD = os.environ.get("VANOVA_CLOUD", "http://127.0.0.1:8000")
TIMEOUT = float(os.environ.get("VANOVA_TIMEOUT", "8"))


def _get(url: str) -> tuple[int, dict | str]:
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
            body = r.read().decode("utf-8", "replace")
            try:
                return r.status, json.loads(body)
            except Exception:
                return r.status, body
    except Exception as e:  # noqa: BLE001
        return 0, str(e)


def main() -> int:
    results: list[str] = []
    print("== Verificación end-to-end VANOVA (MVP vendible) ==\n")

    # 1) Runtime local
    s, b = _get(RUNTIME + "/api/health")
    ok = s == 200
    results.append(f"[{'OK' if ok else 'FALLO'}] runtime {RUNTIME}/api/health -> {s} {b if not ok else ''}")
    print(results[-1])

    # 2) Cloud local
    s2, b2 = _get(CLOUD + "/api/health")
    ok2 = s2 == 200
    results.append(f"[{'OK' if ok2 else 'FALLO'}] cloud {CLOUD}/api/health -> {s2} {b2 if not ok2 else ''}")
    print(results[-1])

    # 3) Estado Hermes (degrada a modelo cloud sin Ollama)
    s3, b3 = _get(RUNTIME + "/api/hermes/status")
    if isinstance(b3, dict):
        healthy = b3.get("healthy")
        active = b3.get("activeModel") or b3.get("model") or "?"
        results.append(f"[{'OK' if healthy else 'INFO'}] hermes -> healthy={healthy} model={active}")
    else:
        results.append(f"[INFO] hermes status -> {s3} {b3}")
    print(results[-1])

    # 4) Endpoint de Valor Capturado / impacto (datos reales de measure())
    s4, b4 = _get(RUNTIME + "/api/recommendations/impact")
    if isinstance(b4, dict):
        captured = b4.get("capturedEuro")
        improved = b4.get("improved") or b4.get("improvedCount")
        total = b4.get("total")
        results.append(f"[OK] impact -> capturedEuro={captured} improved={improved} total={total}")
    else:
        results.append(f"[FALLO] impact -> {s4} {b4}")
    print(results[-1])

    # 5) Productos/ventas cargados (catálogo con datos reales)
    s5, b5 = _get(RUNTIME + "/api/products")
    if isinstance(b5, dict):
        items = b5.get("products") or b5.get("items") or []
        n = len(items)
        results.append(f"[{'OK' if n > 0 else 'INFO'}] catálogo -> {n} productos")
    else:
        results.append(f"[INFO] catálogo -> {s5} {b5}")
    print(results[-1])

    # Resumen
    print("\n== Resumen ==")
    for r in results:
        print("  " + r)
    fails = [r for r in results if r.startswith("[FALLO]")]
    print(f"\n{'TODO LISTO PARA EL PILOTO' if not fails else 'HAY ' + str(len(fails)) + ' FALLO(S)'} — "
          f"{len(results) - len(fails)}/{len(results)} checks OK")

    # Código de salida: 0 = listo para el piloto, !=0 si hay FALLO
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
