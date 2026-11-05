#!/usr/bin/env python3
"""Capture the J2 fixtures and goldens for the UI tests from a J2 MOCK run (UI-0, docs/design/ui.md section 10).

    scripts/py scripts/capture_j2_fixtures.py --j2 /path/to/J2_Prototype --j2-python /path/to/J2_Prototype/venv/bin/python
    scripts/py scripts/capture_j2_fixtures.py --j2 ... --j2-python ... --check      # drift check, writes nothing

What it does, in a scratch folder (the J2 checkout is read-only here and is checked to be unchanged afterwards):
  1. starts J2's own `j2_server.py` with `STUDIO_MOCK=1` on a free loopback port, in a scrubbed environment and under a
     frozen clock, so two captures give the same bytes: no model, no network, no Chrome (`J2_CHROME=none`);
  2. sends one brief to `/api/say` and waits until the team has answered;
  3. saves what every J2 read route answered, byte for byte (`state.json`, `map.json`, ..., `agent-<who>.json`,
     `site-latest.html`), the preview replies, and the inputs of J2's two node harnesses;
  4. runs `j2_ui_render.js` on J2's own `j2_ui.html` (twice, the outputs must be equal) and `j2_graph_layout.js`, and
     saves the outputs as `golden-<key>.json` (the goldens that `page_render.test.js` of UI-2 compares with);
  5. writes `MANIFEST.json` (J2 commit, brief, size and sha256 of every file).
The files go to `tests/ui/fixtures/j2/`. The state must stay under `--max-state-bytes` (default 150,000).
`--check` captures into a scratch folder and compares byte for byte with the committed files: exit 1 when J2 has drifted. A J2 that
moved to a new commit but gives the same bytes is not drift: the check says so and exits 0 (only the manifest's `j2_commit` differs).
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterator

REPO = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO / "tests" / "ui" / "fixtures" / "j2"

# Long enough that J2's mock treats the brief as complete (25 words or more) and runs the whole team.
BRIEF = (
    "A one-page website for Brew Lab, a small specialty coffee shop in Indiranagar, Bengaluru. Visitors should see "
    "the menu with prices, the opening hours, and where to find us, and be able to pre-order a coffee for pickup. "
    "It should feel warm and modern and work well on a phone."
)
MAX_STATE_BYTES = 150_000
STOP_GRACE_S = 5.0  # how long J2's server gets to leave after SIGTERM, and again after SIGKILL
FIXED_TIME = 1793786404  # 2026-11-04T10:00:04Z: the clock the J2 process sees, so a re-capture gives the same bytes
FUNCTIONS = ("identity", "adaptation", "priority", "coordination", "audit")
AGENT_WHO = (*FUNCTIONS, "W-1", "nobody")  # `nobody` is J2's answer for an agent it does not know (found: false)
GOLDEN_KEYS = ("simple", "sprog", "workflows", "rail", "needs", "map", "agent")  # the outputs page_render.test.js compares
REQUIRED_J2_FILES = ("j2_server.py", "j2_ui.html", "j2_ui_render.js", "j2_graph_layout.js")

# fixture file -> the J2 read route it holds, byte for byte
ROUTE_FILES = {
    "state.json": "/api/state",
    "runs.json": "/api/runs",
    "map.json": "/api/map",
    "plan.json": "/api/plan",
    "docs.json": "/api/docs",
    "library.json": "/api/library",
    "run-templates.json": "/api/run-templates",
    "artifacts.json": "/api/artifacts",
    "artifacts-tree.json": "/api/artifacts/tree",
    "board.json": "/api/board",
    "story.json": "/api/story",
    "audits.json": "/api/audits",
    "refs.json": "/api/refs",
    "site-latest.html": "/site/latest",
}

# A launcher that freezes the clock before J2 is imported. Local time is UTC and every timestamp is FIXED_TIME,
# including the times J2 reads from file modification times.
CLOCK_LAUNCHER = '''\
import datetime as _dt
import os
import runpy
import sys
import time as _time

FIXED = %(fixed)d
_gmtime, _strftime = _time.gmtime, _time.strftime
_time.time = lambda: float(FIXED)
_time.localtime = lambda secs=None: _gmtime(FIXED)
_time.gmtime = lambda secs=None: _gmtime(FIXED)
_time.strftime = lambda fmt, t=None: _strftime(fmt, _gmtime(FIXED) if t is None else t)


class _FixedDateTime(_dt.datetime):
    @classmethod
    def _fixed(cls):
        return cls(1970, 1, 1) + _dt.timedelta(seconds=FIXED)

    @classmethod
    def now(cls, tz=None):
        return cls._fixed() if tz is None else cls._fixed().replace(tzinfo=_dt.timezone.utc).astimezone(tz)

    @classmethod
    def utcnow(cls):
        return cls._fixed()

    @classmethod
    def today(cls):
        return cls._fixed()


_dt.datetime = _FixedDateTime
script = os.path.abspath(sys.argv[1])
sys.argv = sys.argv[1:]
sys.path.insert(0, os.path.dirname(script))
runpy.run_path(script, run_name="__main__")
'''


class CaptureError(RuntimeError):
    """The capture cannot go on; the message says why."""


# ---------------------------------------------------------------------------------------------------------------------
# Small pure helpers
# ---------------------------------------------------------------------------------------------------------------------
def rail_tabs(page_html: str) -> list[str]:
    """The tab names of the rail's sections, as J2's own tests read them from the page (the harness cannot see the DOM)."""
    start = page_html.index('<nav class="rail tabs"')
    nav = page_html[start:page_html.index("</nav>", start)]
    return re.findall(r'data-tab="(\w+)"', nav[nav.index('id="railsub"'):])


def atom_ids(state: dict) -> list[str]:
    """Every atom id of the state's workflows, in order, once."""
    seen: list[str] = []
    for workflow in state.get("workflows") or []:
        for atom in workflow.get("atoms") or []:
            if atom.get("id") and atom["id"] not in seen:
                seen.append(atom["id"])
    return seen


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump_json(value) -> bytes:
    """Derived files: compact JSON, UTF-8, one line (the route files keep J2's own bytes)."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def free_port() -> int:
    with contextlib.closing(socket.socket()) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def scrubbed_env(work: Path, base: dict[str, str] | None = None) -> dict[str, str]:
    """The environment of the J2 process: only what Python needs plus the switches of the capture. Nothing of the
    developer's own (keys, tokens, J2_* settings) can leak into the files or change what J2 does."""
    base = dict(os.environ if base is None else base)
    env = {k: base[k] for k in ("PATH", "LANG", "LC_ALL", "SYSTEMROOT", "TEMP", "TMP") if k in base}
    env.update({
        "HOME": str(work / "home"),
        "TZ": "UTC",
        "PYTHONDONTWRITEBYTECODE": "1",  # J2's folder stays untouched
        "PYTHONHASHSEED": "0",
        "PYTHONUTF8": "1",
        "STUDIO_MOCK": "1",
        "J2_CHROME": "none",  # J2's render check would use this machine's Chrome and change the audits
        "J2_MEMORY": "0",
        "J2_RUNS_DIR": str(work / "runs"),
        "J2_MEMORY_FILE": str(work / "lessons.jsonl"),
        "J2_PLAYBOOK_FILE": str(work / "playbooks.jsonl"),
    })
    return env


