"""test_j2ui_map.py -- the J2 page's Map, map/1, from a department's record (j2ui_map.py, j2ui_mapedges.py; UIPORT j2ui-views M3, M4).

Named claims:
  M3a  the nodes: the person first, the five functions in order, then the Charter (only with a goal) and the work boxes;
       no node of kind know; node kinds and statuses within the prototype's pinned constants; each node's keys in the
       prototype's order
  M3b  a function's status is its state (working -> running, waiting -> waiting, fault -> fault, quiet -> idle) and
       `waiting_on_you` appears only while an ask is open, on the person and on Identity alike
  M3c  a box's status: filed, done_unchecked (a version whose check failed with no failed run), fault (the engine's latest
       run failed), running (never in a finished department), waiting_on_you (an ask names the engine), left_open,
       not_made; an engine the plan left out draws one hollow branch box after the trunk
  M3d  what Sutra does not record is listed, never invented: no goal, no Charter and the reason; no chat, no counts
Shares the department fixtures and the Ctx stand-in of test_j2ui_artifacts.py.
"""
import json
import re

import pytest

from test_j2ui_artifacts import (REF, FUNCS, add_ver, ago, make_ctx, mods, msg, proto_consts, put_ask, put_post,  # noqa: F401 -- mods is a fixture
                                 put_run, put_step, seed_line, set_cycle)

WORK = ["work:brief", "work:site-plan", "work:pages", "work:build", "work:live-site"]
PERSON_KEYS = ["id", "kind", "row", "label", "status", "version", "tag", "color", "file", "detail", "workflows"]
FUNCTION_KEYS = ["id", "kind", "row", "label", "status", "version", "tag", "color", "file", "workflows", "tab", "wait_on", "calls",
                 "seconds", "tokens", "detail"]
WORK_KEYS = ["id", "kind", "row", "label", "tag", "color", "status", "version", "detail", "file", "workflows", "lane"]
ENGINE_KEYS = ["id", "kind", "row", "label", "status", "version", "detail", "file", "workflows", "tag", "color", "lane", "team",
               "unchecked", "made_by"]
#: the constants of the prototype's j2_map.py at the pin, copied (proto_consts compares them when the prototype is here)
STATUSES = ("filed", "done_unchecked", "running", "waiting", "waiting_on_you", "fault", "left_open", "not_made", "idle")
NODE_KINDS = ("person", "function", "engine", "work", "know")


def register(W, R, left=()):
    """Root's check has registered the plan: Coordination's table says so, with the engines of the line and the ones left out."""
    t = dict(R.coordination(REF))
    t["registered"] = 1
    t["line"] = [e for e in t["line"] if e not in left]
    t["left_out"] = [{"engine": e, "in_line": False, "since": W.now()} for e in left]
    W._write(W.ddir(REF) / "coordination.json", t)


def nodes_of(m, kind=None):
    return [n for n in m["nodes"] if kind is None or n["kind"] == kind]


def ids(m, kind=None):
    return [n["id"] for n in nodes_of(m, kind)]


def node(m, nid):
    return next(n for n in m["nodes"] if n["id"] == nid)


@pytest.fixture
def line(mods):
    """A department with the whole line filed and the plan registered."""
    W, R = mods[0], mods[1]
    seed_line(W)
    register(W, R)
    return mods


# ---- M3a: the nodes -------------------------------------------------------------------------------------------------------------
def test_m3a_the_person_first_then_the_five_functions_then_the_work(line):
    import j2ui_map as M
    m = M.build(make_ctx(line))
    assert ids(m, "person") == ["person:requester"] and m["nodes"][0]["id"] == "person:requester"
    assert ids(m, "function") == ["fn:" + f.lower() for f in FUNCS] and ids(m)[1:6] == ids(m, "function")
    assert ids(m, "work") == ["work:charter"] + WORK
    assert ids(m)[6] == "work:charter"
    assert [n["row"] for n in m["nodes"]] == ["people"] + ["functions"] * 5 + ["work"] * (len(m["nodes"]) - 6)


