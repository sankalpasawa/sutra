"""Run:  python server.py   then open http://127.0.0.1:8770
Mock mode (no API key): STUDIO_MOCK=1 python server.py
"""
import argparse
import http.server
import json
import os
import webbrowser
from urllib.parse import parse_qs, urlparse

import llm
from studio import Studio

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = Studio()


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "ui.html"), encoding="utf-8") as f:
                return self._send(200, f.read(), "text/html")
        if u.path == "/api/state":
            since = int(parse_qs(u.query).get("since", ["0"])[0])
            return self._send(200, json.dumps(STUDIO.snapshot(since), ensure_ascii=False))
        if u.path == "/site/live":  # HTML Development has streamed so far in the current call
            a = STUDIO.activity
            html = llm.partial_html(STUDIO.live) if a and a["agent"] == "development" else ""
            return self._send(200, html, "text/html")
        if u.path.startswith("/site/"):
            key = u.path.rsplit("/", 1)[-1]
            sites = STUDIO.sites
            if not sites:
                return self._send(200, "<p style='font:14px system-ui;color:#667;padding:24px'>"
                                       "No site yet. It appears here once Development builds it.</p>", "text/html")
            i = len(sites) if key == "latest" else int(key.lstrip("v") or 0)
            if not 1 <= i <= len(sites):
                return self._send(404, "not found", "text/plain")
            return self._send(200, sites[i - 1], "text/html")
        self._send(404, "not found", "text/plain")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/api/say":
            text = (body.get("text") or "").strip()
            if not text:
                return self._send(400, json.dumps({"error": "empty message"}))
            ok = STUDIO.user_says(text)
            return self._send(200 if ok else 409, json.dumps({"ok": ok}))
        if self.path == "/api/reset":
            STUDIO.reset()
            return self._send(200, json.dumps({"ok": True}))
        self._send(404, "{}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{a.port}/"
    print("Mode:", "MOCK (scripted agents)" if llm.MOCK else f"{llm.PROVIDER} API ({llm.MODEL})")
    print("Open:", url)
    if not a.no_browser:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
