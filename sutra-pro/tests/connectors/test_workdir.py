"""The working folder (GAP3-workdir, connectors/workdir.py): what is accepted and what is refused, the small private file it lives in, the
read-only preview of its top, the words the model is told, and the three routes (`GET`, `PUT`, `DELETE /api/connectors/workdir`)."""
from __future__ import annotations

import json
import os
import stat
import sys
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sutra_app import oslayer
from sutra_app.connectors.api import PREFIX, build_api_router
from sutra_app.connectors.errors import InvalidRequestError
from sutra_app.connectors.factory import build_router
from sutra_app.connectors.models import ConnectorConfig
from sutra_app.connectors.workdir import (
    NO_FOLDER_TEXT, PREVIEW_MAX, WORKDIR_FILE, WorkFolder, check_folder, grounding_text, preview_of,
)
from sutra_app.orchestrator.api.deps import install_error_handlers, require_token

POSIX = pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX file modes, links and rights")
TOKEN = "t" * 24
HEADERS = {"X-Sutra-Token": TOKEN}


@pytest.fixture
def dirs(tmp_path):
    data, work, mine = tmp_path / "data", tmp_path / "work", tmp_path / "mine"
    for d in (data, work, mine):
        d.mkdir()
    return SimpleNamespace(data=data, work=work, mine=mine, root=tmp_path)


@pytest.fixture
def store(dirs):
    return WorkFolder(dirs.data, dirs.work)


def says(exc_info):
    return exc_info.value.user_message()


# ---- validation ---------------------------------------------------------------------------------------------------------------

def test_a_folder_of_the_owner_is_accepted_and_resolved_with_realpath(dirs):
    assert check_folder(str(dirs.mine), data_dir=dirs.data, work_root=dirs.work) == os.path.realpath(dirs.mine)


@POSIX
def test_a_link_to_a_folder_is_stored_as_the_folder_it_leads_to(dirs):
    link = dirs.root / "shortcut"
    link.symlink_to(dirs.mine)
    assert check_folder(str(link), data_dir=dirs.data, work_root=dirs.work) == os.path.realpath(dirs.mine)


def test_a_leading_tilde_is_the_owners_home_folder(dirs):
    (dirs.root / "home" / "projects").mkdir(parents=True)
    got = check_folder("~/projects", data_dir=dirs.data, home=str(dirs.root / "home"))
    assert got == os.path.realpath(dirs.root / "home" / "projects")
    assert check_folder("~", data_dir=dirs.data, home=str(dirs.root / "home")) == os.path.realpath(dirs.root / "home")


@pytest.mark.parametrize(("raw", "words"), [
    ("", "full path"), ("   ", "full path"), (None, "full path"), (42, "full path"),
    ("projects/notes", "full path"), ("./here", "full path"), ("a" * 1100, "full path"), ("/tmp/x\n/etc", "full path"),
    ("~someone/else", "full path"),
])
def test_a_text_that_is_not_a_full_path_is_refused_with_the_reason(dirs, raw, words):
    with pytest.raises(InvalidRequestError) as e:
        check_folder(raw, data_dir=dirs.data, work_root=dirs.work)
    assert words in says(e)


def test_a_folder_that_does_not_exist_is_refused(dirs):
    with pytest.raises(InvalidRequestError) as e:
        check_folder(str(dirs.root / "nothing"), data_dir=dirs.data)
    assert "There is no folder at" in says(e)


def test_a_file_is_refused(dirs):
    file = dirs.root / "notes.txt"
    file.write_text("x", encoding="utf-8")
    with pytest.raises(InvalidRequestError) as e:
        check_folder(str(file), data_dir=dirs.data)
    assert "is a file, not a folder" in says(e)


def test_the_top_of_the_disk_is_refused(dirs):
    top = os.path.abspath(os.sep) if not oslayer.IS_WINDOWS else os.path.splitdrive(str(dirs.root))[0] + "\\"
    with pytest.raises(InvalidRequestError) as e:
        check_folder(top, data_dir=dirs.data)
    assert "not the top of the whole disk" in says(e)


