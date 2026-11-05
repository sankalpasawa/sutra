"""The scripted walk of the whole UI in one headless Chrome (UI-9, docs/design/ui.md section 10 "Scripted smoke"; S3-web-09, S4-fnodes-11).

Runs only with SUTRA_BROWSER=1 (the gate skips it). Against the fake backend of UI-0, which mounts the real pages and the real static files, one
browser does what an owner does on a first day: opens Home, sends a brief, watches the team appear, looks at a function node and at Identity,
sees a node turn green as events arrive, answers a question, opens the team's page, and looks at its two new tabs. The walk is ONE test (a failure
says at which step it stopped); the second test drops the live stream; the third checks that the walk's two pages ran under the page's own CSP
with nothing blocked. Zero console errors and zero failed requests are checked after EVERY step, which fails on any CSP violation (S3-web-09).

The `-k real` run against `create_app(settings, connector=ScriptedConnector(...), launcher=FakeLauncher(...))` (ORCH-7 and ORCH-8) is not here yet:
neither package is merged (docs/notes/UI-9.md).
"""
from __future__ import annotations

import json
import shutil
import urllib.request
from pathlib import Path

import pytest

import fake_backend  # tests/ui is on sys.path (conftest.py)

browser_only = pytest.mark.browser

BRIEF = "A website for my cafe"
DEPT_SESSION = "cs_5e0a77b19c3d"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


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


def posts(fake, prefix="/api/"):
    return [r for r in fake.log(prefix) if r["method"] in ("POST", "PUT", "DELETE")]


@pytest.fixture()
def story(tmp_path, make_fake_server):
    """A fake backend whose third graph has the Identity node filed (green) while the question is still open: the fixtures are copied and two changed."""
    folder = tmp_path / "fixtures"
    shutil.copytree(FIXTURES, folder)
    path = folder / "graph.v3.json"
    graph = json.loads(path.read_text(encoding="utf-8"))
    for node in graph["nodes"]:
        if node["id"] == "web.identity":
            node["status"] = "filed"
    path.write_text(json.dumps(graph), encoding="utf-8")
    needs = json.loads((folder / "needs-you.json").read_text(encoding="utf-8"))
    needs["3"] = needs["2"]                                      # the owner has not answered yet when the third graph arrives
    (folder / "needs-you.json").write_text(json.dumps(needs), encoding="utf-8")
    return make_fake_server(fixtures_dir=folder)


