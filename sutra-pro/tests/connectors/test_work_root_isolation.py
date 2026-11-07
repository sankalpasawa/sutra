"""QA direct-chat bug 1: a data folder owns its provider sessions.

The default work root used to be `<tempdir>/sutra-app-<uid>/work` for EVERY data folder of the machine, and session ids repeat (`cs_org` is the org chat of
all of them), so a brand-new data folder resumed the provider session another instance had created (with a real Claude: another folder's conversation),
two instances overwrote each other's `session.json` and `system.txt`, and the first turn of a fresh folder could show a switch from a provider it never used.
The default now carries the folder's identity: the realpath of the data folder plus a random id kept in `<data>/connectors/work-id`, so a folder
that was deleted and made again at the same path starts clean too.

Real Claude connector against the fake CLI (the call log shows `--resume` or not); the temp root is private to each test."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

from sutra_app.connectors.chat_models import ChatTurnIn
from sutra_app.connectors.chat_port import RouterChatPort
from sutra_app.connectors.claude import ClaudeConnector
from sutra_app.connectors.models import ConnectorConfig, Message, RouteContext
from sutra_app.connectors.router import Router
from sutra_app.connectors.usage import load_session_state

from test_router_chat import History, policy

SID = "cs_org"          # the same id in every data folder


@pytest.fixture
def private_tmp(tmp_path, monkeypatch):
    """The default work root is under the temp folder: make that folder this test's own, so earlier runs cannot be read back."""
    root = tmp_path / "tmp"
    root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(root))
    return root


def instance(fake, data_dir: Path):
    """One 'app instance': its own data folder, the DEFAULT work root (no work_root passed, as the app does), the real claude connector."""
    data_dir.mkdir(parents=True, exist_ok=True)
    kwargs = fake.config_kwargs(data_dir.parent)
    kwargs.pop("work_root")
    cfg = ConnectorConfig(**{**kwargs, "data_dir": data_dir})
    history = History()
    router = Router({"claude": ClaudeConnector(cfg)}, policy(), transcripts=history, sleep=lambda s: None)
    return RouterChatPort(router), router, history, cfg


def resumes(fake):
    """The `--resume` id of every claude model call so far (None for a call that started a new session)."""
    out = []
    for call in fake.model_calls("claude"):
        argv = call["argv"]
        out.append(argv[argv.index("--resume") + 1] if "--resume" in argv else None)
    return out


def test_a_fresh_data_folder_starts_its_own_provider_session_not_the_one_of_another_instance(fake, tmp_path, private_tmp):
    fake.sequence("ok_plain").reply(text="pong")
    a_port, a_router, _, a_cfg = instance(fake, tmp_path / "a" / "data")
    b_port, b_router, b_history, b_cfg = instance(fake, tmp_path / "b" / "data")
    a_port.send(SID, ChatTurnIn(text="My secret codeword is kiwi."))
    a_port.send(SID, ChatTurnIn(text="Do you remember it?"))
    assert resumes(fake) == [None, load_session_state(a_cfg.resolved_work_root() / SID).provider_session_id]          # A resumes ITS session on turn two
    b_port.send(SID, ChatTurnIn(text="What is my secret codeword?"))
    assert resumes(fake)[2] is None                                    # B never saw A's session: a new one, not --resume of A's id
    a_state = load_session_state(a_cfg.resolved_work_root() / SID)
    b_state = load_session_state(b_cfg.resolved_work_root() / SID)
    assert a_state.provider_session_id != b_state.provider_session_id and (a_state.turns, b_state.turns) == (2, 1)
    assert a_cfg.resolved_work_root() != b_cfg.resolved_work_root()
    a_router.close()
    b_router.close()


