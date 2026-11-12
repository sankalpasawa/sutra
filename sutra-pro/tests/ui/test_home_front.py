"""Home's front door and the owner's level in a real browser (the one-front brief: front_door.js, SutraCtx.level, home.js setPlace).

Runs only with SUTRA_BROWSER=1, against the fake backend (stages as in test_home.py: "1" a new app, "2" the Web team asks about the menu).
What it proves:

  simple     the front door is the page: what needs you (the Web question as a card with its options), In progress, the box; no graph, org chart,
             settings or org chat on show
  answers    an option pressed on the card goes to the TEAM's session (never cs_org); an approval's Approve goes through the org chat as its button
  new        the box sends a new project to the org chat
  levels     Manager adds the org chart, the workflow graph and team chats (opening the workspace, with a way back), Debug adds Settings, Usage and
             log and the Raw AI chat hook; the choice is kept in localStorage sutra:level
  phone      390 px wide: no sideways scroll
"""
from __future__ import annotations

import json

import pytest

browser_only = pytest.mark.browser

DEPT_SESSION = "cs_5e0a77b19c3d"       # the Web team's chat


def q(css: str) -> str:
    return json.dumps(css)


def load(browser, fake, *, stage="2", level="simple", place="front"):
    browser.set_level(level, place)
    fake.stage(stage)
    browser.goto(fake.url + "/")
    browser.wait_for("window.HomePage && HomePage.state().loaded === true && HomePage.state().departmentsLoaded")
    fake.wait_subscribers(1)


def texts(browser, css):
    return browser.js(f"Array.from(document.querySelectorAll({q(css)}), e => e.textContent.trim().replace(/\\s+/g, ' '))")


def on_screen(browser, css) -> bool:
    return browser.js(f"(() => {{ const e = document.querySelector({q(css)}); if (!e) return false; const r = e.getBoundingClientRect(); "
                      f"return getComputedStyle(e).display !== 'none' && r.width > 0 && r.height > 0; }})()")


def posts(fake, prefix="/api/"):
    return [r for r in fake.log(prefix) if r["method"] in ("POST", "PUT", "DELETE")]


@browser_only
def test_simple_shows_only_the_front_door_with_the_question_first(browser, fake):
    load(browser, fake)
    assert browser.js("document.documentElement.dataset.level") == "simple"
    assert on_screen(browser, "#front") and on_screen(browser, "#fdbox")
    for hidden in ("#sview", "#dview", "#pane-graph", "#pane-chart", "#pane-settings", "#smsgs"):
        assert not on_screen(browser, hidden), hidden
    assert texts(browser, "#fdorgname") == ["Sutra"]                                   # no "org" at Simple
    assert texts(browser, "#fd-new-h") == ["What should we make?"]
    assert texts(browser, "#fdfaces .fdteam") == ["Asha, Mira, Kabir, Dev and Nora are ready."]
    assert texts(browser, "#fdneeds .fdcard .fdasker") == ["Asha needs one answer"]
    assert browser.js("document.getElementById('fdnav').hidden")                       # Simple adds no views
    assert texts(browser, "#fdneeds .fdcard .fdwho") == ["Web"]
    assert texts(browser, "#fdneeds .fdcard .fdq") == ["Should the menu show prices?"]
    assert texts(browser, "#fdneeds [data-act=fd-option]") == ["Yes, show the prices", "No, names only"]
    assert browser.js("document.querySelector('#fdneeds .fdopen').getAttribute('href')") == "/d/web/?view=simple"
    assert browser.console_errors == []


@browser_only
def test_an_option_on_the_card_answers_in_the_teams_own_chat(browser, fake):
    load(browser, fake)
    browser.click("#fdneeds [data-act=fd-option][data-opt='1']")
    browser.wait_for("HomePage.state().needs.length === 0")
    sent = posts(fake, "/api/chats/")
    assert [(r["path"], r["body"]) for r in sent] == [(f"/api/chats/{DEPT_SESSION}/messages", {"text": "Option 1"})]
    browser.wait_for("document.querySelector('#fdneeds .fdempty') !== null")
    assert "Nothing needs you right now" in texts(browser, "#fdneeds")[0]


@browser_only
def test_approve_presses_the_approval_cards_yes_through_the_org_chat(browser, fake):
    load(browser, fake, stage="1")
    browser.js("""(() => { const S = HomePage.state(); S.needs.push({message_id: 9, session_id: "cs_org", kind: "approval", dept_id: null, dept_name: "",
      text: "Add a Design team?", options: ["Yes", "No"], asked_at: "2026-11-04T10:05:00Z", waiting_s: 90}); HomePage.renderFront(); })()""")
    assert texts(browser, "#fdneeds .fdappr .fdq") == ["Add a Design team?"]
    assert texts(browser, "#fdneeds .fdappr button") == ["Approve", "Not now"]
    browser.click("#fdneeds [data-act=fd-approve]")
    browser.wait_for("HomePage.state().front.answering[9] === undefined && HomePage.state().answers[9] === 'Yes'")
    org = posts(fake, "/api/chats/cs_org/messages")
    assert org and org[0]["body"] == {"text": "Yes", "choice": {"message_id": 9, "option": "Yes"}}


