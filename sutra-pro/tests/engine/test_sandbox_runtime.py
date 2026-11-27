"""The bundled srt (D462): which srt J2 launches (`llm.sandbox_cmd`), the sandbox status, and failing closed when the bundle can't start."""
import logging
import shlex
import subprocess
import sys

import pytest

from sutra_app.engine import llm


def fake_node(folder, version):
    """A python script that answers `-p process.versions.node` like node does."""
    p = folder / "node"
    p.write_text(f"#!{sys.executable}\nimport sys\nif sys.argv[1:] == ['-p', 'process.versions.node']:\n    print({version!r})\n")
    p.chmod(0o755)
    return p


@pytest.fixture
def live(monkeypatch, tmp_path):
    """darwin, live, J2_SANDBOX and J2_SANDBOX_CMD unset, PATH = only a fake-node folder, the node probe's cache empty."""
    for name in ("J2_SANDBOX", "J2_SANDBOX_CMD", "SUTRA_ELECTRON_NODE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(llm.sys, "platform", "darwin")
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    monkeypatch.setenv("PATH", str(bin_))
    llm._NODE_VERSIONS.clear()
    yield bin_
    llm._NODE_VERSIONS.clear()


@pytest.mark.parametrize("version", ["22.12.0", "24.22.1"])
def test_a_new_enough_node_runs_the_bundled_srt(live, version):
    node = fake_node(live, version)
    on, why = llm.sandbox_status(mock=False)
    assert on and why == f"bundled srt 0.0.83 at {llm.SRT_DIR}, node {version}"
    assert shlex.split(llm.sandbox_cmd()) == [str(node), str(llm.SRT_DIR / "srt.mjs")]


def test_an_old_node_keeps_the_sandbox_on_and_says_why(live):
    node = fake_node(live, "20.0.0")
    on, why = llm.sandbox_status(mock=False)
    assert on and "needs node >= 22.12 (found 20.0.0" in why and str(node) in why


def test_no_node_keeps_the_sandbox_on_and_says_why(live):
    on, why = llm.sandbox_status(mock=False)
    assert on and "no node on PATH" in why


def test_a_missing_bundle_keeps_the_sandbox_on_and_every_launch_is_refused(live, monkeypatch, tmp_path):
    """AC-6: on with the bundled folder in the reason; the command stands in for srt, prints why and exits 1."""
    fake_node(live, "24.22.1")
    empty = tmp_path / "no-bundle"
    empty.mkdir()
    monkeypatch.setattr(llm, "SRT_DIR", empty)
    on, why = llm.sandbox_status(mock=False)
    assert on and str(empty) in why
    argv = shlex.split(llm.sandbox_cmd())
    assert argv[:2] == [sys.executable, "-c"]
    done = subprocess.run(argv + ["-s", "x", "-c", "touch should-not-exist"], capture_output=True, text=True, cwd=tmp_path, timeout=30)
    assert done.returncode == 1 and str(empty) in done.stderr and "Restore it" in done.stderr
    assert not (tmp_path / "should-not-exist").exists()


def test_off_only_for_j2_sandbox_0_offline_and_windows(live, monkeypatch):
    fake_node(live, "24.22.1")
    assert llm.sandbox_status(mock=True)[0] is False
    monkeypatch.setenv("J2_SANDBOX", "0")
    assert llm.sandbox_status(mock=False) == (False, "J2_SANDBOX=0")
    monkeypatch.delenv("J2_SANDBOX")
    monkeypatch.setattr(llm.sys, "platform", "win32")
    assert llm.sandbox_status(mock=False)[0] is False


def test_the_app_runs_srt_on_electrons_node(live, tmp_path, monkeypatch):
    """AC-16, first part: SUTRA_ELECTRON_NODE puts `env ELECTRON_RUN_AS_NODE=1 <exe> <bundle>/srt.mjs` first."""
    exe = fake_node(tmp_path, "24.22.1")
    monkeypatch.setenv("SUTRA_ELECTRON_NODE", str(exe))
    assert shlex.split(llm.sandbox_cmd()) == ["env", "ELECTRON_RUN_AS_NODE=1", str(exe), str(llm.SRT_DIR / "srt.mjs")]
    assert llm.sandbox_status(mock=False) == (True, f"bundled srt 0.0.83 at {llm.SRT_DIR}, node 24.22.1")


def test_the_override_warns_on_every_launch(live, tmp_path, monkeypatch, caplog):
    """AC-15 (unit): one WARNING per sandbox_cmd() call naming the override's resolved path."""
    srt = live / "my-srt"
    srt.write_text("#!/bin/sh\n")
    srt.chmod(0o755)
    monkeypatch.setenv("J2_SANDBOX_CMD", "my-srt --debug")
    caplog.set_level(logging.WARNING, logger="sutra_app.engine.llm")
    for n in (1, 2):
        assert llm.sandbox_cmd() == "my-srt --debug"
        warnings = [r for r in caplog.records if r.name == "sutra_app.engine.llm" and r.levelno == logging.WARNING]
        assert len(warnings) == n and str(srt) in warnings[-1].getMessage()
    assert llm.sandbox_status(mock=False) == (True, f"J2_SANDBOX_CMD overrides the bundled srt: my-srt at {srt}")


def test_the_command_is_never_empty(live, monkeypatch, tmp_path):
    assert llm.sandbox_cmd()                     # no node
    fake_node(live, "20.0.0")
    llm._NODE_VERSIONS.clear()
    assert llm.sandbox_cmd()                     # old node
    monkeypatch.setattr(llm, "SRT_DIR", tmp_path / "gone")
    assert llm.sandbox_cmd()                     # no bundle


# ---- through the real bundled srt (macOS) and failing closed (every OS) ---------------------------------------------------
import gzip  # noqa: E402
import http.server  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import threading  # noqa: E402
from pathlib import Path  # noqa: E402

needs_bundled_srt = pytest.mark.skipif(sys.platform != "darwin" or llm.bundled_srt()[1] is not None,
                                       reason="needs macOS and the bundled srt (node >= 22.12)")
SIZES = (10_240, 51_200, 512_000)


class Body(http.server.BaseHTTPRequestHandler):
    """Made-up bytes: /plain/N (Content-Length), /chunked/N (4 KB chunks), /gzip/N (gzip of N random bytes, Content-Length = the
    compressed size); every response says Connection: close and the server closes right after the body."""
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_GET(self):
        kind, n = self.path.strip("/").split("/")[:2]
        n = int(n)
        body = os.urandom(n)
        self.send_response(200)
        self.send_header("Connection", "close")
        if kind == "chunked":
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            for i in range(0, n, 4096):
                self.wfile.write(b"%x\r\n%s\r\n" % (len(body[i:i + 4096]), body[i:i + 4096]))
            self.wfile.write(b"0\r\n\r\n")
        else:
            if kind == "gzip":
                body = gzip.compress(body)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        self.close_connection = True


@pytest.fixture
def server():
    s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Body)
    s.daemon_threads = True
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield s.server_port
    s.shutdown()
    s.server_close()


