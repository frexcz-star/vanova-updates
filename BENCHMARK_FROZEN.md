# BENCHMARK CONGELADO — TEST DE REGRESIÓN EMPRESARIAL DE VANOVA

**Estado: CONGELADO (17/08/2026)** — FASE C cerrada.

El benchmark empresarial de VANOVA (5 empresas ficticias, 200 preguntas reales a
Hermes, ground truth aislada) queda **congelado como referencia inmutable**. A
partir de ahora, cualquier actualización futura de VANOVA debe poder compararse
contra esta referencia. **NO se modifican los datos, la ground truth, las
preguntas, los criterios de evaluación ni los resultados históricos.**

---

## 1. Referencia de métricas (inmutable)

| Métrica | FASE A | FASE B | FASE C |
|---|---:|---:|---:|
| Recall estricto | 8% | 48% | **72%** |
| Recall con parciales | 17% | 96% | **96%** |
| Falsos positivos | 0 | 0 | **0** |
| Alucinaciones graves | 0 | 0 | **0** |
| Findings del motor | 0 (bug harness) | 154 | **235** |
| Tests | — | 462+1sk | **475+1sk** |

FASE C fue ejecutada con el código de B7/B8/B9 (señales, detectores, contexto
empresarial, preservación de suciedad). El leak de prompt de Hermes detectado en
M02 fue corregido DESPUÉS del run C (ver §5); las 13 respuestas de empresa-2 que
contenían el leak fueron excluidas de la evaluación (el evaluador ignora
respuestas que filtran el prompt interno).

---

## 2. Dataset congelado (benchmark-data/)

No se toca nada. Hash SHA-256 por archivo:

| Archivo | SHA-256 |
|---|---|
| empresa-1/productos.csv | `0320559d6d1f60eea799aa60dabd68ef2ba09ebef78ea121e5b189fc07fe4782` |
| empresa-1/ventas.csv | `5c36388f9dc89b12d89e5b471f8dfb8c8427b4ae267904cdbed9618154ba253d` |
| empresa-1/clientes.csv | `2c7953c313abb0b062da78c071da6b7009df582283491e654154f43a43c3db72` |
| empresa-1/canonical-connector.json | `517576a4d910d50fc943883ad8b3713c37fc804365befcee0c299f0017e1c2d6` |
| empresa-2/canonical-connector.json | `2c7bcce03a5a765f622f29563b27bfc2054b65f9df2e5091ca1e316490124c26` |
| empresa-3/canonical-connector.json | `512252958211d8a39c27b5473a7ce6a196c8e92be6ce4306c53b0cb05bc6048d` |
| empresa-4/canonical-connector.json | `b6796077fd0d0a586edd774916f60a6f1afcce31094563a70a982a958c43dfa8` |
| empresa-5/canonical-connector.json | `0d73d1884881a3643d2c319053ac04a533d46a2a78374a221de36c75861eed9d` |

Los CSV de productos/ventas/clientes de empresa-2..5 quedan cubiertos por el
generador congelado (hash §4) y por el commit de benchmark-data; su contenido no
se modifica. Verificar con `git status` que `benchmark-data/` no tiene cambios.

## 3. Ground truth (benchmark-secret/GROUND_TRUTH.md)

- **Nunca se copia a un sandbox ni se entrega a Hermes.**
- SHA-256: `c09d47ac83079eb7b5f1912c79958333b10d179cc4b72bd7277c6031fc62b7da`
- Se conserva SIEMPRE fuera de `benchmark-data/` y de cualquier directorio que
  VANOVA pueda escanear.

## 4. Preguntas y evaluadores (inmutables)

| Archivo | SHA-256 |
|---|---|
| benchmark-data/BENCHMARK_QUESTIONS.md | `e29f9606c03a7302466b77875bf6881c407db82ac2e432e2a3134222656a1011` |
| benchmark-data/DATASET_README.md | `52395ec2535224afde62c2877f3fcfd5bffc599d30c57d5c16d9aa4cb8508682` |
| scripts/benchmark/generate.py | `4d87cf3816897f227e78071d4cde8aad40e666cc13cfe98e6d800081e1d9b963` |
| scripts/benchmark/run_benchmark.py | `a3fe7ba36dc5faaec80ce795ad937090743dcb7abef8848612214bd5e7e6611e` |
| scripts/benchmark/evaluate_phase_b.py | `2f17ce1bc142462883927bc204b1558a1c85d056d35dd6fdf84381cabcce2a28` |

