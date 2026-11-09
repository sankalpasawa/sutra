"""backend-checks/1: code's checks of a run's generated backend (J2_BACKEND=1; docs/backend-design.md, section 4).

The backend is one file, runs/<id>/site/server.py, standard library only, serving index.html and a JSON API on
127.0.0.1 with a SQLite file. Code never trusts it: before it is started the file is compiled (backend-compile) and
scanned (backend-safety: only an allowlist of imports, no subprocess / eval / sockets / outgoing HTTP, no file
writes but its own database, a literal 127.0.0.1 bind); then it is started on a free port, in the run folder,
under `python -I` with an environment built from scratch (backend-start), each LLD endpoint is called with its
example request (backend-endpoint), the built page's /api/ calls are compared with the LLD (page-calls-known-
endpoints), the form is filled and submitted in headless Chrome through a same-origin proxy and the booking is
read back from the list endpoint (backend-e2e), and the run folder is compared before and after so nothing but
the database was written (backend-files, which also stops the server).

Every check answers {"actual", "pass", "evidence"} like j2.run_check's own, so each is one receipt line; pass is
None only when the check could not run (no Chrome), never for a failure of the build. One server at a time per
run folder; stop() always ends it. Python 3.9.
"""
import ast
import hashlib
import http.server
import json
import os
import py_compile
import re
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import j2_check

SCHEMA = "backend-checks/1"
CHECK_TYPES = ("backend-compile", "backend-safety", "backend-start", "backend-endpoint", "page-calls-known-endpoints",
               "backend-e2e", "backend-files")
START_TIMEOUT = 10      # seconds for the server to answer GET /
REQUEST_TIMEOUT = 5     # seconds per endpoint request
STOP_TIMEOUT = 3        # seconds between SIGTERM and SIGKILL
SCRIPT = "site/server.py"
INDEX = "site/index.html"
# The imports a server may make. Exact names: "import urllib" alone is refused (its request module is outgoing HTTP),
# "import urllib.parse" is allowed.
ALLOWED_IMPORTS = {"http", "http.server", "socketserver", "sqlite3", "json", "urllib.parse", "argparse", "os",
                   "os.path", "sys", "datetime", "time", "re", "html", "pathlib", "logging", "typing", "functools",
                   "collections", "uuid", "threading"}
BLOCKED_NAMES = {"eval", "exec", "compile", "__import__", "getattr", "globals", "locals", "vars", "breakpoint",
                 "subprocess", "socket", "ctypes", "importlib", "shutil", "requests"}
BLOCKED_DOTTED = {"os.system", "os.popen", "os.remove", "os.unlink", "os.rename", "os.replace", "os.rmdir",
                  "os.removedirs", "os.truncate", "os.chmod", "os.chown", "os.kill", "os.fork", "os.makedirs",
                  "os.mkdir", "os.symlink", "os.link", "os.environ", "os.putenv", "urllib.request", "http.client",
                  "sys.modules", "sys.path"}
BLOCKED_PREFIXES = ("os.exec", "os.spawn", "os.posix_spawn", "shutil.", "subprocess.", "socket.", "urllib.request.",
                    "http.client.", "ctypes.", "importlib.")
SERVER_CLASSES = ("HTTPServer", "ThreadingHTTPServer", "TCPServer", "ThreadingTCPServer")
WRITE_MODES = re.compile(r"[wax+]")
DB_SUFFIXES = ("", "-journal", "-wal", "-shm")
BASE_ENV = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
            "PYTHONIOENCODING": "utf-8"}

_LIVE = {}        # run folder -> the running server (one at a time)
_SAFE = {}        # run folder -> sha256 of the last file that passed backend-safety
_ATTEMPTS = {}    # run folder -> starts so far (names the log and database when the check has no attempt number)


def enabled():
    """J2_BACKEND=1 (default off). Read per call so tests can switch it."""
    return os.environ.get("J2_BACKEND") == "1"


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _res(ok, evidence, actual=None):
    return {"actual": ok if actual is None else actual, "pass": ok, "evidence": evidence}


