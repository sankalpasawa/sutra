"""The CLI file the owner chose in Settings survives a restart on Windows too (QA firstrun-settings; discover.py `connector_config`).

Windows does no folder discovery (the installer's PATH is used), but `connector_config` once returned before it read bins.json there, so the
file the page confirmed with "Using that file." was applied to the running connector and forgotten at the next start. These tests run on every
platform: where the machine is not Windows they switch `oslayer.IS_WINDOWS` on, which is all the Windows branch looks at."""
from __future__ import annotations

import sys

import pytest

from sutra_app import oslayer
from sutra_app.connectors.bins import BinStore, check_path
from sutra_app.connectors.discover import connector_config
from sutra_app.connectors.errors import InvalidRequestError

EXE = ".exe" if sys.platform.startswith("win") else ""        # a Windows file is claude.exe; the stand-in on another system keeps the bare name


@pytest.fixture(autouse=True)
def windows(monkeypatch):
    monkeypatch.setattr(oslayer, "IS_WINDOWS", True)


def runnable(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("@echo off\r\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def test_a_chosen_file_is_the_executable_after_a_restart(tmp_path):
    data = tmp_path / "data"
    claude = runnable(tmp_path / "tools" / f"claude{EXE}")
    BinStore(data).set("claude", str(claude))
    cfg = connector_config(data)                                           # what the next start builds
    assert cfg.claude_exe == str(claude)
    assert cfg.codex_exe == "codex"                                        # nothing chosen for Codex: the name, looked up on PATH as before
    assert cfg.extra_env == {}                                             # no POSIX folder discovery on Windows


def test_both_choices_are_read_and_a_field_the_caller_hands_in_wins(tmp_path):
    data = tmp_path / "data"
    claude = runnable(tmp_path / "tools" / f"claude{EXE}")
    codex = runnable(tmp_path / "tools" / f"codex{EXE}")
    BinStore(data).set("claude", str(claude))
    BinStore(data).set("codex", str(codex))
    both = connector_config(data)
    assert (both.claude_exe, both.codex_exe) == (str(claude), str(codex))
    handed = connector_config(data, claude_exe="fake-claude", work_root=tmp_path / "work")
    assert (handed.claude_exe, handed.codex_exe, handed.work_root) == ("fake-claude", str(codex), tmp_path / "work")


def test_a_choice_whose_file_has_vanished_is_ignored_not_honoured(tmp_path):
    data = tmp_path / "data"
    claude = runnable(tmp_path / "tools" / f"claude{EXE}")
    BinStore(data).set("claude", str(claude))
    claude.unlink()
    assert connector_config(data).claude_exe == "claude"


def test_no_choice_and_no_data_folder_give_the_plain_defaults(tmp_path):
    cfg = connector_config(tmp_path / "never-made")
    assert (cfg.claude_exe, cfg.codex_exe, cfg.extra_env, cfg.claude_desktop) == ("claude", "codex", {}, False)


def test_the_refusals_say_where_not_which_and_a_drive_letter_not_a_slash():
    """The box on Windows says `where claude`; the sentences that come back for a wrong entry must not send the owner to `which` or to a leading /."""
    with pytest.raises(InvalidRequestError) as empty:
        check_path("claude", "")
    assert "`where claude`" in str(empty.value) and "which" not in str(empty.value) and "Terminal" not in str(empty.value)
    with pytest.raises(InvalidRequestError) as relative:
        check_path("claude", "claude.exe")
    text = str(relative.value)
    assert "starting with a drive letter, like C:\\ " in text and "`where claude`" in text and "which" not in text and "starting with /" not in text


def test_a_tilde_and_a_backslash_is_expanded_to_the_home_folder_on_windows(tmp_path):
    """`~\\claude.exe` is a home-folder path there as `~/claude` is on a Mac: it is not refused as a path that does not start at a root."""
    with pytest.raises(InvalidRequestError) as caught:
        check_path("claude", "~\\claude", home=str(tmp_path))
    assert "starting with" not in str(caught.value), str(caught.value)
