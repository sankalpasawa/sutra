"""A page that outlives its server (GAP-E2E-UI, G06): the app is stopped and started again on the SAME data folder and the SAME port, while Chrome keeps
one Home document open.

  * `test_a_restarted_server_...`  the live chip turns to `○ polling` (the stream failed three times), then the stream comes back, its `server.hello`
    reaches the page as `server.resync` (SutraEvents turns every hello but the first into one) and Home re-reads everything: the graph (a team made while
    the page could not hear) and the org chat (a line the restarted app wrote) appear with no reload, and the chip is `● live` again.
  * `test_a_page_opened_before_the_restart_...`  the restarted app has a NEW per-launch token (D81), so the old page's write is answered 401 and the page says,
    in words, to reload it from the app; the reloaded page can write.

Runs only with SUTRA_BROWSER=1. "Stop the server" is `LiveApp.stop()` (the owner closes the app: the lifespan runs its ladders, the stream ends) and the
restart is a second `LiveApp` on the same folder; the port is pinned by wrapping the harness's `bind_socket`. The reads that the outage refuses are announced
(`expect_failed`) and nothing else may fail, before or after.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import harness
import pytest
from harness import ORG, LiveApp, decide, run_new_team

from sutra_app.orchestrator.agent import planner
from sutra_app.orchestrator.testing.scripted import ScriptedConnector

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ui"))      # `import cdp` (tests/ui has no __init__.py and its conftest is not loaded here)
import cdp  # noqa: E402

NEW_TOKEN = "restarted-token-0123456789abcdef"
SMALLTALK = decide("smalltalk", "none", reuse=())                             # a reply that makes the chat agent answer with one fixed line, no team
# remembers every raw server.hello the stream delivered (the resync is made from the second one inside SutraEvents), and never changes how the page listens
HELLO_LOG = """(() => {
  const Native = window.EventSource;
  window.__sse = [];
  window.EventSource = class extends Native {
    constructor(url, options) {
      super(url, options);
      this.addEventListener("server.hello", () => window.__sse.push("server.hello"));
    }
  };
})();"""


def q(css: str) -> str:
    return json.dumps(css)


def texts(browser, css):
    return browser.js(f"Array.from(document.querySelectorAll({q(css)}), e => e.textContent.trim().replace(/\\s+/g, ' '))")


def present(browser, css, timeout=10.0):
    browser.wait_for(f"!!document.querySelector({q(css)})", timeout=timeout)


def chip(browser) -> str:
    return browser.js("document.querySelector('#pane-graph .wlive').dataset.state")


def health_reads(browser) -> int:
    return browser.js("performance.getEntriesByType('resource').filter(e => new URL(e.name).pathname === '/api/health').length")


@pytest.fixture()
def browser():
    chrome = cdp.find_chrome()
    if chrome is None:
        pytest.skip("Chrome is not installed (set SUTRA_CHROME to its path)")
    with cdp.Browser(chrome) as instance:
        yield instance
        assert not instance.failed_requests, f"requests failed during the test (announce them with browser.expect_failed): {instance.failed_requests}"


@pytest.fixture()
def apps(tmp_path, monkeypatch):
    """`apps.first()` starts the app; `apps.restart(token=...)` stops it and starts it again on the same folder and port. All are stopped at the end."""
    made: list[LiveApp] = []
    real_bind = harness.bind_socket

    class Apps:
        port = 0

        def first(self) -> LiveApp:
            live = LiveApp(tmp_path, connector=ScriptedConnector()).start()
            made.append(live)
            self.port = live.port
            return live

        def restart(self, token: str | None = None) -> LiveApp:
            made[-1].stop()
            monkeypatch.setattr(harness, "bind_socket", lambda host, port, **kw: real_bind(host, self.port, **kw))      # the same address as before
            live = LiveApp(tmp_path, connector=ScriptedConnector())
            if token is not None:
                live.settings = live.settings.model_copy(update={"token": token})
            live.start()
            if token is not None:
                live.http.headers["X-Sutra-Token"] = token
            made.append(live)
            assert live.port == self.port
            return live

    yield Apps()
    for live in reversed(made):
        try:
            if live.started:
                live.stop()
        finally:
            live.kill_engines()


def open_home(browser, live) -> None:
    browser._send("Page.addScriptToEvaluateOnNewDocument", {"source": HELLO_LOG})
    browser.goto(live.base_url + "/")
    browser.wait_for("window.HomePage && HomePage.state().loaded === true")
    browser.wait_for("document.querySelector('#pane-graph .wlive').dataset.state === 'live'")
    browser.js("window.__sameDocument = true")


def outage(browser, live) -> None:
    """The server goes away: every read of the page is refused from now on, which is announced; the chip must reach polling."""
    browser.expect_failed(live.base_url + "/api/")
    live.stop()
    browser.wait_for("document.querySelector('#pane-graph .wlive').dataset.state === 'polling'", timeout=60)


def after_outage(browser) -> None:
    """The outage is over: forget what was announced and the browser's own lines about it; from here on nothing may fail."""
    browser.wait_for("document.querySelector('#pane-graph .wlive').dataset.state === 'live'", timeout=60)
    assert all(e.startswith("[network]") for e in browser.console_errors), browser.console_errors                 # only the refused reads
    browser._expect_rules.clear()
    browser.clear_diagnostics()


