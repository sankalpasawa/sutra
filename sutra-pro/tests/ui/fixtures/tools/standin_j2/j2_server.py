"""A stand-in for J2's j2_server.py, for the tests of scripts/capture_j2_fixtures.py (UI-0). It is NOT J2: it answers the
same read routes with small fixed bodies, becomes `waiting` at the first state poll after the brief is posted, and shows in its state what
the capture script did to its process (the environment it saw, the clock, its folder), so a test can look at that.

The brief picks a behaviour: STRAY writes a file in this folder, SAYFAIL answers /api/say with 500, DIE ends the process
after the answer, HANG never finishes, BIG pads the state, ONE and TWO finish with that many chat lines, anything else
is a normal run (3 lines). Two control routes serve a test that
shares one process: POST /__standin/break {path, status} makes a GET path (with or without its query), or a POST path, answer that
status, and POST /__standin/reset forgets the brief and every break.
"""
import argparse
import datetime
import http.server
import json
import os
import sys
import time
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
WATCHED = ("HOME", "TZ", "STUDIO_MOCK", "J2_CHROME", "J2_MEMORY", "J2_RUNS_DIR", "J2_MEMORY_FILE", "J2_PLAYBOOK_FILE",
           "PYTHONDONTWRITEBYTECODE", "PYTHONHASHSEED", "PYTHONUTF8", "ANTHROPIC_API_KEY", "GITHUB_TOKEN", "J2_BUDGET")
RUN = {"brief": None, "polls": 0}
BROKEN = {}
WORKFLOWS = [{"id": "W-1", "atoms": [{"id": "W-1.a1"}, {"id": "W-1.a2"}]}, {"id": "W-2", "atoms": [{"id": "W-1.a1"}, {"id": "W-2.a1"}]}]
FUNCS = ("identity", "adaptation", "priority", "coordination", "audit", "validator")      # J2's j2_agent.FUNCS
SIMPLE = {
    "/api/runs": {"live": "j2-standin-run", "runs": []},
    "/api/runlist": {"live": "j2-standin-run", "runs": [{"id": "j2-standin-run", "title": "Stand-in", "status": "stopped", "output": "website"}]},
    "/api/changes": {"changes": []},
    "/api/map": {"run": "j2-standin-run", "nodes": [{"id": "n1"}], "edges": []},
    "/api/plan": {"found": False},
    "/api/plan-map": {"found": False},
    "/api/docs": {"prd": {"asked": False, "text": None, "workflows": []}},
    "/api/library": {"schema": "template-library/1", "groups": []},
    # the seed library index records where J2's own development runs ran: two of the values are home-folder paths (a made-up one here)
    "/api/catalog": {"schema": "template-library/1", "dir": "library", "groups": [],
                     "runs": [{"run": "r1", "library": "/Users/someone/work/library"}, {"run": "r2", "library": "/tmp/standin-library"}]},
    "/api/run-templates": {"decisions": []},
    "/api/artifacts": {"deliverables": [{"name": "Website", "type": "website", "form": "page"}, {"name": "Menu card", "type": "document", "form": "doc"}],
                       "records": []},
    "/api/artifacts/tree": {"schema": "artifacts-tree/1", "groups": []},
    "/api/artifacts/groups": {"schema": "artifacts-groups/1", "documents": {}, "site": None, "groups": []},
    "/api/board": {"schema": "board/1", "entries": []},
    "/api/story": {"schema": "story/1"},
    "/api/audits": [],
    "/api/refs": {"conditions": {}, "rubric": {}},
}


