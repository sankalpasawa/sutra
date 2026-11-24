"""scripts/install_app.py on Windows (D432): the beta is a folder holding `Sutra Pro Beta.exe` beside the stable `Sutra Pro` folder, its facts come from
resources/build-info.json, its processes from PowerShell's process list, it is closed the way a person closes it (the window's own close, never a forced
kill), copied in whole or not at all, opened by starting its exe, and given a Start-menu shortcut. `--pull` brings the checkout to origin/main first.

The commands are answered by a fake over a temporary folder, as in test_install_app.py; `sys.platform` is set to win32, so these run on any system.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import install_app as ia                                                       # noqa: E402

REAL_PROCESS_TABLE = ia.process_table
STABLE_ID, BETA_ID = "os.sutra.pro", "os.sutra.pro.beta"


def make_win_app(path: Path, bundle_id: str, version: str, *, build: str = "", payload: str = "x") -> Path:
    """What the script reads of a Windows app folder: resources/build-info.json and the exe (its bytes tell one copy from another)."""
    name = "Sutra Pro Beta" if bundle_id == BETA_ID else "Sutra Pro"
    (path / "resources").mkdir(parents=True, exist_ok=True)
    record = {"app": name, "bundle_id": bundle_id, "version": version, "target": "win-x64"}
    if build:
        record.update(channel="beta", build=build)
    (path / "resources" / "build-info.json").write_text(json.dumps(record))
    (path / f"{name}.exe").write_text(payload)
    return path


class FakeWindows:
    def __init__(self, tmp_path: Path):
        self.home = tmp_path / "home"
        self.apps = tmp_path / "Programs"
        self.apps.mkdir()
        self.home.mkdir()
        self.calls: list[list[str]] = []
        self.processes: list[tuple[int, int, str]] = []
        self.served_version = None
        self.started: list[Path] = []
        self.git_changes = ""
        self.git_upstream = "origin/main"
        self.close_works = True

    def run(self, args, *, timeout=None, cwd=None, env=None):
        args = [str(item) for item in args]
        self.calls.append(args)
        program = "python" if args[0] == sys.executable else Path(args[0]).stem.lower()
        handler = getattr(self, f"cmd_{program}", None)
        if handler is None:
            raise AssertionError(f"the script ran a command nobody expected: {args}")
        code, out, err = handler(args)
        return subprocess.CompletedProcess(args, code, out, err)

    def process_table(self):
        return list(self.processes)

    def health(self, port):
        return {"ok": True, "version": self.served_version} if self.served_version else None

    def start(self, program: Path):
        self.started.append(Path(program))
        data = self.home / ".sutra-pro-beta"
        data.mkdir(exist_ok=True)
        (data / "app.pid").write_text("4343 8782\n{}\n")
        self.processes.append((4300, 1, f'"{program}"'))

    def cmd_taskkill(self, args):
        pid = int(args[args.index("/PID") + 1])
        if self.close_works:                                    # the window closes, and with it its helpers and its server
            root = next(command for p, _parent, command in self.processes if p == pid)
            folder = root.strip('"').rsplit("\\", 1)[0].rsplit("/", 1)[0]
            self.processes = [row for row in self.processes if folder not in row[2]]
        return 0, "SUCCESS: Sent termination signal", ""

    def cmd_powershell(self, args):
        script = args[-1]
        if "Win32_Process" in script:
            return 0, "\r\n".join(f"{pid} {parent} {command}" for pid, parent, command in self.processes), ""
        if "WScript.Shell" in script:
            return 0, "", ""
        raise AssertionError(args)

    def cmd_uv(self, args):
        out = Path(args[args.index("--out-dir") + 1])
        (out / "sutra_pro-0.8.1-py3-none-any.whl").write_bytes(b"wheel")
        return 0, "", ""

    def cmd_git(self, args):
        if "rev-parse" in args and "@{u}" in " ".join(args):
            return (0, self.git_upstream + "\n", "") if self.git_upstream else (128, "", "fatal: no upstream configured")
        if "rev-parse" in args:
            return 0, "1a2b3c4\n", ""
        if "status" in args:
            return 0, self.git_changes, ""
        if "fetch" in args or "merge" in args:
            return 0, "", ""
        raise AssertionError(args)

    def cmd_bash(self, args):
        return 0, "", ""

    def cmd_python(self, args):
        return 0, "PROVED", ""


@pytest.fixture
def win(tmp_path, monkeypatch):
    fake = FakeWindows(tmp_path)
    monkeypatch.setattr(ia, "run", fake.run)
    monkeypatch.setattr(ia, "process_table", fake.process_table)
    monkeypatch.setattr(ia, "health", fake.health)
    monkeypatch.setattr(ia, "start", fake.start)
    monkeypatch.setattr(ia, "sleep", lambda seconds: None)
    monkeypatch.setattr(ia, "QUIT_TIMEOUT_S", 3)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake.home))
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(ia.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(ia.shutil, "which", lambda name: f"C:/tools/{name}.exe")
    return fake


def running_beta(fake, *, children=()):
    app = fake.apps / "Sutra Pro Beta"
    fake.processes += [(500, 1, f'"{app / "Sutra Pro Beta.exe"}"'), (501, 500, f'"{app / "Sutra Pro Beta.exe"}" --type=renderer'),
                       (502, 500, f'"{app / "resources" / "python" / "python.exe"}" -I -B -X utf8 -m sutra_app --exit-when-stdin-closes')]
    data = fake.home / ".sutra-pro-beta"
    data.mkdir(exist_ok=True)
    (data / "app.pid").write_text("502 8782\n{}\n")
    fake.processes += [(600 + index, 502, command) for index, command in enumerate(children)]


# ================================================================ where things are

def test_on_windows_the_target_is_win_x64_and_each_app_is_a_folder(win, monkeypatch):
    assert ia.host_target() == ("win-x64", "x64")
    assert ia.bundle("beta", win.apps) == win.apps / "Sutra Pro Beta"
    assert ia.bundle("stable", win.apps) == win.apps / "Sutra Pro"
    monkeypatch.setattr(ia.platform, "machine", lambda: "ARM64")
    with pytest.raises(ia.InstallError, match="architecture"):
        ia.host_target()


def test_the_default_install_folder_on_windows_is_the_users_programs_folder(win, monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    assert ia.default_install_dir() == tmp_path / "Local" / "Programs"
    monkeypatch.setattr(sys, "platform", "darwin")
    assert ia.default_install_dir() == Path("/Applications")


def test_a_folders_facts_come_from_its_build_info_and_no_signature_is_checked(win):
    beta = make_win_app(win.apps / "Sutra Pro Beta", BETA_ID, "0.8.1", build="1a2b3c4")
    assert ia.bundle_facts(beta) == {"id": BETA_ID, "version": "0.8.1", "name": "Sutra Pro Beta", "build": "1a2b3c4"}
    assert ia.check_bundle(beta, "beta", "0.8.1")["id"] == BETA_ID
    assert not any(call[0] == "codesign" for call in win.calls)
    with pytest.raises(ia.InstallError, match="not the stable app"):
        ia.check_bundle(beta, "stable")
    assert ia.bundle_facts(win.apps / "missing") == {}


def test_the_process_table_is_read_from_powershell(win):
    win.processes = [(12, 4, r'"C:\Programs\Sutra Pro Beta\Sutra Pro Beta.exe" --type=gpu')]
    assert REAL_PROCESS_TABLE() == [(12, 4, r'"C:\Programs\Sutra Pro Beta\Sutra Pro Beta.exe" --type=gpu')]
    assert any(call[0] == "powershell.exe" and "Win32_Process" in call[-1] for call in win.calls)


def test_the_betas_processes_are_not_the_stable_apps_beside_it(win):
    stable = win.apps / "Sutra Pro"
    win.processes = [(100, 1, f'"{stable / "Sutra Pro.exe"}"'), (101, 100, f'"{stable / "resources" / "python" / "python.exe"}" -m sutra_app')]
    running_beta(win)
    assert ia.running(win.apps / "Sutra Pro Beta") == [500, 501, 502]
    assert ia.running(stable) == [100, 101]


def test_an_engine_run_of_the_betas_data_folder_is_busy_work_with_either_separator(win):
    running_beta(win)
    data = win.home / ".sutra-pro-beta"
    assert ia.busy_work(data) == []
    win.processes.append((700, 1, f"python.exe -m sutra_app.engine --run-dir {data}\\departments\\web\\runs\\j2-1"))
    assert [line.split()[0] for line in ia.busy_work(data)] == ["700"]


# ================================================================ closing, copying, opening

def test_a_working_beta_is_not_closed(win):
    running_beta(win, children=["claude -p hello"])
    with pytest.raises(ia.Busy):
        ia.quit_app(win.apps / "Sutra Pro Beta", "beta")
    assert not any(call[0] == "taskkill" for call in win.calls)


def test_an_idle_beta_is_closed_through_its_window_never_forced(win):
    running_beta(win)
    assert ia.quit_app(win.apps / "Sutra Pro Beta", "beta") is True
    closes = [call for call in win.calls if call[0] == "taskkill"]
    assert closes == [["taskkill", "/PID", "500"]], "the window's own close (WM_CLOSE): no /F, no /T"
    assert ia.running(win.apps / "Sutra Pro Beta") == []


def test_a_beta_that_does_not_close_stops_the_install(win):
    running_beta(win)
    win.close_works = False
    with pytest.raises(ia.InstallError, match="did not quit"):
        ia.quit_app(win.apps / "Sutra Pro Beta", "beta")


def test_a_folder_is_replaced_whole_and_a_failed_copy_leaves_the_old_one(win, tmp_path, monkeypatch):
    old = make_win_app(win.apps / "Sutra Pro Beta", BETA_ID, "0.8.0", payload="old")
    new = make_win_app(tmp_path / "built" / "Sutra Pro Beta", BETA_ID, "0.8.1", payload="new")
    ia.replace_bundle(new, old)
    assert (old / "Sutra Pro Beta.exe").read_text() == "new"
    assert not any(call[0] in ("ditto", "xattr") for call in win.calls)
    newer = make_win_app(tmp_path / "built2" / "Sutra Pro Beta", BETA_ID, "0.8.2", payload="newer")

    def broken(source, destination, **kwargs):
        Path(destination).mkdir(parents=True)
        raise OSError("no space left on device")

    monkeypatch.setattr(ia.shutil, "copytree", broken)
    with pytest.raises(ia.InstallError, match="no space left"):
        ia.replace_bundle(newer, old)
    assert (old / "Sutra Pro Beta.exe").read_text() == "new"
    assert sorted(p.name for p in win.apps.iterdir()) == ["Sutra Pro Beta"], "no half copy is left beside it"


def test_a_folder_is_opened_by_starting_its_exe_and_must_answer_with_its_version(win):
    beta = make_win_app(win.apps / "Sutra Pro Beta", BETA_ID, "0.8.1")
    win.served_version = "0.8.1"
    started = ia.open_and_check(beta, "beta", "0.8.1")
    assert started["port"] == 8782
    assert win.started == [beta / "Sutra Pro Beta.exe"]
    assert not any(call[0] == "open" for call in win.calls)


# ================================================================ the beta, end to end

def built_beta(win, monkeypatch, tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "pyproject.toml").write_text('[project]\nname = "sutra-pro"\nversion = "0.8.1"\n')
    monkeypatch.setattr(ia, "ROOT", tree)
    built = {}

    def build_app(**kwargs):
        built.update(kwargs)
        return make_win_app(kwargs["out"] / "Sutra Pro Beta", BETA_ID, "0.8.1", build=kwargs["build_label"], payload="beta from the tree")

    monkeypatch.setattr(ia.builder, "build_app", build_app)
    return built


def test_a_windows_beta_is_built_proved_installed_beside_the_stable_app_and_given_a_shortcut(win, monkeypatch, tmp_path):
    built = built_beta(win, monkeypatch, tmp_path)
    stable = make_win_app(win.apps / "Sutra Pro", STABLE_ID, "0.7.0", payload="stable")
    make_win_app(win.apps / "Sutra Pro Beta", BETA_ID, "0.8.0", payload="old beta")
    running_beta(win)
    win.served_version = "0.8.1"

    assert ia.install_beta(win.apps, skip_npm=True) == 0

    assert (win.apps / "Sutra Pro Beta" / "Sutra Pro Beta.exe").read_text() == "beta from the tree"
    assert (stable / "Sutra Pro.exe").read_text() == "stable", "the stable app is not touched"
    assert built["target"] == "win-x64" and built["channel"] == "beta"
    assert not any(call[0] == "bash" for call in win.calls), "no ad hoc signing on Windows"
    proof = next(call for call in win.calls if call[1:2] and call[1].endswith("prove_desktop_app.py"))
    assert "--no-team" in proof
    assert ["taskkill", "/PID", "500"] in win.calls, "the running idle beta was closed first"
    assert win.started == [win.apps / "Sutra Pro Beta" / "Sutra Pro Beta.exe"]
    shortcut = next(call[-1] for call in win.calls if call[0] == "powershell.exe" and "WScript.Shell" in call[-1])
    assert "Sutra Pro Beta.lnk" in shortcut and str(win.apps / "Sutra Pro Beta" / "Sutra Pro Beta.exe") in shortcut


def test_pull_brings_the_checkout_to_its_upstream_before_anything_is_built(win, monkeypatch, tmp_path):
    built_beta(win, monkeypatch, tmp_path)
    win.served_version = "0.8.1"
    assert ia.install_beta(win.apps, skip_npm=True, pull=True) == 0
    names = [" ".join(call[1:]) for call in win.calls if call[0] == "git"]
    fetch = next(i for i, call in enumerate(win.calls) if call[0] == "git" and "fetch" in call)
    merge = next(i for i, call in enumerate(win.calls) if call[0] == "git" and "merge" in call)
    build = next(i for i, call in enumerate(win.calls) if call[0] == "uv")
    assert fetch < merge < build, names
    assert "--ff-only" in win.calls[merge]


def test_pull_refuses_a_tree_with_changes_or_without_an_upstream_and_builds_nothing(win, monkeypatch, tmp_path):
    built = built_beta(win, monkeypatch, tmp_path)
    win.git_changes = " M sutra_app/main.py"
    with pytest.raises(ia.InstallError, match="changes"):
        ia.install_beta(win.apps, skip_npm=True, pull=True)
    win.git_changes, win.git_upstream = "", ""
    with pytest.raises(ia.InstallError, match="upstream"):
        ia.install_beta(win.apps, skip_npm=True, pull=True)
    assert not built and not any(call[0] == "uv" for call in win.calls)


def test_the_command_line_takes_pull(win, monkeypatch):
    seen = {}
    monkeypatch.setattr(ia, "install_beta", lambda install_dir, **kwargs: seen.update(kwargs, install_dir=install_dir) or 0)
    assert ia.main(["beta", "--pull", "--install-dir", str(win.apps)]) == 0
    assert seen["pull"] is True and seen["install_dir"] == win.apps


def test_a_release_is_still_installed_on_a_mac_only(win):
    with pytest.raises(ia.InstallError, match="Mac"):
        ia.install_release("sutra-pro-v0.8.1", win.apps)
    assert win.calls == []
