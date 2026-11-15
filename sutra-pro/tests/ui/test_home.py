"""The Home page in a real browser (UI-7, docs/design/ui.md sections 6.6, 6.7, 8, 9 and 10; S1-contracts-03, S1-contracts-08, S3-web-06, S3-web-13).

Runs only with SUTRA_BROWSER=1 (the gate skips it): headless Chrome over CDP against the fake backend of UI-0, which mounts the REAL `/` page
(`pages/home.html`) and the real static files. What it proves:

  start page    the greeting, J2's four example briefs, nothing written to the server until the first Send, no console error and no failed request
  org chat      send (the bubble at once, the box emptied only when the server accepts), the progress bar, the task card and its link, the chart_change card,
                the first graph taking the right pane, a choice card, Retry for a message that turned into an error, a refusal (503, 401) in words
  needs you     the strip, "Answer in <team>'s chat" opening the team's own chat (tests/ui/test_home_team_chat.py), an answer going to the DEPARTMENT's session (never cs_org), the card reading "Answered"
  rail, panes   Chat | Workflow graph | Org chart | Teams | Settings, deep links, the root node focusing the chat, a node opening the panel, the phone toggle
  settings      Appearance, the Connectors rows (Test; Sign in for codex only, link and code, polling, Cancel), the Engine group (editable fields, locked
                fields read-only, the {set, unset} body, `dept` in the query, a 422 beside its field)

Stages of the story (the fake's): "1" a new app, "2" the Web team asks about the menu, "3" the owner answered, "full" two teams and every status word.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from sutra_app.ui import PAGES_DIR, STATIC_DIR, inline_script_hashes

browser_only = pytest.mark.browser

DEPT_SESSION = "cs_5e0a77b19c3d"       # the Web team's chat: where an answer to its question goes
BRIEF = "A website for my cafe"
NO_TOKEN = "This page was opened without its access token. Reload it from the app."


def q(css: str) -> str:
    return json.dumps(css)


def load(browser, fake, *, stage="1", query=""):
    """Open Home on one stage of the story and wait until its first load is done."""
    fake.stage(stage)
    browser.goto(fake.url + "/" + query)
    browser.wait_for("window.HomePage && HomePage.state().loaded === true")
    fake.wait_subscribers(1)


def texts(browser, css):
    return browser.js(f"Array.from(document.querySelectorAll({q(css)}), e => e.textContent.trim().replace(/\\s+/g, ' '))")


def attrs(browser, css, name):
    return browser.js(f"Array.from(document.querySelectorAll({q(css)}), e => e.getAttribute({q(name)}))")


def present(browser, css):
    browser.wait_for(f"!!document.querySelector({q(css)})")


def absent(browser, css):
    browser.wait_for(f"!document.querySelector({q(css)})")


def shown(browser, css) -> bool:
    return browser.js(f"(() => {{ const e = document.querySelector({q(css)}); return !!e && !e.hidden && e.offsetParent !== null; }})()")


def on_screen(browser, css) -> bool:
    """Drawn with a size (also a fixed element, which has no offsetParent)."""
    return browser.js(f"(() => {{ const e = document.querySelector({q(css)}); if (!e) return false; const r = e.getBoundingClientRect(); "
                      f"return getComputedStyle(e).display !== 'none' && r.width > 0 && r.height > 0; }})()")


def posts(fake, prefix="/api/"):
    return [r for r in fake.log(prefix) if r["method"] in ("POST", "PUT", "DELETE")]


def send_text(browser, value):
    browser.type("#sbox", value)
    browser.click("#ssend")


# ---------------------------------------------------------------------------------------------------------------------
# the page file (no browser: these run in the merge gate)
# ---------------------------------------------------------------------------------------------------------------------
HOME = (PAGES_DIR / "home.html").read_text(encoding="utf-8")
SHELL_CSS = (STATIC_DIR / "css" / "sutra-shell.css").read_text(encoding="utf-8")
SKELETON_IDS = ("sview", "stitle", "sotype", "smsgs", "sprog", "sstatus", "scompose", "sbox", "ssend", "sright", "needs", "pane-graph", "pane-chart",
                "pane-settings", "dview", "railtoggle", "barbadge", "rail", "gochat", "railteams", "nodepanel", "sbanner", "set-appearance", "set-connectors",
                "set-workdir", "set-engine")


def test_the_page_has_one_boot_marker_and_one_inline_script_that_is_hashed():
    assert HOME.count("<!--SUTRA-BOOT-->") == 1
    assert len(inline_script_hashes(HOME)) == 1                        # the first-paint theme script; no inline handler, no other inline script
    assert re.search(r"<script(?![^>]*\bsrc=)[^>]*\s[a-z-]+=", HOME) is None, "an inline script with attributes would not be covered by the CSP"
    assert re.search(r"\son[a-z]+\s*=", HOME) is None                  # no inline event handler (script-src has no 'unsafe-inline')
    assert "localStorage.getItem(\"j2theme\")" in HOME                 # J2's key: one theme for Home and the team pages


def test_the_page_loads_only_its_own_files_and_every_one_exists():
    assert re.search(r"(?:src|href)\s*=\s*[\"']\s*(?:https?:)?//", HOME) is None
    assert re.search(r"https?://|url\(", SHELL_CSS) is None
    scripts = re.findall(r'<script src="/ui/js/([\w.]+\.js)"', HOME)
    sheets = re.findall(r'<link rel="stylesheet" href="/ui/css/([\w.-]+\.css)"', HOME)
    for name in scripts:
        assert (STATIC_DIR / "js" / name).is_file(), name
    for name in sheets:
        assert (STATIC_DIR / "css" / name).is_file(), name
    assert sheets == ["j2-shell.css", "sutra-graph.css", "sutra-panel.css", "sutra-shell.css"]       # D138: Home keeps the frozen sheet, not the team page's j2.css
    assert scripts[0] == "sutra_ctx.js" and scripts[-1] == "home.js"
    assert scripts.index("settings_view.js") < scripts.index("home.js")
    for earlier, later in (("sutra_events.js", "home.js"), ("graph_layout.js", "graph_view.js"), ("chart_marks.js", "orgchart_view.js"),
                           ("graph_view.js", "orgchart_view.js"), ("chat_view.js", "node_panel.js"), ("fnode_view.js", "node_panel.js")):
        assert scripts.index(earlier) < scripts.index(later), (earlier, later)
    assert len(scripts) == len(set(scripts))                          # no script twice
    assert HOME.index("<!--SUTRA-BOOT-->") < HOME.index("sutra_ctx.js")   # the boot block comes before the script that reads it


def test_the_page_has_the_skeleton_and_the_hooks_the_script_and_the_tests_use():
    for ident in SKELETON_IDS:
        assert f'id="{ident}"' in HOME, ident
    assert '<body class="simple home">' in HOME
    assert 'class="stoggle"' in HOME and 'data-show="chat"' in HOME and 'data-show="right"' in HOME
    assert [m for m in re.findall(r'<button[^>]*data-pane="(\w+)"[^>]*data-group="(\w+)"', HOME)] == [
        ("settings", "appearance"), ("settings", "connectors"), ("settings", "limits"), ("settings", "notices"), ("settings", "recurring"),
        ("settings", "engine"), ("settings", "notes"), ("settings", "about")]
    assert re.findall(r'<button[^>]*data-pane="(\w+)"(?![^>]*data-group)', HOME) == ["graph", "chart"]
    assert 'id="pane-chart" hidden' in HOME and 'id="pane-settings" hidden' in HOME and 'id="pane-graph" hidden' not in HOME


def test_the_style_sheet_uses_only_j2_tokens_for_colour():
    colours = re.findall(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(", SHELL_CSS)
    assert colours == []                                              # every colour is a token, so light, dark and system need no rule here


def test_the_real_page_is_served_with_a_csp_that_covers_its_one_script(fake_server):
    import urllib.request

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(fake_server.url + "/", timeout=20) as response:
        body = response.read().decode()
        csp = response.headers["Content-Security-Policy"]
    assert inline_script_hashes(body) == inline_script_hashes(HOME)
    assert all(h in csp for h in inline_script_hashes(HOME))
    script_src = [part for part in csp.split(";") if part.strip().startswith("script-src")][0]
    assert "'unsafe-inline'" not in script_src
    assert '"page":"home"' in body.replace(" ", "")


# ---------------------------------------------------------------------------------------------------------------------
# the start page
# ---------------------------------------------------------------------------------------------------------------------
@browser_only
def test_a_new_app_shows_the_greeting_and_the_example_briefs_and_writes_nothing(browser, fake):
    load(browser, fake)
    assert texts(browser, "#smsgs .nmsg")[0].endswith("Hello. Tell me what you need and I will find the right team.")
    briefs = attrs(browser, "[data-brief]", "data-brief")
    assert len(briefs) == 4 and briefs[0] == BRIEF
    assert browser.js("document.title") == "Sutra"
    assert shown(browser, "#sbox") and not browser.js("document.getElementById('sbox').disabled")
    assert not browser.js("!document.getElementById('sprog').hidden")                       # no turn has run: no progress bar
    assert texts(browser, "#needs")[0].endswith("Nothing needs you right now.")
    assert "No teams yet" in texts(browser, "#railteams")[0]
    assert posts(fake) == []                                                               # nothing is created until the first Send
    assert browser.console_errors == []


@browser_only
def test_home_reads_what_the_design_says_on_load_and_nothing_else(browser, fake):
    load(browser, fake)
    paths = sorted({(r["path"], tuple(sorted(r["query"].split("&"))) if r["query"] else ()) for r in fake.log("/api/") if r["method"] == "GET"})
    wanted = {"/api/chats/cs_org", "/api/chats/cs_org/messages", "/api/chart", "/api/chart/changes", "/api/graph", "/api/departments", "/api/needs-you",
              "/api/health", "/api/heads-up",
              "/api/chats/cs_org/providers",                   # the model pill of the org chat (ABS-9)
              "/api/limits", "/api/ops/attention",             # the limit line of the strip and the quiet hours (gap routines-limits)
              "/api/ops/welcome"}                              # whether the first-run card is due (gap welcome-settings)
    assert {p for p, _ in paths if p != "/api/events"} == wanted
    graph = [r for r in fake.log("/api/graph") if r["path"] == "/api/graph"][0]
    assert "level=chart" in graph["query"]
    assert not any("dept=" in r["query"] for r in fake.log("/api/") if r["path"] != "/api/events")      # Home never passes a department
    assert browser.console_errors == []


@browser_only
def test_home_asks_for_the_newest_changes_not_the_first_of_a_long_log(browser, fake):
    """QA org-chat-teams: `limit=50` alone is the OLDEST 50, so after change 50 the log pane, its marks and Show in the org chart never moved on."""
    load(browser, fake)
    asked = [r["query"] for r in fake.log("/api/chart/changes") if r["path"] == "/api/chart/changes"]
    assert asked and set(asked) == {"limit=50&newest=true"}


@browser_only
def test_home_boots_with_no_console_error_and_the_rail_shows_its_items(browser, fake):
    load(browser, fake, stage="full")
    assert texts(browser, "#rail > button, #rail .railhead, #rail .railsec > button") == [
        "Chat", "Workflow graph", "Org chart", "Teams", "Settings", "Appearance", "Connectors", "Limits", "Notifications", "Recurring work", "Engine", "Notes", "About", "Owner"]
    assert texts(browser, "#goconsole .rtname") == ["Usage and log"] and attrs(browser, "#goconsole", "href") == ["/console"]       # the Owner section's one link
    assert browser.console_errors == []


# ---------------------------------------------------------------------------------------------------------------------
# the org chat
# ---------------------------------------------------------------------------------------------------------------------
@browser_only
def test_a_brief_is_sent_with_the_token_and_the_whole_first_task_plays_out(browser, fake):
    load(browser, fake)
    browser.click("[data-brief]")                                                         # J2's start page: a brief button sends it
    present(browser, ".c-task")
    sent = [r for r in posts(fake, "/api/chats/cs_org/messages")]
    assert len(sent) == 1 and sent[0]["body"] == {"text": BRIEF} and sent[0]["token"] is True and sent[0]["status"] == 202
    assert BRIEF in texts(browser, "#smsgs .sb.me")
    assert browser.count("[data-start]") == 0                                              # the examples go once the owner has written
    present(browser, ".c-chart")
    assert "Added the Web team" in texts(browser, ".c-chart .csum")
    fake.wait_flows()
    assert browser.js("HomePage.state().turn.phase") == "done"
    assert attrs(browser, "#sprog > div", "class")[-1] == "on"                             # the last segment, Done
    assert texts(browser, "#sprog > div") == ["Reading the org chart", "Checking the model library", "Planning", "Setting up the team", "Done"]
    assert browser.console_errors == []


@browser_only
def test_the_progress_bar_and_sentence_follow_the_turn(browser, fake):
    load(browser, fake)
    fake.emit("chat.turn", {"session_id": "cs_org", "turn": 1, "phase": "planning", "detail": "Planning"})
    browser.wait_for("!document.getElementById('sprog').hidden")
    assert attrs(browser, "#sprog > div", "class") == ["done", "done", "on", "", ""]
    assert browser.text("#sstatus") == "Planning…"
    fake.emit("chat.turn", {"session_id": "cs_org", "turn": 1, "phase": "applying", "detail": "Setting up the team"})
    browser.wait_for("document.getElementById('sstatus').textContent === 'Setting up the team\\u2026'")
    fake.emit("chat.turn", {"session_id": "cs_org", "turn": 1, "phase": "error", "detail": ""})
    browser.wait_for("document.getElementById('sprog').hidden")
    assert browser.text("#sstatus") == ""
    fake.emit("chat.turn", {"session_id": "cs_other", "turn": 1, "phase": "planning", "detail": ""})         # another session's turn is not the org chat's
    assert browser.js("HomePage.state().turn.phase") == "error"


@browser_only
def test_the_enter_that_confirms_an_ime_candidate_does_not_send_the_half_typed_line(browser, fake):
    """QA org-chat-teams: Enter while composing (Japanese, Chinese, Korean, phonetic Hindi) sent the line; the node panel's box already waited."""
    load(browser, fake)
    enter = lambda init: browser.js(                                                      # noqa: E731  (what the keydown carries is the point of the test)
        "(() => { const t = document.getElementById('sbox'); t.focus(); const e = new KeyboardEvent('keydown', Object.assign({key: 'Enter', bubbles: true, cancelable: true}, "
        + json.dumps(init) + ")); t.dispatchEvent(e); return [e.defaultPrevented, HomePage.state().pending.length]; })()")
    browser.js("(() => { const t = document.getElementById('sbox'); t.value = 'nihongo wo nyuuryoku'; t.dispatchEvent(new CompositionEvent('compositionstart', {bubbles: true})); })()")
    assert enter({"keyCode": 229, "isComposing": True}) == [False, 0]                    # Chrome: the candidate is being accepted
    assert enter({"keyCode": 229, "isComposing": False}) == [False, 0]                   # Safari reports the key after the composition ended with keyCode 229
    assert browser.js("document.getElementById('sbox').value") == "nihongo wo nyuuryoku" and posts(fake) == []
    assert enter({"keyCode": 13, "isComposing": False}) == [True, 1]                     # a plain Enter still sends
    assert enter({"keyCode": 13, "shiftKey": True}) [0] is False                         # Shift+Enter is a new line, as before


