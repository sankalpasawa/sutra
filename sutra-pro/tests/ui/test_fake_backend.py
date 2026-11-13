"""UI-0: the tooling of the UI tests (docs/design/ui.md sections 8 and 10, decision D85).

What is tested here, in this order:

  1. the fixtures (every file parses; ids are the library's, status and edge words are J2's, the five atom words, the
     division lens, one chat line for every `who` that `whoLabel` names, the J2 captures against their manifest);
  2. the fake backend: every path of the UI-to-server contract (ui.md section 8, ORCH section 6) with the keys the UI
     reads, the error envelope, the token / Origin / Host rules, the event stream (hello, replay, resync, topics, ring),
     what the owner's lines do (the scripted stories of a first brief and of an answer);
  3. its test-only controls (`/__fake/emit|fixture|fail|log|state|reset|page|mount`);
  4. J2's data routes at the root with `?dept=` (the 28 of engine.md 7.1 and what sync 4 added: the plan map, the feeds, the catalog, the Artifacts groups,
     the run list and changes, the studio's records and pages, the Decide for me switch, and `POST /api/ask` with the lines it stores);
  5. the real UI package mounted on it (pages, boot block, CSP, static files) and the fixtures folder as an option;
  6. `cdp.py`: the Chrome driver against a stand-in DevTools endpoint and a stand-in Chrome program (no Chrome needed);
     `conftest.py`: its marker and fixtures, run under a copy of it; and, in tests marked `browser` (they run only with
     `SUTRA_BROWSER=1`), the driver and the fake with the app's own client scripts in a real Chrome;
  7. `scripts/capture_j2_fixtures.py`: against a stand-in J2 folder (no J2 needed) and, when `SUTRA_J2_CHECKOUT` names an
     extraction of prototypes/j2 at the pinned commit, against the real J2 (a drift check of the committed captures).

The stand-ins live in `fixtures/tools/` (`fake_devtools.py`, `standin_j2/`). Expected values come from the design (ui.md,
orchestrator.md, library.md, engine.md), written out below, and not from the code under test.
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import copy
import hashlib
import http.client
import importlib.util
import io
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import textwrap
import threading
import time
import urllib.parse
from collections import Counter
from pathlib import Path

import pytest
from fastapi.routing import iter_route_contexts

import cdp
import fake_backend as fb
from fake_backend import FakeClient
from sutra_app.library.types import overhead_atom_id

REPO = Path(__file__).resolve().parents[2]
UI_TESTS = Path(__file__).resolve().parent
FIXTURES = UI_TESTS / "fixtures"
J2_FIXTURES = FIXTURES / "j2"
TOOLS = FIXTURES / "tools"  # the stand-in DevTools and Chrome, and the stand-in J2 checkout (fixtures of the tests of cdp.py and the capture script)
SCRIPT = REPO / "scripts" / "capture_j2_fixtures.py"
sys.path.insert(0, str(TOOLS))
import fake_devtools as fdt  # noqa: E402  (after the path line above)

# ---- the design's vocabulary, written out here on purpose --------------------------------------------------------------
FUNCTIONS = ("identity", "adaptation", "priority", "coordination", "audit")
J2_FUNCS = (*FUNCTIONS, "validator")  # J2's own six: the names /api/activity and /api/ask serve (the validator is code)
# what J2's render harness printed that page_render.test.js compares (the seven of the first capture, then the Simple view's, the chat
# panel's and the Studio view's), and the layout harness last: the manifest lists them in this order (docs/design/j2-sync-4.md 4.8)
J2_GOLDENS = ("simple", "sprog", "workflows", "rail", "needs", "map", "agent", "finish", "journey", "journeyhtml", "sframe", "needids",
              "railst", "planmap", "msgfns", "feed", "teamwork", "plan", "team", "status", "views", "files", "parts", "tabs", "inline", "layout")
STATUS_WORDS = ("idle", "running", "waiting", "waiting_on_you", "fault", "filed", "done_unchecked", "left_open", "not_made")  # J2 map/1
FUNCTION_STATUS_WORDS = STATUS_WORDS[:5]  # a function node uses the first five
EDGE_KINDS = ("contains", "has_function", "has_step", "handoff", "depends_on", "speaks_to", "step")
STRUCTURAL_EDGE_KINDS = ("contains", "has_function", "has_step")
ATOM_WORDS = ("open", "verify_failed", "closed", "refused", "abandoned")
EVENTS = ("server.hello", "server.resync", "chat.turn", "chat.message", "chart.changed", "chart.approval", "graph.updated",
          "task.updated", "atom.updated", "usage.recorded", "needs_you.changed", "connector.health", "connector.switch",
          "connector.mode")
WHO = ("user", "sutra", "identity", "adaptation", "priority", "coordination", "audit", "validator", "system")  # plus W-<n>
CARD_KEYS = {  # ORCH 3.3 ChatCard, by type
    "chart_change": {"change_id", "decision", "summary", "added", "moved", "archived", "pending"},
    "task": {"task_id", "dept_id", "dept_name", "title", "status"},
    "approval": {"change_id", "question", "options"},
    "choice": {"question", "options"},
    "needs_you": {"dept_id", "dept_name", "question_message_id", "text", "options"},
    "done": {"task_id", "dept_name", "title", "status", "outcome"},
    "atom": {"atom_id", "outcome", "label", "goal", "rows"},
}
SESSION_KEYS = {"id", "node_id", "kind", "title", "writable", "status", "filed_under", "connector", "model", "provider_session_id",
                "last_message_id", "note"}
MESSAGE_KEYS = {"id", "session_id", "role", "who", "kind", "text", "card", "pause", "answered_by", "task_id", "state", "at"}
NODE_KEYS = {"id", "kind", "label", "status", "detail", "chat_session_id", "org_node_id", "dept_id", "task_id", "fn", "step_ref",
             "version", "meta"}
CHANGE_KEYS = {"seq", "id", "at", "actor", "decision", "status", "summary", "reason", "task_id", "task_title", "revision", "added",
               "moved", "archived", "reused"}
STATS_KEYS = {"calls", "seconds", "tokens_in", "tokens_out", "atoms_open", "atoms_closed", "atoms_failed", "atoms_total"}
FUNCTION_META_KEYS = {"goal", "task", "context", "constraints", "wait_on", "hands_to", "stats"}  # NodeDetail.node.meta of a function
ATOM_OUT_KEYS = {"id", "schema", "node_id", "task_id", "state", "goal", "attempt", "ts_open", "ts_closed", "body", "usage"}
USAGE_KEYS = {"calls", "usd", "tokens_in", "tokens_out"}
DEPARTMENT_KEYS = {"id", "name", "purpose", "node_status", "live_task_id", "session_id", "functions"}
NEEDS_KEYS = {"message_id", "session_id", "kind", "dept_id", "dept_name", "text", "options", "asked_at"}
HANDOFFS = {  # ORCH 3.3 NodeDetail: hands_to = HANDOFFS[fn]
    "identity": ["adaptation", "priority", "coordination", "audit"],
    "adaptation": ["priority", "identity", "audit", "coordination"],
    "priority": ["adaptation", "identity", "coordination"],
    "coordination": ["priority", "adaptation", "identity", "audit"],
    "audit": ["identity"],
}
STAGES = ("1", "2", "3", "full")

RE_TS = re.compile(r"^2026-11-\d\dT\d\d:\d\d:\d\dZ$")
RE_SESSION = re.compile(r"^(cs_org|cs_[0-9a-f]{12})$")
RE_STEP = re.compile(r"^s-[0-9a-f]{10}$")
RE_TASK = re.compile(r"^tsk_[0-9a-f]{12}$")
RE_RUN = re.compile(r"^j2-\d{8}-\d{6}-[0-9a-f]{4}$")
RE_ATOM = re.compile(r"^a-[0-9a-f]{10}-\d\d$")
RE_DEPT = re.compile(r"^[a-z][a-z0-9-]{1,39}$")


def load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def chats_fixtures() -> list[dict]:
    return [load(n) for n in ("chat-org.json", "chat-dept.json", "chat-identity.json", "chat-division.json")] + load("chat-others.json")["sessions"]


def graph_fixtures() -> dict[str, dict]:
    return {"1": load("graph.v1.json"), "2": load("graph.v2.json"), "3": load("graph.v3.json"), "full": load("graph-full.json")}


STAGE_CHART = {"1": "1", "2": "2", "3": "2", "full": "3"}  # stage -> chart version, as the fake serves it


def chart_fixtures() -> dict[str, dict]:
    return {v: load(f"chart.v{v}.json") for v in ("1", "2", "3")}


def change_fixtures() -> dict[str, list]:
    return {v: load(f"changes.v{v}.json") for v in ("1", "2", "3")}


# =====================================================================================================================
# 1. The fixtures
# =====================================================================================================================
EXPECTED_FILES = {
    "chart.v1.json", "chart.v2.json", "chart.v3.json", "changes.v1.json", "changes.v2.json", "changes.v3.json",
    "graph.v1.json", "graph.v2.json", "graph.v3.json", "graph-full.json", "node-identity.json", "chat-org.json",
    "chat-identity.json", "chat-dept.json", "chat-division.json", "chat-others.json", "departments.json", "needs-you.json",
    "health.json", "engine-settings.json", "connectors.json", "events.script.json", "functions.json", "atom-log.json",
    "mount_graph.html", "mount_panel.html", "j2",
}


def test_the_fixture_folder_holds_every_file_the_design_lists():
    assert EXPECTED_FILES <= {p.name for p in FIXTURES.iterdir()}


def test_every_fixture_parses():
    parsed = 0
    for path in sorted(FIXTURES.rglob("*.json")):
        json.loads(path.read_text(encoding="utf-8"))
        parsed += 1
    assert parsed >= 50  # 22 of the design plus the J2 captures


def test_the_mount_pages_have_one_boot_marker_and_a_script_that_names_their_module():
    graph = (FIXTURES / "mount_graph.html").read_text(encoding="utf-8")
    panel = (FIXTURES / "mount_panel.html").read_text(encoding="utf-8")
    for page in (graph, panel):
        assert page.count("<!--SUTRA-BOOT-->") == 1
        assert "/ui/js/sutra_ctx.js" in page and "/api/events" in page
        assert "http://" not in page and "https://" not in page  # offline, like the pages
    assert "GraphView.create" in graph and "OrgChartView.create" in graph and "sutra-graph.css" in graph
    assert "NodePanel.mount" in panel and 'id="nodepanel"' in panel and "sutra-panel.css" in panel


# ---- ids and words -----------------------------------------------------------------------------------------------------
def test_chart_ids_are_the_librarys():
    for version, chart in chart_fixtures().items():
        ids = [n["id"] for n in chart["nodes"]]
        assert len(set(ids)) == len(ids) and ids[0] == "root"
        for node in chart["nodes"]:
            assert set(node) == {"id", "kind", "name", "purpose", "parent_id", "position"}
            assert node["id"] == "root" or RE_DEPT.match(node["id"]), node
            assert node["kind"] in ("root", "department", "division")
            assert (node["parent_id"] is None) == (node["kind"] == "root")
            if node["parent_id"]:
                assert node["parent_id"] in ids
        # `position` is the index among siblings
        for parent in set(n["parent_id"] for n in chart["nodes"] if n["parent_id"]):
            positions = [n["position"] for n in chart["nodes"] if n["parent_id"] == parent]
            assert positions == list(range(len(positions)))
        # departments hang from the root, divisions from a department
        for node in chart["nodes"]:
            if node["kind"] == "department":
                assert node["parent_id"] == "root"
            if node["kind"] == "division":
                assert next(p for p in chart["nodes"] if p["id"] == node["parent_id"])["kind"] == "department"


def test_graph_ids_are_the_librarys_and_never_prefixed():
    for stage, graph in graph_fixtures().items():
        for node in graph["nodes"]:
            assert set(node) == NODE_KEYS, node["id"]
            kind, id_ = node["kind"], node["id"]
            if kind in ("root", "department", "division"):
                assert node["org_node_id"] == id_ and (id_ == "root" or RE_DEPT.match(id_))
            elif kind == "function":
                assert id_ == f"{node['dept_id']}.{node['fn']}" and node["fn"] in FUNCTIONS and node["org_node_id"] is None
            else:
                assert kind == "step" and RE_STEP.match(id_) and RE_TASK.match(node["task_id"]) and node["org_node_id"] is None
            assert RE_SESSION.match(node["chat_session_id"]), node
            assert "/" not in id_ and not id_.startswith(("n:", "f:", "s:", "org_"))
            assert isinstance(node["version"], int) and isinstance(node["meta"], dict)
        assert [n["id"] for n in graph["nodes"]][0] == "root"
        sessions = [n["chat_session_id"] for n in graph["nodes"]]
        assert len(set(sessions)) == len(sessions) and graph["nodes"][0]["chat_session_id"] == "cs_org"


def test_graph_statuses_are_j2s_nine_words_and_a_function_uses_the_first_five():
    seen = set()
    for stage, graph in graph_fixtures().items():
        for node in graph["nodes"]:
            assert node["status"] in STATUS_WORDS, node
            if node["kind"] == "function":
                assert node["status"] in FUNCTION_STATUS_WORDS, node
            seen.add(node["status"])
    assert seen == set(STATUS_WORDS), f"the fixtures miss the look of {set(STATUS_WORDS) - seen}"
    # the full graph alone shows every word, so one fixture can drive a test of every look
    assert {n["status"] for n in load("graph-full.json")["nodes"]} == set(STATUS_WORDS)


def test_graph_nodes_are_a_depth_first_preorder_with_functions_after_divisions_and_steps_last():
    charts = chart_fixtures()
    for stage, graph in graph_fixtures().items():
        chart = {n["id"]: n for n in charts[STAGE_CHART[stage]]["nodes"]}
        parent_of = {}
        for edge in graph["edges"]:
            if edge["kind"] in STRUCTURAL_EDGE_KINDS:
                assert edge["dst"] not in parent_of, f"two parents for {edge['dst']}"
                parent_of[edge["dst"]] = edge["src"]
        position = {n["id"]: i for i, n in enumerate(graph["nodes"])}
        assert set(parent_of) == set(position) - {"root"}
        children: dict[str, list] = {}
        for node in graph["nodes"][1:]:
            parent = parent_of[node["id"]]
            assert position[parent] < position[node["id"]], f"{node['id']} comes before its parent {parent}"
            children.setdefault(parent, []).append(node)
        for parent, kids in children.items():
            rank = [{"department": 0, "division": 0, "function": 1, "step": 2}[k["kind"]] for k in kids]
            assert rank == sorted(rank), f"{parent}: chart children, then functions, then steps"
            org = [chart[k["id"]]["position"] for k in kids if rank[kids.index(k)] == 0]
            assert org == sorted(org)
            fns = [k["fn"] for k in kids if k["kind"] == "function"]
            assert fns in ([], list(FUNCTIONS))
        # each edge kind goes with the right pair of kinds
        by_id = {n["id"]: n for n in graph["nodes"]}
        for edge in graph["edges"]:
            src, dst = by_id[edge["src"]], by_id[edge["dst"]]
            if edge["kind"] == "contains":
                assert src["kind"] in ("root", "department") and dst["kind"] in ("department", "division")
            elif edge["kind"] == "has_function":
                assert src["kind"] == "department" and dst["kind"] == "function"
            elif edge["kind"] == "has_step":
                assert dst["kind"] == "step" and src["kind"] in ("department", "step")


def test_the_graph_mirrors_the_chart_it_names():
    charts = chart_fixtures()
    for stage, graph in graph_fixtures().items():
        chart = charts[STAGE_CHART[stage]]
        assert graph["chart_version"] == chart["version"]
        structural = [n for n in graph["nodes"] if n["kind"] in ("root", "department", "division")]
        assert sorted(n["id"] for n in structural) == sorted(n["id"] for n in chart["nodes"])
        chart_edges = {(n["parent_id"], n["id"]) for n in chart["nodes"] if n["parent_id"]}
        graph_edges = {(e["src"], e["dst"]) for e in graph["edges"] if e["kind"] == "contains"}
        assert graph_edges == chart_edges
        for node in structural:
            label = next(c["name"] for c in chart["nodes"] if c["id"] == node["id"])
            assert node["label"] == label
        departments = {n["id"] for n in structural if n["kind"] == "department"}
        functions = [n for n in graph["nodes"] if n["kind"] == "function"]
        assert len(functions) == 5 * len(departments)
        for n in graph["nodes"]:
            if n["kind"] == "division":  # a division belongs to the department above it
                assert n["dept_id"] == next(c["parent_id"] for c in chart["nodes"] if c["id"] == n["id"])


def test_function_nodes_carry_exactly_stats_and_wait_on():
    for stage, graph in graph_fixtures().items():
        for node in graph["nodes"]:
            if node["kind"] != "function":
                assert "stats" not in node["meta"]
                continue
            assert set(node["meta"]) == {"stats", "wait_on"}, node["id"]
            stats = node["meta"]["stats"]
            assert set(stats) == STATS_KEYS
            assert stats["atoms_open"] in (0, 1)  # a node has at most one open atom
            assert stats["atoms_total"] >= stats["atoms_open"] + stats["atoms_closed"] + stats["atoms_failed"]
            assert all(isinstance(v, (int, float)) and v >= 0 for v in stats.values())
            waiting = node["status"] in ("waiting", "waiting_on_you")
            assert (node["meta"]["wait_on"] is not None) == waiting, node  # a waiting node always names who it waits on
            if node["status"] == "waiting_on_you":
                assert node["meta"]["wait_on"] == "you"
            if node["meta"]["wait_on"] not in (None, "you"):
                assert node["meta"]["wait_on"] in FUNCTIONS


def test_departments_and_steps_name_their_run():
    for stage, graph in graph_fixtures().items():
        for node in graph["nodes"]:
            if node["kind"] in ("department", "step"):
                assert RE_RUN.match(node["meta"]["run_id"]), node
            elif node["kind"] != "function":
                assert node["meta"] == {}


def test_steps_are_one_task_step_per_task_with_builder_steps_below_it():
    graph = load("graph-full.json")
    steps = [n for n in graph["nodes"] if n["kind"] == "step"]
    task_steps = [n for n in steps if n["step_ref"] == "task"]
    builders = [n for n in steps if n["step_ref"] != "task"]
    assert len(task_steps) == 2 and len(builders) == 4
    assert all(re.fullmatch(r"W-\d+", n["step_ref"]) for n in builders)
    parents = {e["dst"]: e["src"] for e in graph["edges"] if e["kind"] == "has_step"}
    for b in builders:
        parent = next(n for n in task_steps if n["id"] == parents[b["id"]])
        assert parent["task_id"] == b["task_id"] and parent["dept_id"] == b["dept_id"]
    # the chart level shows only the latest task step of each department
    for stage in ("2", "3", "full"):
        assert any(n["step_ref"] == "task" for n in graph_fixtures()[stage]["nodes"] if n["kind"] == "step")


def test_edges_use_the_seven_kinds_and_the_stored_ones_are_all_there():
    graph = load("graph-full.json")
    kinds = Counter(e["kind"] for e in graph["edges"])
    assert set(kinds) == set(EDGE_KINDS)
    ids = {n["id"] for n in graph["nodes"]}
    seen = set()
    for edge in graph["edges"]:
        assert set(edge) == {"src", "dst", "kind", "label"} and edge["src"] in ids and edge["dst"] in ids
        key = (edge["src"], edge["dst"], edge["kind"])
        assert key not in seen
        seen.add(key)
    depends = [e for e in graph["edges"] if e["kind"] == "depends_on"]
    assert {e["label"] for e in depends} == {"reads", "revises"}  # a revision is terracotta, a read blue
    assert all(e["label"].isdigit() for e in graph["edges"] if e["kind"] == "speaks_to")  # the message count
    by_id = {n["id"]: n for n in graph["nodes"]}
    assert all(by_id[e["src"]]["kind"] == "step" and by_id[e["dst"]]["kind"] == "step" for e in depends)
    # a step relation is stored once, from the reading step, and two steps never get a handoff
    pairs = {frozenset((e["src"], e["dst"])) for e in depends}
    assert len(pairs) == len(depends)
    assert all(by_id[e["src"]]["kind"] == "function" for e in graph["edges"] if e["kind"] == "handoff")
    for stage, g in graph_fixtures().items():
        assert {e["kind"] for e in g["edges"]} <= set(EDGE_KINDS)


def test_graph_versions_only_grow():
    graphs = graph_fixtures()
    assert [graphs[s]["version"] for s in ("1", "2", "3", "full")] == sorted(graphs[s]["version"] for s in ("1", "2", "3", "full"))
    assert graphs["2"]["version"] != graphs["3"]["version"]


# ---- the change log ----------------------------------------------------------------------------------------------------
def test_changes_are_the_wire_shape_in_order():
    changes = change_fixtures()
    full = changes["3"]
    assert changes["1"] == full[:1] and changes["2"] == full[:2]
    for index, change in enumerate(full, start=1):
        assert set(change) == CHANGE_KEYS
        assert change["seq"] == index and change["id"] == f"chg-{index:04d}"
        assert RE_TS.match(change["at"]) and (index == 1 or change["at"] > full[index - 2]["at"])
        assert change["actor"] in ("chat_agent", "user", "system")
        assert change["decision"] in ("reuse", "add", "rearrange")
        assert change["status"] in ("applied", "pending_approval", "rejected", "stale", "failed")
        assert re.fullmatch(r"req-\d+", change["task_id"])
        assert all(isinstance(change[k], list) for k in ("added", "moved", "archived", "reused"))
    first = full[0]  # the bootstrap row
    assert (first["decision"], first["actor"], first["added"]) == ("add", "system", ["root"])
    assert Counter(c["decision"] for c in full) == Counter(add=3, reuse=1, rearrange=2)
    assert full[2]["reused"] == ["web"] and full[2]["added"] == []  # a reuse changes nothing
    pending = full[-1]
    assert pending["status"] == "pending_approval" and pending["revision"] is None and pending["archived"] == ["faq"]


def test_every_chart_version_is_the_result_of_its_changes():
    charts, changes = chart_fixtures(), change_fixtures()
    for version, chart in charts.items():
        rows = changes[version]
        applied = [c for c in rows if c["status"] == "applied"]
        assert chart["version"] == max(c["revision"] for c in applied)
        ids = {n["id"] for n in chart["nodes"]}
        for change in applied:
            assert set(change["added"] + change["moved"] + change["reused"]) <= ids
        added = {i for c in applied for i in c["added"]}
        assert added == ids  # every node was added by some change
        for change in rows:
            if change["status"] != "applied":  # the lists hold the plan, which the chart does not have yet
                assert set(change["archived"]) <= ids


# ---- chats -------------------------------------------------------------------------------------------------------------
def test_chat_sessions_and_messages_have_the_wire_shape():
    for chat in chats_fixtures():
        session, messages = chat["session"], chat["messages"]
        assert set(session) == SESSION_KEYS and RE_SESSION.match(session["id"])
        assert session["kind"] in ("org", "department", "division", "function", "step")
        assert session["writable"] == (session["kind"] in ("org", "department", "division"))  # ORCH 1.1
        assert session["status"] == "active" and session["filed_under"] is None
        assert [m["id"] for m in messages] == list(range(1, len(messages) + 1))
        stages = set(chat["visible_at"])
        assert stages <= set(STAGES)
        assert all(0 <= v <= len(messages) for v in chat["visible_at"].values()) and 0 <= chat["initial_visible"] <= len(messages)
        for message in messages:
            assert set(message) == MESSAGE_KEYS and message["session_id"] == session["id"]
            assert message["role"] in ("user", "agent", "system")
            assert message["kind"] in ("text", "question", "card", "note", "error")
            assert message["state"] in ("ok", "pending", "error")
            assert RE_TS.match(message["at"])
            assert (message["card"] is not None) == (message["kind"] == "card")
            assert (message["who"] == "user") == (message["role"] == "user")
            assert message["who"] in WHO or re.fullmatch(r"W-\d+", message["who"]), message
            if message["card"]:
                card = message["card"]
                assert set(card) == CARD_KEYS[card["type"]] | {"type"}, card
            if message["kind"] == "question":
                assert message["pause"] and message["who"] == "identity" and "Option 1" in message["text"]
                later = [m for m in messages if m["id"] > message["id"] and m["role"] == "user"]
                assert message["answered_by"] == (later[0]["id"] if later else None)
        ats = [m["at"] for m in messages]
        assert ats == sorted(ats)


def test_chats_cover_every_who_whoLabel_names_and_every_card_type():
    who, cards = Counter(), Counter()
    for chat in chats_fixtures():
        for message in chat["messages"]:
            who[message["who"]] += 1
            if message["card"]:
                cards[message["card"]["type"]] += 1
    assert set(WHO) <= set(who) and any(re.fullmatch(r"W-\d+", w) for w in who)
    assert set(cards) == set(CARD_KEYS)


def test_the_org_chat_is_the_root_session_with_the_greeting_first_and_every_owner_card():
    org = load("chat-org.json")
    assert org["session"]["id"] == "cs_org" and org["session"]["node_id"] == "root" and org["session"]["kind"] == "org"
    first = org["messages"][0]
    assert (first["who"], first["kind"]) == ("sutra", "text") and first["text"].startswith("Hello.")
    assert org["initial_visible"] == 1
    cards = {m["card"]["type"]: m["card"] for m in org["messages"] if m["card"]}
    assert set(cards) == {"chart_change", "task", "needs_you", "done", "approval", "choice"}
    task_cards = [m["card"] for m in org["messages"] if m["card"] and m["card"]["type"] == "task"]
    assert [c["dept_id"] for c in task_cards] == ["web", "content"] and all(RE_TASK.match(c["task_id"]) for c in task_cards)
    assert cards["choice"]["question"] == "Which team fits best?" and cards["choice"]["options"][-1]["label"] == "None of these"
    assert [o["label"] for o in cards["approval"]["options"]] == ["Yes", "No"]
    needs = next(m for m in org["messages"] if m["card"] and m["card"]["type"] == "needs_you")
    assert needs["who"] == "identity" and needs["card"]["text"].startswith("@Requester")  # the team's question, verbatim
    # chart_change cards point at the change log by id; moved and archived carry names for the sentence
    changes = {c["id"]: c for c in change_fixtures()["3"]}
    for message in org["messages"]:
        card = message["card"]
        if card and card["type"] in ("chart_change", "approval"):
            assert card["change_id"] in changes
        if card and card["type"] == "chart_change":
            assert card["decision"] == changes[card["change_id"]]["decision"]
            assert card["pending"] == (changes[card["change_id"]]["status"] == "pending_approval")


def test_each_chat_shows_how_much_per_stage_and_the_stage_story_is_monotonic():
    org = load("chat-org.json")
    assert org["visible_at"] == {"1": 1, "2": 6, "3": 6, "full": 22}
    dept = load("chat-dept.json")
    assert dept["session"]["kind"] == "department" and dept["session"]["writable"]
    assert [m["role"] for m in dept["messages"]] == ["user", "agent", "user", "agent"]
    assert dept["messages"][1]["kind"] == "question" and dept["messages"][1]["answered_by"] == 3
    assert dept["visible_at"]["2"] == 2 and dept["visible_at"]["3"] == 4  # asked at stage 2, answered at stage 3


def test_the_division_lens_holds_notes_and_the_departments_lines_and_is_writable():
    chat = load("chat-division.json")
    session = chat["session"]
    assert session["kind"] == "division" and session["writable"] and session["node_id"] == "menu"
    assert session["connector"] is None  # a lens has no provider of its own
    kinds = [m["kind"] for m in chat["messages"]]
    assert kinds[0] == "note" and "division of Content" in chat["messages"][0]["text"]
    assert any(m["role"] == "user" for m in chat["messages"]) and any(m["who"] == "identity" for m in chat["messages"])
    department = next(c for c in chats_fixtures() if c["session"]["node_id"] == "content")
    lines = [m["text"] for m in department["messages"]]
    assert all(m["text"] in lines for m in chat["messages"] if m["kind"] != "note")  # the department's own words
    assert load("graph-full.json")["nodes"][[n["id"] for n in load("graph-full.json")["nodes"]].index("menu")]["kind"] == "division"


def test_function_logs_are_read_only_and_atom_cards_live_only_in_function_sessions():
    for chat in chats_fixtures():
        kind = chat["session"]["kind"]
        for message in chat["messages"]:
            if message["card"] and message["card"]["type"] == "atom":
                assert kind == "function" and message["who"] == "sutra"  # a record written by code (D58, D64)
                card = message["card"]
                assert card["label"] in ("WORK ATOM OPEN", "WORK ATOM CLOSED", "VERIFY FAILED", "WORK ATOM ABANDONED", "ATOM REFUSED")
                assert card["outcome"] in ("opened", "closed", "verify_failed", "refused", "abandoned")
                assert all(set(row) == {"label", "text"} for row in card["rows"])
        if kind in ("function", "step"):
            assert not chat["session"]["writable"]
    assert load("chat-identity.json")["session"]["node_id"] == "web.identity"


# ---- the function node and its atoms ---------------------------------------------------------------------------------------
def atoms_of_identity():
    return load("node-identity.json")["atoms"]


def test_node_identity_holds_one_atom_of_each_of_the_five_display_states():
    detail = load("node-identity.json")
    assert set(detail) == {"node", "session", "atoms", "usage_total", "task", "archived_chats"}
    atoms = detail["atoms"]
    assert Counter(a["state"] for a in atoms) == Counter(ATOM_WORDS)
    assert atoms[0]["state"] == "open"  # the open atom first, then the newest
    assert [a["ts_open"] for a in atoms[1:]] == sorted((a["ts_open"] for a in atoms[1:]), reverse=True)
    for atom in atoms:
        assert set(atom) == ATOM_OUT_KEYS and atom["schema"] == "work-atom/0.3" and set(atom["usage"]) == USAGE_KEYS
        assert RE_ATOM.match(atom["id"]) and atom["node_id"] == "web.identity" and RE_TASK.match(atom["task_id"])


def test_the_atom_ids_are_built_by_the_librarys_own_functions():
    from sutra_app.library.types import atom_sid, function_atom_id

    sid = atom_sid("j2-20261104-100004-7f3a", "web.identity")
    ids = sorted(a["id"] for a in atoms_of_identity())
    assert ids == [function_atom_id(sid, n) for n in range(1, 6)]


def test_the_five_atoms_follow_the_stored_state_rules_of_the_library():
    by = {a["state"]: a for a in atoms_of_identity()}
    opened = by["open"]
    assert opened["attempt"] == 2 and opened["ts_closed"] is None
    assert not {"closed_by", "reason", "refusal", "abandon_code"} & set(opened["body"])
    checks = opened["body"]["verify"]["checks"]
    assert all(len(c["results"]) == opened["attempt"] for c in checks)  # V6: exactly `attempt` results per check
    failed = by["verify_failed"]  # stored abandoned with abandon_code verify_failed, shown verify_failed (D57)
    assert failed["attempt"] == 2 and failed["ts_closed"]
    assert failed["body"]["abandon_code"] == "verify_failed" and failed["body"]["closed_by"] == "manual-override"
    assert failed["body"]["reason"].startswith("verify failed:")
    assert all(len(c["results"]) == 2 for c in failed["body"]["verify"]["checks"])  # two tries
    assert any(c["results"][-1]["exit_code"] != 0 for c in failed["body"]["verify"]["checks"])
    closed = by["closed"]
    assert closed["body"]["closed_by"] == "verify" and closed["ts_closed"] and closed["attempt"] >= 1
    assert all(c["results"][-1]["exit_code"] == 0 for c in closed["body"]["verify"]["checks"])
    assert any(r["evidence"].startswith("RECOVERED:") for c in closed["body"]["verify"]["checks"] for r in c["results"])
    refused = by["refused"]
    assert refused["attempt"] == 0 and refused["ts_closed"] and "closed_by" not in refused["body"]
    assert set(refused["body"]["refusal"]) == {"code", "message"}
    assert refused["usage"] == {"calls": 0, "usd": None, "tokens_in": None, "tokens_out": None}
    abandoned = by["abandoned"]
    assert abandoned["body"]["abandon_code"] in ("run_ended", "replaced", "manual")  # not verify_failed
    assert abandoned["body"]["reason"] and abandoned["body"]["closed_by"] == "manual-override" and abandoned["ts_closed"]
    for atom in (opened, failed, closed, abandoned):
        for check in atom["body"]["verify"]["checks"]:
            assert check["text"] and check["template"] and check["relevance"]
            assert [r["attempt"] for r in check["results"]] == list(range(1, len(check["results"]) + 1))
            assert all(set(r) == {"attempt", "exit_code", "evidence"} for r in check["results"])


def test_the_function_node_detail_matches_its_graph_chip_and_hands_to_follows_handoffs():
    detail = load("node-identity.json")
    node, graph_node = detail["node"], next(n for n in load("graph.v2.json")["nodes"] if n["id"] == "web.identity")
    assert set(node["meta"]) == FUNCTION_META_KEYS
    assert {k: v for k, v in node.items() if k != "meta"} == {k: v for k, v in graph_node.items() if k != "meta"}
    assert node["meta"]["stats"] == graph_node["meta"]["stats"] and node["meta"]["wait_on"] == graph_node["meta"]["wait_on"]
    assert node["meta"]["hands_to"] == HANDOFFS["identity"]
    assert isinstance(node["meta"]["goal"], str) and isinstance(node["meta"]["task"], str)
    assert node["meta"]["task"].startswith("J2.")  # the standing ROLE line, its step code first
    assert all(isinstance(c, str) for c in node["meta"]["context"] + node["meta"]["constraints"])
    stats = node["meta"]["stats"]
    atoms = detail["atoms"]
    assert stats["atoms_open"] == sum(a["state"] == "open" for a in atoms)
    assert stats["atoms_closed"] == sum(a["state"] == "closed" for a in atoms)
    assert stats["atoms_failed"] == sum(a["state"] == "verify_failed" for a in atoms)
    assert stats["atoms_total"] == len(atoms)
    session = detail["session"]
    assert session["id"] == node["chat_session_id"] and session["node_id"] == "web.identity" and not session["writable"]
    assert detail["task"] == {"id": atoms[0]["task_id"], "title": "Coffee shop landing page", "status": "waiting_user"}
    assert detail["usage_total"]["calls"] == stats["calls"] and detail["archived_chats"] == []


def test_the_identity_log_has_a_card_for_every_atom_and_the_cards_use_the_librarys_labels():
    cards = [m["card"] for m in load("chat-identity.json")["messages"] if m["card"]]
    for atom in atoms_of_identity():
        mine = [c for c in cards if c["atom_id"] == atom["id"]]
        assert mine, atom["id"]
        last = mine[-1]
        if atom["state"] == "open":  # a failed try with tries left leaves the atom open: its last card is VERIFY FAILED
            assert last["outcome"] in ("opened", "verify_failed")
        else:  # a final failure is stored abandoned: its last card is the abandon card
            assert last["outcome"] == {"verify_failed": "abandoned", "closed": "closed", "refused": "refused",
                                       "abandoned": "abandoned"}[atom["state"]]
    assert {c["label"] for c in cards} == {"WORK ATOM OPEN", "WORK ATOM CLOSED", "VERIFY FAILED", "WORK ATOM ABANDONED", "ATOM REFUSED"}


def test_the_atom_log_is_append_only_one_row_per_closed_atom_and_follows_the_ledger_rules():
    rows = load("atom-log.json")
    assert [r["seq"] for r in rows] == list(range(1, len(rows) + 1))
    assert len({r["atom_id"] for r in rows}) == len(rows)
    atoms = {a["id"]: a for a in atoms_of_identity()}
    assert {r["status"] for r in rows} == {"closed", "verify_failed", "abandoned", "refused"}
    for row in rows:
        assert set(row) == {"seq", "atom_id", "node_id", "status", "body", "ts"} and RE_TS.match(row["ts"])
        body = row["body"]
        assert body["atom_id"] == row["atom_id"] and body["status"] == row["status"] and body["node_id"] == "web.identity"
        atom = atoms[row["atom_id"]]
        assert atom["state"] == row["status"]  # the display word of the stored atom
        if row["status"] == "closed":
            assert body["verify"]["exit_code"] == 0
        elif row["status"] == "verify_failed":
            assert body["verify"]["exit_code"] != 0 and body["reason"]
        else:
            assert body["verify"] is None and body["reason"]
    assert next(a for a in atoms.values() if a["state"] == "open")["id"] not in {r["atom_id"] for r in rows}  # not finished yet


# ---- the rest of the fixtures ----------------------------------------------------------------------------------------------
def test_departments_follow_the_graph_stage():
    departments = load("departments.json")
    assert set(departments) == set(STAGES)
    graphs = graph_fixtures()
    for stage, rows in departments.items():
        graph = graphs[stage]
        assert [d["id"] for d in rows] == [n["id"] for n in graph["nodes"] if n["kind"] == "department"]
        for row in rows:
            assert set(row) == DEPARTMENT_KEYS and RE_DEPT.match(row["id"])
            node = next(n for n in graph["nodes"] if n["id"] == row["id"])
            assert row["node_status"] == node["status"] and row["session_id"] == node["chat_session_id"]
            assert [f["fn"] for f in row["functions"]] == list(FUNCTIONS)
            for f in row["functions"]:
                fn_node = next(n for n in graph["nodes"] if n["id"] == f["id"])
                assert (f["id"], f["status"], f["chat_session_id"]) == (f"{row['id']}.{f['fn']}", fn_node["status"], fn_node["chat_session_id"])
                assert set(f) == {"id", "fn", "status", "chat_session_id"}
            assert (row["live_task_id"] is None) or RE_TASK.match(row["live_task_id"])


def test_needs_you_is_the_open_question_of_the_department_session():
    needs = load("needs-you.json")
    assert set(needs) == set(STAGES) and needs["1"] == [] and needs["3"] == []
    dept_chat = load("chat-dept.json")
    for stage in ("2", "full"):
        (item,) = needs[stage]
        assert set(item) == NEEDS_KEYS and item["kind"] == "question" and item["dept_id"] == "web"
        question = next(m for m in dept_chat["messages"] if m["id"] == item["message_id"])
        assert item["session_id"] == dept_chat["session"]["id"] and item["text"] == question["text"]  # verbatim
        assert item["options"] == ["Yes, show the prices", "No, names only"]
        assert all(f"Option {i}: {o}" in item["text"] for i, o in enumerate(item["options"], start=1))


def test_health_is_the_two_connector_rows_with_one_signed_out_so_sign_in_has_something_to_do():
    health = load("health.json")
    assert set(health) == {"ok", "version", "schema", "connectors"} and set(health["connectors"]) == {"claude", "codex"}
    claude, codex = health["connectors"]["claude"], health["connectors"]["codex"]
    assert claude["signed_in"] and claude["health"]["state"] == "ok" and claude["billing"] == "subscription"
    assert not codex["signed_in"] and codex["health"]["state"] == "signed_out" and codex["method"] is None
    assert {"installed", "signed_in", "detail", "version", "method", "billing", "plan", "plan_label", "health", "quota"} == set(claude) == set(codex)


def test_engine_settings_follow_the_engine_sections_field_list():
    settings = load("engine-settings.json")
    assert settings["schema"] == "engine-settings/1"
    locked = ["send_mode", "send_cap", "milestone_emails", "test_email", "test_slack_target", "chrome", "force_audit_fail",
              "force_audit_note", "force_question", "memory_test_lessons"]  # engine.md LOCKED_FIELDS
    assert settings["locked"] == locked
    assert settings["editable"] == [f for f in settings["defaults"] if f not in locked]
    assert len(settings["defaults"]) == 37 and settings["defaults"]["builder_timeout"] == 600.0       # J2 sync 5 (D169); sync 6 (D177, D179): run_templates, auto_reuse, artifact_library, reviewer, reviewer_wait
    flags = {f: settings["defaults"][f] for f in ("run_templates", "auto_reuse", "artifact_library", "reviewer", "reviewer_wait")}
    assert flags == {"run_templates": False, "auto_reuse": False, "artifact_library": False, "reviewer": True, "reviewer_wait": 120.0}
    types = settings["output_types"]                                                  # D166: the pages' choices; the names are data
    assert types and all(set(t) == {"name", "label", "form", "pin"} and isinstance(t["pin"], bool) for t in types)
    assert len({t["name"] for t in types}) == len(types) and {t["form"] for t in types} <= {"page", "document"}
    assert settings["defaults"]["send_mode"] == "dry-run" and settings["defaults"]["budget"] == 100
    assert settings["defaults"]["delay"] == 0.0 and settings["defaults"]["realization"] is True and settings["defaults"]["board"] is False
    assert settings["effective"] == {**settings["defaults"], **settings["global"], **settings["department"]}
    assert set(settings["global"]) <= set(settings["editable"]) and set(settings["department"]) <= set(settings["editable"])
    assert settings["global"] and settings["department"]  # a test can see both layers


def test_connector_fixtures_give_test_answers_an_error_and_every_sign_in_ending():
    connectors = load("connectors.json")
    assert connectors["test"]["claude"]["ok"] is True and isinstance(connectors["test"]["claude"]["seconds"], float)
    assert connectors["test"]["codex"]["usd"] is None  # Codex has no price on the wire
    error = connectors["test_error"]["error"]
    assert set(error) == {"code", "message", "details"} and error["details"]["kind"]
    start = connectors["sign_in"]["start"]
    assert set(start) == {"id", "url", "code", "expires_in"} and start["expires_in"] == 900
    ends = {name: seq[-1] for name, seq in connectors["sign_in"]["sequences"].items()}
    assert ends == {"success": "signed_in", "failed": "failed", "expired": "expired"}
    assert all(set(seq[:-1]) == {"pending"} for seq in connectors["sign_in"]["sequences"].values())


def test_the_function_table_has_all_five_functions_and_all_fourteen_check_texts():
    functions = load("functions.json")
    assert list(functions["meta"]) == list(FUNCTIONS) == list(functions["atom_templates"])
    for fn in FUNCTIONS:
        meta = functions["meta"][fn]
        assert meta["hands_to"] == HANDOFFS[fn] and meta["goal"] and meta["task"].startswith("J2.")
        template = functions["atom_templates"][fn]
        assert all(c["template"] in functions["check_text"] for c in template["checks"])
    assert len(functions["check_text"]) == 14  # the verify registry (D54)


def test_the_event_script_has_a_sample_for_every_event_and_flows_that_use_real_sessions():
    script = load("events.script.json")
    assert set(script["samples"]) == set(EVENTS)
    sessions = {c["session"]["id"] for c in chats_fixtures()}
    for name, flow in script["flows"].items():
        assert flow["session"] in sessions
        for step in flow["steps"]:
            kinds = [k for k in ("reveal", "emit", "fixture") if k in step]
            assert len(kinds) == 1, step
            assert set(step.get("only_stage", STAGES)) <= set(STAGES)
            if "reveal" in step:
                assert step["reveal"]["session"] in sessions
            if "emit" in step:
                assert step["emit"] in EVENTS
                assert step["data"] is not None
            if "fixture" in step:
                assert step["fixture"]["name"] in ("chart", "graph")
    assert set(script["flows"]) == {"first_task", "answer"}


def test_the_event_samples_have_the_wire_keys():
    samples = load("events.script.json")["samples"]
    assert set(samples["server.hello"]) == {"version", "chart_version", "graph_version"}
    assert samples["server.resync"]["reason"] in ("gap", "restart")
    assert set(samples["chat.turn"]) == {"session_id", "turn", "phase", "detail"}
    assert set(samples["chat.message"]) == {"session_id", "message"} and set(samples["chat.message"]["message"]) == MESSAGE_KEYS
    assert set(samples["chart.changed"]) == {"revision", "change_id", "kind", "added", "moved", "merged", "version", "summary", "archived"}
    assert set(samples["chart.approval"]) == {"change_id", "summary", "message_id"}
    assert set(samples["graph.updated"]) == {"version", "nodes", "edges_added", "edges_removed"}
    assert all(set(n) == NODE_KEYS for n in samples["graph.updated"]["nodes"])
    assert set(samples["task.updated"]["task"]) == {"id", "dept_id", "dept_name", "scope_node_id", "title", "status", "run_id",
                                                    "parent_task_id", "depends_on", "outcome", "created_at", "started_at",
                                                    "ended_at", "usage"}
    atom = samples["atom.updated"]
    assert set(atom) == {"atom_id", "node_id", "outcome", "state", "atom"} and set(atom["atom"]) == ATOM_OUT_KEYS
    assert atom["atom"]["state"] == atom["state"] == "closed" and atom["atom_id"] == atom["atom"]["id"]
    assert set(samples["usage.recorded"]) == {"row", "task_total"}
    assert set(samples["usage.recorded"]["row"]) >= {"provider", "model", "purpose", "atom_id", "usd", "tokens_in", "tokens_out",
                                                     "call_ref", "id", "at"}
    assert samples["needs_you.changed"] == {"count": 1}
    assert set(samples["connector.health"]) == {"provider", "state", "until", "reason"}
    assert set(samples["connector.switch"]) == {"session_id", "from", "to", "reason"} and set(samples["connector.mode"]) == {"mode"}


def test_the_flows_end_where_the_stage_visibility_says():
    script = load("events.script.json")
    org_reveals = [s["reveal"]["upto"] for s in script["flows"]["first_task"]["steps"] if s.get("reveal", {}).get("session") == "cs_org"]
    assert org_reveals == sorted(org_reveals) and org_reveals[-1] == load("chat-org.json")["visible_at"]["2"]
    dept = [s["reveal"]["upto"] for s in script["flows"]["answer"]["steps"] if s.get("reveal", {}).get("session") == "cs_5e0a77b19c3d"]
    assert dept[-1] == load("chat-dept.json")["visible_at"]["3"]
    answer_first = script["flows"]["answer"]["steps"][0]
    assert answer_first["reveal"]["upto"] == 3 and answer_first["text_from_post"]  # the owner's own line shows what was posted


# ---- the J2 captures ---------------------------------------------------------------------------------------------------
def test_the_j2_captures_match_their_manifest_byte_for_byte():
    manifest = json.loads((J2_FIXTURES / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "j2-fixtures/1" and manifest["mock"] is True
    assert re.fullmatch(r"[0-9a-f]{40}", manifest["j2_commit"])
    files = {p.name for p in J2_FIXTURES.iterdir() if p.is_file()} - {"MANIFEST.json"}
    assert files == set(manifest["files"]), "every captured file is in the manifest and the reverse"
    for name, info in manifest["files"].items():
        data = (J2_FIXTURES / name).read_bytes()
        assert len(data) == info["bytes"] and hashlib.sha256(data).hexdigest() == info["sha256"], name


def test_the_j2_captures_hold_a_small_finished_mock_run_and_the_goldens_of_the_page_harness():
    state = json.loads((J2_FIXTURES / "state.json").read_bytes())
    assert len((J2_FIXTURES / "state.json").read_bytes()) < 150_000  # R4: small enough to commit
    assert state["mock"] is True and state["status"] == "waiting" and state["workflows"] and state["chat"]
    manifest = json.loads((J2_FIXTURES / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["harness"]["goldens"] == [f"golden-{k}.json" for k in J2_GOLDENS]
    for key in J2_GOLDENS:
        assert (J2_FIXTURES / f"golden-{key}.json").is_file()
    rail = json.loads((J2_FIXTURES / "golden-rail.json").read_bytes())
    assert isinstance(rail, list) and {"conflicts", "identity", "audit"} <= {section["id"] for section in rail}
    for who in (*FUNCTIONS, "W-1"):
        agent = json.loads((J2_FIXTURES / f"agent-{who}.json").read_bytes())
        assert agent["schema"] == "agent/1" and agent["found"] is True
    assert json.loads((J2_FIXTURES / "agent-unknown.json").read_bytes())["found"] is False
    assert "<title>Brew Lab</title>" in (J2_FIXTURES / "site-latest.html").read_text(encoding="utf-8")


def test_the_j2_captures_hold_the_routes_feeds_and_answers_that_j2_added_in_sync_4():
    load = lambda name: json.loads((J2_FIXTURES / name).read_bytes())  # noqa: E731
    plan_map = load("plan-map.json")  # J2's plan-map/1 carries no schema key
    assert plan_map["found"] is True and len(plan_map["workflows"]) == 6 and plan_map["stages"] and plan_map["changes"] == []
    groups = load("artifacts-groups.json")
    assert groups["schema"] == "artifacts-groups/1" and [g["id"] for g in groups["groups"]] == ["plan", "guides", "site", "documents", "records"]
    assert load("changes.json") == {"changes": []}  # the mock brief has no change request
    runlist = load("runlist.json")
    assert list(runlist) == ["live", "runs"] and [r["id"] for r in runlist["runs"]] == [runlist["live"]] == [load("runs.json")["live"]]
    catalog = load("catalog.json")
    assert catalog["schema"] == "template-library/1" and catalog["dir"] == "library" and catalog["groups"] and len(catalog["runs"]) == 8
    for who in J2_FUNCS:  # one feed and one answer per function, from the records of the same run
        feed, answer = load(f"activity-{who}.json"), load(f"ask-{who}.json")
        assert feed["schema"] == "activity/1" and feed["who"] == who and feed["found"] is True and feed["events"], who
        assert set(answer) == {"who", "answer", "from"} and answer["who"] == who and answer["from"] == "records", who
        assert answer["answer"].startswith("From the records:"), who
    unknown = load("activity-unknown.json")  # a name J2 does not know: the run's step names are still there, and no event
    assert (unknown["schema"], unknown["who"], unknown["persona"], unknown["found"], unknown["events"]) == ("activity/1", "nobody", "", False, [])
    assert set(unknown["names"]) == {f"W-{n}" for n in range(1, 7)}


def test_no_j2_capture_holds_an_absolute_home_folder_path():
    """R5: the catalog fixture shows six of J2's own development runs; the capture made the home-folder paths of the machine they ran on
    `not recorded` (the rule of patch P15 of the vendoring) and refuses any other."""
    home = re.compile(rb"(?:/Users|/home)/[^/\s\"'\\]+/")
    assert [p.name for p in sorted(J2_FIXTURES.iterdir()) if p.is_file() and home.search(p.read_bytes())] == []
    libraries = [run.get("library") for run in json.loads((J2_FIXTURES / "catalog.json").read_bytes())["runs"]]
    assert libraries.count("not recorded") == 6 and sorted(v for v in libraries if v != "not recorded") == ["/tmp/j2-live-library", "/tmp/j2-live-library-2"]


def test_the_graph_run_ids_extend_the_run_id_j2_recorded():
    j2_run = json.loads((J2_FIXTURES / "runs.json").read_bytes())["live"]
    graph_runs = {n["meta"]["run_id"] for g in graph_fixtures().values() for n in g["nodes"] if n["meta"].get("run_id")}
    assert any(r.startswith(j2_run + "-") for r in graph_runs)  # the app adds 4 hex digits to J2's own id


# =====================================================================================================================
# 2. The fake backend
# =====================================================================================================================
def ok(client, path, **query):
    status, body = client.get(path, **query)
    assert status == 200, (path, status, body)
    return body


def error_of(answer, status, code):
    got_status, body = answer
    assert got_status == status, answer
    assert set(body) == {"error"} and set(body["error"]) == {"code", "message", "details"}, body
    assert body["error"]["code"] == code, body
    assert isinstance(body["error"]["message"], str) and body["error"]["message"] and isinstance(body["error"]["details"], dict)
    return body["error"]


class Stream:
    """One open `/api/events` connection, read frame by frame with plain `http.client`."""

    def __init__(self, base_url: str, path: str = "/api/events", headers: dict | None = None, timeout: float = 5.0) -> None:
        parts = urllib.parse.urlsplit(base_url)
        self.conn = http.client.HTTPConnection(parts.hostname, parts.port, timeout=timeout)
        self.conn.request("GET", path, headers=headers or {})
        self.response = self.conn.getresponse()
        self.status = self.response.status
        self.headers = {k.lower(): v for k, v in self.response.getheaders()}

    def next(self, timeout: float = 10.0) -> dict | None:
        """The next frame, `{"comment": ...}` for a comment line, or None when the server closed the stream."""
        self.conn.sock.settimeout(timeout)
        frame: dict = {}
        while True:
            line = self.response.readline()
            if not line:
                return None
            text = line.decode("utf-8").rstrip("\n")
            if text == "":
                if frame:
                    if "data" in frame:
                        frame["data"] = json.loads(frame["data"])
                    if "id" in frame:
                        frame["id"] = int(frame["id"])
                    return frame
                continue
            if text.startswith(":"):
                return {"comment": text}
            key, _, value = text.partition(": ")
            frame[key] = value

    def take(self, count: int, timeout: float = 10.0) -> list[dict]:
        out = []
        for _ in range(count):
            frame = self.next(timeout)
            assert frame is not None, f"the stream ended after {len(out)} frames: {out}"
            out.append(frame)
        return out

    def until(self, event: str, timeout: float = 10.0) -> list[dict]:
        seen = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            frame = self.next(max(0.05, deadline - time.monotonic()))
            assert frame is not None, f"the stream ended before {event}: {seen}"
            seen.append(frame)
            if frame.get("event") == event:
                return seen
        raise AssertionError(f"no {event} within {timeout} s: {seen}")

    def quiet(self, seconds: float = 0.3) -> bool:
        try:
            self.next(seconds)
        except (TimeoutError, OSError):
            return True
        return False

    def close(self) -> None:
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def raw_request(base_url: str, method: str, path: str, *, headers: dict | None = None, body: bytes | None = None):
    """A request with exactly the headers given (Host included): (status, headers, body bytes)."""
    parts = urllib.parse.urlsplit(base_url)
    conn = http.client.HTTPConnection(parts.hostname, parts.port, timeout=10)
    try:
        conn.putrequest(method, path, skip_host="Host" in (headers or {}), skip_accept_encoding=True)
        for key, value in (headers or {}).items():
            conn.putheader(key, value)
        if body is not None:
            conn.putheader("Content-Length", str(len(body)))
        conn.endheaders(body)
        response = conn.getresponse()
        return response.status, {k.lower(): v for k, v in response.getheaders()}, response.read()
    finally:
        conn.close()


# ---- the chart and the graph ---------------------------------------------------------------------------------------------
def test_the_chart_and_its_change_log_follow_the_stage(fake):
    charts, changes = chart_fixtures(), change_fixtures()
    assert ok(fake, "/api/chart") == charts["1"] and ok(fake, "/api/chart/changes") == changes["1"]  # a new app starts at stage 1
    fake.stage("2")
    assert ok(fake, "/api/chart") == charts["2"] and ok(fake, "/api/chart/changes") == changes["2"]
    fake.stage("3")
    assert ok(fake, "/api/chart") == charts["2"]  # the owner answered a question: the chart did not change
    fake.stage("full")
    assert ok(fake, "/api/chart") == charts["3"] and ok(fake, "/api/chart/changes") == changes["3"]


def test_chart_changes_take_after_and_limit(fake):
    fake.stage("full")
    assert [c["seq"] for c in ok(fake, "/api/chart/changes")] == [1, 2, 3, 4, 5, 6]
    assert [c["seq"] for c in ok(fake, "/api/chart/changes", after=4)] == [5, 6]
    assert [c["seq"] for c in ok(fake, "/api/chart/changes", limit=2)] == [1, 2]
    assert [c["seq"] for c in ok(fake, "/api/chart/changes", after=2, limit=2)] == [3, 4]
    assert ok(fake, "/api/chart/changes", after=6) == []
    assert [c["seq"] for c in ok(fake, "/api/chart/changes", after=-3)] == [1, 2, 3, 4, 5, 6]  # a negative cursor is the start
    assert len(ok(fake, "/api/chart/changes", limit=0)) == 1  # the smallest page is one row
    assert len(ok(fake, "/api/chart/changes", limit=100000)) == 6
    error_of(fake.get("/api/chart/changes", after="x"), 422, "validation")


def test_int_arg_clamps_a_page_size_between_its_bounds():
    assert fb.int_arg(None, 50, 1, 500) == 50
    assert fb.int_arg(0, 50, 1, 500) == 1 and fb.int_arg(7, 50, 1, 500) == 7 and fb.int_arg(10_000, 50, 1, 500) == 500


def test_the_graph_at_level_chart_is_the_structure_and_one_task_step_per_team(fake):
    assert ok(fake, "/api/graph") == graph_fixtures()["1"]  # chart is the default level
    fake.stage("full")
    graph = ok(fake, "/api/graph", level="chart")
    assert Counter(n["kind"] for n in graph["nodes"]) == Counter(root=1, department=2, division=2, step=2)
    assert all(n["step_ref"] == "task" for n in graph["nodes"] if n["kind"] == "step")
    ids = {n["id"] for n in graph["nodes"]}
    assert graph["edges"] and all(e["src"] in ids and e["dst"] in ids for e in graph["edges"])
    assert not any(e["kind"] in ("has_function", "depends_on", "handoff", "speaks_to") for e in graph["edges"])
    assert {k: v for k, v in graph.items() if k not in ("nodes", "edges")} == {
        k: v for k, v in graph_fixtures()["full"].items() if k not in ("nodes", "edges")}


def test_the_graph_at_level_full_is_the_whole_fixture_and_the_stage_picks_the_version(fake):
    for stage in STAGES:
        fake.stage(stage)
        assert ok(fake, "/api/graph", level="full") == graph_fixtures()[stage]


def test_the_graph_can_be_cut_to_one_team_or_one_task(fake):
    fake.stage("full")
    web = ok(fake, "/api/graph", level="full", dept="web")
    assert {n["id"] for n in web["nodes"]} == {"root", "web", "faq", *(f"web.{f}" for f in FUNCTIONS)} | {
        n["id"] for n in graph_fixtures()["full"]["nodes"] if n["kind"] == "step" and n["dept_id"] == "web"}
    assert {n["id"] for n in ok(fake, "/api/graph", level="chart", dept="content")["nodes"]} == {"root", "content", "menu", "s-8d2e6b4a1f"}
    one = ok(fake, "/api/graph", level="full", task="tsk_b7c8d9e0f1a2")
    steps = [n for n in one["nodes"] if n["kind"] == "step"]
    assert [n["id"] for n in steps] == ["s-8d2e6b4a1f"] and len(one["nodes"]) == 21 - 5
    error_of(fake.get("/api/graph", dept="nosuch"), 404, "not_found")
    assert error_of(fake.get("/api/graph", level="deep"), 422, "validation")["message"] == "level must be chart or full."


def test_graph_node_detail_of_a_function_node_has_the_seven_meta_keys_and_atoms_that_add_up(fake):
    fake.stage("full")
    detail = ok(fake, "/api/graph/nodes/web.adaptation")
    assert set(detail) == {"node", "session", "atoms", "usage_total", "task", "archived_chats"}
    node = detail["node"]
    assert set(node) == NODE_KEYS and set(node["meta"]) == FUNCTION_META_KEYS
    assert node["meta"]["hands_to"] == HANDOFFS["adaptation"] and isinstance(node["meta"]["task"], str)
    stats = node["meta"]["stats"]
    assert len(detail["atoms"]) == stats["atoms_total"] == 3
    assert Counter(a["state"] for a in detail["atoms"]) == Counter(closed=2, open=1) and detail["atoms"][0]["state"] == "open"
    assert all(set(a) == ATOM_OUT_KEYS for a in detail["atoms"])
    assert detail["usage_total"]["calls"] == stats["calls"] and detail["usage_total"]["tokens_in"] == stats["tokens_in"]
    assert detail["session"] == ok(fake, f"/api/chats/{node['chat_session_id']}")
    assert detail["task"] == {"id": "tsk_a1b2c3d4e5f6", "title": "Coffee shop landing page", "status": "waiting_user"}
    assert detail["archived_chats"] == []


def test_a_function_without_work_has_no_atoms_and_no_usage(fake):
    fake.stage("full")
    detail = ok(fake, "/api/graph/nodes/web.coordination")
    assert detail["atoms"] == [] and detail["usage_total"] == {"calls": 0, "usd": None, "tokens_in": None, "tokens_out": None}


def test_the_atoms_of_every_function_node_agree_with_its_chip_at_every_stage(fake):
    for stage in STAGES:
        fake.stage(stage)
        for node in graph_fixtures()[stage]["nodes"]:
            if node["kind"] != "function":
                continue
            detail = ok(fake, f"/api/graph/nodes/{node['id']}")
            stats = node["meta"]["stats"]
            states = Counter(a["state"] for a in detail["atoms"])
            assert len(detail["atoms"]) == stats["atoms_total"], (stage, node["id"])
            assert states["open"] == stats["atoms_open"] and states["closed"] == stats["atoms_closed"]
            assert states["verify_failed"] == stats["atoms_failed"], (stage, node["id"])
            assert set(states) <= set(ATOM_WORDS)
            assert detail["node"]["status"] == node["status"] and detail["node"]["meta"]["stats"] == stats


def test_the_detail_of_identity_at_stage_2_is_the_node_identity_fixture(fake):
    fake.stage("2")
    assert ok(fake, "/api/graph/nodes/web.identity") == load("node-identity.json")


def test_when_the_owner_has_answered_identity_has_no_open_atom_and_its_detail_says_so(fake):
    fake.stage("3")
    detail = ok(fake, "/api/graph/nodes/web.identity")
    assert detail["node"]["status"] == "idle" and detail["node"]["meta"]["wait_on"] is None
    by_id = {a["id"]: a for a in detail["atoms"]}
    before = {a["id"]: a for a in load("node-identity.json")["atoms"]}
    assert Counter(a["state"] for a in detail["atoms"]) == Counter(closed=2, verify_failed=1, refused=1, abandoned=1)
    opened_id = next(i for i, a in before.items() if a["state"] == "open")
    closed = by_id[opened_id]  # the open atom was closed by a third, passing try
    assert closed["attempt"] == 3 and closed["body"]["closed_by"] == "verify" and closed["ts_closed"] == "2026-11-04T10:02:15Z" > closed["ts_open"]
    assert all(c["results"][-1] == {"attempt": 3, "exit_code": 0, "evidence": "ok"} for c in closed["body"]["verify"]["checks"])
    assert all(len(c["results"]) == 3 for c in closed["body"]["verify"]["checks"])
    stats = detail["node"]["meta"]["stats"]
    assert (stats["atoms_open"], stats["atoms_closed"], stats["atoms_failed"], stats["atoms_total"]) == (0, 2, 1, 5)
    assert before[opened_id]["state"] == "open"  # the fixture itself is not touched


def test_node_detail_of_other_kinds(fake):
    fake.stage("full")
    department = ok(fake, "/api/graph/nodes/web")
    assert department["atoms"] == [] and department["node"]["meta"] == {"run_id": "j2-20261104-100004-7f3a"}
    assert department["task"]["id"] == "tsk_a1b2c3d4e5f6" and department["session"]["kind"] == "department"
    step = ok(fake, "/api/graph/nodes/s-577ba56fe5")
    assert step["node"]["status"] == "done_unchecked" and step["session"]["kind"] == "step" and not step["session"]["writable"]
    division = ok(fake, "/api/graph/nodes/menu")
    assert division["task"] is None and division["session"]["kind"] == "division" and division["session"]["writable"]
    assert ok(fake, "/api/graph/nodes/root")["session"]["id"] == "cs_org"
    error_of(fake.get("/api/graph/nodes/nobody.identity"), 404, "not_found")


def test_task_status_words_follow_the_step_status_of_orch_5_6(fake):
    # ORCH 5.6: task step node: blocked/queued/cancelled -> not_made; starting/running -> running; waiting_user -> waiting_on_you;
    # done -> filed; done_with_open_items/stopped -> left_open; crashed -> fault
    for task_status, step_status in [("queued", "not_made"), ("running", "running"), ("waiting_user", "waiting_on_you"),
                                     ("done", "filed"), ("done_with_open_items", "left_open"), ("crashed", "fault")]:
        assert fb.TASK_STATUS[step_status] == task_status
    fake.stage("2")
    assert ok(fake, "/api/graph/nodes/web.identity")["task"]["status"] == "waiting_user"
    fake.stage("3")
    assert ok(fake, "/api/graph/nodes/web.identity")["task"]["status"] == "running"
    fake.stage("full")
    assert ok(fake, "/api/graph/nodes/content.identity")["task"]["status"] == "done"  # the Content step is filed


# ---- chats ---------------------------------------------------------------------------------------------------------------
def test_chat_sessions_exist_for_the_nodes_of_the_current_graph_only(fake):
    sessions = ok(fake, "/api/chats")
    assert [s["id"] for s in sessions] == ["cs_org"]
    error_of(fake.get("/api/chats/cs_5e0a77b19c3d"), 404, "not_found")  # the Web team does not exist yet: "This chat is gone."
    error_of(fake.get("/api/chats/cs_5e0a77b19c3d/messages"), 404, "not_found")
    fake.stage("2")
    listed = ok(fake, "/api/chats")
    assert len(listed) == len(graph_fixtures()["2"]["nodes"]) == 8
    assert {s["node_id"] for s in listed} == {n["id"] for n in graph_fixtures()["2"]["nodes"]}
    assert all(set(s) == SESSION_KEYS for s in listed)
    assert [s["id"] for s in ok(fake, "/api/chats", node_id="web.audit")] == ["cs_e1acceab39f9"]
    assert ok(fake, "/api/chats", node_id="web.audit", include="archived") == ok(fake, "/api/chats", node_id="web.audit")
    error_of(fake.get("/api/chats/cs_000000000000"), 404, "not_found")


def test_the_org_session_carries_the_phase_of_the_turn_that_runs(fake):
    assert ok(fake, "/api/chats/cs_org")["phase"] is None
    fake.emit("chat.turn", {"session_id": "cs_org", "turn": 1, "phase": "planning", "detail": "Planning"})
    assert ok(fake, "/api/chats/cs_org")["phase"] == "planning"
    fake.emit("chat.turn", {"session_id": "cs_org", "turn": 1, "phase": "done", "detail": ""})
    assert ok(fake, "/api/chats/cs_org")["phase"] is None
    fake.emit("chat.turn", {"session_id": "cs_org", "turn": 2, "phase": "applying", "detail": ""})
    fake.emit("chat.turn", {"session_id": "cs_org", "turn": 2, "phase": "error", "detail": "boom"})
    assert ok(fake, "/api/chats/cs_org")["phase"] is None
    fake.stage("2")
    assert "phase" not in ok(fake, "/api/chats/cs_5e0a77b19c3d")  # only the org session has one


def test_messages_come_in_pages_after_a_cursor(fake):
    first = ok(fake, "/api/chats/cs_org/messages")
    assert [m["id"] for m in first["messages"]] == [1] and first["next_after"] == 1
    assert first["messages"][0]["text"].startswith("Hello.")
    fake.stage("full")
    everything = ok(fake, "/api/chats/cs_org/messages")
    assert [m["id"] for m in everything["messages"]] == list(range(1, 23)) and everything["next_after"] == 22
    page = ok(fake, "/api/chats/cs_org/messages", after=20)
    assert [m["id"] for m in page["messages"]] == [21, 22] and page["next_after"] == 22
    small = ok(fake, "/api/chats/cs_org/messages", after=3, limit=2)
    assert [m["id"] for m in small["messages"]] == [4, 5] and small["next_after"] == 5
    past = ok(fake, "/api/chats/cs_org/messages", after=99)
    assert past == {"messages": [], "next_after": 99}
    assert ok(fake, "/api/chats/cs_org/messages", after=-4)["messages"][0]["id"] == 1
    assert len(ok(fake, "/api/chats/cs_org/messages", limit=0)["messages"]) == 1
    assert all(set(m) == MESSAGE_KEYS for m in everything["messages"])
    session = ok(fake, "/api/chats/cs_org")
    assert session["last_message_id"] == 22 and set(session) - {"phase"} == SESSION_KEYS


def test_a_function_log_and_a_step_session_are_served_read_only(fake):
    fake.stage("2")
    log = ok(fake, "/api/chats/cs_77aa10c2e9b4/messages")["messages"]
    assert len(log) == 16 and not ok(fake, "/api/chats/cs_77aa10c2e9b4")["writable"]
    empty = ok(fake, "/api/chats/cs_e1acceab39f9")  # Audit has said nothing yet: an empty read-only session
    assert empty["writable"] is False and empty["last_message_id"] == 0 and empty["kind"] == "function"
    assert ok(fake, "/api/chats/cs_e1acceab39f9/messages") == {"messages": [], "next_after": 0}


def test_a_question_is_answered_by_the_owners_next_line(fake):
    fake.stage("2")
    question = ok(fake, "/api/chats/cs_5e0a77b19c3d/messages")["messages"][1]
    assert question["kind"] == "question" and question["answered_by"] is None
    fake.stage("3")
    messages = ok(fake, "/api/chats/cs_5e0a77b19c3d/messages")["messages"]
    assert messages[1]["answered_by"] == 3 and messages[2]["role"] == "user"


# ---- needs you, departments, atoms ---------------------------------------------------------------------------------------
def test_needs_you_and_departments_follow_the_stage(fake):
    assert ok(fake, "/api/needs-you") == [] and ok(fake, "/api/departments") == []
    fake.stage("2")
    assert ok(fake, "/api/needs-you") == load("needs-you.json")["2"]
    assert ok(fake, "/api/departments") == load("departments.json")["2"]
    fake.stage("3")
    assert ok(fake, "/api/needs-you") == [] and ok(fake, "/api/departments")[0]["node_status"] == "running"
    fake.stage("full")
    assert [d["id"] for d in ok(fake, "/api/departments")] == ["web", "content"]
    assert ok(fake, "/api/departments/content") == load("departments.json")["full"][1]
    error_of(fake.get("/api/departments/nosuch"), 404, "not_found")
    error_of(fake.get("/api/departments/root"), 404, "not_found")


def test_atoms_list_filters_orders_and_pages(fake):
    fake.stage("full")
    every = ok(fake, "/api/atoms")
    assert every and all(set(a) == ATOM_OUT_KEYS for a in every)
    assert [a["ts_open"] for a in every] == sorted((a["ts_open"] for a in every), reverse=True)  # newest first
    total = sum(n["meta"]["stats"]["atoms_total"] for n in graph_fixtures()["full"]["nodes"] if n["kind"] == "function")
    assert len(every) == total
    mine = ok(fake, "/api/atoms", node_id="web.identity")
    assert len(mine) == 5 and {a["node_id"] for a in mine} == {"web.identity"}
    assert Counter(a["state"] for a in mine) == Counter(ATOM_WORDS)
    assert {a["state"] for a in ok(fake, "/api/atoms", status="verify_failed")} == {"verify_failed"}  # status takes the display word
    assert {a["task_id"] for a in ok(fake, "/api/atoms", task_id="tsk_b7c8d9e0f1a2")} <= {"tsk_b7c8d9e0f1a2"}
    assert [a["id"] for a in ok(fake, "/api/atoms", node_id="web.identity", limit=2, offset=1)] == [a["id"] for a in mine[1:3]]
    assert ok(fake, "/api/atoms", node_id="web.identity", offset=5) == [] and len(ok(fake, "/api/atoms", limit=1)) == 1
    assert len(ok(fake, "/api/atoms", limit=0)) == 1 and len(ok(fake, "/api/atoms", limit=-3)) == 1  # the smallest page is one row
    assert [a["id"] for a in ok(fake, "/api/atoms", node_id="web.identity", offset=-2)] == [a["id"] for a in mine]  # a negative offset is the start
    assert ok(fake, "/api/atoms", node_id="nobody") == []


def atom_time(seconds: int) -> str:
    return f"2026-11-04T10:{seconds // 60 % 60:02d}:{seconds % 60:02d}Z"


def test_the_atoms_made_for_a_function_from_its_counts_follow_the_lifecycle_rules(fake):
    from sutra_app.library.types import atom_sid, function_atom_id

    fake.stage("full")
    functions = load("functions.json")
    sid = atom_sid("j2-20261104-100004-7f3a", "web.adaptation")  # the Web team's run
    atoms = ok(fake, "/api/graph/nodes/web.adaptation")["atoms"]  # counts: two closed, one open
    assert [a["state"] for a in atoms] == ["open", "closed", "closed"]  # the open atom first, then the newest first
    assert [a["id"] for a in atoms] == [function_atom_id(sid, n) for n in (3, 2, 1)]
    template = functions["atom_templates"]["adaptation"]
    for atom in atoms:
        number = int(atom["id"].rsplit("-", 1)[1])
        body = atom["body"]
        assert atom["schema"] == "work-atom/0.3" and atom["node_id"] == "web.adaptation" and atom["task_id"] == "tsk_a1b2c3d4e5f6"
        assert atom["goal"] == template["goal"] and body["model"] == template["model"] and body["outputs"] == template["outputs"]
        assert body["work"] == {"dispatch_kind": "llm", "agent": "adaptation", "steps": template["steps"], "how_kind": "AI"}
        assert [c["text"] for c in body["constraints"]] == functions["meta"]["adaptation"]["constraints"][:2] and body["touches"] == []
        assert body["context"] == functions["meta"]["adaptation"]["context"][:2]
        assert [(c["template"], c["args"]) for c in body["verify"]["checks"]] == [(c["template"], c["args"]) for c in template["checks"]]
        assert all(c["text"] == functions["check_text"][c["template"]] and c["relevance_source"] == "declared" for c in body["verify"]["checks"])
        assert atom["ts_open"] == atom_time(10 * number)
        if atom["state"] == "closed":
            assert atom["attempt"] == 1 and body["closed_by"] == "verify" and atom["ts_closed"] == atom_time(10 * number + 7)
            assert all(c["results"] == [{"attempt": 1, "exit_code": 0, "evidence": "ok"}] for c in body["verify"]["checks"])
        else:
            assert atom["attempt"] == 0 and atom["ts_closed"] is None and "closed_by" not in body  # nothing tried yet
            assert all(c["results"] == [] for c in body["verify"]["checks"])
        calls = 2 + number
        assert atom["usage"] == {"calls": calls, "usd": round(calls * 0.03, 2), "tokens_in": calls * 600, "tokens_out": calls * 180}


def test_an_atom_that_failed_its_checks_has_two_tries_the_last_check_failing_and_says_so(fake):
    fake.stage("full")
    functions = load("functions.json")
    (atom,) = ok(fake, "/api/graph/nodes/web.audit")["atoms"]  # counts: one failed
    checks = atom["body"]["verify"]["checks"]
    assert atom["state"] == "verify_failed" and atom["attempt"] == 2 and atom["ts_closed"] == atom_time(17)
    assert all(len(c["results"]) == 2 for c in checks)
    assert all(r == {"attempt": n, "exit_code": 0, "evidence": "ok"} for c in checks[:-1] for n, r in enumerate(c["results"], 1))
    assert checks[-1]["results"] == [{"attempt": 1, "exit_code": 0, "evidence": "ok"},
                                     {"attempt": 2, "exit_code": 1, "evidence": functions["check_text"][checks[-1]["template"]] + ": not met"}]
    body = atom["body"]
    assert (body["closed_by"], body["abandon_code"]) == ("manual-override", "verify_failed")
    assert body["reason"] == "verify failed: " + functions["check_text"][checks[-1]["template"]]
    assert atom["usage"]["calls"] == 3 and atom["usage"]["usd"] == 0.09


def test_every_atom_of_the_story_is_well_formed_and_has_an_id_of_its_own(fake):
    fake.stage("full")
    atoms = ok(fake, "/api/atoms", limit=500)
    assert len({a["id"] for a in atoms}) == len(atoms) > 10
    for atom in atoms:
        assert RE_ATOM.fullmatch(atom["id"]) and atom["state"] in ATOM_WORDS and atom["ts_open"] <= (atom["ts_closed"] or atom["ts_open"])
        assert (atom["ts_closed"] is None) == (atom["state"] == "open") or atom["state"] == "refused"
        usage = atom["usage"]
        assert set(usage) == USAGE_KEYS and (usage["usd"] is None) == (usage["calls"] == 0) == (usage["tokens_in"] is None)


def test_one_atom_by_its_id_and_a_missing_one(fake):
    fake.stage("full")
    atom = ok(fake, "/api/atoms")[0]
    assert ok(fake, f"/api/atoms/{atom['id']}") == atom
    error_of(fake.get("/api/atoms/a-0000000000-99"), 404, "not_found")


def test_the_atom_log_is_in_seq_order_and_empty_until_identity_exists(fake):
    assert ok(fake, "/api/atoms/log") == []
    fake.stage("2")
    rows = ok(fake, "/api/atoms/log")
    assert rows == load("atom-log.json") and [r["seq"] for r in rows] == [1, 2, 3, 4]
    assert [r["seq"] for r in ok(fake, "/api/atoms/log", after=2)] == [3, 4]
    assert [r["seq"] for r in ok(fake, "/api/atoms/log", limit=1)] == [1]
    assert ok(fake, "/api/atoms/log", node_id="web.audit") == []
    assert len(ok(fake, "/api/atoms/log", node_id="web.identity")) == 4


# ---- health, engine settings, connectors ----------------------------------------------------------------------------------
def test_health_is_the_two_connector_rows(fake):
    assert ok(fake, "/api/health") == load("health.json")


def test_engine_settings_get_has_the_documented_shape_for_all_teams_and_for_one(fake):
    fake.stage("2")
    es = load("engine-settings.json")
    everyone = ok(fake, "/api/engine/settings")
    assert set(everyone) == {"schema", "defaults", "global", "effective", "effective_flags", "editable", "locked", "output_types"}  # no `department` without dept; sync 6 (D178): effective_flags
    assert everyone["defaults"] == es["defaults"] and everyone["global"] == es["global"]
    assert everyone["effective"] == {**es["defaults"], **es["global"]} and everyone["editable"] == es["editable"]
    one = ok(fake, "/api/engine/settings", dept="web")
    assert set(one) == {"schema", "defaults", "global", "department", "effective", "effective_flags", "editable", "locked", "output_types", "next_run"}   # sync 4 (D139): what the next run would use
    assert one["department"] == es["department"] and one["effective"] == es["effective"]
    assert one["next_run"] == {"output": es["effective"]["output"]} == {"output": "auto"}     # nothing chosen on the start page: the team's own setting
    error_of(fake.get("/api/engine/settings", dept="nosuch"), 404, "not_found")
    error_of(fake.get("/api/engine/settings", dept="Not A Team"), 404, "not_found")


def test_engine_settings_put_sets_unsets_and_answers_like_the_get(fake):
    fake.stage("2")
    status, answer = fake.request("PUT", "/api/engine/settings", {"set": {"budget": 150, "slim": True}, "unset": ["max_cycles"]}, token=True)
    assert status == 200 and answer["global"] == {"budget": 150, "slim": True}
    assert answer == ok(fake, "/api/engine/settings")
    assert answer["effective"]["budget"] == 150 and answer["effective"]["slim"] is True
    status, one = fake.request("PUT", "/api/engine/settings?dept=web", {"set": {"max_cycles": 9}, "unset": ["max_cycles"]}, token=True)
    assert status == 200 and one["department"] == {}  # unset applies after set, within one layer
    status, one = fake.request("PUT", "/api/engine/settings?dept=web", {"set": {"max_cycles": 9}}, token=True)
    assert one["department"] == {"max_cycles": 9} and one["effective"]["max_cycles"] == 9 and one["global"]["budget"] == 150
    assert ok(fake, "/api/engine/settings")["effective"]["max_cycles"] == 6  # the team's layer does not leak into all teams
    status, back = fake.request("PUT", "/api/engine/settings?dept=web", {"unset": ["max_cycles"]}, token=True)
    assert back["department"] == {} and back["effective"]["max_cycles"] == 6
    status, null_cap = fake.request("PUT", "/api/engine/settings", {"set": {"budget_cap": None}}, token=True)
    assert status == 200 and null_cap["global"]["budget_cap"] is None
    fake.reset()  # the layers are reset with the rest
    assert ok(fake, "/api/engine/settings")["global"] == load("engine-settings.json")["global"]


@pytest.mark.parametrize("field,value,fragment", [
    ("nope", 1, "is not a setting"),
    ("send_mode", "live", "only be changed by hand"),
    ("chrome", "/x", "only be changed by hand"),
    ("output", "poster", "unknown output type poster"),
    ("output", "Poster", "must be auto or a type name"),
    ("fixes", 2, "must be one of 0, 1"),
    ("fixes", True, "must be one of 0, 1"),
    ("rates", "yes", "must be true or false"),
    ("rates", 1, "must be true or false"),
    ("budget", 0, "at least 1"),
    ("budget", "5", "whole number"),
    ("budget", True, "whole number"),
    ("budget", 1.5, "whole number"),
    ("budget_cap", 0, "at least 1"),
    ("max_turns", -1, "at least 1"),
    ("chat_full_chars", 999, "at least 1000"),
    ("limit_add", -1, "at least 0"),
    ("bargain_minutes", -0.5, "number of at least 0"),
    ("bargain_minutes", "soon", "number of at least 0"),
    ("bargain_minutes", True, "number of at least 0"),
    ("max_cycles", 0, "at least 1"),
    ("bargain_calls", -1, "at least 0"),
    ("tap_min", -5, "at least 0"),
    ("delay", -1, "number of at least 0"),
])
def test_engine_settings_put_refuses_a_bad_field_and_names_it(fake, field, value, fragment):
    status, answer = fake.request("PUT", "/api/engine/settings", {"set": {field: value}}, token=True)
    error = error_of((status, answer), 422, "validation")
    (violation,) = error["details"]["violations"]
    assert violation["path"] == f"set.{field}" and fragment in violation["message"]
    assert error["message"] == f"Not saved: {violation['message']}"
    assert ok(fake, "/api/engine/settings")["global"] == load("engine-settings.json")["global"]  # nothing was saved


def test_engine_settings_put_accepts_the_edge_values(fake):
    body = {"set": {"output": "lld", "fixes": 1, "budget": 1, "budget_cap": 7, "bargain_minutes": 0, "delay": 2, "limit_add": 0,
                    "chat_full_chars": 1000, "max_turns": 1, "rates": False}}
    status, answer = fake.request("PUT", "/api/engine/settings", body, token=True)
    assert status == 200 and answer["global"]["output"] == "lld" and answer["global"]["chat_full_chars"] == 1000


def test_engine_settings_put_checks_the_shape_of_the_body(fake):
    def put(body, query=""):
        return fake.request("PUT", "/api/engine/settings" + query, body, token=True)

    error_of(put({"set": {}, "extra": 1}), 422, "validation")
    error_of(put([1]), 422, "validation")
    assert error_of(put({"set": [1]}), 422, "validation")["details"]["violations"] == [
        {"path": "set", "code": "bad_type", "message": "set must be an object"}]
    assert error_of(put({"unset": "budget"}), 422, "validation")["details"]["violations"][0]["path"] == "unset"
    assert error_of(put({"unset": [3]}), 422, "validation")["details"]["violations"][0]["path"] == "unset"
    violations = error_of(put({"unset": ["nope", "send_mode"]}), 422, "validation")["details"]["violations"]
    assert [(v["path"], v["code"]) for v in violations] == [("unset.nope", "unknown_field"), ("unset.send_mode", "locked_field")]
    both = error_of(put({"set": {"budget": 0, "send_mode": "live"}, "unset": ["nope"]}), 422, "validation")["details"]["violations"]
    assert [v["path"] for v in both] == ["set.budget", "set.send_mode", "unset.nope"]  # every problem at once
    error_of(put(None), 422, "validation")  # no body at all is not JSON


def test_an_empty_object_put_changes_nothing(fake):
    status, answer = fake.request("PUT", "/api/engine/settings", {}, token=True)
    assert status == 200 and answer["global"] == load("engine-settings.json")["global"]


def test_engine_settings_put_on_an_unknown_team_is_404_and_needs_the_token(fake):
    fake.stage("2")
    error_of(fake.request("PUT", "/api/engine/settings?dept=nosuch", {"set": {}}, token=True), 404, "not_found")
    error_of(fake.request("PUT", "/api/engine/settings", {"set": {"budget": 5}}), 401, "bad_token")
    assert ok(fake, "/api/engine/settings")["global"]["budget"] == 120


def test_the_connector_test_answers_per_provider_and_codex_needs_a_sign_in_first(fake):
    connectors = load("connectors.json")
    assert fake.post("/api/connectors/claude/test") == (200, connectors["test"]["claude"])
    error = error_of(fake.post("/api/connectors/codex/test"), 503, "provider_unavailable")
    assert error == connectors["test_error"]["error"] and error["details"] == {"kind": "auth"}
    error_of(fake.post("/api/connectors/gemini/test"), 404, "not_found")
    error_of(fake.post("/api/connectors/claude/test", token=False), 401, "bad_token")


def test_the_cli_path_route_keeps_the_real_routes_rules_in_small(fake):
    """GAP-providers: PUT /api/connectors/{provider}/path, token first, claude or codex only, a full path named as the command."""
    error_of(fake.request("PUT", "/api/connectors/claude/path", {"path": "/x/claude"}), 401, "bad_token")
    error_of(fake.request("PUT", "/api/connectors/gemini/path", {"path": "/x/gemini"}, token=True), 404, "not_found")
    assert "Choose the file named codex" in error_of(fake.request("PUT", "/api/connectors/codex/path", {"path": "/bin/sh"}, token=True), 422, "invalid_request")["message"]
    error_of(fake.request("PUT", "/api/connectors/codex/path", {"path": 3}, token=True), 422, "validation")
    status, body = fake.request("PUT", "/api/connectors/codex/path", {"path": "/opt/tools/codex"}, token=True)
    assert status == 200 and body["path"] == "/opt/tools/codex" and body["installed"] is True
    status, body = fake.request("PUT", "/api/connectors/codex/path", {"path": None}, token=True)
    assert status == 200 and body["path"] is None


def test_codex_sign_in_walks_through_the_sequence_and_signs_the_connector_in(fake):
    start = fake.post("/api/connectors/codex/sign-in")
    assert start == (200, load("connectors.json")["sign_in"]["start"])
    sid = start[1]["id"]
    polls = [fake.get(f"/api/connectors/codex/sign-in/{sid}") for _ in range(5)]
    assert [p[1]["state"] for p in polls] == ["pending", "pending", "signed_in", "signed_in", "signed_in"]  # the last state repeats
    assert all(p[0] == 200 and set(p[1]) == {"state"} for p in polls)
    codex = ok(fake, "/api/health")["connectors"]["codex"]
    assert codex["signed_in"] is True and codex["method"] == "ChatGPT" and codex["billing"] == "subscription"
    assert codex["health"] == {"state": "ok", "until": None, "reason": None}
    assert fake.post("/api/connectors/codex/test") == (200, load("connectors.json")["test"]["codex"])  # Test works once signed in
    assert fake.state()["codex_signed_in"] is True


def test_signing_in_publishes_connector_health_once(fake_server, fake):
    with Stream(fake_server.url, "/api/events?topics=connector") as stream:
        stream.next()  # hello
        sid = fake.post("/api/connectors/codex/sign-in")[1]["id"]
        for _ in range(4):
            fake.get(f"/api/connectors/codex/sign-in/{sid}")
        frames = stream.take(1)
        assert frames[0]["event"] == "connector.health" and frames[0]["data"] == {"provider": "codex", "state": "ok", "until": None, "reason": None}
        assert stream.quiet()  # the later polls say signed_in again: no second event


@pytest.mark.parametrize("sequence,expected", [("failed", ["pending", "failed", "failed"]), ("expired", ["pending", "expired", "expired"])])
def test_the_other_sign_in_endings_leave_codex_signed_out(fake, sequence, expected):
    fake.fixture("sign_in", sequence)
    sid = fake.post("/api/connectors/codex/sign-in")[1]["id"]
    assert [fake.get(f"/api/connectors/codex/sign-in/{sid}")[1]["state"] for _ in range(3)] == expected
    assert ok(fake, "/api/health")["connectors"]["codex"]["signed_in"] is False


def test_a_sign_in_can_be_cancelled_and_then_is_gone(fake):
    sid = fake.post("/api/connectors/codex/sign-in")[1]["id"]
    status, body = fake.request("DELETE", f"/api/connectors/codex/sign-in/{sid}", token=True)
    assert (status, body) == (204, None)
    error_of(fake.get(f"/api/connectors/codex/sign-in/{sid}"), 404, "not_found")
    error_of(fake.request("DELETE", f"/api/connectors/codex/sign-in/{sid}", token=True), 404, "not_found")
    error_of(fake.get("/api/connectors/codex/sign-in/si_unknown"), 404, "not_found")
    sid = fake.post("/api/connectors/codex/sign-in")[1]["id"]
    error_of(fake.request("DELETE", f"/api/connectors/codex/sign-in/{sid}"), 401, "bad_token")
    error_of(fake.post("/api/connectors/codex/sign-in", token=False), 401, "bad_token")


def test_every_404_says_what_is_missing_in_the_words_the_page_shows(fake):
    fake.stage("2")
    cases = [
        ("/api/graph?dept=nosuch", "No team 'nosuch' in the graph."), ("/api/graph/nodes/nobody.identity", "No node 'nobody.identity'."),
        ("/api/chats/cs_000000000000", "This chat is gone."), ("/api/chats/cs_000000000000/messages", "This chat is gone."),
        ("/api/departments/nosuch", "No team 'nosuch'."), ("/api/atoms/a-0000000000-99", "No atom 'a-0000000000-99'."),
        ("/api/engine/settings?dept=nosuch", "No team 'nosuch'."), ("/api/connectors/codex/sign-in/si_nope", "No such sign-in."),
        ("/__fake/mount/nothing.html", "No mount page 'nothing'."), ("/__fake/mount/graph", "A mount page is /__fake/mount/<name>.html"),
    ]
    for path, message in cases:
        assert error_of(fake.get(path), 404, "not_found")["message"] == message, path
    assert error_of(fake.post("/api/connectors/gemini/test"), 404, "not_found")["message"] == "No connector 'gemini'."
    assert error_of(fake.request("DELETE", "/api/connectors/codex/sign-in/si_nope", token=True), 404, "not_found")["message"] == "No such sign-in."


# ---- the write guard, the Host check -----------------------------------------------------------------------------------------
WRITES = [  # every non-GET route that is not a test control: (method, a concrete path, a body, the route as registered)
    ("POST", "/api/ops/welcome/seen", {}, "/api/ops/welcome/seen"),
    ("PUT", "/api/connectors/policy", {}, "/api/connectors/policy"),
    ("POST", "/api/ops/update-check", {}, "/api/ops/update-check"),
    ("POST", "/api/ops/update-plan", {}, "/api/ops/update-plan"),
    ("PUT", "/api/ops/update-setting", {"auto": False}, "/api/ops/update-setting"),
    ("POST", "/api/ops/update-status", {"state": "ready"}, "/api/ops/update-status"),
    ("PUT", "/api/chats/cs_org/choice", {"provider": None}, "/api/chats/{sid}/choice"),
    ("POST", "/api/chats/cs_org/messages", {"text": "x"}, "/api/chats/{sid}/messages"),
    ("POST", "/api/chats/cs_org/steer", {"text": "x"}, "/api/chats/{sid}/steer"),
    ("PUT", "/api/tasks/tsk_000000000001/choice", {"provider": None}, "/api/tasks/{task_id}/choice"),
    ("POST", "/api/chats/cs_org/retry", {}, "/api/chats/cs_org/retry"),
    ("POST", "/api/tasks/tsk_000000000001/retry", {}, "/api/tasks/{task_id}/retry"),
    ("PUT", "/api/limits", {"guard_enabled": True}, "/api/limits"),
    ("POST", "/api/limits/continue", {}, "/api/limits/continue"),
    ("PUT", "/api/ops/attention", {"nudges_per_hour": 1}, "/api/ops/attention"),
    ("POST", "/api/recurring", {"dept_id": "web", "text": "x", "schedule": {"every": "day"}}, "/api/recurring"),
    ("PUT", "/api/recurring/rec_000000000001", {"enabled": False}, "/api/recurring/{rec_id}"),
    ("DELETE", "/api/recurring/rec_000000000001", None, "/api/recurring/{rec_id}"),
    ("POST", "/api/recurring/rec_000000000001/run", {}, "/api/recurring/{rec_id}/run"),
    ("PUT", "/api/engine/settings", {"set": {}}, "/api/engine/settings"),
    ("POST", "/api/connectors/claude/test", {}, "/api/connectors/{provider}/test"),
    ("PUT", "/api/connectors/claude/path", {"path": None}, "/api/connectors/{provider}/path"),
    ("PUT", "/api/connectors/workdir", {"path": "/work/proj"}, "/api/connectors/workdir"),
    ("DELETE", "/api/connectors/workdir", None, "/api/connectors/workdir"),
    ("POST", "/api/connectors/codex/sign-in", {}, "/api/connectors/codex/sign-in"),
    ("DELETE", "/api/connectors/codex/sign-in/si_x", None, "/api/connectors/codex/sign-in/{sign_in_id}"),
    ("POST", "/api/say?dept=web", {"text": "x"}, "/api/say"),
    ("POST", "/api/output?dept=web", {"type": "website"}, "/api/output"),
    ("POST", "/api/reset?dept=web", {}, "/api/reset"),
    ("POST", "/api/ask?dept=web", {"who": "adaptation", "q": "Why?"}, "/api/ask"),
    ("POST", "/api/settings?dept=web", {"decide_for_me": True}, "/api/settings"),
    ("POST", "/api/playbooks/clear?dept=web", {}, "/api/playbooks/clear"),
    ("POST", "/api/lessons/clear?dept=web", {}, "/api/lessons/clear"),
]


def write_request(fake_server, method, path, body, headers):
    data = None if body is None else json.dumps(body).encode()
    return raw_request(fake_server.url, method, path, headers={"Content-Type": "application/json", **headers}, body=data)


def test_every_write_route_of_the_fake_is_in_the_list_above_and_every_one_wants_the_token(fake_server, fake):
    registered = {(method, ctx.path) for ctx in iter_route_contexts(fake_server.app.routes) for method in (ctx.methods or ())
                  if method not in ("GET", "HEAD", "OPTIONS") and not ctx.path.startswith("/__fake/")}
    assert registered == {(method, route) for method, _, _, route in WRITES}  # a new write route must be listed (and guarded)
    for method, path, body, _ in WRITES:
        status, _, raw = write_request(fake_server, method, path, body, {})
        assert status == 401, (method, path)
        assert json.loads(raw)["error"]["code"] == "bad_token"


def test_the_automatic_update_setting_is_stateful_in_the_fake_and_strict_like_the_real_route(fake):
    status, body = fake.get("/api/ops/update-setting")
    assert status == 200 and body["auto"] is True and body["chosen"] is False and body["last"] is None
    for bad in ({"auto": "no"}, {"auto": 0}, {}, {"auto": True, "x": 1}):
        assert fake.request("PUT", "/api/ops/update-setting", bad, token=True)[0] == 422, bad
    status, body = fake.request("PUT", "/api/ops/update-setting", {"auto": False}, token=True)
    assert status == 200 and body["auto"] is False and body["chosen"] is True
    assert fake.get("/api/ops/update-setting")[1]["auto"] is False
    assert error_of(fake.post("/api/ops/update-plan", {"auto": True}), 409, "update_off")                      # off: refused, as the real route does
    assert fake.post("/api/ops/update-plan", {})[0] == 200
    assert fake.post("/api/ops/update-status", {"state": "ready", "version": "0.2.0", "message": "ready"})[1]["last"]["state"] == "ready"
    assert fake.post("/api/ops/update-status", {"state": "weird"})[0] == 422
    fake.post("/__fake/reset", token=False)
    assert fake.get("/api/ops/update-setting")[1]["chosen"] is False                                              # reset with the story


def test_a_wrong_token_is_refused_and_the_right_one_is_not(fake_server, fake):
    status, _, raw = write_request(fake_server, "POST", "/api/chats/cs_org/retry", {}, {"X-Sutra-Token": "nope"})
    # the real server's words (orchestrator/api/deps.py): the page, not the server, turns them into "Reload it from the app" (sutra_ctx.js failure())
    assert status == 401 and json.loads(raw)["error"]["message"] == "A valid X-Sutra-Token header is required for this request"
    status, _, raw = write_request(fake_server, "POST", "/api/chats/cs_org/retry", {}, {"X-Sutra-Token": fb.TOKEN})
    assert status == 202
    status, _, raw = write_request(fake_server, "POST", "/api/chats/cs_org/retry", {}, {"X-Sutra-Token": fb.TOKEN + "x"})
    assert status == 401  # not a prefix match


def test_a_present_origin_must_be_http_plus_the_host_value(fake_server, fake):
    host = urllib.parse.urlsplit(fake_server.url).netloc
    token = {"X-Sutra-Token": fb.TOKEN}
    ok_status, _, _ = write_request(fake_server, "POST", "/api/chats/cs_org/retry", {}, {**token, "Origin": f"http://{host}"})
    assert ok_status == 202
    for origin in ("null", "http://evil.example", f"http://localhost:{host.split(':')[1]}", f"https://{host}", f"http://{host}/"):
        status, _, raw = write_request(fake_server, "POST", "/api/chats/cs_org/retry", {}, {**token, "Origin": origin})
        assert status == 403 and json.loads(raw)["error"]["code"] == "bad_origin", origin
    # the Origin is judged before the token, and an absent Origin is fine
    status, _, raw = write_request(fake_server, "POST", "/api/chats/cs_org/retry", {}, {"Origin": "null"})
    assert status == 403
    assert write_request(fake_server, "POST", "/api/chats/cs_org/retry", {}, token)[0] == 202


def test_only_loopback_host_names_are_answered(fake_server, fake):
    port = urllib.parse.urlsplit(fake_server.url).port
    assert raw_request(fake_server.url, "GET", "/api/health", headers={"Host": f"localhost:{port}"})[0] == 200
    assert raw_request(fake_server.url, "GET", "/api/health", headers={"Host": f"127.0.0.1:{port}"})[0] == 200
    for host in ("evil.example", f"evil.example:{port}", "10.0.0.2", "testserver"):
        status, _, raw = raw_request(fake_server.url, "GET", "/api/health", headers={"Host": host})
        assert status == 400 and json.loads(raw)["error"]["code"] == "bad_host", host
    status, _, raw = raw_request(fake_server.url, "GET", "/__fake/state", headers={"Host": "evil.example"})
    assert status == 400  # the controls are behind the same check


def test_reads_need_no_token_and_carry_no_cookie(fake_server, fake):
    for path in ("/api/chart", "/api/graph", "/api/health", "/api/engine/settings", "/api/chats/cs_org"):
        status, headers, _ = raw_request(fake_server.url, "GET", path)
        assert status == 200 and "set-cookie" not in headers


# ---- the event stream ---------------------------------------------------------------------------------------------------
def test_the_stream_opens_with_hello_which_has_no_id(fake_server, fake):
    with Stream(fake_server.url) as stream:
        assert stream.status == 200 and stream.headers["content-type"].startswith("text/event-stream")
        assert stream.headers["cache-control"] == "no-store"
        hello = stream.next()
        assert hello == {"event": "server.hello", "data": {"version": "0.1.0", "chart_version": 1, "graph_version": 3}}
    fake.stage("full")
    with Stream(fake_server.url) as stream:
        assert stream.next()["data"] == {"version": "0.1.0", "chart_version": 4, "graph_version": 88}


def test_events_get_ids_from_one_and_reach_every_open_stream(fake_server, fake):
    with Stream(fake_server.url) as one, Stream(fake_server.url) as two:
        one.next(), two.next()
        fake.wait_subscribers(2)
        fake.emit("chat.turn", {"session_id": "cs_org", "turn": 1, "phase": "planning", "detail": "x"})
        fake.emit("needs_you.changed", {"count": 3})
        for stream in (one, two):
            frames = stream.take(2)
            assert [(f["id"], f["event"]) for f in frames] == [(1, "chat.turn"), (2, "needs_you.changed")]
            assert frames[1]["data"] == {"count": 3}
    assert fake.state()["last_event_id"] == 2


def test_once_replays_the_ring_and_closes(fake_server, fake):
    for count in (1, 2, 3):
        fake.emit("needs_you.changed", {"count": count})
    with Stream(fake_server.url, "/api/events?once=1") as stream:
        frames = [stream.next() for _ in range(4)]
        assert [f["event"] for f in frames] == ["server.hello", "needs_you.changed", "needs_you.changed", "needs_you.changed"]
        assert [f.get("id") for f in frames] == [None, 1, 2, 3]
        assert stream.next() is None  # closed by the server
    with Stream(fake_server.url, "/api/events?once=1&after=2") as stream:
        assert [f["id"] for f in stream.take(2)[1:]] == [3] and stream.next() is None


def test_replay_starts_after_the_given_id_from_the_query_or_from_last_event_id(fake_server, fake):
    for count in (1, 2, 3, 4):
        fake.emit("needs_you.changed", {"count": count})
    with Stream(fake_server.url, "/api/events?after=2") as stream:
        assert [f.get("id") for f in stream.take(3)] == [None, 3, 4]
    with Stream(fake_server.url, "/api/events", headers={"Last-Event-ID": "3"}) as stream:
        assert [f.get("id") for f in stream.take(2)] == [None, 4]
    with Stream(fake_server.url, "/api/events?after=0", headers={"Last-Event-ID": "3"}) as stream:  # the query wins
        assert [f.get("id") for f in stream.take(5)] == [None, 1, 2, 3, 4]
    with Stream(fake_server.url, "/api/events", headers={"Last-Event-ID": "x"}) as stream:  # not a number: no replay
        assert stream.next()["event"] == "server.hello" and stream.quiet()
    with Stream(fake_server.url) as stream:  # no cursor: no replay
        assert stream.next()["event"] == "server.hello" and stream.quiet()


def test_an_id_from_a_previous_launch_gets_a_restart_resync_and_then_the_live_tail(fake_server, fake):
    fake.emit("needs_you.changed", {"count": 1})
    with Stream(fake_server.url, "/api/events?after=99") as stream:
        frames = stream.take(2)
        assert [f["event"] for f in frames] == ["server.hello", "server.resync"]
        assert frames[1]["data"] == {"reason": "restart"} and "id" not in frames[1]
        fake.wait_subscribers(1)
        fake.emit("needs_you.changed", {"count": 2})
        assert stream.next()["id"] == 2


def test_a_cursor_at_the_head_of_the_ring_is_neither_a_replay_nor_a_resync(fake_server, fake):
    for count in (1, 2, 3):
        fake.emit("needs_you.changed", {"count": count})
    with Stream(fake_server.url, "/api/events?after=3") as stream:  # it has seen the last event
        assert stream.next()["event"] == "server.hello"
        fake.wait_subscribers(1)
        fake.emit("needs_you.changed", {"count": 4})
        assert [(f["event"], f["id"]) for f in stream.take(1)] == [("needs_you.changed", 4)]  # no replay and no resync came first


def test_an_id_older_than_the_ring_gets_a_gap_resync(fake_server, fake, monkeypatch):
    monkeypatch.setattr(fb, "RING_SIZE", 3)
    for count in range(1, 6):
        fake.emit("needs_you.changed", {"count": count})  # ids 1..5, the ring keeps 3, 4 and 5
    with Stream(fake_server.url, "/api/events?after=1") as stream:
        frames = stream.take(2)
        assert frames[1] == {"event": "server.resync", "data": {"reason": "gap"}} and stream.quiet()
    with Stream(fake_server.url, "/api/events?after=0") as stream:
        assert stream.take(2)[1]["data"] == {"reason": "gap"}
    with Stream(fake_server.url, "/api/events?after=2") as stream:  # it has seen 2: 3, 4 and 5 are all it misses
        assert [f.get("id") for f in stream.take(4)] == [None, 3, 4, 5]


def test_topics_filter_by_the_prefix_before_the_dot_and_control_events_always_pass(fake_server, fake):
    with Stream(fake_server.url, "/api/events?topics=chat,graph") as chat_graph, Stream(fake_server.url, "/api/events?topics=connector") as connector:
        assert chat_graph.next()["event"] == "server.hello" and connector.next()["event"] == "server.hello"
        fake.wait_subscribers(2)
        for event in ("chart.changed", "chat.turn", "needs_you.changed", "graph.updated", "connector.mode", "usage.recorded"):
            fake.emit(event)
        fake.emit("server.resync", {"reason": "gap"})
        assert [f["event"] for f in chat_graph.take(3)] == ["chat.turn", "graph.updated", "server.resync"]
        assert [f["event"] for f in connector.take(2)] == ["connector.mode", "server.resync"]
        assert chat_graph.quiet() and connector.quiet()
    fake.emit("chart.changed")
    with Stream(fake_server.url, "/api/events?once=1&topics=chat") as stream:  # the filter holds for the replay too
        events = []
        while (frame := stream.next()) is not None:
            events.append(frame["event"])
        assert events == ["server.hello", "chat.turn"]
    with Stream(fake_server.url, "/api/events?once=1&topics=") as stream:  # empty means every topic
        names = []
        while (frame := stream.next()) is not None:
            names.append(frame["event"])
        assert "chart.changed" in names and "connector.mode" in names


def test_an_idle_stream_sends_a_ping_comment(fake_server, fake, monkeypatch):
    monkeypatch.setattr(fb, "PING_SECONDS", 0.05)
    with Stream(fake_server.url) as stream:
        stream.next()
        assert stream.next() == {"comment": ": ping"}


def test_a_forced_failure_of_the_stream_ends_open_streams_and_answers_new_ones_with_the_status(fake_server, fake):
    with Stream(fake_server.url) as stream:
        stream.next()
        fake.wait_subscribers(1)
        fake.fail("/api/events", 500)
        assert stream.next() is None  # the open stream ended
    with Stream(fake_server.url) as failed:
        assert failed.status == 500
        assert json.loads(failed.response.read())["error"]["code"] == "internal"
    fake.fail("/api/events", None)
    with Stream(fake_server.url) as stream:
        assert stream.status == 200 and stream.next()["event"] == "server.hello"
    fake.fail("/api/events", 503, count=1)
    with Stream(fake_server.url) as first:
        assert first.status == 503
    with Stream(fake_server.url) as second:
        assert second.status == 200


def test_a_reset_tells_open_streams_to_resync_and_ids_start_again_even_for_a_stream_that_replayed(fake_server, fake):
    for count in (1, 2, 3):
        fake.emit("needs_you.changed", {"count": count})
    with Stream(fake_server.url, "/api/events?after=0") as stream:
        assert [f.get("id") for f in stream.take(4)] == [None, 1, 2, 3]
        fake.wait_subscribers(1)
        fake.reset()
        assert stream.next() == {"event": "server.resync", "data": {"reason": "restart"}}
        fake.emit("needs_you.changed", {"count": 9})
        assert stream.next() == {"event": "needs_you.changed", "id": 1, "data": {"count": 9}}  # id 1 again, and it is delivered


def test_a_chat_message_that_is_emitted_is_also_stored_because_the_page_refetches_the_session(fake):
    message = copy.deepcopy(load("events.script.json")["samples"]["chat.message"]["message"])
    message["id"], message["text"] = 7, "A note from the test"
    fake.emit("chat.message", {"session_id": "cs_org", "message": message})
    fake.emit("chat.message", {"session_id": "cs_org", "message": message})  # the same id twice is stored once
    stored = ok(fake, "/api/chats/cs_org/messages", after=1)["messages"]
    assert [(m["id"], m["text"]) for m in stored] == [(7, "A note from the test")]
    elsewhere = {**message, "session_id": "cs_000000000000"}  # the message names its own session
    error_of(fake.request("POST", "/__fake/emit", {"event": "chat.message", "data": {"session_id": elsewhere["session_id"], "message": elsewhere}}),
             404, "not_found")
    error_of(fake.request("POST", "/__fake/emit", {"event": "chat.message", "data": {"nothing": 1}}), 422, "validation")
    error_of(fake.request("POST", "/__fake/emit", {"event": "chat.message", "data": ["x"]}), 422, "validation")


# ---- the test-only controls ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("event", EVENTS)
def test_emit_sends_the_sample_of_the_script_for_every_event_name(fake_server, fake, event):
    sample = load("events.script.json")["samples"][event]
    with Stream(fake_server.url) as stream:
        stream.next()
        fake.wait_subscribers(1)
        answer = fake.emit(event)
        frame = stream.next()
    assert answer == {"id": None if event.startswith("server.") else 1, "event": event}
    assert frame["event"] == event and frame["data"] == sample
    assert ("id" in frame) == (not event.startswith("server."))


def test_emit_takes_its_own_data_and_refuses_an_unknown_event(fake_server, fake):
    with Stream(fake_server.url) as stream:
        stream.next()
        fake.wait_subscribers(1)
        fake.emit("needs_you.changed", {"count": 41})
        assert stream.next()["data"] == {"count": 41}
    error = error_of(fake.request("POST", "/__fake/emit", {"event": "chat.typing"}), 422, "validation")
    assert "chat.typing" in error["message"] and "graph.updated" in error["message"]
    error_of(fake.request("POST", "/__fake/emit", {}), 422, "validation")
    error_of(fake.request("POST", "/__fake/emit", [1]), 422, "validation")
    error_of(fake.request("POST", "/__fake/emit", {"event": 5}), 422, "validation")
    status, _, raw = raw_request(fake_server.url, "POST", "/__fake/emit", headers={"Content-Type": "application/json"}, body=b"{nope")
    assert status == 422 and json.loads(raw)["error"]["details"]["violations"][0]["code"] == "json_invalid"


def test_controls_need_no_token(fake_server):
    status, _, _ = raw_request(fake_server.url, "POST", "/__fake/reset", headers={"Content-Type": "application/json"}, body=b"{}")
    assert status == 200


def test_fixture_switches_the_chart_the_graph_or_the_whole_story(fake):
    assert fake.fixture("chart", "3") == {"chart": "3", "graph": "1", "sign_in": "success"}
    assert ok(fake, "/api/chart") == chart_fixtures()["3"] and ok(fake, "/api/chart/changes") == change_fixtures()["3"]
    assert ok(fake, "/api/graph", level="full") == graph_fixtures()["1"]
    assert fake.fixture("graph", "full") == {"chart": "3", "graph": "full", "sign_in": "success"}
    assert ok(fake, "/api/graph", level="full") == graph_fixtures()["full"]
    assert ok(fake, "/api/chats/cs_org/messages")["next_after"] == 22  # the chats follow the graph version
    assert fake.stage("1") == {"chart": "1", "graph": "1", "sign_in": "success"}
    assert fake.stage("3") == {"chart": "2", "graph": "3", "sign_in": "success"}
    assert fake.fixture("graph", 2)["graph"] == "2"  # a number is as good as its text
    assert fake.fixture("sign_in", "failed")["sign_in"] == "failed"
    assert fake.state()["graph"] == "2" and fake.state()["sign_in"] == "failed"


@pytest.mark.parametrize("name,version,message", [
    ("chart", "9", "no chart version '9'; have 1, 2, 3"), ("graph", "9", "no graph version '9'; have 1, 2, 3, full"),
    ("stage", "9", "stage must be one of 1, 2, 3, full, not '9'"), ("sign_in", "never", "no sign-in sequence 'never'"),
    ("health", "1", "unknown fixture name 'health': chart, graph, stage or sign_in"),
])
def test_fixture_refuses_an_unknown_name_or_version(fake, name, version, message):
    error = error_of(fake.request("POST", "/__fake/fixture", {"name": name, "version": version}), 422, "validation")
    assert error["message"] == message
    assert fake.state()["graph"] == "1"  # nothing changed


def test_fixture_needs_a_name_and_a_version(fake):
    error_of(fake.request("POST", "/__fake/fixture", {"name": "graph"}), 422, "validation")
    error_of(fake.request("POST", "/__fake/fixture", {"version": "2"}), 422, "validation")
    error_of(fake.request("POST", "/__fake/fixture", ["graph"]), 422, "validation")


def test_fail_forces_a_status_with_the_envelope_and_clears_it(fake):
    answer = fake.fail("/api/graph", 500)
    assert answer["failures"] == [{"path": "/api/graph", "method": None, "status": 500, "code": "internal",
                                   "message": "Something went wrong on the server.", "details": {}, "count": None}]
    error = error_of(fake.get("/api/graph"), 500, "internal")
    assert error["message"] == "Something went wrong on the server."
    assert fake.get("/api/chart")[0] == 200  # only that path
    assert fake.fail("/api/graph", None)["failures"] == []
    assert fake.get("/api/graph")[0] == 200
    fake.fail("/api/graph", 404)
    assert fake.fail("/api/graph", 200)["failures"] == []  # 200 clears too


def test_fail_can_name_a_code_a_message_details_a_method_and_a_count(fake):
    fake.fail("/api/chats/cs_org/messages", 503, method="post", code="cli_missing", message="Claude is not installed.", details={"kind": "missing"})
    assert fake.get("/api/chats/cs_org/messages")[0] == 200  # a GET is not a POST
    error = error_of(fake.post("/api/chats/cs_org/messages", {"text": "hi"}), 503, "cli_missing")
    assert error["message"] == "Claude is not installed." and error["details"] == {"kind": "missing"}
    fake.fail("/api/needs-you", 429, count=2)
    assert [fake.get("/api/needs-you")[0] for _ in range(4)] == [429, 429, 200, 200]  # it expires after two answers
    assert fake.state()["failures"][0]["path"] == "/api/chats/cs_org/messages"
    fake.fail("/api/health", 409)
    assert error_of(fake.get("/api/health"), 409, "busy")["message"].startswith("The team is working")
    fake.fail("/api/health", 418)
    assert error_of(fake.get("/api/health"), 418, "internal")["message"] == "Forced failure."


def test_a_forced_failure_on_a_j2_route_has_j2s_body_and_one_on_a_page_the_envelope(fake):
    fake.stage("2")
    fake.fail("/api/state", 500)
    assert fake.get("/api/state", dept="web") == (500, {"error": "internal"})
    fake.fail("/api/state", 502, code="bad_gateway")
    assert fake.get("/api/state", dept="web") == (502, {"error": "bad_gateway"})
    fake.fail("/ui/js/sutra_ctx.js", 500)
    assert error_of(fake.get("/ui/js/sutra_ctx.js"), 500, "internal")


PATH_MESSAGE = "fail needs a path that starts with /"
STATUS_MESSAGE = "status must be a whole number from 200 to 599, or null to clear"
COUNT_MESSAGE = "count must be a whole number of at least 1"


@pytest.mark.parametrize("spec,message", [
    ({"path": "api/graph", "status": 500}, PATH_MESSAGE), ({"status": 500}, PATH_MESSAGE), ({"path": 5, "status": 500}, PATH_MESSAGE),
    ({"path": "/x", "status": 99}, STATUS_MESSAGE), ({"path": "/x", "status": 600}, STATUS_MESSAGE),
    ({"path": "/x", "status": True}, STATUS_MESSAGE), ({"path": "/x", "status": "500"}, STATUS_MESSAGE),
    ({"path": "/x", "status": 500, "count": 0}, COUNT_MESSAGE), ({"path": "/x", "status": 500, "count": True}, COUNT_MESSAGE),
    ({"path": "/x", "status": 500, "count": "2"}, COUNT_MESSAGE),
])
def test_fail_refuses_a_bad_spec(fake, spec, message):
    assert error_of(fake.request("POST", "/__fake/fail", spec), 422, "validation")["message"] == message
    assert fake.state()["failures"] == []


def test_fail_needs_an_object(fake):
    error_of(fake.request("POST", "/__fake/fail", ["x"]), 422, "validation")


def test_the_log_lists_the_requests_seen_in_order_and_not_the_controls(fake):
    fake.get("/api/chart")
    fake.get("/api/graph", level="full")
    fake.post("/api/chats/cs_org/retry")
    fake.request("POST", "/api/chats/cs_org/retry", {})  # no token
    log = fake.log()
    assert [(e["n"], e["method"], e["path"], e["status"]) for e in log] == [
        (1, "GET", "/api/chart", 200), (2, "GET", "/api/graph", 200), (3, "POST", "/api/chats/cs_org/retry", 202),
        (4, "POST", "/api/chats/cs_org/retry", 401)]
    assert log[1]["query"] == "level=full" and log[0]["query"] == "" and log[0]["body"] is None
    assert [e["token"] for e in log] == [False, False, True, False]
    assert log[2]["body"] == {} and set(log[0]) == {"n", "method", "path", "query", "status", "token", "body"}
    assert [e["path"] for e in fake.log("/api/g")] == ["/api/graph"]  # filtered by prefix
    assert fake.log("/nothing") == []
    assert len(fake.log()) == 4  # reading the log is not logged


def test_the_log_records_the_body_of_a_write_and_the_status_of_a_forced_failure(fake):
    fake.stage("full")  # no first-task story is played on top of a full org chat
    fake.post("/api/chats/cs_org/messages", {"text": "hello there"})
    fake.fail("/api/health", 500)
    fake.get("/api/health")
    posts = fake.log("/api/chats")
    assert posts[0]["body"] == {"text": "hello there"} and posts[0]["status"] == 202
    assert fake.log("/api/health")[0]["status"] == 500


def test_the_log_keeps_a_body_that_is_not_json_as_text_and_cuts_a_long_one(fake_server, fake):
    fake.stage("full")
    raw_request(fake_server.url, "POST", "/api/chats/cs_org/messages", headers={"X-Sutra-Token": fb.TOKEN, "Content-Type": "application/json"}, body=b"{nope")
    raw_request(fake_server.url, "POST", "/api/chats/cs_org/messages", headers={"X-Sutra-Token": fb.TOKEN, "Content-Type": "application/json"},
                body=b"x" * 500)
    first, second = fake.log("/api/chats")
    assert first["body"] == "{nope" and second["body"] == "x" * 200 and first["status"] == second["status"] == 422
    assert fb._parse_body(b"") is None and fb._parse_body(b'{"a": 1}') == {"a": 1}


def test_state_reports_stages_failures_streams_and_the_last_event(fake_server, fake):
    assert fake.state() == {"chart": "1", "graph": "1", "sign_in": "success", "failures": [], "subscribers": 0, "last_event_id": 0,
                            "flows_running": 0, "codex_signed_in": False}
    fake.stage("full")
    fake.fail("/api/health", 500)
    fake.emit("needs_you.changed", {"count": 0})
    with Stream(fake_server.url) as stream:
        stream.next()
        fake.wait_subscribers(1)
        state = fake.state()
    assert (state["chart"], state["graph"], state["subscribers"], state["last_event_id"]) == ("3", "full", 1, 1)
    assert [f["path"] for f in state["failures"]] == ["/api/health"]


def test_a_reset_with_no_story_running_does_not_wait(fake):
    started = time.monotonic()
    fake.reset()
    assert time.monotonic() - started < 2.5  # it waits up to 3 s for a story to end, and only when one is running


def test_reset_puts_everything_back_to_stage_one(fake):
    fake.stage("full")
    fake.fail("/api/health", 500)
    fake.emit("needs_you.changed", {"count": 0})
    fake.post("/api/connectors/codex/sign-in")
    fake.request("PUT", "/api/engine/settings", {"set": {"budget": 7}}, token=True)
    fake.page("p", "<p>x</p>")
    assert fake.reset() == {"chart": "1", "graph": "1", "sign_in": "success"}
    assert fake.state() == {"chart": "1", "graph": "1", "sign_in": "success", "failures": [], "subscribers": 0, "last_event_id": 0,
                            "flows_running": 0, "codex_signed_in": False}
    assert fake.log() == [] and ok(fake, "/api/health")["connectors"]["codex"]["signed_in"] is False
    assert ok(fake, "/api/engine/settings")["global"] == load("engine-settings.json")["global"]
    assert ok(fake, "/api/chats/cs_org/messages")["next_after"] == 1
    assert fake.get("/__fake/mount/p.html")[0] == 404


def test_page_registers_a_mount_page_with_the_boot_block(fake_server, fake):
    url = fake.page("probe", "<!doctype html><title>x</title><!--SUTRA-BOOT--><p>mine</p>")
    assert url == f"{fake_server.url}/__fake/mount/probe.html"
    status, headers, raw = raw_request(fake_server.url, "GET", "/__fake/mount/probe.html")
    page = raw.decode()
    assert status == 200 and headers["cache-control"] == "no-store" and "<p>mine</p>" in page and "<!--SUTRA-BOOT-->" not in page
    boot = json.loads(re.search(r'<script type="application/json" id="sutra-boot">(.*?)</script>', page, re.S).group(1))
    assert boot["page"] == "home" and boot["token"] == fb.TOKEN and boot["dept"] == "" and boot["version"] == "0.1.0"
    fake.stage("2")
    page = raw_request(fake_server.url, "GET", "/__fake/mount/probe.html?dept=web")[2].decode()
    boot = json.loads(re.search(r'id="sutra-boot">(.*?)</script>', page, re.S).group(1))
    assert (boot["page"], boot["dept"], boot["dept_label"]) == ("dept", "web", "Web")
    page = raw_request(fake_server.url, "GET", "/__fake/mount/probe.html?dept=nosuch")[2].decode()
    assert json.loads(re.search(r'id="sutra-boot">(.*?)</script>', page, re.S).group(1))["page"] == "home"  # an unknown team: Home's boot


def test_the_mount_pages_of_the_fixtures_are_served_by_name_with_or_without_the_prefix(fake_server, fake):
    for name in ("graph", "mount_graph", "panel", "mount_panel"):
        status, _, raw = raw_request(fake_server.url, "GET", f"/__fake/mount/{name}.html")
        page = raw.decode()
        assert status == 200 and "id=\"sutra-boot\"" in page and "<!--SUTRA-BOOT-->" not in page, name
    assert "GraphView.create" in raw_request(fake_server.url, "GET", "/__fake/mount/graph.html")[2].decode()
    assert "NodePanel.mount" in raw_request(fake_server.url, "GET", "/__fake/mount/panel.html")[2].decode()
    fake.page("graph", "<p>replaced</p><!--SUTRA-BOOT-->")  # a registered page wins over the file
    assert "<p>replaced</p>" in raw_request(fake_server.url, "GET", "/__fake/mount/graph.html")[2].decode()


@pytest.mark.parametrize("path", ["/__fake/mount/nothing.html", "/__fake/mount/graph", "/__fake/mount/Graph.html", "/__fake/mount/a-b.html",
                                  "/__fake/mount/.html"])
def test_a_mount_page_that_does_not_exist_or_has_a_bad_name_is_a_404_envelope(fake, path):
    error_of(fake.get(path), 404, "not_found")


@pytest.mark.parametrize("spec", [{"name": "Upper", "html": "x"}, {"name": "a" * 41, "html": "x"}, {"name": "ok"}, {"name": "ok", "html": 5},
                                  {"html": "x"}, ["x"], {"name": "a-b", "html": "x"}])
def test_page_refuses_a_bad_registration(fake, spec):
    error_of(fake.request("POST", "/__fake/page", spec), 422, "validation")


# ---- what Home reads on load besides the story: the owner's notes and the pill of a chat, answered as the real routes answer -------------------
# Both used to be missing or off, so every test of Home had to announce a failure the product never has (a 404 for the pill of the org chat, a 404 for the
# notes a Settings group reads). The expected shapes are the real models, which the real routes build their answers from (`ProviderPill` is closed: a key it
# has not is an error; `NoteOut` is not, so the fake's control keeps only its fields).
def test_the_owners_notes_are_listed_as_the_real_route_lists_them(fake):
    from sutra_app.orchestrator.notes import GROUP_WORDS, GROUPS, NOTE_CHARS, PER_GROUP, NotesOut

    answer = ok(fake, "/api/notes")
    assert NotesOut.model_validate(answer).model_dump(mode="json") == answer               # the real model reads it and writes it back unchanged
    assert answer == {"notes": [], "groups": [{"id": g, "label": GROUP_WORDS[g]} for g in GROUPS], "per_group": PER_GROUP, "max_chars": NOTE_CHARS}
    assert [g["id"] for g in answer["groups"]] == ["about-you", "work", "preferences"]     # what the page's three lists are named after (notes_view.js)
    assert fake.request("GET", "/api/notes", token=False)[0] == 200                         # a read needs no token


def test_the_notes_a_test_sets_are_listed_by_group_then_id_and_a_row_the_real_route_could_not_send_is_refused(fake):
    rows = [{"id": 2, "group": "preferences", "text": "Plain words.", "expires": None, "expired": False},
            {"id": 5, "group": "about-you", "text": "I run a cafe.", "expires": "2020-01-01", "expired": True},
            {"id": 3, "group": "about-you", "text": "The door is blue.", "expires": None, "expired": False}]
    assert fake.request("POST", "/__fake/notes", {"notes": rows}) == (200, {"notes": 3})
    assert [(n["id"], n["group"]) for n in ok(fake, "/api/notes")["notes"]] == [(3, "about-you"), (5, "about-you"), (2, "preferences")]
    assert ok(fake, "/api/notes")["notes"][1]["expired"] is True                           # an expired note is listed and says so, never dropped
    for bad in ({"id": "x", "group": "work", "text": "t", "expires": None, "expired": False},          # an id that is not a number
                {"id": 1, "group": "work", "text": "t", "expires": None},                                   # no `expired`
                {"id": 1, "group": "gossip", "text": "t", "expires": None, "expired": False}):           # a group the real store does not keep
        error_of(fake.request("POST", "/__fake/notes", {"notes": [bad]}), 422, "validation")
    error_of(fake.request("POST", "/__fake/notes", {}), 422, "validation")
    assert len(ok(fake, "/api/notes")["notes"]) == 3                                        # a refused control changed nothing
    fake.reset()
    assert ok(fake, "/api/notes")["notes"] == []


def test_the_pill_of_every_chat_the_fake_knows_is_served_in_the_real_shape(fake_server, fake):
    from sutra_app.connectors.chat_models import ProviderPill

    fake.stage("full")
    sessions = sorted(fake_server.state.session_ids())
    assert "cs_org" in sessions and len(sessions) > 5                                       # the org chat, the teams, the functions
    for sid in sessions:
        answer = ok(fake, f"/api/chats/{sid}/providers")
        assert set(answer) == {"providers", "chosen", "kind", "agent", "own", "effective"}, sid          # chat_v2.py: what the route sends
        assert [p["name"] for p in answer["providers"]] == ["claude", "codex"], sid
        for entry in answer["providers"]:
            ProviderPill.model_validate(entry)                                              # the real model: closed, so a key it has not is an error
        assert set(answer["effective"]) == {"provider", "model", "effort", "source"}, sid
    assert ok(fake, "/api/chats/cs_org/providers")["kind"] == "org"


def test_a_chat_the_fake_does_not_know_has_no_pill_and_the_control_takes_the_route_away_until_the_next_reset(fake):
    error_of(fake.get("/api/chats/cs_nobody/providers"), 404, "not_found")                  # the real route: NotFound for a session that is not there
    assert fake.request("POST", "/__fake/pill", {"on": False})[1]["pill"] is False
    error_of(fake.get("/api/chats/cs_org/providers"), 404, "not_found")                     # for a test of a page whose pill read fails
    fake.reset()
    assert ok(fake, "/api/chats/cs_org/providers")["providers"][0]["name"] == "claude"


# ---- the owner writes: POST /api/chats/{sid}/messages and the scripted stories it starts ---------------------------------------------
def all_events(fake_server) -> list[dict]:
    """Everything in the ring, with `server.hello` first (once=1 replays from the start and closes)."""
    with Stream(fake_server.url, "/api/events?once=1") as stream:
        frames = []
        while (frame := stream.next()) is not None:
            frames.append(frame)
    return frames


FIRST_TASK_EVENTS = [  # events.script.json "first_task": the chat agent's turn as the owner sees it
    "chat.message", "chat.turn", "chat.turn", "chat.turn", "chat.turn", "chart.changed", "graph.updated", "chat.turn", "chat.message",
    "chat.message", "chat.message", "task.updated", "chat.message", "chat.message", "chat.message", "needs_you.changed", "chat.turn",
]


def test_the_first_brief_plays_the_story_of_the_first_task_in_order(fake_server, fake):
    status, answer = fake.post("/api/chats/cs_org/messages", {"text": "  A website for my cafe  "})
    assert (status, answer) == (202, {"message_id": 2, "turn": "started"})
    fake.wait_flows()
    frames = all_events(fake_server)
    assert [f["event"] for f in frames] == ["server.hello", *FIRST_TASK_EVENTS]
    assert [f.get("id") for f in frames] == [None, *range(1, len(FIRST_TASK_EVENTS) + 1)]
    turns = [f["data"]["phase"] for f in frames if f["event"] == "chat.turn"]
    assert turns == ["reading_chart", "consulting_library", "planning", "applying", "handing_off", "done"]
    assert fake.state()["chart"] == "2" and fake.state()["graph"] == "2"
    messages = ok(fake, "/api/chats/cs_org/messages")["messages"]
    assert [m["id"] for m in messages] == [1, 2, 3, 4, 5, 6] and messages[1]["text"] == "A website for my cafe"  # trimmed, in the story
    assert [m["card"]["type"] for m in messages if m["card"]] == ["chart_change", "task", "needs_you"]
    assert ok(fake, "/api/chats/cs_org")["phase"] is None  # the turn is over
    assert ok(fake, "/api/chart") == chart_fixtures()["2"] and ok(fake, "/api/graph", level="full") == graph_fixtures()["2"]
    assert len(ok(fake, "/api/chats/cs_5e0a77b19c3d/messages")["messages"]) == 2 and ok(fake, "/api/needs-you") == load("needs-you.json")["2"]
    first_turn = next(f for f in frames if f["event"] == "chat.message")
    assert first_turn["data"]["message"]["text"] == "A website for my cafe" and first_turn["data"]["session_id"] == "cs_org"


def test_a_second_brief_is_an_ordinary_line_and_the_story_is_not_played_again(fake_server, fake):
    fake.post("/api/chats/cs_org/messages", {"text": "A website for my cafe"})
    fake.wait_flows()
    before = len(all_events(fake_server))
    status, answer = fake.post("/api/chats/cs_org/messages", {"text": "Also a menu page"})
    after_the_story = len(load("chat-org.json")["messages"]) + 1  # a line of the owner's own gets an id past the whole fixture
    assert (status, answer) == (202, {"message_id": after_the_story, "turn": "started"})
    frames = all_events(fake_server)
    assert len(frames) == before + 1 and frames[-1]["event"] == "chat.message" and frames[-1]["data"]["message"]["text"] == "Also a menu page"
    assert [m["who"] for m in ok(fake, "/api/chats/cs_org/messages", after=6)["messages"]] == ["user"]  # the story ends at message 6


def test_two_briefs_in_a_row_play_the_story_once(fake_server, fake):
    first = fake.post("/api/chats/cs_org/messages", {"text": "One"})
    second = fake.post("/api/chats/cs_org/messages", {"text": "Two"})  # the story is still running
    fake.wait_flows()
    assert first[1]["message_id"] == 2 and second[1]["message_id"] == len(load("chat-org.json")["messages"]) + 1  # the second is a plain line
    events = [f["event"] for f in all_events(fake_server)[1:]]
    assert events.count("graph.updated") == 1 and events.count("chart.changed") == 1


def test_answering_the_teams_question_plays_the_story_of_the_answer(fake_server, fake):
    fake.stage("2")
    status, answer = fake.post("/api/chats/cs_5e0a77b19c3d/messages", {"text": "Option 1"})
    assert (status, answer) == (200, {"message_id": 3, "delivered": "answer", "task_id": "tsk_a1b2c3d4e5f6"})
    fake.wait_flows()
    names = [f["event"] for f in all_events(fake_server)[1:]]
    assert sorted(names) == sorted(["chat.message"] * 5 + ["graph.updated", "task.updated", "needs_you.changed"])
    assert names[0] == "chat.message"  # the owner's line is shown before anything else happens
    assert names.index("graph.updated") < names.index("task.updated")  # the steps of the story keep their order
    assert fake.state()["graph"] == "3" and ok(fake, "/api/needs-you") == []
    assert ok(fake, "/api/graph", level="full") == graph_fixtures()["3"]
    assert len(ok(fake, "/api/chats/cs_b37b2000ef36/messages")["messages"]) == 3  # Adaptation starts to speak
    updated = next(f for f in all_events(fake_server) if f["event"] == "needs_you.changed")
    assert updated["data"] == {"count": 0}


def test_answering_at_the_full_story_moves_nothing_else(fake_server, fake):
    fake.stage("full")
    adaptation = ok(fake, "/api/chats/cs_b37b2000ef36/messages")["messages"]
    assert fake.post("/api/chats/cs_5e0a77b19c3d/messages", {"text": "Option 2"})[1]["delivered"] == "answer"
    fake.wait_flows()
    assert fake.state()["graph"] == "full"  # the steps that belong to stage 2 and stage 3 are skipped: no new graph, no new voice
    names = [f["event"] for f in all_events(fake_server)[1:]]
    assert sorted(names) == sorted(["chat.message", "chat.message", "task.updated", "needs_you.changed"])
    assert ok(fake, "/api/chats/cs_b37b2000ef36/messages")["messages"] == adaptation


def test_an_answer_whose_story_has_been_played_is_a_plain_line(fake_server, fake):
    fake.stage("2")
    fake_server.state.flows_played.add("answer")
    status, answer = fake.post("/api/chats/cs_5e0a77b19c3d/messages", {"text": "Option 1"})
    assert status == 200 and answer["delivered"] == "answer" and answer["message_id"] == len(load("chat-dept.json")["messages"]) + 1
    names = [f["event"] for f in all_events(fake_server)[1:]]
    assert names == ["chat.message", "needs_you.changed"]
    assert [m["text"] for m in ok(fake, "/api/chats/cs_5e0a77b19c3d/messages")["messages"]][-1] == "Option 1"


def test_a_line_to_a_team_that_works_is_busy_and_nothing_is_stored(fake):
    fake.stage("3")
    error = error_of(fake.post("/api/chats/cs_5e0a77b19c3d/messages", {"text": "Add a gallery"}), 409, "busy")
    assert error["message"] == "The team is working. You can write again when it asks you something or is done"
    assert [m["text"] for m in ok(fake, "/api/chats/cs_5e0a77b19c3d/messages")["messages"]] == [
        m["text"] for m in load("chat-dept.json")["messages"][:4]]


def test_the_lines_the_fake_writes_itself_are_stamped_one_second_apart_from_ten_oh_five(fake):
    fake.stage("full")
    first = fake.post("/api/chats/cs_6c0ffee1b2a3/messages", {"text": "One"})[1]["message_id"]
    second = fake.post("/api/chats/cs_6c0ffee1b2a3/messages", {"text": "Two"})[1]["message_id"]
    stamps = {m["id"]: m["at"] for m in ok(fake, "/api/chats/cs_6c0ffee1b2a3/messages")["messages"]}
    assert (stamps[first], stamps[second]) == ("2026-11-04T10:05:01Z", "2026-11-04T10:05:02Z")
    fake.reset()
    fake.stage("full")
    again = fake.post("/api/chats/cs_6c0ffee1b2a3/messages", {"text": "Three"})[1]["message_id"]
    assert {m["id"]: m["at"] for m in ok(fake, "/api/chats/cs_6c0ffee1b2a3/messages")["messages"]}[again] == "2026-11-04T10:05:01Z"  # the clock restarts


def test_a_line_to_an_idle_team_or_to_its_division_is_a_follow_up_for_the_departments_identity(fake):
    fake.stage("full")
    text = "Add a cappuccino"
    task_id = "tsk_" + hashlib.sha1(("follow-up:content" + text).encode()).hexdigest()[:12]
    status, answer = fake.post("/api/chats/cs_3e11bad0c0de/messages", {"text": text})  # the Menu division of Content: a lens on Content's chat
    assert (status, answer) == (200, {"message_id": answer["message_id"], "delivered": "follow_up", "task_id": task_id})
    last = ok(fake, "/api/chats/cs_6c0ffee1b2a3/messages")["messages"][-1]
    assert (last["id"], last["role"], last["who"], last["text"], last["task_id"]) == (answer["message_id"], "user", "user", text, task_id)
    direct = fake.post("/api/chats/cs_6c0ffee1b2a3/messages", {"text": "And a flat white"})[1]
    assert direct["delivered"] == "follow_up" and direct["message_id"] == answer["message_id"] + 1
    assert direct["task_id"] != task_id  # a task id for each line


def test_a_working_log_and_a_step_are_read_only_and_an_unknown_chat_is_gone(fake):
    fake.stage("2")
    error = error_of(fake.post("/api/chats/cs_77aa10c2e9b4/messages", {"text": "hello"}), 403, "read_only")
    assert error["message"] == "This is the working log of Identity. It is read-only."
    error_of(fake.post("/api/chats/cs_0c91d4aa3e77/messages", {"text": "hello"}), 403, "read_only")
    error_of(fake.post("/api/chats/cs_000000000000/messages", {"text": "hello"}), 404, "not_found")
    assert len(ok(fake, "/api/chats/cs_77aa10c2e9b4/messages")["messages"]) == 16  # nothing was added


BODY_MESSAGE = "the body is {text, choice?}"
TEXT_MESSAGE = "text must be 1 to 8000 characters"
CHOICE_MESSAGE = "choice is {message_id, option}"


@pytest.mark.parametrize("body,path,message", [
    ({}, "text", TEXT_MESSAGE), ({"text": ""}, "text", TEXT_MESSAGE), ({"text": "   \n"}, "text", TEXT_MESSAGE), ({"text": 5}, "text", TEXT_MESSAGE),
    ({"text": "x" * 8001}, "text", TEXT_MESSAGE),
    ({"text": "x", "extra": 1}, "", BODY_MESSAGE), ([], "", BODY_MESSAGE), ("text", "", BODY_MESSAGE),
    ({"text": "x", "choice": 5}, "choice", CHOICE_MESSAGE), ({"text": "x", "choice": {"message_id": "1", "option": "Yes"}}, "choice", CHOICE_MESSAGE),
    ({"text": "x", "choice": {"message_id": 1}}, "choice", CHOICE_MESSAGE),
    ({"text": "x", "choice": {"message_id": 1, "option": "Yes", "more": 1}}, "choice", CHOICE_MESSAGE),
    ({"text": "x", "choice": {"message_id": 1, "option": 2}}, "choice", CHOICE_MESSAGE),
])
def test_a_line_that_is_not_text_of_one_to_8000_characters_is_refused_before_anything_is_stored(fake, body, path, message):
    error = error_of(fake.post("/api/chats/cs_org/messages", body), 422, "validation")
    assert error["message"] == message and error["details"]["violations"] == [{"path": path, "code": error["details"]["violations"][0]["code"], "message": message}]
    assert ok(fake, "/api/chats/cs_org/messages")["next_after"] == 1


def test_a_card_button_posts_its_choice_with_the_option_text(fake):
    status, answer = fake.post("/api/chats/cs_org/messages", {"text": "Yes", "choice": {"message_id": 20, "option": "Yes"}})
    assert status == 202 and answer["turn"] == "started"
    fake.wait_flows()
    assert ok(fake, "/api/chats/cs_org/messages")["messages"][1]["text"] == "Yes"  # the option's text is the line
    assert fake.post("/api/chats/cs_org/messages", {"text": "x" * 8000})[0] == 202  # the longest line


# ---- the stories under stress -------------------------------------------------------------------------------------------------
def test_a_reset_in_the_middle_of_a_story_stops_it_at_its_next_step(fake_server, fake, monkeypatch):
    monkeypatch.setattr(fb, "FLOW_STEP_SECONDS", 0.3)
    fake.post("/api/chats/cs_org/messages", {"text": "A website for my cafe"})
    assert fake.state()["flows_running"] == 1
    fake.reset()
    assert fake.state()["flows_running"] == 0 and fake.state()["graph"] == "1" and fake.state()["chart"] == "1"
    assert fake.log() == []  # and the later steps of the story did not run: no event, no new line
    assert ok(fake, "/api/chats/cs_org/messages")["next_after"] == 1


def test_a_story_whose_first_step_fails_does_not_leave_the_counter_raised(fake_server, fake, monkeypatch):
    def broken(self, step, text, keep=frozenset()):
        raise RuntimeError("a step failed")

    monkeypatch.setattr(fb.FakeState, "_run_step", broken)
    status, _, raw = write_request(fake_server, "POST", "/api/chats/cs_org/messages", {"text": "x"}, {"X-Sutra-Token": fb.TOKEN})
    assert status == 500
    assert fake.state()["flows_running"] == 0


def test_closing_the_fake_ends_the_stories_and_streams(fake_server, fake):
    state = fake_server.state
    state.closing = True
    try:
        with Stream(fake_server.url) as stream:
            assert stream.next()["event"] == "server.hello" and stream.next() is None  # a closing server ends the stream at once
    finally:
        state.closing = False


def test_the_ring_keeps_the_last_thousand_events_and_the_stream_pings_every_fifteen_seconds(fake_server, fake):
    state = fake_server.state
    for count in range(1005):
        state.publish("needs_you.changed", {"count": count})  # direct, not over HTTP: 1005 requests would take seconds
    assert len(state.ring) == fb.RING_SIZE == 1000 and (state.ring[0]["id"], state.ring[-1]["id"]) == (6, 1005)
    assert fb.PING_SECONDS == 15.0 and len(fb.TOKEN) >= 16  # the token is as long as the app's own minimum


def test_iso_at_counts_seconds_from_ten_oh_five(fake):
    assert fb.iso_at(0) == "2026-11-04T10:05:00Z" and fb.iso_at(59) == "2026-11-04T10:05:59Z"
    assert fb.iso_at(60) == "2026-11-04T10:06:00Z" and fb.iso_at(55 * 60) == "2026-11-04T11:00:00Z"
    assert fb.iso_at(14 * 3600) == "2026-11-04T00:05:00Z"  # past midnight the hour wraps and the date stays


def test_a_live_event_that_was_also_replayed_is_sent_once(fake_server, fake, monkeypatch):
    state = fake_server.state
    real = state.replay

    def replay_after_a_publish(after):
        state.publish("needs_you.changed", {"count": 1})  # lands in the ring and in the queue of the stream that just subscribed
        return real(after)

    monkeypatch.setattr(state, "replay", replay_after_a_publish)
    with Stream(fake_server.url, "/api/events?after=0") as stream:
        assert [(f["event"], f.get("id")) for f in stream.take(2)] == [("server.hello", None), ("needs_you.changed", 1)]
        fake.wait_subscribers(1)
        fake.emit("needs_you.changed", {"count": 2})
        assert stream.next()["id"] == 2  # and the next one follows, no repeat of the first


def test_the_state_methods_that_a_story_calls_are_quiet_when_there_is_nothing_to_do(fake_server, fake):
    state = fake_server.state
    chat = state.chats["cs_org"]
    assert state.reveal(chat, 0) == [] and state.reveal(chat, 1) == []  # already visible
    assert state.flow_for("nosuch", chat) is None and state.flow_for("answer", chat) is None  # no such story; it belongs to another chat
    state.flows_played.add("first_task")
    assert state.flow_for("first_task", chat) is None  # played already


# ---- the rest of the server's own plumbing ------------------------------------------------------------------------------------
def test_the_middleware_lets_anything_that_is_not_http_through_and_stops_reading_when_the_client_leaves(fake_server):
    import asyncio

    seen = []

    async def app(scope, receive, send):
        seen.append((scope["type"], await receive()))

    middleware = fb.FakeMiddleware(app, fake_server.state)

    async def run():
        async def startup():
            return {"type": "lifespan.startup"}

        await middleware({"type": "lifespan"}, startup, None)
        messages = iter([{"type": "http.request", "body": b'{"a":', "more_body": True}, {"type": "http.disconnect"}])

        async def receive():
            return next(messages)

        async def send(message):
            pass

        scope = {"type": "http", "method": "POST", "path": "/api/x", "headers": [(b"host", b"127.0.0.1:1")], "query_string": b""}
        await middleware(scope, receive, send)

    asyncio.run(run())
    assert seen[0] == ("lifespan", {"type": "lifespan.startup"})
    assert seen[1] == ("http", {"type": "http.request", "body": b'{"a":', "more_body": False})  # what was read is handed to the route


def test_a_websocket_gets_no_answer_from_the_fake(fake_server):
    from websockets.exceptions import InvalidStatus
    from websockets.sync.client import connect

    with pytest.raises(InvalidStatus):
        with connect(fake_server.url.replace("http://", "ws://") + "/ws", open_timeout=5):
            pass


def test_a_fake_that_is_stopped_stops_serving_and_ends_its_streams(make_fake_server):
    import urllib.error
    import urllib.request

    app = fb.make_app()
    running = fb.run_in_thread(app)
    assert urllib.request.urlopen(running.url + "/api/health", timeout=10).status == 200
    with Stream(running.url) as stream:
        assert stream.next()["event"] == "server.hello"
        started = time.monotonic()
        running.stop()  # an open stream does not hold the server back
        assert time.monotonic() - started < 14 and stream.next() is None
    with pytest.raises((urllib.error.URLError, OSError)):
        urllib.request.urlopen(running.url + "/api/health", timeout=3)  # nobody answers any more


def test_the_fake_that_cannot_start_says_so():
    app = fb.make_app()
    with pytest.raises(RuntimeError, match="the fake backend did not start"):
        fb.run_in_thread(app, host="203.0.113.77")  # an address this machine does not have: the server cannot bind


def test_the_client_reads_text_answers_and_builds_mount_urls(fake_server, fake):
    fake.stage("2")
    assert fake.get("/api/code", dept="web") == (404, "not found")
    assert fake.mount_url("graph") == f"{fake_server.url}/__fake/mount/graph.html"
    assert fake.mount_url("panel", open="web.identity", tab="details") == f"{fake_server.url}/__fake/mount/panel.html?open=web.identity&tab=details"


def test_the_client_waits_for_streams_and_stories_and_gives_up(make_fake_server):
    server = make_fake_server()
    client = server.client
    client.wait_subscribers(0)
    with pytest.raises(TimeoutError, match=r"^no event stream opened within 0\.05 s$"):
        client.wait_subscribers(1, timeout=0.05)
    client.wait_flows(timeout=0.05)
    server.state.flows_running = 1
    with pytest.raises(TimeoutError, match="^a scripted flow did not finish$"):
        client.wait_flows(timeout=0.05)
    server.state.flows_running = 0


def test_run_by_hand_it_serves_the_fake_at_the_stage_asked_for(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(fb.uvicorn, "run", lambda app, **kwargs: calls.append((app, kwargs)))
    assert fb.main(["--port", "8791", "--stage", "full"]) == 0
    ((app, kwargs),) = calls
    assert kwargs == {"host": "127.0.0.1", "port": 8791, "log_level": "warning", "lifespan": "off"}
    assert app.state.fake.stages() == {"chart": "3", "graph": "full", "sign_in": "success"}
    assert capsys.readouterr().out == f"fake backend on http://127.0.0.1:8791/  (stage full; token {fb.TOKEN}; Ctrl-C stops)\n"
    assert fb.main([]) == 0 and calls[1][1]["port"] == 8790 and calls[1][0].state.fake.stages()["graph"] == "1"
    with pytest.raises(SystemExit):
        fb.main(["--stage", "7"])


def test_fixtures_of_other_shapes_work_too(tmp_path, make_fake_server):
    folder = fixtures_copy(tmp_path, with_j2=False)
    full = json.loads((folder / "graph-full.json").read_text())
    for node in full["nodes"]:
        if node["id"] == "web.adaptation":
            node["meta"]["stats"]["atoms_total"] = 4  # one more than open and closed: it was abandoned
        if node["id"] == "s-8d2e6b4a1f":
            node["id"] = "s-8d2e6b4a1e"
            node["step_ref"] = "W-9"  # Content has no task step now
    (folder / "graph-full.json").write_text(json.dumps(full), encoding="utf-8")
    settings = json.loads((folder / "engine-settings.json").read_text())
    settings["locked"].remove("chrome")
    settings["editable"].append("chrome")
    (folder / "engine-settings.json").write_text(json.dumps(settings), encoding="utf-8")
    server = make_fake_server(fixtures_dir=folder)
    client = server.client
    client.stage("full")
    atoms = client.get("/api/graph/nodes/web.adaptation")[1]["atoms"]
    assert Counter(a["state"] for a in atoms) == Counter(open=1, closed=2, abandoned=1)
    gone = next(a for a in atoms if a["state"] == "abandoned")
    assert gone["body"]["abandon_code"] == "run_ended" and gone["body"]["reason"] == "run ended: stopped" and gone["usage"]["calls"] == 0
    assert gone["attempt"] == 1 and gone["body"]["closed_by"] == "manual-override" and gone["usage"] == {
        "calls": 0, "usd": None, "tokens_in": None, "tokens_out": None}
    assert client.get("/api/graph/nodes/content.identity")[1]["task"] is None
    assert client.request("PUT", "/api/engine/settings", {"set": {"chrome": "/Applications/Chrome"}}, token=True)[0] == 200
    for bad in (5, "x" * 501, None):
        error = error_of(client.request("PUT", "/api/engine/settings", {"set": {"chrome": bad}}, token=True), 422, "validation")
        assert error["details"]["violations"][0]["message"] == "chrome must be text of at most 500 characters"


# =====================================================================================================================
# 4. J2's data routes at the root, the team in ?dept=
# =====================================================================================================================
J2_GETS = [  # the GET handlers of j2_server.py (ENG 7.1 rows 3-25, then sync 4's), each as a concrete path
    "/api/state", "/api/runs", "/api/call?id=1", "/api/preview?atom=W-2.a1", "/api/docs", "/api/map", "/api/plan", "/api/library",
    "/api/library/website/hero/classic/v1", "/api/run-templates", "/api/artifacts", "/api/agent?who=identity",
    "/api/code?deck=a&section=b", "/api/artifacts/tree", "/api/artifact?name=site/index.html", "/api/story", "/api/board",
    "/api/audits", "/api/refs", "/api/timing", "/shot/1", "/file/prd.md", "/site/latest", "/site/v1",
    "/api/plan-map", "/api/activity?who=adaptation", "/api/catalog", "/api/artifacts/groups", "/api/runlist", "/api/changes",
    "/api/record?sec=nothing", "/doc/prd", "/view?name=site/index.html",
]
J2_POSTS = [("/api/say", {"text": "hello"}), ("/api/playbooks/clear", {}), ("/api/lessons/clear", {}), ("/api/output", {"type": "website"}),
            ("/api/reset", {}), ("/api/ask", {"who": "adaptation", "q": "Why?"}), ("/api/settings", {"decide_for_me": True})]
J2_JSON_FILES = {  # the routes that answer a capture byte for byte
    "/api/runs": "runs.json", "/api/docs": "docs.json", "/api/map": "map.json", "/api/plan": "plan.json",
    "/api/run-templates": "run-templates.json", "/api/artifacts": "artifacts.json", "/api/artifacts/tree": "artifacts-tree.json",
    "/api/story": "story.json", "/api/board": "board.json", "/api/audits": "audits.json", "/api/library": "library.json",
    "/api/refs": "refs.json", "/api/plan-map": "plan-map.json", "/api/catalog": "catalog.json", "/api/artifacts/groups": "artifacts-groups.json",
    "/api/runlist": "runlist.json", "/api/changes": "changes.json", "/api/timing": "timing.json",
}
BAD_DEPTS = [None, "", "Web", "WEB", "w", "web_1", "1web", "a b", "web/../x", "x" * 41, "web."]  # none passes DEPT_ID_RE
J2_SANDBOX = "sandbox allow-scripts allow-forms allow-popups; frame-ancestors 'self'"  # D83


def with_query(path: str, **extra) -> str:
    """`path` plus more query parameters, whether or not it has some."""
    return path + ("&" if "?" in path else "?") + urllib.parse.urlencode(extra) if extra else path


def j2_get(fake_server, path, **extra):
    return raw_request(fake_server.url, "GET", with_query(path, **extra))


def j2_post(fake_server, path, body, *, dept="web", token=True):
    headers = {"Content-Type": "application/json", **({"X-Sutra-Token": fb.TOKEN} if token else {})}
    return raw_request(fake_server.url, "POST", with_query(path, dept=dept) if dept is not None else path, headers=headers,
                       body=json.dumps(body).encode())


def test_the_j2_routes_the_fake_registers_are_the_ones_the_client_wrapper_adds_dept_to(fake_server):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is needed to read J2_PATHS from sutra_ctx.js")
    script = "const c = require(process.argv[1]); process.stdout.write(JSON.stringify(c.J2_PATHS));"
    done = subprocess.run([node, "-e", script, str(REPO / "sutra_app" / "ui" / "static" / "js" / "sutra_ctx.js")], capture_output=True,
                          text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    paths = json.loads(done.stdout)
    assert {"/api/ask", "/api/plan-map", "/api/activity", "/api/catalog", "/api/artifacts/groups", "/api/runlist", "/api/changes"} <= set(paths["exact"])
    assert "patched" not in paths                                   # P13 is retired (D140): runlist and changes are J2's own routes now
    registered = {(method, ctx.path) for ctx in iter_route_contexts(fake_server.app.routes) for method in (ctx.methods or ())
                  if method in ("GET", "POST") and not ctx.path.startswith("/__fake/")}
    # the pages the Simple view puts in its frame build their own ?dept= (E4), so whether the wrapper lists them does not matter here
    fetches = set(paths["exact"]) - set(fb.J2_PAGE_PATHS)
    exact = {path for _, path in registered if path in fetches}
    assert exact == fetches, "every path the wrapper adds ?dept= to has a route in the fake, and the reverse"
    assert fb.J2_PATH_SET == frozenset(fetches)  # the paths whose forced failures have J2's body shape
    assert {path for _, path in registered if path in fb.J2_PAGE_PATHS} == set(fb.J2_PAGE_PATHS) and "/doc/{name}" in {path for _, path in registered}
    prefixed = {path for _, path in registered if any(path.startswith(prefix) for prefix in paths["prefixes"])}
    assert prefixed >= {"/api/library/{artifact}/{section}/{slug}/{ver}", "/site/{key}", "/file/{name}", "/shot/{n}"}
    assert prefixed <= {"/api/library/{artifact}/{section}/{slug}/{ver}", "/site/{key}", "/file/{name}", "/shot/{n}", "/doc/{name}"}
    assert {(m, p) for m, p in registered if p in fb.J2_POST_PATHS} == {("POST", p) for p in fb.J2_POST_PATHS} and len(fb.J2_POST_PATHS) == 7
    # 23 GET and 5 POST handlers of engine.md 7.1; sync 5 added /api/timing; sync 4 added nine GET (the plan map, a feed, the catalog, the groups, the run list, the changes, a record,
    # a document page, a view page) and two POST (ask, settings)
    assert len(J2_GETS) + len(J2_POSTS) == 29 + 9 + 2


@pytest.mark.parametrize("path", J2_GETS)
def test_a_j2_read_route_wants_a_well_formed_team_that_exists(fake_server, fake, path):
    fake.stage("2")
    for dept in BAD_DEPTS:
        status, _, raw = j2_get(fake_server, path, **({} if dept is None else {"dept": dept}))
        assert (status, json.loads(raw)) == (400, {"error": "dept_required"}), (path, dept)
    status, _, raw = j2_get(fake_server, path, dept="nosuch")
    assert (status, json.loads(raw)) == (404, {"error": "not_found"}), path
    fake.stage("1")  # the Web team does not exist yet
    status, _, raw = j2_get(fake_server, path, dept="web")
    assert (status, json.loads(raw)) == (404, {"error": "not_found"}), path


@pytest.mark.parametrize("path,body", J2_POSTS)
def test_a_j2_write_route_wants_the_token_and_then_a_team(fake_server, fake, path, body):
    fake.stage("2")
    assert j2_post(fake_server, path, body, token=False)[0] == 401
    assert j2_post(fake_server, path, body, dept=None, token=False)[0] == 401  # the token is judged before the team
    for dept in (None, "", "Web", "web_1"):
        status, _, raw = j2_post(fake_server, path, body, dept=dept)
        assert (status, json.loads(raw)) == (400, {"error": "dept_required"}), (path, dept)
    status, _, raw = j2_post(fake_server, path, body, dept="nosuch")
    assert (status, json.loads(raw)) == (404, {"error": "not_found"}), path


@pytest.mark.parametrize("path,name", sorted(J2_JSON_FILES.items()))
def test_a_j2_read_route_answers_its_capture_byte_for_byte(fake_server, fake, path, name):
    fake.stage("2")
    status, headers, raw = j2_get(fake_server, path, dept="web")
    assert status == 200 and raw == (J2_FIXTURES / name).read_bytes()
    assert headers["content-type"].startswith("application/json")
    assert headers["x-content-type-options"] == "nosniff" and headers["referrer-policy"] == "no-referrer"  # D83, once
    assert [k for k in headers if k == "set-cookie"] == []


def test_state_is_the_captured_state_with_the_chat_cut_at_since(fake_server, fake):
    fake.stage("2")
    captured = json.loads((J2_FIXTURES / "state.json").read_bytes())
    status, headers, raw = j2_get(fake_server, "/api/state", dept="web")
    state = json.loads(raw)
    assert status == 200 and state["saved"] is None and state["chat"] == captured["chat"] and state["total"] == captured["total"] == 48
    assert {k: v for k, v in state.items() if k != "saved"} == {k: v for k, v in captured.items() if k != "saved"}
    assert headers["x-content-type-options"] == "nosniff"
    cut = json.loads(j2_get(fake_server, "/api/state", dept="web", since=40)[2])
    assert cut["chat"] == captured["chat"][40:] and len(cut["chat"]) == 8 and cut["total"] == 48  # J2: chat[since:], total kept
    for since in ("x", "-3", "", "4.5"):  # not a whole number: no cut (J2 itself would refuse)
        assert len(json.loads(j2_get(fake_server, "/api/state", dept="web", since=since)[2])["chat"]) == 48, since
    assert json.loads(j2_get(fake_server, "/api/state", dept="web", since=99)[2])["chat"] == []


def test_a_run_is_a_saved_view_of_a_run_the_team_has_and_nothing_else(fake_server, fake):
    fake.stage("full")
    j2_run = json.loads((J2_FIXTURES / "runs.json").read_bytes())["live"]
    for run in (j2_run, "j2-20261104-100004-7f3a"):  # the id J2 itself recorded, and the id the Web nodes carry
        assert json.loads(j2_get(fake_server, "/api/state", dept="web", run=run)[2])["saved"] == run
        assert j2_get(fake_server, "/api/map", dept="web", run=run)[0] == 200
    own = "j2-20261104-103300-2c9e"  # Content's run
    assert j2_get(fake_server, "/api/map", dept="content", run=own)[0] == 200
    assert j2_get(fake_server, "/api/map", dept="web", run=own)[0] == 404  # D73: another team's run is not_found
    assert j2_get(fake_server, "/api/map", dept="content", run="j2-20261104-100004-7f3a")[0] == 404
    status, _, raw = j2_get(fake_server, "/api/state", dept="web", run="j2-19990101-000000-0000")
    assert (status, json.loads(raw)) == (404, {"error": "no such run"})  # J2's own body for the state route
    for path in J2_GETS[1:]:
        if path.startswith(("/api/library", "/api/refs", "/api/catalog")):
            continue  # global: J2 ignores `run` there
        status, _, raw = j2_get(fake_server, path, dept="web", run="j2-19990101-000000-0000")
        assert status == 404, path
        assert json.loads(raw) == {"error": "not_found"}, path
    assert j2_get(fake_server, "/api/library", dept="web", run="j2-19990101-000000-0000")[0] == 200


def test_preview_returns_the_section_of_a_known_atom_and_nothing_for_another(fake_server, fake):
    fake.stage("2")
    replies = json.loads((J2_FIXTURES / "preview-replies.json").read_bytes())
    assert replies
    for atom, reply in replies.items():
        status, headers, raw = j2_get(fake_server, "/api/preview", dept="web", atom=atom)
        assert status == 200 and json.loads(raw) == reply and headers["x-content-type-options"] == "nosniff"
        assert reply["html"] and reply["anchor"]
    for other in ("nope", "", "W-99.a1"):
        assert json.loads(j2_get(fake_server, "/api/preview", dept="web", atom=other)[2]) == {"anchor": None, "html": None}
    assert json.loads(j2_get(fake_server, "/api/preview", dept="web")[2]) == {"anchor": None, "html": None}


@pytest.mark.parametrize("who", [*FUNCTIONS, "W-1"])
def test_agent_answers_the_captured_view_of_each_function_and_of_a_builder(fake_server, fake, who):
    fake.stage("2")
    status, _, raw = j2_get(fake_server, "/api/agent", dept="web", who=who)
    assert status == 200 and raw == (J2_FIXTURES / f"agent-{who}.json").read_bytes()


def test_agent_answers_the_unknown_view_for_anyone_else_and_names_who_was_asked_for(fake_server, fake):
    fake.stage("2")
    unknown = json.loads((J2_FIXTURES / "agent-unknown.json").read_bytes())
    for who in ("zed", "W-99", "", "../identity"):
        status, _, raw = j2_get(fake_server, "/api/agent", dept="web", who=who)
        assert status == 200 and json.loads(raw) == {**unknown, "who": who}, who
    assert json.loads(j2_get(fake_server, "/api/agent", dept="web")[2]) == {**unknown, "who": ""}


def test_the_j2_reads_that_have_no_data_in_the_fixtures_answer_j2s_own_404s(fake_server, fake):
    fake.stage("2")
    cases = [("/api/call?id=1", {"error": "no such call"}), ("/api/library/website/hero/classic/v1", {"error": "no such template"})]
    for path, body in cases:
        status, headers, raw = j2_get(fake_server, path, dept="web")
        assert (status, json.loads(raw)) == (404, body), path
    for path in ("/api/code?deck=a&section=b", "/shot/1", "/file/prd.md", "/site/v0", "/site/v6", "/site/vx", "/site/other", "/api/artifact?name=x"):
        status, headers, raw = j2_get(fake_server, path, dept="web")
        assert (status, raw) == (404, b"not found"), path
        assert headers["content-type"].startswith("text/plain") and headers["x-content-type-options"] == "nosniff"


def test_generated_pages_come_sandboxed_like_the_engines_own(fake_server, fake):
    fake.stage("2")
    page = (J2_FIXTURES / "site-latest.html").read_bytes()
    versions = json.loads((J2_FIXTURES / "state.json").read_bytes())["versions"]
    assert versions == 5
    urls = ["/site/latest", "/api/artifact?name=site/index.html"] + [f"/site/v{n}" for n in range(1, versions + 1)]
    for url in urls:
        status, headers, raw = j2_get(fake_server, url, dept="web")
        assert status == 200 and raw == page, url
        assert headers["content-type"].startswith("text/html")
        assert headers["content-security-policy"] == J2_SANDBOX and headers["x-content-type-options"] == "nosniff", url
        assert headers["referrer-policy"] == "no-referrer"
    assert j2_get(fake_server, "/site/latest", dept="web", run="j2-20261104-100004-7f3a")[0] == 200  # a saved run too


def test_say_delivers_the_owners_answer_to_the_team_that_asked(fake_server, fake):
    fake.stage("2")
    status, _, raw = j2_post(fake_server, "/api/say", {"text": "  Option 1  "})
    assert (status, json.loads(raw)) == (200, {"ok": True})
    fake.wait_flows()
    assert fake.get("/api/needs-you") == (200, []) and fake.state()["graph"] == "3"  # the answer moved the story on
    messages = ok(fake, "/api/chats/cs_5e0a77b19c3d/messages")["messages"]
    assert [m["text"] for m in messages if m["role"] == "user"] == ["A website for my cafe", "Option 1"]  # trimmed, stored once


def test_say_to_a_team_that_is_working_is_busy_and_to_a_team_that_is_idle_a_follow_up(fake_server, fake):
    fake.stage("3")  # Web is running
    status, _, raw = j2_post(fake_server, "/api/say", {"text": "Add a gallery"})
    assert (status, json.loads(raw)) == (409, {"ok": False})  # J2's body, not the envelope
    fake.stage("full")  # Content is idle
    status, _, raw = j2_post(fake_server, "/api/say", {"text": "Add a gallery"}, dept="content")
    assert (status, json.loads(raw)) == (200, {"ok": True})
    texts = [m["text"] for m in ok(fake, "/api/chats/cs_6c0ffee1b2a3/messages")["messages"]]
    assert texts[-1] == "Add a gallery"


def test_the_fake_says_the_effective_flags_with_the_implication_chain_of_the_engine(fake):
    """D178: auto_reuse implies run_templates and template_library, template_library implies artifact_schema; artifact_library implies auto_reuse."""
    names = ("auto_reuse", "run_templates", "template_library", "artifact_schema", "artifact_library")
    fake.stage("full")

    def flags_with(field):
        status, answer = fake.request("PUT", "/api/engine/settings?dept=web", {"set": {field: True}}, token=True)
        assert status == 200, answer
        assert fake.request("PUT", "/api/engine/settings?dept=web", {"unset": [field]}, token=True)[0] == 200
        assert answer["effective"][field] is True and all(answer["effective"][n] is False for n in names if n != field), "`effective` is what was stored"
        return {n: answer["effective_flags"][n] for n in names if n != "artifact_library"}
    assert flags_with("run_templates") == {"auto_reuse": False, "run_templates": True, "template_library": False, "artifact_schema": False}
    assert flags_with("auto_reuse") == {"auto_reuse": True, "run_templates": True, "template_library": True, "artifact_schema": True}
    assert flags_with("artifact_library") == dict.fromkeys(("auto_reuse", "run_templates", "template_library", "artifact_schema"), True)
    assert flags_with("template_library")["run_templates"] is False
    stored = ok(fake, "/api/engine/settings", dept="web")
    assert stored["effective"]["auto_reuse"] is False and stored["effective_flags"]["auto_reuse"] is False and "auto_reuse" not in stored["department"]


def test_the_fake_answers_one_run_template_with_enabled_from_the_teams_settings(fake_server, fake):
    fake.stage("full")
    path = "/api/run-template?id=thread-boutique-website"
    status, _, raw = j2_get(fake_server, path, dept="web")
    body = json.loads(raw)
    assert status == 200 and body["id"] == "thread-boutique-website" and body["enabled"] is False, "off by default"
    assert fake.request("PUT", "/api/engine/settings?dept=web", {"set": {"run_templates": True}}, token=True)[0] == 200
    assert json.loads(j2_get(fake_server, path, dept="web")[2])["enabled"] is True
    other = next(d["id"] for d in ok(fake, "/api/departments") if d["id"] != "web")
    assert json.loads(j2_get(fake_server, path, dept=other)[2])["enabled"] is False, "another team's switch is its own"
    for bad in ("", "Thread", "a%20b", "nothing-here"):
        status, _, raw = j2_get(fake_server, "/api/run-template?id=" + bad, dept="web")
        assert (status, json.loads(raw)) == (404, {"error": "no such run template"}), bad
    assert j2_get(fake_server, path)[0] == 400, "the team is required, as on every J2 route"


def test_say_with_a_run_template_takes_the_shapes_of_the_real_route_and_refuses_the_rest(fake_server, fake):
    fake.stage("full")
    good = {"text": "A site", "template": "thread-boutique-website", "workflows": "W-1,W-2"}
    assert j2_post(fake_server, "/api/say", good, dept="content")[0] == 200
    assert j2_post(fake_server, "/api/say", {**good, "workflows": ["all"]}, dept="content")[0] == 200
    for bad in ({"template": "Bad"}, {"template": 5}, {"workflows": "W 1"}, {"workflows": 7}, {"workflows": [f"W-{n}" for n in range(41)]}):
        status, _, raw = j2_post(fake_server, "/api/say", {**good, **bad}, dept="content")
        assert status == 400 and list(json.loads(raw)) == ["error"], bad


@pytest.mark.parametrize("body", [{"text": ""}, {"text": "   "}, {}, {"text": 5}, [], "text"])
def test_say_with_nothing_to_say_is_400_empty(fake_server, fake, body):
    fake.stage("2")
    status, _, raw = j2_post(fake_server, "/api/say", body)
    assert (status, json.loads(raw)) == (400, {"error": "empty"}), body


def test_say_with_a_body_that_is_not_json_is_the_422_envelope(fake_server, fake):
    fake.stage("2")
    status, _, raw = raw_request(fake_server.url, "POST", "/api/say?dept=web", headers={"X-Sutra-Token": fb.TOKEN}, body=b"not json")
    assert status == 422 and json.loads(raw)["error"]["code"] == "validation"


def test_output_takes_one_of_the_types_the_engine_lists_and_otherwise_answers_409_with_the_team_default(fake_server, fake):
    fake.stage("2")
    for kind in ("website", "prd", "hld", "lld"):
        status, _, raw = j2_post(fake_server, "/api/output", {"type": kind})
        assert (status, json.loads(raw)) == (200, {"ok": True, "output": kind})
    for body in ({"type": "poster"}, {}, {"type": 3}, [], {"type": None}):
        status, _, raw = j2_post(fake_server, "/api/output", body)
        assert (status, json.loads(raw)) == (409, {"ok": False, "output": "auto"}), body


def test_reset_is_refused_while_the_team_works_and_clears_the_clear_routes_say_how_many(fake_server, fake):
    fake.stage("3")  # Web is running
    status, _, raw = j2_post(fake_server, "/api/reset", {})
    assert (status, json.loads(raw)) == (409, {"ok": False})
    fake.stage("2")  # Web waits for the owner
    assert (lambda r: (r[0], json.loads(r[2])))(j2_post(fake_server, "/api/reset", {})) == (200, {"ok": True})
    for path in ("/api/playbooks/clear", "/api/lessons/clear"):
        status, headers, raw = j2_post(fake_server, path, {})
        assert (status, json.loads(raw)) == (200, {"ok": True, "cleared": 0}) and headers["x-content-type-options"] == "nosniff"


def test_a_forced_failure_on_a_j2_write_has_j2s_body(fake_server, fake):
    fake.stage("2")
    fake.fail("/api/say", 503, code="busy_starting")
    status, _, raw = j2_post(fake_server, "/api/say", {"text": "x"})
    assert (status, json.loads(raw)) == (503, {"error": "busy_starting"})


# ---- sync 4: the feeds, the records and pages of the studio, the Decide for me switch -------------------------------------------------------------------
def j2_capture(name: str):
    return json.loads((J2_FIXTURES / name).read_bytes())


@pytest.mark.parametrize("who", J2_FUNCS)
def test_activity_answers_the_captured_feed_of_each_of_j2s_six_functions(fake_server, fake, who):
    fake.stage("2")
    status, headers, raw = j2_get(fake_server, "/api/activity", dept="web", who=who)
    assert status == 200 and raw == (J2_FIXTURES / f"activity-{who}.json").read_bytes() and json.loads(raw)["who"] == who
    assert headers["content-type"].startswith("application/json") and headers["x-content-type-options"] == "nosniff"


def test_activity_of_anyone_else_is_the_capture_of_a_name_j2_does_not_know_with_the_name_asked_for(fake_server, fake):
    fake.stage("2")
    unknown = j2_capture("activity-unknown.json")
    for who in ("zed", "W-1", "", "../identity"):
        status, _, raw = j2_get(fake_server, "/api/activity", dept="web", who=who)
        assert status == 200 and json.loads(raw) == {**unknown, "who": who}, who
    assert json.loads(j2_get(fake_server, "/api/activity", dept="web")[2]) == {**unknown, "who": ""}


@pytest.fixture()
def studio_server(tmp_path, make_fake_server):
    """The fake with a few captures of the studio's routes made up here (small, valid, and unlike any real record), so the routes are proved whatever the committed
    captures hold: a part's record, a deliverable's record, one document page and one view page."""
    folder = fixtures_copy(tmp_path)
    (folder / "j2" / "record-S-1.json").write_text(json.dumps({"schema": "studio/1", "sec": "S-1", "name": "Hero"}), encoding="utf-8")
    (folder / "j2" / "record-art-site-index.html.json").write_text(json.dumps({"schema": "studio/1", "name": "site/index.html"}), encoding="utf-8")
    (folder / "j2" / "doc-prd.html").write_text("<!doctype html><title>PRD</title><h1>A made-up PRD</h1>", encoding="utf-8")
    (folder / "j2" / "view-notes-todo.md.html").write_text("<!doctype html><title>todo</title><p>todo</p>", encoding="utf-8")
    server = make_fake_server(fixtures_dir=folder)
    server.client.stage("2")
    return server


def test_a_record_is_the_capture_of_its_part_or_its_deliverable_and_otherwise_j2s_404(studio_server):
    url = studio_server.url
    status, headers, raw = j2_get(studio_server, "/api/record", dept="web", sec="S-1")
    assert status == 200 and json.loads(raw) == {"schema": "studio/1", "sec": "S-1", "name": "Hero"}
    assert headers["content-type"].startswith("application/json") and headers["x-content-type-options"] == "nosniff"
    status, _, raw = j2_get(studio_server, "/api/record", dept="web", art="site/index.html")      # a deliverable: the file name is made safe (site-index.html)
    assert status == 200 and json.loads(raw) == {"schema": "studio/1", "name": "site/index.html"}
    for query in ({"sec": "S-9"}, {"art": "nothing.md"}, {}, {"sec": ""}, {"sec": "../S-1"}):
        status, _, raw = j2_get(studio_server, "/api/record", dept="web", **query)
        assert (status, json.loads(raw)) == (404, {"error": "no such part"}), query              # J2's own body for an unknown part (and for no question at all)
    assert j2_get(studio_server, "/api/record", dept="web", sec="S-1", run="j2-20261104-100004-7f3a")[0] == 200      # a saved run of the team
    assert j2_get(studio_server, "/api/record", dept="web", sec="S-1", run="j2-19990101-000000-0000")[0] == 404      # D73: any other run is not found
    assert raw_request(url, "GET", "/api/record?sec=S-1")[0] == 400                                # no team: dept_required


def test_the_pages_of_the_studio_come_sandboxed_and_a_file_that_is_not_written_is_j2s_own_line(studio_server):
    for path in ("/doc/prd", "/view?name=notes/todo.md"):
        status, headers, raw = j2_get(studio_server, path.split("?")[0], dept="web", **({"name": "notes/todo.md"} if "?" in path else {}))
        assert status == 200 and headers["content-type"].startswith("text/html"), path
        assert headers["content-security-policy"] == J2_SANDBOX and headers["x-content-type-options"] == "nosniff" and headers["referrer-policy"] == "no-referrer"
        assert raw.startswith(b"<!doctype html>"), path
    for path, params in (("/doc/hld", {}), ("/view", {"name": "never.txt"}), ("/view", {})):
        status, headers, raw = j2_get(studio_server, path, dept="web", **params)
        assert (status, raw) == (200, fb.NOT_WRITTEN.encode()), (path, params)              # J2 answers 200 and says so, as the page puts it in its frame
        assert headers["content-security-policy"] == J2_SANDBOX
    assert j2_get(studio_server, "/doc/prd", dept="web", run="j2-19990101-000000-0000")[0] == 404
    assert raw_request(studio_server.url, "GET", "/doc/prd")[0] == 400 and raw_request(studio_server.url, "GET", "/view?name=x")[0] == 400


def test_every_part_and_deliverable_the_captured_state_names_has_its_record_in_the_captures(fake_server, fake):
    """The studio's captures are complete: the fake answers a record for each part of the captured state and for each deliverable the artifacts listing names,
    and a page for each file the listing says the page opens (scripts/capture_j2_fixtures.py makes them with the state)."""
    fake.stage("2")
    studio = j2_capture("state.json")["studio"]
    assert studio["schema"] == "studio/1" and studio["parts"], "state.json holds no studio: the captures were made before the studio redesign"
    for part in studio["parts"]:
        status, _, raw = j2_get(fake_server, "/api/record", dept="web", sec=part["sec"])
        assert status == 200, part["sec"]
        assert (json.loads(raw)["sec"], json.loads(raw)["name"]) == (part["sec"], part["name"])
    deliverables = j2_capture("artifacts.json")["deliverables"]
    assert deliverables
    for row in deliverables:
        status, _, raw = j2_get(fake_server, "/api/record", dept="web", art=row["name"])
        assert status == 200, row["name"]
        assert json.loads(raw)["name"] == row["name"]
        status, _, page = j2_get(fake_server, "/view", dept="web", name=row["file"])
        assert status == 200 and page != fb.NOT_WRITTEN.encode(), row["file"]


def test_decide_for_me_is_a_switch_the_state_reports_back(fake_server, fake):
    fake.stage("2")
    captured = bool(j2_capture("state.json").get("decide_for_me", False))
    reads = lambda: json.loads(j2_get(fake_server, "/api/state", dept="web")[2]).get("decide_for_me", False)  # noqa: E731
    assert reads() is captured
    assert j2_post(fake_server, "/api/settings", {})[0] == 200 and reads() is captured                # no key: nothing changes (J2 answers the switch as it is)
    status, _, raw = j2_post(fake_server, "/api/settings", {"decide_for_me": True})
    assert (status, json.loads(raw)) == (200, {"ok": True, "decide_for_me": True}) and reads() is True
    assert json.loads(j2_post(fake_server, "/api/settings", {"other": 1})[2]) == {"ok": True, "decide_for_me": True}
    assert json.loads(j2_post(fake_server, "/api/settings", {"decide_for_me": 0})[2]) == {"ok": True, "decide_for_me": False} and reads() is False
    fake.stage("full")
    j2_post(fake_server, "/api/settings", {"decide_for_me": True})
    assert reads() is True
    assert json.loads(j2_get(fake_server, "/api/state", dept="content")[2]).get("decide_for_me", False) is captured      # a switch is a team's own
    fake.reset()
    fake.stage("2")
    assert reads() is captured                                                                           # reset with the story


# ---- sync 4: POST /api/ask and the two lines it stores ---------------------------------------------------------------------------------------------------
ASK = "/api/ask"


def ask(fake_server, who="adaptation", q="Why was W-3 scored below the gate?", run="", dept="web", **extra):
    body = {"who": who, "q": q, **({"run": run} if run is not None else {}), **extra}
    status, _, raw = j2_post(fake_server, ASK, body, dept=dept)
    return status, json.loads(raw)


def agent_rows_of(fake, run=None):
    return {row["agent"]: row for row in ok(fake, "/api/teams/web/agents", **({"run": run} if run else {}))}


def lines_of(fake, sid):
    return ok(fake, f"/api/chats/{sid}/messages")["messages"]


def test_a_question_to_something_that_is_not_a_function_or_too_long_is_j2s_400(fake_server, fake):
    fake.stage("full")
    for who in ("zed", "W-1", "", "Identity", "ADAPTATION", "web.identity"):
        assert ask(fake_server, who) == (400, {"error": "not a function"}), who
    assert j2_post(fake_server, ASK, {"q": "no one asked"})[0] == 400 and j2_post(fake_server, ASK, [])[0] == 400
    assert ask(fake_server, q="x" * 2001) == (400, {"error": "question too long"})
    assert ask(fake_server, q=" " + "x" * 2000 + " ")[0] == 200                                         # the ceiling is on what is left after trimming, as the engine's
    sid = agent_rows_of(fake)["adaptation"]["session_id"]
    assert [m["text"] for m in lines_of(fake, sid) if m.get("ask")] == ["x" * 2000, "From the records:"[:0] + j2_capture("ask-adaptation.json")["answer"]]


def test_a_question_to_a_function_with_a_session_is_answered_from_the_records_and_stored_as_two_lines_of_that_session(fake_server, fake):
    fake.stage("full")
    rows = agent_rows_of(fake)
    sid = rows["adaptation"]["session_id"]
    before = lines_of(fake, sid)
    captured = j2_capture("ask-adaptation.json")
    status, body = ask(fake_server, q="  Why was W-3\n scored   below the gate?  ")
    assert status == 200 and set(body) == {"who", "answer", "from", "session_id", "question_id", "answer_id"}
    assert (body["who"], body["answer"], body["from"], body["session_id"]) == ("adaptation", captured["answer"], "records", sid)
    after = lines_of(fake, sid)
    assert after[: len(before)] == before and len(after) == len(before) + 2                               # the lines are added to the transcript, never in place of one
    question, answer = after[-2:]
    assert (question["id"], answer["id"]) == (body["question_id"], body["answer_id"]) and answer["id"] == question["id"] + 1
    assert (question["role"], question["who"], question["kind"], question["text"], question["ask"]) == (
        "user", "user", "text", "Why was W-3 scored below the gate?", "q")                              # whitespace is one space, as `DeptCommands.ask` writes it
    assert (answer["role"], answer["who"], answer["kind"], answer["text"], answer["ask"]) == ("agent", "adaptation", "text", captured["answer"], "records")
    assert {k for k in question} == MESSAGE_KEYS | {"ask"} and {k for k in answer} == MESSAGE_KEYS | {"ask"}
    assert question["task_id"] == answer["task_id"] == rows["adaptation"]["task_id"] and RE_TS.match(question["at"]) and question["at"] <= answer["at"]
    assert all("ask" not in m for m in before)                                                          # a line that is no part of a question has no `ask`
    assert ok(fake, f"/api/chats/{sid}")["last_message_id"] == answer["id"]


@pytest.mark.parametrize("who", FUNCTIONS)
def test_each_of_the_five_functions_keeps_its_own_transcript_of_questions(fake_server, fake, who):
    fake.stage("full")
    rows = agent_rows_of(fake)
    sids = {row["session_id"] for row in rows.values()}
    status, body = ask(fake_server, who)
    assert status == 200 and body["session_id"] == rows[who]["session_id"] and body["answer"] == j2_capture(f"ask-{who}.json")["answer"]
    for other in sids - {body["session_id"]}:
        assert not any("ask" in m for m in lines_of(fake, other)), other                                # the question is in one session only


def test_both_lines_are_announced_the_question_first_so_the_node_panel_and_j2s_panel_read_one_transcript(fake_server, fake):
    fake.stage("full")
    sid = agent_rows_of(fake)["audit"]["session_id"]
    with Stream(fake_server.url, "/api/events?topics=chat,usage") as stream:
        status, body = ask(fake_server, "audit", "Which check failed?")
        frames = [f for f in stream.until("chat.message") + stream.until("chat.message") if f.get("event") == "chat.message"]
    assert status == 200 and len(frames) == 2
    first, second = (f["data"] for f in frames)
    assert first["session_id"] == second["session_id"] == sid
    assert (first["message"]["id"], first["message"]["ask"], first["message"]["role"]) == (body["question_id"], "q", "user")      # the event carries the line as the read does
    assert (second["message"]["id"], second["message"]["ask"], second["message"]["who"]) == (body["answer_id"], "records", "audit")
    assert first["message"] in lines_of(fake, sid) and second["message"] in lines_of(fake, sid)


def test_a_function_with_no_session_of_its_own_is_answered_and_nothing_is_stored(fake_server, fake):
    fake.stage("full")
    before = {sid: len(lines_of(fake, sid)) for sid in (row["session_id"] for row in agent_rows_of(fake).values())}
    status, body = ask(fake_server, "validator")                                                          # the validator is code: it has no session
    assert (status, body) == (200, j2_capture("ask-validator.json"))
    status, body = ask(fake_server, "adaptation", run=fb.PAST_RUN["run_id"])                              # the earlier run has Identity's and Audit's chats only
    assert (status, body) == (200, j2_capture("ask-adaptation.json"))
    status, body = ask(fake_server, "adaptation", dept="content")                                         # the fake keeps agents for the Web team
    assert (status, body) == (200, j2_capture("ask-adaptation.json"))
    assert {sid: len(lines_of(fake, sid)) for sid in before} == before
    assert ask(fake_server, q="   ") == (200, {"who": "adaptation", "answer": "", "from": "records"})      # nothing asked is nothing stored: J2's own empty answer
    assert {sid: len(lines_of(fake, sid)) for sid in before} == before


def test_an_earlier_runs_function_chat_takes_the_question_though_it_is_archived(fake_server, fake):
    fake.stage("full")
    status, body = ask(fake_server, "identity", run=fb.PAST_RUN["run_id"])
    assert status == 200 and body["session_id"] == "cs_past_identity"
    shown = ok(fake, "/api/chats/cs_past_identity")
    assert shown["status"] == "archived" and shown["writable"] is False                                   # the session stays read-only: only this route writes there
    lines = lines_of(fake, "cs_past_identity")
    assert [(m["role"], m.get("ask")) for m in lines[-2:]] == [("user", "q"), ("agent", "records")] and lines[-1]["task_id"] == fb.PAST_RUN["task_id"]
    assert agent_rows_of(fake, fb.PAST_RUN["run_id"])["identity"]["session_id"] == "cs_past_identity"
    error_of(fake.request("POST", "/api/chats/cs_past_identity/steer", {"text": "a note"}, token=True), 409, "not_running")   # a note is another box, and the run is over


def test_a_run_the_fake_does_not_know_is_the_current_run_as_the_engine_reads_it(fake_server, fake):
    fake.stage("full")
    sid = agent_rows_of(fake)["priority"]["session_id"]
    for run in ("", "j2-20261104-100004-7f3a", fb.LIVE_RUN["run_id"], "j2-not-a-run", "../x"):
        status, body = ask(fake_server, "priority", run=run)
        assert status == 200 and body["session_id"] == sid, run
    assert len([m for m in lines_of(fake, sid) if m.get("ask") == "q"]) == 5


def test_an_archived_team_takes_no_question(fake_server, fake, monkeypatch):
    fake.stage("full")

    class Row:
        id, name, archived = "web", "Web", True

    monkeypatch.setattr(fb._Services, "department", lambda self, dept_id: Row() if dept_id == "web" else None)
    status, _, raw = j2_post(fake_server, ASK, {"who": "adaptation", "q": "Why?"})
    assert status == 403 and json.loads(raw)["error"]["code"] == "read_only"                              # the engine's envelope for a write to a merged team
    sid = agent_rows_of(fake)["adaptation"]["session_id"]
    assert not any("ask" in m for m in lines_of(fake, sid))


def test_the_ask_control_sets_how_the_next_questions_are_answered_and_reset_puts_it_back(fake_server, fake):
    fake.stage("full")
    sid = agent_rows_of(fake)["coordination"]["session_id"]
    records = j2_capture("ask-coordination.json")["answer"]
    assert fake.post("/__fake/ask", {"mode": "offline"}, token=False)[1] == {"mode": "offline", "text": None, "note": None, "delay": 0.0, "fail": None}
    status, body = ask(fake_server, "coordination")
    assert status == 200 and body["note"] == "No model is connected." and (body["answer"], body["from"]) == (records, "records")
    assert lines_of(fake, sid)[-1]["ask"] == "records"                                                    # offline: both lines are stored all the same
    fake.post("/__fake/ask", {"mode": "offline", "note": "Your monthly limit is reached."}, token=False)
    assert ask(fake_server, "coordination")[1]["note"] == "Your monthly limit is reached."
    fake.post("/__fake/ask", {"mode": "failed", "note": None}, token=False)
    status, body = ask(fake_server, "coordination")
    assert body["note"].startswith("The model could not answer (") and body["note"].endswith("this is from the records only.") and body["from"] == "records"
    fake.post("/__fake/ask", {"mode": "records", "note": None}, token=False)
    assert "note" not in ask(fake_server, "coordination")[1]
    for bad in ({"mode": "guess"}, {"delay": -1}, {"delay": 31}, {"delay": True}, {"text": 5}, {"extra": 1}, {"fail": 200}, {"fail": "busy"}, []):
        assert fake.post("/__fake/ask", bad, token=False)[0] == 422, bad
    fake.post("/__fake/ask", {"mode": "offline", "delay": 2}, token=False)
    fake.reset()
    fake.stage("full")
    assert fake.post("/__fake/ask", {}, token=False)[1] == {"mode": "records", "text": None, "note": None, "delay": 0.0, "fail": None}
    assert not any("ask" in m for m in lines_of(fake, sid))                                               # the lines go with the story, as every other line does


def test_a_model_answer_is_stored_as_the_models_and_booked_to_the_agent_as_one_agent_chat_call(fake_server, fake):
    fake.stage("full")
    rows = agent_rows_of(fake)
    sid, usage = rows["audit"]["session_id"], rows["audit"]["usage"]
    assert "agent_chat" not in usage["by_purpose"]                                                       # no call, no key: as the real route has it
    fake.post("/__fake/ask", {"mode": "model", "text": "Item 4 was not met: the footer has no phone number."}, token=False)
    with Stream(fake_server.url, "/api/events?topics=usage") as stream:
        status, body = ask(fake_server, "audit", "Which check failed?")
        recorded = stream.until("usage.recorded")[-1]["data"]
    assert status == 200 and (body["answer"], body["from"]) == ("Item 4 was not met: the footer has no phone number.", "model") and "note" not in body
    lines = lines_of(fake, sid)
    assert [(m["role"], m["ask"]) for m in lines[-2:]] == [("user", "q"), ("agent", "model")] and lines[-1]["text"] == body["answer"]
    row = recorded["row"]
    assert (row["purpose"], row["session_id"], row["fn"], row["dept_id"], row["task_id"]) == ("agent_chat", sid, "audit", "web", fb.LIVE_RUN["task_id"])
    assert row["atom_id"] == overhead_atom_id(fb.LIVE_RUN["run_id"]) and row["usd"] == fb.ASK_CALL_USD         # an answer is overhead, never a work atom (D59)
    after = agent_rows_of(fake)["audit"]["usage"]
    assert after["by_purpose"]["agent_chat"] == {"calls": 1, "usd": fb.ASK_CALL_USD}
    assert after["calls"] == usage["calls"] + 1 and after["usd"] == pytest.approx(usage["usd"] + fb.ASK_CALL_USD)
    assert after["tokens_in"] == usage["tokens_in"] + fb.ASK_TOKENS[0] and after["tokens_out"] == usage["tokens_out"] + fb.ASK_TOKENS[1]
    assert recorded["task_total"]["calls"] == sum(r["usage"]["calls"] for r in agent_rows_of(fake).values())
    fake.post("/__fake/ask", {"mode": "model", "text": None}, token=False)                                # no text: the answer says what it was asked
    assert ask(fake_server, "audit", "Which check failed?")[1]["answer"] == "From its records: Which check failed?"
    assert agent_rows_of(fake)["audit"]["usage"]["by_purpose"]["agent_chat"]["calls"] == 2
    assert sum(g["calls"] for g in ok(fake, "/api/usage/summary", by="purpose")["groups"] if g["key"] == "agent_chat") == 2


def test_a_second_question_to_a_session_that_is_still_being_answered_is_409_busy(fake_server, fake):
    fake.stage("full")
    sid = agent_rows_of(fake)["adaptation"]["session_id"]
    fake.post("/__fake/ask", {"delay": 0.8}, token=False)
    first: list = []
    thread = threading.Thread(target=lambda: first.append(ask(fake_server, "adaptation", "First?")))
    thread.start()
    deadline = time.monotonic() + 5
    while not any(m.get("ask") == "q" for m in lines_of(fake, sid)):                                      # the question line is stored before the answer is made
        assert time.monotonic() < deadline, "the first question was never stored"
        time.sleep(0.02)
    assert ask(fake_server, "adaptation", "Second?") == (409, {"error": "busy"})
    assert ask(fake_server, "priority", "Another function?")[0] == 200                                    # one question at a time per session, not per team
    thread.join(10)
    assert first and first[0][0] == 200 and [m["text"] for m in lines_of(fake, sid) if m.get("ask") == "q"] == ["First?"]
    assert ask(fake_server, "adaptation", "Third?")[0] == 200                                             # the busy mark is gone with the answer


def test_an_interrupted_question_stays_without_an_answer_and_frees_the_session(fake_server, fake):
    fake.stage("full")
    sid = agent_rows_of(fake)["priority"]["session_id"]
    fake.post("/__fake/ask", {"mode": "interrupted"}, token=False)
    status, body = ask(fake_server, "priority", "Will this be answered?")
    assert status == 500 and body["error"]["code"] == "internal"
    lines = lines_of(fake, sid)
    assert [(m["role"], m.get("ask")) for m in lines if m.get("ask")] == [("user", "q")]                    # J2's panel says "No answer was stored." for it
    fake.post("/__fake/ask", {"mode": "records"}, token=False)
    assert ask(fake_server, "priority", "And now?")[0] == 200                                              # the session is free again


def test_a_refusal_the_test_asks_for_happens_once_before_anything_is_stored(fake_server, fake):
    fake.stage("full")
    sid = agent_rows_of(fake)["audit"]["session_id"]
    before = lines_of(fake, sid)
    assert fake.post("/__fake/ask", {"fail": 409}, token=False)[1]["fail"] == 409
    assert ask(fake_server, "audit") == (409, {"error": "busy"}) and lines_of(fake, sid) == before                 # J2's busy, and nothing stored
    assert ask(fake_server, "audit")[0] == 200                                                                  # once
    fake.post("/__fake/ask", {"fail": 500}, token=False)
    assert ask(fake_server, "audit", q="  ") == (200, {"who": "audit", "answer": "", "from": "records"})        # nothing asked: nothing refused, and it stays for the next
    assert ask(fake_server, "audit") == (500, {"error": "failed"})


# ---- sync 4: usage by purpose, in the agents rows and in the summary ------------------------------------------------------------------------------------
def test_an_agents_usage_names_its_calls_by_purpose_and_they_add_up(fake):
    fake.stage("full")
    for run in (None, fb.PAST_RUN["run_id"]):
        for agent, row in agent_rows_of(fake, run).items():
            usage = row["usage"]
            assert set(usage) == {"calls", "usd", "tokens_in", "tokens_out", "by_purpose"}, agent
            cells = usage["by_purpose"]
            assert list(cells) == sorted(cells) and set(cells) <= set(fb.PURPOSES), agent                      # the ledger's order (by purpose); only the purposes the agent was charged for
            assert all(set(cell) == {"calls", "usd"} and cell["calls"] > 0 for cell in cells.values())
            assert sum(c["calls"] for c in cells.values()) == usage["calls"], agent
            assert sum(c["usd"] for c in cells.values()) == pytest.approx(usage["usd"], abs=1e-3), agent
    rows = agent_rows_of(fake)
    assert {a: r["usage"]["by_purpose"]["judge"]["calls"] for a, r in rows.items() if "judge" in r["usage"]["by_purpose"]} == {"priority": 2, "coordination": 1}
    assert {a: r["usage"]["by_purpose"]["plan"]["calls"] for a, r in rows.items() if "plan" in r["usage"]["by_purpose"]} == {"adaptation": 2, "coordination": 1}
    assert all("agent_chat" not in r["usage"]["by_purpose"] for r in rows.values())                       # nobody has been asked anything
    assert rows["identity"]["usage"]["by_purpose"] == {"agent_turn": {"calls": 2, "usd": 0.01}}            # an agent that only worked: its turns, and nothing else named
    assert rows["coordination"]["usage"]["by_purpose"] == {"agent_turn": {"calls": 3, "usd": 0.024}, "judge": {"calls": 1, "usd": 0.008}, "plan": {"calls": 1, "usd": 0.008}}
    assert [(r["usage"]["calls"], r["usage"]["usd"]) for r in rows.values()][:5] == [(2, 0.01), (3, 0.02), (4, 0.03), (5, 0.04), (6, 0.05)]      # the totals a row always had


def test_the_usage_summary_groups_the_same_numbers_by_purpose_and_by_the_ledgers_other_keys(fake):
    fake.stage("full")
    rows = [*agent_rows_of(fake).values(), *agent_rows_of(fake, fb.PAST_RUN["run_id"]).values()]
    total = {"calls": sum(r["usage"]["calls"] for r in rows), "usd": sum(r["usage"]["usd"] for r in rows),
             "tokens_in": sum(r["usage"]["tokens_in"] for r in rows), "tokens_out": sum(r["usage"]["tokens_out"] for r in rows)}
    for by in ("purpose", "fn", "session", "day", "dept", "provider", "atom"):
        groups = ok(fake, "/api/usage/summary", by=by)["groups"]
        assert groups and all(set(g) == {"key", "calls", "usd", "tokens_in", "tokens_out"} for g in groups), by
        assert [g["key"] for g in groups] == sorted(g["key"] for g in groups) or groups[0]["key"] == "(none)", by       # key order, a row with no key first
        assert sum(g["calls"] for g in groups) == total["calls"] and sum(g["usd"] for g in groups) == pytest.approx(total["usd"], abs=1e-3), by
        assert sum(g["tokens_in"] for g in groups) == total["tokens_in"] and sum(g["tokens_out"] for g in groups) == total["tokens_out"], by
    purposes = {g["key"]: g for g in ok(fake, "/api/usage/summary", by="purpose")["groups"]}
    assert set(purposes) == {"agent_turn", "judge", "plan"} and purposes["judge"]["calls"] == 3 and purposes["plan"]["calls"] == 3      # agent_chat has no row until a model answers
    assert {g["key"] for g in ok(fake, "/api/usage/summary", by="provider")["groups"]} == {"claude"}
    assert {g["key"] for g in ok(fake, "/api/usage/summary", by="day")["groups"]} == {"2026-11-03", "2026-11-04"}
    atoms = {g["key"]: g for g in ok(fake, "/api/usage/summary", by="atom")["groups"]}
    assert atoms["(none)"]["calls"] == purposes["agent_turn"]["calls"]                                     # a turn's calls have atoms of their own; judging and planning are overhead
    assert atoms[overhead_atom_id(fb.LIVE_RUN["run_id"])]["calls"] == purposes["judge"]["calls"] + purposes["plan"]["calls"]
    assert next(iter(atoms)) == "(none)"                                                                   # a row without a key sorts first, as in the ledger's SQL


def test_the_real_model_reads_every_grouping_of_the_summary_and_writes_it_back_unchanged(fake):
    """The expected shape is the real model, which the real route builds its answer from: a key the fake added, or one it lacked, would fail here."""
    from sutra_app.orchestrator.api.usage import UsageSummary
    fake.stage("full")
    for by in fb.SUMMARY_BY:
        answer = ok(fake, "/api/usage/summary", by=by)
        assert UsageSummary.model_validate(answer).model_dump(mode="json") == answer and answer["groups"], by


def test_the_summary_takes_a_window_and_reads_it_as_the_real_route_does(fake):
    from sutra_app.orchestrator.usage import parse_since
    fake.stage("full")
    live, past = "2026-11-04T10:20:00Z", "2026-11-03T09:30:00Z"                                            # when the agents of the live run and of the earlier run last spoke
    keys = lambda **q: {g["key"]: g["calls"] for g in ok(fake, "/api/usage/summary", by="purpose", **q)["groups"]}  # noqa: E731
    everything = keys()
    assert keys(since=past) == everything and keys(since=live) == keys(since=str(parse_since(live)))        # a row exactly at `since` counts; ISO or seconds
    assert sum(everything.values()) > sum(keys(since=live).values()) > 0                                    # the earlier run's rows are out of the live window
    assert keys(since="2026-11-04T10:20:01Z") == {} == keys(since="4102444800")
    assert sum(g["calls"] for g in ok(fake, "/api/usage/summary", by="day", since=live)["groups"]) == sum(keys(since=live).values())     # every grouping has it


def test_the_fakes_reading_of_since_is_the_real_ones_for_every_text(fake):
    """Parity, text by text: the number the real `parse_since` makes of it is the one the fake makes, or both refuse (the route answers 422 `query.since`)."""
    from sutra_app.orchestrator.usage import parse_since
    fake.stage("full")
    texts = ("0", "1793786400", "253402300799", "253402300800", "99999999999999999999", "-1", "1e3", "", " 5", "5 ", "yesterday", "2026-11-04T10:00:06Z", "9999-12-31T23:59:59Z",
             "10000-01-01T00:00:00Z", "2026-11-04", "2026-11-04T10:20:00", "2026-13-01T00:00:00Z", "2026-11-04T10:00:06+00:00", "\u0663", "\u00b2")
    for text in texts:
        try:
            real = parse_since(text)
        except ValueError:
            real = None
        try:
            mine = fb.since_seconds(text)
        except ValueError:
            mine = None
        assert mine == real, text
        status, body = fake.get("/api/usage/summary", by="purpose", since=text)
        assert status == (200 if real is not None else 422), text
        if real is None:
            assert body["error"]["code"] == "validation" and body["error"]["details"]["violations"][0]["path"] == "query.since", text
            assert body["error"]["details"]["violations"][0]["code"] == "bad_time", text


def test_the_summary_of_one_session_and_a_bad_grouping(fake):
    fake.stage("full")
    sid = agent_rows_of(fake)["coordination"]["session_id"]
    groups = ok(fake, "/api/usage/summary", by="purpose", session_id=sid)["groups"]
    assert {g["key"]: g["calls"] for g in groups} == {"agent_turn": 3, "judge": 1, "plan": 1}
    assert ok(fake, "/api/usage/summary", by="purpose", session_id="cs_nobody") == {"groups": []}
    assert ok(fake, "/api/usage/summary") == ok(fake, "/api/usage/summary", by="dept") == {"groups": [{
        "key": "web", **{k: v for k, v in ok(fake, "/api/usage/summary", by="dept")["groups"][0].items() if k != "key"}}]}                    # dept is the default
    error = error_of(fake.get("/api/usage/summary", by="colour"), 422, "validation")
    assert error["details"]["violations"][0]["path"] == "query.by"
    assert ok(fake, "/api/usage/summary", by="fn", include_stub=1) == ok(fake, "/api/usage/summary", by="fn")                          # no stub rows exist here


# ---- sync 4 (D139): what the next run makes -------------------------------------------------------------------------------------------------------------------
def test_next_run_is_the_start_pages_choice_else_the_teams_setting_else_the_default(fake_server, fake):
    fake.stage("2")
    nxt = lambda: ok(fake, "/api/engine/settings", dept="web")["next_run"]  # noqa: E731
    assert nxt() == {"output": "auto"} and "next_run" not in ok(fake, "/api/engine/settings")              # a team's view only: "all teams" has no next run
    fake.request("PUT", "/api/engine/settings?dept=web", {"set": {"output": "prd"}}, token=True)
    assert nxt() == {"output": "prd"}                                                                       # the team's own setting
    assert json.loads(j2_post(fake_server, "/api/output", {"type": "website"})[2]) == {"ok": True, "output": "website"}
    assert nxt() == {"output": "website"}                                                                   # what was picked on the start page wins
    assert ok(fake, "/api/engine/settings", dept="web")["effective"]["output"] == "prd"                    # and the setting is untouched: a pick is for the next run only
    assert j2_post(fake_server, "/api/output", {"type": "poster"})[0] == 409 and nxt() == {"output": "website"}   # a refused pick changes nothing
    for kind in ("auto", "project", "hld"):
        j2_post(fake_server, "/api/output", {"type": kind})
        assert nxt() == {"output": kind}
    status, answer = fake.request("PUT", "/api/engine/settings?dept=web", {"set": {"budget": 99}}, token=True)
    assert answer["next_run"] == {"output": "hld"}                                                          # the answer of a save is the same view


def test_a_team_that_has_started_closes_the_choice_and_a_follow_up_clears_it(fake_server, fake):
    fake.stage("2")
    assert fake.post("/__fake/output", {"locked": "yes"}, token=False)[0] == 422 and fake.post("/__fake/output", {}, token=False)[0] == 422
    assert fake.post("/__fake/output", {"locked": True}, token=False)[1] == {"locked": True}
    status, _, raw = j2_post(fake_server, "/api/output", {"type": "prd"})
    assert (status, json.loads(raw)) == (409, {"ok": False, "output": "auto"})                              # 409 names what the run makes
    assert ok(fake, "/api/engine/settings", dept="web")["next_run"] == {"output": "auto"}
    fake.post("/__fake/output", {"locked": False}, token=False)
    assert j2_post(fake_server, "/api/output", {"type": "prd"})[0] == 200
    fake.stage("full")
    j2_post(fake_server, "/api/output", {"type": "prd"}, dept="content")
    assert ok(fake, "/api/engine/settings", dept="content")["next_run"] == {"output": "prd"}
    assert j2_post(fake_server, "/api/say", {"text": "Add a gallery"}, dept="content")[0] == 200            # a follow-up created a task: the pick has been used
    assert ok(fake, "/api/engine/settings", dept="content")["next_run"] == {"output": "auto"}
    fake.reset()
    fake.stage("2")
    fake.post("/__fake/output", {"locked": True}, token=False)
    fake.reset()
    fake.stage("2")
    assert j2_post(fake_server, "/api/output", {"type": "prd"})[0] == 200                                   # reset with the story


# ---- the file runs as a script (the motion probe starts it by hand) ---------------------------------------------------------------------------------------------
def test_the_file_runs_as_a_script_so_a_page_can_be_looked_at_by_hand(monkeypatch):
    """`scripts/py tests/ui/fake_backend.py --port 8791 --stage full` once failed with a NameError: its main guard sat above the agent-sessions block, which was
    not defined yet when the guard ran. Run the file as a program with the server stubbed out: it must build the app and serve it."""
    import runpy

    served: dict = {}
    monkeypatch.setattr(fb.uvicorn, "run", lambda app, **kw: served.update(app=app, **kw))
    monkeypatch.setattr(sys, "argv", ["fake_backend.py", "--port", "8791", "--stage", "full"])
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(fb.__file__, run_name="__main__")
    assert stopped.value.code == 0 and served["port"] == 8791 and served["host"] == "127.0.0.1"
    assert served["app"].state.fake.stages()["graph"] == "full"
    source = Path(fb.__file__).read_text(encoding="utf-8").rstrip().splitlines()
    assert source[-2:] == ['if __name__ == "__main__":', "    raise SystemExit(main())"]                       # the guard is the last statement: nothing is defined after it


# =====================================================================================================================
# 5. The real UI package mounted on the fake
# =====================================================================================================================
HOME_HTML = ('<!doctype html><html><head><meta charset="utf-8"><title>Home</title><!--SUTRA-BOOT--></head>'
             '<body><script>var home = 1;</script></body></html>')
DEPT_HTML = ('<!doctype html><html><head><meta charset="utf-8"><title>Team</title><!--SUTRA-BOOT--></head>'
             '<body><script>var theme = 1;</script>\n<script>var main = 2;</script></body></html>')


def boot_of(html: str) -> dict:
    match = re.search(r'<script type="application/json" id="sutra-boot">(.*?)</script>', html, re.S)
    assert match, html
    return json.loads(match.group(1))


def script_hash(source: str) -> str:
    return "'sha256-" + base64.b64encode(hashlib.sha256(source.encode()).digest()).decode() + "'"


def build_ui_tree(root: Path):
    """A pages folder and a static folder of their own: the real pages belong to other work packages."""
    pages, static = root / "pages", root / "static"
    (static / "js").mkdir(parents=True)
    (static / "vendor").mkdir()
    pages.mkdir()
    (pages / "home.html").write_text(HOME_HTML, encoding="utf-8")
    (pages / "j2_ui.html").write_text(DEPT_HTML, encoding="utf-8")
    (static / "js" / "probe.js").write_text("window.probe = 1;\n", encoding="utf-8")
    (static / "vendor" / "d3.min.js").write_text("/* d3 */\n", encoding="utf-8")
    return pages, static


@pytest.fixture()
def ui_tree(tmp_path):
    return build_ui_tree(tmp_path)


@pytest.fixture(scope="module")
def ui_server(tmp_path_factory):
    """One fake whose pages and static files are small stand-ins, with its own token and version."""
    pages, static = build_ui_tree(tmp_path_factory.mktemp("ui"))
    app = fb.make_app(pages_dir=pages, static_dir=static, token="t" * 24, version="9.8.7")
    running = fb.run_in_thread(app)
    try:
        yield running.url, FakeClient(running.url, "t" * 24), app.state.fake
    finally:
        running.stop()


@pytest.fixture()
def ui(ui_server):
    ui_server[1].reset()
    return ui_server


def test_the_pages_come_from_the_real_ui_router_with_the_fakes_token_and_version(ui):
    url, client, state = ui
    client.stage("2")
    status, headers, raw = raw_request(url, "GET", "/")
    page = raw.decode()
    assert status == 200 and headers["content-type"].startswith("text/html") and headers["cache-control"] == "no-store"
    assert boot_of(page) == {"page": "home", "token": "t" * 24, "dept": "", "dept_label": "", "archived": False, "note": "", "version": "9.8.7"}
    policy = headers["content-security-policy"]
    assert script_hash("var home = 1;") in policy and "'unsafe-inline'" not in policy.split(";")[1]  # the script-src directive
    status, headers, raw = raw_request(url, "GET", "/d/web/")
    page = raw.decode()
    assert status == 200 and boot_of(page)["page"] == "dept" and boot_of(page)["dept"] == "web" and boot_of(page)["dept_label"] == "Web"
    policy = headers["content-security-policy"]
    assert script_hash("var theme = 1;") in policy and script_hash("var main = 2;") in policy  # both attribute-less scripts
    assert "<!--SUTRA-BOOT-->" not in page


def test_a_team_page_exists_only_while_the_graph_has_that_team(ui):
    url, client, state = ui
    status, headers, raw = raw_request(url, "GET", "/d/web/")
    assert status == 404 and b"No team called" in raw and headers["cache-control"] == "no-store"  # stage 1: no teams yet
    client.stage("2")
    assert raw_request(url, "GET", "/d/web/")[0] == 200
    assert raw_request(url, "GET", "/d/content/")[0] == 404  # the Content team comes with the full story
    client.stage("full")
    page = raw_request(url, "GET", "/d/content/")[2].decode()
    assert boot_of(page)["dept"] == "content" and boot_of(page)["dept_label"] == "Content"
    for dept in ("nosuchteam", "root", "web.identity"):
        assert raw_request(url, "GET", f"/d/{dept}/")[0] == 404, dept  # a node that is not a team is no team


def test_the_redirects_static_files_and_the_favicon_are_the_real_routers(ui):
    url, client, state = ui
    client.stage("2")
    status, headers, _ = raw_request(url, "GET", "/d/web?view=detail&run=x")
    assert status == 308 and headers["location"] == "/d/web/?view=detail&run=x" and headers["cache-control"] == "no-store"
    status, headers, _ = raw_request(url, "GET", "/?dept=web&view=simple")
    assert status == 308 and headers["location"] == "/d/web/?view=simple"
    assert raw_request(url, "GET", "/?dept=nosuch")[0] == 200  # Home, with `dept` ignored
    status, headers, raw = raw_request(url, "GET", "/ui/js/probe.js")
    assert (status, raw, headers["cache-control"]) == (200, b"window.probe = 1;\n", "no-cache")
    status, headers, _ = raw_request(url, "GET", "/ui/vendor/d3.min.js")
    assert status == 200 and headers["cache-control"] == "max-age=3600"
    for path in ("/ui/%2e%2e/pages/home.html", "/ui/../pages/home.html", "/ui/js/nothing.js", "/ui/pages/home.html"):
        assert raw_request(url, "GET", path)[0] == 404, path
    assert raw_request(url, "GET", "/favicon.ico")[0] == 204
    assert raw_request(url, "HEAD", "/")[0] == 200


def test_the_page_token_is_the_one_every_write_of_the_fake_wants(ui):
    url, client, state = ui
    token = boot_of(raw_request(url, "GET", "/")[2].decode())["token"]
    headers = {"Content-Type": "application/json"}
    assert raw_request(url, "POST", "/api/chats/cs_org/retry", headers={**headers, "X-Sutra-Token": token}, body=b"{}")[0] == 202
    assert raw_request(url, "POST", "/api/chats/cs_org/retry", headers={**headers, "X-Sutra-Token": fb.TOKEN}, body=b"{}")[0] == 401
    assert client.token == token and state.token == token


def test_a_pages_folder_alone_or_a_static_folder_alone_leaves_the_other_at_its_default(make_fake_server, ui_tree):
    pages, static = ui_tree
    only_pages = make_fake_server(pages_dir=pages)
    assert raw_request(only_pages.url, "GET", "/")[0] == 200
    status, headers, raw = raw_request(only_pages.url, "GET", "/ui/js/sutra_ctx.js")  # the real client core, merged by UI-3
    assert status == 200 and raw == (REPO / "sutra_app" / "ui" / "static" / "js" / "sutra_ctx.js").read_bytes()
    assert headers["cache-control"] == "no-cache"
    only_static = make_fake_server(static_dir=static)
    assert raw_request(only_static.url, "GET", "/ui/js/probe.js")[0] == 200
    assert raw_request(only_static.url, "GET", "/ui/js/sutra_ctx.js")[0] == 404


def test_without_options_the_fake_mounts_the_ui_package_with_the_folders_it_names(make_fake_server, ui_tree, monkeypatch):
    import sutra_app.ui as ui

    pages, static = ui_tree
    monkeypatch.setattr(ui, "PAGES_DIR", pages)  # `mount` reads them when it runs
    monkeypatch.setattr(ui, "STATIC_DIR", static)
    server = make_fake_server()
    assert raw_request(server.url, "GET", "/")[0] == 200
    assert raw_request(server.url, "GET", "/ui/js/probe.js")[0] == 200


@pytest.mark.parametrize("page,path", [("home.html", "/"), ("j2_ui.html", "/d/web/")])
def test_the_real_pages_are_served_once_their_work_packages_have_merged(make_fake_server, page, path):
    from sutra_app.ui import PAGES_DIR

    if not (PAGES_DIR / page).is_file():
        pytest.skip(f"sutra_app/ui/pages/{page} is not merged yet (UI-7 owns home.html, UI-2 owns j2_ui.html)")
    server = make_fake_server()
    server.client.stage("2")
    status, headers, raw = raw_request(server.url, "GET", path)
    page_html = raw.decode()
    assert status == 200 and "<!--SUTRA-BOOT-->" not in page_html and boot_of(page_html)["token"] == fb.TOKEN
    hashes = inline_hashes(page_html)
    assert all(h in headers["content-security-policy"] for h in hashes)


def inline_hashes(page_html: str) -> list[str]:
    from sutra_app.ui import inline_script_hashes

    return inline_script_hashes(page_html)


# ---- the fixtures folder is an option ------------------------------------------------------------------------------------------
def fixtures_copy(tmp_path, *, with_j2=True) -> Path:
    target = tmp_path / "fixtures"
    shutil.copytree(FIXTURES, target, ignore=None if with_j2 else shutil.ignore_patterns("j2", "tools"))
    return target


def test_make_app_reads_the_fixtures_folder_it_is_given(tmp_path, make_fake_server):
    folder = fixtures_copy(tmp_path, with_j2=False)
    health = json.loads((folder / "health.json").read_text())
    health["version"] = "from-the-copy"
    (folder / "health.json").write_text(json.dumps(health), encoding="utf-8")
    server = make_fake_server(fixtures_dir=folder)
    assert server.client.get("/api/health")[1]["version"] == "from-the-copy"
    assert make_fake_server().client.get("/api/health")[1]["version"] == "0.1.0"  # the default folder is untouched


def test_a_missing_or_broken_fixture_is_a_fixture_error_that_names_the_file(tmp_path):
    folder = fixtures_copy(tmp_path)
    (folder / "needs-you.json").unlink()
    with pytest.raises(fb.FixtureError, match=rf"^fixture needs-you\.json is missing in {re.escape(str(folder))}$"):
        fb.make_app(folder)
    folder = fixtures_copy(tmp_path / "second")
    (folder / "departments.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(fb.FixtureError, match=r"^fixture departments\.json is not valid JSON: "):
        fb.make_app(folder)
    folder = fixtures_copy(tmp_path / "third")
    for path in folder.glob("chart.v*.json"):
        path.unlink()
    with pytest.raises(fb.FixtureError, match=rf"^no chart\.v\*\.json in {re.escape(str(folder))}$"):
        fb.make_app(folder)


def test_without_the_j2_captures_the_j2_routes_say_which_script_makes_them(tmp_path, make_fake_server):
    server = make_fake_server(fixtures_dir=fixtures_copy(tmp_path, with_j2=False))
    server.client.stage("2")
    status, body = server.client.get("/api/state", dept="web")
    assert (status, body) == (404, {"error": "no J2 fixture state.json: run scripts/capture_j2_fixtures.py"})
    assert server.client.get("/api/chart")[0] == 200  # everything else works without them
    assert server.client.get("/api/preview", dept="web", atom="W-2.a1") == (200, {"anchor": None, "html": None})
    assert server.client.get("/api/runs", dept="web")[0] == 404
    status, body = server.client.get("/api/agent", dept="web", who="zed")
    assert (status, body) == (404, {"error": "no J2 fixture agent-unknown.json: run scripts/capture_j2_fixtures.py"})
    assert server.client.get("/api/agent", dept="web", who="identity")[0] == 404


# =====================================================================================================================
# 6. cdp.py: the Chrome driver, against a stand-in DevTools endpoint and a stand-in Chrome (no Chrome needed)
# =====================================================================================================================
@pytest.fixture()
def devtools():
    with fdt.FakeDevTools() as endpoint:
        yield endpoint


@pytest.fixture()
def tab(devtools):
    """A Browser attached to the stand-in endpoint (3 s patience, so a mistake fails fast)."""
    with cdp.Browser(ws_url=devtools.url, timeout=3) as browser:
        yield browser


@pytest.fixture()
def fake_chrome(tmp_path, monkeypatch):
    """A program that starts like Chrome. The environment variable FAKE_CHROME_MODE (see fake_devtools.chrome_main) picks how."""
    script = tmp_path / "fake-chrome"
    script.write_text(f"#!{sys.executable}\nimport sys\nsys.path.insert(0, {str(TOOLS)!r})\nimport fake_devtools\n"
                      "sys.exit(fake_devtools.chrome_main(sys.argv[1:]))\n", encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setenv("FAKE_CHROME_LOG", str(tmp_path / "chrome-run.json"))
    monkeypatch.delenv("FAKE_CHROME_MODE", raising=False)
    return script


def chrome_log(fake_chrome) -> dict:
    return json.loads((fake_chrome.parent / "chrome-run.json").read_text(encoding="utf-8"))


def pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


# ---- finding Chrome ----------------------------------------------------------------------------------------------------------
def make_executable(path: Path, text: str = "#!/bin/sh\n") -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(0o755)
    return str(path)


def test_chrome_candidates_come_in_the_documented_order(tmp_path):
    home = tmp_path / "home"
    root = tmp_path / "pw"
    paths = [
        make_executable(root / "chromium-1100" / "chrome-mac" / "Chromium.app" / "Contents" / "MacOS" / "Chromium"),
        make_executable(root / "chromium-1234" / "chrome-mac-arm64" / "Chromium.app" / "Contents" / "MacOS" / "Chromium"),
        make_executable(root / "chromium-1234" / "chrome-linux" / "chrome"),
        make_executable(root / "chromium_headless_shell-1234" / "chrome-headless-shell-mac-arm64" / "chrome-headless-shell"),
        make_executable(root / "chromium_headless_shell-1234" / "chrome-mac" / "headless_shell"),
        make_executable(root / "chromium_headless_shell-1234" / "chrome-linux" / "headless_shell"),
    ]
    library = make_executable(home / "Library" / "Caches" / "ms-playwright" / "chromium-9" / "chrome-linux" / "chrome")
    dotcache = make_executable(home / ".cache" / "ms-playwright" / "chromium-8" / "chrome-linux" / "chrome")
    found = {"google-chrome": "/usr/bin/google-chrome", "chromium": "/usr/bin/chromium"}
    env = {"SUTRA_CHROME": "/opt/mine/chrome", "PLAYWRIGHT_BROWSERS_PATH": str(root)}
    candidates = cdp.chrome_candidates(env, which=found.get, home=home)
    assert candidates[:4] == ["/opt/mine/chrome", cdp.MAC_CHROME, "/usr/bin/google-chrome", "/usr/bin/chromium"]
    assert candidates[4:] == [  # the folder from the environment first, each pattern newest build first, then the two default folders
        paths[1], paths[0],  # chromium-*/chrome-mac*/Chromium.app
        paths[2],            # chromium-*/chrome-linux*/chrome
        paths[3],            # chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell
        paths[4], paths[5],  # the two headless_shell patterns
        library, dotcache,
    ]
    # nothing known: only the macOS app (a candidate is a guess, `find_chrome` checks it)
    assert cdp.chrome_candidates({}, which=lambda name: None, home=tmp_path / "nowhere") == [cdp.MAC_CHROME]
    assert cdp.chrome_candidates({"SUTRA_CHROME": ""}, which=lambda name: None, home=tmp_path / "nowhere") == [cdp.MAC_CHROME]


def test_chrome_candidates_sort_the_builds_of_one_pattern_newest_first(tmp_path):
    root = tmp_path / "pw"
    old = make_executable(root / "chromium-1100" / "chrome-linux" / "chrome")
    new = make_executable(root / "chromium-1234" / "chrome-linux" / "chrome")
    candidates = cdp.chrome_candidates({"PLAYWRIGHT_BROWSERS_PATH": str(root)}, which=lambda name: None, home=tmp_path / "home")
    assert candidates[1:] == [new, old]


def test_find_chrome_returns_the_first_candidate_that_exists_and_can_run(tmp_path, monkeypatch):
    monkeypatch.setattr(cdp, "MAC_CHROME", str(tmp_path / "no-mac-chrome"))
    ghost = str(tmp_path / "ghost")
    not_runnable = tmp_path / "not-runnable"
    not_runnable.write_text("#!/bin/sh\n")
    not_runnable.chmod(0o644)
    folder = tmp_path / "a-folder"
    folder.mkdir()
    good = make_executable(tmp_path / "good")
    later = make_executable(tmp_path / "later")
    found = {"chromium": later}
    none = lambda name: None  # noqa: E731
    assert cdp.find_chrome({"SUTRA_CHROME": good}, which=found.get, home=tmp_path) == good
    assert cdp.find_chrome({"SUTRA_CHROME": ghost}, which=found.get, home=tmp_path) == later  # missing: skipped
    assert cdp.find_chrome({"SUTRA_CHROME": str(not_runnable)}, which=found.get, home=tmp_path) == later  # not executable: skipped
    assert cdp.find_chrome({"SUTRA_CHROME": str(folder)}, which=found.get, home=tmp_path) == later  # a folder is no program
    assert cdp.find_chrome({}, which=none, home=tmp_path) is None
    assert cdp.find_chrome({"SUTRA_CHROME": ghost}, which=none, home=tmp_path) is None


def test_the_candidates_read_the_process_environment_and_the_users_home_when_not_told_otherwise(monkeypatch, tmp_path):
    monkeypatch.setattr(cdp.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)
    monkeypatch.delenv("SUTRA_CHROME", raising=False)
    playwright = make_executable(tmp_path / ".cache" / "ms-playwright" / "chromium-7" / "chrome-linux" / "chrome")
    assert cdp.chrome_candidates(which=lambda name: None) == [cdp.MAC_CHROME, playwright]
    monkeypatch.setenv("SUTRA_CHROME", "/from/the/environment")
    assert cdp.chrome_candidates(which=lambda name: None)[0] == "/from/the/environment"
    mine = make_executable(tmp_path / "mine")
    monkeypatch.setenv("SUTRA_CHROME", mine)
    assert cdp.find_chrome() == mine


# ---- the connection -----------------------------------------------------------------------------------------------------------
def test_starting_enables_the_four_domains_and_sets_the_default_size(devtools):
    with cdp.Browser(ws_url=devtools.url, timeout=3) as browser:
        assert browser.pid is None and browser.size == (1280, 900)
        assert devtools.methods() == ["Page.enable", "Runtime.enable", "Network.enable", "Log.enable", "Emulation.setDeviceMetricsOverride"]
        assert devtools.calls("Emulation.setDeviceMetricsOverride") == [{"width": 1280, "height": 900, "deviceScaleFactor": 1, "mobile": False}]
        browser.start()  # a second start does nothing
        assert len(devtools.methods()) == 5
    with cdp.Browser(ws_url=devtools.url, size=(390, 800), timeout=3):
        assert devtools.calls("Emulation.setDeviceMetricsOverride")[-1]["width"] == 390


def test_a_picture_far_bigger_than_the_default_message_limit_still_arrives(tab, devtools, tmp_path):
    big = fdt.PNG_BYTES + b"x" * (3 * 1024 * 1024)  # websockets refuses 1 MiB messages unless told otherwise
    devtools.screenshot = base64.b64encode(big).decode()
    assert tab.shot(tmp_path / "big.png").read_bytes() == big


def test_the_connection_to_chrome_ignores_the_proxy_settings_of_the_environment(devtools, monkeypatch):
    for name in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY", "all_proxy", "ALL_PROXY", "ws_proxy", "WS_PROXY"):
        monkeypatch.setenv(name, "http://127.0.0.1:9")  # nothing listens there
    monkeypatch.delenv("no_proxy", raising=False)
    monkeypatch.delenv("NO_PROXY", raising=False)
    with cdp.Browser(ws_url=devtools.url, timeout=5) as browser:
        assert browser.js("1") is None  # connected and talking (the stand-in answers undefined)


def test_the_documented_waits_are_the_defaults():
    import inspect

    assert cdp.Browser().timeout == 15.0 and cdp.Browser().size == (1280, 900) and cdp.Browser().dialogs == []
    wait = inspect.signature(cdp.Browser.wait_for).parameters
    assert (wait["timeout"].default, wait["interval"].default) == (10.0, 0.05)
    assert cdp.STOP_GRACE_S == 5.0 and cdp.STARTUP_S == 20.0
    assert (cdp.THEMES, cdp.SCHEMES, cdp.THEME_KEY) == (("light", "dark", "system"), ("light", "dark"), "j2theme")


def test_a_browser_that_is_closed_cannot_send_and_closing_twice_is_fine(devtools):
    browser = cdp.Browser(ws_url=devtools.url, timeout=3)
    with pytest.raises(cdp.BrowserError, match=r"^Runtime\.evaluate: the browser is not started$"):
        browser.js("1")
    browser.start()
    browser.close()
    browser.close()
    with pytest.raises(cdp.BrowserError, match=r"^Runtime\.evaluate: the browser is not started$"):
        browser.js("1")


def test_leaving_the_with_block_closes_the_connection(devtools):
    with cdp.Browser(ws_url=devtools.url, timeout=3) as browser:
        devtools.wait_for_client()
    deadline = time.monotonic() + 3
    while devtools._connections and time.monotonic() < deadline:
        time.sleep(0.01)
    assert devtools._connections == []
    assert browser._conn is None


def test_a_connection_that_cannot_be_made_is_a_browser_error():
    browser = cdp.Browser(ws_url="ws://127.0.0.1:9/devtools/page/none", timeout=2)
    with pytest.raises(cdp.BrowserError, match=r"^cannot connect to ws://127\.0\.0\.1:9/devtools/page/none: "):
        browser.__enter__()
    assert browser._conn is None  # nothing is left half open


def test_a_failed_start_inside_with_closes_what_it_opened(devtools):
    devtools.fail["Network.enable"] = "no network domain"
    browser = cdp.Browser(ws_url=devtools.url, timeout=3)
    with pytest.raises(cdp.BrowserError, match=r"^Network\.enable: no network domain$"):
        browser.__enter__()
    assert browser._conn is None


def test_a_protocol_error_names_the_command_and_chromes_words(tab, devtools):
    devtools.fail["Page.captureScreenshot"] = "Unable to capture screenshot"
    with pytest.raises(cdp.BrowserError, match=r"^Page\.captureScreenshot: Unable to capture screenshot$"):
        tab._send("Page.captureScreenshot")


def test_a_command_chrome_never_answers_times_out_with_its_name(devtools):
    devtools.silent.add("Runtime.evaluate")
    with cdp.Browser(ws_url=devtools.url, timeout=0.4) as browser:
        start = time.monotonic()
        with pytest.raises(cdp.BrowserError, match=r"^Runtime\.evaluate: no answer from Chrome within 0\.4 s$"):
            browser.js("1")
        assert time.monotonic() - start < 20
        with pytest.raises(cdp.BrowserError, match=r"^Runtime\.evaluate: no answer from Chrome within 0\.1 s$"):
            browser._send("Runtime.evaluate", {"expression": "1"}, timeout=0.1)  # a per-command patience wins
        assert browser._conn._pending == {}  # nothing waits for the answer any more


def test_a_chrome_that_goes_away_releases_a_waiting_call_and_refuses_the_next(devtools):
    devtools.silent.add("Runtime.evaluate")
    with cdp.Browser(ws_url=devtools.url, timeout=5) as browser:
        threading.Timer(0.2, devtools.drop_clients).start()
        with pytest.raises(cdp.BrowserError, match="^Runtime\\.evaluate: the connection to Chrome closed$"):
            browser.js("1")
        deadline = time.monotonic() + 3
        while not browser._conn.closed and time.monotonic() < deadline:
            time.sleep(0.01)
        assert browser._conn.closed
        with pytest.raises(cdp.BrowserError, match=r"^Runtime\.evaluate: the connection to Chrome is closed$"):
            browser.js("2")
        browser._conn.post("Runtime.evaluate", {"expression": "3"})  # a post to a closed connection is dropped quietly


def test_a_listener_that_throws_does_not_stop_the_events_that_follow(tab, devtools):
    devtools.push("Runtime.consoleAPICalled", {"type": "error", "args": ["a string, not an object"]})  # _remote_text raises on it
    devtools.push("Runtime.consoleAPICalled", {"type": "error", "args": [{"type": "string", "value": "still heard"}]})
    wait_until(lambda: tab.console_errors == ["still heard"])


def wait_until(check, timeout: float = 15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.01)
    raise AssertionError("the condition did not become true")


# ---- the page ------------------------------------------------------------------------------------------------------------------
def test_goto_navigates_and_waits_for_the_load_event(tab, devtools):
    tab.goto("http://127.0.0.1:1/x")
    assert devtools.calls("Page.navigate") == [{"url": "http://127.0.0.1:1/x"}]
    tab.goto("http://127.0.0.1:1/y", timeout=1)  # the event of the first load does not count for the second
    assert [c["url"] for c in devtools.calls("Page.navigate")] == ["http://127.0.0.1:1/x", "http://127.0.0.1:1/y"]


def test_goto_raises_timeout_when_the_page_never_finishes_loading(tab, devtools):
    devtools.after["Page.navigate"] = []
    start = time.monotonic()
    with pytest.raises(TimeoutError, match=r"^http://127\.0\.0\.1:1/slow did not finish loading within 0\.3 s$"):
        tab.goto("http://127.0.0.1:1/slow", timeout=0.3)
    assert time.monotonic() - start < 20


def test_goto_raises_browser_error_when_chrome_cannot_open_the_address(tab, devtools):
    devtools.navigate_result = {"frameId": "f", "errorText": "net::ERR_CONNECTION_REFUSED"}
    with pytest.raises(cdp.BrowserError, match=r"^cannot open http://127\.0\.0\.1:1/: net::ERR_CONNECTION_REFUSED$"):
        tab.goto("http://127.0.0.1:1/")


def test_goto_does_not_wait_for_a_load_when_only_the_hash_changes(tab, devtools):
    devtools.after["Page.navigate"] = []  # and no load event will come
    devtools.navigate_result = {"frameId": "f"}  # no loaderId: the same document
    tab.goto("http://127.0.0.1:1/x#orgchart", timeout=10)  # would raise TimeoutError if it waited for a load
    assert devtools.calls("Page.navigate") == [{"url": "http://127.0.0.1:1/x#orgchart"}]


def test_reload_waits_for_the_load_event_and_times_out_without_one(tab, devtools):
    tab.reload()
    assert devtools.methods().count("Page.reload") == 1
    devtools.after["Page.reload"] = []
    with pytest.raises(TimeoutError, match=r"^the page did not finish loading within 0\.3 s$"):
        tab.reload(timeout=0.3)


def test_js_returns_the_value_and_asks_for_the_right_things(tab, devtools):
    devtools.values.update({"1 + 1": 2, "'text'": "text", "({a: 1})": {"a": 1}, "[1, 2]": [1, 2], "true": True, "void 0": None})
    assert tab.js("1 + 1") == 2 and tab.js("'text'") == "text" and tab.js("({a: 1})") == {"a": 1}
    assert tab.js("[1, 2]") == [1, 2] and tab.js("true") is True and tab.js("void 0") is None
    assert devtools.calls("Runtime.evaluate")[0] == {"expression": "1 + 1", "returnByValue": True, "awaitPromise": True, "userGesture": True}


def test_js_raises_the_pages_own_error_text(tab, devtools):
    devtools.values["boom()"] = fdt.ScriptError("ReferenceError: boom is not defined\n    at <anonymous>:1:1")
    with pytest.raises(cdp.JSError, match="^ReferenceError: boom is not defined\\n    at <anonymous>:1:1$"):
        tab.js("boom()")
    assert issubclass(cdp.JSError, cdp.BrowserError)


def test_js_falls_back_to_the_details_text_and_then_to_a_generic_one(tab, devtools):
    original = devtools._evaluate
    devtools._evaluate = lambda expression: {"exceptionDetails": {"text": "Uncaught SyntaxError"}}
    with pytest.raises(cdp.JSError, match="^Uncaught SyntaxError$"):
        tab.js("(")
    devtools._evaluate = lambda expression: {"exceptionDetails": {}}
    with pytest.raises(cdp.JSError, match="^script error$"):
        tab.js("(")
    devtools._evaluate = original


def test_wait_for_returns_the_first_truthy_value_and_keeps_asking_until_then(tab, devtools):
    answers = iter([None, 0, "", False, "ready"])
    devtools.hook = lambda expression: next(answers) if expression == "page.ready" else None
    assert tab.wait_for("page.ready", timeout=3, interval=0.01) == "ready"
    assert len(devtools.calls("Runtime.evaluate")) == 5


def test_wait_for_swallows_script_errors_while_the_page_is_not_ready_and_reports_the_last_one(tab, devtools):
    answers = iter([fdt.ScriptError("TypeError: x is undefined"), True])
    devtools.hook = lambda expression: next(answers)
    assert tab.wait_for("x.y", timeout=3, interval=0.01) is True
    devtools.values["never()"] = fdt.ScriptError("ReferenceError: never is not defined")
    devtools.push("Runtime.consoleAPICalled", {"type": "error", "args": [{"type": "string", "value": "page said no"}]})
    wait_until(lambda: tab.console_errors)
    with pytest.raises(TimeoutError) as caught:
        tab.wait_for("never()", timeout=0.2, interval=0.01)
    message = str(caught.value)
    assert "wait_for('never()') was still false after 0.2 s" in message
    assert "last script error: ReferenceError: never is not defined" in message and "console errors: ['page said no']" in message


def test_wait_for_says_nothing_extra_when_there_was_no_error_to_report(tab, devtools):
    with pytest.raises(TimeoutError) as caught:
        tab.wait_for("false", timeout=0.1, interval=0.01)
    assert str(caught.value) == "wait_for('false') was still false after 0.1 s"


def test_exists_count_and_text_put_the_selector_into_the_script_as_a_json_string(tab, devtools):
    selector = 'a[title="x\\y"]'  # a quote and a backslash: only a JSON string survives both
    quoted = json.dumps(selector)
    seen = []

    def page(expression):
        seen.append(expression)
        if quoted not in expression:
            return None
        return {"querySelectorAll": 3, "querySelector": "Hello"}["querySelectorAll" if "querySelectorAll" in expression else "querySelector"]

    devtools.hook = page
    assert tab.count(selector) == 3
    assert tab.text(selector) == "Hello" and tab.exists(selector) is True  # "Hello" is truthy
    assert all(quoted in expression for expression in seen) and len(seen) == 3
    devtools.hook = lambda expression: None
    assert tab.exists("#none") is False and tab.text("#none") is None
    devtools.hook = lambda expression: 0
    assert tab.count("#none") == 0 and tab.exists("#none") is False


def aimed(x, y, *, ok=True, hit="button#go"):
    """What the page's aiming script answers (`Browser._AIM`): the middle of the element once it held still, and the topmost element there."""
    return {"x": x, "y": y, "steady": True, "ok": ok, "hit": hit}


def test_click_scrolls_to_the_element_and_presses_and_releases_the_mouse_at_its_middle(tab, devtools):
    quoted = json.dumps("#go")
    seen = []

    def page(expression):
        seen.append(expression)
        return aimed(120.5, 80) if quoted in expression and "scrollIntoView" in expression else None

    devtools.hook = page
    tab.click("#go")
    assert "scrollIntoView" in seen[0] and "elementFromPoint" in seen[0] and "requestAnimationFrame" in seen[0]      # one script: scroll, hold still, ask what is on top
    assert devtools.calls("Input.dispatchMouseEvent") == [
        {"type": "mouseMoved", "x": 120.5, "y": 80.0},
        {"type": "mousePressed", "x": 120.5, "y": 80.0, "button": "left", "clickCount": 1},
        {"type": "mouseReleased", "x": 120.5, "y": 80.0, "button": "left", "clickCount": 1},
    ]


def test_click_waits_while_a_cover_is_on_top_and_clicks_where_the_element_is_once_it_is_free(tab, devtools):
    answers = iter([aimed(10, 20, ok=False, hit="div#swelcome.swelcome"), aimed(10, 20, ok=False, hit="div#swelcome.swelcome"), aimed(11, 21)])
    devtools.hook = lambda expression: next(answers) if "elementFromPoint" in expression else None
    tab.click("#go")
    assert [(c["type"], c["x"], c["y"]) for c in devtools.calls("Input.dispatchMouseEvent")] == [("mouseMoved", 11.0, 21.0), ("mousePressed", 11.0, 21.0), ("mouseReleased", 11.0, 21.0)]
    assert not list(answers)                                                    # all three answers were used: it asked again after each cover


def test_click_on_an_element_that_stays_covered_names_what_covers_it_and_sends_no_mouse_event(tab, devtools):
    devtools.hook = lambda expression: aimed(10.4, 20.6, ok=False, hit="div#swelcome.swelcome") if "elementFromPoint" in expression else None
    with pytest.raises(cdp.BrowserError, match=r"^a click on '#go' would not reach it: div#swelcome\.swelcome is on top of it, at \(10, 21\), after 0\.2 s$"):
        tab.click("#go", timeout=0.2)
    assert devtools.calls("Input.dispatchMouseEvent") == []
    devtools.hook = lambda expression: aimed(5, 900, ok=False, hit=None) if "elementFromPoint" in expression else None
    with pytest.raises(cdp.BrowserError, match="its middle is outside the window"):
        tab.click("#go", timeout=0.1)
    assert devtools.calls("Input.dispatchMouseEvent") == []


def test_hover_moves_the_mouse_to_the_middle_of_the_element_and_does_not_press(tab, devtools):
    quoted = json.dumps(".wnode")
    devtools.hook = lambda expression: [40, 25.5] if quoted in expression and "scrollIntoView" in expression else None
    tab.hover(".wnode")
    assert devtools.calls("Input.dispatchMouseEvent") == [{"type": "mouseMoved", "x": 40.0, "y": 25.5}]
    devtools.hook = lambda expression: None
    with pytest.raises(cdp.BrowserError, match=r"^no element matches '\.nothing'$"):
        tab.hover(".nothing")
    assert len(devtools.calls("Input.dispatchMouseEvent")) == 1


def test_click_on_nothing_is_a_browser_error_and_sends_no_mouse_event(tab, devtools):
    with pytest.raises(cdp.BrowserError, match="^no element matches '#nothing'$"):
        tab.click("#nothing")
    assert devtools.calls("Input.dispatchMouseEvent") == []


def test_type_focuses_the_element_and_inserts_the_text(tab, devtools):
    quoted = json.dumps("#box")
    devtools.hook = lambda expression: True if quoted in expression and ".focus()" in expression else None
    tab.type("#box", "A website for my cafe")
    assert devtools.methods()[-2:] == ["Runtime.evaluate", "Input.insertText"]  # focus first, then the text
    assert devtools.calls("Input.insertText") == [{"text": "A website for my cafe"}]
    with pytest.raises(cdp.BrowserError, match="^no element matches '#nothing'$"):
        tab.type("#nothing", "x")
    assert len(devtools.calls("Input.insertText")) == 1


@pytest.mark.parametrize("name,key,code,vk,text", [
    ("Enter", "Enter", "Enter", 13, "\r"), ("Escape", "Escape", "Escape", 27, None), ("Tab", "Tab", "Tab", 9, None),
    ("Backspace", "Backspace", "Backspace", 8, None), ("Delete", "Delete", "Delete", 46, None),
    ("ArrowUp", "ArrowUp", "ArrowUp", 38, None), ("ArrowDown", "ArrowDown", "ArrowDown", 40, None),
    ("ArrowLeft", "ArrowLeft", "ArrowLeft", 37, None), ("ArrowRight", "ArrowRight", "ArrowRight", 39, None),
    ("Space", " ", "Space", 32, " "),
])
def test_press_sends_a_key_down_and_a_key_up(tab, devtools, name, key, code, vk, text):
    tab.press(name)
    down = {"type": "keyDown", "key": key, "code": code, "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk}
    if text:
        down["text"] = text  # only keys that type something carry text
    up = {"type": "keyUp", "key": key, "code": code, "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk}
    assert devtools.calls("Input.dispatchKeyEvent") == [down, up]


def test_the_keys_the_driver_knows_are_the_ones_the_tests_press():
    assert list(cdp.KEYS) == ["Enter", "Escape", "Tab", "Backspace", "Delete", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Space"]


def test_press_refuses_a_key_it_does_not_know_and_lists_the_known_ones(tab, devtools):
    with pytest.raises(cdp.BrowserError, match=r"^unknown key 'F13'; known: Enter, Escape, Tab, Backspace, Delete, ArrowUp, ArrowDown, ArrowLeft, ArrowRight, Space$"):
        tab.press("F13")
    assert devtools.calls("Input.dispatchKeyEvent") == []


def test_shot_saves_the_png_makes_the_folder_and_returns_the_path(tab, devtools, tmp_path):
    target = tmp_path / "deep" / "er" / "home.png"
    assert tab.shot(target) == target
    assert target.read_bytes() == fdt.PNG_BYTES
    assert tab.shot(str(tmp_path / "plain.png")) == tmp_path / "plain.png"  # a str works too
    assert devtools.calls("Page.captureScreenshot") == [{"format": "png"}, {"format": "png"}]


def test_shot_refuses_data_that_is_not_a_png_and_writes_nothing(tab, devtools, tmp_path):
    devtools.screenshot = base64.b64encode(b"GIF89a not a png").decode()
    with pytest.raises(cdp.BrowserError, match="^Chrome did not return a PNG$"):
        tab.shot(tmp_path / "bad.png")
    assert not (tmp_path / "bad.png").exists()


def stored_theme(devtools, index: int) -> str:
    """The theme the index-th new-document script writes to localStorage."""
    source = devtools.calls("Page.addScriptToEvaluateOnNewDocument")[index]["source"]
    match = re.fullmatch(r'try \{ localStorage\.setItem\("j2theme", ("[a-z]+")\); \} catch \(e\) \{\}', source)
    assert match, source  # the key both pages read, written inside a try (storage can be blocked)
    return json.loads(match.group(1))


def test_set_theme_stores_the_choice_for_the_next_page_and_emulates_the_scheme(tab, devtools):
    tab.set_theme("dark")
    assert stored_theme(devtools, 0) == "dark"
    assert devtools.calls("Emulation.setEmulatedMedia") == [{"features": [{"name": "prefers-color-scheme", "value": "dark"}]}]
    assert devtools.calls("Page.removeScriptToEvaluateOnNewDocument") == []
    tab.set_theme("light")
    assert devtools.calls("Page.removeScriptToEvaluateOnNewDocument") == [{"identifier": "script-1"}]  # one script at a time
    assert stored_theme(devtools, 1) == "light"
    assert devtools.calls("Emulation.setEmulatedMedia")[1]["features"][0]["value"] == "light"
    tab.set_theme("system")  # the page follows the browser: light unless a scheme is given
    assert stored_theme(devtools, 2) == "system"
    assert devtools.calls("Emulation.setEmulatedMedia")[2]["features"][0]["value"] == "light"
    tab.set_theme("system", "dark")
    assert stored_theme(devtools, 3) == "system"
    assert devtools.calls("Emulation.setEmulatedMedia")[3]["features"][0]["value"] == "dark"
    tab.set_theme("light", "dark")  # an explicit scheme is the emulated one whatever the stored choice
    assert devtools.calls("Emulation.setEmulatedMedia")[4]["features"][0]["value"] == "dark"
    assert devtools.calls("Page.removeScriptToEvaluateOnNewDocument") == [{"identifier": f"script-{n}"} for n in (1, 2, 3, 4)]


@pytest.mark.parametrize("theme,scheme,message", [
    ("sepia", None, r"^theme must be one of light, dark, system, not 'sepia'$"),
    ("", None, r"^theme must be one of light, dark, system, not ''$"),
    ("dark", "system", r"^scheme must be one of light, dark, not 'system'$"),
    ("system", "blue", r"^scheme must be one of light, dark, not 'blue'$"),
])
def test_set_theme_refuses_what_is_not_a_theme_or_a_scheme_and_changes_nothing(tab, devtools, theme, scheme, message):
    with pytest.raises(ValueError, match=message):
        tab.set_theme(theme, scheme)
    assert devtools.calls("Page.addScriptToEvaluateOnNewDocument") == [] and devtools.calls("Emulation.setEmulatedMedia") == []


def test_set_size_resizes_the_window_and_remembers_it(tab, devtools):
    tab.set_size(390, 844)
    assert devtools.calls("Emulation.setDeviceMetricsOverride")[-1] == {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": False}
    assert tab.size == (390, 844)
    tab.set_size(100, 5000)
    tab.set_size(5000, 100)
    assert tab.size == (5000, 100)


@pytest.mark.parametrize("size", [(99, 800), (800, 99), (5001, 800), (800, 5001), (0, 0), (-1, 800), (800.5, 600), ("800", 600), (None, 600)])
def test_set_size_refuses_sizes_that_are_not_whole_numbers_from_100_to_5000(tab, devtools, size):
    with pytest.raises(ValueError, match=rf"^the size must be two whole numbers from 100 to 5000, not {re.escape(repr(size[0]))} x {re.escape(repr(size[1]))}$"):
        tab.set_size(*size)
    assert tab.size == (1280, 900) and len(devtools.calls("Emulation.setDeviceMetricsOverride")) == 1


# ---- what the page did wrong ----------------------------------------------------------------------------------------------------
def test_console_errors_collect_errors_assertions_exceptions_and_error_log_entries(tab, devtools):
    push = devtools.push
    push("Runtime.consoleAPICalled", {"type": "log", "args": [{"type": "string", "value": "just a log"}]})
    push("Runtime.consoleAPICalled", {"type": "warning", "args": [{"type": "string", "value": "just a warning"}]})
    push("Runtime.consoleAPICalled", {"type": "error", "args": [{"type": "string", "value": "bad"}, {"type": "number", "value": 3},
                                                              {"type": "object", "description": "Error: boom"},
                                                              {"type": "number", "unserializableValue": "NaN"}, {"type": "symbol"}, {}]})
    push("Runtime.consoleAPICalled", {"type": "assert", "args": [{"type": "string", "value": "assertion"}]})
    push("Runtime.exceptionThrown", {"exceptionDetails": {"text": "Uncaught", "exception": {"description": "TypeError: x is null\n at a.js:1"}}})
    push("Runtime.exceptionThrown", {"exceptionDetails": {"text": "Uncaught (in promise)"}})
    push("Runtime.exceptionThrown", {"exceptionDetails": {}})
    push("Log.entryAdded", {"entry": {"level": "error", "source": "security", "text": "Refused to execute inline script (CSP)", "url": "http://x/"}})
    push("Log.entryAdded", {"entry": {"level": "warning", "source": "network", "text": "a warning"}})
    push("Log.entryAdded", {"entry": {"level": "error", "source": "network", "text": "Failed to load resource", "url": "http://x/favicon.ico"}})
    push("Log.entryAdded", {"entry": {"level": "error", "text": "no source"}})
    wait_until(lambda: len(tab.console_errors) == 7)
    assert tab.console_errors == [
        "bad 3 Error: boom NaN symbol ",  # a value, else Chrome's description, else the unserializable value, else the type
        "assertion",
        "TypeError: x is null\n at a.js:1",  # an uncaught exception: its description,
        "Uncaught (in promise)",  # else the details' text,
        "uncaught exception",  # else a fixed phrase
        "[security] Refused to execute inline script (CSP)",  # an error log entry: a CSP violation is one
        "[log] no source",
    ]


def test_console_errors_is_a_copy_and_clear_diagnostics_empties_it(tab, devtools):
    devtools.push("Runtime.consoleAPICalled", {"type": "error", "args": [{"type": "string", "value": "one"}]})
    wait_until(lambda: tab.console_errors)
    tab.console_errors.append("not stored")
    assert tab.console_errors == ["one"]
    tab.clear_diagnostics()
    assert tab.console_errors == [] and tab.failed_requests == [] and tab.expected_failures == []

def sent(devtools, request_id: str, url: str, method: str = "GET") -> None:
    devtools.push("Network.requestWillBeSent", {"requestId": request_id, "request": {"url": url, "method": method}})


def answered(devtools, request_id: str, url: str, status: int) -> None:
    devtools.push("Network.responseReceived", {"requestId": request_id, "response": {"url": url, "status": status}})


def test_an_answer_of_400_or_more_is_a_failed_request_and_names_the_method_that_made_it(tab, devtools):
    base = "http://127.0.0.1:8780"
    for number, (url, method, status) in enumerate([("/api/graph", "GET", 500), ("/api/say", "POST", 401), ("/ok", "GET", 200),
                                                    ("/moved", "GET", 304), ("/edge", "GET", 399), ("/gone", "GET", 400)], start=1):
        sent(devtools, str(number), base + url, method)
        answered(devtools, str(number), base + url, status)
    answered(devtools, "never-sent", base + "/orphan", 404)  # an answer to a request the page never announced: GET
    wait_until(lambda: len(tab.failed_requests) == 4)
    assert tab.failed_requests == [
        {"url": base + "/api/graph", "status": 500, "error": None, "method": "GET"},
        {"url": base + "/api/say", "status": 401, "error": None, "method": "POST"},
        {"url": base + "/gone", "status": 400, "error": None, "method": "GET"},
        {"url": base + "/orphan", "status": 404, "error": None, "method": "GET"},
    ]
    tab.failed_requests.clear()
    assert len(tab.failed_requests) == 4  # a copy


def test_a_request_that_failed_without_an_answer_is_a_failed_request_unless_the_page_cancelled_it(tab, devtools):
    sent(devtools, "1", "http://127.0.0.1:8780/refused", "POST")
    devtools.push("Network.loadingFailed", {"requestId": "1", "errorText": "net::ERR_CONNECTION_REFUSED"})
    sent(devtools, "2", "http://127.0.0.1:8780/api/events")
    devtools.push("Network.loadingFailed", {"requestId": "2", "errorText": "net::ERR_ABORTED", "canceled": True})  # a navigation ended the stream
    sent(devtools, "3", "http://127.0.0.1:8780/nameless")
    devtools.push("Network.loadingFailed", {"requestId": "3"})
    sent(devtools, "4", "data:text/plain,hello")
    devtools.push("Network.loadingFailed", {"requestId": "4", "errorText": "net::ERR_FAILED"})
    sent(devtools, "5", "blob:http://127.0.0.1:8780/uuid")
    devtools.push("Network.loadingFailed", {"requestId": "5", "errorText": "net::ERR_FAILED"})
    devtools.push("Network.loadingFailed", {"requestId": "unknown", "errorText": "net::ERR_FAILED"})  # no url known: nothing to report
    wait_until(lambda: len(tab.failed_requests) == 2)
    assert tab.failed_requests == [
        {"url": "http://127.0.0.1:8780/refused", "status": 0, "error": "net::ERR_CONNECTION_REFUSED", "method": "POST"},
        {"url": "http://127.0.0.1:8780/nameless", "status": 0, "error": "failed", "method": "GET"},
    ]


def test_the_favicon_never_counts_whatever_happens_to_it(tab, devtools):
    for number, url in enumerate(["http://127.0.0.1:8780/favicon.ico", "http://127.0.0.1:8780/x/favicon.ico?v=2"], start=1):
        sent(devtools, str(number), url)
        answered(devtools, str(number), url, 404)
        devtools.push("Network.loadingFailed", {"requestId": str(number), "errorText": "net::ERR_FAILED"})
    devtools.push("Log.entryAdded", {"entry": {"level": "error", "source": "network", "text": "404", "url": "http://127.0.0.1:8780/favicon.ico"}})
    sent(devtools, "3", "http://127.0.0.1:8780/favicon.icon")  # not the favicon
    answered(devtools, "3", "http://127.0.0.1:8780/favicon.icon", 404)
    wait_until(lambda: tab.failed_requests)
    assert [f["url"] for f in tab.failed_requests] == ["http://127.0.0.1:8780/favicon.icon"] and tab.console_errors == []


def test_a_failure_announced_with_expect_failed_is_kept_apart_and_only_from_then_on(tab, devtools):
    base = "http://127.0.0.1:8780"
    answered(devtools, "a", base + "/api/graph", 500)  # before the announcement: a failure
    wait_until(lambda: len(tab.failed_requests) == 1)
    tab.expect_failed("/api/graph")
    tab.expect_failed("/api/say", 401)
    answered(devtools, "b", base + "/api/graph?level=full", 503)  # a part of the url, any status
    answered(devtools, "c", base + "/api/say", 401)  # this status
    answered(devtools, "d", base + "/api/say", 500)  # another status: still a failure
    answered(devtools, "e", base + "/other", 500)
    sent(devtools, "f", base + "/api/graph")
    devtools.push("Network.loadingFailed", {"requestId": "f", "errorText": "net::ERR_FAILED"})  # a failure with no status matches a part-only rule
    wait_until(lambda: len(tab.failed_requests) == 3 and len(tab.expected_failures) == 3)
    assert [f["url"] for f in tab.failed_requests] == [base + "/api/graph", base + "/api/say", base + "/other"]
    assert [(f["url"], f["status"]) for f in tab.expected_failures] == [
        (base + "/api/graph?level=full", 503), (base + "/api/say", 401), (base + "/api/graph", 0)]
    tab.clear_diagnostics()  # empties the lists, keeps the announcements
    answered(devtools, "g", base + "/api/graph", 500)
    wait_until(lambda: tab.expected_failures)
    assert tab.failed_requests == []


def test_dialogs_are_accepted_at_once_and_remembered(tab, devtools):
    devtools.push("Page.javascriptDialogOpening", {"type": "confirm", "message": "Clear the memory?"})
    devtools.push("Page.javascriptDialogOpening", {"type": "alert"})
    devtools.wait_for_command("Page.handleJavaScriptDialog", 2)
    assert devtools.calls("Page.handleJavaScriptDialog") == [{"accept": True}, {"accept": True}]
    assert tab.dialogs == [{"type": "confirm", "message": "Clear the memory?"}, {"type": "alert", "message": ""}]


# ---- Chrome itself: a program that starts like Chrome --------------------------------------------------------------------------
def test_a_browser_starts_chrome_with_its_own_profile_and_removes_everything_when_it_closes(fake_chrome, monkeypatch):
    monkeypatch.setenv("FAKE_CHROME_MODE", "helper")  # Chrome starts helper processes in its group; they must go too
    sleeps: list[float] = []
    with cdp.Browser(str(fake_chrome), timeout=5, startup_timeout=15) as browser:
        run = chrome_log(fake_chrome)
        argv = run["argv"]
        profile = Path(next(a for a in argv if a.startswith("--user-data-dir=")).split("=", 1)[1])
        assert argv[-1] == "about:blank" and set(cdp.CHROME_FLAGS) <= set(argv)
        assert "--headless=new" in argv and "--remote-debugging-port=0" in argv and "--disable-background-networking" in argv
        assert profile.name.startswith("sutra-chrome-") and (profile / "DevToolsActivePort").is_file()
        assert browser.pid == run["pid"] and pid_exists(run["pid"]) and group_exists(run["pgid"])
        assert browser.js("1 + 1") == 2
        browser.goto("data:text/html,x")
        process = browser._process.process
        real_sleep = time.sleep
        monkeypatch.setattr(cdp.time, "sleep", lambda seconds: (sleeps.append(seconds), real_sleep(seconds))[1])  # counts the waits of close()
    monkeypatch.undo()
    assert len(sleeps) < 40  # a group that is gone is noticed at once; one believed alive would be waited for 5 s in 0.05 s steps
    assert process.returncode == 0  # it was asked to leave (SIGTERM) and left by itself; it was not killed
    assert not pid_exists(run["pid"]) and not group_exists(run["pgid"])
    assert not profile.exists()  # the folder is gone, the Default/Cookies file Chrome wrote into it too


class QuitsAtOnce:
    """Stands in for subprocess.Popen: remembers how it was started and has already quit."""

    started: list = []

    def __init__(self, args, **kwargs):
        self.args, self.kwargs, self.pid, self.returncode = args, kwargs, 99999999, 5
        QuitsAtOnce.started.append(self)

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode


def started_with(monkeypatch, tmp_path, **options) -> QuitsAtOnce:
    QuitsAtOnce.started = []
    monkeypatch.setattr(cdp.subprocess, "Popen", QuitsAtOnce)
    monkeypatch.setattr(cdp.tempfile, "mkdtemp", lambda prefix: str(tmp_path / "temp-profile"))
    (tmp_path / "temp-profile").mkdir(exist_ok=True)
    with pytest.raises(cdp.BrowserError, match="^Chrome exited with code 5 before it opened its debugging port$"):
        cdp.ChromeProcess("/the/chrome", **options)
    (process,) = QuitsAtOnce.started
    return process


def test_chrome_is_started_headless_with_the_flags_a_quiet_test_needs_in_its_own_session(monkeypatch, tmp_path):
    process = started_with(monkeypatch, tmp_path)
    profile = tmp_path / "temp-profile"
    assert process.args == ["/the/chrome", *cdp.CHROME_FLAGS, f"--user-data-dir={profile}", "about:blank"]
    for flag in ("--headless=new", "--remote-debugging-port=0", "--no-first-run", "--disable-background-networking", "--disable-sync",
                 "--disable-extensions", "--mute-audio", "--hide-scrollbars", "--disable-component-update"):
        assert flag in cdp.CHROME_FLAGS, flag
    assert process.kwargs == {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "start_new_session": True}
    assert not profile.exists()  # a profile Chrome made for itself goes when Chrome does, even when it never started


def test_chrome_gets_the_flags_the_caller_asks_for_in_front_of_the_blank_page(monkeypatch, tmp_path):
    process = started_with(monkeypatch, tmp_path, headless=False, extra_args=["--window-size=800,600", "--lang=en"])
    assert not any(a.startswith("--headless") for a in process.args)  # headless=False takes the flag away
    assert process.args[-4:] == [f"--user-data-dir={tmp_path / 'temp-profile'}", "--window-size=800,600", "--lang=en", "about:blank"]
    assert [a for a in process.args if a.startswith("--") and not a.startswith(("--user-data-dir", "--window-size", "--lang"))] == [
        f for f in cdp.CHROME_FLAGS if not f.startswith("--headless")]


def test_a_profile_chrome_still_writes_into_is_removed_again_until_it_is_gone_and_then_given_up_on(monkeypatch, tmp_path):
    calls = []
    real = shutil.rmtree

    def stubborn(path, ignore_errors=False):
        calls.append(ignore_errors)
        if len(calls) >= 3:  # the first two do not manage it: a helper of Chrome writes into the folder meanwhile
            real(path, ignore_errors=ignore_errors)

    monkeypatch.setattr(cdp.shutil, "rmtree", stubborn)
    pauses = []
    monkeypatch.setattr(cdp.time, "sleep", pauses.append)  # no real waiting between the tries
    started_with(monkeypatch, tmp_path)
    assert calls == [True, True, True] and not (tmp_path / "temp-profile").exists()  # errors are ignored, the try is repeated
    assert pauses == [0.1, 0.1]  # a short pause after each try that did not manage it
    calls.clear()
    monkeypatch.setattr(cdp.shutil, "rmtree", lambda path, ignore_errors=False: calls.append(ignore_errors))  # never succeeds
    (tmp_path / "temp-profile").mkdir(exist_ok=True)
    started_with(monkeypatch, tmp_path)  # does not raise and does not wait for ever
    assert calls == [True] * 10 and (tmp_path / "temp-profile").exists()


def test_a_process_group_is_alive_unless_the_system_says_there_is_no_such_process(monkeypatch):
    chrome = object.__new__(cdp.ChromeProcess)
    chrome.process = type("P", (), {"pid": 4242})()
    asked = []

    def kill(group, signal_number):
        asked.append((group, signal_number))
        if outcome is not None:
            raise outcome

    monkeypatch.setattr(cdp.os, "killpg", kill)
    outcome = None
    assert chrome._group_alive() is True  # signal 0 is delivered: the group exists
    outcome = ProcessLookupError()
    assert chrome._group_alive() is False
    outcome = PermissionError()  # not ours to signal, but it exists
    assert chrome._group_alive() is True
    assert asked == [(4242, 0)] * 3


def test_what_is_left_of_chrome_after_the_grace_time_is_killed(monkeypatch, tmp_path):
    asked = []
    monkeypatch.setattr(cdp, "STOP_GRACE_S", 0.2)
    monkeypatch.setattr(cdp.os, "killpg", lambda group, signal_number: asked.append((group, signal_number)))  # everything is "alive"
    started_with(monkeypatch, tmp_path)  # Chrome quit at once, but its group is believed to live
    assert asked[-1] == (99999999, signal.SIGKILL) and len(asked) > 2 and all(a == (99999999, 0) for a in asked[:-1])
    asked.clear()

    def refuse(group, signal_number):
        asked.append(signal_number)
        raise OSError("not allowed" if signal_number else "alive")

    monkeypatch.setattr(cdp.os, "killpg", refuse)
    started_with(monkeypatch, tmp_path)  # a kill that is refused is not an error
    assert asked[-1] == signal.SIGKILL


def test_a_command_that_cannot_be_written_to_a_closing_connection_is_the_closed_error(tab, devtools):
    class Gone:
        def send(self, data):
            raise OSError("broken pipe")

    tab._conn._ws = Gone()
    with pytest.raises(cdp.BrowserError, match=r"^Runtime\.evaluate: the connection to Chrome is closed$"):
        tab.js("1")
    assert tab._conn._pending == {}  # nothing waits for an answer that cannot come
    tab._conn.post("Runtime.evaluate", {"expression": "2"})  # and a post to it is dropped quietly


def test_a_profile_the_caller_names_is_used_and_never_removed(monkeypatch, tmp_path):
    mine = tmp_path / "my-profile"
    mine.mkdir()
    (mine / "keep.txt").write_text("mine")
    process = started_with(monkeypatch, tmp_path, profile_dir=mine)
    assert f"--user-data-dir={mine}" in process.args and (mine / "keep.txt").read_text() == "mine"


def test_chrome_that_quits_before_opening_its_port_is_reported_with_its_exit_code_and_cleaned_up(fake_chrome, tmp_path, monkeypatch):
    known = tmp_path / "temp-profile"
    known.mkdir()
    monkeypatch.setattr(cdp.tempfile, "mkdtemp", lambda prefix: str(known))
    monkeypatch.setenv("FAKE_CHROME_MODE", "exit")
    browser = cdp.Browser(str(fake_chrome), startup_timeout=10)
    with pytest.raises(cdp.BrowserError, match="^Chrome exited with code 7 before it opened its debugging port$"):
        browser.__enter__()
    assert not known.exists() and browser._process is None and browser._conn is None


def test_chrome_that_never_opens_its_port_is_given_up_on_after_the_startup_time_and_is_stopped(fake_chrome, monkeypatch):
    started = []

    class Recording(subprocess.Popen):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            started.append(self)

    monkeypatch.setattr(cdp.subprocess, "Popen", Recording)
    monkeypatch.setenv("FAKE_CHROME_MODE", "noport")
    with pytest.raises(cdp.BrowserError, match=r"^Chrome did not open its debugging port within 1 s$"):
        cdp.Browser(str(fake_chrome), startup_timeout=1).__enter__()
    (process,) = started
    assert process.poll() is not None and not group_exists(process.pid)  # the Chrome it started is gone, with its group


class DevToolsHttp:
    """The HTTP side of Chrome's debugging port: /json/list and PUT /json/new, with answers the test sets."""

    def __init__(self, listing, created):
        import http.server

        outer = self
        self.listing, self.created, self.requests = listing, created, []

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, payload):
                if isinstance(payload, Exception):
                    self.send_error(500)
                    return
                body = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):  # noqa: N802
                outer.requests.append(("GET", self.path))
                self._send(outer.listing)

            def do_PUT(self):  # noqa: N802
                outer.requests.append(("PUT", self.path))
                self._send(outer.created)

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def process(self):
        chrome = object.__new__(cdp.ChromeProcess)  # only `port` is used to find the page
        chrome.port = self.port
        return chrome

    def stop(self):
        self.server.shutdown()


def test_the_page_of_a_chrome_is_the_first_page_target_with_a_websocket():
    http = DevToolsHttp([{"type": "service_worker", "webSocketDebuggerUrl": "ws://x/sw"}, {"type": "page"},
                         {"type": "page", "webSocketDebuggerUrl": "ws://x/first"}, {"type": "page", "webSocketDebuggerUrl": "ws://x/second"}], {})
    try:
        assert http.process().page_ws_url(2) == "ws://x/first"
        assert http.requests == [("GET", "/json/list")]
    finally:
        http.stop()


def test_a_chrome_with_no_page_is_made_one_and_a_chrome_that_cannot_is_reported():
    http = DevToolsHttp([], {"webSocketDebuggerUrl": "ws://x/new"})
    try:
        assert http.process().page_ws_url(2) == "ws://x/new" and http.requests == [("GET", "/json/list"), ("PUT", "/json/new?about:blank")]
        http.created = {}  # it cannot: it keeps trying until the time is up, then says so
        start = time.monotonic()
        with pytest.raises(cdp.BrowserError, match=r"^Chrome has no page to drive within 0\.2 s \(None\)$"):
            http.process().page_ws_url(0.2)
        assert time.monotonic() - start >= 0.15  # it kept trying for the time it was given
        assert len(http.requests) >= 4 and http.requests[2:4] == [("GET", "/json/list"), ("PUT", "/json/new?about:blank")]  # list, then new, each time
        http.listing = RuntimeError("boom")  # a server error is one more reason to try again, and is named at the end
        with pytest.raises(cdp.BrowserError, match=r"^Chrome has no page to drive within 0\.2 s \(HTTP Error 500: .*\)$"):
            http.process().page_ws_url(0.2)
    finally:
        http.stop()


def test_a_chrome_that_ignores_sigterm_is_killed_after_the_grace_time_and_so_are_its_helpers(fake_chrome, monkeypatch):
    monkeypatch.setattr(cdp, "STOP_GRACE_S", 0.3)
    monkeypatch.setenv("FAKE_CHROME_MODE", "stubborn")
    start = time.monotonic()
    with cdp.Browser(str(fake_chrome), timeout=5, startup_timeout=10):
        run = chrome_log(fake_chrome)
        began = time.monotonic()
    assert time.monotonic() - began >= 0.27  # it was asked first, and given the grace time
    assert not pid_exists(run["pid"]) and not group_exists(run["pgid"])
    assert time.monotonic() - start < 30


def test_a_browser_with_no_chrome_to_start_says_how_to_name_one(monkeypatch):
    monkeypatch.setattr(cdp, "find_chrome", lambda *args, **kwargs: None)
    browser = cdp.Browser()
    with pytest.raises(cdp.BrowserError, match=r"^Chrome is not installed \(set SUTRA_CHROME to its path\)$"):
        browser.__enter__()


def test_the_startup_time_is_the_longer_of_twenty_seconds_and_the_command_timeout():
    assert cdp.Browser().startup_timeout == 20.0 and cdp.Browser(timeout=30).startup_timeout == 30
    assert cdp.Browser(timeout=30, startup_timeout=2).startup_timeout == 2 and cdp.Browser(timeout=3).startup_timeout == 20.0


# ---- the command line ---------------------------------------------------------------------------------------------------------
@pytest.fixture()
def self_test_page(devtools, monkeypatch):
    """A stand-in endpoint that renders the self-test page, and `cdp.Browser` patched to attach to it."""
    real = cdp.Browser
    devtools.values.update({"document.getElementById('x').textContent": "ok", "1 + 1": 2})
    monkeypatch.setattr(cdp, "find_chrome", lambda *args, **kwargs: "/stand-in/chrome")
    monkeypatch.setattr(cdp, "Browser", lambda chrome: real(ws_url=devtools.url, timeout=3))
    return devtools


def test_self_test_opens_a_page_runs_a_script_and_takes_a_picture_before_it_says_ok(self_test_page):
    out = io.StringIO()
    assert cdp.self_test(out) == 0 and out.getvalue() == "chrome ok\n"
    methods = self_test_page.methods()
    assert [m for m in methods if m in ("Page.navigate", "Page.captureScreenshot")] == ["Page.navigate", "Page.captureScreenshot"]
    assert self_test_page.calls("Page.navigate")[0]["url"].startswith("data:text/html,")
    assert self_test_page.methods().count("Runtime.evaluate") == 2


def test_self_test_says_chrome_missing_and_still_exits_zero_when_there_is_none(monkeypatch):
    monkeypatch.setattr(cdp, "find_chrome", lambda *args, **kwargs: None)
    out = io.StringIO()
    assert cdp.self_test(out) == 0 and out.getvalue() == "chrome missing\n"


def test_self_test_defaults_to_standard_output(monkeypatch, capsys):
    monkeypatch.setattr(cdp, "find_chrome", lambda *args, **kwargs: None)
    assert cdp.self_test() == 0 and capsys.readouterr().out == "chrome missing\n"


def test_self_test_says_why_a_page_did_not_render_or_a_script_did_not_run(self_test_page):
    self_test_page.values["document.getElementById('x').textContent"] = "not ok"
    out = io.StringIO()
    assert cdp.self_test(out) == 1 and out.getvalue() == "chrome failed: the test page did not render\n"
    self_test_page.values.update({"document.getElementById('x').textContent": "ok", "1 + 1": 3})
    out = io.StringIO()
    assert cdp.self_test(out) == 1 and out.getvalue() == "chrome failed: scripts do not run\n"


def test_self_test_fails_on_a_console_error_of_a_clean_page(self_test_page):
    self_test_page.after["Page.navigate"].append(("Runtime.consoleAPICalled", {"type": "error", "args": [{"type": "string", "value": "boom"}]}))
    out = io.StringIO()
    assert cdp.self_test(out) == 1 and out.getvalue() == "chrome failed: console errors on a clean page: ['boom']\n"


def test_self_test_names_the_error_when_a_picture_cannot_be_taken(self_test_page):
    self_test_page.fail["Page.captureScreenshot"] = "no screen"
    out = io.StringIO()
    assert cdp.self_test(out) == 1 and out.getvalue() == "chrome failed: Page.captureScreenshot: no screen\n"


@pytest.mark.parametrize("error,words", [(cdp.BrowserError("not started"), "not started"), (OSError("cannot run it"), "cannot run it"),
                                         (TimeoutError("took too long"), "took too long")])
def test_self_test_says_chrome_failed_for_each_way_a_chrome_can_fail_to_run(monkeypatch, error, words):
    def refuse(chrome):
        raise error

    monkeypatch.setattr(cdp, "find_chrome", lambda *args, **kwargs: "/stand-in/chrome")
    monkeypatch.setattr(cdp, "Browser", refuse)
    out = io.StringIO()
    assert cdp.self_test(out) == 1 and out.getvalue() == f"chrome failed: {words}\n"


def test_self_test_does_not_catch_what_is_not_a_browser_problem(monkeypatch):
    def refuse(chrome):
        raise KeyError("a bug in the test, not in Chrome")

    monkeypatch.setattr(cdp, "find_chrome", lambda *args, **kwargs: "/stand-in/chrome")
    monkeypatch.setattr(cdp, "Browser", refuse)
    with pytest.raises(KeyError):
        cdp.self_test(io.StringIO())


def test_main_prints_the_chrome_it_would_use_or_none(monkeypatch, capsys):
    monkeypatch.setattr(cdp, "find_chrome", lambda *args, **kwargs: "/opt/chrome")
    assert cdp.main(["--where"]) == 0 and capsys.readouterr().out == "/opt/chrome\n"
    monkeypatch.setattr(cdp, "find_chrome", lambda *args, **kwargs: None)
    assert cdp.main(["--where"]) == 0 and capsys.readouterr().out == "none\n"


def test_main_runs_the_self_test_and_without_a_flag_prints_the_help_and_exits_two(monkeypatch, capsys):
    monkeypatch.setattr(cdp, "find_chrome", lambda *args, **kwargs: None)
    assert cdp.main(["--self-test"]) == 0 and capsys.readouterr().out == "chrome missing\n"
    assert cdp.main([]) == 2
    help_text = capsys.readouterr().out
    assert "--self-test" in help_text and "--where" in help_text


def test_run_as_a_program_the_self_test_starts_a_chrome_and_prints_its_answer(fake_chrome):
    env = {**os.environ, "SUTRA_CHROME": str(fake_chrome)}
    done = subprocess.run([sys.executable, str(Path(cdp.__file__)), "--self-test"], capture_output=True, text=True, env=env, timeout=60)
    assert (done.returncode, done.stdout, done.stderr) == (0, "chrome ok\n", "")
    done = subprocess.run([sys.executable, str(Path(cdp.__file__)), "--where"], capture_output=True, text=True, env=env, timeout=60)
    assert (done.returncode, done.stdout) == (0, f"{fake_chrome}\n")


# ---- the conftest: its fixtures and the marker, run under a copy of it with stand-ins next to it ---------------------------------
FAKE_BACKEND_STAND_IN = '''
import json
import os

STOPPED = []
MADE = []


class FakeState:
    token = "stand-in-token"


class FakeClient:
    def __init__(self, url, token):
        self.url, self.token, self.resets = url, token, 0

    def reset(self):
        self.resets += 1


class _App:
    def __init__(self, options):
        self.options = options
        self.state = type("S", (), {"fake": FakeState()})()


class _Running:
    url = "http://127.0.0.1:1"

    def __init__(self, options):
        self.options = options

    def stop(self):
        STOPPED.append(self.options)
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "stops.jsonl"), "a", encoding="utf-8") as log:
            log.write(json.dumps(self.options) + "\\n")  # the module's own server stops after the last test: this file shows it


def make_app(**options):
    MADE.append(options)
    return _App(options)


def run_in_thread(app):
    return _Running(app.options)
'''
CDP_STAND_IN = '''
LOG = []
CHROME = None  # what find_chrome() answers
FAILED = []  # what the next Browser reports as failed requests


def find_chrome():
    return CHROME


class Browser:
    def __init__(self, chrome):
        self.chrome, self.failed_requests = chrome, list(FAILED)

    def __enter__(self):
        LOG.append("start " + self.chrome)
        return self

    def __exit__(self, *exc):
        LOG.append("stop")
'''
INNER_TESTS = '''
from pathlib import Path

import pytest

import cdp
import fake_backend


@pytest.mark.browser
def test_01_the_marker_is_registered():
    pass


def test_02_the_folders(fixtures_dir, screens_dir):
    here = Path(__file__).resolve().parent
    assert fixtures_dir == here / "fixtures" and screens_dir == here / "screens" and screens_dir.is_dir()


def test_03_the_module_server_and_a_reset_client(fake_server, fake):
    assert fake is fake_server.client and fake.url == fake_server.url == "http://127.0.0.1:1"
    assert fake.token == "stand-in-token" and fake_server.state.token == "stand-in-token" and fake_server.app.options == {}
    assert fake.resets == 1  # reset before the test


def test_04_the_module_server_is_shared_and_reset_again(fake_server, fake):
    assert fake.resets == 2 and fake_backend.MADE == [{}] and fake_backend.STOPPED == []


def test_05_servers_with_options(make_fake_server):
    first = make_fake_server(pages_dir="p", token="t" * 20)
    second = make_fake_server(version="9")
    assert first.app.options == {"pages_dir": "p", "token": "t" * 20} and second.app.options == {"version": "9"}
    assert first.client.token == "stand-in-token" and fake_backend.STOPPED == []


def test_06_those_servers_were_stopped_after_the_test_and_the_module_server_was_not():
    assert fake_backend.STOPPED == [{"version": "9"}, {"pages_dir": "p", "token": "t" * 20}]  # the last made is stopped first


@pytest.fixture()
def no_chrome():
    cdp.CHROME = None


@pytest.fixture()
def chrome():
    cdp.CHROME, cdp.FAILED = "/stand-in/chrome", []


@pytest.fixture()
def dirty(chrome):
    cdp.FAILED = [{"url": "http://127.0.0.1/api/graph", "status": 500}]


def test_07_without_chrome_the_test_is_skipped(no_chrome, browser):
    raise AssertionError("never runs")


def test_08_a_clean_test_gets_a_started_chrome(chrome, browser):
    assert browser.chrome == "/stand-in/chrome" and cdp.LOG == ["start /stand-in/chrome"]


def test_09_and_it_is_stopped_after_it(chrome, browser):
    assert cdp.LOG[-2:] == ["stop", "start /stand-in/chrome"]


def test_10_a_failed_request_fails_the_test_that_left_it(dirty, browser):
    pass
'''


def run_under_conftest(tmp_path) -> subprocess.CompletedProcess:
    """Run INNER_TESTS with a copy of tests/ui/conftest.py, a stand-in fake_backend and cdp next to it, and no marker registered
    anywhere else (so a `browser` test passes under --strict-markers only if the conftest registers the marker)."""
    (tmp_path / "conftest.py").write_text((UI_TESTS / "conftest.py").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "fake_backend.py").write_text(FAKE_BACKEND_STAND_IN, encoding="utf-8")
    (tmp_path / "cdp.py").write_text(CDP_STAND_IN, encoding="utf-8")
    (tmp_path / "test_inner.py").write_text(INNER_TESTS, encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\naddopts = -p no:cacheprovider\n", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTEST", "SUTRA_"))}
    return subprocess.run([sys.executable, "-m", "pytest", "--strict-markers", "-rA", "-q", "test_inner.py"], cwd=tmp_path,
                          capture_output=True, text=True, env=env, timeout=120)


def test_the_conftest_registers_the_marker_hands_out_folders_and_servers_and_guards_the_browser(tmp_path):
    done = run_under_conftest(tmp_path)
    out = done.stdout + done.stderr
    outcomes: dict[str, set[str]] = {}
    for outcome, name in re.findall(r"^(PASSED|ERROR|FAILED) test_inner\.py::(\w+)", done.stdout, re.M):
        outcomes.setdefault(name, set()).add(outcome)
    passing = ("test_01_the_marker_is_registered", "test_02_the_folders", "test_03_the_module_server_and_a_reset_client",
               "test_04_the_module_server_is_shared_and_reset_again", "test_05_servers_with_options",
               "test_06_those_servers_were_stopped_after_the_test_and_the_module_server_was_not",
               "test_08_a_clean_test_gets_a_started_chrome", "test_09_and_it_is_stopped_after_it")
    for name in passing:
        assert outcomes.get(name) == {"PASSED"}, (name, out)
    assert "test_07_without_chrome_the_test_is_skipped" not in outcomes  # skipped: it never ran
    assert "SKIPPED" in done.stdout and "Chrome is not installed (set SUTRA_CHROME to its path)" in out
    # the failed-request check runs after the test body: the body passed, the teardown made it an error
    assert outcomes["test_10_a_failed_request_fails_the_test_that_left_it"] == {"PASSED", "ERROR"}
    assert "requests failed during the test (announce them with browser.expect_failed)" in out and "/api/graph" in out
    assert "9 passed, 1 skipped, 1 error" in out or "9 passed, 1 skipped, 1 error" in out.replace("\n", " ")
    stops = [json.loads(line) for line in (tmp_path / "stops.jsonl").read_text(encoding="utf-8").splitlines()]
    assert stops == [{"version": "9"}, {"pages_dir": "p", "token": "t" * 20}, {}]  # and the module's own server, after the last test


def test_screenshots_are_never_committed():
    if shutil.which("git") is None:
        pytest.skip("git is needed")
    names = ["home-light.png", "REVIEW.md", "dept-graph-dark-390.png", ".gitignore"]
    done = subprocess.run(["git", "check-ignore", *[f"tests/ui/screens/{n}" for n in names]], cwd=REPO, capture_output=True, text=True)
    ignored = done.stdout.split()
    assert ignored == [f"tests/ui/screens/{n}" for n in names[:3]], done  # the pictures and the notes, not the ignore file itself
    assert (FIXTURES.parent / "screens" / ".gitignore").read_text().splitlines()[-2:] == ["*", "!.gitignore"]


# ---- Chrome for real (SUTRA_BROWSER=1): the driver on a page, and the fake backend with the client scripts of the app ----------------
PROBE_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>Probe</title><!--SUTRA-BOOT--></head>
<body><input id="box"><button id="go">Go</button><p id="out"></p><ul><li class="item">a</li><li class="item">b</li></ul>
<script>
document.getElementById('go').addEventListener('click', function () { document.getElementById('out').textContent = 'clicked'; });
document.getElementById('go').addEventListener('mouseenter', function () { this.setAttribute('data-hot', 'yes'); });
document.getElementById('box').addEventListener('keydown', function (e) { if (e.key === 'Enter') document.getElementById('out').textContent = 'entered:' + this.value; });
window.theme = (function () { try { return localStorage.getItem('j2theme'); } catch (e) { return 'blocked'; } })();
</script></body></html>"""


@pytest.mark.browser
def test_the_driver_clicks_types_presses_waits_and_takes_a_picture_in_a_real_chrome(browser, fake, tmp_path):
    browser.goto(fake.page("probe", PROBE_HTML))
    assert browser.js("document.title") == "Probe" and browser.exists("#go") and browser.count(".item") == 2
    assert browser.text("#go") == "Go" and browser.text("#nothing") is None and not browser.exists("#nothing")
    assert browser.js("document.getElementById('go').hasAttribute('data-hot')") is False
    browser.hover("#go")
    assert browser.wait_for("document.getElementById('go').getAttribute('data-hot') === 'yes'") is True
    assert browser.text("#out") == ""  # a hover is not a click
    browser.click("#go")
    assert browser.wait_for("document.getElementById('out').textContent === 'clicked'") is True
    browser.type("#box", "hello")
    browser.press("Enter")
    assert browser.wait_for("document.getElementById('out').textContent === 'entered:hello'") is True
    picture = browser.shot(tmp_path / "shots" / "probe.png")
    assert picture.read_bytes().startswith(b"\x89PNG\r\n\x1a\n") and picture.stat().st_size > 500
    with pytest.raises(cdp.BrowserError, match="^no element matches '#nothing'$"):
        browser.click("#nothing")
    with pytest.raises(cdp.JSError, match="ReferenceError"):
        browser.js("nothingDefinedHere()")
    with pytest.raises(TimeoutError, match="still false"):
        browser.wait_for("false", timeout=0.2)
    assert browser.js("new Promise(r => setTimeout(() => r(7), 50))") == 7  # a promise is awaited
    assert browser.console_errors == []


COVER_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>Cover</title><!--SUTRA-BOOT--></head><body style="margin:0">
<button id="go" style="position:absolute;left:100px;top:100px;width:120px;height:40px">Go</button>
<div id="cover" class="veil" style="position:fixed;inset:0;background:rgba(0,0,0,.1)"><h3 style="margin:100px 0 0 100px">A card</h3></div>
<div id="out"></div>
<script>document.getElementById('go').addEventListener('click', function (e) { document.getElementById('out').textContent = 'clicked at ' + Math.round(e.clientX); });</script>
</body></html>"""


@pytest.mark.browser
def test_a_click_a_cover_would_take_is_refused_by_name_and_a_button_that_is_still_moving_is_clicked_where_it_stops(browser, fake):
    """The welcome card of Home is a full-screen dialog: a click on the page behind it used to do nothing and the test waited 40 s for the effect. And a button
    that moves between the reading of its place and the press (a pane still filling in) was clicked at the place it had left."""
    browser.goto(fake.page("cover", COVER_HTML))
    with pytest.raises(cdp.BrowserError, match=r"^a click on '#go' would not reach it: h3 in div#cover\.veil is on top of it, at \(160, 120\), after 0\.5 s$"):
        browser.click("#go", timeout=0.5)                                          # what is hit is the card's heading: it is named with the card it is in
    assert browser.text("#out") == ""
    browser.js("document.getElementById('cover').remove()")
    browser.js("(() => { const b = document.getElementById('go'); b.style.transition = 'left 300ms linear'; b.style.left = '500px'; })()")        # slides while it is aimed at
    browser.click("#go")
    assert browser.text("#out") == "clicked at 560"                             # the middle of the button where it stopped (500 + 120 / 2), not where it was


@pytest.mark.browser
def test_the_theme_and_the_size_reach_the_next_page(browser, fake):
    url = fake.page("probe", PROBE_HTML)
    browser.set_theme("dark")
    browser.goto(url)
    assert browser.js("window.theme") == "dark" and browser.js("matchMedia('(prefers-color-scheme: dark)').matches") is True
    browser.set_theme("light")
    browser.reload()
    assert browser.js("window.theme") == "light" and browser.js("matchMedia('(prefers-color-scheme: dark)').matches") is False
    browser.set_theme("system", "dark")
    browser.reload()
    assert browser.js("window.theme") == "system" and browser.js("matchMedia('(prefers-color-scheme: dark)').matches") is True
    browser.set_size(390, 700)
    assert browser.js("innerWidth") == 390 and browser.js("innerHeight") == 700
    browser.set_size(1440, 900)
    assert browser.js("innerWidth") == 1440


@pytest.mark.browser
def test_console_errors_failed_requests_dialogs_and_csp_violations_are_collected(browser, fake, make_fake_server, tmp_path):
    browser.goto(fake.page("probe", PROBE_HTML))
    browser.js("console.error('from the test', 3)")
    browser.js("console.log('only a log')")
    browser.js("setTimeout(function () { throw new Error('late failure'); }, 0)")
    wait_until(lambda: len(browser.console_errors) >= 2)
    assert browser.console_errors[0] == "from the test 3" and "Error: late failure" in browser.console_errors[1]
    assert not any("only a log" in line for line in browser.console_errors)
    browser.clear_diagnostics()
    assert browser.js("fetch('/api/graph/nodes/nobody').then(r => r.status)") == 404
    assert browser.js("fetch('/api/chats/cs_org/retry', {method: 'POST'}).then(r => r.status)") == 401
    wait_until(lambda: len(browser.failed_requests) >= 2)
    assert [(f["method"], f["status"], f["url"].rsplit("/api/", 1)[1]) for f in browser.failed_requests] == [
        ("GET", 404, "graph/nodes/nobody"), ("POST", 401, "chats/cs_org/retry")]
    browser.expect_failed("/api/graph/nodes/nobody")
    assert browser.js("fetch('/api/graph/nodes/nobody').then(r => r.status)") == 404
    wait_until(lambda: len(browser.expected_failures) == 1)
    assert len(browser.failed_requests) == 2
    assert browser.js("alert('hello'); 5") == 5 and browser.dialogs == [{"type": "alert", "message": "hello"}]
    browser.clear_diagnostics()
    # a script the policy does not name is blocked, and the driver sees the violation as a console error
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "home.html").write_text('<!doctype html><html><head><!--SUTRA-BOOT--></head><body>'
                                     '<script>window.hashed = true;</script><script type="text/javascript">window.loose = true;</script>'
                                     '</body></html>', encoding="utf-8")
    server = make_fake_server(pages_dir=pages)
    browser.goto(server.url + "/")
    assert browser.js("window.hashed === true") is True and browser.js("window.loose === true") is False
    wait_until(lambda: browser.console_errors)
    assert all("Content Security Policy" in line or "Refused to execute" in line for line in browser.console_errors), browser.console_errors
    browser.clear_diagnostics()


STUB_VIEWS = {
    "graph_layout.js": "", "chart_marks.js": "", "graph_render.js": "", "fnode_view.js": "", "chat_view.js": "", "fluid.js": "", "chat_scroll.js": "", "chat_draft.js": "",
    "graph_view.js": "window.GraphView = {create: function (host, opts) { window.__gv = {host: host, opts: opts, updates: [], live: []};"
                     " return {update: function (g) { window.__gv.updates.push(g); }, setLive: function (s) { window.__gv.live.push(s); }}; }};",
    "orgchart_view.js": "window.OrgChartView = {create: function (host, opts) { window.__ov = {host: host, opts: opts, updates: []};"
                        " return {update: function (c, l) { window.__ov.updates.push([c, l]); }}; }};",
    "node_panel.js": "window.NodePanel = {mount: function (root, opts) { window.__np = {root: root, opts: opts, opened: []};"
                     " return {open: function (id, tab) { window.__np.opened.push([id, tab]); return Promise.resolve(); }}; }};",
}


@pytest.fixture()
def mount_server(make_fake_server, tmp_path):
    """The fake with the REAL client scripts (sutra_ctx.js, sutra_events.js) and stand-ins for the views other packages build."""
    static = tmp_path / "static"
    (static / "js").mkdir(parents=True)
    (static / "css").mkdir()
    real = REPO / "sutra_app" / "ui" / "static" / "js"
    for name in ("sutra_ctx.js", "sutra_events.js"):
        shutil.copy(real / name, static / "js" / name)
    for name, source in STUB_VIEWS.items():
        (static / "js" / name).write_text(source, encoding="utf-8")
    for name in ("j2.css", "sutra-graph.css", "sutra-panel.css"):
        (static / "css" / name).write_text("/* stand-in */\n", encoding="utf-8")
    return make_fake_server(static_dir=static)


@pytest.mark.browser
def test_the_graph_mount_page_draws_what_the_server_gives_and_refetches_once_per_event(browser, mount_server):
    fake = mount_server.client
    fake.stage("2")
    browser.goto(fake.mount_url("graph"))
    browser.wait_for("window.mounted === true && window.liveState === 'live'")
    assert browser.js("window.mountErrors") == [] and browser.js("window.__gv.opts.mode") == "graph"
    assert browser.js("window.__gv.opts.level") == "full" and browser.js("window.__gv.opts.scope") == "all"
    assert browser.js("window.__gv.updates.length") == 1 and browser.js("window.__gv.updates[0].nodes.length") == 8
    assert browser.js("window.__gv.live.includes('live')") is True
    assert queries_of(fake, "/api/graph") == ["level=full"]
    fake.stage("3")
    fake.wait_subscribers(1)
    fake.emit("graph.updated")
    browser.wait_for("window.__gv.updates.length === 2")
    assert browser.js("window.events") == ["graph.updated"] and queries_of(fake, "/api/graph") == ["level=full", "level=full"]
    # a burst, sent from the page so that the four arrive within a few milliseconds: one refetch (coalesced, 100 ms)
    assert browser.js("Promise.all(Array.from({length: 4}, () => fetch('/__fake/emit', {method: 'POST', "
                      "headers: {'Content-Type': 'application/json'}, body: JSON.stringify({event: 'graph.updated'})}).then(r => r.status)))") == [200] * 4
    browser.wait_for("window.__gv.updates.length >= 3")
    time.sleep(0.4)
    assert browser.js("window.__gv.updates.length") == 3 and len(queries_of(fake, "/api/graph")) == 3
    assert browser.js("window.__gv.updates[2].nodes.find(n => n.id === 'web.adaptation').status") == "running"  # stage 3
    browser.expect_failed("/api/graph")
    fake.fail("/api/graph", 500)
    fake.emit("graph.updated")
    browser.wait_for("window.mountErrors.length === 1")  # the page keeps its last good graph and reports the failure
    assert browser.js("window.__gv.updates.length") == 3
    fake.fail("/api/graph", None)


@pytest.mark.browser
def test_the_chart_mount_page_gives_the_view_the_chart_and_its_change_log(browser, mount_server):
    fake = mount_server.client
    fake.stage("full")
    browser.goto(fake.mount_url("graph", mode="chart", dept="web"))
    browser.wait_for("window.mounted === true")
    assert browser.js("window.mountErrors") == [] and browser.js("window.__ov.opts.dept") == "web"
    assert browser.js("window.__ov.updates[0][0].nodes.length") == 5 and browser.js("window.__ov.updates[0][1].length") == 6
    assert queries_of(fake, "/api/chart") == [""] and queries_of(fake, "/api/chart/changes") == ["limit=50"]
    fake.emit("chart.changed")
    browser.wait_for("window.__ov.updates.length === 2")
    browser.goto(fake.mount_url("graph", level="chart", dept="web"))
    browser.wait_for("window.mounted === true")
    assert browser.js("window.__gv.opts.level") == "chart" and browser.js("window.__gv.opts.scope") == "this"
    assert queries_of(fake, "/api/graph") == ["level=chart&dept=web"]


@pytest.mark.browser
def test_the_panel_mount_page_opens_the_node_it_is_asked_for_on_the_graph_it_loaded(browser, mount_server):
    fake = mount_server.client
    fake.stage("2")
    browser.goto(fake.mount_url("panel", open="web.identity", tab="details"))
    browser.wait_for("window.__np && window.__np.opened.length === 1")
    assert browser.js("window.__np.opened") == [["web.identity", "details"]] and browser.js("window.mountErrors") == []
    assert browser.js("window.__np.opts.getGraph().nodes.length") == 8
    browser.js("window.__np.opts.navigate('/d/web/?view=simple')")
    assert browser.js("window.navigated") == "/d/web/?view=simple"


@pytest.mark.browser
def test_the_scripted_first_task_plays_in_a_real_chrome_through_the_real_event_client(browser, mount_server):
    fake = mount_server.client
    browser.goto(fake.mount_url("graph"))
    browser.wait_for("window.mounted === true && window.liveState === 'live'")
    fake.wait_subscribers(1)
    status, answer = fake.post("/api/chats/cs_org/messages", {"text": "A website for my cafe"})
    assert status == 202 and answer["turn"] == "started"
    fake.wait_flows()
    browser.wait_for("window.__gv.updates.some(g => g.nodes.some(n => n.id === 'web.identity'))")
    seen = set(browser.js("window.events"))
    assert {"chat.message", "chat.turn", "chart.changed", "graph.updated", "task.updated", "needs_you.changed"} <= seen


def queries_of(fake, path: str) -> list[str]:
    """The raw query strings of the requests the fake saw for exactly this path, oldest first."""
    return [entry["query"] for entry in fake.log() if entry["path"] == path]


# =====================================================================================================================
# 7. scripts/capture_j2_fixtures.py, against a stand-in J2 checkout (tools/standin_j2) and, on request, the real J2
# =====================================================================================================================
def load_capture_module():
    spec = importlib.util.spec_from_file_location("capture_j2_fixtures", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["capture_j2_fixtures"] = module
    spec.loader.exec_module(module)
    return module


capture = load_capture_module()
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is needed for J2's two harnesses")
PLANTED = {"ANTHROPIC_API_KEY": "sk-planted-secret-value", "GITHUB_TOKEN": "ghp_planted_token_value", "J2_BUDGET": "budget-planted-77"}


def git_in(folder: Path, *args: str) -> str:
    done = subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.com", *args], cwd=folder, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return done.stdout


def standin_checkout(root: Path, *, repository: bool = True) -> Path:
    """A copy of the stand-in J2 checkout, committed to its own git repository (so the script can say its commit)."""
    j2 = root / "j2"
    shutil.copytree(TOOLS / "standin_j2", j2, ignore=shutil.ignore_patterns("__pycache__"))
    if repository:
        git_in(j2, "init", "-q")
        git_in(j2, "add", "-A")
        git_in(j2, "commit", "-q", "-m", "the stand-in")
    return j2


def quick_capture(j2: Path, **overrides):
    options = {"brief": capture.BRIEF, "max_state_bytes": capture.MAX_STATE_BYTES, "timeout": 30, "commit": None}
    options.update(overrides)
    return capture.capture(j2, sys.executable, NODE, options["brief"], options["max_state_bytes"], options["timeout"], log=lambda text: None,
                           commit=options["commit"])


@pytest.fixture(scope="module")
def standin(tmp_path_factory):
    """(the stand-in checkout, one capture of it). The stand-in tells in its state what the capture did to its process."""
    if NODE is None:
        pytest.skip("node is needed for J2's two harnesses")
    j2 = standin_checkout(tmp_path_factory.mktemp("standin"))
    with pytest.MonkeyPatch.context() as patch:
        for name, value in PLANTED.items():
            patch.setenv(name, value)  # the developer's own environment: none of it may reach the J2 process or the files
        files = quick_capture(j2)
    return j2, files


@pytest.fixture(scope="module")
def quiet(tmp_path_factory):
    """A stand-in that does not tell the random port and scratch folder, so two captures of it can be equal; its server has an edit
    that is not committed (the capture must be fine with that). (the checkout, one capture)"""
    if NODE is None:
        pytest.skip("node is needed for J2's two harnesses")
    j2 = standin_checkout(tmp_path_factory.mktemp("quiet"))
    source = (j2 / "j2_server.py").read_text(encoding="utf-8")
    for telling in ('"argv": sys.argv[1:],', '"env": {name: os.environ.get(name) for name in WATCHED}, "env_names": sorted(os.environ),'):
        assert telling in source
        source = source.replace(telling, "")
    (j2 / "j2_server.py").write_text(source, encoding="utf-8")  # an edit nobody committed
    return j2, quick_capture(j2)


# ---- the small pure functions -------------------------------------------------------------------------------------------------
def test_rail_tabs_reads_the_tab_names_of_the_sections_not_the_buttons_before_them():
    page = ('<nav class="rail tabs" id="rail"><button data-tab="map">Map</button><div id="railsub">'
            '<button data-tab="goal"></button><button role="tab" data-tab="workflows" aria-selected="false"></button>'
            '<button data-tab="run_settings"></button></div></nav><button data-tab="outside"></button>')
    assert capture.rail_tabs(page) == ["goal", "workflows", "run_settings"]


def test_rail_tabs_leaves_out_the_map_tab_that_the_page_keeps_in_the_rails_panel():
    """J2's page since the icon rail: every tab button sits in #railsub, the Map's first (hidden); the Map has its own rail item."""
    page = ('<nav class="rail tabs" id="rail" aria-label="x"><button data-ri="map"></button><div class="railsub" id="railsub">'
            '<div class="rpool"><button role="tab" data-tab="map" hidden></button><button role="tab" data-tab="story" hidden></button>'
            '<button role="tab" data-tab="planmap"></button></div></div></nav><button data-tab="outside"></button>')
    assert capture.rail_tabs(page) == ["story", "planmap"]


def test_the_home_folder_paths_of_j2s_development_machine_are_not_recorded_and_no_other_is_let_through():
    body = (b'{"runs": [{"run": "a", "library": "/Users/someone/dev/library"}, {"run": "b", "library": "/home/someone/dev/library"}, '
            b'{"run": "c", "library": "/tmp/j2-live-library"}], "dir": "library"}')
    assert capture.scrub_home_paths(body) == (b'{"runs": [{"run": "a", "library": "not recorded"}, {"run": "b", "library": "not recorded"}, '
                                              b'{"run": "c", "library": "/tmp/j2-live-library"}], "dir": "library"}')
    assert capture.scrub_home_paths(b'{"a": 1}') == b'{"a": 1}'  # nothing to change: the same bytes
    capture.refuse_home_paths({"ok.json": b'{"library": "not recorded", "p": "/tmp/x/y/", "u": "/home"}'})  # none of these is a home folder
    with pytest.raises(capture.CaptureError, match=r"^an absolute home-folder path \(rule R5: none in any file of this product\) is in: a\.json, c\.html$"):
        capture.refuse_home_paths({"c.html": b"<p>/Users/me/x</p>", "ok.json": b"{}", "a.json": b'{"where": "/home/me/dev"}'})


def test_a_folders_digest_lists_every_file_by_content_and_ignores_a_git_folder(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "one.txt").write_bytes(b"1")
    (tmp_path / "two.txt").write_bytes(b"2")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_bytes(b"ref")
    expected = {"a/one.txt": hashlib.sha256(b"1").hexdigest(), "two.txt": hashlib.sha256(b"2").hexdigest()}
    assert capture.folder_digest(tmp_path) == expected
    (tmp_path / "two.txt").write_bytes(b"changed")
    assert capture.folder_digest(tmp_path) != expected and list(capture.folder_digest(tmp_path)) == ["a/one.txt", "two.txt"]
    assert capture.folder_digest(tmp_path / "nowhere") == {}


def test_the_parts_and_deliverables_of_the_studio_view_name_their_records():
    state = json.dumps({"studio": {"parts": [{"sec": "W-1"}, {"name": "no sec"}, {"sec": "Intro/Hero"}]}}).encode()
    assert capture.record_secs(state) == ["W-1", "Intro/Hero"]
    assert capture.record_secs(b"{}") == [] and capture.record_secs(b'{"studio": null}') == []
    assert capture.record_arts(json.dumps({"deliverables": [{"name": "Website"}, {"type": "x"}, {"name": "Menu card"}]}).encode()) == ["Website", "Menu card"]
    assert capture.record_arts(b"{}") == []
    assert capture.file_part("Menu card") == "Menu-card" and capture.file_part("Intro/Hero") == "Intro-Hero" and capture.file_part("W-1") == "W-1"
    assert capture.file_part("  a b.c_d ") == "a-b.c_d"


def test_the_commit_option_takes_a_full_commit_id_and_nothing_else():
    pin = "025e265c594564f47a2365874cd5a5cc5d0d20a6"
    assert capture.commit_id(pin) == pin
    for bad in ("025e265", "main", pin.upper(), pin + "0", ""):
        with pytest.raises(argparse.ArgumentTypeError, match="is not a full commit id"):
            capture.commit_id(bad)
    assert capture.build_parser().parse_args(["--j2", "/j2", "--commit", pin]).commit == pin
    with pytest.raises(SystemExit):
        capture.build_parser().parse_args(["--j2", "/j2", "--commit", "main"])


def test_atom_ids_lists_each_atom_of_the_state_once_in_order():
    state = {"workflows": [{"atoms": [{"id": "W-1.a1"}, {"id": "W-1.a2"}, {"no": "id"}]}, {"atoms": [{"id": "W-1.a1"}, {"id": "W-2.a1"}]},
                           {"atoms": None}, {}]}
    assert capture.atom_ids(state) == ["W-1.a1", "W-1.a2", "W-2.a1"]
    assert capture.atom_ids({}) == [] and capture.atom_ids({"workflows": None}) == []


def test_hashes_and_json_dumps_are_plain():
    assert capture.sha256_hex(b"abc") == hashlib.sha256(b"abc").hexdigest()
    assert capture.dump_json({"b": [1, 2], "a": "\u00e9"}) == '{"b":[1,2],"a":"\u00e9"}'.encode("utf-8")  # compact, UTF-8 not escapes, key order kept


def test_free_port_is_a_port_nothing_listens_on():
    import socket

    port = capture.free_port()
    assert 1024 <= port <= 65535
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", port))


def test_the_j2_process_gets_a_scrubbed_environment_and_nothing_of_the_developers(tmp_path):
    base = {"PATH": "/bin", "LANG": "en_US.UTF-8", "LC_ALL": "C", "SYSTEMROOT": "C:\\", "TEMP": "t", "TMP": "t", "HOME": "/Users/me",
            "ANTHROPIC_API_KEY": "sk-x", "GITHUB_TOKEN": "ghp-x", "J2_BUDGET": "5", "STUDIO_MOCK": "0", "TZ": "Asia/Kolkata", "PYTHONPATH": "/x"}
    env = capture.scrubbed_env(tmp_path, base)
    assert {k: env[k] for k in ("PATH", "LANG", "LC_ALL", "SYSTEMROOT", "TEMP", "TMP")} == {k: base[k] for k in ("PATH", "LANG", "LC_ALL", "SYSTEMROOT", "TEMP", "TMP")}
    assert env["HOME"] == str(tmp_path / "home") and env["TZ"] == "UTC" and env["STUDIO_MOCK"] == "1" and env["J2_CHROME"] == "none"
    assert env["J2_MEMORY"] == "0" and env["J2_RUNS_DIR"] == str(tmp_path / "runs")
    assert env["J2_MEMORY_FILE"] == str(tmp_path / "lessons.jsonl") and env["J2_PLAYBOOK_FILE"] == str(tmp_path / "playbooks.jsonl")
    assert env["PYTHONDONTWRITEBYTECODE"] == "1" and env["PYTHONHASHSEED"] == "0" and env["PYTHONUTF8"] == "1"
    assert set(env) == {"PATH", "LANG", "LC_ALL", "SYSTEMROOT", "TEMP", "TMP", "HOME", "TZ", "STUDIO_MOCK", "J2_CHROME", "J2_MEMORY", "J2_RUNS_DIR",
                        "J2_MEMORY_FILE", "J2_PLAYBOOK_FILE", "PYTHONDONTWRITEBYTECODE", "PYTHONHASHSEED", "PYTHONUTF8"}
    assert capture.scrubbed_env(tmp_path, {"PATH": "/bin"})["PATH"] == "/bin" and "LANG" not in capture.scrubbed_env(tmp_path, {"PATH": "/bin"})


def test_scrubbed_env_reads_the_process_environment_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-from-the-process")
    monkeypatch.setenv("LANG", "xx_XX.UTF-8")
    env = capture.scrubbed_env(tmp_path)
    assert env["LANG"] == "xx_XX.UTF-8" and "ANTHROPIC_API_KEY" not in env


@pytest.mark.skipif(shutil.which("git") is None, reason="git is needed")
def test_git_commands_are_read_only_questions_that_answer_none_outside_a_repository(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert capture.git(plain, "rev-parse", "HEAD") is None and capture.checkout_state(plain) is None
    assert capture.git(tmp_path / "missing", "status") is None  # a folder that is not there
    j2 = standin_checkout(tmp_path)
    assert capture.git(j2, "rev-parse", "HEAD").strip() == git_in(j2, "rev-parse", "HEAD").strip()
    assert capture.checkout_state(j2) == ""
    (j2 / "j2_ui.html").write_text("changed", encoding="utf-8")
    (j2 / "new" / "deep").mkdir(parents=True)
    (j2 / "new" / "deep" / "f.txt").write_text("x", encoding="utf-8")
    assert capture.checkout_state(j2) == " M j2_ui.html\n?? new/deep/f.txt\n"  # every untracked file, not just its folder


def test_git_missing_is_none(tmp_path, monkeypatch):
    monkeypatch.setattr(capture.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError("git")))
    assert capture.git(tmp_path, "status") is None
    monkeypatch.setattr(capture.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired("git", 30)))
    assert capture.git(tmp_path, "status") is None


def test_check_checkout_refuses_what_is_not_an_extraction_of_j2_a_python_that_cannot_run_or_a_missing_node(tmp_path):
    j2 = standin_checkout(tmp_path, repository=False)
    capture.check_checkout(j2, sys.executable, "/usr/bin/node")  # nothing is run here: the names are enough
    with pytest.raises(capture.CaptureError, match=r"^--j2 .*nowhere is not a folder$"):
        capture.check_checkout(tmp_path / "nowhere", sys.executable, "node")
    (j2 / "j2_graph_layout.js").unlink()
    (j2 / "j2_ui_render.js").unlink()
    with pytest.raises(capture.CaptureError, match=r"is not an extraction of prototypes/j2: missing j2_ui_render\.js, j2_graph_layout\.js$"):
        capture.check_checkout(j2, sys.executable, "node")
    j2 = standin_checkout(tmp_path / "again", repository=False)
    with pytest.raises(capture.CaptureError, match=r"^--j2-python .*no-python is not an executable file$"):
        capture.check_checkout(j2, str(tmp_path / "no-python"), "node")
    (tmp_path / "plain-file").write_text("x")
    with pytest.raises(capture.CaptureError, match="not an executable file$"):
        capture.check_checkout(j2, str(tmp_path / "plain-file"), "node")
    with pytest.raises(capture.CaptureError, match=r"^node is needed for the goldens \(put it on PATH or pass --node\)$"):
        capture.check_checkout(j2, sys.executable, None)


# ---- a whole capture of the stand-in ------------------------------------------------------------------------------------------
STANDIN_FILES = 78  # 23 route files + 7 agent views + 7 feeds + 6 answers + 4 records (2 parts, 2 deliverables) + 4 derived inputs + 26 goldens + the manifest


def test_the_capture_of_the_stand_in_makes_the_files_the_committed_set_has(standin):
    j2, files = standin
    committed = {p.name for p in J2_FIXTURES.iterdir() if p.is_file()}
    families = lambda names: {n for n in names if not n.startswith("record-")}  # noqa: E731  (one record per part and per deliverable: the stand-in has others)
    assert families(files) == families(committed) and len(files) == STANDIN_FILES
    assert {n for n in files if n.startswith("record-")} == {"record-W-1.json", "record-W-2.json", "record-art-Website.json", "record-art-Menu-card.json"}
    assert any(n.startswith("record-W-") for n in committed) and any(n.startswith("record-art-") for n in committed)
    assert all(isinstance(data, bytes) for data in files.values())


def test_the_routes_are_saved_as_the_server_answered_them(standin):
    j2, files = standin
    assert json.loads(files["runs.json"]) == {"live": "j2-standin-run", "runs": []}
    assert json.loads(files["plan.json"]) == {"found": False} and json.loads(files["board.json"])["schema"] == "board/1"
    assert files["site-latest.html"] == b"<!doctype html><title>Stand-in</title><p>site</p>"
    for who in (*FUNCTIONS, "W-1"):
        assert json.loads(files[f"agent-{who}.json"]) == {"schema": "agent/1", "who": who, "found": True}
    assert json.loads(files["agent-unknown.json"]) == {"schema": "agent/1", "who": "nobody", "found": False}
    state = json.loads(files["state.json"])
    assert state["status"] == "waiting" and state["total"] == 3 and state["brief"] == capture.BRIEF  # the run was asked and had answered


def test_the_routes_feeds_answers_and_records_of_sync_4_are_saved_as_the_server_answered_them(standin):
    j2, files = standin
    load = lambda name: json.loads(files[name])  # noqa: E731
    assert load("changes.json") == {"changes": []} and load("plan-map.json") == {"found": False}
    assert load("artifacts-groups.json")["schema"] == "artifacts-groups/1" and load("runlist.json")["live"] == "j2-standin-run"
    assert files["doc-prd.html"] == b"<p>This isn't written yet.</p>"
    assert files["view-site.html"] == b"<p>view of site/index.html</p>" and files["view-goal.html"] == b"<p>view of goal.json</p>"
    for who in J2_FUNCS:  # J2's six functions: a feed and an answer to the one question
        assert load(f"activity-{who}.json") == {"schema": "activity/1", "who": who, "found": True, "events": []}
        assert load(f"ask-{who}.json") == {"who": who, "answer": "From the records: " + capture.ASK_QUESTION, "from": "records"}
    assert load("activity-unknown.json") == {"schema": "activity/1", "who": "nobody", "found": False, "events": []}
    assert load("record-W-1.json") == {"schema": "studio/1", "sec": "W-1", "name": "Part W-1"}
    assert load("record-art-Menu-card.json") == {"schema": "studio/1", "art": "Menu card"}  # a deliverable's name, made a file name


def test_the_catalog_is_saved_with_the_home_folder_paths_not_recorded(standin):
    j2, files = standin
    assert [run["library"] for run in json.loads(files["catalog.json"])["runs"]] == ["not recorded", "/tmp/standin-library"]
    assert not any(b"/Users/" in data for data in files.values())  # the made-up home path of the stand-in's catalog is in no file


def test_the_j2_process_ran_in_its_folder_under_a_frozen_clock_in_a_scrubbed_environment(standin):
    j2, files = standin
    state = json.loads(files["state.json"])
    assert state["cwd"] == str(j2.resolve()) and state["bytecode"] is True and state["argv"][0] == "--port" and state["argv"][2] == "--no-browser"
    assert state["now"] == capture.FIXED_TIME == 1793786404  # 2026-11-04T10:00:04Z
    assert state["iso"] == "2026-11-04T10:00:04" and state["stamp"] == "2026-11-04 10:00:04"
    env = state["env"]
    assert (env["TZ"], env["STUDIO_MOCK"], env["J2_CHROME"], env["J2_MEMORY"]) == ("UTC", "1", "none", "0")
    assert env["PYTHONDONTWRITEBYTECODE"] == "1" and env["PYTHONHASHSEED"] == "0" and env["PYTHONUTF8"] == "1"
    scratch = Path(env["HOME"]).parent
    assert scratch.name.startswith("j2-capture-") and env["J2_RUNS_DIR"] == str(scratch / "runs")
    assert env["J2_MEMORY_FILE"] == str(scratch / "lessons.jsonl") and env["J2_PLAYBOOK_FILE"] == str(scratch / "playbooks.jsonl")
    assert not scratch.exists()  # the scratch folder is gone
    for name, value in PLANTED.items():
        assert env[name] is None and name not in state["env_names"]
        assert all(value.encode() not in data for data in files.values()), name  # not in any file either


def test_the_previews_are_asked_for_once_per_atom_and_only_those_with_a_page_are_kept_as_replies(standin):
    j2, files = standin
    previews = json.loads(files["previews.json"])
    assert previews == {"W-1.a1": "<p>W-1.a1</p>", "W-1.a2": "<p>W-1.a2</p>", "W-2.a1": "<p>W-2.a1</p>"}  # W-1.a1 is in two workflows
    assert set(json.loads(files["preview-replies.json"])) == {"W-1.a1", "W-1.a2", "W-2.a1"}
    assert json.loads(files["preview-replies.json"])["W-2.a1"] == {"anchor": "a-1", "html": "<p>W-2.a1</p>"}


def test_the_harness_inputs_are_made_from_the_routes_and_the_pages_rail(standin):
    j2, files = standin
    docs = json.loads(files["render-docs.json"])
    assert set(docs) == {"docs", "map", "railtabs", "plan", "planmap", "activity", "changes", "journey", "msgs", "arts", "artifacts", "agent"}
    assert docs["railtabs"] == ["goal", "workflows", "audit"] and docs["map"] == json.loads(files["map.json"])  # the Map's own tab is left out
    assert docs["docs"] == json.loads(files["docs.json"]) and docs["plan"] == json.loads(files["plan.json"])
    assert docs["agent"] == json.loads(files["agent-identity.json"])
    assert docs["planmap"] == json.loads(files["plan-map.json"]) and docs["activity"] == json.loads(files["activity-adaptation.json"])  # Adaptation's feed
    assert docs["changes"] == [] and docs["journey"] is True and docs["msgs"] == json.loads(files["state.json"])["chat"]
    assert docs["arts"] == json.loads(files["artifacts.json"])  # what the Studio view reads at /api/artifacts
    assert docs["artifacts"] == {"tree": json.loads(files["artifacts-tree.json"]), "groups": json.loads(files["artifacts-groups.json"])}
    assert json.loads(files["maps.json"]) == {"j2-standin-run": json.loads(files["map.json"])}  # keyed by the map's own run id


def test_the_goldens_are_what_the_page_harnesses_printed(standin):
    j2, files = standin
    golden = {key: json.loads(files[f"golden-{key}.json"]) for key in J2_GOLDENS}
    assert golden == {
        "simple": "chat:1", "sprog": "status:waiting", "workflows": "W-1:2,W-2:2", "rail": ["goal", "workflows", "audit"],
        "needs": "", "map": "nodes:1", "agent": "identity", "finish": "", "journey": {"stops": 0}, "journeyhtml": "journey:0",
        "sframe": "/site/v0?t=1793786404000",  # the page puts the time in it: node's clock is frozen at the capture's (in ms)
        "needids": [], "railst": {"tabs": 3}, "planmap": "planmap:false", "msgfns": [["you"]], "feed": "feed:adaptation:0",
        "teamwork": "teamwork:1", "plan": "plan:2", "team": "team:2", "status": "status:waiting", "views": "views:deliverables,records",
        "files": "", "parts": ["W-1", "W-2"], "tabs": ["site", "team"], "inline": "", "layout": [{"run": "j2-standin-run", "nodes": 1}]}
    assert files["golden-simple.json"] == b'"chat:1"'  # compact one-line JSON


def test_the_manifest_names_the_commit_the_brief_the_clock_and_every_other_file(standin):
    j2, files = standin
    manifest = json.loads(files["MANIFEST.json"])
    assert files["MANIFEST.json"].endswith(b"}\n") and files["MANIFEST.json"].startswith(b'{\n  "schema"')  # indented, one final newline
    assert manifest["schema"] == "j2-fixtures/1" and manifest["mock"] is True and manifest["brief"] == capture.BRIEF
    assert manifest["j2_commit"] == git_in(j2, "rev-parse", "HEAD").strip() and manifest["clock"] == capture.FIXED_TIME
    assert manifest["harness"] == {"page": "j2_ui.html", "render": ["state.json", "previews.json", "render-docs.json"], "layout": ["maps.json"],
                                   "goldens": [f"golden-{k}.json" for k in J2_GOLDENS]}
    assert list(manifest["files"]) == sorted(manifest["files"]) and set(manifest["files"]) == set(files) - {"MANIFEST.json"}
    for name, info in manifest["files"].items():
        assert info == {"bytes": len(files[name]), "sha256": hashlib.sha256(files[name]).hexdigest()}, name


def test_a_checkout_that_is_not_a_repository_has_no_commit_in_the_manifest_unless_one_is_given(tmp_path):
    j2 = standin_checkout(tmp_path, repository=False)
    manifest = json.loads(capture.manifest(j2, "a brief", {"a.json": b"1"}))
    assert manifest["j2_commit"] is None and manifest["brief"] == "a brief" and manifest["files"] == {
        "a.json": {"bytes": 1, "sha256": hashlib.sha256(b"1").hexdigest()}}
    pin = "025e265c594564f47a2365874cd5a5cc5d0d20a6"  # an extraction made by `git archive` knows its commit only from --commit
    assert json.loads(capture.manifest(j2, "a brief", {"a.json": b"1"}, pin))["j2_commit"] == pin
    repository = standin_checkout(tmp_path / "repo")
    assert json.loads(capture.manifest(repository, "b", {}, pin))["j2_commit"] == pin  # the given commit wins over the folder's own HEAD
    assert json.loads(capture.manifest(repository, "b", {}))["j2_commit"] == git_in(repository, "rev-parse", "HEAD").strip()


# ---- the capture does not touch J2, and says so when it did ---------------------------------------------------------------------
@needs_node
def test_a_j2_that_writes_into_its_own_folder_is_caught(tmp_path):
    j2 = standin_checkout(tmp_path)
    with pytest.raises(capture.CaptureError) as caught:
        quick_capture(j2, brief="STRAY: write a file")
    assert str(caught.value) == ("the J2 checkout changed during the capture (git status before and after differ):\n"
                                 "\n--\n?? stray.txt\n")  # what it was (clean), then what it is
    assert (j2 / "stray.txt").is_file()


@needs_node
def test_a_j2_extraction_that_is_written_into_is_caught_by_the_content_of_its_files(tmp_path):
    """An extraction made by `git archive` is not a repository: `git status` has nothing to say, the digest of its files does."""
    j2 = standin_checkout(tmp_path, repository=False)
    assert capture.checkout_state(j2) is None
    with pytest.raises(capture.CaptureError) as caught:
        quick_capture(j2, brief="STRAY: write a file")
    assert str(caught.value) == "the J2 folder changed during the capture (files added, removed or changed): stray.txt"
    (j2 / "stray.txt").unlink()
    assert len(quick_capture(j2)) == STANDIN_FILES  # and without the write the same folder is fine: no repository, no commit
    assert json.loads(quick_capture(j2, commit="025e265c594564f47a2365874cd5a5cc5d0d20a6")["MANIFEST.json"])["j2_commit"] == "025e265c594564f47a2365874cd5a5cc5d0d20a6"


@needs_node
def test_a_checkout_with_uncommitted_edits_is_fine_when_the_capture_leaves_them_alone(quiet):
    j2, files = quiet
    assert capture.checkout_state(j2) == " M j2_server.py\n" and len(files) == STANDIN_FILES  # captured with the edit in place, and still there


# ---- the J2 server as a child process --------------------------------------------------------------------------------------------
def server_checkout(tmp_path, source: str) -> Path:
    j2 = tmp_path / "j2"
    j2.mkdir()
    (j2 / "j2_server.py").write_text(source, encoding="utf-8")
    return j2


def test_a_server_that_exits_at_once_is_reported_with_its_code_and_its_last_words(tmp_path):
    j2 = server_checkout(tmp_path, "import sys\nprint('cannot bind')\nsys.exit(3)\n")
    with pytest.raises(capture.CaptureError, match=r"J2's server exited with code 3:\ncannot bind"):
        with capture.J2Server(j2, sys.executable, tmp_path / "work"):
            pass


def test_a_server_that_never_answers_is_stopped_and_reported_after_the_ready_time(tmp_path, monkeypatch):
    started = []

    class Recording(subprocess.Popen):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            started.append(self)

    monkeypatch.setattr(capture.subprocess, "Popen", Recording)
    j2 = server_checkout(tmp_path, "import time\nprint('starting slowly', flush=True)\ntime.sleep(60)\n")
    waiting = capture.J2Server(j2, sys.executable, tmp_path / "work", ready_timeout=0.6)
    start = time.monotonic()
    with pytest.raises(capture.CaptureError, match=r"^J2's server did not answer within 0\.6 s:\nstarting slowly\n$"):
        waiting.__enter__()
    assert time.monotonic() - start < 30
    (process,) = started
    assert process.poll() is not None and waiting.process is None  # it was stopped, not left running


def test_a_server_that_ignores_sigterm_is_killed_after_the_grace_time(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, "STOP_GRACE_S", 0.3)
    source = ("import http.server, signal, sys\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\nport = int(sys.argv[sys.argv.index('--port') + 1])\n"
              "class H(http.server.BaseHTTPRequestHandler):\n    def do_GET(self):\n        self.send_response(200)\n"
              "        self.send_header('Content-Length', '2')\n        self.end_headers()\n        self.wfile.write(b'{}')\n"
              "    def log_message(self, *a):\n        pass\nhttp.server.ThreadingHTTPServer(('127.0.0.1', port), H).serve_forever()\n")
    j2 = server_checkout(tmp_path, source)
    with capture.J2Server(j2, sys.executable, tmp_path / "work") as server:
        process = server.process
        assert server.get("/api/runs") == (200, b"{}")
        started = time.monotonic()
    assert process.poll() is not None and server.process is None  # gone, and stopping twice is fine
    assert time.monotonic() - started >= 0.27
    server.stop()


@pytest.fixture(scope="module")
def shared_j2(tmp_path_factory):
    """One running stand-in J2 for the tests that only talk to it; `server` resets its brief and its breaks before each test."""
    root = tmp_path_factory.mktemp("shared")
    j2 = standin_checkout(root, repository=False)
    with capture.J2Server(j2, sys.executable, root / "work") as running:
        yield running, root


@pytest.fixture()
def server(shared_j2):
    running, _ = shared_j2
    assert running.post("/__standin/reset", {}) == 200
    return running


def break_route(server, path: str, status: int) -> None:
    assert server.post("/__standin/break", {"path": path, "status": status}) == 200


def test_a_server_is_asked_to_stop_with_sigterm_before_anything_else(tmp_path):
    source = ("import http.server, os, signal, sys\nport = int(sys.argv[sys.argv.index('--port') + 1])\n"
              "def goodbye(*args):\n    open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'goodbye'), 'w').write('SIGTERM')\n    os._exit(0)\n"
              "signal.signal(signal.SIGTERM, goodbye)\n"
              "class H(http.server.BaseHTTPRequestHandler):\n    def do_GET(self):\n        self.send_response(200)\n"
              "        self.send_header('Content-Length', '2')\n        self.end_headers()\n        self.wfile.write(b'{}')\n"
              "    def log_message(self, *a):\n        pass\nhttp.server.ThreadingHTTPServer(('127.0.0.1', port), H).serve_forever()\n")
    j2 = server_checkout(tmp_path, source)
    with capture.J2Server(j2, sys.executable, tmp_path / "work") as running:
        process = running.process
    assert (j2 / "goodbye").read_text() == "SIGTERM" and process.returncode == 0  # it left by itself when asked


def test_the_server_gets_its_scratch_folders_and_a_clock_launcher(shared_j2, tmp_path):
    running, root = shared_j2
    assert (root / "work" / "runs").is_dir() and (root / "work" / "home").is_dir()
    launcher = (root / "work" / "frozen_clock.py").read_text()
    assert f"FIXED = {capture.FIXED_TIME}" in launcher and "runpy.run_path" in launcher
    assert running.base == f"http://127.0.0.1:{running.port}" and "stand-in J2 on" in running.log_tail()
    assert running.get("/nope") == (404, b'{"error": "not found"}')  # a 4xx is an answer, not an error
    assert running.log_tail(10) == running.log_path.read_text()[-10:]
    unused = capture.J2Server(tmp_path / "j2", sys.executable, tmp_path / "other")
    assert unused.log_tail() == "(no log)"
    unused.log_path.parent.mkdir()
    unused.log_path.write_text("a" * 1000 + "b" * 1500, encoding="utf-8")
    assert unused.log_tail() == "b" * 1500 and unused.log_tail(10) == "b" * 10 and unused.log_tail(3000) == "a" * 1000 + "b" * 1500


def test_a_work_folder_can_be_used_by_one_server_after_another(tmp_path):
    j2 = standin_checkout(tmp_path, repository=False)
    work = tmp_path / "work"
    for _ in range(2):  # the scratch folders exist the second time
        with capture.J2Server(j2, sys.executable, work) as running:
            assert running.get("/api/runs")[0] == 200
    assert (work / "runs").is_dir() and (work / "home").is_dir()


def test_run_team_sends_the_brief_and_waits_until_the_team_has_answered(server):
    assert json.loads(server.get("/api/state")[1])["status"] == "idle"
    capture.run_team(server, "A short brief", 20)
    state = json.loads(server.get("/api/state")[1])
    assert state["status"] == "waiting" and state["total"] == 3 and state["brief"] == "A short brief"


def test_run_team_names_the_answer_when_the_server_refuses_the_brief(server):
    with pytest.raises(capture.CaptureError, match=r"^POST /api/say answered 500$"):
        capture.run_team(server, "SAYFAIL", 5)


def test_run_team_waits_for_an_answer_not_only_for_the_waiting_status(server):
    with pytest.raises(capture.CaptureError, match=r"^J2 did not finish the mock run within 0\.5 s:\nstand-in J2 on"):
        capture.run_team(server, "ONE: waiting, but with no answer in the chat", 0.5)
    assert json.loads(server.get("/api/state")[1])["total"] == 1
    capture.run_team(server, "TWO: waiting, with the brief and one answer", 20)  # two lines are enough
    assert json.loads(server.get("/api/state")[1])["total"] == 2


def test_run_team_gives_up_when_the_team_never_finishes(server):
    with pytest.raises(capture.CaptureError, match=r"J2 did not finish the mock run within 0\.5 s:\nstand-in J2 on"):
        capture.run_team(server, "HANG", 0.5)


def test_run_team_reports_a_server_that_dies_during_the_run(tmp_path):
    j2 = standin_checkout(tmp_path, repository=False)
    with capture.J2Server(j2, sys.executable, tmp_path / "work") as dying:
        with pytest.raises(capture.CaptureError, match=r"J2's server died during the run:"):
            capture.run_team(dying, "DIE", 30)


# ---- collecting and deriving -----------------------------------------------------------------------------------------------------
def test_a_state_over_the_limit_is_refused_with_the_limit_in_the_message(server):
    capture.run_team(server, "BIG", 20)
    with pytest.raises(capture.CaptureError, match=r"^the state is \d{4,} bytes, over --max-state-bytes 3000: use a shorter --brief$"):
        capture.collect_routes(server, 3000)
    assert len(capture.collect_routes(server, 100_000)["state.json"]) > 5000  # and under the limit it is saved


@pytest.mark.parametrize("path,message", [
    ("/api/refs", r"^GET /api/refs answered 404$"),
    ("/api/agent?who=nobody", r"^GET /api/agent\?who=nobody answered 404$"),
    ("/api/state", r"^GET /api/state answered 404$"),
    ("/api/plan-map", r"^GET /api/plan-map answered 404$"),
    ("/api/activity?who=audit", r"^GET /api/activity\?who=audit answered 404$"),
    ("/api/record?sec=W-2", r"^GET /api/record\?sec=W-2 answered 404$"),
    ("/api/record?art=Menu%20card", r"^GET /api/record\?art=Menu card answered 404$"),  # a name with a space is asked for quoted
    ("/view?name=goal.json", r"^GET /view\?name=goal\.json answered 404$"),
    ("/api/ask", r"^POST /api/ask \(who identity\) answered 404$"),  # a POST path can be broken too
])
def test_a_route_that_does_not_answer_200_stops_the_capture_and_names_it(server, path, message):
    capture.run_team(server, "a brief", 20)
    break_route(server, path, 404)
    with pytest.raises(capture.CaptureError, match=message):
        capture.collect_routes(server, 100_000)


def test_every_route_every_agent_view_every_feed_every_record_and_every_answer_is_asked_for_once(server):
    capture.run_team(server, "a brief", 20)
    routes = capture.collect_routes(server, 100_000)
    assert list(routes) == (list(capture.ROUTE_FILES) + [f"agent-{who}.json" for who in (*FUNCTIONS, "W-1")] + ["agent-unknown.json"]
                            + [f"activity-{who}.json" for who in J2_FUNCS] + ["activity-unknown.json"]
                            + ["record-W-1.json", "record-W-2.json", "record-art-Website.json", "record-art-Menu-card.json"]
                            + [f"ask-{who}.json" for who in J2_FUNCS])
    assert len(capture.ROUTE_FILES) == 23 and len(routes) == 23 + 7 + 7 + 4 + 6


def test_a_preview_route_that_does_not_answer_200_stops_the_capture(server):
    capture.run_team(server, "a brief", 20)
    break_route(server, "/api/preview?atom=W-1.a1", 500)
    with pytest.raises(capture.CaptureError, match=r"^GET /api/preview\?atom=W-1\.a1 answered 500$"):
        capture.collect_previews(server, {"workflows": [{"atoms": [{"id": "W-1.a1"}]}]})
    assert capture.collect_previews(server, {}) == {}
    assert capture.collect_previews(server, {"workflows": [{"atoms": [{"id": "W-2.a1"}, {"id": "W-nope"}]}]}) == {
        "W-2.a1": {"anchor": "a-1", "html": "<p>W-2.a1</p>"}, "W-nope": {"anchor": None, "html": None}}


@pytest.fixture(scope="module")
def standin_parts(standin):
    """The routes and previews of the stand-in as `collect_routes` and `collect_previews` hand them over, for the tests of `derive`."""
    j2, files = standin
    routes = {name: data for name, data in files.items() if name in capture.ROUTE_FILES or name.startswith(("agent-", "activity-", "ask-", "record-"))}
    previews = {atom: {"anchor": "a-1", "html": html} for atom, html in json.loads(files["previews.json"]).items()}
    return j2, routes, previews


@needs_node
def test_derive_makes_the_same_goldens_again_from_the_same_routes(standin, standin_parts, tmp_path):
    files = standin[1]
    j2, routes, previews = standin_parts
    derived = capture.derive(j2, NODE, routes, previews, tmp_path)
    assert {name: derived[name] for name in derived} == {name: files[name] for name in derived}
    assert capture.derive(j2, NODE, routes, previews, tmp_path) == derived  # and again in the same working folder
    assert set(derived) == {"previews.json", "preview-replies.json", "render-docs.json", "maps.json"} | {f"golden-{key}.json" for key in J2_GOLDENS}
    assert "golden-sframe.json" in derived and derived["golden-sframe.json"] == b'"/site/v0?t=1793786404000"'  # the harness ran on the frozen clock


@needs_node
@pytest.mark.parametrize("mode,message", [
    ("random", r"^J2's render harness gave two different outputs for one input: the goldens would not be stable$"),
    ("nokey", r"^J2's render harness printed no 'rail'$"),
    ("fail", r"^node j2_ui_render\.js failed: render failed on purpose\n$"),
])
def test_a_harness_that_is_not_stable_incomplete_or_failing_stops_the_capture(standin_parts, tmp_path, monkeypatch, mode, message):
    j2, routes, previews = standin_parts
    monkeypatch.setenv("STANDIN_RENDER", mode)
    with pytest.raises(capture.CaptureError, match=message):
        capture.derive(j2, NODE, routes, previews, tmp_path)


# ---- files in and out ---------------------------------------------------------------------------------------------------------------
def test_write_files_replaces_the_content_of_the_folder_and_makes_it(tmp_path):
    out = tmp_path / "deep" / "out"
    capture.write_files(out, {"a.json": b"1", "b.html": b"<p>"})
    assert {p.name: p.read_bytes() for p in out.iterdir()} == {"a.json": b"1", "b.html": b"<p>"}
    (out / "stale.json").write_bytes(b"old")
    (out / "sub").mkdir()
    capture.write_files(out, {"a.json": b"2"})
    assert {p.name for p in out.iterdir()} == {"a.json", "sub"} and (out / "a.json").read_bytes() == b"2"  # files are replaced, folders are left


def test_compare_lists_what_differs_missing_extra_and_changed(tmp_path):
    out = tmp_path / "out"
    assert capture.compare(out, {"a": b"1"}) == ["a (missing)"]  # no folder at all
    capture.write_files(out, {"same": b"1", "changed": b"1", "gone": b"1"})
    (out / "folder").mkdir()
    assert capture.compare(out, {"same": b"1", "changed": b"2", "new": b"1"}) == ["changed (changed)", "gone (not captured now)", "new (missing)"]
    assert capture.compare(out, {"same": b"1", "changed": b"1", "gone": b"1"}) == []


def test_the_parser_defaults_to_the_committed_folder_and_the_documented_limits():
    args = capture.build_parser().parse_args(["--j2", "/j2", "--j2-python", "/py"])
    assert args.out == REPO / "tests" / "ui" / "fixtures" / "j2" == capture.DEFAULT_OUT
    assert (args.max_state_bytes, args.timeout, args.brief, args.check, args.node) == (150_000, 180.0, capture.BRIEF, False, shutil.which("node"))
    assert len(capture.BRIEF.split()) >= 25  # J2's mock treats a brief of 25 words or more as complete
    with pytest.raises(SystemExit):
        capture.build_parser().parse_args([])  # --j2 and --j2-python are required


def test_main_writes_the_folder_checks_it_and_reports_drift_and_failures(standin, tmp_path, monkeypatch, capsys):
    j2, files = standin
    monkeypatch.setattr(capture, "capture", lambda *args, **kwargs: files)  # the capture itself is tested above
    out = tmp_path / "out"
    common = ["--j2", str(j2), "--j2-python", sys.executable, "--out", str(out)]
    assert capture.main(common) == 0
    assert capsys.readouterr().out == f"wrote {len(files)} files ({sum(len(d) for d in files.values()):,} bytes) to {out}\n"
    assert {p.name for p in out.iterdir()} == set(files)
    assert capture.main([*common, "--check"]) == 0
    assert capsys.readouterr().out == f"ok: {len(files)} files equal a fresh capture\n"
    (out / "state.json").write_bytes(b"{}")
    (out / "extra.json").write_bytes(b"1")
    (out / "runs.json").unlink()
    assert capture.main([*common, "--check"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("the J2 fixtures have drifted from a fresh capture:\n")
    assert "  extra.json (not captured now)\n" in err and "  runs.json (missing)\n" in err and "  state.json (changed)\n" in err
    assert (out / "state.json").read_bytes() == b"{}"  # --check writes nothing


def test_a_j2_that_moved_to_a_new_commit_but_gives_the_same_bytes_is_not_drift(standin, tmp_path, monkeypatch, capsys):
    j2, files = standin
    out = tmp_path / "out"
    capture.write_files(out, files)
    manifest = json.loads(files["MANIFEST.json"])
    moved = {**files, "MANIFEST.json": (json.dumps({**manifest, "j2_commit": "abcdef0123456789abcdef0123456789abcdef01"}, indent=2) + "\n").encode()}
    monkeypatch.setattr(capture, "capture", lambda *args, **kwargs: moved)
    common = ["--j2", str(j2), "--j2-python", sys.executable, "--out", str(out), "--check"]
    assert capture.main(common) == 0
    assert capsys.readouterr().out == (f"ok: {len(files) - 1} files equal a fresh capture; J2 moved on ({manifest['j2_commit'][:7]} captured, "
                                       "abcdef0 now) and gives the same bytes\n")
    unknown = {**files, "MANIFEST.json": (json.dumps({**manifest, "j2_commit": None}, indent=2) + "\n").encode()}  # an extraction and no --commit
    monkeypatch.setattr(capture, "capture", lambda *args, **kwargs: unknown)
    assert capture.main(common) == 0
    assert capsys.readouterr().out == (f"ok: {len(files) - 1} files equal a fresh capture (no --commit given: the committed manifest's commit "
                                       f"{manifest['j2_commit'][:7]} is not compared)\n")
    monkeypatch.setattr(capture, "capture", lambda *args, **kwargs: moved)
    changed = {**moved, "board.json": b"[]"}  # a file differs as well: that is drift whatever the commit
    changed["MANIFEST.json"] = capture.manifest(j2, capture.BRIEF, {k: v for k, v in changed.items() if k != "MANIFEST.json"})
    monkeypatch.setattr(capture, "capture", lambda *args, **kwargs: changed)
    assert capture.main(common) == 1
    assert "board.json (changed)" in capsys.readouterr().err


def test_only_a_manifest_that_differs_in_its_commit_alone_counts_as_the_same(standin):
    j2, files = standin
    manifest = json.loads(files["MANIFEST.json"])
    dump = lambda body: json.dumps(body).encode()  # noqa: E731
    other = {**manifest, "j2_commit": "abc1234"}
    assert capture.commit_only_moved(dump(manifest), dump(other)) == (manifest["j2_commit"], "abc1234")
    assert capture.commit_only_moved(dump({**manifest, "j2_commit": None}), dump(other)) == (None, "abc1234")
    assert capture.commit_only_moved(dump(manifest), dump(manifest)) is None  # nothing moved
    assert capture.commit_only_moved(dump(manifest), dump({**other, "brief": "another"})) is None  # something else differs too
    assert capture.commit_only_moved(dump(manifest), dump({**other, "files": {}})) is None
    assert capture.commit_only_moved(b"not json", dump(other)) is None and capture.commit_only_moved(dump(manifest), b"{") is None
    assert capture.commit_only_moved(dump([1]), dump(other)) is None and capture.commit_only_moved(dump(manifest), dump("x")) is None


def test_main_reports_a_failed_capture_on_stderr_and_writes_nothing(tmp_path, capsys):
    out = tmp_path / "out"
    assert capture.main(["--j2", str(tmp_path / "nowhere"), "--j2-python", sys.executable, "--out", str(out)]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and f"capture failed: --j2 {tmp_path / 'nowhere'} is not a folder" in captured.err and not out.exists()


@needs_node
def test_run_as_a_program_a_second_capture_equals_the_first_and_the_checkout_stays_as_it_was(quiet, tmp_path):
    j2, files = quiet
    before = capture.checkout_state(j2)
    out = tmp_path / "out"
    capture.write_files(out, files)
    base = [sys.executable, str(SCRIPT), "--j2", str(j2), "--j2-python", sys.executable, "--out", str(out), "--timeout", "30", "--check"]
    checked = subprocess.run(base, capture_output=True, text=True, timeout=120)  # another process, another port, another scratch folder
    assert (checked.returncode, checked.stdout.strip().splitlines()[-1], checked.stderr) == (0, f"ok: {STANDIN_FILES} files equal a fresh capture", "")
    assert capture.checkout_state(j2) == before


@pytest.mark.skipif(not os.environ.get("SUTRA_J2_CHECKOUT"),
                    reason="set SUTRA_J2_CHECKOUT to an extraction of prototypes/j2 at the pinned commit (and SUTRA_J2_COMMIT to that commit)")
def test_the_committed_j2_captures_equal_a_fresh_capture_of_the_real_j2(capsys):
    j2 = Path(os.environ["SUTRA_J2_CHECKOUT"])
    before = capture.folder_digest(j2)
    commit = ["--commit", os.environ["SUTRA_J2_COMMIT"]] if os.environ.get("SUTRA_J2_COMMIT") else []
    # J2's server runs on this Python, the project's own virtualenv: J2's mock mode needs only the standard library and pydantic
    assert capture.main(["--j2", str(j2), *commit, "--check"]) == 0, capsys.readouterr().err
    assert capture.folder_digest(j2) == before  # J2 is read-only for the app: nothing was written there


# ---- the run list and the changes: J2's own routes since sync 4 (D140), so captures like the rest ------------------------------
def test_the_run_list_and_the_changes_are_j2s_captures_and_a_team_is_asked_for(fake_server, fake):
    fake.stage("2")
    status, _, raw = j2_get(fake_server, "/api/runlist", dept="web")
    body = json.loads(raw)
    assert status == 200 and list(body) == ["live", "runs"] and body["runs"], body
    assert set(body["runs"][0]) == {"id", "title", "status", "output", "label", "form", "when", "brief"} and body["runs"][0]["when"] == "2026-11-04T10:00:04"
    assert json.loads(j2_get(fake_server, "/api/changes", dept="web")[2]) == {"changes": []}
    for path in ("/api/runlist", "/api/changes"):
        assert j2_get(fake_server, path)[0] == 400 and j2_get(fake_server, path, dept="nosuch")[0] == 404
