"""test_j2ui_state.py -- `api/state`, the 56 keys the J2 page polls (j2ui_state.py; UI port steps C3 and C6).

Named claims:
  C3-1  one row per cycle state (STATE_TABLE, which j2ui-verify imports): status, thinking, step, which ask is paused and that its
        message is an ASK message, outcome, done and stamped; 'waiting' whenever something waits on the owner, even while an
        engine runs; outcome is only Done or Done with open items, never Stopped, Crashed or Paused
  C3-2  every state has exactly the 56 keys; a department with nothing in it gives the page's idle shape; goal is None before a goal
  C3-3  since slices the chat and total is the whole; the state is built once per read, only the slice differs
  C3-4  with j2ui_work absent or raising the thirteen keys keep their empties and the rest is complete; only its thirteen are merged
  C3-5  every s.<key> and CTX.<key> the pinned page reads is a key of the state
  C3-6  paused is one ask at a time, in the order Identity's question, options asks, stamp asks; runs lists no saved run
  C6-1  the build is cheap to poll: 5,000 board rows, 20,000 step rows and 20,000 ledger events are read once; fifty polls, through
        the router too, read nothing; one appended row of each is the only thing the rebuild reads of its journal; the wall time has
        a ceiling
"""
import json
import re
import sys
import time
import types

import pytest

from test_fixtures.j2ui import proto
from test_fixtures.j2ui.core_fixtures import *  # noqa: F401,F403

import j2ui_chat as CH
import j2ui_common as C
import j2ui_state as S


def read(m, ref=REF, since=0):
    C.touch(ref)
    c = C.get_ctx(ref)
    return c, S.build_state(c, since)


# ---- the table: one row per state ---------------------------------------------------------------------------------------
def s_not_started(m):
    pass


def s_assessing(m):
    cycle(m, "assessing", 1)


def s_waiting(m):
    q = m.W.j2_identity_ask("What is the site for, and about whom?", "cycle-test", "words", "Your words name nothing yet.")
    m.W._put_ask(REF, q)
    post(m, "Identity", "Owner", "inform", {"word": "question", "done": q["text"], "card": q["id"]}, thread="x-q")
    cycle(m, "waiting", 1, open_ask=q["id"])


def s_adapting(m):
    cycle(m, "adapting", 2)


def s_bargaining(m):
    cycle(m, "bargaining", 3)
    thread(m, "Adaptation", "Priority", "propose", "line")


def s_closing(m):
    cycle(m, "closing", 4)
    thread(m, "Adaptation", "Identity", "inform", "conflict", state="submitted")


def s_checking(m):
    cycle(m, "checking", 5)


def s_reshaping(m):
    cycle(m, "reshaping", 5)


def s_running(m):
    cycle(m, "running", 6)
    run(m, "Write")


def s_running_ask(m):
    cycle(m, "running", 6)
    run(m, "Write")
    stamp_ask(m, "publish")


def s_blocked(m):
    cycle(m, "blocked", 4)
    a = blocked(m)
    card_post(m, a, objective=a["text"])


def s_pursuing(m):
    cycle(m, "pursuing", 8)


def s_unread(m):
    cycle(m, "unread", 7)


def s_done(m):
    cycle(m, "done", 8)
    event(m, "identity.assessed", actor="Identity", step=1, summary="The identity is good enough to start on.")


def s_done_open(m):
    s_done(m)
    d = m.W.dept(REF)
    d["to_be_confirmed"] = [{"item": "D1", "why": "the phone number is not given"}]
    m.W.save_dept(REF, d)


def s_done_finding(m):
    s_done(m)
    stamp_ask(m, "finding", text="Audit found: the home page has no phone number. Stamp to have it put right.")


def s_stopped(m):
    cycle(m, "running", 6)
    d = m.W.dept(REF)
    d["stopped"] = True
    m.W.save_dept(REF, d)


