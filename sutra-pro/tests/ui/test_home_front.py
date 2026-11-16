"""Attention (Home), the sidebar, Agent Org, Settings & logs and a project's one view button in a real browser (the approved layout:
project_rail.js, home.js, front_door.js, orgchart_view.js teamCardsHtml, dept_ext.js viewSwitch).

Runs only with SUTRA_BROWSER=1, against the fake backend (stages as in test_home.py: "1" a new app, "2" the Web team asks about the menu).
What it proves:

  attention  Home is the sidebar, "What should we make?", then "Needs you" with the Web question answered in place, then "Just finished";
             no level switch; no graph, org chart, settings or org chat on show
  sidebar    New project, Attention (with its count), Agent Org, My sections (+ makes one, rename and delete from its menu, a project's
             menu moves it; kept on the server), All projects (plain words on hover), Settings & logs
  new        the box sends a new project to the org chat; Sutra's question shows as a card; once a team has the work, its page opens
  org        Agent Org keeps the sidebar, shows one card per team, and a card opens the team's agent view (?view=detail)
  settings   Settings & logs opens the back room, with Usage and log and Raw AI chat under Logs & debug
  project    a team page carries the same sidebar with the project marked, and ONE button: Agent view <-> Simple view
  phone      390 px wide: the sidebar folds behind a menu button; no sideways scroll
"""
from __future__ import annotations

import json

import pytest

browser_only = pytest.mark.browser

DEPT_SESSION = "cs_5e0a77b19c3d"       # the Web team's chat


def q(css: str) -> str:
    return json.dumps(css)


def load(browser, fake, *, stage="2", place="front", path="/"):
    browser.set_place(place)
    fake.stage(stage)
    browser.goto(fake.url + path)
    if path == "/":
        browser.wait_for("window.HomePage && HomePage.state().loaded === true && HomePage.state().departmentsLoaded")
        fake.wait_subscribers(1)
    browser.wait_for("document.getElementById('prail') !== null")


def load_team(browser, fake, path="/d/web/"):
    load(browser, fake, path=path)
    browser.wait_for("document.getElementById('agentview') !== null && document.querySelector('#prail .pr-item') !== null")


def texts(browser, css):
    return browser.js(f"Array.from(document.querySelectorAll({q(css)}), e => e.textContent.trim().replace(/\\s+/g, ' '))")


def on_screen(browser, css) -> bool:
    return browser.js(f"(() => {{ const e = document.querySelector({q(css)}); if (!e) return false; const r = e.getBoundingClientRect(); "
                      f"return getComputedStyle(e).display !== 'none' && getComputedStyle(e).visibility !== 'hidden' && r.width > 0 && r.height > 0; }})()")


def posts(fake, prefix="/api/"):
    return [r for r in fake.log(prefix) if r["method"] in ("POST", "PUT", "DELETE")]


@browser_only
def test_attention_is_the_box_then_what_needs_you_answered_in_place(browser, fake):
    load(browser, fake)
    assert on_screen(browser, "#front") and on_screen(browser, "#fdbox") and on_screen(browser, "#prail")
    for hidden in ("#sview", "#dview", "#pane-graph", "#pane-chart", "#pane-settings", "#smsgs"):
        assert not on_screen(browser, hidden), hidden
    for gone in ("#fdlevel", "#fdnav", "#fdlists", "#fddebug", "#agentview", "html[data-level]"):      # no level anywhere on Home
        assert not browser.exists(gone), gone
    assert texts(browser, "#fd-new-h") == ["What should we make?"]
    assert texts(browser, "#fdsend") == ["Go"]
    browser.wait_for("document.querySelector('#fdattn .fdcard') !== null")
    assert texts(browser, "#fd-needs-h") == ["Needs you 1"]
    assert texts(browser, "#fdattn .fdwho") == ["Web"]
    assert texts(browser, "#fdattn [data-act=fd-option]") == ["Yes, show the prices", "No, names only"]
    browser.click("#fdattn [data-act=fd-option][data-opt='1']")
    browser.wait_for("Object.values(HomePage.state().answers).includes('Option 1')")
    sent = posts(fake, f"/api/chats/{DEPT_SESSION}/messages")
    assert sent and sent[0]["body"] == {"text": "Option 1"} and sent[0]["token"] is True       # to the team's own chat, never the org chat
    assert browser.console_errors == []