def test_m3a_no_node_of_kind_know_and_kinds_and_statuses_are_the_prototypes(line):
    import j2ui_map as M
    m = M.build(make_ctx(line))
    kinds, stats = proto_consts("j2_map.py", "NODE_KINDS") or NODE_KINDS, proto_consts("j2_map.py", "STATUSES") or STATUSES
    assert tuple(kinds) == NODE_KINDS and tuple(stats) == STATUSES and M.NODE_KINDS == NODE_KINDS and M.STATUSES == STATUSES
    assert "know" not in {n["kind"] for n in m["nodes"]}
    assert {n["kind"] for n in m["nodes"]} <= set(kinds) - {"know"}
    assert {n["status"] for n in m["nodes"]} <= set(stats)


def test_m3a_each_nodes_keys_are_the_prototypes_in_order(line):
    import j2ui_map as M
    m = M.build(make_ctx(line))
    assert list(node(m, "person:requester")) == PERSON_KEYS
    for n in nodes_of(m, "function"):
        assert list(n) == FUNCTION_KEYS
    for n in nodes_of(m, "work"):
        assert list(n) == WORK_KEYS
    assert node(m, "fn:identity")["tab"] == "charter" and node(m, "fn:audit")["tab"] == "audit"
    assert [node(m, "fn:" + f)["tab"] for f in ("adaptation", "priority", "coordination")] == ["workflows", "conflicts", "timeline"]
    assert node(m, "fn:priority")["color"] == "--priority" and node(m, "person:requester")["color"] == "--user"
    assert node(m, "person:requester")["label"] == "You" and node(m, "fn:coordination")["label"] == "Coordination"


def test_m3a_the_charter_box(line):
    import j2ui_map as M
    c = node(M.build(make_ctx(line)), "work:charter")
    assert c == {"id": "work:charter", "kind": "work", "row": "work", "label": "Charter", "tag": "Charter", "color": "--charter",
                 "status": "filed", "version": None, "detail": "the plan every workflow reads", "file": None, "workflows": [],
                 "lane": "trunk"}


def test_m3a_a_work_box_has_its_version_file_workflow_and_tag(line):
    import j2ui_map as M
    W = line[0]
    add_ver(W, "Build")                                                     # a second Build
    m = M.build(make_ctx(line))
    b = node(m, "work:build")
    assert (b["label"], b["version"], b["file"], b["workflows"], b["lane"]) == ("Build", 2, "build/v2/index.html", ["W-3"], "trunk")
    assert (b["tag"], b["color"]) == ("Site", "--site") and (b["row"], b["kind"]) == ("work", "work")
    assert (node(m, "work:live-site")["tag"], node(m, "work:live-site")["workflows"]) == ("Site", ["W-4"])
    brief, plan = node(m, "work:brief"), node(m, "work:site-plan")
    assert (brief["tag"], brief["color"], brief["workflows"], brief["file"]) == ("Other", "--other", [], "brief/v1/brief.md")
    assert (plan["tag"], plan["workflows"], plan["version"]) == ("Other", ["W-1"], 1)


def test_m3a_a_box_with_no_version_is_a_page_to_be_before_it_is_built(mods):
    import j2ui_map as M
    m = M.build(make_ctx(mods))
    b = node(m, "work:build")
    assert (b["version"], b["file"], b["tag"], b["status"]) == (None, None, "Site", "not_made")
    assert node(m, "work:pages")["tag"] == "Other"


def test_m3a_detail_counts_the_steps_the_engine_checked(line):
    import j2ui_map as M
    W, R = line[0], line[1]
    m = M.build(make_ctx(line))
    sv = [n for n in nodes_of(m, "work") if n["id"] in WORK]
    assert node(m, "work:brief")["detail"] == "no steps recorded"
    assert {n["detail"] for n in sv} == {"no steps recorded"}
    first = R.steps_view(REF, "Plan")["steps"][0]
    put_step(R, W, "Plan", first["id"], ok=True)
    m = M.build(make_ctx(line))
    assert node(m, "work:site-plan")["detail"] == "1 step checked"
    second = next(s for s in R.steps_view(REF, "Plan")["steps"] if s["mode"] == "slot" and s["id"] != first["id"])
    put_step(R, W, "Plan", second["id"], ok=False)
    assert node(M.build(make_ctx(line)), "work:site-plan")["detail"] == "2 steps checked"


