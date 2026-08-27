# QA PRODUCTO TAREA 3 - ciclo real: recomendacion -> medida -> impacto.
# Usa el mecanismo REAL de recommendation_store (no mock). Config aislado en temp.
import sys, json, tempfile
from pathlib import Path
sys.path.insert(0, 'C:/Users/Admin/maios/desktop')
from runtime import config_store, recommendation_store as rs

tmp = tempfile.TemporaryDirectory()
cfg_file = Path(tmp.name) / 'maios.json'
config_store.CONFIG_FILE = cfg_file

# 1) simular un finding cross-sell con metricBefore revenue (fue medido antes con 100)
finding = {"type":"cross_sell","signature":"cs:art-101:art-102","title":"Cross A+B","entity":"art-101+art-102",
           "metrics":{"pair":"art-101+art-102","ordersTogether":60,"revenue":100.0}}
# crear una recomendacion "open" con metricBefore revenue=100
rec = rs.record_finding(finding, data=config_store.load())
print("rec creada:", rec.get("id")[:8], "status:", rec.get("status"), "metricBefore.revenue:", rec.get("metricBefore",{}).get("revenue"))

# 2) la entidad ahora genera revenue 150 (el usuario hizo algo) -> remedir
data = config_store.load()
data["businessFindings"] = [finding]
# _metric_for usa el finding; simular que el revenue ahora es 150
import runtime.recommendation_store as rsm
# parchear _metric_for para devolver revenue 150 (simula la medicion posterior real)
orig = rsm._metric_for
rsm._metric_for = lambda *a, **k: {"revenue":150.0}

m = rs.measure(rec_id=rec["id"], data=data)
print("medida:", {k:m.get(k) for k in ("status","outcome","measuredAt")})
print("metricNow.revenue:", (m.get("metricNow") or {}).get("revenue"))

# 3) el impacto debe reflejarlo
impact = None
# inyectar el store con la rec medida
from unittest.mock import patch
with patch.object(rs, "list_recommendations", return_value=[m]):
    from runtime.api_server import _recommendations_impact
    # config_store.load debe dar organizedSales para capturedPct; con revenue 0 -> pct None
    impact = _recommendations_impact()
print("\nimpact:", impact)
rsm._metric_for = orig
tmp.cleanup()
