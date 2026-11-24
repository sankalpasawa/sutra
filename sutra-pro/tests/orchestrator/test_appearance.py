"""The team avatar style: the store (default, round trip, refusals, the atomic write, a damaged file), the two routes (GET default, PUT, refusals,
the write guard) and the page boot block, which is how a page learns the style on a new port.

The routes run over a `Services` with no wiring at all: the store is built from `services.settings.data_dir` on each call."""
import json
import logging
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from orchestrator.test_tasks import tenv  # noqa: F401  (tenv is a fixture)

from sutra_app import oslayer, ui
from sutra_app.orchestrator import appearance as appearance_mod
from sutra_app.orchestrator.api import appearance as appearance_api
from sutra_app.orchestrator.api.deps import install_error_handlers, redacted_response_class
from sutra_app.orchestrator.appearance import AppearanceStore, default_doc
from sutra_app.orchestrator.redact import Redactor
from sutra_app.orchestrator.services import Services

TOKEN = "X-Sutra-Token"
CLASSIC = {"version": 1, "avatars": "classic"}
ILLUSTRATED = {"version": 1, "avatars": "illustrated"}
BOOT_BLOCK = re.compile(r'<script type="application/json" id="sutra-boot">(.*?)</script>', re.S)


# ---- the store -------------------------------------------------------------------------------------------------------------------

def test_nothing_saved_is_classic_and_a_choice_survives_a_new_store_over_the_same_folder(tmp_path):
    store = AppearanceStore(tmp_path)
    assert store.load() == default_doc() == CLASSIC and store.avatars() == "classic"
    assert not store.path.exists()                                                  # reading writes nothing
    assert store.save({"avatars": "illustrated"}) == ILLUSTRATED
    assert store.path == tmp_path / "ui" / "appearance.json" and json.loads(store.path.read_text(encoding="utf-8")) == ILLUSTRATED
    assert AppearanceStore(tmp_path).avatars() == "illustrated"                     # a new store: a restart, another port
    assert store.save({"avatars": "classic"}) == CLASSIC and AppearanceStore(tmp_path).avatars() == "classic"      # and back


@pytest.mark.parametrize("doc", [None, [], "illustrated", {}, {"avatars": "Illustrated"}, {"avatars": "photo"}, {"avatars": 1}, {"avatars": None}, {"avatars": ["classic"]}])
def test_a_value_that_is_not_a_style_is_refused_and_nothing_is_written(tmp_path, doc):
    store = AppearanceStore(tmp_path)
    with pytest.raises(ValueError, match="classic, illustrated"):
        store.save(doc)
    assert not store.path.exists()


@pytest.mark.parametrize("text", ["{not json", "[]", "", '{"version": 1}', '{"version": 1, "avatars": "photo"}', '{"version": 1, "avatars": 7}', "null"])
def test_a_damaged_file_or_an_unknown_value_reads_as_classic_with_a_warning_and_the_next_save_heals_it(tmp_path, caplog, text):
    store = AppearanceStore(tmp_path)
    store.path.parent.mkdir(parents=True)
    store.path.write_text(text, encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger=appearance_mod.__name__):
        assert store.load() == CLASSIC and store.avatars() == "classic"
    assert "damaged" in caplog.text
    assert store.save({"avatars": "illustrated"}) == ILLUSTRATED and store.load() == ILLUSTRATED


def test_a_file_that_cannot_be_read_is_classic_and_never_raises(tmp_path, monkeypatch):
    store = AppearanceStore(tmp_path)
    store.save({"avatars": "illustrated"})
    store.path.unlink()
    store.path.mkdir()                                                              # a folder where the file should be: reading it is an OSError
    assert store.load() == CLASSIC and store.avatars() == "classic"

    def boom():
        raise RuntimeError("anything at all")
    monkeypatch.setattr(store, "load", boom)
    assert store.avatars() == "classic"


def test_the_write_goes_through_a_temp_file_in_the_same_folder_and_a_failed_swap_keeps_the_old_choice(tmp_path, monkeypatch):
    store = AppearanceStore(tmp_path)
    store.save({"avatars": "illustrated"})
    swaps = []
    real = oslayer.replace

    def spy(src, dst):
        swaps.append((str(src), str(dst)))
        real(src, dst)
    monkeypatch.setattr(appearance_mod.oslayer, "replace", spy)
    store.save({"avatars": "classic"})
    (src, dst), = swaps
    assert dst == str(store.path) and src != dst and src.endswith(".tmp") and str(store.path.parent) in src

    def broken(src, dst):
        raise OSError("disk full")
    monkeypatch.setattr(appearance_mod.oslayer, "replace", broken)
    with pytest.raises(OSError):
        store.save({"avatars": "illustrated"})
    assert store.load() == CLASSIC                                                  # the last complete file, not half of the new one
    assert [p.name for p in store.path.parent.iterdir()] == ["appearance.json"]     # no temp file is left behind


