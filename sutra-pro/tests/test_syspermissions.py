"""What the computer has allowed (MAN-15, D295): the probe only looks, a permission error is a need, a plan that names no protected folder shows no card, and the steps are those of the system.
Fake adapters and a monkeypatched platform: no real system dialog is opened."""
import errno
import os
import subprocess

import pytest

from sutra_app import oslayer, syspermissions
from sutra_app.syspermissions import MacAdapter, Need, NoAdapter, WindowsAdapter, adapter_for, is_permission_failure


def mac(tmp_path):
    home = tmp_path / "home"
    (home / "Desktop" / "site").mkdir(parents=True)
    (home / "Projects" / "site").mkdir(parents=True)
    return MacAdapter(home=home), home


def refuse_scandir(monkeypatch):
    monkeypatch.setattr(os, "scandir", lambda path: (_ for _ in ()).throw(PermissionError(errno.EPERM, "Operation not permitted")))


def test_a_folder_that_macos_protects_and_will_not_list_is_a_files_and_folders_need(tmp_path, monkeypatch):
    adapter, home = mac(tmp_path)
    refuse_scandir(monkeypatch)
    assert adapter.probe(home / "Desktop" / "site", write=False) == [Need("files_folders", "read", "Desktop")]
    assert adapter.probe(home / "Desktop" / "site", write=True) == [Need("files_folders", "write", "Desktop")]


def test_a_plan_that_never_names_a_protected_folder_shows_nothing_even_when_listing_would_fail(tmp_path, monkeypatch):
    adapter, home = mac(tmp_path)
    refuse_scandir(monkeypatch)
    assert adapter.probe(home / "Projects" / "site", write=True) == [] and adapter.probe(None, write=True) == []


def test_a_write_probe_leaves_no_file_behind_and_a_refused_write_is_a_need(tmp_path, monkeypatch):
    adapter, home = mac(tmp_path)
    folder = home / "Desktop" / "site"
    assert adapter.probe(folder, write=True) == [] and list(folder.iterdir()) == []                    # made and removed
    real_open = os.open

    def refuse(path, flags, *a, **k):
        if ".sutra-probe-" in str(path):
            raise PermissionError(errno.EPERM, "Operation not permitted")
        return real_open(path, flags, *a, **k)
    monkeypatch.setattr(os, "open", refuse)
    assert adapter.probe(folder, write=True) == [Need("files_folders", "write", "Desktop")] and list(folder.iterdir()) == []


def test_the_write_probe_never_touches_the_git_folder(tmp_path, monkeypatch):
    adapter, home = mac(tmp_path)
    git = home / "Desktop" / "site" / ".git"
    git.mkdir()
    calls = []
    monkeypatch.setattr(os, "open", lambda *a, **k: calls.append(a) or (_ for _ in ()).throw(AssertionError("must not write")))
    assert adapter.probe(git, write=True) == [] and calls == [] and list(git.iterdir()) == []


def test_windows_asks_for_controlled_folder_access_for_administrator_rights_and_for_long_paths(tmp_path, monkeypatch):
    adapter = WindowsAdapter()
    folder = tmp_path / "work"
    folder.mkdir()
    monkeypatch.setattr(oslayer, "is_elevated", lambda: True)
    assert adapter.probe(folder, write=False) == [Need("elevated", "read", "administrator rights")]
    monkeypatch.setattr(oslayer, "is_elevated", lambda: False)
    real_open = os.open
    monkeypatch.setattr(os, "open", lambda path, flags, *a, **k: (_ for _ in ()).throw(PermissionError(13, "Access is denied")) if ".sutra-probe-" in str(path) else real_open(path, flags, *a, **k))
    assert adapter.probe(folder, write=True) == [Need("controlled_folder", "write", "work")]
    long_folder = tmp_path / ("d" * 120) / ("e" * 120)
    long_folder.mkdir(parents=True)
    monkeypatch.undo()                                                                                  # a plain open again, and a system that refuses long file names
    monkeypatch.setattr(oslayer, "is_elevated", lambda: False)
    monkeypatch.setattr(oslayer, "long_paths_enabled", lambda: False)
    assert Need("long_paths", "read", "long file names") in adapter.probe(long_folder, write=False)


def test_the_steps_are_those_of_the_system_in_plain_words(tmp_path):
    steps = " ".join(MacAdapter(home=tmp_path).explain(Need("files_folders", "write", "Desktop")))
    assert "Files & Folders" in steps and "Desktop" in steps and "Check again" in steps and "changes no setting" in steps
    assert "Full Disk Access" in " ".join(MacAdapter(home=tmp_path).explain(Need("full_disk")))
    windows = " ".join(WindowsAdapter().explain(Need("controlled_folder", "write", "work")))
    assert "Controlled folder access" in windows and "Check again" in windows and "Files & Folders" not in windows
    assert "`claude`" in windows and "`codex`" in windows and "Sutra Pro" in windows and "Sutra Pro" in steps          # the programs that write are named (m4)
    assert "administrator" in " ".join(WindowsAdapter().explain(Need("elevated"))) and syspermissions.explain(Need("x"), NoAdapter())


def test_the_adapter_follows_the_platform_and_a_system_with_nothing_to_ask_asks_nothing(tmp_path):
    assert isinstance(adapter_for("darwin"), MacAdapter) and isinstance(adapter_for("win32"), WindowsAdapter) and isinstance(adapter_for("linux"), NoAdapter)
    assert syspermissions.probe(tmp_path, write=True, adapter=NoAdapter()) == [] and NoAdapter().open_settings(Need("x")) is False


def test_opening_the_settings_page_runs_one_open_command_and_a_failure_is_false_never_an_error(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: seen.append(argv) or subprocess.CompletedProcess(argv, 0))
    assert MacAdapter(home=tmp_path).open_settings(Need("files_folders", "read", "Desktop")) is True
    assert seen == [["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_FilesAndFolders"]]
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: (_ for _ in ()).throw(OSError("no open")))
    assert MacAdapter(home=tmp_path).open_settings(Need("full_disk")) is False


def test_the_probe_alone_never_opens_a_settings_page_or_changes_anything(tmp_path, monkeypatch):
    adapter, home = mac(tmp_path)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("the probe must not open anything")))
    assert adapter.probe(home / "Desktop" / "site", write=True) == []


@pytest.mark.parametrize("failure,expected", [(PermissionError(1, "x"), True), (OSError(errno.EPERM, "x"), True), (OSError(errno.EACCES, "x"), True), ("needs_system_permission: [Errno 1] x", True),
                                              ("WinError 5: Access is denied", False), ("EPERM: operation not permitted, open '/Users/x'", False), ("the model said no", False), (ValueError("bad"), False), ("", False),
                                              ("a node wrote: needs_system_permission", False), (OSError(2, "gone"), False)])
def test_a_refusal_of_the_computer_is_told_from_any_other_failure_by_the_word_the_host_writes(failure, expected):
    assert is_permission_failure(failure) is expected


def test_the_oslayer_questions_are_false_or_true_where_nothing_can_be_found_out(monkeypatch):
    monkeypatch.setattr(oslayer, "IS_WINDOWS", False)
    assert oslayer.is_elevated() is False and oslayer.long_paths_enabled() is True