def test_the_apps_own_data_folder_and_everything_inside_it_is_refused(dirs):
    inside = dirs.data / "connectors" / "deep"
    inside.mkdir(parents=True)
    for path in (dirs.data, dirs.data / "connectors", inside):
        with pytest.raises(InvalidRequestError) as e:
            check_folder(str(path), data_dir=dirs.data, work_root=dirs.work)
        assert "belongs to Sutra itself" in says(e)


def test_the_apps_work_root_is_refused_too(dirs):
    session = dirs.work / "cs_1"
    session.mkdir()
    for path in (dirs.work, session):
        with pytest.raises(InvalidRequestError) as e:
            check_folder(str(path), data_dir=dirs.data, work_root=dirs.work)
        assert "belongs to Sutra itself" in says(e)


@POSIX
def test_a_link_into_the_data_folder_is_refused_after_resolving_it(dirs):
    link = dirs.root / "sneaky"
    link.symlink_to(dirs.data)
    with pytest.raises(InvalidRequestError) as e:
        check_folder(str(link), data_dir=dirs.data, work_root=dirs.work)
    assert "belongs to Sutra itself" in says(e)


def test_a_sibling_whose_name_starts_like_the_data_folder_is_not_inside_it(dirs):
    sibling = dirs.root / "data-backup"
    sibling.mkdir()
    assert check_folder(str(sibling), data_dir=dirs.data, work_root=dirs.work) == os.path.realpath(sibling)


@POSIX
@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root can read everything")
def test_a_folder_that_cannot_be_read_is_refused(dirs):
    locked = dirs.root / "locked"
    locked.mkdir()
    locked.chmod(0)
    try:
        with pytest.raises(InvalidRequestError) as e:
            check_folder(str(locked), data_dir=dirs.data)
        assert "cannot be read" in says(e)
    finally:
        locked.chmod(0o700)


# ---- the store ----------------------------------------------------------------------------------------------------------------

def test_a_chosen_folder_is_stored_next_to_the_policy_and_read_back(store, dirs):
    assert store.set(str(dirs.mine)) == os.path.realpath(dirs.mine)
    path = dirs.data / "connectors" / WORKDIR_FILE
    assert path == store.path
    assert json.loads(path.read_text(encoding="utf-8")) == {"version": 1, "path": os.path.realpath(dirs.mine)}
    assert store.stored() == store.get() == os.path.realpath(dirs.mine)


@POSIX
def test_the_file_is_private_and_no_temporary_file_is_left(store, dirs):
    store.set(str(dirs.mine))
    assert stat.S_IMODE(os.stat(store.path).st_mode) == 0o600
    assert sorted(p.name for p in store.path.parent.iterdir()) == [WORKDIR_FILE]


def test_a_refused_folder_writes_nothing_and_keeps_the_old_choice(store, dirs):
    store.set(str(dirs.mine))
    with pytest.raises(InvalidRequestError):
        store.set(str(dirs.data))
    assert store.get() == os.path.realpath(dirs.mine)


def test_a_change_is_seen_by_the_next_read_without_a_restart(store, dirs):
    other = dirs.root / "other"
    other.mkdir()
    store.set(str(dirs.mine))
    assert store.get() == os.path.realpath(dirs.mine)
    store.set(str(other))
    assert store.get() == os.path.realpath(other)
    store.clear()
    assert store.get() is None and store.stored() is None and not store.path.exists()
    store.clear()                                                                      # clearing nothing is not an error


def test_a_folder_that_vanished_is_ignored_not_honoured_but_still_reported(store, dirs):
    gone = dirs.root / "gone"
    gone.mkdir()
    store.set(str(gone))
    gone.rmdir()
    assert store.get() is None
    assert store.stored() == os.path.realpath(gone)
    assert "There is no folder at" in (store.problem() or "")


def test_a_stored_path_that_now_lies_inside_the_data_folder_is_not_used(dirs):
    inside = dirs.data / "connectors" / "x"
    inside.mkdir(parents=True)
    (dirs.data / "connectors" / WORKDIR_FILE).write_text(json.dumps({"version": 1, "path": str(inside)}), encoding="utf-8")
    store = WorkFolder(dirs.data, dirs.work)
    assert store.get() is None and "belongs to Sutra itself" in (store.problem() or "")


