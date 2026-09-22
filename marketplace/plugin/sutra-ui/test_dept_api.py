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


def _charter(E, ref, purpose, invariants=(), constraints=(), authority=None,
             milestones=(), title="A Charter", kind="standing",
             done_when=(), rules=(), person=""):
    """A charter body written the way fixture_seed.py:465-487 and
    org_import.py:600-620 write one -- composed, hashed with charter_id_of,
    saved under its own id -- because `invariants`, `constraints` and
    `authority` are body-only fields that mint_charter_stub hard-codes empty
    (placement_engine.py:659, 664) and NO writer in the system fills. A test
    that used mint_charter_stub could therefore never exercise the rules list
    or the charter-owner branch at all."""
    body = {
        "title": title[:60], "domain_ref": ref, "purpose": purpose,
        "scope_in": [], "scope_out": [], "obligations": [],
        "obligations_empty_reason": "test fixture",
        "invariants": list(invariants), "success_metrics": [],
        "constraints": list(constraints),
        "acl": [{"tenant_id": "T-local", "access": "rw"}],
        "cutover_contract": None, "authority": authority or {},
        "termination": {}, "tenant_id": "T-local", "kind": kind,
        "supersedes": None, "schema": E.CHARTER_SCHEMA,
    }
    cid = E.charter_id_of(body)
    body["id"] = cid
    (Path(E.CHARTERS) / (cid + ".json")).write_text(
        json.dumps(body, sort_keys=True, indent=2), encoding="utf-8")
    sc = E._sidecar_default(1)
    sc["milestones"] = [dict(m) for m in milestones]
    # DS-1/DS-2: the three sidecar fields slice G added. Written here the way
    # the org.charter proposal writes them, so a reader test does not have to
    # drive the whole request path to exercise the card.
    sc["done_when"] = list(done_when)
    sc["rules"] = [dict(r) for r in rules]
    sc["person"] = person
    E.save_sidecar(cid, sc)
    return cid


# --------------------------------------------------------------------- S23 --

def test_identity_reads_the_goal_the_done_line_and_the_rules():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _charter(E, a, "Own the operator's experience of Sutra Desktop.",
                 invariants=["A mock is the app's own markup"],
                 constraints=["Never a third AI in one task"],
                 milestones=[{"label": "v1", "status": "now",
                              "done_when": "every screen reads its own record"},
                             {"label": "v2", "status": "planned", "done_when": ""}])
        out = M.identity(a)
        assert out["goal"] == "Own the operator's experience of Sutra Desktop."
        assert out["done"] == "every screen reads its own record.", out["done"]
        assert out["rules"] == [
            {"tag": "always", "text": "A mock is the app's own markup"},
            {"tag": "always", "text": "Never a third AI in one task"}]
        assert set(r["tag"] for r in out["rules"]) <= {"go", "ask", "refuse", "always"}


def test_identity_has_no_goal_when_the_department_has_no_charter():
    """A12: the card reads "No goal yet" off a null, and never off a guess."""
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        out = M.identity(a1)
        assert out["goal"] is None
        assert out["done"] is None
        assert out["rules"] == []


def test_identity_ignores_a_retired_charter_and_prefers_the_standing_one():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        old = _charter(E, a, "The old goal.", title="Old", kind="standing")
        sc = E.load_sidecar(old)
        sc["status"] = "retired"
        E.save_sidecar(old, sc)
        _charter(E, a, "The goal that holds.", title="New", kind="standing")
        assert M.identity(a)["goal"] == "The goal that holds."


def test_identity_404s_on_an_unknown_department():
    import fastapi
    with _fresh() as (M, E, tmp):
        _tree(E, tmp)
        with __import__("pytest").raises(fastapi.HTTPException) as exc:
            M.identity("no-such-ref")
        assert exc.value.status_code == 404


# --------------------------------------------------------------------- S28 --

def test_identity_owner_is_the_charter_authority_when_one_is_written():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _charter(E, a, "A goal.", authority={"name": "Meera"})
        assert M.identity(a)["owner"] == {"source": "charter", "name": "Meera"}


def test_identity_owner_falls_back_to_the_git_user(monkeypatch):
    """A11 + F-12: `authority` is {} on every charter any writer mints, so the
    git user is the owner the card actually shows today."""
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _charter(E, a, "A goal.")
        monkeypatch.setattr(M, "_git_user", lambda cwd: "Sankalp Asawa")
        assert M.identity(a)["owner"] == {"source": "git", "name": "Sankalp Asawa"}
        monkeypatch.setattr(M, "_git_user", lambda cwd: "")
        assert M.identity(a)["owner"] == {"source": "none", "name": None}


def test_identity_owner_never_raises_on_git():
    """The real reader, on folders that are not checkouts: a string every
    time, never an exception, and an unusable cwd is simply ignored."""
    with _fresh() as (M, _E, tmp):
        assert isinstance(M._git_user(str(tmp)), str)
        assert isinstance(M._git_user("/no/such/folder"), str)
        assert isinstance(M._git_user(None), str)


def test_identity_budget_is_the_stored_limits_and_nothing_when_unset():
    with _fresh() as (M, E, tmp):
        import mission_engine
        root, desk, a, a1 = _tree(E, tmp)
        b = M.identity(a)["budget"]
        assert b["running_at_once"] is None, "A11: nothing set reads as no reading"
        assert b["turn_budget"] == {}
        assert b["ceiling"] == mission_engine.RUNNING_CEILING
        Path(mission_engine.limits_path()).parent.mkdir(parents=True, exist_ok=True)
        Path(mission_engine.limits_path()).write_text(
            json.dumps({"running_at_once": 3, "turn_budget": {"task": 12}}),
            encoding="utf-8")
        b = M.identity(a)["budget"]
        assert b["running_at_once"] == 3
        assert b["turn_budget"] == {"task": 12}


def test_identity_budget_survives_a_hand_edited_limits_file():
    with _fresh() as (M, E, tmp):
        import mission_engine
        root, desk, a, a1 = _tree(E, tmp)
        Path(mission_engine.limits_path()).parent.mkdir(parents=True, exist_ok=True)
        Path(mission_engine.limits_path()).write_text("{ not json",
                                                      encoding="utf-8")
        assert M.identity(a)["budget"]["running_at_once"] is None


# --------------------------------------------------------------------- S29 --

def test_identity_owner_chat_carries_the_ask_and_the_answer_as_turns():
    with _fresh() as (M, E, tmp):
        import proposals
        root, desk, a, a1 = _tree(E, tmp)
        _charter(E, a, "A goal.", authority={"name": "Meera"})
        p1 = proposals.create("org.charter", {"ref": a1, "purpose": "x"},
                              "Write the goal of A1")
        time.sleep(0.002)          # two asks in one millisecond tie; separate them
        proposals.create("org.rename", {"ref": a1, "name": "A2"}, "Rename A1")
        proposals.decide(p1["id"], False)
        rows = M.identity(a)["chats"]["owner"]
        assert [(r["who"], r["to"], r["line"]) for r in rows] == [
            ("Identity", "Meera", "Write the goal of A1"),
            ("Meera", "Identity", "Refused."),
            ("Identity", "Meera", "Rename A1"),
        ], rows
        assert all("row" in r and r["row"]["id"].startswith("p-") for r in rows)
        assert rows[0]["at"], "the ask carries the record's own stamp"
        assert rows[1]["at"], "so does the answer"


def test_identity_owner_chat_shows_what_went_ahead_without_the_owner():
    """F-13: the permission gate's log is the only decision record there is,
    and it carries allow rows only. The pattern it matched is path-shaped and
    stays out of the line (A28)."""
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        d = tmp / ".enforcement"
        d.mkdir(parents=True, exist_ok=True)
        (d / "permission-gate.jsonl").write_text("".join(json.dumps(r) + "\n" for r in [
            {"ts": 100, "tool": "Bash", "pattern": "/Users/x/**", "decision": "allow"},
            {"ts": 101, "tool": "Read", "pattern": "/Users/x/**", "decision": "deny"},
        ]), encoding="utf-8")
        rows = M.identity(a)["chats"]["owner"]
        assert [(r["who"], r["mode"], r["line"]) for r in rows] == [
            ("Identity", "think", "Went ahead without asking: Bash")]
        assert "/Users/" not in rows[0]["line"]
        assert rows[0]["row"]["pattern"] == "/Users/x/**", "the raw row keeps it"


def test_identity_chats_are_empty_with_nothing_to_show():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        out = M.identity(a)
        assert out["chats"]["owner"] == []
        assert out["chats"]["adaptation"] == []


def test_identity_adaptation_chat_is_the_proposal_rows():
    with _fresh() as (M, E, tmp):
        import proposals
        root, desk, a, a1 = _tree(E, tmp)
        p = proposals.create("org.charter", {"ref": a}, "Write the goal of A")
        proposals.decide(p["id"], False)
        rows = M.identity(a)["chats"]["adaptation"]
        assert [(r["who"], r["to"], r["line"]) for r in rows] == [
            ("Adaptation", "Identity", "Write the goal of A"),
            ("Identity", "Adaptation", "Refused."),
        ]
        assert rows[0]["row"]["kind"] == "org.charter", \
            "A29: the word charter reaches the screen only in a raw row"


