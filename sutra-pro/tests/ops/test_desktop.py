"""sutra_app.desktop (D101): the Windows app's entry, tested with a fake pystray and Pillow so the logic runs on every system.

What cannot be tested here is a real notification area; the Windows proof (scripts/prove_windows_app.py) runs the real launcher and records
whether the tray could be shown. What can: the order of things (server in a thread, icon in the main thread), Quit, a server that ends
by itself, a second launch, a missing tray library, a process with no console.
"""
import sys
import threading
import time
import types

import pytest

from sutra_app import desktop, oslayer
from sutra_app.ops import lock


class FakeIcon:
    last = None

    def __init__(self, name, image, title, menu):
        self.name, self.image, self.title, self.menu = name, image, title, menu
        self.stopped = threading.Event()
        self.running = threading.Event()
        FakeIcon.last = self

    def run(self):
        self.running.set()
        self.stopped.wait(20)

    def stop(self):
        self.stopped.set()

    def action(self, text):
        return next(item.action for item in self.menu.items if item.text == text)


class FakeMenu:
    def __init__(self, *items):
        self.items = items


class FakeItem:
    def __init__(self, text, action, default=False):
        self.text, self.action, self.default = text, action, default


@pytest.fixture
def fake_tray(monkeypatch):
    monkeypatch.setitem(sys.modules, "pystray", types.SimpleNamespace(Icon=FakeIcon, Menu=FakeMenu, MenuItem=FakeItem))
    image = types.ModuleType("PIL.Image")
    image.open = lambda path: ("image", str(path))
    pil = types.ModuleType("PIL")
    pil.Image = image
    monkeypatch.setitem(sys.modules, "PIL", pil)
    monkeypatch.setitem(sys.modules, "PIL.Image", image)
    FakeIcon.last = None
    return FakeIcon


def test_the_server_runs_in_a_thread_and_the_icon_ends_when_the_server_does(fake_tray, monkeypatch, tmp_path):
    seen = {}

    def serve(argv, result):
        seen["argv"], seen["thread"] = argv, threading.current_thread().name
        time.sleep(0.2)
        result["code"] = 0

    monkeypatch.setattr(desktop, "_serve", serve)
    assert desktop._run_with_tray(["--port", "0"], tmp_path) == 0
    assert seen == {"argv": ["--port", "0"], "thread": "sutra-server"}
    icon = fake_tray.last
    assert icon.stopped.is_set() and icon.title == "Sutra Pro" and icon.name == "sutra-pro"
    assert [item.text for item in icon.menu.items] == ["Open Sutra Pro", "Quit Sutra Pro"] and icon.menu.items[0].default


def test_quit_asks_the_server_to_stop_through_the_stop_file_and_ends_the_icon(fake_tray, monkeypatch, tmp_path):
    def serve(argv, result):
        while not lock.stop_requested(tmp_path):
            time.sleep(0.02)
        result["code"] = 0

    monkeypatch.setattr(desktop, "_serve", serve)
    outcome = {}
    runner = threading.Thread(target=lambda: outcome.update(code=desktop._run_with_tray([], tmp_path)))
    runner.start()
    assert _wait(lambda: fake_tray.last is not None and fake_tray.last.running.is_set())
    fake_tray.last.action("Quit Sutra Pro")(fake_tray.last)
    runner.join(30)
    assert not runner.is_alive() and outcome == {"code": 0}
    assert fake_tray.last.stopped.is_set() and lock.stop_requested(tmp_path)


def test_open_opens_the_browser_on_the_running_server(fake_tray, monkeypatch, tmp_path):
    opened = []
    monkeypatch.setattr("sutra_app.ops.browser.open_url", lambda url, *a, **k: opened.append(url))
    lock.InstanceLock(tmp_path).acquire()
    holder_lock = lock.InstanceLock(tmp_path)               # a second one cannot take it, but the pid file names the first
    assert holder_lock.acquire() is False
    (tmp_path / lock.PID_NAME).write_text(f"{__import__('os').getpid()} 8791\n", encoding="utf-8")

    def serve(argv, result):
        time.sleep(0.3)
        result["code"] = 0

    monkeypatch.setattr(desktop, "_serve", serve)
    runner = threading.Thread(target=lambda: desktop._run_with_tray([], tmp_path))
    runner.start()
    assert _wait(lambda: fake_tray.last is not None and fake_tray.last.running.is_set())
    fake_tray.last.action("Open Sutra Pro")(fake_tray.last)
    runner.join(30)
    assert opened == ["http://127.0.0.1:8791/"]


