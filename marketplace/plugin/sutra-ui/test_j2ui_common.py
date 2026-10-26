"""test_j2ui_common.py -- the J2 view's scope, its cache, its journal tails and its empty shapes (j2ui_common.py; UI port step C1).

Named claims:
  C1-1  the state has exactly the prototype's 56 keys (the literal list, the prototype's own snapshot when it is here, the captured
        state when verify committed one), and EMPTY_STATE has exactly them
  C1-2  need() is the one scope: an unknown ref, a ref with path characters, a runtime-1 department, a Root and the kinds
        default and organic are all NotJ2; a runtime-2 website department is not
  C1-3  one read per signature: a second get_ctx with no file change reads nothing; a change rebuilds only after MIN_REBUILD_S
        unless touch(ref) was called
  C1-4  JournalTail reads 5,000 rows once and then only the row appended later, survives a torn last line, and re-reads after
        a truncation; the ledger is read from its last seq
  C1-5  caches are keyed by (home, ref): two homes in one process that reuse a ref never see each other
  C1-6  clean() leaves build/v1/index.html and 5/6/2026 alone, shortens an absolute path to its file name and drops a private key
  C1-7  a department with no cycle is 'not_started'; a broken sub-read leaves its attribute empty, says why, and still gives a ctx
  C1-8  the W-k numbering, who/dest/fn_id and step_at, on a department Root set up
"""
import ast
import json
import os
from pathlib import Path

import pytest

from test_fixtures.j2ui import proto
from test_fixtures.j2ui.core_fixtures import *  # noqa: F401,F403

import j2ui_common as C

KEYS56 = ["chat", "total", "status", "thinking", "step", "steps", "goal", "stamped", "workflows", "budget", "spent", "conflicts",
          "audits", "versions", "cycle", "calls", "error", "done", "atoms_v1", "turn", "cycle_turns", "max_turns", "paused",
          "outcome", "style", "rubric", "playbooks", "playbooks_used", "playbook_saved", "mock", "model", "fixes",
          "force_audit_fail", "test_lessons", "force_question", "has_board", "placeholders", "report", "sections", "write_lock",
          "agents", "lanes", "call_log", "workable", "memory", "lessons", "lessons_used", "lessons_saved", "output",
          "output_label", "doc", "conditions", "files", "docset", "docset_files", "saved"]
UI = Path(__file__).resolve().parent


def spy(monkeypatch, obj, name):
    real, calls = getattr(obj, name), []

    def wrapped(*a, **k):
        calls.append(a)
        return real(*a, **k)
    monkeypatch.setattr(obj, name, wrapped)
    return calls


# ---- C1-1: the shapes -------------------------------------------------------------------------------------------------
def test_c11_the_state_has_the_prototypes_56_keys():
    assert list(C.STATE_KEYS) == KEYS56 and len(set(KEYS56)) == 56
    assert list(C.EMPTY_STATE()) == KEYS56
    # the work package's thirteen are among them
    assert set(C.WORK_KEYS) <= set(KEYS56) and len(C.WORK_KEYS) == 13
    # a fresh copy each call: nobody shares the lists
    a, b = C.EMPTY_STATE(), C.EMPTY_STATE()
    a["chat"].append(1)
    assert b["chat"] == [] and C.EMPTY_STATE["chat"] == []


def test_c11_the_keys_are_the_prototypes_own_snapshot():
    """J2Run.snapshot (48 keys) + output_info (7 more) + saved (j2_server), read from the pinned j2.py without running it."""
    tree = ast.parse(proto.show("j2.py").decode("utf-8"))
    snap = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "snapshot")
    keys = next([k.value for k in r.value.keys if isinstance(k, ast.Constant)]
                for r in ast.walk(snap) if isinstance(r, ast.Return) and isinstance(r.value, ast.Dict))
    info = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "output_info")
    more = next([k.value for k in r.value.keys] for r in ast.walk(info) if isinstance(r, ast.Return))
    assert list(dict.fromkeys(keys + more + ["saved"])) == KEYS56


