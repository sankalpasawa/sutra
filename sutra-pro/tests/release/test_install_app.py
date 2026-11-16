"""scripts/install_app.py (D242): the beta built from a working tree and the published release, both installed on one Mac.

Nothing here builds an app, downloads anything or touches /Applications: the commands the script runs (`ditto`, `hdiutil`, `osascript`, `open`,
`codesign`, `curl`, `uv`, `git`, `ps`) are answered by a small fake system over a temporary folder, so what is tested is the script's own decisions: which app it
replaces, what it refuses, in which order it does things, and that the other app and the owner's data are never touched.
"""
import json
import plistlib
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import install_app as ia                                                       # noqa: E402

REAL_PROCESS_TABLE = ia.process_table

POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="the apps are Mac apps; the script's own logic is what runs here, over POSIX paths")
pytestmark = POSIX_ONLY                                                        # the whole installer is a Mac one: its tests run where its paths and process table make sense
STABLE_ID, BETA_ID = "os.sutra.pro", "os.sutra.pro.beta"
SHA = "a" * 64


def make_app(path: Path, bundle_id: str, version: str, *, build: str = "", payload: str = "x") -> Path:
    """What the script reads of an app: the Info.plist, build-info.json, and a file to tell one copy from another."""
    shutil.rmtree(path, ignore_errors=True)                       # a fresh copy each time
    (path / "Contents" / "Resources").mkdir(parents=True)
    (path / "Contents" / "MacOS").mkdir(parents=True)
    (path / "Contents" / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": bundle_id, "CFBundleShortVersionString": version, "CFBundleName": path.stem}))
    (path / "Contents" / "Resources" / "build-info.json").write_text(json.dumps({"build": build}))
    (path / "Contents" / "MacOS" / "program").write_text(payload)
    return path


class FakeSystem:
    """The commands the script runs, answered over a temporary home folder, with a record of every call."""

    def __init__(self, tmp_path: Path):
        self.home = tmp_path / "home"
        self.apps = tmp_path / "Applications"
        self.apps.mkdir()
        self.home.mkdir()
        self.calls: list[list[str]] = []
        self.processes: list[tuple[int, int, str]] = []         # (pid, ppid, command)
        self.codesign_ok = True
        self.copy_ok = True
        self.release_app = None                                 # the app a mounted DMG holds
        self.served_version = None                              # what /api/health says once an app is opened
        self.checksum_ok = True
        self.uv_listing = ""
        self.tags = ""
        self.git_head = "1a2b3c4d5e6f"
        self.git_changes = ""
        self.mounts: list[str] = []
        self.downloads: list[str] = []

    # --- the seams
    def process_table(self):
        return list(self.processes)

    def run(self, args, *, timeout=None, cwd=None, env=None):
        args = [str(item) for item in args]
        self.calls.append(args)
        program = "python" if args[0] == sys.executable else Path(args[0]).name
        handler = getattr(self, f"cmd_{program.replace('-', '_')}", None)
        if handler is None:
            raise AssertionError(f"the script ran a command nobody expected: {args}")
        code, out, err = handler(args)
        return subprocess.CompletedProcess(args, code, out, err)

    def health(self, port):
        return {"ok": True, "version": self.served_version} if self.served_version else None

    # --- the commands
    def cmd_ps(self, args):
        return 0, "\n".join(f"{pid} {ppid} {command}" for pid, ppid, command in self.processes), ""

    def cmd_ditto(self, args):
        if not self.copy_ok:
            return 1, "", "no space left on device"
        shutil.copytree(args[1], args[2], symlinks=True)
        return 0, "", ""

    def cmd_xattr(self, args):
        return 0, "", ""

    def cmd_codesign(self, args):
        return (0, "", "") if self.codesign_ok else (1, "", "a sealed resource is missing or invalid")

    def cmd_osascript(self, args):
        wanted = args[-1].split('"')[1]                           # tell application id "<id>" to quit
        for pid, _ppid, command in list(self.processes):
            for app in self.apps.glob("*.app"):
                facts = ia.bundle_facts(app)
                if facts.get("id") == wanted and f"{app}/Contents/" in command:
                    self.processes.remove((pid, _ppid, command))
        return 0, "", ""

    def cmd_open(self, args):
        app = Path(args[-1])
        facts = ia.bundle_facts(app)
        channel = "beta" if facts.get("id") == BETA_ID else "stable"
        data = self.home / ia.CHANNELS[channel]["dataDirName"]
        data.mkdir(exist_ok=True)
        (data / "app.pid").write_text("4242 8781\n{}\n")
        self.processes.append((4242, 1, f"{app}/Contents/MacOS/program"))
        return 0, "", ""

    def cmd_curl(self, args):
        url, target = args[-1], Path(args[args.index("-o") + 1])
        self.downloads.append(url.rsplit("/", 1)[-1])
        name = url.rsplit("/", 1)[-1]
        if name.endswith(".sha256"):
            bare = name[: -len(".sha256")]
            target.write_text(f"{(SHA if not self.checksum_ok else self.sums[bare])}  {bare}\n")
        else:
            target.write_bytes(f"bytes of {name}".encode())
        return 0, "", ""

    @property
    def sums(self):
        import hashlib
        return {name: hashlib.sha256(f"bytes of {name}".encode()).hexdigest() for name in self.downloads}

    def cmd_hdiutil(self, args):
        if args[1] == "attach":
            mount = Path(args[args.index("-mountpoint") + 1])
            shutil.copytree(self.release_app, mount / self.release_app.name, symlinks=True)
            self.mounts.append(str(mount))
        else:
            self.mounts.remove(args[-1])
        return 0, "", ""

    def cmd_uv(self, args):
        if args[1] == "build":
            out = Path(args[args.index("--out-dir") + 1])
            (out / "sutra_pro-0.6.1-py3-none-any.whl").write_bytes(b"wheel")
            (out / "sutra_pro-0.6.1.tar.gz").write_bytes(b"sdist")
            return 0, "", ""
        if args[1:3] == ["tool", "install"]:
            self.uv_listing = "sutra-pro v" + Path(args[-1]).name.split("-")[1] + "\n- sutra-pro\n"
            return 0, "", ""
        if args[1:3] == ["tool", "list"]:
            return 0, self.uv_listing, ""
        raise AssertionError(args)

    def cmd_git(self, args):
        if "ls-remote" in args:
            return 0, self.tags, ""
        if "rev-parse" in args:
            return 0, (self.git_head[:7] if "--short=7" in args else self.git_head) + "\n", ""
        if "status" in args:
            return 0, self.git_changes, ""
        raise AssertionError(args)

    def cmd_bash(self, args):
        return 0, "", ""

    def cmd_python(self, args):
        return 0, "PROVED", ""

    cmd_python3 = cmd_python


@pytest.fixture
def system(tmp_path, monkeypatch):
    fake = FakeSystem(tmp_path)
    monkeypatch.setattr(ia, "run", fake.run)
    monkeypatch.setattr(ia, "process_table", fake.process_table)
    monkeypatch.setattr(ia, "health", fake.health)
    monkeypatch.setattr(ia, "sleep", lambda seconds: None)
    monkeypatch.setattr(ia, "QUIT_TIMEOUT_S", 3)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake.home))
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(ia.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(ia.shutil, "which", lambda name: f"/usr/bin/{name}")
    return fake


def running_stable(fake, *, children=()):
    app = fake.apps / "Sutra Pro.app"
    fake.processes += [(100, 1, f"{app}/Contents/MacOS/Sutra Pro"), (101, 100, f"{app}/Contents/Frameworks/Sutra Pro Helper"),
                       (102, 100, f"{app}/Contents/Resources/python/bin/python3 -I -B -m sutra_app --data-dir x")]
    data = fake.home / ".sutra-pro"
    data.mkdir(exist_ok=True)
    (data / "app.pid").write_text("102 8780\n{}\n")
    fake.processes += [(200 + index, 102, command) for index, command in enumerate(children)]


# ================================================================ where things are

def test_each_channel_has_its_own_app_and_its_own_data_folder(system):
    assert ia.bundle("stable", Path("/Applications")) == Path("/Applications/Sutra Pro.app")
    assert ia.bundle("beta", Path("/Applications")) == Path("/Applications/Sutra Pro Beta.app")
    assert ia.data_dir("stable") == system.home / ".sutra-pro"
    assert ia.data_dir("beta") == system.home / ".sutra-pro-beta"


def test_the_target_follows_the_mac_and_other_systems_are_refused(system, monkeypatch):
    assert ia.host_target() == ("mac-arm64", "arm64")
    monkeypatch.setattr(ia.platform, "machine", lambda: "x86_64")
    assert ia.host_target() == ("mac-x64", "x86_64")
    monkeypatch.setattr(ia.platform, "machine", lambda: "ppc")
    with pytest.raises(ia.InstallError, match="architecture"):
        ia.host_target()
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(ia.InstallError, match="Mac app"):
        ia.host_target()


def test_the_processes_of_one_app_are_not_the_processes_of_the_other(system):
    stable, beta = system.apps / "Sutra Pro.app", system.apps / "Sutra Pro Beta.app"
    system.processes = [(1, 0, f"{stable}/Contents/MacOS/Sutra Pro"), (2, 1, f"{stable}/Contents/Resources/python/bin/python3 -m sutra_app"),
                        (3, 0, f"{beta}/Contents/MacOS/Sutra Pro Beta"), (4, 0, "/usr/bin/other")]
    assert ia.running(stable) == [1, 2]
    assert ia.running(beta) == [3]


def test_ps_output_is_read_into_rows_with_spaces_in_the_command_kept(system, monkeypatch):
    system.processes = [(7, 1, "/Applications/Sutra Pro.app/Contents/MacOS/Sutra Pro --flag"), (80, 7, "x")]
    monkeypatch.setattr(ia, "process_table", REAL_PROCESS_TABLE)
    assert ia.process_table() == [(7, 1, "/Applications/Sutra Pro.app/Contents/MacOS/Sutra Pro --flag"), (80, 7, "x")]


# ================================================================ what is busy, what may be quit

def test_an_idle_server_is_not_busy_and_a_child_or_an_engine_run_is(system):
    running_stable(system)
    data = ia.data_dir("stable")
    assert ia.busy_work(data) == []
    system.processes.append((300, 102, "claude -p hello"))
    assert [line.split()[0] for line in ia.busy_work(data)] == ["300"]
    system.processes = [row for row in system.processes if row[0] != 300]
    system.processes.append((301, 1, f"python3 -m sutra_app.engine --run-dir {data}/departments/x/runs/r1"))
    assert [line.split()[0] for line in ia.busy_work(data)] == ["301"]
    # the other channel's run folder is another folder: ~/.sutra-pro-beta is not below ~/.sutra-pro
    system.processes.append((302, 1, f"python3 -m sutra_app.engine --run-dir {ia.data_dir('beta')}/departments/x/runs/r2"))
    assert 302 not in [int(line.split()[0]) for line in ia.busy_work(data)]


def test_an_app_that_is_not_running_is_not_quit(system):
    assert ia.quit_app(system.apps / "Sutra Pro.app", "stable") is False
    assert not any(call[0] == "osascript" for call in system.calls)


def test_a_working_app_is_not_quit_and_force_is_the_owners_word(system):
    running_stable(system, children=["claude -p a reply in progress"])
    make_app(system.apps / "Sutra Pro.app", STABLE_ID, "0.6.1")
    with pytest.raises(ia.Busy, match="working"):
        ia.quit_app(system.apps / "Sutra Pro.app", "stable")
    assert not any(call[0] == "osascript" for call in system.calls)
    assert ia.quit_app(system.apps / "Sutra Pro.app", "stable", force=True) is True
    assert system.calls[-1][:2] == ["osascript", "-e"] and f'id "{STABLE_ID}"' in system.calls[-1][2], "it asks the app by its bundle id, so never the other app"


def test_an_idle_app_is_quit_by_its_menu_and_one_that_does_not_quit_stops_the_install(system, monkeypatch):
    running_stable(system)
    make_app(system.apps / "Sutra Pro.app", STABLE_ID, "0.6.1")
    assert ia.quit_app(system.apps / "Sutra Pro.app", "stable") is True
    assert ia.running(system.apps / "Sutra Pro.app") == []
    running_stable(system)
    monkeypatch.setattr(system, "cmd_osascript", lambda args: (0, "", ""))               # the app ignores the request
    with pytest.raises(ia.InstallError, match="did not quit"):
        ia.quit_app(system.apps / "Sutra Pro.app", "stable")
    assert not any("kill" in call[0] for call in system.calls), "nothing is ever killed"


# ================================================================ the bundle

def test_a_bundle_must_be_the_app_of_its_channel_and_its_seal_must_hold(system):
    beta = make_app(system.apps / "Sutra Pro Beta.app", BETA_ID, "0.6.1", build="abc1234")
    assert ia.check_bundle(beta, "beta", "0.6.1")["build"] == "abc1234"
    with pytest.raises(ia.InstallError, match="not the stable app"):
        ia.check_bundle(beta, "stable")                                # a beta never goes into the stable app's place
    with pytest.raises(ia.InstallError, match="0.7.0"):
        ia.check_bundle(beta, "beta", "0.7.0")
    system.codesign_ok = False
    with pytest.raises(ia.InstallError, match="signature"):
        ia.check_bundle(beta, "beta", "0.6.1")
    assert ia.bundle_facts(system.apps / "nothing.app") == {}


def test_an_app_is_replaced_whole_and_a_failed_copy_leaves_the_old_one(system):
    old = make_app(system.apps / "Sutra Pro.app", STABLE_ID, "0.6.0", payload="old")
    new = make_app(system.apps / "from" / "Sutra Pro.app", STABLE_ID, "0.6.1", payload="new")
    system.copy_ok = False
    with pytest.raises(ia.InstallError, match="copying"):
        ia.replace_bundle(new, old)
    assert (old / "Contents" / "MacOS" / "program").read_text() == "old"
    assert [path.name for path in system.apps.iterdir() if path.name != "from"] == ["Sutra Pro.app"], "no half copy is left beside it"
    system.copy_ok = True
    ia.replace_bundle(new, old)
    assert (old / "Contents" / "MacOS" / "program").read_text() == "new"
    assert sorted(path.name for path in system.apps.iterdir()) == ["Sutra Pro.app", "from"]


def test_an_app_is_opened_through_launch_services_and_must_answer_with_its_version(system, monkeypatch):
    beta = make_app(system.apps / "Sutra Pro Beta.app", BETA_ID, "0.6.1")
    system.served_version = "0.6.1"
    started = ia.open_and_check(beta, "beta", "0.6.1")
    assert started == {"pid": 4242, "port": 8781, "health": {"ok": True, "version": "0.6.1"}}
    assert system.calls[-1][:2] == ["open", "-a"]
    system.served_version = "0.5.0"                                        # another version answers: an old server is not the new app
    monkeypatch.setattr(ia, "time", types.SimpleNamespace(monotonic=iter([0, 1, 2, 500]).__next__))
    with pytest.raises(ia.InstallError, match="did not answer"):
        ia.open_and_check(beta, "beta", "0.6.1", timeout=10)


# ================================================================ the download

def test_a_checksum_is_checked_and_a_bad_one_stops_the_install(tmp_path):
    import hashlib
    file = tmp_path / "A.dmg"
    file.write_bytes(b"data")
    good = tmp_path / "A.dmg.sha256"
    good.write_text(f"{hashlib.sha256(b'data').hexdigest()}  A.dmg\n")
    ia.verify_checksum(file, good)
    good.write_text(f"{'0' * 64}  A.dmg\n")
    with pytest.raises(ia.InstallError, match="does not match"):
        ia.verify_checksum(file, good)
    good.write_text("not a checksum\n")
    with pytest.raises(ia.InstallError, match="does not hold a SHA-256"):
        ia.verify_checksum(file, good)
    good.write_text(f"{hashlib.sha256(b'data').hexdigest()}  B.dmg\n")
    with pytest.raises(ia.InstallError, match="is for B.dmg"):
        ia.verify_checksum(file, good)


def test_the_newest_stable_tag_is_the_largest_number_not_the_last_listed(system):
    system.tags = "\n".join(f"abc\trefs/tags/{tag}" for tag in [
        "sutra-pro-v0.9.0", "sutra-pro-v0.10.0", "sutra-pro-v0.10.1-beta.2", "sutra-pro-v0.2.7", "sutra-pro-vx", "sutra-pro-v01.2.3"])
    assert ia.newest_release_tag() == "sutra-pro-v0.10.0"
    system.tags = "abc\trefs/tags/sutra-pro-v1.0.0-beta.1"
    with pytest.raises(ia.InstallError, match="no stable"):
        ia.newest_release_tag()


# ================================================================ release

def fake_release(system, version="0.6.1", bundle_id=STABLE_ID):
    system.release_app = make_app(system.apps.parent / "dmg-content" / "Sutra Pro.app", bundle_id, version, payload="released")
    system.served_version = version


@POSIX_ONLY
def test_a_release_replaces_the_stable_app_only_and_installs_the_command(system):
    fake_release(system)
    old = make_app(system.apps / "Sutra Pro.app", STABLE_ID, "0.6.0", payload="old")
    beta = make_app(system.apps / "Sutra Pro Beta.app", BETA_ID, "0.6.1", payload="beta")
    (system.home / ".sutra-pro").mkdir()
    (system.home / ".sutra-pro" / "db.sqlite3").write_text("the owner's data")
    (system.home / ".sutra-pro-beta").mkdir()
    (system.home / ".sutra-pro-beta" / "db.sqlite3").write_text("the beta's data")
    assert ia.install_release("sutra-pro-v0.6.1", system.apps) == 0
    assert (old / "Contents" / "MacOS" / "program").read_text() == "released"
    assert (beta / "Contents" / "MacOS" / "program").read_text() == "beta", "the beta is left as it was"
    assert (system.home / ".sutra-pro" / "db.sqlite3").read_text() == "the owner's data"
    assert (system.home / ".sutra-pro-beta" / "db.sqlite3").read_text() == "the beta's data"
    assert system.mounts == [], "the disk image is always detached"
    assert system.downloads == ["Sutra-Pro-arm64.dmg", "Sutra-Pro-arm64.dmg.sha256", "sutra_pro-0.6.1-py3-none-any.whl", "sutra_pro-0.6.1-py3-none-any.whl.sha256"]
    assert system.uv_listing.startswith("sutra-pro v0.6.1")
    order = [call[0] for call in system.calls if call[0] in ("curl", "hdiutil", "codesign", "ditto", "uv", "open")]
    assert order.index("curl") < order.index("hdiutil") < order.index("ditto") < order.index("uv") < order.index("open")
    assert not any(isinstance(arg, str) and arg.endswith("Sutra Pro Beta.app") for call in system.calls for arg in call if call[0] in ("ditto", "osascript"))


@POSIX_ONLY
def test_a_release_whose_checksum_is_wrong_installs_nothing(system):
    fake_release(system)
    old = make_app(system.apps / "Sutra Pro.app", STABLE_ID, "0.6.0", payload="old")
    system.checksum_ok = False
    with pytest.raises(ia.InstallError, match="does not match"):
        ia.install_release("sutra-pro-v0.6.1", system.apps)
    assert (old / "Contents" / "MacOS" / "program").read_text() == "old"
    assert not any(call[0] in ("hdiutil", "ditto") for call in system.calls)


@POSIX_ONLY
def test_a_release_whose_disk_image_holds_a_beta_is_refused_and_a_busy_app_is_not_quit(system):
    old = make_app(system.apps / "Sutra Pro.app", STABLE_ID, "0.6.0", payload="old")
    system.release_app = make_app(system.apps.parent / "dmg-content" / "Sutra Pro.app", BETA_ID, "0.6.1")
    with pytest.raises(ia.InstallError, match="not the stable app"):
        ia.install_release("sutra-pro-v0.6.1", system.apps)
    assert system.mounts == []
    fake_release(system)
    running_stable(system, children=["claude -p a reply"])
    with pytest.raises(ia.Busy):
        ia.install_release("sutra-pro-v0.6.1", system.apps)
    assert (old / "Contents" / "MacOS" / "program").read_text() == "old", "a busy app is left exactly as it was"
    assert system.mounts == []


def test_only_a_stable_tag_is_installed_as_the_app(system):
    for tag in ("sutra-pro-v0.6.1-beta.1", "v2.3.4", "sutra-pro-v1", "latest"):
        with pytest.raises(ia.InstallError, match="not a stable release tag"):
            ia.install_release(tag, system.apps)


def test_without_a_tag_the_newest_one_is_installed(system):
    system.tags = "x\trefs/tags/sutra-pro-v0.6.0\nx\trefs/tags/sutra-pro-v0.6.1"
    assert ia.install_release(None, system.apps, dry_run=True) == 0
    assert not any(call[0] == "curl" for call in system.calls)


@POSIX_ONLY
def test_the_dry_runs_touch_nothing(system, capsys):
    assert ia.install_release("sutra-pro-v0.6.1", system.apps, dry_run=True) == 0
    assert ia.install_beta(system.apps, dry_run=True) == 0
    out = capsys.readouterr().out
    assert "dry run" in out and "Sutra-Pro-arm64.dmg" in out and "Sutra Pro Beta.app" in out
    assert [call[0] for call in system.calls] == ["git", "git"], "only the build label was read"
    assert list(system.apps.iterdir()) == []


# ================================================================ beta

@POSIX_ONLY
def test_a_beta_is_built_from_the_tree_proved_and_installed_beside_the_stable_app(system, tmp_path, monkeypatch):
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "pyproject.toml").write_text('[project]\nname = "sutra-pro"\nversion = "0.6.1"\n')
    monkeypatch.setattr(ia, "ROOT", tree)
    built = {}

    def build_app(**kwargs):
        built.update(kwargs)
        return make_app(kwargs["out"] / "Sutra Pro Beta.app", BETA_ID, "0.6.1", build=kwargs["build_label"], payload="beta from the tree")

    monkeypatch.setattr(ia.builder, "build_app", build_app)
    system.git_changes = " M pyproject.toml"
    stable = make_app(system.apps / "Sutra Pro.app", STABLE_ID, "0.6.1", payload="stable")
    old_beta = make_app(system.apps / "Sutra Pro Beta.app", BETA_ID, "0.6.0", payload="old beta")
    (system.home / ".sutra-pro").mkdir()
    (system.home / ".sutra-pro" / "db.sqlite3").write_text("the owner's data")
    system.served_version = "0.6.1"

    assert ia.install_beta(system.apps, skip_npm=True) == 0

    assert (old_beta / "Contents" / "MacOS" / "program").read_text() == "beta from the tree"
    assert (stable / "Contents" / "MacOS" / "program").read_text() == "stable", "the stable app is not touched"
    assert (system.home / ".sutra-pro" / "db.sqlite3").read_text() == "the owner's data"
    assert built["channel"] == "beta" and built["target"] == "mac-arm64" and built["build_label"] == "1a2b3c4+changes" and built["skip_npm"] is True
    assert built["wheel"].name == "sutra_pro-0.6.1-py3-none-any.whl", "the wheel, not the sdist that was built on the way"
    proof = next(call for call in system.calls if call[1:2] and call[1].endswith("prove_desktop_app.py"))
    assert "--version" in proof and "0.6.1" in proof and "--no-team" in proof
    assert any(call[0] == "bash" and call[1].endswith("sign_desktop_app.sh") for call in system.calls)
    assert any(call[0] == "open" and call[-1].endswith("Sutra Pro Beta.app") for call in system.calls)
    assert not any(call[0] == "open" and call[-1].endswith("/Sutra Pro.app") for call in system.calls), "the stable app is not opened by a beta install"
    assert (system.home / ".sutra-pro-beta" / "app.pid").is_file()


