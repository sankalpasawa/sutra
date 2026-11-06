"""Finding the CLIs for an app opened from Finder (GAP-providers, discover.py; re-expresses the old app's test_provider_detect.py): the
version-manager folders are looked in, only a folder that holds the command joins the child's PATH, appended and never prepended, the
owner's chosen file wins while it is still there, and a Mac with Claude Desktop but no Claude Code is told so, never "not on PATH"."""
from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from sutra_app.connectors import discover
from sutra_app.connectors.bins import BinStore
from sutra_app.connectors.discover import (
    DESKTOP_APPS, augment_path, claude_desktop_installed, connector_config, explain_missing, find_cli, known_dirs, use_cli,
)
from sutra_app.connectors.errors import DESKTOP_ONLY, CliMissingError
from sutra_app.connectors.factory import build_router
from sutra_app.connectors.models import ConnectorConfig

pytestmark = pytest.mark.skipif(sys.platform.startswith("win"), reason="CLI discovery is POSIX only; Windows keeps the installer's PATH")

LAUNCHD_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"          # what a Mac app opened from Finder gets


def executable(path: Path, body: str = "#!/bin/sh\nexit 0\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


@pytest.fixture(autouse=True)
def no_system_folders(monkeypatch):
    """This machine's own Homebrew may hold a real claude or codex: the tests look only in their temporary home."""
    monkeypatch.setattr(discover, "KNOWN_DIRS", tuple(d for d in discover.KNOWN_DIRS if d not in discover.SYSTEM_DIRS))


@pytest.fixture
def home(tmp_path):
    folder = tmp_path / "home"
    folder.mkdir()
    return folder


def test_version_manager_shims_are_looked_in_and_nvm_newest_version_first(home):
    for version in ("v18.20.1", "v22.1.0", "v9.0.0", "system"):
        (home / ".nvm" / "versions" / "node" / version / "bin").mkdir(parents=True)
    dirs = known_dirs(str(home), {})
    for entry in ("/.local/bin", "/.volta/bin", "/Library/pnpm", "/.local/share/mise/shims", "/.asdf/shims", "/.fnm/aliases/default/bin",
                  "/.yarn/bin", "/.bun/bin", "/.npm-global/bin", "/.claude/local"):
        assert str(home) + entry in dirs, entry
    nvm = [d for d in dirs if "/.nvm/" in d]
    assert nvm == [str(home / ".nvm/versions/node" / v / "bin") for v in ("v22.1.0", "v18.20.1", "v9.0.0", "system")]
    assert len(dirs) == len(set(dirs))


def test_an_installer_variable_names_a_folder_too(home, tmp_path):
    volta = tmp_path / "elsewhere" / "volta"
    dirs = known_dirs(str(home), {"VOLTA_HOME": str(volta), "PNPM_HOME": "relative/is/ignored", "NVM_DIR": str(tmp_path / "nvm")})
    assert dirs[0] == str(volta / "bin") and "relative/is/ignored" not in dirs


def test_codex_from_nvm_and_claude_from_volta_are_found_with_a_launchd_path(home):
    codex = executable(home / ".nvm/versions/node/v22.1.0/bin/codex")
    claude = executable(home / ".volta/bin/claude")
    found = find_cli("codex", stored=None, path=LAUNCHD_PATH, home=str(home), environ={})
    assert (found.exe, found.folder, found.source) == (str(codex), str(codex.parent), "known")
    assert find_cli("claude", stored=None, path=LAUNCHD_PATH, home=str(home), environ={}).exe == str(claude)


def test_a_folder_that_does_not_hold_the_command_is_never_used(home):
    (home / ".volta/bin").mkdir(parents=True)                             # exists, but holds no claude
    (home / ".local/bin").mkdir(parents=True)
    (home / ".local/bin/claude").write_text("not executable", encoding="utf-8")
    found = find_cli("claude", stored=None, path=LAUNCHD_PATH, home=str(home), environ={})
    assert (found.exe, found.folder, found.source) == ("claude", None, "none")


def test_the_path_wins_over_the_known_folders(home, tmp_path):
    executable(home / ".local/bin/claude")
    on_path = executable(tmp_path / "bin" / "claude")
    found = find_cli("claude", stored=None, path=f"{tmp_path / 'bin'}:{LAUNCHD_PATH}", home=str(home), environ={})
    assert (found.exe, found.folder, found.source) == (str(on_path), None, "path")


def test_the_chosen_file_wins_while_it_exists_and_is_ignored_once_it_vanished(home, tmp_path):
    executable(home / ".local/bin/claude")
    chosen = executable(tmp_path / "opt" / "claude")
    assert find_cli("claude", stored=str(chosen), path=LAUNCHD_PATH, home=str(home), environ={}).source == "stored"
    chosen.unlink()
    found = find_cli("claude", stored=str(chosen), path=LAUNCHD_PATH, home=str(home), environ={})
    assert (found.source, found.exe) == ("known", str(home / ".local/bin/claude"))


def test_a_folder_is_appended_once_and_never_prepended():
    assert augment_path(LAUNCHD_PATH, ["/x/bin", None, "/x/bin", "/usr/bin"]) == LAUNCHD_PATH + ":/x/bin"
    assert augment_path("", ["/x/bin"]) == "/x/bin"


def test_claude_desktop_without_claude_code_is_named_and_never_called_a_path_problem(home):
    assert claude_desktop_installed(str(home), isdir=lambda p: p == "/Applications/Claude.app")
    assert claude_desktop_installed(str(home), isdir=lambda p: p == str(home / "Applications/Claude.app"))
    assert not claude_desktop_installed(str(home), isdir=lambda p: False)
    said = explain_missing("claude", True, "CLI not found on PATH")
    assert said == DESKTOP_ONLY and "Claude Code" in said and "Claude Desktop" in said and "PATH" not in said
    assert explain_missing("claude", False, "CLI not found on PATH") == "CLI not found on PATH"       # without Desktop the PATH diagnosis stays
    assert explain_missing("codex", True, "CLI not found on PATH") == "CLI not found on PATH"
    assert CliMissingError("", provider="claude", detail={"desktop": True}).user_message() == DESKTOP_ONLY
    assert "PATH" in CliMissingError("", provider="claude").user_message()
    assert DESKTOP_APPS == ("/Applications/Claude.app", "~/Applications/Claude.app")


def test_the_running_apps_config_has_full_paths_a_child_path_and_the_desktop_flag(home, tmp_path):
    codex = executable(home / ".nvm/versions/node/v22.1.0/bin/codex")
    data = tmp_path / "data"
    cfg = connector_config(data, environ={"PATH": LAUNCHD_PATH, "HOME": str(home)}, isdir=lambda p: p == "/Applications/Claude.app")
    assert (cfg.claude_exe, cfg.codex_exe) == ("claude", str(codex))
    assert cfg.extra_env == {"PATH": LAUNCHD_PATH + ":" + str(codex.parent)}          # the shim's `#!/usr/bin/env node` finds node
    assert cfg.claude_desktop is True
    plain = connector_config(data, environ={"PATH": LAUNCHD_PATH, "HOME": str(tmp_path / "empty")}, isdir=lambda p: False)
    assert (plain.claude_exe, plain.codex_exe, plain.extra_env, plain.claude_desktop) == ("claude", "codex", {}, False)


def test_the_running_apps_config_uses_the_owners_chosen_file(home, tmp_path):
    chosen = executable(tmp_path / "tools" / "claude")
    data = tmp_path / "data"
    BinStore(data).set("claude", str(chosen))
    cfg = connector_config(data, environ={"PATH": LAUNCHD_PATH, "HOME": str(home)}, isdir=lambda p: False)
    assert cfg.claude_exe == str(chosen) and cfg.extra_env["PATH"].endswith(":" + str(chosen.parent))


def fake_in(folder: Path, fake, name: str) -> Path:
    """A shim where an installer would put it, handing over to the fake CLI (what a Volta or asdf shim does with the real one)."""
    return executable(folder / name, f'#!/bin/sh\nexec "{fake.exe(name)}" "$@"\n')


def test_a_claude_in_a_volta_folder_is_installed_for_the_router_with_a_launchd_path(fake, home, tmp_path):
    fake_in(home / ".volta" / "bin", fake, "claude")
    base = fake.config_kwargs(tmp_path)
    found = connector_config(base["data_dir"], environ={"PATH": LAUNCHD_PATH, "HOME": str(home)}, isdir=lambda p: False,
                             work_root=base["work_root"], python=base["python"])
    cfg = found.model_copy(update={"extra_env": {**base["extra_env"], **found.extra_env}, "codex_exe": base["codex_exe"]})
    router = build_router(SimpleNamespace(data_dir=cfg.data_dir, connector="auto", offline=False), config=cfg)
    try:
        status = router.provider_summary("claude")
        assert status.installed is True and status.signed_in is True and status.detail != "CLI not found on PATH"
    finally:
        router.close()
    assert fake.model_calls() == []


def test_the_status_says_desktop_is_not_claude_code_and_keeps_the_path_wording_otherwise(tmp_path):
    def summary(desktop):
        cfg = ConnectorConfig(data_dir=tmp_path / "d", work_root=tmp_path / "w", claude_exe=str(tmp_path / "no-claude"),
                              codex_exe=str(tmp_path / "no-codex"), claude_desktop=desktop)
        router = build_router(SimpleNamespace(data_dir=cfg.data_dir, connector="auto", offline=False), config=cfg)
        try:
            return router.provider_summary("claude")
        finally:
            router.close()

    with_desktop = summary(True)
    assert with_desktop.installed is False and with_desktop.detail == DESKTOP_ONLY
    assert summary(False).detail == "CLI not found on PATH"


def _ask():
    from sutra_app.connectors.models import AskRequest
    return AskRequest(user="hi", kind="text")


def test_the_plan_and_the_pill_name_claude_code_when_only_desktop_is_there(tmp_path):
    from sutra_app.connectors.chat_port import RouterChatPort
    from sutra_app.connectors.errors import NoProviderError
    cfg = ConnectorConfig(data_dir=tmp_path / "d", work_root=tmp_path / "w", claude_exe=str(tmp_path / "no-claude"),
                          codex_exe=str(tmp_path / "no-codex"), claude_desktop=True)
    router = build_router(SimpleNamespace(data_dir=cfg.data_dir, connector="auto", offline=False), config=cfg)
    try:
        with pytest.raises(NoProviderError) as e:
            router.plan(_ask())
        reasons = dict((s["provider"], s["reason"]) for s in e.value.detail["skipped"])
        assert reasons["claude"] == DESKTOP_ONLY and "PATH" in reasons["codex"]
        pill = {p.name: p for p in RouterChatPort(router).providers()}
        assert pill["claude"].ready is False and pill["claude"].why_not == DESKTOP_ONLY
    finally:
        router.close()


def test_use_cli_points_the_running_router_at_the_new_file_and_says_so(fake, tmp_path):
    events = []
    base = fake.config_kwargs(tmp_path)
    cfg = ConnectorConfig(**{**base, "claude_exe": str(tmp_path / "no-claude")})
    router = build_router(SimpleNamespace(data_dir=cfg.data_dir, connector="auto", offline=False), config=cfg,
                          events=lambda t, d: events.append((t, d)))
    try:
        assert router.provider_summary("claude").installed is False
        chosen = fake_in(tmp_path / "picked", fake, "claude")
        found = use_cli(router, "claude", str(chosen), environ={"PATH": LAUNCHD_PATH, "HOME": str(tmp_path)})
        assert found.source == "stored" and router.connectors["claude"].cfg.claude_exe == str(chosen)
        assert router.connectors["claude"].cfg.extra_env["PATH"].endswith(":" + str(chosen.parent))
        assert router.connectors["codex"].cfg.codex_exe == base["codex_exe"]                     # the other provider is untouched
        assert router.provider_summary("claude").installed is True
        assert ("connector.health", {"provider": "claude", "state": "ok", "until": None, "reason": None}) in events
    finally:
        router.close()


def test_discovery_runs_nothing_and_reads_no_shell_file(home, tmp_path, monkeypatch):
    import subprocess
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("discovery started a process")))
    (home / ".zshrc").write_text("echo should never run", encoding="utf-8")
    connector_config(tmp_path / "data", environ={"PATH": LAUNCHD_PATH, "HOME": str(home)}, isdir=lambda p: False)
    assert os.path.exists(home / ".zshrc")
