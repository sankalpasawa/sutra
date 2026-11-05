"""Fixtures of the end-to-end suite (GAP-E2E). The harness itself is `harness.py` (imported by name: this folder has no __init__.py,
so pytest puts it on sys.path)."""
import pytest
from harness import LiveApp


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
