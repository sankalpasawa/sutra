#!/usr/bin/env python3
"""capture_j2_fixtures.py -- what the J2 prototype's own server answers on its real runs, kept as test fixtures.

The department's page is the prototype's, and the shapes it reads are the prototype's. The tests of the UI port
(test_j2ui_render.py, test_j2ui_contract.py) treat these captures as the shape truth: the pinned page must render each of
them, and the adapter's answers must have the same keys.

    J2_PROTOTYPE=<repo> python3 scripts/capture_j2_fixtures.py [--prototype PATH] [--out DIR] [--runs ID ...] [--keep]

What it does, in order:
    1  extracts the pinned commit (j2ui_assets/PINNED.json source.commit) with `git archive | tar -x` into a temp folder,
       so a dirty or moved working tree changes nothing
    2  copies the run folders named in RUNS from <repo>/runs to a scratch folder (the prototype's runs/ is read, never written)
    3  starts the extracted j2_server.py with J2_RUNS_DIR=<scratch> and STUDIO_MOCK=1 on a free port with --no-browser
       (the prototype's own venv python when it has one, else python3)
    4  for each run asks api/state?since=0&run=ID, api/map, api/board, api/artifacts, api/docs, api/audits (all with run=ID),
       api/refs, api/runs and api/preview?atom=ID for the first atom with a page output; and the idle live state
       (api/state?since=0 with no run, and the same endpoints without run)
    5  writes each answer as gzip JSON (mtime 0, so the same answers are the same bytes) to
       test_fixtures/j2ui/captured/<run>/<name>.json.gz, and captured/SOURCE.json with the pinned commit and the hashes

It refuses to run when the scratch folder or the output folder would be inside the prototype's folder, and it fails when
`git status --short` of the prototype is not the same before and after. When the prototype or its runs/ is not on this
machine it says so and exits 0: the committed fixtures stand.
"""
import argparse
import gzip
import hashlib
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
UI = HERE.parent
PINNED = UI / "j2ui_assets" / "PINNED.json"
OUT = UI / "test_fixtures" / "j2ui" / "captured"
SCHEMA = "j2ui-captured/1"

#: the runs kept: the two the package names (a small website run, the large documents run) and two more that put the page's
#: other paths to work (a conflict between Adaptation and Priority with three audits; a crashed run with the atom/1 views)
RUNS = (
    ("j2-20261008-153402", "a small website run, a boutique: done with open items"),
    ("j2-20261008-123848", "a website run with a conflict, three audits and six workflows"),
    ("j2-20261014-111512", "a website run that crashed, with atoms_v1 for its seven workflows"),
    ("j2-20261022-123744", "the large documents run: PRD, HLD and LLD, then the website"),
)
IDLE = "idle"
#: what the prototype answers per run; `state` takes since=0, `refs` and `runs` take no run
PER_RUN = ("state", "map", "board", "artifacts", "docs", "audits")
PLAIN = ("refs", "runs")
#: keys a call_log row must not carry into a fixture (the page reads none of them; api/call serves them in full)
HEAVY = ("prompt", "full", "messages", "raw")


class Refused(Exception):
    """The capture would write inside the prototype, or the prototype is not as it was."""


def pinned():
    try:
        return json.loads(PINNED.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def inside(path, root):
    """True when `path` is `root` or lies under it (both resolved: a link out of the way does not hide it)."""
    p, r = Path(path).resolve(), Path(root).resolve()
    return p == r or r in p.parents


def refuse_inside(prototype, *paths):
    """Raise Refused for any path that is inside the prototype's folder. The capture writes only to its scratch folder and
    the output folder; this is the one check that keeps it so."""
    for p in paths:
        if inside(p, prototype):
            raise Refused("%s is inside the prototype folder %s: this script never writes there" % (p, prototype))


def git(repo, *args):
    got = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=False)
    if got.returncode != 0:
        raise RuntimeError("git %s: %s" % (" ".join(args), got.stderr.decode("utf-8", "replace").strip()))
    return got.stdout


