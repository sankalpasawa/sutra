"""Fixtures of the orchestrator tests: `settings`, `clock`, `ids`, `events`, `db`. Fixtures only (design 7).

`settings` points at a temp data dir and a fixed token; `db` is a migrated file database whose commits land in `events`.
tests/library holds the builders of atoms and nodes (it has no __init__.py, so its folder goes on sys.path here)."""
import sys
from pathlib import Path

import pytest

from sutra_app.config import Settings
from sutra_app.orchestrator.db import Database
from sutra_app.orchestrator.testing import EventCollector, FakeClock, FakeIds

_LIBRARY_TESTS = str(Path(__file__).resolve().parents[1] / "library")
if _LIBRARY_TESTS not in sys.path:
    sys.path.append(_LIBRARY_TESTS)

TOKEN = "test-token-0123456789abcdef"


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings.load({}, data_dir=tmp_path / "data", token=TOKEN, env_file=tmp_path / "none.env")


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def ids(clock) -> FakeIds:
    return FakeIds(clock)


@pytest.fixture
def events() -> EventCollector:
    return EventCollector()


@pytest.fixture
def db(settings, events, clock):
    database = Database(settings.db_path, events, clock=clock)
    database.migrate()
    yield database
    database.close()
