"""Logging (GAP-OPS-1, gaps G11): the rotating file, redaction of messages, arguments and tracebacks, the request id, uvicorn's access log."""
import io
import logging
import re
import stat

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sutra_app.config import Settings
from sutra_app.main import create_app
from sutra_app.ops import logsetup
from sutra_app.orchestrator.testing.fake_engine import FakeLauncher
from sutra_app.orchestrator.testing.scripted import ScriptedConnector

TOKEN = "tok-0123456789abcdef"
KEY = "override-key-987654321"


@pytest.fixture(autouse=True)
def clean_root_logger():
    root = logging.getLogger()
    before, level = list(root.handlers), root.level
    yield
    for handler in [h for h in root.handlers if h not in before]:
        root.removeHandler(handler)
        handler.close()
    root.setLevel(level)


def make_settings(tmp_path, **changes):
    env_file = tmp_path / "x.env"
    env_file.write_text("J2_SMTP_PASSWORD=smtp-secret-value\n")
    return Settings.load({}, data_dir=tmp_path / "data", token=TOKEN, env_file=env_file, override_key=KEY, engine="fake", **changes)


def log_text(settings):
    for handler in logging.getLogger().handlers:
        handler.flush()
    return settings.log_path.read_text()


def test_configure_writes_a_private_rotating_file_of_5_mb_times_5(tmp_path):
    settings = make_settings(tmp_path)
    handler = logsetup.configure(settings)
    assert settings.log_path.parent == settings.data_dir / "logs"
    assert isinstance(handler, logging.handlers.RotatingFileHandler)
    assert (handler.maxBytes, handler.backupCount) == (5 * 1024 * 1024, 5)
    logging.getLogger("t").info("hello")
    assert stat.S_IMODE(settings.log_path.stat().st_mode) == 0o600
    assert logging.getLogger().level == logging.INFO


def test_a_rolled_over_file_is_private_again_and_old_files_are_kept(tmp_path):
    settings = make_settings(tmp_path)
    handler = logsetup.configure(settings, console=False)
    handler.maxBytes = 300
    for index in range(12):
        logging.getLogger("t").info("line %d %s", index, "x" * 60)
    handler.flush()
    files = sorted(p.name for p in settings.logs_dir.iterdir())
    assert "server.log.1" in files and len(files) <= 6
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in settings.logs_dir.iterdir())


def test_verbose_sets_debug_and_the_console_shows_warnings_by_default(tmp_path):
    settings = make_settings(tmp_path)
    sink = io.StringIO()
    logsetup.configure(settings, stream=sink)
    log = logging.getLogger("t.console")
    log.info("quiet")
    log.warning("loud")
    assert "loud" in sink.getvalue() and "quiet" not in sink.getvalue() and "quiet" in log_text(settings)
    logsetup.configure(settings, verbose=True, stream=sink)
    assert logging.getLogger().level == logging.DEBUG
    log.debug("detail")
    assert "detail" in log_text(settings) and "detail" in sink.getvalue()


def test_configure_twice_leaves_one_set_of_handlers_and_replaces_orch8s(tmp_path):
    from sutra_app.orchestrator.wiring import configure_logging, make_redactor
    settings = make_settings(tmp_path)
    configure_logging(settings, make_redactor(settings))
    logsetup.configure(settings)
    logsetup.configure(settings)
    ours = [h for h in logging.getLogger().handlers if getattr(h, "_sutra_app", False)]
    assert len(ours) == 2                                              # the file and the console
    assert sum(isinstance(h, logging.handlers.RotatingFileHandler) for h in ours) == 1


def test_every_secret_is_redacted_in_the_message_its_arguments_and_the_traceback(tmp_path, monkeypatch):
    monkeypatch.setenv("MY_SERVICE_TOKEN", "env-secret-value-1")
    settings = make_settings(tmp_path)
    logsetup.configure(settings)
    log = logging.getLogger("t.secret")
    log.info("plain %s", TOKEN)
    log.info("args %s and %s", KEY, {"k": "smtp-secret-value"})
    log.info("env value env-secret-value-1")
    try:
        raise RuntimeError(f"failed with {TOKEN}")
    except RuntimeError:
        log.exception("it broke")
    text = log_text(settings)
    for secret in (TOKEN, KEY, "smtp-secret-value", "env-secret-value-1"):
        assert secret not in text, secret
    assert text.count("[redacted]") >= 5
    assert "Traceback (most recent call last)" in text and "RuntimeError: failed with [redacted]" in text


def test_a_message_with_a_bad_format_string_is_still_logged():
    record = logging.LogRecord("t.bad", logging.INFO, __file__, 1, "needs %s and %s", ("one",), None)
    assert logsetup.RedactingFilter(lambda text: text.upper()).filter(record) is True
    assert record.getMessage() == "NEEDS %S AND %S" and record.args is None and record.request_id == "-"


