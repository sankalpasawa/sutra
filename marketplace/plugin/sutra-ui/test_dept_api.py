"""test_dept_api.py -- the department screen's reads (dept_api.py) on an
isolated registry, proposal store, routine store, shadow home and workdir.

The fixture idiom is test_org2_api.py's `_fresh()` (SUTRA_NATIVE_HOME at a
temporary directory, every affected module popped and reloaded so the isolated
registry is the only one bound), widened to the four other stores dept_api
reads: proposals, routines, the shadow home behind MissionStore, and the
configured workdir that holds the atom ledger. Every environment variable and
every reloaded module is restored on the way out, so a whole-directory pytest
run cannot leak this test's stores into another module's.

Run: .venv/bin/python -m pytest test_dept_api.py -q
"""
import contextlib
import importlib
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

_ENV = ("SUTRA_NATIVE_HOME", "SUTRA_UI_PROPOSALS", "SUTRA_UI_ROUTINES",
        "SUTRA_UI_RUNS", "SUTRA_SHADOW_HOME", "SUTRA_UI_SETTINGS",
        "SUTRA_UI_WORKDIR_ROOT")
_RELOAD = ("placement_engine", "dept_api")


@contextlib.contextmanager
def _fresh():
    """dept_api + every store it reads, bound to one temporary directory."""
    import tempfile
    keep = {k: os.environ.get(k) for k in _ENV}
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        for sub in ("proposals", "routines", "runs", "shadow", ".sutra"):
            (tmp / sub).mkdir(parents=True, exist_ok=True)
        os.environ["SUTRA_NATIVE_HOME"] = str(tmp)
        os.environ["SUTRA_UI_PROPOSALS"] = str(tmp / "proposals")
        os.environ["SUTRA_UI_ROUTINES"] = str(tmp / "routines")
        os.environ["SUTRA_UI_RUNS"] = str(tmp / "runs")
        os.environ["SUTRA_SHADOW_HOME"] = str(tmp / "shadow")
        os.environ["SUTRA_UI_SETTINGS"] = str(tmp / "settings.json")
        os.environ["SUTRA_UI_WORKDIR_ROOT"] = str(tmp)
        (tmp / "settings.json").write_text(
            json.dumps({"workdir": str(tmp)}), encoding="utf-8")
        for m in _RELOAD:
            sys.modules.pop(m, None)
        import providers
        importlib.reload(providers)
        import dept_api as M          # puts ../lib on sys.path for the next line
        import placement_engine as E
        importlib.reload(E)
        importlib.reload(M)
        try:
            yield M, E, tmp
        finally:
            for m in _RELOAD:
                sys.modules.pop(m, None)
            for k, v in keep.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            importlib.reload(providers)


def _tree(E, cwd):
    """Root Co, the machine node Desktop carrying `cwd`, an organisation A and
    A's child A1 -- the same shape test_org2_api._tree builds, plus the cwd the
    department screen's filters resolve through."""
    root, _ = E.mint_domain(None, "Co", ["root"], "T-local", origin="test")
    desk, _ = E.mint_domain(root, "Desktop", ["desk"], "T-local",
                            origin="project-import")
    E.set_domain_fields(desk, cwd=str(cwd))
    a, _ = E.mint_domain(desk, "A", ["a"], "T-local", origin="test")
    a1, _ = E.mint_domain(a, "A1", ["a1"], "T-local", origin="test")
    return root, desk, a, a1


# ------------------------------------------------------------------ S1, S4 --

def test_ping_is_ok():
    with _fresh() as (M, _E, _tmp):
        assert M.ping() == {"ok": True}


def test_forbidden_scan_covers_this_module():
    """BUILD-PLAN risk 5: test_forbidden_calls.py's alias detection only checks
    a file that declares `import placement_engine as <alias>`. If dept_api.py
    ever stops declaring one the scan passes vacuously -- fail loudly here."""
    import test_forbidden_calls as F
    text = (HERE / "dept_api.py").read_text(encoding="utf-8")
    assert F._engine_aliases(text), (
        "dept_api.py no longer declares `import placement_engine as <alias>`; "
        "the forbidden-mutator grep would silently check nothing")
    assert (HERE / "dept_api.py") in F.FILES_UNDER_TEST, \
        "dept_api.py must stay in FILES_UNDER_TEST (BUILD-PLAN S3)"


# ---------------------------------------------------------------------- S7 --

def test_cwd_inherits_the_machine_rows_working_directory():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        rows = E.load_domains()
        want = os.path.realpath(str(tmp))
        assert M._dept_cwd(desk, rows) == want
        assert M._dept_cwd(a, rows) == want, "an organisation under the machine inherits it"
        assert M._dept_cwd(a1, rows) == want, "so does a leaf two levels down"


def test_cwd_is_none_above_the_machine():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        assert M._dept_cwd(root, E.load_domains()) is None, \
            "the root carries no cwd and inherits none (PRD F-3)"


def test_cwd_of_the_department_itself_wins_over_the_ancestors():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        own = tmp / "own"
        own.mkdir()
        E.set_domain_fields(a1, cwd=str(own))
        rows = E.load_domains()
        assert M._dept_cwd(a1, rows) == os.path.realpath(str(own))
        assert M._dept_cwd(a, rows) == os.path.realpath(str(tmp)), "a sibling is unaffected"


