"""The scripted conversation (ORCH-8, orchestrator 7): the WHOLE app, built by `create_app`, driven over HTTP with a scripted model and a
fake engine. Each step asserts the database, the files and the order of the events the stream recorded. Nothing here calls a model, a
CLI or a real engine process.

The fake engine plays a script (run.started, then wait for the owner's answer, then close the atom, report usage and end); the test
writes the middle of the run (the question, Identity waiting, the opened atom) into `events.jsonl` itself, exactly where the real
engine would, so every moment of the run is deterministic."""
import json
import shutil
import sqlite3
import time

import pytest
from factories_atom import close_with, open_transition
from fastapi.testclient import TestClient
from orchestrator.test_chat_agent import add_dept, add_div, assignments, change_reply, decide, draft
from orchestrator.test_projector_fnodes import atom_line

from sutra_app.config import Settings
from sutra_app.library.types import overhead_atom_id
from sutra_app.main import create_app
from sutra_app.orchestrator.agent import planner
from sutra_app.orchestrator.agent.ports import ConnectorFailure
from sutra_app.orchestrator.testing.fake_engine import FakeLauncher, ev
from sutra_app.orchestrator.testing.scripted import ScriptedConnector

TOKEN = "test-token-0123456789abcdef"
HEADERS = {"X-Sutra-Token": TOKEN}
ORG = "cs_org"
ASK = "What is the business called?\nOption 1: Sweet Bean\nOption 2: Other"
ATOM = "a-3f9a1c2b7d-01"
MERGE = {"op": "merge", "into": "recipes", "sources": ["menu"]}
MOVE = {"op": "move", "node": "menu", "to_parent": "$content"}


def first_script(_spec) -> list[dict]:
    """The first task: starts, waits for the owner's one answer, closes Identity's atom, reports a call and ends done."""
    opened = open_transition(node_id="web.identity", id=ATOM, department_id="web")
    closed = close_with(opened.atom, 0)
    return [
        {"emit": ev("run.started", schema="events/1", mock=True, seed="none")},
        {"wait_inbox": 1},
        {"emit": atom_line(closed)},
        {"emit": ev("usage", fn="identity", step=None, atom=ATOM, provider="claude", model="sonnet", purpose="agent_turn", usd=0.02,
                    tokens_in=300, tokens_out=60, seconds=1.5, ok=True, how="native", call_ref="r:1")},
        {"emit": ev("run.ended", status="done", outcome="Landing page ready")},
    ]


def later_script(_spec) -> list[dict]:
    return [{"emit": ev("run.started", schema="events/1", mock=True, seed="none")}, {"emit": ev("run.ended", status="done", outcome="Done")}]


class Scenario:
    """One running app and the little it takes to talk to it."""

    def __init__(self, client: TestClient, app, connector: ScriptedConnector) -> None:
        self.client, self.app, self.connector = client, app, connector
        self.services = app.state.services
        self.db = self.services.db
        self.opened = open_transition(node_id="web.identity", id=ATOM, department_id="web")

    # ---- driving ---------------------------------------------------------------------------------------------------------------

    def until(self, what: str, check, timeout: float = 10.0):
        end = time.time() + timeout
        while time.time() < end:
            found = check()
            if found:
                return found
            time.sleep(0.01)
        pytest.fail(f"timed out waiting for {what}")

    def post(self, session: str, text: str, **extra):
        return self.client.post(f"/api/chats/{session}/messages", json={"text": text, **extra}, headers=HEADERS)

    def say(self, text: str, *script, **extra) -> int:
        """The owner writes in the org chat; the model answers with `script`; returns once the whole turn is over."""
        self.connector.push(*script)
        response = self.post(ORG, text, **extra)
        assert response.status_code == 202, response.text
        self.until("the turn to end", lambda: not self.services.runner.busy)
        return response.json()["message_id"]

    def head(self) -> int:
        return self.services.bus.head

    def events_since(self, after: int) -> list[tuple[str, dict]]:
        """What the stream replays after `after`: (type, data) in order, read over the wire."""
        text = self.client.get("/api/events", params={"after": after, "once": 1}).text
        out = []
        for block in text.split("\n\n"):
            fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
            if "event" in fields and not fields["event"].startswith("server."):
                out.append((fields["event"], json.loads(fields["data"])))
        return out

    # ---- reading ---------------------------------------------------------------------------------------------------------------

    def sql(self, text: str, *args):
        return self.db.conn().execute(text, args)

    def one(self, text: str, *args):
        row = self.sql(text, *args).fetchone()
        return row[0] if row is not None else None

    def messages(self, session: str = ORG) -> list[dict]:
        return self.client.get(f"/api/chats/{session}/messages").json()["messages"]

    def sutra(self) -> list[tuple[str, str]]:
        """What Sutra said in the org chat: ('text', line) or ('card', type)."""
        return [("card", m["card"]["type"]) if m["kind"] == "card" else (m["kind"], m["text"]) for m in self.messages() if m["who"] == "sutra"]

    def cards(self, kind: str) -> list[dict]:
        return [m["card"] for m in self.messages() if m["kind"] == "card" and m["card"]["type"] == kind]

    def session_of(self, node_id: str) -> str:
        return self.one("SELECT chat_session_id FROM graph_nodes WHERE id = ?", node_id)

    def task_status(self, task_id: str) -> str:
        return self.one("SELECT status FROM tasks WHERE id = ?", task_id)

    def run_dir(self, task_id: str):
        return self.services.tasks.store.run_dir_of(self.services.tasks.store.row(task_id))

    def write_events(self, task_id: str, *events: dict) -> None:
        """Append lines to a run's events.jsonl, where the real engine would."""
        with open(self.run_dir(task_id) / "events.jsonl", "ab") as handle:
            for event in events:
                handle.write((json.dumps({"at": "2026-11-04T10:00:00Z", **event}) + "\n").encode())


