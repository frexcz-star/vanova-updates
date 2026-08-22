"""Guided Shopify setup via Hermes chat — step-by-step prompts, no Integrations UI required."""
from __future__ import annotations

import re
from typing import Any

from . import hermes_config, integrations_store, shopify_sync
from .logger import get_logger

log = get_logger("maios.hermes_shopify_setup", "hermes-shopify-setup")

REQUIRED_SCOPES = ("read_products", "read_orders")

_SETUP_INTENT = re.compile(
    r"(?:"
    r"configur[aáe]\s+(?:la\s+)?(?:integraci[oó]n\s+(?:de\s+)?)?shopify"
    r"|conect[aáe]\s+(?:mi\s+)?tienda"
    r"|conect[aáe]\r?\n?\s*shopify"
    r"|reconfigur[aáe]\s+shopify"
    r"|setup\s+shopify"
    r"|configura\s+shopify"
    r")",
    re.IGNORECASE,
)

_HERMES_YES = re.compile(
    r"^(?:s[ií]|yes|ok|vale|usar\s+(?:las\s+)?credenciales|usar\s+hermes)\b",
    re.IGNORECASE,
)
_HERMES_NO = re.compile(
    r"^(?:no|manual|configurar\s+manualmente)\b",
    re.IGNORECASE,
)
_CANCEL = re.compile(r"^(?:cancelar|abortar|salir|stop)\b", re.IGNORECASE)

_SHOP_URL = re.compile(
    r"(?:https?://)?([a-z0-9][a-z0-9\-]*\.myshopify\.com)",
    re.IGNORECASE,
)
_TOKEN = re.compile(r"\b(shpat_[a-zA-Z0-9]{10,}|shpua_[a-zA-Z0-9]{10,}|shpss_[a-zA-Z0-9]{10,})\b")


def redact_sensitive(text: str) -> str:
    """Remove tokens from chat history / logs."""
    if not text:
        return text
    out = _TOKEN.sub("[token redactado]", text)
    return out


def wants_shopify_setup(message: str) -> bool:
    m = (message or "").strip()
    if not m:
        return False
    if _SETUP_INTENT.search(m):
        return True
    lower = m.lower()
    return lower in {
        "configura shopify",
        "conecta mi tienda",
        "conectar shopify",
        "reconfigurar shopify",
        "configurar shopify",
    }


def is_active(conversation: dict[str, Any] | None) -> bool:
    setup = (conversation or {}).get("shopify_setup") or {}
    return bool(setup.get("active"))


def _setup_state(conversation: dict[str, Any]) -> dict[str, Any]:
    setup = conversation.setdefault("shopify_setup", {})
    return setup


def _reply(
    text: str,
    *,
    step: str,
    quick_replies: list[dict[str, str]] | None = None,
    notification: dict[str, str] | None = None,
    active: bool = True,
    reload_integrations: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "completed",
        "summary": text,
        "shopifySetup": {
            "active": active,
            "step": step,
            "quickReplies": quick_replies or [],
        },
    }
    if notification:
        payload["shopifySetup"]["notification"] = notification
    if reload_integrations:
        payload["shopifySetup"]["reloadIntegrations"] = True
    return payload


def _notify(title: str, message: str, *, level: str = "info") -> dict[str, str]:
    return {"title": title, "message": message, "level": level}


def _hermes_credentials_available() -> dict[str, str]:
    hermes = hermes_config.load_hermes_shopify_credentials()
    if hermes.get("url") and hermes.get("token"):
        return hermes
    return {}


def _format_shop_display(url: str) -> str:
    u = (url or "").rstrip("/")
    if u.lower().startswith("https://"):
        return u[8:]
    if u.lower().startswith("http://"):
        return u[7:]
    return u


def _parse_shop_url(text: str) -> str | None:
    m = _SHOP_URL.search(text or "")
    if not m:
        return None
    return "https://" + m.group(1).lower()


def _parse_token(text: str) -> str | None:
    m = _TOKEN.search(text or "")
    return m.group(1) if m else None


