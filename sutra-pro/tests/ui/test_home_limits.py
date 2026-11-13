"""Home's limits, notifications and recurring work (gap package routines-limits, docs/notes/GAP2-routines-limits.md): the line in the Needs strip, the three
Settings groups and what they send. The page-file checks run in the merge gate; the rest drive a real headless Chrome over the fake backend (`SUTRA_BROWSER=1`)."""
from __future__ import annotations

import re

import pytest
from test_home import HOME, load, posts, present, absent, texts

from sutra_app.ui import STATIC_DIR

browser_only = pytest.mark.browser

WARN = {"spend": {"limit": 10.0, "spent": 8.2, "pct": 0.82, "level": "warn", "line": "About $8.20 of your $10 monthly limit"}}
HOLD = {"guard": {"enabled": True, "level": "hold", "holding": True, "line": "Claude weekly window is at 83%, resets Fri 09:00", "top": {"continued": False}}}


def open_home(browser, fake, stage="1"):
    """Home on one stage."""
    load(browser, fake, stage=stage)


def open_settings(browser, group):
    browser.click(f'#rail [data-pane="settings"][data-group="{group}"]')
    present(browser, f'#pane-settings .setgrp[data-group="{group}"]')


def console_errors(browser):
    return [line for line in browser.console_errors if "404" not in line]


def test_home_loads_the_two_new_modules_before_its_controller_and_has_a_place_for_each_group():
    scripts = re.findall(r'<script src="/ui/js/([\w.]+\.js)"', HOME)
    for name in ("limits_view.js", "recurring_view.js"):
        assert (STATIC_DIR / "js" / name).is_file()
        assert scripts.index(name) < scripts.index("home.js")
    for ident in ("set-limits", "set-notices", "set-recurring"):
        assert f'id="{ident}"' in HOME


@browser_only
def test_the_strip_says_nothing_until_a_limit_is_near_then_one_line_each(browser, fake):
    open_home(browser, fake)
    assert texts(browser, "#needs .nylimit") == []
    fake.request("POST", "/__fake/limits", WARN)
    present(browser, "#needs .nylimit")
    assert texts(browser, "#needs .nylimit") == ["About $8.20 of your $10 monthly limit"]
    fake.request("POST", "/__fake/limits", {"spend": {"level": "over", "line": "This month's spending limit is used up: about $10.20 of your $10 monthly limit."}})
    browser.wait_for("document.querySelector('#needs .nylimit[data-level=bad]') !== null")
    assert console_errors(browser) == []


@browser_only
def test_the_strip_offers_continue_while_the_guard_holds_work_and_the_click_sends_it_with_the_token(browser, fake):
    open_home(browser, fake)
    fake.request("POST", "/__fake/limits", HOLD)
    present(browser, '#needs [data-act="guard-continue"]')
    assert texts(browser, "#needs .nylimit")[0].startswith("Claude weekly window is at 83%, resets Fri 09:00. New team runs wait.")
    browser.click('#needs [data-act="guard-continue"]')
    absent(browser, '#needs [data-act="guard-continue"]')
    sent = [r for r in posts(fake) if r["path"] == "/api/limits/continue"]
    assert len(sent) == 1 and sent[0]["token"] is True
    assert console_errors(browser) == []


@browser_only
def test_the_limits_group_saves_a_limit_clears_it_and_refuses_a_bad_amount_without_a_request(browser, fake):
    open_home(browser, fake)
    open_settings(browser, "limits")
    assert browser.js("document.querySelector('#set-limits [data-input=monthly_usd]').value") == ""
    browser.type("#set-limits [data-input=monthly_usd]", "ten")
    browser.click('#set-limits [data-act="save-limit"]')
    present(browser, "#set-limits .seterr")
    assert "dollar amount" in texts(browser, "#set-limits .seterr")[0]
    assert [r for r in posts(fake) if r["path"] == "/api/limits"] == []
    assert browser.js("document.querySelector('#set-limits [data-input=monthly_usd]').value") == "ten"        # what was typed stays beside the refusal
    browser.js("document.querySelector('#set-limits [data-input=monthly_usd]').value = ''")
    browser.type("#set-limits [data-input=monthly_usd]", "12.5")
    browser.click('#set-limits [data-act="save-limit"]')
    present(browser, '#set-limits [data-act="clear-limit"]')
    sent = [r for r in posts(fake) if r["path"] == "/api/limits"]
    assert [(r["method"], r["token"], r["body"]) for r in sent] == [("PUT", True, {"monthly_usd": 12.5})]
    assert browser.js("document.querySelector('#set-limits [data-input=monthly_usd]').value") == "12.5"
    browser.click('#set-limits [data-act="clear-limit"]')
    absent(browser, '#set-limits [data-act="clear-limit"]')
    assert [r["body"] for r in posts(fake) if r["path"] == "/api/limits"][-1] == {"monthly_usd": None}
    assert console_errors(browser) == []