#: name, setup, status, thinking, step, paused.kind, outcome, done, stamped. j2ui-verify imports this table.
STATE_TABLE = [
    ("not_started", s_not_started, "idle", None, 0, None, None, False, False),
    ("assessing", s_assessing, "running", "identity", 1, None, None, False, False),
    ("waiting", s_waiting, "waiting", None, 1, "info", None, False, False),
    ("adapting", s_adapting, "running", "adaptation", 2, None, None, False, False),
    ("bargaining", s_bargaining, "running", "priority", 3, None, None, False, False),
    ("closing", s_closing, "running", "identity", 4, None, None, False, False),
    ("checking", s_checking, "waiting", None, 5, None, None, False, False),
    ("reshaping", s_reshaping, "running", "adaptation", 5, None, None, False, False),
    ("running", s_running, "running", "coordination", 6, None, None, False, False),
    ("running_with_a_publish_ask", s_running_ask, "waiting", "coordination", 6, "approval", None, False, False),
    ("blocked", s_blocked, "waiting", None, 4, "limit", None, False, False),
    ("pursuing", s_pursuing, "waiting", None, 8, None, None, False, False),
    ("unread", s_unread, "waiting", None, 7, None, None, False, False),
    ("done", s_done, "waiting", None, 8, None, "Done", True, True),
    ("done_with_an_item_to_confirm", s_done_open, "waiting", None, 8, None, "Done with open items", True, True),
    ("done_with_a_finding_asked", s_done_finding, "waiting", None, 8, "audit", "Done with open items", True, True),
    ("stopped", s_stopped, "waiting", None, 6, None, None, False, False),
]


@pytest.mark.parametrize("row", STATE_TABLE, ids=[r[0] for r in STATE_TABLE])
def test_c31_each_state_says_what_the_page_needs(mods, row):
    name, setup, status, thinking, step, pause, outcome, done, stamped = row
    setup(mods)
    c, s = read(mods)
    assert list(s) == list(C.STATE_KEYS), name
    got = (s["status"], s["thinking"], s["step"], (s["paused"] or {}).get("kind"), s["outcome"], s["done"], s["stamped"])
    assert got == (status, thinking, step, pause, outcome, done, stamped), (name, got, c.reasons)
    assert c.reasons == [] and len(c.engines) == 4, (name, c.reasons, "every state reads whole: the engines are there, no sub-read failed")
    assert s["turn"] == s["thinking"]
    assert s["outcome"] in (None, "Done", "Done with open items"), "never Stopped, Crashed or Paused"
    if s["paused"]:
        msg = s["paused"]["msg"]
        assert msg and s["chat"][msg - 1]["act"] == "ASK_REQUESTER" and s["chat"][msg - 1]["id"] == msg, "paused.msg is an ASK message"
        assert set(s["paused"]) == {"kind", "questions", "msg", "label", "choices"} and s["paused"]["choices"] is None
    if status == "waiting" and pause:
        assert s["status"] != "running", "the composer and the option buttons stay live"
    assert s["steps"]["1"] == "J2.a Enough to work" and s["steps"]["8"] == "J2.h Next or done" and len(s["steps"]) == 8
    assert s["total"] == len(c.chat) and s["error"] is None and s["saved"] is None and s["write_lock"] is None


def test_c31_a_running_engine_with_a_stamp_waiting_still_says_waiting(mods):
    s_running_ask(mods)
    c, s = read(mods)
    assert [e["state"] for e in c.engines if e["name"] == "Write"] == ["Running"]
    assert s["status"] == "waiting" and s["paused"]["kind"] == "approval" and s["thinking"] == "coordination"
    assert s["paused"]["questions"][0]["options"] == ["Stamp", "Say no"]
    assert s["paused"]["label"] == "Publish: put it to the owner"


# ---- C3-2: the keys, the idle shape, the goal --------------------------------------------------------------------------------
def test_c32_a_department_with_nothing_in_it_is_the_pages_idle_shape(mods):
    c, s = read(mods)
    assert list(s) == list(C.STATE_KEYS) and len(s) == 56
    idle = C.EMPTY_STATE()
    for k in ("chat", "total", "status", "thinking", "step", "goal", "stamped", "workflows", "conflicts", "audits", "versions", "cycle",
              "calls", "error", "done", "turn", "paused", "outcome", "style", "model", "fixes", "has_board", "memory", "output",
              "output_label", "doc", "files", "docset", "docset_files", "saved", "lessons", "playbooks", "report", "lanes", "call_log"):
        assert s[k] == idle[k], (k, s[k], idle[k])
    assert s["steps"] != {} and s["budget"] > 0 and s["spent"] == 0, "the budget is the calls limit; nothing is spent"
    assert s["mock"] is True, "these tests run the offline functions"