def test_cwd_prefix_test_refuses_an_empty_path():
    """realpath("") is the process's own cwd; an empty touch must not match."""
    with _fresh() as (M, _E, tmp):
        cwd = os.path.realpath(str(tmp))
        assert M._under(cwd, str(tmp / "a" / "b")) is True
        assert M._under(cwd, "") is False
        assert M._under(cwd, None) is False
        assert M._under(None, str(tmp)) is False
        assert M._under(cwd, str(tmp) + "-sibling") is False, "a name prefix is not a path prefix"


def _routine(rid, cwd, enabled=True, description="Nightly sweep"):
    """A routine record written through routines.save(), the module's own
    writer. routines.create() installs a launchd job and a runner script, which
    a test must never do; validate_new() confines cwd to $HOME, which a
    temporary directory is not. The shape is validate_new()'s own output."""
    import routines
    rec = {"schema": routines.SCHEMA, "id": rid, "description": description,
           "prompt": "sweep the department", "cwd": str(cwd), "model": "",
           "permission_mode": "plan", "opts": {"max_budget_usd": 1.0},
           "schedule": {"preset": "manual", "cron": None, "human": "manual"},
           "enabled": enabled, "created_at": routines.now_iso(),
           "updated_at": routines.now_iso(), "prompt_sha256": "",
           "claude_bin": "", "auto_disabled": None}
    routines.save(rec)
    return rec


# ---------------------------------------------------------------------- S9 --

def test_now_lists_an_ask_whose_routine_sits_under_the_department():
    with _fresh() as (M, E, tmp):
        import proposals
        root, desk, a, a1 = _tree(E, tmp)
        inside = tmp / "inside"
        inside.mkdir()
        outside = Path(os.path.realpath(str(tmp.parent))) / ("out-" + tmp.name)
        outside.mkdir()
        try:
            _routine("in-here", inside)
            _routine("elsewhere", outside)
            proposals.create("routine.update", {"id": "in-here"}, "Pause the sweep")
            proposals.create("routine.update", {"id": "elsewhere"}, "Pause the other sweep")
            out = M.now(a)
            assert [r["summary"] for r in out["asks"]] == ["Pause the sweep"]
            row = out["asks"][0]
            assert row["kind"] == "routine.update"
            assert row["window_ms"] == proposals.TTL_SECONDS * 1000
            assert row["default"] == "Nothing happens"
            assert row["irreversible"] is False
            assert row["created_ms"] > 0
            assert out["decidable"] is True and out["skipped"] == 0
        finally:
            for f in outside.glob("*"):
                f.unlink()
            outside.rmdir()


def test_now_lists_an_org_ask_naming_the_department_or_a_child():
    with _fresh() as (M, E, tmp):
        import proposals
        root, desk, a, a1 = _tree(E, tmp)
        proposals.create("org.charter", {"ref": a1, "purpose": "x"}, "Write the goal of A1")
        proposals.create("org.rename", {"ref": root, "name": "Other"}, "Rename the root")
        assert [r["summary"] for r in M.now(a)["asks"]] == ["Write the goal of A1"]
        assert [r["summary"] for r in M.now(a1)["asks"]] == ["Write the goal of A1"]


def test_now_marks_the_two_outbound_kinds_irreversible():
    with _fresh() as (M, E, tmp):
        import proposals
        root, desk, a, a1 = _tree(E, tmp)
        proposals.create("pr.create", {"cwd": str(tmp / "work")},
                         "Open a pull request")
        (tmp / "work").mkdir()
        out = M.now(a)
        assert [r["irreversible"] for r in out["asks"]] == [True]


def test_now_is_empty_when_the_department_has_no_cwd():
    """A9 + PRD F-3: above the machine nothing can be attributed, and the card
    says so with one quiet line rather than showing another department's work."""
    with _fresh() as (M, E, tmp):
        import proposals
        root, desk, a, a1 = _tree(E, tmp)
        _routine("in-here", tmp)
        proposals.create("routine.update", {"id": "in-here"}, "Pause the sweep")
        assert M._dept_cwd(root, E.load_domains()) is None
        assert M.now(root)["asks"] == []


def test_now_404s_on_an_unknown_department():
    import fastapi
    with _fresh() as (M, E, tmp):
        _tree(E, tmp)
        with __import__("pytest").raises(fastapi.HTTPException) as exc:
            M.now("no-such-ref")
        assert exc.value.status_code == 404


def _ledger(tmp, lines):
    p = tmp / ".sutra" / "atom-ledger.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(
        (l if isinstance(l, str) else json.dumps(l)) + "\n" for l in lines),
        encoding="utf-8")
    return p


# --------------------------------------------------------------------- S10 --

