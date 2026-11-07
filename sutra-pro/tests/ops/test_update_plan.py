"""The automatic update check (gap package autoupdate): the asset facts of a release, `plan`, the setting and the last-check line, and the three routes the
desktop app and the About group use (`update-plan`, `update-setting`, `update-status`).

The feed is a fake `fetch(url, timeout) -> bytes` everywhere; every route test counts the requests that left the app with an injected fetcher
(`app.state.update_fetch`): none until an explicit start, and none at all while the setting is off or the app is offline.
"""
import json

import pytest
from fastapi.testclient import TestClient

import sutra_app
from sutra_app.config import Settings
from sutra_app.main import create_app
from sutra_app.ops import update_check, update_state
from sutra_app.orchestrator.testing.fake_engine import FakeLauncher
from sutra_app.orchestrator.testing.scripted import ScriptedConnector

BASE = "http://127.0.0.1:8780"
TOKEN = "update-plan-token-0123456789abcdef"
HEADERS = {"X-Sutra-Token": TOKEN}
REPO = update_check.REPO
PAGE = f"https://github.com/{REPO}/releases/tag/"
DMG_ARM, DMG_X64, EXE = update_check.ASSET_NAMES


def url_of(tag, name):
    return f"https://github.com/{REPO}/releases/download/{tag}/{name}"


def asset(tag, name, *, size=1000, state="uploaded", url=None):
    return {"name": name, "state": state, "size": size, "browser_download_url": url if url is not None else url_of(tag, name)}


def good_assets(tag, *, names=update_check.ASSET_NAMES):
    out = []
    for name in names:
        out += [asset(tag, name, size=5_000_000), asset(tag, name + ".sha256", size=90)]
    return out


def release(tag, *, assets="good", draft=False, prerelease=False):
    item = {"tag_name": tag, "draft": draft, "prerelease": prerelease, "html_url": PAGE + tag}
    item["assets"] = good_assets(tag) if assets == "good" else assets
    return item


def feed(*releases):
    body = json.dumps(list(releases)).encode()
    return lambda url, timeout: body


def ask(current, *releases, platform="darwin", arch="arm64"):
    return update_check.plan(current, platform, arch, fetch=feed(*releases), how="mac-app")


# ============================================ the asset facts ================================================================

def test_the_three_assets_of_the_matching_release_come_with_url_size_and_checksum_url():
    tag = "sutra-pro-v0.3.0"
    a = update_check.check("0.2.0", fetch=feed(release(tag)), how="mac-app")
    assert a.tag == tag and a.newer is True and sorted(a.assets) == sorted(update_check.ASSET_NAMES)
    for name in update_check.ASSET_NAMES:
        fact = a.assets[name]
        assert (fact.name, fact.url, fact.size, fact.sha256_url) == (name, url_of(tag, name), 5_000_000, url_of(tag, name) + ".sha256")


def test_the_facts_are_those_of_the_release_latest_names_and_come_also_when_nothing_is_newer():
    old, new = release("sutra-pro-v0.1.0"), release("sutra-pro-v0.3.0", assets=good_assets("sutra-pro-v0.3.0", names=(DMG_ARM,)))
    a = update_check.check("0.3.0", fetch=feed(old, new), how="mac-app")
    assert a.latest == "0.3.0" and a.newer is False and list(a.assets) == [DMG_ARM]
    assert a.assets[DMG_ARM].url == url_of("sutra-pro-v0.3.0", DMG_ARM)