def test_c32_the_goal_is_none_before_a_goal_and_the_records_words_after(mods):
    assert read(mods)[1]["goal"] is None
    d = mods.W.dept(REF)
    d["goal"] = "A site for a florist in Jaipur"
    d["rules"] = [{"id": "u-1", "tag": "refuse", "line": "never show a price"}, {"id": "u-2", "tag": "always", "line": "keep the phone number on every page"}]
    d["done_items"] = [{"id": "D1", "text": "Every page is checked", "how": "code", "level": "target"},
                       {"id": "D2", "text": "The phone number is there", "how": "model", "level": "outcome"}]
    d["to_be_confirmed"] = [{"item": "D2", "why": "the number is not given"}]
    mods.W.save_dept(REF, d)
    mods.W.add_version(REF, "Brief", {"brief.md": "x"}, [], "owner", {"ok": True, "notes": []})
    g = read(mods)[1]["goal"]
    assert list(g) == ["statement", "site_name", "audience", "standards", "rules", "done_when", "charter_items", "to_be_confirmed",
                       "confirmed_facts", "dropped_by_requester"]
    assert g["statement"] == "A site for a florist in Jaipur" and g["site_name"] == "City Care Hospital Website"
    assert g["rules"] == ["never: never show a price", "always: keep the phone number on every page"], "the screen says never, not refuse"
    assert g["done_when"] == g["charter_items"] == ["Every page is checked", "The phone number is there"]
    assert g["to_be_confirmed"] == [{"criterion": "The phone number is there", "fact": "the number is not given"}]
    assert g["audience"] == "" and g["standards"] == [] and g["confirmed_facts"] == [] and g["dropped_by_requester"] == []


def test_c32_versions_budget_and_calls(mods):
    mods.W.add_version(REF, "Build", {"index.html": "<p>1</p>"}, [], "r-x", {"ok": True, "notes": []})
    mods.W.add_version(REF, "Build", {"index.html": "<p>2</p>"}, [], "r-y", {"ok": True, "notes": []})
    run(mods, "Write", status="ok", spend={"calls": 4, "usd": 0.4})
    run(mods, "Plan", status="ok", spend={"calls": 2, "usd": 0.1}, slot="Plan@brief.v1")
    c, s = read(mods)
    assert s["versions"] == 2 and s["calls"] == 6 and s["budget"] == c.fv["budget"]["calls_limit"] and s["spent"] == c.fv["budget"]["calls"]
    assert (s["output"], s["output_label"], s["doc"], s["files"], s["docset"], s["docset_files"]) == ("website", "Website", False, [], [], [])
    assert (s["model"], s["fixes"], s["memory"], s["saved"]) == ("not recorded", 1, False, None)


def test_c32_mock_follows_the_offline_switch(mods, monkeypatch):
    assert read(mods)[1]["mock"] is True
    monkeypatch.delenv("SUTRA_WEBSITE_OFFLINE")
    C.touch(REF)
    c = C.get_ctx(REF)
    c.memo.clear()
    assert S.build_state(c)["mock"] is False


# ---- C3-3: since --------------------------------------------------------------------------------------------------------------
def test_c33_since_slices_the_chat_and_total_is_the_whole(mods):
    for i in range(5):
        thread(mods, "Identity", "Adaptation", "request", "line", tid="x-%d" % i, words="w%d" % i)
    c, whole = read(mods)
    assert whole["total"] == 5 and [m["id"] for m in whole["chat"]] == [1, 2, 3, 4, 5]
    part = S.build_state(c, 3)
    assert [m["id"] for m in part["chat"]] == [4, 5] and part["total"] == 5
    assert S.build_state(c, 5)["chat"] == [] and S.build_state(c, 99)["chat"] == [] and S.build_state(c, -4)["total"] == 5
    assert S.build_state(c, "2")["chat"][0]["id"] == 3 and S.build_state(c, "x")["total"] == 5
    assert len(S.build_state(c)["chat"]) == 5, "slicing one call does not cut another"
    assert "state" in c.memo, "the state is built once per read"