@POSIX_ONLY
def test_a_beta_that_does_not_start_is_not_installed(system, tmp_path, monkeypatch):
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "pyproject.toml").write_text('[project]\nversion = "0.6.1"\n')
    monkeypatch.setattr(ia, "ROOT", tree)
    monkeypatch.setattr(ia.builder, "build_app", lambda **kw: make_app(kw["out"] / "Sutra Pro Beta.app", BETA_ID, "0.6.1"))
    monkeypatch.setattr(system, "cmd_python", lambda args: (1, "", "the window did not draw"))
    monkeypatch.setattr(system, "cmd_python3", lambda args: (1, "", "the window did not draw"))
    old_beta = make_app(system.apps / "Sutra Pro Beta.app", BETA_ID, "0.6.0", payload="old beta")
    with pytest.raises(ia.InstallError, match="does not start"):
        ia.install_beta(system.apps, skip_npm=True)
    assert (old_beta / "Contents" / "MacOS" / "program").read_text() == "old beta"


@POSIX_ONLY
def test_a_beta_build_that_fails_says_why_and_a_busy_beta_is_not_quit(system, tmp_path, monkeypatch):
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "pyproject.toml").write_text('[project]\nversion = "0.6.1"\n')
    monkeypatch.setattr(ia, "ROOT", tree)

    def broken(**kwargs):
        raise ia.builder.BuildError("npm ci failed (exit 1): no network")

    monkeypatch.setattr(ia.builder, "build_app", broken)
    with pytest.raises(ia.InstallError, match="npm ci failed"):
        ia.install_beta(system.apps, skip_npm=True)
    monkeypatch.setattr(ia.builder, "build_app", lambda **kw: make_app(kw["out"] / "Sutra Pro Beta.app", BETA_ID, "0.6.1"))
    beta = system.apps / "Sutra Pro Beta.app"
    make_app(beta, BETA_ID, "0.6.0", payload="old beta")
    data = system.home / ".sutra-pro-beta"
    data.mkdir()
    (data / "app.pid").write_text("500 8781\n")
    system.processes = [(500, 1, f"{beta}/Contents/Resources/python/bin/python3 -m sutra_app"), (501, 500, "codex exec something")]
    with pytest.raises(ia.Busy):
        ia.install_beta(system.apps, skip_npm=True)
    assert (beta / "Contents" / "MacOS" / "program").read_text() == "old beta"