def test_running_lists_open_atom_rows_touching_the_department():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        (tmp / "here").mkdir()
        _ledger(tmp, [
            {"sid": "s-1", "id": "a-1", "goal": "Land the list column",
             "status": "open", "touches": ["here/"], "ts": "200"},
            {"sid": "s-2", "id": "a-2", "goal": "Somewhere else",
             "status": "open", "touches": ["/tmp/not-here"], "ts": "300"},
            {"sid": "s-3", "id": "a-3", "goal": "Already done",
             "status": "closed", "touches": ["here/"], "ts": "100"},
            "{ this line is not json",
        ])
        out = M.running(a)
        assert [r["id"] for r in out["running"]] == ["a-1"]
        assert out["running"][0]["goal"] == "Land the list column"
        assert out["running"][0]["touches"] == ["here/"], "the touch is shown as written"
        assert out["running"][0]["ts"] == 200
        assert out["skipped"] == 1, "a malformed line is counted, not fatal (PRD J)"


def test_running_reads_the_last_row_per_work_item():
    """The ledger is append-only: a work item opened and then closed is not
    running, however many open rows precede the closing one."""
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _ledger(tmp, [
            {"sid": "s-1", "id": "a-1", "goal": "One", "status": "open", "touches": ["x"], "ts": "1"},
            {"sid": "s-1", "id": "a-1", "goal": "One", "status": "closed", "touches": ["x"], "ts": "2"},
            {"sid": "s-1", "id": "a-2", "goal": "Two", "status": "closed", "touches": ["x"], "ts": "3"},
            {"sid": "s-1", "id": "a-2", "goal": "Two", "status": "open", "touches": ["x"], "ts": "4"},
        ])
        assert [r["id"] for r in M.running(a)["running"]] == ["a-2"]


def test_running_is_empty_with_no_ledger_and_never_raises():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        assert M.running(a) == {"running": [], "skipped": 0}
        assert M.running(root) == {"running": [], "skipped": 0}, "no cwd, no attribution"


def test_running_is_empty_when_the_workdir_setting_is_unusable():
    """BUILD-PLAN risk 2: a fresh install has no workdir configured. The card is
    quiet; the route does not 500 the way org_api's automation read 400s."""
    with _fresh() as (M, E, tmp):
        import providers
        root, desk, a, a1 = _tree(E, tmp)
        _ledger(tmp, [{"sid": "s", "id": "a-1", "goal": "g", "status": "open",
                       "touches": ["."], "ts": "1"}])
        (tmp / "settings.json").write_text(json.dumps({"workdir": "/nope/gone"}),
                                           encoding="utf-8")
        importlib.reload(providers)
        assert M._workdir() is None
        assert M.running(a)["running"] == []


def _mission(tmp, mid, state, objective, target_session=None):
    """One row in MissionStore's file-per-mission store. Written as a file
    rather than through create()+transition(), which would drive the whole
    state machine and append ledger rows for a fixture."""
    d = tmp / "shadow" / "missions"
    d.mkdir(parents=True, exist_ok=True)
    (d / (mid + ".json")).write_text(json.dumps({
        "id": mid, "objective": objective, "state": state,
        "target_session": target_session, "template": "task",
        "turns_used": 0, "max_turns": 10}), encoding="utf-8")


# --------------------------------------------------------------------- S11 --

def test_waits_lists_queued_and_blocked_tasks_of_a_session_that_worked_here():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        (tmp / "here").mkdir()
        _ledger(tmp, [{"sid": "s-here", "id": "a-1", "goal": "g", "status": "closed",
                       "touches": ["here/"], "ts": "1"}])
        _mission(tmp, "m-1", "queued", "Write the release note", "s-here")
        _mission(tmp, "m-2", "blocked", "Waiting on the founder", "s-here")
        _mission(tmp, "m-3", "running", "Already moving", "s-here")
        _mission(tmp, "m-4", "queued", "Another department's", "s-elsewhere")
        out = M.waits(a)
        assert sorted(r["id"] for r in out["waits"]) == ["m-1", "m-2"]
        assert sorted(r["state"] for r in out["waits"]) == ["blocked", "queued"]
        assert out["waits"][0]["objective"]


def test_waits_is_empty_when_no_session_has_touched_the_department():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _mission(tmp, "m-1", "queued", "Unattributable", "s-nowhere")
        assert M.waits(a) == {"waits": [], "skipped": 0}
        assert M.waits(root) == {"waits": [], "skipped": 0}, "no cwd, no attribution"


def test_waits_states_are_the_engines_own_words():
    """The PRD says 'waiting'; mission_engine has no such state. queued and
    blocked are the two it does have (LLD section 8 correction)."""
    with _fresh() as (M, _E, _tmp):
        import mission_engine
        assert M.WAIT_STATES == ("queued", "blocked")
        for s in M.WAIT_STATES:
            assert s in mission_engine.TRANSITIONS, "%s is a real mission state" % s


def test_writes_only_through_proposals():
    """R2: the read side files nothing. dept_api never calls a routines mutator
    and never writes a placement; the only create() it may ever name is
    proposals.create."""
    text = (HERE / "dept_api.py").read_text(encoding="utf-8")
    for forbidden in ("routines.update(", "routines.create(", "routines.delete(",
                      "E.write_placement(", "E.mint_domain("):
        assert forbidden not in text, "dept_api.py calls %s" % forbidden
