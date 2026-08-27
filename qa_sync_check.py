import hashlib, os

repo_base = "C:/Users/Admin/maios/desktop/runtime"
inst_base = os.environ.get("LOCALAPPDATA", "") + "/Programs/VANOVA/resources/vanova/desktop/runtime"

files = ["process_manager.py","shopify_sync.py","facturascripts_sync.py","config_store.py",
         "agent_architect.py","hermes_chat.py","task_queue.py","api_server.py","file_inventory.py"]

def h(p):
    with open(p,'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()[:12]

for f in files:
    rp = os.path.join(repo_base, f)
    ip = os.path.join(inst_base, f)
    if not os.path.exists(rp):
        print("MISS repo", f); continue
    if not os.path.exists(ip):
        print("MISS inst", f); continue
    rh, ih = h(rp), h(ip)
    print("SYNC  " if rh==ih else "DESYNC", f, "(repo=%s inst=%s)" % (rh, ih))
