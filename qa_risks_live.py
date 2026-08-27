import json, urllib.request, urllib.parse
CLOUD="http://127.0.0.1:8000"
def req(method, base, path, token=None, form=None):
    data=None; headers={"Accept":"application/json"}
    if form is not None:
        data=urllib.parse.urlencode(form).encode(); headers["Content-Type"]="application/x-www-form-urlencoded"
    if token: headers["Authorization"]="Bearer "+token
    r=urllib.request.Request(base+path,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(r,timeout=10) as resp: return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, str(e)
st,lr=req("POST",CLOUD,"/api/auth/login",form={"username":"ceo","password":"E8kYBk7DYJUhaN2X9ork1g"})
tok=lr.get("access_token")
st,dash=req("GET",CLOUD,"/api/dashboard",token=tok)
dd=dash.get("data",dash)
priorities=dd.get("priorities") if isinstance(dd,dict) else None
print("priorities type:", type(priorities))
if isinstance(priorities,list):
    print("priorities total:", len(priorities))
    risks=[p for p in priorities if (p.get("type")=="risk")]
    print("priorities type=risk:", len(risks))
    for r in risks[:10]:
        print("   RISK:", {k:r.get(k) for k in ["id","title","summary","type","severity","score","status"]})
    # show sample of other types
    from collections import Counter
    print("type distribution:", Counter((p.get("type") for p in priorities if isinstance(p,dict))))
# also sources
print("\nsources:", json.dumps(dd.get("sources"))[:300] if isinstance(dd,dict) else None)
print("dataMode:", dd.get("dataMode") if isinstance(dd,dict) else None)
