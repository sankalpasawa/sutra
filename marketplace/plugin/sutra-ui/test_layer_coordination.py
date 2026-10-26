"""Coordination behind its interface (PRD amendment A1.11, W1-COORD): layers/coordination/v1.py and the line it keeps.

  K1  every code, prompt, draft and check name Coordination's recipe uses is provided by the module itself, by reference
      (nineteen, none of them left to the legacy registries), and contract cases 1 to 4 and 7 pass for coordination/v1
  K3  set_line checks the line as a write before it puts the table: an engine no registered plan names and the owner did not add
      is one row in warn mode and a refusal in refuse mode (the line then stands as it was); a grown engine passes; every
      table written while a department of each kind settles validates
  K4  view() and engine_card() are functions_view's S7 and S17 read models by reference, and validate as view.coordination
      and view.engine_card in every state a department passes through (empty, running, waiting, alarm, stopped, done; an
      engine running, waiting, held, left out and stopped)
"""
import importlib
import json

import pytest

import layer_schema as S
import layers
import layers.contract as C
from layers.coordination import v1 as V1

WEBSITE = "Build a website that teaches algebra to Class 8 students"
ORGANIC = "Set up a laboratory system to track chemical inventory for our school science team"
LINE = ["Plan", "Write", "Check", "Publish"]


