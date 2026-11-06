"""The composer of the direct chat in a real browser (work package ABS-15): a team's node panel and Home, over the real app and the fake `claude` and
`codex` (the offline harness of ABS-13; nothing reaches a real model).

One owner, one Chrome: the node panel's "Ask the model" mode, a text file attached through the real upload route and delivered to the model, the
streamed reply (the row under the messages while it is written, then the stored message), the provider pill respected (a turn goes to the chosen model),
Stop on a turn that hangs, the typed blocks of a settled reply folded into one row, and Home's "Ask directly". Zero console errors and zero failed
requests are checked after every step.

Run it: `SUTRA_BROWSER=1 scripts/py -m pytest tests/e2e/test_browser_chat_composer.py -q`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from harness import ORG, FakeCliBin, LiveApp

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ui"))      # `import cdp`
import cdp  # noqa: E402

from sutra_app.orchestrator.api import chat_v2  # noqa: E402

NOTE = "The cafe opens at seven. Closed on Mondays."
# a 1x1 PNG: what a pasted screenshot is to the upload route (its bytes are sniffed)
PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


def q(css: str) -> str:
    return json.dumps(css)


def present(browser, css, timeout=15.0):
    browser.wait_for(f"!!document.querySelector({q(css)})", timeout=timeout)


def label(browser, css) -> str:
    return browser.js(f"(() => {{ const e = document.querySelector({q(css)}); return e ? e.textContent.trim().replace(/\\s+/g, ' ') : null; }})()")


def shown(browser, css) -> bool:
    return browser.js(f"(() => {{ const e = document.querySelector({q(css)}); return !!e && !e.hidden && e.offsetParent !== null; }})()")


def clean(browser, step):
    assert browser.console_errors == [], f"{step}: console errors {browser.console_errors}"
    assert browser.failed_requests == [], f"{step}: failed requests {browser.failed_requests}"


def attach_file(browser, selector: str, path: Path) -> None:
    """What the owner's file chooser does: set the files of the (hidden) input; the page gets the same `change` event."""
    root = browser._send("DOM.getDocument", {"depth": 0})["root"]["nodeId"]
    node = browser._send("DOM.querySelector", {"nodeId": root, "selector": selector})["nodeId"]
    assert node, f"no element matches {selector!r}"
    browser._send("DOM.setFileInputFiles", {"nodeId": node, "files": [str(path)]})


def agent_after(live: LiveApp, sid: str, count: int) -> dict:
    live.until("the reply to be stored", lambda: len(live.messages(sid)) >= count and sid not in chat_v2._running)
    return live.messages(sid)[-1]


@pytest.fixture()
def browser():
    chrome = cdp.find_chrome()
    if chrome is None:
        pytest.skip("Chrome is not installed (set SUTRA_CHROME to its path)")
    with cdp.Browser(chrome) as instance:
        yield instance


@pytest.fixture()
def app(tmp_path):
    cli = FakeCliBin(tmp_path)
    cli.sequence["claude"] = "slow,hang,ok"        # Claude's calls: the first streams slowly, the second hangs (Stop), then answers at once
    live = LiveApp(tmp_path, cli=cli, connector_name="auto", offline=False).start()
    try:
        yield live, cli
    finally:
        try:
            live.stop()
        finally:
            live.kill_engines()


