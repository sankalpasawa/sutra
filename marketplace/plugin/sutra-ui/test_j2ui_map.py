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
  M4a  the contract: the top-level keys, every edge ends on a node, edge kinds, the legend, a JSON round trip; the page's own
       renderMap draws it (node, the pinned page) with no undefined, NaN or null
  M4b  the steps: a 4-engine line gives the Charter, 5 trunk boxes and 5 step nodes in trunk order; a step's label, detail,
       status and workflows; made_by None; the engines left out make no step
  M4c  the edges: step, handoff (only where an engine reads a box that is not the one before it, and the charter's), speaks_to
       from the chat, wrote the charter, audits from the ledger, asks and uses from the board
  M4d  the status pill (waiting on you, a function running, Done, Done with open items, Stopped, Running, Waiting, Idle) and
       the checks; not_recorded names every gap and every workflow is on one box or named
  M6   all four views end to end in every cycle state (not started, assessing, waiting, adapting, bargaining, blocked,
       running, pursuing, done, stopped): map, board, artifacts and a site request, as the router serves them; no private key,
       no machine path, no GRANT, COUNTER or REFUSE and no act id in any string, no None where the page reads a string,
       the same twice, nothing written, and the page's own render of each draws without undefined, NaN or null; the same
       holds for text a builder or a function wrote (a question, an answer, a post, an ask, a payload with a private key and a
       path), as the router sends it: the board and the Map say the protocol's tokens in the owner's words, and the router
       shortens the paths and drops the private keys
Shares the department fixtures and the Ctx stand-in of test_j2ui_artifacts.py.
"""
import json
import re

import pytest

from test_j2ui_artifacts import (REF, FUNCS, add_ver, ago, make_ctx, mods, msg, page_render, plain_text, proto_consts,  # noqa: F401 -- mods is a fixture
                                 put_ask, put_post, put_run, put_step, router_client, seed_line, set_cycle)
from test_fixtures.j2ui.core_fixtures import machine  # noqa: F401 -- a fixture: the machine whose paths the router shortens
from test_j2ui_board import HOSTILE, hostile, put_questions, q

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
    assert any("goal" in s and "none is recorded" in s for s in m["not_recorded"])


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


# ---- M4a: the contract ---------------------------------------------------------------------------------------------------------------------
TOP_KEYS = {"schema", "run", "live", "status", "nodes", "edges", "legend", "built_from", "not_recorded"}
EDGE_KINDS = ("handoff", "step", "speaks_to", "draws_on", "asks", "uses")


def captured_map_keys():
    """The top-level keys of a captured prototype map when j2ui-verify's fixtures exist, else the list in the schema doc."""
    import pathlib
    cap = pathlib.Path(__file__).resolve().parent / "test_fixtures" / "j2ui" / "captured"
    for f in sorted(cap.glob("*map*.json")) if cap.is_dir() else []:
        got = json.loads(f.read_text(encoding="utf-8"))
        if isinstance(got, dict) and "nodes" in got:
            return set(got)
    return set(TOP_KEYS)


def test_m4a_top_level_keys_edges_legend_and_json(line):
    import j2ui_map as M
    m = M.build(make_ctx(line))
    assert set(m) == TOP_KEYS == captured_map_keys()
    assert m["schema"] == "map/1" and m["built_from"] == ["department record"] and m["run"] == REF
    json.loads(json.dumps(m))
    assert json.loads(json.dumps(m)) == m
    every = set(ids(m))
    for e in m["edges"]:
        assert list(e) == ["from", "to", "kind", "label", "n", "basis"]
        assert e["from"] in every and e["to"] in every, e
        assert e["kind"] in (proto_consts("j2_map.py", "EDGE_KINDS") or EDGE_KINDS)
        assert e["basis"] in ("recorded", "declared")
    pinned = proto_consts("j2_map.py", "LEGEND")
    if pinned is not None:
        assert m["legend"] == pinned
    assert len(m["legend"]) == 14 and [r["key"] for r in m["legend"]][:3] == ["function", "engine", "work"]
    assert M.EDGE_KINDS == EDGE_KINDS


def test_m4a_the_run_is_the_cycle_or_the_ref(line):
    import j2ui_map as M
    assert M.build(make_ctx(line))["run"] == REF
    set_cycle(line[0], "running", 6)
    assert M.build(make_ctx(line))["run"] == "cycle-test"


def test_m4a_the_pages_own_renderMap_draws_it(line):
    import j2ui_map as M
    W, R = line[0], line[1]
    put_run(W, "Plan", "ok", id="r-plan", wrote={"art": "Site plan", "v": 1})
    first = R.steps_view(REF, "Plan")["steps"][0]
    put_step(R, W, "Plan", first["id"], ok=True)
    chat = [msg(1, "user", "Build us a site"), msg(2, "identity", "@Requester Got it", next="user"), msg(3, "adaptation", "Proposed", next="priority")]
    m = M.build(make_ctx(line, chat=chat))
    out = page_render(map_=m)
    if out is None:
        pytest.skip("the pinned page or node is not here")
    html, words = out["map"], plain_text(out["map"])
    assert not re.search(r"\bundefined\b|\bNaN\b|\bnull\b", words), words[:300]
    assert "Nothing to draw yet" not in html and 'class="mappill idle"' in html
    for label in ("Charter", "Brief", "Site plan", "Pages", "Build", "Live site"):
        assert label in words, label
    assert "1 of 1 checks passed" in words and "Client Lead" in words and "Quality Reviewer" in words
    assert "You" in words and "1 from you" in words


def test_m4a_the_pages_own_renderMap_draws_every_state_and_a_branch(mods):
    import j2ui_map as M
    W, R = mods[0], mods[1]
    seed_line(W, upto=3)
    add_ver(W, "Build", ok=False)
    register(W, R, left=("Publish",))
    put_run(W, "Write", "failed", id="r-write-bad")
    put_ask(W, "publish", engine="Publish")
    m = M.build(make_ctx(mods))
    out = page_render(map_=m)
    if out is None:
        pytest.skip("the pinned page or node is not here")
    words = plain_text(out["map"])
    assert not re.search(r"\bundefined\b|\bNaN\b|\bnull\b", words) and "Waiting on you" in words
    assert "done · checks did not pass" in words and "Live site" in words


# ---- M4b: the steps ---------------------------------------------------------------------------------------------------------------------------
TRUNK_STEPS = ["step:charter>brief", "step:brief>site-plan", "step:site-plan>pages", "step:pages>build", "step:build>live-site"]


def test_m4b_a_four_engine_line_gives_the_charter_five_boxes_and_five_steps_in_order(line):
    import j2ui_map as M
    m = M.build(make_ctx(line))
    assert ids(m, "engine") == TRUNK_STEPS
    row = [n["id"] for n in m["nodes"] if n["row"] == "work"]
    assert row == ["work:charter", "step:charter>brief", "work:brief", "step:brief>site-plan", "work:site-plan", "step:site-plan>pages",
                   "work:pages", "step:pages>build", "work:build", "step:build>live-site", "work:live-site"]
    assert len([n for n in nodes_of(m, "work") if n["lane"] == "trunk"]) == 6                  # the Charter and five boxes


def test_m4b_without_a_goal_there_is_no_step_before_the_first_box(mods):
    import j2ui_map as M
    m = M.build(make_ctx(mods))
    assert ids(m, "engine") == TRUNK_STEPS[1:] and ids(m, "work")[0] == "work:brief"


def test_m4b_a_step_is_labelled_by_its_engine_and_the_first_is_make(line):
    import j2ui_map as M
    m = M.build(make_ctx(line))
    assert [node(m, s)["label"] for s in TRUNK_STEPS] == ["Make", "Plan", "Write", "Check", "Publish"]
    first = node(m, "step:charter>brief")
    assert (first["workflows"], first["detail"], first["file"], first["version"]) == ([], "not recorded", None, None)
    assert [node(m, s)["workflows"] for s in TRUNK_STEPS[1:]] == [["W-1"], ["W-2"], ["W-3"], ["W-4"]]


def test_m4b_a_step_node_has_the_prototypes_keys_and_no_made_by(line):
    import j2ui_map as M
    m = M.build(make_ctx(line))
    for n in nodes_of(m, "engine"):
        assert list(n) == ENGINE_KEYS
        assert (n["made_by"], n["team"], n["tag"], n["color"], n["unchecked"], n["row"]) == (None, None, None, None, [], "work")
    assert "made_by" not in json.dumps(m["not_recorded"])


def test_m4b_a_step_takes_the_status_and_lane_of_the_box_it_leads_to(mods):
    import j2ui_map as M
    W, R = mods[0], mods[1]
    seed_line(W, upto=3)
    add_ver(W, "Build", ok=False)
    register(W, R)
    m = M.build(make_ctx(mods))
    assert node(m, "step:site-plan>pages")["status"] == "filed" and node(m, "step:pages>build")["status"] == "done_unchecked"
    assert node(m, "step:build>live-site")["status"] == "not_made"
    assert {n["lane"] for n in nodes_of(m, "engine")} == {"trunk"}


def test_m4b_the_detail_counts_workflows_and_checks_passed(line):
    import j2ui_map as M
    W, R = line[0], line[1]
    steps = [s for s in R.steps_view(REF, "Write")["steps"] if s["mode"] == "slot"]
    assert len(steps) >= 2
    put_step(R, W, "Write", steps[0]["id"], ok=True)
    put_step(R, W, "Write", steps[1]["id"], ok=False)
    m = M.build(make_ctx(line))
    assert node(m, "step:site-plan>pages")["detail"] == "1 workflow · 1 of 2 checks passed"
    assert node(m, "step:brief>site-plan")["detail"] == "not recorded"                      # Plan has no rows
    assert m["status"]["checks"] == {"passed": 1, "run": 2}


def test_m4b_the_engines_the_plan_left_out_make_no_step(mods):
    import j2ui_map as M
    W, R = mods[0], mods[1]
    seed_line(W, upto=4)
    register(W, R, left=("Publish",))
    m = M.build(make_ctx(mods))
    assert ids(m, "engine") == TRUNK_STEPS[:-1]
    assert not [e for e in m["edges"] if "live-site" in e["from"] + e["to"]]


def test_m4b_before_the_plan_is_registered_no_engine_has_a_workflow(mods):
    import j2ui_map as M
    W = mods[0]
    seed_line(W, upto=3)
    set_cycle(W, "adapting", 2)                                   # a cycle, and no plan registered yet
    ctx = make_ctx(mods)
    assert ctx.planned is False and all(e["wid"] is None for e in ctx.engines)
    m = M.build(ctx)
    assert all(n["workflows"] == [] for n in m["nodes"]) and all(node(m, s)["detail"] == "not recorded" for s in TRUNK_STEPS)
    assert not [s for s in m["not_recorded"] if "not placed" in s]


# ---- M4c: the edges -----------------------------------------------------------------------------------------------------------------------------
def edges_of(m, kind):
    return [e for e in m["edges"] if e["kind"] == kind]


def test_m4c_step_edges_run_box_step_box_with_the_workflow_count(line):
    import j2ui_map as M
    m = M.build(make_ctx(line))
    got = [(e["from"], e["to"], e["n"], e["basis"]) for e in edges_of(m, "step")]
    assert got[:4] == [("work:charter", "step:charter>brief", 0, "declared"), ("step:charter>brief", "work:brief", 0, "declared"),
                       ("work:brief", "step:brief>site-plan", 1, "recorded"), ("step:brief>site-plan", "work:site-plan", 1, "recorded")]
    assert len(got) == 10 and all(e["label"] is None for e in edges_of(m, "step"))


def test_m4c_the_only_handoff_of_the_born_line_is_the_charters(line):
    import j2ui_map as M
    m = M.build(make_ctx(line))
    assert edges_of(m, "handoff") == [{"from": "work:charter", "to": "work:brief", "kind": "handoff", "label": "built from the charter",
                                       "n": 1, "basis": "declared"}]


def test_m4c_an_engine_that_reads_a_box_other_than_the_one_before_it_is_given_that_box(line):
    import j2ui_map as M
    ctx = make_ctx(line)
    next(e for e in ctx.engines if e["name"] == "Check")["reads"] = "Site plan"        # Check reads the plan as well as the pages
    ho = edges_of(M.build(ctx), "handoff")
    assert {"from": "work:site-plan", "to": "work:build", "kind": "handoff", "label": "given to W-3", "n": 1, "basis": "recorded"} in ho
    assert len(ho) == 2


def test_m4c_speaks_to_counts_come_from_the_chat(line):
    import j2ui_map as M
    chat = [msg(1, "user", "a"), msg(2, "user", "b"), msg(3, "identity", "@Requester x", next="user"), msg(4, "identity", "to adaptation", next="adaptation"),
            msg(5, "adaptation", "p", next="priority"), msg(6, "adaptation", "q", next="priority"), msg(7, "priority", "r", next="adaptation"),
            msg(8, "priority", "to a workflow", next="W-1"), msg(9, "W-1", "w", next="priority"), msg(10, "audit", "self", next="audit")]
    m = M.build(make_ctx(line, chat=chat))
    got = [(e["from"], e["to"], e["n"]) for e in edges_of(m, "speaks_to") if e["label"] is None]
    assert got == [("person:requester", "fn:identity", 2), ("fn:identity", "person:requester", 1), ("fn:identity", "fn:adaptation", 1),
                   ("fn:adaptation", "fn:priority", 2), ("fn:priority", "fn:adaptation", 1)]
    assert all(e["basis"] == "recorded" for e in edges_of(m, "speaks_to"))


def test_m4c_no_chat_no_speaks_to_counts(line):
    import j2ui_map as M
    assert [e for e in edges_of(M.build(make_ctx(line)), "speaks_to") if e["label"] is None] == []


def test_m4c_identity_wrote_the_charter_only_when_there_is_one(line, mods):
    import j2ui_map as M
    m = M.build(make_ctx(line))
    assert {"from": "fn:identity", "to": "work:charter", "kind": "speaks_to", "label": "wrote the charter", "n": None, "basis": "recorded"} in m["edges"]


def test_m4c_audit_audited_the_preview_box_as_many_times_as_it_read(line):
    import j2ui_map as M
    ctx = make_ctx(line)
    assert not [e for e in edges_of(M.build(ctx), "speaks_to") if e["label"] == "audits"]
    ev = lambda i, a: {"seq": i, "action": a, "actor": "Audit", "recipient": "Identity", "occurred_at": "2026-10-26T10:00:0%d+00:00" % i}
    ctx = make_ctx(line)
    ctx.events = [ev(1, "audit.finding_filed"), ev(2, "audit.not_read"), ev(3, "audit.finding_filed")]
    got = [e for e in edges_of(M.build(ctx), "speaks_to") if e["label"] == "audits"]
    assert got == [{"from": "fn:audit", "to": "work:build", "kind": "speaks_to", "label": "audits", "n": 2, "basis": "recorded"}]
    assert "which other function worked on Build (only Audit is recorded)" in M.build(ctx)["not_recorded"]


def test_m4c_asks_and_uses_lines_join_two_different_boxes(line):
    import j2ui_mapedges as E
    owner = {"W-1": "work:site-plan", "W-2": "work:pages", "W-3": "work:build"}
    entries = [{"id": "Q-1", "asked_by": "W-2", "to": "W-1", "status": "answered", "used_by": ["W-3", "W-1"]},
               {"id": "Q-2", "asked_by": "W-2", "to": "W-2", "status": "answered", "used_by": []},                  # inside one box
               {"id": "Q-3", "asked_by": "identity", "to": "W-1", "status": "answered", "used_by": []},             # a function has no box
               {"id": "Q-4", "asked_by": "W-2", "to": "W-1", "status": "open", "used_by": []}]                       # not answered
    got = E.board_edges(entries, owner)
    assert got == [{"from": "work:pages", "to": "work:site-plan", "kind": "asks", "label": "Q-1", "n": None, "basis": "recorded"},
                   {"from": "work:build", "to": "work:site-plan", "kind": "uses", "label": "Q-1", "n": None, "basis": "recorded"}]
    assert E.board_edges(None, owner) == [] and E.board_edges([{}], owner) == []


# ---- M4d: the pill, the checks and what is not recorded ------------------------------------------------------------------------------------
def state_of(m):
    return m["status"]["state"], m["status"]["state_status"]


def test_m4d_the_pill_says_what_stands(mods):
    import j2ui_map as M
    W, R = mods[0], mods[1]
    assert state_of(M.build(make_ctx(mods))) == ("Idle", "idle")
    set_cycle(W, "checking", 5)                                   # Adaptation waits on Root's review: nobody is working
    assert state_of(M.build(make_ctx(mods))) == ("Waiting", "waiting")
    set_cycle(W, "running", 6)
    assert state_of(M.build(make_ctx(mods))) == ("Coordination running", "running")
    set_cycle(W, "unread", 7)
    put_run(W, "Write", "running", id="r-write-now")
    assert state_of(M.build(make_ctx(mods))) == ("Running", "running")
    set_cycle(W, "adapting", 2)
    assert state_of(M.build(make_ctx(mods))) == ("Adaptation running", "running")
    put_ask(W, "publish", engine="Publish")
    assert state_of(M.build(make_ctx(mods))) == ("Waiting on you", "waiting_on_you")


def test_m4d_a_finished_or_stopped_department_never_says_running(mods):
    import j2ui_map as M
    W = mods[0]
    put_run(W, "Write", "running", id="r-write-now")
    set_cycle(W, "done", 8)
    assert state_of(M.build(make_ctx(mods))) == ("Done", "idle")
    W.set_stopped(REF, True)
    m = M.build(make_ctx(mods))
    assert state_of(m) == ("Done", "idle") and "running" not in {n["status"] for n in m["nodes"]}
    set_cycle(W, "assessing", 1)
    assert state_of(M.build(make_ctx(mods))) == ("Stopped", "idle")


def test_m4d_done_with_open_items(mods):
    import j2ui_map as M
    W = mods[0]
    set_cycle(W, "done", 8)
    assert state_of(M.build(make_ctx(mods)))[0] == "Done"
    put_ask(W, "finding", engine="Audit", text="The phone number is missing")
    assert state_of(M.build(make_ctx(mods)))[0] == "Waiting on you"          # an ask that waits on you comes first
    d = W.dept(REF)
    d["to_be_confirmed"] = [{"item": "D1", "why": "nobody gave the opening hours"}]
    W.save_dept(REF, d)
    W._put_ask(REF, dict(W.asks(REF)[0], status="stamped"))
    assert state_of(M.build(make_ctx(mods))) == ("Done with open items", "idle")


def test_m4d_not_recorded_names_every_gap_and_ends_with_the_two_fixed_lines(line):
    import j2ui_map as M
    nr = M.build(make_ctx(line))["not_recorded"]
    assert len(nr) == len(set(nr)) and all(isinstance(x, str) and x for x in nr)
    for want in ("version of Charter", "workflows of Brief", "tokens per function (Sutra records calls and cost, not tokens)",
                 "which function worked on Brief: not recorded", "which function worked on Site plan: not recorded",
                 "what Identity did (chat)", "chat (messages from the Requester)"):
        assert want in nr, want
    assert nr[-2:] == ["messages to and from workflow agents (W-n) are not drawn", "what the work draws on (Knows row, later version)"]


def test_m4d_every_workflow_is_on_one_box_or_named(line):
    import j2ui_map as M
    ctx = make_ctx(line)
    m = M.build(ctx)
    placed = [w for n in nodes_of(m, "work") for w in n["workflows"]]
    assert sorted(placed) == ["W-1", "W-2", "W-3", "W-4"] and len(placed) == len(set(placed))
    ctx = make_ctx(line)
    next(e for e in ctx.engines if e["name"] == "Write")["writes"] = "Ghost"             # an artifact the line does not hold
    m = M.build(ctx)
    placed = [w for n in nodes_of(m, "work") for w in n["workflows"]]
    assert "W-2" not in placed and "workflows not placed on the map: W-2" in m["not_recorded"]


def test_m4d_a_box_with_no_version_is_listed_and_a_made_one_names_its_gap(mods):
    import j2ui_map as M
    seed_line(mods[0], upto=2)
    nr = M.build(make_ctx(mods))["not_recorded"]
    assert "version of Pages" in nr and "version of Live site" in nr and "which function worked on Pages: not recorded" not in nr
    assert "which function worked on Brief: not recorded" in nr


# ---- M6: all four views, in every cycle state -------------------------------------------------------------------------------------------------
STATES = ["not_started", "assessing", "waiting", "adapting", "bargaining", "blocked", "running", "pursuing", "done", "stopped"]
#: an absolute machine path (j2ui_common.ABS_PATH once j2ui-core is merged); a relative file name such as build/v1/index.html is not one
ABS_PATH = re.compile(r"(?<![\w.@/-])(?:~|[A-Za-z]:)?(?:/[\w.@-]+){2,}")
BARGAIN = re.compile(r"\b(?:GRANT|COUNTER|REFUSE)\b|\b(?:grant|granted|counter|countered|refuse|refused)\b", re.I)
ACT_IDS = re.compile(r"accept-proposal|reject-proposal|not-understood|ASK_REQUESTER")


def scene(mods, state):
    """A department in one cycle state, with what that state looks like on the record: the line filed as far as the state
    goes, an ask where the state waits on the owner, an engine running where one runs."""
    W, R, J, F = mods
    if state == "not_started":
        return
    seed_line(W, upto={"assessing": 1, "waiting": 1, "adapting": 1, "bargaining": 1}.get(state, 5))
    step = {"assessing": 1, "waiting": 1, "adapting": 2, "bargaining": 3, "blocked": 8, "running": 6, "pursuing": 8, "done": 8, "stopped": 6}[state]
    cycle_state = "stopped" if state == "stopped" else state
    if state in ("running", "pursuing", "done", "stopped", "blocked"):
        from test_j2ui_map import register
        register(W, R, left=("Publish",) if state == "pursuing" else ())
        put_run(W, "Check", "ok", id="r-check")
    if state == "waiting":
        ask = W.j2_identity_ask("Which pages does the site need?", "cycle-test", "words", why="The brief names no pages")
        W._put_ask(REF, ask)
        set_cycle(W, "waiting", 1, open_ask=ask["id"])
    else:
        set_cycle(W, cycle_state, step)
    if state == "running":
        put_run(W, "Write", "running", id="r-write-now")
    if state == "blocked":
        put_ask(W, "blocked", engine="Identity", text="Priority said no to the plan and you can decide", id="a-blocked")
    if state == "pursuing":
        put_ask(W, "finding", engine="Audit", text="The phone number is missing", id="a-finding")
        put_questions(W, [q("Q-1", status="answered", answer="Home and About", answered_by="Plan", used_by=["Check"])])
    if state == "stopped":
        W.set_stopped(REF, True)


def all_views(ctx):
    import j2ui_artifacts as A
    import j2ui_board as B
    import j2ui_map as M
    import j2ui_site as S
    arts = A.listing(ctx)
    site = S.site(ctx, "latest")
    page = S.site(ctx, "latest", "index.html")
    served = [A.served(ctx, r["file"]) for r in arts["deliverables"] + arts["records"]]
    return {"map": M.build(ctx), "board": B.build(ctx), "artifacts": arts, "site": [site[0], site[1].decode("utf-8"), site[2], site[3]],
            "page": [page[0], page[1].decode("utf-8"), page[2], page[3]], "served": [[b.decode("utf-8"), m] for b, m in served if b is not None]}


def walk(value, path=""):
    """Every (path, key-or-None, value) of a JSON value, keys included."""
    if isinstance(value, dict):
        for k, v in value.items():
            yield path, k, v
            yield from walk(v, path + "/" + str(k))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from walk(v, path + "/%d" % i)
    else:
        yield path, None, value


def clean_views(got):
    """No private key, no machine path, no GRANT, COUNTER or REFUSE, no act id and no traceback in any key or string, and the
    JSON round trip is the same value."""
    import j2_runtime as J
    blob = json.dumps(got, ensure_ascii=False)
    assert json.loads(blob) == got
    keys = {str(k).lower() for _, k, _ in walk(got) if k is not None}
    assert not keys & set(J.PRIVATE_KEYS), keys & set(J.PRIVATE_KEYS)
    strings = [v for _, k, v in walk(got) if isinstance(v, str)]
    bad = [s for s in strings if ABS_PATH.search(s) or BARGAIN.search(s) or ACT_IDS.search(s)]
    assert not bad, bad[:3]
    assert not [s for s in strings if "Traceback" in s]


@pytest.mark.parametrize("state", STATES)
def test_m6_every_view_in_every_state_is_clean(mods, state):
    scene(mods, state)
    ctx = make_ctx(mods, chat=[msg(1, "user", "Build us a site"), msg(2, "identity", "@Requester Got it, working on it"),
                              msg(3, "adaptation", "Proposed the plan to Priority", next="priority")])
    got = all_views(ctx)
    clean_views(got)
    assert got["map"]["schema"] == "map/1" and got["board"]["schema"] == "board/1" and set(got["artifacts"]) == {"deliverables", "records"}


@pytest.mark.parametrize("state", STATES)
def test_m6_the_real_ctx_gives_the_same_views_once_core_is_merged(mods, state):
    """j2ui-core's get_ctx in place of the stand-in: the same nodes and box statuses in every state, and the same clean
    output (skipped until j2ui_common exists). The waiting scene here files one artifact; the line with its engines is
    test_m6_the_real_ctx_keeps_the_engines_while_identitys_question_is_open."""
    C = pytest.importorskip("j2ui_common", reason="j2ui-core is not merged yet")
    scene(mods, state)
    C.reset_caches()
    real, stand = all_views(C.get_ctx(REF)), all_views(make_ctx(mods))
    clean_views(real)
    assert [n["id"] for n in real["map"]["nodes"]] == [n["id"] for n in stand["map"]["nodes"]]
    work = lambda m: {n["id"]: n["status"] for n in m["nodes"] if n["kind"] == "work"}
    assert work(real["map"]) == work(stand["map"]) and real["map"]["status"]["state"] == stand["map"]["status"]["state"]
    files = lambda a: [r["file"] for r in a["deliverables"] + a["records"]]
    assert files(real["artifacts"]) == files(stand["artifacts"])


def waiting_line(mods):
    """The waiting state of a department that has most of its line: Root's check has registered the plan, Plan, Write and
    Check have each filed their work and a checked step, a stamp ask names Publish, and Identity's question to the owner is
    open beside it (the cycle waits on the owner)."""
    W, R = mods[0], mods[1]
    seed_line(W, upto=4)
    register(W, R)
    for engine in ("Plan", "Write", "Check"):
        put_run(W, engine, "ok", id="r-" + engine.lower())
        put_step(R, W, engine, next(s for s in R.steps_view(REF, engine)["steps"] if s["mode"] == "slot")["id"], ok=True)
    put_ask(W, "publish", id="a-publish")
    ask = W.j2_identity_ask("Which pages does the site need?", "cycle-test", "words", why="The brief names no pages")
    W._put_ask(REF, ask)
    set_cycle(W, "waiting", 1, open_ask=ask["id"])


def test_m6_the_real_ctx_keeps_the_engines_while_identitys_question_is_open(mods):
    """Identity's question names no engine, and website_dept.map_view read the engine of every pending ask: with the question
    open the real ctx had no engines and no plan, so the Map labelled every step 'Make', no box carried a workflow, the
    artifacts lost their writers and the box statuses could not see an engine's runs or asks. The real ctx and the stand-in
    (which reads the engines part by part) must give the same picture, and it must be the whole one."""
    C = pytest.importorskip("j2ui_common", reason="j2ui-core is not merged yet")
    import j2ui_artifacts as A
    import j2ui_map as M
    waiting_line(mods)
    C.reset_caches()
    real, stand = C.get_ctx(REF), make_ctx(mods)
    assert real.state == "waiting" and stand.state == "waiting" and real.paused_ask
    assert not [r for r in real.reasons if r.startswith("map")], real.reasons             # the engines were read, not given up on
    assert real.planned is True and len(real.engines) == 4
    mine = lambda c: [(e["name"], e["wid"], e["state"], e["in_line"], e["writes"]) for e in c.engines]
    assert mine(real) == mine(stand) == [("Plan", "W-1", "Idle", True, "Site plan"), ("Write", "W-2", "Idle", True, "Pages"),
                                         ("Check", "W-3", "Idle", True, "Build"), ("Publish", "W-4", "Waits", True, "Live site")]
    got, want = M.build(real), M.build(stand)
    assert [node(got, s)["label"] for s in TRUNK_STEPS] == ["Make", "Plan", "Write", "Check", "Publish"]
    assert [node(got, s)["workflows"] for s in TRUNK_STEPS] == [[], ["W-1"], ["W-2"], ["W-3"], ["W-4"]]
    assert [node(got, s)["detail"] for s in TRUNK_STEPS[1:4]] == ["1 workflow · 1 of 1 checks passed"] * 3
    assert node(got, "work:live-site")["status"] == "waiting_on_you" and node(got, "work:live-site")["workflows"] == ["W-4"]
    assert not [x for x in got["not_recorded"] if x.startswith("workflows of") and x != "workflows of Brief"], got["not_recorded"]
    assert not [x for x in got["not_recorded"] if "not placed" in x]
    chat_free = lambda m: ([(n["id"], n["label"], n["status"], n["detail"], n["file"], n["workflows"]) for n in m["nodes"] if n["row"] == "work"],
                           [e for e in m["edges"] if e["kind"] in ("step", "handoff")])
    assert chat_free(got) == chat_free(want)                                              # steps, boxes, workflows, hand-offs
    rows = lambda c: [(r["name"], r["workflows"], r["depends_on"], r["depends_on_labels"]) for r in
                      A.listing(c)["deliverables"] + A.listing(c)["records"]]
    assert rows(real) == rows(stand) and ("Site plan", ["W-1"], ["brief"], ["Brief"]) in rows(real)


def hostile_scene(mods, state):
    """The scene of a state with text a builder or a function wrote at its most hostile: a board row whose every field carries
    HOSTILE, a function's post and an ask of Identity's that carry it too (they reach the Map through the chat)."""
    W, R = mods[0], mods[1]
    scene(mods, state)
    rows = W._read(W.ddir(REF) / "questions.json", None) or {"entries": []}
    put_questions(W, list(rows["entries"]) + [hostile("Q-9")])
    put_post(W, R, "Adaptation", "Priority", "propose", HOSTILE, thread="x-hostile")
    put_ask(W, "finding", engine="Audit", text=HOSTILE, id="a-hostile")


@pytest.mark.parametrize("state", STATES)
def test_m6_text_a_builder_or_a_function_wrote_is_clean_as_the_router_sends_it(mods, state, machine):
    """Rule 4(e) holds for what the record's own writers put in: through the router, in every state, no string of the Map, the
    Board or the Artifacts holds a machine path, a private key, GRANT, COUNTER, REFUSE or an act id. (Before, only scenes with
    no hostile text were checked, and the board passed a question through a phrase table that leaves bare tokens alone.)"""
    machine("/Users/someone")                                  # the paths of HOSTILE are this machine's
    hostile_scene(mods, state)
    client = router_client()
    got = {}
    for name in ("map", "board", "artifacts"):
        r = client.get("/j2ui/%s/api/%s" % (REF, name))
        assert r.status_code == 200, (state, name, r.text[:200])
        got[name] = r.json()
    clean_views(got)
    blob = json.dumps(got)
    assert "/Users/" not in blob and "~/" not in blob and "abc123" not in blob
    board = got["board"]["entries"]
    assert board and board[-1]["id"] == "Q-9" and board[-1]["question"].startswith("Where is file.txt and x.md? said yes asked for less said no")
    assert board[-1]["artifact_update"]["kept"] == {"file": "out.json"} and "token" not in board[-1]["artifact_update"]
    for n in got["map"]["nodes"]:
        assert not re.search(r"GRANT|COUNTER|REFUSE|ASK_REQUESTER|-proposal|not-understood", n["detail"] + n["label"]), n


@pytest.mark.parametrize("state", STATES)
def test_m6_nothing_is_none_where_the_page_reads_a_string(mods, state):
    scene(mods, state)
    got = all_views(make_ctx(mods))
    m = got["map"]
    for n in m["nodes"]:
        assert isinstance(n["label"], str) and n["label"] and isinstance(n["detail"], str) and isinstance(n["id"], str), n
        assert isinstance(n["status"], str) and isinstance(n["workflows"], list), n
        assert n["file"] is None or isinstance(n["file"], str)
    for e in m["edges"]:
        assert all(isinstance(e[k], str) for k in ("from", "to", "kind", "basis")), e
    assert isinstance(m["status"]["state"], str) and m["status"]["state_status"] in ("running", "waiting", "waiting_on_you", "idle")
    assert all(isinstance(x, str) for x in m["not_recorded"]) and m["legend"]
    for r in got["artifacts"]["deliverables"] + got["artifacts"]["records"]:
        for k in ("name", "type", "kind", "form", "file", "sha256", "time", "label", "tag", "color", "open"):
            assert isinstance(r[k], str) and r[k], (k, r)
        assert isinstance(r["workflows"], list) and isinstance(r["depends_on"], list) and isinstance(r["depends_on_labels"], list)
    for e in got["board"]["entries"]:
        for k in ("id", "asked_by", "to", "about", "question", "status", "asked_by_role"):
            assert isinstance(e[k], str), (k, e)
        assert isinstance(e["used_by"], list) and isinstance(e["attempt"], int)
    for status, body, mime, headers in (got["site"], got["page"]):
        assert isinstance(body, str) and isinstance(mime, str) and "script-src 'none'" in headers["Content-Security-Policy"]


@pytest.mark.parametrize("state", STATES)
def test_m6_the_views_are_the_same_twice_and_write_nothing(mods, state):
    W = mods[0]
    scene(mods, state)
    snap = lambda: sorted((str(p.relative_to(W.ddir(REF))), p.stat().st_mtime_ns, p.stat().st_size) for p in W.ddir(REF).rglob("*") if p.is_file())
    before = snap()
    a = json.dumps(all_views(make_ctx(mods)), sort_keys=True)
    b = json.dumps(all_views(make_ctx(mods)), sort_keys=True)
    assert a == b and snap() == before


@pytest.mark.parametrize("state", STATES)
def test_m6_the_state_is_what_the_pill_and_the_boxes_say(mods, state):
    scene(mods, state)
    ctx = make_ctx(mods)
    assert ctx.state in ({"not_started": ("not_started", "not_ready")}.get(state) or (state,)), (state, ctx.state)       # the scene is the state it names
    m = all_views(ctx)["map"]
    said = (m["status"]["state"], m["status"]["state_status"])
    fn_status = {n["id"]: n["status"] for n in m["nodes"] if n["kind"] == "function"}
    boxes = {n["id"]: n["status"] for n in m["nodes"] if n["kind"] == "work"}
    if state in ("done", "stopped"):
        assert "running" not in set(fn_status.values()) | set(boxes.values()) and said[1] == "idle", (state, said)
        assert said[0] in ("Done", "Done with open items", "Stopped")
    if state in ("assessing", "adapting", "bargaining"):
        assert said[1] == "running" and said[0].endswith(" running"), said
        assert {"assessing": "fn:identity", "adapting": "fn:adaptation", "bargaining": "fn:priority"}[state] in [k for k, v in fn_status.items() if v == "running"]
    if state in ("waiting", "blocked", "pursuing"):
        assert said == ("Waiting on you", "waiting_on_you") and fn_status["fn:identity"] == "waiting_on_you"
        assert m["live"] is True
    if state == "not_started":
        assert said == ("Idle", "idle") and m["live"] is False and "work:charter" not in boxes
    if state == "running":
        assert said == ("Coordination running", "running") and boxes["work:pages"] == "running"
    if state == "pursuing":
        assert [n["id"] for n in m["nodes"] if n["kind"] == "work" and n["lane"] == "branch"] == ["work:live-site"]


@pytest.mark.parametrize("state", STATES)
def test_m6_the_pages_own_render_draws_every_view(mods, state):
    scene(mods, state)
    got = all_views(make_ctx(mods))
    out = page_render(map_=got["map"], artifacts=got["artifacts"], board=got["board"]["entries"])
    if out is None:
        pytest.skip("the pinned page or node is not here")
    for pane in ("map", "artifacts", "board"):
        words = plain_text(out[pane])
        assert words and not re.search(r"\bundefined\b|\bNaN\b|\bnull\b", words), (state, pane, words[:200])
    assert "Nothing to draw yet" not in out["map"]
    n = len(got["artifacts"]["deliverables"]) + len(got["artifacts"]["records"])
    assert out["artifacts"].count('class="artrow"') == n


def test_m6_the_four_views_in_the_router_order_for_a_whole_department(line):
    """The page polls state, then map, artifacts and board on a change, then opens the site: one ctx serves them all."""
    import j2ui_artifacts as A
    import j2ui_map as M
    import j2ui_site as S
    ctx = make_ctx(line)
    a, m = A.listing(ctx), M.build(ctx)
    assert A.listing(ctx) is a and M.build(ctx) is m                                      # one rebuild shared by every endpoint
    boxes = {n["file"] for n in m["nodes"] if n["kind"] == "work" and n["file"]}
    assert boxes <= {r["file"] for r in a["deliverables"] + a["records"]}                  # a box opens a file the listing names
    for f in boxes:
        assert A.served(ctx, f) is not None
    assert S.site(ctx, "latest")[0] == 302


def test_m6_when_the_engines_could_not_be_read_the_views_still_answer(line):
    """A read the engines depend on can fail (a card the record cannot read), and j2ui-core's get_ctx then hands over no
    engines and no plan: every view answers with what it can read, nothing raised, nothing blank."""
    import j2ui_artifacts as A
    import j2ui_map as M
    ctx = make_ctx(line)
    ctx.engines, ctx.planned = [], False
    ctx.reasons.append("the engines could not be read")
    m = M.build(ctx)
    assert m["schema"] == "map/1" and "work:build" in ids(m) and node(m, "work:build")["status"] == "filed"
    assert all(n["workflows"] == [] for n in m["nodes"])
    rows = A.listing(ctx)
    assert [r["name"] for r in rows["deliverables"]] == ["Build", "Live site"] and all(r["workflows"] == [] for r in rows["deliverables"] + rows["records"])
    json.dumps([m, rows])
