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


# D257: the Budget chip is a pill beside Go and a popover that opens below it (R1-8: above, it covered the text box). What the layout must keep,
# open or closed: the row's height, the hint on its one line, and the popover inside the window and below the pill.
LAYOUT_JS = """((row, hint) => {
  const r = document.querySelector(row), h = document.querySelector(hint), pill = r.querySelector('.bchippill'), pop = r.querySelector('.bchippop');
  const box = e => e.getBoundingClientRect(), fs = parseFloat(getComputedStyle(h).fontSize);
  const shown = !!pop && !pop.hidden && getComputedStyle(pop).display !== 'none';
  return {row: box(r).height, hintOneLine: box(h).height < 1.8 * fs, pill: pill.textContent.trim().replace(/\\s+/g, ' '), expanded: pill.getAttribute('aria-expanded'),
          shown, position: pop ? getComputedStyle(pop).position : '', below: shown ? box(pop).top >= box(pill).bottom : null,
          inside: shown ? box(pop).left >= 0 && box(pop).top >= 0 && box(pop).right <= innerWidth : null,
          focus: document.activeElement ? (document.activeElement.className + '|' + (document.activeElement.dataset.usd || document.activeElement.dataset.custom || '')) : ''};
})(%s, %s)"""


def chip_layout(browser, row, hint):
    return browser.js(LAYOUT_JS % (q(row), q(hint)))


def check_open_and_closed(browser, screens_dir, page, row, hint):
    """The closed pill and the open popover, with a screenshot of each in tests/ui/screens (git-ignored)."""
    closed = chip_layout(browser, row, hint)
    assert closed["pill"] == "$20 budget ▾" and closed["expanded"] == "false" and closed["shown"] is False and closed["hintOneLine"] is True, closed
    browser.shot(screens_dir / f"budget-chip__{page}__closed.png")
    browser.click(f"{row} .bchippill")
    opened = chip_layout(browser, row, hint)
    assert opened["expanded"] == "true" and opened["shown"] is True and opened["position"] == "absolute", opened
    assert opened["row"] == closed["row"] and opened["hintOneLine"] is True, (closed, opened)          # the popover floats: nothing under it moves
    assert opened["below"] is True and opened["inside"] is True, opened
    assert opened["focus"] == "bchippick|20", opened                                                   # focus moves in, to the default
    words = browser.js(f"document.querySelector({q(row + ' .bchippop')}).innerText").split("\n")
    assert [w.strip() for w in words if w.strip()][0] == "Run budget"
    assert texts(browser, f"{row} .bchippick") == ["$10", "$20 default", "$40", "Custom"]
    assert texts(browser, f"{row} .bchipnote") == ["Asks before going over · estimated at API prices, not billed."]
    browser.shot(screens_dir / f"budget-chip__{page}__open.png")
    browser.press("Escape")
    shut = chip_layout(browser, row, hint)
    assert shut["shown"] is False and shut["expanded"] == "false" and shut["focus"] == "bchippill|", shut      # Esc closes and gives focus back
    return closed


@browser_only
def test_home_chip_is_a_pill_and_a_popover_that_never_moves_the_footer(browser, fake, screens_dir):
    load(browser, fake, stage="1")
    browser.wait_for("document.querySelector('#fdbudget .bchippill') !== null")
    assert "credit" not in browser.js("document.querySelector('.fdcompose').innerText").lower()
    check_open_and_closed(browser, screens_dir, "home", ".fdcfoot", ".fdtry")
    browser.click("#fdbudget .bchippill")
    browser.click(".fdtitle")                                                         # a click outside closes it
    assert chip_layout(browser, ".fdcfoot", ".fdtry")["shown"] is False
    assert browser.console_errors == []


@browser_only
def test_home_chip_popover_stays_on_a_phone_screen(browser, fake):
    """R1-8: at 390 px the open popover sits below the pill and inside the screen (its left edge was at -1 px), with no sideways scroll."""
    browser.set_size(390, 844)
    load(browser, fake, stage="1")
    browser.wait_for("document.querySelector('#fdbudget .bchippill') !== null")
    browser.click("#fdbudget .bchippill")
    opened = chip_layout(browser, ".fdcfoot", ".fdtry")
    assert opened["shown"] is True and opened["below"] is True and opened["inside"] is True, opened
    assert browser.js("document.documentElement.scrollWidth <= window.innerWidth + 1")