def test_without_the_tray_library_the_caller_is_told_to_run_the_server_itself(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "pystray", None)                 # `import pystray` raises ImportError
    assert desktop._run_with_tray([], tmp_path) == -1


def test_main_runs_the_tray_when_wanted_and_the_folder_is_free(monkeypatch, tmp_path):
    monkeypatch.setattr(oslayer, "IS_WINDOWS", True)
    monkeypatch.setattr(desktop, "attach_streams", lambda *a: False)
    monkeypatch.delenv("SUTRA_NO_TRAY", raising=False)
    calls = []
    monkeypatch.setattr(desktop, "_run_with_tray", lambda argv, data_dir: calls.append(("tray", argv, data_dir)) or 0)
    monkeypatch.setattr(desktop, "_serve", lambda argv, result: calls.append(("serve", argv)) or result.update(code=0))
    assert desktop.main(["--data-dir", str(tmp_path), "--no-browser"]) == 0
    assert calls == [("tray", ["--browser", "auto", "--data-dir", str(tmp_path), "--no-browser"], tmp_path)]


def test_a_second_launch_only_opens_the_running_app_and_shows_no_second_icon(monkeypatch, tmp_path):
    monkeypatch.setattr(oslayer, "IS_WINDOWS", True)
    monkeypatch.setattr(desktop, "attach_streams", lambda *a: False)
    first = lock.InstanceLock(tmp_path)
    assert first.acquire()
    calls = []
    monkeypatch.setattr(desktop, "_run_with_tray", lambda *a: calls.append("tray") or 0)
    monkeypatch.setattr(desktop, "_serve", lambda argv, result: calls.append("serve") or result.update(code=0))
    try:
        assert desktop.main(["--data-dir", str(tmp_path)]) == 0
    finally:
        first.release()
    assert calls == ["serve"], "the server's own `already running` path opens the browser; the tray is not started"


def test_no_tray_when_the_variable_says_so_or_the_library_is_missing_and_the_server_owns_the_process(monkeypatch, tmp_path):
    monkeypatch.setattr(oslayer, "IS_WINDOWS", True)
    monkeypatch.setattr(desktop, "attach_streams", lambda *a: False)
    monkeypatch.setenv("SUTRA_NO_TRAY", "1")
    calls = []
    monkeypatch.setattr(desktop, "_run_with_tray", lambda *a: calls.append("tray") or 0)
    monkeypatch.setattr(desktop, "_serve", lambda argv, result: calls.append("serve") or result.update(code=0))
    assert desktop.main(["--data-dir", str(tmp_path)]) == 0 and calls == ["serve"]
    monkeypatch.delenv("SUTRA_NO_TRAY")
    calls.clear()
    monkeypatch.setattr(desktop, "_run_with_tray", lambda *a: calls.append("tray") or -1)          # the library is missing
    assert desktop.main(["--data-dir", str(tmp_path)]) == 0 and calls == ["tray", "serve"]


def test_a_failed_start_shows_one_message_naming_the_log(monkeypatch, tmp_path):
    monkeypatch.setattr(oslayer, "IS_WINDOWS", False)
    monkeypatch.setattr(desktop, "attach_streams", lambda *a: False)
    shown = []
    monkeypatch.setattr(desktop, "_message_box", shown.append)
    monkeypatch.setattr(desktop, "_serve", lambda argv, result: result.update(code=2))
    assert desktop.main(["--data-dir", str(tmp_path)]) == 2
    assert len(shown) == 1 and "could not start" in shown[0] and "desktop.log" in shown[0]


def test_a_process_with_no_console_gets_its_streams_pointed_at_a_log_file(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    target = tmp_path / "logs" / "desktop.log"
    assert desktop.attach_streams(target) is True
    print("hello from a process with no console")
    sys.stdout.flush()
    assert "hello from a process with no console" in target.read_text(encoding="utf-8")


def test_streams_that_exist_are_left_alone(tmp_path):
    assert desktop.attach_streams(tmp_path / "never.log") is False and not (tmp_path / "never.log").exists()


def test_the_log_is_in_the_data_folder(tmp_path):
    assert desktop.log_path({"SUTRA_DATA_DIR": str(tmp_path)}) == tmp_path / "logs" / "desktop.log"
    assert desktop.data_dir_of(["--data-dir", "x"]).name == "x" and desktop.data_dir_of(["--data-dir=y"]).name == "y"


def _wait(predicate, seconds=15.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()