def test_identity_chat_leaves_an_open_ask_unanswered():
    with _fresh() as (M, E, tmp):
        import proposals
        root, desk, a, a1 = _tree(E, tmp)
        proposals.create("org.charter", {"ref": a}, "Write the goal of A")
        rows = M.identity(a)["chats"]["adaptation"]
        assert len(rows) == 1, "no verdict turn until there is a verdict"
        assert rows[0]["row"]["status"] == "pending"


# --------------------------------------------------------------------- S35 --

def _aged(pid, days):
    """Move a proposal's own clock back. proposals.create() stamps `now`, and a
    seven-day window cannot be exercised without a row outside it."""
    import proposals
    rec = proposals.get(pid)
    rec["created_ms"] = rec["created_ms"] - int(days * 24 * 3600 * 1000)
    proposals._write(rec)
    return rec


def test_adaptation_reads_three_of_a_kind_as_one_pattern():
    with _fresh() as (M, E, tmp):
        import proposals
        root, desk, a, a1 = _tree(E, tmp)
        for _ in range(3):
            proposals.create("org.charter", {"ref": a1}, "Write the goal of A1")
            time.sleep(0.002)
        proposals.create("org.rename", {"ref": a1, "name": "A2"}, "Rename A1")
        out = M.adaptation(a)
        assert [(p["kind"], p["summary"], p["count"]) for p in out["patterns"]] == [
            ("org.charter", "Write the goal of A1", 3)], out["patterns"]
        assert out["patterns"][0]["since_ms"] > 0, "the pattern says when it started"


def test_adaptation_does_not_pattern_two_of_a_kind():
    with _fresh() as (M, E, tmp):
        import proposals
        root, desk, a, a1 = _tree(E, tmp)
        for _ in range(2):
            proposals.create("org.charter", {"ref": a1}, "Write the goal of A1")
            time.sleep(0.002)
        assert M.adaptation(a)["patterns"] == [], "A13: two is not a pattern"


def test_adaptation_pattern_window_is_seven_days():
    with _fresh() as (M, E, tmp):
        import proposals
        root, desk, a, a1 = _tree(E, tmp)
        ids = []
        for _ in range(3):
            ids.append(proposals.create("org.charter", {"ref": a1}, "Write the goal of A1")["id"])
            time.sleep(0.002)
        assert M.adaptation(a)["patterns"][0]["count"] == 3
        _aged(ids[0], 8)
        assert M.adaptation(a)["patterns"] == [], \
            "an ask outside the window counts toward nothing"


def test_adaptation_proposal_rows_are_newest_first_with_their_state():
    with _fresh() as (M, E, tmp):
        import proposals
        root, desk, a, a1 = _tree(E, tmp)
        p1 = proposals.create("org.charter", {"ref": a1}, "Write the goal of A1")
        time.sleep(0.002)
        proposals.create("org.rename", {"ref": a1, "name": "A2"}, "Rename A1")
        proposals.decide(p1["id"], False)
        rows = M.adaptation(a)["proposals"]
        assert [r["change"] for r in rows] == ["Rename A1", "Write the goal of A1"]
        assert [r["state"] for r in rows] == ["Waits.", "Refused."]
        assert [r["open"] for r in rows] == [True, False]
        assert rows[0]["window_ms"] == proposals.TTL_SECONDS * 1000, \
            "an open change carries its window so the card can draw it"
        assert rows[0]["created_ms"] > 0
        assert rows[0]["row"]["id"].startswith("p-"), "the raw row rides along for Exact"


def test_adaptation_evidence_is_the_repeat_count_and_nothing_when_there_is_none():
    with _fresh() as (M, E, tmp):
        import proposals
        root, desk, a, a1 = _tree(E, tmp)
        for _ in range(3):
            proposals.create("org.charter", {"ref": a1}, "Write the goal of A1")
            time.sleep(0.002)
        proposals.create("org.rename", {"ref": a1, "name": "A2"}, "Rename A1")
        rows = {r["change"]: r["evidence"] for r in M.adaptation(a)["proposals"]}
        assert rows["Write the goal of A1"] == "Asked 3 times in seven days"
        assert rows["Rename A1"] == "", "a change that stands alone invents no evidence"


def test_adaptation_is_empty_for_a_department_with_nothing_put_forward():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        out = M.adaptation(a)
        assert out == {"proposals": [], "patterns": [], "births": [], "chat": []}


def test_adaptation_chat_is_the_exchange_that_carried_the_changes():
    with _fresh() as (M, E, tmp):
        import proposals
        root, desk, a, a1 = _tree(E, tmp)
        p = proposals.create("org.charter", {"ref": a}, "Write the goal of A")
        proposals.decide(p["id"], False)
        assert [(r["who"], r["to"], r["line"]) for r in M.adaptation(a)["chat"]] == [
            ("Adaptation", "Identity", "Write the goal of A"),
            ("Identity", "Adaptation", "Refused.")]


def test_adaptation_404s_on_an_unknown_department():
    import fastapi
    with _fresh() as (M, E, tmp):
        _tree(E, tmp)
        with __import__("pytest").raises(fastapi.HTTPException) as exc:
            M.adaptation("no-such-ref")
        assert exc.value.status_code == 404


# --------------------------------------------------------------------- S36 --

def _dispatch(tmp, sid, unit, model, ts, touches="here/", extra=None):
    """One dispatch record, written the way holding/bin/sutra-dispatch writes
    one: a KEY=VALUE marker under `.sutra/dispatch/<session>/`."""
    d = tmp / ".sutra" / "dispatch" / sid
    d.mkdir(parents=True, exist_ok=True)
    rows = {"UNIT": unit, "MODEL": model, "PROVIDER": "claude", "CLASS": "3",
            "TOUCHES": touches, "SESSION": sid, "TS": str(ts)}
    rows.update(extra or {})
    (d / "dispatch-record").write_text(
        "".join("%s=%s\n" % (k, v) for k, v in rows.items()), encoding="utf-8")


def test_priority_reads_the_newest_dispatch_record_first():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        (tmp / "here").mkdir()
        _dispatch(tmp, "s-old", "Land the list column", "claude-sonnet-5", 1000)
        _dispatch(tmp, "s-new", "Land the department screen", "claude-opus-5", 2000)
        out = M.priority(a)
        assert [q["next"] for q in out["queue"]] == [
            "Land the department screen", "Land the list column"]
        assert out["model"] == "claude-opus-5", "the newest record says what it runs as"
        assert out["class"] == "3"
        assert out["queue"][0]["runs_as"] == "claude-opus-5"
        assert out["queue"][0]["when_ms"] == 2000 * 1000
        assert out["queue"][0]["row"]["SESSION"] == "s-new", "the raw row rides along"


def test_priority_leaves_out_a_record_that_touched_another_department():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        (tmp / "here").mkdir()
        _dispatch(tmp, "s-here", "Land the list column", "claude-opus-5", 2000,
                  touches="here/|holding/")
        _dispatch(tmp, "s-away", "Somewhere else", "claude-opus-5", 3000,
                  touches="/tmp/not-here/")
        assert [q["next"] for q in M.priority(a)["queue"]] == ["Land the list column"]


def test_priority_is_empty_with_no_dispatch_record_and_never_raises():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        out = M.priority(a)
        assert out["queue"] == [] and out["class"] is None and out["model"] is None
        assert out["chat"] == []
        assert M.priority(root)["queue"] == [], "no cwd, no attribution"


def test_priority_carries_the_turn_budget_from_the_task_limits_store():
    with _fresh() as (M, E, tmp):
        import mission_engine
        root, desk, a, a1 = _tree(E, tmp)
        assert M.priority(a)["budget"]["running_at_once"] is None, "A11: nothing set"
        Path(mission_engine.limits_path()).parent.mkdir(parents=True, exist_ok=True)
        Path(mission_engine.limits_path()).write_text(
            json.dumps({"running_at_once": 4, "turn_budget": {"task": 12}}),
            encoding="utf-8")
        b = M.priority(a)["budget"]
        assert b["running_at_once"] == 4
        assert b["turn_budget"] == {"task": 12}
        assert b["ceiling"] == mission_engine.RUNNING_CEILING


def test_priority_survives_a_half_written_dispatch_record():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        (tmp / "here").mkdir()
        d = tmp / ".sutra" / "dispatch" / "s-junk"
        d.mkdir(parents=True, exist_ok=True)
        (d / "dispatch-record").write_text("not a marker at all\n", encoding="utf-8")
        _dispatch(tmp, "s-good", "Land the list column", "claude-opus-5", 2000)
        assert [q["next"] for q in M.priority(a)["queue"]] == ["Land the list column"]


def test_priority_chat_is_what_it_admitted():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        (tmp / "here").mkdir()
        _dispatch(tmp, "s-new", "Land the department screen", "claude-opus-5", 2000)
        rows = M.priority(a)["chat"]
        assert [(r["who"], r["to"], r["line"]) for r in rows] == [
            ("Priority", "Coordination",
             "Admitted: Land the department screen. Runs as claude-opus-5.")]
        assert rows[0]["at"], "the record's own stamp, formatted like every other"


