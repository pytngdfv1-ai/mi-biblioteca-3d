"""Renderizador: abre render/render.html en Chromium (WebGL por software) y devuelve hojas de cuadros."""
import base64
import functools
import http.server
import io
import os
import threading

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _Q(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=ROOT, **k)

    def log_message(self, *a):
        pass


def data_url(jpeg_bytes, mime="image/jpeg"):
    return f"data:{mime};base64," + base64.b64encode(jpeg_bytes).decode()


class Renderer:
    def __init__(self):
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Q)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.pw = sync_playwright().start()
        self.br = self.pw.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
        self.pg = self.br.new_page(viewport={"width": 300, "height": 300})
        self.pg.goto(f"http://127.0.0.1:{self.srv.server_port}/render/render.html")
        self.pg.wait_for_function("window.ready === true", timeout=60000)

    def sheet(self, **opts):
        """Devuelve la hoja de cuadros como imagen PIL (RGBA)."""
        url = self.pg.evaluate("o => window.renderSheet(o)", opts)
        return Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))).convert("RGBA")

    def close(self):
        try:
            self.br.close()
            self.pw.stop()
            self.srv.shutdown()
        except Exception:
            pass


def webp(im, q=72):
    b = io.BytesIO()
    im.save(b, "WEBP", quality=q, method=6)
    return b.getvalue()
