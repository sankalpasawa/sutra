"""build_router (CN-9, connectors design 5.5, S1-contracts-08): settings in, a Router out. The CLIs are the fakes; no model is called."""
from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import pytest

from sutra_app.connectors.claude import ClaudeConnector
from sutra_app.connectors.codex import CodexConnector
from sutra_app.connectors.errors import ConnectorError, NoProviderError
from sutra_app.connectors.factory import REQUIRED_FLAGS, TESTED_VERSIONS, build_router
from sutra_app.connectors.models import AskRequest, ConnectorConfig
from sutra_app.connectors.policy import load_default_policy, user_policy_path
from sutra_app.connectors.usage import MemoryUsageSink


class Events:
    def __init__(self):
        self.items = []

    def __call__(self, type_, data):
        self.items.append((type_, data))

    def of(self, type_):
        return [d for t, d in self.items if t == type_]


@pytest.fixture
def env(fake, tmp_path):
    """make(connector, offline) -> (router, events). The config is built when make is called, so FAKE_* set by the test count."""

    def make(connector="auto", offline=False, **kw):
        cfg = ConnectorConfig(**fake.config_kwargs(tmp_path))
        settings = SimpleNamespace(data_dir=cfg.data_dir, connector=connector, offline=offline)
        events = Events()
        router = build_router(settings, config=cfg, events=events, **kw)
        return router, events

    make.cfg = SimpleNamespace(data_dir=tmp_path / "data")
    return make


def text_request(**kw):
    return AskRequest(user="hello", kind="text", **kw)


def test_auto_mode_with_signed_in_fakes_builds_both_providers(env, fake):
    router, events = env()
    assert sorted(router.connectors) == ["claude", "codex"]
    assert isinstance(router.connectors["claude"], ClaudeConnector) and isinstance(router.connectors["codex"], CodexConnector)
    status = router.status()
    assert status.mode == "live"
    by_name = {p.name: p for p in status.providers}
    assert by_name["claude"].signed_in is True and by_name["codex"].signed_in is True
    assert by_name["claude"].health.state == "ok"
    assert router.plan(text_request()).order == ("claude", "codex")
    assert fake.model_calls() == []                         # nothing called a model


def test_signed_out_clis_leave_no_provider(env, fake):
    fake.auth(claude="signed_out", codex="signed_out")
    router, _ = env()
    status = router.status()
    assert [p.signed_in for p in status.providers] == [False, False]
    assert router.health.state("claude").state == "signed_out"
    with pytest.raises(NoProviderError) as err:
        router.plan(text_request())
    assert "not signed in" in err.value.user_message()


def test_signing_out_of_one_falls_back_to_the_other(env, fake):
    fake.auth(claude="signed_out", codex="signed_in")
    router, _ = env()
    assert router.plan(text_request()).order == ("codex",)


def test_offline_builds_a_stub_only_router_and_starts_no_cli(env, fake):
    router, events = env(offline=True)
    assert list(router.connectors) == ["stub"]
    assert router.mode == "offline"
    turn = router.ask(text_request())
    assert turn.provider == "stub"
    assert fake.calls() == []                               # not even a --help probe
    assert events.of("connector.mode") == [{"mode": "offline"}]


def test_connector_stub_is_stub_only(env, fake):
    router, _ = env(connector="stub")
    assert list(router.connectors) == ["stub"] and fake.calls() == []


@pytest.mark.parametrize("mode", ["claude", "codex"])
def test_a_named_connector_builds_only_that_cli(env, mode):
    router, _ = env(connector=mode)
    assert list(router.connectors) == [mode]
    assert router.plan(text_request()).order == (mode,)


def test_the_mode_event_is_published_once_at_start(env):
    router, events = env()
    assert events.of("connector.mode") == [{"mode": "live"}]


def test_the_wiring_arguments_reach_the_router(env):
    sink = MemoryUsageSink()
    transcripts = object()
    hook = lambda *a: None          # noqa: E731
    router, _ = env(usage_sink=sink, transcripts=transcripts, session_hook=hook)
    assert router.usage_sink is sink and router.transcripts is transcripts and router._session_hook is hook


