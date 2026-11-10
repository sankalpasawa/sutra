"""The org-wide "N need you" pill on a team page and on the console (gap package attention, docs/notes/GAP-attention.md). A real headless
Chrome over the fake backend (`SUTRA_BROWSER=1`): the J2 page is not edited, dept_ext.js adds the scripts. The pill's place on the console, clear of the header's links from 320 to
1920 px wide, is measured here; its place on the Simple and the Detailed view of a team page is in test_dept_page.py."""
from __future__ import annotations

import json

import pytest
from test_dept_page import CRASH_ELSEWHERE, PILL_WIDTHS, Page, measure_the_pill, pill_problems, pill_sweep_height

browser_only = pytest.mark.browser

CONSOLE_ROUTES = ("/api/ops/", "/api/connectors/status", "/api/atoms/")           # the console's own routes are not in this fake (test_console.py has them)
CONSOLE_LINKS = ['.shead a.ghost', '.cjump a[href="#c-usage"]', '.cjump a[href="#c-log"]', '.cjump a[href="#c-health"]']      # Home and the three links under the title
CONSOLE_PHONE = 600                                                              # up to here the header's links wrap under its title, and the pill has a row above the header
CONSOLE_REGIONS = [".shead > *", ".cpanel"]                                       # what the pill's row keeps clear of


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


def console_ready(browser, text: str) -> None:
    browser.wait_for("!!document.querySelector('#attnpill a.apill') && document.querySelector('#attnpill a.apill').textContent === " + json.dumps(text))


@browser_only
def test_the_pill_does_not_sit_on_the_consoles_links_at_phone_widths(fake_server, fake, browser):
    """At 600px and under the console's three links ("Usage and cost", "Atom log", "Health") wrap to a row under its title, which is where the pill rode (58px from the top): the long pill
    covered "Atom log" and "Health" at 320px and "Health" at 360 and 375px, the plain one ("1 needs you") "Health" at 320px, and a click on the link went to Home. The pill has a row above
    the header's own now: no control and no part of the header or of the panels is under it, and the links take their own clicks (the page goes to the panel and stays on the console)."""
    fake.stage("2")
    for part in CONSOLE_ROUTES:
        browser.expect_failed(part, 404)
    browser.expect_failed("/providers", 404)           # a click that lands on the pill goes to Home, whose chat asks for what the fake does not have (pre-existing, as the Home tests announce)
    problems: list[tuple] = []
    for text in ("1 needs you", "2 need you 1 to try again"):
        if text != "1 needs you":
            fake.request("POST", "/__fake/heads-up", {"items": [CRASH_ELSEWHERE]})        # one thing for the owner here and one problem elsewhere
        for width in (320, 360, 375, 414, 480, CONSOLE_PHONE):
            browser.set_size(width, 812)
            browser.goto(fake_server.url + "/console")
            console_ready(browser, text)
            seen = measure_the_pill(browser, CONSOLE_LINKS, CONSOLE_REGIONS)
            assert seen["missing"] == [] and seen["swept"] > len(CONSOLE_LINKS), seen            # the links to clear are really on screen
            found = pill_problems(seen, boxes=True, regions=True)
            if found:
                problems.append((text, width, found, seen["box"]))
            for link, panel in (('.cjump a[href="#c-log"]', "#c-log"), ('.cjump a[href="#c-health"]', "#c-health")):
                browser.click(link)                                                      # a real click in the middle of the link
                here = browser.js("location.pathname + location.hash")
                if here != "/console" + panel:
                    problems.append((text, width, f"a click on {link} went to {here}"))
                    break
    assert problems == [], problems
    assert browser.console_errors == [] or all("404" in line for line in browser.console_errors), browser.console_errors


@browser_only
def test_the_pill_is_clear_of_the_console_from_320_to_1920_wide_in_both_themes(fake_server, fake, browser):
    """The pill with the most to say ("2 need you, 1 to try again") on the console at every width from a small phone to a wide screen, in both themes: no control under it, it is on
    screen and under a click, Home and the three links take their own clicks, no sideways scroll; at 600px and under, where it has a row above the header, no part of the header or of the
    panels meets it either, and at 900px and under no control's box does."""
    fake.stage("2")
    fake.request("POST", "/__fake/heads-up", {"items": [CRASH_ELSEWHERE]})
    for part in CONSOLE_ROUTES:
        browser.expect_failed(part, 404)
    problems: list[tuple] = []
    for theme in ("light", "dark"):
        browser.set_theme(theme)
        for width in PILL_WIDTHS:
            browser.set_size(width, pill_sweep_height(width))
            browser.goto(fake_server.url + "/console")
            console_ready(browser, "2 need you 1 to try again")
            seen = measure_the_pill(browser, CONSOLE_LINKS, CONSOLE_REGIONS if width <= CONSOLE_PHONE else [])
            found = pill_problems(seen, boxes=width <= 900, regions=width <= CONSOLE_PHONE)
            if found:
                problems.append((theme, width, found, seen["box"]))
    assert problems == [], problems
    assert browser.console_errors == [] or all("404" in line for line in browser.console_errors), browser.console_errors
