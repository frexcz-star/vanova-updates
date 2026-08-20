"""Read/write Hermes Agent config.yaml (Ollama launch, NVIDIA, etc.)."""
from __future__ import annotations

import json
import os
import re
import socket
import time
import urllib.request
from pathlib import Path
from typing import Any

from . import config_store
from .logger import get_logger

log = get_logger("maios.hermes_config", "hermes-config")

OLLAMA_URL = "http://127.0.0.1:11434"
HERMES_API_DEFAULT = "http://127.0.0.1:8642"

# Windows: %LOCALAPPDATA%\\hermes\\config.yaml — Linux/macOS: ~/.hermes/config.yaml
def config_path() -> Path | None:
    candidates = [
        Path(os.getenv("LOCALAPPDATA", "")) / "hermes" / "config.yaml",
        Path.home() / ".hermes" / "config.yaml",
        Path.home() / "AppData" / "Local" / "hermes" / "config.yaml",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def hermes_env_path() -> Path | None:
    """Hermes CLI secrets — includes SHOPIFY_ACCESS_TOKEN when Shopify is configured."""
    candidates = [
        Path(os.getenv("LOCALAPPDATA", "")) / "hermes" / ".env",
        Path.home() / ".hermes" / ".env",
        Path.home() / "AppData" / "Local" / "hermes" / ".env",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def load_hermes_shopify_credentials() -> dict[str, str]:
    """Read Shopify URL/token from Hermes .env (runtime only — never log values)."""
    path = hermes_env_path()
    if not path:
        return {}
    url = ""
    token = ""
    try:
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("'\"")
            if key == "SHOPIFY_ACCESS_TOKEN":
                token = val
            elif key == "SHOPIFY_STORE_DOMAIN":
                domain = val.rstrip("/")
                if domain and not domain.lower().startswith(("http://", "https://")):
                    url = "https://" + domain.lstrip("/")
                else:
                    url = domain
    except OSError as exc:
        log.warning("Could not read Hermes .env: %s", exc)
        return {}
    return {"url": url.rstrip("/"), "token": token}


def _read_text() -> str:
    path = config_path()
    if not path:
        return ""
    try:
        return path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        log.warning("Could not read Hermes config: %s", exc)
        return ""


def _yaml_scalar(block: str, key: str) -> str:
    m = re.search(rf"^\s*{re.escape(key)}:\s*(.+)$", block, re.MULTILINE)
    if not m:
        return ""
    val = m.group(1).strip().strip("'\"")
    return val


def _yaml_section(text: str, name: str) -> str:
    """Extract a YAML section body; tolerates 2- or 4-space child indent (Hermes uses 4)."""
    m = re.search(rf"^{re.escape(name)}:\s*\n", text, re.MULTILINE)
    if not m:
        return ""
    rest = text[m.end() :]
    lines: list[str] = []
    child_indent: int | None = None
    for line in rest.splitlines(True):
        if not line.strip():
            lines.append(line)
            continue
        indent = len(line) - len(line.lstrip(" "))
        if child_indent is None:
            if indent == 0:
                break
            child_indent = indent
            lines.append(line)
            continue
        if indent >= child_indent:
            lines.append(line)
        else:
            break
    return "".join(lines)


def _yaml_list_items(block: str, key: str) -> list[str]:
    items: list[str] = []
    in_list = False
    list_indent: int | None = None
    for line in block.splitlines():
        km = re.match(rf"^(\s*){re.escape(key)}:\s*$", line)
        if km:
            in_list = True
            list_indent = len(km.group(1))
            continue
        if in_list:
            lm = re.match(r"^(\s*)- (.+)$", line)
            if lm and (list_indent is None or len(lm.group(1)) > list_indent):
                items.append(lm.group(2).strip().strip("'\""))
                continue
            if line.strip() and (list_indent is None or len(line) - len(line.lstrip(" ")) <= list_indent):
                break
    return items


def _provider_blocks(text: str) -> dict[str, str]:
    providers_sec = _yaml_section(text, "providers")
    out: dict[str, str] = {}
    if not providers_sec:
        return out
    current = ""
    buf: list[str] = []
    prov_indent: int | None = None
    for line in providers_sec.splitlines():
        m = re.match(r"^(\s*)([\w-]+):\s*$", line)
        if m and (prov_indent is None or len(m.group(1)) == prov_indent):
            if current:
                out[current] = "\n".join(buf)
            current = m.group(2)
            prov_indent = len(m.group(1))
            buf = []
        elif current:
            buf.append(line)
    if current:
        out[current] = "\n".join(buf)
    return out


def load_config() -> dict[str, Any]:
    text = _read_text()
    if not text:
        return {"found": False, "path": ""}

    model_block = _yaml_section(text, "model")
    aux_block = _yaml_section(text, "auxiliary")
    api_block = _yaml_section(text, "platforms")
    provider_map = _provider_blocks(text)

    provider_id = _yaml_scalar(model_block, "provider") or "unknown"
    model = _yaml_scalar(model_block, "default") or ""
    base_url = _yaml_scalar(model_block, "base_url") or ""

    providers: list[dict[str, Any]] = []
    for pid, block in provider_map.items():
        pname = _yaml_scalar(block, "name") or pid
        pmodel = _yaml_scalar(block, "default_model") or ""
        models = _yaml_list_items(block, "models") or ([pmodel] if pmodel else [])
        api = _yaml_scalar(block, "api") or ""
        providers.append({
            "id": pid,
            "name": pname,
            "model": pmodel,
            "models": models,
            "api": api,
            "active": pid == provider_id,
        })

    vision_provider = ""
    vision_model = ""
    if aux_block:
        vis = _yaml_section(aux_block, "vision")
        if vis:
            vision_provider = _yaml_scalar(vis, "provider")
            vision_model = _yaml_scalar(vis, "model")

    api_port = 8642
    api_enabled = False
    if api_block:
        srv = _yaml_section(api_block, "api_server")
        if srv:
            api_enabled = _yaml_scalar(srv, "enabled").lower() == "true"
            try:
                api_port = int(_yaml_scalar(srv, "port") or "8642")
            except ValueError:
                api_port = 8642

    path = config_path()
    return {
        "found": True,
        "path": str(path) if path else "",
        "providerId": provider_id,
        "providerName": next((p["name"] for p in providers if p["id"] == provider_id), provider_id),
        "model": model,
        "baseUrl": base_url,
        "providers": providers,
        "ollamaLaunch": provider_id in ("ollama-launch", "ollama"),
        "vision": {"provider": vision_provider, "model": vision_model} if vision_provider else None,
        "apiServer": {"enabled": api_enabled, "port": api_port},
    }


def active_model() -> tuple[str, str]:
    """Return (provider_id, model) from Hermes config — source of truth for chat."""
    cfg = load_config()
    if not cfg.get("found"):
        return "", ""
    return str(cfg.get("providerId") or ""), str(cfg.get("model") or "")


def should_use_hermes_model_flag() -> bool:
    """When False, hermes chat uses model from config.yaml (ollama launch workflow)."""
    pid, _ = active_model()
    if pid in ("ollama-launch", "ollama"):
        return False
    return bool(active_model()[1])


def _normalize_cloud_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        return ""
    if not name.endswith(":cloud") and ":" not in name.rsplit("/", 1)[-1]:
        return f"{name}:cloud"
    return name


def ollama_available_models() -> list[str]:
    """Union of local Ollama tags and Hermes cloud model cache."""
    local = check_ollama().get("models") or []
    merged: list[str] = []
    for name in local:
        val = str(name or "").strip()
        if val and val not in merged:
            merged.append(val)
    for name in ollama_cloud_models():
        val = str(name or "").strip()
        if val and val not in merged:
            merged.append(val)
    return merged


def ollama_cloud_models() -> list[str]:
    path = config_path()
    if not path:
        return []
    cache = path.parent / "ollama_cloud_models_cache.json"
    models: list[str] = []
    if cache.is_file():
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            for m in data.get("models") or []:
                name = _normalize_cloud_name(str(m))
                if name and name not in models:
                    models.append(name)
        except (json.JSONDecodeError, OSError):
            pass
    cfg = load_config()
    for p in cfg.get("providers") or []:
        if p.get("id") in ("ollama-launch", "ollama"):
            for m in p.get("models") or []:
                name = _normalize_cloud_name(str(m))
                if name and name not in models:
                    models.append(name)
    cur = _normalize_cloud_name(str(cfg.get("model") or ""))
    if cur and cur not in models:
        models.insert(0, cur)
    # Preferred defaults first, then cache remainder
    preferred = (
        "deepseek-v4-flash:cloud",
        "kimi-k2.6:cloud",
        "kimi-k2.5:cloud",
        "qwen3.5:cloud",
        "glm-5.1:cloud",
    )
    ordered: list[str] = []
    for m in preferred:
        if m in models and m not in ordered:
            ordered.append(m)
    for m in models:
        if m not in ordered:
            ordered.append(m)
    return ordered


def nvidia_models() -> list[str]:
    path = config_path()
    if not path:
        return []
    cache = path.parent / "provider_models_cache.json"
    if not cache.is_file():
        return []
    try:
        data = json.loads(cache.read_text(encoding="utf-8"))
        return list(data.get("nvidia", {}).get("models") or [])[:40]
    except (json.JSONDecodeError, OSError):
        return []


def check_ollama() -> dict[str, Any]:
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                names = [m.get("name", "") for m in data.get("models") or []]
                return {"running": True, "models": names[:20], "message": "Ollama activo en localhost:11434"}
    except Exception as exc:
        return {
            "running": False,
            "models": [],
            "message": f"Ollama no responde en localhost:11434 — ejecuta «ollama serve» o «ollama launch hermes». ({exc})",
        }


def _sync_connector_env(provider_id: str, model: str) -> None:
    """Keep connector.env aligned so subprocesses never inherit openrouter/auto."""
    from .paths import config_dir

    env_path = config_dir() / "connector.env"
    if not env_path.is_file():
        return
    updates = {
        "MAIOS_AI_PROVIDER": provider_id,
        "MAIOS_AI_MODEL": model,
    }
    lines = env_path.read_text(encoding="utf-8").splitlines()
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0] if "=" in line else ""
        if key in updates:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, val in updates.items():
        if key not in seen:
            out.append(f"{key}={val}")
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")


_sync_last_at = 0.0
_sync_last_key = ""
_SYNC_MIN_INTERVAL_SEC = 30.0


def sync_maios_from_hermes() -> dict[str, Any] | None:
    """Mirror Hermes config into maios.json aiProviders.primary."""
    global _sync_last_at, _sync_last_key
    cfg = load_config()
    if not cfg.get("found") or not cfg.get("model"):
        return None
    pid = cfg["providerId"]
    model = cfg["model"]
    sync_key = f"{pid}|{model}|{cfg.get('baseUrl') or ''}"
    now = time.monotonic()
    if sync_key == _sync_last_key and (now - _sync_last_at) < _SYNC_MIN_INTERVAL_SEC:
        existing = config_store.load().get("aiProviders", {}).get("primary")
        return existing if existing else None
    name_map = {
        "ollama-launch": "Ollama (ollama launch hermes)",
        "ollama": "Ollama",
        "nvidia": "NVIDIA NIM",
        "openrouter": "OpenRouter",
    }
    entry = {
        "providerId": pid,
        "providerName": name_map.get(pid, cfg.get("providerName") or pid),
        "model": model,
        "roles": {"primary": model, "fast": model, "reasoning": model, "fallback": model},
        "configured": True,
        "source": "hermes-config",
        "baseUrl": cfg.get("baseUrl") or "",
    }
    existing = config_store.load().get("aiProviders", {}).get("primary") or {}
    if (
        existing.get("providerId") == entry["providerId"]
        and existing.get("model") == entry["model"]
        and existing.get("baseUrl") == entry.get("baseUrl")
        and existing.get("source") == "hermes-config"
    ):
        _sync_last_at = now
        _sync_last_key = sync_key
        return existing
    config_store.save({"aiProviders": {"primary": entry}})
    _sync_connector_env(pid, model)
    _sync_last_at = now
    _sync_last_key = sync_key
    log.info("Synced VANOVA aiProviders from Hermes: %s / %s", pid, model)
    return entry


def set_primary_model(provider_id: str, model: str) -> dict[str, Any]:
    """Update Hermes config.yaml primary model (ollama-launch / nvidia)."""
    path = config_path()
    if not path:
        return {"ok": False, "error": "Hermes config.yaml no encontrado. Ejecuta «ollama launch hermes» primero."}

    text = path.read_text(encoding="utf-8-sig")
    model = (model or "").strip()
    provider_id = (provider_id or "").strip()
    if not model:
        return {"ok": False, "error": "Modelo requerido"}

    # Update model: section (2- or 4-space indent)
    text = re.sub(
        r"(^model:\s*\n(?:[ \t].+\n)*?[ \t]+default:\s*).+$",
        rf"\g<1>{model}",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if provider_id:
        if re.search(r"^[ \t]+provider:\s*", text, re.MULTILINE):
            text = re.sub(
                r"^[ \t]+provider:\s*.+$",
                lambda m: m.group(0).split(":")[0] + f": {provider_id}",
                text,
                count=1,
                flags=re.MULTILINE,
            )
        else:
            text = re.sub(r"(^model:\s*\n)", rf"\1    provider: {provider_id}\n", text, count=1, flags=re.MULTILINE)

    # Update providers.<id>.default_model
    prov_key = provider_id if provider_id in _provider_blocks(text) else "ollama-launch"
    prov_pattern = (
        rf"(^providers:\s*\n(?:[ \t].+\n)*?[ \t]+{re.escape(prov_key)}:\s*\n"
        rf"(?:[ \t].+\n)*?[ \t]+default_model:\s*).+$"
    )
    if re.search(prov_pattern, text, re.MULTILINE):
        text = re.sub(prov_pattern, rf"\g<1>{model}", text, count=1, flags=re.MULTILINE)

    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)

    sync_maios_from_hermes()
    log.info("Hermes primary model set: %s / %s", provider_id, model)
    return {"ok": True, "providerId": provider_id, "model": model}


def full_status() -> dict[str, Any]:
    cfg = load_config()
    ollama = check_ollama()
    sync_maios_from_hermes()
    maios_primary = config_store.load().get("aiProviders", {}).get("primary", {})
    return {
        "hermesConfig": cfg,
        "ollama": ollama,
        "ollamaCloudModels": ollama_cloud_models(),
        "ollamaAvailableModels": ollama_available_models(),
        "nvidiaModels": nvidia_models()[:20],
        "maiosPrimary": maios_primary,
        "chatUsesHermesConfig": not should_use_hermes_model_flag(),
        "instructions": {
            "setup": "Ejecuta «ollama launch hermes --model deepseek-v4-flash:cloud» en terminal.",
            "switchModel": "Selecciona modelo abajo o usa «hermes model» en terminal.",
        },
    }