@pytest.mark.browser
def test_a_restarted_server_shows_polling_then_the_hello_resync_restores_the_graph_and_the_chat_without_a_reload(apps, browser):
    first = apps.first()
    run_new_team(first)                                                                      # the Web team exists and its task is done
    open_home(browser, first)
    present(browser, '#pane-graph .wnode[data-id="web"]')
    assert texts(browser, "#pane-graph .wlive") == ["● live"] and browser.js("window.__sse") == ["server.hello"]
    assert browser.count("#pane-graph .wnode[data-id='docs']") == 0
    lines = texts(browser, "#smsgs .nmsg")
    reads = health_reads(browser)
    assert browser.console_errors == [] and browser.failed_requests == []

    outage(browser, first)
    assert texts(browser, "#pane-graph .wlive") == ["○ polling"]
    assert browser.count("#pane-graph .wnode[data-id='web']") == 1                           # the page keeps what it had while it cannot ask

    second = apps.restart()                                                                  # same data folder, same port
    second.add_department("docs", "Docs", "Documentation")                                   # what the page could not hear: a team ...
    second.say("Thanks, team", SMALLTALK)                                                    # ... and a line in the org chat
    after_outage(browser)

    present(browser, '#pane-graph .wnode[data-id="docs"]')                                   # the graph re-read
    browser.wait_for(f"Array.from(document.querySelectorAll('#smsgs .nmsg')).some(e => e.textContent.includes({q(planner.LINES['smalltalk'])}))")
    now = texts(browser, "#smsgs .nmsg")
    assert now[:len(lines)] == lines and "Thanks, team" in now                               # the chat re-read: nothing lost, the new lines added
    server_lines = [m for m in second.messages(ORG) if m["kind"] in ("text", "card")]
    assert browser.count("#smsgs .nmsg") == len(server_lines)                               # the page shows exactly what the restarted server holds
    browser.click('#rail [data-pane="chart"]')
    present(browser, '#pane-chart g.wnode[data-id="docs"]')
    assert browser.js("window.__sameDocument === true")                                      # no reload
    assert browser.js("window.__sse") == ["server.hello", "server.hello"]                    # the stream said hello again: SutraEvents makes that a resync
    assert health_reads(browser) > reads                                                     # only a full re-read (loadAll) asks for /api/health; polling never does
    assert texts(browser, "#pane-graph .wlive") == ["● live"]
    assert browser.console_errors == [] and browser.failed_requests == []


@pytest.mark.browser
def test_a_page_opened_before_the_restart_gets_401_on_a_write_and_says_to_reload_it_from_the_app(apps, browser):
    first = apps.first()
    run_new_team(first)
    open_home(browser, first)
    present(browser, '#pane-graph .wnode[data-id="web"]')

    outage(browser, first)
    second = apps.restart(token=NEW_TOKEN)                                                   # a new launch: a new token (D81)
    after_outage(browser)
    before = len(second.messages(ORG))

    browser.expect_failed("/api/chats/cs_org/messages", 401)
    browser.type("#sbox", "Is anyone there?")
    browser.click("#ssend")
    browser.wait_for("!document.getElementById('sbanner').hidden")
    assert texts(browser, "#sbanner > span") == ["This page was opened without its access token. Reload it from the app."]
    assert browser.js("document.getElementById('sbox').disabled") is True                  # the page is blocked: it does not try again with a token it knows is wrong
    assert [f["status"] for f in browser.expected_failures] == [401]
    assert len(second.messages(ORG)) == before                                               # the server wrote nothing
    assert browser.failed_requests == [] and all("401" in e for e in browser.console_errors)

    browser.clear_diagnostics()
    browser.goto(second.base_url + "/")                                                      # "reload it from the app": the new page carries the new token
    browser.wait_for("window.HomePage && HomePage.state().loaded === true")
    second.connector.push(SMALLTALK)
    browser.type("#sbox", "Is anyone there?")
    browser.click("#ssend")
    browser.wait_for(f"Array.from(document.querySelectorAll('#smsgs .nmsg')).some(e => e.textContent.includes({q(planner.LINES['smalltalk'])}))")
    assert browser.js("document.getElementById('sbanner').hidden") is True
    assert browser.console_errors == [] and browser.failed_requests == []
