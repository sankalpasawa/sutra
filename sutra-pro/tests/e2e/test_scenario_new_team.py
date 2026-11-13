"""Scenario 1 (GAP-E2E, G05): a new team from ONE chat message to a finished workflow and an audit verdict.

The whole app runs for real (uvicorn thread, SQLite, ProcessLauncher, the engine as its own process in J2's mock mode with the
default function-node hooks); only the chat agent's model is scripted. The journey runs once (module fixture, about 3 s); each test
looks at one thing it left behind and names the draw.io step it proves (docs/design/gaps.md section 4):

  1 the chat agent reads the chart        2 a new team references the models library     3 claude cli + python models (test_scenario_fake_cli)
  4 the graph is visible                  5 each node is linked to its chat session
  6 the graph updates dynamically          7 each department and division is linked to its chat
"""
import json
import os

import pytest
from harness import ANSWER, FIRST_MESSAGE, FUNCTIONS, ORG, LiveApp, run_new_team

from sutra_app.library.registry import REGISTRY
from sutra_app.library.types import overhead_atom_id
from sutra_app.orchestrator.agent import prompts
from sutra_app.orchestrator.agent.replies import AssignmentDraft, AssignmentPlan, ChatDecision
from sutra_app.orchestrator.testing.scripted import ScriptedConnector

TERMINAL_DISPLAYS = ("closed", "verify_failed", "refused", "abandoned")


@pytest.fixture(scope="module")
def journey(tmp_path_factory):
    live = LiveApp(tmp_path_factory.mktemp("new-team"), connector=ScriptedConnector()).start()
    try:
        yield run_new_team(live)
    finally:
        try:
            live.stop()
        finally:
            live.kill_engines()


@pytest.fixture
def live(journey) -> LiveApp:
    return journey.live


def schema_text(*args, **kw) -> str:
    return json.dumps(REGISTRY.transport_schema(*args, **kw), sort_keys=True, separators=(",", ":"))


# ============================================ step 1 and 2: the chat agent's prompts =========================================

def test_step1_the_chat_agent_reads_the_chart_digest_and_stops_at_add(journey, live):
    calls = live.connector.calls
    assert [(c.function, c.step) for c in calls] == [("chat_agent", "decide"), ("chat_agent", "change"), ("chat_agent", "assign")]
    first = calls[0].prompt
    assert journey.digest0 in first and "Org chart revision 1." in first and f"OWNER REQUEST:\n{FIRST_MESSAGE}" in first
    assert "Web" not in journey.digest0                                                   # the chart held no team yet
    after = calls[2].prompt                                                               # the assignment is asked from the NEW chart
    assert "revision 2" in after and "Web" in after and "(revision 1)" not in after


def test_step2_every_stage_prompt_carries_the_models_library_schema_and_field_digest(journey, live):
    first, second, third = live.connector.calls
    assert schema_text("chat_turn", kind="decide") in first.prompt and first.schema == json.loads(schema_text("chat_turn", kind="decide"))
    assert prompts.field_digest(AssignmentDraft, ChatDecision) in first.prompt
    assert schema_text("chart_change_request") in second.prompt and second.schema == json.loads(schema_text("chart_change_request"))
    assert "AddOp" in second.prompt and "NewNode" in second.prompt                         # the models the reply nests are named
    assert schema_text("chat_turn", kind="assignments") in third.prompt
    assert prompts.field_digest(AssignmentDraft, AssignmentPlan) in third.prompt
    assert "Every department has five function nodes: identity, adaptation, priority, coordination, audit." in first.prompt


def test_step2_chart_change_2_is_applied_with_chained_shas_and_the_department_exists(journey, live):
    first, second = live.rows("SELECT * FROM chart_changes ORDER BY seq")
    assert (second["seq"], second["kind"], second["status"], second["actor"]) == (2, "add", "applied", "chat_agent")
    assert second["before_sha"] == first["after_sha"] and second["after_sha"] != second["before_sha"]
    assert [r["id"] for r in live.rows("SELECT id FROM departments")] == ["web"]
    assert live.one("SELECT name FROM org_nodes WHERE id = 'web'") == "Web"
    assert (live.settings.data_dir / "departments" / "web" / "runs" / journey.run_id).is_dir()
    [card] = live.cards("chart_change")
    assert card["decision"] == "add" and live.cards("task")[-1]["dept_id"] == "web"


