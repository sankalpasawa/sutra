"""Home's front door, the project sidebar and a project's view switch in a real browser (the approved layout: project_rail.js, home.js,
dept_ext.js viewSwitch, SutraCtx.level).

Runs only with SUTRA_BROWSER=1, against the fake backend (stages as in test_home.py: "1" a new app, "2" the Web team asks about the menu).
What it proves:

  home       Home is the sidebar and "What should we make?": no Simple/Manager/Debug switch, no needs cards or lists in the main area; no graph,
             org chart, settings or org chat on show
  sidebar    New project, Needs you (the Web question, with its count, going to the project), Projects (plain words on hover), Settings & logs
             (the back room: Settings, with a way back); an approval of no project goes to the org chart
  new        the box sends a new project to the org chat; Sutra's question shows as a card; once a team has the work, its page opens
  project    a team page carries the same sidebar with the project marked, and the view switch in the studio's top bar: Simple shows the studio
             only, Manager adds the Detailed view and the org map, Debug adds the Raw AI chat and Usage and log; the choice is kept in
             localStorage sutra:level and Home has none
  phone      390 px wide: the sidebar folds behind a menu button; no sideways scroll
"""
from __future__ import annotations

import json

import pytest

browser_only = pytest.mark.browser

DEPT_SESSION = "cs_5e0a77b19c3d"       # the Web team's chat


def q(css: str) -> str:
    return json.dumps(css)


def load(browser, fake, *, stage="2", level="simple", place="front", path="/"):
    browser.set_level(level, place)
    fake.stage(stage)
    browser.goto(fake.url + path)
    if path == "/":
        browser.wait_for("window.HomePage && HomePage.state().loaded === true && HomePage.state().departmentsLoaded")
        fake.wait_subscribers(1)
    browser.wait_for("document.getElementById('prail') !== null")


def load_team(browser, fake, level="simple"):
    load(browser, fake, level=level, path="/d/web/?view=simple")
    browser.wait_for("document.getElementById('pviewsw') !== null && document.querySelector('#prail .pr-item') !== null")


def texts(browser, css):
    return browser.js(f"Array.from(document.querySelectorAll({q(css)}), e => e.textContent.trim().replace(/\\s+/g, ' '))")


def on_screen(browser, css) -> bool:
    return browser.js(f"(() => {{ const e = document.querySelector({q(css)}); if (!e) return false; const r = e.getBoundingClientRect(); "
                      f"return getComputedStyle(e).display !== 'none' && getComputedStyle(e).visibility !== 'hidden' && r.width > 0 && r.height > 0; }})()")


def posts(fake, prefix="/api/"):
    return [r for r in fake.log(prefix) if r["method"] in ("POST", "PUT", "DELETE")]


@browser_only
def test_home_is_the_sidebar_and_the_box_with_no_level_switch(browser, fake):
    load(browser, fake)
    assert on_screen(browser, "#front") and on_screen(browser, "#fdbox") and on_screen(browser, "#prail")
    for hidden in ("#sview", "#dview", "#pane-graph", "#pane-chart", "#pane-settings", "#smsgs"):
        assert not on_screen(browser, hidden), hidden
    for gone in ("#fdlevel", "#fdnav", "#fdneeds", "#fdlists", "#fddebug", "#pviewsw", "#front [data-level]"):      # the switch lives in a project only
        assert not browser.exists(gone), gone
    assert texts(browser, "#fd-new-h") == ["What should we make?"]
    assert texts(browser, "#fdsend") == ["Go"]
    assert texts(browser, "#fdfaces .fdteam") == ["Asha, Mira, Kabir, Dev and Nora are ready."]
    assert browser.console_errors == []


@browser_only
def test_the_sidebar_lists_what_needs_you_and_every_project_in_plain_words(browser, fake):
    load(browser, fake)
    browser.wait_for("document.getElementById('pr-needs-h') !== null")
    assert texts(browser, "#pr-new") == ["New project"]
    assert texts(browser, ".pr-head") == ["Needs you", "Projects"]
    assert texts(browser, "#pr-needs-h + .pr-list .pr-name") == ["Web"]
    assert texts(browser, "#pr-needs-h + .pr-list .pr-count") == ["1"]
    assert browser.js("document.querySelector('#pr-proj-h + .pr-list .pr-item').getAttribute('title')") == "Needs your answer"
    assert browser.js("document.querySelector('#pr-needs-h + .pr-list .pr-item').getAttribute('href')") == "/d/web/?view=simple"
    assert texts(browser, "#pr-settings") == ["Settings & logs"]
    assert not browser.exists("#prail [aria-current=page]")                            # Home: no project is open
    # New project on Home goes to the box itself
    browser.click("#pr-new")
    browser.wait_for("document.activeElement === document.getElementById('fdbox')")
    # an approval belongs to no project: it is "Your organisation", and it opens the org chart
    browser.js("""ProjectRail.set({needs: [{message_id: 9, kind: "approval", dept_id: null, text: "Add a Design team?"}]})""")
    assert texts(browser, "#pr-needs-h + .pr-list .pr-name") == ["Your organisation"]
    assert browser.js("document.querySelector('#pr-needs-h + .pr-list .pr-item').getAttribute('href')") == "/?pane=chart"


