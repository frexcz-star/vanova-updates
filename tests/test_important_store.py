"""Tests for the Important Store and integration provider manifest."""
from __future__ import annotations

from desktop.runtime import important_store
from desktop.runtime.integration_providers import get_providers, to_hermes_prompt
from desktop.runtime.integration_providers import test_connection as check_connection


def test_mark_and_unmark_important():
    r = important_store.mark_important("task", "T-ABC", title="Vender más", body="El margen sube")
    assert r["ok"] is True
    item = r["item"]
    assert item["kind"] == "task"
    assert item["refId"] == "T-ABC"
    assert important_store.is_important("task", "T-ABC") is True
    # Duplicate mark refreshes, does not duplicate
    r2 = important_store.mark_important("task", "T-ABC", title="Vender más (actualizado)")
    assert r2["updated"] is True
    items = important_store.list_important()
    assert len([i for i in items if i["refId"] == "T-ABC"]) == 1
    u = important_store.unmark("task", "T-ABC")
    assert u["ok"] is True
    assert important_store.is_important("task", "T-ABC") is False


def test_mark_requires_ref():
    r = important_store.mark_important("task", "", title="Sin id")
    assert r["ok"] is False
    assert r["error"]


def test_unmark_missing():
    r = important_store.unmark("insight", "NO-EXISTE")
    assert r["ok"] is False


def test_unmark_uses_atomic_update():
    """BUG-027: unmark debe usar config_store.update() (RMW atómico), no
    load→save que pierde escrituras concurrentes del API server."""
    from unittest.mock import patch
    from desktop.runtime import config_store

    state = {"importantItems": [{"id": "1", "kind": "task", "refId": "X", "createdAt": "2026-08-21T00:00:00Z"}]}
    calls = []

    def fake_update(mutator):
        calls.append("update")
        cfg = dict(state)
        out = mutator(cfg)
        state.clear()
        state.update(out)

    with patch.object(config_store, "update", side_effect=fake_update), \
         patch.object(config_store, "load", side_effect=lambda: dict(state)):
        r = important_store.unmark("task", "X")
    assert r["ok"] is True
    assert calls == ["update"]
    assert important_store.list_important() == []


def test_get_providers_returns_three():
    ids = [p["id"] for p in get_providers()]
    assert "gmail" in ids
    assert "drive" in ids
    assert "facturascript" in ids


def test_test_connection_unknown():
    r = check_connection("nope", {})
    assert r["ok"] is False
    assert "desconocida" in r["error"]


def test_test_connection_gmail_missing_creds():
    r = check_connection("gmail", {})
    assert r["ok"] is False
    assert "correo" in r["error"].lower() or "contraseña" in r["error"].lower()


def test_hermes_prompt_mentions_provider():
    p = to_hermes_prompt("facturascript", {}, mode="web")
    assert "FacturaScript" in p
    assert "Hermes" in p or "ayúdale" in p.lower()
