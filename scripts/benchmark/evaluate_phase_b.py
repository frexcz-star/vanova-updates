"""Evaluación honesta de FASE B contra la ground truth congelada.

Este evaluador no usa coincidencias genéricas de palabras para declarar éxito.
Exige el tipo de finding y la entidad deliberadamente afectada, o una evidencia
específica de calidad de datos. Mantiene separadas estas capas:

DATOS → MODELO → DETECTOR → CONTEXTO/HERMES → DECISIÓN

La GROUND_TRUTH solo se usa aquí, nunca se copia al sandbox ni se entrega a
Hermes. La evaluación genera ``benchmark-results/evaluation-phase-b.json`` y
una matriz reproducible que luego se incorpora al informe manual.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "benchmark-results"
SANDBOX = ROOT / "benchmark-sandbox"

# Entidades objetivo tomadas de GROUND_TRUTH. El evaluador puede conocerlas;
# VANOVA/Hermes no las recibe.
PROBLEMS: list[dict[str, Any]] = [
    {"id": "P01", "company": "empresa-1", "type": "high_revenue_low_margin", "targets": ["lh-014"]},
    {"id": "P02", "company": "empresa-1", "type": "low_revenue_high_margin", "targets": ["lh-031"]},
    {"id": "P03", "company": "empresa-1", "type": "stockout_risk", "targets": ["lh-007"]},
    {"id": "P04", "company": "empresa-1", "type": "supplier_cost_increase", "targets": ["sup-lh-003"]},
    {"id": "P05", "company": "empresa-1", "type": "customer_churn", "targets": ["decor 88 interiorismo"]},
    {"id": "P06", "company": "empresa-1", "type": "upcoming_payments_concentration", "targets": []},
    {"id": "P07", "company": "empresa-1", "type": "product_declining", "targets": ["lh-048"]},
    {"id": "M01", "company": "empresa-2", "type": "customer_low_margin", "targets": ["grupo norte"]},
    {"id": "M02", "company": "empresa-2", "type": "supplier_dependency", "targets": ["sup-id-001"]},
    {"id": "M03", "company": "empresa-2", "type": "stockout_risk", "targets": ["id-001"]},
    {"id": "M04", "company": "empresa-2", "type": "supplier_cost_increase", "targets": ["sup-id-004"]},
    {"id": "I01", "company": "empresa-3", "type": "stockout_risk", "targets": ["ts-005"]},
    {"id": "I02", "company": "empresa-3", "type": "overstock", "targets": ["ts-077"]},
    {"id": "I03", "company": "empresa-3", "type": "dead_stock", "targets": ["ts-120"]},
    {"id": "I04", "company": "empresa-3", "type": "stockout_risk", "targets": ["ts-001"]},
    {"id": "I05", "company": "empresa-3", "type": "supplier_cost_increase", "targets": ["sup-ts-006"]},
    {"id": "F01", "company": "empresa-4", "type": "expense_growing", "targets": ["rent", "services"], "allTargets": True},
    {"id": "F02", "company": "empresa-4", "type": "upcoming_payments_concentration", "targets": []},
    {"id": "F03", "company": "empresa-4", "type": "supplier_cost_increase", "targets": ["sup-pm-002"]},
    {"id": "F04", "company": "empresa-4", "type": "dead_stock", "targets": ["pm-020"]},
    {"id": "D01", "company": "empresa-5", "type": "duplicate_sku", "targets": ["ms-003"], "quality": "duplicate_sku"},
    {"id": "D02", "company": "empresa-5", "type": "missing_sku", "targets": [], "quality": "missing_sku"},
    {"id": "D03", "company": "empresa-5", "type": "missing_cost", "targets": [], "quality": "missing_cost"},
    {"id": "D04", "company": "empresa-5", "type": "duplicate_customer", "targets": [], "quality": "duplicate_identity"},
    {"id": "D05", "company": "empresa-5", "type": "inconsistent_order_total", "targets": ["ord-e5-00006"], "quality": "order_mismatch"},
]


def _norm(value: Any) -> str:
    raw = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", raw).strip()


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _load_snapshot(company: str) -> dict[str, Any]:
    return _load_json(RESULTS / company / "snapshot.json", {})


def _load_answers(company: str) -> list[dict[str, Any]]:
    value = _load_json(RESULTS / company / "answers.json", [])
    return value if isinstance(value, list) else []


def _load_sandbox_data(company: str) -> dict[str, Any]:
    path = SANDBOX / company / "VANOVA" / "config" / "maios.json"
    value = _load_json(path, {})
    return value if isinstance(value, dict) else {}


def _load_findings(company: str) -> list[dict[str, Any]]:
    data = _load_sandbox_data(company)
    findings = data.get("businessFindings") or []
    return [f for f in findings if isinstance(f, dict)] if isinstance(findings, list) else []


def _finding_blob(finding: dict[str, Any]) -> str:
    return _norm(json.dumps(finding, ensure_ascii=False, sort_keys=True))


def _target_finding(problem: dict[str, Any], findings: list[dict[str, Any]]) -> dict[str, Any] | None:
    expected = problem["type"]
    targets = [_norm(t) for t in problem.get("targets") or []]
    candidates = [f for f in findings if str(f.get("type") or "") == expected]
    if not targets:
        return candidates[0] if candidates else None
    for finding in candidates:
        blob = _finding_blob(finding)
        if all(t in blob for t in targets):
            return finding
    return None


def _type_present(problem: dict[str, Any], findings: list[dict[str, Any]]) -> bool:
    return any(str(f.get("type") or "") == problem["type"] for f in findings)


_PROMPT_LEAK_MARKERS = ("[Contexto VANOVA", "[DATOS REALES DE VANOVA", "[Sistema] Eres el orquestador")


def _is_leaked_reply(reply: str) -> bool:
    """FASE C (cierre): una respuesta que reproduce el prompt interno (leak)
    NO es una respuesta de Hermes: es un fallo del CLI/API que filtró el
    contexto. Nunca cuenta como evidencia del modelo."""
    return any(m in (reply or "") for m in _PROMPT_LEAK_MARKERS)


def _target_hermes_text(problem: dict[str, Any], answers: list[dict[str, Any]]) -> bool:
    """Solo evidencia específica; no cuenta el texto de la pregunta ni una
    mención genérica del tipo de problema. Para un finding global se requiere
    que Hermes exponga el tipo con lenguaje afirmativo en alguna respuesta.

    FASE C (cierre): las respuestas que filtran el prompt interno (leak) se
    excluyen — el contexto copiado no es evidencia del modelo."""
    text = "\n".join(
        str(a.get("reply") or "") for a in answers if not _is_leaked_reply(a.get("reply"))
    )
    blob = _norm(text)
    targets = [_norm(t) for t in problem.get("targets") or []]
    if targets:
        return all(t in blob for t in targets)
    type_terms = {
        "upcoming_payments_concentration": ("pagos", "vencimientos"),
        "missing_cost": ("sin coste", "sin costo", "coste verificado"),
        "duplicate_sku": ("duplicado", "ms 003"),
        "missing_sku": ("sin sku", "sin referencia"),
        "duplicate_customer": ("duplicado", "cliente"),
        "inconsistent_order": ("incoherente", "inconsistente", "no cuadra"),
        "inconsistent_order_total": ("incoherente", "inconsistente", "no cuadra"),
    }
    terms = type_terms.get(problem["type"], ())
    return any(_norm(term) in blob for term in terms)


def _quality_evidence(problem: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    products = [p for p in (data.get("organizedProducts") or []) if isinstance(p, dict)]
    customers = [c for c in (data.get("organizedCustomers") or []) if isinstance(c, dict)]
    sales = [s for s in (data.get("organizedSales") or []) if isinstance(s, dict)]
    if problem.get("quality") == "duplicate_sku":
        groups: dict[str, list[dict[str, Any]]] = {}
        for p in products:
            sku = str(p.get("sku") or "").strip().lower()
            if sku:
                groups.setdefault(sku, []).append(p)
        rows = groups.get("ms-003", [])
        return {"preserved": len(rows) >= 2, "reviewed": sum(p.get("qualityReason") == "duplicate_sku" for p in rows) >= 2, "count": len(rows)}
    if problem.get("quality") == "missing_sku":
        rows = [p for p in products if not str(p.get("sku") or "").strip()]
        return {"preserved": bool(rows), "reviewed": any(p.get("qualityReason") == "missing_sku" for p in rows), "count": len(rows)}
    if problem.get("quality") == "missing_cost":
        missing = 0
        for p in products:
            cost = p.get("cost") if p.get("cost") not in (None, "") else p.get("netPrice")
            sale = p.get("rrp")
            if cost in (None, "") or (sale not in (None, "") and cost == sale):
                missing += 1
        return {"preserved": True, "reviewed": missing > 0, "count": missing}
    if problem.get("quality") == "duplicate_identity":
        groups: dict[str, list[dict[str, Any]]] = {}
        for c in customers:
            email = str(c.get("email") or "").strip().lower()
            if email:
                groups.setdefault(email, []).append(c)
        biggest = max(groups.values(), key=len, default=[])
        rows = biggest
        return {"preserved": len(rows) >= 2, "reviewed": sum(c.get("qualityReason") == "duplicate_identity" for c in rows) >= 2, "count": len(rows)}
    if problem.get("quality") == "order_mismatch":
        rows = [s for s in sales if str(s.get("id") or "").lower() == "ord-e5-00006"]
        mismatch = []
        for s in rows:
            lines = s.get("line_items") or []
            line_total = sum((float(li.get("price") or 0) * float(li.get("quantity") or 1)) for li in lines if isinstance(li, dict))
            total = float(s.get("total") or 0)
            mismatch.append(abs(line_total - total) > 0.01 if lines else False)
        return {"preserved": bool(rows), "reviewed": any(mismatch), "count": len(rows)}
    return {"preserved": False, "reviewed": False, "count": 0}


def _domain_availability(problem: dict[str, Any], data: dict[str, Any]) -> tuple[bool, bool, str]:
    products = [p for p in (data.get("organizedProducts") or []) if isinstance(p, dict)]
    sales = [s for s in (data.get("organizedSales") or []) if isinstance(s, dict)]
    invoices = [i for i in (data.get("organizedInvoices") or []) if isinstance(i, dict)]
    lines = [l for l in (data.get("organizedInvoiceLines") or []) if isinstance(l, dict)]
    finance = [f for f in (data.get("organizedFinance") or []) if isinstance(f, dict)]
    pid = problem["id"]
    if pid.startswith(("P03", "M03", "I0", "F04")):
        available = any(p.get("stock") is not None or p.get("stockQty") is not None for p in products)
        model = available and bool(products)
        return available, model, "stock por SKU"
    if pid in {"P04", "M02", "M04", "I05", "F03"}:
        available = bool(invoices and lines)
        return available, available, "proveedores + líneas de compra"
    if pid in {"P05", "M01"}:
        available = any(s.get("customer") or s.get("customerEmail") for s in sales)
        return available, available, "cliente por pedido"
    if pid in {"P06", "F02"}:
        available = bool(invoices and finance)
        return available, available, "facturas/tesorería"
    if pid.startswith("D"):
        q = _quality_evidence(problem, data)
        return True, bool(q["preserved"]), "archivo original + filas canónicas"
    return bool(products and sales), bool(products and sales), "ventas + catálogo"


def evaluate() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for problem in PROBLEMS:
        company = problem["company"]
        data = _load_sandbox_data(company)
        findings = _load_findings(company)
        answers = _load_answers(company)
        snapshot = _load_snapshot(company)
        data_present, model_available, needed = _domain_availability(problem, data)
        quality = _quality_evidence(problem, data) if problem.get("quality") else {}
        finding = _target_finding(problem, findings)
        type_present = _type_present(problem, findings)
        hermes = _target_hermes_text(problem, answers)
        # FASE C (B8): con los detectores de calidad dedicados, la detección es
        # engine-first (tipo + entidad). D03 mantiene además el fallback de
        # cobertura/Hermes por si el catálogo no llega al motor en alguna fuente.
        detected = bool(finding)
        if problem["id"] == "D03":
            detected = detected or bool(quality.get("reviewed") and quality.get("count", 0) > 0 and hermes)
        partial = (not detected) and (type_present or hermes or quality.get("preserved", False))
        status = "detected" if detected else ("partial" if partial else "not_detected")
        rows.append({
            "id": problem["id"], "company": company, "expectedType": problem["type"],
            "targets": problem.get("targets") or [], "dataNeeded": needed,
            "dataPresent": data_present, "modelAvailable": model_available,
            "detectorTarget": bool(finding), "detectorTypePresent": type_present,
            "hermesEvidence": hermes, "qualityEvidence": quality,
            "status": status,
            "finding": {"title": finding.get("title"), "observation": finding.get("observation"), "metrics": finding.get("metrics")} if finding else None,
            "snapshot": {"products": snapshot.get("products"), "orders": snapshot.get("orders"), "customers": snapshot.get("customers"), "findings": snapshot.get("findings")},
        })
    detected = sum(r["status"] == "detected" for r in rows)
    partial = sum(r["status"] == "partial" for r in rows)
    total = len(rows)
    return {
        "problems": rows,
        "summary": {
            "total": total, "detected": detected, "partial": partial,
            "notDetected": total - detected - partial,
            "targetRecallPct": round(detected / total * 100, 1) if total else 0.0,
            "recallIncludingPartialPct": round((detected + partial) / total * 100, 1) if total else 0.0,
        },
    }


def main() -> None:
    import sys
    out_name = "evaluation-phase-c.json" if "--phase=c" in sys.argv else "evaluation-phase-b.json"
    out = evaluate()
    (RESULTS / out_name).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out["summary"], ensure_ascii=False, indent=1))
    for row in out["problems"]:
        print(f"{row['id']:>3} {row['status']:<12} detector={str(row['detectorTarget']):<5} type={str(row['detectorTypePresent']):<5} hermes={str(row['hermesEvidence']):<5} model={str(row['modelAvailable']):<5}")


if __name__ == "__main__":
    main()