def test_the_line_format_is_time_level_logger_request_id_message(tmp_path):
    settings = make_settings(tmp_path)
    logsetup.configure(settings)
    logging.getLogger("t.fmt").warning("something")
    token = logsetup.request_id_var.set("abc123def456")
    try:
        logging.getLogger("t.fmt").warning("inside")
    finally:
        logsetup.request_id_var.reset(token)
    first, second = [l for l in log_text(settings).splitlines() if "t.fmt" in l]
    assert re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3} WARNING t\.fmt - something", first)
    assert re.fullmatch(r"\S+ \S+ WARNING t\.fmt abc123def456 inside", second)


def test_the_access_log_loses_its_query_string(tmp_path):
    settings = make_settings(tmp_path)
    logsetup.configure(settings)
    logging.getLogger("uvicorn.access").info('%s - "%s %s HTTP/%s" %d', "127.0.0.1:5", "GET", "/api/events?run=j2-1&dept=web", "1.1", 200)
    text = log_text(settings)
    assert '"GET /api/events HTTP/1.1" 200' in text and "run=j2-1" not in text


def test_the_middleware_sets_a_fresh_12_hex_request_id_and_ignores_the_callers():
    app = FastAPI()

    @app.get("/ping")
    def ping():
        logging.getLogger("t.mw").info("in handler")
        return {"id": logsetup.request_id_var.get()}
    client = TestClient(logsetup.RequestIdMiddleware(app))
    one = client.get("/ping", headers={"X-Request-Id": "forged"})
    two = client.get("/ping")
    missing = client.get("/nope")
    ids = [r.headers["x-request-id"] for r in (one, two, missing)]
    assert all(re.fullmatch(r"[0-9a-f]{12}", i) for i in ids) and len(set(ids)) == 3
    assert one.json()["id"] == ids[0]                                   # the handler (a worker thread) saw the same id
    assert logsetup.request_id_var.get() == "-"                         # and nothing leaks out of the request


def test_a_log_line_written_while_a_request_is_served_carries_its_id(tmp_path):
    settings = make_settings(tmp_path)
    logsetup.configure(settings)
    app = FastAPI()

    @app.get("/ping")
    def ping():
        logging.getLogger("t.mw2").info("in handler")
        return {}
    response = TestClient(logsetup.RequestIdMiddleware(app)).get("/ping")
    line = next(l for l in log_text(settings).splitlines() if "t.mw2" in l)
    assert f" {response.headers['x-request-id']} in handler" in line


def test_create_app_puts_the_id_on_every_answer_even_a_refused_host_and_an_unhandled_error(tmp_path):
    settings = make_settings(tmp_path)
    app = create_app(settings, connector=ScriptedConnector(), launcher=FakeLauncher())

    @app.get("/boom")
    def boom():
        raise RuntimeError("boom")
    with TestClient(app, base_url="http://127.0.0.1:8780", raise_server_exceptions=False) as client:
        ok = client.get("/api/health")
        bad_host = client.get("/api/health", headers={"Host": "evil.example.com"})
        failed = client.get("/boom")
    assert ok.status_code == 200 and bad_host.status_code == 400 and failed.status_code == 500
    for response in (ok, bad_host, failed):
        assert re.fullmatch(r"[0-9a-f]{12}", response.headers["x-request-id"])


def test_an_ops_api_module_is_mounted_when_it_exists_and_skipped_when_it_does_not(tmp_path, monkeypatch):
    import sys
    import types
    from fastapi import APIRouter
    settings = make_settings(tmp_path)
    assert create_app(settings, connector=ScriptedConnector(), launcher=FakeLauncher()).state.ops_api is True      # GAP-CONSOLE's real module exists
    monkeypatch.setitem(sys.modules, "sutra_app.ops.api", None)                                                    # a module that cannot be found
    assert create_app(settings, connector=ScriptedConnector(), launcher=FakeLauncher()).state.ops_api is False
    router = APIRouter()

    @router.get("/api/ops/ping")
    def ping():
        return {"pong": True}
    import importlib.machinery
    module = types.ModuleType("sutra_app.ops.api")
    module.__spec__ = importlib.machinery.ModuleSpec("sutra_app.ops.api", None)
    module.router = router
    monkeypatch.setitem(sys.modules, "sutra_app.ops.api", module)
    monkeypatch.setattr("sutra_app.ops.api", module, raising=False)
    app = create_app(settings, connector=ScriptedConnector(), launcher=FakeLauncher())
    assert app.state.ops_api is True
    with TestClient(app, base_url="http://127.0.0.1:8780") as client:
        assert client.get("/api/ops/ping").json() == {"pong": True}
