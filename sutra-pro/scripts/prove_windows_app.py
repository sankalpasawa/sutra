#!/usr/bin/env python3
"""Prove that a built (or installed) Windows app folder works, by running it the way its shortcut does (D101).

    python scripts/prove_windows_app.py --app "build/Sutra Pro" --version 0.1.0
    python scripts/prove_windows_app.py --app "%LOCALAPPDATA%\\Programs\\Sutra Pro" --version 0.1.0

What it does, with a throw-away data folder, no network (every proxy points at a closed port) and no model (SUTRA_OFFLINE):

  1. starts `python\\SutraPro.exe -I -X utf8 -m sutra_app.desktop --no-browser --port 0`, the shortcut's own command line, and waits
     for the instance lock's pid file to name a port
  2. /api/health answers and reports the version it was given
  3. the Home page carries a token; a chat message posts and its turn ends; a department is added and a task given to it, so a real
     engine process starts; the task reaches `waiting_user` (the offline engine asked its first question)
  4. `python\\python.exe -m sutra_app stop` ends the server; the lock is free; no process that mentions the data folder is left
  5. the log files are printed, so a failure is read from the run itself

The tray icon is tried as it would be for a user; where Windows has no notification area (a CI session) the app says so in
desktop.log and keeps running, which is also a pass. Stdlib only. Exit status 0 when every step held, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

LAUNCH_TIMEOUT_S = 180
STOP_TIMEOUT_S = 60


class Failure(Exception):
    pass


def check(condition: object, message: str) -> None:
    if not condition:
        raise Failure(message)


def clean_environment(data: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("SUTRA_", "J2_", "STUDIO_", "PYTHON", "VIRTUAL_ENV"))}
    closed = "http://127.0.0.1:9"                                      # nothing listens there: any outbound request fails at once
    env.update(SUTRA_DATA_DIR=str(data), SUTRA_ENV_FILE=str(data.parent / "none.env"), SUTRA_OFFLINE="1", SUTRA_NO_DIALOG="1",
               HTTP_PROXY=closed, HTTPS_PROXY=closed, ALL_PROXY=closed, NO_PROXY="127.0.0.1,localhost")
    return env


def read_pid_file(data: Path) -> tuple[int, int] | None:
    try:
        words = (data / "app.pid").read_text(encoding="utf-8").splitlines()[0].split()
        pid, port = int(words[0]), int(words[1])
    except (OSError, IndexError, ValueError):
        return None
    return (pid, port) if pid > 0 and 0 < port < 65536 else None


class Client:
    def __init__(self, base: str) -> None:
        self.base, self.token = base, ""
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def call(self, method: str, path: str, body: dict | None = None, *, token: bool = True) -> tuple[int, str]:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, method=method)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        if token and self.token:
            request.add_header("X-Sutra-Token", self.token)
        try:
            with self.opener.open(request, timeout=30) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode("utf-8")

    def json(self, path: str) -> dict:
        status, text = self.call("GET", path)
        check(status == 200, f"GET {path} answered {status}: {text[:300]}")
        return json.loads(text)


def processes_mentioning(needle: str) -> list[str]:
    """The command lines of the running processes that contain `needle` (this script's own are left out)."""
    if sys.platform == "win32":
        script = "Get-CimInstance Win32_Process | ForEach-Object { '{0} {1}' -f $_.ProcessId, $_.CommandLine }"
        out = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, timeout=120).stdout
    else:
        out = subprocess.run(["ps", "-A", "-o", "pid=,command="], capture_output=True, timeout=30).stdout
    own = str(os.getpid())
    return [line for line in out.decode("utf-8", "replace").splitlines()
            if needle in line and line.strip().split(None, 1)[0] != own and "powershell" not in line.lower() and "prove_windows_app" not in line]


def tail(path: Path, lines: int = 60) -> str:
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
    except OSError:
        return "(not there)"


def show_logs(data: Path) -> None:
    logs = data / "logs"
    for name in ("desktop.log", "app.log", "server.log"):
        print(f"----- {name} (last lines)\n{tail(logs / name)}\n", flush=True)