def git(j2: Path, *args: str) -> str | None:
    """A read-only git command in the J2 checkout; None when it is not a repository or git is missing."""
    try:
        done = subprocess.run(["git", "-C", str(j2), *args], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout if done.returncode == 0 else None


def checkout_state(j2: Path) -> str | None:
    """What `git status` says about the J2 checkout, to prove afterwards that nothing was written there."""
    return git(j2, "status", "--porcelain", "--untracked-files=all")


def check_checkout(j2: Path, j2_python: str, node: str | None) -> None:
    if not j2.is_dir():
        raise CaptureError(f"--j2 {j2} is not a folder")
    missing = [name for name in REQUIRED_J2_FILES if not (j2 / name).is_file()]
    if missing:
        raise CaptureError(f"{j2} is not a J2 checkout: missing {', '.join(missing)}")
    if not (os.path.isfile(j2_python) and os.access(j2_python, os.X_OK)):
        raise CaptureError(f"--j2-python {j2_python} is not an executable file")
    if not node:
        raise CaptureError("node is needed for the goldens (put it on PATH or pass --node)")


# ---------------------------------------------------------------------------------------------------------------------
# The J2 server
# ---------------------------------------------------------------------------------------------------------------------
class J2Server:
    """J2's `j2_server.py` as a child process under the frozen clock."""

    def __init__(self, j2: Path, j2_python: str, work: Path, *, ready_timeout: float = 30.0) -> None:
        self.j2, self.work, self.ready_timeout = j2, work, ready_timeout
        self.j2_python = j2_python
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.log_path = work / "j2-server.log"
        self.process: subprocess.Popen | None = None

    def __enter__(self) -> "J2Server":
        (self.work / "runs").mkdir(parents=True, exist_ok=True)
        (self.work / "home").mkdir(parents=True, exist_ok=True)
        launcher = self.work / "frozen_clock.py"
        launcher.write_text(CLOCK_LAUNCHER % {"fixed": FIXED_TIME}, encoding="utf-8")
        log = open(self.log_path, "wb")
        try:
            self.process = subprocess.Popen(
                [self.j2_python, "-B", str(launcher), str(self.j2 / "j2_server.py"), "--port", str(self.port), "--no-browser"],
                cwd=self.j2, env=scrubbed_env(self.work), stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
            )
        finally:
            log.close()
        deadline = time.monotonic() + self.ready_timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise CaptureError(f"J2's server exited with code {self.process.returncode}:\n{self.log_tail()}")
            try:
                self.get("/api/runs")
                return self
            except (OSError, urllib.error.URLError):
                time.sleep(0.1)
        self.stop()
        raise CaptureError(f"J2's server did not answer within {self.ready_timeout} s:\n{self.log_tail()}")

    def __exit__(self, *exc: object) -> None:
        self.stop()

    def log_tail(self, size: int = 1500) -> str:
        try:
            return self.log_path.read_text(errors="replace")[-size:]
        except OSError:
            return "(no log)"

    def stop(self) -> None:
        process, self.process = self.process, None
        if process is None or process.poll() is not None:
            return
        with contextlib.suppress(OSError):
            os.killpg(process.pid, 15)
        try:
            process.wait(timeout=STOP_GRACE_S)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(OSError):
                os.killpg(process.pid, 9)
            process.wait(timeout=STOP_GRACE_S)

    def get(self, path: str) -> tuple[int, bytes]:
        """Status and raw body; a 4xx is an answer, not an error."""
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(self.base + path, timeout=30) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def post(self, path: str, body: dict) -> int:
        request = urllib.request.Request(self.base + path, data=json.dumps(body).encode(), method="POST",
                                         headers={"Content-Type": "application/json"})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=30) as response:
                return response.status
        except urllib.error.HTTPError as exc:
            return exc.code