# ---- M3b: the person and the functions ---------------------------------------------------------------------------------------------
def test_m3b_a_working_function_is_running_with_its_line(mods):
    import j2ui_map as M
    W = mods[0]
    set_cycle(W, "adapting", 2)
    m = M.build(make_ctx(mods))
    a = node(m, "fn:adaptation")
    assert (a["status"], a["detail"], a["wait_on"]) == ("running", "proposing the work", None)
    assert {node(m, "fn:" + f)["status"] for f in ("identity", "priority", "coordination", "audit")} == {"idle"}
    assert m["live"] is True


def test_m3b_a_function_waiting_on_another_names_it(mods):
    import j2ui_map as M
    W, R = mods[0], mods[1]
    set_cycle(W, "running", 6)
    put_post(W, R, "Adaptation", "Priority", "propose", "the plan")
    a = node(M.build(make_ctx(mods)), "fn:adaptation")
    assert (a["status"], a["wait_on"]) == ("waiting", "Priority")


def test_m3b_waiting_on_you_appears_only_while_an_ask_is_open(mods):
    import j2ui_map as M
    W = mods[0]
    set_cycle(W, "blocked", 8)                                              # the cycle is stuck, but no ask is open
    m = M.build(make_ctx(mods))
    assert "waiting_on_you" not in {n["status"] for n in m["nodes"]}
    assert node(m, "person:requester")["status"] == "idle" and m["live"] is False
    put_ask(W, "publish", engine="Publish")
    m = M.build(make_ctx(mods))
    assert node(m, "person:requester")["status"] == "waiting_on_you"
    i = node(m, "fn:identity")
    assert (i["status"], i["wait_on"]) == ("waiting_on_you", "you") and m["live"] is True


def test_m3b_a_fault_is_a_fault_and_a_quiet_function_is_idle(mods):
    import j2ui_map as M
    W, R = mods[0], mods[1]
    R._append(REF, "steps.jsonl", {"id": "s-1", "run": "r-1", "engine": "Identity", "step": "identity.read", "mode": "slot",
                                   "status": "failed", "why": "Read the words: the brief is not text", "started": W.now(), "ended": W.now()})
    m = M.build(make_ctx(mods))
    i = node(m, "fn:identity")
    assert (i["status"], i["detail"]) == ("fault", "Read the words: the brief is not text")
    assert {node(m, "fn:" + f)["status"] for f in ("adaptation", "priority", "coordination", "audit")} == {"idle"}


def test_m3b_a_finished_department_never_shows_a_function_running(mods):
    import j2ui_map as M
    W = mods[0]
    set_cycle(W, "done", 8)
    put_run(W, "Identity", "running", system=True)
    m = M.build(make_ctx(mods))
    assert {node(m, "fn:" + f.lower())["status"] for f in FUNCS} == {"idle"}


def test_m3b_calls_and_seconds_come_from_the_functions_own_runs(mods):
    import j2ui_map as M
    W = mods[0]
    put_run(W, "Priority", "ok", system=True, id="r-p1", started="2026-10-26T10:00:00+00:00", ended="2026-10-26T10:00:04.25+00:00",
            spend={"calls": 2, "usd": 0.1})
    put_run(W, "Priority", "ok", system=True, id="r-p2", started="2026-10-26T10:05:00+00:00", ended="2026-10-26T10:05:01+00:00",
            spend={"calls": 1, "usd": 0.0})
    put_run(W, "Write", "ok", id="r-w1", spend={"calls": 9, "usd": 0.0})           # an engine's run is not a function's
    m = M.build(make_ctx(mods))
    p = node(m, "fn:priority")
    assert (p["calls"], p["seconds"], p["tokens"]) == (3, 5.2, {"input": 0, "output": 0})
    assert (node(m, "fn:audit")["calls"], node(m, "fn:audit")["seconds"]) == (0, 0.0)