# ---------------------------------------------------------------- backend-compile
def compile_check(path):
    """py_compile of the file, its bytecode thrown away. Fails with the SyntaxError's own file, line and message."""
    if not os.path.isfile(path):
        return _res(False, f"{os.path.basename(path)} not found in the run")
    with tempfile.TemporaryDirectory(prefix="j2-pyc-") as tmp:
        try:
            py_compile.compile(path, cfile=os.path.join(tmp, "server.pyc"), doraise=True)
        except py_compile.PyCompileError as e:
            exc = e.exc_value
            line = getattr(exc, "lineno", None)
            msg = getattr(exc, "msg", None) or str(exc).splitlines()[0]
            return _res(False, f"{e.exc_type_name}: {os.path.basename(path)}:{line}: {msg}")
    return _res(True, f"{os.path.basename(path)} compiles")


# ---------------------------------------------------------------- backend-safety
def _dotted(node):
    """"os.system" for an Attribute chain that ends in a Name; None otherwise."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _blocked_dotted(name):
    return name in BLOCKED_DOTTED or any(name.startswith(p) for p in BLOCKED_PREFIXES) \
        or name.split(".")[0] in BLOCKED_NAMES


def _literal(node):
    return node.value if isinstance(node, ast.Constant) else None


def safety_problems(src, name="server.py"):
    """Every line of the source that the server may not have (empty when it is clean). Static, one AST walk."""
    try:
        tree = ast.parse(src, name)
    except SyntaxError as e:
        return [f"line {e.lineno}: the file does not parse ({e.msg})"]
    out, servers = [], 0
    for node in ast.walk(tree):
        ln = getattr(node, "lineno", "?")
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name not in ALLOWED_IMPORTS:
                    out.append(f"line {ln}: import {a.name} is not allowed; allowed: "
                               + ", ".join(sorted(ALLOWED_IMPORTS)))
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level:
                out.append(f"line {ln}: a relative import is not allowed (one file, standard library only)")
                continue
            for a in node.names:
                full = f"{mod}.{a.name}"
                if not (full in ALLOWED_IMPORTS or (mod in ALLOWED_IMPORTS and not _blocked_dotted(full))):
                    out.append(f"line {ln}: from {mod} import {a.name} is not allowed")
        elif isinstance(node, ast.Name) and node.id in BLOCKED_NAMES:
            out.append(f"line {ln}: {node.id} is not allowed")
        elif isinstance(node, ast.Attribute):
            d = _dotted(node)
            if d and (d in BLOCKED_DOTTED or any(d.startswith(p) for p in BLOCKED_PREFIXES)):
                out.append(f"line {ln}: {d} is not allowed")
        elif isinstance(node, ast.Constant) and node.value == "0.0.0.0":
            out.append(f"line {ln}: \"0.0.0.0\" binds every interface; the server must bind 127.0.0.1 only")
        if isinstance(node, ast.Call):
            fn = _dotted(node.func) if isinstance(node.func, ast.Attribute) else \
                node.func.id if isinstance(node.func, ast.Name) else None
            if fn == "open":
                mode = node.args[1] if len(node.args) > 1 else next((k.value for k in node.keywords
                                                                     if k.arg == "mode"), None)
                m = _literal(mode)
                if mode is not None and (not isinstance(m, str) or WRITE_MODES.search(m)):
                    out.append(f"line {ln}: open(..., {m!r}) writes a file; only the sqlite database may be written"
                               if isinstance(m, str) else f"line {ln}: open() needs a literal read mode")
            if fn in ("sqlite3.connect", "connect"):
                p = _literal(node.args[0]) if node.args else None
                if isinstance(p, str) and (os.path.isabs(p) or ".." in p.split("/") or ".." in p.split(os.sep)):
                    out.append(f"line {ln}: sqlite3.connect({p!r}) points outside the run folder")
            if fn and fn.split(".")[-1].endswith("Server"):
                servers += 1
                addr = node.args[0] if node.args else None
                host = _literal(addr.elts[0]) if isinstance(addr, ast.Tuple) and addr.elts else None
                if not isinstance(addr, ast.Tuple) or host is None:
                    out.append(f"line {ln}: the server address must be the literal (\"127.0.0.1\", port)")
                elif host not in ("127.0.0.1", "localhost"):
                    out.append(f"line {ln}: the server binds {host!r}; it must bind 127.0.0.1 only")
    if not servers:
        out.append("no HTTPServer, ThreadingHTTPServer or TCPServer is constructed, so there is nothing to start")
    return list(dict.fromkeys(out))


def safety_check(path, run_dir=None):
    """The scan as a check; a clean file is remembered (by sha) so backend-start may run it."""
    if not os.path.isfile(path):
        return _res(False, f"{os.path.basename(path)} not found in the run")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    bad = safety_problems(src, os.path.basename(path))
    if bad:
        _SAFE.pop(run_dir, None)
        return _res(False, "; ".join(bad)[:1200], actual=bad)
    if run_dir:
        _SAFE[run_dir] = _sha(path)
    return _res(True, "standard-library imports only; no subprocess, eval, exec, socket or outgoing HTTP; no file "
                      "write but the database; binds 127.0.0.1", actual=[])


# ---------------------------------------------------------------- backend-start / backend-files
def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _listing(run_dir):
    out = set()
    for root, _, files in os.walk(run_dir):
        for f in files:
            out.add(os.path.relpath(os.path.join(root, f), run_dir))
    return out


def _tail(path, n=5):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = [x.rstrip() for x in f.read().splitlines() if x.strip()]
    except OSError:
        return ""
    return " | ".join(lines[-n:])


def _get(url, timeout=REQUEST_TIMEOUT):
    """(status, body bytes) of a GET; (None, reason) when nothing answered."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, socket.timeout, ConnectionError, OSError) as e:
        return None, str(getattr(e, "reason", e))


