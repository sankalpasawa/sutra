"""The live direct chat in a real Chrome, over the real app and the fake `claude` that replays streamed turns (streaming design, work packages STR-10 to STR-13).

Everything between the page and the process is real: the HTML and scripts, the event stream, `SUTRA_LIVE_V1` routes, `LiveTurn`, the router and the connector, the process
group and its cancel ladder. Only the model is a fake CLI that replays JSONL made from the captured real turn (tests/e2e/stream_fixtures.py), a line at a time with a delay.

The eight scenarios of the brief: normal, long, tool, multi-stage, cancel, network drop, error, existing conversation. Plus the facts the design promises: the first visible
state before the first token, the reply item does not move at settle, nothing is recreated while it streams, the reduced-motion and phone layouts, the node panel.

Run it: `SUTRA_BROWSER=1 scripts/py -m pytest tests/e2e/test_browser_live_chat.py -q`. Screenshots go to docs/design/streaming/screens when SUTRA_SHOTS=1.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest
from harness import ORG, FakeCliBin, LiveApp
from stream_fixtures import Fail, Text, Think, Tool, write_turn

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ui"))      # `import cdp`
import cdp  # noqa: E402

from sutra_app.orchestrator import direct_running  # noqa: E402

SHOTS = Path(__file__).resolve().parents[2] / "docs" / "design" / "streaming" / "screens"
TURN = "#smsgs .clive"


def q(css: str) -> str:
    return json.dumps(css)


class StreamCli(FakeCliBin):
    """The fake CLIs with a pause between lines, so a turn takes long enough to be watched."""

    line_delay = "0.06"

    def config_kwargs(self):
        kw = super().config_kwargs()
        kw["extra_env"] = {**kw["extra_env"], "FAKE_LINE_DELAY": self.line_delay}
        return kw


@pytest.fixture()
def browser():
    chrome = cdp.find_chrome()
    if chrome is None:
        pytest.skip("Chrome is not installed (set SUTRA_CHROME to its path)")
    with cdp.Browser(chrome) as instance:
        yield instance


@pytest.fixture()
def make(tmp_path, browser):
    """make(*turns, delay=...) -> LiveApp with the live chat on; each turn is a list of steps (stream_fixtures) or a ready scenario name (`hang`, ...)."""
    started: list[LiveApp] = []

    def build(*turns, delay: str = "0.06", codex: str | None = None, **env) -> LiveApp:
        cli = StreamCli(tmp_path)
        cli.line_delay = delay
        if codex is not None:
            cli.sequence["codex"] = codex
        names = []
        for n, turn in enumerate(turns):
            names.append(turn if isinstance(turn, str) else write_turn(tmp_path / f"turn{n}.jsonl", turn))
        cli.sequence["claude"] = ",".join(names)
        live = LiveApp(tmp_path, cli=cli, connector_name="auto", offline=False)
        live.settings = live.settings.model_copy(update={"live_v1": True, "live_coalesce_ms": 33, "live_checkpoint_s": 0.5, "live_heartbeat_s": 1.0, **env})
        live.start()
        live.welcome_seen()
        started.append(live)
        return live

    try:
        yield build
    finally:
        for live in started:
            for sid in list(direct_running.RUNNING):
                token = direct_running.token_of(sid)
                if token is not None:
                    token.request()
            try:
                live.stop()
            finally:
                live.kill_engines()


def home(browser, live: LiveApp):
    browser.goto(live.base_url + "/")
    browser.wait_for("window.HomePage && HomePage.state().loaded === true")
    browser.click('#sbar [data-mode="direct"]')
    browser.wait_for("!!document.querySelector('#sbar .ccinput')")


def ask(browser, words: str):
    browser.type("#sbox", words)
    browser.click("#ssend")


def clean(browser, step: str):
    assert browser.console_errors == [], f"{step}: console errors {browser.console_errors}"
    assert browser.failed_requests == [], f"{step}: failed requests {browser.failed_requests}"


def shot(browser, name: str):
    if os.environ.get("SUTRA_SHOTS") == "1":
        SHOTS.mkdir(parents=True, exist_ok=True)
        browser.shot(SHOTS / name)


def shell_state(browser) -> dict:
    return browser.js("""(() => { const s = document.querySelector('#smsgs .clive'); if (!s) return null;
      const r = s.getBoundingClientRect();
      return {state: s.dataset.state, phase: s.dataset.phase, status: (s.querySelector('.cl-state') || {}).textContent || '', clock: (s.querySelector('.cl-clock') || {}).textContent || '',
        text: Array.from(s.querySelectorAll('.cl-text')).map(n => n.textContent).join('|'), tools: Array.from(s.querySelectorAll('.cl-tool .cl-title')).map(n => n.textContent),
        blocks: Array.from(s.querySelectorAll('.cl-block')).map(n => n.dataset.block), top: r.top + scrollY, height: r.height, id: s.dataset.id || '',
        stop: !!s.querySelector('[data-act=composer-stop]'), copy: !!s.querySelector('[data-act=copy-reply]')}; })()""")


def mark_nodes(browser):
    """Tag every node of the reply so that a later look can tell a recreated node from a kept one."""
    browser.js("""(() => { document.querySelectorAll('#smsgs .clive, #smsgs .clive *').forEach((n, i) => { if (!n.__mark) n.__mark = 'n' + i + '-' + Math.random(); }); })()""")


def unmarked(browser) -> int:
    return browser.js("(() => Array.from(document.querySelectorAll('#smsgs .clive .cl-block, #smsgs .clive')).filter(n => !n.__mark).length)()")


# ------------------------------------------------------------------------------------------------------------------------------------------------------------
# 1. normal
# ------------------------------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.browser
def test_normal_turn_first_state_before_the_first_token_then_streamed_text_then_settled_in_place(make, browser):
    live = make([Text("Hello! I can help with the cafe's website. Ask me anything.", pieces=12)], delay="0.25")
    home(browser, live)
    ask(browser, "Hello there")
    # the owner's own line is on the page at once, and the reply item exists with an honest state before any model byte
    browser.wait_for("document.querySelectorAll('#smsgs .nmsg.me').length >= 1", timeout=10)
    browser.wait_for("!!document.querySelector('#smsgs .clive .cl-state') && document.querySelector('#smsgs .clive .cl-state').textContent.length > 0", timeout=10)
    first = shell_state(browser)
    assert first["text"] == "" and first["state"] == "live", first
    assert first["status"] in ("Sent", "Starting Claude", "Waiting for Claude"), first
    assert first["stop"] is True
    assert browser.js("document.getElementById('ssend').textContent") == "Stop"
    # streamed: the text grows in more than one step, in the same node
    seen: list[str] = []
    marked = False
    deadline = time.time() + 20
    while time.time() < deadline:
        s = shell_state(browser)
        if s and s["text"] and (not seen or seen[-1] != s["text"]):
            seen.append(s["text"])
            if not marked:
                mark_nodes(browser)                       # the reply item and its text block exist now: they must be the very nodes that settle
                marked = True
        if s and s["state"] == "ok":
            break
        time.sleep(0.04)
    assert len(seen) >= 3, f"the text arrived in {len(seen)} steps: {seen}"
    assert all(b.startswith(a) for a, b in zip(seen, seen[1:])), "the text only grew"
    final = shell_state(browser)
    assert final["state"] == "ok" and final["text"] == "Hello! I can help with the cafe's website. Ask me anything."
    assert final["copy"] is True and final["stop"] is False and final["id"] != ""
    assert unmarked(browser) == 0, "no node of the reply was recreated while it streamed and settled"
    assert browser.count("#smsgs .clive") == 1, "one reply item, no duplicate assistant message"
    assert browser.js("document.getElementById('ssend').textContent") == "Send"
    assert browser.js("document.getElementById('sstream').hidden") is True
    shot(browser, "01-normal-settled.png")
    clean(browser, "normal")


# ------------------------------------------------------------------------------------------------------------------------------------------------------------
# 2. long: markdown with a table and a code fence, 6 KB; no layout jump at settle; the fence node is never recreated; the page keeps its place
# ------------------------------------------------------------------------------------------------------------------------------------------------------------
LONG = ("## Plan\n\nHere is the plan for the site, in short paragraphs that read well.\n\n- Home page with the menu\n- Opening hours and the map\n- A pre-order form for pickup\n\n"
        "| Page | Owner | Status |\n|---|---|---|\n| Home | Ana | done |\n| Menu | Ben | draft |\n| Contact | Cy | todo |\n\n"
        "```python\ndef price(item):\n    # the menu price in rupees\n    return item.base * 1.18\n```\n\n"
        + "\n\n".join(f"Paragraph {i}: the menu lists coffee, tea and pastries, each with a short description and a price in rupees." for i in range(1, 25)) + "\n\nThat is all.")


@pytest.mark.browser
def test_long_reply_with_table_and_code_fence_does_not_jump_or_remount_and_highlights_on_settle(make, browser):
    live = make([Text(LONG, pieces=90)], delay="0.05")
    home(browser, live)
    ask(browser, "Plan the site")
    browser.wait_for("!!document.querySelector('#smsgs .clive pre')", timeout=30)
    pre_before = browser.js("(() => { const p = document.querySelector('#smsgs .clive pre'); p.__mark = 'fence'; return p.textContent; })()")
    assert browser.js("document.querySelectorAll('#smsgs .clive pre .tk-k, #smsgs .clive pre .tk-s').length") == 0 or "def price" in pre_before
    browser.wait_for("document.querySelector('#smsgs .clive').dataset.state === 'ok'", timeout=60)
    still = browser.js("(() => { const p = document.querySelector('#smsgs .clive pre'); return p && p.__mark === 'fence'; })()")
    assert still is True, "the code block that streamed is the node that settled"
    assert browser.js("document.querySelectorAll('#smsgs .clive pre .tk-k').length") >= 1, "highlighted once it settled"
    assert browser.js("document.querySelectorAll('#smsgs .clive table').length") == 1
    assert browser.js("document.querySelectorAll('#smsgs .clive .cl-copycode').length") == 1
    assert "def price" in browser.js("document.querySelector('#smsgs .clive pre code').textContent")
    assert browser.js("document.body.scrollWidth <= window.innerWidth + 1") is True
    shot(browser, "02-long-settled.png")
    clean(browser, "long")


@pytest.mark.browser
def test_the_reply_item_does_not_move_when_it_settles(make, browser):
    live = make([Think(), Tool("Read", {"file_path": "notes.txt"}, "scratch notes"), Text("The notes say three things: build, test and ship the site.", pieces=6)], delay="0.2")
    home(browser, live)
    ask(browser, "Read the notes")
    browser.wait_for("(() => { const s = document.querySelector('#smsgs .clive'); return !!s && s.dataset.state === 'live' && s.querySelectorAll('.cl-text').length > 0 && s.querySelector('.cl-text').textContent.length > 20; })()", timeout=30)
    # while it writes its last words, sample the item's box until it has settled: the top and the left may not move, and the height only grows with its text
    samples = []
    deadline = time.time() + 30
    while time.time() < deadline:
        s = browser.js("""(() => { const e = document.querySelector('#smsgs .clive'); if (!e) return null; const r = e.getBoundingClientRect(); const box = document.getElementById('smsgs');
          return {state: e.dataset.state, top: Math.round(r.top - box.getBoundingClientRect().top + box.scrollTop), left: Math.round(r.left), height: Math.round(r.height)}; })()""")
        if s:
            samples.append(s)
            if s["state"] == "ok":
                break
        time.sleep(0.03)
    assert samples and samples[-1]["state"] == "ok"
    tops = {s["top"] for s in samples}
    assert len(tops) == 1, f"the reply item moved: {sorted(tops)}"
    live_h = [s["height"] for s in samples if s["state"] == "live"][-3:]
    settled_h = samples[-1]["height"]
    assert settled_h >= min(live_h or [0]) - 2, f"the item shrank at settle: live {live_h}, settled {settled_h}"
    # the action row keeps its place (Stop becomes Copy in a row of the same height)
    assert settled_h - max(live_h or [settled_h]) <= 40, f"the item jumped by {settled_h - max(live_h)} px at settle"
    clean(browser, "no jump")


# ------------------------------------------------------------------------------------------------------------------------------------------------------------
# 3. tool: "Using Read", then its real target; the timeline stays honest; expandable
# ------------------------------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.browser
def test_tool_turn_shows_the_real_tool_line_its_target_its_end_and_expands(make, browser, tmp_path):
    work = tmp_path / "work"
    live = make([Think(), Tool("Read", {"file_path": str(work / "notes.txt")}, "1\tscratch notes"), Tool("Bash", {"command": "ls -la"}, "total 0"),
                 Text("I read the notes and listed the folder. Nothing else to do.", pieces=5)], delay="0.35")
    home(browser, live)
    ask(browser, "Look around")
    browser.wait_for("document.querySelectorAll('#smsgs .clive .cl-think').length > 0", timeout=30)
    names = []
    deadline = time.time() + 40
    while time.time() < deadline:
        s = shell_state(browser)
        if s:
            for t in s["tools"]:
                if t not in names:
                    names.append(t)
            if s["state"] == "ok":
                break
        time.sleep(0.05)
    assert any(n.startswith("Using ") for n in names) or any("Read" in n or "notes.txt" in n for n in names), names
    final = shell_state(browser)
    assert final["state"] == "ok" and len(final["tools"]) == 2, final
    assert any("notes.txt" in t for t in final["tools"]), final["tools"]
    assert not any(str(work) in t for t in final["tools"]), "a path under the work folder is shown relative to it, never absolute"
    assert browser.js("document.querySelectorAll('#smsgs .clive .cl-tool[data-status=ok]').length") == 2
    assert browser.js("document.querySelectorAll('#smsgs .clive .cl-think').length") == 1
    assert "%" not in browser.js("document.querySelector('#smsgs .clive').textContent"), "no percentage anywhere"
    browser.js("document.querySelector('#smsgs .clive .cl-tool summary').click()")
    assert browser.js("document.querySelector('#smsgs .clive .cl-tool').open") is True
    assert "Status: Done" in browser.js("document.querySelector('#smsgs .clive .cl-tool .cl-detail').textContent")
    shot(browser, "03-tool-settled.png")
    clean(browser, "tool")


# ------------------------------------------------------------------------------------------------------------------------------------------------------------
# 4. multi-stage: text, tool, text, tool, text in order; reload mid-turn reattaches (stream first, then snapshot)
# ------------------------------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.browser
def test_multi_stage_turn_keeps_its_order_and_a_reload_mid_turn_reattaches(make, browser):
    live = make([Text("First I will look at the notes before anything else.", pieces=4), Tool("Read", {"file_path": "a.txt"}, "alpha"), Text("Then I will check the second file as well.", pieces=4),
                 Tool("Grep", {"pattern": "beta"}, "beta found"), Text("Both files agree. The work is done and nothing needs changing.", pieces=5)], delay="0.3")
    home(browser, live)
    ask(browser, "Check both files")
    browser.wait_for("(() => { const s = document.querySelector('#smsgs .clive'); return !!s && s.querySelectorAll('.cl-tool').length >= 1; })()", timeout=40)
    # a reload in the middle of the turn: the page opens the stream, reads the snapshot and shows the turn again, with Stop
    browser.reload()
    browser.wait_for("window.HomePage && HomePage.state().loaded === true", timeout=20)
    browser.wait_for("(() => { const s = document.querySelector('#smsgs .clive'); return !!s && s.dataset.state === 'live'; })()", timeout=20)
    assert browser.js("document.getElementById('ssend').textContent") == "Stop"
    assert browser.count("#smsgs .clive") == 1
    browser.wait_for("document.querySelector('#smsgs .clive').dataset.state === 'ok'", timeout=60)
    kinds = browser.js("Array.from(document.querySelectorAll('#smsgs .clive .cl-block')).map(n => n.classList.contains('cl-text') ? 'text' : (n.classList.contains('cl-tool') ? 'tool' : 'think'))")
    assert kinds == ["text", "tool", "text", "tool", "text"], kinds
    assert browser.count("#smsgs .clive") == 1, "no duplicate assistant message after the reattach"
    shot(browser, "04-multi-stage.png")
    clean(browser, "multi-stage")


# ------------------------------------------------------------------------------------------------------------------------------------------------------------
# 5. cancel: Stop really stops the process; the text on screen is what is stored
# ------------------------------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.browser
def test_stop_cancels_the_process_and_what_is_shown_is_what_is_stored(make, browser):
    live = make([Text("A very long answer that is still being written when the owner presses Stop. " * 12, pieces=240)], delay="0.1")
    home(browser, live)
    ask(browser, "Write at length")
    browser.wait_for("(() => { const s = document.querySelector('#smsgs .clive'); return !!s && s.querySelector('.cl-text') && s.querySelector('.cl-text').textContent.length > 60; })()", timeout=30)
    t0 = time.time()
    browser.click("#smsgs .clive [data-act=composer-stop]")
    browser.wait_for("document.querySelector('#smsgs .clive .cl-state') && document.querySelector('#smsgs .clive .cl-state').textContent === 'Stopping'", timeout=5)
    assert time.time() - t0 < 3, "Stopping shows at once"
    browser.wait_for("document.querySelector('#smsgs .clive').dataset.state === 'stopped' || document.querySelector('#smsgs .clive').dataset.state === 'ok'", timeout=30)
    shown = browser.js("document.querySelector('#smsgs .clive .cl-text').textContent")
    live.until("the stopped reply to be stored", lambda: any(m["role"] == "agent" and m.get("turn") for m in live.messages(ORG)))
    stored = [m for m in live.messages(ORG) if m["role"] == "agent" and m.get("kind") == "text"][-1]["text"]
    assert shown == stored, f"shown {len(shown)} characters, stored {len(stored)}"
    assert len(shown) < len("A very long answer that is still being written when the owner presses Stop. " * 12)
    live.until("the process to be gone", lambda: not direct_running.RUNNING)
    assert browser.js("document.getElementById('ssend').textContent") == "Send"
    assert browser.js("!!document.querySelector('#smsgs .nmsg.note')") is True, "the calm note that says it was stopped"
    shot(browser, "05-stopped.png")
    clean(browser, "cancel")


# ------------------------------------------------------------------------------------------------------------------------------------------------------------
# 6. network drop: the stream goes away mid-turn; the page catches up from the snapshot, no word is repeated or lost, no second reply
# ------------------------------------------------------------------------------------------------------------------------------------------------------------
DROP_JS = """(() => {
  if (window.__drop) return;
  const Native = window.EventSource; window.__sources = [];
  window.EventSource = function (url, opts) { const es = new Native(url, opts); window.__sources.push(es); return es; };
  window.EventSource.prototype = Native.prototype; window.EventSource.CONNECTING = 0; window.EventSource.OPEN = 1; window.EventSource.CLOSED = 2;
  window.__drop = () => { window.__sources.forEach(es => { try { es.close(); es.dispatchEvent(new Event('error')); } catch (e) {} }); };
})()"""


@pytest.mark.browser
def test_network_drop_mid_turn_catches_up_with_no_repeated_or_lost_text_and_one_reply(make, browser):
    text = "".join(f"Sentence number {i} of the answer arrives here. " for i in range(1, 31))
    live = make([Text(text, pieces=120)], delay="0.08")
    browser._send("Page.addScriptToEvaluateOnNewDocument", {"source": DROP_JS})
    home(browser, live)
    browser.js(DROP_JS)
    ask(browser, "Say a lot")
    browser.wait_for("(() => { const s = document.querySelector('#smsgs .clive .cl-text'); return !!s && s.textContent.length > 150; })()", timeout=30)
    before = browser.js("document.querySelector('#smsgs .clive .cl-text').textContent.length")
    browser.js("window.__drop()")                              # the connection dies; the page's own handle makes a new one after a second
    browser.wait_for("document.querySelector('#smsgs .clive').dataset.state === 'ok'", timeout=60)
    final = browser.js("document.querySelector('#smsgs .clive .cl-text').textContent")
    assert final == text.strip() or final == text, "the text is whole: nothing repeated, nothing lost"
    assert len(final) > before
    assert browser.count("#smsgs .clive") == 1
    others = browser.js("Array.from(document.querySelectorAll('#smsgs .nmsg.sb.team:not(.clive):not(.starter)')).map(n => n.textContent.slice(0, 60))")
    assert not any("Sentence number" in t for t in others), f"the reply is also drawn as a second assistant message: {others}"
    stored = [m for m in live.messages(ORG) if m["role"] == "agent" and m.get("kind") == "text" and m.get("turn")]
    assert len(stored) == 1 and stored[0]["text"] == final
    shot(browser, "06-after-network-drop.png")
    clean(browser, "network drop")


# ------------------------------------------------------------------------------------------------------------------------------------------------------------
# 7. error: the provider fails; the reason is real, Send is back, and Retry answers again as a new try
# ------------------------------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.browser
def test_provider_error_ends_with_its_reason_and_retry_answers_again(make, browser):
    live = make("not_logged_in", [Text("Second time lucky: here is the answer you asked for.", pieces=4)], codex="not_signed_in", delay="0.05")
    home(browser, live)
    ask(browser, "Try this")
    browser.wait_for("!!document.querySelector('#smsgs .nmsg.oops, #smsgs .clive[data-state=error]')", timeout=60)
    assert browser.js("document.getElementById('ssend').textContent") == "Send"
    words = browser.js("document.querySelector('#smsgs .nmsg.oops, #smsgs .clive[data-state=error]').textContent")
    assert words.strip() != "" and "Stopping" not in words
    print("ERROR WORDS:", words)
    assert browser.exists("#smsgs [data-act=retry-direct]"), "Retry is offered on the failed line"
    shot(browser, "07-error.png")
    browser.click("#smsgs [data-act=retry-direct]")
    browser.wait_for("document.querySelectorAll('#smsgs .clive').length >= 1 && Array.from(document.querySelectorAll('#smsgs .clive')).some(n => n.dataset.attempt === '2' && n.dataset.state === 'ok')", timeout=60)
    assert "Second time lucky" in browser.js("Array.from(document.querySelectorAll('#smsgs .clive')).filter(n => n.dataset.attempt === '2')[0].textContent")
    assert browser.js("document.querySelectorAll('#smsgs .nmsg.me').length") == 1, "a retry adds no second owner line"
    clean(browser, "error")


# a first try that fails and is tried again by the router: the page says who failed and why, counts down the real wait, then shows the new try; Stop ends the wait at once
@pytest.mark.browser
def test_router_backoff_shows_the_real_reason_and_countdown_and_stop_ends_the_wait(make, browser):
    live = make("crash", "crash", "crash", codex="crash,crash", delay="0.05")
    home(browser, live)
    ask(browser, "Try this")
    browser.wait_for("document.querySelector('#smsgs .clive') && /failed/.test(document.querySelector('#smsgs .clive .cl-state').textContent)", timeout=30)
    s = shell_state(browser)
    assert s["phase"] == "backoff" and "Retrying" in s["status"] or "Trying" in s["status"], s
    assert s["clock"].startswith("in ") or "Trying" in s["status"], s
    shot(browser, "07b-backoff.png")
    t0 = time.time()
    browser.click("#smsgs .clive [data-act=composer-stop]")
    browser.wait_for("['stopped', 'error', 'ok'].includes(document.querySelector('#smsgs .clive').dataset.state)", timeout=15)
    assert time.time() - t0 < 6, "Stop does not wait for the length of the back-off"
    live.until("the turn to be over", lambda: not direct_running.RUNNING)
    clean(browser, "backoff")


# ------------------------------------------------------------------------------------------------------------------------------------------------------------
# 8. existing conversation: older replies (a legacy one with its tools folded, a plain one) render through the same model, and a new turn goes on below them
# ------------------------------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.browser
def test_an_existing_conversation_renders_through_the_same_model_and_a_new_turn_continues_it(make, browser):
    live = make([Text("First answer, complete and settled.", pieces=3)], [Think(), Tool("Read", {"file_path": "x.txt"}, "xx"), Text("Second answer, after reading the file.", pieces=3)], delay="0.05")
    home(browser, live)
    ask(browser, "One")
    browser.wait_for("document.querySelectorAll('#smsgs .clive[data-state=ok]').length === 1", timeout=60)
    ask(browser, "Two")
    browser.wait_for("document.querySelectorAll('#smsgs .clive[data-state=ok]').length === 2", timeout=60)
    ids = browser.js("Array.from(document.querySelectorAll('#smsgs .clive')).map(n => n.dataset.turn + ':' + n.dataset.attempt)")
    assert len(set(ids)) == 2
    browser.reload()                                                                  # the same two replies, drawn from the stored messages alone
    browser.wait_for("window.HomePage && HomePage.state().loaded === true", timeout=20)
    browser.wait_for("document.querySelectorAll('#smsgs .clive').length === 2", timeout=20)
    texts = browser.js("Array.from(document.querySelectorAll('#smsgs .clive')).map(n => n.querySelector('.cl-text').textContent)")
    assert texts == ["First answer, complete and settled.", "Second answer, after reading the file."]
    assert browser.js("document.querySelectorAll('#smsgs .clive')[1].querySelectorAll('.cl-tool').length") == 1
    assert browser.js("document.querySelectorAll('#smsgs .clive.cl-live').length") == 0
    shot(browser, "08-existing-conversation.png")
    clean(browser, "existing conversation")


# ------------------------------------------------------------------------------------------------------------------------------------------------------------
# reduced motion, phone width
# ------------------------------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.browser
def test_reduced_motion_stops_the_loops_and_the_entrances_but_the_state_still_changes(make, browser):
    browser._send("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-reduced-motion", "value": "reduce"}]})
    live = make([Think(), Text("A reply under reduced motion, which still arrives and settles.", pieces=5)], delay="0.2")
    home(browser, live)
    ask(browser, "Hello")
    browser.wait_for("!!document.querySelector('#smsgs .clive .cl-state')", timeout=20)
    names = browser.js("""(() => Array.from(document.querySelectorAll('#smsgs .clive *, #smsgs .clive')).map(n => getComputedStyle(n).animationName).filter(a => a && a !== 'none'))()""")
    assert names == [], names
    browser.wait_for("document.querySelector('#smsgs .clive').dataset.state === 'ok'", timeout=40)
    assert "reduced motion" in browser.js("document.querySelector('#smsgs .clive .cl-text').textContent")
    clean(browser, "reduced motion")


@pytest.mark.browser
def test_phone_width_has_no_horizontal_scroll_and_a_usable_stop(make, browser):
    live = make([Tool("Bash", {"command": "ls " + "x" * 120}, "out"), Text(LONG[:2500], pieces=40)], delay="0.1")
    browser.set_size(375, 740)
    home(browser, live)
    ask(browser, "Hello on a phone")
    browser.wait_for("!!document.querySelector('#smsgs .clive [data-act=composer-stop]')", timeout=30)
    box = browser.js("(() => { const b = document.querySelector('#smsgs .clive [data-act=composer-stop]').getBoundingClientRect(); return {w: b.width, h: b.height}; })()")
    assert box["h"] >= 30 and box["w"] >= 40, box
    browser.wait_for("document.querySelector('#smsgs .clive').dataset.state === 'ok'", timeout=60)
    assert browser.js("document.documentElement.scrollWidth <= window.innerWidth + 1") is True
    assert browser.js("(() => { const s = document.querySelector('#smsgs'); return s.scrollWidth <= s.clientWidth + 1; })()") is True
    shot(browser, "09-phone.png")
    clean(browser, "phone")