@pytest.mark.parametrize("body", ["not json", "[]", '{"version": 2, "path": "/x"}', '{"version": 1}', '{"version": 1, "path": "/x", "more": 1}'])
def test_a_file_that_does_not_read_is_ignored(store, body):
    store.path.parent.mkdir(parents=True)
    store.path.write_text(body, encoding="utf-8")
    assert store.stored() is None and store.get() is None


# ---- the preview --------------------------------------------------------------------------------------------------------------

def test_the_preview_lists_folders_first_then_names_and_never_contents(dirs):
    (dirs.mine / "src").mkdir()
    (dirs.mine / "docs").mkdir()
    (dirs.mine / "README.md").write_text("SECRET-CONTENT-ONE", encoding="utf-8")
    (dirs.mine / "app.py").write_text("SECRET-CONTENT-TWO", encoding="utf-8")
    out = preview_of(str(dirs.mine))
    assert [(e["name"], e["kind"]) for e in out["entries"]] == [("docs", "dir"), ("src", "dir"), ("app.py", "file"), ("README.md", "file")]
    assert out["total"] == 4 and out["shown"] == 4 and out["readable"] is True and out["capped"] is False
    assert "SECRET-CONTENT" not in json.dumps(out)
    assert all(set(e) == {"name", "kind"} for e in out["entries"])


def test_the_preview_shows_at_most_sixty_names_and_counts_them_all(dirs):
    for i in range(PREVIEW_MAX + 15):
        (dirs.mine / f"file{i:03d}.txt").write_text("x", encoding="utf-8")
    (dirs.mine / "zdir").mkdir()
    out = preview_of(str(dirs.mine))
    assert PREVIEW_MAX == 60 and out["shown"] == 60 and len(out["entries"]) == 60 and out["total"] == 76
    assert out["entries"][0] == {"name": "zdir", "kind": "dir"}              # a folder sorts first, whatever its name


def test_an_empty_folder_and_a_folder_that_cannot_be_listed(dirs):
    assert preview_of(str(dirs.mine)) == {"entries": [], "total": 0, "shown": 0, "capped": False, "readable": True}
    assert preview_of(str(dirs.root / "missing"))["readable"] is False


@POSIX
def test_an_entry_that_cannot_be_read_is_skipped_and_not_counted(dirs):
    (dirs.mine / "real.txt").write_text("x", encoding="utf-8")
    (dirs.mine / "dead").symlink_to(dirs.root / "nowhere")                          # a link to nothing: stat fails
    out = preview_of(str(dirs.mine))
    assert [e["name"] for e in out["entries"]] == ["real.txt"] and out["total"] == 1


@POSIX
def test_a_name_with_a_control_character_is_cleaned_for_the_page(dirs):
    (dirs.mine / "bad\nname").write_text("x", encoding="utf-8")
    assert preview_of(str(dirs.mine))["entries"][0]["name"] == "bad?name"


def test_the_store_previews_the_folder_it_holds_and_nothing_when_there_is_none(store, dirs):
    assert store.preview() is None
    (dirs.mine / "a.txt").write_text("x", encoding="utf-8")
    store.set(str(dirs.mine))
    assert [e["name"] for e in store.preview()["entries"]] == ["a.txt"]


# ---- the words the model is told ----------------------------------------------------------------------------------------------

def test_the_grounding_names_the_folder_and_says_the_tools_are_read_only():
    text = grounding_text("/work/my-project")
    assert text.startswith("Working folder: /work/my-project")
    assert "read-only" in text and "cannot create, change or delete a file" in text and "cannot run a command" in text


def test_the_grounding_with_no_folder_says_so_and_where_to_set_one():
    text = grounding_text(None)
    assert text == grounding_text("") == NO_FOLDER_TEXT
    assert "No working folder is set" in text and "Settings" in text and "Working folder" in text