def status_of(repo):
    return git(repo, "status", "--short").decode("utf-8", "replace")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def get(port, path, tries=1):
    last = None
    for _ in range(tries):
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/%s" % (port, path), timeout=60) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()
        except (urllib.error.URLError, OSError) as exc:
            last = exc
            time.sleep(0.3)
    raise RuntimeError("the prototype's server did not answer %s: %s" % (path, last))


def drop_heavy(state):
    """The state's call_log without the fields the page does not read (none survive at the pinned commit; kept as a guard)."""
    for row in state.get("call_log") or []:
        if isinstance(row, dict):
            for k in HEAVY:
                row.pop(k, None)
    return state


def first_preview_atom(state):
    """The id of the first atom with a page output (an anchor) or a document section, else None."""
    for w in state.get("workflows") or []:
        for a in w.get("atoms") or []:
            ao = a.get("agent_output") or {}
            if ao.get("anchor") or ao.get("kind") == "doc":
                return a.get("id")
    return None


def pack(obj):
    """gzip JSON with a header that does not depend on the day or the Python (mtime 0, the OS byte GzipFile always writes)."""
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=9, mtime=0) as g:
        g.write(raw)
    return buf.getvalue()


def write_one(folder, name, obj):
    folder.mkdir(parents=True, exist_ok=True)
    data = pack(obj)
    (folder / (name + ".json.gz")).write_bytes(data)
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def capture_endpoint(port, name, run):
    q = {"state": "api/state?since=0", "map": "api/map", "board": "api/board", "artifacts": "api/artifacts",
         "docs": "api/docs", "audits": "api/audits", "refs": "api/refs", "runs": "api/runs"}[name]
    if run and name in PER_RUN:
        q += ("&" if "?" in q else "?") + "run=" + urllib.parse.quote(run)
    code, body = get(port, q)
    if code != 200:
        raise RuntimeError("%s answered %s" % (q, code))
    return json.loads(body.decode("utf-8"))


def capture_all(port, runs, out):
    """Ask the server for every endpoint of every run and of the idle live state; returns the SOURCE.json rows."""
    rows = []
    for rid, why in list(runs) + [(None, "the live run before anything is said: the page's start screen")]:
        folder = out / (rid or IDLE)
        files = {}
        state = None
        for name in PER_RUN + PLAIN:
            got = capture_endpoint(port, name, rid)
            if name == "state":
                state = drop_heavy(got)
                got = state
            files[name] = write_one(folder, name, got)
        atom = first_preview_atom(state or {})
        if atom:
            q = "api/preview?atom=%s" % urllib.parse.quote(atom) + ("&run=" + urllib.parse.quote(rid) if rid else "")
            code, body = get(port, q)
            if code == 200:
                files["preview"] = write_one(folder, "preview", json.loads(body.decode("utf-8")))
        rows.append({"id": rid or IDLE, "why": why, "preview_atom": atom, "files": files})
    return rows