@pytest.mark.parametrize("bad", [
    {"browser_download_url": "https://evil.example/releases/download/sutra-pro-v0.3.0/Sutra-Pro-arm64.dmg"},
    {"browser_download_url": "http://github.com/sankalpasawa/sutra/releases/download/sutra-pro-v0.3.0/Sutra-Pro-arm64.dmg"},
    {"browser_download_url": "https://github.com.evil.example/sankalpasawa/sutra/releases/download/sutra-pro-v0.3.0/Sutra-Pro-arm64.dmg"},
    {"browser_download_url": "https://github.com/other/repo/releases/download/sutra-pro-v0.3.0/Sutra-Pro-arm64.dmg"},
    {"browser_download_url": "https://github.com/sankalpasawa/sutra/releases/download/sutra-pro-v9.9.9/Sutra-Pro-arm64.dmg"},      # another tag
    {"browser_download_url": "https://github.com/sankalpasawa/sutra/releases/download/sutra-pro-v0.3.0/../../Sutra-Pro-arm64.dmg"},
    {"browser_download_url": "https://github.com/sankalpasawa/sutra/releases/download/sutra-pro-v0.3.0/Sutra-Pro-arm64.dmg?x=1"},
    {"browser_download_url": "https://github.com/sankalpasawa/sutra/releases/download/sutra-pro-v0.3.0/Sutra-Pro-arm64.dmg "},
    {"browser_download_url": None}, {"browser_download_url": 5}, {"browser_download_url": ["x"]},
    {"size": "5000000"}, {"size": True}, {"size": False}, {"size": 0}, {"size": -1}, {"size": 1.5}, {"size": 5e6}, {"size": (1 << 30) + 1}, {"size": 10 ** 30},
    {"size": None}, {"size": [1]},
    {"state": "starter"}, {"state": "open"}, {"state": None},
])
def test_a_hostile_asset_drops_only_itself_never_the_answer(bad):
    tag = "sutra-pro-v0.3.0"
    listed = [{**a, **bad} if a["name"] == DMG_ARM else a for a in good_assets(tag)]
    a = update_check.check("0.2.0", fetch=feed(release(tag, assets=listed)), how="mac-app")
    assert a.error is None and a.latest == "0.3.0" and a.newer is True
    assert sorted(a.assets) == sorted([DMG_X64, EXE])                       # the other two are untouched


def test_the_largest_legal_size_is_kept_and_a_checksum_file_has_its_own_limit():
    tag = "sutra-pro-v0.3.0"
    listed = [asset(tag, DMG_ARM, size=1 << 30), asset(tag, DMG_ARM + ".sha256", size=4096)]
    assert list(update_check.check("0.2.0", fetch=feed(release(tag, assets=listed)), how="x").assets) == [DMG_ARM]
    for size in (4097, 0, True, "90"):
        listed = [asset(tag, DMG_ARM, size=100), asset(tag, DMG_ARM + ".sha256", size=size)]
        assert update_check.check("0.2.0", fetch=feed(release(tag, assets=listed)), how="x").assets == {}


@pytest.mark.parametrize("bad", [{"name": "../Sutra-Pro-arm64.dmg"}, {"name": "sub/Sutra-Pro-arm64.dmg"}, {"name": "sutra-pro-arm64.dmg"},
                                 {"name": "Sutra-Pro-arm64.dmg\n"}, {"name": "Sutra-Pro-win-x64.zip"}, {"name": None}, {"name": 7}])
def test_a_name_that_is_not_one_of_the_three_is_never_taken(bad):
    tag = "sutra-pro-v0.3.0"
    listed = [{**a, **bad, "browser_download_url": url_of(tag, str(bad["name"]))} if a["name"] == DMG_ARM else a for a in good_assets(tag)]
    a = update_check.check("0.2.0", fetch=feed(release(tag, assets=listed)), how="mac-app")
    assert DMG_ARM not in a.assets and "../Sutra-Pro-arm64.dmg" not in a.assets and a.error is None


def test_an_asset_with_no_checksum_file_is_not_offered():
    tag = "sutra-pro-v0.3.0"
    listed = [asset(tag, DMG_ARM, size=1000), asset(tag, EXE, size=1000), asset(tag, EXE + ".sha256", size=90)]
    assert list(update_check.check("0.2.0", fetch=feed(release(tag, assets=listed)), how="x").assets) == [EXE]
    wrong_url = [asset(tag, DMG_ARM), asset(tag, DMG_ARM + ".sha256", url="https://evil.example/x.sha256")]
    assert update_check.check("0.2.0", fetch=feed(release(tag, assets=wrong_url)), how="x").assets == {}
    not_ready = [asset(tag, DMG_ARM), asset(tag, DMG_ARM + ".sha256", state="starter")]
    assert update_check.check("0.2.0", fetch=feed(release(tag, assets=not_ready)), how="x").assets == {}


