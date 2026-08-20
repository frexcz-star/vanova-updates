"""FASE A — Harness del benchmark de valor empresarial.

Ejecuta el experimento CIEGO contra un sandbox aislado (LOCALAPPDATA temporal),
sin tocar la instalación real:

1. Backup de la instalación real (autorizado).
2. Crear sandbox con LOCALAPPDATA → benchmark-sandbox/{company}.
3. Shadow .env vacío (bloquea H30: el bridge no importa Shopify real).
4. Importar los 3 CSV con los mecanismos NORMALES (file_inventory.add_imported_file
   → file_organizer.organize_files) y el modelo canónico como hace un conector.
5. Ejecutar integrity + detection (snapshot de lo que VANOVA ve).
6. Preguntar a Hermes la batería completa y registrar respuestas + timings.
7. Guardar resultados en benchmark-results/{company}/.

El ask + polling se ejecutan en el MISMO proceso (el worker de Hermes es un
thread daemon en memoria; un proceso nuevo no puede hacer el poll).

Uso:  python scripts/benchmark/run_benchmark.py [empresa-1 ... empresa-5]
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH_DATA = ROOT / "benchmark-data"
SANDBOX_ROOT = ROOT / "benchmark-sandbox"
RESULTS_ROOT = ROOT / "benchmark-results"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"

CORE_QUESTIONS = [
    "¿Cómo está mi empresa?",
    "¿Cuál es el principal problema de mi empresa?",
    "¿Qué está funcionando bien?",
    "¿Qué está empeorando?",
    "¿Qué productos venden más?",
    "¿Cuáles generan más revenue?",
    "¿Cuáles son los productos más rentables?",
    "¿Hay algún producto que venda mucho pero gane poco?",
    "¿Qué producto debería potenciar?",
    "¿Tengo riesgo de quedarme sin stock?",
    "¿Tengo productos con exceso de stock?",
    "¿Qué productos tienen peor rotación?",
    "¿Quiénes son mis mejores clientes?",
    "¿Qué clientes debería intentar retener?",
    "¿Hay algún comportamiento extraño en clientes?",
    "¿Qué proveedores me están costando más?",
    "¿Han aumentado los costes de algún proveedor?",
    "¿Hay algo que debería renegociar?",
    "¿Cómo está mi tesorería?",
    "¿Estoy generando suficiente caja?",
    "¿Hay algún riesgo financiero?",
    "¿Qué gastos están creciendo?",
    "¿Qué datos no son fiables?",
    "¿Qué información te falta?",
    "¿Qué métricas no puedes calcular con suficiente confianza?",
    "¿Qué debería hacer esta semana?",
    "Dame las 3 decisiones más importantes que debería tomar.",
    "Si solo pudiera solucionar un problema, ¿cuál sería?",
    "¿Dónde estoy perdiendo dinero?",
    "¿Dónde tengo una oportunidad de crecimiento?",
]

SPECIFIC_QUESTIONS = {
    "empresa-1": [
        "¿Qué lámpara debo promocionar más?",
        "¿Mi producto estrella es rentable?",
        "¿Qué decoración vende mejor?",
        "¿Debo pedir más stock de sillas?",
        "¿Qué clientes de decoración valen más?",
        "¿Por qué mi tesorería está tensa si vendo bien?",
        "¿Qué proveedor de iluminación me conviene más?",
        "¿Cuál es mi ticket medio y cómo ha evolucionado?",
        "¿Qué vendo en verano vs invierno?",
        "¿Vale la pena seguir vendiendo estanterías?",
    ],
    "empresa-2": [
        "¿Es rentable mi cliente más grande?",
        "¿Debería subir los precios a algún cliente?",
        "¿Qué artículo de papelería debería reponer ya?",
        "¿Dependo demasiado de algún proveedor?",
        "¿Qué clientes compran con más frecuencia?",
        "¿Qué margen tengo en papel A4?",
        "¿Mis descuentos a mayoristas son correctos?",
        "¿Qué línea de productos debería ampliar?",
        "¿Qué clientes han reducido sus compras?",
        "¿Cómo está mi concentración de ventas por cliente?",
    ],
    "empresa-3": [
        "¿Me falta stock de algún componente crítico?",
        "¿Qué producto tiene demasiado stock parado?",
        "¿Qué cables debería dejar de comprar?",
        "¿Tengo capital inmovilizado en inventario?",
        "¿Qué sensor debería reordenar con urgencia?",
        "¿Hay productos que llevan meses sin venderse?",
        "¿Qué referencia debo liquidar?",
        "¿Mi rotación de inventario es saludable?",
        "¿Qué componentes venden de forma estable?",
        "¿Cuánto dinero tengo en stock que no rota?",
    ],
    "empresa-4": [
        "¿Mis gastos fijos están subiendo?",
        "¿Puedo pagar las facturas este mes?",
        "¿Qué clientes me deben dinero?",
        "¿Tengo pagos grandes próximos?",
        "¿Estoy gastando más de lo que ingreso?",
        "¿Qué temporada vende más moda?",
        "¿Mi alquiler es demasiado caro?",
        "¿Debo recortar gastos? ¿Cuáles?",
        "¿Qué prenda tiene mejor margen?",
        "¿Estoy en riesgo de quedarme sin caja?",
    ],
    "empresa-5": [
        "¿Mis datos de catálogo son fiables?",
        "¿Tengo productos duplicados?",
        "¿Hay productos sin referencia?",
        "¿Puedo calcular márgenes de todo mi catálogo?",
        "¿Hay clientes duplicados?",
        "¿Algún pedido tiene datos raros?",
        "¿Qué parte de mis ventas no puedo analizar?",
        "¿Debo limpiar algo antes de tomar decisiones?",
        "¿Qué productos no tienen coste?",
        "¿Confías en los números que me das?",
    ],
}


def _py(cmd: list[str], env: dict | None = None, timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(PYTHON)] + cmd,
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def sandbox_env(sandbox: Path) -> dict:
    env = dict(os.environ)
    env["LOCALAPPDATA"] = str(sandbox)
    (sandbox / "hermes").mkdir(parents=True, exist_ok=True)
    (sandbox / "hermes" / ".env").write_text("", encoding="utf-8")
    return env


def import_company(company_id: str, reuse: bool = False) -> Path:
    sandbox = SANDBOX_ROOT / company_id
    if sandbox.exists() and reuse:
        print(f"[{company_id}] sandbox reutilizado (importación previa intacta)")
        return sandbox
    if sandbox.exists():
        shutil.rmtree(sandbox)
    sandbox.mkdir(parents=True, exist_ok=True)
    env = sandbox_env(sandbox)
    src = BENCH_DATA / company_id

    for csv_name in ("productos.csv", "ventas.csv", "clientes.csv"):
        path = src / csv_name
        r = _py(["-c",
                 "import json, sys\n"
                 f"sys.path.insert(0, r\"{ROOT}\")\n"
                 "from desktop.runtime import file_inventory\n"
                 f"result = file_inventory.add_imported_file({{\"name\": \"{csv_name}\", "
                 f"\"ext\": \"csv\", \"path\": r\"{path}\", \"size\": {path.stat().st_size}}})\n"
                 "print(json.dumps(result, ensure_ascii=False))"], env=env)
        if r.returncode != 0:
            print(f"[{company_id}] ERROR import {csv_name}:\n{r.stderr[-600:]}")
        else:
            try:
                out = json.loads(r.stdout.strip().splitlines()[-1])
                print(f"[{company_id}] import {csv_name}: ok={out.get('ok')} files={out.get('count')}")
            except Exception:
                print(f"[{company_id}] import {csv_name}: {r.stdout[-200:]}")

    canon_path = src / "canonical-connector.json"
    r = _py(["-c",
             "import json, sys\n"
             f"sys.path.insert(0, r\"{ROOT}\")\n"
             "from desktop.runtime import config_store\n"
             f"payload = json.loads(open(r\"{canon_path}\", encoding=\"utf-8\").read())\n"
             "config_store.save({\"organizedSuppliers\": payload.get(\"organizedSuppliers\") or [],\n"
             "                   \"organizedInvoices\": payload.get(\"organizedInvoices\") or [],\n"
             "                   \"organizedInvoiceLines\": payload.get(\"organizedInvoiceLines\") or [],\n"
             "                   \"organizedFinance\": payload.get(\"organizedFinance\") or []})\n"
             "config_store.save({\"organizedSales\": payload.get(\"ordersWithLines\") or []})\n"
             "print(\"canonical ok\")"], env=env)
    if r.returncode != 0:
        print(f"[{company_id}] ERROR canonical:\n{r.stderr[-600:]}")
    else:
        print(f"[{company_id}] canonical-connector importado")

    r = _py(["-c",
             "import json, sys\n"
             f"sys.path.insert(0, r\"{ROOT}\")\n"
             "from desktop.runtime import business_model, product_identity, detection_engine, config_store\n"
             "data = config_store.load()\n"
             "products = [p for p in (data.get(\"organizedProducts\") or []) if isinstance(p, dict)]\n"
             "sales = [s for s in (data.get(\"organizedSales\") or []) if isinstance(s, dict)]\n"
             "customers = [c for c in (data.get(\"organizedCustomers\") or []) if isinstance(c, dict)]\n"
             "cc = product_identity.cost_coverage(sales, products)\n"
             "ic = product_identity.identity_coverage(sales, products)\n"
             "try:\n"
             "    report = business_model.integrity_report()\n"
             "    integrity_issues = report.get(\"issues\") or []\n"
             "except Exception:\n"
             "    integrity_issues = []\n"
             "try:\n"
             "    # FASE B: ejecutar el motor (persist=True) para que los hallazgos\n"
             "    # queden persistidos y Hermes los reciba vía list_findings() en su\n"
             "    # contexto (render_business_brief).\n"
             "    detection_engine.run_detection(persist=True)\n"
             "    findings = detection_engine.list_findings()\n"
             "    findings_list = findings.get(\"findings\") or []\n"
             "except Exception:\n"
             "    findings_list = []\n"
             "print(json.dumps({\"products\": len(products), \"orders\": len(sales),\n"
             "    \"customers\": len(customers),\n"
             "    \"costCoveragePct\": cc.get(\"coveragePct\"),\n"
             "    \"identityCoveragePct\": ic.get(\"coveragePct\"),\n"
             "    \"integrityIssues\": len(integrity_issues),\n"
             "    \"findings\": len(findings_list),\n"
             "    \"findingTitles\": [f.get(\"title\") or f.get(\"type\") or \"\" for f in findings_list[:25]]},\n"
             "    ensure_ascii=False, indent=1))"], env=env)
    snapshot = {}
    if r.returncode == 0:
        try:
            # El JSON se imprime con indent=1 (multilínea): parsear el stdout
            # completo, no la última línea.
            snapshot = json.loads(r.stdout.strip())
        except Exception:
            snapshot = {"raw": r.stdout[-500:]}
    else:
        snapshot = {"error": r.stderr[-600:]}
    out_dir = RESULTS_ROOT / company_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "snapshot.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[{company_id}] SNAPSHOT: {json.dumps({k: v for k, v in snapshot.items() if k != 'findingTitles'}, ensure_ascii=False)}")
    return sandbox


# Un solo proceso hace ask + poll (el worker de Hermes es un thread daemon).
_ASK_SCRIPT = r"""
import json, sys, time
sys.path.insert(0, r"{ROOT}")
from desktop.runtime import hermes_chat