def test_priority_404s_on_an_unknown_department():
    import fastapi
    with _fresh() as (M, E, tmp):
        _tree(E, tmp)
        with __import__("pytest").raises(fastapi.HTTPException) as exc:
            M.priority("no-such-ref")
        assert exc.value.status_code == 404


# --------------------------------------------------------------------- S37 --

def _lock(tmp, rid):
    """The overlap lock routines.py takes around a run (routines.py:566): a
    directory beside the run folder. Made here with mkdir, exactly as the
    module makes it, and never through acquire_lock()."""
    d = tmp / "runs" / rid / ".lock"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _heartbeat(tmp, sid):
    d = tmp / ".claude" / "heartbeats"
    d.mkdir(parents=True, exist_ok=True)
    (d / sid).write_text("", encoding="utf-8")
    return d / sid


def test_coordination_reads_a_routine_lock_as_a_hold():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _routine("held-one", tmp / "here", description="Nightly sweep")
        _routine("free-one", tmp / "here", description="Weekly sweep")
        _lock(tmp, "held-one")
        held = M.coordination(a)["held"]
        assert [(h["resource"], h["holder"]) for h in held] == [
            ("Nightly sweep", "Its own run")]
        assert held[0]["since_ms"] > 0, "a hold says since when"


def test_coordination_leaves_out_a_lock_in_another_department():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        outside = Path(os.path.realpath(str(tmp.parent))) / ("out-" + tmp.name)
        outside.mkdir()
        try:
            _routine("elsewhere", outside, description="Another sweep")
            _lock(tmp, "elsewhere")
            assert M.coordination(a)["held"] == []
        finally:
            for f in outside.glob("*"):
                f.unlink()
            outside.rmdir()


def test_coordination_reads_a_live_heartbeat_as_a_hold_and_a_stale_one_as_none():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        live = _heartbeat(tmp, "s-live")
        held = M.coordination(a)["held"]
        assert [(h["resource"], h["holder"]) for h in held] == [("A", "A session")]
        old = time.time() - (M.HEARTBEAT_FRESH_MS / 1000.0) - 60
        os.utime(str(live), (old, old))
        assert M.coordination(a)["held"] == [], "a stale mark is not a holder"


def test_coordination_lists_the_hand_off_a_placement_chain_left_behind():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        c_a = _charter(E, a, "A goal.", title="A charter")
        c_a1 = _charter(E, a1, "A1 goal.", title="A1 charter")
        wr = {"id": "holding/departments/a/NOTE.md", "kind": "task"}
        E.write_placement(wr, a1, c_a1, "test", 1.0, "2026-09-20", "T-local")
        E.write_placement(wr, a, c_a, "test", 1.0, "2026-09-21", "T-local")
        rows = M.coordination(a)["handoffs"]
        assert [(r["from"], r["to"], r["what"]) for r in rows] == [("A1", "A", "NOTE")], rows
        assert rows[0]["ts_ms"] > 0
        assert rows[0]["row"]["supersedes"], "the raw row carries the chain"


def test_coordination_does_not_call_a_move_inside_one_department_a_hand_off():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        c1 = _charter(E, a, "A goal.", title="One")
        c2 = _charter(E, a, "A goal, again.", title="Two")
        wr = {"id": "holding/departments/a/NOTE.md", "kind": "task"}
        E.write_placement(wr, a, c1, "test", 1.0, "2026-09-20", "T-local")
        E.write_placement(wr, a, c2, "test", 1.0, "2026-09-21", "T-local")
        assert M.coordination(a)["handoffs"] == []


def test_coordination_is_empty_with_nothing_held_and_nothing_handed_over():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        assert M.coordination(a) == {"held": [], "handoffs": [], "chat": []}


def test_coordination_chat_says_what_is_held_and_what_changed_hands():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _routine("held-one", tmp / "here", description="Nightly sweep")
        _lock(tmp, "held-one")
        rows = M.coordination(a)["chat"]
        assert [(r["who"], r["to"], r["line"]) for r in rows] == [
            ("Coordination", "Priority", "Nightly sweep held by its own run.")]


def test_coordination_404s_on_an_unknown_department():
    import fastapi
    with _fresh() as (M, E, tmp):
        _tree(E, tmp)
        with __import__("pytest").raises(fastapi.HTTPException) as exc:
            M.coordination("no-such-ref")
        assert exc.value.status_code == 404


# ---------------------------------------------------------------- S38, S46 --

def _findings(tmp, rows, base=None):
    """The daily governance audit's own log, where it writes it."""
    d = Path(base or tmp)
    for part in ("holding", "observability", "governance-audit"):
        d = d / part
    d.mkdir(parents=True, exist_ok=True)
    p = d / "findings.jsonl"
    p.write_text("".join(
        (r if isinstance(r, str) else json.dumps(r)) + "\n" for r in rows),
        encoding="utf-8")
    return p


def _finding(fid, text, severity="warn", status="open",
             first="2026-09-01", last="2026-09-20", check="C2", **kw):
    row = {"id": fid, "check": check, "severity": severity, "text": text,
           "status": status, "first_seen": first, "last_seen": last}
    row.update(kw)
    return row


def test_audit_lists_findings_that_name_a_path_under_the_department_newest_first():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        (tmp / "here").mkdir()
        _findings(tmp, [
            _finding("f-1", "here/one.sh is missing or not executable", last="2026-09-18"),
            _finding("f-2", "here/two-thing.sh still emits on stderr",
                     severity="critical", last="2026-09-20"),
            _finding("f-3", "/tmp/not-here/three.sh is another department's",
                     last="2026-09-19"),
            "{ this line is not json",
        ])
        out = M.audit(a)
        assert [f["id"] for f in out["findings"]] == ["f-2", "f-1"], out["findings"]
        assert out["findings"][0]["dot"] == "block", "critical is a block dot"
        assert out["findings"][1]["dot"] == "warn"
        assert out["skipped"] == 1, "a malformed line is counted, not fatal (PRD J)"


def test_audit_puts_the_name_on_the_claim_and_leaves_the_path_in_the_raw_row():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        (tmp / "here").mkdir()
        _findings(tmp, [_finding("f-1", "here/sessionstart-audit.sh emits on stderr")])
        row = M.audit(a)["findings"][0]
        assert row["claim"] == "sessionstart audit emits on stderr", row["claim"]
        assert "/" not in row["claim"], "A28: names, never paths"
        assert row["row"]["text"].startswith("here/"), "the raw row keeps it"


def test_audit_reads_the_last_row_per_finding():
    """The log is appended to every audit day under one id; where a finding
    stands is what the last row says, not the first."""
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        (tmp / "here").mkdir()
        _findings(tmp, [
            _finding("f-1", "here/one.sh is missing", status="open", last="2026-09-18"),
            _finding("f-1", "here/one.sh is missing", status="fixed",
                     last="2026-09-20", fix_ref="abc123"),
        ])
        out = M.audit(a)
        assert len(out["findings"]) == 1
        assert out["findings"][0]["record"] == "Fixed."
        assert out["findings"][0]["dot"] == "ok"
        assert out["unseen"] == [], "a fixed finding was looked at"


def test_audit_never_looked_at_is_what_nobody_has_written_a_word_against():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        (tmp / "here").mkdir()
        _findings(tmp, [
            _finding("f-1", "here/one.sh is missing", first="2026-08-04"),
            _finding("f-2", "here/two.sh is missing", first="2026-09-01",
                     note="judged a measurement artifact"),
            _finding("f-3", "here/three.sh is missing", first="2026-09-02",
                     fix_ref="abc123"),
        ])
        out = M.audit(a)
        assert [u["claim"] for u in out["unseen"]] == ["one is missing"], out["unseen"]
        assert out["unseen"][0]["since"] == "2026-08-04", "it says since when"
        recs = {f["id"]: f["record"] for f in out["findings"]}
        assert recs["f-1"] == "Still open."
        assert recs["f-2"] == "judged a measurement artifact", "the record's own words"


def test_audit_missing_file_is_an_empty_list_and_never_a_500():
    """S46 + PRD section J: the findings log is holding's own routine, so most
    installs have never had one. That is an empty card, not an error."""
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        assert M.audit(a) == {"findings": [], "unseen": [], "skipped": 0, "chat": []}
        assert M.audit(root)["findings"] == [], "no cwd, no attribution"
        assert M.audit(a1)["findings"] == []


def test_audit_missing_file_survives_an_unreadable_workdir():
    with _fresh() as (M, E, tmp):
        import providers
        root, desk, a, a1 = _tree(E, tmp)
        (tmp / "settings.json").write_text(json.dumps({"workdir": "/nope/gone"}),
                                           encoding="utf-8")
        importlib.reload(providers)
        assert M.audit(a)["findings"] == []


