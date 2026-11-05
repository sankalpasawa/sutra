"""The INSTALLED app (GAP-INSTALL, G17): the wheel installed with `uv tool` into a temporary tool folder, run from there.

Two groups. The first checks the two shell scripts (`scripts/install_local.sh`, `scripts/uninstall_local.sh`) without installing
anything: syntax, `--dry-run`, usage errors and the missing-uv branch. The second is marked `slow` (SUTRA_SLOW=1): it builds the wheel
from a copy of the package, installs it into a temporary UV_TOOL_DIR / UV_TOOL_BIN_DIR with a throw-away HOME and a cleaned
environment, and runs the installed copy: `--help`, `doctor --offline`, the data files it must find (function_specs.json, the seed
library, the page files, the default `<data>/.env`), and an offline server that serves health and the Home page, takes a chat
message and a team with a task, and stops with `sutra-pro stop`. The scripts are run for real too, against the same temporary folders.
Everything skips, with the reason printed, where uv is missing or cannot install without the network.
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
INSTALL = REPO / "scripts" / "install_local.sh"
UNINSTALL = REPO / "scripts" / "uninstall_local.sh"
_spec = importlib.util.spec_from_file_location("check_wheel", REPO / "scripts" / "check_wheel.py")
cw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cw)
VERSION = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["version"]
HAVE_UV = shutil.which("uv") is not None
needs_uv = pytest.mark.skipif(not HAVE_UV, reason="uv is not installed: nothing can be built or installed here")


def sh(script: Path, *args: str, env: dict | None = None, cwd: Path | None = None, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(["/bin/sh", str(script), *args], capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)


def clean_env(home: Path, tool_dir: Path | None = None, bin_dir: Path | None = None, **extra: str) -> dict:
    """The owner's shell with nothing of this project in it: no SUTRA_*, J2_*, STUDIO_*, PYTHON* or virtualenv; HOME is a temp folder."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("SUTRA_", "J2_", "STUDIO_", "PYTHON", "UV_", "VIRTUAL_ENV"))}
    env["HOME"] = str(home)
    env["TMPDIR"] = "/tmp"
    if tool_dir is not None:
        env["UV_TOOL_DIR"] = str(tool_dir)
        env["UV_TOOL_BIN_DIR"] = str(bin_dir)
    env.update(extra)
    return env


# ======================================================== the scripts, without installing anything ==========================

