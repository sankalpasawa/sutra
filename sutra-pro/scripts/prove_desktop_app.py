#!/usr/bin/env python3
"""Prove that a built or installed desktop app works, by running it the way a person does (D124).

    python scripts/prove_desktop_app.py --app "build/Sutra Pro.app" --version 0.2.0            # a Mac
    python scripts/prove_desktop_app.py --app "build/Sutra Pro" --version 0.2.0                # Windows: the folder that holds `Sutra Pro.exe`
    python scripts/prove_desktop_app.py --app "/Applications/Sutra Pro.app" --version 0.2.0 --no-team
    python scripts/prove_desktop_app.py --app "build/Sutra Pro.app" --version 0.2.0 --keep proof     # keep the picture and the logs in ./proof

Two proofs, each in a throw-away data folder, with no network (every proxy points at a closed port) and no model (SUTRA_OFFLINE):

  1. THE WINDOW. The app is started with SUTRA_PRO_SELFTEST=1 (desktop/src/selftest.js): the real window opens, the app starts its server on the
     Python inside it, the page loads, the app asks the page whether it finished loading, is the server's own, drew something and gets /api/health
     from inside the page, saves selftest.png, writes selftest.json and quits through its normal path. This script requires exit status 0, `ok`,
     the version it was given, that the app started its OWN server, and that afterwards no process of the data folder is left and nothing answers on the port.
  2. THE TEAM. The Python inside the app is started as the server alone (the command line the window gives it): a chat message posts, a department is added
     and a task given to it, so a real engine process starts; the task reaches `waiting_user` (the offline engine asked its first question); a stop
     request ends everything. This is what scripts/prove_windows_app.py proves for the older app, on the interpreter that now sits in the window's resources.

The logs are printed when a step fails, so a failure is read from the run itself. Stdlib only. Exit status 0 when every step held, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prove_windows_app import (   # noqa: E402  (the helpers that do not care which shell the app has)
    Client, Failure, check, clean_environment, processes_mentioning, read_pid_file, show_logs, tail,
)

WINDOW_TIMEOUT_S = 240
LAUNCH_TIMEOUT_S = 180
STOP_TIMEOUT_S = 60
WINDOWS = sys.platform == "win32"


def layout(app: Path) -> tuple[Path, Path]:
    """(the program a person starts, the interpreter inside the app) of a Mac app or a Windows folder."""
    if WINDOWS:
        return app / "Sutra Pro.exe", app / "resources" / "python" / "python.exe"
    return app / "Contents" / "MacOS" / "Sutra Pro", app / "Contents" / "Resources" / "python" / "bin" / "python3"


def kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if WINDOWS:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            proc.kill()


def popen_kwargs() -> dict:
    return {} if WINDOWS else {"start_new_session": True}


def port_answers(url: str) -> bool:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url.rstrip("/") + "/api/health", timeout=3):
            return True
    except (OSError, urllib.error.URLError):
        return False


def prove_window(exe: Path, version: str | None, work: Path) -> None:
    data, out = work / "window-data", work / "window-out"
    env = clean_environment(data)
    # a cold runner that is scanning a fresh install is slow to start Python: the server gets as long as the older proof gave it
    env.update(SUTRA_PRO_SELFTEST="1", SUTRA_PRO_SELFTEST_DIR=str(out), SUTRA_PRO_START_TIMEOUT="170")
    if version:
        env["SUTRA_PRO_EXPECT_VERSION"] = version
    log = work / "electron.out"
    with log.open("wb") as sink:
        proc = subprocess.Popen([str(exe)], cwd=str(exe.parent), env=env, stdin=subprocess.DEVNULL, stdout=sink, stderr=subprocess.STDOUT,
                                **popen_kwargs())
        try:
            proc.wait(timeout=WINDOW_TIMEOUT_S)
        except subprocess.TimeoutExpired as error:
            kill_tree(proc)
            show_logs(data)
            print("----- electron output (last lines)\n" + tail(log, 40), flush=True)
            raise Failure(f"the window did not finish its self-test in {WINDOW_TIMEOUT_S} s") from error
        finally:
            kill_tree(proc)
    try:
        result = json.loads((out / "selftest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        show_logs(data)
        print("----- electron output (last lines)\n" + tail(log, 40), flush=True)
        raise Failure(f"the window left no selftest.json (exit status {proc.returncode})") from error
    print(json.dumps({k: result.get(k) for k in ("ok", "failures", "url", "owned", "picture", "electron", "platform", "arch")}), flush=True)
    if not result.get("ok") or proc.returncode != 0:
        show_logs(data)
        raise Failure(f"the window's self-test failed (exit status {proc.returncode}): {result.get('failures')}")
    check(result.get("owned") is True, "the window did not start its own server")
    health = (result.get("probe") or {}).get("health") or {}
    if version:
        check(health.get("version") == version, f"the server in the app reports {health.get('version')!r}, expected {version!r}")
    check(not port_answers(result["url"]), f"{result['url']} still answers after the window quit: the server was left running")
    time.sleep(1.0)
    left = processes_mentioning(str(data))
    check(not left, f"processes of the data folder are still running after the window quit: {left}")
    check(not (data / "app.pid").exists(), "app.pid was left behind")
    picture = result.get("picture")
    print(f"step 1: the window started its server, drew the page, answered health and stopped it ({'picture ' + str(picture['width']) + 'x' + str(picture['height']) if picture else 'no picture'})", flush=True)


def prove_team(python: Path, version: str | None, work: Path) -> None:
    data = work / "team-data"
    env = clean_environment(data)
    command = [str(python), "-I", "-B", *(["-X", "utf8"] if WINDOWS else []), "-m", "sutra_app", "--no-browser", "--port", "0"]
    proc = subprocess.Popen(command, cwd=str(python.parent), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            **popen_kwargs())
    try:
        end = time.monotonic() + LAUNCH_TIMEOUT_S
        found = None
        while time.monotonic() < end and found is None:
            check(proc.poll() is None, f"the server exited with {proc.returncode} before it served")
            found = read_pid_file(data)
            time.sleep(0.25)
        check(found is not None, f"no port in {data / 'app.pid'} after {LAUNCH_TIMEOUT_S} s")
        _, port = found
        client = Client(f"http://127.0.0.1:{port}")
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
            check(health.get("version") == version, f"the server reports version {health.get('version')!r}, expected {version!r}")
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
        done = subprocess.run([str(python), "-I", "-B", *(["-X", "utf8"] if WINDOWS else []), "-m", "sutra_app", "stop", "--wait", str(STOP_TIMEOUT_S - 10)],
                              cwd=str(python.parent), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=STOP_TIMEOUT_S + 30)
        print(done.stdout + done.stderr, flush=True)
        check(done.returncode == 0, f"`sutra-pro stop` exited {done.returncode}")
        try:
            proc.wait(timeout=STOP_TIMEOUT_S)
        except subprocess.TimeoutExpired as error:
            raise Failure("the server is still running after `stop`") from error
        time.sleep(1.0)
        left = processes_mentioning(str(data))
        check(not left, f"processes of the data folder are still running after the stop: {left}")
        check(not (data / "app.stop").exists(), "app.stop was left behind")
        print(f"step 2: a team ran its first turn on the app's own Python ({len(engines)} processes of the data folder), a stop ended all of them", flush=True)
    except BaseException:
        show_logs(data)
        raise
    finally:
        kill_tree(proc)


def keep_evidence(work: Path, keep: Path | None) -> None:
    """Copy what a person reading a CI run needs, whether the proof held or not: the window's picture and result, what the app printed, the logs of both
    data folders. Never raises: a missing file is just not there."""
    if keep is None:
        return
    try:
        keep.mkdir(parents=True, exist_ok=True)
        for source, name in ((work / "window-out", "window"), (work / "window-data" / "logs", "window-logs"), (work / "team-data" / "logs", "team-logs")):
            if source.is_dir():
                shutil.copytree(source, keep / name, dirs_exist_ok=True)
        if (work / "electron.out").is_file():
            shutil.copy2(work / "electron.out", keep / "electron.out")
    except OSError as error:
        print(f"could not keep the evidence: {error}", flush=True)


def prove(app: Path, version: str | None, *, team: bool = True, keep: Path | None = None) -> None:
    app = app.resolve()                    # a relative program path plus cwd= is resolved differently on Windows than on POSIX
    exe, python = layout(app)
    check(exe.is_file() and python.is_file(), f"{app} is not a desktop app: {exe} or {python} is missing")
    work = Path(tempfile.mkdtemp(prefix="sutra-pro-prove-"))
    try:
        prove_window(exe, version, work)
        if team:
            prove_team(python, version, work)
        print("PROVED", flush=True)
    finally:
        keep_evidence(work, keep)
        shutil.rmtree(work, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a desktop app the way a person does and check that it works.")
    parser.add_argument("--app", required=True, type=Path, help="'Sutra Pro.app' (a Mac), or the Windows folder that holds 'Sutra Pro.exe'")
    parser.add_argument("--version", default=None, help="the version the app and its server must report")
    parser.add_argument("--no-team", action="store_true", help="skip the second proof (the server alone, a team's first turn)")
    parser.add_argument("--keep", type=Path, default=None, help="copy the window's picture and result and the logs into this folder (a CI run uploads it)")
    args = parser.parse_args(argv)
    try:
        prove(args.app, args.version, team=not args.no_team, keep=args.keep)
    except Failure as failure:
        print(f"NOT PROVED: {failure}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
