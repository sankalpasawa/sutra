"""The Ask mode of a function's chat in the node panel (J2 sync 4, D147 and D148): the box under an agent's pill has a Note and an Ask mode, a question is one
POST /api/ask?dept=, the question and the answer are lines of the function's own chat, and the words of a question that could not be sent stay in the box.

The tests run the real node_panel.js, agent_chats.js and chat_view.js in headless Chrome (marker `browser`, SUTRA_BROWSER=1) on the node panel's mount page, over
the fake backend. The fake has no /api/ask of its own in the folder this file was written for, so the module adds the one a server would have: it stores the
owner's question as a line of the function's session (`ask: "q"`), waits a moment, and stores the answer (`ask: "records"`), as POST /api/ask does. If the fake
already has the route, that one is used and the checks below hold for it as well.
"""
from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import NamedTuple

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse

import fake_backend

STATIC = Path(__file__).resolve().parents[2] / "sutra_app" / "ui" / "static"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCRIPTS = ("sutra_ctx.js", "sutra_events.js", "fluid.js", "fnode_view.js", "chat_view.js", "chat_draft.js", "chat_scroll.js", "model_pick.js", "chat_pill.js",
           "agent_chats.js", "node_panel.js")
AUDIT = "cs_e1acceab39f9"                 # web.audit's own session
THINK_S = 0.5                             # how long the fake's answer takes: long enough for the page to show "Asking Audit..."
WHY = "Why was W-3 scored below the gate?"


class PanelServer(NamedTuple):
    url: str
    client: fake_backend.FakeClient


def add_ask_route(app) -> bool:
    """POST /api/ask on the fake, the way the real route behaves for a function that has a session: the question is stored at once, the answer after a moment.
    `/__test/ask` {fail: 409} makes the next question be refused; {note: "..."} adds a note to the next answer. False when the fake already has the route."""
    state = app.state.fake
    if any(getattr(route, "path", "") == "/api/ask" for route in app.router.routes):
        return False
    plan = {"fail": None, "note": ""}

    @app.post("/api/ask")
    async def ask(request: Request, dept: str | None = None):
        fake_backend.require_token(request, state)
        body = await fake_backend.json_body(request)
        who = body.get("who") if isinstance(body, dict) else None
        if who not in ("identity", "adaptation", "priority", "coordination", "audit", "validator"):
            return JSONResponse({"error": "not a function"}, status_code=400)
        if plan["fail"]:
            status, plan["fail"] = plan["fail"], None
            return JSONResponse({"error": "busy" if status == 409 else "failed"}, status_code=status)
        question = " ".join(str(body.get("q") or "").split())
        sid = next((sid for sid, node in state.session_ids().items() if node["id"] == f"web.{who}"), AUDIT)
        chat = state.chat(sid)
        asked = state.add_message(chat, "user", "user", "text", question, task_id=fake_backend.LIVE_RUN["task_id"])
        asked["ask"] = "q"
        await asyncio.sleep(THINK_S)
        answer = state.add_message(chat, "agent", who, "text", f"From the records: {question}", task_id=fake_backend.LIVE_RUN["task_id"])
        answer["ask"] = "records"
        reply = {"who": who, "answer": answer["text"], "from": "records", "session_id": sid, "question_id": asked["id"], "answer_id": answer["id"]}
        if plan["note"]:
            reply["note"], plan["note"] = plan["note"], ""
        return JSONResponse(reply)

    @app.post("/__test/ask")
    async def control(request: Request):
        body = await fake_backend.json_body(request)
        plan.update({k: v for k, v in body.items() if k in plan})
        return JSONResponse(plan)
    return True


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
    app = fake_backend.make_app(static_dir=build_static(tmp_path_factory.mktemp("ask-static")))
    add_ask_route(app)
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


def load(browser, fake):
    fake.stage("full")
    assert fake.request("POST", "/__fake/pill", {"on": True}, token=False)[0] == 200
    fake.page("agents", page_html())
    browser.goto(fake.mount_url("agents"))
    browser.wait_for("window.mounted === true")


def open_node(browser, node_id):
    browser.js(f"window.openNode({json.dumps(node_id)}, 'chat')")
    browser.wait_for("!!document.querySelector('.nnotehost .nnote-text')")


def shown(browser, css) -> bool:
    return browser.js(f"(() => {{ const e = document.querySelector({q(css)}); return !!e && !e.hidden && e.offsetParent !== null; }})()")


