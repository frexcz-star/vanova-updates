import asyncio, json, os, urllib.request, subprocess, time
import websockets

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9333
URL = "http://127.0.0.1:8000/"
TMP = os.path.join(os.environ.get("LOCALAPPDATA",""), "Temp")

class CDP:
    def __init__(self, url): self.url = url; self.id = 0; self.pending = {}
    async def connect(self):
        self.ws = await websockets.connect(self.url, max_size=None)
        return self
    async def call(self, method, params=None):
        self.id += 1; mid = self.id
        fut = asyncio.get_event_loop().create_future()
        self.pending[mid] = fut
        await self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        return await fut
    async def pump(self):
        async for msg in self.ws:
            d = json.loads(msg)
            if d.get("id") in self.pending:
                self.pending.pop(d["id"]).set_result(d)

async def main():
    user_data = os.path.join(TMP, "chrome-cdp-mathew2")
    proc = subprocess.Popen([
        CHROME, f"--remote-debugging-port={PORT}",
        f"--user-data-dir={user_data}", "--headless=new", "--disable-gpu",
        "--no-sandbox", "--window-size=1400,900", URL
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(4)
    ver = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json").read())
    page = [t for t in ver if t.get("type")=="page"][0]
    cdp = await CDP(page["webSocketDebuggerUrl"]).connect()
    pump_task = asyncio.ensure_future(cdp.pump())
    await cdp.call("Runtime.enable")
    await cdp.call("Page.enable")

    async def jsA(expr):
        r = await cdp.call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True})
        return (r.get("result",{}).get("result",{}) or {}).get("value")

    await asyncio.sleep(3)
    # Inspect login page presence
    has_login = await jsA("document.getElementById('login') ? !document.getElementById('login').classList.contains('hidden') : false")
    print("LOGIN VISIBLE:", has_login)

    # Fill and submit login
    fill = await jsA("""(() => {
      const u=document.getElementById('l-user'), p=document.getElementById('l-pass');
      if(!u||!p) return 'no-fields';
      u.value='ceo'; p.value='E8kYBk7DYJUhaN2X9ork1g';
      u.dispatchEvent(new Event('input',{bubbles:true})); p.dispatchEvent(new Event('input',{bubbles:true}));
      return 'filled';
    })()""")
    print("FILL:", fill)
    await asyncio.sleep(0.5)
    click = await jsA("""(() => {
      const btn=[...document.querySelectorAll('button')].find(b=>/entrar|acceder|login|iniciar|continuar/i.test(b.textContent||''));
      if(btn){btn.click(); return 'clicked:'+btn.textContent.trim();}
      return 'no-btn';
    })()""")
    print("CLICK:", click)
    # Wait for login to process and app to load
    for i in range(10):
        await asyncio.sleep(2)
        ready = await jsA("window.store && window.state && document.getElementById('app') && !document.getElementById('app').classList.contains('hidden')")
        if ready:
            print("APP READY after ~", (i+1)*2, "s"); break
    await asyncio.sleep(2)

    badge = await jsA("""(() => {
      const bell=document.getElementById('hdr-bell');
      if(!bell) return 'NO-BELL (not logged in?)';
      const b=bell.querySelector('.badge');
      return {
        badgeText: b?b.textContent:null,
        badgeOpacity: b?getComputedStyle(b).opacity:null,
        view: window.state?window.state.view:null,
        loggedIn: !!(window.state && window.state.token),
        store_guardrails:(window.store?(window.store.guardrails||[]).length:null),
        store_decisions_pending:(window.store?((window.store.decisions||[]).filter(d=>(d.status||'pending')==='pending').length):null),
        store_risks:(window.store?((window.store.priorities||[]).filter(p=>p.type==='risk').length):null),
        store_files:(window.store?(window.store.fileCandidates||[]).length:null),
        connected:(window.state?window.state.connected:null),
        dataMode:(window.state?window.state.dataMode:null)
      };
    })()""")
    print("BADGE STATE:", json.dumps(badge, ensure_ascii=False))

    # Open the notifications drawer and read its content + bell
    opn = await jsA("typeof openNotificationsDrawer==='function' ? (openNotificationsDrawer(), 'opened') : 'no-fn'")
    print("OPEN DRAWER:", opn)
    await asyncio.sleep(1)
    drawer = await jsA("""(() => {
      const d=document.getElementById('drawer');
      if(!d) return 'no-drawer';
      const t=d.querySelector('#drawer-title'); 
      const body=d.querySelector('#drawer-body');
      return {open:d.classList.contains('open'), title:t?t.textContent:null, bodyText: body?body.textContent.replace(/\\s+/g,' ').slice(0,400):null};
    })()""")
    print("DRAWER:", json.dumps(drawer, ensure_ascii=False))

    # 'Marcar como leídas' button presence
    dismiss = await jsA("""(() => {
      const btn=[...document.querySelectorAll('button')].find(b=>/marcar como le/i.test(b.textContent||''));
      return btn ? 'PRESENT' : 'absent';
    })()""")
    print("DISMISS BTN:", dismiss)

    proc.terminate()
    return 0

if __name__ == "__main__":
    asyncio.run(main())