def test_c33_runs_lists_no_saved_run_and_only_the_live_one_is_live(mods):
    c, _ = read(mods)
    assert S.runs(c) == {"live": REF, "runs": []}
    cycle(mods, "running", 6)
    c, _ = read(mods)
    assert S.runs(c) == {"live": "cycle-test", "runs": []}
    assert S.is_live_run(c, None) and S.is_live_run(c, "") and S.is_live_run(c, "cycle-test") and S.is_live_run(c, REF)
    assert not S.is_live_run(c, "j2-20261008-153402")


# ---- C3-4: the work package's keys -----------------------------------------------------------------------------------------------
def _work(monkeypatch, module):
    monkeypatch.setitem(sys.modules, "j2ui_work", module)


def test_c34_with_the_work_package_absent_or_failing_its_keys_stay_empty(mods, monkeypatch):
    _work(monkeypatch, None)                                   # not importable
    c, s = read(mods)
    assert all(s[k] == C.EMPTY_STATE[k] for k in C.WORK_KEYS) and list(s) == list(C.STATE_KEYS)

    def boom(ctx):
        raise RuntimeError("the builder broke")
    _work(monkeypatch, types.SimpleNamespace(build=boom))
    c, s = read(mods)
    assert all(s[k] == C.EMPTY_STATE[k] for k in C.WORK_KEYS) and s["total"] == len(c.chat)
    assert any("j2ui_work: RuntimeError" in r for r in c.reasons)


def test_c34_only_the_thirteen_keys_of_the_work_package_are_merged(mods, monkeypatch):
    fake = {k: C.EMPTY_STATE[k] for k in C.WORK_KEYS}
    fake.update(workflows=[{"id": "W-1"}], status="running", total=99, chat=[{"id": 7}], extra="x")
    _work(monkeypatch, types.SimpleNamespace(build=lambda ctx: fake))
    c, s = read(mods)
    assert s["workflows"] == [{"id": "W-1"}] and s["status"] == "idle" and s["total"] == 0 and s["chat"] == [] and "extra" not in s
    assert list(s) == list(C.STATE_KEYS)


def test_c34_the_board_tab_follows_the_board_module(mods, monkeypatch):
    monkeypatch.setitem(sys.modules, "j2ui_board", types.SimpleNamespace(build=lambda ctx: {"schema": "board/1", "entries": [{"id": "B-1"}]}))
    assert read(mods)[1]["has_board"] is True
    monkeypatch.setitem(sys.modules, "j2ui_board", types.SimpleNamespace(build=lambda ctx: {"schema": "board/1", "entries": []}))
    assert read(mods)[1]["has_board"] is False


# ---- C3-5: what the page reads -----------------------------------------------------------------------------------------------------
def test_c35_every_key_the_page_reads_is_in_the_state():
    html = proto.show("j2_ui.html").decode("utf-8")
    tokens = set(re.findall(r"\b(?:s|CTX|state)\.(\w+)", html))
    # not the state: another s (a box's, a section's), and what the page adds to the state itself
    not_state = {"id", "detail", "allChat"}
    assert tokens - not_state <= set(C.STATE_KEYS), sorted(tokens - not_state - set(C.STATE_KEYS))
    assert {"chat", "total", "status", "paused", "outcome", "versions", "thinking", "has_board", "workflows", "atoms_v1"} <= tokens


# ---- C3-6: one ask at a time -------------------------------------------------------------------------------------------------------
def test_c36_paused_is_one_ask_in_order_and_counts_the_rest(mods):
    q = mods.W.j2_identity_ask("What is the site for?", "cycle-test", "words", "Your words name nothing yet.")
    mods.W._put_ask(REF, q)
    post(mods, "Identity", "Owner", "inform", {"word": "question", "done": q["text"], "card": q["id"]}, thread="x-q")
    cycle(mods, "waiting", 1, open_ask=q["id"])
    stamp_ask(mods, "rule", tid="x-rule")
    a = blocked(mods)
    card_post(mods, a, objective=a["text"])
    stamp_ask(mods, "publish")
    c, s = read(mods)
    p = s["paused"]
    assert p["kind"] == "info" and p["msg"] == c.ask_msg[q["id"]] and p["label"] == "Your words name nothing yet. (3 more waiting)"
    assert p["questions"] == [{"question": "What is the site for?", "options": []}]
    # answered: the options ask is next, then the stamps, oldest first
    q.update(status="stamped", decided=mods.W.now(), by="the owner", answered="A florist site")
    mods.W._put_ask(REF, q)
    cycle(mods, "blocked", 4)
    c, s = read(mods)
    assert s["paused"]["kind"] == "limit" and s["paused"]["msg"] == c.ask_msg[a["id"]] and s["paused"]["label"] == "Check has no reader (2 more waiting)"
    assert [o.startswith(("Change the plan", "Leave D2", "Stop here")) for o in s["paused"]["questions"][0]["options"]] == [True, True, True]
    mods.W.choose_option(REF, a["id"], "stop")
    c, s = read(mods)
    assert s["paused"]["msg"] == c.ask_msg["a-rule"] and s["paused"]["label"].endswith("(1 more waiting)")
    assert s["paused"]["questions"][0]["options"] == ["Stamp", "Say no"]