@browser_only
def test_a_reload_during_a_turn_brings_the_progress_bar_and_sentence_back_from_the_servers_phase(browser, fake):
    """QA org-chat-teams: the strip and 'Planning...' went blank after a reload while the server still said planning; the dimmed bubble looked stuck."""
    load(browser, fake)
    reload = lambda: (browser.goto(fake.url + "/"), browser.wait_for("window.HomePage && HomePage.state().loaded === true"))   # noqa: E731
    fake.emit("chat.turn", {"session_id": "cs_org", "turn": 1, "phase": "planning", "detail": "Planning"})
    browser.wait_for("!document.getElementById('sprog').hidden")
    reload()                                                                              # the page starts with no memory of the turn
    assert not browser.js("document.getElementById('sprog').hidden")
    assert attrs(browser, "#sprog > div", "class") == ["done", "done", "on", "", ""] and browser.text("#sstatus") == "Planning…"
    assert browser.js("HomePage.state().turn.active") is True                               # the box waits for the answer as it did before the reload
    fake.emit("chat.turn", {"session_id": "cs_org", "turn": 1, "phase": "building", "detail": "Setting up the team"})    # the real server's word for applying
    reload()
    assert attrs(browser, "#sprog > div", "class") == ["done", "done", "done", "on", ""] and browser.text("#sstatus") == "Setting up the team…"
    fake.emit("chat.turn", {"session_id": "cs_org", "turn": 1, "phase": "done", "detail": ""})                             # no turn: the phase is ready, the strip stays hidden
    reload()
    assert browser.js("document.getElementById('sprog').hidden") and browser.text("#sstatus") == ""
    assert browser.js("HomePage.state().turn.active") is False
    fake.emit("chat.turn", {"session_id": "cs_org", "turn": 2, "phase": "planning", "detail": "Planning"})
    reload()                                                                              # resumed again: now the turn ends while no event reaches the page
    assert browser.js("HomePage.state().turn.active") is True
    fake.emit("chat.turn", {"phase": "done"})                                              # (no session_id: the page ignores it, the server's phase becomes ready)
    assert wait_until(browser, lambda: browser.js("HomePage.state().turn.active") is False)    # the 2.5 s re-read of the session ends it
    assert attrs(browser, "#sprog > div", "class")[-1] == "on" and browser.text("#sstatus") == ""


