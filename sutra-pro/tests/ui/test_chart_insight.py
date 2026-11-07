"""Home's chart insight parts (gap package chart-insight, docs/notes/GAP2-chart-insight.md): the rail's search, the Chart notes under the Org chart's
log, the card's address, and the boxes a search keeps lit. The page-file checks run in the merge gate; the rest drive a real headless Chrome over the
fake backend (`SUTRA_BROWSER=1`)."""
from __future__ import annotations

import re

import pytest
from test_home import HOME, SHELL_CSS, attrs, load, posts, present, absent, shown, texts

from sutra_app.ui import STATIC_DIR

browser_only = pytest.mark.browser
DEPT_EXT = (STATIC_DIR / "js" / "dept_ext.js").read_text(encoding="utf-8")
GRAPH_CSS = (STATIC_DIR / "css" / "sutra-graph.css").read_text(encoding="utf-8")

FAQ = {"team_id": "web", "team_name": "Web", "node_id": "faq", "kind": "division", "address": "Web > FAQ", "matched_on": ["purpose"], "snippet": "Questions people ask"}
MENU = {"team_id": "content", "team_name": "Content", "node_id": "menu", "kind": "division", "address": "Content > Menu", "matched_on": ["name", "task"],
        "snippet": "The coffee menu"}
CHAT = {"session_id": "cs_5e0a77b19c3d", "message_id": 4, "title": "Web", "snippet": "the cake list", "at": "2026-11-04T10:00:00Z", "archived": False}
NOTES = [
    {"kind": "overlap", "nodes": [{"id": "faq", "label": "FAQ"}, {"id": "menu", "label": "Menu"}], "words": "FAQ and Menu look alike (45% of their words)", "say": "merge Menu into FAQ"},
    {"kind": "no_purpose", "nodes": [{"id": "content", "label": "Content"}], "words": "Content has no purpose written", "say": "change the purpose of Content to ..."},
]


def open_home(browser, fake, stage="full"):
    browser.expect_failed("/api/chats/cs_org/providers", 404)           # the fake has no provider pill route (not this package's)
    load(browser, fake, stage=stage)


def errors(browser):
    return [line for line in browser.console_errors if "404" not in line]


def find_calls(fake):
    return [r["query"] for r in fake.log("/api/find")]


# ---- the page files (no browser: these run in the merge gate) -----------------------------------------------------------------------------------------

def test_home_loads_the_two_modules_before_its_controller_and_has_the_search_box():
    scripts = re.findall(r'<script src="/ui/js/([\w.]+\.js)"', HOME)
    for name in ("chart_notes.js", "team_find.js"):
        assert (STATIC_DIR / "js" / name).is_file()
        assert scripts.index("orgchart_view.js") < scripts.index(name) < scripts.index("home.js")
    assert re.search(r'<input type="search" id="railfind"[^>]*aria-label="Find a team or its work"', HOME)
    assert 'id="railfindres"' in HOME and HOME.index('id="railfind"') < HOME.index('id="railfindres"') < HOME.index('id="railteams"')


def test_the_team_page_adds_the_notes_script_from_dept_ext_and_the_styles_exist():
    assert 'tag.src = "/ui/js/chart_notes.js"' in DEPT_EXT and "insight();" in DEPT_EXT
    for rule in (".railfind {", ".railfindres {", ".rfhead {"):
        assert rule in SHELL_CSS
    for rule in (".ocpane .ocnotes {", ".ocpane .ocaddr {", ".ocpane .ocsay {"):
        assert rule in GRAPH_CSS


# ---- the rail's search --------------------------------------------------------------------------------------------------------------------------------

@browser_only
def test_the_rail_search_waits_for_a_pause_asks_once_and_lists_teams_then_chats(browser, fake):
    open_home(browser, fake)
    fake.request("POST", "/__fake/find", {"teams": [FAQ, MENU], "messages": [CHAT]})
    assert not shown(browser, "#railfindres")
    browser.type("#railfind", "cake")
    present(browser, "#railfindres .rfound")
    assert find_calls(fake) == ["q=cake"]
    assert shown(browser, "#railfindres")
    assert texts(browser, "#railfindres .rfhead") == ["Found in teams", "Found in chats"]
    assert texts(browser, "#railfindres .rfound .rtname") == ["Web > FAQ", "Content > Menu"]
    assert texts(browser, "#railfindres .rfound .rtstat") == ["matched on purpose · Questions people ask", "matched on name, a task · The coffee menu"]
    assert attrs(browser, "#railfindres a.rfound", "href") == ["/d/web/", "/d/content/"]
    assert texts(browser, "#railfindres .rfmsg .rtname") == ["Web"]
    assert errors(browser) == []


@browser_only
def test_one_character_is_not_a_search_and_escape_clears_the_box(browser, fake):
    open_home(browser, fake)
    fake.request("POST", "/__fake/find", {"teams": [FAQ], "messages": []})
    browser.type("#railfind", "c")
    browser.js("new Promise(r => setTimeout(r, 400))")
    assert find_calls(fake) == [] and not shown(browser, "#railfindres")
    browser.type("#railfind", "a")
    present(browser, "#railfindres .rfound")
    browser.press("Escape")
    absent(browser, "#railfindres .rfound")
    assert browser.js("document.getElementById('railfind').value") == "" and not shown(browser, "#railfindres")


@browser_only
def test_nothing_found_says_so(browser, fake):
    open_home(browser, fake)
    fake.request("POST", "/__fake/find", {"teams": [], "messages": []})
    browser.type("#railfind", "zebra")
    present(browser, "#railfindres .railnone")
    assert texts(browser, "#railfindres .railnone") == ["Nothing found."]