def status_of(browser, group):
    return browser.js(f"document.querySelector('#set-{group} .setstatus').textContent")


@browser_only
def test_saved_goes_as_soon_as_a_field_of_its_group_is_edited_again(browser, fake):
    """QA firstrun-settings: "Saved." stayed on screen beside a new value that the server did not have (Limits, Notifications and Engine; a group is not
    repainted while the owner types in it, so the line has to be cleared in place)."""
    open_home(browser, fake)
    open_settings(browser, "limits")
    browser.type("#set-limits [data-input=monthly_usd]", "5")
    press(browser, '#set-limits [data-act="save-limit"]')
    browser.wait_for("document.querySelector('#set-limits .setstatus').textContent === 'Saved.'")
    browser.type("#set-limits [data-input=monthly_usd]", "7")
    assert status_of(browser, "limits") == ""
    assert browser.js("HomePage.state().limitsForm.saved") is False                                  # and the next repaint does not bring it back
    open_settings(browser, "notices")
    browser.js("(() => { const e = document.querySelector('#set-notices [data-input=nudges_per_hour]'); e.value = '2'; e.dispatchEvent(new Event('input', {bubbles: true})); })()")
    press(browser, '#set-notices [data-act="save-notices"]')
    browser.wait_for("document.querySelector('#set-notices .setstatus').textContent === 'Saved.'")
    browser.type("#set-notices [data-input=nudges_per_hour]", "9")
    assert status_of(browser, "notices") == ""
    open_settings(browser, "engine")
    present(browser, '#set-engine [data-input="budget"]')
    browser.js("document.querySelector('#set-engine [data-input=budget]').value = '250'")
    press(browser, '#set-engine [data-act="save-engine"]')
    browser.wait_for("document.querySelector('#set-engine .setstatus').textContent.indexOf('Saved.') === 0")
    browser.type("#set-engine [data-input=budget]", "1")
    assert status_of(browser, "engine") == ""
    assert browser.js("HomePage.state().saved") is False
    assert console_errors(browser) == []


@browser_only
def test_enter_in_a_settings_field_presses_the_save_of_its_group(browser, fake):
    """QA firstrun-settings: there is no <form>, so Enter did nothing in Limits, Notifications or Engine and a keyboard-only owner had to Tab to Save."""
    open_home(browser, fake)
    open_settings(browser, "limits")
    browser.type("#set-limits [data-input=monthly_usd]", "1234")
    browser.press("Enter")
    present(browser, '#set-limits [data-act="clear-limit"]')
    assert [(r["method"], r["body"]) for r in posts(fake) if r["path"] == "/api/limits"] == [("PUT", {"monthly_usd": 1234.0})]
    open_settings(browser, "notices")
    browser.js("document.querySelector('#set-notices [data-input=nudges_per_hour]').value = ''")            # it holds the default 3
    browser.type("#set-notices [data-input=nudges_per_hour]", "4")
    browser.press("Enter")
    browser.wait_for("document.querySelector('#set-notices .setstatus').textContent === 'Saved.'")
    assert [r["body"] for r in posts(fake) if r["path"] == "/api/ops/attention"] == [{"quiet_hours": None, "nudges_per_hour": 4}]
    open_settings(browser, "engine")
    present(browser, '#set-engine [data-input="budget"]')
    browser.js("document.querySelector('#set-engine [data-input=budget]').value = ''")
    browser.type("#set-engine [data-input=budget]", "250")
    browser.press("Enter")
    browser.wait_for("document.querySelector('#set-engine .setstatus').textContent.indexOf('Saved.') === 0")
    assert [r["body"] for r in posts(fake, "/api/engine/settings")] == [{"set": {"budget": 250}, "unset": []}]
    assert console_errors(browser) == []


