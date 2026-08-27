# QA PRODUCTO TAREA 3 - validar el ciclo: recomendar -> marcar realizada -> medir delta EUR.
# Usa datos mock (etiquetado demo) porque el entorno real MOOVING no tiene ventas.
# Probar el mecanismo completo del "Valor Capturado" con config aislado (no toca produccion).
import sys, json, copy, tempfile
from pathlib import Path
sys.path.insert(0, 'C:/Users/Admin/maios/desktop')
from runtime import config_store, recommendation_store

tmp = tempfile.TemporaryDirectory()
config_store.CONFIG_FILE = Path(tmp.name) / 'maios.json'
config_store.save({'organizedSales': [], 'organizedProducts': []})

# Simular 2 recomendaciones: una measured+improved (delta real), una measured+no_change
recs = [
    {"id":"rec-1","title":"Cross-sell A+B","status":"done",
     "metricBefore":{"revenue":100.0},"metricNow":{"revenue":150.0},   # delta +50
     "outcome":"improved"},
    {"id":"rec-2","title":"Reactivar cliente","status":"done",
     "metricBefore":{"revenue":80.0},"metricNow":{"revenue":80.0},      # sin cambio
     "outcome":"no_change"},
]
recommendation_store = __import__('runtime.recommendation_store', fromlist=['x'])
# inyectar directamente en el store para el test
import runtime.recommendation_store as rs
# sobreescribir list para test
_orig = rs.list_recommendations
rs.list_recommendations = lambda: recs

from runtime.api_server import _recommendations_impact
out = _recommendations_impact()
print("impact con r1(improved,+50) y r2(no_change):", out)
print("\nESPECTATIVA honesta:")
print("  capturedEuro debe ser 50.0 (solo la improved cuenta)")
print("  improvedCount=1, noChangeCount=1")
ok = out['capturedEuro'] == 50.0 and out['improvedCount'] == 1 and out['noChangeCount'] == 1
print("\nRESULTADO:", "OK - el mecanismo mide el delta EUR real de las recs medidas" if ok else "revisar")

rs.list_recommendations = _orig
tmp.cleanup()