@pytest.mark.parametrize("assets", ["nope", None, 5, {"a": 1}, [], [None, 1, "x", [], {"name": 5}], [{"name": DMG_ARM}], [[DMG_ARM]]])
def test_assets_that_are_not_a_list_of_objects_give_an_answer_with_no_facts(assets):
    a = update_check.check("0.2.0", fetch=feed(release("sutra-pro-v0.3.0", assets=assets)), how="x")
    assert a.assets == {} and a.error is None and a.latest == "0.3.0" and a.newer is True
    item = release("sutra-pro-v0.3.0")
    del item["assets"]
    assert update_check.check("0.2.0", fetch=feed(item), how="x").assets == {}


def test_a_repeated_name_is_not_a_way_to_replace_the_first_listed_asset():
    tag = "sutra-pro-v0.3.0"
    listed = [asset(tag, DMG_ARM, size=111), asset(tag, DMG_ARM + ".sha256", size=90), asset(tag, DMG_ARM, size=222)]
    assert update_check.check("0.2.0", fetch=feed(release(tag, assets=listed)), how="x").assets[DMG_ARM].size == 111


def test_the_new_fields_do_not_break_a_feed_without_assets_and_the_old_fields_are_unchanged():
    a = update_check.check("0.2.0", fetch=feed({"tag_name": "sutra-pro-v0.2.1", "html_url": PAGE + "sutra-pro-v0.2.1"}), how="mac-app")
    assert (a.latest, a.newer, a.error, a.tag, a.assets) == ("0.2.1", True, None, "sutra-pro-v0.2.1", {})
    assert set(a.model_dump()) == {"current", "latest", "newer", "url", "notes_url", "how", "kind", "error", "tag", "assets"}


# ============================================ plan: the asset of one platform ================================================

@pytest.mark.parametrize("platform, arch, name", [("darwin", "arm64", DMG_ARM), ("darwin", "x64", DMG_X64), ("win32", "x64", EXE)])
def test_plan_picks_the_asset_of_this_platform_and_architecture(platform, arch, name):
    p = ask("0.2.0", release("sutra-pro-v0.3.0"), platform=platform, arch=arch)
    assert p.asset is not None and p.asset.name == name and p.asset.url == url_of("sutra-pro-v0.3.0", name)
    assert (p.latest, p.newer, p.error, p.channel) == ("0.3.0", True, None, "stable")


@pytest.mark.parametrize("platform, arch", [("linux", "x64"), ("darwin", "ia32"), ("win32", "arm64"), ("win32", "ia32"), ("freebsd", "x64"), (None, None), ("darwin", None),
                                            ("", ""), ("darwin\n", "arm64"), (5, 6)])
def test_plan_has_no_asset_for_a_platform_that_has_none(platform, arch):
    p = ask("0.2.0", release("sutra-pro-v0.3.0"), platform=platform, arch=arch)
    assert p.asset is None and p.newer is True and p.error is None and len(p.assets) == 3


def test_plan_has_no_asset_when_nothing_newer_is_out_or_the_question_failed():
    assert ask("0.3.0", release("sutra-pro-v0.3.0")).asset is None
    assert ask("0.4.0", release("sutra-pro-v0.3.0")).asset is None

    def down(url, timeout):
        raise OSError("down")
    p = update_check.plan("0.2.0", "darwin", "arm64", fetch=down, how="mac-app")
    assert p.asset is None and p.error and p.channel == "stable"


def test_plan_has_no_asset_when_the_release_lacks_this_platforms_file():
    tag = "sutra-pro-v0.3.0"
    p = ask("0.2.0", release(tag, assets=good_assets(tag, names=(DMG_X64, EXE))), platform="darwin", arch="arm64")
    assert p.asset is None and p.newer is True