@browser_only
def test_the_guard_switch_saves_at_once(browser, fake):
    open_home(browser, fake)
    open_settings(browser, "limits")
    browser.click("#set-limits [data-guard]")
    browser.wait_for("document.querySelector('#set-limits [data-guard]').checked === true")
    sent = [r for r in posts(fake) if r["path"] == "/api/limits"]
    assert [(r["method"], r["token"], r["body"]) for r in sent] == [("PUT", True, {"guard_enabled": True})]
    assert console_errors(browser) == []


def press(browser, selector):
    """The press itself, in one step: Settings repaints a group when its read lands, and a real press that straddles a repaint is lost. The button takes
    the focus first, as a mouse press gives it: a group is not repainted while a field of it has the focus, so the answer of a save would not show."""
    assert browser.js(f"(() => {{ const e = document.querySelector({selector!r}); if (!e) return false; e.focus(); e.click(); return true; }})()"), selector


@browser_only
def test_a_write_the_heal_cannot_rescue_says_to_reload_the_page_beside_its_field_not_the_name_of_a_header(browser, fake):
    """QA firstrun-settings: with the launch token dead and the heal refused, Limits, the guard, Notifications, About (and Engine, Default model and Connectors)
    printed the server's "A valid X-Sutra-Token header is required for this request". The fake's real pages hold the first token, so the heal reads the
    same one again and gives up, as it does inside its 60 seconds; Notes and the chat already said "Reload it from the app"."""
    plain = "This page was opened without its access token. Reload it from the app."
    for path in ("/api/limits", "/api/ops/attention", "/api/ops/update-check"):
        browser.expect_failed(path, 401)
    open_home(browser, fake)
    open_settings(browser, "limits")
    fake.post("/__fake/restart", {"token": "restarted-token-0123456789abcdef"}, token=False)
    browser.js("(() => { const e = document.querySelector('#set-limits [data-input=monthly_usd]'); e.value = '12'; e.dispatchEvent(new Event('input', {bubbles: true})); })()")
    press(browser, '#set-limits [data-act="save-limit"]')
    present(browser, "#set-limits .seterr")
    assert texts(browser, "#set-limits .seterr") == [plain]
    press(browser, "#set-limits [data-guard]")
    browser.wait_for("document.querySelector('#set-limits [data-guard]').checked === false && document.querySelectorAll('#set-limits .seterr').length > 0")
    assert texts(browser, "#set-limits .seterr") == [plain]
    open_settings(browser, "notices")
    browser.js("(() => { const e = document.querySelector('#set-notices [data-input=nudges_per_hour]'); e.value = '4'; e.dispatchEvent(new Event('input', {bubbles: true})); })()")
    press(browser, '#set-notices [data-act="save-notices"]')
    present(browser, "#set-notices .seterr")
    assert texts(browser, "#set-notices .seterr") == [plain]
    open_settings(browser, "about")
    press(browser, '#set-about [data-act="check-update"]')
    browser.wait_for("document.querySelector('#set-about .settest[data-step=error]') !== null")
    assert texts(browser, "#set-about .settest") == [plain]
    assert "X-Sutra-Token" not in browser.js("document.getElementById('pane-settings').innerText")
    assert [line for line in console_errors(browser) if "401" not in line] == []                      # the refused writes are the announced 401s, nothing else


@browser_only
def test_the_notifications_group_sends_both_times_and_the_cap_and_refuses_equal_times_without_a_request(browser, fake):
    open_home(browser, fake)
    open_settings(browser, "notices")
    assert browser.js("document.querySelector('#set-notices [data-input=nudges_per_hour]').value") == "3"
    browser.js("(() => { const set = (n, v) => { const e = document.querySelector('#set-notices [data-input=' + n + ']'); e.value = v; e.dispatchEvent(new Event('input', {bubbles: true})); };"
               "set('quiet_start', '10:00'); set('quiet_end', '10:00'); })()")
    browser.click('#set-notices [data-act="save-notices"]')
    present(browser, "#set-notices .seterr")
    assert "all day or no time at all" in texts(browser, "#set-notices .seterr")[0]
    assert [r for r in posts(fake) if r["path"] == "/api/ops/attention"] == []
    browser.js("(() => { const set = (n, v) => { const e = document.querySelector('#set-notices [data-input=' + n + ']'); e.value = v; e.dispatchEvent(new Event('input', {bubbles: true})); };"
               "set('quiet_start', '21:00'); set('quiet_end', '08:00'); set('nudges_per_hour', '0'); })()")
    browser.click('#set-notices [data-act="save-notices"]')
    present(browser, '#set-notices [data-act="clear-quiet"]')
    sent = [r for r in posts(fake) if r["path"] == "/api/ops/attention"]
    assert [(r["method"], r["token"], r["body"]) for r in sent] == [("PUT", True, {"quiet_hours": {"start": "21:00", "end": "08:00"}, "nudges_per_hour": 0})]
    assert browser.js("document.querySelector('#set-notices [data-input=nudges_per_hour]').value") == "0"            # 0 stays 0
    assert browser.js("HomePage.state().notices.quiet_hours.start") == "21:00"                                   # the notices now obey the new window
    assert console_errors(browser) == []


