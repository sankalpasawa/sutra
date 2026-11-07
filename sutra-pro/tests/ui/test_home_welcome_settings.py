"""Home in a real browser, the welcome-settings package: the first-run card, Settings -> Default model and About, and the model picker under the pill.

Runs only with SUTRA_BROWSER=1 (the gate skips it), like tests/ui/test_home.py: headless Chrome over CDP against the fake backend, which mounts the REAL
page and the real static files. The fake serves the welcome card seen by default and no chat pill until a test asks, so no other test is touched by either.
"""
from __future__ import annotations

import json
import time

import pytest
from test_home import absent, attrs, open_settings, posts, present, shown, texts
from test_home import load as load_home

browser_only = pytest.mark.browser


def load(browser, fake, **kw):
    """Home on stage 1 with the fake's pill route on (without it the page's one pill request is a 404 that has nothing to do with these tests)."""
    fake.post("/__fake/pill", {"on": True, **kw}, token=False)
    load_home(browser, fake)


def seen(fake, on):
    fake.post("/__fake/welcome", {"seen": on}, token=False)


def card_text(browser):
    return browser.js("(document.getElementById('swelcome') || {innerText: ''}).innerText")


@browser_only
def test_the_welcome_card_shows_the_four_readings_and_not_now_hides_it_for_this_load_only(browser, fake):
    seen(fake, False)
    load(browser, fake)
    present(browser, "#swelcome .swbox[role=dialog][aria-modal=true]")
    text = card_text(browser)
    for words in ("Welcome to Sutra", "Which model answers", "Where your files are", "What leaves this computer", "What Sutra does alone"):
        assert words in text, words
    assert "run `codex login`" in text and "/data/sutra-pro" in text and "never uses an API key" in text
    assert browser.js("document.getElementById('swelcome').parentNode === document.body")           # outside #sview: a re-render cannot tear it down
    assert browser.js("document.activeElement && document.activeElement.dataset.act") == "welcome-gotit"
    browser.click('#swelcome [data-act="welcome-later"]')
    absent(browser, "#swelcome")
    assert posts(fake) == []                                                                          # Not now writes nothing
    browser.goto(browser.js("location.href"))
    present(browser, "#swelcome")                                                                     # a reload brings it back: it was this load only
    assert browser.console_errors == []


@browser_only
def test_got_it_posts_with_the_token_and_the_card_stays_away_after_a_reload(browser, fake):
    seen(fake, False)
    load(browser, fake)
    browser.click('#swelcome [data-act="welcome-gotit"]')
    absent(browser, "#swelcome")
    assert [(r["method"], r["path"], r["token"]) for r in posts(fake, "/api/ops/")] == [("POST", "/api/ops/welcome/seen", True)]
    browser.goto(browser.js("location.href"))
    browser.wait_for("window.HomePage && HomePage.state().loaded === true")
    assert not browser.js("!!document.getElementById('swelcome')")
    browser.wait_for("true")
    assert browser.console_errors == []


@browser_only
def test_escape_closes_the_card_without_writing(browser, fake):
    seen(fake, False)
    load(browser, fake)
    present(browser, "#swelcome")
    browser.press("Escape")
    absent(browser, "#swelcome")
    assert posts(fake) == []


def policy_rows(browser):
    return attrs(browser, '#set-models .setmodel', "data-provider")


@browser_only
def test_make_first_puts_the_whole_policy_with_only_the_order_changed_and_the_rows_follow(browser, fake):
    load(browser, fake)
    open_settings(browser, "connectors")
    present(browser, "#set-models .setmodel")
    assert policy_rows(browser) == ["claude", "codex"]
    assert texts(browser, "#set-models .setmodel .setchip") == ["First", "Second"]
    before = json.loads(browser.js("fetch('/api/connectors/policy').then(r => r.text())"))
    browser.click('#set-models [data-act="make-first"][data-provider="codex"]')
    browser.wait_for("document.querySelector('#set-models .setmodel').dataset.provider === 'codex'")
    puts = [r for r in posts(fake, "/api/connectors/") if r["method"] == "PUT"]
    assert [(r["path"], r["token"]) for r in puts] == [("/api/connectors/policy", True)]
    sent = puts[0]["body"]
    assert sent["defaults"]["order"] == ["codex", "claude"]
    assert {k: v for k, v in sent.items() if k != "defaults"} == {k: v for k, v in before.items() if k != "defaults"}         # providers, rules, rates untouched
    assert {k: v for k, v in sent["defaults"].items() if k != "order"} == {k: v for k, v in before["defaults"].items() if k != "order"}
    assert texts(browser, "#set-models .setstatus") == ["Saved. New chats use this from now on."]