@pytest.mark.parametrize("script", [INSTALL, UNINSTALL], ids=lambda p: p.name)
def test_the_scripts_are_valid_shell(script):
    proc = subprocess.run(["/bin/sh", "-n", str(script)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_install_dry_run_lists_every_step_and_changes_nothing(tmp_path):
    dist = tmp_path / "dist"
    proc = sh(INSTALL, "--dry-run", env=clean_env(tmp_path / "home", SUTRA_DIST_DIR=str(dist)), cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    for step in ("uv build --wheel", "check_wheel.py", "uv tool install --reinstall", "sutra-pro --help", "sutra-pro doctor --offline",
                 "/api/health", "chat message", "sutra-pro stop", "within 20 s", f"{tmp_path / 'home'}/.sutra-pro"):
        assert step in proc.stdout, step
    assert not dist.exists() and list(tmp_path.iterdir()) == [], "a dry run writes nothing"


def test_install_dry_run_works_without_uv_and_says_so(tmp_path):
    bare = tmp_path / "bare"
    bare.mkdir()
    for tool in ("dirname", "sed", "cat"):
        (bare / tool).symlink_to(shutil.which(tool))
    proc = sh(INSTALL, "--dry-run", env=clean_env(tmp_path / "home", PATH=str(bare)))
    assert proc.returncode == 0 and "'uv' is not installed here" in proc.stdout


def test_install_without_uv_fails_with_a_message(tmp_path):
    bare = tmp_path / "bare"
    bare.mkdir()
    (bare / "dirname").symlink_to(shutil.which("dirname"))
    proc = sh(INSTALL, env=clean_env(tmp_path / "home", SUTRA_DIST_DIR=str(tmp_path / "dist"), PATH=str(bare)))
    assert proc.returncode == 1 and "FAILED: 'uv' is not installed" in proc.stderr
    assert not (tmp_path / "dist").exists()


def test_install_help_prints_the_header_and_an_unknown_flag_is_a_usage_error(tmp_path):
    helped = sh(INSTALL, "--help", env=clean_env(tmp_path))
    assert helped.returncode == 0 and "uv tool install" in helped.stdout and "set -eu" not in helped.stdout
    bad = sh(INSTALL, "--nope", env=clean_env(tmp_path))
    assert bad.returncode == 2 and "unknown argument '--nope'" in bad.stderr and bad.stdout == ""


def test_uninstall_dry_run_names_the_command_and_leaves_the_data(tmp_path):
    proc = sh(UNINSTALL, "--dry-run", env=clean_env(tmp_path / "home"), cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert "uv tool uninstall sutra-pro" in proc.stdout and f"{tmp_path / 'home'}/.sutra-pro is left in place" in proc.stdout
    assert list(tmp_path.iterdir()) == []


def test_uninstall_usage_error_and_missing_uv(tmp_path):
    bad = sh(UNINSTALL, "--nope", env=clean_env(tmp_path))
    assert bad.returncode == 2 and "unknown argument '--nope'" in bad.stderr
    bare = tmp_path / "bare"
    bare.mkdir()
    (bare / "dirname").symlink_to(shutil.which("dirname"))
    none = sh(UNINSTALL, env=clean_env(tmp_path / "home", PATH=str(bare)))
    assert none.returncode == 1 and "FAILED: 'uv' is not installed" in none.stderr


@needs_uv
def test_uninstall_when_nothing_is_installed_says_so_and_still_names_the_data(tmp_path):
    home = tmp_path / "home"
    proc = sh(UNINSTALL, env=clean_env(home, tmp_path / "tools", tmp_path / "bin"))
    assert proc.returncode == 0, proc.stderr
    assert "not installed" in proc.stdout and f"left in place: {home}/.sutra-pro" in proc.stdout


def test_install_stops_before_installing_when_the_wheel_check_finds_a_problem(tmp_path):
    """The build is replaced by one that makes an empty wheel: check_wheel.py must fail it and `uv tool install` must never run."""
    import zipfile
    home, fake = tmp_path / "home", tmp_path / "fake"
    fake.mkdir()
    with zipfile.ZipFile(fake / "empty.whl", "w"):
        pass
    (fake / "uv").write_text(
        "#!/bin/sh\n"
        f'echo "$@" >> "{fake}/calls.log"\n'
        f'if [ "$1" = build ]; then mkdir -p "$4"; cp "{fake}/empty.whl" "$4/sutra_pro-0.0.1-py3-none-any.whl"; exit 0; fi\n'
        "exit 9\n")
    (fake / "uv").chmod(0o755)
    env = clean_env(home, PATH=f"{fake}:{os.environ['PATH']}", SUTRA_DIST_DIR=str(tmp_path / "dist"))
    proc = sh(INSTALL, env=env, cwd=tmp_path)
    assert proc.returncode == 1 and "FAILED: check_wheel.py found a problem in the wheel" in proc.stderr
    calls = (fake / "calls.log").read_text().splitlines()
    assert calls[0].startswith("build --wheel") and not [c for c in calls if c.startswith("tool")]


# ======================================================== the installed copy (slow) =========================================

def uv_tool_install(wheel: Path, env: dict) -> None:
    """`uv tool install --reinstall <wheel>`: from uv's cache when it can, else through the network; skips where neither works."""
    uv = shutil.which("uv")
    last = None
    for flags in (["--offline"], []):
        last = subprocess.run([uv, "tool", "install", *flags, "--reinstall", str(wheel)], capture_output=True, text=True, timeout=600, env=env)
        if last.returncode == 0:
            return
    pytest.skip("uv cannot install the wheel's dependencies here (not in its cache, no network): " + last.stderr.strip()[-300:])


@pytest.fixture(scope="module")
def wheel(tmp_path_factory) -> Path:
    """The wheel `uv build --wheel` makes from a copy of the package (so no build/ folder lands in the checkout), checked first."""
    if not HAVE_UV:
        pytest.skip("uv is not installed: no wheel can be built here")
    tree = tmp_path_factory.mktemp("tree")
    shutil.copytree(REPO / "sutra_app", tree / "sutra_app", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy(REPO / "pyproject.toml", tree / "pyproject.toml")
    out = tmp_path_factory.mktemp("dist")
    proc = subprocess.run(["uv", "build", "--wheel", "--out-dir", str(out), str(tree)], capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        pytest.skip("uv cannot build the wheel here (build requirements are not available): " + proc.stderr.strip()[-300:])
    [built] = list(out.glob("sutra_pro-*.whl"))
    assert cw.check_wheel(built, tree) == []
    return built


class Installed:
    def __init__(self, root: Path, wheel: Path) -> None:
        self.home = root / "home"
        self.home.mkdir()
        self.tools, self.bin = root / "tools", root / "bin"
        self.env = clean_env(self.home, self.tools, self.bin)
        uv_tool_install(wheel, self.env)
        self.command = self.bin / "sutra-pro"
        self.python = self.tools / "sutra-pro" / "bin" / "python"

    def run(self, *args: str, cwd: Path, **extra: str) -> subprocess.CompletedProcess:
        return subprocess.run([str(self.command), *args], capture_output=True, text=True, timeout=120, cwd=cwd, env={**self.env, **extra})

    def inspect(self, code: str, cwd: Path, **extra: str) -> dict:
        """Run `code` (it prints one JSON document) in the installed copy's own interpreter, isolated (-I: no cwd, no PYTHON* variables)."""
        proc = subprocess.run([str(self.python), "-I", "-c", code], capture_output=True, text=True, timeout=120, cwd=cwd, env={**self.env, **extra})
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout)


@pytest.fixture(scope="module")
def installed(wheel, tmp_path_factory) -> Installed:
    return Installed(tmp_path_factory.mktemp("installed"), wheel)


@pytest.mark.slow
def test_the_installed_command_answers_help_and_doctor_offline(installed, tmp_path):
    helped = installed.run("--help", cwd=tmp_path)
    assert helped.returncode == 0 and helped.stdout.startswith("usage: sutra-pro")
    data = tmp_path / "data"
    doctor = installed.run("doctor", "--offline", cwd=tmp_path, SUTRA_DATA_DIR=str(data))
    assert doctor.returncode == 0, doctor.stdout + doctor.stderr
    assert re.search(r"\d+ ok, 0 warning\(s\), 0 failed", doctor.stdout)
    assert "Free space" in doctor.stdout and "Template library" in doctor.stdout


INSPECT = """
import json, os
from pathlib import Path
import sutra_app
from sutra_app.config import default_data_dir, default_env_file, project_root
from sutra_app.library.node import DEFAULT_SPECS_PATH, load_function_specs
from sutra_app.ops.doctor import seed_dir
from sutra_app.ui.routes import PAGES_DIR, STATIC_DIR
from sutra_app.connectors import policy
import sutra_app.orchestrator.agent.agent as agent
print(json.dumps({
    "package": sutra_app.__file__,
    "specs_file": str(DEFAULT_SPECS_PATH), "specs_file_exists": DEFAULT_SPECS_PATH.is_file(),
    "functions": sorted(load_function_specs().specs),
    "seed_dir": str(seed_dir()), "seed_index": (seed_dir() / "index.json").is_file(),
    "seed_templates": len(json.loads((seed_dir() / "index.json").read_text())["templates"]),
    "pages": sorted(p.name for p in PAGES_DIR.iterdir()), "static": STATIC_DIR.is_dir(),
    "project_root": str(project_root()), "has_pyproject": (project_root() / "pyproject.toml").exists(),
    "data_dir": str(default_data_dir()), "env_file": str(default_env_file()),
    "agent_templates": sorted(p.name for p in (Path(agent.__file__).parent / "templates").glob("*.md")),
    "policy": (Path(policy.__file__).parent / "policy.default.json").is_file(),
}))
"""


@pytest.mark.slow
def test_the_installed_copy_finds_its_specs_seed_library_pages_and_the_default_env_file(installed, tmp_path):
    seen = installed.inspect(INSPECT, tmp_path)
    site = installed.tools.resolve()
    assert Path(seen["package"]).resolve().is_relative_to(site), "the code under test is the installed copy, not the checkout"
    assert seen["specs_file_exists"] and seen["functions"] == ["adaptation", "audit", "coordination", "identity", "priority"]
    assert seen["seed_index"] and seen["seed_templates"] >= 4 and Path(seen["seed_dir"]).resolve().is_relative_to(site)
    assert {"home.html", "console.html", "j2_ui.html", "j2_ui_render.js", "j2_graph_layout.js"} <= set(seen["pages"]) and seen["static"]
    assert seen["agent_templates"] and seen["policy"]
    # an installed package sits in site-packages: no pyproject beside it, so the data and the .env live in the home folder (D88, D95)
    assert seen["has_pyproject"] is False
    home = installed.home.resolve()
    assert Path(seen["data_dir"]).resolve() == home / ".sutra-pro" and Path(seen["env_file"]).resolve() == home / ".sutra-pro" / ".env"


@pytest.mark.slow
def test_with_a_data_folder_named_the_installed_env_file_is_inside_it(installed, tmp_path):
    data = tmp_path / "data"
    seen = installed.inspect(INSPECT, tmp_path, SUTRA_DATA_DIR=str(data))
    assert Path(seen["data_dir"]) == data and Path(seen["env_file"]) == data / ".env"
    shown = installed.run("config", "show", cwd=tmp_path, SUTRA_DATA_DIR=str(data))
    assert shown.returncode == 0 and f"env file = {data}/.env" in shown.stdout


class Running:
    """The installed server as a child process: its output read by a thread, a few token-aware HTTP helpers."""

    def __init__(self, installed: Installed, data: Path, cwd: Path) -> None:
        self.installed, self.data, self.cwd = installed, data, cwd
        self.env = {**installed.env, "SUTRA_DATA_DIR": str(data), "SUTRA_HEARTBEAT_S": "0.5"}
        self.lines: list[str] = []
        self.proc = subprocess.Popen([str(installed.command), "--offline", "--no-browser", "--port", "0"], cwd=cwd, env=self.env,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
        threading.Thread(target=self._read, daemon=True).start()
        self.base = self._wait_for_url()
        self.token = ""

    def _read(self) -> None:
        for line in self.proc.stdout:
            self.lines.append(line.rstrip())

    def _wait_for_url(self) -> str:
        end = time.time() + 20
        while time.time() < end:
            for line in self.lines:
                found = re.search(r"running at (http://127\.0\.0\.1:\d+)/", line)
                if found:
                    return found.group(1)
            if self.proc.poll() is not None:
                pytest.fail("the installed server exited early:\n" + "\n".join(self.lines))
            time.sleep(0.05)
        pytest.fail("the installed server did not announce its address within 20 s:\n" + "\n".join(self.lines))

    def request(self, method: str, path: str, body: dict | None = None, token: bool = True):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if token and self.token:
            req.add_header("X-Sutra-Token", self.token)
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                return response.status, response.read().decode()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode()

    def json(self, path: str):
        status, text = self.request("GET", path)
        assert status == 200, text
        return json.loads(text)

    def until(self, what: str, done, seconds: float = 30):
        end = time.time() + seconds
        while time.time() < end:
            value = done()
            if value:
                return value
            time.sleep(0.1)
        pytest.fail(f"timed out waiting for {what}")


def engine_pids(data: Path) -> list[int]:
    out = subprocess.run(["ps", "-A", "-o", "pid=,command="], capture_output=True, text=True).stdout
    return [int(line.split(None, 1)[0]) for line in out.splitlines() if f"--run-dir {data}" in line]


def add_department_payload(revision: int) -> dict:
    from sutra_app.library.org_chart import AddOp, ChartChange, NewNode      # the owner's hand-made chart change (no model)
    node = NewNode(ref="$web", kind="department", name="Web", purpose="Websites", parent="root")
    change = ChartChange(kind="add", reason="add Web", reuses=[], ops=[AddOp(node=node)], id="chg-0002", task_id="req-1", base_revision=revision, ts=1)
    return change.model_dump(mode="json")


@pytest.mark.slow
def test_the_installed_server_serves_chats_runs_a_team_and_stops_with_the_stop_command(installed, tmp_path):
    data = tmp_path / "data"
    server = Running(installed, data, tmp_path)
    try:
        server.until("/api/health", lambda: _health_ok(server))
        health = server.json("/api/health")
        assert health["ok"] is True and set(health["connectors"]) == {"stub"}
        status, page = server.request("GET", "/", token=False)
        boot = json.loads(re.search(r'<script type="application/json" id="sutra-boot">(.*?)</script>', page, re.S).group(1))
        assert status == 200 and boot["page"] == "home" and len(boot["token"]) >= 16
        server.token = boot["token"]
        # one chat message, and the same without the token is refused
        assert server.request("POST", "/api/chats/cs_org/messages", {"text": "hi"}, token=False)[0] == 401
        status, text = server.request("POST", "/api/chats/cs_org/messages", {"text": "hello from the installed copy"})
        assert status == 202, text
        message_id = json.loads(text)["message_id"]
        server.until("the chat turn", lambda: next((m for m in server.json("/api/chats/cs_org/messages")["messages"]
                                                    if m["id"] == message_id and m["state"] != "pending"), None))
        # a team with a task: the engine process of the INSTALLED copy starts and seeds the template library into the data folder
        revision = server.json("/api/chart")["version"]
        assert server.request("POST", "/api/chart/changes", add_department_payload(revision))[0] == 200
        task = json.loads(server.request("POST", "/api/tasks", {"dept_id": "web", "text": "a website for my cafe"})[1])["id"]
        server.until("the team to ask its question", lambda: server.json(f"/api/tasks/{task}")["status"] == "waiting_user", 60)
        pids = engine_pids(data)
        assert pids and server.proc.pid not in pids
        seeded = json.loads((data / "library" / "index.json").read_text())["templates"]
        seed = installed.inspect(INSPECT, tmp_path)
        assert len(seeded) == seed["seed_templates"]
        status_run = installed.run("status", cwd=tmp_path, SUTRA_DATA_DIR=str(data))
        assert status_run.returncode == 0 and f"version {VERSION}" in status_run.stdout and f"data folder: {data}" in status_run.stdout
        # stop with the command, as the owner would
        stopped = installed.run("stop", cwd=tmp_path, SUTRA_DATA_DIR=str(data))
        assert stopped.returncode == 0, stopped.stdout + stopped.stderr
        assert server.proc.wait(timeout=20) is not None
        assert engine_pids(data) == []
        assert installed.run("status", cwd=tmp_path, SUTRA_DATA_DIR=str(data)).returncode == 1
        log = (data / "logs" / "server.log").read_text()
        assert "Traceback" not in log and server.token not in log
        assert (data / "db.sqlite3").is_file()
    finally:
        if server.proc.poll() is None:
            os.killpg(server.proc.pid, 9)
            server.proc.wait()
        server.proc.stdout.close()


def _health_ok(server: Running) -> bool:
    try:
        return bool(server.json("/api/health")["ok"])
    except (OSError, AssertionError, ValueError):
        return False


@pytest.mark.slow
@needs_uv
def test_install_local_builds_checks_installs_and_verifies_the_installed_command(tmp_path):
    home, dist = tmp_path / "home", tmp_path / "dist"
    home.mkdir()
    (tmp_path / "tmp").mkdir()
    dist.mkdir()
    (dist / "sutra_pro-0.0.1-py3-none-any.whl").write_text("a stale wheel from an earlier build")
    # SUTRA_CONNECTOR is an invalid value here: the script must not let the owner's shell settings leak into the check
    env = clean_env(home, tmp_path / "tools", tmp_path / "bin", SUTRA_DIST_DIR=str(dist), TMPDIR=str(tmp_path / "tmp"), SUTRA_CONNECTOR="nonsense")
    had_build = (REPO / "build").exists()
    proc = sh(INSTALL, env=env, cwd=tmp_path)
    if proc.returncode != 0 and "uv tool install" in proc.stderr and re.search(r"network|offline|resolve|download", proc.stderr, re.I):
        pytest.skip("uv cannot install the dependencies here: " + proc.stderr.strip()[-300:])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = proc.stdout
    for step in ("verify: sutra-pro --help", "verify: sutra-pro doctor --offline", "verify: offline start", "verify: it answers on http://127.0.0.1:",
                 "one chat message accepted", "verify: sutra-pro stop"):
        assert step in out, step
    assert f"OK: sutra-pro {VERSION} is installed at {tmp_path / 'bin' / 'sutra-pro'}" in out
    assert f"your data folder is {home}/.sutra-pro" in out
    assert (tmp_path / "bin" / "sutra-pro").exists() and [w.name for w in dist.glob("*.whl")] == [f"sutra_pro-{VERSION}-py3-none-any.whl"]
    assert not (home / ".sutra-pro").exists(), "the check runs on a throw-away data folder and leaves the real one alone"
    assert (REPO / "build").exists() == had_build, "the build leaves no scratch folder in the checkout"
    assert not list((tmp_path / "tmp").glob("sutra-install.*")), "the throw-away data folder and the server log are removed"
    assert str(tmp_path) not in subprocess.run(["ps", "-A", "-o", "command="], capture_output=True, text=True).stdout, "no server is left running"


@pytest.mark.slow
def test_install_local_fails_loudly_when_the_installed_server_never_answers(wheel, tmp_path):
    """The build is replaced by the finished wheel and the installed command by one that starts but never answers: the script must say
    so after the wait, show the server's output, exit 1, and leave nothing running."""
    home, bin_dir, fake = tmp_path / "home", tmp_path / "bin", tmp_path / "fake"
    for folder in (home, bin_dir, fake):
        folder.mkdir()
    env = clean_env(home, tmp_path / "tools", bin_dir, SUTRA_DIST_DIR=str(tmp_path / "dist"), SUTRA_INSTALL_START_WAIT="3")
    (fake / "uv").write_text(
        "#!/bin/sh\n"
        f'echo "$@" >> "{fake}/calls.log"\n'
        f'if [ "$1" = build ]; then mkdir -p "$4"; cp "{wheel}" "$4/"; exit 0; fi\n'
        f'if [ "$1" = tool ] && [ "$2" = install ]; then cp "{fake}/sutra-pro" "{bin_dir}/sutra-pro"; exit 0; fi\n'
        f'exec "{shutil.which("uv")}" "$@"\n')
    (fake / "sutra-pro").write_text(
        '#!/bin/sh\ncase "$1" in --help) echo "usage: sutra-pro";; doctor | stop) exit 0;; *) echo "starting, never ready"; exec sleep 31;; esac\n')
    for name in ("uv", "sutra-pro"):
        (fake / name).chmod(0o755)
    env["PATH"] = f"{fake}:{env['PATH']}"
    started = time.time()
    proc = sh(INSTALL, env=env, cwd=tmp_path)
    assert proc.returncode == 1 and "FAILED: the server did not answer /api/health within 3 s" in proc.stderr
    assert "last lines of the server's output" in proc.stderr and "starting, never ready" in proc.stderr
    assert time.time() - started < 30
    calls = (fake / "calls.log").read_text().splitlines()
    assert calls[0] == f"build --wheel --out-dir {tmp_path / 'dist'} {REPO}"
    assert f"tool install --reinstall {tmp_path / 'dist' / wheel.name}" in calls
    time.sleep(0.5)
    assert "sleep 31" not in subprocess.run(["ps", "-A", "-o", "command="], capture_output=True, text=True).stdout


@pytest.mark.slow
def test_uninstall_local_removes_the_command_and_leaves_the_data_folder(wheel, tmp_path):
    home = tmp_path / "home"
    (home / ".sutra-pro").mkdir(parents=True)
    (home / ".sutra-pro" / "marker.txt").write_text("mine")
    env = clean_env(home, tmp_path / "tools", tmp_path / "bin")
    uv_tool_install(wheel, env)
    assert (tmp_path / "bin" / "sutra-pro").exists()
    proc = sh(UNINSTALL, env=env, cwd=tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "sutra-pro was uninstalled" in proc.stdout and f"left in place: {home}/.sutra-pro" in proc.stdout
    assert not (tmp_path / "bin" / "sutra-pro").exists()
    assert (home / ".sutra-pro" / "marker.txt").read_text() == "mine"
    again = sh(UNINSTALL, env=env, cwd=tmp_path)
    assert again.returncode == 0 and "not installed" in again.stdout
