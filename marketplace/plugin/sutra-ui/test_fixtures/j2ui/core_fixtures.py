"""core_fixtures.py -- the departments the j2ui-core tests read (UI port, package j2ui-core).

The helpers are test_functions_view.py's (`mods`, `_cycle`, `_ask`, `_thread`, `_run`), so a department here is born the way the
app makes one (website_dept.create) and then set to the state under test; `born` founds an organisation and lets Root set
a department up, as a person does (the recipe of the UI port's reference probe). Import the fixtures into a test module:

    from test_fixtures.j2ui.core_fixtures import *      # noqa: F401,F403  (mods, born, tick)
"""
import importlib
import time
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

REF = "dref-j2c0001"
WEBSITE = "Build a website that teaches algebra to Class 8 students"
__all__ = ["REF", "WEBSITE", "mods", "born", "tick", "cycle", "ask", "thread", "run", "post", "event", "rewind"]


@pytest.fixture
def mods(tmp_path, monkeypatch):
    """Fresh records homes, the modules reloaded on them, one runtime-2 website department at REF, every j2ui cache empty."""
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    for var, sub in (("SUTRA_UI_PROPOSALS", "proposals"), ("SUTRA_UI_ROUTINES", "routines"), ("SUTRA_UI_RUNS", "runs")):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv(var, str(tmp_path / sub))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.setenv("J2_FLOW_V1", "1")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME", raising=False)
    import engine_runtime as R
    import functions_view as F
    import j2_runtime as J
    import website_dept as W
    for m in (W, R, J, F):
        importlib.reload(m)
    import j2ui_common as C
    C.reset_caches()
    W.create(REF, "City Care Hospital Website", None, kind="website")
    yield SimpleNamespace(W=W, R=R, J=J, F=F, C=C, ref=REF, home=tmp_path)
    C.reset_caches()


@pytest.fixture
def born(mods, monkeypatch):
    """A department as a person makes one: found the organisation, say the words, Root sets it up. make(words, org) -> ref."""
    monkeypatch.setenv("J1_FLOW_V1", "1")
    import founding
    import org2_apply
    import placement_engine as E
    for m in (E, org2_apply, founding):
        importlib.reload(m)
    if not E.active_roots(E.load_domains()):
        E.mint_domain(None, "Sutra", ["Sutra"], "T-local", origin="operator-request")
    W = mods.W

    def make(words=WEBSITE, org="Acme Learning", settle=True):
        root = founding.found_structure(org, owner="Sankalp")["root"]
        W.owner_ask(root, words)
        W.run_until_idle(root, limit=300)
        child = next(d for d in W.list_depts() if d.get("parent") == root)["ref"]
        if settle:
            W.run_until_idle(child, limit=300)
        make.root = root
        return child
    make.root = None
    return make


@pytest.fixture
def tick(mods, monkeypatch):
    """A clock that moves one second at every W.now(): every record is stamped in the order it was written, so the order
    by time is the order of writing (records are stamped to the second, and a test runs inside one)."""
    t = [datetime.now().astimezone().replace(microsecond=0) - timedelta(minutes=30)]

    def now():
        t[0] += timedelta(seconds=1)
        return t[0].isoformat(timespec="seconds")
    monkeypatch.setattr(mods.W, "now", now)
    return now


def cycle(m, state, step, ref=REF, **more):
    row = {"cycle_id": "cycle-test", "step": step, "journey": "J2", "state": state, "open_ask": None, "workflow": [],
           "repairs": 0, "updated_at": m.W.now()}
    row.update(more)
    m.W._write(m.W.ddir(ref) / "j2-state.json", row)
    return row


def ask(m, kind="publish", ref=REF, **more):
    row = {"id": more.pop("id", "a-" + kind), "kind": kind, "engine": more.pop("engine", "Publish"),
           "text": more.pop("text", "Publish: go live for the first time"), "status": "pending", "created": m.W.now()}
    row.update(more)
    m.W._put_ask(ref, row)
    return row


def post(m, src, dst, act, payload, ref=REF, thread="x-t1", about=None, n=None):
    """A row on the department's board, as engine_runtime.post writes it (without the thread's bookkeeping)."""
    rows = m.R.board(ref)
    n = n or len(rows) + 1
    row = {"n": n, "src": src, "dst": [dst] if isinstance(dst, str) else list(dst), "msg_type": act, "thread": thread, "hop": 1,
           "about": about, "payload": payload, "ack_id": None, "by": None, "at": m.W.now()}
    m.R._append(ref, "board.jsonl", row)
    return row


def thread(m, src, dst, act, word, state="working", tid="x-t1", ref=REF, **payload):
    """A thread on the board whose latest post is src's, as test_functions_view._thread writes them."""
    row = post(m, src, dst, act, dict({"word": word}, **payload), ref=ref, thread=tid)
    ths = [t for t in m.R.threads(ref) if t["id"] != tid]
    ths.append({"id": tid, "opened_by": src, "with": [dst], "topic": word, "protocol": "propose" if act == "propose" else "inform",
                "decider": dst, "bounds": dict(m.R.BOUNDS), "default": "cancel", "state": state, "hops": 1, "spent": 0.0,
                "age_s": 0.0, "opened": m.W.now(), "closed": None, "outcome": None})
    m.R._save_threads(ref, ths)
    return row


def run(m, engine, status="running", what="Write a page", system=False, ref=REF, **more):
    row = {"id": "r-" + engine.lower() + status, "engine": engine, "system": system, "slot": more.pop("slot", "%s@x.v1" % engine),
           "status": status, "started": more.pop("started", m.W.now()), "ended": None if status == "running" else m.W.now(),
           "what": what, "wrote": more.pop("wrote", None), "chain": None, "spend": {"calls": 0, "usd": 0.0}, "retries": 0}
    row.update(more)
    m.W._put_run(ref, row)
    return row


def event(m, action, actor="Root", recipient="Adaptation", step=5, summary=None, ref=REF, key=None, **more):
    """One ledger event of the cycle `cycle` set (j2_runtime.note)."""
    return m.J.note(ref, step, actor, recipient, action, more.pop("state", "complete"), summary or action,
                    key or "%s-%d" % (action, len(m.J.events(ref)) + 1), **more)


def rewind(path, seconds):
    """Age a file's mtime (the signature reads it)."""
    st = path.stat()
    import os
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns - int(seconds * 1e9)))
    return time.time()
