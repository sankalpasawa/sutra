"""optimus_api -- the daemon, visible (Focus > Optimus).

Optimus is a WINDOW over sutra-daemon's on-disk stores plus a request surface
that shells the daemon CLI. The core invariant (dual-lane consult 2026-08-24):
Optimus may visualize and request; the daemon alone decides, mutates, logs and
rejects. No endpoint here writes a store file directly -- every mutation is a
subprocess of `bin/sutra-daemon`, so the CLI gate (and its audit rows) sees
exactly what a terminal operator's action would look like.

Root resolution: org_api rewrites SUTRA_NATIVE_HOME to the registry root
(~/.sutra-native/user-kit) at import, which is one level BELOW the daemon's
root. Optimus therefore resolves its own root -- SUTRA_UI_DAEMON_ROOT env,
else ~/.sutra-native -- and passes it to subprocesses explicitly. Never read
SUTRA_NATIVE_HOME from the environment in this module.

Reads are fixed-path and bounded (the /api/balance discipline): no path
parameters, no traversal surface, absent files answer honestly.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from org_api import _desktop_control

router = APIRouter(prefix="/api/optimus")

READ_CAP_BYTES = 1_000_000
TAIL_ROWS = 25
CLI_TIMEOUT_S = 20


def _root() -> Path:
    return Path(os.environ.get("SUTRA_UI_DAEMON_ROOT")
                or os.path.expanduser("~/.sutra-native"))


def _daemon_bin() -> Path:
    return Path(__file__).resolve().parent.parent / "bin" / "sutra-daemon"


def _cli(args, extra_env=None, detach=False):
    """Run the daemon CLI: absolute argv, minimal env, bounded, never a shell.
    Timeout returns rc=124, distinct from any CLI failure code."""
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
           "HOME": os.path.expanduser("~"),
           "SUTRA_NATIVE_HOME": str(_root())}
    if extra_env:
        env.update(extra_env)
    argv = [sys.executable, str(_daemon_bin())] + list(args)
    if detach:
        p = subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True, close_fds=True)
        return 0, "started pid=%d" % p.pid
    try:
        p = subprocess.run(argv, env=env, capture_output=True, text=True,
                           timeout=CLI_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return 124, "daemon CLI timed out after %ss" % CLI_TIMEOUT_S
    return p.returncode, (p.stdout + p.stderr)[-4000:]


def _tail_jsonl(path: Path, n=TAIL_ROWS):
    """Last n parseable rows + malformed count. Bounded read, honest absence.
    A torn final line parses as malformed and never breaks the snapshot."""
    if not path.is_file():
        return [], 0, False
    data = path.read_bytes()[-READ_CAP_BYTES:]
    rows, bad = [], 0
    for line in data.decode(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            bad += 1
    return rows[-n:], bad, True


def _load_json(path: Path, default):
    try:
        if not path.is_file():
            return default, False
        return json.loads(path.read_text()), True
    except (ValueError, OSError):
        return default, True  # present but unreadable -- surfaced by caller


@router.get("")
def optimus_snapshot() -> dict:
    """Everything the screen renders, in one bounded read. Read-only."""
    root = _root()
    d = root / "daemon"

    pid_info, running = None, False
    pid_file = d / "daemon.pid"
    if pid_file.is_file():
        try:
            pid_info = json.loads(pid_file.read_text())
            os.kill(int(pid_info.get("pid", -1)), 0)
            running = True
        except (ValueError, OSError, TypeError):
            running = False

    routes, routes_present = _load_json(d / "routes.json", [])
    states, _ = _load_json(d / "state.json", {})
    inbox_rows, inbox_bad, _ = _tail_jsonl(d / "inbox.jsonl", 200)
    pending = [r.get("input_id") for r in inbox_rows
               if isinstance(r, dict) and r.get("input_id") not in states]
    outbox_rows, _, outbox_present = _tail_jsonl(
        root / "outbox" / "outbox.jsonl", TAIL_ROWS)
    ledger_rows, _, ledger_present = _tail_jsonl(
        root / "ledger" / "run-ledger.jsonl", TAIL_ROWS)
    quarantine_rows, _, _ = _tail_jsonl(d / "quarantine.jsonl", 5)

    state_summary = {}
    for st in states.values():
        if isinstance(st, dict):
            k = st.get("state", "?")
            state_summary[k] = state_summary.get(k, 0) + 1

    return {
        "present": routes_present or running or ledger_present or outbox_present,
        "root": str(root),
        "daemon": {"running": running, "pid": pid_info},
        "routes": [
            {k: r.get(k) for k in ("route_id", "status", "pattern", "workflow",
                                   "host", "department", "charter")}
            for r in routes if isinstance(r, dict)],
        "pending_inputs": pending[:20],
        "state_summary": state_summary,
        "asks": [r for r in outbox_rows if isinstance(r, dict)],
        "runs": [
            {k: r.get(k) for k in ("run_id", "workflow_ref", "outcome",
                                   "attempts", "ts_open", "ts_close")}
            for r in ledger_rows if isinstance(r, dict)],
        "quarantine": quarantine_rows,
        "inbox_malformed": inbox_bad,
    }


@router.post("/ask")
def optimus_ask(request: Request, body: dict) -> dict:
    _desktop_control(request)
    text = (body or {}).get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="ask needs text")
    rc, out = _cli(["ask", text])
    if rc != 0:
        raise HTTPException(status_code=502, detail=out)
    return {"ok": True, "out": out.strip()}


@router.post("/route-propose")
def optimus_route_propose(request: Request, body: dict) -> dict:
    _desktop_control(request)
    b = body or {}
    required = ("pattern", "workflow", "host", "prompt_template",
                "verify_template_id", "verify_version")
    missing = [k for k in required if not b.get(k)]
    if missing:
        raise HTTPException(status_code=400, detail="missing: " + ", ".join(missing))
    args = ["route-propose"]
    for k in required:
        args += ["--" + k.replace("_", "-"), str(b[k])]
    for a in b.get("verify_args", []) or []:
        args += ["--verify-arg", str(a)]
    for opt in ("department", "charter", "timeout_s"):
        if b.get(opt):
            args += ["--" + opt.replace("_", "-"), str(b[opt])]
    rc, out = _cli(args)
    if rc != 0:
        raise HTTPException(status_code=502, detail=out)
    return {"ok": True, "out": out.strip()}


@router.post("/route-approve")
def optimus_route_approve(request: Request, body: dict) -> dict:
    """Two-step human gate (consult fold): the operator must TYPE the route id
    back as confirmation -- no one-click approve. The CLI's non-interactive
    honor override is used deliberately and is audit-logged by the daemon
    (route-approvals.jsonl records tty=false); the exit code + output return
    inline so the operator sees exactly what the gate said."""
    _desktop_control(request)
    b = body or {}
    import getpass
    rid, confirm = b.get("route_id"), b.get("confirm")
    operator = b.get("operator") or getpass.getuser()  # A3: the machine's one operator
    if not rid:
        raise HTTPException(status_code=400, detail="route_id is required")
    if confirm != rid:
        raise HTTPException(status_code=400, detail=(
            "confirmation mismatch: type the route id (%s) to approve" % rid))
    rc, out = _cli(["route-approve", "--route-id", rid, "--i-approve",
                    "--operator", operator],
                   extra_env={"SUTRA_DAEMON_APPROVE_ACK": "1"})
    return {"ok": rc == 0, "exit_code": rc, "out": out.strip()}


@router.post("/daemon/start")
def optimus_daemon_start(request: Request) -> dict:
    _desktop_control(request)
    snap = optimus_snapshot()
    if snap["daemon"]["running"]:
        raise HTTPException(status_code=409, detail="daemon already running pid=%s"
                            % (snap["daemon"]["pid"] or {}).get("pid"))
    rc, out = _cli(["start"], detach=True)
    return {"ok": True, "out": out}


@router.post("/daemon/stop")
def optimus_daemon_stop(request: Request, body: dict) -> dict:
    """PID-visible stop (consult fold): the caller must echo the pid it saw,
    so a stale screen can never stop a process it was not looking at."""
    _desktop_control(request)
    snap = optimus_snapshot()
    live = (snap["daemon"]["pid"] or {}).get("pid")
    sent = (body or {}).get("pid_confirm")
    if not snap["daemon"]["running"]:
        return {"ok": True, "out": "not running"}
    if sent != live:
        raise HTTPException(status_code=409, detail=(
            "pid mismatch: screen saw %s, live is %s -- refresh first" % (sent, live)))
    rc, out = _cli(["stop"])
    return {"ok": rc == 0, "exit_code": rc, "out": out.strip()}