# ============================================ step 4, 5, 7: the graph and its chats ==========================================

def test_step4_the_graph_shows_the_department_the_five_function_nodes_and_the_steps(journey, live):
    graph = live.get("/api/graph", level="full")
    by_id = {n["id"]: n for n in graph["nodes"]}
    assert {"root", "web", *(f"web.{fn}" for fn in FUNCTIONS)} <= set(by_id)
    assert [by_id[f"web.{fn}"]["kind"] for fn in FUNCTIONS] == ["function"] * 5
    steps = [n for n in graph["nodes"] if n["kind"] == "step"]
    assert len(steps) >= 5 and {n["task_id"] for n in steps} == {journey.task}
    assert all(n["status"] in ("filed", "done_unchecked") for n in steps)
    assert {e["kind"] for e in graph["edges"]} >= {"contains"}


def test_step5_every_graph_node_links_to_a_chat_session_that_resolves(journey, live):
    graph = live.get("/api/graph", level="full")
    assert len(graph["nodes"]) >= 15
    for node in graph["nodes"]:
        session = live.get(f"/api/chats/{node['chat_session_id']}")                     # 200 or the helper fails
        assert session["node_id"] == node["id"] and session["status"] == "active"
    function_chats = [live.get(f"/api/chats/{live.session_of('web.' + fn)}") for fn in FUNCTIONS]
    assert [c["kind"] for c in function_chats] == ["function"] * 5 and not any(c["writable"] for c in function_chats)


def test_step7_the_department_and_the_org_root_are_linked_to_their_chats(journey, live):
    web, root = live.get("/api/chats/" + live.session_of("web")), live.get("/api/chats/" + live.session_of("root"))
    assert (web["kind"], web["writable"], web["node_id"]) == ("department", True, "web")
    assert (root["id"], root["kind"], root["writable"]) == (ORG, "org", True)
    texts = [(m["who"], m["kind"]) for m in live.messages(web["id"])]
    assert texts[:2] == [("user", "text"), ("identity", "question")] and ("user", "text") in texts[2:]
    assert [m["text"] for m in live.messages(web["id"]) if m["who"] == "user"] == [FIRST_MESSAGE, ANSWER]


# ============================================ the engine, the function nodes and the ledgers =================================

def test_the_real_engine_process_ran_the_mock_run_to_done_with_the_function_layer_on(journey, live):
    events = live.events_of(journey.task)
    started, ended = events[0], events[-1]
    assert (started["t"], started["mock"], started["seed"]) == ("run.started", True, "none")
    assert (ended["t"], ended["status"]) == ("run.ended", "done")
    row = live.task_row(journey.task)
    assert row["pid"] == started["pid"] and row["pid"] != os.getpid()      # its own process, not a thread of the tests
    stderr = (live.run_dir(journey.task) / "run.stderr.log").read_text(errors="replace")
    assert "Traceback" not in stderr and "function nodes are off" not in stderr
    assert not any("function nodes are off" in (m["text"] or "") for m in live.messages(live.session_of("web")))
    kinds = {e["t"] for e in events}
    assert {"say", "node", "step", "atom", "usage", "heartbeat"} <= kinds
    assert row["events_offset"] == (live.run_dir(journey.task) / "events.jsonl").stat().st_size       # every byte was projected


def test_function_atoms_exist_for_every_function_with_cards_and_one_ledger_row_per_terminal_atom(journey, live):
    for fn in FUNCTIONS:
        node = f"web.{fn}"
        assert live.one("SELECT count(*) FROM atoms WHERE node_id = ? AND schema = 'work-atom/0.3'", node) >= 1, fn
        cards = [m["card"] for m in live.messages(live.session_of(node)) if m["kind"] == "card"]
        assert cards and {c["type"] for c in cards} == {"atom"}, fn                       # the atom cards sit in the function's own chat
    assert live.one("SELECT count(*) FROM atoms WHERE display = 'open'") == 0
    terminal = {r["id"] for r in live.rows(f"SELECT id FROM atoms WHERE display IN ({','.join('?' * 4)})", *TERMINAL_DISPLAYS)}
    ledger = [r["atom_id"] for r in live.rows("SELECT atom_id FROM atom_ledger ORDER BY seq")]
    assert len(ledger) == len(set(ledger)) == len(terminal) and set(ledger) == terminal
    assert len(live.get("/api/atoms/log")) == len(ledger)


