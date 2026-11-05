"""Which browser opens the app (GAP-OPS-1, D92): Chrome when installed, the system default on request, SUTRA_BROWSER_APP over both."""
import plistlib
import subprocess
from types import SimpleNamespace

import pytest

from sutra_app.ops import browser

URL = "http://127.0.0.1:8780/"
CHROME_APP = "/Applications/Google Chrome.app"


class Recorder:
    def __init__(self, code=0, boom=None):
        self.calls, self.code, self.boom = [], code, boom

    def run(self, argv, **kw):
        self.calls.append(argv)
        if self.boom:
            raise self.boom
        return SimpleNamespace(returncode=self.code)


def opened_urls():
    seen = []

    def web_open(url):
        seen.append(url)
        return True
    web_open.seen = seen
    return web_open


def has_chrome(path):
    return path == CHROME_APP


def test_auto_opens_chrome_with_open_dash_a_on_a_mac_that_has_it():
    rec, web = Recorder(), opened_urls()
    result = browser.open_url(URL, "auto", environ={}, platform="darwin", run=rec.run, web_open=web, exists=has_chrome)
    assert rec.calls == [["open", "-a", "Google Chrome", URL]] and web.seen == []
    assert (result.opened, result.how) == (True, "chrome")


def test_chrome_preference_behaves_like_auto_when_chrome_is_there():
    rec = Recorder()
    assert browser.open_url(URL, "chrome", environ={}, platform="darwin", run=rec.run, web_open=opened_urls(), exists=has_chrome).how == "chrome"


def test_default_uses_the_system_browser_even_when_chrome_and_an_app_are_set():
    rec, web = Recorder(), opened_urls()
    result = browser.open_url(URL, "default", environ={"SUTRA_BROWSER_APP": "Brave Browser"}, platform="darwin", run=rec.run, web_open=web,
                              exists=has_chrome)
    assert rec.calls == [] and web.seen == [URL] and result.how == "default"


def test_sutra_browser_app_beats_auto_and_chrome():
    rec = Recorder()
    result = browser.open_url(URL, "auto", environ={"SUTRA_BROWSER_APP": " Brave Browser "}, platform="darwin", run=rec.run,
                              web_open=opened_urls(), exists=has_chrome)
    assert rec.calls == [["open", "-a", "Brave Browser", URL]] and (result.how, result.detail) == ("app", "Brave Browser")


def test_the_app_is_an_executable_off_a_mac():
    rec = Recorder()
    browser.open_url(URL, "auto", environ={"SUTRA_BROWSER_APP": "firefox"}, platform="linux", run=rec.run, web_open=opened_urls())
    assert rec.calls == [["firefox", URL]]


def test_without_chrome_the_system_browser_is_used_and_chrome_preference_says_so():
    rec, web = Recorder(), opened_urls()
    result = browser.open_url(URL, "chrome", environ={}, platform="darwin", run=rec.run, web_open=web, exists=lambda p: False)
    assert rec.calls == [] and web.seen == [URL]
    assert result.how == "default" and "Chrome was not found" in result.detail
    assert "Chrome was not found" not in browser.open_url(URL, "auto", environ={}, platform="darwin", run=rec.run, web_open=web, exists=lambda p: False).detail


def test_a_failing_open_falls_back_to_the_system_browser_and_says_why():
    web = opened_urls()
    result = browser.open_url(URL, "auto", environ={}, platform="darwin", run=Recorder(code=1).run, web_open=web, exists=has_chrome)
    assert web.seen == [URL] and result.how == "default" and "Chrome did not open (exit 1)" in result.detail
    result = browser.open_url(URL, "auto", environ={"SUTRA_BROWSER_APP": "Nope"}, platform="darwin",
                              run=Recorder(boom=subprocess.TimeoutExpired("open", 10)).run, web_open=web, exists=has_chrome)
    assert result.how == "default" and "SUTRA_BROWSER_APP=Nope did not open (TimeoutExpired)" in result.detail


def test_off_a_mac_chrome_is_left_to_webbrowser():
    rec, web = Recorder(), opened_urls()
    assert browser.open_url(URL, "auto", environ={}, platform="linux", run=rec.run, web_open=web, exists=has_chrome).how == "default"
    assert rec.calls == []


def test_no_browser_at_all_is_a_result_not_an_error():
    assert browser.open_url(URL, "default", environ={}, web_open=lambda url: False).opened is False

    def boom(url):
        raise RuntimeError("no display")
    result = browser.open_url(URL, "default", environ={}, web_open=boom)
    assert result.opened is False and "no display" in result.detail


def test_an_unknown_preference_is_refused():
    with pytest.raises(ValueError, match="auto, chrome, default"):
        browser.open_url(URL, "safari")


def test_find_chrome_prefers_j2_chrome_then_the_standard_places_then_path(tmp_path):
    mine = tmp_path / "chrome"
    mine.write_text("")
    assert browser.find_chrome({"J2_CHROME": str(mine)}) == str(mine)
    standard = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    assert browser.find_chrome({"J2_CHROME": str(tmp_path / "missing")}, exists=lambda p: p == standard) == standard
    assert browser.find_chrome({}, exists=lambda p: False, which=lambda n: "/usr/bin/chromium" if n == "chromium" else None) == "/usr/bin/chromium"
    assert browser.find_chrome({}, exists=lambda p: False, which=lambda n: None) is None


def write_plist(path, bundle):
    handlers = [{"LSHandlerURLScheme": "mailto", "LSHandlerRoleAll": "com.apple.mail"}]
    if bundle:
        handlers.append({"LSHandlerURLScheme": "https", "LSHandlerRoleAll": bundle})
    path.write_bytes(plistlib.dumps({"LSHandlers": handlers}))
    return path


def test_default_browser_reads_the_https_handler(tmp_path):
    chrome = browser.default_browser(platform="darwin", plist_path=write_plist(tmp_path / "a.plist", "com.google.chrome"))
    assert (chrome.name, chrome.chromium) == ("Google Chrome", True)
    brave = browser.default_browser(platform="darwin", plist_path=write_plist(tmp_path / "b.plist", "com.brave.browser"))
    assert brave.chromium is True
    firefox = browser.default_browser(platform="darwin", plist_path=write_plist(tmp_path / "c.plist", "org.mozilla.firefox"))
    assert (firefox.name, firefox.chromium) == ("Firefox", False)


def test_default_browser_is_safari_without_a_record_and_unknown_when_unreadable(tmp_path):
    for plist in (write_plist(tmp_path / "d.plist", None), tmp_path / "missing.plist"):
        found = browser.default_browser(platform="darwin", plist_path=plist)
        assert (found.name, found.chromium) == ("Safari", False)
    (tmp_path / "bad.plist").write_text("not a plist")
    assert browser.default_browser(platform="darwin", plist_path=tmp_path / "bad.plist") is None
    assert browser.default_browser(platform="linux") is None
