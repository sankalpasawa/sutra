"""Where a department's and a run's files live, plus two small process helpers (engine design 3.3, 4.7 step 2, section 5).

    <data>/engine.json                          optional EngineSettings defaults for every department
    <data>/library/                             the global template library (J2_LIBRARY_DIR)
    <data>/agents/j2/                           optional role-file overrides (J2_AGENTS_DIR)
    <data>/departments/<dept>/engine.json       optional overrides for one department
    <data>/departments/<dept>/page.json         the start page's output choice and reset marker
    <data>/departments/<dept>/memory/           lessons.jsonl, playbooks.jsonl (J2_MEMORY_FILE, J2_PLAYBOOK_FILE)
    <data>/departments/<dept>/runs/<run id>/    J2's run folder + task.json, inbox.jsonl, events.jsonl, trace.jsonl, ...

`DataPaths` only computes paths; it creates nothing. The orchestrator makes a run's folder, the engine never does.
"""
import os
from collections.abc import MutableMapping
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .spec import DEPT_ID_RE, is_dept_id, is_run_id

__all__ = ["DataPaths", "RunDirError", "SMTP_VARS", "load_env_file", "default_env_file", "default_data_dir", "project_root", "pid_alive"]

SMTP_VARS = ("J2_SMTP_HOST", "J2_SMTP_PORT", "J2_SMTP_USER", "J2_SMTP_PASSWORD", "J2_SMTP_FROM")   # j2_send.py:94


class RunDirError(ValueError):
    """`--run-dir` is not a run folder the engine may use. The message says why, in words fit for 'could not start: ...'."""


@dataclass(frozen=True)
class DataPaths:
    """The paths of one department, and of one of its runs when `run_id` is set."""

    data_dir: Path
    dept_id: str
    run_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not is_dept_id(self.dept_id):
            raise ValueError(f"a department id must match {DEPT_ID_RE}, not {str(self.dept_id)[:60]!r}")
        if self.run_id is not None and not is_run_id(self.run_id):
            raise ValueError(f"a run id looks like j2-..., not {str(self.run_id)[:60]!r}")
        object.__setattr__(self, "data_dir", Path(os.path.abspath(self.data_dir)))

    @classmethod
    def for_dept(cls, data_dir, dept_id: str, run_id: Optional[str] = None) -> "DataPaths":
        return cls(Path(data_dir), dept_id, run_id)

    @classmethod
    def from_run_dir(cls, run_dir) -> "DataPaths":
        """The paths for an existing run folder `<data>/departments/<dept>/runs/<run id>` (`--run-dir`). Nothing is created:
        a folder that is missing, is a link, or sits anywhere else is a `RunDirError`."""
        path = Path(os.path.abspath(os.fspath(run_dir)))
        if os.path.islink(path):
            raise RunDirError(f"the run directory is a symbolic link: {path}")
        if not path.is_dir():
            raise RunDirError(f"the run directory does not exist: {path}")
        runs, dept, departments = path.parent, path.parent.parent, path.parent.parent.parent
        if runs.name != "runs" or departments.name != "departments":
            raise RunDirError(f"the run directory is not <data>/departments/<department>/runs/<run id>: {path}")
        if not is_dept_id(dept.name):
            raise RunDirError(f"the department folder name is not a department id: {dept.name[:60]!r}")
        if not is_run_id(path.name):
            raise RunDirError(f"the run folder name is not a run id: {path.name[:60]!r}")
        return cls(departments.parent, dept.name, path.name)

    # ---- the department
    @property
    def dept_dir(self) -> Path:
        return self.data_dir / "departments" / self.dept_id

    @property
    def runs_dir(self) -> Path:
        return self.dept_dir / "runs"

    @property
    def memory_dir(self) -> Path:
        return self.dept_dir / "memory"

    @property
    def lessons_file(self) -> Path:
        return self.memory_dir / "lessons.jsonl"

    @property
    def playbooks_file(self) -> Path:
        return self.memory_dir / "playbooks.jsonl"

    @property
    def dept_engine_json(self) -> Path:
        return self.dept_dir / "engine.json"

    @property
    def page_json(self) -> Path:
        return self.dept_dir / "page.json"

    # ---- the whole data directory
    @property
    def engine_json(self) -> Path:
        return self.data_dir / "engine.json"

    @property
    def library_dir(self) -> Path:
        return self.data_dir / "library"

    @property
    def agents_dir(self) -> Path:
        return self.data_dir / "agents" / "j2"

    # ---- the run
    def _run(self, *parts: str) -> Path:
        if self.run_id is None:
            raise ValueError("these paths belong to a run, and this DataPaths has none")
        return self.runs_dir.joinpath(self.run_id, *parts)

    @property
    def run_dir(self) -> Path:
        return self._run()

    @property
    def task_json(self) -> Path:
        return self._run("task.json")

    @property
    def inbox(self) -> Path:
        return self._run("inbox.jsonl")

    @property
    def events(self) -> Path:
        return self._run("events.jsonl")

    @property
    def trace(self) -> Path:
        return self._run("trace.jsonl")

    @property
    def snapshot(self) -> Path:
        return self._run("snapshot.json")

    @property
    def live(self) -> Path:
        return self._run("live.json")

    @property
    def settings_json(self) -> Path:
        return self._run("settings.json")

    @property
    def upstream_dir(self) -> Path:
        return self._run("upstream")

    def j2_env(self) -> dict[str, str]:
        """The path variables the host exports before it imports J2: where this department's runs and memory are, the
        global library, and the role-file override folder when it exists."""
        env = {"J2_RUNS_DIR": str(self.runs_dir), "J2_MEMORY_FILE": str(self.lessons_file),
               "J2_PLAYBOOK_FILE": str(self.playbooks_file), "J2_LIBRARY_DIR": str(self.library_dir)}
        if self.agents_dir.is_dir():
            env["J2_AGENTS_DIR"] = str(self.agents_dir)
        return env