def test_c11_the_captured_state_when_there_is_one():
    """The prototype's own states, captured by j2ui-verify (plain or gzipped JSON, a state or a bundle that holds one)."""
    import gzip
    d = UI / "test_fixtures" / "j2ui" / "captured"
    files = sorted(list(d.glob("*.json")) + list(d.glob("*.json.gz"))) if d.is_dir() else []
    found = []

    def states(x, depth=0):
        if isinstance(x, dict) and {"chat", "total", "status"} <= set(x):
            found.append(x)
        elif isinstance(x, (dict, list)) and depth < 3:
            for v in (x.values() if isinstance(x, dict) else x):
                states(v, depth + 1)
    for f in files:
        try:
            raw = gzip.open(f, "rt", encoding="utf-8").read() if f.suffix == ".gz" else f.read_text(encoding="utf-8")
            states(json.loads(raw))
        except (OSError, ValueError):
            continue
    if not found:
        pytest.skip("test_fixtures/j2ui/captured holds no captured state yet (j2ui-verify T1)")
    for st in found:
        assert set(st) == set(KEYS56) and list(st) == KEYS56


def test_c11_the_other_empty_shapes_are_the_prototypes():
    assert C.EMPTY_BOARD == {"schema": "board/1", "entries": []} and C.EMPTY_BOARD() is not C.EMPTY_BOARD
    assert C.EMPTY_ARTIFACTS() == {"deliverables": [], "records": []}
    assert C.EMPTY_DOCS() == {k: {"asked": False, "text": None, "workflows": []} for k in ("prd", "hld", "lld")}
    assert C.EMPTY_REFS() == {"conditions": {}, "rubric": {}} and C.EMPTY_PREVIEW() == {"anchor": None, "html": None}
    m = C.EMPTY_MAP("why not")
    assert list(m) == ["schema", "run", "live", "status", "nodes", "edges", "legend", "built_from", "not_recorded"]
    assert m["schema"] == "map/1" and m["not_recorded"] == ["why not"] and len(m["legend"]) == 14


def test_c11_the_legend_is_the_prototypes():
    if proto.skip_reason():
        pytest.skip(proto.skip_reason())
    assert C.LEGEND == proto.consts("j2_map.py", "LEGEND") and C.EMPTY_MAP()["legend"] == C.LEGEND


# ---- C1-2: the scope --------------------------------------------------------------------------------------------------
def test_c12_need_is_the_one_scope(mods, monkeypatch):
    W = mods.W
    assert C.need(REF)["ref"] == REF and C.is_j2_kind("website") and not C.is_j2_kind("default")
    for bad in ("dref-nobody", "../x", "a/b", "..", ".", "", "x" * 200, None, 7):
        with pytest.raises(C.NotJ2):
            C.need(bad)
    W.create("dref-root", "Acme", None, kind="root")
    W.create("dref-def", "Defaulted", None, kind="default")
    W.create("dref-org", "Organic", None, kind="organic")
    for ref in ("dref-root", "dref-def", "dref-org"):
        assert W.dept(ref)["runtime"] == 2
        with pytest.raises(C.NotJ2):
            C.need(ref)
    monkeypatch.setenv("SUTRA_ENGINE_RUNTIME", "1")
    W.create("dref-old", "Old way", None, kind="website")
    assert W.dept("dref-old")["runtime"] == 1
    with pytest.raises(C.NotJ2):
        C.need("dref-old")


# ---- C1-3: one read per signature -------------------------------------------------------------------------------------
def test_c13_a_second_read_with_no_change_reads_nothing(mods, monkeypatch):
    W, R, F, J = mods.W, mods.R, mods.F, mods.J
    monkeypatch.setattr(C, "_now", lambda: 1_000_000.0)
    first = C.get_ctx(REF)
    calls = {n: spy(monkeypatch, o, n) for o, n in ((W, "runs"), (W, "asks"), (R, "step_rows"), (F, "functions"), (J, "events_after"))}
    again = C.get_ctx(REF)
    assert again is first and not any(calls.values()), {k: len(v) for k, v in calls.items()}
    for _ in range(50):
        assert C.get_ctx(REF) is first
    assert not any(calls.values())