def test_a_stable_install_is_offered_stables_and_a_beta_install_betas_and_stables():
    feed_all = (release("sutra-pro-v0.4.0-beta.1", prerelease=True), release("sutra-pro-v0.3.0"))
    stable = ask("0.2.0", *feed_all)
    assert (stable.latest, stable.channel, stable.asset.name) == ("0.3.0", "stable", DMG_ARM)
    beta = ask("0.3.1-beta.1", *feed_all)
    assert (beta.latest, beta.channel, beta.newer) == ("0.4.0-beta.1", "beta", True)
    assert beta.asset.url == url_of("sutra-pro-v0.4.0-beta.1", DMG_ARM)
    pep = ask("0.3.1b1", *feed_all)                                                   # the wheel spells it the PEP 440 way
    assert (pep.channel, pep.latest) == ("beta", "0.4.0-beta.1")
    beta_then_stable = ask("0.4.0-beta.1", release("sutra-pro-v0.4.0"), release("sutra-pro-v0.4.0-beta.1", prerelease=True))
    assert (beta_then_stable.latest, beta_then_stable.newer, beta_then_stable.channel) == ("0.4.0", True, "beta")


def test_plan_is_one_request_while_the_newest_release_is_on_the_first_page():
    calls = []

    def fetch(url, timeout):
        calls.append(url)
        return json.dumps([release("sutra-pro-v0.3.0")]).encode()
    update_check.plan("0.2.0", "darwin", "arm64", fetch=fetch, how="mac-app")
    assert calls == [update_check.RELEASE_API]


def test_a_feed_full_of_hostile_numbers_and_assets_still_gives_a_plan():
    huge = "9" * 5000
    raw = json.dumps([release(f"sutra-pro-v{huge}.0.0"), release("sutra-pro-v0.3.0", assets=[{"name": DMG_ARM, "state": "uploaded", "size": 7, "browser_download_url": "x" * 100000}])])
    p = update_check.plan("0.2.0", "darwin", "arm64", fetch=lambda u, t: raw.encode(), how="mac-app")
    assert (p.latest, p.error, p.asset) == ("0.3.0", None, None)
    big = "1" + "0" * 4000                                                             # a size of 4000 digits is read, and is far over the limit
    body = ('[{"tag_name": "sutra-pro-v0.3.0", "assets": [{"name": "Sutra-Pro-arm64.dmg", "state": "uploaded", "size": ' + big + ', "browser_download_url": "x"}]}]').encode()
    assert update_check.plan("0.2.0", "darwin", "arm64", fetch=lambda u, t: body, how="mac-app").asset is None
    too_big = body.replace(big.encode(), ("1" + "0" * 5000).encode())                  # past the interpreter's own limit the body is unreadable: an answer with an error
    unread = update_check.plan("0.2.0", "darwin", "arm64", fetch=lambda u, t: too_big, how="mac-app")
    assert unread.asset is None and unread.error


# ============================================ the store ======================================================================

def make_app(tmp_path, **changes):
    env_file = tmp_path / "x.env"
    env_file.write_text("")
    changes.setdefault("offline", False)
    settings = Settings.load({}, data_dir=tmp_path / "data", token=TOKEN, env_file=env_file, engine="fake", watch_ms=20, **changes)
    return create_app(settings, connector=ScriptedConnector(), launcher=FakeLauncher(lambda spec: []))


class Fetcher:
    """The injected feed: counts every request, answers one newer release with its assets."""

    def __init__(self, *releases, fail=None):
        self.calls = []
        self.body = json.dumps(list(releases) or [release("sutra-pro-v9.0.0")]).encode()
        self.fail = fail

    def __call__(self, url, timeout):
        self.calls.append(url)
        if self.fail:
            raise self.fail
        return self.body


@pytest.fixture
def counted(monkeypatch):
    """The default fetcher too: anything that reaches for the network by its default is counted (and answers like a feed)."""
    fetcher = Fetcher()
    monkeypatch.setattr(update_check, "default_fetch", fetcher)
    return fetcher