@browser_only
def test_the_first_graph_after_a_turn_takes_the_right_pane_and_the_task_card_links_to_the_team(browser, fake):
    load(browser, fake, query="?pane=chart")
    assert shown(browser, "#pane-chart") and not shown(browser, "#pane-graph")
    browser.type("#sbox", BRIEF)
    browser.press("Enter")                                                                 # Enter sends, as in J2
    present(browser, ".c-task")
    browser.wait_for("document.getElementById('pane-graph') && !document.getElementById('pane-graph').hidden")
    assert not shown(browser, "#pane-chart")
    assert attrs(browser, '.c-task [data-act="open-team"]', "href") == ["/d/web/?view=simple"]
    browser.click('.c-task [data-act="show-node"]')
    present(browser, '.wnode.sel[data-id="web"]')


@browser_only
def test_show_in_the_org_chart_switches_the_pane_and_selects_that_change(browser, fake):
    load(browser, fake, stage="2")
    browser.click('.c-chart [data-act="show-change"]')
    browser.wait_for("!document.getElementById('pane-chart').hidden")
    present(browser, ".chgrow.sel")
    assert attrs(browser, ".chgrow.sel", "data-change") == ["2"]
    assert not shown(browser, "#pane-graph")


@browser_only
def test_the_box_keeps_its_text_when_no_connector_is_usable_and_a_banner_leads_to_settings(browser, fake):
    load(browser, fake)
    sentence = "Claude and Codex are both unavailable. Open Settings to sign in."
    fake.fail("/api/chats/cs_org/messages", 503, code="provider_unavailable", message=sentence, count=1)
    browser.expect_failed("/api/chats/cs_org/messages", 503)
    send_text(browser, BRIEF)
    browser.wait_for("!document.getElementById('sbanner').hidden")
    assert sentence in texts(browser, "#sbanner")[0]
    assert browser.js("document.getElementById('sbox').value") == BRIEF                     # nothing was lost
    assert browser.count("#smsgs .sb.me") == 0                                              # the pending bubble is gone: nothing was stored
    browser.click('#sbanner [data-act="open-settings"]')
    browser.wait_for("!document.getElementById('pane-settings').hidden")
    assert browser.count('#pane-settings .setconn') == 2
    browser.click("#ssend")                                                                 # the rule was for one call: the same text now goes through
    browser.wait_for("document.getElementById('sbox').value === '' && document.querySelectorAll('#smsgs .sb.me').length >= 1")


@browser_only
def test_a_missing_token_closes_the_box_and_says_why(browser, fake):
    load(browser, fake)
    fake.fail("/api/chats/cs_org/messages", 401, count=1)
    browser.expect_failed("/api/chats/cs_org/messages", 401)
    send_text(browser, "hello")
    browser.wait_for("!document.getElementById('sbanner').hidden")
    assert NO_TOKEN in texts(browser, "#sbanner")[0]
    assert browser.js("document.getElementById('sbox').disabled && document.getElementById('ssend').disabled")
    assert NO_TOKEN in texts(browser, "#snote")[0]


@browser_only
def test_too_many_waiting_is_said_in_words(browser, fake):
    load(browser, fake)
    fake.fail("/api/chats/cs_org/messages", 429, count=1)
    browser.expect_failed("/api/chats/cs_org/messages", 429)
    send_text(browser, "hello")
    browser.wait_for("!document.getElementById('sbanner').hidden")
    assert "I answer them one at a time." in texts(browser, "#sbanner")[0]
    assert browser.js("document.getElementById('sbox').value") == "hello"
    assert not browser.js("document.getElementById('sbox').disabled")


@browser_only
def test_a_message_that_turned_into_an_error_has_a_retry_button(browser, fake):
    load(browser, fake)
    failed = {"id": 40, "session_id": "cs_org", "role": "user", "who": "user", "kind": "text", "text": "Make a menu", "card": None, "pause": None,
              "answered_by": None, "task_id": None, "state": "error", "at": "2026-11-04T10:05:00Z"}
    fake.emit("chat.message", {"session_id": "cs_org", "message": failed})
    present(browser, '.nmsg[data-state="error"] [data-act="retry"]')
    browser.click('[data-act="retry"]')
    browser.wait_for("HomePage.state().awaitGraph === true")
    assert [r["path"] for r in posts(fake)] == ["/api/chats/cs_org/retry"]


@browser_only
def test_a_choice_card_posts_the_chosen_option_to_the_org_chat(browser, fake):
    load(browser, fake, stage="full")
    present(browser, '.c-approval [data-act="choose"]')
    assert texts(browser, '.c-approval [data-act="choose"]') == ["Yes", "No"]
    browser.click('.c-approval [data-act="choose"]')
    present(browser, ".c-approval[data-answered]")
    assert "You answered: Yes" in texts(browser, ".c-approval")[0]
    sent = posts(fake, "/api/chats/cs_org/messages")
    assert len(sent) == 1 and sent[0]["body"] == {"text": "Yes", "choice": {"message_id": 20, "option": "yes"}}
    assert browser.count(".c-choice [data-act=\"choose\"]") == 3                            # the other card is still open


@browser_only
def test_an_answered_approval_stays_closed_after_a_reload_and_the_open_cards_stay_open(browser, fake):
    """QA org-chat-teams: the answer lived only in the page, so a reload (or a second window) drew the answered card with Yes and No again."""
    load(browser, fake, stage="full")
    present(browser, '.c-approval [data-act="choose"]')
    browser.click('.c-approval [data-act="choose"]')
    present(browser, ".c-approval[data-answered]")
    browser.goto(fake.url + "/")                                                              # the reload: the page starts from what the server holds
    browser.wait_for("window.HomePage && HomePage.state().loaded === true")
    present(browser, ".c-approval[data-answered]")
    assert browser.count('.c-approval [data-act="choose"]') == 0
    assert "You answered: Yes" in texts(browser, ".c-approval")[0]
    assert browser.count('.c-choice [data-act="choose"]') == 3 and browser.count(".c-choice[data-answered]") == 0