def test_c13_a_change_rebuilds_after_the_floor_unless_touched(mods, monkeypatch):
    W, R = mods.W, mods.R
    now = [1_000_000.0]
    monkeypatch.setattr(C, "_now", lambda: now[0])
    first = C.get_ctx(REF)
    assert first.posts == []
    post(mods, "Identity", "Adaptation", "request", {"word": "line", "words": "x"})
    assert C.get_ctx(REF) is first, "inside the floor the read stands, though the board changed"
    now[0] += C.MIN_REBUILD_S + 0.1
    second = C.get_ctx(REF)
    assert second is not first and len(second.posts) == 1
    post(mods, "Identity", "Adaptation", "request", {"word": "line", "words": "y"})
    assert C.get_ctx(REF) is second
    C.touch(REF)
    third = C.get_ctx(REF)
    assert third is not second and len(third.posts) == 2
    assert C.get_ctx(REF) is third, "touch lifts the wait once"
    # a new ten-second tick is a new signature, but the floor still holds
    now[0] += 11
    assert C.get_ctx(REF) is not third


# ---- C1-4: journal tails ----------------------------------------------------------------------------------------------
def test_c14_the_tail_reads_only_what_was_appended(tmp_path):
    p = tmp_path / "board.jsonl"
    rows = [json.dumps({"n": i, "src": "Identity", "payload": {"words": "w" * 40}}) for i in range(1, 5001)]
    p.write_text("\n".join(rows) + "\n", encoding="utf-8")
    t = C.JournalTail(p)
    got = t.rows()
    assert len(got) == 5000 and t.last_read == p.stat().st_size and t.bytes_read == t.last_read
    before = t.bytes_read
    assert len(t.rows()) == 5000 and t.last_read == 0 and t.bytes_read == before
    extra = json.dumps({"n": 5001, "src": "Owner"}) + "\n"
    with open(p, "a", encoding="utf-8") as f:
        f.write(extra)
    got = t.rows()
    assert len(got) == 5001 and got[-1]["n"] == 5001 and t.last_read == len(extra.encode("utf-8"))
    assert len(t.rows()) == 5001 and t.last_read == 0
    assert got is not t.rows(), "each call hands out its own list"


def test_c14_a_torn_line_is_skipped_and_a_truncated_journal_is_read_again(tmp_path):
    p = tmp_path / "steps.jsonl"
    p.write_text('{"n": 1}\n{"n": 2}\n{"n": 3, "torn', encoding="utf-8")
    t = C.JournalTail(p)
    assert [r["n"] for r in t.rows()] == [1, 2], "the unfinished line is left unread"
    with open(p, "a", encoding="utf-8") as f:
        f.write('x\n{"n": 4}\n')                          # the torn line is now a whole line that is not JSON: skipped, as record.lines skips it
    assert [r["n"] for r in t.rows()] == [1, 2, 4]
    p.write_text('{"n": 9}\n', encoding="utf-8")            # shorter: read again whole
    assert [r["n"] for r in t.rows()] == [9]
    os.remove(p)
    assert t.rows() == []
    p.write_text('{"n": 5}', encoding="utf-8")             # a last line with no newline that parses is a row (record.lines reads it)
    assert [r["n"] for r in t.rows()] == [5]
    with open(p, "a", encoding="utf-8") as f:
        f.write('\n{"n": 6}\n')
    assert [r["n"] for r in t.rows()] == [5, 6]


def test_c14_a_replaced_journal_is_read_again(tmp_path):
    p = tmp_path / "j.jsonl"
    p.write_text('{"n": 1}\n{"n": 2}\n', encoding="utf-8")
    t = C.JournalTail(p)
    assert len(t.rows()) == 2
    q = tmp_path / "other"
    q.write_text('{"n": 7}\n{"n": 8}\n{"n": 9}\n', encoding="utf-8")
    os.replace(q, p)                                        # another inode, and longer
    assert [r["n"] for r in t.rows()] == [7, 8, 9]