def state():
    brief = RUN["brief"]
    waiting = brief is not None and "HANG" not in brief and RUN["polls"] >= 1
    out = {
        "status": "waiting" if waiting else ("running" if brief else "idle"),
        "total": (1 if "ONE" in brief else 2 if "TWO" in brief else 3) if waiting else 1, "chat": [{"who": "you", "text": brief}] if brief else [], "workflows": WORKFLOWS if waiting else [],
        "studio": {"schema": "studio/1", "parts": [{"sec": w["id"], "name": "Part " + w["id"]} for w in WORKFLOWS] if waiting else []},
        "mock": True, "brief": brief, "now": time.time(), "iso": datetime.datetime.now().isoformat(),
        "stamp": time.strftime("%Y-%m-%d %H:%M:%S"), "cwd": os.getcwd(), "argv": sys.argv[1:],
        "env": {name: os.environ.get(name) for name in WATCHED}, "env_names": sorted(os.environ),
        "bytecode": sys.dont_write_bytecode,
    }
    if brief and "BIG" in brief:
        out["pad"] = "x" * 5000
    return out


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else (body if isinstance(body, str) else json.dumps(body)).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        for key in (self.path, u.path):
            if key in BROKEN:
                return self._send(BROKEN[key], {"error": "broken on purpose"})
        if u.path == "/api/state":
            if RUN["brief"] is not None:
                RUN["polls"] += 1
            return self._send(200, state())
        if u.path in SIMPLE:
            return self._send(200, SIMPLE[u.path])
        if u.path == "/api/agent":
            return self._send(200, {"schema": "agent/1", "who": q.get("who", ""), "found": q.get("who") != "nobody"})
        if u.path == "/api/activity":
            return self._send(200, {"schema": "activity/1", "who": q.get("who", ""), "found": q.get("who") != "nobody", "events": []})
        if u.path == "/api/record":      # the Studio view's record of one part (sec) or one deliverable (art)
            known = {w["id"] for w in WORKFLOWS}
            if q.get("sec") in known:
                return self._send(200, {"schema": "studio/1", "sec": q["sec"], "name": "Part " + q["sec"]})
            if q.get("art") in ("Website", "Menu card"):
                return self._send(200, {"schema": "studio/1", "art": q["art"]})
            return self._send(404, {"error": "no such part"})
        if u.path.startswith("/doc/"):
            return self._send(200, "<p>This isn't written yet.</p>", "text/html")
        if u.path == "/view":
            return self._send(200, "<p>view of " + q.get("name", "") + "</p>", "text/html")
        if u.path == "/api/preview":
            known = {a["id"] for w in WORKFLOWS for a in w["atoms"]}
            return self._send(200, {"anchor": "a-1", "html": "<p>" + q["atom"] + "</p>"} if q.get("atom") in known else {"anchor": None, "html": None})
        if u.path == "/site/latest":
            return self._send(200, "<!doctype html><title>Stand-in</title><p>site</p>", "text/html")
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
        if self.path == "/__standin/break":
            BROKEN[body["path"]] = body["status"]
            return self._send(200, {"ok": True})
        if self.path == "/__standin/reset":
            RUN.update(brief=None, polls=0)
            BROKEN.clear()
            return self._send(200, {"ok": True})
        if self.path in BROKEN:
            return self._send(BROKEN[self.path], {"error": "broken on purpose"})
        if self.path == "/api/ask":      # a question to one function: answered from the records, as J2 does in mock mode
            if body.get("who") not in FUNCS:
                return self._send(400, {"error": "not a function"})
            return self._send(200, {"who": body["who"], "answer": "From the records: " + str(body.get("q")), "from": "records"})
        if self.path != "/api/say":
            return self._send(404, {"error": "not found"})
        brief = body.get("text", "")
        if "SAYFAIL" in brief:
            return self._send(500, {"error": "refused"})
        RUN["brief"] = brief
        if "STRAY" in brief:
            with open(os.path.join(HERE, "stray.txt"), "w", encoding="utf-8") as stray:
                stray.write("written by the stand-in")
        self._send(200, {"ok": True})
        if "DIE" in brief:
            sys.stdout.flush()
            os._exit(9)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8773)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    print(f"stand-in J2 on {args.port}", flush=True)
    http.server.ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