# ================================================================ status and the command line

@POSIX_ONLY
def test_status_says_what_is_installed_and_running(system, capsys):
    make_app(system.apps / "Sutra Pro.app", STABLE_ID, "0.6.1")
    make_app(system.apps / "Sutra Pro Beta.app", BETA_ID, "0.6.1", build="abc1234")
    running_stable(system)
    system.served_version = "0.6.1"
    system.uv_listing = "sutra-pro v0.6.1\n- sutra-pro\n"
    assert ia.status(system.apps) == 0
    out = capsys.readouterr().out
    assert "Sutra Pro: 0.6.1" in out and "running, server on port 8780" in out
    assert "Sutra Pro Beta: 0.6.1, built from abc1234" in out and "not running" in out
    assert "~/.sutra-pro-beta" in out and "the sutra-pro command: v0.6.1" in out


def test_the_exit_status_says_busy_or_failed_or_done(system, capsys, monkeypatch):
    monkeypatch.setattr(ia, "status", lambda install_dir: 0)
    assert ia.main(["status"]) == 0
    monkeypatch.setattr(ia, "status", lambda install_dir: (_ for _ in ()).throw(ia.Busy("the app is working")))
    assert ia.main(["status"]) == 3
    monkeypatch.setattr(ia, "status", lambda install_dir: (_ for _ in ()).throw(ia.InstallError("it broke")))
    assert ia.main(["status"]) == 1
    assert "error: it broke" in capsys.readouterr().err
    with pytest.raises(SystemExit) as stop:
        ia.main(["nonsense"])
    assert stop.value.code == 2


def test_every_command_takes_the_install_folder_after_its_name(system, monkeypatch):
    seen = []
    monkeypatch.setattr(ia, "install_beta", lambda install_dir, **kw: seen.append(("beta", install_dir, kw)) or 0)
    monkeypatch.setattr(ia, "install_release", lambda tag, install_dir, **kw: seen.append(("release", tag, install_dir, kw)) or 0)
    assert ia.main(["beta", "--install-dir", "/x", "--no-launch", "--no-proof", "--dry-run"]) == 0
    assert ia.main(["release", "sutra-pro-v1.2.3", "--install-dir", "/y", "--no-cli", "--force"]) == 0
    assert seen[0][:2] == ("beta", Path("/x")) and seen[0][2]["launch"] is False and seen[0][2]["proof"] is False and seen[0][2]["dry_run"] is True
    assert seen[1][:3] == ("release", "sutra-pro-v1.2.3", Path("/y")) and seen[1][3]["cli"] is False and seen[1][3]["force"] is True