def test_two_instances_do_not_overwrite_each_others_system_text_or_session_file(fake, tmp_path, private_tmp):
    fake.sequence("ok_plain").reply(text="pong")
    a_port, a_router, _, a_cfg = instance(fake, tmp_path / "a" / "data")
    b_port, b_router, _, b_cfg = instance(fake, tmp_path / "b" / "data")
    a_port.set_system(SID, "the record of instance A")
    b_port.set_system(SID, "the record of instance B")
    assert (a_cfg.resolved_work_root() / SID / "system.txt").read_text() == "the record of instance A"
    assert (b_cfg.resolved_work_root() / SID / "system.txt").read_text() == "the record of instance B"
    a_router.close()
    b_router.close()


def test_a_folder_deleted_and_made_again_at_the_same_path_starts_a_new_provider_session(fake, tmp_path, private_tmp):
    fake.sequence("ok_plain").reply(text="pong")
    data = tmp_path / "x" / "data"
    first_port, first_router, _, first_cfg = instance(fake, data)
    first_port.send(SID, ChatTurnIn(text="My secret codeword is kiwi."))
    old = load_session_state(first_cfg.resolved_work_root() / SID).provider_session_id
    first_router.close()
    shutil.rmtree(data)                                                  # the owner deletes the data folder to start again
    again_port, again_router, _, again_cfg = instance(fake, data)
    again_port.send(SID, ChatTurnIn(text="What is my secret codeword?"))
    assert resumes(fake)[-1] is None and load_session_state(again_cfg.resolved_work_root() / SID).provider_session_id != old
    again_router.close()


def test_one_folder_keeps_its_work_root_between_restarts(fake, tmp_path, private_tmp):
    """The identity is stable: the same folder gets the same root, so a chat still resumes its provider session after the app restarts."""
    fake.sequence("ok_plain").reply(text="pong")
    data = tmp_path / "x" / "data"
    port, router, _, cfg = instance(fake, data)
    port.send(SID, ChatTurnIn(text="one"))
    sid = load_session_state(cfg.resolved_work_root() / SID).provider_session_id
    router.close()
    port2, router2, _, cfg2 = instance(fake, data)
    assert cfg2.resolved_work_root() == cfg.resolved_work_root()
    port2.send(SID, ChatTurnIn(text="two"))
    assert resumes(fake)[-1] == sid
    router2.close()


def test_the_default_root_is_under_the_temp_root_by_uid_outside_the_data_folder(tmp_path, private_tmp):
    """CD9 stays: the work dirs sit outside the repo (a data folder inside a checkout must not make them read its CLAUDE.md)."""
    data = tmp_path / "repo" / "data"
    data.mkdir(parents=True)
    root = ConnectorConfig(data_dir=data).resolved_work_root()
    assert Path(os.path.realpath(private_tmp)) in root.parents and root.parent.name.startswith("sutra-app-")
    assert data.resolve() not in root.parents


def test_an_explicit_work_root_is_used_as_it_is_and_a_missing_data_folder_is_not_created(tmp_path, private_tmp):
    explicit = ConnectorConfig(data_dir=tmp_path / "gone", work_root=tmp_path / "w").resolved_work_root()
    assert explicit == Path(os.path.realpath(tmp_path / "w"))
    default = ConnectorConfig(data_dir=tmp_path / "gone").resolved_work_root()
    assert default.parent.name.startswith("sutra-app-") and not (tmp_path / "gone").exists()          # reading a root never makes the data folder


def test_the_id_file_is_private_and_a_damaged_one_is_made_again(tmp_path, private_tmp):
    data = tmp_path / "d"
    data.mkdir()
    first = ConnectorConfig(data_dir=data).resolved_work_root()
    mark = data / "connectors" / "work-id"
    assert mark.is_file() and len(mark.read_text().strip()) >= 16
    if os.name == "posix":
        assert (mark.stat().st_mode & 0o777) == 0o600
    assert ConnectorConfig(data_dir=data).resolved_work_root() == first
    mark.write_text("")                                                  # damaged: a root that would be shared by every empty file must not result
    second = ConnectorConfig(data_dir=data).resolved_work_root()
    assert second != first and len(mark.read_text().strip()) >= 16
    assert json.dumps(str(second))                                       # a plain path
