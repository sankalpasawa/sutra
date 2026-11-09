"""Fixtures and collection rules for tests/engine (work package E0; every later engine package uses them).

    data_dir        an empty data directory (`<tmp>/data`)
    make_run_dir    a factory: `make_run_dir(dept_id="web", run_id=..., **task_fields)` makes
                    `<data>/departments/<dept>/runs/<run id>/` the way the orchestrator does (folder 0700, `task.json` 0600,
                    empty `inbox.jsonl` and `events.jsonl`) and returns its Path
    run_dir         `make_run_dir()`: department `web`, the example task of engine.md section 5
    scripted_port   a `ScriptedPort` (J2's mock mode) whose `usage_sink` is a recording sink: `scripted_port.usage_sink.rows`
    clean_env       removes `J2_*`, `STUDIO_*` and the engine's own switches (SUTRA_MOCK, SUTRA_OFFLINE, SUTRA_HOOKS,
                    SUTRA_NODES, SUTRA_HEARTBEAT_S, SUTRA_RECORDS, SUTRA_RECORDS_HOOK, SUTRA_ENV_FILE) from the environment
                    for the test and returns the `monkeypatch`, so `clean_env.setenv("J2_BOARD", "1")` reads naturally
    llm_reset       puts `sutra_app.engine.llm` into a known state (no port, mock off, no base tag, no bound atom) and
                    restores it after the test; returns the module
    fake_services   a `FakeServices`: the `EngineServices` of engine.md 4.9 over a temp data directory

The helpers are fixtures, not importable names: a plain `import conftest` is ambiguous between the conftest.py files of the
suite. `tests/engine/legacy/` (J2's own scripts, which match `*_test.py`) is never collected; slow engine suites are skipped
unless SUTRA_SLOW=1 or `-m` selects them (the merge gate runs plain `pytest -q`, and tests/conftest.py is stricter: it also
needs SUTRA_SLOW=1). The markers `slow` and `live` are registered here as well as in pyproject.toml.
"""
import functools
import hmac
import json
import os
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pytest

HERE = Path(__file__).resolve().parent
collect_ignore = ["legacy"]

CLEAN_PREFIXES = ("J2_", "STUDIO_")
CLEAN_NAMES = ("SUTRA_MOCK", "SUTRA_OFFLINE", "SUTRA_HOOKS", "SUTRA_NODES", "SUTRA_HEARTBEAT_S", "SUTRA_RECORDS",
               "SUTRA_RECORDS_HOOK", "SUTRA_ENV_FILE")

EXAMPLE_TASK = {      # engine.md section 5, as the orchestrator writes it
    "schema": "run-spec/1", "run_id": "j2-20261104-100004-7f3a", "task_id": "tsk_a1b2c3d4e5f6", "dept_id": "web",
    "dept_label": "Web", "scope_id": None, "scope_label": None, "user_text": "A website for my cafe", "framing": "",
    "parent_run_id": None, "seed_from": None, "upstream": [], "settings": {"J2_BUDGET": "100"}, "connector": "auto",
}


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: long engine suites (legacy J2 scripts, prompt goldens); runs only with SUTRA_SLOW=1")
    config.addinivalue_line("markers", "live: talks to the real claude or codex CLI; runs only with SUTRA_LIVE=1")


def pytest_collection_modifyitems(config, items):
    """This hook sees every item of the session, so it touches only the ones under tests/engine."""
    if os.environ.get("SUTRA_SLOW") == "1" or config.getoption("markexpr", default=""):
        return
    skip = pytest.mark.skip(reason="slow engine suite: set SUTRA_SLOW=1, or select it with -m")
    for item in items:
        if "slow" in item.keywords and HERE in Path(str(item.path)).parents:
            item.add_marker(skip)


@pytest.fixture
def data_dir(tmp_path) -> Path:
    path = tmp_path / "data"
    path.mkdir()
    return path


def write_task_json(run_dir: Path, task: Mapping) -> None:
    """task.json by temp file and rename, mode 0600: the orchestrator's way."""
    temp = run_dir / ".task.json.tmp"
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(task, f)
    os.replace(temp, run_dir / "task.json")