# Runs inside the sandbox: every case through srt's CONNECT proxy (HTTPS_PROXY), one JSON line each into argv[2]/result.jsonl.
CONNECT_CLIENT = r'''
import base64, http.client, json, os, sys, urllib.parse
port, out = int(sys.argv[1]), sys.argv[2]
px = urllib.parse.urlsplit(os.environ["HTTPS_PROXY"])
auth = {"Proxy-Authorization": "Basic " + base64.b64encode(
    (urllib.parse.unquote(px.username or "") + ":" + urllib.parse.unquote(px.password or "")).encode()).decode()} if px.username else {}
with open(os.path.join(out, "result.jsonl"), "w") as f:
    for kind in ("plain", "chunked", "gzip"):
        for n in map(int, sys.argv[3:]):
            c = http.client.HTTPConnection(px.hostname, px.port, timeout=30)
            c.set_tunnel("127.0.0.1", port, headers=auth)
            row = {"case": f"{kind}/{n}", "expected": n, "got": None, "error": None}
            try:
                c.request("GET", f"/{kind}/{n}", headers={"Connection": "close"})
                r = c.getresponse()
                if kind == "gzip":
                    row["expected"] = int(r.getheader("Content-Length"))
                row["got"] = len(r.read())
            except Exception as e:
                row["error"] = repr(e)[:200]
            f.write(json.dumps(row) + "\n")
'''

