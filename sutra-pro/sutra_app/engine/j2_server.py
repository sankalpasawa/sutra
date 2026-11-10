"""J2's stdlib HTTP server, kept for the legacy tests and single-run development (work package E2, engine design 3.1).

The application never uses it: uvicorn serves the FastAPI routes of `engine/api`, and `python -m sutra_app` does not start this
module. It is a thin adapter over `views.py`, which holds the one implementation of the 37 handlers: it picks the view from the
path, builds the `RunCtx` of the one global run `RUN` (state read from the live `J2Run` per request, no files) and sends the
`Reply`. Every text body goes through `redact()`. A question (`POST /api/ask`) is answered from the run's records, always: this
adapter has no model port, and no path of this tree calls `llm.ask` for an answer (J2 sync 4, D147).

Differences from J2's `j2_server.py` (all written down in docs/notes/E2.md):
- `do_POST` routes on `urlparse(self.path).path`, so `POST /api/say?dept=web` is not a 404 (J2 compared the whole `self.path`) [S3-web-07].
- `HERE` is the J2 checkout named by `SUTRA_J2_CHECKOUT` (J2's own page lives there), or None: then `/` is a 404 and `/vendor/d3.min.js`
  is too. The tests point `HERE` and `RUN` elsewhere at run time; both are read per request.
- It never imports `sutra_app.ui`.

Run:  SUTRA_J2_CHECKOUT=<J2 checkout> STUDIO_MOCK=1 scripts/py -m sutra_app.engine.j2_server
"""
import argparse
import http.server
import json
import os
import traceback
import webbrowser
from urllib.parse import parse_qs, urlparse

from . import j2, j2_agent, llm, views
from .j2 import J2Run
from .views import DOCX, MemoryPaths, RunCtx

RUN = J2Run()
HERE = os.environ.get("SUTRA_J2_CHECKOUT") or None
VENDOR = os.path.join(HERE, "vendor") if HERE else None       # never HERE at request time: tests point HERE at a temp page
__all__ = ["RUN", "HERE", "VENDOR", "DOCX", "Handler", "secrets", "redact", "route", "main"]


def secrets():
    """Values the page must never show: every .env value and any env var whose name looks like a credential."""
    vals = {v for k, v in os.environ.items() if any(w in k.upper() for w in ("KEY", "TOKEN", "SECRET", "PASSWORD", "AUTH"))}
    try:
        with open(os.path.join(HERE, ".env"), encoding="utf-8") as f:
            vals |= {ln.split("=", 1)[1].strip().strip("\"'") for ln in f if "=" in ln and not ln.lstrip().startswith("#")}
    except (OSError, TypeError):          # TypeError: HERE is None
        pass
    return sorted((v for v in vals if len(v) >= 8), key=len, reverse=True)


def redact(text):
    for v in secrets():
        text = text.replace(v, "[redacted]")
    return text


def route(path):
    """(view name, extra query entries) of a GET path, or None. The parts of a path become query entries, as `views` expects."""
    if path in ("/", "/index.html", "/library"):         # /library: the same page, showing the template catalog (J2's own route; the app serves /d/{dept}/library)
        return "index", {}
    if path == "/vendor/d3.min.js":
        return "vendor", {}
    fixed = {"/api/state": "state", "/api/runs": "runs", "/api/call": "call", "/api/preview": "preview", "/api/docs": "docs",
             "/api/map": "map", "/api/plan": "plan", "/api/plan-map": "plan_map", "/api/library": "library",
             "/api/catalog": "catalog", "/api/run-templates": "run_templates", "/api/artifacts": "artifacts", "/api/agent": "agent",
             "/api/activity": "activity", "/api/code": "code", "/api/artifacts/tree": "artifacts_tree",
             "/api/artifacts/groups": "artifacts_groups", "/api/artifact": "artifact", "/api/story": "story", "/api/board": "board",
             "/api/audits": "audits", "/api/refs": "refs", "/api/runlist": "runlist", "/api/changes": "changes"}
    if path in fixed:
        return fixed[path], {}
    if path.startswith("/api/library/"):      # /api/library/<artifact>/<section>/<slug>/v<N>
        parts = path[len("/api/library/"):].split("/")
        parts = parts if len(parts) == 4 else ["", "", "", ""]
        return "library_item", dict(zip(("artifact", "section", "slug", "version"), parts))
    last = path.rsplit("/", 1)[-1]
    if path.startswith("/shot/"):
        return "shot", {"n": last}
    if path.startswith("/file/"):
        return "file", {"name": last}
    if path.startswith("/site/"):
        return "site", {"key": last}
    return None


