"""Local Hermes chat — direct CLI execution without Cloud/Connector."""
from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
import threading
import time
from queue import Empty, Queue
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config_store, hermes_activity, hermes_config, hermes_service, hermes_sessions, hermes_shopify_setup
from .logger import get_logger
from .paths import config_dir

log = get_logger("maios.hermes_chat", "hermes-chat")

CHAT_TIMEOUT_FIRST = 600
CHAT_TIMEOUT_RESUME = 480
CHAT_QUEUE_WAIT_SECONDS = 45.0
ORPHANED_REQUEST_GRACE_SECONDS = 20.0

CHAT_FILE = config_dir() / "hermes_chat.json"
_lock = threading.Lock()
# Hermes CLI can take minutes for a cloud model. Serializing CLI sessions keeps
# two clicks from spawning two expensive terminal trees and starving the runtime.
_chat_semaphore = threading.BoundedSemaphore(value=1)
_active_request_ids: set[str] = set()
_requests: dict[str, dict[str, Any]] = {}
_conversations: dict[str, dict[str, Any]] = {}
_ready_cache: dict[str, Any] = {}
_ready_cache_at: float = 0.0
READY_CACHE_TTL = 4.0
_chat_proven: bool = False


def _cli_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env.setdefault("LANG", "C.UTF-8")
    env.setdefault("LC_ALL", "C.UTF-8")
    return env


def _fix_mojibake(text: str) -> str:
    """Repair UTF-8 bytes mis-decoded as Latin-1 (e.g. Â¿ quÃ© → ¿ qué)."""
    if not text or ("Ã" not in text and "Â" not in text):
        return text
    try:
        repaired = text.encode("latin-1").decode("utf-8")
        return repaired if repaired else text
    except (UnicodeDecodeError, UnicodeEncodeError):
        return text


def _decode_cli_text(raw: bytes | str | None) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return _fix_mojibake(raw)
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return _fix_mojibake(raw.decode(enc))
        except UnicodeDecodeError:
            continue
    return _fix_mojibake(raw.decode("utf-8", errors="replace"))


_STREAM_ICON_LABELS = {
    "🔎": "Búsqueda",
    "💻": "Terminal",
    "📁": "Archivo",
    "📄": "Archivo",
    "🌐": "Web",
    "🔗": "Enlace",
}