# Runs inside the sandbox: SOCKS5 (RFC 1928, user/password RFC 1929) to the proxy port in HTTPS_PROXY (srt's mux serves both).
SOCKS_CLIENT = r'''
import json, os, socket, struct, sys, urllib.parse
port, out, n = int(sys.argv[1]), sys.argv[2], int(sys.argv[3])
px = urllib.parse.urlsplit(os.environ["HTTPS_PROXY"])
u, p = urllib.parse.unquote(px.username or "").encode(), urllib.parse.unquote(px.password or "").encode()
s = socket.create_connection((px.hostname, px.port), timeout=30)
def take(k):
    b = b""
    while len(b) < k:
        c = s.recv(k - len(b))
        if not c:
            raise EOFError("proxy closed")
        b += c
    return b
s.sendall(b"\x05\x01\x02")
assert take(2) == b"\x05\x02"
s.sendall(b"\x01" + bytes([len(u)]) + u + bytes([len(p)]) + p)
assert take(2)[1] == 0, "socks auth refused"
s.sendall(b"\x05\x01\x00\x01" + socket.inet_aton("127.0.0.1") + struct.pack(">H", port))
reply = take(4)
assert reply[1] == 0, reply
take(6 if reply[3] == 1 else 18)
s.sendall(b"GET /plain/%d HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n" % n)
data = b""
while True:
    c = s.recv(65536)
    if not c:
        break
    data += c
head, _, body = data.partition(b"\r\n\r\n")
length = int([x.split(b":")[1] for x in head.split(b"\r\n") if x.lower().startswith(b"content-length:")][0])
json.dump({"expected": length, "got": len(body), "electron_flag": "ELECTRON_RUN_AS_NODE" in os.environ}, open(os.path.join(out, "socks.json"), "w"))
'''


@pytest.fixture(scope="module")
def j2(tmp_path_factory):
    from test_engine_patches import fresh_j2      # lazily: that module imports this one's skip rule
    with fresh_j2(tmp_path_factory.mktemp("j2-srt")) as mod:
        yield mod


@pytest.fixture
def real_srt(monkeypatch, tmp_path):
    """J2_SANDBOX=1, no override (the bundled srt), a temp HOME (srt denies reads under ~), a built folder and a writable folder."""
    monkeypatch.setenv("J2_SANDBOX", "1")
    for name in ("J2_SANDBOX_CMD", "SUTRA_ELECTRON_NODE"):
        monkeypatch.delenv(name, raising=False)
    home, out, folder = tmp_path / "home", tmp_path / "out", tmp_path / "folder"
    for d in (home, out, folder):
        d.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return out, folder


@needs_bundled_srt
def test_real_srt_delivers_whole_bodies_when_the_server_closes(j2, real_srt, server):
    """AC-1 (D462, S1): 10 KB, 50 KB and 500 KB, plain, chunked and gzip, each closed by the server after the body, all arrive whole
    through the real Sutra launch path (j2.real_run, the bundled srt's CONNECT tunnel). Stock srt 0.0.83 cuts every one."""
    out, folder = real_srt
    (out / "client.py").write_text(CONNECT_CLIENT)
    rr = {"command": [sys.executable, "client.py", str(server), str(folder), *map(str, SIZES)], "folder": str(folder), "hosts": ["127.0.0.1"]}
    res = j2.real_run(str(out), rr, 60)
    assert res["ran"] and res["exit"] == 0 and "in the sandbox" in res["evidence"], res
    rows = [json.loads(x) for x in (folder / "result.jsonl").read_text().splitlines()]
    assert len(rows) == 9 and [r for r in rows if r["error"] or r["got"] != r["expected"]] == [], rows


@needs_bundled_srt
def test_real_srt_socks_delivers_a_whole_body(j2, real_srt, server, monkeypatch):
    """AC-2 (S2) and AC-16's last part: SOCKS5 through the same proxy port, srt on node as the app starts it (`env
    ELECTRON_RUN_AS_NODE=1 <node> srt.mjs`); 500 KB arrives whole and the script never sees ELECTRON_RUN_AS_NODE."""
    out, folder = real_srt
    monkeypatch.setenv("SUTRA_ELECTRON_NODE", shutil.which("node"))
    assert shlex.split(llm.sandbox_cmd())[:2] == ["env", "ELECTRON_RUN_AS_NODE=1"]
    (out / "socks.py").write_text(SOCKS_CLIENT)
    rr = {"command": [sys.executable, "socks.py", str(server), str(folder), "512000"], "folder": str(folder), "hosts": ["127.0.0.1"]}
    res = j2.real_run(str(out), rr, 60)
    assert res["ran"] and res["exit"] == 0, res
    assert json.loads((folder / "socks.json").read_text()) == {"expected": 512000, "got": 512000, "electron_flag": False}


