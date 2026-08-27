import json, urllib.request, urllib.parse

BASE = "http://127.0.0.1:8000"

def req(method, path, token=None, body=None, form=None):
    data = None
    headers = {"Accept": "application/json"}
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, str(e)

# login
st, lr = req("POST", "/api/auth/login", form={"username":"ceo","password":"E8kYBk7DYJUhaN2X9ork1g"})
tok = lr.get("access_token")
print("LOGIN:", st, "role:", lr.get("role"))

# dashboard (decisions)
st, dash = req("GET", "/api/dashboard", token=tok)
print("\n=== /api/dashboard status", st)
if isinstance(dash, dict):
    dd = dash.get("data", dash)
    print("keys:", list(dd.keys()) if isinstance(dd, dict) else type(dd))
    decisions = dd.get("decisions") if isinstance(dd, dict) else None
    if decisions is not None:
        pending = [x for x in decisions if (x.get("status") or "pending")=="pending"]
        print("decisions total:", len(decisions), "pending:", len(pending))
        for x in pending[:5]:
            print("   PENDING DEC:", {k:x.get(k) for k in ["id","title","summary","status","createdAt"]})
    guardrails = dd.get("guardrails") if isinstance(dd, dict) else None
    if guardrails is not None:
        print("guardrails total:", len(guardrails))
        for g in guardrails[:5]:
            print("   GR:", {k:g.get(k) for k in ["id","title","status","summary"]})

# try direct endpoints
for ep in ["/api/guardrails", "/api/decisions", "/api/files/candidates", "/api/files"]:
    try:
        st, r = req("GET", ep, token=tok)
        print(f"\n=== {ep} status {st}")
        if isinstance(r, dict):
            print("   keys:", list(r.keys())[:20])
            for k in ["guardrails","decisions","candidates","files"]:
                if k in r and isinstance(r[k], list):
                    print(f"   {k}: {len(r[k])}")
    except Exception as e:
        print(f"=== {ep} ERR {e}")