def test_audit_chat_flags_what_is_not_ok_and_otherwise_says_every_claim_has_its_row():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        (tmp / "here").mkdir()
        _findings(tmp, [_finding("f-1", "here/one.sh is missing", severity="critical")])
        rows = M.audit(a)["chat"]
        assert [(r["who"], r["to"]) for r in rows] == [("Audit", "Priority")]
        assert rows[0]["line"] == 'Flag: claimed "one is missing"; the record says Still open.'
        _findings(tmp, [_finding("f-1", "here/one.sh is missing", status="fixed")])
        rows = M.audit(a)["chat"]
        assert [r["line"] for r in rows] == ["Every claim has its row."]


def test_audit_never_scores_a_check():
    """A16: a check is a check. The route answers rows and no number -- no
    total, no share, no count of any kind."""
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        (tmp / "here").mkdir()
        _findings(tmp, [_finding("f-%d" % i, "here/%d.sh is missing" % i) for i in range(4)])
        out = M.audit(a)
        assert set(out) == {"findings", "unseen", "skipped", "chat"}
        assert set(out["findings"][0]) == {
            "id", "check", "claim", "record", "dot", "first_seen", "last_seen", "row"}
        assert all(not isinstance(f.get("dot"), (int, float)) for f in out["findings"])


def test_audit_404s_on_an_unknown_department():
    import fastapi
    with _fresh() as (M, E, tmp):
        _tree(E, tmp)
        with __import__("pytest").raises(fastapi.HTTPException) as exc:
            M.audit("no-such-ref")
        assert exc.value.status_code == 404


# ---------------------------------------------------------------- S49-S52 --
# The engines: the routines that run in the department's folder, their runs,
# what they filed, and the one ask this screen files of its own.


def _runs_index(tmp, rid, rows):
    """The run index routines.py appends to (routines.py:112, 729): one JSON
    row per line under the run store. Written here, never through run_now()."""
    d = tmp / "runs" / rid
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return d


def _run_row(rid, started, ended="2026-09-20T04:00:00+05:30", outcome="ok",
             trigger="schedule", duration=120.0):
    row = {"schema": 1, "id": rid, "trigger": trigger, "started_at": started,
           "outcome": outcome, "duration_s": duration}
    if ended:
        row["ended_at"] = ended
    return row


def _workflow(tmp, wid, steps):
    d = tmp / "workflows"
    d.mkdir(parents=True, exist_ok=True)
    (d / (wid + ".json")).write_text(json.dumps(
        {"id": wid, "title": wid + " title", "goal": "do the thing",
         "steps": steps}), encoding="utf-8")


def test_engines_list_names_each_routine_under_the_department():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        inside = tmp / "inside"
        inside.mkdir()
        outside = Path(os.path.realpath(str(tmp.parent))) / ("out-" + tmp.name)
        outside.mkdir()
        try:
            _routine("in-here", inside, description="Nightly sweep")
            _routine("elsewhere", outside, description="Another sweep")
            rows = M.engines(a)["engines"]
            assert [r["id"] for r in rows] == ["in-here"], \
                "a routine whose folder is outside is another department's"
            assert rows[0]["name"] == "Nightly sweep"
            assert set(rows[0]) == {
                "id", "name", "state", "enabled", "cwd", "runs_as", "cadence",
                "made_by", "needs", "makes", "read_by", "workflow", "prompt"}
        finally:
            for f in outside.glob("*"):
                f.unlink()
            outside.rmdir()


def test_engines_list_state_word_is_paused_running_or_idle():
    """A18: the word is DERIVED -- `enabled` and the run lock are the whole
    answer, and a paused engine holding a stale lock is paused, not running."""
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _routine("idle-one", tmp, description="Idle sweep")
        _routine("busy-one", tmp, description="Busy sweep")
        _routine("off-one", tmp, description="Off sweep", enabled=False)
        _lock(tmp, "busy-one")
        _lock(tmp, "off-one")
        got = {r["id"]: r["state"] for r in M.engines(a)["engines"]}
        assert got == {"idle-one": "idle", "busy-one": "running",
                       "off-one": "paused"}


def test_engines_list_reads_a_run_with_no_end_as_running():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _routine("live-one", tmp, description="Live sweep")
        _runs_index(tmp, "live-one",
                    [_run_row("live-one", "2026-09-20T03:00:00+05:30", ended=None)])
        assert M.engines(a)["engines"][0]["state"] == "running"


def test_engines_list_is_empty_above_the_machine_and_never_raises():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _routine("in-here", tmp)
        assert M.engines(root)["engines"] == [], "PRD F-3: nothing to attribute"


def test_engines_list_reads_without_writing_anything():
    """The drift stated in dept_api's ENGINES header: routines.state() writes a
    .heartbeat file and shells launchctl, so it is not called. Pin that the
    read leaves the routine store exactly as it found it."""
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _routine("in-here", tmp, description="Nightly sweep")
        before = sorted(p.name for p in (tmp / "routines").iterdir())
        M.engines(a)
        assert sorted(p.name for p in (tmp / "routines").iterdir()) == before
        code = [l for l in (HERE / "dept_api.py").read_text(encoding="utf-8").splitlines()
                if not l.lstrip().startswith("#")]
        assert not any("routines.state(" in l for l in code), \
            "the ENGINES header says state() is not called -- keep it that way"


def test_engines_list_404s_on_an_unknown_department():
    import fastapi
    with _fresh() as (M, E, tmp):
        _tree(E, tmp)
        with __import__("pytest").raises(fastapi.HTTPException) as exc:
            M.engines("no-such-ref")
        assert exc.value.status_code == 404


def test_engines_list_cadence_is_the_records_own_sentence():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        rec = _routine("in-here", tmp)
        assert M.engines(a)["engines"][0]["cadence"] == rec["schedule"]["human"]


def test_engines_list_workflow_is_the_one_its_instruction_names():
    """A19: no routine record references a workflow, so the join is the
    engine's own instruction naming one -- and nothing looser."""
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _workflow(tmp, "W-sweep", [{"id": "S1", "name": "read the folder",
                                    "produces": ["a list"], "verify": "the list exists"}])
        import routines
        rec = _routine("named-one", tmp, description="Named sweep")
        rec["prompt"] = "run W-sweep over the department"
        routines.save(rec)
        _routine("plain-one", tmp, description="Plain sweep")
        got = {r["id"]: (r["workflow"] or {}).get("id") for r in M.engines(a)["engines"]}
        assert got == {"named-one": "W-sweep", "plain-one": None}
        flow = [r for r in M.engines(a)["engines"] if r["id"] == "named-one"][0]["workflow"]
        assert [s["name"] for s in flow["steps"]] == ["read the folder"]


def test_engines_list_makes_prefers_what_was_filed_over_what_was_declared():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _workflow(tmp, "W-sweep", [{"id": "S1", "name": "sweep",
                                    "produces": ["a list"], "verify": "x"}])
        import routines
        rec = _routine("named-one", tmp, description="Named sweep")
        rec["prompt"] = "run W-sweep"
        routines.save(rec)
        rows = M.engines(a)["engines"]
        assert rows[0]["makes"] == ["a list"], "the declaration, until something is filed"
        assert rows[0]["needs"] is None and rows[0]["read_by"] is None, \
            "no record names either -- the card says so in a quiet line"
        cid = _charter(E, a, "Own the sweep")
        E.write_placement({"id": "holding/observability/LATEST.md", "kind": "task"},
                          a, cid, "named-one", 1.0, "2026-09-20", "T-local")
        rows = M.engines(a)["engines"]
        assert rows[0]["makes"] == ["LATEST"], "evidence beats the declaration"


def test_engine_runs_pass_routines_runs_through_with_its_chat():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _routine("in-here", tmp, description="Nightly sweep")
        _runs_index(tmp, "in-here", [
            _run_row("in-here", "2026-09-19T03:00:00+05:30"),
            _run_row("in-here", "2026-09-20T03:00:00+05:30", outcome="failed"),
        ])
        out = M.engine_runs(a, "in-here")
        assert out["id"] == "in-here" and out["total"] == 2 and out["never_run"] is False
        assert [r["outcome"] for r in out["runs"]] == ["failed", "ok"], "newest first"
        assert [t["who"] for t in out["chat"]] == ["Nightly sweep", "Nightly sweep"]
        assert out["chat"][0]["line"] == "On the schedule: failed."
        assert out["chat"][0]["row"] is out["runs"][0], "Exact shows the run row itself"


def test_engine_runs_of_a_live_row_say_running():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _routine("in-here", tmp, description="Nightly sweep")
        _runs_index(tmp, "in-here",
                    [_run_row("in-here", "2026-09-20T03:00:00+05:30", ended=None)])
        out = M.engine_runs(a, "in-here")
        assert out["runs"][0].get("ended_at") is None
        assert out["chat"][0]["line"] == "On the schedule: running."


def test_engine_runs_is_never_run_with_no_index():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _routine("in-here", tmp)
        out = M.engine_runs(a, "in-here")
        assert out["runs"] == [] and out["never_run"] is True and out["chat"] == []


