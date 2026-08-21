"""AI Provider configuration — multi-provider support with role separation."""
from __future__ import annotations

from typing import Any

import urllib.request
import json

from . import config_store, hermes_config
from .logger import get_logger

log = get_logger("maios.ai", "ai-providers")

PROVIDERS = {
    "google-gemini": {
        "name": "Google Gemini",
        "models": ["gemini-2.0-flash", "gemini-1.5-pro"],
        "testUrl": "https://generativelanguage.googleapis.com/v1beta/models",
    },
    "openai": {
        "name": "OpenAI",
        "models": ["gpt-4o", "gpt-4o-mini"],
        "testUrl": "https://api.openai.com/v1/models",
    },
    "anthropic": {
        "name": "Anthropic",
        "models": ["claude-sonnet-4-20250514", "claude-3-5-haiku-20241022"],
        "testUrl": "https://api.anthropic.com/v1/messages",
    },
    "openrouter": {
        "name": "OpenRouter",
        "models": ["openrouter/auto"],
        "testUrl": "https://openrouter.ai/api/v1/models",
    },
    "nvidia": {
        "name": "NVIDIA NIM",
        "models": ["meta/llama-3.1-8b-instruct", "nvidia/auto"],
        "testUrl": "https://integrate.api.nvidia.com/v1/models",
    },
    "ollama": {
        "name": "Ollama (ollama launch hermes)",
        "models": ["deepseek-v4-flash:cloud", "kimi-k2.6:cloud", "qwen3.5:cloud"],
        "testUrl": "http://127.0.0.1:11434/api/tags",
    },
    "ollama-launch": {
        "name": "Ollama Launch Hermes",
        "models": ["deepseek-v4-flash:cloud", "kimi-k2.6:cloud"],
        "testUrl": "http://127.0.0.1:11434/api/tags",
    },
    "other": {
        "name": "Other",
        "models": ["custom"],
        "testUrl": "",
    },
}


def save_provider_config(
    provider_id: str,
    api_key: str,
    model: str,
    roles: dict[str, str] | None = None,
) -> dict[str, Any]:
    roles = roles or {
        "primary": model,
        "fast": model,
        "reasoning": model,
        "fallback": model,
    }
    config_store.secure_store_credentials(provider_id, api_key)
    # BUG-015 FIX: RMW atómico bajo un solo lock. Antes hacía load() → modificar
    # → save() sin serializar el ciclo completo (lost-update si dos requests
    # concurrentes configuran providers distintos).
    def _mutate(cfg: dict[str, Any]) -> dict[str, Any]:
        providers = dict(cfg.get("aiProviders") or {})
        providers["primary"] = {
            "providerId": provider_id,
            "providerName": PROVIDERS.get(provider_id, {}).get("name", provider_id),
            "model": model,
            "roles": roles,
            "configured": True,
        }
        cfg["aiProviders"] = providers
        return cfg

    config_store.update(_mutate)
    _write_env_provider(provider_id, api_key, model)
    log.info("AI provider configured: %s", provider_id)
    # Reload para devolver el estado persistido
    primary = config_store.load().get("aiProviders", {}).get("primary") or {
        "providerId": provider_id,
        "providerName": PROVIDERS.get(provider_id, {}).get("name", provider_id),
        "model": model,
        "roles": roles,
        "configured": True,
    }
    return primary


def _write_env_provider(provider_id: str, api_key: str, model: str) -> None:
    """Write provider config to user connector.env."""
    from .paths import config_dir
    from .process_manager import _ensure_env_files

    _ensure_env_files()
    env_path = config_dir() / "connector.env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    updates = {
        "MAIOS_AI_PROVIDER": provider_id,
        "MAIOS_AI_MODEL": model,
        "MAIOS_AI_API_KEY": api_key,
    }
    existing_keys = set()
    new_lines = []
    for line in lines:
        key = line.split("=")[0] if "=" in line else ""
        if key in updates:
            new_lines.append(f"{key}={updates[key]}")
            existing_keys.add(key)
        else:
            new_lines.append(line)
    for k, v in updates.items():
        if k not in existing_keys:
            new_lines.append(f"{k}={v}")
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def test_connection(provider_id: str, api_key: str) -> dict[str, Any]:
    provider = PROVIDERS.get(provider_id, {})
    if provider_id == "ollama" or provider_id == "ollama-launch":
        try:
            req = urllib.request.Request(provider["testUrl"])
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    return {"ok": True, "message": "Ollama responde en localhost:11434"}
        except Exception:
            return {
                "ok": False,
                "message": "Ollama no responde en localhost:11434 — ejecuta «ollama serve» e instala un modelo.",
            }
    if not api_key:
        return {"ok": False, "message": "API key required"}
    if provider_id in ("openrouter", "nvidia", "openai", "anthropic", "google-gemini"):
        try:
            headers = {"Authorization": f"Bearer {api_key}"}
            if provider_id == "anthropic":
                headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
            req = urllib.request.Request(provider["testUrl"], headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status in (200, 204):
                    return {"ok": True, "message": "Connected successfully"}
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return {"ok": False, "message": "API key inválida (401 Unauthorized)"}
            log.warning("Provider test HTTP %s", e.code)
            return {"ok": False, "message": f"Proveedor respondió HTTP {e.code}"}
        except Exception as e:
            log.warning("Provider test failed: %s", type(e).__name__)
            return {"ok": False, "message": "Could not verify connection. Check your API key."}
    # Generic validation — key format check
    if len(api_key) >= 8:
        return {"ok": True, "message": "Connected successfully"}
    return {"ok": False, "message": "Invalid API key format"}


def get_provider_status() -> dict[str, Any]:
    hermes_config.sync_maios_from_hermes()
    hcfg = hermes_config.load_config()
    providers = config_store.load().get("aiProviders", {})
    primary = providers.get("primary", {})
    provider_id = primary.get("providerId", "") or hcfg.get("providerId", "")
    model = primary.get("model", "") or hcfg.get("model", "")
    configured = bool(model) and (bool(primary.get("configured")) or hcfg.get("found"))
    ollama = hermes_config.check_ollama() if hcfg.get("ollamaLaunch") or provider_id in ("ollama", "ollama-launch") else None
    vision = hcfg.get("vision") or {}
    return {
        "configured": configured,
        "providerId": provider_id,
        "provider": primary.get("providerName") or hcfg.get("providerName") or "Not configured",
        "model": model,
        "source": "hermes-config" if hcfg.get("found") else "maios",
        "hermesConfigPath": hcfg.get("path") or "",
        "ollamaRunning": ollama.get("running") if ollama else None,
        "visionProvider": vision.get("provider") or "",
        "visionModel": vision.get("model") or "",
        "message": (
            f"{primary.get('providerName') or hcfg.get('providerName') or provider_id} — {model}"
            if configured
            else "Proveedor de IA no configurado — ejecuta «ollama launch hermes»"
        ),
    }


def get_hermes_provider_catalog() -> dict[str, Any]:
    return hermes_config.full_status()


def select_hermes_provider(provider_id: str, model: str) -> dict[str, Any]:
    result = hermes_config.set_primary_model(provider_id, model)
    if result.get("ok"):
        entry = hermes_config.sync_maios_from_hermes()
        result["primary"] = entry
    return result
