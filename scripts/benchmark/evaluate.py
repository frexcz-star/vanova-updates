"""FASE A — Evaluador del benchmark (veredicto HONESTO, revisado manualmente).

El matcher automático por palabras clave infló resultados: contaba como
"detectado" la mera mención de un SKU cuando Hermes en realidad decía
"no tengo ese dato". Este evaluador usa veredictos MANUALES — cada problema
fue revisado contra el texto completo de las respuestas (benchmark-results/
_review_dump.txt) — y documenta la evidencia textual de cada veredicto.

Estados:
  ✅ DETECTADO    Hermes identificó el problema concreto con datos reales.
  🟡 PARCIAL      Detectó algo relacionado (tendencia general) pero no el
                  problema específico introducido.
  ❌ NO DETECTADO  No lo identificó (a menudo porque el dato no llega a su
                  contexto operativo, y lo dijo con honestidad).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "benchmark-results"

# Veredicto manual por problema, con la evidencia textual clave.
# La evidencia es citas literales de las respuestas de Hermes.
MANUAL = {
    "empresa-1": {
        "P01": {
            "status": "DETECTADO",
            "evidence": "Q8: «LH-014 · Lámpara LED Nordic 60W — 590 uds, 73.987,95 €, margen 5,97% (coste 121,30 / PVD 129)»; Q29 «LA FUGA»; Q9 decisión: potenciar LH-007, no LH-014.",
        },
        "P02": {
            "status": "NO_DETECTADO",
            "evidence": "Q7 lista top márgenes (LH-013, LH-005…) pero no destaca LH-031 Difusor Premium como oportunidad de baja rotación/alto margen.",
        },
        "P03": {
            "status": "NO_DETECTADO",
            "evidence": "Q10: «necesito stock actual por SKU… NO DISPONIBLE». Hermes da velocidad de venta pero no puede calcular riesgo de agotamiento.",
        },
        "P04": {
            "status": "NO_DETECTADO",
            "evidence": "Q16/Q17: «no hay datos a nivel de proveedor… no puedo afirmar que un coste haya subido». Q18 reinterpreta «renegociar» como coste de producto (LH-014) — dato real, pero no el problema introducido (SUP-LH-003 +60%).",
        },
        "P05": {
            "status": "NO_DETECTADO",
            "evidence": "Q13/Q14/Q15: «no tengo agregación por cliente… no puedo nombrarte clientes sin inventar». No identifica al VIP ni al cliente que dejó de comprar.",
        },
        "P07": {
            "status": "PARCIAL",
            "evidence": "Q4 detecta caída de ventas mensuales (Jun 41.636 → Ago 28.025, -21%) con caveat honesto sobre la ventana, pero NO identifica LH-048 Estantería Modular Oak como el producto en declive.",
        },
    },
    "empresa-2": {
        "M01": {
            "status": "NO_DETECTADO",
            "evidence": "Q31/Q13: «no tengo agregación de rentabilidad por cliente». Q8 detecta productos de margen bajo (ID-014, ID-012) pero no al cliente grande.",
        },
        "M02": {
            "status": "NO_DETECTADO",
            "evidence": "Q16/Q17: no hay datos de proveedor ni histórico; no detecta la dependencia de SUP-ID-001 (40 productos).",
        },
        "M03": {
            "status": "NO_DETECTADO",
            "evidence": "Q10: ID-001 es la mayor rotación (587 uds) pero «stock actual NO está en los datos»; no detecta el riesgo de agotamiento.",
        },
        "M04": {
            "status": "NO_DETECTADO",
            "evidence": "Q16/Q17: sin histórico de costes por proveedor; no detecta SUP-ID-004 +45%.",
        },
    },
    "empresa-3": {
        "I01": {
            "status": "NO_DETECTADO",
            "evidence": "Q10/Q31: «niveles de stock NO están en el dataset… no puedo afirmar que te falte stock». No detecta TS-005 stock 0.",
        },
        "I02": {
            "status": "NO_DETECTADO",
            "evidence": "Q32 llama a TS-077 «tu cable estrella» (al revés del sobrestock real de 8.400 uds); sin stock por SKU no detecta el exceso.",
        },
        "I03": {
            "status": "NO_DETECTADO",
            "evidence": "Q36: «no tengo la fecha de la última venta de cada producto»; no detecta TS-120 VGA (dead stock 3.200 uds).",
        },
        "I04": {
            "status": "NO_DETECTADO",
            "evidence": "Q10/Q31: sin stock por SKU no detecta TS-001 (stock 4, alta rotación).",
        },
        "I05": {
            "status": "NO_DETECTADO",
            "evidence": "Q16/Q17: sin histórico por proveedor; Q18 reinterpreta como margen de producto. No detecta SUP-TS-006 +50%.",
        },
    },
    "empresa-4": {
        "F01": {
            "status": "NO_DETECTADO",
            "evidence": "Q22: «no hay serie temporal de gastos… no se puede determinar qué gastos están creciendo». No detecta el alquiler 1800→2605 ni los servicios 600→1104.",
        },
        "F02": {
            "status": "PARCIAL",
            "evidence": "Q21 detecta «riesgo financiero» general (concentración en PM-001, sin visibilidad de caja) pero NO la deuda creciente por facturas impagadas (Q33: FacturaScripts desconectado).",
        },
        "F03": {
            "status": "NO_DETECTADO",
            "evidence": "Q16/Q17: sin mapping SKU→proveedor ni histórico; no detecta SUP-PM-002 +55%.",
        },
        "F04": {
            "status": "NO_DETECTADO",
            "evidence": "Q11/Q12: sin stock por SKU no detecta PM-020 Abrigo (stock 220, demanda 0,5×).",
        },
    },
    "empresa-5": {
        "D01": {
            "status": "NO_DETECTADO",
            "evidence": "Q32: «no hay productos duplicados». El CSV tenía MS-003 duplicado (47 filas) pero el import deduplicó a 46, así que el dato sucio no llegó al modelo.",
        },
        "D02": {
            "status": "NO_DETECTADO",
            "evidence": "Q33: «los 46 productos tienen todos SKU». El producto sin referencia del CSV se perdió en la normalización (47→46).",
        },
        "D03": {
            "status": "DETECTADO",
            "evidence": "Q23: «77,3% del revenue con coste verificado, 9 productos sin coste MS-011..MS-018»; Q34: margen no calculable para el 22,7%; Q39 lista los productos sin coste.",
        },
        "D04": {
            "status": "NO_DETECTADO",
            "evidence": "Q35: «no hay análisis de duplicados en los datos». El email duplicado del CSV (121→120 clientes) se deduplicó en el import; Hermes no puede detectarlo.",
        },
        "D05": {
            "status": "NO_DETECTADO",
            "evidence": "Q36 flagga ORD-E5-00002 (9,50 €) y la numeración, pero NO el total incoherente ×2,3 del ORD-E5-00006; además solo ve 5 de 180 pedidos.",
        },
    },
}

LABELS = {
    "DETECTADO": "✅ DETECTADO",
    "PARCIAL": "🟡 PARCIAL",
    "NO_DETECTADO": "❌ NO DETECTADO",
}


def main() -> None:
    companies = ["empresa-1", "empresa-2", "empresa-3", "empresa-4", "empresa-5"]
    total = 0
    counts = {"DETECTADO": 0, "PARCIAL": 0, "NO_DETECTADO": 0}
    by_company = {}
    for c in companies:
        probs = MANUAL.get(c, {})
        by_company[c] = {}
        for pid, v in probs.items():
            counts[v["status"]] += 1
            total += 1
            by_company[c][pid] = v
    detected = counts["DETECTADO"] + counts["PARCIAL"]

    L = []
    L.append("# BENCHMARK REPORT — FASE A (Business Value Challenge)\n")
    L.append("**Evaluación HONESTA revisada manualmente** sobre las 200 respuestas reales de")
    L.append("Hermes (40 por empresa) contra la GROUND TRUTH (que VANOVA nunca vio).\n")
    L.append("## Resumen ejecutivo\n")
    L.append(f"- **Problemas deliberados evaluados:** {total}")
    L.append(f"- **✅ Detectados:** {counts['DETECTADO']} · **🟡 Parciales:** {counts['PARCIAL']} · "
             f"**❌ No detectados:** {counts['NO_DETECTADO']}")
    L.append(f"- **Recall (detectado+parcial):** {round(detected/total*100)}%")
    L.append(f"- **Falsos negativos:** {round(counts['NO_DETECTADO']/total*100)}%")
    L.append("- **Falsos positivos:** 0 — el evaluador no cuenta como detectado nada que Hermes")
    L.append("  no haya identificado con datos reales (el matcher por palabras clave inicial")
    L.append("  inflaba resultados y fue descartado).")
    L.append("- **Hallazgo de infraestructura:** el motor de detección determinista")
    L.append("  (`detection_engine`) devolvió **0 findings** en las 5 empresas aunque los")
    L.append("  problemas existen en los datos (ver `snapshot.json`). Las pocas detecciones")
    L.append("  provienen de Hermes leyendo los datos, no del motor de detección.")
    L.append("- **Causa raíz de los no-detectados:** el contexto operativo de Hermes NO incluye")
    L.append("  stock por SKU, mapping/histórico de proveedores ni agregación por cliente.")
    L.append("  Hermes lo dice con honestidad (\"no tengo ese dato\"), pero no puede detectar")
    L.append("  problemas de inventario, proveedores ni clientes.\n")

    L.append("## Resultado por empresa\n")
    for c in companies:
        L.append(f"### {c}")
        probs = by_company[c]
        if not probs:
            L.append("- Sin problemas evaluados.")
            continue
        for pid in sorted(probs):
            v = probs[pid]
            L.append(f"- **{pid}** → {LABELS[v['status']]}")
            L.append(f"  - Evidencia: {v['evidence']}")
        L.append("")

    L.append("## Resultado por pregunta\n")
    L.append("Las 200 respuestas completas están en `benchmark-results/{empresa}/answers.json`")
    L.append("(40 por empresa). La clasificación por problema (arriba) se hizo leyendo el texto")
    L.append("completo de cada respuesta relevante (`benchmark-results/_review_dump.txt`).\n")

    L.append("## Problemas correctamente detectados\n")
    L.append("1. **P01 (E1) — ancla con margen 6%**: LH-014 identificado con cifras exactas")
    L.append("   (590 uds, 73.987,95 €, 5,97%) y decisión accionable (potenciar LH-007, renegociar LH-014).")
    L.append("2. **D03 (E5) — costes faltantes**: 77,3% de cobertura, 9 productos listados, margen")
    L.append("   correctamente bloqueado para el 22,7% restante.\n")

    L.append("## Problemas parcialmente detectados\n")
    L.append("1. **P07 (E1)**: detecta la caída de ventas mensuales (-21% jun→ago) con caveat honesto,")
    L.append("   pero no el producto específico en declive (LH-048).")
    L.append("2. **F02 (E4)**: señala riesgo financiero general (concentración, sin visibilidad de caja)")
    L.append("   pero no la deuda creciente por facturas impagadas.\n")

    L.append("## Problemas NO detectados (20)\n")
    L.append("Inventario (P03, M03, I01, I02, I03, I04, F04): Hermes no recibe stock por SKU.")
    L.append("Proveedores (P04, M02, M04, I05, F03): Hermes no recibe mapping ni histórico de proveedores.")
    L.append("Clientes (P05, M01, D04): Hermes no recibe agregación por cliente ni análisis de duplicados.")
    L.append("Gastos/tesorería (F01, F02): sin serie temporal de gastos ni FacturaScripts conectado.")
    L.append("Datos sucios (D01, D02, D05): el import deduplica silenciosamente (47→46 productos,")
    L.append("121→120 clientes), ocultando la suciedad antes de que la gobernanza pueda marcarla;")
    L.append("D05 se detectó un pedido raro distinto al introducido.\n")

    L.append("## Falsos positivos\n")
    L.append("0 con la evaluación manual. (El matcher automático inicial arrojaba varios, y fue")
    L.append("descartado por sobrecontar menciones de SKU como detecciones.)\n")

    L.append("## Alucinaciones\n")
    L.append("No se observaron cifras inventadas. Hermes respondió consistentemente con la política")
    L.append("HECHO / INFERENCIA / NO DISPONIBLE y rechazó inventar stock, deudas o tendencias.\n")

    L.append("## Datos que VANOVA consideró fiables cuando no debía\n")
    L.append("- En E5, Hermes afirmó «no hay productos duplicados» y «todos tienen SKU» porque el")
    L.append("  import ya había deduplicado el catálogo (47→46). La afirmación es coherente con lo")
    L.append("  que ve, pero oculta un problema real de calidad en el archivo original.\n")

    L.append("## Datos que VANOVA rechazó correctamente\n")
    L.append("- Margen global en E5 (bloqueado: 22,7% sin coste).")
    L.append("- Deudas/tesorería en E4 (FacturaScripts desconectado → «no puedo determinarlo»).")
    L.append("- Stock y rotación en E1–E4 (dato ausente → no lo convierte en 0).")
    L.append("- Aumentos de coste de proveedor en todas (sin histórico → no afirma tendencia).\n")

    L.append("## Decisiones empresariales útiles\n")
    L.append("1. P01: «potencia LH-007, no LH-014; renegocia el coste de LH-014» (cifra el impacto: +5.900 €).")
    L.append("2. E1 Q30: oportunidad de +10 €/ud sobre 590 uds = +5.900 € de margen.")
    L.append("3. D03: lista exacta de productos a los que falta coste (acción: cargar coste real).\n")

    L.append("## Decisiones empresariales incorrectas\n")
    L.append("- E3 I02: llamar a TS-077 «tu cable estrella» (es el producto con 8.400 uds de sobrestock) —")
    L.append("  no es un consejo falso, pero omite por completo el problema de capital inmovilizado.\n")

    L.append("## Limitaciones de VANOVA detectadas\n")
    L.append("1. **El motor de detección no dispara** (`findings: 0` en las 5 empresas): no detecta")
    L.append("   churn, dead stock, sobrestock, dependencia de proveedor ni gastos por categoría.")
    L.append("2. **El contexto operativo de Hermes no incluye stock, proveedores ni clientes** —")
    L.append("   por eso los problemas de esas dimensiones no se detectan aunque existan en los datos.")
    L.append("3. **El import deduplica silenciosamente** (E5 47→46 productos, 121→120 clientes),")
    L.append("   ocultando duplicados antes de que la gobernanza pueda marcarlos.")
    L.append("4. Hermes solo ve top-10 de productos en contexto; problemas en la cola larga (dead stock,")
    L.append("   baja rotación) quedan invisibles.\n")

    L.append("## Problemas de UX / integración / Hermes\n")
    L.append("- **UX**: Hermes a menudo responde «¿quieres que consulte get_X?» pidiendo permiso en vez de")
    L.append("  ejecutar la tool — buena honestidad, pero UX lenta para el empresario.")
    L.append("- **Integración**: el flujo de benchmark no pasó stock/inventario ni proveedores al modelo")
    L.append("  (el conector canónico de prueba no los exporta a Hermes); FacturaScripts sigue bloqueado.")
    L.append("- **Hermes**: la ruta ligera responde «no tengo datos en este turno» en preguntas ambiguas,")
    L.append("  aunque los datos existan (falta de routing a la ruta completa).\n")

    L.append("## Métricas\n")
    L.append(f"- **% de respuestas correctas:** las respuestas factuales (revenue, top productos, cobertura)")
    L.append("  fueron correctas en las 200; el % de problemas detectados es {round(detected/total*100)}%.")
    L.append(f"- **% de problemas detectados (recall):** {round(detected/total*100)}%")
    L.append(f"- **% de falsos positivos:** 0%")
    L.append(f"- **% de falsos negativos:** {round(counts['NO_DETECTADO']/total*100)}%")
    L.append("- **% de respuestas accionables:** alto en las preguntas de producto/margen (P01, D03);")
    L.append("  bajo en inventario/proveedores/clientes (se devuelve «no tengo el dato»).")
    L.append("- **% que reconocen falta de datos:** alto — Hermes lo hace explícitamente en stock,")
    L.append("  proveedores, tesorería y deudas (comportamiento honesto, sin inventar).\n")

    L.append("## Conclusión\n")
    L.append("VANOVA **responde con honestidad y precisión sobre lo que ve** (revenue, top productos,")
    L.append("márgenes, cobertura de costes) y **nunca inventa** — eso es real y valioso. Pero su")
    L.append("**valor de detección empresarial automática es bajo hoy**: el motor determinista dio 0")
    L.append("findings y los problemas de inventario, proveedores y clientes no se detectan porque esos")
    L.append("datos no llegan al contexto de Hermes. La mayoría de problemas solo emergen si el")
    L.append("empresario hace la pregunta exacta, y aun así muchos quedan en «no tengo ese dato».\n")
    L.append("**Veredicto del experimento ciego:** VANOVA es un lector honesto de datos, no todavía un")
    L.append("detector proactivo de problemas de negocio. Recomendación prioritaria: alimentar el")
    L.append("contexto con stock/proveedores/clientes y reactivar el motor de detección con los")
    L.append("detectores que faltan (churn, dead stock, sobrestock, dependencia de proveedor, gastos).")

    out = ROOT / "BENCHMARK_REPORT.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    (RESULTS / "evaluation.json").write_text(
        json.dumps(by_company, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Reporte: {out}")
    print(f"RESUMEN: {counts} sobre {total} problemas")
    print(f"Recall: {round(detected/total*100)}%")


if __name__ == "__main__":
    main()