def test_engine_runs_404s_for_an_engine_in_another_department():
    import fastapi
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        outside = Path(os.path.realpath(str(tmp.parent))) / ("out-" + tmp.name)
        outside.mkdir()
        try:
            _routine("elsewhere", outside)
            with __import__("pytest").raises(fastapi.HTTPException) as exc:
                M.engine_runs(a, "elsewhere")
            assert exc.value.status_code == 404
            with __import__("pytest").raises(fastapi.HTTPException) as exc:
                M.engine_runs(a, "no-such-engine")
            assert exc.value.status_code == 404
        finally:
            for f in outside.glob("*"):
                f.unlink()
            outside.rmdir()


def test_engine_data_lists_the_placements_whose_origin_names_the_engine():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _routine("in-here", tmp, description="Nightly sweep")
        cid = _charter(E, a, "Own the sweep")
        wr = {"id": "holding/observability/LATEST.md", "kind": "task"}
        E.write_placement(wr, a, cid, "in-here", 1.0, "2026-09-20", "T-local")
        E.write_placement({"id": "holding/other.md", "kind": "task"}, a, cid,
                          "system-minted", 1.0, "2026-09-20", "T-local")
        filed = M.engine_data(a, "in-here")["filed"]
        assert [f["label"] for f in filed] == ["LATEST"], \
            "only the rows whose origin names this engine, and as a name"
        assert filed[0]["ts_ms"] > 0 and filed[0]["row"]["origin"] == "in-here"


def test_engine_data_is_nothing_filed_when_no_origin_names_it():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _routine("in-here", tmp)
        assert M.engine_data(a, "in-here") == {"filed": []}


def test_engine_pause_files_one_ask_and_changes_nothing():
    """A22 + R2: the routine's `enabled` is untouched until the ask is stamped
    somewhere else. This route writes a proposal and nothing else."""
    with _fresh() as (M, E, tmp):
        import proposals
        import routines
        root, desk, a, a1 = _tree(E, tmp)
        _routine("in-here", tmp, description="Nightly sweep")
        out = M.engine_pause(a, "in-here")
        rows = proposals.listing()
        assert len(rows) == 1 and rows[0]["kind"] == "routine.update"
        assert rows[0]["args"] == {"id": "in-here", "patch": {"enabled": False}}
        assert rows[0]["status"] == "pending"
        assert out["summary"] == "Pause Nightly sweep"
        assert out["proposal"]["id"] == rows[0]["id"]
        assert routines.load("in-here")["enabled"] is True, "nothing applied"
        assert M.engines(a)["engines"][0]["state"] == "idle", \
            "the state word does not move until the ask is stamped"


def test_engine_pause_400s_when_it_is_already_paused():
    import fastapi
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _routine("off-one", tmp, enabled=False)
        with __import__("pytest").raises(fastapi.HTTPException) as exc:
            M.engine_pause(a, "off-one")
        assert exc.value.status_code == 400


def test_engine_pause_404s_for_an_engine_in_another_department():
    import fastapi
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        with __import__("pytest").raises(fastapi.HTTPException) as exc:
            M.engine_pause(a, "no-such-engine")
        assert exc.value.status_code == 404


# --------------------------------------------------------------------- S61 --

def test_engine_birth_is_from_an_ask_when_the_stamps_line_up():
    """A23 / F-10: no routine row references the ask that made it, so the match
    is the ask being DECIDED in the same minute the record was written."""
    with _fresh() as (M, E, tmp):
        import proposals
        import routines
        root, desk, a, a1 = _tree(E, tmp)
        rec = _routine("in-here", tmp, description="Nightly sweep")
        p = proposals.create("routine.create", {"id": "in-here"}, "Add the sweep")
        proposals.decide(p["id"], True, apply_fn=lambda kind, args: {"routine": "in-here"})
        born = M.engines(a)["engines"][0]["made_by"]
        assert born["from_ask"] is True
        assert born["at"] == rec["created_at"] and born["at_ms"] > 0


def test_engine_birth_is_written_when_the_ask_names_another_engine():
    with _fresh() as (M, E, tmp):
        import proposals
        root, desk, a, a1 = _tree(E, tmp)
        _routine("in-here", tmp, description="Nightly sweep")
        p = proposals.create("routine.create", {"id": "other-one"}, "Add another")
        proposals.decide(p["id"], True, apply_fn=lambda kind, args: {"routine": "other-one"})
        assert M.engines(a)["engines"][0]["made_by"]["from_ask"] is False


def test_engine_birth_is_written_when_the_ask_was_decided_much_later():
    with _fresh() as (M, E, tmp):
        import proposals
        import routines
        root, desk, a, a1 = _tree(E, tmp)
        rec = _routine("in-here", tmp, description="Nightly sweep")
        rec["created_at"] = "2026-01-01T00:00:00+05:30"
        routines.save(rec)
        p = proposals.create("routine.create", {"id": "in-here"}, "Add the sweep")
        proposals.decide(p["id"], True, apply_fn=lambda kind, args: {"routine": "in-here"})
        assert M.engines(a)["engines"][0]["made_by"]["from_ask"] is False, \
            "two stamps a year apart are not one act"


def test_engine_birth_is_written_with_no_ask_at_all():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _routine("in-here", tmp)
        assert M.engines(a)["engines"][0]["made_by"]["from_ask"] is False


# --------------------------------------------------------------------- S63 --
# R13 / A24: the filed work of a department, and the version chain behind each
# row. The three state words are DERIVED from two fields, so every one of them
# is pinned here against a placement written to carry it.


def _filed(E, ref, cid, work_id, phase="pre-flight", origin="matched", day="2026-09-20"):
    return E.write_placement({"id": work_id, "kind": "task"}, ref, cid,
                             origin, 1.0, day, "T-local", phase=phase)


def test_filed_lists_one_row_per_work_item_with_its_version_count():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        cid = _charter(E, a, "Own the plan")
        _filed(E, a, cid, "holding/plans/department-screen/LLD.md")
        _filed(E, a, cid, "holding/plans/department-screen/LLD.md", phase="post-close")
        _filed(E, a, cid, "holding/plans/department-screen/PRD.md")
        rows = M.filed(a)["filed"]
        assert sorted(r["label"] for r in rows) == ["LLD", "PRD"], \
            "one row per work item, not one per version, and a name not a path"
        lld = [r for r in rows if r["label"] == "LLD"][0]
        assert lld["versions"] == 2, "the supersedes chain is the version count"
        assert lld["id"] == "holding/plans/department-screen/LLD.md", \
            "the row is keyed by the work item, the way org2_api._filed keys it"
        assert lld["kind"] == "task" and lld["placement_id"].startswith("PL-")
        assert [r for r in rows if r["label"] == "PRD"][0]["versions"] == 1


def test_filed_versions_are_newest_first_with_their_state_word():
    """A24: in use / waits / retired, off `supersedes` and `phase`."""
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        cid = _charter(E, a, "Own the plan")
        first = _filed(E, a, cid, "holding/a.md", day="2026-09-19")
        last = _filed(E, a, cid, "holding/a.md", phase="post-close", day="2026-09-20")
        hist = M.filed(a)["filed"][0]["history"]
        assert [h["id"] for h in hist] == [last["id"], first["id"]], "newest first"
        assert [h["state"] for h in hist] == ["in use", "retired"]
        assert hist[1]["row"]["supersedes"] is None and hist[0]["row"]["supersedes"] == first["id"]


def test_filed_reads_waits_while_the_work_has_not_closed():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        cid = _charter(E, a, "Own the plan")
        _filed(E, a, cid, "holding/b.md")                 # pre-flight, unsuperseded
        row = M.filed(a)["filed"][0]
        assert row["versions"] == 1
        assert [h["state"] for h in row["history"]] == ["waits"]


def test_filed_reads_waits_for_a_phase_the_engine_does_not_define():
    """87 rows on this machine carry `open`, written outside placement_engine.
    An undefined phase does not say the work closed, so it is not called in
    use -- the word is not guessed at."""
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        cid = _charter(E, a, "Own the plan")
        _filed(E, a, cid, "holding/c.md", phase="open")
        assert [h["state"] for h in M.filed(a)["filed"][0]["history"]] == ["waits"]


def test_filed_names_the_filer_and_never_invents_a_reader():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        cid = _charter(E, a, "Own the plan")
        _filed(E, a, cid, "holding/d.md", origin="backfilled")
        one = M.filed(a)["filed"][0]["history"][0]
        assert one["made_by"] == "backfilled", "the filer's own word for itself"
        assert one["read_by"] is None, "no record names who reads a filed item"
        assert one["where"] == "A" and one["ts_ms"] > 0
        assert one["charter_id"] == cid


def test_filed_follows_a_re_homed_item_to_its_new_department():
    """A placement re-homed under another department leaves the first one's
    list: the current row is the only head, and it sits where it was re-filed."""
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        c_a, c_a1 = _charter(E, a, "Own A"), _charter(E, a1, "Own A1")
        _filed(E, a1, c_a1, "holding/e.md", day="2026-09-19")
        _filed(E, a, c_a, "holding/e.md", phase="post-close", day="2026-09-20")
        assert M.filed(a1)["filed"] == [], "it moved away"
        moved = M.filed(a)["filed"]
        assert len(moved) == 1 and moved[0]["versions"] == 2
        assert [h["where"] for h in moved[0]["history"]] == ["A", "A1"], \
            "each version says which department held it"