# The Custom pill, picked, is the box: its place, height and radius in the one row of pills. Focus is the accent border and a ring that follows the
# radius (no rectangular outline); a bad amount is the --s-bad border and a line under the row that describes the box.
CUSTOM_JS = """((root) => {
  const pop = document.querySelector(root + ' .bchippop'), row = pop.querySelector('.bchiprow'), pick = row.querySelector('.bchippick');
  const box = row.querySelector('.bchipcustom'), own = box.querySelector('.bchipown'), err = pop.querySelector('.bchiperr');
  const r = e => e.getBoundingClientRect(), cs = e => getComputedStyle(e), tok = n => cs(pop).getPropertyValue(n).trim();
  const rgb = c => { const d = document.createElement('i'); d.style.color = c; document.body.appendChild(d); const v = cs(d).color; d.remove(); return v; };
  return {last: row.lastElementChild === box, kids: row.children.length, sameRow: Math.abs(r(box).top - r(pick).top) < 1,
          height: [Math.round(r(box).height), Math.round(r(pick).height)], radius: [cs(box).borderTopLeftRadius, cs(pick).borderTopLeftRadius],
          rowFits: r(row).height < 1.6 * r(pick).height, prefix: box.textContent.trim(), placeholder: own.placeholder,
          focused: document.activeElement === own, outline: cs(own).outlineStyle + ' ' + cs(own).outlineWidth,
          border: cs(box).borderTopColor, ring: cs(box).boxShadow, accent: rgb(tok('--s-accent')), bad: rgb(tok('--s-bad')),
          invalid: own.getAttribute('aria-invalid'), describedby: own.getAttribute('aria-describedby'), errId: err.id,
          errShown: !err.hidden && cs(err).display !== 'none', errText: err.textContent, errBelow: r(err).top >= r(row).bottom,
          inside: r(pop).left >= 0 && r(pop).right <= innerWidth, noScroll: document.documentElement.scrollWidth <= innerWidth + 1};
})(%s)"""


def custom_look(browser, root):
    return browser.js(CUSTOM_JS % q(root))


@browser_only
@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("width", [390, 1280])
def test_home_custom_pill_is_the_box(browser, fake, screens_dir, theme, width):
    browser.set_theme(theme)
    browser.set_size(width, 844)
    load(browser, fake, stage="1")
    browser.wait_for("document.querySelector('#fdbudget .bchippill') !== null")
    browser.click("#fdbudget .bchippill")
    browser.click("#fdbudget [data-custom]")
    got = custom_look(browser, "#fdbudget")
    assert got["last"] and got["kids"] == 4 and got["sameRow"] and got["rowFits"], got                 # the 4th pill, in the one row: no second row
    assert got["height"][0] == got["height"][1] and got["radius"][0] == got["radius"][1], got
    assert got["prefix"] == "$" and got["placeholder"] == "amount" and got["focused"], got
    assert got["outline"].split()[0] == "none" or got["outline"].endswith(" 0px"), got                  # no rectangular outline
    assert got["border"] == got["accent"] and got["accent"] in got["ring"], got                         # the pill's own border and a ring
    assert got["invalid"] is None and got["errShown"] is False and got["inside"] and got["noScroll"], got
    browser.shot(screens_dir / f"budget-chip__home__{theme}__{width}__custom.png")
    browser.type("#fdbudget .bchipown", "0.5")
    bad = custom_look(browser, "#fdbudget")
    assert bad["invalid"] == "true" and bad["describedby"] == bad["errId"] and bad["errShown"] and bad["errBelow"], bad
    assert bad["errText"] == "Dollars from $1 to $10,000" and bad["border"] == bad["bad"] and bad["bad"] in bad["ring"], bad
    assert bad["sameRow"] and bad["rowFits"] and bad["inside"] and bad["noScroll"], bad
    browser.shot(screens_dir / f"budget-chip__home__{theme}__{width}__custom-bad.png")
    browser.js("document.querySelector('#fdbudget .bchipown').value = ''")
    browser.type("#fdbudget .bchipown", "12")
    ok = custom_look(browser, "#fdbudget")
    assert ok["invalid"] is None and ok["describedby"] is None and ok["errShown"] is False and ok["border"] == ok["accent"], ok
    assert browser.console_errors == []


