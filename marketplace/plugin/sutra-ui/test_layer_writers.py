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
    a = R.instructions_ask("w-instr", "identity", "take", "take", "task", "Judge one request from the owner, briefly.")
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


# ---- S5: the sink, the post check and the test fixture (A1.20) --------------------------------------------------------
import os  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402

import record  # noqa: E402


def test_s5_an_unknown_key_saved_on_dept_json_is_one_fault_and_one_row_and_lands_in_warn_mode(j2, monkeypatch):
    monkeypatch.setattr(S, "MODE", "warn")      # this test is about warn mode: a fault is a row and the write goes through
    W = j2[0]
    W.create("s-colour", "Acme", None)
    d, runs = W.dept("s-colour"), len(W.runs("s-colour"))
    d["colour"] = "red"
    with S.expect_refused("department") as met:
        W.save_dept("s-colour", d)
    assert met == ["$.colour: is not a field here"]
    rows = W.runs("s-colour")[runs:]
    assert len(rows) == 1 and rows[0]["what"] == "kept a record that does not fit the interface: department: $.colour: is not a field here"
    assert W._read(W.ddir("s-colour") / "dept.json", None)["colour"] == "red", "warn mode: the write lands"
    d["goal"] = "A site for Acme"
    W.save_dept("s-colour", W.dept("s-colour"))          # the legacy key is not changed again, so it is not a fault again


def test_s5_dept_json_written_past_save_dept_is_a_fault(j2):
    W = j2[0]
    W.create("s-direct", "Acme", None)
    with S.expect_refused("department") as met:
        with pytest.raises(S.SchemaFault):
            W._write(W.ddir("s-direct") / "dept.json", W.dept("s-direct"))
    assert met == ["$: dept.json is written only by save_dept"]


def test_s5_an_asks_json_write_with_status_maybe_is_caught_whoever_writes_it(j2, monkeypatch):
    monkeypatch.setattr(S, "MODE", "warn")      # this test is about warn mode: a fault is a row and the write goes through
    W, R, _, _, _ = j2
    W.create("s-asks", "Acme", None)
    with S.expect_refused("identity.ask") as met:
        W._put_ask("s-asks", {"id": "a-maybe001", "kind": "publish", "status": "maybe", "text": "x", "created": W.now()})
    assert met == ["$.status: is not one of %s" % ", ".join(S.ASK_STATUSES)]
    with S.expect_refused("identity.ask") as met:
        W._write(W.ddir("s-asks") / "asks.json", W.asks("s-asks") + [{"id": "a-maybe002", "kind": "rung", "status": "maybe"}])
    assert met == ["$.status: is not one of %s" % ", ".join(S.ASK_STATUSES)], "only the new row is read again"
    # identity_wait_engine's direct write of asks.json passes the sink too: the row it changes is checked
    record.write(W.ddir("s-asks") / "asks.json", [{"id": "a-eng00002", "kind": "engine", "engine": "Talks List", "text": 7,
                                                  "status": "pending", "created": W.now()}])
    with S.expect_refused("identity.ask") as met:
        assert R.identity_wait_engine({"ref": "s-asks", "dept": W.dept("s-asks")}, None, None)[0] == "wait"
    assert met == ["$.text: is not a string"]


def test_s5_set_stopped_always_lands_even_in_refuse_mode(j2, monkeypatch):
    W = j2[0]
    W.create("s-stop", "Acme", None)
    raw = W._read(W.ddir("s-stop") / "dept.json", None)
    record.write(W.ddir("s-stop") / "dept.json", dict(raw, colour="a legacy fault"))
    monkeypatch.setattr(S, "MODE", "refuse")
    assert W.set_stopped("s-stop", True)["stopped"] is True, "a legacy key never blocks the owner's Stop"
    assert W.dept("s-stop")["stopped"] is True
    d = W.dept("s-stop")
    d["stopped"] = "yes"
    with S.expect_refused("department") as met:
        W.save_dept("s-stop", d)
    assert met == ["$.stopped: is not true or false"] and W.dept("s-stop")["stopped"] == "yes", "a row only, and it lands"
    d = W.dept("s-stop")
    d["windows"] = {"Plan": "fifteen"}
    with S.expect_refused("department"):
        with pytest.raises(S.SchemaFault):
            W.save_dept("s-stop", d)
    assert W.dept("s-stop")["windows"]["Plan"] == 15, "refuse mode: the write is refused after its row"
    assert W.set_stopped("s-stop", False)["stopped"] is False