def test_filed_is_empty_for_a_department_with_nothing_filed():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        assert M.filed(a) == {"filed": []}


def test_filed_404s_on_an_unknown_department():
    import fastapi
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        with __import__("pytest").raises(fastapi.HTTPException) as exc:
            M.filed("dref-nope")
        assert exc.value.status_code == 404


def test_filed_stops_on_a_chain_that_names_a_row_this_store_does_not_hold():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        cid = _charter(E, a, "Own the plan")
        body = _filed(E, a, cid, "holding/f.md")
        path = Path(E.PLACEMENTS) / (body["id"] + ".json")
        body["supersedes"] = "PL-does-not-exist"
        path.write_text(json.dumps(body, sort_keys=True, indent=2), encoding="utf-8")
        E._JSON_CACHE.clear()          # the body was edited under the engine's cache
        row = M.filed(a)["filed"][0]
        assert row["versions"] == 1, "a dangling predecessor is not a version"


# --------------------------------------------------------------------- S64 --
# R14 / A25: the owner first, then role charters. F-14 is real -- no charter on
# disk carries kind "role" -- so the owner-only answer is the one every
# department gives today, and the role branch is pinned against a fixture.


def test_people_lists_the_owner_only_when_no_role_charter_exists():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _charter(E, a, "A goal.", authority={"name": "Meera"})
        out = M.people(a)
        assert out["owner"]["name"] == "Meera" and out["owner"]["source"] == "charter"
        assert out["roles"] == [], "F-14: no charter carries kind role today"


def test_people_owner_is_the_same_one_identity_resolves(monkeypatch):
    monkeypatch.setattr("subprocess.run", lambda *a, **k: type(
        "R", (), {"returncode": 0, "stdout": "SankalpAsawa\n"})())
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        assert M.people(a)["owner"] == dict(M.identity(a)["owner"],
                                            stamps="", seen=[]), \
            "one owner rule, read twice"


def test_people_lists_a_role_charter_after_the_owner():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _charter(E, a, "A goal.", authority={"name": "Meera"})
        _charter(E, a, "Stamp the release notes.", title="Reviewer", kind="role")
        out = M.people(a)
        assert out["owner"]["name"] == "Meera", "the owner is still first"
        assert [r["title"] for r in out["roles"]] == ["Reviewer"]
        assert out["roles"][0]["name"] == "Reviewer"
        assert out["roles"][0]["stamps"] == "Stamp the release notes."
        assert out["roles"][0]["charter_id"].startswith("C-")


def test_people_owner_stamps_nothing_when_the_record_names_no_scope():
    """F-12's twin: `authority` is {} on every charter on disk, so what the
    owner stamps is honestly unwritten and the card shows its quiet line."""
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _charter(E, a, "A goal.", authority={"name": "Meera"})
        assert M.people(a)["owner"]["stamps"] == ""


def test_people_owner_stamps_the_scope_the_record_does_name():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _charter(E, a, "A goal.",
                 authority={"name": "Meera", "scope": "Every release of Desktop"})
        assert M.people(a)["owner"]["stamps"] == "Every release of Desktop"


def test_people_seen_carries_the_answered_asks_and_not_the_open_one():
    with _fresh() as (M, E, tmp):
        import proposals
        root, desk, a, a1 = _tree(E, tmp)
        _charter(E, a, "A goal.", authority={"name": "Meera"})
        p1 = proposals.create("org.charter", {"ref": a1, "purpose": "x"},
                              "Write the goal of A1")
        proposals.create("org.rename", {"ref": a1, "name": "A2"}, "Rename A1")
        proposals.decide(p1["id"], False)
        seen = M.people(a)["owner"]["seen"]
        assert [(s["summary"], s["answer"]) for s in seen] == [
            ("Write the goal of A1", "Refused.")], "an open ask was not seen"
        assert seen[0]["at"] and seen[0]["at_ms"] > 0
        assert seen[0]["row"]["id"] == p1["id"]


def test_people_seen_leaves_out_an_ask_whose_window_closed_on_its_own():
    with _fresh() as (M, E, tmp):
        import proposals
        root, desk, a, a1 = _tree(E, tmp)
        rec = proposals.create("org.charter", {"ref": a, "purpose": "x"}, "Write it")
        rec["created_ms"] = int(time.time() * 1000) - (proposals.TTL_SECONDS + 60) * 1000
        proposals._write(rec)
        assert [r["status"] for r in proposals.listing()] == ["expired"]
        assert M.people(a)["owner"]["seen"] == [], \
            "a window that closed on its own was never looked at"


def test_people_is_quiet_with_no_charter_and_no_git_user(monkeypatch):
    monkeypatch.setattr("subprocess.run", lambda *a, **k: type(
        "R", (), {"returncode": 1, "stdout": ""})())
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        out = M.people(a)
        assert out == {"owner": {"source": "none", "name": None, "stamps": "", "seen": []},
                       "roles": []}


def test_people_404s_on_an_unknown_department():
    import fastapi
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        with __import__("pytest").raises(fastapi.HTTPException) as exc:
            M.people("dref-nope")
        assert exc.value.status_code == 404


# -------------------------------------------------------------- S73, S82 --
# The meters and the births: the last two readings, both COUNTED on the read.


def _this_month(days_back=0):
    """An ISO stamp inside the current calendar month, never spilling into the
    previous one on the 1st (a test that runs at 00:30 on the 1st must not be
    the one that fails)."""
    now = time.localtime()
    day = max(1, now.tm_mday - days_back)
    return time.strftime("%%Y-%%m-%02dT03:00:00" % day, now)


def _last_month():
    now = time.time()
    back = now
    this = time.strftime("%Y-%m", time.localtime(now))
    while time.strftime("%Y-%m", time.localtime(back)) == this:
        back -= 3 * 24 * 3600
    return time.strftime("%Y-%m-%dT03:00:00", time.localtime(back))


def test_meters_count_this_calendar_month_and_say_so_with_no_row_at_all():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        out = M.meters(a)
        assert out["month"] == time.strftime("%Y-%m")
        assert [m["key"] for m in out["meters"]] == ["runs", "asks", "refuses", "spend"]
        assert [m["reading"] for m in out["meters"]] == [False, False, False, False], \
            "A27: nothing on record is no reading, never a zero"
        assert out["runs"] == 0 and out["asks"] == 0 and out["refuses"] == 0
        assert out["spend_usd"] is None
        assert out["engines"] == []


def test_meters_runs_are_this_months_run_rows_against_the_busiest_month():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _routine("sweep", tmp)
        _runs_index(tmp, "sweep", [
            _run_row("sweep", _last_month()), _run_row("sweep", _last_month()),
            _run_row("sweep", _last_month()), _run_row("sweep", _this_month()),
        ])
        out = M.meters(a)
        runs = [m for m in out["meters"] if m["key"] == "runs"][0]
        assert out["runs"] == 1
        assert runs["reading"] is True
        assert runs["value"] == 1 and runs["of"] == 3, \
            "the ceiling is the department's own busiest month"


def test_meters_asks_and_refuses_read_the_departments_own_proposals():
    with _fresh() as (M, E, tmp):
        import proposals
        root, desk, a, a1 = _tree(E, tmp)
        _routine("here", tmp)
        p1 = proposals.create("routine.update", {"id": "here"}, "Pause the sweep")
        proposals.create("routine.update", {"id": "here"}, "Pause it again")
        proposals.decide(p1["id"], False)
        out = M.meters(a)
        assert out["asks"] == 2
        assert out["refuses"] == 1
        assert [m["reading"] for m in out["meters"] if m["key"] in ("asks", "refuses")] \
            == [True, True]


def test_meters_spend_is_none_until_a_run_row_carries_a_cost():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _routine("sweep", tmp)
        _runs_index(tmp, "sweep", [_run_row("sweep", _this_month())])
        assert M.meters(a)["spend_usd"] is None, "an unmeasured run is not a free one"
        row = _run_row("sweep", _this_month())
        row["cost_usd"] = 0.25
        _runs_index(tmp, "sweep", [row])
        out = M.meters(a)
        assert out["spend_usd"] == 0.25
        assert [m["reading"] for m in out["meters"] if m["key"] == "spend"] == [True]


def test_meters_per_engine_answer_only_what_a_record_carries():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _routine("sweep", tmp)
        rows = M.meters(a)["engines"]
        assert [e["id"] for e in rows] == ["sweep"]
        assert rows[0]["meters"] == [], \
            "an engine with no run this month and no ask answers nothing"
        _runs_index(tmp, "sweep", [_run_row("sweep", _this_month(), outcome="failed")])
        one = M.meters(a)["engines"][0]["meters"]
        assert [m["key"] for m in one] == ["tick", "asks"]
        assert one[0]["dot"] == "block" and one[1]["dot"] == "ok"
        assert "fit" not in [m["key"] for m in one], \
            "Fit has no record anywhere and is never given a dot"