@browser_only
def test_the_box_starts_a_new_project_through_the_org_chat(browser, fake):
    load(browser, fake, stage="1")
    browser.type("#fdbox", "A website for my cafe")
    browser.click("#fdsend")
    browser.wait_for("document.querySelector('#fdlatest .fdlatest') !== null")
    sent = posts(fake, "/api/chats/cs_org/messages")
    assert sent and sent[0]["body"] == {"text": "A website for my cafe"} and sent[0]["token"] is True
    browser.wait_for("document.getElementById('fdbox').value === ''")


@browser_only
def test_a_new_app_at_simple_shows_only_the_box_and_manager_reads_calm(browser, fake):
    load(browser, fake, stage="1")
    assert texts(browser, "#fdneeds") == [""] and texts(browser, "#fdlists") == [""]   # nothing made yet: the box is the one thing to do
    browser.click("#fdlevel [data-level=manager]")
    browser.wait_for("document.documentElement.dataset.level === 'manager'")
    assert texts(browser, "#fdneeds .fdempty b") == ["Nothing needs you right now"]


@browser_only
def test_simple_takes_the_owner_to_the_team_page_once_a_team_has_the_work(browser, fake):
    load(browser, fake, stage="1")
    browser.expect_failed("/d/web/")                                                   # the fake serves no team page at stage 1
    browser.js("""(() => { const S = HomePage.state(); S.front.sent = true;
      S.messages.push({id: 900, role: "user", text: "A website for my cafe"}, {id: 901, role: "agent", text: "", card: {type: "task", dept_id: "web", dept_name: "Web", title: "A website for my cafe"}});
      HomePage.renderFront(); })()""")
    assert texts(browser, "#fdlatest .fdwatch") == ["Watch it being built"]
    assert browser.js("document.querySelector('#fdlatest .fdwatch').getAttribute('href')") == "/d/web/?view=simple"
    assert not browser.exists("#fdlatest [data-act=fd-conversation]")                  # Simple never lands in the org chat
    browser.wait_for("location.pathname === '/d/web/'", timeout=10)


@browser_only
def test_simple_shows_sutras_question_as_a_card_on_the_front_door_in_plain_words(browser, fake):
    load(browser, fake, stage="1")
    browser.js("""(() => { const S = HomePage.state(); S.front.sent = true;
      S.messages.push({id: 900, role: "user", text: "Add booking"}, {id: 902, role: "agent", text: "", card: {type: "choice", question: "Which team fits best?",
        options: [{id: "web", label: "Web"}, {id: "none", label: "None of these"}]}});
      HomePage.renderFront(); })()""")
    assert texts(browser, "#fdlatest .fdq") == ["Is this for one of your projects, or something new?"]
    assert texts(browser, "#fdlatest [data-act=fd-choose]") == ["Web", "Something new"]
    browser.click("#fdlatest [data-act=fd-choose][data-option=none]")
    browser.wait_for("HomePage.state().answers[902] === 'None of these'")
    sent = posts(fake, "/api/chats/cs_org/messages")
    assert sent and sent[0]["body"] == {"text": "None of these", "choice": {"message_id": 902, "option": "none"}}


@browser_only
def test_manager_adds_the_org_chart_the_graph_and_team_chats_and_comes_back_home(browser, fake):
    load(browser, fake)
    browser.click("#fdlevel [data-level=manager]")
    browser.wait_for("document.documentElement.dataset.level === 'manager'")
    assert browser.js("localStorage.getItem('sutra:level')") == "manager"
    assert texts(browser, "#fdnav button") == ["Org chart", "Workflow graph", "Team chats"]
    assert texts(browser, "#fdlists [data-act=fd-chat]") == ["Chat"]                  # each team's chat
    browser.click("#fdnav [data-pane=chart]")
    browser.wait_for("document.documentElement.dataset.place === 'ws'")
    assert on_screen(browser, "#pane-chart") and not on_screen(browser, "#front")
    assert not on_screen(browser, "#railsettings") and not on_screen(browser, "#railowner")   # Settings and Usage and log wait for Debug
    browser.click("#gofront")
    browser.wait_for("document.documentElement.dataset.place === 'front'")
    assert on_screen(browser, "#front")


@browser_only
def test_debug_adds_settings_usage_and_log_and_the_raw_ai_chat_hook(browser, fake):
    load(browser, fake, level="debug")
    assert texts(browser, "#fdnav .fdnavb") == ["Org chart", "Workflow graph", "Team chats", "Settings", "Usage and log", "Raw AI chat"]
    assert browser.js("document.querySelector('#fdnav a.fdnavb').getAttribute('href')") == "/console"
    assert on_screen(browser, "#fddebug .fddebug")                                    # the Heads up lane, in full
    browser.click("#fd-rawchat")
    browser.wait_for("document.getElementById('fddebug').textContent.includes('raw AI chat viewer')")
    browser.click("#fdnav [data-pane=settings]")
    browser.wait_for("document.documentElement.dataset.place === 'ws'")
    assert on_screen(browser, "#pane-settings") and on_screen(browser, "#railsettings")


@browser_only
def test_the_phone_has_no_sideways_scroll(browser, fake):
    browser.set_size(390, 844)
    load(browser, fake, level="manager")
    assert browser.js("document.documentElement.scrollWidth <= window.innerWidth + 1")
    assert browser.js("document.getElementById('front').scrollWidth <= document.getElementById('front').clientWidth + 1")
