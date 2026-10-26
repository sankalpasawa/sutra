"""Every definition of the interface is bound to the writer that exists on main (PRD amendment A1.6, A1.27's P0): one
test per writer, each building that writer's output in a records home of its own, the way test_j2's fixture makes one,
and asserting that the interface takes it (S.validate(...) == []). A writer whose shape the interface refused would be
a write the app makes every day refused once the interface refuses, so these tests come before refuse mode.
"""
import importlib
import json

import pytest

import layer_schema as S

WEBSITE = "Build a website that teaches algebra to Class 8 students"
ORGANIC = "Set up a laboratory system to track chemical inventory for our school science team"
LINE = ["Plan", "Write", "Check", "Publish"]


@pytest.fixture
def j2(tmp_path, monkeypatch):
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


def _born(j2, words=WEBSITE, org="Acme Learning"):
    """A department as a person makes one: found the organisation, say the words, Root sets it up, and it settles."""
    W, _, _, founding, _ = j2
    root = founding.found_structure(org, owner="Sankalp")["root"]
    W.owner_ask(root, words)
    W.run_until_idle(root, limit=300)
    child = next(d for d in W.list_depts() if d.get("parent") == root)
    W.run_until_idle(child["ref"], limit=300)
    return child["ref"]


def _ok(name, value):
    got = S.validate(name, value)
    assert got == [], "%s: %s" % (name, got)


def _asks_ok(W, ref):
    for a in W.asks(ref):
        _ok("identity.ask", a)


# ---- the department record -------------------------------------------------------------------------------------------
@pytest.mark.parametrize("kind", ["website", "root", "default", "organic"])
def test_w_create_writes_a_department_of_every_kind(j2, kind):
    W = j2[0]
    d, _ = W.create("w-" + kind, "Acme " + kind, None, kind=kind)
    _ok("department", d)
    _ok("department", W.dept(d["ref"]))
    _ok("coordination.table", W._read(W.ddir(d["ref"]) / "coordination.json", None))


def test_founding_spawn_writes_the_root_and_the_child(j2):
    W = j2[0]
    ref = _born(j2)
    child = W.dept(ref)
    _ok("department", child)
    _ok("department", W.dept(child["root"]))
    assert child["founding"]["checkpoints"] and child["templates"] and child["done_items"]
    for wf in child.get("workflows") or []:
        _ok("workflow.registration", wf)
    _asks_ok(W, ref)
    _asks_ok(W, child["root"])


def test_founding_spawn_of_an_organic_department(j2):
    W = j2[0]
    ref = _born(j2, ORGANIC, "Lab Co")
    _ok("department", W.dept(ref))
    _asks_ok(W, ref)


# ---- Identity's records ----------------------------------------------------------------------------------------------
def test_w_done_items_keeps_how_and_level_as_said_and_the_store_takes_them(j2):
    W = j2[0]
    items = W.done_items([{"text": "Every page is live", "how": "code", "level": "outcome"},
                          {"text": "Each page reads well", "how": "by eye", "level": "a feeling", "confirm": "the owner gave no list"}])
    for i in items:
        _ok("identity.done_item", i)
    assert items[1]["how"] == "by eye", "the store keeps it; the covering judges it"
    for i in W.done_items(None, "website"):
        _ok("identity.done_item", i)


def test_w_rule_row_and_a_rule_with_no_tag(j2):
    W = j2[0]
    _ok("identity.rule", W.rule_row("always", "Every page ends with the school's name", words="always end with the name"))
    _ok("identity.rule", W.rule_row("ask", "Ask before a price goes on a page", scope="one-time"))
    _ok("identity.rule", {"line": "A rule nobody tagged"})
    _ok("identity.rule", {"tag": None, "line": "A rule tagged null"})
    for r in W.KINDS["website"]["rules"]:
        _ok("identity.rule", r)


def test_w_done_items_ask(j2):
    W = j2[0]
    ask = W.done_items_ask("Done when: add D2", [{"text": "A", "how": "code", "level": "target"},
                                                 {"text": "B", "how": "model", "level": "outcome", "confirm": "not given"}],
                           "the owner's words say when it is done", words="it is done when B", thread="x-1")
    _ok("identity.ask", ask)


