"""The node panel in a real browser (UI-6, docs/design/ui.md sections 6.4, 6.5, 9 and 10; S3-web-05, S4-fnodes-06, S4-fnodes-10, S4-fnodes-12).

Runs only with SUTRA_BROWSER=1 (the gate skips it): headless Chrome over CDP against the fake backend of UI-0, on its `panel` mount page, which loads the
real `sutra_ctx.js`, `sutra_events.js`, `fnode_view.js`, `chat_view.js`, `node_panel.js` and `sutra-panel.css` and nothing else of the UI. The J2 style sheet
is the real `j2.css` once UI-2 has merged it and, until then, a small stand-in with J2's tokens and the few J2 rules the panel leans on.

What it proves: the Identity chip opens the DEPARTMENT's chat with a message box and the other four functions open a read-only log; a division click is a
lens on its team's Identity with a link to the whole team's chat; the Details tab draws the function drawer with the five atom states; the department page
has the Go-to-tab button and Home has not; one drawer at a time, Esc, focus; what happens on 409, 403, 401, 404; the panel keeps itself current from the
event stream and from polling; Show all; Earlier chats; and that nothing is logged as an error.

Stages of the story (the fake's): "2" the Web team asks about the menu (the box is open: it is an answer), "3" the owner answered and the team works (the box
is closed), "full" two teams, two divisions and every status word.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import NamedTuple

import pytest

import fake_backend

STATIC = Path(__file__).resolve().parents[2] / "sutra_app" / "ui" / "static"
SCRIPTS = ("sutra_ctx.js", "sutra_events.js", "fluid.js", "fnode_view.js", "chat_view.js", "chat_draft.js", "chat_scroll.js", "node_panel.js")
DEPT_SESSION = "cs_5e0a77b19c3d"          # the Web team's chat (the department node)
IDENTITY_LOG = "cs_77aa10c2e9b4"          # Identity's own working log
ADAPTATION_LOG = "cs_b37b2000ef36"
DIVISION_MENU = "cs_3e11bad0c0de"         # Menu, a division of Content
CONTENT_SESSION = "cs_6c0ffee1b2a3"
FUNCTIONS = ("identity", "adaptation", "priority", "coordination", "audit")
DOT = "·"
BUSY = "The team is working. You can write again when it asks you something or is done"
NO_TOKEN = "This page was opened without its access token. Reload it from the app."

# J2's tokens (the dark set) and the few J2 rules the panel leans on, for the days before the real j2.css is in the repository.
STAND_IN_J2_CSS = """
:root{color-scheme:dark;--bg:#161513;--panel:#1c1b19;--panel2:#24221f;--ink:#ece6dc;--muted:#9a9186;--line:#2e2b27;--on:#161513;--validator:#e0b25c;--bad:#ef8f7a;
--ok:#9fc08a;--accent:#a58be6;--warm1:#e0a458;--warm3:#c9a96e;--shadow:rgb(0 0 0 / .45);--mono:Menlo,monospace;--display:Arial,sans-serif;--body:Arial,sans-serif}
:root[data-theme=light]{color-scheme:light;--bg:#f6f2ec;--panel:#fbf8f3;--panel2:#f2ece3;--ink:#2b2620;--muted:#6b6155;--line:#e6dfd4;--on:#ffffff;--validator:#80590f;--bad:#b0392c;--ok:#456e33;--accent:#6e52c4}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14.5px/1.5 var(--body)}
button{font:500 13px var(--body);cursor:pointer}.empty{color:var(--muted)}.code{font:500 11px var(--mono);color:var(--muted)}
.linkbtn{border:0;background:none;color:var(--accent);text-decoration:underline;padding:0;font:inherit}
.agentdrawer{position:fixed;top:0;right:0;bottom:0;width:50vw;z-index:60;overflow:auto;background:var(--panel);border-left:1px solid var(--line);padding:14px 18px}
.agentdrawer[hidden]{display:none}@media (max-width:700px){.agentdrawer{width:100vw}}
.adhead{display:flex;align-items:center;justify-content:space-between;gap:10px}.adhead h3{margin:0}.adnote{color:var(--muted);font-size:13px}
.adsec{margin:12px 0}.adsec h4{margin:0 0 6px}.adsmall{color:var(--muted);font-size:12px;margin-top:2px}
.sb{max-width:88%;padding:9px 12px;border-radius:12px;white-space:pre-wrap;word-wrap:break-word}
.sb.team{background:var(--panel);border:1px solid var(--line);align-self:flex-start}.sb.me{background:var(--accent);color:var(--on);align-self:flex-end}
.opts{display:flex;flex-direction:column;gap:6px;margin-top:8px}.opts button{text-align:left;border:1px solid var(--accent);background:var(--panel);color:var(--ink);border-radius:9px;padding:8px 11px}
.row{display:flex;gap:8px}textarea{flex:1;resize:none;height:56px;border:1px solid var(--line);border-radius:9px;padding:9px 11px;font:inherit;background:var(--panel);color:var(--ink)}
.send{background:var(--accent);color:var(--on);border:0;border-radius:9px;padding:0 18px;font-weight:600}.send:disabled,textarea:disabled{opacity:.5;cursor:not-allowed}
.ready{border:2px solid var(--ok);border-radius:12px;padding:12px;background:var(--panel)}.oops{border:2px solid var(--bad);border-radius:12px;padding:12px;background:var(--panel)}
"""


class PanelServer(NamedTuple):
    url: str
    client: fake_backend.FakeClient


def build_static(folder: Path) -> Path:
    """A static folder with the real panel scripts and style, plus a j2.css (the real one when it exists)."""
    (folder / "js").mkdir(parents=True)
    (folder / "css").mkdir()
    for name in SCRIPTS:
        shutil.copy(STATIC / "js" / name, folder / "js" / name)
    shutil.copy(STATIC / "css" / "sutra-panel.css", folder / "css" / "sutra-panel.css")
    real = STATIC / "css" / "j2.css"
    if real.is_file():
        shutil.copy(real, folder / "css" / "j2.css")
    else:
        (folder / "css" / "j2.css").write_text(STAND_IN_J2_CSS, encoding="utf-8")
    return folder


@pytest.fixture(scope="module")
def panel_server(tmp_path_factory):
    app = fake_backend.make_app(static_dir=build_static(tmp_path_factory.mktemp("panel-static")))
    running = fake_backend.run_in_thread(app)
    try:
        yield PanelServer(running.url, fake_backend.FakeClient(running.url, app.state.fake.token))
    finally:
        running.stop()


@pytest.fixture()
def fake(panel_server) -> fake_backend.FakeClient:
    panel_server.client.reset()
    return panel_server.client


# ---------------------------------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------------------------------
def q(css: str) -> str:
    return json.dumps(css)


def load(browser, fake, *, stage="2", dept=None):
    """Open the panel's mount page on one stage of the story; `dept` makes it a department page."""
    fake.stage(stage)
    browser.goto(fake.mount_url("panel", **({"dept": dept} if dept else {})))
    browser.wait_for("window.mounted === true")


def open_node(browser, node_id, tab="chat"):
    """Open a node and wait until the panel has loaded it (`open` returns a promise, which the browser driver awaits)."""
    browser.js(f"window.openNode({json.dumps(node_id)}, {json.dumps(tab)})")


def present(browser, css):
    browser.wait_for(f"!!document.querySelector({q(css)})")


def absent(browser, css):
    browser.wait_for(f"!document.querySelector({q(css)})")


def count(browser, css) -> int:
    return browser.count(css)


def texts(browser, css):
    return browser.js(f"Array.from(document.querySelectorAll({q(css)}), e => e.textContent.trim().replace(/\\s+/g, ' '))")


def attrs(browser, css, name):
    return browser.js(f"Array.from(document.querySelectorAll({q(css)}), e => e.getAttribute({q(name)}))")


def visible(browser, css) -> bool:
    return browser.js(f"(() => {{ const e = document.querySelector({q(css)}); return !!e && !e.hidden && e.offsetParent !== null; }})()")


def hidden(browser, css) -> bool:
    return browser.js(f"(() => {{ const e = document.querySelector({q(css)}); return !e || e.hidden || e.offsetParent === null; }})()")


def is_open(browser) -> bool:
    return browser.js("window.panel.isOpen()") is True


def type_and_send(browser, text):
    browser.type(".nbox", text)
    browser.click(".ncomposer .send")


def clear_box(browser):
    """Empty the message box the way the owner does (an input event follows, so the chat's draft is emptied too)."""
    browser.js("(() => { const b = document.querySelector('.nbox'); b.value = ''; b.dispatchEvent(new Event('input', {bubbles: true})); })()")


def posts(fake, session):
    return [r for r in fake.log(f"/api/chats/{session}/messages") if r["method"] == "POST"]


def gets(fake, path):
    return [r for r in fake.log(path) if r["method"] == "GET" and r["path"] == path]


def wait_until(check, what, timeout=8.0):
    deadline = time.monotonic() + timeout
    while not check():
        assert time.monotonic() < deadline, f"still false after {timeout} s: {what}"
        time.sleep(0.03)


def no_errors(browser, network=False):
    """Nothing was logged as an error. `network`: the refusals the test asked for are logged by Chrome as network errors; those are allowed."""
    errors = [line for line in browser.console_errors if not (network and line.startswith("[network]"))]
    assert errors == []
    assert browser.js("window.mountErrors") == []


def message(sid, number, text, *, who="identity", kind="text", card=None):
    return {"id": number, "session_id": sid, "role": "agent", "who": who, "kind": kind, "text": text, "card": card, "pause": None, "answered_by": None,
            "task_id": None, "state": "ok", "at": "2026-11-04T10:09:00Z"}


def chat_message(sid, number, text, **extra):
    return {"session_id": sid, "message": message(sid, number, text, **extra)}


# ======================================================================================================================
# the Chat tab: whose chat is it, and can the owner write in it
# ======================================================================================================================
@pytest.mark.browser
def test_the_identity_chip_opens_the_departments_chat_with_a_message_box(browser, fake):
    load(browser, fake)
    open_node(browser, "web.identity")
    assert is_open(browser) and browser.js("document.body.classList.contains('nodeopen')") is True
    assert texts(browser, "#nptitle") == ["Identity"] and texts(browser, ".npsub") == ["Client Lead"]
    assert texts(browser, ".nstatus") == ["waiting on you"] and texts(browser, ".npprovider") == ["Claude"]
    assert texts(browser, ".nlens") == ["This is Web's chat. Identity is the voice of the team."]
    assert attrs(browser, ".nmsgs .nmsg", "data-who") == ["user", "identity"]
    assert texts(browser, ".nmsg.me") == ["A website for my cafe"]
    assert texts(browser, ".nmsg .sq") == ["Should the menu show prices?"]
    assert texts(browser, ".nmsg .opts button") == ["Yes, show the prices", "No, names only"]
    assert visible(browser, ".ncomposer") and browser.js("document.querySelector('.nbox').disabled") is False
    assert browser.js("document.querySelector('.nbox').placeholder") == "Or type your own answer…"
    # the chat shown is the team's, not Identity's own working log
    chats = [r["path"] for r in fake.log("/api/chats/") if r["path"].endswith("/messages")]
    assert chats == [f"/api/chats/{DEPT_SESSION}/messages"]
    assert not any(IDENTITY_LOG in r["path"] for r in fake.log())
    session_of = "window.panel.chatSessionFor(window.graph.nodes.find(n => n.id === %s), window.graph)"
    assert browser.js(session_of % q("web.identity")) == DEPT_SESSION
    assert browser.js(session_of % q("web.adaptation")) == ADAPTATION_LOG
    assert browser.js(session_of % q("web")) == DEPT_SESSION
    assert browser.js("window.panel.chatSessionFor(null, window.graph)") is None
    assert browser.js("window.panel.chatSessionFor({id: 'ghost.identity', kind: 'function', fn: 'identity', dept_id: 'ghost'}, window.graph)") is None
    assert browser.js("window.panel.chatSessionFor({id: 'x', kind: 'step', chat_session_id: ''}, window.graph)") is None
    assert browser.js("localStorage.getItem('sutra:seen:%s')" % DEPT_SESSION) == "2"
    no_errors(browser)


@pytest.mark.browser
def test_the_departments_chat_links_to_the_team_page_and_the_focus_starts_on_close(browser, fake):
    load(browser, fake)
    open_node(browser, "web")
    assert texts(browser, "#nptitle") == ["Web"] and texts(browser, ".npsub") == ["team"]
    assert texts(browser, ".nlinks") == ["Open the team page"] and hidden(browser, ".nlens")
    assert browser.js("document.activeElement.hasAttribute('data-npclose')") is True
    browser.click(".nlinks button")
    assert browser.js("window.navigated") == "/d/web/?view=simple"
    no_errors(browser)


@pytest.mark.browser
def test_an_option_button_answers_with_option_n_and_the_question_closes(browser, fake):
    load(browser, fake)
    open_node(browser, "web.identity")
    fake.wait_subscribers(2)
    browser.click(".nmsg .opts button")
    browser.wait_for("document.querySelectorAll('.nmsg .opts').length === 0 && document.querySelectorAll('.nmsg').length === 4")
    sent = posts(fake, DEPT_SESSION)
    assert len(sent) == 1 and sent[0]["body"] == {"text": "Option 1"} and sent[0]["token"] is True
    assert texts(browser, ".nmsg.me") == ["A website for my cafe", "Yes, show the prices"]
    assert texts(browser, ".nmsg:last-child")[0].endswith("Thanks. I have what I need and the team is starting.")
    assert "@Requester" not in browser.js("document.querySelector('.nmsgs').textContent")
    no_errors(browser)


@pytest.mark.browser
def test_a_typed_line_goes_to_the_session_in_view_and_the_box_keeps_it_until_the_server_answers(browser, fake):
    load(browser, fake)
    open_node(browser, "web.identity")
    browser.expect_failed(f"/api/chats/{DEPT_SESSION}/messages", 409)
    fake.fail(f"/api/chats/{DEPT_SESSION}/messages", 409, method="POST", count=1)
    type_and_send(browser, "Show the prices")
    browser.wait_for("!document.querySelector('.nbanner').hidden")
    assert texts(browser, ".nbanner") == [BUSY]
    assert browser.js("document.querySelector('.nbox').value") == "Show the prices"       # kept: it did not go
    assert browser.js("document.querySelector('.nbox').disabled") is False
    browser.click(".ncomposer .send")                                                      # the same text again: accepted this time
    browser.wait_for("document.querySelector('.nbox').value === '' && document.querySelectorAll('.nmsg.me').length === 2")
    assert [p["body"] for p in posts(fake, DEPT_SESSION)] == [{"text": "Show the prices"}] * 2
    assert texts(browser, ".nmsg.me")[-1] == "Show the prices" and browser.js("document.querySelector('.nbanner').hidden") is True
    assert count(browser, ".nmsg .opts") == 0
    no_errors(browser, network=True)


@pytest.mark.browser
def test_enter_sends_shift_enter_does_not_and_an_empty_box_sends_nothing(browser, fake):
    load(browser, fake)
    open_node(browser, "web.identity")
    browser.type(".nbox", "first line")
    browser.js("document.querySelector('.nbox').dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', shiftKey: true, bubbles: true}))")
    time.sleep(0.2)
    assert posts(fake, DEPT_SESSION) == []
    browser.press("Enter")
    browser.wait_for("document.querySelector('.nbox').value === ''")
    assert [p["body"] for p in posts(fake, DEPT_SESSION)] == [{"text": "first line"}]
    browser.type(".nbox", "   ")
    browser.press("Enter")
    time.sleep(0.2)
    assert len(posts(fake, DEPT_SESSION)) == 1
    no_errors(browser)


@pytest.mark.browser
def test_a_team_at_work_has_its_box_closed_with_the_servers_sentence_until_it_asks_again(browser, fake):
    load(browser, fake, stage="3")
    open_node(browser, "web.identity")
    assert visible(browser, ".ncomposer") and browser.js("document.querySelector('.nbox').disabled") is True
    assert browser.js("document.querySelector('.ncomposer .send').disabled") is True
    assert texts(browser, ".nnote") == [BUSY] and browser.js("document.querySelector('.nbox').placeholder") == "The team is working…"
    fake.wait_subscribers(2)
    fake.stage("2")                                      # the team asks the owner again
    fake.emit("task.updated")
    browser.wait_for("document.querySelector('.nbox').disabled === false")
    assert hidden(browser, ".nnote") and posts(fake, DEPT_SESSION) == []
    no_errors(browser)


@pytest.mark.browser
def test_the_other_four_functions_open_a_read_only_working_log_that_shows_addresses_and_atom_cards(browser, fake):
    load(browser, fake, stage="full")
    personas = {"adaptation": "Strategist", "priority": "Prioritiser", "coordination": "Scheduler", "audit": "Quality Reviewer"}
    for fn, persona in personas.items():
        open_node(browser, f"web.{fn}")
        assert texts(browser, ".nnote") == [f"Read-only: this is the working log of {persona}."], fn
        assert browser.js("document.querySelector('.ncomposer').hidden") is True, fn
        assert texts(browser, ".npsub") == [persona] and hidden(browser, ".nlens") and hidden(browser, ".nlinks"), fn
    open_node(browser, "web.adaptation")
    assert attrs(browser, ".nmsg", "data-who") == ["adaptation", "validator", "adaptation"]
    assert texts(browser, ".nmsg small") == ["Strategist (Adaptation)", "Validator", "Strategist (Adaptation)"]
    assert texts(browser, ".nmsg")[0].startswith("Strategist (Adaptation)@Priority Proposing 3 workflows")          # a log keeps the addresses
    log = f"/api/chats/{ADAPTATION_LOG}"
    assert sorted(r["path"] for r in fake.log(log)) == sorted([log, log + "/messages"] * 2)            # the session and its messages, asked for at each of the two opens
    # an atom's card is written into the node's own log by the server; the panel draws it
    card = {"type": "atom", "atom_id": "a-b37b2000ef-01", "outcome": "closed", "label": "WORK ATOM CLOSED", "goal": "workflows are proposed", "rows": [{"label": "Result", "text": "goal reached"}]}
    fake.wait_subscribers(2)
    fake.emit("chat.message", chat_message(ADAPTATION_LOG, 4, "", who="sutra", kind="card", card=card))
    present(browser, ".ncard.c-atom")
    assert texts(browser, ".ncard.c-atom h4") == ["WORK ATOM CLOSED"] and texts(browser, ".ncard.c-atom dd") == ["goal reached"]
    assert texts(browser, ".nmsg:last-child small") == ["Sutra"]
    no_errors(browser)


@pytest.mark.browser
def test_a_division_is_a_lens_on_its_teams_identity(browser, fake):
    load(browser, fake, stage="full")
    open_node(browser, "menu")
    assert texts(browser, "#nptitle") == ["Menu"] and texts(browser, ".npsub") == ["division"]
    assert texts(browser, ".nlenstext") == ["Menu is part of Content. This is Content's Identity, showing the work for Menu."]
    assert texts(browser, ".nlens button") == ["Show everything for Content"]
    assert visible(browser, ".ncomposer")
    assert texts(browser, ".nmsg.note") == ["Menu is a division of Content. This chat shows Content's work for Menu."]
    assert texts(browser, ".nmsg.me") == ["Write the menu page copy"]
    assert [r["path"] for r in fake.log("/api/chats/") if r["path"].endswith("/messages")] == [f"/api/chats/{DIVISION_MENU}/messages"]
    type_and_send(browser, "Add the lunch menu")                         # a line written in a division goes to its team's Identity
    browser.wait_for("document.querySelector('.nbox').value === ''")
    assert [p["body"] for p in posts(fake, DIVISION_MENU)] == [{"text": "Add the lunch menu"}]
    # the link shows the whole team's chat, and the lens can be put back
    browser.click(".nlens button")
    browser.wait_for("document.querySelector('.nlens button').textContent.startsWith('Show only the work for') && document.querySelectorAll('.nmsg').length === 3")
    assert texts(browser, ".nlenstext") == ["Everything for Content."] and visible(browser, ".ncomposer")
    assert texts(browser, ".nmsg.me") == ["Write the menu page copy", "Add the lunch menu"]          # the line written in the division went to the team
    type_and_send(browser, "How is the Content team doing?")
    browser.wait_for("document.querySelector('.nbox').value === ''")
    assert [p["body"] for p in posts(fake, CONTENT_SESSION)] == [{"text": "How is the Content team doing?"}]
    browser.wait_for("document.querySelectorAll('.nmsg.me').length === 3")
    browser.click(".nlens button")
    browser.wait_for("document.querySelector('.nlenstext').textContent.startsWith('Menu is part of')")
    assert texts(browser, ".nmsg.me") == ["Write the menu page copy"]
    no_errors(browser)


@pytest.mark.browser
def test_a_divisions_details_list_the_five_functions_of_its_team_and_each_opens_its_panel(browser, fake):
    load(browser, fake, stage="full")
    open_node(browser, "menu", "details")
    assert texts(browser, ".fnfuncs h4") == ["Functions of Content"]
    assert attrs(browser, ".fnfuncs [data-fn]", "data-fn") == list(FUNCTIONS)
    assert attrs(browser, ".fnfuncs [data-fn]", "data-node") == [f"content.{fn}" for fn in FUNCTIONS]
    assert count(browser, ".fnsec[data-sec=goal]") == 0 and count(browser, ".atomcard") == 0 and texts(browser, ".fnpart") == ["Menu is a division of Content."]
    browser.click(".fnfuncs [data-fn=adaptation]")
    browser.wait_for("document.querySelector('#nptitle').textContent === 'Adaptation' && !!document.querySelector('.fnsec[data-sec=goal]')")
    assert texts(browser, ".fnsec[data-sec=goal] p")[0].startswith("Read the current state")
    assert attrs(browser, ".nptabs [aria-selected=true]", "data-nptab") == ["details"]
    no_errors(browser)


# ======================================================================================================================
# the Details tab: the function drawer
# ======================================================================================================================
@pytest.mark.browser
def test_the_function_drawer_has_the_sections_the_legend_and_the_five_atom_states(browser, fake):
    load(browser, fake)
    open_node(browser, "web.identity", "details")
    assert attrs(browser, ".fndetail > .fnsec", "data-sec") == ["head", "goal", "task", "context", "atoms", "constraints", "hands"]
    assert texts(browser, ".fncounts") == ["16 calls, 52 s, 1 atom open, 1 closed, 1 failed"]
    assert texts(browser, ".fnsec[data-sec=head] .fnusage") == [f"16 calls {DOT} $0.56 {DOT} 9,600 in / 2,880 out tokens"]
    assert texts(browser, ".atomlegend") == ["open > work > verify, close; exits: refuse, abandon"]
    assert texts(browser, ".fnsec[data-sec=atoms] h4") == ["Work atoms (5)"]
    assert texts(browser, ".fnsec[data-sec=task] .fnwork") == ["Working for: Coffee shop landing page (waiting for you)"]
    assert attrs(browser, "details.atomcard", "data-state") == ["open", "abandoned", "verify_failed", "closed", "refused"]
    assert texts(browser, ".astate") == ["OPEN", "ABANDONED", "VERIFY FAILED", "CLOSED", "REFUSED"]
    # the open atom is unfolded, the others are folded until the owner opens them
    assert browser.js("Array.from(document.querySelectorAll('details.atomcard'), d => d.open)") == [True, False, False, False, False]
    browser.click("details.atomcard[data-state=verify_failed] summary")
    assert texts(browser, "details.atomcard[data-state=verify_failed] .try-failed")[-1] == "attempt 2: failed, Charter rejected: fewer than 3 'done when' criteria."
    assert texts(browser, "details.atomcard[data-state=closed] .aconcern")[0].startswith("Concern on record RECOVERED:")
    assert "Limits" not in browser.js("document.querySelector('.npbody').textContent")
    assert attrs(browser, "details.atomcard[data-state=open] .ablock", "data-block") == ["goal", "constraints", "context", "how", "expected_output", "verification", "result"]
    assert visible(browser, "details.atomcard[data-state=open] .ablock[data-block=verification]")
    assert texts(browser, ".fnsec[data-sec=hands] .fnto .fnchip") == ["Strategist Adaptation", "Prioritiser Priority", "Scheduler Coordination", "Quality Reviewer Audit"]
    # a chip of "Hands to" opens that function's panel
    browser.click(".fnto [data-fn=priority]")
    browser.wait_for("document.querySelector('#nptitle').textContent === 'Priority' && !!document.querySelector('.fnsec[data-sec=head]')")
    assert texts(browser, ".fnsec[data-sec=head] .fntitle") == [f"Prioritiser {DOT} Priority"] and is_open(browser)
    no_errors(browser)


def result_rows(browser, state):
    """The class names of the children of the Result block of the atom card in this state, in the order they are drawn."""
    return browser.js(f"Array.from(document.querySelector('details.atomcard[data-state={state}] .ablock[data-block=result] > div').children, e => e.tagName.toLowerCase() + '.' + e.className.split(' ').join('.'))")


@pytest.mark.browser
def test_the_result_of_an_atom_shows_what_it_produced_and_the_reply_the_model_gave_behind_a_fold(browser, fake, screens_dir):
    """D157: the owner can see what an atom made. A closed atom shows its output, a failed atom shows the reply that failed (here a charter with two
    done-when items, which is why the check said fewer than 3), an atom stored before the layer recorded it says so, and a refused one never ran."""
    load(browser, fake)
    open_node(browser, "web.identity", "details")
    present(browser, "details.atomcard")
    for state in ("verify_failed", "closed", "abandoned", "refused"):
        browser.click(f"details.atomcard[data-state={state}] summary")
    # the open atom (unfolded): what its last failed try said, and its reply behind a closed fold
    assert texts(browser, "details.atomcard[data-state=open] .aoutput li") == ["said: I need one more answer."]
    assert browser.js("document.querySelector('details.atomcard[data-state=open] details.areply').open") is False
    # a closed atom shows what the turn made
    assert texts(browser, "details.atomcard[data-state=closed] .aoutput b") == ["Output"]
    assert texts(browser, "details.atomcard[data-state=closed] .aoutput li") == ["read your answer: carry on", "posted 1 message to you"]
    # a failed atom: the output, the reply behind the fold, then the Reason (in that order); the fold opens to the text as it was printed
    assert result_rows(browser, "verify_failed") == ["span.apill.st-verify_failed", "div.arow.aoutput", "details.areply", "div.arow.areason", "div.arow.acost"]
    assert texts(browser, "details.atomcard[data-state=verify_failed] .aoutput li") == ["the charter: Coffee shop landing page, 2 done-when items", "posted 1 message to Adaptation"]
    assert texts(browser, "details.atomcard[data-state=verify_failed] .areply summary") == ["The reply"]
    fold = "document.querySelector('details.atomcard[data-state=verify_failed] details.areply')"
    assert browser.js(f"{fold}.open") is False
    browser.click("details.atomcard[data-state=verify_failed] .areply summary")
    assert browser.js(f"{fold}.open") is True and browser.js(f"{fold}.querySelector('.areplytext').getBoundingClientRect().height") > 40
    reply = browser.js("document.querySelector('details.atomcard[data-state=verify_failed] .areplytext').textContent")
    assert json.loads(reply)["goal"]["done_when"] == ["The menu is on the page", "Opening hours are shown"] and reply.startswith("{\n  ")
    assert browser.js("getComputedStyle(document.querySelector('details.atomcard[data-state=verify_failed] .areplytext')).whiteSpace") == "pre-wrap"
    assert texts(browser, "details.atomcard[data-state=verify_failed] .areason") == ["Reason verify failed: charter-stamp: Charter rejected: fewer than 3 'done when' criteria."]
    # an atom stored before the layer recorded anything says so; a refused atom has no Output row at all
    assert texts(browser, "details.atomcard[data-state=abandoned] .aoutput") == ["Output not recorded for this atom"]
    assert count(browser, "details.atomcard[data-state=abandoned] .areply") == 0
    assert count(browser, "details.atomcard[data-state=refused] .aoutput") == 0 and count(browser, "details.atomcard[data-state=refused] .areply") == 0
    # the fold the owner opened stays open when the drawer is drawn again (an atom event refetches the node's detail)
    before = len(gets(fake, "/api/graph/nodes/web.identity"))
    fake.emit("atom.updated")
    wait_until(lambda: len(gets(fake, "/api/graph/nodes/web.identity")) > before, "the drawer refetched its node")
    time.sleep(0.3)
    assert browser.js("document.querySelector('details.atomcard[data-state=verify_failed] details.areply').open") is True
    browser.shot(screens_dir / "atom-output.png")
    no_errors(browser)


@pytest.mark.browser
def test_an_atom_that_closes_shows_the_output_and_reply_of_its_last_try_in_place_of_a_failed_one(browser, fake):
    load(browser, fake)
    open_node(browser, "web.identity", "details")
    present(browser, "details.atomcard")
    assert texts(browser, "details.atomcard[data-state=open] .aoutput li") == ["said: I need one more answer."]
    fake.stage("3")                                                            # the owner answered: the third try passes and the atom closes
    fake.emit("atom.updated")
    browser.wait_for("document.querySelector('details.atomcard').getAttribute('data-state') === 'closed'")
    assert texts(browser, "details.atomcard:first-of-type .aoutput li") == ["the charter: Coffee shop landing page, 4 done-when items", "posted 1 message to Adaptation"]
    browser.click("details.atomcard:first-of-type .areply summary")
    assert len(json.loads(browser.js("document.querySelector('details.atomcard .areplytext').textContent"))["goal"]["done_when"]) == 4
    no_errors(browser)


@pytest.mark.browser
def test_the_tabs_switch_without_losing_the_node(browser, fake):
    load(browser, fake)
    open_node(browser, "web.identity")
    assert attrs(browser, ".nptabs [aria-selected=true]", "data-nptab") == ["chat"]
    browser.click("[data-nptab=details]")
    present(browser, ".fndetail .atomcard")
    assert attrs(browser, ".nptabs [aria-selected=true]", "data-nptab") == ["details"] and count(browser, ".nchat") == 0
    browser.click(".fnchat")                                                  # the Chat button of the head
    present(browser, ".nchat .nmsg")
    assert attrs(browser, ".nptabs [aria-selected=true]", "data-nptab") == ["chat"] and count(browser, ".nmsg") == 2 and count(browser, ".fndetail") == 0
    browser.js("document.querySelector('[data-nptab=chat]').dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowRight', bubbles: true}))")
    present(browser, ".fndetail")
    browser.js("document.querySelector('[data-nptab=details]').dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowLeft', bubbles: true}))")
    present(browser, ".nchat")
    no_errors(browser)


@pytest.mark.browser
def test_on_the_department_page_the_drawer_has_go_to_tab_and_j2s_block_and_home_has_neither(browser, fake):
    load(browser, fake, dept="web")
    browser.js("""window.shown = []; window.showTab = function (name) { window.shown.push(name); };
                  window.renderAgent = function (v) { return '<div class="adhead">hidden head</div><section class="adsec"><h4>Summary</h4><div>' + v.summary.calls + ' AI calls</div></section>'; };""")
    open_node(browser, "web.identity", "details")
    present(browser, ".fnagent .adsec")
    assert texts(browser, ".fngo") == ["Go to the Identity tab"] and attrs(browser, ".fngo", "data-tab") == ["charter"]
    assert texts(browser, ".fnagent h4") == ["Summary"] and hidden(browser, ".fnagent .adhead")
    assert [r["query"] for r in fake.log("/api/agent")] == ["who=identity&dept=web"]
    assert count(browser, ".fnfull") == 0
    browser.click("[data-nptab=chat]")                                        # back and forth: the block is not fetched again
    browser.click("[data-nptab=details]")
    present(browser, ".fnagent .adsec")
    assert len(fake.log("/api/agent")) == 1
    browser.click(".fngo")
    assert browser.js("window.shown") == ["charter"] and not is_open(browser)
    for fn, tab in {"adaptation": "workflows", "priority": "conflicts", "coordination": "timeline", "audit": "audit"}.items():
        open_node(browser, f"web.{fn}", "details")
        assert attrs(browser, ".fngo", "data-tab") == [tab] and texts(browser, ".fngo") == [f"Go to the {fn.capitalize()} tab"], fn
    no_errors(browser)
    # Home: no button, no block, a line that sends the owner to the team page
    load(browser, fake)
    open_node(browser, "web.identity", "details")
    assert count(browser, ".fngo") == 0 and count(browser, ".fnagent") == 0
    assert texts(browser, ".fnfull") == ["Full conversations and thinking: open the team page."]
    browser.click(".fnfull button")
    assert browser.js("window.navigated") == "/d/web/?view=detail"
    no_errors(browser)


@pytest.mark.browser
def test_without_showtab_the_go_to_tab_button_clicks_the_rail(browser, fake):
    load(browser, fake, dept="web")
    browser.js("""const nav = document.createElement('nav'); nav.className = 'tabs'; nav.innerHTML = '<button role="tab" data-tab="charter">Charter</button>';
                  document.body.append(nav); window.railClicks = 0; nav.firstChild.addEventListener('click', () => window.railClicks++);""")
    open_node(browser, "web.identity", "details")
    browser.click(".fngo")
    assert browser.js("window.railClicks") == 1 and not is_open(browser)
    no_errors(browser)


@pytest.mark.browser
def test_the_agent_chips_of_the_map_reach_the_panel_through_wants_and_open_function(browser, fake):
    load(browser, fake, dept="web")
    assert browser.js("NodePanel.wants('identity')") is True and browser.js("NodePanel.wants('W-1')") is False
    assert browser.js("NodePanel.wants('')") is False and browser.js("NodePanel.wants(null)") is False
    browser.js("NodePanel.openFunction('audit')")
    browser.wait_for("document.querySelector('#nptitle') && document.querySelector('#nptitle').textContent === 'Audit'")
    assert attrs(browser, ".nptabs [aria-selected=true]", "data-nptab") == ["details"]       # the Agent drawer's place is the Details tab
    browser.js("NodePanel.openFunction('identity', 'chat')")
    browser.wait_for("document.querySelector('#nptitle').textContent === 'Identity' && document.querySelectorAll('.nmsg').length === 2")
    browser.js("NodePanel.openFunction('nobody')")
    assert texts(browser, "#nptitle") == ["Identity"]
    assert browser.js("NodePanel.close()") is True and browser.js("NodePanel.isOpen()") is False and browser.js("NodePanel.close()") is False
    # the overview graph holds no function nodes: the team's own record names them
    browser.js("window.graph = {version: 1, chart_version: 1, nodes: window.graph.nodes.filter(n => n.kind !== 'function'), edges: []}")
    browser.js("NodePanel.openFunction('coordination')")
    browser.wait_for("document.querySelector('#nptitle') && document.querySelector('#nptitle').textContent === 'Coordination'")
    assert len(gets(fake, "/api/departments/web")) == 1
    # a panel that has been taken down wants nothing, and the static calls do nothing
    browser.js("window.panel.destroy()")
    assert browser.js("NodePanel.wants('identity')") is False and browser.js("NodePanel.open('web.identity')") is None
    assert browser.js("NodePanel.openFunction('identity')") is None and browser.js("NodePanel.isOpen()") is False
    no_errors(browser)


# ======================================================================================================================
# one drawer at a time, Esc, focus
# ======================================================================================================================
@pytest.mark.browser
def test_esc_closes_the_panel_and_the_focus_goes_back_to_the_node_that_opened_it(browser, fake):
    load(browser, fake)
    browser.js("""const b = document.createElement('button'); b.id = 'opener'; b.setAttribute('data-id', 'web.identity'); b.textContent = 'Identity'; document.body.prepend(b);
                  b.addEventListener('click', () => window.openNode('web.identity', 'chat'));""")
    browser.click("#opener")
    browser.wait_for("window.panel.isOpen() && document.querySelectorAll('.nmsg').length === 2")
    assert browser.js("document.activeElement.hasAttribute('data-npclose')") is True
    browser.press("Escape")
    assert not is_open(browser) and browser.js("document.body.classList.contains('nodeopen')") is False
    assert browser.js("document.getElementById('nodepanel').hidden") is True and browser.js("document.activeElement.id") == "opener"
    assert hidden(browser, "#nodepanel") and browser.js("document.querySelector('.npbody').innerHTML") == ""
    # the picture was redrawn while the panel was open: the focus finds the node again by its id
    browser.click("#opener")
    browser.wait_for("window.panel.isOpen()")
    browser.js("document.getElementById('opener').replaceWith(Object.assign(document.createElement('button'), {id: 'opener2', tabIndex: 0}))")
    browser.js("document.getElementById('opener2').setAttribute('data-id', 'web.identity')")
    browser.click("[data-npclose]")
    assert not is_open(browser) and browser.js("document.activeElement.id") == "opener2"
    no_errors(browser)


@pytest.mark.browser
def test_opening_the_panel_closes_j2s_agent_drawer_and_opening_that_closes_the_panel(browser, fake):
    load(browser, fake)
    browser.js("""const d = document.createElement('aside'); d.id = 'agentdrawer'; d.className = 'agentdrawer'; d.textContent = 'agent'; document.body.append(d);
                  window.closeAgent = () => { d.hidden = true; document.body.classList.remove('agentopen'); window.agentClosed = (window.agentClosed || 0) + 1; };
                  document.body.classList.add('agentopen');""")
    open_node(browser, "web.adaptation")
    assert browser.js("window.agentClosed") == 1 and browser.js("document.body.classList.contains('agentopen')") is False
    assert is_open(browser)
    browser.js("document.body.classList.add('agentopen')")                     # J2's openAgent for a builder
    browser.wait_for("!window.panel.isOpen()")
    assert browser.js("document.body.classList.contains('nodeopen')") is False
    # without J2's closeAgent the panel closes the drawer itself
    browser.js("delete window.closeAgent; document.body.classList.add('agentopen'); document.getElementById('agentdrawer').hidden = false")
    open_node(browser, "web.priority")
    assert browser.js("document.getElementById('agentdrawer').hidden") is True and browser.js("document.body.classList.contains('agentopen')") is False
    no_errors(browser)


@pytest.mark.browser
def test_opening_another_node_keeps_one_panel_and_a_closed_panel_stops_listening(browser, fake):
    load(browser, fake)
    open_node(browser, "web.identity")
    fake.wait_subscribers(2)
    open_node(browser, "web.adaptation")
    assert texts(browser, "#nptitle") == ["Adaptation"] and count(browser, "#nodepanel") == 1
    wait_until(lambda: fake.state()["subscribers"] == 2, "the old stream is gone and the new one is open")
    browser.js("window.panel.close()")
    wait_until(lambda: fake.state()["subscribers"] == 1, "only the mount page's own stream is left")
    no_errors(browser)


# ======================================================================================================================
# what goes wrong
# ======================================================================================================================
@pytest.mark.browser
def test_a_refusal_from_the_server_hides_the_box_or_closes_it_or_says_the_chat_is_gone(browser, fake):
    load(browser, fake)
    path = f"/api/chats/{DEPT_SESSION}/messages"
    open_node(browser, "web.identity")
    browser.expect_failed(path)                                                # every refusal below is on purpose
    fake.fail(path, 403, method="POST", count=1)                               # 403 read_only: the box goes away
    type_and_send(browser, "one")
    browser.wait_for("document.querySelector('.ncomposer').hidden === true")
    assert texts(browser, ".nnote") == ["This chat is read-only."]
    open_node(browser, "web.identity")
    assert browser.js("document.querySelector('.nbox').value") == "one"      # a refused line is the chat's draft: it comes back (GAP-chat-comfort)
    clear_box(browser)
    fake.fail(path, 401, method="POST", count=1)                               # 401 bad_token: shown, closed, with the reload sentence
    type_and_send(browser, "two")
    browser.wait_for("!document.querySelector('.nbanner').hidden")
    assert browser.js("document.querySelector('.nbox').disabled") is True
    assert texts(browser, ".nbanner") == [NO_TOKEN] and texts(browser, ".nnote") == [NO_TOKEN] and visible(browser, ".ncomposer")
    assert browser.js("document.querySelector('.nbox').value") == "two"
    open_node(browser, "web.identity")
    assert browser.js("document.querySelector('.nbox').value") == "two"
    clear_box(browser)
    fake.fail(path, 404, method="POST", count=1)                               # 404: the chat is gone, with a Close button
    type_and_send(browser, "three")
    browser.wait_for("!document.querySelector('.nbanner').hidden")
    assert texts(browser, ".nbanner") == ["This chat is gone. Close"]
    browser.click(".nbanner [data-npclose]")
    assert not is_open(browser)
    open_node(browser, "web.identity")
    assert browser.js("document.querySelector('.nbox').value") == "three"
    clear_box(browser)
    fake.fail(path, 429, method="POST", count=1)
    type_and_send(browser, "four")
    browser.wait_for("!document.querySelector('.nbanner').hidden")
    assert texts(browser, ".nbanner") == ["Too many messages are waiting. I answer them one at a time."]
    fake.fail(path, 422, method="POST", count=1, message="Text is too long.")
    browser.click(".ncomposer .send")
    browser.wait_for("document.querySelector('.nbanner').textContent === 'Text is too long.'")
    fake.fail(path, 500, method="POST", count=1)
    browser.click(".ncomposer .send")
    browser.wait_for("document.querySelector('.nbanner').textContent === 'Something went wrong. Try again.'")
    assert browser.js("document.querySelector('.nbox').value") == "four" and posts(fake, DEPT_SESSION)
    no_errors(browser, network=True)


@pytest.mark.browser
def test_a_node_or_a_chat_the_server_does_not_have_says_so(browser, fake):
    load(browser, fake)
    browser.expect_failed("/api/")
    open_node(browser, "nobody")
    assert texts(browser, ".nempty") == ["This node is gone."] and visible(browser, "[data-npclose]")
    fake.fail(f"/api/chats/{DEPT_SESSION}", 404)
    open_node(browser, "web.identity")
    assert texts(browser, ".nempty") == ["This chat is gone."] and hidden(browser, ".ncomposer")
    fake.fail(f"/api/chats/{DEPT_SESSION}", None)
    fake.fail(f"/api/chats/{DEPT_SESSION}/messages", 500)
    open_node(browser, "web.identity")
    assert texts(browser, ".nbanner") == ["Something went wrong. Try again. Try again"]
    fake.fail(f"/api/chats/{DEPT_SESSION}/messages", None)
    browser.click("[data-act=retry-load]")
    browser.wait_for("document.querySelectorAll('.nmsg').length === 2")
    assert browser.js("document.querySelector('.nbanner').hidden") is True
    # a node with no chat at all
    browser.js("window.graph.nodes.find(n => n.id === 'web.audit').chat_session_id = null")
    open_node(browser, "web.audit")
    assert texts(browser, ".nempty") == ["This node has no chat."]
    browser.click("[data-nptab=details]")
    present(browser, ".fndetail .fnsec")
    no_errors(browser, network=True)


# ======================================================================================================================
# staying current
# ======================================================================================================================
@pytest.mark.browser
def test_a_new_message_is_fetched_after_the_last_one_and_a_burst_costs_one_request(browser, fake):
    load(browser, fake)
    open_node(browser, "web.identity")
    fake.wait_subscribers(2)
    messages = f"/api/chats/{DEPT_SESSION}/messages"
    assert [r["query"] for r in gets(fake, messages)] == ["after=0&limit=200"]
    fake.emit("chat.message", chat_message(DEPT_SESSION, 20, "News 1"))
    browser.wait_for("document.querySelectorAll('.nmsg').length === 3")
    assert [r["query"] for r in gets(fake, messages)][-1] == "after=2&limit=200" and len(gets(fake, messages)) == 2
    before = len(gets(fake, messages))
    for n in range(21, 25):                                                    # four in a burst: one request (two at the most), all four shown
        fake.emit("chat.message", chat_message(DEPT_SESSION, n, f"News {n}"))
    browser.wait_for("document.querySelectorAll('.nmsg').length === 7")
    assert len(gets(fake, messages)) - before <= 2 and texts(browser, ".nmsg:last-child")[0].endswith("News 24")
    seen = len(gets(fake, messages))
    fake.emit("chat.message", chat_message("cs_org", 99, "elsewhere", who="sutra"))      # another session: nothing is fetched
    time.sleep(0.5)
    assert len(gets(fake, messages)) == seen and "elsewhere" not in browser.js("document.querySelector('.nmsgs').textContent")
    assert browser.js("localStorage.getItem('sutra:seen:%s')" % DEPT_SESSION) == "24"
    no_errors(browser)


@pytest.mark.browser
def test_the_panel_scrolls_to_the_newest_line_only_when_the_owner_is_at_the_bottom(browser, fake):
    load(browser, fake)
    open_node(browser, "web.identity")
    fake.wait_subscribers(2)
    for n in range(20, 50):
        fake.emit("chat.message", chat_message(DEPT_SESSION, n, f"Line {n} " + "text " * 20))
    browser.wait_for("document.querySelectorAll('.nmsg').length >= 20")
    wait_until(lambda: texts(browser, ".nmsg:last-child")[0].count("Line 49"), "the last line arrived")
    assert browser.js("(() => { const m = document.querySelector('.nmsgs'); return m.scrollHeight - m.scrollTop - m.clientHeight < 4; })()") is True
    browser.js("document.querySelector('.nmsgs').scrollTop = 0")
    fake.emit("chat.message", chat_message(DEPT_SESSION, 50, "Line 50"))
    browser.wait_for("document.querySelector('.nmsg:last-child').textContent.includes('Line 50')")
    assert browser.js("document.querySelector('.nmsgs').scrollTop") < 40                 # still where the owner was reading
    no_errors(browser)


@pytest.mark.browser
def test_an_atom_update_of_the_open_node_refetches_its_detail_and_one_of_another_node_does_not(browser, fake):
    load(browser, fake)
    open_node(browser, "web.identity", "details")
    fake.wait_subscribers(2)
    path = "/api/graph/nodes/web.identity"
    assert len(gets(fake, path)) == 1
    assert attrs(browser, "details.atomcard", "data-state")[0] == "open" and texts(browser, ".fnsec[data-sec=head] .nstatus") == ["waiting on you"]
    other = {"atom_id": "a-x", "node_id": "web.adaptation", "outcome": "closed", "state": "closed", "atom": {"id": "a-x", "node_id": "web.adaptation", "state": "closed"}}
    fake.emit("atom.updated", other)
    time.sleep(0.5)
    assert len(gets(fake, path)) == 1
    fake.stage("3")                                                            # the owner answered: the open atom closes and Identity is idle
    fake.emit("atom.updated")
    browser.wait_for("document.querySelector('details.atomcard').getAttribute('data-state') === 'closed'")
    assert len(gets(fake, path)) == 2
    assert texts(browser, ".fnsec[data-sec=head] .nstatus") == ["idle"] and texts(browser, ".nphead .nstatus") == ["idle"]
    assert texts(browser, "details.atomcard summary .aattempt")[0] == "attempt 3 of 3"
    no_errors(browser)


@pytest.mark.browser
def test_a_task_update_or_a_graph_update_that_names_the_node_refetches_the_detail_and_another_does_not(browser, fake):
    load(browser, fake)
    open_node(browser, "web.identity", "details")
    fake.wait_subscribers(2)
    path = "/api/graph/nodes/web.identity"
    fake.emit("graph.updated", {"version": 50, "nodes": [{"id": "s-3f9a1c2b7d", "kind": "step", "label": "x", "status": "running"}], "edges_added": 0, "edges_removed": 0})
    time.sleep(0.5)
    assert len(gets(fake, path)) == 1
    fake.emit("graph.updated", {"version": 51, "nodes": [{"id": "web.identity", "kind": "function", "label": "Identity", "status": "idle"}], "edges_added": 0, "edges_removed": 0})
    wait_until(lambda: len(gets(fake, path)) == 2, "a graph update that names the node")
    fake.emit("graph.updated", {"version": 52, "nodes": [{"id": "web", "kind": "department", "label": "Web", "status": "running"}], "edges_added": 0, "edges_removed": 0})
    wait_until(lambda: len(gets(fake, path)) == 3, "a graph update that names the node's team")
    fake.emit("task.updated")
    wait_until(lambda: len(gets(fake, path)) == 4, "a task update")
    fake.emit("needs_you.changed")
    wait_until(lambda: len(gets(fake, path)) == 5, "a change in what needs the owner")
    no_errors(browser)


@pytest.mark.browser
def test_when_the_stream_drops_the_panel_polls_its_two_calls(browser, fake):
    load(browser, fake)
    open_node(browser, "web.identity")
    fake.wait_subscribers(2)
    browser.js("window.panel.destroy(); window.panel = NodePanel.mount(document.getElementById('nodepanel'), {getGraph: () => window.graph, navigate: () => {}, pollMs: 150});")
    open_node(browser, "web.identity")
    fake.wait_subscribers(2)
    messages = f"/api/chats/{DEPT_SESSION}/messages"
    before = len(gets(fake, messages))
    browser.expect_failed("/api/events")
    fake.fail("/api/events", 500)
    fake.emit("chat.message", chat_message(DEPT_SESSION, 31, "Polled in"))          # stored by the fake; no stream is left to announce it
    browser.wait_for("document.querySelectorAll('.nmsg').length === 3", timeout=30)
    assert len(gets(fake, messages)) > before and "Polled in" in browser.js("document.querySelector('.nmsgs').textContent")
    assert len(gets(fake, "/api/graph/nodes/web.identity")) >= 2
    fake.fail("/api/events", None)
    no_errors(browser, network=True)


@pytest.mark.browser
def test_show_all_asks_for_the_atoms_in_pages_of_a_hundred(browser, fake):
    load(browser, fake)
    # the server "holds" 30 atoms and the page of the fake is cut to 3, so that each page can be seen to have arrived
    browser.js("""const orig = window.fetch.bind(window);
                  const json = (body, r) => new Response(JSON.stringify(body), {status: r.status, headers: {'Content-Type': 'application/json'}});
                  window.fetch = (url, init) => orig(url, init).then(async r => {
                    if (String(url).includes('/api/graph/nodes/web.identity')) { const body = await r.json(); body.node.meta.stats.atoms_total = 30; return json(body, r); }
                    if (String(url).includes('/api/atoms')) { return json((await r.json()).slice(0, 3), r); }
                    return r; });""")
    open_node(browser, "web.identity", "details")
    assert texts(browser, ".fnsec[data-sec=atoms] h4") == ["Work atoms (30)"] and texts(browser, ".fnmore") == ["Show all (30)"]
    assert count(browser, "details.atomcard") == 5
    browser.click(".fnmore")
    browser.wait_for("document.querySelectorAll('details.atomcard').length === 3")
    assert fake.log("/api/atoms")[0]["query"] == "node_id=web.identity&limit=100&offset=0"
    assert browser.js("Array.from(document.querySelectorAll('details.atomcard'), d => d.getAttribute('data-atom'))") == [
        "a-a810960e61-05", "a-a810960e61-04", "a-a810960e61-03"]                       # open first, then the newest
    browser.click(".fnmore")                                                   # 3 are in view and the server holds 30: the next page starts after them
    browser.wait_for("document.querySelectorAll('details.atomcard').length === 5")
    assert fake.log("/api/atoms")[1]["query"] == "node_id=web.identity&limit=100&offset=3" and len(fake.log("/api/atoms")) == 2
    assert texts(browser, ".fnmore") == ["Show all (30)"]
    no_errors(browser)


@pytest.mark.browser
def test_earlier_chats_of_a_node_open_read_only_with_their_note_and_the_owner_can_go_back(browser, fake):
    load(browser, fake, stage="full")
    browser.js("""const orig = window.fetch.bind(window);
                  window.fetch = (url, init) => orig(url, init).then(async r => {
                    if (String(url).includes('/api/graph/nodes/menu')) {
                      const body = await r.json();
                      body.archived_chats = [{id: 'cs_fa9fa9fa9fa9', node_id: 'faq', kind: 'division', title: 'FAQ', writable: false, status: 'archived', filed_under: 'menu',
                                              connector: null, model: null, provider_session_id: null, last_message_id: 0, note: 'Merged into Menu'}];
                      return new Response(JSON.stringify(body), {status: r.status, headers: {'Content-Type': 'application/json'}});
                    }
                    return r; });""")
    open_node(browser, "menu")
    assert texts(browser, ".nearlier summary") == ["Earlier chats (1)"]
    browser.click(".nearlier summary")
    assert texts(browser, ".nearlier li") == ["FAQ · Merged into Menu"]
    browser.click(".nearlier [data-act=earlier]")
    present(browser, ".nlens-archived")
    assert browser.js("document.querySelector('.ncomposer').hidden") is True and texts(browser, ".nnote") == ["Merged into Menu"]
    assert texts(browser, ".npnote") == ["Merged into Menu"] and browser.js("document.querySelector('.nearlier').hidden") is True
    assert count(browser, ".nmsg .opts") == 0
    before = len([r for r in fake.log("/api/chats/") if r["method"] == "POST"])
    browser.click(".nlens-archived [data-act=back]")
    absent(browser, ".nlens-archived")
    assert visible(browser, ".ncomposer") and hidden(browser, ".npnote") and len([r for r in fake.log("/api/chats/") if r["method"] == "POST"]) == before
    no_errors(browser)


# ======================================================================================================================
# the look
# ======================================================================================================================
@pytest.mark.browser
def test_on_a_phone_the_panel_fills_the_screen_and_nothing_scrolls_sideways(browser, fake):
    browser.set_size(390, 800)
    load(browser, fake)
    open_node(browser, "web.identity")
    assert browser.js("Math.round(document.getElementById('nodepanel').getBoundingClientRect().width)") == 390
    assert browser.js("document.documentElement.scrollWidth <= innerWidth") is True
    assert visible(browser, ".ncomposer") and browser.js("document.getElementById('nodepanel').scrollWidth <= document.getElementById('nodepanel').clientWidth") is True
    browser.click("[data-nptab=details]")
    present(browser, ".fndetail .atomcard")
    assert browser.js("document.getElementById('nodepanel').scrollWidth <= document.getElementById('nodepanel').clientWidth") is True
    no_errors(browser)


@pytest.mark.browser
def test_the_panel_reads_in_both_themes_and_keeps_its_markup_inside_the_drawer(browser, fake, screens_dir):
    panel_background = {}
    for theme in ("dark", "light"):
        load(browser, fake)
        browser.js(f"document.documentElement.setAttribute('data-theme', {q(theme)})")         # what J2's first-paint script does with the saved choice
        open_node(browser, "web.identity", "details")
        browser.shot(screens_dir / f"panel-details-{theme}.png")
        browser.click("[data-nptab=chat]")
        present(browser, ".nchat .nmsg")
        browser.shot(screens_dir / f"panel-chat-{theme}.png")
        assert browser.js("getComputedStyle(document.querySelector('.nmsg.team small')).color") != browser.js("getComputedStyle(document.getElementById('nodepanel')).backgroundColor")
        panel_background[theme] = browser.js("getComputedStyle(document.getElementById('nodepanel')).backgroundColor")
    assert panel_background["dark"] != panel_background["light"]
    assert browser.js("Array.from(document.querySelectorAll('body > *')).filter(e => e.id !== 'nodepanel' && e.tagName !== 'SCRIPT' && e.className.toString().match(/\\b(fn|nmsg|ncard|atom)/)).length") == 0
    no_errors(browser)


# ======================================================================================================================
# the comfort of a chat (GAP-chat-comfort): the box keeps its words, grows with them, and the reader is never pulled down
# ======================================================================================================================
DRAFT_KEY = f"sutra:draft:{DEPT_SESSION}"


def box_value(browser):
    return browser.js("document.querySelector('.nbox').value")


def from_bottom(browser):
    return browser.js("(() => { const m = document.querySelector('.nmsgs'); return m.scrollHeight - m.scrollTop - m.clientHeight; })()")


@pytest.mark.browser
def test_the_box_keeps_its_words_through_esc_a_tab_switch_and_a_reload_and_only_an_accepted_send_clears_them(browser, fake):
    load(browser, fake)
    open_node(browser, "web.identity")
    words = "Dear team,\nthe menu needs prices"
    browser.type(".nbox", words)
    browser.press("Escape")                                                    # nothing runs: Esc closes the panel, the words are kept
    assert not is_open(browser)
    open_node(browser, "web.identity")
    assert box_value(browser) == words
    browser.click("[data-nptab=details]")
    present(browser, ".fndetail .fnsec")
    browser.click("[data-nptab=chat]")
    present(browser, ".nchat .nbox")
    assert box_value(browser) == words
    browser.reload()
    browser.wait_for("window.mounted === true")
    open_node(browser, "web.identity")
    assert box_value(browser) == words
    open_node(browser, "web.adaptation")                                       # another chat has its own box (a read-only log: no box at all)
    open_node(browser, "web.identity")
    assert box_value(browser) == words
    browser.expect_failed(f"/api/chats/{DEPT_SESSION}/messages", 409)
    fake.fail(f"/api/chats/{DEPT_SESSION}/messages", 409, method="POST", count=1)
    browser.click(".ncomposer .send")                                          # refused: the draft stays
    browser.wait_for("!document.querySelector('.nbanner').hidden")
    assert browser.js(f"localStorage.getItem({q(DRAFT_KEY)}) !== null") is True
    browser.click(".ncomposer .send")                                          # accepted: the box and the draft are empty
    browser.wait_for("document.querySelector('.nbox').value === '' && document.querySelectorAll('.nmsg.me').length === 2")
    assert browser.js(f"localStorage.getItem({q(DRAFT_KEY)})") is None
    open_node(browser, "web.identity")
    assert box_value(browser) == ""
    no_errors(browser, network=True)


@pytest.mark.browser
def test_the_box_grows_with_its_text_up_to_a_ceiling_and_shrinks_back_after_a_send(browser, fake):
    load(browser, fake)
    open_node(browser, "web.identity")
    start = browser.js("document.querySelector('.nbox').getBoundingClientRect().height")
    assert 50 <= start <= 70
    browser.type(".nbox", "line\n" * 4)
    grown = browser.js("document.querySelector('.nbox').getBoundingClientRect().height")
    assert grown > start + 20
    browser.type(".nbox", "more\n" * 40)
    assert browser.js("Math.round(document.querySelector('.nbox').getBoundingClientRect().height)") <= 200
    assert browser.js("getComputedStyle(document.querySelector('.nbox')).overflowY") == "auto"
    browser.click(".ncomposer .send")
    browser.wait_for("document.querySelector('.nbox').value === ''")
    assert browser.js("document.querySelector('.nbox').getBoundingClientRect().height") <= start + 2
    no_errors(browser)


@pytest.mark.browser
def test_a_reader_who_scrolls_up_stays_put_a_pill_counts_the_new_lines_and_takes_them_to_the_newest(browser, fake):
    load(browser, fake)
    open_node(browser, "web.identity")
    fake.wait_subscribers(2)
    for n in range(20, 45):
        fake.emit("chat.message", chat_message(DEPT_SESSION, n, f"Line {n} " + "text " * 20))
    wait_until(lambda: "Line 44" in texts(browser, ".nmsg:last-child")[0], "the last line arrived")
    assert from_bottom(browser) < 4 and hidden(browser, ".cjump")                # following: nothing to jump to
    browser.js("document.querySelector('.nmsgs').dispatchEvent(new WheelEvent('wheel', {deltaY: -120, bubbles: true}))")
    browser.js("document.querySelector('.nmsgs').scrollTop = 200")
    time.sleep(0.2)
    fake.emit("chat.message", chat_message(DEPT_SESSION, 45, "Line 45"))
    fake.emit("chat.message", chat_message(DEPT_SESSION, 46, "Line 46"))
    browser.wait_for("document.querySelector('.nmsg:last-child').textContent.includes('Line 46')")
    browser.wait_for("!document.querySelector('.cjump').hidden")
    assert abs(browser.js("document.querySelector('.nmsgs').scrollTop") - 200) <= 2          # not pulled down
    assert texts(browser, ".cjump-btn") == ["2 new messages below"]
    browser.click(".cjump-btn")
    browser.wait_for("(() => { const m = document.querySelector('.nmsgs'); return m.scrollHeight - m.scrollTop - m.clientHeight < 4; })()")
    assert hidden(browser, ".cjump")
    fake.emit("chat.message", chat_message(DEPT_SESSION, 47, "Line 47"))                       # following again
    browser.wait_for("document.querySelector('.nmsg:last-child').textContent.includes('Line 47')")
    wait_until(lambda: from_bottom(browser) < 4, "the follower follows")
    no_errors(browser)


@pytest.mark.browser
def test_the_owners_own_line_goes_to_the_bottom_and_a_reopened_chat_comes_back_where_it_was_read(browser, fake):
    load(browser, fake, stage="full")                                          # Content is idle: a line is a follow-up, stored after the others
    open_node(browser, "content")
    fake.wait_subscribers(2)
    for n in range(100, 125):
        fake.emit("chat.message", chat_message(CONTENT_SESSION, n, f"Line {n} " + "text " * 20))
    wait_until(lambda: "Line 124" in texts(browser, ".nmsg:last-child")[0], "the last line arrived")
    browser.js("document.querySelector('.nmsgs').scrollTop = 300")
    time.sleep(0.2)
    browser.press("Escape")
    assert not is_open(browser)
    open_node(browser, "content")
    wait_until(lambda: abs(browser.js("document.querySelector('.nmsgs').scrollTop") - 300) <= 2, "the chat opened where it was read")
    browser.click("[data-nptab=details]")
    present(browser, ".fndetail .fnsec")
    browser.click("[data-nptab=chat]")
    present(browser, ".nchat .nmsg")
    wait_until(lambda: abs(browser.js("document.querySelector('.nmsgs').scrollTop") - 300) <= 2, "the chat tab came back where it was read")
    type_and_send(browser, "Prices, please")
    browser.wait_for("Array.from(document.querySelectorAll('.nmsg.me')).some(e => e.textContent.includes('Prices, please'))")
    wait_until(lambda: from_bottom(browser) < 4, "the owner's own line is in view")
    browser.press("Escape")
    open_node(browser, "content")                                              # closed at the bottom: opens at the bottom
    wait_until(lambda: from_bottom(browser) < 4, "a chat read to its end opens at its end")
    no_errors(browser)