def test_c14_the_ledger_is_read_from_its_last_seq(mods, monkeypatch):
    m = mods
    cycle(m, "running", 6)
    for i in range(3):
        event(m, "slot.assigned", key="k%d" % i)
    calls = spy(monkeypatch, m.J, "events_after")
    monkeypatch.setattr(C, "_now", lambda: 1_000_000.0)
    c = C.get_ctx(REF)
    assert [e["seq"] for e in c.events] == [1, 2, 3] and [a[1] for a in calls] == [0]
    event(m, "run.started", key="k9")
    C.touch(REF)
    c = C.get_ctx(REF)
    assert [e["seq"] for e in c.events] == [1, 2, 3, 4] and [a[1] for a in calls] == [0, 3], "only after seq 3"
    C.touch(REF)
    C.get_ctx(REF)
    assert [a[1] for a in calls] == [0, 3], "a ledger that did not grow is not read"


# ---- C1-5: the home is part of the key --------------------------------------------------------------------------------
def test_c15_two_homes_reusing_a_ref_never_see_each_other(mods, tmp_path, monkeypatch):
    m = mods
    post(m, "Identity", "Adaptation", "request", {"word": "line", "words": "in the first home"})
    first = C.get_ctx(REF)
    assert len(first.posts) == 1 and first.d["name"] == "City Care Hospital Website"
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "second-home"))
    m.W.create(REF, "Another Website", None, kind="website")
    second = C.get_ctx(REF)
    assert second is not first and second.d["name"] == "Another Website" and second.posts == []
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    assert C.get_ctx(REF) is first, "the first home's read is still the first home's"


# ---- C1-6: nothing private, no path of this machine -------------------------------------------------------------------
def test_c16_clean_keeps_relative_paths_and_dates_and_shortens_machine_paths():
    got = C.clean({"file": "build/v1/index.html", "when": "due 5/6/2026 and 24/7/365", "words": "see /Users/x/y/z.txt.",
                   "win": "C:\\Users\\x\\f.txt now", "home": "in ~/notes/a.md, ok", "tmp": "/private/var/folders/ab/cd/ef.json",
                   "url": "https://example.test/var/log/x", "token": "t", "nested": [{"Password": "p", "keep": "ok"}], "n": 3})
    assert got["file"] == "build/v1/index.html" and got["when"] == "due 5/6/2026 and 24/7/365"
    assert got["words"] == "see z.txt." and got["win"] == "f.txt now" and got["home"] == "in a.md, ok"
    assert got["tmp"] == "ef.json" and got["url"] == "https://example.test/var/log/x"
    assert "token" not in got and got["nested"] == [{"keep": "ok"}] and got["n"] == 3
    assert C.clean("/Users/x/y/z.txt") == "z.txt" and C.clean(("a", "/etc/hosts")) == ["a", "hosts"]


def test_c16_times():
    assert C.hhmmss("2026-10-26T22:44:21+05:30") == "22:44:21" and C.hhmmss("nonsense") == "" and C.hhmmss(None) == ""
    assert C.epoch("2026-10-26T22:44:21+05:30") - C.epoch("2026-10-26T22:44:20+05:30") == 1.0
    assert C.epoch("") == 0.0 and C.epoch("x") == 0.0