def test_w_apply_done_items(j2):
    W = j2[0]
    d, _ = W.create("w-items", "Acme", None)
    ask = W.done_items_ask("Done when", [{"text": "A", "how": "code", "level": "target"},
                                         {"text": "B", "how": "model", "level": "outcome", "confirm": "not given"}], "why")
    d = W.apply_done_items("w-items", ask)
    _ok("department", d)
    assert d["to_be_confirmed"] == [{"item": "D2", "why": "not given"}]


def test_w_option_and_w_options_ask(j2):
    W = j2[0]
    opts = [W.option(W.WORDS_OPTION, "Change the plan in my words", "Adaptation shapes it afresh"),
            W.option("leave:D2", "Leave D2 out", "D2 is dropped from done-when (%s); nothing more is spent" % ("x" * 300)),
            W.option("stop", "Stop here", "the department stops where it is")]
    for o in opts:
        _ok("option", o)
    _ok("identity.ask", W.options_ask("blocked", "The plan is blocked", opts, title="Blocked", who="Root", why="x"))


def test_r_blocked_and_w_choose_option(j2):
    W, R, J, _, _ = j2
    ref = _born(j2)
    d = W.dept(ref)
    R._blocked(ref, d, {"src": "Owner"}, "Root's check sent the plan back: D2 has no engine.", "Blocked", "Root, at its review", "D2")
    R._blocked(ref, W.dept(ref), {"src": "Owner"}, "Again: D2 has no engine.", "Blocked", "Root, at its review", "D2")
    _asks_ok(W, ref)
    kinds = [(a["kind"], a["status"]) for a in W.asks(ref) if a["kind"] == "blocked"]
    assert kinds == [("blocked", "replaced"), ("blocked", "pending")]
    aid = next(a["id"] for a in W.asks(ref) if a["kind"] == "blocked" and a["status"] == "pending")
    a = W.choose_option(ref, aid, "stop")
    _ok("identity.ask", a)
    assert a["status"] == "chosen" and a["chosen"]["id"] == "stop"
    _asks_ok(W, ref)
    _ok("department", W.dept(ref))


def test_j_questioned_files_identitys_question(j2):
    W, R, J, _, _ = j2
    d, _ = W.create("w-thin", "Thin Website", None, kind="website")
    d["events"] = [{"kind": "j2_ready", "route": "template"}]
    W.save_dept(d["ref"], d)
    J.start("w-thin")
    J.questioned("w-thin", J.THIN, 1)
    asks = [a for a in W.asks("w-thin") if a["kind"] == "j2_identity"]
    assert asks and asks[0]["missing"] == "words"
    _asks_ok(W, "w-thin")


def test_r_identity_wait_engine_writes_asks_json_directly(j2):
    W, R, _, _, _ = j2
    d, _ = W.create("w-wait", "Acme", None)
    W._put_ask("w-wait", {"id": "a-eng00001", "kind": "engine", "engine": "Talks List", "offer": {}, "idea": None,
                          "text": "Add the engine Talks List?", "status": "pending", "created": W.now(), "thread": None})
    got = R.identity_wait_engine({"ref": "w-wait", "dept": W.dept("w-wait")}, None, None)
    assert got[0] == "wait"
    a = next(x for x in W.asks("w-wait") if x["id"] == "a-eng00001")
    assert a.get("told"), "the direct write marked it told"
    _asks_ok(W, "w-wait")


def test_r_instructions_ask(j2):
    W, R, _, _, _ = j2
    W.create("w-instr", "Acme", None)
    text = R._instruction("identity", "take").replace("Judge one request from the owner.", "Judge one request from the owner, briefly.")
    a = R.instructions_ask("w-instr", "identity", "take", text)
    _ok("identity.ask", a)


# ---- Coordination's records ------------------------------------------------------------------------------------------
def test_r_born_writes_coordinations_table(j2):
    W, R, _, _, _ = j2
    W.create("w-born", "Acme", None)
    t = R.born("w-born")
    _ok("coordination.table", t)
    assert t["by"] == "born"


def test_r_put_table_through_set_line_and_grow_line(j2):
    W, R, _, _, _ = j2
    ref = _born(j2)
    t = R.set_line(ref, ["Plan", "Write", "Check"], 2)
    _ok("coordination.table", t)
    _ok("coordination.table", W._read(W.ddir(ref) / "coordination.json", None))
    assert [r["engine"] for r in t["left_out"]] == ["Publish"]
    t = R.grow_line(ref, "Publish")
    _ok("coordination.table", t)
    assert t["grown"] == ["Publish"] and t["by"] == "Coordination"


