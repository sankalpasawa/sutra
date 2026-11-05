"""Fixtures of the end-to-end suite (GAP-E2E). The harness itself is `harness.py` (imported by name: this folder has no __init__.py,
so pytest puts it on sys.path)."""
import sys

import pytest
from harness import LiveApp

# On Windows only these modules run: the others start real servers and engine processes and assert POSIX process-group semantics
# (killpg, ps, SIGTERM exit codes). The Windows equivalents are test_stop_request.py (a real server, stopped through app.stop and through
# `sutra-pro stop`) and scripts/prove_windows_app.py (the packaged app, a team's first turn, a stop request, nothing left running).
WINDOWS_MODULES = {"test_stop_request"}


@pytest.fixture(autouse=True)
def _windows_runs_only_the_windows_modules(request):
    if sys.platform == "win32" and request.module.__name__ not in WINDOWS_MODULES:
        pytest.skip("POSIX process-group semantics (D104); see tests/e2e/conftest.py")


@pytest.fixture
def make_app(tmp_path):
    """`make_app(connector=..., ...)` -> a started `LiveApp` on `tmp_path`. Every app is stopped and every engine process of it
    killed at the end, whatever the test did."""
    made: list[LiveApp] = []

    def make(**kwargs) -> LiveApp:
        live = LiveApp(kwargs.pop("root", tmp_path), **kwargs)
        made.append(live)
        return live.start()

    yield make
    for live in reversed(made):
        try:
            if live.started:
                live.stop()
        finally:
            live.kill_engines()