def _lan_ip():
    """The machine's outbound address, to prove the server does not answer there; None when unknown."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return None if ip.startswith("127.") else ip
    except OSError:
        return None


def start_check(run_dir, script=SCRIPT, attempt=None, index=INDEX):
    """Start the server on a free port: `python -I <script> --port P --db backend/check-<n>.sqlite`, cwd the run
    folder, an environment built from scratch, stdout and stderr to backend/start-<n>.log. Passes when GET / answers
    200 with index.html's bytes within START_TIMEOUT and nothing answers on the machine's other address. The server
    stays up for the endpoint and e2e checks; backend-files (or stop) ends it."""
    stop(run_dir)
    path = os.path.join(run_dir, script)
    if not os.path.isfile(path):
        return _res(False, f"{script} not found in the run")
    if _SAFE.get(run_dir) != _sha(path):
        return _res(False, f"not started: backend-safety has not passed for this {os.path.basename(script)}")
    n = attempt or _ATTEMPTS.get(run_dir, 0) + 1
    _ATTEMPTS[run_dir] = n
    os.makedirs(os.path.join(run_dir, "backend"), exist_ok=True)
    db, log = f"backend/check-{n}.sqlite", f"backend/start-{n}.log"
    for suf in DB_SUFFIXES:
        try:
            os.remove(os.path.join(run_dir, db + suf))
        except OSError:
            pass
    before = _listing(run_dir) | {log}
    port = free_port()
    env = {**BASE_ENV, "HOME": os.path.join(run_dir, "backend")}
    logf = open(os.path.join(run_dir, log), "w", encoding="utf-8")
    t0 = time.time()
    try:
        proc = subprocess.Popen([sys.executable, "-I", script, "--port", str(port), "--db", db], cwd=run_dir, env=env,
                                stdin=subprocess.DEVNULL, stdout=logf, stderr=subprocess.STDOUT, start_new_session=True)
    except OSError as e:
        logf.close()
        return _res(False, f"could not start {script}: {e}")
    handle = {"proc": proc, "port": port, "pid": proc.pid, "log": log, "db": db, "before": before, "attempt": n,
              "logf": logf, "script": script}
    url = f"http://127.0.0.1:{port}/"
    status, body = None, b""
    while time.time() - t0 < START_TIMEOUT:
        if proc.poll() is not None:
            _end(handle)
            return _res(False, f"{script} exited with code {proc.returncode} before answering on 127.0.0.1:{port}"
                               + (f"; its log: {_tail(os.path.join(run_dir, log))}" if _tail(os.path.join(run_dir, log))
                                  else ""), actual={"port": port, "exit": proc.returncode, "log": log})
        status, body = _get(url, timeout=2)
        if status is not None:
            break
        time.sleep(0.2)
    secs = round(time.time() - t0, 2)
    if status is None:
        _end(handle)
        return _res(False, f"the server did not answer on 127.0.0.1:{port} within {START_TIMEOUT} s"
                           + (f"; its log: {_tail(os.path.join(run_dir, log))}" if _tail(os.path.join(run_dir, log))
                              else ""), actual={"port": port, "log": log, "seconds": secs})
    _LIVE[run_dir] = handle
    actual = {"port": port, "pid": proc.pid, "seconds": secs, "log": log, "db": db, "status": status}
    want = None
    try:
        with open(os.path.join(run_dir, index), "rb") as f:
            want = f.read()
    except OSError:
        pass
    if status != 200:
        return _res(False, f"GET / answered {status}, not 200, after {secs} s on 127.0.0.1:{port}", actual=actual)
    if want is not None and body != want:
        return _res(False, f"GET / answered 200 with {len(body)} bytes that are not {index} ({len(want)} bytes)",
                    actual=actual)
    ip = _lan_ip()
    if ip:
        try:
            socket.create_connection((ip, port), timeout=1).close()
            return _res(False, f"the server answers on {ip}:{port} too; it must bind 127.0.0.1 only", actual=actual)
        except OSError:
            pass
    return _res(True, f"answered GET / with {index} in {secs} s on 127.0.0.1:{port} (pid {proc.pid}, log {log})",
                actual=actual)


def _end(handle):
    """SIGTERM the server's process group, SIGKILL after STOP_TIMEOUT; close its log."""
    proc = handle["proc"]
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except OSError:
            proc.terminate()
        try:
            proc.wait(timeout=STOP_TIMEOUT)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                proc.kill()
            proc.wait()
    try:
        handle["logf"].close()
    except OSError:
        pass