@browser_only
def test_quiet_right_now_follows_the_pages_clock_not_the_servers_reading_at_the_last_fetch(browser, fake):
    """QA recurring-limits: the line kept saying what the server said when the page last read it. The fake answers quiet_now: false whatever the window is,
    so a window around the browser's own minute can only read as quiet through the page's twin of the rule."""
    open_home(browser, fake)
    open_settings(browser, "notices")
    minute = browser.js("(() => { const d = new Date(); return d.getHours() * 60 + d.getMinutes(); })()")
    hm = lambda m: f"{(m % 1440) // 60:02d}:{(m % 1440) % 60:02d}"

    def save_window(start, end):
        browser.js("(() => { const set = (n, v) => { const e = document.querySelector('#set-notices [data-input=' + n + ']'); e.value = v; e.dispatchEvent(new Event('input', {bubbles: true})); };"
                   f"set('quiet_start', '{start}'); set('quiet_end', '{end}'); }})()")
        browser.click('#set-notices [data-act="save-notices"]')

    save_window(hm(minute - 60), hm(minute + 60))
    browser.wait_for("document.querySelector('#set-notices .sethint').textContent.indexOf('Quiet right now.') === 0")
    save_window(hm(minute + 120), hm(minute + 180))
    browser.wait_for("document.querySelector('#set-notices .sethint').textContent.indexOf('Leave both empty') === 0")
    assert console_errors(browser) == []


@browser_only
def test_recurring_work_add_run_now_pause_and_remove(browser, fake):
    open_home(browser, fake, "full")
    open_settings(browser, "recurring")
    browser.wait_for("document.getElementById('set-recurring').textContent.indexOf('Nothing is scheduled yet') >= 0")
    browser.js("(() => { const t = document.querySelector('#set-recurring [data-input=rec_dept]'); t.value = t.options[1].value; t.dispatchEvent(new Event('change', {bubbles: true})); })()")
    browser.type("#set-recurring [data-input=rec_text]", "Write the pipeline summary")
    browser.click('#set-recurring [data-act="rec-add"]')
    present(browser, "#set-recurring .recrow")
    sent = [r for r in posts(fake) if r["path"] == "/api/recurring"]
    assert len(sent) == 1 and sent[0]["token"] is True and sent[0]["body"]["text"] == "Write the pipeline summary"
    assert sent[0]["body"]["schedule"] == {"every": "weekdays", "hour": 9, "minute": 0}
    assert "Every weekday at 9:00 AM (local)" in texts(browser, "#set-recurring .recrow")[0]
    browser.click('#set-recurring [data-act="rec-run"]')
    browser.wait_for("document.querySelector('#set-recurring .reclast').textContent.indexOf('started by you') >= 0")
    assert "has not fired on its own yet" in texts(browser, "#set-recurring .recrow")[0]
    browser.click('#set-recurring [data-act="rec-toggle"]')
    browser.wait_for("document.querySelector('#set-recurring .recrow').dataset.enabled === 'false'")
    assert "Switch on" in texts(browser, "#set-recurring .recrow")[0]
    browser.click('#set-recurring [data-act="rec-history"]')
    present(browser, "#set-recurring .recruns li")
    browser.click('#set-recurring [data-act="rec-delete"]')
    present(browser, '#set-recurring [data-act="rec-delete-yes"]')
    assert [r for r in posts(fake) if r["method"] == "DELETE"] == []                                  # the first click only asks
    browser.click('#set-recurring [data-act="rec-delete-yes"]')
    absent(browser, "#set-recurring .recrow")
    assert [(r["method"], r["token"]) for r in posts(fake) if r["method"] == "DELETE" and r["path"].startswith("/api/recurring/")] == [("DELETE", True)]
    assert console_errors(browser) == []


