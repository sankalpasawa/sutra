"""Scenario 6 (GAP-E2E, G05): `python -m sutra_app --offline --no-browser --port 0` as the owner's terminal would start it.

A real child process on a temp data folder (`SUTRA_DATA_DIR`), no token given (the server makes one and puts it into the pages): the
health route answers, `GET /` serves the Home page under a Content-Security-Policy, a chat message posts with the token the page
carries (and is refused without it), a team gets a task so an engine process exists, and SIGTERM ends the server inside 15 s with
no engine process left behind.
"""
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest
from harness import REPO, dept_change_payload, pid_alive

STOP_WITHIN_S = 15


class Server:
    """The child process, its stdout read by a thread (so the pipe never fills) and a few HTTP helpers."""

    def __init__(self, data_dir) -> None:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("SUTRA_", "J2_", "STUDIO_"))}
        env.update({"SUTRA_DATA_DIR": str(data_dir), "SUTRA_ENV_FILE": str(data_dir.parent / "none.env"), "SUTRA_HEARTBEAT_S": "0.5"})
        self.lines: list[str] = []
        self.proc = subprocess.Popen([sys.executable, "-m", "sutra_app", "--offline", "--no-browser", "--port", "0"], cwd=str(REPO), env=env,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
        threading.Thread(target=self._read, daemon=True).start()
        self.base = self._wait_for_url()
        self.token = ""

    def _read(self) -> None:
        for line in self.proc.stdout:
            self.lines.append(line.rstrip())

    def _wait_for_url(self) -> str:
        end = time.time() + 60
        while time.time() < end:
            for line in self.lines:
                found = re.search(r"running at (http://127\.0\.0\.1:\d+)/", line)
                if found:
                    return found.group(1)
            if self.proc.poll() is not None:
                pytest.fail("the server exited early:\n" + "\n".join(self.lines))
            time.sleep(0.05)
        pytest.fail("the server did not announce its address:\n" + "\n".join(self.lines))

    def request(self, method: str, path: str, body: dict | None = None, token: bool = True):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if token and self.token:
            req.add_header("X-Sutra-Token", self.token)
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                return response.status, {k.lower(): v for k, v in response.headers.items()}, response.read().decode()
        except urllib.error.HTTPError as exc:
            return exc.code, {k.lower(): v for k, v in exc.headers.items()}, exc.read().decode()

    def json(self, path: str):
        status, _, text = self.request("GET", path)
        assert status == 200, text
        return json.loads(text)

    def stop(self) -> int:
        self.proc.send_signal(signal.SIGTERM)
        return self.proc.wait(timeout=STOP_WITHIN_S)


@pytest.fixture
def server(tmp_path):
    data = tmp_path / "data"
    box = Server(data)
    box.data = data
    yield box
    if box.proc.poll() is None:
        os.killpg(box.proc.pid, signal.SIGKILL)
        box.proc.wait()
    box.proc.stdout.close()


def engine_pids(data) -> list[int]:
    out = subprocess.run(["ps", "-A", "-o", "pid=,command="], capture_output=True, text=True).stdout
    return [int(line.split(None, 1)[0]) for line in out.splitlines() if f"--run-dir {data}" in line]


def test_the_cli_serves_health_the_home_page_and_one_message_and_stops_on_sigterm_leaving_no_child(server):
    # --- health, before anything else
    end = time.time() + 30
    while True:
        try:
            health = server.json("/api/health")
            break
        except (OSError, AssertionError):
            assert time.time() < end
            time.sleep(0.1)
    assert health["ok"] is True and health["schema"] == 1 and set(health["connectors"]) == {"stub"}
    assert server.json("/api/config")["offline"] is True
    # --- the Home page, its policy and the token it carries
    status, headers, page = server.request("GET", "/", token=False)
    assert status == 200 and headers["content-type"].startswith("text/html")
    csp = headers["content-security-policy"]
    assert "default-src 'self'" in csp and "object-src 'none'" in csp and "frame-ancestors 'self'" in csp
    script_src = next(part for part in csp.split("; ") if part.startswith("script-src"))
    assert "'unsafe-inline'" not in script_src and "'sha256-" in script_src
    boot = json.loads(re.search(r'<script type="application/json" id="sutra-boot">(.*?)</script>', page, re.S).group(1))
    assert boot["page"] == "home" and len(boot["token"]) >= 16
    server.token = boot["token"]
    assert "Sutra" in page
    # --- a message posts with the page's token, and not without it
    refused = server.request("POST", "/api/chats/cs_org/messages", {"text": "hello there"}, token=False)
    assert refused[0] == 401 and json.loads(refused[2])["error"]["code"] == "bad_token"
    status, _, text = server.request("POST", "/api/chats/cs_org/messages", {"text": "hello there"})
    assert status == 202, text
    message_id = json.loads(text)["message_id"]
    end = time.time() + 30
    while True:
        mine = [m for m in server.json("/api/chats/cs_org/messages")["messages"] if m["id"] == message_id]
        if mine and mine[0]["state"] != "pending":
            break
        assert time.time() < end, "the offline chat turn never ended"
        time.sleep(0.1)
    assert mine[0]["text"] == "hello there" and server.json("/api/health")["ok"] is True
    # --- give a team a task so a real engine process exists (offline: the engine plays J2's mock)
    revision = server.json("/api/chart")["version"]
    chart = server.request("POST", "/api/chart/changes", dept_change_payload(revision, "chg-0002", "web", "Web", "Websites"))
    assert chart[0] == 200, chart[2]
    task = json.loads(server.request("POST", "/api/tasks", {"dept_id": "web", "text": "a website for my cafe"})[2])["id"]
    end = time.time() + 60
    while server.json(f"/api/tasks/{task}")["status"] != "waiting_user":
        assert time.time() < end, server.json(f"/api/tasks/{task}")
        time.sleep(0.1)
    pids = engine_pids(server.data)                                   # ours, and any the offline chat agent started for the message above
    assert pids and server.proc.pid not in pids and all(pid_alive(pid) for pid in pids)
    assert server.json(f"/api/tasks/{task}")["status"] == "waiting_user"
    # --- SIGTERM: the server and its engine are gone inside 15 s
    started = time.time()
    code = server.stop()
    assert time.time() - started < STOP_WITHIN_S and code in (0, -signal.SIGTERM, 128 + signal.SIGTERM)
    assert not any(pid_alive(pid) for pid in pids) and engine_pids(server.data) == []
    log = (server.data / "logs" / "server.log").read_text()
    assert server.token not in log and "Traceback" not in log
    assert (server.data / "db.sqlite3").is_file()
