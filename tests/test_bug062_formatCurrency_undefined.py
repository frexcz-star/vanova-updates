"""BUG-062: formatCurrency no definido en dashboard.html

Boss encontro que formatCurrency() se llamaba en el hero "Valor Capturado"
pero no estaba definido en ningun lado del dashboard.html, causando
ReferenceError que podia romper updateBellBadge() y el contador de
notificaciones.

Fix: definir formatCurrency() en el scope global del dashboard.
"""
import re

def test_formatCurrency_definido_en_dashboard():
    """El dashboard.html debe definir formatCurrency antes de usarlo."""
    with open("web/dashboard.html", encoding="utf-8") as f:
        src = f.read()
    # Debe existir la definicion de formatCurrency
    assert "function formatCurrency(" in src, "formatCurrency no esta definido en dashboard.html"
    # El uso debe venir despues de la definicion (orden)
    def_idx = src.find("function formatCurrency(")
    use_idx = src.find("formatCurrency(store.valorCapturado)")
    assert def_idx > 0, "formatCurrency no encontrado"
    assert use_idx > 0, "uso de formatCurrency no encontrado"
    assert def_idx < use_idx, "formatCurrency se usa antes de definirse"

def test_formatCurrency_maneja_null():
    """formatCurrency debe devolver '--' para null/undefined/NaN."""
    with open("web/dashboard.html", encoding="utf-8") as f:
        src = f.read()
    block = src[src.find("function formatCurrency("):src.find("function formatCurrency(") + 200]
    assert "n == null" in block or "isNaN" in block, "formatCurrency no maneja null/invalidos"
    assert "'--'" in block, "formatCurrency no retorna '--' para valores invalidos"

def test_hero_valor_capturado_estructura_presente():
    """El hero Valor Capturado debe existir en el HTML."""
    with open("web/dashboard.html", encoding="utf-8") as f:
        src = f.read()
    assert "hero-valor-capturado" in src, "hero Valor Capturado no existe"
    assert "valor-capturado-num" in src, "elemento valor-capturado-num no existe"
    assert "updateHeroValorCapturado" in src, "funcion updateHeroValorCapturado no existe"