def make_scenario(tmp_path, *, launcher=None, clock=None):
    settings = Settings.load({}, data_dir=tmp_path / "data", token=TOKEN, env_file=tmp_path / "none.env", engine="fake", watch_ms=20)
    made = []

    def script_for(spec):
        made.append(spec.run_id)
        return (first_script if len(made) == 1 else later_script)(spec)

    connector = ScriptedConnector()
    app = create_app(settings, connector=connector, launcher=launcher or FakeLauncher(script_for), clock=clock)
    return app, connector


@pytest.fixture
def convo(tmp_path):
    app, connector = make_scenario(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1:8780") as client:
        yield Scenario(client, app, connector)


# ============================================ the steps, each building on the one before =====================================

def new_team(c: Scenario) -> str:
    """Step 2: 'I need a landing page for my coffee shop.' makes the Web team and gives it a task. Returns the task id."""
    mid = c.say("I need a landing page for my coffee shop.",
                decide(change="add", reuse=(), why="no team builds pages"),
                change_reply(add_dept("$web", "Web", "Websites and landing pages")),
                assignments(draft("a1", "web", title="Cafe page", brief="Build the cafe landing page.")))
    return c.one("SELECT id FROM tasks WHERE request_id = ?", f"req-{mid}")


def asked(c: Scenario) -> str:
    """Step 3: the engine asks the owner; returns the task id."""
    task = new_team(c)
    c.until("the task to run", lambda: c.task_status(task) == "running")
    c.write_events(
        task,
        ev("say", id=1, who="adaptation", text="Checking the shop's tone first.", next="identity"),
        ev("node", fn="identity", status="waiting_on_you", detail="asked the owner"),
        atom_line(c.opened),
        ev("say", id=2, who="identity", text=ASK, to_user=True, act="ASK_REQUESTER", pause="info", next="user"))
    c.until("the question", lambda: c.task_status(task) == "waiting_user")
    return task


def answered(c: Scenario) -> str:
    """Step 4: the owner answers in the department chat; the script finishes the run."""
    task = asked(c)
    response = c.post(c.session_of("web"), "Sweet Bean")
    assert response.status_code == 200, response.text
    c.until("the run to end", lambda: c.task_status(task) == "done")
    return task


def reused(c: Scenario) -> str:
    """Step 5: 'Also write a menu page.' reuses Web."""
    answered(c)
    mid = c.say("Also write a menu page.", decide(change="reuse", reuse=("web",), assignments=[draft("a1", "web", title="Menu page")]))
    return c.one("SELECT id FROM tasks WHERE request_id = ?", f"req-{mid}")


def divided(c: Scenario) -> None:
    """Step 6: 'Make Menu its own division of Web.'"""
    reused(c)
    c.say("Make Menu its own division of Web.", decide("chart_request", "add", reuse=(), assignments=[]),
          change_reply(add_div("$menu", "Menu", "web", "Menu pages")))


def content_team(c: Scenario) -> None:
    """Step 7: a new Content team, and Menu moves there (one change, two ops)."""
    c.say("Menu belongs in a new Content team; make it and move Menu there.", decide("chart_request", "rearrange", reuse=(), assignments=[]),
          change_reply(add_dept("$content", "Content", "Words and menus"), MOVE))


def moved(c: Scenario) -> None:
    """Steps 1 to 7, then a Recipes division in Content (the merge target of step 8)."""
    divided(c)
    content_team(c)
    c.say("Add a Recipes division to Content.", decide("chart_request", "add", reuse=(), assignments=[]),
          change_reply(add_div("$recipes", "Recipes", "content", "Recipes")))


# ============================================ 1. boot ========================================================================

def test_boot_holds_the_root_and_the_greeting_only(convo):
    assert convo.one("SELECT count(*) FROM org_nodes") == 1 and convo.one("SELECT kind FROM org_nodes") == "root"
    assert convo.one("SELECT count(*) FROM chart_changes") == 1 and convo.one("SELECT count(*) FROM tasks") == 0
    assert convo.sutra() == [("text", planner.LINES["greeting"])]
    assert [s["id"] for s in convo.client.get("/api/chats").json()] == [ORG]


# ============================================ 2. a new team ==================================================================

def test_a_new_team_is_made_from_one_sentence(convo):
    before = convo.head()
    task = new_team(convo)
    first, second = [r for r in convo.sql("SELECT * FROM chart_changes ORDER BY seq")]
    assert (second["seq"], second["kind"], second["status"], second["actor"], second["task_title"]) == (2, "add", "applied", "chat_agent", "Cafe page")
    assert second["before_sha"] == first["after_sha"] and second["after_sha"] != second["before_sha"]              # the chain of I5
    assert [r["id"] for r in convo.sql("SELECT id FROM departments")] == ["web"]
    assert (convo.services.settings.data_dir / "departments" / "web" / "runs").is_dir()
    functions = [r["id"] for r in convo.sql("SELECT id FROM graph_nodes WHERE id LIKE 'web.%' ORDER BY id")]
    assert functions == sorted(f"web.{fn}" for fn in ("identity", "adaptation", "priority", "coordination", "audit"))
    for node_id in ("root", "web", *functions, *[r["id"] for r in convo.sql("SELECT id FROM graph_nodes WHERE kind = 'step'")]):
        sid = convo.session_of(node_id)
        assert sid and convo.one("SELECT node_id FROM chat_sessions WHERE id = ? AND status = 'active'", sid) == node_id      # I1: one session each
    row = convo.sql("SELECT * FROM tasks WHERE id = ?", task).fetchone()
    spec = json.loads((convo.run_dir(task) / "task.json").read_text())
    assert spec["run_id"] == row["run_id"] and spec["dept_id"] == "web" and spec["user_text"] == "I need a landing page for my coffee shop."
    convo.until("run.started", lambda: convo.task_status(task) == "running")
    assert convo.sutra()[-4:] == [("text", "I set up a Web team and gave it your request."), ("card", "chart_change"), ("card", "team_chat"), ("card", "task")]
    assert convo.cards("chart_change")[-1]["decision"] == "add" and convo.cards("task")[-1]["dept_id"] == "web"
    started = convo.cards("team_chat")[-1]
    assert (started["node_id"], started["name"], started["about"], started["session_id"]) == ("web", "Web", "started", convo.session_of("web"))


def test_the_events_of_a_new_team_come_in_the_designed_order(convo):
    before = convo.head()
    new_team(convo)
    types = [t for t, _ in convo.events_since(before)]
    wanted = ["chat.message", "chat.turn", "chat.turn", "chat.turn", "chat.turn", "chart.changed", "graph.updated", "task.updated", "chat.message", "chat.turn"]
    at = 0
    for kind in wanted:
        at = types.index(kind, at) + 1
    phases = [d["phase"] for t, d in convo.events_since(before) if t == "chat.turn"]
    assert phases == ["reading_chart", "consulting_library", "planning", "applying", "handing_off", "done"]


def test_the_models_calls_carry_the_request_overhead_key(convo):
    mid = convo.say("I need a landing page for my coffee shop.", decide("smalltalk", "none", reuse=()))
    assert [c.context["atom_id"] for c in convo.connector.calls] == [overhead_atom_id(f"req-{mid}")]


# ============================================ 3. the team asks ===============================================================

def test_a_write_while_the_team_works_is_busy(convo):
    task = new_team(convo)
    convo.until("the task to run", lambda: convo.task_status(task) == "running")
    response = convo.post(convo.session_of("web"), "hello?")
    assert response.status_code == 409 and response.json()["error"]["code"] == "busy"


def test_the_question_reaches_needs_you_the_department_chat_and_the_org_chat(convo):
    task = asked(convo)
    [needs] = convo.client.get("/api/needs-you").json()
    assert (needs["kind"], needs["dept_id"], needs["text"]) == ("question", "web", ASK) and needs["options"]
    question = [m for m in convo.messages(convo.session_of("web")) if m["kind"] == "question"]
    assert [m["text"] for m in question] == [ASK]
    [card] = [c for c in convo.cards("team_chat") if c["about"] == "question"]               # the org chat only points at the team's own chat
    assert (card["node_id"], card["session_id"], card["question_message_id"]) == ("web", convo.session_of("web"), question[0]["id"])
    assert ASK not in json.dumps(convo.messages("cs_org")) and not convo.cards("needs_you")
    assert convo.one("SELECT state FROM graph_nodes WHERE id = 'web.identity'") == "waiting_on_you"
    adaptation = convo.messages(convo.session_of("web.adaptation"))
    assert [m["text"] for m in adaptation] == ["Checking the shop's tone first."]
    assert convo.one("SELECT display FROM atoms WHERE id = ?", ATOM) == "open"
    assert convo.task_status(task) == "waiting_user"


# ============================================ 4. the owner answers ===========================================================

def test_the_answer_goes_to_the_team_and_the_run_ends_with_its_costs(convo):
    task = answered(convo)
    lines = [json.loads(line) for line in (convo.run_dir(task) / "inbox.jsonl").read_text().splitlines()]
    assert [(line["kind"], line["text"]) for line in lines] == [("user", "Sweet Bean")]
    question = convo.one("SELECT id FROM chat_messages WHERE kind = 'question'")
    assert convo.one("SELECT answered_by FROM chat_messages WHERE id = ?", question) is not None
    step = convo.sql("SELECT state FROM graph_nodes WHERE kind = 'step' AND task_id = ?", task).fetchone()
    assert step["state"] in ("done_unchecked", "filed")
    [done] = convo.cards("done")
    assert (done["task_id"], done["status"], done["outcome"]) == (task, "done", "Landing page ready")
    out = convo.client.get(f"/api/tasks/{task}").json()
    assert out["status"] == "done" and out["usage"] == {"calls": 1, "usd": 0.02, "tokens_in": 300, "tokens_out": 60}
    assert convo.one("SELECT display FROM atoms WHERE id = ?", ATOM) == "closed"
    assert convo.one("SELECT count(*) FROM atom_ledger") == 1


def test_a_second_request_for_a_busy_team_waits_and_starts_when_the_first_run_ends(convo):
    first = asked(convo)
    mid = convo.say("Also write a menu page.", decide(change="reuse", reuse=("web",), assignments=[draft("a1", "web", title="Menu page")]))
    second = convo.one("SELECT id FROM tasks WHERE request_id = ?", f"req-{mid}")
    assert convo.task_status(second) == "queued" and convo.cards("task")[-1]["status"] == "queued"          # one live task per team (D22)
    assert convo.post(convo.session_of("web"), "Sweet Bean").status_code == 200                           # the answer goes to the first run
    convo.until("the first run to end", lambda: convo.task_status(first) == "done")
    convo.until("the queued one to run and end", lambda: convo.task_status(second) == "done")                # started by the watcher, no request needed


# ============================================ 5-8. the chart changes =========================================================

def test_a_second_request_reuses_the_team_and_changes_no_node(convo):
    answered(convo)
    nodes = convo.one("SELECT count(*) FROM org_nodes")
    mid = convo.say("Also write a menu page.", decide(change="reuse", reuse=("web",), assignments=[draft("a1", "web", title="Menu page")]))
    assert len(convo.connector.calls) == 4                                      # three for the first request, one here
    third = convo.sql("SELECT * FROM chart_changes ORDER BY seq DESC LIMIT 1").fetchone()
    assert (third["seq"], third["kind"], third["status"]) == (3, "reuse", "applied") and convo.one("SELECT count(*) FROM org_nodes") == nodes
    tasks = convo.sql("SELECT dept_id, run_id FROM tasks WHERE request_id = ?", f"req-{mid}").fetchall()
    assert [t["dept_id"] for t in tasks] == ["web"] and tasks[0]["run_id"] != convo.one("SELECT run_id FROM tasks ORDER BY created_at LIMIT 1")
    assert convo.one("SELECT count(*) FROM tasks") == 2


def test_a_division_is_added_under_a_team(convo):
    divided(convo)
    assert convo.one("SELECT kind FROM org_nodes WHERE id = 'menu'") == "division"
    assert convo.one("SELECT parent_id FROM graph_nodes WHERE id = 'menu'") == "web"
    assert convo.session_of("menu")


def test_moving_a_division_keeps_its_id_session_and_history(convo):
    divided(convo)
    menu_session = convo.session_of("menu")
    response = convo.post(menu_session, "Make the menu pages friendly for phones")                  # a follow-up task scoped to Menu
    assert response.status_code == 200 and response.json()["delivered"] == "follow_up", response.text
    scoped = response.json()["task_id"]
    convo.until("the scoped task to end", lambda: convo.task_status(scoped) == "done")
    lines = [m["text"] for m in convo.messages(menu_session)]
    assert "Make the menu pages friendly for phones" in lines
    before_edges = [tuple(r) for r in convo.sql("SELECT parent_id, child_id FROM org_edges WHERE child_id = 'menu'")]
    content_team(convo)
    assert convo.session_of("menu") == menu_session and convo.one("SELECT status FROM chat_sessions WHERE id = ?", menu_session) == "active"
    assert [m["text"] for m in convo.messages(menu_session)] == lines                                  # the transcript came along
    after_edges = [tuple(r) for r in convo.sql("SELECT parent_id, child_id FROM org_edges WHERE child_id = 'menu'")]
    assert before_edges != after_edges and after_edges == [("content", "menu")]
    view = convo.client.get("/api/graph").json()
    [node] = [n for n in view["nodes"] if n["id"] == "menu"]
    assert convo.one("SELECT parent_id FROM graph_nodes WHERE id = 'menu'") == "content" and node["chat_session_id"] == menu_session
    assert [n["id"] for n in view["nodes"] if n["kind"] == "department"] == ["web", "content"]


def test_a_merge_waits_for_a_yes_and_a_second_click_is_refused(convo):
    moved(convo)
    nodes = convo.one("SELECT count(*) FROM org_nodes")
    head = convo.one("SELECT max(revision) FROM org_charts")
    convo.say("Merge Menu into Recipes.", decide("chart_request", "rearrange", reuse=(), assignments=[]), change_reply(MERGE))
    [card] = convo.cards("approval")
    assert convo.one("SELECT max(revision) FROM org_charts") == head and convo.one("SELECT count(*) FROM org_nodes") == nodes     # nothing changed yet
    assert convo.one("SELECT status FROM chart_changes ORDER BY seq DESC LIMIT 1") == "pending_approval"
    card_id = max(m["id"] for m in convo.messages() if m["kind"] == "card")
    convo.say("Yes", choice={"message_id": card_id, "option": "yes"})
    assert convo.one("SELECT status FROM chart_changes WHERE id = ?", card["change_id"]) == "applied"
    row = convo.sql("SELECT state, merged_into FROM org_nodes WHERE id = 'menu'").fetchone()
    assert (row["state"], row["merged_into"]) == ("archived", "recipes")
    assert convo.one("SELECT count(*) FROM graph_nodes WHERE id = 'menu'") == 0
    session = convo.one("SELECT status FROM chat_sessions WHERE node_id = 'menu'")
    assert session == "archived" and convo.one("SELECT filed_under FROM chat_sessions WHERE node_id = 'menu'") == "recipes"
    second = convo.post(ORG, "Yes", choice={"message_id": card_id, "option": "yes"})
    assert second.status_code == 409 and second.json()["error"]["code"] == "already_decided"


def test_the_chart_invariants_hold_after_every_step(convo):
    moved(convo)
    chart = convo.client.get("/api/chart").json()
    graph = convo.client.get("/api/graph", params={"level": "full"}).json()
    live = {n["id"] for n in chart["nodes"]}
    assert {n["id"] for n in graph["nodes"] if n["kind"] in ("root", "department", "division")} == live              # I2: the graph mirrors the chart
    assert not [e for e in graph["edges"] if e["kind"] == "contains" and (e["src"], e["dst"]) not in
                {(n["parent_id"], n["id"]) for n in chart["nodes"]}]
    assert convo.one("SELECT count(*) FROM graph_nodes WHERE chat_session_id IS NULL") == 0
    assert convo.one("SELECT count(*) FROM usage_ledger WHERE provider != 'stub' AND atom_id IS NULL") == 0                   # no money without an atom


# ============================================ failures =======================================================================

def test_bad_json_twice_then_a_good_reply_changes_the_chart_once(convo):
    good = decide("smalltalk", "none", reuse=())
    convo.say("Thanks a lot", {"kind": "decide", "intent": "dance"}, {"nonsense": True}, good)
    assert len(convo.connector.calls) == 3 and convo.sutra()[-1] == ("text", planner.LINES["smalltalk"])
    assert convo.one("SELECT count(*) FROM chart_changes") == 1 and convo.one("SELECT count(*) FROM tasks") == 0


def test_an_unavailable_model_changes_nothing_and_retry_works(convo):
    mid = convo.say("I need a landing page for my coffee shop.", ConnectorFailure("unavailable", "no model"))
    assert convo.one("SELECT state FROM chat_messages WHERE id = ?", mid) == "error"
    assert convo.one("SELECT count(*) FROM chart_changes") == 1 and convo.one("SELECT count(*) FROM tasks") == 0
    convo.connector.push(decide("smalltalk", "none", reuse=()))
    response = convo.client.post(f"/api/chats/{ORG}/retry", headers=HEADERS)
    assert response.status_code == 202, response.text
    convo.until("the retry to end", lambda: not convo.services.runner.busy)
    assert convo.one("SELECT state FROM chat_messages WHERE id = ?", mid) == "ok"


class SurvivingLauncher(FakeLauncher):
    """The launcher of the app after a crash: the engine processes of the app that died are still alive, and `adopt` says which."""

    def adopt(self, pid: int, run_dir) -> None:
        self._alive.add(pid)
        self.commands[pid] = f"python -m sutra_app.engine --run-dir {run_dir}"


class FixedClock:
    def __init__(self, at: int) -> None:
        self.at = at

    def time(self) -> float:
        return float(self.at)

    def now(self) -> int:
        return self.at


def test_a_restart_in_the_middle_of_a_run_reattaches_and_leaves_one_copy_of_every_line(tmp_path):
    first = tmp_path / "first"
    app, connector = make_scenario(first)
    with TestClient(app, base_url="http://127.0.0.1:8780") as client:
        c = Scenario(client, app, connector)
        task = asked(c)
        c.db.checkpoint()
        shutil.copytree(first, tmp_path / "crashed")                       # the folder as a crash would have left it: the run is waiting
    launcher = SurvivingLauncher()
    app2, connector2 = make_scenario(tmp_path / "crashed", launcher=launcher, clock=FixedClock(1793786400 + 5))
    pid = sqlite3.connect(tmp_path / "crashed" / "data" / "db.sqlite3").execute("SELECT pid FROM tasks WHERE id = ?", (task,)).fetchone()[0]
    launcher.adopt(pid, "(the run folder)")                                  # the process of the dead app still runs
    with TestClient(app2, base_url="http://127.0.0.1:8780") as client2:
        c2 = Scenario(client2, app2, connector2)
        assert c2.services.reconciled.reattached == [task] and c2.task_status(task) == "waiting_user"
        sessions = c2.session_of("web")

        def counts():
            return (len(c2.messages(sessions)), c2.one("SELECT count(*) FROM atoms"), c2.one("SELECT count(*) FROM chat_messages WHERE src_ref LIKE '%#chat:2'"),
                    c2.one("SELECT events_offset FROM tasks WHERE id = ?", task))

        before = counts()
        assert before[1:3] == (1, 1)
        c2.write_events(task, atom_line(close_with(c2.opened.atom, 0)), ev("run.ended", status="done", outcome="Landing page ready"))
        c2.until("the reattached run to end", lambda: c2.task_status(task) == "done")
        after = counts()
        assert after[:3] == before[:3] and after[3] > before[3]                       # nothing is read twice; only the new lines were
        assert c2.one("SELECT display FROM atoms WHERE id = ?", ATOM) == "closed" and len(c2.cards("done")) == 1