@browser_only
def test_a_model_choice_and_the_off_switch_are_saved_and_the_last_provider_cannot_be_turned_off(browser, fake):
    load(browser, fake)
    open_settings(browser, "connectors")
    present(browser, "#set-models .setmodel")
    browser.js("(() => { const s = document.querySelector('select[data-policy-model=claude]'); s.value = 'opus'; s.dispatchEvent(new Event('change', {bubbles: true})); })()")
    browser.wait_for("HomePage.state().policy.providers.claude.model === 'opus'")
    browser.click('#set-models input[data-policy-on="codex"]')
    browser.wait_for("HomePage.state().policy.providers.codex.enabled === false")
    assert texts(browser, '#set-models .setmodel[data-provider="codex"] .setchip') == ["Off"]
    count = len(posts(fake, "/api/connectors/"))
    browser.click('#set-models input[data-policy-on="claude"]')
    browser.wait_for("document.querySelector('#set-models .seterr') !== null")
    assert "At least one model must stay on" in texts(browser, "#set-models .seterr")[0]
    assert len(posts(fake, "/api/connectors/")) == count                                              # refused in the page: nothing was sent
    assert browser.js("HomePage.state().policy.providers.claude.enabled") is True


@browser_only
def test_about_checks_for_updates_only_when_the_owner_presses_the_button(browser, fake):
    fake.post("/__fake/update", {"newer": True, "latest": "0.2.0", "said": "You have 0.1.0; 0.2.0 is out.", "notes_url":
              "https://github.com/sankalpasawa/sutra/releases/tag/sutra-pro-v0.2.0", "how": "Run `git pull`."}, token=False)
    load(browser, fake)
    open_settings(browser, "about")
    browser.wait_for("document.querySelector('#set-about .setvalue').textContent === '0.1.0'")
    assert texts(browser, "#set-about .setvalue") == ["0.1.0", "/data/sutra-pro"]
    assert posts(fake, "/api/ops/") == []                                                             # opening Settings asked nobody
    browser.click('#set-about [data-act="check-update"]')
    browser.wait_for("document.querySelector('#set-about .settest').dataset.step === 'new'")
    assert texts(browser, "#set-about .settest") == ["You have 0.1.0; 0.2.0 is out."]
    assert attrs(browser, "#set-about .sulink", "href") == ["https://github.com/sankalpasawa/sutra/releases/tag/sutra-pro-v0.2.0"]
    assert [(r["method"], r["path"], r["token"]) for r in posts(fake, "/api/ops/")] == [("POST", "/api/ops/update-check", True)]


@browser_only
def test_the_pill_offers_the_model_list_and_a_change_is_one_put_that_the_page_reads_back(browser, fake):
    load(browser, fake, choice={"provider": "claude"})
    present(browser, "#spill .cpick select[data-act=choose-model]")
    options = browser.js("Array.from(document.querySelectorAll('#spill select[data-act=choose-model] option'), o => o.value)")
    assert options[:4] == ["best", "opus", "sonnet", "haiku"] and "opus[1m]" in options
    assert browser.js("document.querySelector('#spill optgroup').label") == "More models"
    assert browser.js("document.querySelector('#spill select[data-act=choose-model]').value") == "sonnet"
    browser.js("(() => { const s = document.querySelector('#spill select[data-act=choose-model]'); s.value = 'haiku'; s.dispatchEvent(new Event('change', {bubbles: true})); })()")
    # wait for the page's own state: the server's answer, read back (the select already shows what the test set, so its value proves nothing)
    browser.wait_for("(HomePage.state().pillData || {providers: []}).providers.some(p => p.chat_model === 'haiku')")
    browser.js("(() => { const s = document.querySelector('#spill select[data-act=choose-effort]'); s.value = 'max'; s.dispatchEvent(new Event('change', {bubbles: true})); })()")
    browser.wait_for("(HomePage.state().pillData || {providers: []}).providers.some(p => p.chat_effort === 'max')")
    assert browser.js("document.querySelector('#spill select[data-act=choose-model]').value") == "haiku"
    assert browser.js("document.querySelector('#spill select[data-act=choose-effort]').value") == "max"
    puts = [r for r in posts(fake, "/api/chats/") if r["method"] == "PUT"]
    assert [(r["path"], r["token"], r["body"]) for r in puts] == [
        ("/api/chats/cs_org/choice", True, {"provider": "claude", "model": "haiku"}), ("/api/chats/cs_org/choice", True, {"provider": "claude", "effort": "max"})]
    assert shown(browser, "#spill") and browser.console_errors == []


