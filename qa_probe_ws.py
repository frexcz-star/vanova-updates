import importlib
for mod in ["websocket", "websockets", "requests", "httpx"]:
    try:
        m = importlib.import_module(mod)
        print(f"{mod}: OK {getattr(m,'__version__','?')}")
    except Exception as e:
        print(f"{mod}: MISSING ({type(e).__name__})")
