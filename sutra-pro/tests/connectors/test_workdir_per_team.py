"""A working folder per team (named projects, task 1): a team's own folder lives in `departments/<id>/workdir.json`, beside the app-wide
`connectors/workdir.json`; a team without a usable folder of its own falls back to the app-wide one."""
from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest

from sutra_app.connectors.errors import InvalidRequestError
from sutra_app.connectors.router import Router
from sutra_app.connectors.workdir import WorkFolder

from connectors.test_workdir_chat import policy


def real(path):
    return os.path.realpath(str(path))


@pytest.fixture
def dirs(tmp_path):
    data, a, b = tmp_path / "data", tmp_path / "a", tmp_path / "b"
    for d in (data, a, b):
        d.mkdir()
    return SimpleNamespace(data=data, a=a, b=b)


def test_a_team_folder_is_its_own_file(dirs):
    WorkFolder(dirs.data, dept_id="pulse").set(str(dirs.a), access="edit")
    body = json.loads((dirs.data / "departments" / "pulse" / "workdir.json").read_text(encoding="utf-8"))
    assert body == {"version": 1, "path": real(dirs.a), "access": "edit"}
    assert not (dirs.data / "connectors" / "workdir.json").exists()


def test_team_grant_prefers_the_team_folder(dirs):
    WorkFolder(dirs.data).set(str(dirs.b), access="read")
    WorkFolder(dirs.data, dept_id="pulse").set(str(dirs.a), access="edit")
    grant = WorkFolder(dirs.data).team_grant("pulse")
    assert grant == real(dirs.a)
    assert grant.edit is True


def test_a_team_without_a_folder_gets_the_app_wide_one(dirs):
    WorkFolder(dirs.data).set(str(dirs.b), access="read")
    grant = WorkFolder(dirs.data).team_grant("web")
    assert grant == real(dirs.b)
    assert grant.edit is False


def test_a_vanished_team_folder_gives_no_folder_never_the_app_wide_one(dirs):
    """R1.6: only a project WITHOUT a folder falls back; one whose folder vanished must not edit an unrelated folder."""
    WorkFolder(dirs.data).set(str(dirs.b))
    WorkFolder(dirs.data, dept_id="pulse").set(str(dirs.a))
    dirs.a.rmdir()
    assert WorkFolder(dirs.data).team_grant("pulse") is None


def test_blank_dept_is_the_app_wide_folder(dirs):
    WorkFolder(dirs.data).set(str(dirs.b))
    WorkFolder(dirs.data, dept_id="pulse").set(str(dirs.a))
    store = WorkFolder(dirs.data)
    assert store.team_grant("") == store.grant() == real(dirs.b)


def test_for_team_keeps_the_roots(dirs, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    team = WorkFolder(dirs.data, work).for_team("pulse")
    assert (team.data_dir, team.work_root, team.dept_id) == (dirs.data, work, "pulse")


def test_a_team_folder_is_refused_like_the_app_wide_one(dirs):
    with pytest.raises(InvalidRequestError, match="That folder belongs to Sutra itself"):
        WorkFolder(dirs.data, dept_id="pulse").set(str(dirs.data))
    assert not (dirs.data / "departments" / "pulse" / "workdir.json").exists()


@pytest.mark.parametrize("bad", ["../x", "Pulse", "a", "x/y", "-pulse"])
def test_a_bad_team_id_is_refused(dirs, bad):
    with pytest.raises(ValueError):
        WorkFolder(dirs.data, dept_id=bad)


def test_router_chat_folder_uses_the_team(dirs):
    WorkFolder(dirs.data).set(str(dirs.b))
    WorkFolder(dirs.data, dept_id="pulse").set(str(dirs.a))
    router = Router({}, policy())
    router.folders = WorkFolder(dirs.data)
    assert router.chat_folder("pulse") == real(dirs.a)
    assert router.chat_folder("") == real(dirs.b)
    assert router.chat_folder() == real(dirs.b)


def test_a_team_chat_turn_names_its_team():
    from sutra_app.connectors.chat_models import ChatTurnIn
    from sutra_app.engine.port import CallTag
    from sutra_app.orchestrator.api.chat_v2 import _for_team
    sessions = {"cs_pulse": SimpleNamespace(kind="department", node_id="pulse"), "cs_org": SimpleNamespace(kind="org", node_id="root")}
    services = SimpleNamespace(chats=SimpleNamespace(session=lambda sid: sessions[sid]))
    turn = _for_team(services, "cs_pulse", ChatTurnIn(text="hi", tag=CallTag(workspace="read")))
    assert (turn.tag.dept_id, turn.tag.workspace) == ("pulse", "read")
    assert _for_team(services, "cs_org", ChatTurnIn(text="hi")).tag.dept_id == ""