# ---- C1-7: a department with nothing in it, and a sub-read that breaks ------------------------------------------------
def test_c17_no_cycle_is_not_started_and_every_attribute_is_there(mods):
    c = C.get_ctx(REF)
    assert c.state == "not_started" and c.ref == REF and c.kind == "website" and c.doc is False and c.stopped is False
    for name in ("d", "root_ref", "fv", "cur", "runs", "asks", "posts", "root_posts", "steps", "events", "engines", "planned", "arts",
                 "chat", "msg_of", "ask_msg", "ask_opts", "paused_ask", "reasons", "memo"):
        assert hasattr(c, name), name
    assert c.d["ref"] == REF and c.root_ref is None and c.cur == {} and c.root_posts == [] and c.memo == {}
    assert [a["name"] for a in c.arts] == ["Brief", "Site plan", "Pages", "Build", "Live site"]
    assert c.planned is True and [e["wid"] for e in c.engines] == ["W-1", "W-2", "W-3", "W-4"], "no cycle: the line it was born with is its plan"
    assert c.reasons == []


def test_c17_a_cycle_with_no_registered_plan_numbers_no_engine(mods):
    cycle(mods, "adapting", 2)
    c = C.get_ctx(REF)
    assert c.state == "adapting" and c.planned is False
    assert all(e["wid"] is None and e["k"] is None for e in c.engines) and c.who("Plan") is None and c.dest("Plan") is None


def test_c17_a_broken_read_leaves_its_attribute_empty_and_says_why(mods, monkeypatch):
    def boom(ref):
        raise RuntimeError("the file is gone")
    monkeypatch.setattr(mods.W, "runs", boom)
    c = C.get_ctx(REF)
    assert c.runs == [] and any(r.startswith("runs: RuntimeError") for r in c.reasons), c.reasons
    assert c.d["ref"] == REF and c.state == "not_started", "the rest of the read stands"


def identity_asks(m, ref=REF, question="What evidence will prove this site is done?"):
    """Identity's question put the way the ledger puts it (J.asked: a j2_identity ask, which has no `engine` key)."""
    d = m.W.dept(ref)
    d["events"] = [{"kind": "j2_ready", "route": "template"}]
    m.W.save_dept(ref, d)
    if not m.J._state(ref):
        m.J.begin(ref)
    cur = m.J.asked(ref, question, ["done-when"], "Identity's standard is not met yet: done-when", standard=False)
    assert cur["open_ask"] and "engine" not in next(a for a in m.W.asks(ref) if a["id"] == cur["open_ask"])
    return cur


def test_c17_identitys_open_question_does_not_take_the_engines_away(mods):
    """website_dept.map_view raises KeyError('engine') while an ask with no `engine` key (Identity's question) is pending; the
    ctx rebuilds the engines from the public readers, so the engines, the plan flag and the W-k numbering are never empty."""
    identity_asks(mods)
    with pytest.raises(KeyError):
        mods.W.map_view(REF)                                   # the record's own reader still fails: reported to its owner, not hidden
    C.touch(REF)
    c = C.get_ctx(REF)
    assert c.state == "waiting" and c.paused_ask and c.paused_ask["form"] == "words"
    assert c.reasons == [], c.reasons
    assert [e["name"] for e in c.engines] == ["Plan", "Write", "Check", "Publish"] and c.planned is False
    assert all(e["wid"] is None and e["in_line"] and e["state"] == "Idle" and e["steps_view"] for e in c.engines), "no plan is registered yet: no W-k"


def test_c17_the_engines_read_the_same_with_and_without_the_question(mods, born, tick):
    ref = born()
    C.reset_caches()
    before = C.get_ctx(ref)
    assert before.planned and [e["wid"] for e in before.engines] == ["W-1", "W-2", "W-3", "W-4"]
    identity_asks(mods, ref)
    C.touch(ref)
    after = C.get_ctx(ref)
    assert after.reasons == [], after.reasons
    keys = ("k", "wid", "name", "reads", "writes", "runs_as", "in_line", "env", "window_min", "timetable")
    assert [{k: e[k] for k in keys} for e in after.engines] == [{k: e[k] for k in keys} for e in before.engines]
    assert after.planned is True and [e["state"] for e in after.engines] == [e["state"] for e in before.engines]
    assert after.wid("Write") == "W-2" and after.who("Check") == "W-3"