def test_meters_per_engine_asks_turn_at_three_of_a_kind():
    with _fresh() as (M, E, tmp):
        import proposals
        root, desk, a, a1 = _tree(E, tmp)
        _routine("sweep", tmp)
        for _ in range(M.METER_ASK_WARN):
            proposals.create("routine.update", {"id": "sweep"}, "Pause the sweep")
        one = M.meters(a)["engines"][0]["meters"]
        assert [m["dot"] for m in one if m["key"] == "asks"] == ["warn"]


def test_meters_per_engine_spend_turns_at_the_designs_own_share():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _routine("sweep", tmp)                    # opts max_budget_usd = 1.0
        low = _run_row("sweep", _this_month())
        low["cost_usd"] = 0.1
        _runs_index(tmp, "sweep", [low])
        assert [m["dot"] for m in M.meters(a)["engines"][0]["meters"]
                if m["key"] == "spend"] == ["ok"]
        high = _run_row("sweep", _this_month())
        high["cost_usd"] = 0.9
        _runs_index(tmp, "sweep", [high])
        assert [m["dot"] for m in M.meters(a)["engines"][0]["meters"]
                if m["key"] == "spend"] == ["warn"]


def test_meters_are_empty_above_the_machine_and_never_raise():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _routine("sweep", tmp)
        _runs_index(tmp, "sweep", [_run_row("sweep", _this_month())])
        out = M.meters(root)
        assert out["runs"] == 0 and out["engines"] == []


def test_meters_404s_on_an_unknown_department():
    import fastapi
    with _fresh() as (M, E, tmp):
        _tree(E, tmp)
        with __import__("pytest").raises(fastapi.HTTPException) as exc:
            M.meters("dref-nope")
        assert exc.value.status_code == 404


def test_meters_read_without_writing_anything():
    """R15 files nothing: no run folder, no proposal, no placement."""
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _routine("sweep", tmp)
        before = sorted(p.name for p in (tmp / "proposals").iterdir())
        M.meters(a)
        assert sorted(p.name for p in (tmp / "proposals").iterdir()) == before


def test_births_are_the_engines_an_ask_brought_into_being():
    with _fresh() as (M, E, tmp):
        import proposals
        import routines
        root, desk, a, a1 = _tree(E, tmp)
        rec = _routine("born", tmp, description="Nightly sweep")
        p = proposals.create("routine.create", {"id": "born"}, "Make a nightly sweep")
        proposals.decide(p["id"], True, apply_fn=lambda kind, args: {"routine": "born"})
        rec["created_at"] = routines.now_iso()
        routines.save(rec)
        rows = M._births(M._dept_cwd(a, E.load_domains()))
        assert [r["name"] for r in rows] == ["Nightly sweep"]
        assert M.adaptation(a)["births"] == rows
        assert M.priority(a)["births"] == rows


def test_births_leave_out_an_engine_nobody_asked_for():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _routine("written", tmp)
        assert M.adaptation(a)["births"] == []
        assert M.priority(a)["births"] == []


def test_writes_only_through_proposals():
    """R2: the read side files nothing. dept_api never calls a routines mutator
    and never writes a placement; the only create() it may ever name is
    proposals.create."""
    text = (HERE / "dept_api.py").read_text(encoding="utf-8")
    for forbidden in ("routines.update(", "routines.create(", "routines.delete(",
                      "E.write_placement(", "E.mint_domain("):
        assert forbidden not in text, "dept_api.py calls %s" % forbidden


# ----------------------------------------------------------------- slice G --
# DS-1: `done_when` and `rules` on the charter sidecar, written through the
# org.charter proposal and read by Identity. DS-2: `role` as a charter kind,
# carrying the person who holds it, listed under People and nowhere else.
#
# The proposal path is driven END TO END here (file the request -> nothing is
# written -> approve -> the card reads it), because the whole claim of this
# slice is that a record the operator can edit reaches the screen through the
# one writer. A unit test on either half alone would not show that.


@contextlib.contextmanager
def _org2():
    """org2_api + org2_apply rebound to the registry `_fresh` just made.

    Both bind `placement_engine` at import, and `_fresh` replaces that module
    object; a stale import would write into the real registry. Popped on the
    way in AND on the way out, so no other module's test inherits the binding.
    """
    for m in ("org2_api", "org2_apply"):
        sys.modules.pop(m, None)
    import org2_apply
    import org2_api
    try:
        yield org2_api, org2_apply
    finally:
        for m in ("org2_api", "org2_apply"):
            sys.modules.pop(m, None)


def _file_charter(api, ref, **args):
    """One org.charter request, as the charter sheet files it."""
    return api.request(api.RequestBody(kind="org.charter", args=dict(ref=ref, **args)))["proposal"]


def test_the_charter_sidecar_carries_done_when_rules_and_person():
    """DS-1/DS-2 round trip: written at mint, read back, and absent from the
    hashed body -- re-wording a rule must not move the charter's id."""
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        cid = E.mint_charter_stub(
            a, "A Charter", "Own the release.", [], [], "T-local",
            extras={"done_when": ["every screen reads its own record"],
                    "rules": [{"tag": "refuse", "line": "Never a third AI in one task"}]})
        sc = E.load_sidecar(cid)
        assert sc["done_when"] == ["every screen reads its own record"]
        assert sc["rules"] == [{"tag": "refuse", "line": "Never a third AI in one task"}]
        assert sc["person"] == ""
        body = E.load_charter(cid)
        for key in ("done_when", "rules", "person"):
            assert key not in body, "%s rode into the hashed body" % key
        assert E.charter_id_of(body) == cid
        view = E.charter_view(cid)
        assert view["rules"][0]["tag"] == "refuse" and view["done_when"]


def test_a_sidecar_written_before_the_fields_existed_still_reads():
    """The defaults are [] / "", so every charter on disk stays valid and
    simply reads as "nothing said yet" (DS-1's reversal clause)."""
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        cid = E.mint_charter_stub(a, "Old", "An older goal.", [], [], "T-local")
        legacy = {"status": "active", "artifacts": [], "linked_domain_refs": [],
                  "goals": [], "metrics": [], "milestones": [], "todos": [], "ts_ms": 1}
        E.save_sidecar(cid, legacy)
        sc = E.load_sidecar(cid)
        assert sc["done_when"] == [] and sc["rules"] == [] and sc["person"] == ""
        assert M.identity(a)["rules"] == [] and M.identity(a)["done"] is None


def test_the_rule_normalizer_keeps_the_four_words_and_refuses_a_fifth():
    with _fresh() as (_M, E, _tmp):
        assert E.CHARTER_RULE_TAGS == ("go", "ask", "refuse", "always")
        assert E.normalize_rules([{"tag": "GO ", "line": "  Ship a patch  "},
                                  {"tag": "ask", "line": ""}]) == \
            [{"tag": "go", "line": "Ship a patch"}], "a rule with no line is not a rule"
        assert E.normalize_rules(None) == []
        with __import__("pytest").raises(ValueError):
            E.normalize_rules([{"tag": "shout", "line": "five"}])
        assert E.normalize_done_when("one\n\n  two  ") == ["one", "two"]
        assert E.normalize_done_when(None) == []


def test_the_org_charter_proposal_writes_the_rules_and_identity_reads_them():
    """The whole path: file it, nothing changes, approve it, the card reads it."""
    with _fresh() as (M, E, tmp):
        import proposals
        root, desk, a, a1 = _tree(E, tmp)
        with _org2() as (api, apply_):
            rec = _file_charter(api, a, title="A Charter", purpose="Own the release.",
                                done_when=["every screen reads its own record"],
                                rules=[{"tag": "refuse", "line": "Never a third AI in one task"},
                                       {"tag": "go", "line": "Ship a patch without asking"}])
            assert M.identity(a)["rules"] == [], "a proposal applies nothing"
            assert M.identity(a)["goal"] is None
            out = proposals.decide(rec["id"], True, apply_fn=apply_.apply_request)
        assert out["status"] == "approved", out.get("result")
        card = M.identity(a)
        assert card["goal"] == "Own the release."
        assert card["done"] == "every screen reads its own record."
        assert card["rules"] == [
            {"tag": "refuse", "text": "Never a third AI in one task"},
            {"tag": "go", "text": "Ship a patch without asking"}]


def test_amending_a_charter_keeps_the_rules_it_was_not_asked_about():
    """A request that says nothing about a field keeps the prior value; one
    that sends it empty clears it. Both ride the succession, never an edit."""
    with _fresh() as (M, E, tmp):
        import proposals
        root, desk, a, a1 = _tree(E, tmp)
        with _org2() as (api, apply_):
            first = _file_charter(api, a, title="A Charter", purpose="Own the release.",
                                  done_when=["the screen reads its own record"],
                                  rules=[{"tag": "ask", "line": "Ask before a push"}])
            proposals.decide(first["id"], True, apply_fn=apply_.apply_request)
            cid = M._standing_charter(a)["id"]
            # a title-only edit: the rules are not mentioned and must survive
            second = _file_charter(api, a, charter_id=cid, title="The Charter",
                                   purpose="Own the release.")
            r2 = proposals.decide(second["id"], True, apply_fn=apply_.apply_request)
            assert r2["status"] == "approved", r2.get("result")
            assert M.identity(a)["rules"] == [{"tag": "ask", "text": "Ask before a push"}]
            assert M.identity(a)["done"] == "the screen reads its own record."
            # sending them empty is a deletion, and is meant to be
            third = _file_charter(api, a, charter_id=M._standing_charter(a)["id"],
                                  title="The Charter", purpose="Own the release.",
                                  done_when=[], rules=[])
            r3 = proposals.decide(third["id"], True, apply_fn=apply_.apply_request)
            assert r3["status"] == "approved", r3.get("result")
        assert M.identity(a)["rules"] == [] and M.identity(a)["done"] is None


