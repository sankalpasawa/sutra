"""welcome-settings, item 5: the server half of a page that outlives a restart.

`tab_heal.js` (tested in tests/ui/js/tab_heal.test.js with fakes) relies on three facts of the real app, and this test pins all three with two real
`create_app` instances that differ only in their launch token, as a stopped and started server does:

  1. the old token is refused with 401 and the code `bad_token` (the code the page keys on),
  2. the page's own path, fetched again, carries the NEW token in its boot block, in the shape the page's parser reads
     (`<script type="application/json" id="sutra-boot">`, page kind and team included), with no new route and no cookie,
  3. a write with that token goes through.
"""
import json
import re

from fastapi.testclient import TestClient

from sutra_app.config import Settings
from sutra_app.main import create_app
from sutra_app.orchestrator.testing.fake_engine import FakeLauncher
from sutra_app.orchestrator.testing.scripted import ScriptedConnector

BASE = "http://127.0.0.1:8780"
OLD = "launch-one-token-0123456789abcdef"
NEW = "launch-two-token-0123456789abcdef"
# the pattern of tab_heal.js, character for character (the JS test and this one must agree on what a boot block is)
BLOCK = re.compile(r"""<script\b[^>]*\bid\s*=\s*["']sutra-boot["'][^>]*>([\s\S]*?)</script\s*>""", re.IGNORECASE)
WRITE = "/api/ops/welcome/seen"


def launch(tmp_path, token):
    """One launch of the server over the SAME data folder with its own token."""
    env_file = tmp_path / "x.env"
    env_file.write_text("")
    settings = Settings.load({}, data_dir=tmp_path / "data", token=token, env_file=env_file, engine="fake", watch_ms=20, offline=True)
    return create_app(settings, connector=ScriptedConnector(), launcher=FakeLauncher(lambda spec: []))


def boot_of(html):
    found = BLOCK.search(html)
    assert found is not None, "the page has no boot block"
    return json.loads(found.group(1))


def test_a_restart_kills_the_token_of_an_open_page_and_the_page_can_read_the_new_one_from_its_own_path(tmp_path):
    with TestClient(launch(tmp_path, OLD), base_url=BASE) as before:
        assert boot_of(before.get("/").text)["token"] == OLD
        assert before.post(WRITE, headers={"X-Sutra-Token": OLD}).status_code == 200
    with TestClient(launch(tmp_path, NEW), base_url=BASE) as after:                           # the server was stopped and started again
        dead = after.post(WRITE, headers={"X-Sutra-Token": OLD})
        assert dead.status_code == 401 and dead.json()["error"]["code"] == "bad_token"       # fact 1: what the page's rider keys on
        page = after.get("/", params={"pane": "settings"})                                    # the page's own path and query, as heal() fetches it
        assert page.status_code == 200
        boot = boot_of(page.text)
        assert (boot["page"], boot["dept"], boot["token"]) == ("home", "", NEW)               # fact 2: same kind, same team, the new token
        assert len(boot["token"]) >= 16 and "set-cookie" not in page.headers
        assert after.post(WRITE, headers={"X-Sutra-Token": boot["token"]}).status_code == 200  # fact 3


def test_no_route_hands_out_the_token(tmp_path):
    """D81: the token reaches a page only through its boot block; a heal never needs an endpoint for it."""
    with TestClient(launch(tmp_path, NEW), base_url=BASE) as client:
        for path in ("/api/token", "/api/panel-token", "/api/ops/token", "/api/config", "/api/health", "/api/ops/info", "/api/ops/welcome"):
            assert NEW not in client.get(path).text, path