def org_reply(number, text="ok"):
    return {"session_id": "cs_org", "message": {"id": number, "session_id": "cs_org", "role": "agent", "who": "sutra", "kind": "text", "text": text, "card": None,
                                                "pause": None, "answered_by": None, "answered_at": None, "task_id": None, "state": "ok", "at": "2026-11-04T10:09:30Z"}}


@browser_only
def test_the_pill_reads_the_server_again_when_the_chat_answers_so_the_pickers_appear_without_a_reload(browser, fake):
    """QA firstrun-settings: after a switch, the pill kept saying "can be chosen after your next message" and drew no select until a reload, because
    the page read GET /providers once and only a click on the pill read it again."""
    load(browser, fake, choice={"provider": "claude"}, can_pick=False)
    present(browser, "#spill .cpick .cpick-note")
    assert not browser.js("!!document.querySelector('#spill select')")
    assert "after your next message" in browser.js("document.querySelector('#spill .cpick').innerText")
    fake.post("/__fake/pill", {"on": True, "can_pick": True, "choice": {"provider": "claude", "model": "haiku", "effort": "high"}}, token=False)   # the answer ran: the server now knows
    fake.emit("chat.message", org_reply(51))
    present(browser, "#spill .cpick select[data-act=choose-model]")
    assert browser.js("document.querySelector('#spill select[data-act=choose-model]').value") == "haiku"
    assert browser.js("document.querySelector('#spill select[data-act=choose-effort]').value") == "high"
    assert "after your next message" not in browser.js("document.getElementById('spill').innerText")
    assert shown(browser, "#spill") and browser.console_errors == []


@browser_only
def test_a_provider_switch_of_the_org_chat_reads_the_pill_again_and_another_chat_does_not(browser, fake):
    load(browser, fake, choice={"provider": "claude"}, can_pick=False)
    present(browser, "#spill .cpick .cpick-note")
    reads = lambda: len([r for r in fake.log("/api/chats/cs_org/providers") if r["method"] == "GET"])
    before = reads()
    fake.post("/__fake/pill", {"on": True, "can_pick": True, "choice": {"provider": "claude", "model": "sonnet", "effort": "high"}}, token=False)
    fake.emit("connector.switch", {"session_id": "cs_other", "from": "codex", "to": "claude", "reason": "pinned"})
    time.sleep(0.6)
    assert reads() == before and not browser.js("!!document.querySelector('#spill select')")             # a switch of another chat is not this pill's business
    fake.emit("connector.switch", {"session_id": "cs_org", "from": "codex", "to": "claude", "reason": "pinned"})
    present(browser, "#spill .cpick select[data-act=choose-model]")
    assert reads() == before + 1 and browser.console_errors == []


HEAL_PAGE = ('<!doctype html><html><head><meta charset="utf-8"><!--SUTRA-BOOT-->'
             '<script src="/ui/js/sutra_ctx.js"></script><script src="/ui/js/tab_heal.js"></script></head><body>heal</body></html>')


@browser_only
def test_a_page_that_outlives_a_restart_takes_the_new_token_from_its_own_boot_block_and_the_write_goes_through(browser, fake):
    """welcome-settings, item 5, end to end with the real scripts: the launch token changes under an open page; its next write is refused with a 401, the
    page reads its own path again, takes the fresh token, and repeats that one write, which is accepted."""
    fake.post("/__fake/page", {"name": "heal", "html": HEAL_PAGE}, token=False)
    browser.goto(fake.url + "/__fake/mount/heal.html")
    browser.wait_for("window.SutraCtx && window.TabHeal && SutraCtx.boot.token")
    old = browser.js("SutraCtx.boot.token")
    fake.post("/__fake/restart", {"token": "restarted-token-0123456789abcdef"}, token=False)
    browser.expect_failed("/api/ops/welcome/seen", 401)                                              # the first, refused attempt is on purpose
    browser.js("window.__out = null; SutraCtx.api.post('/api/ops/welcome/seen', {}).then(r => { window.__out = {ok: true, r}; }, e => { window.__out = {ok: false, code: e.code}; })")
    browser.wait_for("window.__out !== null")
    assert browser.js("window.__out") == {"ok": True, "r": {"seen": True}}
    assert browser.js("SutraCtx.boot.token") == "restarted-token-0123456789abcdef" != old
    writes = [(r["status"], r["token"]) for r in fake.log("/api/ops/welcome/seen") if r["method"] == "POST"]
    assert writes == [(401, True), (200, True)]                                                      # one refused write, one repeated: no third