# ---------------------------------------------------------------------------------------------------------------------
# needs you
# ---------------------------------------------------------------------------------------------------------------------
@browser_only
def test_the_needs_you_strip_lists_the_question_and_its_button_opens_the_teams_own_chat(browser, fake):
    load(browser, fake, stage="2")
    assert texts(browser, "#needs .needitem span") == ["Web: Should the menu show prices?"]
    assert texts(browser, "#needcount") == ["1"]
    assert browser.js("document.getElementById('barbadge').textContent") == "1" and not browser.js("document.getElementById('barbadge').hidden")
    assert browser.js("document.getElementById('railtoggle').getAttribute('aria-label')") == "Menu, 1 waiting on you"
    assert texts(browser, "#needs [data-needmsg]") == ["Answer in Web's chat"]        # the button says which chat the question is in (gap dept-chats)
    browser.click("#needs [data-needmsg]")
    browser.wait_for("!document.getElementById('teamchat').hidden && document.activeElement && document.activeElement.classList.contains('nmsg') "
                     "&& document.activeElement.dataset.kind === 'question'")                # the team's own chat, with the question in view


@browser_only
def test_a_chart_change_reads_the_rail_and_the_needs_you_strip_again_so_a_renamed_team_shows_its_new_name(browser, fake):
    """QA org-chat-teams: a rename (from the chat or another window) moved the graph and the org chart but the rail and the Needs-you line kept the old name."""
    load(browser, fake, stage="2")
    reads = lambda path: len([r for r in fake.log(path) if r["path"] == path])        # noqa: E731
    before = (reads("/api/departments"), reads("/api/needs-you"))
    fake.emit("chart.changed", {"revision": 2, "version": 2, "change_id": "chg-0002", "kind": "rearrange", "added": [], "moved": [], "merged": [],
                                "summary": "Renamed Web to Site", "archived": []})
    assert wait_until(browser, lambda: reads("/api/departments") > before[0] and reads("/api/needs-you") > before[1])


@browser_only
def test_an_approval_in_the_needs_you_strip_reads_approval_needed_not_a_leading_colon(browser, fake):
    """QA org-chat-teams: an approval has no team, so its row began with ': Merge Corporate into Weddings?'."""
    load(browser, fake, stage="2")
    browser.js("""(() => { const S = HomePage.state(); S.needs.push({message_id: 9, session_id: "cs_org", kind: "approval", dept_id: null, dept_name: "",
      text: "Merge Corporate into Weddings? Their chats and history stay available.", options: ["Yes", "No"], asked_at: "2026-11-04T10:05:00Z"});
      S.needs.push({message_id: 10, session_id: "cs_org", kind: "question", dept_id: null, dept_name: "", text: "Which colour?", options: [], asked_at: "2026-11-04T10:06:00Z"});
      HomePage.renderNeeds(); })()""")
    assert texts(browser, "#needs .needitem span") == ["Web: Should the menu show prices?",
                                                       "Approval needed: Merge Corporate into Weddings? Their chats and history stay available.",
                                                       "Which colour?"]                  # a team's name still leads its question; a line with neither team nor kind is just the words


@browser_only
def test_an_answer_goes_to_the_teams_own_session_and_the_card_then_reads_answered(browser, fake):
    load(browser, fake, stage="2")
    browser.click('.c-needs [data-act="answer-option"]')
    present(browser, ".c-needs[data-answered]")
    assert texts(browser, ".c-needs .canswer") == ["Answered"]
    sent = posts(fake, "/api/chats/")
    assert len(sent) == 1
    assert sent[0]["path"] == f"/api/chats/{DEPT_SESSION}/messages" and sent[0]["body"] == {"text": "Option 1"} and sent[0]["token"] is True
    assert not any(r["path"] == "/api/chats/cs_org/messages" for r in posts(fake))        # never to the org chat
    browser.wait_for("document.getElementById('needcount').textContent === '0'")
    assert texts(browser, "#needs")[0].endswith("Nothing needs you right now.")
    assert browser.js("document.getElementById('barbadge').hidden")


@browser_only
def test_a_typed_answer_is_sent_as_typed(browser, fake):
    load(browser, fake, stage="2")
    browser.type(".c-needs .canswerbox", "Names only, please")
    browser.click('.c-needs [data-act="answer"]')
    present(browser, ".c-needs[data-answered]")
    assert posts(fake, "/api/chats/")[0]["body"] == {"text": "Names only, please"}
    assert texts(browser, ".c-needs .canswer") == ["Answered"]


@browser_only
def test_a_question_that_is_no_longer_listed_reads_answered_after_a_reload(browser, fake):
    load(browser, fake, stage="3")
    present(browser, ".c-needs[data-answered]")
    assert browser.count('.c-needs [data-act="answer-option"]') == 0
    assert texts(browser, "#needcount") == ["0"]


# ---------------------------------------------------------------------------------------------------------------------
# the rail and the panes
# ---------------------------------------------------------------------------------------------------------------------
@browser_only
def test_the_rail_lists_the_teams_with_their_status_and_the_panes_switch(browser, fake):
    load(browser, fake, stage="full")
    assert texts(browser, "#railteams .railteam .rtname") == ["Web", "Content"]
    assert texts(browser, "#railteams .railteam .rtstat") == ["waiting on you", "idle"]
    assert attrs(browser, "#railteams .railteam", "href") == ["/d/web/", "/d/content/"]
    assert shown(browser, "#pane-graph") and not shown(browser, "#pane-chart") and not shown(browser, "#pane-settings")
    browser.click('#rail [data-pane="chart"]')
    assert shown(browser, "#pane-chart") and not shown(browser, "#pane-graph")
    present(browser, "#pane-chart .wnode")
    assert attrs(browser, "#rail [aria-current]", "data-pane")[-1] == "chart"
    browser.click('#rail [data-pane="settings"][data-group="engine"]')
    assert shown(browser, "#pane-settings") and not shown(browser, "#pane-chart")
    browser.click('#rail [data-pane="graph"]')
    assert shown(browser, "#pane-graph")
    browser.click("#gochat")
    assert browser.js("document.activeElement.id") == "sbox"
    assert browser.console_errors == []


@browser_only
def test_deep_links_open_a_pane_a_node_or_a_change(browser, fake):
    load(browser, fake, stage="full", query="?pane=graph&node=web")
    present(browser, '.wnode.sel[data-id="web"]')
    load(browser, fake, stage="full", query="?pane=chart&change=2")
    assert shown(browser, "#pane-chart")
    present(browser, ".chgrow.sel")
    assert attrs(browser, ".chgrow.sel", "data-change") == ["2"]
    load(browser, fake, stage="full", query="?pane=nonsense")
    assert shown(browser, "#pane-graph")


@browser_only
def test_a_node_click_opens_its_panel_and_the_root_focuses_the_org_chat(browser, fake):
    load(browser, fake, stage="2")
    present(browser, '.wnode[data-id="web"]')
    browser.click('.wnode[data-id="web"]')
    browser.wait_for("!document.getElementById('nodepanel').hidden")
    assert "Web" in browser.text("#nptitle")
    browser.press("Escape")
    browser.wait_for("document.getElementById('nodepanel').hidden")
    browser.click('.wnode[data-id="root"]')
    browser.wait_for("document.activeElement && document.activeElement.id === 'sbox'")
    assert browser.js("document.getElementById('nodepanel').hidden")


