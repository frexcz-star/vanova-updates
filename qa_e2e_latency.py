import asyncio, json, os, urllib.request, urllib.parse, subprocess, time, uuid
import websockets

CHROME=r"C:\Program Files\Google\Chrome\Application\chrome.exe"; PORT=9337
CLOUD="http://127.0.0.1:8000"; URL=CLOUD+"/"; TMP=os.path.join(os.environ.get("LOCALAPPDATA",""),"Temp")

def cloud(method,path,token=None,json_body=None,form=None):
    data=None; headers={"Accept":"application/json"}
    if form is not None: data=urllib.parse.urlencode(form).encode(); headers["Content-Type"]="application/x-www-form-urlencoded"
    elif json_body is not None: data=json.dumps(json_body).encode(); headers["Content-Type"]="application/json"
    if token: headers["Authorization"]="Bearer "+token
    r=urllib.request.Request(CLOUD+path,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(r,timeout=15) as resp: return resp.status,json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code,json.loads(e.read().decode())
        except Exception: return e.code,str(e)
def login():
    st,lr=cloud("POST","/api/auth/login",form={"username":"ceo","password":"E8kYBk7DYJUhaN2X9ork1g"})
    assert st==200, lr; return lr["access_token"]

class CDP:
    def __init__(self,u): self.url=u; self.id=0; self.pending={}
    async def connect(self): self.ws=await websockets.connect(self.url,max_size=None); return self
    async def call(self,m,p=None):
        self.id+=1; mid=self.id; f=asyncio.get_event_loop().create_future(); self.pending[mid]=f
        await self.ws.send(json.dumps({"id":mid,"method":m,"params":p or {}})); return await f
    async def pump(self):
        async for msg in self.ws:
            d=json.loads(msg)
            if d.get("id") in self.pending: self.pending.pop(d["id"]).set_result(d)

async def main():
    tok=login()
    ud=os.path.join(TMP,"chrome-cdp-lat"); 
    proc=subprocess.Popen([CHROME,f"--remote-debugging-port={PORT}",f"--user-data-dir={ud}",
        "--headless=new","--disable-gpu","--no-sandbox","--window-size=1400,900",URL],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    time.sleep(4)
    ver=json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json").read())
    page=[t for t in ver if t.get("type")=="page"][0]
    cdp=await CDP(page["webSocketDebuggerUrl"]).connect()
    asyncio.ensure_future(cdp.pump()); await cdp.call("Runtime.enable"); await cdp.call("Page.enable")
    async def jsA(e):
        r=await cdp.call("Runtime.evaluate",{"expression":e,"returnByValue":True,"awaitPromise":True})
        return (r.get("result",{}).get("result",{}) or {}).get("value")
    async def btext(): return await jsA("""(()=>{const bell=document.getElementById('hdr-bell');if(!bell)return null;const b=bell.querySelector('.badge');return {text:b?b.textContent:null,opacity:b?getComputedStyle(b).opacity:null,view:(window.state?window.state.view:null)};})()""")
    await asyncio.sleep(3)
    await jsA("""(()=>{const u=document.getElementById('l-user'),p=document.getElementById('l-pass');u.value='ceo';p.value='E8kYBk7DYJUhaN2X9ork1g';u.dispatchEvent(new Event('input',{bubbles:true}));p.dispatchEvent(new Event('input',{bubbles:true}));[...document.querySelectorAll('button')].find(b=>/entrar|acceder|iniciar/i.test(b.textContent||'')).click();})()""")
    for _ in range(20):
        await asyncio.sleep(1)
        if await jsA("document.getElementById('app') && !document.getElementById('app').classList.contains('hidden')"): break
    await asyncio.sleep(5)  # let initial poll run a few ticks

    # Navigate to a non-whitelisted view and verify poll active
    await jsA("go('sales');")
    await asyncio.sleep(1)
    print("View:", json.dumps(await btext(), ensure_ascii=False))

    # Measure latency over 3 trials
    for trial in range(3):
        gid=str(uuid.uuid4())
        st,gr=cloud("POST","/api/guardrails",token=tok,json_body={"agent":"a","action":"trial_"+str(trial),"target":"t"+gid[:6],"risk":"medium"})
        gid2=gr.get("id")
        t0=time.time(); lat=None
        while time.time()-t0 < 25:
            await asyncio.sleep(0.2)
            b=await btext()
            if b and b.get("text") and b["text"]!="":
                lat=time.time()-t0; break
        print(f"Trial {trial}: badge->[{b.get('text') if b else '?'}] latency={lat:.2f}s view={b.get('view') if b else '?'}")
        # cleanup
        st2,dr=cloud("POST","/api/guardrails/decide",token=tok,json_body={"id":gid2,"decision":"deny"})
        # wait for badge to clear before next trial
        t0=time.time()
        while time.time()-t0 < 12:
            await asyncio.sleep(0.3)
            b=await btext()
            if b and (not b.get("text") or b["text"]==""): break
        await asyncio.sleep(3)  # let poll settle

    proc.terminate()

asyncio.run(main())