REC = {"id": "rec_0123456789ab", "dept_id": "web", "dept_name": "Web", "text": "Write the pipeline summary", "schedule": {"every": "weekdays", "hour": 9, "minute": 0, "weekday": 0},
       "human": "Every weekday at 9:00 AM (local)", "enabled": True, "paused_reason": "", "next_due_at": "2999-01-01T09:00:00Z", "created_at": "2026-11-01T08:00:00Z",
       "last_run": None, "never_fired_on_schedule": False}


def focused(browser):
    """What the keyboard is on: the data-act or data-input of the control, else its id or tag."""
    return browser.js("(() => { const a = document.activeElement; return a ? (a.dataset.act || a.dataset.input || a.id || a.tagName) : ''; })()")


@browser_only
def test_the_keyboard_keeps_its_place_in_the_recurring_group_after_each_action(browser, fake):
    """QA recurring-limits: every action repainted the group and focus fell to the page; after Remove the confirm could not be reached from the keyboard."""
    open_home(browser, fake, "full")
    fake.request("POST", "/__fake/recurring", {"items": [REC]})
    open_settings(browser, "recurring")
    present(browser, '#set-recurring [data-act="rec-toggle"]')
    browser.js("document.querySelector('#set-recurring [data-act=rec-toggle]').focus()")
    browser.press("Enter")                                                                          # Pause
    browser.wait_for("document.querySelector('#set-recurring .recrow').dataset.enabled === 'false'")
    assert focused(browser) == "rec-toggle"                                                         # the same button, now "Switch on"
    browser.press("Enter")                                                                          # Switch on again
    browser.wait_for("document.querySelector('#set-recurring .recrow').dataset.enabled === 'true'")
    assert focused(browser) == "rec-toggle"
    browser.js("document.querySelector('#set-recurring [data-act=rec-delete]').focus()")
    browser.press("Enter")                                                                          # Remove asks: the safe answer has the focus
    present(browser, '#set-recurring [data-act="rec-delete-yes"]')
    assert focused(browser) == "rec-delete-no"
    browser.press("Enter")                                                                          # No: back to Remove
    absent(browser, '#set-recurring [data-act="rec-delete-yes"]')
    assert focused(browser) == "rec-delete" and [r for r in posts(fake) if r["method"] == "DELETE"] == []
    browser.press("Enter")
    present(browser, '#set-recurring [data-act="rec-delete-yes"]')
    browser.js("document.querySelector('#set-recurring [data-act=rec-delete-yes]').focus()")
    browser.press("Enter")                                                                          # Yes: the row is gone, the keyboard stays in the group
    absent(browser, "#set-recurring .recrow")
    assert focused(browser) == "set-recurring-h"
    assert console_errors(browser) == []


@browser_only
def test_enter_in_the_limit_and_notice_fields_saves_like_the_button(browser, fake):
    open_home(browser, fake)
    open_settings(browser, "limits")
    browser.type("#set-limits [data-input=monthly_usd]", "77")
    browser.press("Enter")
    browser.wait_for("document.querySelector('#set-limits .setstatus').textContent === 'Saved.'")
    sent = [r for r in posts(fake) if r["path"] == "/api/limits"]
    assert [(r["method"], r["token"], r["body"]) for r in sent] == [("PUT", True, {"monthly_usd": 77.0})]
    assert focused(browser) == "monthly_usd"                                                        # the field keeps the caret for the next change
    open_settings(browser, "notices")
    browser.js("document.querySelector('#set-notices [data-input=nudges_per_hour]').select()")
    browser.type("#set-notices [data-input=nudges_per_hour]", "2")
    browser.press("Enter")
    browser.wait_for("document.querySelector('#set-notices .setstatus').textContent === 'Saved.'")
    sent = [r for r in posts(fake) if r["path"] == "/api/ops/attention"]
    assert [(r["method"], r["body"]) for r in sent] == [("PUT", {"quiet_hours": None, "nudges_per_hour": 2})]
    assert console_errors(browser) == []


@browser_only
def test_a_refusal_of_the_add_form_is_shown_and_sends_nothing(browser, fake):
    open_home(browser, fake, "full")
    open_settings(browser, "recurring")
    present(browser, '#set-recurring [data-act="rec-add"]')                                           # the list has loaded
    browser.click('#set-recurring [data-act="rec-add"]')
    present(browser, "#set-recurring .seterr")
    assert texts(browser, "#set-recurring .seterr") == ["Choose the team."]
    assert [r for r in posts(fake) if r["path"] == "/api/recurring"] == []