class _RunCommands:
    """The POSTs that act, done on whichever run `RUN` is now."""

    def say(self, text):
        return RUN.user_says(text)

    def ask(self, who, question, run_id):
        """J2's answer to a question about a run, from its records only (`ask=None`): `d` is J2's own resolution, a saved run's
        folder for a run id, else the run `RUN` holds, and None when the folder is missing. No model is ever called here (R2)."""
        d = j2.saved_dir(run_id) if run_id else RUN.dir
        return j2_agent.answer(d if d and os.path.isdir(d) else None, who, question, ask=None)

    def set_output(self, out):
        ok = RUN.set_output(out)
        return ok, RUN.output

    def reset(self):
        if RUN.status == "running":
            return False
        RUN.reset()
        return True


def _ctx(q, name):
    """The `RunCtx` of this request. A saved run (`?run=`) is read from `j2.RUNS_DIR` (read per request: the tests change it)."""
    live_id = os.path.basename(RUN.dir)
    run = q.get("run")              # a saved run's folder name, opened read-only
    if run and run == live_id and not os.path.isdir(RUN.dir):
        run = None                  # the live run's id before its folder exists (no prompt sent yet): the live run, empty
    common = dict(runs_dir=j2.RUNS_DIR, live_id=live_id, memory=MemoryPaths(j2.MEMORY_FILE, j2.PLAYBOOK_FILE),
                  commands=_RunCommands(), here=HERE, vendor=VENDOR, dept_id=q.get("dept"))
    if run:
        return RunCtx("saved", run, j2.saved_dir(run, j2.RUNS_DIR), **common)
    snap, extras = views.live_state(RUN) if name in views.LIVE_VIEWS else (None, None)
    return RunCtx("live", live_id, RUN.dir, snap=snap, extras=extras, alive=True, **common)


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json", name="prd.docx"):
        if ctype in ("image/png", DOCX):     # a screenshot or a .docx: binary, no text to redact
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            if ctype == DOCX:
                self.send_header("Content-Disposition", f'attachment; filename="{name}"')
            self.end_headers()
            return self.wfile.write(body)
        data = redact(body if isinstance(body, str) else body.decode("utf-8", "replace")).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_reply(self, r):
        if r.ctype == "text/javascript":     # the d3 file: sent as it is, cached for an hour, not redacted
            self.send_response(r.code)
            self.send_header("Content-Type", "text/javascript; charset=utf-8")
            self.send_header("Cache-Control", r.cache)
            self.end_headers()
            return self.wfile.write(r.body)
        return self._send(r.code, r.body, r.ctype, r.name or "prd.docx")

    def do_GET(self):
        u = urlparse(self.path)
        found = route(u.path)
        if not found:
            return self._send(404, "not found", "text/plain")
        name, extra = found
        q = {**{k: v[0] for k, v in parse_qs(u.query).items()}, **extra}
        try:
            reply = views.VIEWS[name](_ctx(q, name), q)
        except Exception:      # noqa: BLE001 - a handler bug is a 500 for this request, never a dead connection
            traceback.print_exc()
            return self._send(500, '{"error": "internal"}')
        return self._send_reply(reply)

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        raw = self.rfile.read(n) or b"{}"
        try:
            body = json.loads(raw)
        except ValueError:
            body = None
        name = {"/api/say": "say", "/api/ask": "ask", "/api/playbooks/clear": "playbooks_clear", "/api/lessons/clear": "lessons_clear",
                "/api/output": "output", "/api/reset": "reset"}.get(urlparse(self.path).path)      # S3-web-07: the path, not the query
        if name is None:
            return self._send(404, "{}")
        if not isinstance(body, dict):
            return self._send(400, '{"error": "bad json"}')
        try:
            reply = views.VIEWS[name](_ctx({}, name), body)
        except Exception:      # noqa: BLE001
            traceback.print_exc()
            return self._send(500, '{"error": "internal"}')
        return self._send_reply(reply)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8773)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{a.port}/"
    print("Mode:", "MOCK (scripted functions)" if llm.MOCK else f"{llm.PROVIDER} ({llm.MODEL})")
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
