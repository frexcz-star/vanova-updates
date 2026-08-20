"""Servidor estatico con soporte Range requests para el updater de MAIOS.

Uso:  python range_static_server.py <directorio> <puerto>
Sirve archivos con soporte de reanudacion de descargas (HTTP Range / 206),
que es lo que el downloader de MAIOS usa para reanudar descargas.
"""
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class RangeHandler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def send_head(self):
        path = self.translate_path(self.path)
        if not os.path.exists(path):
            self.send_error(404, "File not found")
            return None

        ctype = self.guess_type(path)
        size = os.path.getsize(path)

        range_header = self.headers.get("Range")
        start, end = 0, size - 1
        status = 200

        if range_header:
            try:
                spec = range_header.strip().split("=")[1]
                start_s, _, end_s = spec.partition("-")
                if start_s:
                    start = int(start_s)
                if end_s:
                    end = int(end_s)
                if start > end or start >= size:
                    self.send_error(416, "Requested Range Not Satisfiable")
                    return None
                status = 206
            except Exception:
                pass

        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()

        f = open(path, "rb")
        f.seek(start)
        # Guardamos cuantos bytes hay que enviar; copyfile() respeta este limite.
        self._range_send_len = length
        return f

    def copyfile(self, source, outputfile):
        # El base copia hasta EOF; aqui enviamos exactamente Content-Length
        # bytes para que los rangos parciales (resume) nunca se desborden.
        remaining = getattr(self, "_range_send_len", None)
        if remaining is None:
            # Sin limite (no deberia ocurrir): copia completa.
            return super().copyfile(source, outputfile)
        while remaining > 0:
            chunk = source.read(min(256 * 1024, remaining))
            if not chunk:
                break
            outputfile.write(chunk)
            remaining -= len(chunk)


if __name__ == "__main__":
    serve_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8137
    os.chdir(serve_dir)
    srv = ThreadingHTTPServer(("127.0.0.1", port), RangeHandler)
    print(f"Range static server: http://127.0.0.1:{port} -> {serve_dir}", flush=True)
    srv.serve_forever()