def stop(run_dir):
    """End the run folder's server if one is up. Returns its handle (with the files it added), or None."""
    handle = _LIVE.pop(run_dir, None)
    if not handle:
        return None
    _end(handle)
    allowed = {handle["db"] + s for s in DB_SUFFIXES} | {handle["log"]}
    handle["new_files"] = sorted(_listing(run_dir) - handle["before"] - allowed)
    return handle


def stop_all():
    for d in list(_LIVE):
        stop(d)


def files_check(run_dir):
    """Stop the server and compare the run folder with its state before the start: the only new files may be the
    check's database (and its journal). Fails naming every other file."""
    handle = stop(run_dir)
    if handle is None:
        return _res(False, "the server was not running (backend-start did not pass), so nothing to compare")
    new = handle["new_files"]
    if new:
        return _res(False, f"the server wrote {', '.join(new[:8])} outside its database {handle['db']}", actual=new)
    return _res(True, f"no file written but {handle['db']}; server stopped (pid {handle['pid']})", actual=[])


# ---------------------------------------------------------------- backend-endpoint
def _request(port, method, path, body=None, timeout=REQUEST_TIMEOUT):
    """(status, bytes, seconds) or (None, reason, seconds)."""
    url = f"http://127.0.0.1:{port}{path}"
    data = body.encode("utf-8") if isinstance(body, str) else body
    req = urllib.request.Request(url, data=data if method in ("POST", "PUT", "PATCH", "DELETE") else None,
                                 method=method, headers={"Content-Type": "application/json"} if data else {})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), round(time.time() - t0, 2)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), round(time.time() - t0, 2)
    except (urllib.error.URLError, socket.timeout, ConnectionError, OSError) as e:
        return None, str(getattr(e, "reason", e)), round(time.time() - t0, 2)


def _rows(obj):
    """The list a reply carries: the reply itself, or the first list value of an object."""
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        return next((v for v in obj.values() if isinstance(v, list)), None)
    return None


def endpoint_check(run_dir, ep):
    """One LLD endpoint: its example request with its method and path; passes on the expected status and every
    expected field in the JSON reply (for a list, in its first item)."""
    handle = _LIVE.get(run_dir)
    eid, method, path = ep.get("id") or "?", str(ep.get("method") or "GET").upper(), str(ep.get("path") or "")
    label = f"{eid} {method} {path}"
    if not handle:
        return _res(False, f"{label}: the server is not running (backend-start did not pass)")
    if not path.startswith("/api/"):
        return _res(False, f"{label}: the path does not start with /api/")
    want = int(ep.get("expected_status") or 200)
    fields = [str(x) for x in ep.get("expected_fields") or []]
    body = ep.get("example_request") or ""
    status, raw, secs = _request(handle["port"], method, path, body if method != "GET" else None)
    actual = {"status": status, "seconds": secs}
    if status is None:
        return _res(False, f"{label}: no reply within {REQUEST_TIMEOUT} s ({raw})", actual=actual)
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
    actual["body"] = text[:300]
    if status != want:
        return _res(False, f"{label}: expected {want}, got {status}; body: {text[:200]!r}", actual=actual)
    try:
        reply = json.loads(text or "null")
    except ValueError:
        return _res(False, f"{label}: {status} but the reply is not JSON: {text[:120]!r}", actual=actual)
    rows = _rows(reply)
    item = reply if isinstance(reply, dict) and rows is None else (rows[0] if rows else None)
    if fields and isinstance(item, dict):
        missing = [f for f in fields if f not in item]
        if missing:
            return _res(False, f"{label}: {status} but the reply lacks fields: {', '.join(missing)}", actual=actual)
    elif fields and rows is not None and not rows:
        return _res(True, f"{label}: {status} in {secs} s; the list is empty, so its item fields were not checked",
                    actual=actual)
    elif fields:
        return _res(False, f"{label}: {status} but the reply is not an object with fields {', '.join(fields)}",
                    actual=actual)
    return _res(True, f"{label}: {status} in {secs} s" + (f" with {', '.join(fields)}" if fields else ""),
                actual=actual)