def test_a_rule_change_alone_is_a_change():
    """The old guard compared the title and the purpose only, so an edit that
    reworded a rule read as "nothing changed" and was refused."""
    with _fresh() as (M, E, tmp):
        import proposals
        root, desk, a, a1 = _tree(E, tmp)
        with _org2() as (api, apply_):
            rec = _file_charter(api, a, title="A Charter", purpose="Own the release.")
            proposals.decide(rec["id"], True, apply_fn=apply_.apply_request)
            cid = M._standing_charter(a)["id"]
            again = _file_charter(api, a, charter_id=cid, title="A Charter",
                                  purpose="Own the release.",
                                  rules=[{"tag": "refuse", "line": "Never a third AI in one task"}])
            out = proposals.decide(again["id"], True, apply_fn=apply_.apply_request)
            assert out["status"] == "approved", out.get("result")
            assert M._standing_charter(a)["id"] != cid, "by succession, never in place"
            # and a request that truly changes nothing is still refused
            same = _file_charter(api, a, charter_id=M._standing_charter(a)["id"],
                                 title="A Charter", purpose="Own the release.",
                                 rules=[{"tag": "refuse", "line": "Never a third AI in one task"}])
            refused = proposals.decide(same["id"], True, apply_fn=apply_.apply_request)
            assert refused["status"] == "failed"
            assert "nothing changed" in refused["result"]["error"]


def test_identity_prefers_the_charters_own_rules_over_invariants():
    """DS-1's order of record: the charter's own tagged rules first, the
    invariants and constraints tagged `always` only when none is written."""
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _charter(E, a, "Own the release.",
                 invariants=["A mock is the app's own markup"],
                 constraints=["Never a third AI in one task"],
                 milestones=[{"label": "v1", "status": "now", "done_when": "the milestone line"}],
                 done_when=["the charter's own line"],
                 rules=[{"tag": "refuse", "line": "Never ship on a Friday"}])
        out = M.identity(a)
        assert out["rules"] == [{"tag": "refuse", "text": "Never ship on a Friday"}]
        assert out["done"] == "the charter's own line."


def test_identity_still_falls_back_to_the_milestones_and_the_invariants():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _charter(E, a, "Own the release.",
                 invariants=["A mock is the app's own markup"],
                 milestones=[{"label": "v1", "status": "now", "done_when": "the milestone line"}])
        out = M.identity(a)
        assert out["rules"] == [{"tag": "always", "text": "A mock is the app's own markup"}]
        assert out["done"] == "the milestone line."


def test_identity_ignores_a_rule_whose_tag_is_not_one_of_the_four():
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _charter(E, a, "Own the release.",
                 rules=[{"tag": "shout", "line": "five"}, {"tag": "go", "line": "Ship it"}])
        assert M.identity(a)["rules"] == [{"tag": "go", "text": "Ship it"}]


# --------------------------------------------------------------- DS-2 role --

def test_role_is_a_legal_charter_kind_and_junk_is_not():
    with _fresh() as (M, E, tmp):
        import fastapi
        import pytest as _pytest
        root, desk, a, a1 = _tree(E, tmp)
        assert E.CHARTER_KINDS == ("standing", "project", "role")
        cid = E.mint_charter_stub(a, "Reviewer", "Stamp the release notes.",
                                  [], [], "T-local", kind="role")
        assert E.load_charter(cid)["kind"] == "role"
        for legal in ("standing", "project"):
            assert E.mint_charter_stub(a, legal.title(), "A goal.", [], [], "T-local", kind=legal)
        with _pytest.raises(ValueError):
            E.mint_charter_stub(a, "Nope", "A goal.", [], [], "T-local", kind="wizard")
        with _org2() as (api, _apply):
            with _pytest.raises(fastapi.HTTPException) as exc:
                _file_charter(api, a, purpose="A goal.", kind="wizard")
            assert exc.value.status_code == 400
            with _pytest.raises(fastapi.HTTPException) as exc2:
                _file_charter(api, a, purpose="A goal.", rules=[{"tag": "shout", "line": "five"}])
            assert exc2.value.status_code == 400


def test_people_lists_a_role_with_its_person_after_the_owner():
    """A36, through the one writer: the role names the person, and `unfilled`
    is an answer rather than a blank."""
    with _fresh() as (M, E, tmp):
        import proposals
        root, desk, a, a1 = _tree(E, tmp)
        _charter(E, a, "Own the release.", authority={"name": "Meera"})
        with _org2() as (api, apply_):
            held = _file_charter(api, a, title="Reviewer", purpose="Stamp the release notes.",
                                 kind="role", person="Devansh")
            assert "for Devansh" in held["summary"], held["summary"]
            proposals.decide(held["id"], True, apply_fn=apply_.apply_request)
            open_role = _file_charter(api, a, title="Release manager", purpose="Run the release.",
                                      kind="role")
            proposals.decide(open_role["id"], True, apply_fn=apply_.apply_request)
        out = M.people(a)
        assert out["owner"]["name"] == "Meera", "the owner is still first"
        assert [r["title"] for r in out["roles"]] == ["Release manager", "Reviewer"]
        by_title = {r["title"]: r for r in out["roles"]}
        assert by_title["Reviewer"]["name"] == "Devansh"
        assert by_title["Reviewer"]["person"] == "Devansh"
        assert by_title["Reviewer"]["unfilled"] is False
        assert by_title["Reviewer"]["stamps"] == "Stamp the release notes."
        assert by_title["Release manager"]["person"] == "unfilled"
        assert by_title["Release manager"]["unfilled"] is True


def test_a_role_charter_appears_under_people_and_nowhere_else():
    """A role speaks for a person, not for the department, so it is never the
    charter Identity reads -- not even when it is the only one on the row."""
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        _charter(E, a, "Stamp the release notes.", title="Reviewer", kind="role",
                 person="Devansh", rules=[{"tag": "go", "line": "Ship a patch"}])
        card = M.identity(a)
        assert card["goal"] is None, "a role is not the department's goal"
        assert card["rules"] == [] and card["done"] is None
        assert M.filed(a)["filed"] == []
        assert [r["name"] for r in M.people(a)["roles"]] == ["Devansh"]
        _charter(E, a, "Own the release.", title="A Charter")
        assert M.identity(a)["goal"] == "Own the release."


# ------------------------------------------------------------ slice I, DS-8 --

def test_functions_reads_the_default_until_a_pick_is_stamped():
    """Slice I: every function runs its Default until an approved org.template
    ask picks another; the read lists each function's templates as picker rows,
    Default first, and never 500s on a broken picks file."""
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        out = M.functions(a)
        assert set(out["picked"]) == {"identity", "adaptation", "priority", "coordination", "audit"}
        assert all(v["id"].endswith("/default") for v in out["picked"].values())
        assert [r["id"] for r in out["templates"]["audit"]] == [
            "audit/default", "audit/money-movement", "audit/product-build"]
        assert all(set(r) == {"id", "name", "use_case"} for r in out["templates"]["audit"])
        sys.modules.pop("org2_apply", None)
        sys.modules.pop("org_apply", None)
        import org2_apply
        org2_apply.apply_request("org.template", {"ref": a, "function": "audit", "template": "audit/money-movement"})
        out = M.functions(a)
        assert out["picked"]["audit"] == {"id": "audit/money-movement", "name": "Money movement",
                                          "use_case": out["templates"]["audit"][1]["use_case"]}
        assert M.functions(a1)["picked"]["audit"]["id"] == "audit/default", "a child keeps its own picks"
        (tmp / "function_templates.json").write_text("[1, 2", encoding="utf-8")
        assert M.functions(a)["picked"]["audit"]["id"] == "audit/default"


def test_function_brief_is_the_picked_templates_and_404s_cleanly():
    from fastapi import HTTPException
    with _fresh() as (M, E, tmp):
        root, desk, a, a1 = _tree(E, tmp)
        b = M.function_brief(a, "Priority")
        assert b["template"]["id"] == "priority/default"
        for ph in ("{department}", "{goal}", "{done}", "{rules}", "{owner}", "{folder}"):
            assert ph in b["brief"]
        assert os.path.realpath(b["cwd"]) == os.path.realpath(str(tmp)), \
            "the department's working folder rides with the brief"
        for ref, fn in ((a, "payroll"), ("dref-none", "audit")):
            try:
                M.function_brief(ref, fn)
            except HTTPException as exc:
                assert exc.status_code == 404
            else:
                raise AssertionError("no 404 for %s %s" % (ref, fn))
