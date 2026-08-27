# QA: validar persistencia de archivos (agregar/aceptar/eliminar) tras reinicio.
# Simula el flujo real con config aislado (temp). No toca produccion.
import sys, tempfile, os
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, 'C:/Users/Admin/maios/desktop')
from runtime import config_store, file_inventory

tmp = tempfile.TemporaryDirectory()
cfg_file = Path(tmp.name) / 'maios.json'
config_store.CONFIG_FILE = cfg_file
# Inicializar config
config_store.save({'scanFiles': [], 'fileCandidates': []})

print("=== Flujo 1: agregar archivo -> persiste ===")
r = file_inventory.add_imported_file({'name': 'ventas.csv', 'path': 'C:/datos/ventas.csv', 'source': 'import'})
print("add:", r.get('ok'), "| count:", r.get('count'))
# "Reiniciar": recargar desde disco (como un nuevo proceso)
config_store.CONFIG_FILE = cfg_file  # mismo archivo
d = config_store.load()
files = [f for f in d.get('scanFiles', []) if isinstance(f, dict)]
print("tras 'reinicio', scanFiles:", len(files), "| contiene ventas.csv:", any('ventas' in str(f.get('path','')) for f in files))

print("\n=== Flujo: eliminar archivo -> persiste la eliminacion ===")
if files:
    p = files[0]['path']
    r2 = file_inventory.remove_imported_file(p)
    print("remove:", r2.get('ok'))
    d2 = config_store.load()
    files2 = [f for f in d2.get('scanFiles', []) if isinstance(f, dict)]
    print("tras reinicio, scanFiles:", len(files2), "| ventas presente:", any('ventas' in str(f.get('path','')) for f in files2))

print("\n=== RESULTADO QA ===")
print("Si el archivo persiste tras reiniciar -> el bug NO se reproduce con este flujo aislado.")
print("El bug podria estar en el flujo REAL (organize_files en thread que pisa scanFiles).")
tmp.cleanup()