def texts(browser, css):
    return browser.js(f"Array.from(document.querySelectorAll({q(css)}), e => e.textContent.trim().replace(/\\s+/g, ' '))")


def ask_mode(browser):
    browser.click('[data-act="box-mode"][data-mode="ask"]')
    browser.wait_for("!!document.querySelector('.nask-text')")


def asks(fake):
    return [r for r in fake.log("/api/ask")]


# ---- the page ----------------------------------------------------------------------------------------------------------------------------------------

@pytest.mark.browser
def test_a_functions_box_offers_a_note_and_a_question_and_starts_as_the_note(fake, browser):
    load(browser, fake)
    open_node(browser, "web.audit")
    assert browser.count('[data-act="box-mode"]') == 2
    assert texts(browser, '[data-act="box-mode"]') == ["Note", "Ask"]
    assert browser.js("document.querySelector('[data-mode=\"note\"]').getAttribute('aria-pressed')") == "true"
    assert texts(browser, ".nnote-l") == ["Note to Audit"] and browser.count('[data-act="steer"]') == 1 and browser.count('[data-act="ask"]') == 0
    assert not browser.console_errors


@pytest.mark.browser
def test_a_question_is_one_post_the_box_waits_and_both_lines_show_in_the_chat(fake, browser):
    load(browser, fake)
    open_node(browser, "web.audit")
    ask_mode(browser)
    assert texts(browser, ".nnote-l") == ["Ask Audit"] and browser.count('[data-act="steer"]') == 0
    assert browser.js("document.querySelector('.nask-text').placeholder") == "Ask Audit about this run"
    browser.type(".nask-text", WHY)
    browser.click('[data-act="ask"]')
    browser.wait_for("!!document.querySelector('.nask-wait')")
    assert texts(browser, ".nask-wait") == ["Asking Audit…"]
    assert browser.js("document.querySelector('.nask-text').disabled") is True and browser.js("document.querySelector('[data-act=\"ask\"]').disabled") is True
    browser.wait_for("!document.querySelector('.nask-wait')")
    assert browser.js("document.querySelector('.nask-text').value") == "" and browser.js("document.querySelector('.nask-text').disabled") is False
    sent = asks(fake)
    assert [r["method"] for r in sent] == ["POST"] and sent[0]["status"] == 200 and sent[0]["token"] is True
    assert sent[0]["query"] == "dept=web"
    assert sent[0]["body"]["who"] == "audit" and sent[0]["body"]["q"] == WHY and "run" in sent[0]["body"]
    browser.wait_for("document.querySelectorAll('.nmsgs [data-ask]').length === 2")
    assert texts(browser, '.nmsgs [data-ask="q"]') == [f"You asked{WHY}"]
    assert texts(browser, '.nmsgs [data-ask="records"]')[0].endswith("From its records, no AI call") and f"From the records: {WHY}" in texts(browser, '.nmsgs [data-ask="records"]')[0]
    assert browser.js("document.querySelector('.nmsgs [data-ask=\"q\"]').classList.contains('me')") is True
    assert not browser.console_errors


@pytest.mark.browser
def test_enter_asks_and_shift_enter_is_a_new_line(fake, browser):
    load(browser, fake)
    open_node(browser, "web.audit")
    ask_mode(browser)
    browser.type(".nask-text", "Line one")
    browser.js("(() => { const t = document.querySelector('.nask-text'); t.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', shiftKey: true, bubbles: true, cancelable: true})); })()")
    assert asks(fake) == []
    browser.js("(() => { const t = document.querySelector('.nask-text'); t.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true, cancelable: true})); })()")
    browser.wait_for("!!document.querySelector('.nask-wait')")
    browser.wait_for("!document.querySelector('.nask-wait')")
    assert [r["body"]["q"] for r in asks(fake)] == ["Line one"]


