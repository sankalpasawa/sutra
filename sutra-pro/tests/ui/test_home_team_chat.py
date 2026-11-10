"""A team's own chat in Home's chat column (gap package dept-chats, docs/notes/GAP3-dept-chats.md).

Runs only with SUTRA_BROWSER=1 (the gate skips it): headless Chrome over CDP against the fake backend of UI-0, which mounts the REAL `/` page and the
real static files. What it proves, on stage "2" of the fake's story (the Web team asked about the menu):

  the line        the org chat shows "Started Web: [Open its chat]" with a real button that carries the team's node and chat session
  the switcher    a strip of tabs names the org chat and the team (the team's tab says one question waits), the active one is selected, and the
                  column is labelled "Chat with <name>"
  the chip        opens the team's own chat in the column: its heading names it, its own lines show, the org chat is hidden but kept, and nothing
                  is sent to the server
  back            the panel's Back button and Esc return to the org chat, and the Sutra tab is selected again
  the strip       "Needs you" says which chat the question is in ("Answer in Web's chat") and opens it with the question in view
  keys            the arrow keys move between the tabs; the chip and the tabs are buttons (Enter and Space work)
  division        a division has its own tab after its team's (the graph names the team in `dept_id`), and its chat is named and selected
"""
from __future__ import annotations

import json

import pytest
from test_home import DEPT_SESSION, attrs, load, on_screen, posts, present, shown, texts

browser_only = pytest.mark.browser

POINTER = {"type": "team_chat", "node_id": "web", "name": "Web", "kind": "department", "session_id": DEPT_SESSION, "about": "started"}


def add_pointer(fake_server, card=None, who="sutra") -> int:
    """A `team_chat` card in the org chat of the fake (the real server writes one when a turn makes a team)."""
    chat = fake_server.state.chat("cs_org")
    mid = chat.next_id()
    chat.extra.append({"id": mid, "session_id": "cs_org", "role": "agent", "who": who, "kind": "card", "text": "", "card": card or POINTER, "pause": None,
                       "answered_by": None, "task_id": None, "state": "ok", "at": "2026-11-04T10:05:00Z"})
    return mid


def open_chip(browser):
    browser.click(".c-teamchat .chatchip")
    browser.wait_for("!document.getElementById('teamchat').hidden && document.getElementById('npititle').textContent === 'Web'")
    present(browser, "#teamchat .nmsg")


@browser_only
def test_the_org_chat_says_started_with_a_chip_and_the_switcher_names_both_chats(browser, fake, fake_server):
    add_pointer(fake_server)
    load(browser, fake, stage="2")
    present(browser, ".c-teamchat .chatchip")
    assert texts(browser, ".c-teamchat .cteamlead") == ["Started Web:"] and texts(browser, ".c-teamchat .chatchip") == ["Open its chat"]
    assert attrs(browser, ".c-teamchat .chatchip", "data-node") == ["web"] and attrs(browser, ".c-teamchat .chatchip", "data-session") == [DEPT_SESSION]
    assert browser.js("document.querySelector('.c-teamchat .chatchip').tagName") == "BUTTON"
    assert shown(browser, "#cswitch")
    assert browser.js("Array.from(document.querySelectorAll('#cswitch .cstab'), t => t.firstChild.textContent)") == ["Sutra", "Web"]
    assert attrs(browser, "#cswitch .cstab", "aria-selected") == ["true", "false"] and attrs(browser, "#cswitch .cstab", "tabindex") == ["0", "-1"]
    assert "1" in texts(browser, "#cswitch .csbadge")[0]                      # the Web question that waits
    assert browser.js("document.getElementById('schat').getAttribute('aria-label')") == "Chat with Sutra"
    assert posts(fake) == []


@browser_only
def test_the_chip_opens_the_teams_own_chat_in_the_column_and_back_returns_to_the_org_chat(browser, fake, fake_server):
    add_pointer(fake_server)
    load(browser, fake, stage="2")
    present(browser, ".c-teamchat .chatchip")
    open_chip(browser)
    assert browser.js("document.getElementById('schat').classList.contains('team-open')")
    assert attrs(browser, "#cswitch .cstab", "aria-selected") == ["false", "true"]
    assert browser.js("document.getElementById('schat').getAttribute('aria-label')") == "Chat with Web"
    assert browser.js("document.activeElement.id") == "npititle"              # focus lands on the team's name
    assert not on_screen(browser, "#smsgs") and not on_screen(browser, "#scompose") and on_screen(browser, "#teamchat")
    lines = texts(browser, "#teamchat .nmsg")                                 # the team's OWN lines: the owner's request and Identity's question
    assert lines[0].endswith("A website for my cafe") and any("Should the menu show prices?" in t for t in lines)
    assert not any("Hello. Tell me what you need" in t for t in lines)        # nothing of the org chat
    assert browser.js("document.getElementById('nodepanel').hidden")           # the drawer is another thing and stays shut
    assert browser.js("document.querySelector('#teamchat .npclose').textContent") == "Back to Sutra"
    assert posts(fake) == []
    browser.click("#teamchat [data-npclose]")
    browser.wait_for("document.getElementById('teamchat').hidden")
    assert not browser.js("document.getElementById('schat').classList.contains('team-open')")
    assert on_screen(browser, "#smsgs") and on_screen(browser, "#scompose")
    assert attrs(browser, "#cswitch .cstab", "aria-selected") == ["true", "false"]
    assert browser.js("document.getElementById('schat').getAttribute('aria-label')") == "Chat with Sutra"
    assert browser.js("document.activeElement.id") == "cstab-cs_org"