@browser_only
def test_the_whole_first_day_walk(story, browser):
    fake = story.client
    fake.reset()
    fake.stage("1")

    # 1. Home: the start page with J2's four example briefs
    browser.goto(story.url + "/")
    browser.wait_for("window.HomePage && HomePage.state().loaded === true")
    fake.wait_subscribers(1)
    assert len(attrs(browser, "[data-brief]", "data-brief")) == 4
    assert texts(browser, "#smsgs .nmsg")[0].endswith("Hello. Tell me what you need and I will find the right team.")
    clean(browser, "home start page")

    # 2. send a brief: progress, reply, chart_change and task cards, the chart marks "added", the graph draws
    browser.click(f'[data-brief="{BRIEF}"]')
    present(browser, ".c-task")
    present(browser, ".c-chart")
    fake.wait_flows()
    assert browser.js("HomePage.state().turn.phase") == "done"
    assert texts(browser, "#sprog > div") == ["Reading the org chart", "Checking the model library", "Planning", "Setting up the team", "Done"]
    assert "Added the Web team" in texts(browser, ".c-chart .csum")
    sent = posts(fake, "/api/chats/cs_org/messages")
    assert len(sent) == 1 and sent[0]["body"] == {"text": BRIEF} and sent[0]["token"] is True
    present(browser, '#pane-graph .wnode[data-id="web"]')
    assert browser.count("#pane-graph .wnode") >= 2                                          # Overview: the root and the team (and its task step)
    browser.click('#rail [data-pane="chart"]')
    present(browser, '#pane-chart g.wnode[data-id="web"].mk-add')
    assert browser.js("document.querySelector('#pane-chart g.wnode[data-id=\"web\"] .wtag').textContent") == "added"
    browser.click('#rail [data-pane="graph"]')
    browser.click("#pane-graph [data-wlevel='full']")                                        # Detail: the five function nodes of the team appear
    present(browser, '#pane-graph g.wnode[data-id="web.adaptation"]')
    browser.click("#pane-graph [data-wfit]")                                                 # the whole team in view: the five boxes are wider than the pane
    clean(browser, "send a brief")

    # 3. a function node that is not Identity: read-only chat, then Details
    browser.click('#pane-graph g.wnode[data-id="web.adaptation"]')
    browser.wait_for("!document.getElementById('nodepanel').hidden && document.getElementById('nptitle').textContent === 'Adaptation'")
    present(browser, ".nnote")
    assert texts(browser, ".nnote") == ["Read-only: this is the working log of Strategist."]
    assert browser.js("document.querySelector('.ncomposer').hidden") is True
    browser.click("[data-nptab=details]")
    present(browser, ".fndetail")
    sections = attrs(browser, ".fndetail > .fnsec", "data-sec")
    for wanted in ("goal", "task", "context", "atoms", "constraints", "hands"):
        assert wanted in sections, (wanted, sections)
    assert texts(browser, ".fnsec[data-sec=hands] .fnto .fnchip")                              # who it hands to
    clean(browser, "function node details")

    # 4. the Identity chip: the department's own chat, with its composer (closed with its button, not with Esc: the drawer covers half of the graph;
    #    a real Escape key before more mouse moves makes Chrome wait 5 s for each of them in this driver, so Esc is pressed once, last)
    browser.click("[data-npclose]")
    browser.wait_for("document.getElementById('nodepanel').hidden")
    browser.js("document.querySelector('#pane-graph g.wnode[data-id=\"web.identity\"]').focus()")      # a box is a button: the keyboard opens it
    browser.press("Enter")
    browser.wait_for("document.getElementById('nptitle').textContent === 'Identity'")
    present(browser, ".nchat .nmsg")
    assert shown(browser, ".ncomposer") and browser.js("document.querySelector('.nbox').disabled") is False
    asked = [r["path"] for r in fake.log("/api/chats/") if r["path"].endswith("/messages") and r["method"] == "GET"]
    assert f"/api/chats/{DEPT_SESSION}/messages" in asked
    clean(browser, "identity chat")
    browser.click("[data-npclose]")
    browser.wait_for("document.getElementById('nodepanel').hidden")

    # 5. events: an atom closes and the graph changes; the Identity node turns green with no reload
    browser.js("window.__sameDocument = true")
    assert "st-filed" not in attrs(browser, '#pane-graph g.wnode[data-id="web.identity"]', "class")[0]
    atom = json.loads((FIXTURES / "events.script.json").read_text(encoding="utf-8"))["samples"]["atom.updated"]
    fake.fixture("graph", "3")
    fake.emit("atom.updated", atom)
    fake.emit("graph.updated", {"version": 44, "nodes": [{"id": "web.identity", "dept_id": "web"}], "edges_added": 0, "edges_removed": 0})
    present(browser, '#pane-graph g.wnode.st-filed[data-id="web.identity"]')
    assert browser.js("window.__sameDocument === true")                                      # the same document: nothing reloaded
    clean(browser, "live update")

    # 6. a needs_you card is answered and reads "Answered"
    present(browser, ".c-needs")
    browser.click('.c-needs [data-act="answer-option"]')
    present(browser, ".c-needs[data-answered]")
    assert texts(browser, ".c-needs .canswer") == ["Answered"]
    answered = posts(fake, "/api/chats/")
    assert answered[-1]["path"] == f"/api/chats/{DEPT_SESSION}/messages" and answered[-1]["token"] is True
    clean(browser, "needs you answered")

    # 7. Open the team: the J2 page loads offline under its CSP with zero console errors
    browser.click('.c-task [data-act="open-team"]')
    browser.wait_for("window.DeptExt !== undefined && DeptExt.state().started === true")
    assert browser.js("location.pathname") == "/d/web/"
    assert browser.js("document.title") == "Web \u00b7 Sutra"
    origin = story.url
    assert browser.js(f"performance.getEntriesByType('resource').every(e => e.name.startsWith({q(origin)}))")        # offline: every file is the app's own
    clean(browser, "team page")

    # 8. the Workflow graph tab draws, the Org chart tab shows its marks
    browser.click('.tabs [data-tab="graph"]')
    browser.wait_for("document.querySelectorAll('#pane-graph g.wnode').length > 0")
    browser.click('.tabs [data-tab="orgchart"]')
    present(browser, '#pane-orgchart g.wnode.mk-add[data-id="web"]')
    clean(browser, "team tabs")

    # 9. Esc closes the drawer
    browser.click('#pane-orgchart g.wnode[data-id="web"]')
    browser.wait_for("!document.querySelector('#pane-orgchart .ocard').hidden")
    browser.click('#pane-orgchart [data-oc="chat"]')
    browser.wait_for("!document.getElementById('nodepanel').hidden")
    browser.press("Escape")
    browser.wait_for("document.getElementById('nodepanel').hidden")
    clean(browser, "escape")