def test_s5_a_v0_record_reads_as_the_current_version_and_the_next_save_writes_it(j2):
    W = j2[0]
    W.create("s-v0", "Acme", None)
    v0 = json.loads((S.HERE / "schemas" / "layers" / "fixtures" / "department.v0.json").read_text(encoding="utf-8"))
    v0.update({"ref": "s-v0", "parent": None, "root": None})
    record.write(W.ddir("s-v0") / "dept.json", v0)
    d = W.dept("s-v0")
    assert (d["schema_version"], d["layers"], d["done_items"][0]["id"]) == (2, S.DEFAULT_PINS, "D1")
    assert "schema_version" not in W._read(W.ddir("s-v0") / "dept.json", None), "a read never writes"
    W.save_dept("s-v0", d)
    on_disk = W._read(W.ddir("s-v0") / "dept.json", None)
    assert on_disk["schema_version"] == 2 and on_disk["layers"] == S.DEFAULT_PINS and on_disk["an_older_key"] == "kept on read"


def test_s5_an_owner_request_holding_braces_posts_and_files(j2):
    W, R, _, _, _ = j2
    ref = _born(j2)
    words = 'Add a page that shows the JSON {"a": {"b": 1}} and the template {{name}} as I wrote it }}'
    _, p = R.request(ref, words)
    assert p and p["payload"]["words"] == words
    W.run_until_idle(ref, limit=300)
    brief = W.read_files(ref, "Brief", W.latest(ref, "Brief")["v"])["brief.md"]
    assert '{"a": {"b": 1}}' in brief and "}}" in brief


def test_s5_a_post_that_does_not_fit_is_a_row_in_warn_mode_and_refused_in_refuse_mode(j2, monkeypatch):
    monkeypatch.setattr(S, "MODE", "warn")      # this test is about warn mode: a fault is a row and the write goes through
    W, R, _, _, _ = j2
    W.create("s-post", "Acme", None)
    n = len(R.board("s-post"))
    with S.expect_refused("act") as met:
        assert R.post("s-post", "Adaptation", "Priority", "propose", {"word": "grant"})
    assert len(met) == 1 and "Adaptation does not propose with the word 'grant'" in met[0]
    assert len(R.board("s-post")) == n + 1, "warn mode: the post goes through"
    monkeypatch.setattr(S, "MODE", "refuse")
    with S.expect_refused("act"):
        with pytest.raises(S.SchemaFault):
            R.post("s-post", "Adaptation", "Priority", "propose", {"word": "grant"})
    assert len(R.board("s-post")) == n + 1, "refuse mode: nothing is appended"
    assert R.post("s-post", "Adaptation", "Priority", "propose", {"word": "trial", "step": "write.page"}), "a post that fits goes"


def test_s5_append_row_checks_each_journal_row_and_rows_reads_them_back(j2, monkeypatch):
    monkeypatch.setattr(S, "MODE", "warn")      # this test is about warn mode: a fault is a row and the write goes through
    W = j2[0]
    W.create("s-rows", "Acme", None)
    row = {"id": "r-0123abcd", "v": 1, "artifact": "Live site", "read": False, "why_not_read": "it was not sampled",
           "items": [], "at": W.now()}
    assert W.append_row("s-rows", "readings.jsonl", row) == row
    assert W.rows("s-rows", "readings.jsonl") == [row]
    with S.expect_refused("audit.reading") as met:
        W.append_row("s-rows", "readings.jsonl", dict(row, id="reading-1"))
    assert met == ["$.id: does not match ^r-[0-9a-f]{8}$"] and len(W.rows("s-rows", "readings.jsonl")) == 2
    with pytest.raises(ValueError):
        W.append_row("s-rows", "colours.jsonl", {})


def test_s5_a_test_that_meets_a_fault_fails_through_the_conftest_fixture(tmp_path):
    ui = S.HERE
    (tmp_path / "conftest.py").write_text("exec(compile(open(%r).read(), 'conftest.py', 'exec'))\n" % str(ui / "conftest.py"),
                                          encoding="utf-8")
    (tmp_path / "test_scratch.py").write_text(
        "import layer_schema as S\n\n"
        "def test_a_bad_write():\n"
        "    try:\n"
        "        S.check('envelope', {'calls': -1, 'usd': 1.0})\n"
        "    except S.SchemaFault:\n"
        "        pass    # a caller that swallows the exception still leaves the row and the count\n\n"
        "def test_a_fault_it_expects():\n"
        "    with S.expect_refused('envelope') as met:\n"
        "        try:\n"
        "            S.check('envelope', {'calls': -1, 'usd': 1.0})\n"
        "        except S.SchemaFault:\n"
        "            pass\n"
        "    assert met == ['$.calls: below 0']\n", encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=str(ui))
    got = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "test_scratch.py"], cwd=str(tmp_path),
                         env=env, capture_output=True, text=True, timeout=120)
    assert got.returncode != 0, got.stdout
    assert "2 passed, 1 error" in got.stdout, "the bad write's test errors at its teardown; the one that expected it passes"
    assert "ERROR test_scratch.py::test_a_bad_write" in got.stdout
    assert "the test met 1 fault of the interface schema layer: envelope: $.calls: below 0" in got.stdout