@browser_only
def test_nothing_waiting_reads_calm(browser, fake):
    load(browser, fake, stage="1")
    browser.wait_for("document.querySelector('#fdattn .fdempty') !== null")
    assert texts(browser, "#fdattn .fdempty b") == ["Nothing needs you right now."]
    assert not on_screen(browser, "#fddone")


@browser_only
def test_the_sidebar_has_attention_agent_org_sections_and_every_project_in_plain_words(browser, fake):
    load(browser, fake)
    browser.wait_for("document.querySelector('#pr-att .pr-count') !== null")
    assert texts(browser, "#pr-new") == ["New project"]
    assert texts(browser, "#pr-att .pr-name") == ["Attention"] and texts(browser, "#pr-att .pr-count") == ["1"]
    assert browser.js("document.getElementById('pr-att').getAttribute('aria-current')") == "page"          # Home is Attention
    assert browser.js("document.getElementById('pr-org').getAttribute('href')") == "/?pane=org"
    assert texts(browser, ".pr-head") == ["My sections"]
    assert texts(browser, ".pr-all .pr-secname") == ["All projects"]
    assert browser.js("document.querySelector('.pr-all .pr-item').getAttribute('title')") == "Needs your answer"
    assert browser.js("document.querySelector('.pr-all .pr-item').getAttribute('href')") == "/d/web/"
    assert texts(browser, "#pr-settings") == ["Settings & logs"]
    browser.click("#pr-new")                                                             # New project on Home goes to the box itself
    browser.wait_for("document.activeElement === document.getElementById('fdbox')")


@browser_only
def test_sections_are_made_renamed_filled_and_deleted_and_kept_on_the_server(browser, fake):
    load(browser, fake)
    browser.click("#pr-addsec")
    browser.wait_for("document.activeElement && document.activeElement.classList.contains('pr-input')")
    browser.js("document.activeElement.value = 'Clients'; document.activeElement.form.requestSubmit()")
    browser.wait_for("document.querySelector('.pr-sec[data-sec^=sec_] .pr-secname') !== null")
    assert texts(browser, ".pr-sec[data-sec^=sec_] .pr-secname") == ["Clients"]
    put = [r for r in posts(fake, "/api/sections") if r["method"] == "PUT"]
    assert put and put[-1]["body"]["sections"][0]["name"] == "Clients" and put[-1]["token"] is True
    # a project's menu moves it into the section
    browser.click('.pr-more[data-team="web"]')
    assert texts(browser, "#pr-menu .pr-mi") == ["Clients", "New section…"]
    browser.click("#pr-menu .pr-mi[data-pr=move][data-sec^=sec_]")
    browser.wait_for("document.querySelector('.pr-sec[data-sec^=sec_] .pr-item[href=\"/d/web/\"]') !== null")
    assert texts(browser, ".pr-all .pr-hint") == ["Every project is in a section."]
    # rename from the section's menu
    browser.click(".pr-more[data-sec^=sec_]")
    assert texts(browser, "#pr-menu .pr-mi") == ["Rename", "Delete section"]
    browser.click("#pr-menu .pr-mi[data-pr=rename]")
    browser.wait_for("document.activeElement && document.activeElement.classList.contains('pr-input')")
    browser.js("document.activeElement.value = 'Customers'; document.activeElement.form.requestSubmit()")
    browser.wait_for("Array.from(document.querySelectorAll('.pr-secname'), e => e.textContent).includes('Customers')")
    # a reload reads them back from the server
    browser.reload()
    browser.wait_for("document.querySelector('.pr-sec[data-sec^=sec_] .pr-item') !== null")
    assert texts(browser, ".pr-sec[data-sec^=sec_] .pr-secname") == ["Customers"]
    # delete: the project goes back to All projects
    browser.click(".pr-more[data-sec^=sec_]")
    browser.click("#pr-menu .pr-mi[data-pr=delete]")
    browser.wait_for("document.querySelector('.pr-sec[data-sec^=sec_]') === null")
    assert browser.js("document.querySelector('.pr-all .pr-item').getAttribute('href')") == "/d/web/"
    assert browser.console_errors == []


