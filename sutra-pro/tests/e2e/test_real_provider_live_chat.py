"""The live direct chat against the REAL Claude CLI, in a real Chrome (streaming design, STR-13; analysis section 9).

Opt-in and costs a little of the owner's plan: it makes two short calls (one answered, one stopped). It runs only with `SUTRA_LIVE=1 SUTRA_BROWSER=1`, only where `claude` is on the PATH
and signed in, and only on the owner's go-ahead (the same rule as tests/live):

    SUTRA_LIVE=1 SUTRA_BROWSER=1 scripts/py -m pytest tests/e2e/test_real_provider_live_chat.py -q -s

What it measures is printed, not asserted against a budget (a model's speed is not ours): the time from Send to the first visible state, to the first word, and from Stop to the process
being gone. What it asserts is what must hold with any provider: a visible state before the first word, text that grows in the one node, a Stop that ends the process, and one stored reply.
POSIX only. Not run in CI; nothing is claimed for Windows."""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

import pytest
from harness import ORG, LiveApp

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ui"))      # `import cdp`
import cdp  # noqa: E402

from sutra_app.orchestrator import direct_running  # noqa: E402

pytestmark = [pytest.mark.live, pytest.mark.browser, pytest.mark.skipif(sys.platform == "win32", reason="POSIX only"),
              pytest.mark.skipif(shutil.which("claude") is None, reason="the claude CLI is not installed")]


@pytest.mark.live
@pytest.mark.browser
def test_real_claude_streams_into_one_node_and_stop_ends_the_process(tmp_path):
    chrome = cdp.find_chrome()
    if chrome is None:
        pytest.skip("Chrome is not installed")
    live = LiveApp(tmp_path, connector_name="auto", offline=False)
    live.settings = live.settings.model_copy(update={"live_v1": True})
    live.start()
    live.welcome_seen()
    try:
        with cdp.Browser(chrome) as browser:
            browser.goto(live.base_url + "/")
            browser.wait_for("window.HomePage && HomePage.state().loaded === true")
            browser.click('#sbar [data-mode="direct"]')
            browser.wait_for("!!document.querySelector('#sbar .ccinput')")
            t0 = time.time()
            browser.type("#sbox", "Count from 1 to 40, one number per line, then stop.")
            browser.click("#ssend")
            browser.wait_for("!!document.querySelector('#smsgs .clive .cl-state') && document.querySelector('#smsgs .clive .cl-state').textContent !== ''", timeout=30)
            first_state = time.time() - t0
            browser.wait_for("(() => { const t = document.querySelector('#smsgs .clive .cl-text'); return !!t && t.textContent.length > 0; })()", timeout=120)
            first_word = time.time() - t0
            print(f"first visible state {first_state:.2f} s, first word {first_word:.2f} s")
            assert first_state <= first_word
            browser.wait_for("document.querySelector('#smsgs .clive').dataset.state === 'ok'", timeout=180)
            assert browser.count("#smsgs .clive") == 1
            stored = [m for m in live.messages(ORG) if m["role"] == "agent" and m.get("turn")]
            assert len(stored) == 1 and stored[0]["text"] == browser.js("document.querySelector('#smsgs .clive .cl-text').textContent")
            browser.type("#sbox", "Write the numbers 1 to 400, one per line, slowly.")
            browser.click("#ssend")
            browser.wait_for("(() => { const t = document.querySelectorAll('#smsgs .clive')[1]; return !!t && t.querySelector('.cl-text') && t.querySelector('.cl-text').textContent.length > 10; })()", timeout=120)
            t1 = time.time()
            browser.click("#smsgs .clive:last-of-type [data-act=composer-stop]")
            live.until("the process to be gone", lambda: not direct_running.RUNNING, timeout=30)
            print(f"stop to process gone {time.time() - t1:.2f} s")
            browser.wait_for("['stopped', 'ok'].includes(document.querySelectorAll('#smsgs .clive')[1].dataset.state)", timeout=30)
    finally:
        live.stop()
        live.kill_engines()
