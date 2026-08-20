"""QA verificación funcional BUG-001/BUG-002 — criterio correcto.
BUG-001 real: los findings originales NO deben recrearse como nuevos (duplicación).
Criterio: (a) ninguna firma duplicada dentro de un run; (b) todos los sigs
originales preservados tras re-análisis con ref desplazada.
"""
import sys, os
from datetime import timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "desktop"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tests"))

from runtime import detection_engine as de
from test_detection_engine import _rich_data, _sale, TODAY

def run_persisted(stored, data):
    captured = {}
    with patch.object(de.config_store, "load", side_effect=lambda: dict(data)), \
         patch.object(de.config_store, "save", side_effect=lambda d: captured.update(d)):
        result = de.run_detection(data, persist=True)
    data.update(captured)
    return result

def dup_sigs(findings):
    from collections import Counter
    c = Counter(f["signature"] for f in findings)
    return {sig: n for sig, n in c.items() if n > 1}

# Run 1: baseline
data1 = _rich_data()
r1 = run_persisted({}, data1)
sigs1 = {f["signature"] for f in r1["findings"]}
d1 = dup_sigs(r1["findings"])

# Run 2: re-análisis con ref desplazada (venta futura)
data2 = _rich_data()
future = (TODAY + timedelta(days=45)).isoformat()
data2["organizedSales"] = data2["organizedSales"] + [_sale("O-NEW", future, ("A", 1, 10.0))]
r2 = run_persisted({}, data2)
sigs2 = {f["signature"] for f in r2["findings"]}
d2 = dup_sigs(r2["findings"])

print(f"run1: {len(r1['findings'])} findings, {len(sigs1)} sigs únicos, duplicados={d1 or 'ninguno'}")
print(f"run2: {len(r2['findings'])} findings, {len(sigs2)} sigs únicos, duplicados={d2 or 'ninguno'}")
print(f"originales preservados: {len(sigs1 & sigs2)}/{len(sigs1)}")
print(f"nuevos legítimos (venta futura): {len(sigs2 - sigs1)}")

ok_dup = not d1 and not d2
ok_preserved = len(sigs1 & sigs2) == len(sigs1)
print(f"BUG-001: {'OK' if (ok_dup and ok_preserved) else 'FALLA'} "
      f"(sin firmas duplicadas={ok_dup}, originales preservados={ok_preserved})")

# BUG-002: falsa auto-resolución
data3 = _rich_data()
r3 = run_persisted({}, data3)
target = next((f for f in r3["findings"] if f["status"] == "new"), None)
if target:
    de.update_finding_status(target["id"], "acknowledged")
    data4 = _rich_data()
    future2 = (TODAY + timedelta(days=60)).isoformat()
    data4["organizedSales"] = data4["organizedSales"] + [_sale("O-NEW2", future2, ("A", 1, 10.0))]
    r4 = run_persisted({}, data4)
    found = [f for f in r4["findings"] if f["signature"] == target["signature"]]
    if found:
        st = found[0]["status"]
        print(f"BUG-002: '{target['type']}' status tras re-análisis = {st} -> "
              f"{'OK' if st != 'resolved' else 'FALLA (auto-resuelto)'}")
    else:
        print("BUG-002: FALLA — finding perdido tras re-análisis")
else:
    print("BUG-002: sin finding 'new' para probar")
