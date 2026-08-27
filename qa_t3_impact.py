# QA PRODUCTO TAREA 3 - ciclo real medicion -> impacto, backend real.
# Se inyecta una rec ya "measured+improved" con deltas reales en el config
# (persistencia real), y se verifica que _recommendations_impact lo refleja.
import sys, json, tempfile
from pathlib import Path
sys.path.insert(0, 'C:/Users/Admin/maios/desktop')
from runtime import config_store, recommendation_store as rs
from runtime.api_server import _recommendations_impact

tmp = tempfile.TemporaryDirectory()
cfg_file = Path(tmp.name) / 'maios.json'
config_store.CONFIG_FILE = cfg_file

# rec measured+improved con deltas reales + facturacion real
rec = {
    "id":"rec-measured-1",
    "title":"Cross-sell A+B",
    "status":"measured",
    "outcome":"improved",
    "metricBefore":{"revenue":100.0},
    "metricNow":{"revenue":150.0},   # delta +50
}
rec2 = {
    "id":"rec-nochange-2",
    "title":"Reactivar cliente",
    "status":"measured",
    "outcome":"no_change",
    "metricBefore":{"revenue":80.0},
    "metricNow":{"revenue":80.0},
}
config_store.save({"recommendations":[rec, rec2], "organizedSales":[
    {"total":500.0}  # facturacion real 500 -> capturedPct = 50/500 = 10%
]})

# usar el store real: list_recommendations lee del config
out = _recommendations_impact()
print("impact real:", out)
print("\nVERIFICACION:")
print("  capturedEuro (debe ser 50.0 = solo improved):", out["capturedEuro"])
print("  improvedCount:", out["improvedCount"], "| noChangeCount:", out["noChangeCount"])
print("  capturedPct (50/5000=1.0%):", out["capturedPct"])
ok = out["capturedEuro"]==50.0 and out["improvedCount"]==1 and out["noChangeCount"]==1
print("\nRESULTADO:", "OK - el ciclo medicion->impacto funciona con deltas reales" if ok else "revisar")
tmp.cleanup()
