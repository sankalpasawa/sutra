"""Home's attention parts (gap package attention, docs/notes/GAP-attention.md): the Heads up lane, Try again, the count in the strip, the
badge and the tab title, and the age of each ask. The page-file checks run in the merge gate; the rest drive a real headless Chrome over the
fake backend (`SUTRA_BROWSER=1`)."""
from __future__ import annotations

import re

import pytest
from test_home import HOME, load, posts, present, absent, texts

from sutra_app.ui import STATIC_DIR

browser_only = pytest.mark.browser
CRASHED = "tsk_b7c8d9e0f1a2"          # the task of the org chat's done card in the "full" story
DONE = "tsk_00000000abcd"


def lane_rows():
    return [
        {"kind": "problem", "tone": "err", "task_id": CRASHED, "dept_id": "content", "dept_name": "Content", "title": "Menu page copy", "status": "crashed",
         "text": 'Content ran into a problem on "Menu page copy"', "outcome": "The team stopped unexpectedly.", "at": "2026-11-04T10:36:00Z",
         "since_s": 7200, "retry": True},
        {"kind": "finished", "tone": "ok", "task_id": DONE, "dept_id": "web", "dept_name": "Web", "title": "Landing page", "status": "done",
         "text": 'Web finished "Landing page"', "outcome": "", "at": "2026-11-04T10:30:00Z", "since_s": 600, "retry": False},
    ]


def open_home(browser, fake, stage):
    """Home on one stage."""
    load(browser, fake, stage=stage)


def console_errors(browser):
    return [line for line in browser.console_errors if "404" not in line]


def test_home_loads_the_two_attention_modules_before_its_controller():
    scripts = re.findall(r'<script src="/ui/js/([\w.]+\.js)"', HOME)
    for name in ("heads_up_view.js", "chat_attention.js"):
        assert (STATIC_DIR / "js" / name).is_file()
        assert scripts.index(name) < scripts.index("home.js")


@browser_only
def test_a_crash_is_counted_offers_try_again_in_the_lane_and_on_its_card_and_goes_once_retried(browser, fake):
    open_home(browser, fake, "full")
    waiting = len(fake.get("/api/needs-you")[1])
    status, _ = fake.request("POST", "/__fake/heads-up", {"items": lane_rows()})
    assert status == 200
    present(browser, '#needs .huitem[data-kind="problem"]')
    assert texts(browser, "#needcount") == [str(waiting + 1)]                     # the crash counts; the finished row does not
    assert browser.js("document.title") == f"({waiting + 1}) Sutra"
    assert texts(browser, "#needs .huitem .hutext") == ['Content ran into a problem on "Menu page copy"', 'Web finished "Landing page"']
    present(browser, f'.c-done[data-task="{CRASHED}"] [data-act="retry-task"]')
    browser.click('#needs .huitem[data-kind="problem"] [data-act="retry-task"]')
    absent(browser, '#needs .huitem[data-kind="problem"]')
    sent = [r for r in posts(fake) if r["path"] == f"/api/tasks/{CRASHED}/retry"]
    assert len(sent) == 1 and sent[0]["token"] is True
    absent(browser, f'.c-done[data-task="{CRASHED}"] [data-act="retry-task"]')     # the card's button goes with the problem
    assert texts(browser, "#needcount") == [str(waiting)]
    assert browser.js("document.title") == (f"({waiting}) Sutra" if waiting else "Sutra")
    assert console_errors(browser) == []


@browser_only
def test_got_it_hides_a_heads_up_row_in_this_browser(browser, fake):
    open_home(browser, fake, "full")
    fake.request("POST", "/__fake/heads-up", {"items": lane_rows()[1:]})
    present(browser, '#needs .huitem[data-kind="finished"]')
    browser.click('#needs .huitem[data-kind="finished"] [data-act="headsup-seen"]')
    absent(browser, '#needs .huitem[data-kind="finished"]')
    assert DONE in browser.js("localStorage.getItem('sutra:headsup:seen') || ''")
    browser.js("HomePage.loadAll()")
    assert browser.count('#needs .huitem[data-kind="finished"]') == 0


@browser_only
def test_an_ask_says_how_long_it_has_waited(browser, fake):
    open_home(browser, fake, "2")
    browser.js("HomePage.state().needs.forEach(n => { n.waiting_s = 3 * 86400; n.stale = true; }); HomePage.renderNeeds()")
    assert texts(browser, "#needs .needitem .nwait.stale") == ["waiting 3 days"]
    assert texts(browser, "#needs .needitem span") == ["Web: Should the menu show prices?"]     # the question itself is unchanged