def test_a_failing_event_callback_does_not_stop_start_up(fake, tmp_path):
    cfg = ConnectorConfig(**fake.config_kwargs(tmp_path))

    def boom(type_, data):
        raise RuntimeError("bus is down")

    router = build_router(SimpleNamespace(data_dir=cfg.data_dir, connector="auto", offline=False), config=cfg, events=boom)
    assert sorted(router.connectors) == ["claude", "codex"]


def test_only_data_dir_connector_and_offline_are_read_from_settings(fake, tmp_path):
    cfg = ConnectorConfig(**fake.config_kwargs(tmp_path))
    seen = []

    class Strict:
        data_dir = cfg.data_dir
        connector = "auto"
        offline = False

        def __getattribute__(self, name):
            if not name.startswith("__"):
                seen.append(name)
            return object.__getattribute__(self, name)

    build_router(Strict(), config=cfg)
    assert sorted(set(seen)) == ["connector", "data_dir", "offline"]


def test_the_environment_is_not_read(env, monkeypatch):
    monkeypatch.setenv("SUTRA_CONNECTOR", "codex")
    monkeypatch.setenv("SUTRA_OFFLINE", "1")
    router, _ = env()
    assert sorted(router.connectors) == ["claude", "codex"] and router.mode == "live"


def test_default_config_uses_the_data_dir_of_the_settings(tmp_path):
    router = build_router(SimpleNamespace(data_dir=tmp_path / "d", connector="stub", offline=False))
    assert router.connectors["stub"].cfg.data_dir == tmp_path / "d"


def test_an_unknown_connector_value_is_refused(tmp_path):
    with pytest.raises(ValueError):
        build_router(SimpleNamespace(data_dir=tmp_path, connector="gpt", offline=False))


def test_a_valid_policy_file_is_used(env):
    path = user_policy_path(env.cfg.data_dir)
    path.parent.mkdir(parents=True)
    policy = load_default_policy().model_dump(mode="json")
    policy["defaults"]["order"] = ["codex", "claude"]
    path.write_text(json.dumps(policy))
    router, _ = env()
    assert router.status().policy.source == "file"
    assert router.plan(text_request()).order == ("codex", "claude")


def test_an_invalid_policy_file_is_not_used_and_the_reason_is_in_the_status(env, caplog):
    path = user_policy_path(env.cfg.data_dir)
    path.parent.mkdir(parents=True)
    path.write_text('{"version": 1, "allow_api_key_billing": true}')
    with caplog.at_level(logging.WARNING, logger="sutra_app.connectors.factory"):
        router, _ = env()
    policy = router.status().policy
    assert policy.source == "default" and policy.error and "routing policy is not valid" in policy.error
    assert router.plan(text_request()).order == ("claude", "codex")
    assert any("not used" in r.message for r in caplog.records)


def test_a_missing_required_flag_marks_the_provider_degraded_and_falls_back(env, fake):
    fake.set(FAKE_HELP_MISSING="--effort")
    router, events = env()
    state = router.health.state("claude")
    assert state.state == "cooldown" and "needed flag" in state.reason and state.until is not None
    assert router.health.state("codex").state == "ok"
    plan = router.plan(text_request())
    assert plan.order == ("codex",)
    assert any(p == "claude" and "needed flag" in why for p, why in plan.skipped)
    announced = events.of("connector.health")
    assert [(e["provider"], e["state"]) for e in announced] == [("claude", "cooldown")]


def test_a_missing_required_codex_flag_marks_codex_degraded(env, fake):
    fake.set(FAKE_HELP_MISSING="--skip-git-repo-check")
    router, _ = env()
    assert router.health.state("codex").state == "cooldown" and router.health.state("claude").state == "ok"


def test_a_missing_optional_flag_does_not_degrade(env, fake):
    fake.set(FAKE_HELP_MISSING="--json-schema,--resume,--mcp-config")
    router, events = env()
    assert router.health.state("claude").state == "ok"
    assert events.of("connector.health") == []