@browser_only
def test_a_new_app_shows_only_the_box_and_an_empty_project_list(browser, fake):
    load(browser, fake, stage="1")
    assert not browser.exists("#pr-att .pr-count")
    assert texts(browser, "#prail .pr-all .pr-empty") == ["Your projects show here."]


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
    assert browser.js("document.querySelector('#fdlatest .fdwatch').getAttribute('href')") == "/d/web/"
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
def test_settings_and_logs_opens_the_back_room_with_the_logs_and_a_way_home(browser, fake):
    load(browser, fake)
    browser.click("#pr-settings")
    browser.wait_for("document.documentElement.dataset.place === 'ws' && HomePage.state().loaded === true")
    assert on_screen(browser, "#pane-settings") and not on_screen(browser, "#front") and not on_screen(browser, "#prail")
    assert texts(browser, "#rail-owner-h") == ["Logs & debug"]
    assert texts(browser, "#railowner .rtname") == ["Usage and log", "Raw AI chat"]
    assert browser.js("document.getElementById('goconsole').getAttribute('href')") == "/console"
    browser.expect_failed("/d/web/raw")                                               # the fake serves no /raw page
    browser.click("#gorawchat")                                                       # the team waiting on the owner
    browser.wait_for("location.pathname === '/d/web/raw'", timeout=10)


@browser_only
def test_raw_ai_chat_with_no_team_says_so(browser, fake):
    load(browser, fake, stage="1", path="/?pane=settings")
    browser.wait_for("HomePage.state().departmentsLoaded")
    browser.click("#gorawchat")
    browser.wait_for("!document.getElementById('rawchatnote').hidden")
    assert texts(browser, "#rawchatnote") == ["No team has run yet. The raw AI chat shows every AI call once a team starts work."]


@browser_only
def test_agent_org_keeps_the_sidebar_and_a_team_card_opens_its_agent_view(browser, fake):
    load(browser, fake, path="/?pane=org")
    browser.wait_for("document.querySelector('#orgteams .orgcard') !== null")
    assert on_screen(browser, "#prail") and on_screen(browser, "#orgview") and on_screen(browser, "#pane-chart")
    for hidden in ("#schat", "#rail", "#needs", "#front"):
        assert not on_screen(browser, hidden), hidden
    assert browser.js("document.getElementById('pr-org').getAttribute('aria-current')") == "page"
    assert texts(browser, "#org-h") == ["Agent Org"]
    assert browser.js("document.querySelector('#orgteams .orgcard').getAttribute('href')") == "/d/web/?view=detail"
    assert browser.js("document.querySelectorAll('#orgteams .orgcard .orgagent').length") == 5
    browser.click(".orgtabs [data-orgpane=graph]")
    browser.wait_for("!document.getElementById('pane-graph').hidden && document.getElementById('pane-chart').hidden")
    browser.click("#orgteams .orgcard")
    browser.wait_for("location.pathname === '/d/web/' && window.DeptExt && DeptExt.state().started === true")
    browser.wait_for("!document.body.classList.contains('simple')")                # the agent view
    assert browser.console_errors == []


@browser_only
def test_a_project_has_the_sidebar_and_one_agent_view_button(browser, fake):
    load_team(browser, fake)
    assert texts(browser, "#prail [aria-current=page] .pr-name") == ["Web"]           # the open project is marked
    assert browser.js("document.body.classList.contains('simple')")                    # no ?view=: the studio
    assert browser.js("document.getElementById('agentview').parentElement.matches('#sview .stop')")
    assert texts(browser, "#agentview") == ["Agent view"]
    assert not on_screen(browser, "#shome") and not on_screen(browser, "#to-home-s")
    assert not on_screen(browser, "#sdetail") and not browser.exists("#rawchat-open") and not browser.exists("#pv-menu")
    browser.click("#agentview")
    browser.wait_for("!document.body.classList.contains('simple')")
    assert texts(browser, "#agentview") == ["Simple view"]
    assert browser.js("document.getElementById('agentview').classList.contains('pv-inrail')")     # the sidebar's foot in the agent view
    browser.click("#agentview")
    browser.wait_for("document.body.classList.contains('simple')")
    assert texts(browser, "#agentview") == ["Agent view"]
    assert browser.console_errors == []


@browser_only
def test_a_bare_project_link_opens_the_studio_even_after_the_agent_view(browser, fake):
    load_team(browser, fake, path="/d/web/?view=detail")
    browser.wait_for("!document.body.classList.contains('simple')")
    browser.goto(fake.url + "/d/web/")
    browser.wait_for("window.DeptExt && DeptExt.state().started === true")
    assert browser.js("document.body.classList.contains('simple')")


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