# ---- the routes ------------------------------------------------------------------------------------------------------------------

def app_of(tenv):  # noqa: F811
    app = FastAPI()
    app.state.services = Services(settings=tenv.settings, version="test", db=tenv.db, redact=Redactor(None, environ={}), clock=tenv.clock)
    install_error_handlers(app, redacted_response_class(Redactor(None, environ={})))
    app.include_router(appearance_api.build_router())
    return app


@pytest.fixture
def client(tenv):  # noqa: F811
    return TestClient(app_of(tenv), base_url="http://127.0.0.1:8780", raise_server_exceptions=False)


@pytest.fixture
def auth(tenv):  # noqa: F811
    return {TOKEN: tenv.settings.token}


def test_get_answers_classic_before_anything_is_saved(client):
    got = client.get("/api/appearance")
    assert (got.status_code, got.json()) == (200, CLASSIC)


def test_a_valid_put_is_kept_read_back_and_can_be_switched_back(client, auth, tenv):  # noqa: F811
    done = client.put("/api/appearance", json={"avatars": "illustrated"}, headers=auth)
    assert (done.status_code, done.json()) == (200, ILLUSTRATED)
    assert client.get("/api/appearance").json() == ILLUSTRATED
    assert json.loads((tenv.settings.data_dir / "ui" / "appearance.json").read_text(encoding="utf-8")) == ILLUSTRATED
    assert client.put("/api/appearance", json={"avatars": "classic"}, headers=auth).json() == CLASSIC
    assert client.get("/api/appearance").json() == CLASSIC


@pytest.mark.parametrize("body", [{"avatars": "photo"}, {"avatars": ""}, {"avatars": 1}, {}, {"avatars": "illustrated", "more": 1}, {"version": 1, "avatars": "illustrated"}, []])
def test_a_bad_put_is_a_422_in_the_error_envelope_and_changes_nothing(client, auth, body):
    client.put("/api/appearance", json={"avatars": "illustrated"}, headers=auth)
    refused = client.put("/api/appearance", json=body, headers=auth)
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "validation"
    assert client.put("/api/appearance", content=b"not json", headers={**auth, "Content-Type": "application/json"}).status_code == 422
    assert client.get("/api/appearance").json() == ILLUSTRATED


def test_a_put_without_the_token_or_from_another_origin_is_refused_and_changes_nothing(client, auth):
    body = {"avatars": "illustrated"}
    assert client.put("/api/appearance", json=body).status_code == 401
    assert client.put("/api/appearance", json=body, headers={TOKEN: "wrong-token-wrong-token"}).status_code == 401
    assert client.put("/api/appearance", json=body, headers={**auth, "Origin": "http://evil.example"}).status_code == 403
    assert client.get("/api/appearance").json() == CLASSIC


# ---- the pages: the style reaches a page in its boot block, so a new port (a restart of the desktop app) draws the same avatars ----------------

class _Row:
    id, name = "web", "Web"


def boot_of(html: str) -> dict:
    return json.loads(BOOT_BLOCK.search(html).group(1))


def page_client(tenv, port: int) -> TestClient:  # noqa: F811
    app = app_of(tenv)
    app.state.services.department = lambda dept_id: _Row() if dept_id == "web" else None
    ui.mount(app, app.state.services)                                               # the real Services: its `avatars` reads the data folder
    return TestClient(app, base_url=f"http://127.0.0.1:{port}", raise_server_exceptions=False)


def test_home_and_the_team_page_are_told_the_style_and_a_second_app_on_another_port_is_told_the_same(tenv, auth):  # noqa: F811
    first = page_client(tenv, 8780)
    assert boot_of(first.get("/").text)["avatars"] == "classic" and boot_of(first.get("/d/web/").text)["avatars"] == "classic"
    assert first.put("/api/appearance", json={"avatars": "illustrated"}, headers=auth).status_code == 200
    assert boot_of(first.get("/").text)["avatars"] == "illustrated"                 # the next load of the same app, no restart needed
    second = page_client(tenv, 8793)                                                # a new app over the same data folder, on another port
    assert boot_of(second.get("/").text)["avatars"] == "illustrated" and boot_of(second.get("/d/web/").text)["avatars"] == "illustrated"
    assert second.put("/api/appearance", json={"avatars": "classic"}, headers=auth).status_code == 200
    assert boot_of(first.get("/d/web/").text)["avatars"] == "classic"               # and back, seen by the first one too


def test_a_damaged_file_still_serves_the_pages_with_the_classic_avatars(tenv):  # noqa: F811
    path = tenv.settings.data_dir / "ui" / "appearance.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"avatars": "<script>"}', encoding="utf-8")
    client = page_client(tenv, 8780)
    for url in ("/", "/d/web/"):
        got = client.get(url)
        assert got.status_code == 200 and boot_of(got.text)["avatars"] == "classic"