@browser_only
def test_a_dropped_stream_shows_the_polling_chip_and_the_page_keeps_up_by_asking(story, browser):
    fake = story.client
    fake.reset()
    fake.stage("2")
    browser.goto(story.url + "/")
    browser.wait_for("window.HomePage && HomePage.state().loaded === true")
    fake.wait_subscribers(1)
    present(browser, '#pane-graph .wnode[data-id="web"]')
    browser.wait_for("document.querySelector('#pane-graph .wlive').dataset.state === 'live'")
    assert texts(browser, "#pane-graph .wlive") == ["\u25cf live"]
    graphs = len([r for r in fake.log("/api/graph") if r["path"] == "/api/graph"])
    browser.expect_failed("/api/events")                                    # the stream is cut: every reconnect is refused
    fake.fail("/api/events", 500)
    fake.fixture("graph", "3")                                              # the Web team starts to run while no event can say so
    browser.wait_for("document.querySelector('#pane-graph .wlive').dataset.state === 'polling'", timeout=40)
    assert texts(browser, "#pane-graph .wlive") == ["\u25cb polling"]
    present(browser, '#pane-graph g.wnode.st-running[data-id="web"]', timeout=20)
    assert len([r for r in fake.log("/api/graph") if r["path"] == "/api/graph"]) > graphs      # polling read the graph again, with no event
    fake.fail("/api/events", None)
    assert all(e.startswith("[network]") for e in browser.console_errors), browser.console_errors     # only the refused stream; nothing else


@browser_only
def test_both_pages_are_served_under_a_csp_and_a_violation_would_show_in_the_console(story, browser):
    story.client.reset()
    story.client.stage("2")                                                 # the Web team exists
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for path in ("/", "/d/web/"):
        with opener.open(story.url + path, timeout=20) as response:
            csp = response.headers["Content-Security-Policy"]
        script_src = [part.strip() for part in csp.split(";") if part.strip().startswith("script-src")][0]
        assert "'unsafe-inline'" not in script_src and "sha256-" in script_src, (path, script_src)
    browser.goto(story.url + "/d/web/")
    browser.wait_for("window.DeptExt !== undefined && DeptExt.state().started === true")
    clean(browser, "team page before the probe")
    # the same detector the walk uses: an inline script that the page's policy does not allow is refused and reported
    browser.js("(() => { const s = document.createElement('script'); s.textContent = 'window.__probe = 1'; document.head.appendChild(s); })()")
    browser.wait_for("window.__probe === undefined && " + q("x") + " === 'x'")
    assert browser.js("window.__probe") is None
    assert any("Content Security Policy" in e or "Refused to execute" in e for e in browser.console_errors), browser.console_errors