def wait_until(browser, check, tries=100):
    """Poll a Python check every 50 ms (the browser's own clock is used for the wait, so a busy machine does not shorten it)."""
    for _ in range(tries):
        if check():
            return True
        browser.js("new Promise(r => setTimeout(r, 50))")
    return check()


@browser_only
def test_a_graph_update_repaints_the_graph_without_a_reload(browser, fake):
    load(browser, fake, stage="2")
    present(browser, '.wnode[data-id="web"]')
    count = lambda: len([r for r in fake.log("/api/graph") if r["path"] == "/api/graph"])   # noqa: E731
    before = count()
    fake.fixture("graph", "3")
    fake.emit("graph.updated")
    assert wait_until(browser, lambda: count() > before)
    browser.js("new Promise(r => setTimeout(r, 300))")
    assert count() == before + 1                                                            # one event, one refetch
    assert browser.console_errors == []


@browser_only
def test_the_phone_gets_a_chat_graph_toggle_and_no_sideways_scroll(browser, fake):
    browser.set_size(390, 800)
    load(browser, fake, stage="2")
    assert shown(browser, "#sview .stoggle") and shown(browser, ".schat") and not shown(browser, "#sright")
    browser.click('.stoggle [data-show="right"]')
    assert shown(browser, "#sright") and not shown(browser, ".schat")
    present(browser, "#pane-graph .wnode, #pane-graph .wlist")
    browser.click('.stoggle [data-show="chat"]')
    assert shown(browser, ".schat") and not shown(browser, "#sright")
    assert browser.js("document.documentElement.scrollWidth <= window.innerWidth")
    # the menu button is on the screen (J2's own page puts it below it on a phone), opens the rail over the page, and a choice closes it again
    assert browser.js("(() => { const r = document.getElementById('railtoggle').getBoundingClientRect(); return r.top >= 0 && r.bottom <= 100 && r.right <= 390; })()")
    assert not on_screen(browser, "#rail")
    browser.click("#railtoggle")
    assert on_screen(browser, "#rail")
    browser.click('#rail [data-pane="chart"]')
    browser.wait_for("!document.getElementById('pane-chart').hidden")
    assert not on_screen(browser, "#rail") and shown(browser, "#sright")


@browser_only
def test_the_left_bar_opens_and_closes_and_remembers_on_a_wide_screen(browser, fake):
    browser.set_size(1440, 900)
    load(browser, fake)
    assert shown(browser, "#rail")
    browser.click("#railtoggle")
    assert not shown(browser, "#rail") and browser.js("document.getElementById('railtoggle').getAttribute('aria-expanded')") == "false"
    assert browser.js("localStorage.getItem('j2bar')") == "0"
    browser.reload()
    browser.wait_for("HomePage.state().loaded === true")
    assert not shown(browser, "#rail")


# ---------------------------------------------------------------------------------------------------------------------
# settings: Appearance
# ---------------------------------------------------------------------------------------------------------------------
@browser_only
def test_appearance_sets_the_theme_for_both_pages_and_keeps_it(browser, fake):
    load(browser, fake)
    browser.click('#rail [data-pane="settings"][data-group="appearance"]')
    present(browser, '[data-themepick="light"]')
    assert browser.js("document.documentElement.dataset.theme") == "dark"                  # dark is the default
    browser.click('[data-themepick="light"]')
    assert browser.js("document.documentElement.dataset.theme") == "light"
    assert browser.js("localStorage.getItem('j2theme')") == "light"                         # J2's key: the team pages read it too
    assert attrs(browser, "[data-themepick]", "aria-pressed") == ["true", "false", "false"]
    browser.reload()
    browser.wait_for("HomePage.state().loaded === true")
    assert browser.js("document.documentElement.dataset.theme") == "light"
    browser.click('#rail [data-pane="settings"][data-group="appearance"]')
    browser.click('[data-themepick="system"]')
    assert browser.js("localStorage.getItem('j2theme')") == "system"


# ---------------------------------------------------------------------------------------------------------------------
# settings: Connectors
# ---------------------------------------------------------------------------------------------------------------------
def open_settings(browser, group):
    browser.click(f'#rail [data-pane="settings"][data-group="{group}"]')
    present(browser, f'#pane-settings .setgrp[data-group="{group}"]')


@browser_only
def test_the_connector_rows_have_test_and_only_codex_has_sign_in(browser, fake):
    load(browser, fake)
    open_settings(browser, "connectors")
    assert attrs(browser, ".setconn", "data-provider") == ["claude", "codex"]
    assert texts(browser, ".setconn .setchip") == ["Ready", "Not signed in"]
    assert attrs(browser, ".setconn [data-act=test]", "data-provider") == ["claude", "codex"]
    assert attrs(browser, ".setconn [data-act=signin]", "data-provider") == ["codex"]
    assert not browser.js("/\\bpin\\b/i.test(document.getElementById('set-connectors').innerText)")


@browser_only
def test_test_posts_to_the_provider_and_shows_the_seconds_or_the_servers_sentence(browser, fake):
    load(browser, fake)
    open_settings(browser, "connectors")
    browser.click('.setconn[data-provider="claude"] [data-act="test"]')
    browser.wait_for("document.querySelector('.setconn[data-provider=claude] .settest').dataset.step === 'ok'")
    assert texts(browser, '.setconn[data-provider="claude"] .settest') == ["Worked in 3.2 s"]
    browser.expect_failed("/api/connectors/codex/test", 503)
    browser.click('.setconn[data-provider="codex"] [data-act="test"]')
    browser.wait_for("document.querySelector('.setconn[data-provider=codex] .settest').dataset.step === 'error'")
    assert texts(browser, '.setconn[data-provider="codex"] .settest') == ["Codex is not signed in. Use Sign in on the Codex row."]
    tests = [r for r in posts(fake, "/api/connectors/")]
    assert [(r["path"], r["token"]) for r in tests] == [("/api/connectors/claude/test", True), ("/api/connectors/codex/test", True)]


@browser_only
def test_the_claude_row_shows_its_plan_and_a_meter_per_window_and_takes_another_cli_file(browser, fake):
    """GAP-providers: the plan in words, one bar per usage window, and the folded "Use another file" box that PUTs the path with the token."""
    load(browser, fake)
    open_settings(browser, "connectors")
    assert texts(browser, '.setconn[data-provider="claude"] .setplan') == ["Claude Max, counted against your plan, not billed per call"]
    assert texts(browser, '.setconn[data-provider="claude"] .pml') == ["5-hour", "Weekly"]
    assert texts(browser, '.setconn[data-provider="claude"] .pmp') == ["62%", "81%"]
    assert attrs(browser, '.setconn[data-provider="claude"] .pmw', "data-sev") == ["ok", "warn"]
    assert browser.count('.setconn[data-provider="codex"] .pmeter') == 0
    browser.click('.setconn[data-provider="claude"] .setpathd summary')
    browser.type("#setpath-claude", "/opt/tools/claude")
    browser.click('.setconn[data-provider="claude"] [data-act="set-path"]')
    browser.wait_for("document.querySelector('.setconn[data-provider=claude] .setpath .settest') !== null")
    assert texts(browser, '.setconn[data-provider="claude"] .setpath .settest') == ["Using that file."]
    puts = [r for r in posts(fake, "/api/connectors/") if r["method"] == "PUT"]
    assert [(r["path"], r["token"], r["body"]) for r in puts] == [("/api/connectors/claude/path", True, {"path": "/opt/tools/claude"})]
    assert [e for e in browser.console_errors if not e.startswith("[network]")] == []          # the one network line is the 404 announced above