def test_c36_a_question_that_is_not_the_cycles_open_one_is_not_paused(mods):
    q = mods.W.j2_identity_ask("An old question?", "cycle-old", "words", "old")
    mods.W._put_ask(REF, q)
    cycle(mods, "running", 6)
    c, s = read(mods)
    assert s["paused"] is None and c.paused_ask is None


# ---- C6: the build is cheap to poll --------------------------------------------------------------------------------------------------
BOARD, STEPS, EVENTS = 5000, 20000, 20000


def _big(m):
    """A department with BOARD board rows, STEPS step rows and EVENTS ledger events, written straight into its journals."""
    W, ref = m.W, REF
    d = W.ddir(ref)
    at = "2026-10-26T10:00:00+05:30"
    with open(d / "board.jsonl", "w", encoding="utf-8") as f:
        for i in range(1, BOARD + 1):
            if i % 5 == 0:
                row = {"n": i, "src": "Owner", "dst": ["Identity"], "msg_type": "request", "thread": "x-%d" % i, "hop": 1, "about": None,
                       "payload": {"word": "request", "words": "Change number %d" % i}, "ack_id": None, "by": None, "at": at}
            else:
                row = {"n": i, "src": ("Adaptation", "Priority", "Identity")[i % 3], "dst": [("Priority", "Adaptation", "Coordination")[i % 3]],
                       "msg_type": "inform", "thread": "x-%d" % i, "hop": 1, "about": None,
                       "payload": {"word": "line", "done": "a post %d" % i}, "ack_id": None, "by": None, "at": at}
            f.write(json.dumps(row) + "\n")
    with open(d / "steps.jsonl", "w", encoding="utf-8") as f:
        for i in range(STEPS):
            f.write(json.dumps({"id": "s-%d" % i, "run": None, "engine": "Plan", "step": "plan.read", "item": None, "mode": "slot", "slot": "Plan@x",
                                "rung": "C2", "by": "code", "answer": "ok", "check": {"ok": True, "notes": ["the brief has words"]},
                                "usd": 0.0, "calls": 0, "ms": 1, "status": "ok", "started": at, "ended": at}) + "\n")
    with open(d / "j2-events.jsonl", "w", encoding="utf-8") as f:
        for i in range(1, EVENTS + 1):
            f.write(json.dumps({"idempotency_key": "%s/cycle-test/6/k-%d" % (ref, i), "department_ref": ref, "cycle_id": "cycle-test", "step": 6,
                                "journey": "J2.f", "actor": "Coordination", "recipient": "Write", "action": "slot.assigned", "state": "assigned",
                                "summary": "Write has the next turn.", "payload": {}, "evidence_refs": [], "occurred_at": at, "seq": i,
                                "event_id": "evt-%d" % i}) + "\n")
    cycle(m, "running", 6)


