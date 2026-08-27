import json, urllib.request, urllib.parse

BASE = "http://localhost:8000"

def post_token():
    data = urllib.parse.urlencode({"username": "ceo", "password": "mooving2026"}).encode()
    req = urllib.request.Request(BASE + "/token", data=data,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())

def get(path, token):
    req = urllib.request.Request(BASE + path, headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read().decode()

tok = post_token()
t = tok.get("access_token", "")
print("token_len:", len(t))
dash = json.loads(get("/api/dashboard", t))
print("=== /api/dashboard (live cloud) ===")
print("dataMode:", dash.get("dataMode"))
print("decisions count:", len(dash.get("decisions", [])))
print("decisions statuses:", [d.get("status") for d in dash.get("decisions", [])][:10])
print("guardrails/priorities keys present:", "priorities" in dash)

# decisions endpoint
dec = json.loads(get("/api/decisions", t))
print("\n=== /api/decisions ===")
print("count:", len(dec) if isinstance(dec, list) else dec)