def prove(app: Path, version: str | None) -> None:
    app = app.resolve()                    # a relative program path plus cwd= is resolved differently on Windows than on POSIX
    exe, python = app / "python" / "SutraPro.exe", app / "python" / "python.exe"
    check(exe.is_file() and python.is_file(), f"{app} is not an app folder: python\\SutraPro.exe or python\\python.exe is missing")
    work = Path(tempfile.mkdtemp(prefix="sutra-pro-prove-"))
    data = work / "data"
    env = clean_environment(data)
    proc = subprocess.Popen([str(exe), "-I", "-X", "utf8", "-m", "sutra_app.desktop", "--no-browser", "--port", "0"], cwd=str(app), env=env,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        # 1. the server comes up
        end = time.monotonic() + LAUNCH_TIMEOUT_S
        found = None
        while time.monotonic() < end and found is None:
            check(proc.poll() is None, f"the app exited with {proc.returncode} before it served")
            found = read_pid_file(data)
            time.sleep(0.25)
        check(found is not None, f"no port in {data / 'app.pid'} after {LAUNCH_TIMEOUT_S} s")
        server_pid, port = found
        client = Client(f"http://127.0.0.1:{port}")
        print(f"step 1: serving on port {port} (pid {server_pid})", flush=True)

        # 2. health and version
        end = time.monotonic() + 60
        health = None
        while health is None:
            try:
                health = client.json("/api/health")
            except (OSError, Failure, ValueError):
                check(time.monotonic() < end and proc.poll() is None, "/api/health never answered")
                time.sleep(0.25)
        check(health.get("ok") is True, f"/api/health says {health}")
        if version:
            check(health.get("version") == version, f"the app reports version {health.get('version')!r}, expected {version!r}")
        print(f"step 2: health ok, version {health.get('version')}", flush=True)

        # 3. a team runs: token, a chat message, a department, a task, the engine's first question
        status, page = client.call("GET", "/", token=False)
        check(status == 200, f"GET / answered {status}")
        boot = re.search(r'<script type="application/json" id="sutra-boot">(.*?)</script>', page, re.S)
        check(boot is not None, "the Home page carries no boot block")
        client.token = json.loads(boot.group(1))["token"]
        refused, _ = client.call("POST", "/api/chats/cs_org/messages", {"text": "hello there"}, token=False)
        check(refused == 401, f"a message without the token answered {refused}, expected 401")
        status, text = client.call("POST", "/api/chats/cs_org/messages", {"text": "hello there"})
        check(status == 202, f"posting a message answered {status}: {text[:300]}")
        message_id = json.loads(text)["message_id"]
        end = time.monotonic() + 60
        while True:
            mine = [m for m in client.json("/api/chats/cs_org/messages")["messages"] if m["id"] == message_id]
            if mine and mine[0]["state"] != "pending":
                break
            check(time.monotonic() < end, "the offline chat turn never ended")
            time.sleep(0.2)
        revision = client.json("/api/chart")["version"]
        change = {"reason": "add Web", "reuses": [], "kind": "add", "schema_version": 1, "id": "chg-0002", "task_id": "req-1",
                  "base_revision": revision, "ts": 1,
                  "ops": [{"op": "add", "node": {"ref": "$web", "kind": "department", "name": "Web", "purpose": "Websites", "parent": "root"}}]}
        status, text = client.call("POST", "/api/chart/changes", change)
        check(status == 200, f"adding a department answered {status}: {text[:300]}")
        status, text = client.call("POST", "/api/tasks", {"dept_id": "web", "text": "a website for my cafe"})
        check(status in (200, 201, 202), f"giving the team a task answered {status}: {text[:300]}")
        task = json.loads(text)["id"]
        end = time.monotonic() + 120
        while client.json(f"/api/tasks/{task}")["status"] != "waiting_user":
            check(time.monotonic() < end, f"the task never reached waiting_user: {client.json(f'/api/tasks/{task}')}")
            time.sleep(0.25)
        engines = processes_mentioning(str(data))
        check(len(engines) >= 2, f"expected the server and an engine process of this data folder, saw {engines}")
        print(f"step 3: a team ran its first turn ({len(engines)} processes of this data folder)", flush=True)

        # 4. a stop request ends it, and leaves nothing behind
        done = subprocess.run([str(python), "-I", "-X", "utf8", "-m", "sutra_app", "stop", "--wait", str(STOP_TIMEOUT_S - 10)], cwd=str(app),
                              env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=STOP_TIMEOUT_S + 30)
        print(done.stdout + done.stderr, flush=True)
        check(done.returncode == 0, f"`sutra-pro stop` exited {done.returncode}")
        try:
            proc.wait(timeout=STOP_TIMEOUT_S)
        except subprocess.TimeoutExpired as error:
            raise Failure("the app is still running after `stop`") from error
        time.sleep(1.0)
        left = processes_mentioning(str(data))
        check(not left, f"processes of the data folder are still running after the stop: {left}")
        check(not (data / "app.stop").exists(), "app.stop was left behind")
        print("step 4: stopped, nothing left running", flush=True)
        log = tail(data / "logs" / "desktop.log", 200)
        print("tray:", "failed (no notification area here, the app carried on)" if "tray icon failed" in log else "no failure recorded", flush=True)
        print("PROVED", flush=True)
    except BaseException:
        show_logs(data)
        raise
    finally:
        if proc.poll() is None:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True) if sys.platform == "win32" else proc.kill()
        shutil.rmtree(work, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a Windows app folder the way its shortcut does and check that it works.")
    parser.add_argument("--app", required=True, type=Path, help="the app folder: the one that holds python\\SutraPro.exe")
    parser.add_argument("--version", default=None, help="the version /api/health must report")
    args = parser.parse_args(argv)
    try:
        prove(args.app, args.version)
    except Failure as failure:
        print(f"NOT PROVED: {failure}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