@needs_bundled_srt
def test_live_status_names_the_bundle(monkeypatch):
    """AC-7."""
    for name in ("J2_SANDBOX", "J2_SANDBOX_CMD", "SUTRA_ELECTRON_NODE"):
        monkeypatch.delenv(name, raising=False)
    on, why = llm.sandbox_status(mock=False)
    version = llm._node_version(shutil.which("node"))
    assert on and why == f"bundled srt 0.0.83 at {llm.SRT_DIR}, node {'.'.join(map(str, version))}"


def test_missing_bundle_fails_closed_with_the_sandbox_unset(j2, live, monkeypatch, tmp_path):
    """AC-19: no bundle, J2_SANDBOX and J2_SANDBOX_CMD unset, live: the real run, the test rerun and the install step each fail
    with the bundled path and "Restore it"; the plan's command never runs and an srt on PATH is never called."""
    monkeypatch.setattr(llm, "MOCK", False)
    fake_node(live, "24.22.1")
    marker = tmp_path / "path-srt.marker"
    (live / "srt").write_text(f"#!/bin/sh\ntouch {shlex.quote(str(marker))}\n")
    (live / "srt").chmod(0o755)
    monkeypatch.setenv("PATH", f"{live}{os.pathsep}/usr/bin{os.pathsep}/bin")
    empty = tmp_path / "no-bundle"
    empty.mkdir()
    monkeypatch.setattr(llm, "SRT_DIR", empty)
    assert llm.sandbox_status() == (True, f"the bundled sandbox runtime is missing at {empty}") and j2.sandbox_on()
    out, folder = tmp_path / "out", tmp_path / "folder"
    out.mkdir()
    folder.mkdir()
    (out / "mark.py").write_text("import sys, pathlib\npathlib.Path(sys.argv[1], 'ran.marker').write_text('1')\n")
    (out / "test_ok.py").write_text("pass\n")
    res = j2.real_run(str(out), {"command": [sys.executable, "mark.py", str(folder)], "folder": str(folder)}, 30)
    assert res["exit"] not in (0, None) and str(empty) in res["output"] and "Restore it" in res["output"], res
    rerun = j2.sandbox_rerun(str(out), [sys.executable, "{target}"], "test_ok.py", 30)
    assert rerun["pass"] is not True and str(empty) in rerun["output"] and "Restore it" in rerun["output"], rerun
    (out / "requirements.txt").write_text("pulsedep==1.2.0\n")
    plan = {"dir": str(tmp_path / "envs" / "e1"), "requirements": str(out / "requirements.txt"),
            "base": {"python": sys.executable, "base": sys.prefix}}
    got = j2.j2_runenv.install(plan, 120, llm.sandbox_cmd(), env=llm.run_env())      # as j2's _env_install calls it (P42, P47)
    assert got["ok"] is False and got["exit"] == 1 and str(empty) in got["stderr"] and "Restore it" in got["stderr"], got
    assert not marker.exists() and not (folder / "ran.marker").exists()