@browser_only
def test_the_working_folder_group_saves_shows_what_the_model_can_see_and_clears(browser, fake):
    """GAP3-workdir: Settings, Connectors shows the Working folder group: PUT with the token, the top of the folder, a refusal in words, DELETE."""
    browser.expect_failed("/api/connectors/workdir", 422)            # the refusal of a relative path, on purpose
    load(browser, fake)
    open_settings(browser, "connectors")
    present(browser, '#set-workdir .setgrp[data-group="workdir"]')
    assert texts(browser, "#set-workdir h3") == ["Working folder"]
    browser.wait_for("!!document.querySelector('#set-workdir .wdstatus')")
    assert texts(browser, "#set-workdir .wdstatus") == ["No folder is set. Chats run in a private empty folder and cannot see your files."]
    assert texts(browser, "#set-workdir .setsub") == ["What the model can see"]
    browser.type("#setwd", "relative/folder")
    browser.click('#set-workdir [data-act="workdir-save"]')
    browser.wait_for("!!document.querySelector('#set-workdir .seterr')")
    assert texts(browser, "#set-workdir .seterr") == ["Write the full path, starting with / (or ~ for your home folder)"]
    browser.js("document.querySelector('#setwd').value = ''")
    browser.type("#setwd", "/work/proj")
    browser.click('#set-workdir [data-act="workdir-save"]')
    browser.wait_for("document.querySelector('#set-workdir .wdstatus').dataset.state === 'set'")
    assert texts(browser, "#set-workdir .wdstatus") == ["In use: /work/proj"]
    assert texts(browser, "#set-workdir .wdlist li") == ["src/", "README.md"]
    assert texts(browser, "#set-workdir .settest") == ["Saved. The next message in any chat can read this folder."]
    assert browser.js("document.querySelector('#setwd').value") == "/work/proj"
    puts = [r for r in posts(fake, "/api/connectors/workdir") if r["method"] == "PUT"]
    assert [(r["token"], r["body"]) for r in puts] == [(True, {"path": "relative/folder"}), (True, {"path": "/work/proj"})]
    browser.click('#set-workdir [data-act="workdir-clear"]')
    browser.wait_for("document.querySelector('#set-workdir .wdstatus').dataset.state === 'none'")
    assert browser.count("#set-workdir .wdlist") == 0
    deletes = [r for r in posts(fake, "/api/connectors/workdir") if r["method"] == "DELETE"]
    assert [r["token"] for r in deletes] == [True]
    assert [e for e in browser.console_errors if not e.startswith("[network]")] == []


def speed_up_sign_in(browser):
    """The page asks every 2 s; a test asks every 40 ms (the module's own function, with a shorter wait)."""
    browser.js("(() => { const orig = SettingsView.signIn; SettingsView.signIn = (api, o) => orig(api, Object.assign({}, o, {pollMs: 40})); })()")


@browser_only
def test_sign_in_shows_the_link_and_the_code_polls_until_signed_in_and_the_row_follows(browser, fake):
    load(browser, fake)
    open_settings(browser, "connectors")
    speed_up_sign_in(browser)
    browser.click('[data-act="signin"]')
    browser.wait_for("!!document.querySelector('.signin[data-step=\"pending\"] .sicode')")
    assert texts(browser, ".sicode") == ["WXYZ-1234"]
    assert attrs(browser, ".sulink", "href") == ["https://auth.openai.com/codex/device"]
    assert attrs(browser, ".sulink", "target") == ["_blank"]
    browser.wait_for("!!document.querySelector('.signin[data-step=\"signed_in\"]')")
    assert browser.count(".sicode") == 0
    browser.wait_for("document.querySelector('.setconn[data-provider=codex] .setchip').textContent === 'Ready'")        # connector.health made the rows refetch
    polls = [r for r in fake.log("/api/connectors/codex/sign-in") if r["method"] == "GET"]
    assert len(polls) == 3 and all(r["path"] == "/api/connectors/codex/sign-in/si_4f7a9c1e" for r in polls)
    assert browser.console_errors == []


@browser_only
@pytest.mark.parametrize("outcome,words", [("failed", "Sign in did not work. Try again."), ("expired", "The code ran out. Press Sign in for a new one.")])
def test_sign_in_that_fails_or_expires_says_so_and_can_be_started_again(browser, fake, outcome, words):
    load(browser, fake)
    fake.fixture("sign_in", outcome)
    open_settings(browser, "connectors")
    speed_up_sign_in(browser)
    browser.click('[data-act="signin"]')
    browser.wait_for(f"!!document.querySelector('.signin[data-step=\"{outcome}\"]')")
    assert words in texts(browser, ".signin")[0]
    assert not browser.js("document.querySelector('[data-act=signin]').disabled")


@browser_only
def test_cancel_sends_delete_and_stops_the_polling(browser, fake):
    load(browser, fake)
    open_settings(browser, "connectors")
    browser.click('[data-act="signin"]')                                                    # the page's own 2 s wait: Cancel comes first
    present(browser, '[data-act="cancel"]')
    browser.click('[data-act="cancel"]')
    browser.wait_for("!!document.querySelector('.signin[data-step=\"cancelled\"]')")
    deletes = [r for r in posts(fake, "/api/connectors/") if r["method"] == "DELETE"]
    assert [(r["path"], r["token"]) for r in deletes] == [("/api/connectors/codex/sign-in/si_4f7a9c1e", True)]
    assert [r for r in fake.log("/api/connectors/codex/sign-in") if r["method"] == "GET"] == []


@browser_only
def test_a_connector_event_refetches_the_health_once(browser, fake):
    load(browser, fake)
    health = lambda: len([r for r in fake.log("/api/health") if r["method"] == "GET"])      # noqa: E731
    start = health()
    for event, data in (("connector.health", {"provider": "claude", "state": "ok", "until": None, "reason": None}),
                        ("connector.switch", {"session_id": "cs_org", "from": "claude", "to": "codex", "reason": "quota"}),
                        ("connector.mode", {"mode": "live"})):
        fake.emit(event, data)
        assert wait_until(browser, lambda: health() > start), event
        start += 1
        browser.js("new Promise(r => setTimeout(r, 250))")
        assert health() == start, event
    fake.emit("graph.updated")                                                              # an event of another kind leaves it alone
    browser.js("new Promise(r => setTimeout(r, 400))")
    assert health() == start


# ---------------------------------------------------------------------------------------------------------------------
# settings: Engine
# ---------------------------------------------------------------------------------------------------------------------
@browser_only
def test_the_engine_group_shows_editable_fields_and_locked_ones_read_only(browser, fake):
    load(browser, fake)
    open_settings(browser, "engine")
    browser.wait_for("document.querySelectorAll('#set-engine .setfield').length === 37")          # the 37 settings of engine.json (`workspace`, D127, was the 31st; `builder_timeout`, D169, the 32nd; sync 6 added run_templates, auto_reuse, artifact_library, reviewer and reviewer_wait)
    assert browser.count('.setfield[data-locked="false"] input[type="checkbox"]') == 13          # rates slim memory realization change board artifact_schema template_library fixes, then run_templates auto_reuse artifact_library reviewer (sync 6)
    assert browser.count('.setfield[data-locked="false"] select') == 2                          # output and workspace
    assert browser.count('.setfield[data-locked="false"] input[type="number"]') == 12                          # ... the builder time limit (D169) and the reviewer wait (sync 6)
    assert browser.count('.setfield[data-locked="true"]') == 10
    assert browser.count('.setfield[data-locked="true"] input, .setfield[data-locked="true"] select') == 0
    browser.wait_for("document.querySelector('.setfield[data-locked=true] .setlock').textContent.indexOf('/data/sutra-pro/engine.json') >= 0")      # the fake's data folder, read from About's info
    assert set(texts(browser, ".setfield[data-locked=true] .setlock")) == {"edit /data/sutra-pro/engine.json"}
    assert "Changes apply to the next run." in texts(browser, "#set-engine .setnote")[0]
    assert browser.js("document.querySelector('select[data-scope]').value") == ""                 # all teams
    assert [r["query"] for r in fake.log("/api/engine/settings")] == [""]                   # `dept` is left out for all teams


