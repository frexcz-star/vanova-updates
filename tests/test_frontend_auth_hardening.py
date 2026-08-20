"""Regression tests for the dashboard authentication boundary."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB_VARIANTS = (
    ROOT / "web" / "index.html",
    ROOT / "web" / "dashboard.html",
    ROOT / "web" / "dist" / "index.html",
    ROOT / "web" / "dist" / "dashboard.html",
)


def test_dashboard_has_no_client_side_demo_login_bypass():
    for page in WEB_VARIANTS:
        text = page.read_text(encoding="utf-8")
        assert "p==='mooving2026'" not in text, page
        assert "Prueba: mooving2026" not in text, page


def test_dashboard_requires_auth_service_when_login_is_unavailable():
    for page in WEB_VARIANTS:
        text = page.read_text(encoding="utf-8")
        # The login form must never bypass authentication client-side. The
        # manual login either resolves against the local runtime (which
        # validates real cloud.env owner credentials) or the Cloud; when both
        # are unreachable the user sees an explicit service-unavailable error.
        assert "Credenciales incorrectas" in text, page
        assert "No se pudo conectar con el servicio" in text, page