@browser_only
def test_a_chat_hit_opens_the_node_that_owns_the_chat(browser, fake):
    browser.expect_failed("/api/chats/cs_5e0a77b19c3d/providers", 404)          # the fake has no provider pill route either
    open_home(browser, fake)
    fake.request("POST", "/__fake/find", {"teams": [], "messages": [CHAT]})
    browser.type("#railfind", "cake")
    present(browser, '#railfindres [data-act="find-chat"]')
    browser.click('#railfindres [data-act="find-chat"]')
    browser.wait_for("document.getElementById('nodepanel') && !document.getElementById('nodepanel').hidden")
    assert [r["path"] for r in fake.log("/api/chats/cs_5e0a77b19c3d")][:1] == ["/api/chats/cs_5e0a77b19c3d"]


# ---- the Org chart pane -------------------------------------------------------------------------------------------------------------------------

def open_chart(browser):
    """The Org chart pane, with the boxes' eased opacity switched off: the headless page is hidden, so its transitions do not run on a clock."""
    browser.js("document.head.appendChild(Object.assign(document.createElement('style'), {textContent: '.ocpane g.wnode, .ocpane path.wedge {transition: none !important}'}))")
    browser.js("HomePage.selectPane('chart')")
    present(browser, "#pane-chart .ocpane g.wnode")


@browser_only
def test_the_chart_notes_name_what_drifted_and_a_name_opens_its_card_with_its_address(browser, fake):
    fake.request("POST", "/__fake/chart-notes", {"notes": NOTES})
    open_home(browser, fake)
    open_chart(browser)
    present(browser, "#pane-chart .ocnotes .ocnote")
    assert shown(browser, "#pane-chart .ocnotes")
    assert texts(browser, "#pane-chart .ocnotes h4") == ["Chart notes"]
    assert texts(browser, "#pane-chart .ocnote .ocsent") == ["FAQ and Menu look alike (45% of their words)", "Content has no purpose written"]
    assert texts(browser, "#pane-chart .ocnote .ocsay") == ["Say: “merge Menu into FAQ”", "Say: “change the purpose of Content to ...”"]
    assert texts(browser, "#pane-chart .ocnotes .ocinfo")[0].startswith("These notes change nothing")
    browser.click('#pane-chart .ocnotes [data-note-node="menu"]')
    present(browser, "#pane-chart .ocard:not([hidden])")
    assert texts(browser, "#pane-chart .ocard h4") == ["Menu"] and texts(browser, "#pane-chart .ocard .ocaddr") == ["Content > Menu"]
    browser.click('#pane-chart .ocnotes [data-note-node="content"]')
    browser.wait_for("document.querySelector('#pane-chart .ocard h4').textContent === 'Content'")
    assert texts(browser, "#pane-chart .ocard .ocaddr") == []                         # a team has no address
    assert [r["path"] for r in fake.log("/api/chart/notes")] != [] and errors(browser) == []


@browser_only
def test_with_nothing_flagged_the_panel_says_so_in_one_line(browser, fake):
    open_home(browser, fake)
    open_chart(browser)
    present(browser, "#pane-chart .ocnotes .ocnone")
    assert texts(browser, "#pane-chart .ocnotes h4") == ["Chart notes"] and texts(browser, "#pane-chart .ocnotes .ocnone") == ["Nothing flagged"]
    assert browser.count("#pane-chart .ocnotes .ocnote") == 0


@browser_only
def test_a_failed_notes_read_leaves_the_pane_as_it_was(browser, fake):
    fake.request("POST", "/__fake/fail", {"path": "/api/chart/notes", "status": 500})
    browser.expect_failed("/api/chart/notes", 500)
    open_home(browser, fake)
    open_chart(browser)
    browser.js("new Promise(r => setTimeout(r, 300))")
    assert not shown(browser, "#pane-chart .ocnotes") and browser.count("#pane-chart .ocpane g.wnode") >= 4


def fades_to(browser, node: str, value: float) -> None:
    """Wait until the box of `node` has the opacity `value`."""
    browser.wait_for(f"Math.abs(parseFloat(getComputedStyle(document.querySelector('#pane-chart g.wnode[data-id=\"{node}\"]')).opacity) - {value}) < 0.01")


@browser_only
def test_a_search_keeps_its_hits_lit_the_boxes_above_in_view_and_fades_the_rest(browser, fake):
    open_home(browser, fake)
    open_chart(browser)
    fake.request("POST", "/__fake/find", {"teams": [FAQ], "messages": []})
    browser.type("#railfind", "questions")
    browser.wait_for("document.querySelector('#pane-chart .ocpane').hasAttribute('data-find')")
    fades_to(browser, "faq", 1.0)                                                       # the hit
    fades_to(browser, "web", 0.7)
    fades_to(browser, "root", 0.7)                                                      # the boxes above it stay in view
    fades_to(browser, "menu", 0.22)
    fades_to(browser, "content", 0.22)                                                  # the rest fade
    browser.press("Escape")
    browser.wait_for("!document.querySelector('#pane-chart .ocpane').hasAttribute('data-find')")
    fades_to(browser, "menu", 1.0)


@browser_only
def test_a_search_made_before_the_pane_opened_lights_it_when_it_opens(browser, fake):
    open_home(browser, fake)
    fake.request("POST", "/__fake/find", {"teams": [MENU], "messages": []})
    browser.type("#railfind", "coffee")
    present(browser, "#railfindres .rfound")
    open_chart(browser)
    browser.wait_for("document.querySelector('#pane-chart .ocpane').hasAttribute('data-find')")
    fades_to(browser, "faq", 0.22)
    fades_to(browser, "menu", 1.0)