# ---------------------------------------------------------------- page-calls-known-endpoints
API_CALLS = (re.compile(r"""action\s*=\s*["'](/api/[^"'\s]*)["']""", re.I),
             re.compile(r"""fetch\s*\(\s*[`"'](/api/[^`"'\s]*)[`"']""", re.I),
             re.compile(r"""\.open\s*\(\s*["']\w+["']\s*,\s*["'](/api/[^"'\s]*)["']""", re.I))


def page_calls(page):
    """Every /api/ path the page's markup and script name (action=, fetch(, XMLHttpRequest.open), query dropped."""
    hits = [(m.start(), m.group(1).split("?")[0]) for rx in API_CALLS for m in rx.finditer(page or "")]
    return [p for _, p in sorted(hits)]


def page_calls_check(page, endpoints):
    """Every /api/ path the page calls is an LLD endpoint's path, and the page calls at least one."""
    known = {str(e.get("path") or "") for e in endpoints or []}
    calls = page_calls(page)
    if not calls:
        return _res(False, "the page calls no /api/ path (no action=, fetch( or open( names one)", actual=[])
    bad = sorted({c for c in calls if c not in known})
    if bad:
        return _res(False, f"the page calls {', '.join(bad)}, which no LLD endpoint has", actual=sorted(set(calls)))
    return _res(True, f"the page calls {', '.join(sorted(set(calls)))} ({len(calls)} place(s)), every one an LLD "
                      "endpoint", actual=sorted(set(calls)))