def _clean_display_text(value: str | None) -> str:
    """Convert Hermes terminal decoration into readable UI text.

    Hermes may emit box-drawing characters, ANSI fragments and tool emojis.
    They are useful in a terminal but confusing in VANOVA, so the dashboard
    receives plain Spanish labels instead of raw terminal markup.
    """
    text = _fix_mojibake(str(value or ""))
    for symbol, label in _STREAM_ICON_LABELS.items():
        text = text.replace(symbol, label + ": ")
    text = re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", text)
    text = re.sub(r"[╭╮╰╯│┌┐└┘├┤┬┴┼─═]", "", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return "\n".join(line.strip() for line in text.splitlines()).strip()


def _progress_kind(message: str) -> str:
    lower = (message or "").lower()
    if "💻" in (message or "") or any(word in lower for word in ("terminal", "comando", "ejecutando", "shell", "powershell")):
        return "command"
    if any(icon in (message or "") for icon in ("🔎", "📁", "📄", "🌐", "🔗")) or any(word in lower for word in ("leyendo", "buscando", "consultando", "navegando", "archivo", "web")):
        return "tool"
    return "progress"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_store() -> None:
    global _requests, _conversations
    if not CHAT_FILE.exists():
        return
    try:
        data = json.loads(CHAT_FILE.read_text(encoding="utf-8-sig"))
        _requests = data.get("requests", {})
        _conversations = data.get("conversations", {})
    except Exception as exc:
        log.warning("Could not load hermes chat store: %s", exc)


def _persist() -> None:
    CHAT_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CHAT_FILE.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps({"requests": _requests, "conversations": _conversations}, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, CHAT_FILE)


def _request_age_seconds(request: dict[str, Any]) -> float:
    created = str(request.get("created_at") or "")
    if not created:
        return float("inf")
    try:
        return max(0.0, datetime.now(timezone.utc).timestamp() - datetime.fromisoformat(created).timestamp())
    except (TypeError, ValueError, OverflowError):
        return float("inf")


def _recover_request_unlocked(request: dict[str, Any], *, reason: str) -> None:
    """Finish a request whose worker disappeared during a runtime restart.

    Requests are persisted so the UI can survive an update, but worker threads
    are deliberately not resurrected after a process restart. Leaving the old
    ``processing`` value in the store made Hermes look permanently busy and
    caused the dashboard to report a false runtime outage.
    """
    now = _now()
    request["status"] = "error"
    request["error"] = reason
    request["processed_at"] = now
    request["activity"] = "Petición interrumpida; puedes reintentarlo."
    request["recovered_at"] = now
    activity_log = list(request.get("activityLog") or [])
    activity_log.append({"step": "recovered", "message": reason, "at": now})
    request["activityLog"] = activity_log[-30:]


def recover_orphaned_requests(*, max_age_seconds: float = 0.0) -> int:
    """Mark persisted pending/processing requests with no live worker as failed.

    This is safe to call on startup and while the UI polls. A live request is
    protected by ``_active_request_ids``; only requests older than the grace
    period are recovered during normal operation.
    """
    recovered = 0
    with _lock:
        for req_id, request in _requests.items():
            if request.get("status") not in {"pending", "processing"}:
                continue
            if req_id in _active_request_ids:
                continue
            if _request_age_seconds(request) < max_age_seconds:
                continue
            _recover_request_unlocked(
                request,
                reason="La petición se interrumpió al reiniciar VANOVA. No se han modificado tus datos; puedes reintentarlo.",
            )
            recovered += 1
        if recovered:
            _persist()
    if recovered:
        log.warning("Recovered %d orphaned Hermes request(s)", recovered)
    return recovered


_load_store()


def _find_hermes_cli() -> list[str]:
    path = hermes_service._find_hermes()  # noqa: SLF001 — shared discovery
    if path:
        return [path]
    exe = shutil.which("hermes")
    return [exe] if exe else ["hermes"]


def _chat_model() -> tuple[str, str, bool]:
    """Return (provider_id, model, pass -m flag). Hermes config.yaml is always source of truth."""
    hermes_config.sync_maios_from_hermes()
    hcfg = hermes_config.load_config()
    pid, model = hermes_config.active_model()
    if hcfg.get("found") and hcfg.get("ollamaLaunch"):
        # ollama launch hermes: model lives in config.yaml — never pass -m (avoids openrouter/auto override)
        return pid or "ollama-launch", model or str(hcfg.get("model") or ""), False
    if model:
        return pid, model, hermes_config.should_use_hermes_model_flag()
    primary = config_store.load().get("aiProviders", {}).get("primary", {})
    env_model = str(os.getenv("MAIOS_AI_MODEL") or "").strip()
    env_pid = str(os.getenv("MAIOS_AI_PROVIDER") or "").strip()
    model = str(primary.get("model") or env_model or "").strip()
    pid = str(primary.get("providerId") or env_pid or "")
    # Never pass stale openrouter/auto to hermes CLI
    if pid == "openrouter" or model.startswith("openrouter/"):
        return "", "", False
    return pid, model, bool(model) and pid not in ("ollama-launch", "ollama")


def _preflight_chat() -> str | None:
    pid, model, _ = _chat_model()
    if pid in ("ollama-launch", "ollama") or ":cloud" in model:
        ollama = hermes_config.check_ollama()
        if not ollama.get("running"):
            return ollama.get("message") or "Ollama no responde. Ejecuta «ollama serve» o «ollama launch hermes»."
    return None


def _classify_cli_error(stderr: str, stdout: str) -> str:
    text = f"{stderr}\n{stdout}".lower()
    if "openrouter/auto" in text or "openrouter" in text and "404" in text:
        return (
            "Modelo incorrecto (openrouter/auto). VANOVA debe usar config.yaml de Hermes. "
            "Reinicia VANOVA tras «ollama launch hermes --model deepseek-v4-flash:cloud»."
        )
    if "connection refused" in text or "failed to connect" in text or "dial tcp" in text:
        if "11434" in text or "ollama" in text:
            return "Ollama no responde en localhost:11434 — inicia Ollama (ollama serve) y comprueba que el modelo esté descargado."
        return "No se pudo conectar al proveedor de IA local. Comprueba que el servicio (Ollama u otro) esté en ejecución."
    if "401" in text or "unauthorized" in text or "invalid api key" in text or "authentication" in text:
        return "API key inválida o caducada (NVIDIA/OpenAI/etc.). Reconfigura el proveedor en Ajustes → Configure your AI."
    if "404" in text and "model" in text:
        return "Modelo no encontrado. Comprueba el nombre del modelo en config.yaml (deepseek-v4-flash:cloud)."
    if "hermes" in text and ("not found" in text or "no se reconoce" in text):
        return "Hermes CLI no encontrado. Instala Hermes o indica la ruta en Ajustes."
    if "loading" in text or "pulling" in text:
        return "El modelo se está cargando (primera consulta puede tardar 1-3 min). Espera e inténtalo de nuevo."
    if "timeout" in text or "timed out" in text:
        return "Hermes tardó demasiado. Los modelos cloud (:cloud) pueden tardar en la primera respuesta — prueba de nuevo o usa un mensaje más corto."
    detail = [
        ln.strip()
        for ln in (stderr or stdout or "").strip().splitlines()
        if ln.strip() and not ln.strip().startswith("session_id:")
    ]
    if detail:
        line = detail[-1][:240]
        return f"Hermes no pudo completar la consulta: {line}"
    return "Hermes no pudo completar la consulta. Comprueba el proveedor de IA configurado."


_CLI_NOISE_PREFIXES = (
    "Query:",
    "Initializing agent",
    "Resume this session with:",
    "Session:",
    "Duration:",
    "Messages:",
)


def _is_cli_noise(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    if s.startswith(_CLI_NOISE_PREFIXES):
        return True
    if s.startswith(("┊", "│", "╭", "╰")):
        return True
    if set(s) <= {"─", "═", " "}:
        return True
    return False


def _clean_cli_output(stdout: str, stderr: str) -> str:
    """Return assistant text only; Hermes prints terminal decoration too."""
    lines = [
        _clean_display_text(ln)
        for ln in stdout.splitlines()
        if not _is_cli_noise(ln)
    ]
    return "\n".join(ln for ln in lines if ln).strip()


# FASE C (cierre): el CLI de Hermes puede, tras un fallo de la API o un
# comportamiento errático del modelo, devolver el PROMPT completo (system hint
# + contexto operativo + pregunta) en lugar de una respuesta. Es un leak de
# prompt/contexto: el empresario vería bloques internos como "[Contexto
# VANOVA — usa estos hechos…]". La protección es GENERAL (marcadores, no
# preguntas concretas): si la respuesta contiene estos bloques, se recortan y
# se conserva solo la parte que no es contexto interno.
_CONTEXT_LEAK_MARKERS = (
    "[Contexto VANOVA",
    "[DATOS REALES DE VANOVA",
    # Prefijo corto a propósito: cubre el hint real ("…orquestador de VANOVA")
    # y variantes/paráfrasis del modelo ("…orquestador de datos de VANOVA",
    # "…orquestador del sistema") sin depender de la redacción exacta.
    "[Sistema] Eres el orquestador",
    "[Nota: no menciones Shopify",
)

_API_FAILURE_MARKERS = (
    "API call failed after",
    "API call failed (attempt",
    "InternalServerError",
    "dial tcp: lookup",
    "connection refused",
    "hermes --resume",
    "HTTP 50",
    "HTTP 40",
)


def _strip_prompt_leak(
    text: str,
    *,
    action_hint: str = "",
    context: str = "",
    message: str = "",
) -> str:
    """Remove any trace of the injected VANOVA prompt/context from a reply.

    Hermes CLI occasionally echoes back the exact prompt (system hint +
    operational context + user message) instead of answering — typically after
    an upstream API failure. This guard is general: it never depends on a
    specific question. It removes

    - the exact echoed prompt (action_hint + context + message) when present;
    - any internal block marked ``[Contexto VANOVA`` / ``[DATOS REALES DE
      VANOVA`` / ``[Sistema] Eres el orquestador…`` / ``[Nota: no menciones
      Shopify``, keeping the part before the block (a real answer);
    - the tail of the system hint when the model only echoed its end;
    - trailing CLI/API failure noise (resume command, retries).

    Returns the sanitized text (possibly empty → caller reports an honest
    error instead of exposing internal context).
    """
    if not text:
        return ""
    out = text.strip()

    # 1) Echo literal del prompt completo (fidelidad máxima).
    full_prompt = (action_hint + context + "\n\n" + message).strip()
    if full_prompt and full_prompt in out:
        out = out.replace(full_prompt, " ")

    # 2) Cola del system hint sin su apertura ("…usando el proveedor de IA…].").
    hint_tail = "usando el proveedor de IA ya configurado en Hermes"
    tidx = out.find(hint_tail)
    if tidx >= 0:
        close = out.find("]", tidx)
        if close >= 0:
            out = (out[:tidx] + " " + out[close + 1 :]).strip()

    # 3) Bloques de contexto interno reproducidos: cortar el bloque completo.
    #    El bloque termina donde aparece la pregunta del usuario (si el modelo
    #    la re-ecoó) o al final del texto.
    cut_done = False
    for marker in _CONTEXT_LEAK_MARKERS:
        idx = out.find(marker)
        if idx < 0:
            continue
        cut_end = len(out)
        um = (message or "").strip()
        if um:
            qpos = out.find(um, idx + len(marker))
            if qpos >= 0:
                cut_end = qpos + len(um)
        out = (out[:idx] + " " + out[cut_end:]).strip()
        cut_done = True
        break
    if cut_done:
        # Volver a barrer por si quedó otro bloque interno tras el primero.
        out = _strip_prompt_leak(out, action_hint="", context="", message=message)

    # 4) Ruido de fallo de API/CLI (retries, comando resume, logs del proveedor).
    #    Si tras recortar el prompt interno lo que queda es mayormente un fallo
    #    del proveedor, no es una respuesta válida: devolver vacío para que el
    #    llamador reporte un error honesto (nunca el log interno).
    for noise in _API_FAILURE_MARKERS:
        n = out.find(noise)
        if n >= 0:
            before = out[:n].strip()
            # Solo conservar si hay una respuesta real sustancial delante.
            if len(before) >= 80 and not before.startswith(("Initializing", "⚠️", "🔌", "📝", "Web:", "Provider:")):
                out = before
                break
            return ""

    # 5) Líneas de log/estado del CLI (no parte de la respuesta): inicialización,
    #    provider, endpoints, emojis de estado. Se filtran línea a línea.
    _CLI_LOG_PREFIXES = (
        "Initializing",
        "⚠️",
        "🔌",
        "📝",
        "Web:",
        "Provider:",
        "Endpoint:",
        "Model:",
        "hermes --resume",
        "Resume this session",
        "Session:",
        "Duration:",
    )
    kept = []
    for line in out.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith(_CLI_LOG_PREFIXES) or s.startswith(("┊", "│", "╭", "╰")):
            continue
        if set(s) <= {"─", "═", " "}:
            continue
        kept.append(s)
    return "\n".join(kept).strip()


def _terminate_cli_process(proc: subprocess.Popen) -> None:
    """Stop a timed-out Hermes CLI and its tool subprocesses without a window."""
    try:
        if proc.poll() is not None:
            return
    except Exception:
        pass
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode == 0:
                return
        except Exception as exc:
            log.warning("Could not terminate Hermes process tree: %s", exc)
    try:
        proc.kill()
    except Exception:
        pass


def _extract_session_id(stdout: str, stderr: str) -> str:
    for line in (stdout + "\n" + stderr).splitlines():
        s = line.strip()
        if s.startswith("session_id:"):
            return s.split(":", 1)[1].strip()
        if s.startswith("Session:"):
            val = s.split(":", 1)[1].strip()
            if val and not val.lower().startswith(("resume", "name")):
                return val
    return ""


def build_operational_context(*, include_shopify: bool = True, domain: str = "general") -> dict[str, Any]:
    """Structured VANOVA state for Hermes CLI injection and UI «Estado operativo» panel.

    MEGA UPDATE (A6): ``domain`` selecciona las secciones del textBlock según
    la pregunta (product/stock/customer/supplier/finance/general). La caché se
    indexa por dominio para no servir un contexto general a una pregunta de
    clientes (ni al revés)."""
    global _context_cache, _context_cache_ts, _context_cache_domain
    # FASE 15: la caché aplica SIEMPRE (antes solo con include_shopify=True, lo
    # que forzaba construir el contexto dos veces por consulta casual). El
    # textBlock base es idéntico; la nota "no menciones Shopify" se añade en
    # _build_chat_context encima del bloque cacheado.
    now = time.monotonic()
    if _context_cache is not None and _context_cache_domain == domain and (now - _context_cache_ts) < CONTEXT_CACHE_TTL_SECONDS:
        return copy.deepcopy(_context_cache)
    _build_started = time.monotonic()
    from . import agent_architect, file_inventory, file_organizer, health_monitor, hermes_config, integrations_store, process_manager, shopify_sync
    from .honest_state import describe_mode, normalize_mode

    data = config_store.load()
    org = data.get("fileOrganization") or {}
    all_products = [p for p in (data.get("organizedProducts") or []) if file_organizer._is_product_entity(p)]
    sales = data.get("organizedSales") or []
    if not isinstance(sales, list):
        sales = []

    local_products = [p for p in all_products if (p.get("source") or "local") != "shopify"]
    shopify_products = [p for p in all_products if p.get("source") == "shopify"]
    local_sales = [s for s in sales if isinstance(s, dict) and s.get("source") != "shopify"]
    shopify_sales = [s for s in sales if isinstance(s, dict) and s.get("source") == "shopify"]

    files_info = file_inventory.list_imported_files()
    file_count = int(files_info.get("count") or 0)
    scan_files = files_info.get("files") or []
    product_file_count = sum(
        1 for f in scan_files if isinstance(f, dict) and f.get("category") == "products"
    ) or int(org.get("productFiles") or 0)
    sales_file_count = sum(
        1 for f in scan_files if isinstance(f, dict) and f.get("category") == "sales"
    ) or int(org.get("salesFiles") or 0)

    shop_cfg = integrations_store.get_config("shopify")
    shop_entry = integrations_store.get_shopify_entry()
    shop_sync = shopify_sync.sync_status()
    shop_counts = shop_sync.get("counts") or {}
    missing = list(shop_sync.get("missingScopes") or [])
    synced_products = int(shop_counts.get("products") or len(shopify_products))
    synced_orders = int(shop_counts.get("orders") or len(shopify_sales))

    snapshot = data.get("dashboardSnapshot") or {}
    has_local = bool(all_products or sales or file_count)
    mode_info = describe_mode(
        normalize_mode(snapshot.get("dataMode") or data.get("dataMode"), has_local_files=has_local)
    )

    # FASE HERMES (P1): las sondas a procesos/servicios son independientes y
    # cada una puede tardar 200-500 ms (timeouts de red). Ejecutarlas en
    # paralelo recorta el build frío del contexto de ~1.2 s a ~0.5 s sin
    # cambiar ningún dato ni comportamiento.
    import concurrent.futures as _futures

    def _probe_services() -> tuple[dict, dict, dict, dict, list]:
        with _futures.ThreadPoolExecutor(max_workers=5) as ex:
            f_hs = ex.submit(hermes_service.status)
            f_hcfg = ex.submit(hermes_config.load_config)
            f_pm = ex.submit(process_manager.status)
            f_health = ex.submit(health_monitor.check_all)
            f_agents = ex.submit(agent_architect.list_agents)
            return (
                f_hs.result(timeout=8),
                f_hcfg.result(timeout=8),
                f_pm.result(timeout=8),
                f_health.result(timeout=8),
                f_agents.result(timeout=8),
            )

    try:
        hs, hcfg, pm, health, agents = _probe_services()
    except Exception:  # noqa: BLE001 — si una sonda falla, el contexto continúa
        hs, hcfg, pm, health, agents = {}, {}, {}, {}, []
    health_components = health.get("components") or {} if isinstance(health, dict) else {}
    agent_summary = []
    for ag in agents[:12]:
        agent_summary.append({
            "id": ag.get("id"),
            "name": ag.get("name"),
            "status": ag.get("status", "idle"),
            "statusReason": ag.get("statusReason", ""),
        })

    counts = {
        "organizedProductsTotal": len(all_products),
        "organizedProductsLocal": len(local_products),
        "organizedProductsShopify": len(shopify_products),
        "catalogExcelRows": len(local_products),
        "organizedSalesTotal": len(sales),
        "organizedSalesLocal": len(local_sales),
        "organizedSalesShopify": len(shopify_sales),
        "shopifySyncedProducts": synced_products,
        "shopifySyncedOrders": synced_orders,
        "productFiles": product_file_count,
        "salesFiles": sales_file_count,
        "totalFiles": file_count,
    }

    lines: list[str] = [
        "[Contexto VANOVA — usa estos hechos; no contradigas el estado real]",
        f"- dataMode: {mode_info['dataMode']} ({mode_info['label']}) — {mode_info['description']}",
        (
            f"- Productos organizados: {counts['organizedProductsTotal']} total "
            f"({counts['organizedProductsLocal']} local/Excel + {counts['organizedProductsShopify']} conectores)"
        ),
        (
            f"- Catálogo Excel/local: {counts['catalogExcelRows']} filas producto en "
            f"{counts['productFiles']} archivos"
        ),
        (
            f"- Ventas/pedidos organizados: {counts['organizedSalesTotal']} total "
            f"({counts['organizedSalesLocal']} local + {counts['organizedSalesShopify']} conectores)"
        ),
        f"- Archivos importados: {counts['totalFiles']} ({counts['productFiles']} productos, {counts['salesFiles']} ventas)",
    ]
    # FASE 10 (H19): agregados de ventas en el contexto — sin esto Hermes solo
    # veía el conteo y una muestra, y pedía "consulta get_sales()" para
    # responder revenue total / ticket medio / evolución mensual.
    # FASE HERMES (P2): el total NUNCA se presenta como la suma de los meses
    # visibles. Se declara el rango real del histórico y se advierte cuando la
    # muestra visible no cubre el total, para que Hermes no fabrique una
    # "evolución" con una ventana parcial.
    _sales_ctx: dict[str, Any] = {}
    try:
        from . import business_model

        sm = business_model.sales_summary(sales, products=all_products)
        _sales_ctx["sm"] = sm
        if sm.get("orders"):
            total_rev = sm.get("revenue") or 0.0
            aov = round(total_rev / sm["orders"], 2)
            _sales_ctx["total_rev"] = total_rev
            _sales_ctx["aov"] = aov
            months = sm.get("byMonth") or []
            shown = months[-3:]
            lines.append(
                f"- Ventas (agregado): {sm['orders']} pedidos, revenue total {total_rev:.2f} € "
                f"(TODO el histórico importado), ticket medio {aov:.2f} €"
            )
            if months:
                shown_sum = round(sum(m["revenue"] for m in shown), 2)
                period_txt = f"{months[0]['period']} a {months[-1]['period']} ({len(months)} meses con datos)"
                lines.append(
                    f"- Ventas por mes (año en curso — histórico {period_txt}): "
                    + "; ".join(f"{m['period']}: {m['revenue']:.2f} € ({m['orders']} pedidos)" for m in shown)
                )
                if len(months) > len(shown) or abs(shown_sum - total_rev) > 0.01:
                    lines.append(
                        f"  NOTA de ventana: la suma de los meses visibles ({shown_sum:.2f} €) NO es el total "
                        f"({total_rev:.2f} €). El histórico tiene más meses y/o pedidos fuera de esta muestra. "
                        "No presentes estos meses como una tendencia completa del negocio: di que el total "
                        "cubre todo el histórico importado y que no hay suficiente cobertura mensual para "
                        "afirmar una tendencia global."
                    )
            else:
                lines.append("- Ventas por mes: sin pedidos con fecha para agrupar.")
        else:
            lines.append("- Ventas (agregado): sin pedidos")
    except Exception:  # noqa: BLE001 — el resumen nunca debe romper el contexto
        pass
    # FASE 11 — calidad de datos: cobertura de coste e identidad. Hermes debe
    # poder responder "¿qué % de mis ventas tiene coste real?" con números
    # canónicos y decir exactamente por qué el margen no es calculable.
    _coverage_ctx: dict[str, Any] = {}
    try:
        from . import product_identity

        cc = product_identity.cost_coverage(sales, all_products)
        ic = product_identity.identity_coverage(sales, all_products)
        _coverage_ctx["cc"] = cc
        _coverage_ctx["ic"] = ic
        total_rev_c = round((cc.get("revenueWithVerifiedCost") or 0.0) + (cc.get("revenueWithMissingCost") or 0.0), 2)
        lines.append(
            f"- CALIDAD DE DATOS: {cc.get('coveragePct')}% del revenue tiene coste real "
            f"({cc.get('revenueWithVerifiedCost')}€ de {total_rev_c}€); "
            f"{ic.get('coveragePct')}% del revenue tiene identidad de producto "
            f"({ic.get('matchedLines')} líneas con match / {ic.get('unmatchedLines')} sin match). "
            "SIN coste verificado el margen NO es calculable — responde con estos números "
            "y di qué falta (costes reales, mapping de SKUs, FacturaScripts), nunca inventes un coste."
        )
    except Exception:  # noqa: BLE001
        pass
    # FASE HERMES (P7): DATA COVERAGE — Hermes debe saber automáticamente qué
    # puede afirmar por dominio y qué no, con estados VERIFIED / PARTIAL /
    # BLOCKED / NO DISPONIBLE, para no confundir "sin datos" con "0" ni
    # "desconectado" con "no existe".
    try:
        cc = _coverage_ctx.get("cc") or {}
        ic = _coverage_ctx.get("ic") or {}
        sm = _sales_ctx.get("sm") or {}
        total_rev = _sales_ctx.get("total_rev") or 0.0
        n_orders = sm.get("orders") or 0
        n_inv = len([i for i in (data.get("organizedInvoices") or []) if isinstance(i, dict)])
        n_fin = len([f for f in (data.get("organizedFinance") or []) if isinstance(f, dict)])
        lines.append("- DATA COVERAGE (estado por dominio — úsalo para saber qué puedes afirmar):")
        lines.append(
            f"  · Ventas: DISPONIBLE — {n_orders} pedidos, {total_rev:.2f} € "
            f"(fuentes: conectadas e importadas; cobertura mensual: {len(sm.get('byMonth') or [])} meses)"
        )
        lines.append(
            f"  · Productos: DISPONIBLE — {counts['organizedProductsTotal']} "
            f"(con coste verificado: {cc.get('productsWithVerifiedCost')}, missing: {cc.get('productsWithMissingCost')})"
        )
        lines.append(
            f"  · Costes: PARTIAL — {cc.get('coveragePct')}% del revenue con coste verificado "
            f"({cc.get('productsCoveragePct')}% de los productos tienen coste; son bases distintas); "
            "el resto MISSING → el margen NO es calculable para esa parte (no lo inventes)"
        )
        lines.append(
            f"  · Identidad: PARTIAL — {ic.get('coveragePct')}% del revenue con match de producto "
            f"({ic.get('matchedLines')} líneas con match / {ic.get('unmatchedLines')} sin match)"
        )
        if n_inv or n_fin:
            lines.append(
                f"  · Facturas/Tesorería: DATOS CANÓNICOS — {n_inv} facturas y {n_fin} movimientos en el "
                "modelo; la integración en vivo puede estar desconectada (dilo si preguntan)"
            )
        else:
            lines.append(
                "  · Facturas/Tesorería: NO DISPONIBLE — ninguna fuente conectada ni datos importados; "
                "no digas 0 €, di que no se puede determinar porque no hay datos de facturación"
            )
    except Exception:  # noqa: BLE001
        pass
    # FASE 13 (P9): capabilities — Hermes debe distinguir "esta empresa no
    # tiene facturas porque ninguna fuente las da" de "FacturaScripts está
    # desconectado". Se añade el motivo real al contexto.
    try:
        from . import connector_base

        agg = connector_base.aggregate_capabilities()
        reasons = []
        # H31 (FASE 16): la tesorería/facturación puede existir en el MODELO
        # CANÓNICO (importada vía CSV/canónico o inyectada por un conector)
        # aunque ningún conector en vivo esté conectado. Si los datos ya están
        # organizados, el motor de detección los analiza; Hermes debe decir que
        # EXISTEN datos de facturas/tesorería y que la integración en vivo está
        # desconectada — no negar los datos que ya hay.
        invoices = [i for i in (data.get("organizedInvoices") or []) if isinstance(i, dict)]
        finance = [f for f in (data.get("organizedFinance") or []) if isinstance(f, dict)]
        canon_invoices = bool(invoices)
        canon_finance = bool(finance)
        for cap in (connector_base.CAP_INVOICES, connector_base.CAP_PAYMENTS, connector_base.CAP_FINANCE):
            if agg.get(cap):
                continue
            reason = connector_base.missing_capability_reason(cap)
            present = (
                canon_invoices and cap == connector_base.CAP_INVOICES
            ) or (
                canon_finance and cap in (connector_base.CAP_PAYMENTS, connector_base.CAP_FINANCE)
            )
            if present:
                n_inv = len(invoices)
                n_fin = len(finance)
                reasons.append(
                    f"{connector_base.CAPABILITY_LABELS[cap].lower()}: ya hay {n_inv} facturas y {n_fin} "
                    f"movimientos en el modelo canónico ({reason}); la integración en vivo no está conectada"
                )
            else:
                reasons.append(f"{connector_base.CAPABILITY_LABELS[cap].lower()}: {reason}")
        if reasons:
            lines.append("- CAPACIDADES FALTANTES: " + "; ".join(reasons) + ". Si te preguntan por ello, usa esta explicación.")
    except Exception:  # noqa: BLE001
        pass
    # FASE 14 (auditoría pre-release): DATA HEALTH — Hermes debe saber qué
    # entidades están LEGACY / NEEDS_REVIEW / INVALID / UNKNOWN y NO presentarlas
    # como hechos confirmados. Conteo ligero y canónico del protocolo de gobernanza.
    try:
        from . import data_governance

        health = data_governance._review_counts()  # noqa: SLF001 — API interna del mismo paquete
        n_review = int(health.get("needs_review") or 0)
        n_invalid = int(health.get("invalid") or 0)
        n_legacy = int(health.get("legacy") or 0)
        if n_review or n_invalid or n_legacy:
            lines.append(
                f"- SALUD DE DATOS: {n_review} entidades requieren revisión (incluidos "
                f"{n_legacy} datos heredados) y {n_invalid} son inválidas. No las presentes "
                "como hechos confirmados: di 'hay datos históricos que requieren revisión' o "
                "'este dato está importado pero no verificado' cuando aplique."
            )
    except Exception:  # noqa: BLE001
        pass
    except Exception:  # noqa: BLE001
        pass
    if org.get("message"):
        lines.append(f"- Última organización: {org.get('message')}")

    # VANOVA PRODUCT 8 — BUSINESS BRAIN + FINDINGS + PRIORIDADES.
    # Hermes deja de reconstruir la empresa desde cero: recibe el modelo
    # estructurado (qué vende, concentración, qué falta) y los hallazgos del
    # motor determinista con su acción recomendada. NUNCA inventa: si el motor
    # no tiene findings activos, se dice explícitamente.
    try:
        from . import company_model, detection_engine, prioritization

        # El modelo se construye SIEMPRE en fresco (0.01-0.05 s): un modelo
        # persistido por una versión anterior puede estar desactualizado
        # (p. ej. resumen sin clientes porque el build antiguo no leía
        # line_items). Solo si el build falla se usa el persistido.
        try:
            brain = company_model.build_company_model(data)
        except Exception:  # noqa: BLE001
            brain = company_model.load_stored(data) or {}
        brain_sum = (brain.get("summary") or {})
        brain_conc = (brain.get("concentration") or {}).get("products") or {}
        lines.append("- BUSINESS BRAIN (modelo estructurado de la empresa — úsalo para contexto):")
        lines.append(
            f"  · Ingresos totales {brain_sum.get('revenue')} € · {brain_sum.get('orders')} pedidos · "
            f"ticket medio {brain_sum.get('avgTicket')} € · {brain_sum.get('products')} productos · "
            f"{brain_sum.get('customers')} clientes"
        )
        if brain_conc.get("topShare") is not None:
            lines.append(
                f"  · Concentración de ventas: el producto {brain_conc.get('topSku')} concentra "
                f"el {brain_conc.get('topShare')}% del revenue ({brain_conc.get('productsWithSales')} "
                "productos con ventas). Es un hecho de tus datos, no una opinión."
            )
        top_prods = (brain.get("whatSells") or {}).get("topProducts") or []
        if top_prods:
            top_txt = "; ".join(
                f"{p.get('sku')}: {p.get('revenue')} €" for p in top_prods[:5]
            )
            lines.append(f"  · Top productos por revenue: {top_txt}")
        brain_missing = brain.get("dataMissing") or []
        if brain_missing:
            lines.append("  · Lo que NO sé de esta empresa (no lo afirmes como 0 ni como correcto): "
                         + "; ".join(brain_missing[:4]))

        # Usa los findings YA persistidos por el motor (se ejecuta tras cada
        # import y con «Actualizar análisis») — Hermes interpreta, no sustituye
        # al motor. Los findings no son datos crudos: son razonamiento calculado.
        det = {"findings": data.get("businessFindings") or []}
        findings = [f for f in (det.get("findings") or []) if f.get("status") not in ("resolved", "archived")]
        if findings:
            top_findings = sorted(
                findings,
                key=lambda f: prioritization.score_finding(f),
                reverse=True,
            )[:5]
            lines.append("- FINDINGS ACTIVOS DEL MOTOR (detectados automáticamente; úsalos al responder «qué debería hacer»):")
            for f in top_findings:
                imp = (f.get("estimatedImpact") or {})
                euro = None
                for k in ("economicImpactEuro", "inventoryValue", "revenueAtRisk", "marginPotential", "cashRequired", "monthlyIncrease"):
                    v = imp.get(k)
                    if isinstance(v, (int, float)) and v > 0:
                        euro = v
                        break
                impact_txt = f" — impacto {euro:.2f} €" if euro else " — impacto no cuantificable"
                lines.append(
                    f"  · {f.get('title')} [severidad {f.get('severity')}, confianza {f.get('confidence')}]{impact_txt}. "
                    f"Evidencia: {'; '.join(str(e) for e in (f.get('evidence') or [])[:2])}. "
                    f"Acción recomendada: {f.get('recommendedAction')}."
                )
            if len(findings) > 5:
                lines.append(f"  · … y {len(findings) - 5} hallazgos más (pide el listado completo si hace falta).")
        else:
            lines.append("- FINDINGS ACTIVOS DEL MOTOR: ninguno con evidencia suficiente en este momento. "
                         "No digas que «no hay problemas»: di que el motor no ha detectado hallazgos activos con los datos actuales.")
    except Exception:  # noqa: BLE001 — el brain nunca debe romper el contexto
        pass

    # PRODUCT LEAP — OPORTUNIDADES + RECOMENDACIONES con su resultado medido.
    # Hermes responde «qué debería hacer» con las prioridades y oportunidades
    # del motor, y con el ciclo observar→recomendar→medir ya registrado.
    try:
        from . import prioritization, recommendation_store

        opps = [f for f in (data.get("businessFindings") or []) if f.get("category") == "opportunity" and f.get("status") not in ("resolved", "archived")]
        if opps:
            top_opps = sorted(opps, key=lambda f: prioritization.score_finding(f), reverse=True)[:3]
            lines.append("- OPORTUNIDADES DEL MOTOR (acciones con evidencia; úsalas al responder «¿qué oportunidad tengo?»):")
            for o in top_opps:
                lines.append(
                    f"  · {o.get('title')} [confianza {o.get('confidence')}]. "
                    f"Evidencia: {'; '.join(str(e) for e in (o.get('evidence') or [])[:2])}. "
                    f"Acción: {o.get('recommendedAction')}."
                )
        else:
            lines.append("- OPORTUNIDADES DEL MOTOR: ninguna con evidencia suficiente con los datos actuales. "
                         "Si te piden una oportunidad, di que el motor no tiene una demostrable todavía — no inventes una.")
        recs = [r for r in recommendation_store.list_recommendations() if isinstance(r, dict)]
        if recs:
            lines.append("- RECOMENDACIONES SEGUIDAS (ciclo recomendar→actuar→medir):")
            for r in recs[:5]:
                status_lbl = recommendation_store.VALID_STATUSES.get(str(r.get("status") or ""), str(r.get("status") or ""))
                outcome = r.get("outcome")
                outcome_txt = (
                    {"improved": "MEJORÓ", "worsened": "EMPEORÓ", "no_change": "SIN CAMBIO", "unmeasurable": "NO MEDIBLE"}.get(outcome, "")
                    if outcome else "pendiente de medición"
                )
                mb = (r.get("metricBefore") or {}).get("revenue")
                mn = (r.get("metricNow") or {}).get("revenue")
                metric_txt = f"antes {mb:.2f}€ → ahora {mn:.2f}€" if isinstance(mb, (int, float)) and isinstance(mn, (int, float)) else "métrica no cuantificable"
                lines.append(
                    f"  · {r.get('title')} — estado {status_lbl}, resultado {outcome_txt} ({metric_txt}). "
                    f"Acción registrada: {r.get('recommendedAction')}."
                )
        # PRODUCT LEAP — Hermes como AGENTE OPERATIVO: proponer el siguiente
        # paso concreto, mostrar qué va a cambiar, pedir confirmación antes de
        # ejecutar nada externo y registrar/medir después. Solo acciones que
        # VANOVA puede preparar o ejecutar de verdad.
        lines.append("- ACCIONES DISPONIBLES (solo con confirmación explícita del usuario): "
                     "(1) preparar plantilla CSV de costes pendientes; (2) preparar segmento de "
                     "clientes inactivos; (3) aplicar costes importados (con backup previo y "
                     "previsualización). Si el usuario te pide actuar, propón el siguiente paso "
                     "concreto con impacto esperado, muestra exactamente qué va a cambiar y pide "
                     "confirmación ANTES de ejecutar. Tras ejecutar, registra qué hiciste y di que "
                     "el resultado se medirá en el próximo análisis.")
    except Exception:  # noqa: BLE001 — nunca debe romper el contexto
        pass

    # FASE 13 (P9/P10): «Fuentes de datos» genérico. Hermes no piensa "Shopify
    # tiene X" sino "los datos disponibles de esta empresa vienen de estas
    # fuentes, cada una con sus capacidades". Shopify es un conector más.
    from . import connector_base

    sources_lines: list[str] = []
    sources_meta: list[dict[str, Any]] = []
    for src in connector_base.list_sources(implemented_only=True):
        st = src.status()
        connected = bool(st.get("connected", False) or st.get("configured", False) or st.get("ok", False))
        caps = src.effective_capabilities()
        cap_labels = [connector_base.CAPABILITY_LABELS[k] for k, v in caps.items() if v]
        meta: dict[str, Any] = {
            "source": src.id,
            "label": src.label,
            "connected": connected,
            "status": st.get("status", "unknown"),
            "lastSync": st.get("lastSync"),
            "capabilities": caps,
            "capabilityLabels": cap_labels,
        }
        if src.id == "shopify":
            via_hermes = shop_entry.get("source") == "hermes-env"
            meta["viaHermes"] = via_hermes
            meta["url"] = shop_cfg.get("url") or shop_sync.get("url") or ""
            meta["needsReauth"] = bool(missing or shopify_sync.needs_reauth())
            meta["missingScopes"] = list(missing)
            meta["syncedProducts"] = synced_products
            meta["syncedOrders"] = synced_orders
        sources_meta.append(meta)
        if not connected:
            sources_lines.append(f"- {src.label}: no conectado.")
            continue
        if src.id == "shopify" and (missing or shopify_sync.needs_reauth()):
            scope_list = ", ".join(missing) if missing else "read_products, read_orders"
            prefix = "Shopify (vía Hermes): CONECTADO pero" if meta.get("viaHermes") else "Shopify: CONECTADO pero"
            sources_lines.append(
                f"- {prefix} faltan permisos ({scope_list}). Los productos Excel/locales siguen disponibles."
            )
            continue
        extra = ""
        if src.id == "shopify":
            extra = f"; sync {shop_sync.get('status', 'idle')}; {synced_products} productos y {synced_orders} pedidos en última sync"
        elif st.get("lastSync"):
            extra = f"; última sync {st.get('lastSync')}"
        caps_txt = (f" — datos disponibles: {', '.join(cap_labels)}") if cap_labels else ""
        sources_lines.append(f"- {src.label}: conectado{extra}{caps_txt}")
    if sources_lines:
        lines.append("- Fuentes de datos: " + "; ".join(sources_lines))
    shopify_section = next((m for m in sources_meta if m["source"] == "shopify"), {
        "connected": bool(shop_cfg.get("connected")),
        "message": "No conectado" if include_shopify else "Omitido",
    })

    cloud_comp = health_components.get("cloud") or {}
    connector_comp = health_components.get("connector") or {}
    lines.extend([
        f"- Hermes: {'online' if hs.get('healthy') else 'offline'} ({hcfg.get('model') or hs.get('activeModel') or 'sin modelo'})",
        f"- Cloud: {cloud_comp.get('status', 'unknown')} — {cloud_comp.get('message') or ('activo' if pm.get('cloud', {}).get('running') else 'inactivo')}",
        f"- Connector: {connector_comp.get('status', 'unknown')} — {connector_comp.get('message') or ('activo' if pm.get('connector', {}).get('running') else 'inactivo')}",
    ])
    if agents:
        idle = sum(1 for a in agents if a.get("status") in ("idle", "waiting"))
        running = sum(1 for a in agents if a.get("status") == "running")
        lines.append(f"- Agentes: {len(agents)} configurados ({running} ejecutando, {idle} en espera/listos)")

    lines.append(
        "Distingue siempre: productos organizados (total local+Shopify) vs sync Shopify vs filas catálogo Excel. "
        "Si faltan datos de Shopify por permisos, menciona el catálogo local por separado."
    )
    # FASE HERMES (P5): respuesta ejecutiva para preguntas amplias.
    lines.append(
        "- Estilo de respuesta: cuando te pidan el estado general de la empresa (\"¿cómo está la empresa?\", "
        "\"¿qué tal va todo?\"), responde en 5 secciones breves: ESTADO GENERAL · NÚMEROS CLAVE · "
        "QUÉ FUNCIONA · QUÉ ESTÁ BLOQUEADO · SIGUIENTE ACCIÓN. Sé directo, 150-250 palabras, y no repitas "
        "datos que ya hayas dado."
    )
    # FASE HERMES (P3/P4): separar HECHO / INFERENCIA / NO DISPONIBLE y no
    # afirmar más fuerte que la evidencia.
    lines.append(
        "- Lógica: separa HECHO (dato real, con su fuente), INFERENCIA (interpretación — dilo como tal) "
        "y NO DISPONIBLE (dato ausente). Nunca conviertas \"sin dato\" en 0 € ni \"desconectado\" en "
        "\"no existe\": di \"no se puede determinar porque…\". Correlación ≠ causalidad: no digas "
        "\"sin discusión\" ni \"producto ancla\"; di \"el producto con mayor peso en las ventas "
        "registradas: X € (Y% del revenue)\"."
    )

    # Real data rows (SKU + prices + sales) — the agent must see the SAME
    # facts the Dashboard renders, not just counters.
    try:
        from . import agent_data_tools

        # FASE HERMES (P1): las coberturas ya se calcularon arriba — se pasan
        # precalculadas para no repetir dos veces el mismo cálculo por build.
        pre_cov = None
        if _coverage_ctx.get("cc") is not None and _coverage_ctx.get("ic") is not None:
            pre_cov = {"cc": _coverage_ctx["cc"], "ic": _coverage_ctx["ic"]}
        text_block = "\n".join(lines) + "\n\n" + agent_data_tools.render_context_block(limit=30, precomputed_coverage=pre_cov, domain=domain)
    except Exception:  # noqa: BLE001
        text_block = "\n".join(lines)
    summary = {
        "productos": {
            "total": counts["organizedProductsTotal"],
            "local": counts["organizedProductsLocal"],
            "shopify": counts["organizedProductsShopify"],
            "catalogExcelRows": counts["catalogExcelRows"],
            "productFiles": counts["productFiles"],
            "shopifySynced": synced_products,
        },
        "pedidos": {
            "total": counts["organizedSalesTotal"],
            "local": counts["organizedSalesLocal"],
            "shopify": counts["organizedSalesShopify"],
            "shopifySynced": synced_orders,
        },
        "archivos": {
            "total": counts["totalFiles"],
            "productFiles": counts["productFiles"],
            "salesFiles": counts["salesFiles"],
        },
        "integraciones": {
            "shopify": shopify_section,
            "facturascript": _facturascript_context(),
            "hermes": {
                "healthy": bool(hs.get("healthy")),
                "model": hcfg.get("model") or hs.get("activeModel") or "",
                "provider": hcfg.get("providerId") or hs.get("activeProvider") or "",
                "launchMode": hs.get("launchMode") or "",
            },
            "cloud": {
                "status": cloud_comp.get("status", "unknown"),
                "running": bool(pm.get("cloud", {}).get("running")),
                "message": cloud_comp.get("message") or "",
            },
            "connector": {
                "status": connector_comp.get("status", "unknown"),
                "running": bool(pm.get("connector", {}).get("running")),
                "message": connector_comp.get("message") or "",
            },
        },
        "dataMode": mode_info,
        "agentes": agent_summary,
    }

    result = {
        "title": "[Contexto VANOVA]",
        "textBlock": text_block,
        "lines": lines,
        "counts": counts,
        "summary": summary,
        "updatedAt": _now(),
    }
    # Solo se cachea un build caro (sondas de red lentas). Un build rápido no
    # necesita caché y así los tests con mocks siempre ven datos frescos.
    if (time.monotonic() - _build_started) >= 0.15:
        _context_cache = result
        _context_cache_ts = time.monotonic()
        _context_cache_domain = domain
    return result


def _facturascript_context() -> dict[str, Any]:
    """FASE 4 — structured FacturaScripts facts (or honest absence)."""
    try:
        from . import facturascripts_sync

        fs = facturascripts_sync.sync_status()
        if not fs.get("configured"):
            return {"connected": False, "message": "No conectado"}
        t = facturascripts_sync.treasury_summary()
        return {
            "connected": True,
            "status": fs.get("status"),
            "lastSync": fs.get("lastSync"),
            "counts": fs.get("counts") or {},
            "treasury": t if t.get("available") else None,
            "resourceErrors": fs.get("resourceErrors") or {},
            "error": fs.get("error"),
        }
    except Exception as exc:  # noqa: BLE001
        return {"connected": False, "message": str(exc)}


# P6 (latencia): el contexto operativo se construye DOS veces por pregunta
# (chat + petición) y cada build sondea procesos con timeouts de ~1.5s.
# Un TTL de 10s elimina las llamadas redundantes entre preguntas sin perder
# frescura: los datos de negocio se refrescan por sync, no por pregunta.
_context_cache: dict[str, Any] | None = None
_context_cache_domain: str = "general"
_context_cache_ts: float = 0.0
CONTEXT_CACHE_TTL_SECONDS = 10.0


def operational_context() -> dict[str, Any]:
    """Public API — same facts injected into Hermes chat and shown in VANOVA UI."""
    return build_operational_context(include_shopify=True)


def _is_casual_message(message: str) -> bool:
    """FASE 15: detecta conversación casual (saludo/despedida/agradecimiento)
    claramente FUERA de los datos empresariales, para usar la ruta ligera sin
    construir el operational context (que hoy cuesta ~1s) ni tocar los datos.

    Regla conservadora: solo es casual si hay un marcador claro de saludo Y
    ninguna palabra de negocio/datos. Ante la duda → False (contexto completo),
    para no perder exactitud ni permitir alucinaciones."""
    m = (message or "").lower().strip()
    if not m or len(m) > 100:
        return False
    import re as _re

    words = _re.split(r"[^\wáéíóúñüÁÉÍÓÚÑÜ]+", m)
    words = [w for w in words if w]
    if not words:
        return False
    casual = {
        "hola", "holaa", "holaaa", "buenos", "buenas", "buen", "buena", "buenas",
        "dias", "días", "tardes", "noches", "gracias", "adios", "adiós", "chao",
        "bye", "ok", "vale", "genial", "perfecto", "bien", "tal", "estas",
        "estás", "quien", "quién", "eres", "puedes", "hacer", "saludos", "hey",
    }
    business = {
        "ventas", "venta", "vender", "vendido", "pedidos", "pedido", "productos",
        "producto", "clientes", "cliente", "facturas", "factura", "facturacion",
        "facturación", "tesoreria", "tesorería", "margen", "margenes", "márgenes",
        "coste", "costes", "stock", "inventario", "revenue", "ganancias",
        "beneficios", "beneficio", "dinero", "cuanto", "cuánto", "cuantos",
        "cuántos", "cuantas", "cuántas", "lista", "top", "analiza", "análisis",
        "analisis", "informe", "reporte", "report", "datos", "negocio", "mes",
        "hoy", "semana", "año", "presupuesto", "gastos", "cobros", "pagos",
        "proveedores", "tienda", "shopify", "woocommerce", "prestashop", "excel",
        "csv", "importar", "sincroniza", "sincronizar", "sync", "estado", "operativo",
        "cuantos pedidos", "cuanto he vendido", "cuanto hemos vendido",
    }
    has_casual = any(w in casual for w in words)
    has_business = any(w in business for w in words)
    return has_casual and not has_business


def _message_wants_shopify_context(message: str) -> bool:
    m = (message or "").lower()
    if hermes_shopify_setup.wants_shopify_setup(message):
        return True
    keys = (
        "shopify",
        "myshopify",
        "tienda online",
        "sync shopify",
        "sincroniza shopify",
        "integración shopify",
        "integracion shopify",
        "pedidos shopify",
        "productos shopify",
    )
    return any(k in m for k in keys)


def _message_wants_operational_detail(message: str) -> bool:
    m = (message or "").lower().strip()
    if not m:
        return False
    keys = (
        "estado operativo",
        "estado del sistema",
        "estado de maios",
        "diagnóstico",
        "diagnostico",
        "qué productos tengo",
        "que productos tengo",
        "cuántos productos",
        "cuantos productos",
        "resumen del sistema",
        "resumen operativo",
        "command center",
    )
    return any(k in m for k in keys)


def _build_chat_context(message: str = "") -> str:
    # FASE 15 (ruta ligera): saludo/conversación casual sin datos empresariales
    # → contexto mínimo sin construir el operational context (~1s) ni tocar
    # datos. El prompt deja claro que NO hay datos cargados: si el usuario
    # pregunta por cifras, Hermes debe decirlo, nunca inventarlas.
    if _is_casual_message(message):
        return (
            "[Contexto VANOVA — conversación casual. En este turno NO se cargaron "
            "datos de negocio (ventas, pedidos, productos, márgenes, facturas, "
            "tesorería). Responde de forma natural y breve. Si el usuario te pide "
            "cifras o datos de su empresa, di con honestidad que en este mensaje "
            "no tienes los datos cargados y sugiérele que haga la pregunta concreta "
            "(p. ej. \"¿cuántos pedidos tengo?\"). Nunca inventes números.]\n\n"
        )
    from . import agent_data_tools

    include_shopify = _message_wants_shopify_context(message)
    domain = agent_data_tools._question_domain(message)
    ctx = build_operational_context(include_shopify=include_shopify, domain=domain)
    block = ctx["textBlock"]
    if not include_shopify:
        block += (
            "\n[Nota: no menciones Shopify salvo que el usuario lo pida "
            "explícitamente en este mensaje.]"
        )
    return block


def _run_hermes_cli(
    message: str,
    session_id: str = "",
    progress_cb=None,
    profile: str = "",
) -> dict[str, Any]:
    """Run Hermes chat streaming (no --quiet) so intermediate steps and partial
    text can be surfaced in real time via ``progress_cb``.

    When ``profile`` is given (bot-mode / FASE B), the query runs under that
    Hermes profile so the exchange is persisted as a conversation in the
    agent's own profile (``hermes -p <profile> chat …``).
    """
    import time as _time

    if not hermes_service._find_hermes() and not shutil.which("hermes"):  # noqa: SLF001
        return {"status": "error", "summary": "Hermes CLI no encontrado. Instala con «ollama launch hermes»."}

    preflight = _preflight_chat()
    if preflight:
        return {"status": "error", "summary": preflight}

    provider_id, model, pass_model = _chat_model()
    timeout = CHAT_TIMEOUT_RESUME if session_id else CHAT_TIMEOUT_FIRST

    action_hint = (
        "[Sistema] Eres el orquestador de VANOVA. Responde al mensaje del usuario usando "
        "el proveedor de IA ya configurado en Hermes (NVIDIA, Ollama, etc.).] "
    )
    context = _build_chat_context(message)
    # NOTE: no --quiet — without it the CLI streams steps (┊ tool lines) and the
    # answer box line by line, which is what powers the live progress UI.
    cli = _find_hermes_cli()
    if profile:
        # FASE B: ejecutar bajo el perfil Hermes del bot del agente para que la
        # conversación quede persistida en su propio perfil (no en el default).
        cli = cli + ["-p", profile]
    cmd = cli + ["chat", "-q", action_hint + context + "\n\n" + message]
    if session_id:
        cmd += ["--resume", session_id]
    if pass_model and model:
        cmd += ["-m", model]

    # FASE HERMES: el cmd contiene el contexto operativo COMPLETO (nombres de
    # clientes, emails, productos…). Loggearlo entero filtra PII al archivo de
    # log en cada consulta. Se registra solo un resumen del arranque: binario,
    # flags, modelo y longitud del prompt, nunca el contenido.
    log.info(
        "Hermes chat start provider=%s model=%s pass_model=%s timeout=%ss session=%s prompt_len=%d chars",
        provider_id or "?",
        model or "(hermes-config)",
        pass_model,
        timeout,
        "resume" if session_id else "new",
        len(action_hint) + len(context) + len(message or ""),
    )

    events: list[dict[str, Any]] = []

    def _emit(steps, partial, status_text):
        if progress_cb is None:
            return
        try:
            progress_cb({
                "steps": list(steps),
                "partial": _clean_display_text(partial),
                "statusText": _clean_display_text(status_text),
                "events": list(events),
                "commands": [e for e in events if e.get("kind") == "command"],
            })
        except Exception:
            pass

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=_cli_env(),
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except FileNotFoundError:
        return {"status": "error", "summary": "Hermes CLI no encontrado."}
    except Exception as exc:
        return {"status": "error", "summary": str(exc)}

    stdout_parts: list[str] = []
    box_lines: list[str] = []
    steps: list[str] = []
    in_box = False
    status_text = ""
    deadline = _time.time() + timeout
    timed_out = False

    # ``readline()`` on a pipe is blocking. The old loop could therefore never
    # reach the deadline while a cloud model emitted no output, leaving a live
    # Hermes child and a request stuck in ``processing`` forever. A reader
    # thread feeds a queue so the deadline remains enforceable on Windows too.
    stream_queue: Queue[tuple[str, Any]] = Queue()

    def _read_stream() -> None:
        try:
            stream = proc.stdout
            if stream is not None:
                for raw_line in iter(stream.readline, ""):
                    stream_queue.put(("line", raw_line))
        except Exception as exc:
            stream_queue.put(("error", exc))
        finally:
            stream_queue.put(("eof", None))

    reader = threading.Thread(target=_read_stream, name="vanova-hermes-output", daemon=True)
    reader.start()

    try:
        while True:
            remaining = deadline - _time.time()
            if remaining <= 0:
                timed_out = True
                _terminate_cli_process(proc)
                break
            try:
                kind, value = stream_queue.get(timeout=min(0.25, remaining))
            except Empty:
                if proc.poll() is not None and not reader.is_alive():
                    break
                continue
            if kind == "eof":
                break
            if kind == "error":
                log.warning("Hermes chat stream error: %s", value)
                continue

            text = str(value or "").rstrip("\r\n")
            stdout_parts.append(text)
            s = text.strip()

            if "╭" in text:
                in_box = True
                continue
            if "╰" in text:
                in_box = False
                _emit(steps, "\n".join(box_lines), status_text)
                continue
            if in_box:
                inner = _clean_display_text(s.lstrip("│").strip())
                if inner:
                    box_lines.append(inner)
                _emit(steps, "\n".join(box_lines), status_text)
                continue
            if s.startswith("┊"):
                step = _clean_display_text(s.lstrip("┊").strip())
                if step and (not steps or steps[-1] != step):
                    steps.append(step)
                    events.append({
                        "kind": _progress_kind(step),
                        "label": "Comando" if _progress_kind(step) == "command" else "Progreso",
                        "message": step,
                        "at": _now(),
                    })
                status_text = step or status_text
                _emit(steps, "\n".join(box_lines), status_text)
                continue
            if s.startswith("Initializing agent") or "Initializing" in s:
                status_text = "Inicializando agente…"
                if not any(e.get("message") == status_text for e in events):
                    events.append({"kind": "progress", "label": "Progreso", "message": status_text, "at": _now()})
                _emit(steps, "\n".join(box_lines), status_text)
    except Exception as exc:
        log.warning("Hermes chat stream error: %s", exc)
    finally:
        if timed_out:
            _terminate_cli_process(proc)
        try:
            proc.wait(timeout=10)
        except Exception:
            _terminate_cli_process(proc)
            try:
                proc.wait(timeout=2)
            except Exception:
                pass

    stdout = "\n".join(stdout_parts)
    stderr = ""
    if timed_out:
        hint = ""
        if provider_id in ("ollama-launch", "ollama") or ":cloud" in model:
            hint = " Los modelos cloud (:cloud) pueden tardar 2-4 min en la primera respuesta."
        return {"status": "error", "summary": f"Hermes excedió el tiempo de espera ({timeout} s).{hint}"}

    if proc.returncode not in (0, None):
        err = _classify_cli_error(stderr, stdout)
        log.warning("Hermes chat failed rc=%s stdout=%r", proc.returncode, stdout[:400])
        return {"status": "error", "summary": err}

    summary = _clean_display_text("\n".join(box_lines).strip() or _clean_cli_output(stdout, stderr))
    # FASE C (cierre): protección anti prompt/context leakage. El CLI puede
    # devolver el prompt completo en lugar de una respuesta (p. ej. tras un
    # fallo de la API). Se recorta cualquier bloque interno y, si lo que queda
    # es vacío o solo ruido de error, se responde con un error honesto en vez
    # de exponer el contexto.
    summary = _strip_prompt_leak(summary, action_hint=action_hint, context=context, message=message)
    if not summary:
        log.warning("Hermes chat returned only internal context/error noise: %r", (stdout or "")[:300])
        return {
            "status": "error",
            "summary": "Hermes no pudo generar una respuesta (el asistente devolvió un error del proveedor de IA). Prueba de nuevo en unos segundos.",
        }

    log.info("Hermes chat OK (%d chars, %d steps)", len(summary), len(steps))
    return {
        "status": "completed",
        "summary": summary,
        "session_id": _extract_session_id(stdout, stderr) or session_id,
        "steps": steps,
        "events": events,
        "commands": [e for e in events if e.get("kind") == "command"],
    }


def _run_chat_with_slot(message: str, session_id: str = "", progress_cb=None, profile: str = "") -> dict[str, Any]:
    """Run one CLI session at a time so Hermes cannot overload the runtime."""
    if not _chat_semaphore.acquire(timeout=CHAT_QUEUE_WAIT_SECONDS):
        return {
            "status": "error",
            "summary": "Hermes ya está procesando otra consulta. Espera unos segundos y vuelve a intentarlo.",
        }
    try:
        return _run_hermes_cli(message, session_id=session_id, progress_cb=progress_cb, profile=profile)
    finally:
        _chat_semaphore.release()


def execute_sync(message: str, session_id: str = "", profile: str = "") -> dict[str, Any]:
    """Run Hermes synchronously for agent task execution (Phase 10).

    ``profile`` (optional) runs the query under that Hermes profile (bot-mode).
    Task execution passes the agent's bot profile (FASE B) so the exchange is
    persisted as a conversation in the agent's own Hermes profile instead of
    the default one.
    """
    if not message or not message.strip():
        return {"status": "error", "summary": "Mensaje vacío"}
    return _run_chat_with_slot(message.strip(), session_id=session_id, profile=profile)


def _resolve_conversation(conversation_id: str, message: str, now: str) -> tuple[str, str]:
    """Return (conv_id, hermes_session_id). Caller must hold _lock."""
    cli_session = hermes_sessions.parse_cli_conversation_id(conversation_id)
    if cli_session:
        for cid, conv in _conversations.items():
            if conv.get("hermes_session_id") == cli_session:
                conv["updated_at"] = now
                return cid, cli_session
        conv_id = str(uuid.uuid4())
        _conversations[conv_id] = {
            "conversation_id": conv_id,
            "title": message.strip()[:60],
            "hermes_session_id": cli_session,
            "created_at": now,
            "updated_at": now,
            "linked_from": "hermes_cli",
        }
        return conv_id, cli_session

    conv_id = conversation_id or str(uuid.uuid4())
    if conv_id not in _conversations:
        _conversations[conv_id] = {
            "conversation_id": conv_id,
            "title": message.strip()[:60],
            "hermes_session_id": "",
            "created_at": now,
            "updated_at": now,
        }
    else:
        _conversations[conv_id]["updated_at"] = now
    hermes_session = _conversations[conv_id].get("hermes_session_id") or ""
    return conv_id, hermes_session


def ask(message: str, conversation_id: str = "") -> dict[str, Any]:
    if not message or not message.strip():
        return {"error": "Mensaje vacío", "ok": False}

    req_id = str(uuid.uuid4())
    now = _now()

    with _lock:
        conv_id, _ = _resolve_conversation(conversation_id, message.strip(), now)
        safe_message = hermes_shopify_setup.redact_sensitive(message.strip())
        _requests[req_id] = {
            "id": req_id,
            "conversation_id": conv_id,
            "message": safe_message,
            "status": "pending",
            "result": None,
            "error": None,
            "created_at": now,
            "heartbeat_at": now,
            "processed_at": None,
        }
        _persist()

    threading.Thread(target=_process_request, args=(req_id,), daemon=True).start()
    return {
        "id": req_id,
        "status": "pending",
        "message": message.strip(),
        "conversation_id": conv_id,
        "source": "runtime",
    }


def get_request(req_id: str) -> dict[str, Any] | None:
    # Also heals requests left behind by an earlier runtime process without
    # waiting for a full Electron restart.
    recover_orphaned_requests(max_age_seconds=ORPHANED_REQUEST_GRACE_SECONDS)
    with _lock:
        req = _requests.get(req_id)
        return dict(req) if req else None


def list_conversations() -> list[dict[str, Any]]:
    with _lock:
        rows = sorted(_conversations.values(), key=lambda c: c.get("updated_at", ""), reverse=True)
        out: list[dict[str, Any]] = []
        linked_sessions: set[str] = set()
        for c in rows[:50]:
            msgs = sum(1 for r in _requests.values() if r.get("conversation_id") == c.get("conversation_id"))
            sid = c.get("hermes_session_id") or ""
            if sid:
                linked_sessions.add(sid)
            entry = {
                **c,
                "messages": msgs,
                "source": "maios",
                "source_label": "VANOVA",
            }
            if sid:
                entry["source_label"] = "VANOVA · enlace Hermes"
            out.append(entry)

    for cli in hermes_sessions.list_sessions(limit=30):
        sid = cli.get("hermes_session_id") or ""
        if sid and sid in linked_sessions:
            continue
        out.append(cli)

    out.sort(key=lambda c: c.get("updated_at", ""), reverse=True)
    return out[:60]


def get_messages(conv_id: str) -> list[dict[str, Any]]:
    cli_session = hermes_sessions.parse_cli_conversation_id(conv_id)
    if cli_session:
        return hermes_sessions.get_session_messages(cli_session)

    with _lock:
        rows = [dict(r) for r in _requests.values() if r.get("conversation_id") == conv_id]
        rows.sort(key=lambda r: r.get("created_at", ""))
        return rows


def chat_ready(*, force: bool = False) -> dict[str, Any]:
    """Whether local chat can run (Hermes CLI + AI provider + Ollama when required)."""
    global _ready_cache, _ready_cache_at
    if (
        not force
        and _ready_cache
        and (time.time() - _ready_cache_at) < READY_CACHE_TTL
        and _ready_cache.get("ready") is not None
    ):
        return dict(_ready_cache)

    started = time.perf_counter()
    hs = hermes_service.status()
    hermes_config.sync_maios_from_hermes()
    ai = config_store.load().get("aiProviders", {}).get("primary", {})
    hcfg = hermes_config.load_config()
    uses_ollama = bool(hcfg.get("ollamaLaunch")) or ":cloud" in str(hcfg.get("model") or "")
    ollama = hermes_config.check_ollama() if uses_ollama else {"running": True, "models": []}
    cli_ok = bool(hermes_service._find_hermes())  # noqa: SLF001
    model = str(hcfg.get("model") or ai.get("model") or "").strip()
    ai_ok = bool(hcfg.get("found") and model) or bool(ai.get("configured") and model)
    ollama_ok = bool(ollama.get("running", True))
    model_ok = True
    if uses_ollama and ollama_ok and model and ":cloud" not in model:
        names = ollama.get("models") or []
        base = model.split(":")[0]
        model_ok = any(n == model or n.startswith(base) for n in names)
    ready = cli_ok and ai_ok and ollama_ok and model_ok
    # ollama launch hermes: CLI chat works without hermes serve health or strict model list
    if not ready and hcfg.get("ollamaLaunch") and cli_ok and ollama_ok:
        ready = True
    # Successful chat proves readiness even when preflight checks lag
    if not ready and _chat_proven and cli_ok:
        ready = True
    result = {
        "ready": ready,
        "chatReady": ready,
        "hermesInstalled": cli_ok,
        "hermesHealthy": bool(hs.get("healthy")),
        "hermesWarmed": bool(hs.get("warmed")),
        "aiConfigured": ai_ok,
        "modelReachable": model_ok,
        "aiProvider": ai.get("providerName") or hcfg.get("providerName") or ai.get("providerId") or "",
        "model": model,
        "providerId": hcfg.get("providerId") or ai.get("providerId") or "",
        "ollamaRunning": ollama.get("running"),
        "hermesConfigPath": hcfg.get("path") or "",
        "latencyMs": round((time.perf_counter() - started) * 1000, 1),
        "serviceLatencyMs": hs.get("latencyMs"),
        "checkedAt": time.time(),
        "reason": (
            "ok"
            if ready
            else (
                "ollama_offline"
                if not ollama_ok
                else "model_unreachable"
                if not model_ok
                else "ai_not_configured"
                if not ai_ok
                else "hermes_cli_missing"
            )
        ),
    }
    _ready_cache = result
    _ready_cache_at = time.time()
    return dict(result)


def warm_chat() -> dict[str, Any]:
    """Pre-connect Hermes service and refresh chat-ready cache."""
    global _ready_cache, _ready_cache_at
    started = time.perf_counter()
    hermes_service.ensure_ollama_launch()
    hermes_service.start_warm_pool()
    hermes_service.ensure_running()
    _ready_cache_at = 0.0
    result = chat_ready(force=True)
    result["warmed"] = True
    result["warmLatencyMs"] = round((time.perf_counter() - started) * 1000, 1)
    _ready_cache = result
    _ready_cache_at = time.time()
    log.info(
        "Hermes chat warmed in %sms (ready=%s, service=%s)",
        result["warmLatencyMs"],
        result.get("ready"),
        result.get("hermesHealthy"),
    )
    return result


def _mark_chat_proven() -> None:
    """Chat succeeded — cache ready state so UI and health checks stay in sync."""
    global _chat_proven, _ready_cache, _ready_cache_at
    _chat_proven = True
    _ready_cache_at = 0.0
    chat_ready(force=True)


def _set_req_activity(req_id: str, message: str, *, step: str = "processing") -> None:
    hermes_activity.log_step(message, step=step, source="chat")
    with _lock:
        req = _requests.get(req_id)
        if not req:
            return
        req["status"] = "processing"
        req["activity"] = message
        req["heartbeat_at"] = _now()
        log = list(req.get("activityLog") or [])
        log.append({"step": step, "message": message, "at": _now()})
        req["activityLog"] = log[-30:]
        _persist()


def _process_request(req_id: str) -> None:
    with _lock:
        _active_request_ids.add(req_id)
    try:
        _process_request_impl(req_id)
    except Exception as exc:
        message = f"Hermes no pudo completar la petición: {_clean_display_text(str(exc))[:300]}"
        log.exception("Unhandled Hermes request failure (%s): %s", req_id, exc)
        with _lock:
            req = _requests.get(req_id)
            if req:
                req["status"] = "error"
                req["error"] = message
                req["activity"] = "Error en Hermes."
                req["processed_at"] = _now()
                req["activityLog"] = list(req.get("activityLog") or []) + [
                    {"step": "error", "message": message, "at": _now()}
                ]
                _persist()
    finally:
        with _lock:
            _active_request_ids.discard(req_id)


def _process_request_impl(req_id: str) -> None:
    _t0 = time.monotonic()
    _t_ctx: float | None = None
    _t_model: float | None = None
    hcfg = hermes_config.load_config()
    if not hcfg.get("ollamaLaunch"):
        hermes_service.ensure_running()
    else:
        # ollama launch hermes already running — only verify Ollama, do not spawn hermes serve
        hermes_config.check_ollama()
    with _lock:
        req = _requests.get(req_id)
        if not req:
            return
        conv = _conversations.get(req["conversation_id"], {})
        session_id = conv.get("hermes_session_id") or ""
        message = req["message"]
        req["status"] = "processing"
        req["activity"] = "Iniciando…"
        req["activityLog"] = [{"step": "start", "message": "Iniciando…", "at": _now()}]

    _set_req_activity(req_id, "Analizando tu pregunta…", step="analyze")

    setup_result = hermes_shopify_setup.handle(message, conv)
    if setup_result is not None:
        with _lock:
            req = _requests.get(req_id)
            if not req:
                return
            if setup_result.get("status") == "completed":
                req["status"] = "completed"
                req["result"] = _fix_mojibake(setup_result.get("summary", ""))
                req["processed_at"] = _now()
                req["activity"] = "Configuración Shopify."
                req["activityLog"] = list(req.get("activityLog") or []) + [
                    {"step": "shopify_setup", "message": "Configuración Shopify.", "at": _now()}
                ]
                if setup_result.get("shopifySetup"):
                    req["shopifySetup"] = setup_result["shopifySetup"]
                conv["updated_at"] = _now()
                _mark_chat_proven()
            else:
                req["status"] = "error"
                req["error"] = setup_result.get("summary") or "Error en configuración Shopify"
                req["processed_at"] = _now()
            _persist()
        return

    if hermes_activity.wants_organize(message):
        _set_req_activity(req_id, "Detectada tarea de organización — preparando fuentes de datos…", step="organize_detect")
        try:
            hermes_activity.run_organize_pipeline()
        except Exception as exc:
            _set_req_activity(req_id, f"Organización parcial: {exc}", step="organize_warn")

    model = str(hcfg.get("model") or "")
    if ":cloud" in model:
        _set_req_activity(req_id, f"Consultando modelo cloud ({model})… puede tardar 1–3 min", step="chat_cloud")
    else:
        _set_req_activity(req_id, "Consultando modelo local…", step="chat_local")
    _set_req_activity(req_id, "Hermes está generando la respuesta…", step="chat")

    # FASE 15: solo se construye el contexto pesado cuando hace falta (detalle
    # operativo o pregunta de negocio). En conversación casual se omite: el CLI
    # runner usa la ruta ligera y no hay nada que exponer en la UI.
    _t_ctx = time.monotonic()
    op_ctx = None
    if _message_wants_operational_detail(message) and not _is_casual_message(message):
        op_ctx = build_operational_context(include_shopify=_message_wants_shopify_context(message))
    _t_ctx = time.monotonic() - _t_ctx

    def _progress(payload: dict[str, Any]) -> None:
        with _lock:
            req = _requests.get(req_id)
            if not req:
                return
            req["progress"] = payload
            req["events"] = list(payload.get("events") or [])
            req["commands"] = list(payload.get("commands") or [])
            req["heartbeat_at"] = _now()
            if payload.get("statusText"):
                req["activity"] = payload["statusText"]

    _set_req_activity(req_id, "Esperando turno de Hermes…", step="chat_queue")
    _t_model = time.monotonic()
    result = _run_chat_with_slot(message, session_id, progress_cb=_progress)
    _t_model = time.monotonic() - _t_model

    with _lock:
        req = _requests.get(req_id)
        if not req:
            return
        if _message_wants_operational_detail(message):
            req["operationalContext"] = op_ctx
            req["operationalSummary"] = op_ctx.get("summary")
        progress_snapshot = req.get("progress") or {}
        req["events"] = list(result.get("events") or progress_snapshot.get("events") or [])
        req["commands"] = list(result.get("commands") or progress_snapshot.get("commands") or [])
        req.pop("progress", None)
        if result.get("status") == "completed":
            req["status"] = "completed"
            req["result"] = _fix_mojibake(result.get("summary", ""))
            req["steps"] = list(result.get("steps") or [])
            req["processed_at"] = _now()
            # P14: latencia real por fase (VANOVA vs modelo) — lo que mide el
            # motor de detección y el contexto es separado de la generación LLM.
            req["timings"] = {
                "contextMs": round((_t_ctx or 0.0) * 1000, 1),
                "modelMs": round((_t_model or 0.0) * 1000, 1),
                "totalMs": round((time.monotonic() - _t0) * 1000, 1),
                "note": "contextMs = VANOVA (contexto+tools); modelMs = tiempo de generación del modelo (externo)",
            }
            req["activity"] = "Respuesta generada."
            req["activityLog"] = list(req.get("activityLog") or []) + [
                {"step": "done", "message": "Respuesta generada.", "at": _now()}
            ]
            hermes_activity.log_step("Respuesta generada.", step="done", source="chat")
            _mark_chat_proven()
            conv = _conversations.get(req["conversation_id"])
            if conv and result.get("session_id"):
                conv["hermes_session_id"] = result["session_id"]
                conv["updated_at"] = _now()
        else:
            req["status"] = "error"
            req["error"] = result.get("summary") or "Error desconocido"
            req["processed_at"] = _now()
        _persist()
