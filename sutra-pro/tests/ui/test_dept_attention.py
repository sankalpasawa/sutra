"""The org-wide "N need you" pill on a team page and on the console (gap package attention, docs/notes/GAP-attention.md). A real headless
Chrome over the fake backend (`SUTRA_BROWSER=1`): the J2 page is not edited, dept_ext.js adds the scripts."""
from __future__ import annotations

import pytest
from test_dept_page import Page

browser_only = pytest.mark.browser


@pytest.fixture()
def team(fake_server, fake, browser) -> Page:
    fake.stage("2")          # the Web team asks about the menu: one thing needs the owner
    return Page(browser, fake_server)


@browser_only
def test_a_team_page_shows_the_org_wide_pill_and_it_goes_when_the_question_is_answered(team):
    team.open()
    team.b.wait_for("!!document.querySelector('#attnpill .apill')")
    assert team.b.text("#attnpill .apill") == "1 needs you"
    assert team.js("document.querySelector('#attnpill .apill').getAttribute('href')") == "/"
    assert team.js("document.querySelector('#attnpill .apill').getAttribute('aria-label')") == "1 needs you"
    team.b.wait_for("document.title === '(1) Web · Sutra'")
    status, _ = team.fake.post(f"/api/chats/{team.fake.get('/api/needs-you')[1][0]['session_id']}/messages", {"text": "Option 1"})
    assert status in (200, 202)
    team.b.wait_for("document.getElementById('attnpill').hidden === true", timeout=12)        # its next read (5 s while in front)
    assert team.fake.log("/api/events") == [], "the pill reads; it never opens a second stream (the page keeps one, DeptExt's)"
    team.b.wait_for("document.title === 'Web · Sutra'")
    assert team.b.console_errors == []


@browser_only
def test_a_crash_elsewhere_shows_on_the_pill_with_its_own_words(team):
    team.open()
    team.b.wait_for("!!document.querySelector('#attnpill .apill')")
    crash = {"kind": "problem", "tone": "err", "task_id": "tsk_00000000beef", "dept_id": "sales", "dept_name": "Sales", "title": "Quote", "status": "crashed",
             "text": 'Sales ran into a problem on "Quote"', "outcome": "", "at": "2026-11-04T10:00:00Z", "since_s": 60, "retry": True}
    team.fake.request("POST", "/__fake/heads-up", {"items": [crash]})
    team.b.wait_for("document.querySelector('#attnpill .apill') && document.querySelector('#attnpill .apill').textContent === '2 need you 1 to try again'",
                    timeout=12)
    assert "fresh" in team.js("document.querySelector('#attnpill .apill').className")      # the count went up: it pulses (no motion under reduce)


@browser_only
def test_the_console_has_the_pill_too(fake_server, fake, browser):
    fake.stage("2")
    for part in ("/api/ops/", "/api/connectors/status", "/api/atoms/"):           # the console's own routes are not in this fake (test_console.py has them)
        browser.expect_failed(part, 404)
    browser.goto(fake_server.url + "/console")
    browser.wait_for("!!document.querySelector('#attnpill .apill')")
    assert browser.text("#attnpill .apill") == "1 needs you"
    browser.wait_for("document.title.startsWith('(1) ')")