def run_team(server: J2Server, brief: str, timeout: float) -> None:
    """Send the brief and wait until J2's team has answered (status `waiting` with the chat grown)."""
    status = server.post("/api/say", {"text": brief})
    if status != 200:
        raise CaptureError(f"POST /api/say answered {status}")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if server.process is not None and server.process.poll() is not None:
            raise CaptureError(f"J2's server died during the run:\n{server.log_tail()}")
        try:
            code, body = server.get("/api/state")
        except OSError:  # the server is not answering: either it is about to be seen dead above, or the deadline ends the wait
            time.sleep(0.2)
            continue
        if code == 200:
            state = json.loads(body)
            if state.get("status") == "waiting" and state.get("total", 0) > 1:
                return
        time.sleep(0.2)
    raise CaptureError(f"J2 did not finish the mock run within {timeout} s:\n{server.log_tail()}")


# ---------------------------------------------------------------------------------------------------------------------
# Collecting and deriving
# ---------------------------------------------------------------------------------------------------------------------
def collect_routes(server: J2Server, max_state_bytes: int) -> dict[str, bytes]:
    """Every read route, byte for byte, plus one agent view per `AGENT_WHO`."""
    files: dict[str, bytes] = {}
    for name, route in ROUTE_FILES.items():
        code, body = server.get(route)
        if code != 200:
            raise CaptureError(f"GET {route} answered {code}")
        files[name] = body
    if len(files["state.json"]) > max_state_bytes:
        raise CaptureError(f"the state is {len(files['state.json'])} bytes, over --max-state-bytes {max_state_bytes}: use a shorter --brief")
    for who in AGENT_WHO:
        code, body = server.get(f"/api/agent?who={who}")
        if code != 200:
            raise CaptureError(f"GET /api/agent?who={who} answered {code}")
        files["agent-unknown.json" if who == "nobody" else f"agent-{who}.json"] = body
    return files


