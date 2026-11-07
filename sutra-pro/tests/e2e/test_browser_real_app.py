"""The browser walk against the REAL app (GAP-E2E-UI, G06): the first-day walk of tests/ui/test_browser_smoke.py, run in a headless Chrome
against `create_app` + the real engine process on a temp data folder (the GAP-E2E harness), instead of the fake backend of UI-0.

Runs only with SUTRA_BROWSER=1. One owner, one Chrome, one document for the first half: Home start page, a brief, the progress, `chart_change`
and `task` cards, the graph that draws the new team, a read-only function node, Identity's question card, the answer typed in that card, the steps that turn
green in the same document from `atom.updated` + `graph.updated`, the `Done` card; then the team's J2 page (`/d/web/`: Detailed view, Map, the
Library tab with the run's template copies, Workflow graph, Org chart) and Home's Settings (Engine edit, Connectors Test of the stub). Zero console errors
and zero failed requests are checked after EVERY step, which fails on any CSP violation or a 4xx/5xx the real routes answer.
What the real app changes against the fake: the page's token is the real per-launch one (every write goes through `require_token`), the SSE
stream is the real one, and the cards, statuses and atoms come from the projector, not from fixtures.

Run it: `SUTRA_BROWSER=1 scripts/py -m pytest tests/e2e/test_browser_real_app.py tests/e2e/test_browser_resync.py -q`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from harness import ANSWER, ORG, FakeCliBin, LiveApp, new_team_script

from sutra_app.orchestrator.testing.scripted import ScriptedConnector

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ui"))      # `import cdp` (tests/ui has no __init__.py and its conftest is not loaded here)
import cdp  # noqa: E402

BRIEF = "A website for my cafe"                       # one of J2's four example briefs: vague, so Identity asks before it starts
PROGRESS = ["Reading the org chart", "Checking the model library", "Planning", "Setting up the team", "Done"]


def q(css: str) -> str:
    return json.dumps(css)


def texts(browser, css):
    return browser.js(f"Array.from(document.querySelectorAll({q(css)}), e => e.textContent.trim().replace(/\\s+/g, ' '))")


def attrs(browser, css, name):
    return browser.js(f"Array.from(document.querySelectorAll({q(css)}), e => e.getAttribute({q(name)}))")


def present(browser, css, timeout=10.0):
    browser.wait_for(f"!!document.querySelector({q(css)})", timeout=timeout)


def shown(browser, css) -> bool:
    return browser.js(f"(() => {{ const e = document.querySelector({q(css)}); return !!e && !e.hidden && e.offsetParent !== null; }})()")


def clean(browser, step):
    """After every step: no console error (a CSP violation is one) and no failed request."""
    assert browser.console_errors == [], f"{step}: console errors {browser.console_errors}"
    assert browser.failed_requests == [], f"{step}: failed requests {browser.failed_requests}"


@pytest.fixture()
def browser():
    chrome = cdp.find_chrome()
    if chrome is None:
        pytest.skip("Chrome is not installed (set SUTRA_CHROME to its path)")
    with cdp.Browser(chrome) as instance:
        yield instance
        assert not instance.failed_requests, f"requests failed during the test (announce them with browser.expect_failed): {instance.failed_requests}"


@pytest.fixture()
def app(tmp_path):
    """The real app, offline with the `stub` connector; the chat agent's model is scripted (the new-team replies); the engine plays J2's mock with
    J2's template library on, so the team's page has a Library tab."""
    live = LiveApp(tmp_path, connector=ScriptedConnector(new_team_script()), extra_env={"J2_TEMPLATE_LIBRARY": "1"}).start()
    try:
        yield live
    finally:
        try:
            live.stop()
        finally:
            live.kill_engines()


@pytest.mark.browser
def test_the_whole_first_day_walk_on_the_real_app(app, browser):
    live = app

    # 1. Home: the start page with J2's four example briefs, the live chip on
    browser.goto(live.base_url + "/")
    browser.wait_for("window.HomePage && HomePage.state().loaded === true")
    browser.wait_for("document.querySelector('#pane-graph .wlive').dataset.state === 'live'")
    assert len(attrs(browser, "[data-brief]", "data-brief")) == 4 and BRIEF in attrs(browser, "[data-brief]", "data-brief")
    assert texts(browser, "#smsgs .nmsg")[0].endswith("Hello. Tell me what you need and I will give it to the right team.")
    clean(browser, "home start page")

    # 2. send a brief: progress, chart_change and task cards, the chart marks "added", the graph draws the team
    browser.js("window.__sameDocument = true")
    browser.click(f'[data-brief="{BRIEF}"]')
    present(browser, ".c-teamchat[data-about=question]:not([data-answered])", timeout=40)    # Identity's question arrives last: the org chat only points at it (GAP3 dept-chats)
    assert texts(browser, "#sprog > div") == PROGRESS
    assert "Added the Web team" in texts(browser, ".c-chart .csum")
    assert texts(browser, ".c-task h2") == ["Your Web team is on it"] and texts(browser, ".c-task .ctitle")[0].startswith("Cafe page")
    assert texts(browser, ".c-teamchat[data-about=started] .cteamlead") == ["Started Web:"]     # the line that says the team has its own chat
    assert [m["text"] for m in live.messages(ORG) if m["role"] == "user"] == [BRIEF]            # the write carried the real token: the server took it
    present(browser, '#pane-graph .wnode[data-id="web"]')
    browser.click('#rail [data-pane="chart"]')
    present(browser, '#pane-chart g.wnode[data-id="web"].mk-add')
    assert browser.js("document.querySelector('#pane-chart g.wnode[data-id=\"web\"] .wtag').textContent") == "added"
    browser.click('#rail [data-pane="graph"]')
    browser.click("#pane-graph [data-wlevel='full']")                                        # Detail: the five function nodes of the team appear
    for fn in ("identity", "adaptation", "priority", "coordination", "audit"):
        present(browser, f'#pane-graph g.wnode[data-id="web.{fn}"]')
    assert browser.js("document.querySelector('#pane-graph g.wnode[data-id=\"web.identity\"]').getAttribute('class')").count("st-waiting_on_you") == 1
    clean(browser, "send a brief")

    # 3. a function node that is not Identity: read-only chat, then Details (goal, task, context, atoms, constraints, hands)
    browser.js("document.querySelector('#pane-graph g.wnode[data-id=\"web.adaptation\"]').focus()")        # a box is a button: the keyboard opens it
    browser.press("Enter")
    browser.wait_for("!document.getElementById('nodepanel').hidden && document.getElementById('nptitle').textContent === 'Adaptation'")
    present(browser, ".nnote")
    assert texts(browser, ".nnote") == ["Read-only: this is the working log of Web \u00b7 Adaptation."]
    assert browser.js("document.querySelector('.ncomposer').hidden") is True
    session = live.session_of("web.adaptation")
    assert live.get(f"/api/chats/{session}")["writable"] is False
    browser.click("[data-nptab=details]")
    present(browser, ".fndetail")
    sections = attrs(browser, ".fndetail > .fnsec", "data-sec")
    for wanted in ("goal", "task", "context", "atoms", "constraints", "hands"):
        assert wanted in sections, (wanted, sections)
    assert texts(browser, ".fnsec[data-sec=goal] p")[0] not in ("", "none") and texts(browser, ".fnsec[data-sec=task] .fntask")[0]
    assert texts(browser, ".fnsec[data-sec=context] li") and texts(browser, ".fnsec[data-sec=constraints] li")
    assert texts(browser, ".fnsec[data-sec=hands] .fnto .fnchip")
    clean(browser, "function node details")
    browser.click("[data-npclose]")
    browser.wait_for("document.getElementById('nodepanel').hidden")

    # 4. Identity: its chat shows the owner's brief and the question it asked; the composer is there (Identity is the voice of the team)
    browser.js("document.querySelector('#pane-graph g.wnode[data-id=\"web.identity\"]').focus()")
    browser.press("Enter")
    browser.wait_for("document.getElementById('nptitle').textContent === 'Identity'")
    present(browser, ".nchat .nmsg")
    assert any("a few quick questions" in t for t in texts(browser, ".nchat .nmsg")), texts(browser, ".nchat .nmsg")
    assert browser.js("document.querySelector('.ncomposer').hidden") is False and browser.js("document.querySelector('.nbox').disabled") is False
    clean(browser, "identity chat")
    browser.click("[data-npclose]")
    browser.wait_for("document.getElementById('nodepanel').hidden")

    # 5. Identity's question is answered in the TEAM's own chat (the pointer in the org chat opens it); the steps turn green in the SAME document from
    #    atom.updated + graph.updated, then the Done card
    assert browser.count("#pane-graph g.wnode.st-filed") == 0                                # nothing is filed while Identity waits for the owner
    mark = len(live.sse.snapshot())
    browser.click(".c-teamchat[data-about=question] .chatchip")
    browser.wait_for("!document.getElementById('teamchat').hidden && document.getElementById('npititle').textContent === 'Web'")
    browser.wait_for("Array.from(document.querySelectorAll('#teamchat .nmsg')).some(e => e.textContent.includes('a few quick questions'))")   # the question is in the team's chat
    present(browser, "#teamchat .nbox")
    assert not any("a few quick questions" in t for t in texts(browser, "#smsgs .nmsg"))        # and not in the org chat
    browser.type("#teamchat .nbox", ANSWER)
    browser.click('#teamchat [data-act="send"]')
    browser.wait_for("document.querySelector('.c-teamchat[data-about=question]').dataset.answered === 'true'")
    browser.click("#teamchat [data-npclose]")                                               # back to the org chat for the Done card
    browser.wait_for("document.getElementById('teamchat').hidden")
    answers = [m["text"] for m in live.messages(live.session_of("web")) if m["who"] == "user"]
    assert answers[-1] == ANSWER                                                             # to the department's session, never to the org chat
    present(browser, "#pane-graph g.wnode.st-filed", timeout=60)
    assert browser.js("window.__sameDocument === true")                                      # the same document: nothing reloaded
    after = live.sse.types()[mark:]
    assert "atom.updated" in after and "graph.updated" in after                              # the two events the page re-read the graph and the node for
    present(browser, ".c-done", timeout=60)
    assert browser.js("document.querySelector('.c-done h2').textContent") == "Your Web team is done"
    assert browser.js("document.querySelector('.c-done').dataset.tone") == "ok"
    live.ended(live.rows("SELECT id FROM tasks")[0]["id"], "done")                           # the database agrees with the card
    browser.wait_for("document.querySelector('#pane-graph g.wnode[data-id=\"web.identity\"]').getAttribute('class').includes('st-idle')", timeout=20)
    assert browser.js("window.__sameDocument === true")
    clean(browser, "answer, green steps and Done")

    # 6. Identity's Details now list the atoms the layer filed in the database
    browser.js("document.querySelector('#pane-graph g.wnode[data-id=\"web.identity\"]').focus()")
    browser.press("Enter")
    browser.wait_for("document.getElementById('nptitle').textContent === 'Identity'")
    browser.click("[data-nptab=details]")
    present(browser, ".fnsec[data-sec=atoms]")
    heading = texts(browser, ".fnsec[data-sec=atoms] h4")[0]
    assert heading.startswith("Work atoms (") and heading != "Work atoms (0)", heading
    assert live.one("SELECT count(*) FROM atoms WHERE node_id = 'web.identity'") == int(heading[len("Work atoms ("):-1])
    clean(browser, "identity atoms")
    browser.click("[data-npclose]")

    # 7. Open the team: the J2 page loads offline under its CSP; Detailed view, Map, Library with the run's template copies
    browser.click('.c-done [data-act="open-team"]')
    browser.wait_for("window.DeptExt !== undefined && DeptExt.state().started === true")
    assert browser.js("location.pathname") == "/d/web/" and browser.js("document.title") == "Web · Sutra"
    assert browser.js(f"performance.getEntriesByType('resource').every(e => e.name.startsWith({q(live.base_url)}))")        # offline: every file is the app's own
    clean(browser, "team page")
    browser.click("#to-detail")
    browser.wait_for("!document.body.classList.contains('simple')")
    assert shown(browser, '.tabs [data-tab="map"]')
    browser.click('.tabs [data-tab="map"]')
    present(browser, "#pane-map .mapsvg")
    assert shown(browser, "#pane-map") and not shown(browser, "#pane-library")
    assert browser.js("document.querySelector('.tabs [data-tab=map]').getAttribute('aria-selected')") == "true"
    clean(browser, "detailed view and map")
    assert shown(browser, '.tabs [data-tab="library"]')                                      # the tab is there because this run recorded its routing decisions
    browser.click('.tabs [data-tab="library"]')
    present(browser, "#pane-library [data-tplrow]")
    assert shown(browser, "#pane-library") and not shown(browser, "#pane-map")
    sources = attrs(browser, "#pane-library [data-tplsource]", "data-tplsource")
    assert sources and set(sources) == {"from this run"}, sources                            # every routing decision has the run's own copy of its template
    copies = live.settings.data_dir / "departments" / "web" / "runs"
    assert list(copies.glob("*/templates.json")), "the run recorded its routing decisions"
    first = attrs(browser, "#pane-library table [data-tplopen]", "data-tplopen")[0]
    browser.click("#pane-library table [data-tplopen]")
    present(browser, "#tplviewer [data-tplreadable]")
    assert shown(browser, "#tplviewer")
    assert "from this run" in texts(browser, "#tplviewer h3")[0] and first.split("|")[2] in texts(browser, "#tplviewer h3")[0]
    browser.click('#tplviewer [data-tplmode="template"]')
    present(browser, "#tplviewer [data-tplfile]")
    assert len(attrs(browser, "#tplviewer [data-tplfile]", "data-tplfile")) >= 1
    clean(browser, "library")

    # 8. the Workflow graph tab draws, the Org chart tab shows the team
    browser.click('.tabs [data-tab="graph"]')
    browser.wait_for("document.querySelectorAll('#pane-graph g.wnode').length > 0")
    assert shown(browser, "#pane-graph") and not shown(browser, "#pane-library")
    browser.click('.tabs [data-tab="orgchart"]')
    present(browser, '#pane-orgchart g.wnode[data-id="web"]')
    assert shown(browser, "#pane-orgchart") and not shown(browser, "#pane-graph")
    clean(browser, "team tabs")

    # 9. Home Settings: an Engine edit is saved (and read back from the server), the stub connector answers its Test
    browser.goto(live.base_url + "/")
    browser.wait_for("window.HomePage && HomePage.state().loaded === true")
    browser.click('#rail [data-pane="settings"][data-group="engine"]')
    present(browser, "#set-engine #setf-max_cycles")
    browser.js("(() => { const e = document.getElementById('setf-max_cycles'); e.focus(); e.select(); })()")
    browser.type("#setf-max_cycles", "4")
    browser.click('[data-act="save-engine"]')
    browser.wait_for("document.querySelector('#set-engine .setstatus').textContent.startsWith('Saved')")
    assert live.get("/api/engine/settings")["global"] == {"max_cycles": 4}
    browser.click('#rail [data-pane="settings"][data-group="connectors"]')
    clean(browser, "settings engine")
    present(browser, '#set-connectors [data-provider="stub"] [data-act="test"]')
    browser.expect_failed("/api/connectors/stub/test", 409)                                  # by design: the stub starts no CLI, so the Test is refused (CN-9)
    browser.click('#set-connectors [data-provider="stub"] [data-act="test"]')
    browser.wait_for("document.querySelector('#set-connectors .settest').dataset.step === 'error'")
    assert "not available while the app runs offline" in browser.js("document.querySelector('#set-connectors .settest').textContent")
    assert [f["url"].rsplit("/api/", 1)[1] for f in browser.expected_failures] == ["connectors/stub/test"]
    assert len(browser.console_errors) == 1 and "409" in browser.console_errors[0]          # the browser's own line about that one refusal, nothing else
    assert browser.failed_requests == []


@pytest.mark.browser
def test_the_connector_test_of_settings_makes_a_real_call_through_the_router_to_the_fake_claude(tmp_path, browser):
    """The stub refuses Test (above); with the real router over the fake `claude` the same button makes one tiny call and says "Worked in ... s"."""
    cli = FakeCliBin(tmp_path)
    live = LiveApp(tmp_path, cli=cli, connector_name="auto", offline=False).start()
    try:
        browser.goto(live.base_url + "/")
        browser.wait_for("window.HomePage && HomePage.state().loaded === true")
        browser.click('#rail [data-pane="settings"][data-group="connectors"]')
        present(browser, '#set-connectors [data-provider="claude"] [data-act="test"]')
        assert texts(browser, '#set-connectors [data-provider="claude"] .setchip') == ["Ready"]
        calls = len(cli.calls("claude"))
        browser.click('#set-connectors [data-provider="claude"] [data-act="test"]')
        browser.wait_for("document.querySelector('#set-connectors [data-provider=claude] .settest').dataset.step === 'ok'")
        assert browser.js("document.querySelector('#set-connectors [data-provider=claude] .settest').textContent").startswith("Worked in ")
        assert len(cli.calls("claude")) == calls + 1                                          # exactly one process call, and it was the Test
        clean(browser, "connector test")
    finally:
        try:
            live.stop()
        finally:
            live.kill_engines()