@browser_only
def test_a_saved_change_sends_only_what_changed_in_a_set_unset_body(browser, fake):
    load(browser, fake)
    open_settings(browser, "engine")
    present(browser, '[data-input="budget"]')
    browser.js("(() => { const b = document.querySelector('[data-input=budget]'); b.value = '250'; "
               "const s = document.querySelector('[data-input=rates]'); s.checked = false; })()")
    browser.click('[data-act="save-engine"]')
    browser.wait_for("document.querySelector('#set-engine .setstatus').textContent.indexOf('Saved.') === 0")
    puts = [r for r in posts(fake, "/api/engine/settings")]
    assert len(puts) == 1 and puts[0]["method"] == "PUT" and puts[0]["token"] is True and puts[0]["query"] == ""
    assert puts[0]["body"] == {"set": {"budget": 250, "rates": False}, "unset": []}
    assert browser.js("document.querySelector('[data-input=budget]').value") == "250"       # the answer of the server is what is shown now
    browser.click('[data-act="save-engine"]')                                               # nothing changed: nothing is sent
    browser.js("new Promise(r => setTimeout(r, 200))")
    assert len(posts(fake, "/api/engine/settings")) == 1


@browser_only
def test_going_back_to_the_default_unsets_the_field(browser, fake):
    load(browser, fake)
    open_settings(browser, "engine")
    present(browser, '[data-input="budget"]')
    browser.js("document.querySelector('[data-input=budget]').value = '250'")
    browser.click('[data-act="save-engine"]')
    browser.wait_for("document.querySelector('#set-engine .setstatus').textContent.indexOf('Saved.') === 0")
    browser.js("document.querySelector('[data-input=budget]').value = '100'")               # the default
    browser.click('[data-act="save-engine"]')
    browser.wait_for("document.querySelector('.setfield[data-field=budget]').dataset.source === 'default'")
    assert [r["body"] for r in posts(fake, "/api/engine/settings")] == [{"set": {"budget": 250}, "unset": []}, {"set": {}, "unset": ["budget"]}]


@browser_only
def test_a_team_scope_passes_dept_in_the_query_for_both_calls(browser, fake):
    load(browser, fake, stage="2")
    open_settings(browser, "engine")
    present(browser, "select[data-scope]")
    browser.js("(() => { const s = document.querySelector('select[data-scope]'); s.value = 'web'; s.dispatchEvent(new Event('change', {bubbles: true})); })()")
    browser.wait_for("document.querySelector('#set-engine .setnote').textContent.indexOf('this team only') > 0")
    assert [r["query"] for r in fake.log("/api/engine/settings")] == ["", "dept=web"]
    browser.js("document.querySelector('[data-input=max_cycles]').value = '3'")
    browser.click('[data-act="save-engine"]')
    browser.wait_for("document.querySelector('#set-engine .setstatus').textContent.indexOf('Saved.') === 0")
    put = posts(fake, "/api/engine/settings")[0]
    assert put["query"] == "dept=web" and put["body"] == {"set": {"max_cycles": 3}, "unset": []}
    assert browser.js("document.querySelector('select[data-scope]').value") == "web"


@browser_only
def test_a_refused_value_is_named_beside_its_field_and_stays_in_the_box(browser, fake):
    load(browser, fake)
    open_settings(browser, "engine")
    present(browser, '[data-input="budget"]')
    browser.expect_failed("/api/engine/settings", 422)
    browser.js("document.querySelector('[data-input=budget]').value = '0'")
    browser.click('[data-act="save-engine"]')
    present(browser, '.setfield[data-field="budget"] .seterr')
    assert "budget must be a whole number of at least 1" in texts(browser, '.setfield[data-field="budget"] .seterr')[0]
    assert browser.count('.setfield[data-field="max_cycles"] .seterr') == 0
    assert browser.js("document.querySelector('[data-input=budget]').value") == "0"        # what the owner typed is not thrown away


@browser_only
def test_a_number_that_cannot_be_read_is_refused_on_the_page_without_a_request(browser, fake):
    load(browser, fake)
    open_settings(browser, "engine")
    present(browser, '[data-input="max_cycles"]')
    browser.js("document.querySelector('[data-input=max_cycles]').value = '2.5'")
    browser.click('[data-act="save-engine"]')
    present(browser, '.setfield[data-field="max_cycles"] .seterr')
    assert "whole number" in texts(browser, '.setfield[data-field="max_cycles"] .seterr')[0]
    assert posts(fake, "/api/engine/settings") == []


# ---------------------------------------------------------------------------------------------------------------------
# failures and the event stream
# ---------------------------------------------------------------------------------------------------------------------
@browser_only
def test_every_refusal_has_its_sentence_and_only_the_right_ones_link_to_settings_or_close_the_box(browser, fake):
    load(browser, fake)
    words = browser.js("""(() => [
      HomePage.errorWords({status: 0, code: "network", message: "x"}), HomePage.errorWords({status: 401, code: "bad_token", message: "x"}),
      HomePage.errorWords({status: 503, code: "provider_unavailable", message: "No model."}), HomePage.errorWords({status: 503, code: "cli_missing", message: ""}),
      HomePage.errorWords({status: 429, code: "too_many_pending", message: "x"}), HomePage.errorWords({status: 500, code: "internal", message: "boom"}),
      HomePage.errorWords({status: 409, code: "busy", message: "The team is working."}), HomePage.errorWords({status: 422, code: "validation", message: ""})])()""")
    down, token, unavailable, missing, many, server, busy, empty = words
    assert down == {"text": "The app is not responding. Try again in a moment.", "settings": False, "retry": True}
    assert token == {"text": NO_TOKEN, "settings": False, "blocked": True}
    assert unavailable == {"text": "No model.", "settings": True}
    assert missing == {"text": "No model is available right now.", "settings": True}
    assert many["text"] == "Too many messages are waiting. I answer them one at a time."
    assert server["text"] == "Something went wrong. Try again."                           # a server error is not shown raw
    assert busy["text"] == "The team is working."                                          # the server's own sentence for a 4xx
    assert empty["text"] == "Something went wrong. Try again."


@browser_only
def test_a_refusal_with_a_reason_says_the_reason_so_a_too_long_message_names_its_limit(browser, fake):
    """QA org-chat-teams: a message over 8000 characters came back as 'The request was refused' and the violation's own words were dropped."""
    load(browser, fake)
    too_long = {"violations": [{"path": "body.text", "code": "string_too_long", "message": "String should have at most 8000 characters"}]}
    words = browser.js("""(details => [HomePage.errorWords({status: 422, code: "validation", message: "The request was refused", details: details}),
      HomePage.errorWords({status: 422, code: "validation", message: "The request was refused", details: {violations: [{path: "x", code: "c", message: "  "}]}}),
      HomePage.errorWords({status: 422, code: "validation", message: "The request was refused", details: {}}),
      HomePage.errorWords({status: 500, code: "internal", message: "boom", details: details})])(""" + json.dumps(too_long) + ")")
    assert words[0] == {"text": "The request was refused: String should have at most 8000 characters", "settings": False}
    assert words[1]["text"] == "The request was refused" and words[2]["text"] == "The request was refused"       # no reason given: the server's own sentence, as before
    assert words[3]["text"] == "Something went wrong. Try again."                           # a server fault is still never shown raw
    fake.fail("/api/chats/cs_org/messages", 422, count=1, message="The request was refused", details=too_long)
    browser.expect_failed("/api/chats/cs_org/messages", 422)
    send_text(browser, "x" * 8001)
    browser.wait_for("!document.getElementById('sbanner').hidden")
    assert "String should have at most 8000 characters" in texts(browser, "#sbanner")[0]
    assert browser.js("document.getElementById('sbox').value.length") == 8001                  # nothing is lost: the text stays in the box


