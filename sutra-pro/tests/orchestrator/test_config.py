"""Settings: env parsing, defaults, the loopback rule, the token length, the override key and its secrecy (design 6.4, S3-web-02,
S1-contracts-14, S1-contracts-19)."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from sutra_app import config
from sutra_app.config import ENV_NAMES, Settings, SettingsError, read_env_file

TOKEN = "0123456789abcdef"          # exactly 16 characters
KEY = "owner-override-key-777"


def load(env=None, **kw):
    base = {"SUTRA_DATA_DIR": "/tmp/sutra-config-test", "SUTRA_ENV_FILE": "/nonexistent/.env"}
    return Settings.load({**base, **(env or {})}, **kw)


def test_defaults():
    s = load()
    assert (s.host, s.port, s.connector, s.engine, s.offline, s.live) == ("127.0.0.1", 8780, "auto", "process", False, False)
    assert (s.max_runs, s.max_live, s.watch_ms, s.chat_timeout, s.chat_attempts) == (3, 12, 400, 120.0, 3)
    assert s.override_key is None and len(s.token) == 32


def test_every_variable_is_read():
    s = load({"SUTRA_PORT": "9001", "SUTRA_HOST": "localhost", "SUTRA_TOKEN": TOKEN, "SUTRA_CONNECTOR": "stub",
              "SUTRA_ENGINE": "fake", "SUTRA_OFFLINE": "1", "SUTRA_CHAT_TIMEOUT": "30.5", "SUTRA_CHAT_ATTEMPTS": "2",
              "SUTRA_MAX_RUNS": "2", "SUTRA_MAX_LIVE": "5", "SUTRA_WATCH_MS": "100", "SUTRA_LIVE": "true"})
    assert (s.port, s.host, s.token, s.connector, s.engine, s.offline) == (9001, "localhost", TOKEN, "stub", "fake", True)
    assert (s.chat_timeout, s.chat_attempts, s.max_runs, s.max_live, s.watch_ms, s.live) == (30.5, 2, 2, 5, 100, True)
    assert s.data_dir == Path("/tmp/sutra-config-test") and s.env_file == Path("/nonexistent/.env")


def test_every_env_name_is_a_field():
    assert set(ENV_NAMES) <= set(Settings.model_fields)


@pytest.mark.parametrize("text,expected", [("1", True), ("true", True), ("YES", True), ("on", True), ("0", False), ("off", False), ("", False)])
def test_booleans(text, expected):
    assert load({"SUTRA_OFFLINE": text}).offline is expected


@pytest.mark.parametrize("name,value", [("SUTRA_OFFLINE", "maybe"), ("SUTRA_PORT", "80a"), ("SUTRA_CHAT_TIMEOUT", "soon")])
def test_malformed_variable_names_itself(name, value):
    with pytest.raises(SettingsError, match=name):
        load({name: value})


@pytest.mark.parametrize("name,value", [("SUTRA_PORT", "70000"), ("SUTRA_CHAT_ATTEMPTS", "0"), ("SUTRA_MAX_RUNS", "0"), ("SUTRA_CONNECTOR", "gpt")])
def test_out_of_range_value_is_refused(name, value):
    with pytest.raises(SettingsError, match=name):
        load({name: value})


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.5", "example.com", "::1", ""])
def test_non_loopback_host_is_refused(host):
    with pytest.raises(SettingsError, match="loopback"):
        load({"SUTRA_HOST": host})


def test_a_15_character_token_is_refused_from_the_environment_and_from_code():
    short = TOKEN[:15]
    with pytest.raises(SettingsError, match="SUTRA_TOKEN") as env_err:
        load({"SUTRA_TOKEN": short})
    with pytest.raises(SettingsError, match="token"):
        load(token=short)
    assert short not in str(env_err.value)                     # a rejected secret is never echoed
    assert load(token=TOKEN).token == TOKEN


@pytest.mark.parametrize("token", ["has a space in it!!", "ünicode-token-0123456789", "tab\ttoken-0123456789abc"])
def test_a_token_must_be_visible_ascii(token):
    with pytest.raises(SettingsError):
        load(token=token)


def test_random_tokens_differ_per_load():
    assert load().token != load().token


def test_max_live_cannot_be_below_max_runs():
    with pytest.raises(SettingsError, match="max_live"):
        load({"SUTRA_MAX_RUNS": "5", "SUTRA_MAX_LIVE": "4"})


def test_max_live_may_equal_max_runs():
    assert load({"SUTRA_MAX_RUNS": "4", "SUTRA_MAX_LIVE": "4"}).max_live == 4


def test_keyword_overrides_win_and_none_means_not_given():
    s = load({"SUTRA_PORT": "9001"}, port=9100, offline=True, host=None)
    assert (s.port, s.offline, s.host) == (9100, True, "127.0.0.1")
    with pytest.raises(SettingsError, match="unknown setting"):
        load(prot=1)


def test_data_dir_variable_wins_then_checkout_then_home(monkeypatch, tmp_path):
    assert config.default_data_dir({"SUTRA_DATA_DIR": "~/elsewhere"}) == Path("~/elsewhere").expanduser()
    assert config.default_data_dir({}) == config.project_root() / "data"          # this test runs in a checkout
    monkeypatch.setattr(config, "project_root", lambda: tmp_path)                 # an installed app has no pyproject.toml beside it
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert config.default_data_dir({}) == tmp_path / "home" / ".sutra-pro"


def test_a_relative_data_dir_becomes_absolute(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)                                                   # a team's engine runs elsewhere: `--data-dir ./x` crashed every run
    assert load(data_dir=Path("./demo-data")).data_dir == tmp_path.resolve() / "demo-data"


def test_env_file_defaults_to_the_project_dot_env_and_honours_the_variable():
    assert config.default_env_file({}) == config.project_root() / ".env"
    assert config.default_env_file({"SUTRA_ENV_FILE": "/x/y.env"}) == Path("/x/y.env")


def test_read_env_file(tmp_path):
    path = tmp_path / ".env"
    path.write_text('﻿# comment\n\nPLAIN=one\nexport EXPORTED = "two words"\nQUOTED=\'three\'\nEMPTY=\nNOEQUALS\nPLAIN=later\n', encoding="utf-8")
    assert read_env_file(path) == {"PLAIN": "later", "EXPORTED": "two words", "QUOTED": "three", "EMPTY": ""}
    assert read_env_file(tmp_path / "missing") == {} and read_env_file(None) == {}


@pytest.mark.parametrize("after_equals, value", [
    ("qacomment-VALUE-5544332211 # my key from the vault", "qacomment-VALUE-5544332211"),          # a comment after a space is not the value
    ('"qa\\"escaped\\"-VALUE-7766554433"', 'qa"escaped"-VALUE-7766554433'),                       # an escaped quote inside double quotes
    ('"two # words" # and a comment', "two # words"),                                                  # a hash inside quotes stays
    ("'single # kept' # gone", "single # kept"),
    ('"back\\\\slash"', "back\\slash"),
    ("pass#word", "pass#word"),                                                                        # a hash with no space before it is the value's
    ('say "hi"', 'say "hi"'),                                                                          # the quote marks of an unquoted value stay
    ("trailing-quote\"", 'trailing-quote"'),
    ('"never closed', "never closed"),                                                                  # as before
    ("  spaced  ", "spaced"), ("", ""), ('""', ""),
])
def test_env_value_reads_a_line_the_way_dotenv_tools_do(after_equals, value):
    assert config.env_value(after_equals) == value


def test_the_env_file_values_the_redactor_holds_occur_in_the_text(tmp_path):
    """QA: the parser kept ' # my key from the vault' inside a value and left the escapes in, so the redactor held strings that never
    occur in text and the real secret was stored in clear. Both readings of a line are hidden now."""
    from sutra_app.orchestrator.redact import Redactor
    path = tmp_path / ".env"
    path.write_text('QA_COMMENT=qacomment-VALUE-5544332211 # my key from the vault\nQA_ESC="qa\\"escaped\\"-VALUE-7766554433"\n', encoding="utf-8")
    assert read_env_file(path) == {"QA_COMMENT": "qacomment-VALUE-5544332211", "QA_ESC": 'qa"escaped"-VALUE-7766554433'}
    redactor = Redactor(path, environ={})
    assert redactor("use qacomment-VALUE-5544332211 ok") == "use [redacted] ok"
    assert redactor('use qa"escaped"-VALUE-7766554433 ok') == "use [redacted] ok"
    assert redactor('use qa\\"escaped\\"-VALUE-7766554433 ok') == "use [redacted] ok"                      # as written in the file


def test_override_key_from_environment_then_file_and_env_wins(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(f"J2_OVERRIDE_KEY={KEY}\n", encoding="utf-8")
    from_file = load({"SUTRA_ENV_FILE": str(env_file)})
    assert from_file.override_key.get_secret_value() == KEY
    from_env = load({"SUTRA_ENV_FILE": str(env_file), "J2_OVERRIDE_KEY": "env-wins-key"})
    assert from_env.override_key.get_secret_value() == "env-wins-key"
    assert load({"J2_OVERRIDE_KEY": ""}).override_key is None            # a blank key is no key
    assert load(override_key="kw-key-value").override_key.get_secret_value() == "kw-key-value"


def test_the_secrets_are_in_no_dump_repr_or_public_view(tmp_path):
    s = load({"SUTRA_TOKEN": TOKEN, "J2_OVERRIDE_KEY": KEY})
    shown = [repr(s), str(s), json.dumps(s.model_dump(mode="json")), s.model_dump_json(), json.dumps(s.public()), json.dumps(s.model_dump(mode="python"), default=str)]
    for text in shown:
        assert TOKEN not in text and KEY not in text
    assert "token" not in s.public() and "override_key" not in s.public()
    assert s.token == TOKEN and s.override_key.get_secret_value() == KEY      # still usable by the server


def test_settings_are_closed_and_frozen():
    s = load()
    with pytest.raises(ValidationError):
        Settings(data_dir="/x", env_file="/y", surprise=1)
    with pytest.raises(ValidationError):
        s.port = 1


def test_layout_helpers_and_ensure_dirs(tmp_path):
    s = load({"SUTRA_DATA_DIR": str(tmp_path / "d")})
    assert s.db_path == tmp_path / "d" / "db.sqlite3" and s.log_path == tmp_path / "d" / "logs" / "server.log"
    assert s.department_dir("web") == tmp_path / "d" / "departments" / "web"
    for bad in ("", "..", "a/b", "a\\b"):
        with pytest.raises(SettingsError):
            s.department_dir(bad)
    s.ensure_dirs()
    s.ensure_dirs()                                                     # idempotent
    assert (tmp_path / "d" / "logs").is_dir() and (tmp_path / "d" / "departments").is_dir()
    assert oct((tmp_path / "d").stat().st_mode & 0o777) == "0o700"