def test_every_function_atom_of_the_real_run_says_what_its_turn_produced_and_an_ai_turn_carries_the_reply_it_got(journey, live):
    """D157, end to end with nothing replayed: the engine process and its layer wrote the words and the reply, the real projector and store kept them,
    and the atom route serves them in the shape the page reads."""
    atoms = [live.get(f"/api/atoms/{row['id']}") for row in live.rows("SELECT id FROM atoms WHERE schema = 'work-atom/0.3' ORDER BY rowid")]
    assert len(atoms) >= 5
    said: dict[str, list[str]] = {fn: [] for fn in FUNCTIONS}
    for atom in atoms:
        body = atom["body"]
        assert body["produced"], atom["id"]                                                  # the layer recorded the turn, whatever it did
        assert all(set(item) == {"verb", "name", "form", "ref"} and item["name"] for item in body["produced"]), atom["id"]
        said[atom["node_id"].rpartition(".")[2]] += [item["name"] for item in body["produced"]]
        if body["work"]["dispatch_kind"] == "llm":                                           # an AI turn: the reply the model gave, printed
            reply = body["reply"]
            assert set(reply) == {"text", "clipped"} and reply["text"].startswith("{") and len(reply["text"]) <= 4000, atom["id"]
            assert reply["clipped"] or isinstance(json.loads(reply["text"]), dict), atom["id"]
        else:                                                                                # code and the owner give no reply
            assert body["reply"] is None, atom["id"]
    assert any(n.startswith("the charter: ") for n in said["identity"]) and any(n.startswith("asked you ") for n in said["identity"])
    assert any(n.startswith("you answered: ") for n in said["identity"])                       # the manual atom of Identity's question
    assert any(n.startswith("a proposal of ") for n in said["adaptation"]) and any(n.startswith(("GRANT", "COUNTER")) for n in said["priority"])
    assert any(n.startswith("scheduled ") for n in said["coordination"]) and any("findings and rubric rows: " in n for n in said["audit"])
    assert any(n.startswith("decided the goal is reached") for n in said["identity"]) and any(n.startswith("code posted ") for n in said["coordination"])
    drawer = live.get("/api/graph/nodes/web.audit")["atoms"]
    assert drawer and all(atom["body"]["produced"] for atom in drawer)                      # the drawer's route serves the same words


def test_identity_asked_needs_you_listed_it_and_the_answer_in_the_department_chat_continued_the_run(journey, live):
    [need] = journey.needs
    assert (need["kind"], need["dept_id"], need["text"]) == ("question", "web", journey.question)
    assert need["session_id"] == live.session_of("web") and "business called" in need["text"]
    [asked] = [c for c in live.cards("team_chat") if c["about"] == "question"]      # the org chat points at the team's chat (GAP3 dept-chats), it holds no question
    assert (asked["node_id"], asked["session_id"]) == ("web", live.session_of("web")) and journey.question not in json.dumps(live.messages(ORG))
    assert live.cards("needs_you") == []
    assert journey.answer_response["delivered"] == "answer" and journey.answer_response["task_id"] == journey.task
    inbox = [json.loads(line) for line in (live.run_dir(journey.task) / "inbox.jsonl").read_text().splitlines()]
    assert [(line["kind"], line["n"]) for line in inbox] == [("user", 1)] and inbox[0]["text"].startswith("It's called Little Fig")
    assert live.get("/api/needs-you") == []
    counts = [f["data"]["count"] for f in live.sse.of("needs_you.changed")]
    assert counts[0] == 1 and counts[-1] == 0
    team = [m for m in live.messages(live.session_of("web")) if m["who"] == "identity"]
    assert [m["kind"] for m in team][:2] == ["question", "text"] and "Thanks, I have everything I need" in team[1]["text"]