def collect_previews(server: J2Server, state: dict) -> dict[str, dict]:
    """`/api/preview?atom=` for every atom of the state: {atom id: the route's reply}."""
    replies = {}
    for atom in atom_ids(state):
        code, body = server.get(f"/api/preview?atom={atom}")
        if code != 200:
            raise CaptureError(f"GET /api/preview?atom={atom} answered {code}")
        replies[atom] = json.loads(body)
    return replies


def run_node(node: str, script: Path, args: list[str], work: Path) -> bytes:
    done = subprocess.run([node, str(script), *args], capture_output=True, cwd=work, timeout=120)
    if done.returncode != 0:
        raise CaptureError(f"node {script.name} failed: {done.stderr.decode(errors='replace')[-800:]}")
    return done.stdout


def derive(j2: Path, node: str, routes: dict[str, bytes], preview_replies: dict[str, dict], work: Path) -> dict[str, bytes]:
    """The harness inputs and the goldens, made by J2's own harnesses on J2's own page."""
    state = json.loads(routes["state.json"])
    map_ = json.loads(routes["map.json"])
    previews = {atom: (reply.get("html") or "") for atom, reply in preview_replies.items()}
    listing = json.loads(routes["artifacts.json"])
    render_docs = {
        "docs": json.loads(routes["docs.json"]),
        "map": map_,
        "railtabs": rail_tabs((j2 / "j2_ui.html").read_text(encoding="utf-8")),
        "plan": json.loads(routes["plan.json"]),
        "artifacts": {**listing, "tree": json.loads(routes["artifacts-tree.json"])},
        "agent": json.loads(routes["agent-identity.json"]),
    }
    maps = {map_.get("run") or "run": map_}
    derived = {
        "previews.json": dump_json(previews),
        "preview-replies.json": dump_json({a: r for a, r in preview_replies.items() if r.get("html")}),
        "render-docs.json": dump_json(render_docs),
        "maps.json": dump_json(maps),
    }
    inputs = work / "harness"
    inputs.mkdir(parents=True, exist_ok=True)
    for name in ("previews.json", "render-docs.json", "maps.json"):
        (inputs / name).write_bytes(derived[name])
    (inputs / "state.json").write_bytes(routes["state.json"])
    page = str(j2 / "j2_ui.html")
    render_args = [page, str(inputs / "state.json"), str(inputs / "previews.json"), str(inputs / "render-docs.json")]
    first = run_node(node, j2 / "j2_ui_render.js", render_args, work)
    second = run_node(node, j2 / "j2_ui_render.js", render_args, work)
    if first != second:
        raise CaptureError("J2's render harness gave two different outputs for one input: the goldens would not be stable")
    rendered = json.loads(first)
    for key in GOLDEN_KEYS:
        if key not in rendered:
            raise CaptureError(f"J2's render harness printed no '{key}'")
        derived[f"golden-{key}.json"] = dump_json(rendered[key])
    layout = run_node(node, j2 / "j2_graph_layout.js", [page, str(inputs / "maps.json")], work)
    derived["golden-layout.json"] = dump_json(json.loads(layout))
    return derived


