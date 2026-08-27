import json, urllib.request, urllib.parse, time
CLOUD="http://127.0.0.1:8000"; RUNTIME="http://127.0.0.1:8765"
def req(base,path,token=None):
    headers={"Accept":"application/json"}
    if token: headers["Authorization"]="Bearer "+token
    r=urllib.request.Request(base+path,headers=headers,method="GET")
    t0=time.time()
    try:
        with urllib.request.urlopen(r,timeout=20) as resp:
            body=resp.read(); return resp.status, len(body), time.time()-t0
    except urllib.error.HTTPError as e:
        try: body=e.read()
        except Exception: body=b""
        return e.code, len(body), time.time()-t0

# login
form=urllib.parse.urlencode({"username":"ceo","password":"E8kYBk7DYJUhaN2X9ork1g"}).encode()
r=urllib.request.Request(CLOUD+"/api/auth/login",data=form,headers={"Content-Type":"application/x-www-form-urlencoded"},method="POST")
tok=json.loads(urllib.request.urlopen(r).read())["access_token"]

# The endpoints pollLiveTaskState awaits (badge sources + other):
endpoints = [
    ("CLOUD","/api/guardrails"),
    ("CLOUD","/api/dashboard"),
    ("CLOUD","/api/decisions"),
    ("CLOUD","/api/tasks"),
    ("CLOUD","/api/insights"),
    ("CLOUD","/api/command-center"),
    ("RUNTIME","/api/files/candidates"),
    ("RUNTIME","/api/approvals"),
]
for base_name, base in [("CLOUD",CLOUD),("RUNTIME",RUNTIME)]:
    pass
print(f"{'endpoint':<38} {'status':<7} {'bytes':<7} {'time_s'}")
for which, path in endpoints:
    base = CLOUD if which=="CLOUD" else RUNTIME
    tok_use = tok if which=="CLOUD" else None
    st, bl, dt = req(base, path, tok_use)
    print(f"{which+' '+path:<38} {st:<7} {bl:<7} {dt:.2f}")