@browser_only
def test_a_new_app_shows_only_the_box_and_an_empty_project_list(browser, fake):
    load(browser, fake, stage="1")
    assert not browser.exists("#pr-needs-h")
    assert texts(browser, "#prail .pr-empty") == ["Your projects show here."]


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
def test_home_takes_the_owner_to_the_project_once_a_team_has_the_work(browser, fake):
    load(browser, fake, stage="1")
    browser.expect_failed("/d/web/")                                                   # the fake serves no team page at stage 1
    browser.js("""(() => { const S = HomePage.state(); S.front.sent = true;
      S.messages.push({id: 900, role: "user", text: "A website for my cafe"}, {id: 901, role: "agent", text: "", card: {type: "task", dept_id: "web", dept_name: "Web", title: "A website for my cafe"}});
      HomePage.renderFront(); })()""")
    assert texts(browser, "#fdlatest .fdwatch") == ["Watch it being built"]
    assert browser.js("document.querySelector('#fdlatest .fdwatch').getAttribute('href')") == "/d/web/?view=simple"
    assert not browser.exists("#fdlatest [data-act=fd-conversation]")                  # Home never lands in the org chat
    browser.wait_for("location.pathname === '/d/web/'", timeout=10)


@browser_only
def test_sutras_question_shows_as_a_card_on_the_front_door_in_plain_words(browser, fake):
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
def test_settings_and_logs_opens_the_back_room_with_a_way_home(browser, fake):
    load(browser, fake)
    browser.click("#pr-settings")
    browser.wait_for("document.documentElement.dataset.place === 'ws' && HomePage.state().loaded === true")
    assert on_screen(browser, "#pane-settings") and not on_screen(browser, "#front") and not on_screen(browser, "#prail")
    browser.click("#gofront")
    browser.wait_for("document.documentElement.dataset.place === 'front'")
    assert on_screen(browser, "#front") and on_screen(browser, "#prail") and browser.js("location.search") == ""


@browser_only
def test_a_project_has_the_sidebar_and_its_own_view_switch_in_the_studio_bar(browser, fake):
    load_team(browser, fake)
    assert texts(browser, "#prail [aria-current=page] .pr-name") == ["Web"]           # the open project is marked
    assert browser.js("document.getElementById('pviewsw').parentElement.matches('#sview .stop')")
    assert texts(browser, "#pv-btn") == ["Simple"]
    assert not on_screen(browser, "#shome") and not on_screen(browser, "#to-home-s")    # the sidebar's New project and list replace them (the strip stays as the pill's row)
    assert not on_screen(browser, "#sdetail") and not on_screen(browser, "#rawchat-open")
    browser.click("#pv-btn")
    assert texts(browser, "#pv-menu .pv-opt b") == ["Simple", "Manager", "Debug"]
    assert texts(browser, "#pv-menu .pv-link") == []                                   # Simple: the studio only
    # Manager: the Detailed view and the org map
    browser.click("#pv-menu .pv-opt[data-level=manager]")
    browser.wait_for("document.documentElement.dataset.level === 'manager'")
    assert browser.js("localStorage.getItem('sutra:level')") == "manager"
    assert texts(browser, "#pv-btn") == ["Manager"]
    assert on_screen(browser, "#sdetail")
    browser.click("#pv-btn")
    assert texts(browser, "#pv-menu .pv-link") == ["Detailed view", "Team chats", "Org chart", "Workflow graph"]
    browser.click("#pv-menu .pv-link[data-go=detail]")
    browser.wait_for("!document.body.classList.contains('simple')")
    assert browser.js("document.getElementById('pviewsw').classList.contains('pv-inrail')")      # the switch stays reachable in the Detailed view: the sidebar's foot
    assert browser.console_errors == []


@browser_only
def test_debug_adds_the_raw_ai_chat_and_usage_and_log_to_the_project(browser, fake):
    load_team(browser, fake, level="debug")
    browser.expect_failed("/api/calls")                                              # the fake serves no Raw AI chat calls
    assert texts(browser, "#pv-btn") == ["Debug"]
    assert on_screen(browser, "#rawchat-open")
    browser.click("#pv-btn")
    assert texts(browser, "#pv-menu .pv-link") == ["Detailed view", "Team chats", "Org chart", "Workflow graph", "Raw AI chat", "Usage and log"]
    assert browser.js("document.querySelector('#pv-menu a.pv-link[href=\"/console\"]') !== null")
    browser.click("#pv-menu .pv-link[data-go=raw]")
    browser.wait_for("window.RawChat && RawChat.state().open === true")


@browser_only
def test_the_phone_folds_the_sidebar_behind_a_menu_button_and_has_no_sideways_scroll(browser, fake):
    browser.set_size(390, 844)
    load(browser, fake)
    assert browser.js("document.documentElement.scrollWidth <= window.innerWidth + 1")
    assert browser.js("document.getElementById('front').scrollWidth <= document.getElementById('front').clientWidth + 1")
    assert on_screen(browser, "#prailbtn") and not on_screen(browser, "#prail")
    browser.click("#prailbtn")
    browser.wait_for("document.body.classList.contains('prail-open')")
    browser.wait_for("document.getElementById('prail').getBoundingClientRect().left >= 0")
    assert on_screen(browser, "#prail") and browser.js("document.getElementById('prailbtn').getAttribute('aria-expanded')") == "true"
    browser.js("document.querySelector('.pr-scrim').click()")
    browser.wait_for("!document.body.classList.contains('prail-open')")
