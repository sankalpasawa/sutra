"""Shared setup of the UI tests (UI-0, docs/design/ui.md section 10, D85).

Registers the `browser` marker (the other opt-in markers belong to `tests/conftest.py`; the default suite skips every
`browser` test unless `SUTRA_BROWSER=1`) and offers the fixtures every UI test module shares:

  fixtures_dir        the folder of the JSON fixtures (`tests/ui/fixtures`)
  screens_dir         where screenshots go (`tests/ui/screens`, git-ignored)
  make_fake_server    a factory: `make_fake_server(**make_app_options)` -> FakeServer, stopped at the end of the test
  fake_server         one fake backend for the whole module (the real UI pages and static files)
  fake                the module's FakeClient, reset to stage 1 with an empty log before each test
  browser             a headless Chrome (cdp.Browser) for a test marked `browser`; the test is skipped when Chrome is not
                      installed and FAILS when a request failed that the test did not announce with `expect_failed`

A browser test looks like this:

    @pytest.mark.browser
    def test_home_loads(fake_server, fake, browser):
        browser.goto(fake_server.url + "/")
        browser.wait_for("document.readyState === 'complete'")
        assert not browser.console_errors
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Iterator, NamedTuple

import pytest

UI_TESTS = Path(__file__).resolve().parent
if str(UI_TESTS) not in sys.path:  # `import cdp` and `import fake_backend` work from any test module, in any import mode
    sys.path.insert(0, str(UI_TESTS))

import fake_backend  # noqa: E402  (after the path line above)
from fake_backend import FakeClient, FakeState  # noqa: E402

FIXTURES_DIR = UI_TESTS / "fixtures"
SCREENS_DIR = UI_TESTS / "screens"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "browser: drives a real headless Chrome over CDP; runs only with SUTRA_BROWSER=1")


class FakeServer(NamedTuple):
    """A running fake backend: its `url`, a `client` for the controls, the `app` and its `state` (for direct reads)."""

    url: str
    client: FakeClient
    app: object
    state: FakeState


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture(scope="session")
def screens_dir() -> Path:
    SCREENS_DIR.mkdir(parents=True, exist_ok=True)
    return SCREENS_DIR


def _start(**options) -> tuple[FakeServer, Callable[[], None]]:
    app = fake_backend.make_app(**options)
    running = fake_backend.run_in_thread(app)
    server = FakeServer(running.url, FakeClient(running.url, app.state.fake.token), app, app.state.fake)
    return server, running.stop


@pytest.fixture()
def make_fake_server() -> Iterator[Callable[..., FakeServer]]:
    """Start a fake backend with its own options (`fixtures_dir`, `pages_dir`, `static_dir`, `token`, `version`)."""
    stops: list[Callable[[], None]] = []

    def make(**options) -> FakeServer:
        server, stop = _start(**options)
        stops.append(stop)
        return server

    yield make
    for stop in reversed(stops):
        stop()


@pytest.fixture(scope="module")
def fake_server() -> Iterator[FakeServer]:
    server, stop = _start()
    try:
        yield server
    finally:
        stop()


@pytest.fixture()
def fake(fake_server: FakeServer) -> FakeClient:
    fake_server.client.reset()
    return fake_server.client


@pytest.fixture()
def browser() -> Iterator["cdp.Browser"]:  # noqa: F821  (cdp is imported lazily: websockets is a dev dependency)
    cdp = pytest.importorskip("cdp")
    chrome = cdp.find_chrome()
    if chrome is None:
        pytest.skip("Chrome is not installed (set SUTRA_CHROME to its path)")
    with cdp.Browser(chrome) as instance:
        # Debug, in Home's workspace: every view the tests written before the front door drive (the org chat, the panes, Settings, a team's
        # Detailed view) is shown at that level. The front door's own tests (test_home_front.py) call set_level("simple") and the like.
        if hasattr(instance, "set_level"):                                  # a stand-in Browser (test_fake_backend's own) has none
            instance.set_level("debug", "ws")
        yield instance
        failed = instance.failed_requests
        assert not failed, f"requests failed during the test (announce them with browser.expect_failed): {failed}"