@pytest.mark.browser
def test_the_direct_chat_composer_in_the_node_panel_and_on_home(app, browser, tmp_path):
    live, cli = app
    live.add_department("web", "Web", "Websites")
    sid = live.session_of("web")
    notes = tmp_path / "notes.txt"
    notes.write_text(NOTE)

    # 1. the panel: the pill of both runnable models, the mode toggle (the team's plain route is the default), no attach row yet
    browser.goto(live.base_url + "/")
    browser.wait_for("window.HomePage && HomePage.state().loaded === true")
    present(browser, '#pane-graph .wnode[data-id="web"]')
    browser.js("document.querySelector('#pane-graph g.wnode[data-id=\"web\"]').focus()")
    browser.press("Enter")
    browser.wait_for("!document.getElementById('nodepanel').hidden && document.getElementById('nptitle').textContent === 'Web'")
    present(browser, "#nodepanel .npill .cpill")
    assert browser.count("#nodepanel .npill [data-act=choose-provider]") >= 2
    assert browser.js("document.querySelector('#nodepanel .ccmode [data-mode=team]').getAttribute('aria-pressed')") == "true"
    assert not browser.exists("#nodepanel .ccinput")
    clean(browser, "panel with the composer bar")

    # 2. Ask the model: attach a file through the real upload route, ask; the row shows the writing, then the stored reply replaces it
    browser.click("#nodepanel .ccmode [data-mode=direct]")
    present(browser, "#nodepanel .ccinput")
    attach_file(browser, "#nodepanel .ccinput", notes)
    present(browser, "#nodepanel .ccfile.ready")
    assert label(browser, "#nodepanel .ccfile .ccname") == "notes.txt"
    browser.type(".nbox", "What time do we open?")
    browser.click(".ncomposer .send")
    browser.wait_for("document.querySelector('.ncomposer .send').textContent === 'Stop'")              # Send is Stop while the turn answers
    browser.wait_for("document.querySelectorAll('#nodepanel .ccfile').length === 0")                                                                     # the files went with the message
    browser.wait_for("!document.querySelector('#nodepanel .ccstream').hidden", timeout=20)
    assert "is writing" in label(browser, "#nodepanel .ccstream")
    reply = agent_after(live, sid, 2)
    assert reply["role"] == "agent" and reply["kind"] == "text" and reply["text"]
    browser.wait_for("document.querySelector('#nodepanel .ccstream').hidden && document.querySelector('.ncomposer .send').textContent === 'Send'", timeout=20)
    assert [m["role"] for m in live.messages(sid)] == ["user", "agent"]
    assert NOTE in json.dumps(cli.calls("claude")[0]), "the attached file reached the model"
    assert live.messages(sid)[0]["text"] == "What time do we open?\n(attached: notes.txt)"      # the owner's line records what went with it
    browser.wait_for("Array.from(document.querySelectorAll('.nchat .nmsg.me .cattached li')).some(e => e.textContent.includes('notes.txt'))")
    assert browser.count(".nchat .nmsg") >= 2
    clean(browser, "first direct turn")

    # 3. the pill is respected: Codex chosen, the next turn goes to Codex, and the pill still says so afterwards
    browser.click('#nodepanel .npill [data-provider="codex"]')
    browser.wait_for("document.querySelector('#nodepanel .npill [data-provider=codex]').getAttribute('aria-pressed') === 'true'")
    browser.type(".nbox", "And on Sundays?")
    browser.press("Enter")                                                                                  # Enter sends, as in the team mode
    agent_after(live, sid, 4)
    assert len(cli.calls("codex")) == 1 and len(cli.calls("claude")) == 1
    browser.wait_for("document.querySelector('.ncomposer .send').textContent === 'Send'", timeout=20)
    clean(browser, "turn on the chosen model")

    # 4. Stop: back on Claude (the app chooses), a turn that hangs; Stop ends it and the owner gets a line instead of a frozen box
    browser.click('#nodepanel .npill [data-provider=""]')
    browser.wait_for("!document.querySelector('#nodepanel .npill [data-provider=\"\"]')")
    browser.type(".nbox", "Write the whole menu")
    browser.click(".ncomposer .send")
    browser.wait_for("document.querySelector('.ncomposer .send').textContent === 'Stop'")
    live.until("the model to start", lambda: len(cli.calls("claude")) == 2)
    browser.click(".ncomposer .send")
    final = agent_after(live, sid, 6)
    assert final["role"] == "agent" and final["kind"] == "note"                  # Stop is a calm note (and what was written, if anything, is kept above it)
    assert not [m for m in live.messages(sid) if m["kind"] == "error"]
    browser.wait_for("document.querySelector('.ncomposer .send').textContent === 'Send' && document.querySelector('#nodepanel .ccstream').hidden", timeout=30)
    assert browser.js("document.querySelector('.ncomposer .send').disabled") is False
    present(browser, ".nchat .nmsg.note")
    assert not browser.exists(".nchat .nmsg.oops")
    clean(browser, "stop")

    # 5. a settled reply with typed blocks is ONE folded row that opens into the cards
    chat_v2._post(live.services, sid, role="agent", who="sutra", kind="text", text="Done: the menu is in menu.md.", blocks=[
        {"type": "tool_use", "kind": "read", "name": "Read", "text": "menu.md"}, {"type": "tool_result", "kind": "read", "name": "Read", "text": "ok"},
        {"type": "tool_use", "kind": "run", "name": "Bash", "text": "ls"}])
    browser.wait_for("document.querySelectorAll('.nchat details.cfold').length === 1")
    assert label(browser, ".nchat details.cfold summary") == "2 tool calls: 1 read, 1 run"
    browser.click(".nchat details.cfold summary")
    browser.wait_for("document.querySelector('.nchat details.cfold').open")
    assert browser.count(".nchat .cfold-item") == 3
    clean(browser, "typed blocks")
    browser.click("[data-npclose]")
    browser.wait_for("document.getElementById('nodepanel').hidden")

    # 6. Home: "Ask directly" on the org chat (the staged path stays the default), the third Claude call answers at once
    assert label(browser, "#sbar .ccmode-opt.on") == "Plan with Sutra"
    browser.click('#sbar [data-mode="direct"]')
    present(browser, "#sbar .ccinput")
    browser.type("#sbox", "Hello Sutra, what can you do?")
    browser.click("#ssend")
    live.until("the direct line and its reply on Home", lambda: [m["role"] for m in live.messages(ORG)][-2:] == ["user", "agent"] and ORG not in chat_v2._running)
    assert live.messages(ORG)[-2]["text"] == "Hello Sutra, what can you do?"
    browser.wait_for("Array.from(document.querySelectorAll('#smsgs .nmsg')).some(e => e.textContent.includes('Hello Sutra, what can you do?'))")
    browser.wait_for("document.getElementById('ssend').textContent === 'Send' && document.getElementById('sstream').hidden", timeout=20)
    assert len(cli.calls("claude")) == 3 and not [m for m in live.messages(ORG) if m["kind"] == "card"]      # no team was planned: the staged path did not run
    clean(browser, "Home direct chat")

    # 7. paste a screenshot into Home's box while it plans with Sutra: the box switches to the model with a note, the chip shows its thumbnail,
    #    and the stored line names the pasted file (GAP-chat-comfort); a text paste stays text
    browser.click('#sbar [data-mode="team"]')
    browser.wait_for("document.querySelector('#sbar .ccmode-opt.on').textContent === 'Plan with Sutra'")
    browser.js("""(() => { const dt = new DataTransfer(); dt.setData('text/plain', 'just words');
                  document.getElementById('sbox').dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true})); })()""")
    assert label(browser, "#sbar .ccmode-opt.on") == "Plan with Sutra" and not browser.exists("#sbar .ccfile")
    browser.js(f"""(() => {{ const bytes = Uint8Array.from(atob({json.dumps(PNG_B64)}), c => c.charCodeAt(0));
                  const dt = new DataTransfer(); dt.items.add(new File([bytes], 'image.png', {{type: 'image/png'}}));
                  document.getElementById('sbox').dispatchEvent(new ClipboardEvent('paste', {{clipboardData: dt, bubbles: true, cancelable: true}})); }})()""")
    browser.wait_for("document.querySelector('#sbar .ccmode-opt.on').textContent === 'Ask directly'")
    present(browser, "#sbar .ccfile.ready .ccthumb")
    assert label(browser, "#sbar .ccfile .ccname") == "pasted-image-1.png" and browser.js("document.querySelector('#sbar .ccthumb').src.startsWith('blob:')")
    assert "Files go only to the model" in label(browser, "#sbar .ccnote")
    browser.type("#sbox", "What is in this picture?")
    browser.click("#ssend")
    live.until("the pasted line and its reply", lambda: [m["role"] for m in live.messages(ORG)][-2:] == ["user", "agent"] and len(live.messages(ORG)) >= 4
               and ORG not in chat_v2._running)
    assert live.messages(ORG)[-2]["text"] == "What is in this picture?\n(attached: pasted-image-1.png)"
    browser.wait_for("Array.from(document.querySelectorAll('#smsgs .nmsg.me .cattached li')).some(e => e.textContent.includes('pasted-image-1.png'))")
    clean(browser, "paste on Home")