def test_a_very_long_path_is_clipped_in_the_grounding():
    assert len(grounding_text("/" + "a" * 900).split("\n")[0]) < 330


# ---- the routes ---------------------------------------------------------------------------------------------------------------

@pytest.fixture
def client(fake, tmp_path):
    cfg = ConnectorConfig(**fake.config_kwargs(tmp_path / "app"))
    router = build_router(SimpleNamespace(data_dir=cfg.data_dir, connector="auto", offline=False), config=cfg)
    app = FastAPI()
    app.state.services = SimpleNamespace(settings=SimpleNamespace(token=TOKEN))
    install_error_handlers(app)
    app.include_router(build_api_router(router=router, write_guard=require_token))
    c = TestClient(app)
    c.router, c.cfg, c.mine = router, cfg, tmp_path / "mine"
    c.mine.mkdir()
    (c.mine / "notes.txt").write_text("PRIVATE-WORDS", encoding="utf-8")
    (c.mine / "code").mkdir()
    yield c
    router.close()


def route(path=""):
    return f"{PREFIX}/workdir{path}"


def test_get_needs_no_token_and_says_none_is_set(client):
    response = client.get(route())
    assert response.status_code == 200
    assert response.json() == {"path": None, "usable": False, "problem": None, "preview": None}


def test_put_without_the_token_is_refused_and_writes_nothing(client):
    for headers in ({}, {"X-Sutra-Token": "wrong" * 5}):
        assert client.put(route(), headers=headers, json={"path": str(client.mine)}).status_code == 401
        assert client.delete(route(), headers=headers).status_code == 401
    assert client.router.folders.stored() is None


def test_put_stores_the_folder_and_answers_with_the_preview(client):
    response = client.put(route(), headers=HEADERS, json={"path": str(client.mine)})
    assert response.status_code == 200
    body = response.json()
    assert body["path"] == os.path.realpath(client.mine) and body["usable"] is True and body["problem"] is None
    assert body["preview"]["entries"] == [{"name": "code", "kind": "dir"}, {"name": "notes.txt", "kind": "file"}] and body["preview"]["total"] == 2
    assert "PRIVATE-WORDS" not in response.text
    assert client.get(route()).json() == body
    assert client.router.chat_folder() == os.path.realpath(client.mine)               # the router reads it for the very next turn


def test_put_of_a_folder_that_is_refused_is_a_422_with_the_reason_and_changes_nothing(client):
    client.put(route(), headers=HEADERS, json={"path": str(client.mine)})
    for path, words in ((str(client.cfg.data_dir), "belongs to Sutra itself"), ("relative/path", "full path"), (str(client.mine / "notes.txt"), "is a file")):
        response = client.put(route(), headers=HEADERS, json={"path": path})
        assert response.status_code == 422 and response.json()["error"]["code"] == "invalid_request", path
        assert words in response.json()["error"]["message"]
    assert client.get(route()).json()["path"] == os.path.realpath(client.mine)


def test_put_rejects_a_body_with_other_fields_or_a_path_that_is_too_long(client):
    assert client.put(route(), headers=HEADERS, json={"path": str(client.mine), "write": True}).status_code == 422
    assert client.put(route(), headers=HEADERS, json={"path": "/" + "a" * 1100}).status_code == 422
    assert client.router.folders.stored() is None


def test_delete_forgets_the_folder(client):
    client.put(route(), headers=HEADERS, json={"path": str(client.mine)})
    response = client.delete(route(), headers=HEADERS)
    assert response.status_code == 200 and response.json()["path"] is None and response.json()["preview"] is None
    assert client.router.chat_folder() == ""


def test_get_reports_a_folder_that_has_vanished_with_the_reason(client):
    client.put(route(), headers=HEADERS, json={"path": str(client.mine)})
    for child in client.mine.iterdir():
        if child.is_dir():
            child.rmdir()
        else:
            child.unlink()
    client.mine.rmdir()
    body = client.get(route()).json()
    assert body["path"] == os.path.realpath(client.mine) and body["usable"] is False and "There is no folder at" in body["problem"]
    assert body["preview"] is None and client.router.chat_folder() == ""