def test_override_warns_once_per_launch(j2, live, monkeypatch, tmp_path, caplog):
    """AC-15: J2_SANDBOX=1 and J2_SANDBOX_CMD = a fake srt: one real run, exactly one WARNING naming it, and the fake ran."""
    fake = live / "fake-srt"
    fake.write_text(f"#!{sys.executable}\nimport shlex, subprocess, sys\na = sys.argv[1:]\nopen(sys.argv[0] + '.ran', 'w').write('1')\n"
                    "sys.exit(subprocess.run(shlex.split(a[a.index('-c') + 1])).returncode)\n")
    fake.chmod(0o755)
    monkeypatch.setenv("J2_SANDBOX", "1")
    monkeypatch.setenv("J2_SANDBOX_CMD", str(fake))
    out, folder = tmp_path / "out", tmp_path / "folder"
    out.mkdir()
    folder.mkdir()
    (out / "ok.py").write_text("pass\n")
    caplog.set_level(logging.WARNING, logger="sutra_app.engine.llm")
    res = j2.real_run(str(out), {"command": [sys.executable, "ok.py"], "folder": str(folder)}, 30)
    assert res["exit"] == 0, res
    warnings = [r.getMessage() for r in caplog.records if r.name == "sutra_app.engine.llm" and r.levelno == logging.WARNING]
    assert len(warnings) == 1 and str(fake) in warnings[0], warnings
    assert Path(str(fake) + ".ran").exists()


FLUSH = Path(__file__).resolve().parent / "fixtures" / "srt_close_flush.mjs"


@pytest.mark.skipif(sys.platform.startswith("win") or llm.bundled_srt()[1] is not None, reason="needs the bundled srt (node >= 22.12)")
def test_bundled_proxies_flush_a_slow_readers_stream_after_the_origin_closes():
    """S1 and S2 (D462), by upstream PR #377's method: 1 MiB of made-up bytes, the origin closes right after writing, the client
    drains 16 KiB every 2 ms over a Unix domain socket (small fixed kernel buffers keep the queue in srt's userspace, where a
    destroy() drops it), 6 transfers each through the bundled CONNECT proxy and SOCKS5 relay. Stock 0.0.83 loses 64 KiB of
    every transfer on both paths."""
    import tempfile
    socks_dir = tempfile.mkdtemp(prefix="srtf", dir="/tmp" if os.path.isdir("/tmp") else None)      # a Unix socket path must be short
    try:
        done = subprocess.run(["node", str(FLUSH), str(llm.SRT_DIR / llm.SRT_PACKAGE / "dist"), socks_dir, "6"],
                              capture_output=True, text=True, timeout=60)
    finally:
        shutil.rmtree(socks_dir, ignore_errors=True)
    assert done.returncode == 0, done.stderr
    got = json.loads(done.stdout)
    assert got["connect"] == [1 << 20] * 6 and got["socks"] == [1 << 20] * 6, got


def test_windows_refuses_every_launch_and_never_runs_the_app_as_node(monkeypatch, tmp_path):
    """Review R1-1: on Windows with J2_SANDBOX=1 forced, srt's sandbox can't run; the command is the refusal (never the app's own
    executable from SUTRA_ELECTRON_NODE, never PATH node), and the status says so."""
    monkeypatch.setattr(llm.sys, "platform", "win32")
    monkeypatch.setenv("J2_SANDBOX", "1")
    monkeypatch.delenv("J2_SANDBOX_CMD", raising=False)
    monkeypatch.setenv("SUTRA_ELECTRON_NODE", str(tmp_path / "Sutra Pro.exe"))
    argv = shlex.split(llm.sandbox_cmd())
    assert argv[:2] == [sys.executable, "-c"] and "Sutra Pro.exe" not in " ".join(argv)
    assert "does not run on Windows" in argv[-1] and "J2_SANDBOX=0" in argv[-1]
    done = subprocess.run(argv + ["-s", "x", "-c", "touch should-not-exist"], capture_output=True, text=True, cwd=tmp_path, timeout=30)
    assert done.returncode == 1 and "does not run on Windows" in done.stderr and not (tmp_path / "should-not-exist").exists()
    assert llm.sandbox_status(mock=False) == (True, "J2_SANDBOX=1 (srt's sandbox does not run on Windows: every sandboxed launch is refused)")
    monkeypatch.delenv("J2_SANDBOX")
    assert llm.sandbox_status(mock=False) == (False, "not on win32: srt's sandbox does not run on Windows")


def test_a_failed_node_probe_is_tried_again(live):
    """Review R1-4: only a successful probe is kept, so one slow or broken first probe does not refuse every launch until restart."""
    node = live / "node"
    node.write_text("#!/bin/sh\nexit 1\n")
    node.chmod(0o755)
    assert "found no version" in llm.sandbox_status(mock=False)[1]
    fake_node(live, "24.22.1")
    assert llm.sandbox_status(mock=False)[1].endswith("node 24.22.1")
