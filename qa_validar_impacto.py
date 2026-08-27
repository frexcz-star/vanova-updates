# QA: validar la logica del endpoint /api/recommendations/impact (cierre del loop).
# Usa datos mock / sin inventar EUR.
import sys
sys.path.insert(0, 'C:/Users/Admin/maios/desktop')
sys.path.insert(0, 'C:/Users/Admin/maios')
from runtime import recommendation_store
from runtime.api_server import _recommendations_impact

print("=== Prueba 1: sin recomendaciones measured+improved -> 0/no banner ===")
# Lista vacia de recomendaciones
recs = recommendation_store.list_recommendations()
print("recomendaciones actuales:", len(recs))
# Llamar directamente a la logica del endpoint con datos vacios via store patch
from unittest.mock import patch
with patch.object(recommendation_store, "list_recommendations", return_value=[]):
    out = _recommendations_impact()
    print("impact con lista vacia:", out)
    print("  capturedEuro:", out["capturedEuro"], "| improvedCount:", out["improvedCount"])
    print("  HONESTIDAD: banner NO se muestra (0 no inventado) ->", "PASS" if out["capturedEuro"] == 0 else "FAIL")

print("\n=== Prueba 2: con recomendaciones mejoradas y revenue comparable ===")
fake = [
    {"status": "measured", "outcome": "improved",
     "metricBefore": {"revenue": 100.0}, "metricNow": {"revenue": 150.0}},
    {"status": "measured", "outcome": "improved",
     "metricBefore": {"revenue": 50.0}, "metricNow": {"revenue": 40.0}},  # empeoro -> NO cuenta
    {"status": "measured", "outcome": "no_change",   # no improved -> NO cuenta
     "metricBefore": {"revenue": 10.0}, "metricNow": {"revenue": 12.0}},
    {"status": "done", "outcome": "improved",  # no measured -> NO cuenta
     "metricBefore": {"revenue": 20.0}, "metricNow": {"revenue": 40.0}},
    {"status": "measured", "outcome": "improved",
     "metricBefore": {"revenue": 0.0}, "metricNow": {"revenue": 30.0}},  # before 0 -> sin comparable -> NO cuenta
]
with patch.object(recommendation_store, "list_recommendations", return_value=fake):
    out = _recommendations_impact()
    print("impact:", out)
    # Solo la 1a cuenta: (150-100)=50. El resto excluido.
    expected = 50.0
    ok = abs(out["capturedEuro"] - expected) < 0.001 and out["improvedCount"] == 1
    print("  esperado: 50.0 (solo 1a, improved y comparable), improvedCount=1")
    print("  ->", "PASS" if ok else "FAIL", "(capturedEuro=", out["capturedEuro"], ", count=", out["improvedCount"], ")")

print("\n=== Prueba 3: solo mejoras con revenue comparable (b>0 y n>0) ===")
fake2 = [
    {"status": "measured", "outcome": "improved",
     "metricBefore": {"revenue": 200.0}, "metricNow": {"revenue": 260.0}},
    {"status": "measured", "outcome": "improved",
     "metricBefore": {"revenue": 0.0}, "metricNow": {"revenue": 5.0}},  # before 0 -> excluido
]
with patch.object(recommendation_store, "list_recommendations", return_value=fake2):
    out = _recommendations_impact()
    print("impact:", out)
    ok = out["capturedEuro"] == 60.0 and out["improvedCount"] == 1
    print("  esperado 60.0, count 1 (before>0 y now>0 exigido) ->", "PASS" if ok else "FAIL")

print("\n=== Resumen ===")
print("El endpoint NO suma 0 inventado (exige measured+improved+before>0&now>0).")