def test_usage_rows_carry_an_atom_id_and_add_up_to_the_engines_usage_events(journey, live):
    events = [e for e in live.events_of(journey.task) if e["t"] == "usage"]
    rows = live.rows("SELECT * FROM usage_ledger WHERE task_id = ? ORDER BY id", journey.task)
    assert len(events) == len(rows) >= 20
    assert all(r["atom_id"] for r in rows) and all(r["provider"] == "stub" for r in rows)
    known = {r["id"] for r in live.rows("SELECT id FROM atoms")} | {overhead_atom_id(journey.run_id)}
    assert {r["atom_id"] for r in rows} <= known
    assert sum(r["tokens_in"] or 0 for r in rows) == sum(e["tokens_in"] or 0 for e in events) > 0
    assert sum(r["tokens_out"] or 0 for r in rows) == sum(e["tokens_out"] or 0 for e in events)
    assert {r["call_ref"]: r["tokens_in"] for r in rows} == {e["call_ref"]: e["tokens_in"] for e in events}       # call for call
    assert len(live.sse.of("usage.recorded")) == len(rows)
    chat_calls = live.rows("SELECT count(*) FROM usage_ledger WHERE task_id IS NULL")[0][0]
    assert chat_calls == 0                                                                 # the scripted chat agent has no sink: no unowned row


# ============================================ step 6: the stream during the run ==============================================

def test_step6_the_stream_carries_graph_and_atom_updates_while_the_run_works(journey, live):
    frames = live.sse.snapshot()
    ids = [f["id"] for f in frames if "id" in f]
    assert ids == sorted(ids) and len(set(ids)) == len(ids)                              # one ordered stream, no repeats
    types = [f["type"] for f in frames]
    asked = types.index("needs_you.changed")
    after = frames[journey.sse_before_answer:]
    run_types = [f["type"] for f in after]
    assert {"atom.updated", "graph.updated", "usage.recorded"} <= set(run_types)
    assert run_types.index("graph.updated") < len(run_types) - 1 - run_types[::-1].index("atom.updated")
    last_task = [f for f in frames if f["type"] == "task.updated"][-1]["data"]["task"]
    assert (last_task["id"], last_task["status"]) == (journey.task, "done")
    assert max(i for i, t in enumerate(types) if t in ("atom.updated", "graph.updated")) < max(i for i, t in enumerate(types) if t == "task.updated") + 4
    assert asked < journey.sse_before_answer < len(types)
    chart_at = types.index("chart.changed")
    assert chart_at < types.index("graph.updated") < asked                                # the team appears in the graph before it asks
    states = [f["data"] for f in frames if f["type"] == "atom.updated"]
    assert {s["outcome"] for s in states} >= {"opened", "closed"} and {s["node_id"] for s in states} >= {f"web.{fn}" for fn in FUNCTIONS}


# ============================================ the verdict ====================================================================

def test_the_audit_record_passes_the_done_card_is_in_the_org_chat_and_the_task_is_done(journey, live):
    run = live.run_dir(journey.task)
    summary = json.loads((run / "summary.json").read_text())
    assert (summary["status"], summary["workable"], summary["mock"]) == ("done", [], True)       # no open item: workable
    assert summary["conditions"]["met"] == summary["conditions"]["total"] and summary["verification"]["failed"] == 0
    audits = json.loads((run / "audits.json").read_text())
    assert audits and all(r["pass"] and r["verdict"] == "PASS" for r in audits[-1]["results"])
    assert live.one("SELECT count(*) FROM atoms WHERE node_id = 'web.audit' AND display = 'closed'") >= 1
    assert any(m["kind"] == "text" and "All criteria pass" in m["text"] for m in live.messages(live.session_of("web.audit")))
    [done] = live.cards("done")
    assert (done["task_id"], done["status"]) == (journey.task, "done") and done["outcome"].startswith("Done:")
    task = live.get(f"/api/tasks/{journey.task}")
    assert task["status"] == "done" and task["outcome"] == summary["outcome"]
    assert live.one("SELECT state FROM graph_nodes WHERE id = 'web'") == "idle"
    assert live.one("SELECT count(*) FROM tasks WHERE status NOT IN ('done')") == 0
