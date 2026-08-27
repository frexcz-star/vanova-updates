import json, urllib.request, urllib.parse

CLOUD = "http://127.0.0.1:8000"
RUNTIME = "http://127.0.0.1:8765"

def req(method, base, path, token=None, form=None):
    data = None
    headers = {"Accept": "application/json"}
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if token:
        headers["Authorization"] = "Bearer " + token
    r = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, str(e)

# cloud login
st, lr = req("POST", CLOUD, "/api/auth/login", form={"username":"ceo","password":"E8kYBk7DYJUhaN2X9ork1g"})
tok = lr.get("access_token")
print("CLOUD LOGIN:", st, lr.get("role"))

def dump(label, base, path, token=None):
    st, r = req("GET", base, path, token=token)
    print(f"\n### {label} :: {path} -> {st}")
    if isinstance(r, dict):
        print("   keys:", list(r.keys()))
    elif isinstance(r, list):
        print("   list len:", len(r))
    return r

# Cloud guardrails + decisions + approvals
gr = dump("CLOUD", CLOUD, "/api/guardrails", tok)
dc = dump("CLOUD", CLOUD, "/api/decisions", tok)
print("   decisions content:", json.dumps(dc)[:400])
ap = dump("CLOUD", CLOUD, "/api/approvals", tok)

# Runtime candidates + approvals
cand = dump("RUNTIME", RUNTIME, "/api/files/candidates")
apr = dump("RUNTIME", RUNTIME, "/api/approvals")

# summarize counts
def count_gr(x):
    if isinstance(x, dict): x = x.get("guardrails", x)
    if not isinstance(x, list): return None
    return len(x), [(g.get("id"), g.get("status"), (g.get("title") or g.get("summary") or "")[:40]) for g in x]
def count_dc(x):
    if isinstance(x, dict): x = x.get("decisions", x)
    if not isinstance(x, list): return None
    return len(x), [(d.get("id"), d.get("status"), (d.get("title") or d.get("summary") or "")[:40]) for d in x]
def count_cand(x):
    if isinstance(x, dict):
        x = x.get("files", x.get("candidates", []))
    if not isinstance(x, list): return None
    return len(x)
def count_ap(x):
    if isinstance(x, dict): x = x.get("approvals", x)
    if not isinstance(x, list): return None
    return len(x)

print("\n===== BADGE SOURCES (real, live) =====")
print("guardrails:", count_gr(gr))
print("decisions:", count_dc(dc))
print("approvals cloud:", count_ap(ap), "runtime:", count_ap(apr))
print("fileCandidates runtime:", count_cand(cand))
print("fileCandidates detail:", json.dumps(cand)[:300])
