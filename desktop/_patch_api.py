from pathlib import Path
p = Path(r"C:\Users\Admin\maios\desktop\runtime\api_server.py")
text = p.read_text(encoding="utf-8")
needle = "class Handler(BaseHTTPRequestHandler):"
insert = """class RuntimeHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = False


"""
text = text.replace(needle, insert + needle)
text = text.replace('ThreadingHTTPServer(("127.0.0.1", port), Handler)', 'RuntimeHTTPServer(("127.0.0.1", port), Handler)')
p.write_text(text, encoding='utf-8')
