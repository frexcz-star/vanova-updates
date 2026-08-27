import asyncio, json, os, urllib.request, urllib.parse, subprocess, time, uuid
import websockets

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9335
CLOUD = "http://127.0.0.1:8000"
URL = CLOUD + "/"
TMP = os.path.join(os.environ.get("LOCALAPPDATA",""), "Temp")

# --- cloud REST helpers (thread-safe enough for setup) ---
def cloud(method, path, token=None, json_body=None, form=None):
    data=None; headers={"Accept":"application/json"}
    if form is not None:
        data=urllib.parse.urlencode(form).encode(); headers["Content-Type"]="application/x-www-form-urlencoded"
    elif json_body is not None:
        data=json.dumps(json_body).encode(); headers["Content-Type"]="application/json"
    if token: headers["Authorization"]="Bearer "+token
    r=urllib.request.Request(CLOUD+path,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(r,timeout=15) as resp: return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, str(e)

def login():
    st,lr=cloud("POST","/api/auth/login",form={"username":"ceo","password":"E8kYBk7DYJUhaN2X9ork1g"})
    assert st==200, f"login failed {st} {lr}"
    return lr["access_token"]

class CDP:
    def __init__(self, url): self.url=url; self.id=0; self.pending={}
    async def connect(self):
        self.ws=await websockets.connect(self.url,max_size=None); return self
    async def call(self, method, params=None):
        self.id+=1; mid=self.id; fut=asyncio.get_event_loop().create_future()
        self.pending[mid]=fut
        await self.ws.send(json.dumps({"id":mid,"method":method,"params":params or {}}))
        return await fut
    async def pump(self):
        async for msg in self.ws:
            d=json.loads(msg)
            if d.get("id") in self.pending: self.pending.pop(d["id"]).set_result(d)

async def main():
    tok = login()
    print("CLOUD LOGIN OK, role owner")

    user_data=os.path.join(TMP,"chrome-cdp-mathew3")
    proc=subprocess.Popen([CHROME, f"--remote-debugging-port={PORT}", f"--user-data-dir={user_data}",
        "--headless=new","--disable-gpu","--no-sandbox","--window-size=1400,900",URL],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(4)
    ver=json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json").read())
    page=[t for t in ver if t.get("type")=="page"][0]
    cdp=await CDP(page["webSocketDebuggerUrl"]).connect()
    pt=asyncio.ensure_future(cdp.pump())
    await cdp.call("Runtime.enable"); await cdp.call("Page.enable")

    async def jsA(expr):
        r=await cdp.call("Runtime.evaluate",{"expression":expr,"returnByValue":True,"awaitPromise":True})
        return (r.get("result",{}).get("result",{}) or {}).get("value")
    async def read_badge():
        return await jsA("""(() => {
          const bell=document.getElementById('hdr-bell'); if(!bell) return {err:'no-bell'};
          const b=bell.querySelector('.badge');
          return {text:b?b.textContent:null, opacity:b?getComputedStyle(b).opacity:null,
                  view:(window.state?window.state.view:null),
                  gr:(window.store?(window.store.guardrails||[]).length:null),
                  dec:(window.store?((window.store.decisions||[]).filter(d=>(d.status||'pending')==='pending').length):null),
                  risks:(window.store?((window.store.priorities||[]).filter(p=>p.type==='risk').length):null),
                  files:(window.store?(window.store.fileCandidates||[]).length:null)};
        })()""")

    await asyncio.sleep(3)
    # Login via UI
    await jsA("""(() => {
      const u=document.getElementById('l-user'),p=document.getElementById('l-pass');
      u.value='ceo';p.value='E8kYBk7DYJUhaN2X9ork1g';
      u.dispatchEvent(new Event('input',{bubbles:true}));p.dispatchEvent(new Event('input',{bubbles:true}));
      [...document.querySelectorAll('button')].find(b=>/entrar|acceder|iniciar/i.test(b.textContent||'')).click();
    })()""")
    # wait for app
    for _ in range(15):
        await asyncio.sleep(2)
        ready=await jsA("document.getElementById('app') && !document.getElementById('app').classList.contains('hidden')")
        if ready: break
    await asyncio.sleep(3)
    print("APP LOADED. Badge baseline:", json.dumps(await read_badge(), ensure_ascii=False))

    # 1) Navigate to a NON-whitelisted view: sales (Ventas). Also try finance, products, settings.
    nav = await jsA("typeof go==='function' ? (go('sales'),'navigated') : 'no-go'")
    print("NAVIGATE to sales (non-whitelisted):", nav)
    await asyncio.sleep(1)
    print("View now:", json.dumps(await read_badge(), ensure_ascii=False))

    # 2) Inject a REAL pending guardrail via cloud API while on 'sales'
    gid=str(uuid.uuid4())
    st,gr=cloud("POST","/api/guardrails",token=tok,json_body={"agent":"test-agent","action":"aprovechar_venta_test","target":"qa-"+gid[:8],"risk":"high"})
    print(f"INJECT guardrail {gid[:8]}: status {st}, {gr}")
    # Measure badge update latency in the non-whitelisted view
    t0=time.time(); seen=None
    for _ in range(30):
        await asyncio.sleep(0.5)
        b=await read_badge()
        if b.get("text") and b["text"]!="":
            seen=time.time()-t0; break
    print(f"BADGE updated to [{b.get('text')}] in {seen:.2f}s (view={b.get('view')}, gr={b.get('gr')})")

    # 3) Verify badge==drawer in this view: open drawer and compare counts
    await jsA("openNotificationsDrawer();")
    await asyncio.sleep(0.5)
    drawer=await jsA("""(() => {
      const d=document.getElementById('drawer');
      const b=d.querySelector('#drawer-body');
      return {open:d.classList.contains('open'), text:b?b.textContent.replace(/\\s+/g,' ').slice(0,200):null};
    })()""")
    print("DRAWER (should list the pending approval):", json.dumps(drawer, ensure_ascii=False))
    await jsA("closeDrawer();")

    # 4) 'Marcar como leídas' — test if it clears the badge (expect: does NOT clear real pending)
    await jsA("openNotificationsDrawer();")
    await asyncio.sleep(0.3)
    before=await read_badge()
    await jsA("""(() => {
      const btn=[...document.querySelectorAll('button')].find(b=>/marcar como le/i.test(b.textContent||''));
      if(btn) btn.click();
    })()""")
    await asyncio.sleep(1)
    after=await read_badge()
    print(f"'MARCAR COMO LEÍDAS' before={before.get('text')} after={after.get('text')} (view={after.get('view')})")

    # 5) Approve the guardrail via UI → measure recalc latency
    await jsA("openNotificationsDrawer();")
    await asyncio.sleep(0.3)
    t1=time.time(); recalc=None
    # trigger approve on the pending guardrail card
    click=await jsA("""(() => {
      const btn=[...document.querySelectorAll('#drawer button')].find(b=>/aprobar/i.test(b.textContent||''));
      if(btn){btn.click(); return 'clicked';}
      return 'no-approve-btn';
    })()""")
    print("CLICK APROBAR:", click)
    # wait for badge to clear (guardrail approved -> count drops)
    for _ in range(40):
        await asyncio.sleep(0.5)
        b=await read_badge()
        if not b.get("text") or b["text"]=="":
            recalc=time.time()-t1; break
    print(f"AFTER APPROVE badge=[{b.get('text')}] cleared in {recalc:.2f}s (gr={b.get('gr')})")

    # cleanup guardrail via API (ensure removed)
    st,dr=cloud("POST","/api/guardrails/decide",token=tok,json_body={"id":gid,"decision":"deny"})
    print("CLEANUP guardrail decide:", st, dr)

    proc.terminate()
    return 0

if __name__=="__main__":
    asyncio.run(main())
