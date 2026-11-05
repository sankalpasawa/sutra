"""The offline demo end to end (GAP-DEMO, D97): `create_app` with offline settings over a temp data dir, a message posted through the
HTTP API, and no model, CLI or network. The launcher is the FakeLauncher (a run starts and ends done); the stub answers the chat
agent from the message with the demo reply book."""
import time

import pytest
from fastapi.testclient import TestClient

from sutra_app.config import Settings
from sutra_app.library.types import FUNCTIONS
from sutra_app.main import create_app
from sutra_app.orchestrator.testing.fake_engine import FakeLauncher

TOKEN = "test-token-0123456789abcdef"
HEADERS = {"X-Sutra-Token": TOKEN}
BASE = "http://127.0.0.1:8780"
CAFE = "A website for my cafe"


@pytest.fixture
def app(tmp_path):
    settings = Settings.load({}, data_dir=tmp_path / "data", token=TOKEN, env_file=tmp_path / "none.env", engine="fake", watch_ms=20,
                             offline=True)
    return create_app(settings, launcher=FakeLauncher())


class Owner:
    def __init__(self, client, app) -> None:
        self.client, self.services = client, app.state.services

    def say(self, text: str) -> int:
        response = self.client.post("/api/chats/cs_org/messages", json={"text": text}, headers=HEADERS)
        assert response.status_code == 202, response.text
        end = time.time() + 15
        while self.services.runner.busy and time.time() < end:
            time.sleep(0.01)
        assert not self.services.runner.busy
        return response.json()["message_id"]

    def sql(self, text, *args):
        return [tuple(r) for r in self.services.db.conn().execute(text, args)]

    def sutra(self) -> list[str]:
        messages = self.client.get("/api/chats/cs_org/messages").json()["messages"]
        return [m["text"] for m in messages if m["who"] == "sutra" and m["kind"] == "text"]

    def departments(self) -> list[tuple]:
        return self.sql("SELECT id, name, purpose FROM org_nodes WHERE kind = 'department' ORDER BY rowid")


def test_a_first_message_creates_a_team_with_its_five_function_nodes_and_a_task(app):
    with TestClient(app, base_url=BASE) as client:
        owner = Owner(client, app)
        message_id = owner.say(CAFE)
        assert owner.departments() == [("website-cafe", "Website Cafe", CAFE)]
        kinds = {kind: chat for kind, chat in owner.sql("SELECT kind, chat_session_id FROM graph_nodes WHERE department_id = 'website-cafe'")}
        assert {"department", *FUNCTIONS} <= set(kinds) and all(kinds[f] for f in FUNCTIONS)
        sessions = [row[0] for row in owner.sql("SELECT id FROM chat_sessions WHERE id IN (%s)" % ",".join("?" * len(FUNCTIONS)), *[kinds[f] for f in FUNCTIONS])]
        assert len(sessions) == 5
        tasks = owner.sql("SELECT dept_id, title, request_id FROM tasks")
        assert tasks == [("website-cafe", CAFE, f"req-{message_id}")]
        said = owner.sutra()
        assert "I set up a Website Cafe team and gave it your request." in said
        assert not any("can't reach" in line for line in said)
        assert owner.sql("SELECT provider, model, usd, COUNT(*) FROM usage_ledger WHERE purpose = 'chat_plan' GROUP BY 1, 2, 3") == [
            ("stub", "scripted", 0.0, 3)]       # decide, change, assign: all stub rows, no Claude or Codex


def test_the_same_topic_reuses_the_team_and_another_topic_adds_one(app):
    with TestClient(app, base_url=BASE) as client:
        owner = Owner(client, app)
        owner.say(CAFE)
        owner.say("Add a menu to the cafe website")
        assert [name for _, name, _ in owner.departments()] == ["Website Cafe"]
        assert owner.sutra()[-1] == "I gave this to the Website Cafe team."
        assert [dept for (dept,) in owner.sql("SELECT dept_id FROM tasks ORDER BY rowid")] == ["website-cafe", "website-cafe"]
        owner.say("Track sales leads and quotes")
        assert [name for _, name, _ in owner.departments()] == ["Website Cafe", "Track Sales Leads Quotes"]
        assert owner.sutra()[-1] == "I set up a Track Sales Leads Quotes team and gave it your request."
        assert [dept for (dept,) in owner.sql("SELECT dept_id FROM tasks ORDER BY rowid")][-1] == "track-sales-leads-quotes"
        assert not any("can't reach" in line for line in owner.sutra())


def test_with_the_real_engine_process_the_mock_run_asks_one_question_and_ends_done(tmp_path):
    """No fake: `SUTRA_ENGINE=process` offline starts the real engine on J2's mock scenario (about 5 s). Identity asks its questions in
    the team's chat; the owner's answer lets the run finish."""
    settings = Settings.load({}, data_dir=tmp_path / "data", token=TOKEN, env_file=tmp_path / "none.env", engine="process", watch_ms=50,
                             offline=True)
    app = create_app(settings)
    with TestClient(app, base_url=BASE) as client:
        owner = Owner(client, app)

        def until(what, check, timeout=40.0):
            end = time.time() + timeout
            while time.time() < end:
                found = check()
                if found:
                    return found
                time.sleep(0.1)
            pytest.fail(f"timed out waiting for {what}")

        owner.say(CAFE)
        until("the team to ask", lambda: owner.sql("SELECT 1 FROM tasks WHERE status = 'waiting_user'"))
        (team_chat,) = owner.sql("SELECT chat_session_id FROM graph_nodes WHERE id = 'website-cafe'")[0]
        answer = client.post(f"/api/chats/{team_chat}/messages", json={"text": "Sweet Bean"}, headers=HEADERS)
        assert answer.status_code == 200, answer.text
        until("the run to end", lambda: owner.sql("SELECT 1 FROM tasks WHERE status = 'done'"))
        assert owner.sql("SELECT COUNT(*) FROM graph_nodes WHERE department_id = 'website-cafe' AND kind IN (%s)" % ",".join("?" * 5), *FUNCTIONS) == [(5,)]
        assert owner.sql("SELECT COUNT(*) > 0 FROM atoms") == [(1,)]
        assert not any("can't reach" in line for line in owner.sutra())