def _finish_with_save(url: str, token: str, *, source_note: str = "", client_id: str = "") -> dict[str, Any]:
    body = {"url": url, "token": token}
    if client_id:
        body["api_key"] = client_id  # Dev Dashboard Client ID, para canjear shpss_
    save = integrations_store.save_config("shopify", body)
    if not save.get("ok"):
        return _reply(
            f"No pude guardar la configuración: {save.get('error', 'error desconocido')}. "
            "Comprueba la URL y el token e inténtalo de nuevo.",
            step="ask_token",
            notification=_notify(
                "Shopify",
                save.get("error") or "Error al guardar credenciales",
                level="error",
            ),
            active=True,
            quick_replies=[
                {"label": "Cancelar", "message": "cancelar"},
            ],
        )

    shop_label = _format_shop_display(url)
    missing = list(save.get("missingScopes") or [])
    prefix = f"Shopify conectado ({shop_label})"
    if source_note:
        prefix += f" — {source_note}"

    if missing:
        scope_list = ", ".join(missing)
        text = (
            f"{prefix}, pero faltan permisos: **{scope_list}**.\n\n"
            "En Shopify Admin → Configuración → Apps → tu app → Configuration, "
            "activa esos scopes, genera un token nuevo y dime «Reconfigurar Shopify» "
            "o pega el token aquí."
        )
        return _reply(
            text,
            step="done",
            active=False,
            reload_integrations=True,
            notification=_notify(
                "Shopify conectado — permisos pendientes",
                f"Faltan: {scope_list}. Aprueba los scopes en Shopify Admin.",
                level="warn",
            ),
            quick_replies=[
                {"label": "Reconfigurar token", "message": "Reconfigurar Shopify"},
            ],
        )

    text = (
        f"¡Listo! {prefix}. Permisos OK (read_products, read_orders). "
        "Estoy sincronizando productos y pedidos en segundo plano."
    )
    return _reply(
        text,
        step="done",
        active=False,
        reload_integrations=True,
        notification=_notify("Shopify conectado", f"Tienda {shop_label} — sincronizando datos."),
        quick_replies=[
            {"label": "Ver productos", "message": "¿Qué productos tengo disponibles ahora?"},
        ],
    )


def _start_flow(conversation: dict[str, Any]) -> dict[str, Any]:
    setup = _setup_state(conversation)
    setup.clear()
    setup["active"] = True

    hermes = _hermes_credentials_available()
    if hermes:
        check = shopify_sync.check_credentials(hermes["url"], hermes["token"])
        shop_label = _format_shop_display(hermes["url"])
        setup["step"] = "offer_hermes"
        setup["hermes_url"] = hermes["url"]
        setup["hermes_token"] = hermes["token"]
        setup["hermes_ok"] = bool(check.get("ok"))
        setup["hermes_missing"] = list(check.get("missingScopes") or [])

        if check.get("ok"):
            msg = (
                f"Encontré credenciales de Shopify en Hermes para **{shop_label}** "
                "con permisos completos (read_products, read_orders).\n\n"
                "¿Quieres usarlas en VANOVA?"
            )
        else:
            missing = ", ".join(setup["hermes_missing"]) or "read_products, read_orders"
            msg = (
                f"Encontré credenciales de Shopify en Hermes para **{shop_label}**, "
                f"pero faltan permisos ({missing}).\n\n"
                "¿Quieres importarlas igualmente o configurar manualmente?"
            )
        return _reply(
            msg,
            step="offer_hermes",
            notification=_notify(
                "Configurar Shopify",
                f"Credenciales de Hermes detectadas ({shop_label})",
            ),
            quick_replies=[
                {"label": "Sí, usar Hermes", "message": "Sí, usar credenciales de Hermes"},
                {"label": "No, manual", "message": "No, configurar manualmente"},
                {"label": "Cancelar", "message": "cancelar"},
            ],
        )

    setup["step"] = "ask_url"
    return _ask_url()


def _ask_url() -> dict[str, Any]:
    return _reply(
        "Vamos a conectar tu tienda Shopify.\n\n"
        "**Paso 1/2:** Indica la URL de tu tienda "
        "(ejemplo: `tu-tienda.myshopify.com`).",
        step="ask_url",
        notification=_notify(
            "Configurar Shopify",
            "Paso 1: indica la URL de tu tienda (.myshopify.com)",
        ),
        quick_replies=[
            {"label": "Cancelar", "message": "cancelar"},
        ],
    )


def _ask_token(url: str) -> dict[str, Any]:
    shop = _format_shop_display(url)
    return _reply(
        f"Tienda: **{shop}**\n\n"
        "**Paso 2/2:** Pega el token de acceso de tu app Shopify.\n\n"
        "Puede ser el **Admin API access token** (`shpat_…`, de una Custom App del admin) "
        "o el **Client Secret del Dev Dashboard** (`shpss_…`).\n"
        "→ Si pegas uno que empiece por `shpss_`, dime también el **Client ID** de tu app "
        "(Dev Dashboard → tu app → Settings), porque con él VANOVA lo canjea por un "
        "access token real.\n\n"
        "Permisos necesarios: read_products, read_orders.",
        step="ask_token",
        notification=_notify(
            "Configurar Shopify",
            f"Paso 2: pega el token (o Client Secret) para {shop}",
        ),
        quick_replies=[
            {"label": "Cancelar", "message": "cancelar"},
        ],
    )