# ---------------------------------------------------------------- backend-e2e
class _Proxy(http.server.SimpleHTTPRequestHandler):
    """Serves the behaviour wrapper and the page from a folder, and forwards /api/* to the backend's port, so the
    wrapper's iframe is same-origin with the page and the page's fetch() reaches the server."""
    backend_port = None
    root = None

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=self.root, **kw)

    def log_message(self, *a):
        pass

    def _forward(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else None
        req = urllib.request.Request(f"http://127.0.0.1:{self.backend_port}{self.path}", data=body,
                                     method=self.command,
                                     headers={"Content-Type": self.headers.get("Content-Type") or "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as r:
                status, ctype, out = r.status, r.headers.get("Content-Type") or "application/json", r.read()
        except urllib.error.HTTPError as e:
            status, ctype, out = e.code, e.headers.get("Content-Type") or "application/json", e.read()
        except (urllib.error.URLError, socket.timeout, OSError) as e:
            status, ctype, out = 502, "application/json", json.dumps({"error": str(e)}).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._forward()
        return super().do_GET()

    def do_POST(self):
        return self._forward()

    do_PUT = do_DELETE = do_PATCH = do_POST


def default_value(field, page, form):
    """A test value for one form field, from its type; a select takes its first real option (from the page)."""
    t, name = str(field.get("type") or "text").lower(), str(field.get("name") or "")
    if t == "select":
        sel = re.search(rf"""<select\b[^>]*\bname=["']{re.escape(name)}["'][^>]*>(.*?)</select>""", page or "",
                        re.I | re.S)
        for m in re.finditer(r"""<option\b([^>]*)>(.*?)</option>""", sel.group(1) if sel else "", re.I | re.S):
            v = re.search(r"""value=["']([^"']*)["']""", m.group(1), re.I)
            val = v.group(1) if v else re.sub(r"<[^>]+>", "", m.group(2)).strip()
            if val.strip():
                return val.strip()
        return "not recorded"
    if t == "email":
        return "test@stillpoint.example"
    if t == "date":
        return time.strftime("%Y-%m-%d", time.localtime(time.time() + 7 * 86400))
    if t == "time":
        return "09:00"
    if t == "number":
        return "1"
    if t == "tel":
        return "+91 00000 00000"
    if t == "checkbox":
        return "yes"
    if t == "url":
        return "https://example.com"
    return "Test Person"


def e2e_check(run_dir, page, form, fields, list_endpoint, confirm=None, values=None):
    """Fill the form in headless Chrome (through the proxy, so fetch() reaches the server), submit, then read the
    list endpoint and look for the row with the typed values. form: the form's selector; fields: [{name, type,
    request_name?}]; list_endpoint: {method, path}; confirm: a selector that must be visible after the submit."""
    handle = _LIVE.get(run_dir)
    if not handle:
        return _res(False, "the server is not running (backend-start did not pass)")
    if not j2_check.find_chrome():
        return {"actual": None, "pass": None, "evidence": "could not run: Chrome not found (set J2_CHROME)"}
    typed, steps = {}, []
    for f in fields or []:
        name = str(f.get("name") or "")
        if not name:
            continue
        val = str((values or {}).get(name) or default_value(f, page, form))
        typed[str(f.get("request_name") or name)] = val
        steps.append(f"set {form} [name={name}] {val}")
    steps.append(f"click {form} [type=submit]")
    steps.append("wait 1")
    if confirm:
        steps.append(f"expect-visible {confirm}")
    ops = j2_check.compile_steps(steps)[0]
    servers = []

    def serve(folder):
        cls = type("Proxy", (_Proxy,), {"backend_port": handle["port"], "root": folder})
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), cls)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)
        return f"http://127.0.0.1:{srv.server_address[1]}/wrap.html"
    try:
        r = j2_check.behavior(page, ops, serve=serve)
    finally:
        for s in servers:
            s.shutdown()
            s.server_close()
    if not r.get("available"):
        return {"actual": None, "pass": None, "evidence": f"could not run: {r.get('note')}"}
    verdict = j2_check.judge_steps(steps, r["results"])
    if not verdict["pass"]:
        return _res(False, f"the form did not submit in the browser: {verdict['evidence']}", actual=verdict["actual"])
    method, path = str((list_endpoint or {}).get("method") or "GET").upper(), str((list_endpoint or {}).get("path") or "")
    status, raw, secs = _request(handle["port"], method, path)
    if status is None:
        return _res(False, f"after the submit, {method} {path} gave no reply ({raw})")
    try:
        rows = _rows(json.loads(raw.decode("utf-8", "replace")))
    except ValueError:
        rows = None
    if rows is None:
        return _res(False, f"after the submit, {method} {path} answered {status} without a list")
    hit = next((row for row in rows if isinstance(row, dict)
                and all(str(row.get(k, "")).strip() == v for k, v in typed.items() if k in row)
                and any(k in row for k in typed)), None)
    if not hit:
        return _res(False, f"{method} {path} returned {len(rows)} row(s), none with {json.dumps(typed)}",
                    actual={"rows": len(rows), "typed": typed})
    return _res(True, f"the form submitted in the browser and {method} {path} returned the booking "
                      f"{json.dumps({k: hit.get(k) for k in typed})} ({len(rows)} row(s))",
                actual={"rows": len(rows), "typed": typed, "row": hit})


# ---------------------------------------------------------------- the dispatcher j2.run_check calls
def check(c, run_dir, page):
    """One backend check from a verification entry: type, target (the script, or an endpoint id), spec (the
    endpoint, the endpoints, or the e2e form)."""
    t, spec = c.get("type"), c.get("spec") or {}
    script = c.get("target") if t in ("backend-compile", "backend-safety", "backend-start") and c.get("target") \
        else SCRIPT
    path = os.path.join(run_dir, script)
    if t == "backend-compile":
        return compile_check(path)
    if t == "backend-safety":
        return safety_check(path, run_dir)
    if t == "backend-start":
        return start_check(run_dir, script, attempt=c.get("attempt"))
    if t == "backend-endpoint":
        return endpoint_check(run_dir, spec)
    if t == "page-calls-known-endpoints":
        return page_calls_check(page, spec if isinstance(spec, list) else spec.get("endpoints") or [])
    if t == "backend-e2e":
        return e2e_check(run_dir, page, spec.get("form") or "form", spec.get("fields") or [],
                         spec.get("list_endpoint") or {}, spec.get("confirm"), spec.get("values"))
    if t == "backend-files":
        return files_check(run_dir)
    return _res(False, f"unknown backend check {t!r}")