def test_c61_fifty_polls_read_nothing_and_a_rebuild_reads_only_what_was_appended(mods, monkeypatch):
    W, R, F, J = mods.W, mods.R, mods.F, mods.J
    _big(mods)
    spied = {}
    for obj, name in ((W, "runs"), (W, "asks"), (R, "step_rows"), (R, "board"), (F, "functions"), (J, "events_after"), (R, "chat_view")):
        real = getattr(obj, name)
        spied[name] = calls = []
        monkeypatch.setattr(obj, name, (lambda real, calls: lambda *a, **k: (calls.append(a), real(*a, **k))[1])(real, calls))
    t0 = time.time()
    c = C.get_ctx(REF)
    first = time.time() - t0
    s = S.build_state(c)
    after_first = {k: len(v) for k, v in spied.items()}
    assert after_first["functions"] == 1 and after_first["chat_view"] == 1 and [a[1] for a in spied["events_after"]] == [0], after_first
    assert len(c.posts) == BOARD and len(c.steps) == STEPS and len(c.events) == EVENTS
    for _ in range(50):
        assert S.build_state(C.get_ctx(REF)) is not None
        assert C.get_ctx(REF) is c
    assert {k: len(v) for k, v in spied.items()} == after_first, "fifty polls made no read"
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import j2ui_api
    app = FastAPI()
    app.include_router(j2ui_api.router)
    http = TestClient(app)
    for _ in range(50):
        assert http.get("/j2ui/%s/api/state?since=%d" % (REF, s["total"])).status_code == 200
    assert {k: len(v) for k, v in spied.items()} == after_first, "and fifty polls of the route made none either"
    assert s["total"] == len(c.chat) and len(c.chat) >= BOARD // 5
    # one appended post, step row and ledger event: each journal's rebuild reads only its new bytes
    base = W.ddir(REF)
    post_row = json.dumps({"n": BOARD + 1, "src": "Owner", "dst": ["Identity"], "msg_type": "request", "thread": "x-new", "hop": 1, "about": None,
                           "payload": {"word": "request", "words": "One more change"}, "ack_id": None, "by": None, "at": "2026-10-26T10:00:01+05:30"}) + "\n"
    step_row = json.dumps({"id": "s-new", "engine": "Plan", "step": "plan.read", "status": "ok", "check": {"ok": True, "notes": []}}) + "\n"
    with open(base / "board.jsonl", "a", encoding="utf-8") as f:
        f.write(post_row)
    with open(base / "steps.jsonl", "a", encoding="utf-8") as f:
        f.write(step_row)
    J.append_event(REF, {"idempotency_key": "%s/cycle-test/6/new" % REF, "department_ref": REF, "cycle_id": "cycle-test", "step": 6, "journey": "J2.f",
                         "actor": "Coordination", "recipient": "Write", "action": "run.started", "state": "running", "summary": "x"})
    C.touch(REF)
    t0 = time.time()
    c2 = C.get_ctx(REF)
    rebuild = time.time() - t0
    assert c2 is not c and len(c2.posts) == BOARD + 1 and len(c2.steps) == STEPS + 1 and len(c2.events) == EVENTS + 1
    tails = {p.rsplit("/", 1)[-1]: t for p, t in C._TAILS.items() if p.startswith(str(base))}
    assert tails["board.jsonl"].last_read == len(post_row.encode("utf-8")) and tails["steps.jsonl"].last_read == len(step_row.encode("utf-8"))
    assert [a[1] for a in spied["events_after"]] == [0, EVENTS], "the ledger is read after the last seq it holds"
    assert c2.chat[-1]["text"] == "One more change" and c2.chat[-1]["id"] == len(c2.chat)
    print("j2ui perf: first read %.2f s, rebuild after one appended row of each journal %.2f s (ceiling %.1f s)" % (first, rebuild, 1.5))
    # the ceiling is 1.5 s, and holds where the readers the build must call (functions, each engine's steps, the chat, the map) take
    # a second between them, as here; on a slower or busier machine it is those readers' own cost and a half, so the check still
    # catches work of the adapter's own that grows with the journals, and not the machine
    t0 = time.time()
    F.functions(REF), [R.steps_view(REF, n) for n in ("Plan", "Write", "Check", "Publish")], R.chat_view(REF), W.map_view(REF)
    readers = time.time() - t0
    ceiling = max(1.5, 1.5 * readers)
    print("j2ui perf: the readers alone %.2f s, ceiling %.2f s" % (readers, ceiling))
    assert first < 30 and rebuild < ceiling, (first, rebuild, readers)
    # the registry is a list and a dict of small messages, not the rows again
    reg = CH._registry(REF)
    assert type(reg.keys) is list and type(reg.index) is dict and len(reg.keys) == len(reg.index) == len(c2.chat)
    assert all(set(m) <= {"t", "who", "text", "step", "to_user", "act", "pause", "next", "audience", "register"} for m in reg.last.values())
