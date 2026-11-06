"""Live web page for the budget negotiation demo.

Run:  python negotiate_server.py                 opens http://127.0.0.1:8771
      STUDIO_MOCK=1 STUDIO_MOCK_DELAY=1 python negotiate_server.py   (offline, 1 s per reply)
"""
import argparse
import http.server
import json
import os
import threading
import webbrowser
from urllib.parse import parse_qs, urlparse

import llm
from negotiate import HERE, Negotiation

SCENARIO = os.path.join(HERE, "scenarios", "budget.json")
LOCK = threading.Lock()
CURRENT = {"run": None, "thread": None}


def scenario():
    with open(SCENARIO, encoding="utf-8") as f:
        return json.load(f)


def start():
    with LOCK:
        t = CURRENT["thread"]
        if t and t.is_alive():
            return False
        n = Negotiation(scenario())

        def go():
            try:
                n.run()
            except SystemExit:  # model error: n.error already says why
                pass
            except Exception as e:  # noqa: BLE001
                n.error = f"{type(e).__name__}: {e}"
            n.thinking = None

        CURRENT["run"], CURRENT["thread"] = n, threading.Thread(target=go, daemon=True)
        CURRENT["thread"].start()
        return True


def snapshot(since):
    n = CURRENT["run"]
    s = scenario()
    base = {"title": s["title"], "goal": s["goal"], "budget": s["budget"],
            "agents": [a["name"] for a in s["agents"]], "ceo": s["ceo"]["name"],
            # shown to the audience only; each agent's prompt still contains just its own minimum
            "floors": {a["name"]: Negotiation._floor(a["private_goal"]) for a in s["agents"]},
            "mode": "mock" if llm.MOCK else f"{llm.PROVIDER} {llm.MODEL}"}
    if not n:
        return {**base, "running": False, "phase": "idle", "messages": [], "count": 0}
    t = CURRENT["thread"]
    return {**base, "running": bool(t and t.is_alive()), "phase": n.phase, "thinking": n.thinking,
            "messages": n.chat[since:], "count": len(n.chat), "table": n.table,
            "accepted": sorted(n.accepted), "reserve": n.reserve, "calls": n.calls,
            "result": n.result, "error": n.error, "folder": os.path.relpath(n.dir, HERE)}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "negotiate_ui.html"), encoding="utf-8") as f:
                return self._send(200, f.read(), "text/html")
        if u.path == "/api/state":
            since = int(parse_qs(u.query).get("since", ["0"])[0])
            return self._send(200, json.dumps(snapshot(since), ensure_ascii=False))
        self._send(404, "not found", "text/plain")

    def do_POST(self):
        if self.path == "/api/start":
            ok = start()
            return self._send(200 if ok else 409, json.dumps({"ok": ok}))
        self._send(404, "{}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8771)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{a.port}/"
    print("Mode:", "MOCK (rule-based agents)" if llm.MOCK else f"{llm.PROVIDER} API ({llm.MODEL})")
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