def test_r_timetable_row_and_left_out_row(j2):
    W, R, _, _, _ = j2
    W.create("w-slot", "Acme", None)
    _ok("coordination.slot", R.timetable_row("Plan", R.slot_of("w-slot", "Plan"), 15))
    _ok("coordination.slot", R.timetable_row("Ticker", {"on": "every 1 h", "every_s": 3600}, 30))
    _ok("coordination.left_out", R.left_out_row("Publish"))


# ---- Priority's records ----------------------------------------------------------------------------------------------
def test_r_priority_grant_and_w_set_envelope(j2):
    W, R, _, _, _ = j2
    ref = _born(j2)
    R._ask_rule(ref, "priority.grant", {"engines": ["Plan", "Write"], "version": 1}, key="grant@test")
    for name, env in W.dept(ref)["envelopes"].items():
        _ok("envelope", env)
    env = W.set_envelope(ref, "Plan", calls=12, usd=2.5)
    _ok("envelope", env)
    _ok("department", W.dept(ref))


# ---- the line ---------------------------------------------------------------------------------------------------------
def test_w_add_engine_and_r_born_template(j2):
    W, R, _, _, _ = j2
    W.create("w-grow", "Acme", None)
    out = W.add_engine("w-grow", "Do", by="the owner's stamp")
    assert "Do" in out["engines"]
    _ok("department", W.dept("w-grow"))
    out = W.add_engine("w-grow", "Talks List", shape={"name": "Talks List", "use_case": "lists the school's talks",
                                                      "does": "lists the school's talks", "instruction": "List the talks.",
                                                      "needs": ["internet"], "reads": "Brief", "writes": "Talks"})
    _ok("department", W.dept("w-grow"))
    t = json.loads((R.user_templates_dir() / "talks-list.json").read_text(encoding="utf-8"))
    _ok("engine.template", t)
    assert t["made_by"]["by"] == "Adaptation"
    _ok("coordination.table", W._read(W.ddir("w-grow") / "coordination.json", None))


def test_j_registered_writes_the_workflow_on_the_record(j2):
    W, R, J, _, _ = j2
    ref = _born(j2)
    wf = W.dept(ref)["workflows"]
    assert wf and wf[-1]["engines"] == LINE
    for w in wf:
        _ok("workflow.registration", w)
    _ok("department", W.dept(ref))


def test_a_shaped_line_registers_and_its_born_engines_fit(j2):
    W, R, J, _, _ = j2
    ref = _born(j2, ORGANIC, "Lab Co")
    d = W.dept(ref)
    _ok("department", d)
    for w in d.get("workflows") or []:
        _ok("workflow.registration", w)
    for n in d.get("engines") or []:
        p = R.user_templates_dir() / (W.slug(n) + ".json")
        if p.exists():
            _ok("engine.template", json.loads(p.read_text(encoding="utf-8")))


# ---- the board's acts --------------------------------------------------------------------------------------------------
def test_an_owner_request_whose_words_hold_braces_is_act_words(j2):
    W, R, _, _, _ = j2
    ref = _born(j2)
    words = 'Add a page that shows {"a": {"b": 1}} and the template {{name}} as written }}'
    _, p = R.request(ref, words)
    _ok("act.words", p["payload"])
    assert p["payload"]["words"] == words


# ---- the views -------------------------------------------------------------------------------------------------------
def test_the_views_are_the_read_models_typed_as_they_are(j2):
    W, R, J, _, FV = j2
    ref = _born(j2)
    d, ak = W.dept(ref), W.asks(ref)
    cur = FV._cycle_state(ref)
    events = FV._events(ref, cur.get("cycle_id")) if cur.get("cycle_id") else []
    _ok("view.identity", FV._identity_part(ref, d, events))
    _ok("view.coordination", FV.coordination(ref))
    for name in LINE:
        _ok("view.engine_card", FV.engine_card(ref, name))
    for fn, view in (("Adaptation", "view.adaptation"), ("Priority", "view.priority"), ("Coordination", "view.coordination"),
                     ("Audit", "view.audit"), ("Identity", "view.identity")):
        _ok(view, FV._j2_part(ref, d, fn, events, ak))
        _ok(view, FV.function(ref, fn.lower())["j2"])