@pytest.fixture
def make_run_dir(data_dir):
    def make(dept_id: str = "web", run_id: str = EXAMPLE_TASK["run_id"], **task_fields) -> Path:
        run = data_dir / "departments" / dept_id / "runs" / run_id
        run.mkdir(parents=True)
        os.chmod(run, 0o700)
        write_task_json(run, {**EXAMPLE_TASK, "dept_id": dept_id, "dept_label": dept_id.title(), "run_id": run_id,
                              **task_fields})
        for name in ("inbox.jsonl", "events.jsonl"):
            os.close(os.open(run / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
        return run
    return make


@pytest.fixture
def run_dir(make_run_dir) -> Path:
    return make_run_dir()


class RecordingSink:
    """A usage sink that keeps what it is given (as dicts) in `rows`; `record` returns the number of rows so far."""

    def __init__(self):
        self.rows: list[dict] = []
        self._lock = threading.Lock()

    def record(self, row) -> int:
        data = dict(row) if isinstance(row, Mapping) else row.model_dump()
        with self._lock:
            self.rows.append(data)
            return len(self.rows)


@pytest.fixture
def scripted_port():
    from sutra_app.engine.llm import ScriptedPort
    return ScriptedPort(RecordingSink(), delay=0.0)


@pytest.fixture
def clean_env(monkeypatch):
    for name in list(os.environ):
        if name.startswith(CLEAN_PREFIXES) or name in CLEAN_NAMES:
            monkeypatch.delenv(name)
    return monkeypatch


@pytest.fixture
def llm_reset(monkeypatch):
    from sutra_app.engine import llm
    from sutra_app.engine.port import CallTag
    for name, value in (("_PORT", None), ("_DEFAULT_PORT", None), ("_BASE_TAG", CallTag()), ("_BOUND_ATOM", None),
                        ("MOCK", False), ("PROVIDER", None), ("MODEL", None)):
        monkeypatch.setattr(llm, name, value)
    monkeypatch.setattr(llm, "TAG_HOOKS", [])           # the capabilities' hooks (D126) belong to one host run, not to the next test
    monkeypatch.setattr(llm, "PROGRESS_HOOKS", [])
    llm.LAST_META.clear()
    yield llm
    llm.LAST_META.clear()


# ---- an EngineServices over a temp directory (engine.md 4.9) ----------------------------------------------------

class FakeBusy(Exception):
    """What `deliver_to_department` raises when the department's task is running (the route answers 409)."""


@dataclass
class FakeDept:
    id: str
    name: str
    archived: bool = False


@dataclass
class FakeRunRef:
    run_id: str
    task_id: str
    dept_id: str
    dir: str                                   # relative to the data dir, as the orchestrator's RunRef has it
    status: str = "done"
    pid: Optional[int] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None


@dataclass
class FakeDelivery:
    delivered: str                             # "answer" | "follow_up"
    task_id: str
    message_id: int = 0


LIVE_STATUSES = ("starting", "running", "waiting_user")


class FakeServices:
    """What the engine's FastAPI routes call, over a temp data directory. Set it up with `add_department` and `add_run`; the
    knobs `busy` (deliveries raise FakeBusy), `stop_result` (what `stop_live` answers) and `secrets` (what `redact` hides)
    steer the routes; `deliveries` and `stops` record what the routes did. `require_token` is a FastAPI dependency that
    wants the header `X-Sutra-Token: <token>` and answers 401 without it."""

    token = "fake-token-fake-token-0123"

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.departments: dict[str, FakeDept] = {}
        self.runs: list[FakeRunRef] = []
        self.deliveries: list[dict] = []
        self.stops: list[str] = []
        self.busy = False
        self.stop_result = True
        self.secrets: list[str] = []

    def add_department(self, dept_id: str, name: Optional[str] = None, *, archived: bool = False) -> FakeDept:
        dept = FakeDept(dept_id, name or dept_id.title(), archived)
        self.departments[dept_id] = dept
        (self.data_dir / "departments" / dept_id / "runs").mkdir(parents=True, exist_ok=True)
        return dept

    def add_run(self, dept_id: str, run_id: Optional[str] = None, *, status: str = "done",
                files: Optional[Mapping[str, object]] = None) -> FakeRunRef:
        """Make a run folder. `files` maps a relative path to text, bytes or (written as JSON) a dict or list."""
        if dept_id not in self.departments:
            self.add_department(dept_id)
        run_id = run_id or f"j2-20261104-1000{len(self.runs):02d}-{len(self.runs):04x}"
        rel = f"departments/{dept_id}/runs/{run_id}"
        folder = self.data_dir / rel
        folder.mkdir(parents=True)
        for name, content in (files or {}).items():
            target = folder / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                target.write_bytes(content)
            else:
                target.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
        ref = FakeRunRef(run_id, f"tsk_{len(self.runs):012x}", dept_id, rel, status)
        self.runs.append(ref)
        return ref

    def resolve_run(self, run_id: Optional[str], dept_id: str) -> Optional[FakeRunRef]:
        """`run_id` wins (it must be the department's), else the live task's run, else the latest."""
        mine = [r for r in self.runs if r.dept_id == dept_id]
        if run_id is not None:
            return next((r for r in mine if r.run_id == run_id), None)
        live = [r for r in mine if r.status in LIVE_STATUSES]
        return live[-1] if live else (mine[-1] if mine else None)

    def department(self, dept_id: str) -> Optional[FakeDept]:
        return self.departments.get(dept_id)

    def deliver_to_department(self, dept_id: str, text: str, *, scope_id: Optional[str] = None,
                              settings: Optional[dict] = None) -> FakeDelivery:
        self.deliveries.append({"dept_id": dept_id, "text": text, "scope_id": scope_id, "settings": settings})
        if self.busy:
            raise FakeBusy(dept_id)
        live = [r for r in self.runs if r.dept_id == dept_id and r.status == "waiting_user"]
        return FakeDelivery("answer", live[-1].task_id) if live else FakeDelivery("follow_up", f"tsk_{len(self.runs):012x}")

    def stop_live(self, dept_id: str) -> bool:
        self.stops.append(dept_id)
        return self.stop_result

    def redact(self, text: str) -> str:
        for secret in self.secrets:
            text = text.replace(secret, "[redacted]")
        return text

    @functools.cached_property
    def require_token(self):
        from fastapi import Header, HTTPException
        expected = self.token

        def require_token(x_sutra_token: Optional[str] = Header(None)) -> None:
            if x_sutra_token is None or not hmac.compare_digest(x_sutra_token.encode(), expected.encode()):
                raise HTTPException(status_code=401, detail={"error": {"code": "bad_token", "message": "a write needs the "
                                                                "X-Sutra-Token header", "details": {}}})
        return require_token


@pytest.fixture
def fake_services(data_dir) -> FakeServices:
    return FakeServices(data_dir)