## 5. Resultados históricos (no sobrescribir)

| Archivo | SHA-256 |
|---|---|
| benchmark-results/evaluation-phase-b.json | `f5752a716c623453e4173baf9b18d8eb595965edea7f1babb4b314be298d8c10` |
| benchmark-results/evaluation-phase-c.json | `73e88ef120e04452ebaca9cac773a37a876ccfbb9e36d1bae1859b2efc3f25c6` |
| BENCHMARK_REPORT.md (FASE A) | `f10ff812264f2c09fdce508bbaccd061e0279fddbe8d901ed31fe602a8a47fa0` |
| BENCHMARK_REPORT_PHASE_B.md | `8a4e87cb8d5cd6b54783372e40d565d5a7d5f2eea90a4681c0348504e81ee77b` |
| BENCHMARK_REPORT_PHASE_C.md | `3ea29250055e0959ebbfe00aaf7f1cc726e2b7bc36e7e82a7c3ab18d02f3753e` |

Respuestas crudas de las 200 preguntas: `benchmark-results/empresa-{1..5}/answers.json`
(40 respuestas por empresa, inmutable). Fase B archivada en `benchmark-phase-b/`.
Fase A archivada en `benchmark-phase-a/`.

---

## 6. Corrección aplicada tras el run C (única modificación de código permitida)

**Bug:** Hermes CLI devolvió el prompt interno completo (system hint + contexto
operativo + pregunta) como respuesta tras un fallo de la API del proveedor
(13 respuestas de empresa-2, incl. M02). El empresario veía bloques como
`[Contexto VANOVA — usa estos hechos…]`.

**Fix (general, no específico de M02):**
- `desktop/runtime/hermes_chat.py`: nueva función `_strip_prompt_leak()` que
  recorta cualquier bloque interno (`[Contexto VANOVA`, `[DATOS REALES DE
  VANOVA`, `[Sistema]…`, `[Nota: no menciones Shopify`) de la respuesta final y
  devuelve un error honesto si no queda respuesta real. Se aplica en
  `_run_hermes_cli` sobre el summary.
- `scripts/benchmark/evaluate_phase_b.py`: el evaluador ignora respuestas que
  filtran el prompt interno (no cuentan como evidencia del modelo).
- Tests: `tests/test_hermes_chat_context.py` → `HermesPromptLeakGuardTests`
  (9 casos genéricos: leak real, prompt echo, bloque al final, ruido de API,
  respuestas legítimas intactas, términos BUSINESS HEALTH/RISKS/OPPORTUNITIES/
  DATA QUALITY conservados, wiring del guard).

**Validación post-fix:** la pregunta M02 real contra el sandbox de empresa-2
responde con análisis empresarial normal (concentración de gasto, SUP-ID-004
+45%, HECHO/INFERENCIA/NO DISPONIBLE, acción recomendada) sin ningún bloque
interno, y el contexto empresarial sigue llegando a Hermes.

---

## 7. Cómo ejecutar el benchmark congelado (reproducible)

```bash
# 1. Regenerar datasets (opcional: los archivos ya están congelados)
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/benchmark/generate.py

# 2. Ejecutar el experimento (backup automático de la instalación real)
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/benchmark/run_benchmark.py

# 3. Evaluar contra la ground truth congelada
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/benchmark/evaluate_phase_b.py --phase=c
```

Reglas de congelación:
- El generador NO puede cambiar los archivos ya emitidos (verificar hashes §2/§4).
- Los resultados A/B/C jamás se sobrescriben; un run nuevo guarda en su propio
  directorio (p. ej. `benchmark-phase-d/`).
- No se bajan thresholds, no se hardcodean entidades, no se entrega ground
  truth a VANOVA.

---

## 8. Limitaciones conocidas (documentadas, no corregidas)

- **M02 (dependencia de proveedor por nº de SKUs):** la relación
  proveedor→producto no sobrevive actualmente al dataset/importación utilizado
  (`productos.csv` no lleva columna de proveedor y el modelo canónico no
  conserva el vínculo). **Limitación actual de trazabilidad de datos.** No se
  convierte en falso positivo ni se baja el umbral.
- **6 parciales (P05, P06, M01, M03, F02, F04):** evidencia deliberada ausente
  en los datos congelados (p. ej. «Decor 88» tiene 0 pedidos; pagos próximos =
  5,7%; Grupo Norte margen 37%; ID-001 34 días de stock).
- **Latencia LLM** (~39 s media, 200 respuestas): sin cambios en esta fase.