def test_m3b_the_detail_is_the_line_when_busy_else_the_last_thing_said(mods):
    import j2ui_map as M
    W = mods[0]
    chat = [msg(1, "user", "Build us a site"), msg(2, "identity", "@Requester Got it", step=1), msg(3, "priority", "Said yes: " + "x" * 200)]
    m = M.build(make_ctx(mods, chat=chat))
    assert node(m, "fn:identity")["detail"] == "last seen: @Requester Got it"
    assert node(m, "fn:priority")["detail"] == "last seen: " + ("Said yes: " + "x" * 200)[:140]
    assert node(m, "fn:audit")["detail"] == "no message recorded"
    assert "what Audit did (chat)" in m["not_recorded"] and "what Priority did (chat)" not in m["not_recorded"]


def test_m3b_the_person_counts_what_you_said(mods):
    import j2ui_map as M
    assert node(M.build(make_ctx(mods)), "person:requester")["detail"] == "not recorded"
    chat = [msg(1, "user", "Build us a site"), msg(2, "identity", "@Requester Got it")]
    assert node(M.build(make_ctx(mods, chat=chat)), "person:requester")["detail"] == "1 message from you"
    chat += [msg(3, "user", "Add a page")]
    assert node(M.build(make_ctx(mods, chat=chat)), "person:requester")["detail"] == "2 messages from you"


# ---- M3c: the status of a box -------------------------------------------------------------------------------------------------------
def test_m3c_filed_when_the_version_and_the_engines_latest_run_are_ok(line):
    import j2ui_map as M
    W = line[0]
    put_run(W, "Plan", "ok", id="r-plan", wrote={"art": "Site plan", "v": 1})
    m = M.build(make_ctx(line))
    assert {node(m, b)["status"] for b in WORK} == {"filed"}
    assert node(m, "work:charter")["status"] == "filed"


def test_m3c_a_version_whose_check_failed_with_no_failed_run_is_done_unchecked(mods):
    import j2ui_map as M
    W, R = mods[0], mods[1]
    seed_line(W, upto=3)
    add_ver(W, "Build", ok=False, notes=["index.html: almost no text"])
    put_run(W, "Check", "ok", id="r-check")
    register(W, R)
    m = M.build(make_ctx(mods))
    assert node(m, "work:build")["status"] == "done_unchecked" and node(m, "work:build")["version"] == 1
    assert node(m, "work:pages")["status"] == "filed"


def test_m3c_a_failed_run_is_a_fault(mods):
    import j2ui_map as M
    W, R = mods[0], mods[1]
    seed_line(W, upto=3)
    add_ver(W, "Build", ok=False)
    put_run(W, "Check", "failed", id="r-check-bad", started=ago(30), ended=ago(20))
    register(W, R)
    assert node(M.build(make_ctx(mods)), "work:build")["status"] == "fault"
    # a failed run with no version at all is a fault as well, and an older failure that a later run mended is not
    put_run(W, "Write", "failed", id="r-write-bad", started=ago(500), ended=ago(490))
    put_run(W, "Write", "ok", id="r-write-ok", started=ago(100), ended=ago(90))
    assert node(M.build(make_ctx(mods)), "work:pages")["status"] == "filed"


def test_m3c_an_engine_running_makes_its_box_running(mods):
    import j2ui_map as M
    W, R = mods[0], mods[1]
    seed_line(W, upto=2)
    put_run(W, "Write", "running", id="r-write-now")
    register(W, R)
    set_cycle(W, "running", 6)
    m = M.build(make_ctx(mods))
    assert node(m, "work:pages")["status"] == "running"
    assert node(m, "work:site-plan")["status"] == "filed" and node(m, "work:build")["status"] == "not_made"


def test_m3c_a_finished_department_never_says_running(mods):
    import j2ui_map as M
    W, R = mods[0], mods[1]
    seed_line(W, upto=2)
    put_run(W, "Write", "running", id="r-write-now")
    register(W, R)
    set_cycle(W, "done", 8)
    m = M.build(make_ctx(mods))
    assert "running" not in {n["status"] for n in m["nodes"]} and node(m, "work:pages")["status"] == "left_open"