@pytest.fixture
def j2(tmp_path, monkeypatch):
    """test_j2's fixture: the records home and the registry in this test's own folder, the modules reloaded."""
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    monkeypatch.setenv("SUTRA_UI_PROPOSALS", str(tmp_path / "proposals"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.setenv("J1_FLOW_V1", "1")
    monkeypatch.setenv("J2_FLOW_V1", "1")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME", raising=False)

    import website_dept as W
    import founding
    import placement_engine as E
    import org2_apply
    import engine_runtime as R
    import j2_runtime as J
    import functions_view as FV

    for module in (E, W, org2_apply, founding, R, J, FV):
        importlib.reload(module)
    if not E.active_roots(E.load_domains()):
        E.mint_domain(None, "Sutra", ["Sutra"], "T-local", origin="operator-request")
    return W, R, J, founding, FV


def _recipe():
    return json.loads((layers.HERE / "coordination" / V1.RECIPE).read_text(encoding="utf-8"))


def _names(kind):
    """The names of one kind (code, prompt, draft, check) the recipe's steps, gates, rules and handlers use."""
    return {s[kind] for s in C._steps(_recipe()) if s.get(kind)}


# ---- K1: coordination/v1 by reference -----------------------------------------------------------------------------------
@pytest.mark.parametrize("kind", ["code", "prompt", "draft", "check"])
def test_k1_the_module_provides_every_name_its_recipe_uses_and_leaves_none_to_the_legacy_registries(kind):
    """A name the recipe uses that only engine_runtime's own registry holds, or a name the module holds that no step
    uses, must fail: the module names what its recipe needs, no more and no less."""
    mine = getattr(V1, kind.upper())
    assert set(mine) == _names(kind)
    assert _names(kind), "the recipe uses at least one %s" % kind


def test_k1_each_name_is_a_late_bound_delegate_to_the_body_the_runtime_holds_now(j2):
    """The delegate must reach the body the registry holds (a reloaded runtime's included), so no behaviour changes."""
    _, R, _, _, _ = j2
    registry = {"code": R.CODE, "prompt": R.PROMPT, "draft": R.DRAFT, "check": R.CHECK}
    for kind in registry:
        for name, fn in getattr(V1, kind.upper()).items():
            module, attr = fn.legacy
            assert module == "engine_runtime"
            assert getattr(R, attr) is registry[kind][name], (kind, name, attr)


def test_k1_nineteen_by_reference_and_none_of_its_own():
    assert C.by_reference(V1) == {"by_reference": 19, "own": 0}


@pytest.mark.parametrize("case", [c for c in C.cases() if c[0] in (1, 2, 3, 4, 7)], ids=lambda c: "case %d" % c[0])
def test_k1_contract_cases_1_to_4_and_7_pass_for_coordination_v1(case, j2):
    _, what, fn = case
    assert fn(V1, {}) == [], what


def test_k1_the_recipe_is_the_one_the_default_pin_names():
    assert S.DEFAULT_PINS["coordination"] == C.impl_id(V1) == "coordination/v1"
    assert layers.recipes()["Coordination"] == _recipe()


# ---- K4: Coordination's view and the engine card ------------------------------------------------------------------------
def _born(j2, words=WEBSITE, org="Acme Learning", settle=True):
    """A department as a person makes one (test_j2's way): found the organisation, say the words, Root sets it up."""
    W, _, _, founding, _ = j2
    root = founding.found_structure(org, owner="Sankalp")["root"]
    W.owner_ask(root, words)
    W.run_until_idle(root, limit=300)
    child = next(d for d in W.list_depts() if d.get("parent") == root)
    if settle:
        W.run_until_idle(child["ref"], limit=300)
    return child["ref"]


def _brief_again(W, ref, words="Add a page for the timetable of the algebra classes"):
    """The owner's words filed as the next Brief: the line has new work at its head."""
    v = W.latest(ref, "Brief")["v"]
    W.add_version(ref, "Brief", {"brief.md": words}, [{"art": "Brief", "v": v}], "owner", {"ok": True, "notes": []})


def _view(j2, ref):
    W = j2[0]
    return V1.view(ref, W.dept(ref), [], W.asks(ref))


def _rows(c):
    return {r["engine"]: r for r in c["timetable"]}


def _empty(j2, monkeypatch):
    """Before Root's check: the department is born and the plan is not registered yet (S7, Empty)."""
    return _born(j2, settle=False)


def _waiting(j2, monkeypatch):
    """Settled: Plan, Write and Check ran, and Publish waits for the owner's stamp."""
    return _born(j2)


def _running(j2, monkeypatch):
    """A new Brief, and Plan is running on it: the rest wait their turn."""
    W, R, _, _, _ = j2
    ref = _born(j2)
    _brief_again(W, ref)
    W._put_run(ref, R._run_row("Plan", False, "Plan@brief.v2", "running", "plans the pages"))
    return ref


def _alarm(j2, monkeypatch):
    """A run past its window: Coordination's own rule raises the alarm and the owner is asked."""
    W, R, _, _, _ = j2
    ref = _born(j2)
    _brief_again(W, ref)
    long_ago = "2020-01-01T00:00:00+00:00"
    W._put_run(ref, dict(R._run_row("Plan", False, "Plan@brief.v2", "running", "plans the pages"), started=long_ago))
    R.coord_alarm({"ref": ref, "dept": W.dept(ref), "rs": W.runs(ref)}, None, None)
    return ref


def _stopped(j2, monkeypatch):
    W = j2[0]
    ref = _born(j2)
    W.set_stopped(ref, True)
    return ref


def _done(j2, monkeypatch):
    """The owner stamped what waited and every engine ran: nothing waits, nothing is held."""
    W = j2[0]
    ref = _born(j2)
    for a in [a for a in W.asks(ref) if a["status"] == "pending"]:
        W.decide_ask(ref, a["id"], True)
    W.run_until_idle(ref, limit=300)
    return ref


def _left_out(j2, monkeypatch):
    """Priority asked for less (room for three), so the registered plan leaves Publish out of the line."""
    _, R, _, _, _ = j2
    monkeypatch.delenv("SUTRA_WEBSITE_OFFLINE", raising=False)
    monkeypatch.setattr(R, "MODEL", lambda prompt, step: (
        ({"answer": "counter", "why": "room for three today", "keep": ["Plan", "Write", "Check"]} if "- Publish:" in prompt
         else {"answer": "accept", "why": "the envelope has room"}), 0.01, "model") if step["id"] == "priority.bargain" else (None, 0.0, "offline"))
    return _born(j2, org="Counter Co")


def _held(j2, monkeypatch):
    """Write ran and spent its day's limit (Priority holds it); Publish waits for the stamp (Identity holds it)."""
    W, R, _, _, _ = j2
    ref = _born(j2)
    W._put_run(ref, R._run_row("Write", False, None, "ok", "wrote a page", spend={"calls": 3, "usd": 0.1}))
    W.set_envelope(ref, "Write", calls=2)
    return ref


VIEW_STATES = {"empty": _empty, "running": _running, "waiting": _waiting, "alarm": _alarm, "stopped": _stopped, "done": _done}


@pytest.mark.parametrize("state", list(VIEW_STATES))
def test_k4_view_coordination_validates_in_every_state_and_says_what_the_state_is(state, j2, monkeypatch):
    """A view that fails the interface in a state a department really passes through, or a fixture that is not the state it
    is named for, must fail."""
    ref = VIEW_STATES[state](j2, monkeypatch)
    c = _view(j2, ref)
    assert S.validate_view("coordination", c) == [], state
    assert S.validate_view("coordination", c) == S.validate("view.coordination", c)
    assert tuple(c) == S.COORDINATION_FIELDS
    rows = _rows(c)
    if state == "empty":
        assert (c["timetable"], c["holds"], c["left_out"], c["registered"]) == ([], [], [], None), "no plan yet, nothing waits"
    elif state == "running":
        assert rows["Plan"]["state"] == "running" and rows["Write"]["state"] == "waits"
        assert rows["Write"]["why"] == "Site plan v2 is not filed yet" and c["registered"] == 1
    elif state == "waiting":
        assert (rows["Publish"]["state"], rows["Publish"]["why"]) == ("waits", "waits for the stamp")
        assert [rows[n]["state"] for n in ("Plan", "Write", "Check")] == ["ran"] * 3 and c["alarms"] == []
    elif state == "alarm":
        assert [(a["engine"], a["text"]) for a in c["alarms"]] == [("Plan", "Plan has run past its window")]
    elif state == "stopped":
        assert {r["word"] for r in c["timetable"]} == {"stopped where it was"}
    else:
        assert [r["state"] for r in c["timetable"]] == ["ran"] * 4 and c["holds"] == [] and c["alarms"] == []


@pytest.mark.parametrize("state", list(VIEW_STATES))
def test_k4_the_view_is_the_read_model_of_the_pane_by_reference(state, j2, monkeypatch):
    """The module's view is the very read the S7 pane renders (functions_view.coordination, and the J2 part of the
    function's page), so nothing the screen shows changes."""
    _, _, _, _, FV = j2
    ref = VIEW_STATES[state](j2, monkeypatch)
    W = j2[0]
    assert _view(j2, ref) == FV.coordination(ref, W.dept(ref), ak=W.asks(ref))
    assert _view(j2, ref) == FV._j2_part(ref, W.dept(ref), "Coordination", [], W.asks(ref))
    assert _view(j2, ref) == FV.function(ref, "coordination")["j2"]


CARD_STATES = {
    # state: (how the department is made, the engine whose card is read, the card's head state)
    "running": (_running, "Plan", "running"),
    "waiting": (_running, "Write", "waits"),
    "held": (_waiting, "Publish", "waits"),
    "left out": (_left_out, "Publish", "left_out"),
    "stopped": (_stopped, "Write", "stopped"),
}


@pytest.mark.parametrize("state", list(CARD_STATES))
def test_k4_view_engine_card_validates_for_an_engine_in_every_state(state, j2, monkeypatch):
    make, engine, head = CARD_STATES[state]
    ref = make(j2, monkeypatch)
    _, _, _, _, FV = j2
    card = V1.engine_card(ref, engine)
    assert S.validate_view("engine_card", card) == [], state
    assert tuple(card) == S.ENGINE_CARD_FIELDS and [r["fn"] for r in card["five"]] == [S.TITLE[x] for x in S.FUNCTION_LAYERS]
    assert card["head"]["state"] == head and card == FV.engine_card(ref, engine), "the card is S17's read, by reference"


def test_k4_an_engine_held_by_identity_or_by_priority_says_who_holds_it(j2, monkeypatch):
    ref = _held(j2, monkeypatch)
    five = {r["fn"]: r for r in V1.engine_card(ref, "Publish")["five"]}
    assert (five["Identity"]["state"], five["Coordination"]["state"]) == ("warn", "wait")
    assert S.validate_view("engine_card", V1.engine_card(ref, "Publish")) == []
    write = V1.engine_card(ref, "Write")
    assert {r["fn"]: r for r in write["five"]}["Priority"]["state"] == "block" and S.validate_view("engine_card", write) == []


def test_k4_the_card_of_an_engine_outside_the_line_says_so_and_of_no_department_is_none(j2, monkeypatch):
    W, _, _, _, _ = j2
    ref = _waiting(j2, monkeypatch)
    card = V1.engine_card(ref, "Ticker")
    assert (card["head"]["state"], card["head"]["word"]) == ("quiet", "not in the line") and S.validate_view("engine_card", card) == []
    assert V1.engine_card("dref-nobody", "Plan") is None
    assert W.dept(ref)["runtime"] == 2 and C.case_6(V1, {"ref": ref}) == [], "the contract's case 6 reads the same view"


def test_k4_the_reads_write_nothing_and_never_call_the_model(j2, monkeypatch):
    W, R, _, _, _ = j2
    ref = _running(j2, monkeypatch)
    called = []
    monkeypatch.setattr(R, "MODEL", lambda prompt, step: called.append(step) or (None, 0.0, "offline"))
    import os
    home = str(W.ddir(ref))
    snap = {p: os.path.getmtime(os.path.join(home, p)) for p in os.listdir(home)}
    _view(j2, ref)
    V1.engine_card(ref, "Plan")
    assert {p: os.path.getmtime(os.path.join(home, p)) for p in os.listdir(home)} == snap and called == []


# ---- K3: the line is checked on write ---------------------------------------------------------------------------------------
def _table(W, ref):
    return W._read(W.ddir(ref) / "coordination.json", None)


def _coordination_rows(W, ref):
    return [r for r in W.runs(ref) if r.get("system") and r.get("engine") == "Coordination" and "interface" in str(r.get("what"))]


def test_k3_a_hand_made_table_naming_an_unregistered_engine_is_caught_with_one_row(j2):
    """A line with an engine nobody registered or added, written with no word, must fail: one row, by Coordination, and in
    warn mode the write goes through."""
    W, R, _, _, _ = j2
    ref = _born(j2)
    with S.expect_refused() as met:
        t = R.set_line(ref, LINE + ["Ghost"], 2)
    assert len(met.rows) == 1 and met.rows[0]["name"] == "coordination.table" and met.rows[0]["owner"] == "coordination"
    assert met.rows[0]["ref"] == ref and met.rows[0]["kept"] is True, "warn mode: a row, and the write goes through"
    assert any("Ghost" in f or "engines[4]" in f for f in met), met      # a standard names it; the shape row says where
    assert t["line"] == LINE + ["Ghost"] and _table(W, ref)["line"] == LINE + ["Ghost"]
    rows = _coordination_rows(W, ref)
    assert len(rows) == 1 and "kept a record that does not fit the interface: coordination.table" in rows[0]["what"]


def test_k3_in_refuse_mode_the_unregistered_line_is_not_written_and_the_handler_says_the_line_stands(j2, monkeypatch):
    """Refuse mode must raise after the row and leave the table as it was; Coordination's handler keeps the line it had and
    says so, so the board never meets the exception."""
    W, R, _, _, _ = j2
    ref = _born(j2)
    before = (W.ddir(ref) / "coordination.json").read_bytes()
    monkeypatch.setattr(S, "MODE", "refuse")
    with S.expect_refused() as met:
        with pytest.raises(S.SchemaFault) as caught:
            R.set_line(ref, LINE + ["Ghost"], 2)
    assert caught.value.name == "coordination.table" and len(met.rows) == 1 and met.rows[0]["kept"] is False
    assert (W.ddir(ref) / "coordination.json").read_bytes() == before, "nothing was written"
    assert _coordination_rows(W, ref)[0]["what"].startswith("refused a write that does not fit the interface")
    # the handler an engine born is heard by: it keeps the line it had, says why, and does not raise
    with S.expect_refused() as met:
        got = R.coord_table(R._coord_ctx(ref), {}, {"engines": LINE + ["Ghost"], "version": 2, "full": True})
    assert got["line"] == LINE and got["said"].startswith("kept the line it had: ") and ("Ghost" in got["said"] or "engines[4]" in got["said"])
    assert len(met.rows) == 1 and (W.ddir(ref) / "coordination.json").read_bytes() == before


def test_k3_the_line_is_checked_before_the_table_is_put(j2, monkeypatch):
    """A check that runs after the write (when the table is already on the record) must fail."""
    W, R, _, _, _ = j2
    ref = _born(j2)
    seen, put = [], R._put_table
    with S.expect_refused() as met:
        monkeypatch.setattr(R, "_put_table", lambda r, t, why: seen.append(len(met.rows)) or put(r, t, why))
        R.set_line(ref, LINE + ["Ghost"], 2)
    assert seen == [1] and len(met.rows) == 1, "the row was there when the table was about to be put"


def test_k3_a_grown_engine_passes_and_stays_on_the_line_through_a_later_registration(j2):
    """An engine the owner added (J5), merged into the line again by the next registration, must not be a fault."""
    W, R, J, _, _ = j2
    ref = _born(j2)
    W.add_engine(ref, "Do")
    assert _table(W, ref)["grown"] == ["Do"] and R.coordination(ref)["line"] == ["Do"] + LINE
    d = W.dept(ref)
    with S.expect_refused() as met:
        R._j2_settle(ref, d, [{"name": n} for n in LINE[:3]], "library", d.get("goal"), "a test")
    assert met == [], met
    t = _table(W, ref)
    assert (t["registered"], t["line"], t["grown"]) == (2, ["Do"] + LINE[:3], ["Do"]) and S.validate("coordination.table", t) == []


def test_k3_a_line_of_shaped_engines_is_read_with_its_registrations_source(j2):
    """An organic department's line (source shaped, engines born from its own templates) is no fault: the check reads the
    source of the plan Root registered, not the Library's."""
    W, R, _, _, _ = j2
    ref = _born(j2, words=ORGANIC, org="Lab Co")
    d = W.dept(ref)
    assert d["workflows"][-1]["source"] == "shaped" and _table(W, ref)["line"] == d["workflows"][-1]["engines"]
    with S.expect_refused() as met:
        t = R.set_line(ref, d["workflows"][-1]["engines"], 2)
    assert met == [] and S.validate("coordination.table", t) == []


@pytest.mark.parametrize("words,org", [(WEBSITE, "Acme Learning"), (ORGANIC, "Lab Co")])
def test_k3_every_table_written_as_a_department_settles_validates(words, org, j2):
    """Every write of the table, born and each line, is read back as coordination.table, and none met a fault."""
    W, R, _, _, _ = j2
    start = S.REFUSED["count"]
    written = []
    put = W._write
    import website_dept
    orig = website_dept._write
    website_dept._write = lambda p, obj: (written.append(obj) if str(p).endswith("coordination.json") else None) or orig(p, obj)
    try:
        ref = _born(j2, words=words, org=org)
        for a in [a for a in W.asks(ref) if a["status"] == "pending"]:
            W.decide_ask(ref, a["id"], True)
        W.run_until_idle(ref, limit=300)
    finally:
        website_dept._write = orig
    assert written, "the table was written"
    assert [S.validate("coordination.table", t) for t in written] == [[]] * len(written)
    assert {t["by"] for t in written} <= {"born", "Coordination"}
    assert S.REFUSED["count"] == start, S.REFUSED["rows"][start:]