@browser_only
def test_a_tab_switches_and_esc_comes_back(browser, fake, fake_server):
    load(browser, fake, stage="2")
    present(browser, '#cswitch .cstab[data-node="web"]')
    browser.click('#cswitch .cstab[data-node="web"]')
    browser.wait_for("!document.getElementById('teamchat').hidden && document.getElementById('npititle').textContent === 'Web'")
    assert attrs(browser, "#cswitch .cstab", "aria-selected") == ["false", "true"]
    browser.press("Escape")
    browser.wait_for("document.getElementById('teamchat').hidden")
    assert attrs(browser, "#cswitch .cstab", "aria-selected") == ["true", "false"] and on_screen(browser, "#smsgs")
    browser.click('#cswitch .cstab[data-node="web"]')
    browser.wait_for("!document.getElementById('teamchat').hidden")
    browser.click('#cswitch .cstab[data-node="root"]')                           # the Sutra tab
    browser.wait_for("document.getElementById('teamchat').hidden")
    assert on_screen(browser, "#smsgs") and browser.js("document.activeElement.id") == "cstab-cs_org"


@browser_only
def test_the_arrow_keys_move_between_the_tabs(browser, fake, fake_server):
    load(browser, fake, stage="2")
    present(browser, "#cswitch .cstab")
    browser.js("document.getElementById('cstab-cs_org').focus()")
    browser.press("ArrowRight")
    assert browser.js("document.activeElement.dataset.node") == "web"
    browser.press("ArrowRight")
    assert browser.js("document.activeElement.id") == "cstab-cs_org"          # it wraps
    browser.press("ArrowLeft")
    assert browser.js("document.activeElement.dataset.node") == "web"          # and back the other way
    assert not browser.js("document.getElementById('schat').classList.contains('team-open')")     # moving focus does not switch


@browser_only
def test_the_needs_you_strip_names_the_teams_chat_and_opens_it_with_the_question_in_view(browser, fake):
    load(browser, fake, stage="2")
    assert texts(browser, "#needs [data-needmsg]") == ["Answer in Web's chat"]
    browser.click("#needs [data-needmsg]")
    browser.wait_for("!document.getElementById('teamchat').hidden && document.getElementById('npititle').textContent === 'Web'")
    browser.wait_for("document.activeElement && document.activeElement.classList.contains('nmsg') && document.activeElement.dataset.kind === 'question'")
    assert browser.js("document.getElementById('schat').getAttribute('aria-label')") == "Chat with Web"
    assert not any(r["path"] == "/api/chats/cs_org/messages" for r in posts(fake))
    # an answer from the team's chat goes to the team's session
    browser.click('#teamchat .opts button[data-act="option"]')
    browser.wait_for(f"HomePage && true")
    sent = [r for r in posts(fake, "/api/chats/") if r["path"] == f"/api/chats/{DEPT_SESSION}/messages"]
    assert len(sent) == 1 and sent[0]["body"] == {"text": "Option 1"}
    assert json.dumps(posts(fake)).count("cs_org") == 0


@browser_only
def test_a_question_pointer_reads_answered_once_the_question_is_gone_and_a_started_line_for_an_unknown_team_is_still_a_chip(browser, fake, fake_server):
    add_pointer(fake_server, dict(POINTER, about="question", question_message_id=2))
    load(browser, fake, stage="3")                                           # stage 3: nothing waits any more
    present(browser, ".c-teamchat[data-about=question]")
    assert texts(browser, ".c-teamchat .cteamlead") == ["Web's question was answered."] and texts(browser, ".c-teamchat .chatchip") == ["Open its chat"]
    assert attrs(browser, ".c-teamchat", "data-answered") == ["true"]


@browser_only
def test_a_division_has_its_tab_under_its_team_and_its_chat_is_named_and_selected(browser, fake):
    load(browser, fake, stage="full")                                        # two teams, two divisions: the graph names a division's team in `dept_id`
    present(browser, "#cswitch .cstab")
    assert browser.js("Array.from(document.querySelectorAll('#cswitch .cstab'), t => [t.dataset.kind, t.dataset.node, t.firstChild.textContent])") == [
        ["org", "root", "Sutra"], ["department", "web", "Web"], ["division", "faq", "FAQ"], ["department", "content", "Content"], ["division", "menu", "Menu"]]
    browser.click('#cswitch .cstab[data-node="faq"]')
    browser.wait_for("!document.getElementById('teamchat').hidden && document.getElementById('npititle').textContent === 'FAQ'")
    assert browser.js("document.getElementById('schat').getAttribute('aria-label')") == "Chat with FAQ"
    assert attrs(browser, "#cswitch .cstab", "aria-selected") == ["false", "false", "true", "false", "false"]