@browser_only
def test_a_team_that_is_busy_refuses_the_answer_in_the_servers_words_and_the_card_stays_open(browser, fake):
    load(browser, fake, stage="2")
    sentence = "The team is working. You can write again when it asks you something or is done"
    fake.fail(f"/api/chats/{DEPT_SESSION}/messages", 409, count=1)
    browser.expect_failed(f"/api/chats/{DEPT_SESSION}/messages", 409)
    browser.click('.c-needs [data-act="answer-option"]')
    browser.wait_for("!document.getElementById('sbanner').hidden")
    assert sentence in texts(browser, "#sbanner")[0]
    assert browser.count(".c-needs[data-answered]") == 0 and browser.count('.c-needs [data-act="answer-option"]') == 2
    assert not browser.js("document.getElementById('sbox').disabled")                      # a 409 never closes the box


@browser_only
def test_a_resync_reads_everything_again_and_polling_asks_for_what_changed(browser, fake):
    load(browser, fake)
    counts = lambda path: len([r for r in fake.log(path) if r["path"] == path and r["method"] == "GET"])      # noqa: E731
    paths = ("/api/chart", "/api/chart/changes", "/api/departments", "/api/needs-you", "/api/chats/cs_org/messages", "/api/health")
    start = {p: counts(p) for p in paths}
    fake.emit("server.resync", {"reason": "gap"})
    assert wait_until(browser, lambda: all(counts(p) > start[p] for p in paths))
    mid = {p: counts(p) for p in paths + ("/api/graph",)}
    browser.js("HomePage.poll()")                                                           # what the page asks every 2 s while the stream is down
    assert wait_until(browser, lambda: all(counts(p) > mid[p] for p in ("/api/graph", "/api/chart", "/api/needs-you", "/api/departments", "/api/chats/cs_org/messages")))
    assert counts("/api/health") == mid["/api/health"]                                      # the health is not part of it
    assert browser.console_errors == []


@browser_only
def test_a_message_of_another_chat_marks_its_node_unread_and_a_chat_message_of_the_org_chat_appends(browser, fake):
    load(browser, fake, stage="2")
    fake.emit("chat.message", {"session_id": DEPT_SESSION, "message": {"id": 9, "session_id": DEPT_SESSION, "role": "agent", "who": "identity", "kind": "text",
             "text": "More news", "card": None, "pause": None, "answered_by": None, "task_id": None, "state": "ok", "at": "2026-11-04T10:09:00Z"}})
    present(browser, '.wnode[data-id="web"] .wunread')
    assert "More news" not in browser.js("document.getElementById('smsgs').innerText")      # it is not the org chat's line
    fake.emit("chat.message", {"session_id": "cs_org", "message": {"id": 41, "session_id": "cs_org", "role": "agent", "who": "sutra", "kind": "text",
             "text": "A new line for you", "card": None, "pause": None, "answered_by": None, "task_id": None, "state": "ok", "at": "2026-11-04T10:09:30Z"}})
    browser.wait_for("document.getElementById('smsgs').innerText.indexOf('A new line for you') >= 0")


# ---------------------------------------------------------------------------------------------------------------------
# the comfort of the org chat (GAP-chat-comfort): the reader is never pulled down, the box keeps its words across a reload
# ---------------------------------------------------------------------------------------------------------------------
def org_line(number, text):
    return {"session_id": "cs_org", "message": {"id": number, "session_id": "cs_org", "role": "agent", "who": "sutra", "kind": "text", "text": text, "card": None,
                                                "pause": None, "answered_by": None, "task_id": None, "state": "ok", "at": "2026-11-04T10:09:30Z"}}


def from_bottom(browser):
    return browser.js("(() => { const m = document.getElementById('smsgs'); return m.scrollHeight - m.scrollTop - m.clientHeight; })()")


def no_console_errors(browser):
    assert browser.console_errors == []


@browser_only
def test_a_reader_who_scrolls_up_on_home_stays_put_and_a_pill_counts_what_came_below(browser, fake):
    load(browser, fake, stage="2")
    for n in range(100, 125):
        fake.emit("chat.message", org_line(n, f"Line {n} " + "text " * 25))
    browser.wait_for("document.getElementById('smsgs').innerText.includes('Line 124')")
    assert wait_until(browser, lambda: from_bottom(browser) < 4) and browser.js("document.getElementById('sjump').hidden") is True
    browser.js("const m = document.getElementById('smsgs'); m.dispatchEvent(new WheelEvent('wheel', {deltaY: -120, bubbles: true})); m.scrollTop = 200;")
    browser.js("new Promise(r => setTimeout(r, 200))")
    fake.emit("chat.message", org_line(125, "Line 125"))
    browser.wait_for("document.getElementById('smsgs').innerText.includes('Line 125')")
    browser.wait_for("!document.getElementById('sjump').hidden")
    assert abs(browser.js("document.getElementById('smsgs').scrollTop") - 200) <= 2              # Home no longer pulls the reader down
    assert texts(browser, "#sjump .cjump-btn") == ["1 new message below"]
    browser.click("#sjump .cjump-btn")
    browser.wait_for("(() => { const m = document.getElementById('smsgs'); return m.scrollHeight - m.scrollTop - m.clientHeight < 4; })()")
    assert browser.js("document.getElementById('sjump').hidden") is True
    browser.js("document.getElementById('smsgs').scrollTop = 100")                                 # reading again, then the owner writes
    browser.js("new Promise(r => setTimeout(r, 200))")
    send_text(browser, "And the menu?")
    browser.wait_for("Array.from(document.querySelectorAll('#smsgs .sb.me')).some(e => e.textContent.includes('And the menu?'))")
    assert wait_until(browser, lambda: from_bottom(browser) < 4)                                    # the owner's own line is in view
    no_console_errors(browser)


@browser_only
def test_the_org_chats_box_keeps_its_words_across_a_reload_and_an_accepted_send_clears_them(browser, fake):
    load(browser, fake)
    browser.type("#sbox", "A website for my bakery,\nwith a menu")
    browser.reload()
    browser.wait_for("window.HomePage && HomePage.state().loaded === true")
    assert browser.js("document.getElementById('sbox').value") == "A website for my bakery,\nwith a menu"
    assert browser.js("document.getElementById('sbox').getBoundingClientRect().height") > 56
    browser.click("#ssend")
    browser.wait_for("document.getElementById('sbox').value === ''")
    assert browser.js("localStorage.getItem('sutra:draft:cs_org')") is None
    browser.reload()
    browser.wait_for("window.HomePage && HomePage.state().loaded === true")
    assert browser.js("document.getElementById('sbox').value") == ""
    no_console_errors(browser)


@browser_only
def test_enter_that_confirms_an_ime_candidate_sends_nothing_until_the_second_enter(browser, fake):
    """QA direct-chat bug 2: a Chinese, Japanese or Korean typist presses Enter to confirm a candidate; the box must not send the half-written line."""
    load(browser, fake)
    browser.js("document.getElementById('sbox').focus()")
    browser._send("Input.imeSetComposition", {"text": "にほんご", "selectionStart": 4, "selectionEnd": 4})
    browser.press("Enter")                                                                 # keydown with isComposing: it only confirms the candidate
    assert posts(fake, "/api/chats/cs_org/messages") == []
    assert browser.count("#smsgs .sb.me") == 0
    browser.js("(() => { const b = document.getElementById('sbox'); b.value = 'にほんご'; b.dispatchEvent(new Event('input', {bubbles: true})); })()")
    browser.press("Enter")                                                                 # the second Enter (no composition) sends
    browser.wait_for("document.querySelectorAll('#smsgs .sb.me').length >= 1")
    assert [r["body"] for r in posts(fake, "/api/chats/cs_org/messages")] == [{"text": "にほんご"}]
    no_console_errors(browser)