def test_the_setting_is_on_by_default_without_having_been_chosen_and_both_values_persist(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        assert client.get("/api/ops/update-setting").json()["auto"] is True
        assert update_state.get_auto(app.state.services) == (True, False)
        assert client.put("/api/ops/update-setting", json={"auto": False}, headers=HEADERS).json()["auto"] is False
        client.post("/api/ops/update-status", json={"state": "ready", "version": "0.3.0", "message": "ready"}, headers=HEADERS)
    again = make_app(tmp_path)                                                         # a new app over the same data folder
    with TestClient(again, base_url=BASE) as client:
        got = client.get("/api/ops/update-setting").json()
    assert got["auto"] is False and got["chosen"] is True and got["last"]["state"] == "ready" and got["last"]["version"] == "0.3.0"


def test_update_state_reads_never_raise_and_junk_is_the_default(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app, base_url=BASE):
        services = app.state.services
        assert update_state.get_auto(services) == (True, False) and update_state.get_last(services) is None
        for junk in ("2", "yes", "", "true"):
            services.db.conn().execute("INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (update_state.AUTO_KEY, junk))
            assert update_state.get_auto(services) == (True, False), junk
        for junk in ("not json", "[]", '"x"', '{"state": "weird"}', '{"state": 5}', "null"):
            services.db.conn().execute("INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (update_state.LAST_KEY, junk))
            assert update_state.get_last(services) is None, junk
        with pytest.raises(ValueError):
            update_state.set_last(services, "weird", None, "x")


def test_the_stored_line_is_cleaned_before_it_is_kept(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        body = {"state": "failed", "version": "0.3.0", "message": "bad\x1b[2J\x07 thing\nsecond line  <b>x</b>" + "y" * 400}
        got = client.post("/api/ops/update-status", json={**body, "message": body["message"][:240]}, headers=HEADERS).json()["last"]
    assert got["state"] == "failed" and "\x1b" not in got["message"] and "\n" not in got["message"] and " " not in got["message"] and "\x07" not in got["message"]
    assert len(got["message"]) <= update_state.MAX_MESSAGE and "<b>x</b>" in got["message"]          # markup is the page's to escape; control characters are the store's to drop
    assert update_state.clean_message(None) == "" and update_state.clean_message("a" * 1000) == "a" * update_state.MAX_MESSAGE
    assert update_state.clean_version("0.3.0") == "0.3.0" and update_state.clean_version("0.3.0-beta.2") == "0.3.0-beta.2"
    for bad in ("1.2", "v1.2.3", "1.2.3\n", "1234567890.0.0", "1.2.3; rm", None, 5):
        assert update_state.clean_version(bad) is None, bad


# ============================================ the routes =====================================================================

def test_update_plan_needs_the_token_and_the_origin_and_a_get_does_not_start_it(tmp_path, counted):
    app = make_app(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        assert client.post("/api/ops/update-plan", json={}).status_code == 401
        assert client.post("/api/ops/update-plan", json={}, headers={**HEADERS, "Origin": "http://evil.example"}).status_code == 403
        assert client.get("/api/ops/update-plan").status_code == 405
        assert client.put("/api/ops/update-setting", json={"auto": True}).status_code == 401
        assert client.post("/api/ops/update-status", json={"state": "ready"}).status_code == 401
    assert counted.calls == []


@pytest.mark.parametrize("body", [{"auto": "yes"}, {"auto": 1}, {"platform": "Darwin"}, {"platform": "darwin; rm"}, {"arch": "x" * 13}, {"platform": 5}, {"extra": 1},
                                  {"platform": "darwin\n"}, {"arch": ""}, []])
def test_update_plan_has_a_closed_body(tmp_path, counted, body):
    app = make_app(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        response = client.post("/api/ops/update-plan", json=body, headers=HEADERS)
    assert response.status_code == 422 and counted.calls == []


def test_update_plan_answers_with_the_asset_the_channel_and_the_said_line(tmp_path):
    app = make_app(tmp_path)
    app.state.update_fetch = fetcher = Fetcher(release("sutra-pro-v9.0.0"))
    with TestClient(app, base_url=BASE) as client:
        body = client.post("/api/ops/update-plan", json={"platform": "darwin", "arch": "arm64"}, headers=HEADERS).json()
        none = client.post("/api/ops/update-plan", json={}, headers=HEADERS).json()
    assert fetcher.calls == [update_check.RELEASE_API] * 2                       # one request each
    assert body["newer"] is True and body["latest"] == "9.0.0" and body["channel"] == "stable" and body["tag"] == "sutra-pro-v9.0.0" and body["error"] is None
    assert body["asset"] == {"name": DMG_ARM, "url": url_of("sutra-pro-v9.0.0", DMG_ARM), "size": 5_000_000, "sha256_url": url_of("sutra-pro-v9.0.0", DMG_ARM) + ".sha256"}
    assert body["said"] == f"You have {sutra_app.__version__}; 9.0.0 is out." and body["current"] == sutra_app.__version__ and sorted(body["assets"]) == sorted(update_check.ASSET_NAMES)
    assert none["asset"] is None and none["newer"] is True


def test_update_plan_offline_refuses_and_makes_no_request(tmp_path, counted):
    app = make_app(tmp_path, offline=True)
    with TestClient(app, base_url=BASE) as client:
        plan = client.post("/api/ops/update-plan", json={}, headers=HEADERS)
        auto = client.post("/api/ops/update-plan", json={"auto": True}, headers=HEADERS)
        check = client.post("/api/ops/update-check", headers=HEADERS)
        got = client.get("/api/ops/update-setting").json()
    for response in (plan, auto, check):
        assert response.status_code == 409 and response.json()["error"]["code"] == "offline"
    assert counted.calls == [] and got["offline"] is True


def test_the_stub_connector_is_offline_for_the_updater_too(tmp_path, counted):
    app = make_app(tmp_path, connector="stub")
    with TestClient(app, base_url=BASE) as client:
        assert client.post("/api/ops/update-plan", json={"auto": True}, headers=HEADERS).status_code == 409
    assert counted.calls == []


def test_auto_with_the_setting_off_refuses_and_makes_no_request_but_the_owners_click_still_works(tmp_path):
    app = make_app(tmp_path)
    app.state.update_fetch = fetcher = Fetcher()
    with TestClient(app, base_url=BASE) as client:
        client.put("/api/ops/update-setting", json={"auto": False}, headers=HEADERS)
        refused = client.post("/api/ops/update-plan", json={"auto": True, "platform": "darwin", "arch": "arm64"}, headers=HEADERS)
        assert refused.status_code == 409 and refused.json()["error"]["code"] == "update_off"
        assert "Settings, About" in refused.json()["error"]["message"] and fetcher.calls == []
        clicked = client.post("/api/ops/update-plan", json={"platform": "darwin", "arch": "arm64"}, headers=HEADERS)         # a menu click is not `auto`
        assert clicked.status_code == 200 and clicked.json()["newer"] is True and len(fetcher.calls) == 1
        assert client.post("/api/ops/update-check", headers=HEADERS).status_code == 200 and len(fetcher.calls) == 2
        client.put("/api/ops/update-setting", json={"auto": True}, headers=HEADERS)
        assert client.post("/api/ops/update-plan", json={"auto": True}, headers=HEADERS).status_code == 200 and len(fetcher.calls) == 3


def test_update_plan_records_the_last_check_in_the_owners_words(tmp_path):
    app = make_app(tmp_path)
    app.state.update_fetch = fetcher = Fetcher(release("sutra-pro-v9.0.0"))
    with TestClient(app, base_url=BASE) as client:
        assert client.get("/api/ops/update-setting").json()["last"] is None
        client.post("/api/ops/update-plan", json={}, headers=HEADERS)
        last = client.get("/api/ops/update-setting").json()["last"]
        assert last["state"] == "available" and last["version"] == "9.0.0" and last["message"] == "Sutra Pro 9.0.0 is out." and isinstance(last["at"], float)
        fetcher.body = json.dumps([release(f"sutra-pro-v{sutra_app.__version__}")]).encode()
        client.post("/api/ops/update-plan", json={}, headers=HEADERS)
        last = client.get("/api/ops/update-setting").json()["last"]
        assert (last["state"], last["version"]) == ("up_to_date", None) and "up to date" in last["message"]
        fetcher.fail = OSError("down")
        client.post("/api/ops/update-plan", json={}, headers=HEADERS)
        last = client.get("/api/ops/update-setting").json()["last"]
        assert last["state"] == "error" and "Could not reach GitHub" in last["message"]


def test_update_plan_never_fails_on_a_hostile_feed(tmp_path):
    app = make_app(tmp_path)
    hostile = [b"", b"not json", b'{"message": "rate limit"}', b"null", b'[{"tag_name": 5, "assets": 7}]', b'[{"tag_name": "sutra-pro-v9.0.0", "assets": [{"size": 1e400}]}]',
               json.dumps([release("sutra-pro-v9.0.0", assets=[{"name": DMG_ARM, "state": "uploaded", "size": "9", "browser_download_url": "javascript:alert(1)"}])]).encode()]
    with TestClient(app, base_url=BASE) as client:
        for body in hostile:
            app.state.update_fetch = lambda url, timeout, body=body: body
            response = client.post("/api/ops/update-plan", json={"platform": "darwin", "arch": "arm64"}, headers=HEADERS)
            assert response.status_code == 200 and response.json()["asset"] is None, body


def test_update_setting_put_is_strict_and_closed(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        for body in ({"auto": "false"}, {"auto": 0}, {"auto": None}, {}, {"auto": True, "extra": 1}, [True]):
            assert client.put("/api/ops/update-setting", json=body, headers=HEADERS).status_code == 422, body
        assert client.get("/api/ops/update-setting").json()["chosen"] is False                 # nothing was stored by the refusals
        answer = client.put("/api/ops/update-setting", json={"auto": False}, headers=HEADERS).json()
        assert (answer["auto"], answer["chosen"], answer["default"], answer["offline"]) == (False, True, True, False)
        assert client.put("/api/ops/update-setting", json={"auto": True}, headers=HEADERS).json()["auto"] is True


def test_update_setting_get_is_open_and_says_whether_the_desktop_started_this_server(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        monkeypatch.delenv("SUTRA_PRO_DESKTOP", raising=False)
        got = client.get("/api/ops/update-setting")
        assert got.status_code == 200 and got.json() == {"auto": True, "chosen": False, "default": True, "desktop": False, "offline": False, "last": None, "install": None}
        monkeypatch.setenv("SUTRA_PRO_DESKTOP", "1")
        assert client.get("/api/ops/update-setting").json()["desktop"] is True
        monkeypatch.setenv("SUTRA_PRO_DESKTOP", "yes")
        assert client.get("/api/ops/update-setting").json()["desktop"] is False


@pytest.mark.parametrize("body", [{"state": "weird"}, {"state": ""}, {"state": 5}, {}, {"state": "ready", "extra": 1}, {"state": "ready", "version": 5}, {"state": "ready", "message": "x" * 241},
                                  {"state": "ready", "version": "1" * 41}])
def test_update_status_refuses_a_state_it_does_not_know_and_a_body_that_is_not_closed(tmp_path, body):
    app = make_app(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        assert client.post("/api/ops/update-status", json=body, headers=HEADERS).status_code == 422
        assert client.get("/api/ops/update-setting").json()["last"] is None


def test_update_status_stores_the_states_the_desktop_reports_and_drops_a_version_that_is_not_one(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        for state in ("downloading", "ready", "failed", "tell_only", "installing", "available", "up_to_date", "error"):
            answer = client.post("/api/ops/update-status", json={"state": state, "version": "0.3.0", "message": f"now {state}"}, headers=HEADERS).json()
            assert answer["last"]["state"] == state and answer["last"]["message"] == f"now {state}" and answer["last"]["version"] == "0.3.0"
        odd = client.post("/api/ops/update-status", json={"state": "ready", "version": "1.2.3; rm -rf", "message": ""}, headers=HEADERS).json()
        assert odd["last"]["version"] is None
        assert client.post("/api/ops/update-status", json={"state": "ready"}, headers=HEADERS).json()["last"]["version"] is None


def test_boot_and_every_read_make_no_request_and_only_the_two_explicit_posts_do(tmp_path):
    app = make_app(tmp_path)
    app.state.update_fetch = fetcher = Fetcher()
    paths = ["/", "/api/health", "/api/ops/info", "/api/ops/welcome", "/api/ops/doctor", "/api/ops/update-setting", "/api/ops/attention"]
    with TestClient(app, base_url=BASE) as client:
        for path in paths:
            client.get(path)
        client.put("/api/ops/update-setting", json={"auto": True}, headers=HEADERS)
        client.post("/api/ops/update-status", json={"state": "ready"}, headers=HEADERS)
        client.post("/api/ops/welcome/seen", headers=HEADERS)
        assert fetcher.calls == []                                                   # nothing but an explicit start asks GitHub, setting on or not
        client.post("/api/ops/update-plan", json={"auto": True}, headers=HEADERS)
        client.post("/api/ops/update-check", headers=HEADERS)
    assert len(fetcher.calls) == 2


def test_the_welcome_card_says_what_the_setting_is_and_whether_this_is_the_desktop(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        monkeypatch.delenv("SUTRA_PRO_DESKTOP", raising=False)
        assert client.get("/api/ops/welcome").json()["facts"]["egress"]["auto_update"] == {"on": True, "desktop": False}
        monkeypatch.setenv("SUTRA_PRO_DESKTOP", "1")
        client.put("/api/ops/update-setting", json={"auto": False}, headers=HEADERS)
        assert client.get("/api/ops/welcome").json()["facts"]["egress"]["auto_update"] == {"on": False, "desktop": True}


def test_no_schema_change_the_two_rows_live_in_meta(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        before = {r["name"] for r in app.state.services.db.conn().execute("SELECT name FROM sqlite_master WHERE type='table'")}
        client.put("/api/ops/update-setting", json={"auto": False}, headers=HEADERS)
        client.post("/api/ops/update-status", json={"state": "ready"}, headers=HEADERS)
        db = app.state.services.db.conn()
        after = {r["name"] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        keys = {r["key"] for r in db.execute("SELECT key FROM meta")}
    assert before == after and {update_state.AUTO_KEY, update_state.LAST_KEY} <= keys


def test_the_desktop_says_whether_this_copy_can_install_or_only_tells_and_the_words_are_cleaned(tmp_path, counted):
    app = make_app(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        assert client.get("/api/ops/update-setting").json()["install"] is None
        assert client.post("/api/ops/update-install", json={"can": False, "why": "not signed"}).status_code == 401            # a write: it needs the token
        said = client.post("/api/ops/update-install", json={"can": False, "why": "This copy is not signed.\x1b[2J\n  Download it."}, headers=HEADERS)
        assert said.status_code == 200 and said.json()["install"] == {"can": False, "why": "This copy is not signed. [2J Download it."}
        assert client.get("/api/ops/update-setting").json()["install"]["can"] is False
        assert client.post("/api/ops/update-install", json={"can": True}, headers=HEADERS).json()["install"] == {"can": True, "why": ""}
        for body in ({}, {"can": "yes"}, {"can": 1}, {"can": True, "why": "x" * 241}, {"can": True, "extra": 1}, {"why": "x"}):
            assert client.post("/api/ops/update-install", json=body, headers=HEADERS).status_code == 422, body
    assert counted.calls == []                                                          # none of it reaches the network
    again = make_app(tmp_path)                                                          # stored in the database: a new app over the same folder reads it
    with TestClient(again, base_url=BASE) as client:
        assert client.get("/api/ops/update-setting").json()["install"] == {"can": True, "why": ""}