def test_m3c_an_ask_that_names_the_engine_makes_its_box_wait_on_you(mods):
    import j2ui_map as M
    W, R = mods[0], mods[1]
    seed_line(W, upto=4)
    register(W, R)
    put_ask(W, "publish", engine="Publish")
    m = M.build(make_ctx(mods))
    assert node(m, "work:live-site")["status"] == "waiting_on_you" and node(m, "work:build")["status"] == "filed"


def test_m3c_no_version_is_left_open_in_a_stopped_department_else_not_made(mods):
    import j2ui_map as M
    W, R = mods[0], mods[1]
    seed_line(W, upto=2)
    register(W, R)
    m = M.build(make_ctx(mods))
    assert {node(m, b)["status"] for b in ("work:pages", "work:build", "work:live-site")} == {"not_made"}
    W.set_stopped(REF, True)
    m = M.build(make_ctx(mods))
    assert {node(m, b)["status"] for b in ("work:pages", "work:build", "work:live-site")} == {"left_open"}
    assert node(m, "work:brief")["status"] == "filed"


def test_m3c_the_brief_is_filed_once_it_has_a_version_even_if_its_check_failed(mods):
    import j2ui_map as M
    add_ver(mods[0], "Brief", ok=False)
    assert node(M.build(make_ctx(mods)), "work:brief")["status"] == "filed"


def test_m3c_an_engine_the_plan_left_out_draws_one_hollow_branch_box_after_the_trunk(mods):
    import j2ui_map as M
    W, R = mods[0], mods[1]
    seed_line(W, upto=4)
    register(W, R, left=("Publish",))
    m = M.build(make_ctx(mods))
    branch = [n for n in nodes_of(m, "work") if n["lane"] == "branch"]
    assert [b["id"] for b in branch] == ["work:live-site"] and ids(m, "work")[-1] == "work:live-site"
    b = branch[0]
    assert (b["status"], b["detail"], b["version"], b["file"], b["lane"]) == ("not_made", "left out of the plan", None, None, "branch")
    assert b["workflows"] == ["W-4"] and list(b) == WORK_KEYS
    trunk = [n["id"] for n in nodes_of(m, "work") if n["lane"] == "trunk"]
    assert trunk == ["work:charter", "work:brief", "work:site-plan", "work:pages", "work:build"]


def test_m3c_two_engines_left_out_draw_two_branch_boxes(mods):
    import j2ui_map as M
    W, R = mods[0], mods[1]
    seed_line(W, upto=3)
    register(W, R, left=("Check", "Publish"))
    m = M.build(make_ctx(mods))
    assert [n["id"] for n in nodes_of(m, "work") if n["lane"] == "branch"] == ["work:build", "work:live-site"]


# ---- M3d: what is not recorded ----------------------------------------------------------------------------------------------------------
def test_m3d_a_department_with_no_goal_has_no_charter_and_says_why(mods):
    import j2ui_map as M
    m = M.build(make_ctx(mods))
    assert "work:charter" not in ids(m) and ids(m, "work") == WORK
    assert "version of Charter" in m["not_recorded"]
    assert any("Charter" in s and "no goal" in s for s in m["not_recorded"])


def test_m3d_a_request_gives_the_department_a_goal(mods):
    import j2ui_map as M
    W = mods[0]
    W.owner_ask(REF, "Add a page about our pricing plans")
    assert "work:charter" in ids(M.build(make_ctx(mods)))


def test_m3d_the_builder_never_raises(mods):
    import j2ui_map as M
    from types import SimpleNamespace
    ctx = SimpleNamespace()
    m = M.build(ctx)
    assert m["schema"] == "map/1" and m["nodes"] == [] and m["edges"] == [] and m["not_recorded"]
    bad = make_ctx(mods)
    bad.fv = "nonsense"
    bad.memo = {}
    got = M.build(bad)
    assert got["schema"] == "map/1" and got["not_recorded"] and json.dumps(got)
    assert bad.reasons                                                      # why, for the router to record


def test_m3d_the_map_is_memoised_on_the_ctx(line):
    import j2ui_map as M
    ctx = make_ctx(line)
    assert M.build(ctx) is M.build(ctx)