@pytest.mark.browser
def test_a_question_that_is_refused_says_why_and_keeps_its_words(fake, browser):
    load(browser, fake)
    open_node(browser, "web.audit")
    ask_mode(browser)
    assert fake.request("POST", "/__test/ask", {"fail": 409}, token=False)[0] == 200
    browser.expect_failed("/api/ask", 409)
    browser.type(".nask-text", WHY)
    browser.click('[data-act="ask"]')
    browser.wait_for("document.querySelector('.nbanner') && !document.querySelector('.nbanner').hidden")
    assert texts(browser, ".nbanner")[0] == "Audit is still answering. Ask again in a moment."
    assert browser.js("document.querySelector('.nask-text').value") == WHY and browser.js("document.querySelector('.nask-text').disabled") is False
    assert browser.count(".nmsgs [data-ask]") == 0
    browser.click('[data-act="ask"]')                                                                   # the same words, once the function is free again
    browser.wait_for("document.querySelectorAll('.nmsgs [data-ask]').length === 2")
    assert [r["status"] for r in asks(fake)] == [409, 200]


@pytest.mark.browser
def test_an_answers_note_stays_under_the_box(fake, browser):
    load(browser, fake)
    open_node(browser, "web.audit")
    ask_mode(browser)
    fake.request("POST", "/__test/ask", {"note": "No model is connected."}, token=False)
    browser.type(".nask-text", WHY)
    browser.click('[data-act="ask"]')
    browser.wait_for("!!document.querySelector('.nask-note')")
    assert texts(browser, ".nask-note") == ["No model is connected."]


@pytest.mark.browser
def test_what_was_typed_in_one_mode_is_there_when_it_comes_back(fake, browser):
    load(browser, fake)
    open_node(browser, "web.audit")
    browser.type(".nnote-text", "Check the footer.")
    ask_mode(browser)
    assert browser.js("document.querySelector('.nask-text').value") == ""
    browser.type(".nask-text", "A question")
    browser.click('[data-act="box-mode"][data-mode="note"]')
    browser.wait_for("!!document.querySelector('.nnote-text') && !document.querySelector('.nask-text')")
    assert browser.js("document.querySelector('.nnote-text').value") == "Check the footer."
    ask_mode(browser)
    assert browser.js("document.querySelector('.nask-text').value") == "A question"
    assert asks(fake) == [] and fake.log("/api/chats/" + AUDIT + "/steer") == []


@pytest.mark.browser
def test_a_run_that_is_over_has_no_note_and_still_takes_a_question(fake, browser):
    load(browser, fake)
    open_node(browser, "web.audit")
    fake.request("POST", "/__fake/agents", {"over": True}, token=False)
    browser.expect_failed("/steer", 409)
    browser.type(".nnote-text", "Too late?")
    browser.click('[data-act="steer"]')
    browser.wait_for("!!document.querySelector('.nnotehost .nnote-over')")
    assert "You can still ask it about the run." in texts(browser, ".nnote-over")[0]
    assert browser.count('[data-act="box-mode"]') == 0 and browser.count('[data-act="steer"]') == 0
    assert texts(browser, ".nnote-l") == ["Ask Audit"] and browser.count('[data-act="ask"]') == 1
    browser.type(".nask-text", WHY)
    browser.click('[data-act="ask"]')
    browser.wait_for("document.querySelectorAll('.nmsgs [data-ask]').length === 2")
    assert [r["status"] for r in asks(fake)] == [200]


@pytest.mark.browser
def test_a_workflows_chat_has_no_ask_and_keeps_its_note_box(fake, browser):
    load(browser, fake)
    rows = fake.get("/api/teams/web/agents")[1]
    step = next(r for r in rows if r["kind"] == "step")
    open_node(browser, step["node_id"])
    assert browser.count('[data-act="box-mode"]') == 0 and browser.count('[data-act="ask"]') == 0 and browser.count('[data-act="steer"]') == 1
    assert texts(browser, ".nnote-l") == [f"Note to {step['label']}"]


@pytest.mark.browser
def test_a_past_runs_chat_is_read_and_not_asked(fake, browser):
    load(browser, fake)
    browser.js("window.openNode('web', 'agents')")
    browser.wait_for("!!document.querySelector('.agents-run select')")
    browser.js("(() => { const s = document.querySelector('.agents-run select'); s.value = " + json.dumps(fake_backend.PAST_RUN["run_id"]) +
               "; s.dispatchEvent(new Event('change', {bubbles: true})); })()")
    browser.wait_for("document.querySelectorAll('.agent').length === 2")
    browser.click('.agent-open[data-sid="cs_past_identity"]')
    browser.wait_for("!!document.querySelector('.npill-past')")
    assert not shown(browser, ".nnotehost") and browser.count('[data-act="ask"]') == 0