def test_c17_a_pending_ask_for_an_engine_still_makes_that_engine_wait_when_the_map_is_rebuilt(mods):
    ask(mods, "publish", engine="Publish")
    identity_asks(mods)
    c = C.get_ctx(REF)
    assert c.reasons == [] and {e["name"]: e["state"] for e in c.engines}["Publish"] == "Waits"


def test_c17_the_rebuilt_engines_are_the_maps_own_rows(mods, born, tick):
    """The by-hand rows must stay map_view's rows, or the numbering would change the moment Identity asks."""
    import owner_words

    def same(ref):
        C.touch(ref)
        c = C.get_ctx(ref)
        want = owner_words.map_view(mods.W.map_view(ref))
        got = C._engines_by_hand(c)
        assert got["planned"] == want["planned"] and got["engines"] == want["engines"], ref
    same(REF)                                                  # born, no cycle: the line it was born with
    cycle(mods, "adapting", 2)
    run(mods, "Write")
    ask(mods, "publish", engine="Publish")
    same(REF)                                                  # a cycle with no plan, one engine running, one waiting
    ref = born()
    same(ref)                                                  # a registered plan, as Root sets it up
    mods.W.run_until_idle(ref, limit=50)
    d = mods.W.dept(ref)
    d["stopped"] = True
    mods.W.save_dept(ref, d)
    same(ref)                                                  # stopped


def test_c17_when_the_rebuild_fails_too_the_engines_are_empty_and_the_reason_stands(mods, monkeypatch):
    identity_asks(mods)
    monkeypatch.setattr(mods.W, "engine_view", lambda ref, name: (_ for _ in ()).throw(RuntimeError("gone")))
    C.touch(REF)
    c = C.get_ctx(REF)
    assert c.engines == [] and c.planned is False and c.reasons == ["map: KeyError"], c.reasons


def test_c17_a_ref_with_no_folder_still_gives_a_ctx(mods):
    c = C.get_ctx("dref-never-made")
    assert c.d == {} and c.runs == [] and c.chat == [] and c.state == "not_started"


# ---- C1-8: numbering and who said it ----------------------------------------------------------------------------------
def test_c18_numbers_who_dest_and_step_at(mods, born, tick):
    ref = born()
    C.reset_caches()
    c = C.get_ctx(ref)
    assert c.planned and [e["wid"] for e in c.engines] == ["W-1", "W-2", "W-3", "W-4"]
    assert [e["name"] for e in c.engines] == ["Plan", "Write", "Check", "Publish"] and [e["k"] for e in c.engines] == [1, 2, 3, 4]
    assert c.wid("Check") == "W-3" and c.wid("Nobody") is None
    assert c.who("Owner") == "user" and c.who("Identity") == "identity" and c.who("priority") == "priority"
    assert c.who("Plan") == "W-1" and c.who("Root") is None and c.who("Stranger") is None
    assert c.dest("Owner") == "user" and c.dest("Audit") == "audit" and c.dest("Publish") == "W-4" and c.dest("Root") is None
    assert c.fn_id("Identity") == "fn:identity" and c.fn_id("Plan") is None
    assert c.root_ref and c.root_posts and c.posts and c.steps and c.events and c.runs
    assert all(e["state"] for e in c.engines) and c.engines[0]["steps_view"]["name"] == "Plan"
    assert [r["engine"] for r in c.engines[0]["runs"]] == ["Plan"] or c.engines[0]["runs"] == [r for r in c.runs if r["engine"] == "Plan"]
    # the step of the latest event not after a time
    assert c.step_at("1999-01-01T00:00:00+00:00") is None
    last = c.events[-1]
    assert c.step_at(last["occurred_at"]) == last["step"]
    first = c.events[0]
    assert c.step_at(first["occurred_at"]) in range(1, 9)
    assert [a["name"] for a in c.arts][:2] == ["Brief", "Site plan"] and c.arts[0]["latest"]["v"] == c.arts[0]["versions"][-1]["v"]
    # clean in the owner's words: the engine cards come through owner_words
    assert "GRANT" not in json.dumps(c.engines, default=str)
