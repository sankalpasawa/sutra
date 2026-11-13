"""The chats of the agents in the node panel (agent-sessions design 3.7, D130 to D134): the fake backend's routes, and the page in a real browser.

The fake's routes (GET /api/teams/{dept}/agents, the pill and choice of an agent's chat, POST /api/chats/{sid}/steer, PUT /api/tasks/{id}/choice) always run.
The browser tests run only with SUTRA_BROWSER=1: headless Chrome over CDP against the fake, on the panel mount page with the real node_panel.js, chat_pill.js,
model_pick.js and agent_chats.js. They prove that an agent's chat has the pill above a note box (and no message box), that Default says what it resolves to and
from where, that a pick is one PUT and the chip follows, that a note is one POST, that a finished run takes none, that a team's panel has the Agents tab with a run
switcher, and that a past run's chat shows its choice as a chip and no pill.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import NamedTuple

import pytest

import fake_backend

STATIC = Path(__file__).resolve().parents[2] / "sutra_app" / "ui" / "static"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCRIPTS = ("sutra_ctx.js", "sutra_events.js", "fluid.js", "fnode_view.js", "chat_view.js", "chat_draft.js", "chat_scroll.js", "model_pick.js", "chat_pill.js",
           "agent_chats.js", "node_panel.js")
AUDIT = "cs_e1acceab39f9"                 # web.audit's own session
IDENTITY_LOG = "cs_77aa10c2e9b4"          # web.identity's own working log (its node shows the team's chat; the Agents tab opens this)
W1 = "cs_662ce41c63ee"                    # the step W-1 of the Web team's task
TOKEN = {"X-Sutra-Token": fake_backend.TOKEN}
PAST_RUN = fake_backend.PAST_RUN["run_id"]


class PanelServer(NamedTuple):
    url: str
    client: fake_backend.FakeClient


def build_static(folder: Path) -> Path:
    (folder / "js").mkdir(parents=True)
    (folder / "css").mkdir()
    for name in SCRIPTS:
        shutil.copy(STATIC / "js" / name, folder / "js" / name)
    for name in ("sutra-panel.css", "j2.css"):
        shutil.copy(STATIC / "css" / name, folder / "css" / name)
    return folder


@pytest.fixture(scope="module")
def panel_server(tmp_path_factory):
    app = fake_backend.make_app(static_dir=build_static(tmp_path_factory.mktemp("agents-static")))
    running = fake_backend.run_in_thread(app)
    try:
        yield PanelServer(running.url, fake_backend.FakeClient(running.url, app.state.fake.token))
    finally:
        running.stop()


@pytest.fixture()
def fake(panel_server) -> fake_backend.FakeClient:
    panel_server.client.reset()
    return panel_server.client


def page_html() -> str:
    html = (FIXTURES / "mount_panel.html").read_text(encoding="utf-8")
    extra = "".join(f'<script src="/ui/js/{name}"></script>\n' for name in ("model_pick.js", "chat_pill.js", "agent_chats.js"))
    return html.replace('<script src="/ui/js/node_panel.js"></script>', extra + '<script src="/ui/js/node_panel.js"></script>')


def q(css: str) -> str:
    return json.dumps(css)


def load(browser, fake, **query):
    fake.stage("full")
    assert fake.request("POST", "/__fake/pill", {"on": True}, token=False)[0] == 200
    fake.page("agents", page_html())
    browser.goto(fake.mount_url("agents", **query))
    browser.wait_for("window.mounted === true")


def open_node(browser, node_id, tab="chat"):
    browser.js(f"window.openNode({json.dumps(node_id)}, {json.dumps(tab)})")


def present(browser, css):
    browser.wait_for(f"!!document.querySelector({q(css)})")


def absent(browser, css):
    browser.wait_for(f"!document.querySelector({q(css)})")


def shown(browser, css) -> bool:
    return browser.js(f"(() => {{ const e = document.querySelector({q(css)}); return !!e && !e.hidden && e.offsetParent !== null; }})()")


def texts(browser, css):
    return browser.js(f"Array.from(document.querySelectorAll({q(css)}), e => e.textContent.trim().replace(/\\s+/g, ' '))")


def requests(fake, prefix):
    return [r for r in fake.log(prefix)]


def pick_select(browser, css, value):
    browser.js(f"(() => {{ const s = document.querySelector({q(css)}); s.value = {json.dumps(value)}; s.dispatchEvent(new Event('change', {{bubbles: true}})); }})()")


# ---- the fake's routes (no browser) -----------------------------------------------------------------------------------------------------------------

def test_the_fake_lists_a_teams_agents_per_run_and_cascades_the_pick(fake):
    fake.stage("full")
    fake.request("POST", "/__fake/pill", {"on": True}, token=False)
    status, rows = fake.get("/api/teams/web/agents")
    assert status == 200 and [r["agent"] for r in rows] == ["identity", "adaptation", "priority", "coordination", "audit", "W-1", "W-2", "W-3", "W-4"]
    assert {r["effective"]["source"] for r in rows} == {"default"} and rows[0]["kind"] == "function" and rows[-1]["kind"] == "step"
    sid = rows[0]["session_id"]
    assert fake.request("PUT", f"/api/tasks/{rows[0]['task_id']}/choice", {"provider": "claude", "model": "haiku"}, token=True)[1]["own"]["model"] == "haiku"
    assert fake.get("/api/teams/web/agents")[1][0]["effective"] == {"provider": "claude", "model": "haiku", "effort": None, "source": "run"}
    status, body = fake.request("PUT", f"/api/chats/{sid}/choice", {"provider": "claude", "model": "opus", "effort": "max"}, token=True)
    assert status == 200 and body["source"] == "own" and body["effective"]["model"] == "opus"
    assert fake.get(f"/api/chats/{sid}/providers")[1]["own"] == {"provider": "claude", "model": "opus", "effort": "max"}
    assert fake.request("PUT", f"/api/chats/{sid}/choice", {"provider": None}, token=True)[1]["source"] == "run"
    assert fake.get("/api/teams/web/agents", run=PAST_RUN)[1][0]["status"] == "archived" and fake.get("/api/teams/web/agents", run="j2-nope")[0] == 404
    assert [r["run_id"] for r in fake.get("/api/departments/web/runs")[1]] == [fake_backend.LIVE_RUN["run_id"], PAST_RUN]


def test_the_fake_takes_a_note_only_for_a_live_agent_chat(fake):
    fake.stage("full")
    sid = fake.get("/api/teams/web/agents")[1][4]["session_id"]
    status, body = fake.request("POST", f"/api/chats/{sid}/steer", {"text": "  check the footer  "}, token=True)
    assert status == 200 and body == {"message_id": body["message_id"], "session_id": sid, "applies": "next_call"}
    assert fake.get(f"/api/chats/{sid}/messages")[1]["messages"][-1]["text"] == "check the footer"
    assert fake.request("POST", f"/api/chats/{sid}/steer", {"text": " "}, token=True)[0] == 422
    assert fake.request("POST", f"/api/chats/{sid}/steer", {"text": "x" * 2001}, token=True)[0] == 422
    assert fake.request("POST", f"/api/chats/{sid}/steer", {"text": "x"}, token=False)[0] == 401
    assert fake.request("POST", "/api/chats/cs_5e0a77b19c3d/steer", {"text": "x"}, token=True)[0] == 422                    # a team chat is written to directly
    fake.request("POST", "/__fake/agents", {"over": True}, token=False)
    assert fake.request("POST", f"/api/chats/{sid}/steer", {"text": "too late"}, token=True)[1]["error"]["code"] == "not_running"


# ---- the page ----------------------------------------------------------------------------------------------------------------------------------------

@pytest.mark.browser
def test_an_agents_chat_has_the_pill_above_a_note_box_and_no_message_box(fake, browser):
    load(browser, fake)
    open_node(browser, "web.audit")
    present(browser, ".npill .cpill-agent")
    present(browser, ".nnotehost .nnote-text")
    assert shown(browser, ".npill") and shown(browser, ".nnotehost") and not shown(browser, ".ncomposer")
    assert browser.js("document.querySelector('.npill').compareDocumentPosition(document.querySelector('.nnotehost')) & Node.DOCUMENT_POSITION_FOLLOWING") > 0
    assert texts(browser, ".nnote-l") == ["Note to Audit"]
    assert texts(browser, ".cpill-opt.auto") == ["Default: Claude Sonnet, high (from the app's default)"]
    assert browser.js("document.querySelector('.cpill-opt.auto').getAttribute('aria-pressed')") == "true"
    assert not browser.console_errors


@pytest.mark.browser
def test_a_pick_is_one_put_and_the_chip_follows_and_default_clears_it(fake, browser):
    load(browser, fake)
    open_node(browser, "web.audit")
    present(browser, '[data-act="choose-provider"][data-provider="claude"]')
    browser.click('[data-act="choose-provider"][data-provider="claude"]')
    present(browser, ".cpick-model")
    sent = requests(fake, "/api/chats/" + AUDIT + "/choice")
    assert [r["method"] for r in sent] == ["PUT"] and sent[0]["body"] == {"provider": "claude"}
    browser.wait_for("document.querySelector('.achip') && document.querySelector('.achip').dataset.source === 'own'")
    pick_select(browser, ".cpick-model", "haiku")
    browser.wait_for("!!document.querySelector('.achip') && document.querySelector('.achip').textContent.toLowerCase().includes('haiku')")
    assert browser.js("document.querySelector('.cpick-model').value") == "haiku"
    browser.click('[data-act="choose-provider"][data-provider=""]')
    absent(browser, ".cpick-model")
    browser.wait_for("document.querySelector('.achip').dataset.source === 'default'")
    assert [r["body"] for r in requests(fake, "/api/chats/" + AUDIT + "/choice")] == [{"provider": "claude"}, {"provider": "claude", "model": "haiku"}, {"provider": None}]
    assert not browser.console_errors


@pytest.mark.browser
def test_the_teams_pill_and_the_run_are_what_default_follows(fake, browser):
    load(browser, fake)
    fake.request("POST", "/__fake/agents", {"team": {"provider": "claude", "model": "haiku", "effort": "low"}}, token=False)
    open_node(browser, "web.priority")
    present(browser, ".cpill-agent")
    assert "from the team" in texts(browser, ".cpill-opt.auto")[0]
    fake.request("POST", "/__fake/agents", {"run_pick": {"provider": "claude", "model": "opus", "effort": None}}, token=False)
    fake.wait_subscribers(2)                                                      # the page's own stream and the panel's
    fake.emit("chat.choice", {"session_id": None, "task_id": "tsk_a1b2c3d4e5f6", "run_id": "r", "provider": "claude", "model": "opus", "effort": None, "source": "run"})
    browser.wait_for("document.querySelector('.cpill-opt.auto').textContent.includes('this run')")


@pytest.mark.browser
def test_a_note_is_one_post_the_box_empties_and_the_line_shows(fake, browser):
    load(browser, fake)
    open_node(browser, "web.audit")
    present(browser, ".nnote-text")
    browser.type(".nnote-text", "Check the footer links too.")
    browser.click('[data-act="steer"]')
    browser.wait_for("document.querySelector('.nnote-text').value === ''")
    sent = requests(fake, "/api/chats/" + AUDIT + "/steer")
    assert [r["method"] for r in sent] == ["POST"] and sent[0]["status"] == 200
    browser.wait_for("Array.from(document.querySelectorAll('.nmsgs')).some(e => e.textContent.includes('Check the footer links too.'))")
    assert fake.request("POST", "/__fake/agents", {}, token=False)[1]["notes"][-1]["text"] == "Check the footer links too."
    assert not browser.console_errors


@pytest.mark.browser
def test_a_run_that_is_over_takes_no_note(fake, browser):
    load(browser, fake)
    open_node(browser, "web.audit")
    present(browser, ".nnote-text")
    fake.request("POST", "/__fake/agents", {"over": True}, token=False)
    browser.expect_failed("/steer", 409)
    browser.type(".nnote-text", "Too late?")
    browser.click('[data-act="steer"]')
    browser.wait_for("document.querySelector('.nnotehost').textContent.includes('That run is over')")
    assert not shown(browser, ".nnote-text") or browser.js("!document.querySelector('.nnote-text')")


@pytest.mark.browser
def test_the_agents_tab_lists_the_team_opens_an_agents_own_chat_and_switches_runs(fake, browser):
    load(browser, fake)
    open_node(browser, "web", tab="chat")
    present(browser, '[data-nptab="agents"]:not([hidden])')
    browser.click('[data-nptab="agents"]')
    present(browser, ".agents-list .agent")
    assert browser.count(".agent") == 9 and texts(browser, ".agents-h") == ["The team", "Workflows"]
    assert texts(browser, ".agent .agent-name")[:5] == ["Identity", "Adaptation", "Priority", "Coordination", "Audit"]
    assert texts(browser, ".agent .achip")[0] == "Claude sonnet, high default"
    assert shown(browser, ".agents-run select")
    # Identity's own log (its node shows the team's chat, so the row opens its session itself)
    browser.click('.agent-open[data-sid="' + IDENTITY_LOG + '"]')
    present(browser, ".npill .cpill-agent")
    assert texts(browser, ".nnote-l") == ["Note to Identity"]
    # the earlier run: its chats are read only, the choice is a chip and there is no pill
    open_node(browser, "web", tab="agents")
    present(browser, ".agents-run select")
    pick_select(browser, ".agents-run select", PAST_RUN)
    browser.wait_for("document.querySelectorAll('.agent').length === 2")
    assert texts(browser, ".agent .agent-state") == ["past run", "past run"]
    browser.click('.agent-open[data-sid="cs_past_identity"]')
    present(browser, ".npill-past")
    assert "haiku" in texts(browser, ".npill-past")[0] and not shown(browser, ".cpill") and not shown(browser, ".nnotehost") and not shown(browser, ".ncomposer")
    assert not browser.console_errors


AGENT_LINES = """Object.fromEntries(Array.from(document.querySelectorAll('.agent'), a =>
  [a.querySelector('.agent-name').textContent, Array.from(a.querySelectorAll('.agent-purpose'), p => p.textContent)]))"""
FIVE = ("Identity", "Adaptation", "Priority", "Coordination", "Audit")


@pytest.mark.browser
def test_the_agents_tab_says_how_many_calls_were_judging_under_an_agents_usage_and_no_line_for_an_agent_with_none(fake, browser):
    """D159: `usage.by_purpose` of the agents rows (the fake serves it as the real route does) becomes "judging N calls, $x" (the late judge's plan and judge calls) under the
    usage of the agent that has some; the others have no line. The lines sit on a row of their own below the usage, inside the row."""
    load(browser, fake)
    open_node(browser, "web", tab="agents")
    present(browser, ".agents-list .agent")
    lines = browser.js(AGENT_LINES)
    assert {name: lines[name] for name in FIVE} == {"Identity": [], "Adaptation": ["judging 2 calls, $0.01"], "Priority": ["judging 2 calls, $0.01"],
                                                    "Coordination": ["judging 2 calls, $0.02"], "Audit": []}                         # Coordination: one judge call and one plan call
    assert all(not v for k, v in lines.items() if k not in FIVE), lines                                                              # the workflows only worked
    assert browser.count(".agent .agent-purposes") == 3 and browser.count(".agent [data-line='questions']") == 0                      # nobody was asked anything
    assert texts(browser, ".agent-usage")[1] == "3 calls, $0.02" and "judging" not in texts(browser, ".agent-usage")[1]               # the usage line is as it was
    assert browser.js("document.querySelector(\"[data-line='judging']\").title") == "Calls that planned or judged a workflow in this agent's turn"
    box = browser.js("""(() => {
      const row = Array.from(document.querySelectorAll('.agent')).find(a => a.querySelector('.agent-name').textContent === 'Priority');
      const usage = row.querySelector('.agent-usage').getBoundingClientRect(), lines = row.querySelector('.agent-purposes').getBoundingClientRect(), mine = row.getBoundingClientRect();
      return {below: lines.top >= usage.bottom - 1, inside: lines.left >= mine.left - 1 && lines.right <= mine.right + 1 && lines.bottom <= mine.bottom + 1, sideways: document.documentElement.scrollWidth > innerWidth};
    })()""")
    assert box == {"below": True, "inside": True, "sideways": False}
    assert not browser.console_errors


@pytest.mark.browser
def test_a_question_asked_in_a_functions_chat_adds_its_questions_line_to_the_agents_tab(fake, browser):
    """The whole path of D147 to D149 and D159: the owner asks Audit in its chat, the model answers (booked as one `agent_chat` call of Audit's session), and the Agents tab
    says "questions 1 call, $0.02" under Audit's usage, next to the lines the judging calls already had."""
    load(browser, fake)
    assert fake.request("POST", "/__fake/ask", {"mode": "model", "text": "Item 4 was not met: the footer has no phone number."}, token=False)[0] == 200
    open_node(browser, "web.audit")
    present(browser, ".nnotehost .nnote-text")
    browser.click('[data-act="box-mode"][data-mode="ask"]')
    present(browser, ".nask-text")
    browser.type(".nask-text", "Which check failed?")
    browser.click('[data-act="ask"]')
    browser.wait_for("Array.from(document.querySelectorAll('.nmsgs')).some(e => e.textContent.includes('the footer has no phone number'))")
    open_node(browser, "web", tab="agents")
    present(browser, ".agents-list .agent")
    lines = browser.js(AGENT_LINES)
    assert lines["Audit"] == ["questions 1 call, $0.02"]
    assert lines["Priority"] == ["judging 2 calls, $0.01"] and lines["Identity"] == []                                                # nobody else's row moved
    assert texts(browser, ".agent-usage")[4].startswith("7 calls, $0.07")                                                             # Audit's six turns and the answer: the usage line counts it too
    assert not browser.console_errors


@pytest.mark.browser
def test_an_agents_live_work_shows_while_it_works_and_goes_when_its_line_arrives(fake, browser):
    load(browser, fake)
    open_node(browser, "web.audit")
    present(browser, ".nnote-text")
    fake.wait_subscribers(2)
    fake.emit("chat.partial", {"session_id": AUDIT, "message_id": 0, "who": "audit", "delta": "Checking the footer", "reset": True, "tool": "Read index.html"})
    browser.wait_for("!!document.querySelector('.ccstream .agentlive') && document.querySelector('.ccstream').textContent.includes('Read index.html')")
    assert "Checking the footer" in texts(browser, ".ccstream")[0]
    fake.emit("chat.partial", {"session_id": AUDIT, "message_id": 0, "who": "audit", "delta": "", "reset": True, "done": True})
    browser.wait_for("document.querySelector('.ccstream').hidden === true")