@browser_only
def test_home_chip_sends_dollars_once_and_nothing_for_the_default(browser, fake):
    """D257: nothing is sent for the default; a pick or a typed amount rides with the next request only as usd_budget; Custom applies as you type and a
    bad amount marks the box and changes nothing."""
    load(browser, fake, stage="1")
    browser.wait_for("document.querySelector('#fdbudget .bchippill') !== null")
    pill = lambda: texts(browser, "#fdbudget .bchippill")[0]
    browser.click("#fdbudget .bchippill")
    browser.click('#fdbudget [data-custom]')
    assert browser.js("document.activeElement.className") == "bchipown"
    browser.type("#fdbudget .bchipown", "0.5")
    assert browser.js("document.querySelector('#fdbudget .bchipown').getAttribute('aria-invalid')") == "true" and pill() == "$20 budget ▾"
    browser.js("document.querySelector('#fdbudget .bchipown').value = ''")
    browser.type("#fdbudget .bchipown", "12.50")
    assert browser.js("document.querySelector('#fdbudget .bchipown').getAttribute('aria-invalid')") is None and pill() == "$12.50 budget ▾"
    assert browser.js("document.activeElement.className") == "bchipown"                # it applied without a redraw: the box keeps the caret
    browser.js("document.querySelector('#fdbudget .bchipown').value = ''")
    browser.type("#fdbudget .bchipown", "0.5")                                          # back to a bad amount: $12.50 stays
    assert pill() == "$12.50 budget ▾"
    browser.click('#fdbudget [data-usd="20"]')                                         # back to the default: nothing is sent for it
    assert pill() == "$20 budget ▾" and not browser.exists("#fdbudget .bchipown")
    browser.type("#fdbox", "A website for my cafe")
    browser.click("#fdsend")
    browser.wait_for("document.querySelector('#fdlatest .fdlatest') !== null")
    browser.wait_for("document.getElementById('fdbox').value === ''")
    browser.wait_for("document.querySelector('#fdbudget .bchippill').textContent.indexOf('$20 budget') === 0")
    browser.click("#fdbudget .bchippill")
    browser.click('#fdbudget [data-usd="40"]')
    assert pill() == "$40 budget ▾" and browser.js("document.activeElement.className") == "bchippill"
    browser.type("#fdbox", "A bakery page")
    browser.click("#fdsend")
    browser.wait_for("document.querySelector('#fdbudget .bchippill').textContent.indexOf('$20 budget') === 0")
    browser.wait_for("document.getElementById('fdbox').value === ''")
    sent = [r["body"] for r in posts(fake, "/api/chats/cs_org/messages")]
    assert sent == [{"text": "A website for my cafe"}, {"text": "A bakery page", "usd_budget": 40}]


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
def test_home_stop_after_send(browser, fake):
    """D254: while the card shows the work this box started and its team's task is live, Go is Stop (box empty); typing turns it back into
    Go; Stop asks first and on yes calls the stop ladder once with {} (no force); the team's task ends and Go is back."""
    load(browser, fake)                                                                # stage 2: the Web team's task tsk_a1b2c3d4e5f6 is live
    browser.js("""(() => { const S = HomePage.state(); S.front.sent = true; S.front.going = true;      // stay on Home (no landing)
      S.messages.push({id: 900, role: "user", text: "A website for my cafe"}, {id: 901, role: "agent", text: "", card: {type: "task", dept_id: "web", dept_name: "Web", title: "A website for my cafe"}});
      HomePage.renderFront(); })()""")
    assert texts(browser, "#fdsend") == ["Stop"] and browser.js("document.getElementById('fdsend').getAttribute('aria-label')") == "Stop the run"
    browser.type("#fdbox", "more")
    assert texts(browser, "#fdsend") == ["Go"]
    browser.js("(() => { const b = document.getElementById('fdbox'); b.value = ''; b.dispatchEvent(new Event('input')); })()")
    assert texts(browser, "#fdsend") == ["Stop"]
    browser.js("window.ASKED = []; window.confirm = q => { ASKED.push(q); return false; }")
    browser.click("#fdsend")
    assert browser.js("ASKED") == ["Stop this run? What's built so far is kept."] and not posts(fake, "/api/tasks/")
    browser.js("window.confirm = q => { ASKED.push(q); return true; }")
    browser.click("#fdsend")
    browser.wait_for("document.getElementById('fdsend').textContent.trim() === 'Go'")
    sent = posts(fake, "/api/tasks/")
    assert [(r["path"], r["body"], r["token"]) for r in sent] == [("/api/tasks/tsk_a1b2c3d4e5f6/stop", {}, True)]
    assert browser.console_errors == []


@browser_only
def test_needs_you_raise_input(browser, fake):
    """D257: a dollar raise question on Home's Needs you card takes a typed amount (the suggested one filled in) and answers the team with
    "Add $N and keep going"; a bad amount marks the box and sends nothing."""
    load(browser, fake)
    browser.wait_for("document.querySelector('#fdattn .fdcard') !== null")
    browser.js("""(() => { const S = HomePage.state(); S.needs = [{message_id: 77, session_id: "%s", kind: "question", dept_id: "web", dept_name: "Web",
      text: "@Requester The site isn't finished yet.\\nThis run has used $20.40 of $20 (API price). Add $10? So far: $20 approved.\\n   Option 1: Add $10 and keep going: more. Or type your own amount [adds $10]\\n   Option 2: Finish as it is",
      options: [], asked_at: "2026-11-12T10:00:00Z", waiting_s: 30, stale: false}]; HomePage.renderFront(); })()""" % DEPT_SESSION)
    browser.wait_for("document.querySelector('#fdattn .bchipraisein') !== null")
    assert browser.js("document.querySelector('#fdattn .bchipraisein').value") == "$10"
    assert "credit" not in browser.js("document.getElementById('fdattn').innerText").lower()
    browser.js("document.querySelector('#fdattn .bchipraisein').value = 'lots'")
    browser.click("#fdattn [data-act=fd-raise]")
    assert browser.js("document.querySelector('#fdattn .bchipraisein').getAttribute('aria-invalid')") == "true" and not posts(fake, f"/api/chats/{DEPT_SESSION}/messages")
    browser.js("document.querySelector('#fdattn .bchipraisein').value = '$25'")
    browser.click("#fdattn [data-act=fd-raise]")
    browser.wait_for("Object.values(HomePage.state().answers).includes('Add $25 and keep going')")
    sent = posts(fake, f"/api/chats/{DEPT_SESSION}/messages")
    assert [r["body"] for r in sent] == [{"text": "Add $25 and keep going"}]