def run(question, timeout_s):
    t0 = time.time()
    result = hermes_chat.ask(question)
    req_id = result.get("id")
    if not req_id:
        return {{"question": question, "direct": True, "result": result,
                "elapsedMs": round((time.time() - t0) * 1000)}}
    while time.time() - t0 < timeout_s:
        row = hermes_chat.get_request(req_id)
        st = row.get("status") if row else None
        if st in ("completed", "done"):
            return {{"question": question, "status": "completed",
                     "reply": row.get("result") or row.get("reply"),
                     "steps": row.get("steps"),
                     "elapsedMs": round((time.time() - t0) * 1000)}}
        if st in ("error", "failed"):
            return {{"question": question, "status": "error",
                     "error": row.get("error") or row,
                     "elapsedMs": round((time.time() - t0) * 1000)}}
        time.sleep(2)
    return {{"question": question, "status": "timeout",
             "elapsedMs": round((time.time() - t0) * 1000)}}

q = json.loads(sys.argv[1])
print(json.dumps(run(q, 240), ensure_ascii=False))
"""


def ask_hermes(env: dict, question: str) -> dict:
    r = _py(["-c", _ASK_SCRIPT.format(ROOT=ROOT), json.dumps(question, ensure_ascii=False)],
            env=env, timeout=300)
    if r.returncode != 0:
        return {"question": question, "status": "process_error", "error": r.stderr[-600:]}
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return {"question": question, "status": "parse_error", "error": r.stdout[-600:]}


def run_company(company_id: str, resume: bool = False, max_questions: int | None = None) -> None:
    """Ejecuta la batería de preguntas de una empresa.

    - resume=True: reutiliza el sandbox ya importado y continúa desde el número de
      respuestas ya persistidas (si answers.json es válido), en lugar de reimportar
      y volver a preguntar todo desde cero.
    - max_questions: límite para ejecutar en chunks (evita timeouts de la sesión).
    """
    print(f"\n===== {company_id} =====")
    sandbox = import_company(company_id, reuse=resume)
    env = sandbox_env(sandbox)
    questions = CORE_QUESTIONS + SPECIFIC_QUESTIONS.get(company_id, [])
    results = []
    start = 0
    out_dir = RESULTS_ROOT / company_id
    out_dir.mkdir(parents=True, exist_ok=True)
    answers_path = out_dir / "answers.json"
    if resume and answers_path.exists():
        try:
            existing = json.loads(answers_path.read_text(encoding="utf-8"))
            if isinstance(existing, list) and existing:
                results = existing
                start = len(existing)
                print(f"[{company_id}] reanudando desde pregunta {start + 1}/{len(questions)}")
        except Exception:
            print(f"[{company_id}] answers.json corrupto — empiezo de cero")
            results = []
    for i, q in enumerate(questions, 1):
        if i <= start:
            continue
        if max_questions and (i - start) > max_questions:
            print(f"[{company_id}] chunk de {max_questions} completado ({i - 1}/{len(questions)})", flush=True)
            break
        print(f"[{company_id}] {i}/{len(questions)}: {q[:55]}", flush=True)
        t0 = time.time()
        answer = ask_hermes(env, q)
        answer["num"] = i
        answer["q"] = q
        answer["wallMs"] = round((time.time() - t0) * 1000)
        status = answer.get("status", answer.get("direct", "?"))
        reply = str(answer.get("reply") or answer.get("error") or "")[:90].replace("\n", " ")
        print(f"    -> {status} | {answer.get('elapsedMs')}ms | {reply}", flush=True)
        results.append(answer)
        (answers_path).write_text(
            json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
        time.sleep(0.5)
    if len(results) >= len(questions):
        print(f"[{company_id}] guardado en {RESULTS_ROOT / company_id}")
    else:
        print(f"[{company_id}] parcial: {len(results)}/{len(questions)} (reanudable)")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    resume = "--resume" in sys.argv
    max_q = None
    for a in sys.argv[1:]:
        if a.startswith("--max="):
            try:
                max_q = int(a.split("=", 1)[1])
            except Exception:
                pass
    companies = args or list(SPECIFIC_QUESTIONS.keys())
    if not resume:
        print("Backup de la instalación real…")
        b = _py(["-c",
                 "import sys\n"
                 f"sys.path.insert(0, r\"{ROOT}\")\n"
                 "from desktop.runtime import backup_service\n"
                 "bk = backup_service.run_backup(reason=\"benchmark-fase-a\")\n"
                 "print(bk.get(\"path\") or bk.get(\"backupPath\"))"])
        print("Backup:", (b.stdout or b.stderr).strip()[-90:])

    for cid in companies:
        if (BENCH_DATA / cid).exists():
            run_company(cid, resume=resume, max_questions=max_q)
        else:
            print(f"skip {cid}: no dataset")


if __name__ == "__main__":
    main()