# ---- .env ------------------------------------------------------------------------------------------------------

def project_root() -> Path:
    """The folder that holds the `sutra_app` package: the checkout in development."""
    return Path(__file__).resolve().parents[2]


def default_data_dir(environ=None) -> Path:
    """The same rule as `sutra_app.config.default_data_dir`: `SUTRA_DATA_DIR`; else `<project>/data` in a checkout (a
    `pyproject.toml` beside the package); else `~/.sutra-pro` (an installed app)."""
    env = os.environ if environ is None else environ
    named = (env.get("SUTRA_DATA_DIR") or "").strip()
    if named:
        return Path(named).expanduser()
    root = project_root()
    return root / "data" if (root / "pyproject.toml").is_file() else Path.home() / ".sutra-pro"


def default_env_file(environ=None) -> Path:
    """The file named by SUTRA_ENV_FILE, else `<project>/.env` in a checkout (a `pyproject.toml` beside the package), else
    `<data dir>/.env` (an installed app: the package sits in site-packages, where nobody keeps a `.env`, G03)."""
    env = os.environ if environ is None else environ
    named = (env.get("SUTRA_ENV_FILE") or "").strip()
    if named:
        return Path(named)
    root = project_root()
    return root / ".env" if (root / "pyproject.toml").is_file() else default_data_dir(env) / ".env"


def load_env_file(path=None, *, environ: Optional[MutableMapping] = None) -> tuple[str, ...]:
    """Read `KEY=value` lines of the .env file and set the `J2_SMTP_*` variables (the live email login of j2_send) into
    `environ` (default `os.environ`). Only those five names are ever read: the owner override key stays with the server and
    every other variable is ignored. A variable that is already set wins, as in J2. Blank lines, `#` comments, a leading
    `export ` and one pair of quotes around a value are understood. A missing or unreadable file is no file. Returns the
    names it set, never their values."""
    env = os.environ if environ is None else environ
    target = Path(path) if path is not None else default_env_file(env)
    try:
        lines = target.read_text(encoding="utf-8-sig").splitlines()       # a byte-order mark is not part of the first name
    except (OSError, UnicodeDecodeError):
        return ()
    loaded = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        value = value.strip().strip('"').strip("'")
        if key in SMTP_VARS and value and not env.get(key):
            env[key] = value
            loaded.append(key)
    return tuple(loaded)


def pid_alive(pid) -> bool:
    """True when a process with this id exists (signal 0). A process of another user counts as alive; a zombie does until
    its parent reaps it. 0, negative numbers, bools and non-integers are never a pid."""
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (OSError, OverflowError):
        return False
    return True