def serve(proto_dir, runs_dir, repo, log):
    """Start the extracted j2_server.py; returns (process, port)."""
    venv = Path(repo) / "venv" / "bin" / "python"
    python = str(venv) if venv.exists() else "python3"
    port = free_port()
    env = dict(os.environ, J2_RUNS_DIR=str(runs_dir), STUDIO_MOCK="1")
    proc = subprocess.Popen([python, "j2_server.py", "--port", str(port), "--no-browser"], cwd=str(proto_dir), env=env,
                            stdout=log, stderr=subprocess.STDOUT)
    for _ in range(100):
        if proc.poll() is not None:
            raise RuntimeError("the prototype's server exited with %s (see its log)" % proc.returncode)
        try:
            if get(port, "api/runs")[0] == 200:
                return proc, port
        except RuntimeError:
            pass
        time.sleep(0.3)
    proc.terminate()
    raise RuntimeError("the prototype's server did not start")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--prototype", help="the prototype's checkout (default: $J2_PROTOTYPE, else the path PINNED.json records)")
    ap.add_argument("--out", default=str(OUT), help="where the fixtures go (default test_fixtures/j2ui/captured)")
    ap.add_argument("--runs", nargs="*", help="run ids to keep instead of the default four")
    ap.add_argument("--keep", action="store_true", help="keep the scratch folder and say where it is")
    a = ap.parse_args(argv)

    pin = pinned()
    commit = (pin.get("source") or {}).get("commit")
    path = a.prototype or os.environ.get("J2_PROTOTYPE") or (pin.get("source") or {}).get("path")
    if not commit:
        print("capture_j2_fixtures: j2ui_assets/PINNED.json has no source.commit: run scripts/sync_j2_ui.py first", file=sys.stderr)
        return 1
    repo = Path(os.path.expanduser(path)) if path else None
    if repo is None or not (repo / ".git").exists():
        print("capture_j2_fixtures: the prototype is not on this machine (set J2_PROTOTYPE); the committed fixtures stand")
        return 0
    if not (repo / "runs").is_dir():
        print("capture_j2_fixtures: %s has no runs/ folder; the committed fixtures stand" % repo)
        return 0
    try:
        git(repo, "cat-file", "-e", commit + "^{commit}")
    except RuntimeError:
        print("capture_j2_fixtures: the pinned commit %s is not in %s; the committed fixtures stand" % (commit[:12], repo))
        return 0

    runs = [(r, dict(RUNS).get(r, "a run chosen on the command line")) for r in a.runs] if a.runs else list(RUNS)
    missing = [r for r, _ in runs if not (repo / "runs" / r).is_dir()]
    if missing:
        print("capture_j2_fixtures: these runs are not in %s/runs: %s; the committed fixtures stand" % (repo, ", ".join(missing)))
        return 0

    scratch = Path(tempfile.mkdtemp(prefix="j2ui-capture-")).resolve()
    out = Path(a.out).resolve()
    try:
        refuse_inside(repo, scratch, out)
    except Refused as exc:
        shutil.rmtree(scratch, ignore_errors=True)
        print("capture_j2_fixtures: " + str(exc), file=sys.stderr)
        return 1

    before = status_of(repo)
    proc = None
    try:
        proto_dir, runs_dir = scratch / "proto", scratch / "runs"
        proto_dir.mkdir()
        runs_dir.mkdir()
        archive = subprocess.Popen(["git", "-C", str(repo), "archive", commit], stdout=subprocess.PIPE)
        untar = subprocess.run(["tar", "-x", "-C", str(proto_dir)], stdin=archive.stdout, check=False)
        archive.stdout.close()
        if archive.wait() != 0 or untar.returncode != 0:
            raise RuntimeError("git archive %s failed" % commit[:12])
        for rid, _ in runs:
            shutil.copytree(repo / "runs" / rid, runs_dir / rid)
        with open(scratch / "server.log", "wb") as log:
            proc, port = serve(proto_dir, runs_dir, repo, log)
            if out.exists():                      # only a folder of this script's own (or an empty one) is replaced
                if (out / "SOURCE.json").exists() or not any(out.iterdir()):
                    shutil.rmtree(out)
                else:
                    raise RuntimeError("%s exists and is not a fixtures folder of this script: not replaced" % out)
            rows = capture_all(port, runs, out)
        source = {"schema": SCHEMA, "commit": commit, "prototype": "J2_Prototype", "mode": "STUDIO_MOCK=1, J2_RUNS_DIR=a scratch copy",
                  "runs": rows}
        (out / "SOURCE.json").write_text(json.dumps(source, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except (RuntimeError, OSError, ValueError) as exc:
        print("capture_j2_fixtures: " + str(exc), file=sys.stderr)
        return 1
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        if a.keep:
            print("scratch kept at " + str(scratch))
        else:
            shutil.rmtree(scratch, ignore_errors=True)

    after = status_of(repo)
    if after != before:
        print("capture_j2_fixtures: the prototype's `git status --short` changed:\n--- before\n%s--- after\n%s" % (before, after), file=sys.stderr)
        return 1
    total = sum(f["bytes"] for r in rows for f in r["files"].values())
    print("captured %d runs and the idle state: %d files, %d bytes; prototype status unchanged" %
          (len(rows) - 1, sum(len(r["files"]) for r in rows), total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