@browser_only
def test_needs_you_raise_input_survives_a_repaint(browser, fake):
    """R1-6: a typed raise not yet sent is held like a half-typed answer: the per-minute repaint (or any event) neither replaces it with the
    suggested amount nor takes the focus away."""
    load(browser, fake)
    browser.wait_for("document.querySelector('#fdattn .fdcard') !== null")
    browser.js("""(() => { const S = HomePage.state(); S.needs = [{message_id: 77, session_id: "%s", kind: "question", dept_id: "web", dept_name: "Web",
      text: "@Requester The site isn't finished yet.\\nThis run has used $20.40 of $20 (API price). Add $10? So far: $20 approved.\\n   Option 1: Add $10 and keep going: more. Or type your own amount [adds $10]\\n   Option 2: Finish as it is",
      options: [], asked_at: "2026-11-12T10:00:00Z", waiting_s: 30, stale: false}]; HomePage.renderFront(); })()""" % DEPT_SESSION)
    browser.wait_for("document.querySelector('#fdattn .bchipraisein') !== null")
    browser.js("(() => { const i = document.querySelector('#fdattn .bchipraisein'); i.focus(); i.value = '$25'; })()")
    browser.js("(() => { const S = HomePage.state(); S.needsAt = Date.now() - 3600 * 1000; HomePage.renderFront(); })()")
    assert browser.js("document.querySelector('#fdattn .bchipraisein').value") == "$25"
    assert browser.js("document.activeElement === document.querySelector('#fdattn .bchipraisein')") is True
    browser.js("document.querySelector('#fdattn .bchipraisein').blur()")      # left as suggested: the repaint goes on as before
    browser.js("(() => { const i = document.querySelector('#fdattn .bchipraisein'); i.focus(); i.value = '$10'; HomePage.renderFront(); })()")
    assert browser.js("HomePage.state().front.held") is False


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



@browser_only
def test_team_chip_is_the_same_pill_and_popover_on_the_start_form(browser, fake, screens_dir):
    """The team page's start form (port edit E25) mounts the same component. The fake's captured team always has a chat, so J2 shows the studio, not the
    start page: the test wraps J2's renderSimple to keep the start page on screen, as a team with no request yet has it."""
    load(browser, fake, path="/d/web/?view=simple")
    browser.wait_for("window.DeptExt !== undefined && DeptExt.state().started === true && document.querySelector('#lbudget .bchippill') !== null")
    browser.js("(() => { const own = renderSimple; window.renderSimple = s => { own(s); document.getElementById('sland').hidden = false; "
               "document.getElementById('swork').hidden = true; }; document.getElementById('sland').hidden = false; document.getElementById('swork').hidden = true; })()")
    browser.wait_for("document.getElementById('lform').offsetParent !== null")
    check_open_and_closed(browser, screens_dir, "team", "#lform .sbrow", "#schips")
    browser.click("#lbudget .bchippill")
    browser.click('#lbudget [data-custom]')
    browser.type("#lbudget .bchipown", "25")
    got = custom_look(browser, "#lbudget")                                             # the Custom pill is the box here too: J2's own #sview focus
    assert got["last"] and got["sameRow"] and got["height"][0] == got["height"][1] and got["radius"][0] == got["radius"][1], got   # rectangle is not drawn
    assert got["focused"] and got["outline"].split()[0] == "none" and got["border"] == got["accent"] and got["accent"] in got["ring"], got
    browser.shot(screens_dir / "budget-chip__team__custom.png")
    browser.press("Enter")                                                             # Enter in the box closes the popover and never sends the form
    assert texts(browser, "#lbudget .bchippill") == ["$25 budget ▾"] and not [r for r in posts(fake, "/api/say")]
    assert browser.js("document.activeElement.className") == "bchippill"
    assert browser.console_errors == []