def test_every_required_flag_is_listed_by_the_fake_help(env, fake):
    router, _ = env()
    for name, flags in REQUIRED_FLAGS.items():
        listed = router.connectors[name].flags()
        assert [f for f in flags if not listed.get(f)] == []


def test_a_cli_that_is_not_installed_is_not_degraded(fake, tmp_path):
    kw = fake.config_kwargs(tmp_path)
    kw["claude_exe"] = str(tmp_path / "no-such-claude")
    cfg = ConnectorConfig(**kw)
    events = Events()
    router = build_router(SimpleNamespace(data_dir=cfg.data_dir, connector="auto", offline=False), config=cfg, events=events)
    assert router.health.state("claude").state != "cooldown"
    assert events.of("connector.health") == []
    plan = router.plan(text_request())
    assert plan.order == ("codex",)
    assert any(p == "claude" and "not found" in why for p, why in plan.skipped)


def test_a_different_cli_version_is_logged_as_a_warning(env, fake, caplog):
    fake.set(FAKE_CLAUDE_VERSION="9.9.9")
    with caplog.at_level(logging.WARNING, logger="sutra_app.connectors.factory"):
        env()
    messages = [r.getMessage() for r in caplog.records]
    assert any("claude" in m and "9.9.9" in m and TESTED_VERSIONS["claude"] in m for m in messages)
    assert not any("codex CLI version" in m for m in messages)


def test_the_tested_versions_raise_no_warning(env, caplog):
    with caplog.at_level(logging.WARNING, logger="sutra_app.connectors.factory"):
        env()
    assert [r for r in caplog.records if "version" in r.getMessage()] == []


def test_the_app_redactor_reaches_the_egress_and_scrubs_secret_values_in_a_chat_turn(fake, tmp_path):
    from sutra_app.connectors.chat_models import ChatTurnIn
    from sutra_app.connectors.chat_port import RouterChatPort

    class Secrets:
        def secrets(self):
            return ["custom-token-xyz"]               # matches none of the 13 shapes

    cfg = ConnectorConfig(**fake.config_kwargs(tmp_path))
    router = build_router(SimpleNamespace(data_dir=cfg.data_dir, connector="auto", offline=False), config=cfg, redactor=Secrets())
    assert router.egress.redactor is not None
    RouterChatPort(router).send("cs_fac1", ChatTurnIn(text="please use custom-token-xyz now"))
    assert all("custom-token-xyz" not in str(c) for c in fake.model_calls())
    assert router.egress.rows()[0]["shapes"] == {"secret-value": 1}


# ---- QA direct-chat P3: a CLI that cannot start is not 'a CLI that does not accept a needed flag' ----------------------------------------------------

def _help_cannot_start(monkeypatch):
    """Every `--help` ends with exit 127 and one line on stderr, as a broken node shebang does; the other probes run as before."""
    from sutra_app.connectors.base import ModelConnector
    from sutra_app.connectors.process import ExitInfo
    real = ModelConnector._run_probe

    def run(self, argv, **kw):
        if "--help" in argv:
            return ExitInfo(returncode=127, reason="exit", stderr_tail=f"{self.name}: fatal: cannot start", seconds=0.0, pid=1), []
        return real(self, argv, **kw)

    monkeypatch.setattr(ModelConnector, "_run_probe", run)


def test_a_help_that_could_not_run_says_why_and_is_not_read_as_a_missing_flag(env, fake, monkeypatch):
    _help_cannot_start(monkeypatch)
    router, events = env()
    for name in ("claude", "codex"):
        assert router.health.state(name).state != "cooldown" and router.health.state(name).reason != "the CLI does not accept a needed flag"
        with pytest.raises(ConnectorError, match=rf"--help gave no usable answer \(exit 127\): {name}: fatal: cannot start"):
            router.connectors[name].probe_flags()
        assert router.connectors[name]._flags is None                        # nothing was learned: the next read asks again
    assert events.of("connector.health") == []


def test_a_help_that_ran_and_lacks_a_needed_flag_still_marks_the_provider_degraded(env, fake):
    fake.set(FAKE_HELP_MISSING="--effort")
    router, events = env()
    assert router.health.state("claude").reason == "the CLI does not accept a needed flag"