def manifest(j2: Path, brief: str, files: dict[str, bytes]) -> bytes:
    body = {
        "schema": "j2-fixtures/1",
        "j2_commit": (git(j2, "rev-parse", "HEAD") or "").strip() or None,
        "mock": True,
        "brief": brief,
        "clock": FIXED_TIME,
        "harness": {
            "page": "j2_ui.html",
            "render": ["state.json", "previews.json", "render-docs.json"],
            "layout": ["maps.json"],
            "goldens": [f"golden-{key}.json" for key in GOLDEN_KEYS] + ["golden-layout.json"],
        },
        "files": {name: {"bytes": len(data), "sha256": sha256_hex(data)} for name, data in sorted(files.items())},
    }
    return (json.dumps(body, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


# ---------------------------------------------------------------------------------------------------------------------
# The whole capture, writing and checking
# ---------------------------------------------------------------------------------------------------------------------
def capture(j2: Path, j2_python: str, node: str | None, brief: str, max_state_bytes: int, timeout: float,
            log=print) -> dict[str, bytes]:
    """Run the mock team and return every fixture file as {name: bytes}. Writes nothing in the J2 checkout."""
    check_checkout(j2, j2_python, node)
    before = checkout_state(j2)
    with tempfile.TemporaryDirectory(prefix="j2-capture-") as scratch:
        work = Path(scratch)
        with J2Server(j2, j2_python, work) as server:
            log(f"J2 mock server on {server.base}")
            run_team(server, brief, timeout)
            routes = collect_routes(server, max_state_bytes)
            previews = collect_previews(server, json.loads(routes["state.json"]))
        derived = derive(j2, node, routes, previews, work)
    after = checkout_state(j2)
    if before != after:
        raise CaptureError(f"the J2 checkout changed during the capture (git status before and after differ):\n{before}\n--\n{after}")
    files = {**routes, **derived}
    files["MANIFEST.json"] = manifest(j2, brief, files)
    return files


def write_files(out: Path, files: dict[str, bytes]) -> None:
    """Replace the folder's content with `files`. The folder belongs to this script, nothing else lives in it."""
    out.mkdir(parents=True, exist_ok=True)
    for existing in out.iterdir():
        if existing.is_file():
            existing.unlink()
    for name, data in files.items():
        (out / name).write_bytes(data)


def compare(out: Path, files: dict[str, bytes]) -> list[str]:
    """The names that differ between the committed folder and a fresh capture (missing, extra or changed)."""
    have = {p.name: p.read_bytes() for p in out.iterdir() if p.is_file()} if out.is_dir() else {}
    return sorted(
        [f"{n} (not captured now)" for n in have.keys() - files.keys()]
        + [f"{n} (missing)" for n in files.keys() - have.keys()]
        + [f"{n} (changed)" for n in files.keys() & have.keys() if files[n] != have[n]]
    )


def commit_only_moved(have: bytes, now: bytes) -> tuple[str | None, str | None] | None:
    """(captured commit, current commit) when two manifests differ in nothing but `j2_commit`, else None. J2 is a team repository
    that moves on; the bytes it gives for the mock brief may well stay the same, and then the fixtures are still true."""
    try:
        old, new = json.loads(have), json.loads(now)
    except ValueError:
        return None
    if not (isinstance(old, dict) and isinstance(new, dict)) or old.get("j2_commit") == new.get("j2_commit"):
        return None
    if {**old, "j2_commit": None} != {**new, "j2_commit": None}:
        return None
    return old.get("j2_commit"), new.get("j2_commit")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture the J2 fixtures and goldens of the UI tests from a J2 mock run.")
    parser.add_argument("--j2", required=True, type=Path, help="the J2 checkout (read-only here)")
    parser.add_argument("--j2-python", required=True, help="the Python of J2's own virtualenv")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="where the files go (default tests/ui/fixtures/j2)")
    parser.add_argument("--brief", default=BRIEF, help="the one message sent to J2's team")
    parser.add_argument("--max-state-bytes", type=int, default=MAX_STATE_BYTES)
    parser.add_argument("--timeout", type=float, default=180.0, help="seconds to wait for the mock run")
    parser.add_argument("--node", default=shutil.which("node"), help="node, for J2's two harnesses")
    parser.add_argument("--check", action="store_true", help="compare a fresh capture with --out; write nothing")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        files = capture(args.j2.resolve(), args.j2_python, args.node, args.brief, args.max_state_bytes, args.timeout)
    except CaptureError as exc:
        print(f"capture failed: {exc}", file=sys.stderr)
        return 1
    if args.check:
        differ = compare(args.out, files)
        moved = commit_only_moved((args.out / "MANIFEST.json").read_bytes(), files["MANIFEST.json"]) if differ == ["MANIFEST.json (changed)"] else None
        if moved:
            captured, current = ((c or "none")[:7] for c in moved)
            print(f"ok: {len(files) - 1} files equal a fresh capture; J2 moved on ({captured} captured, {current} now) and gives the same bytes")
            return 0
        if differ:
            print("the J2 fixtures have drifted from a fresh capture:\n  " + "\n  ".join(differ), file=sys.stderr)
            return 1
        print(f"ok: {len(files)} files equal a fresh capture")
        return 0
    write_files(args.out, files)
    total = sum(len(data) for data in files.values())
    print(f"wrote {len(files)} files ({total:,} bytes) to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