def _cancel_flow(conversation: dict[str, Any]) -> dict[str, Any]:
    setup = _setup_state(conversation)
    setup.clear()
    return _reply(
        "Configuración de Shopify cancelada. Puedes retomarla cuando quieras "
        "diciendo «Configura Shopify».",
        step="idle",
        active=False,
    )


def handle(message: str, conversation: dict[str, Any]) -> dict[str, Any] | None:
    """
    Process Shopify setup conversation.
    Returns a result dict when handled locally, or None to fall through to Hermes CLI.
    """
    msg = (message or "").strip()
    if not msg:
        return None

    if _CANCEL.match(msg) and is_active(conversation):
        return _cancel_flow(conversation)

    if is_active(conversation):
        return _continue_setup(msg, conversation)

    if wants_shopify_setup(msg):
        return _start_flow(conversation)

    return None


def _continue_setup(message: str, conversation: dict[str, Any]) -> dict[str, Any]:
    setup = _setup_state(conversation)
    step = setup.get("step") or "ask_url"

    if step == "offer_hermes":
        if _HERMES_YES.match(message):
            url = setup.get("hermes_url") or ""
            token = setup.get("hermes_token") or ""
            setup.clear()
            return _finish_with_save(url, token, source_note="importado desde Hermes")
        if _HERMES_NO.match(message):
            setup["step"] = "ask_url"
            setup.pop("hermes_url", None)
            setup.pop("hermes_token", None)
            return _ask_url()
        return _reply(
            "Responde **Sí** para usar las credenciales de Hermes o **No** para configurar manualmente.",
            step="offer_hermes",
            quick_replies=[
                {"label": "Sí, usar Hermes", "message": "Sí, usar credenciales de Hermes"},
                {"label": "No, manual", "message": "No, configurar manualmente"},
            ],
        )

    if step == "ask_url":
        url = _parse_shop_url(message)
        if not url:
            return _reply(
                "No reconocí una URL de Shopify válida. "
                "Ejemplo: `blisartpaper.myshopify.com`",
                step="ask_url",
                notification=_notify(
                    "URL no válida",
                    "Usa el formato tu-tienda.myshopify.com",
                    level="warn",
                ),
            )
        setup["url"] = url
        setup["step"] = "ask_token"
        return _ask_token(url)

    if step == "ask_token":
        token = _parse_token(message)
        if not token:
            return _reply(
                "No encontré un token válido. Debe empezar por `shpat_` "
                "(Admin API access token) o `shpss_` (Client Secret del Dev Dashboard).",
                step="ask_token",
                notification=_notify(
                    "Token no válido",
                    "Pega el Admin API token (shpat_…) o el Client Secret (shpss_…)",
                    level="warn",
                ),
            )
        url = setup.get("url") or ""
        # Si es un Client Secret del Dev Dashboard, pedimos el Client ID para
        # poder canjearlo por un access token real.
        if token.lower().startswith("shpss_"):
            setup["token"] = token
            setup["step"] = "ask_client_id"
            return _reply(
                "Perfecto, ese es el **Client Secret** del Dev Dashboard (`shpss_…`).\n\n"
                "Para que VANOVA lo canjee por un access token real, dime el **Client ID** "
                "de tu app Shopify (Dev Dashboard → tu app → Settings → Credentials).\n\n"
                "Es una cadena de letras/números (no empieza por `shpss_`).",
                step="ask_client_id",
                notification=_notify(
                    "Configurar Shopify",
                    "Pega el Client ID de tu app del Dev Dashboard",
                ),
            )
        setup.clear()
        return _finish_with_save(url, token)

    if step == "ask_client_id":
        token = str(setup.get("token") or "").strip()
        client_id = str(message or "").strip()
        if not client_id:
            return _reply(
                "Pega el **Client ID** de tu app (Dev Dashboard → tu app → Settings). "
                "Es la cadena que identifica tu app, distinta del Client Secret.",
                step="ask_client_id",
            )
        url = setup.get("url") or ""
        setup.clear()
        return _finish_with_save(url, token, client_id=client_id)

    setup.clear()
    return _start_flow(conversation)
