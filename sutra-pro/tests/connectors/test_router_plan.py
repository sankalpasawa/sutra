"""Router.plan: order by rule, avoid, pin, every skip reason, NoProviderError, restriction (connectors design 3.6, work package CN-7).

The providers are `Named` stub connectors: StubConnector under the name claude or codex, so nothing starts a process and the
tests control sign-in, billing and capabilities by attributes.
"""
from __future__ import annotations

import sys

import pytest

from sutra_app.connectors.errors import ConnectorError, NoProviderError, QuotaError
from sutra_app.connectors.health import API_KEY_REFUSED, HealthBook
from sutra_app.connectors.models import AskRequest, AuthStatus, Capabilities, ConnectorConfig, RouteContext
from sutra_app.connectors.policy import parse_policy
from sutra_app.connectors.router import Router, mode_from_env
from sutra_app.connectors.stub import StubConnector
from sutra_app.engine.port import CallTag


def policy(rules=(), claude=None, codex=None, order=("claude", "codex"), **defaults):
    base = {"order": list(order), "effort_json": "low", "effort_text": "high", "timeout_s": 900, "max_attempts": 2,
            "retry_delays_s": [2, 5], "repair_rounds": 2, "max_calls_per_request": 6, "fallback_on_invalid_json": False,
            "tool_profile": "none", "idle_timeout_s": 120}
    base.update(defaults)
    return parse_policy({"version": 1, "providers": {"claude": {"enabled": True, "model": "sonnet", "max_concurrency": 4, **(claude or {})},
                                                     "codex": {"enabled": True, "model": "gpt-5.6-luna", "max_concurrency": 2, **(codex or {})}},
                         "defaults": base, "rules": list(rules), "rates": {}})


class Named(StubConnector):
    """A stub that calls itself claude or codex. `auth` is what its status command would say."""

    def __init__(self, name, cfg, **kw):
        super().__init__(cfg, **kw)
        self.name = name
        self.auth = dict(signed_in=True, billing="subscription")
        self.probes = 0

    def resolve_model(self, requested):
        return requested or "scripted"

    def probe_auth(self):
        self.probes += 1
        return AuthStatus(provider=self.name, installed=True, version="1.0", checked_at=self._clock(), **self.auth)


@pytest.fixture
def cfg(tmp_path):
    # the executables must exist for `shutil.which`: any real executable will do
    return ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work", claude_exe=sys.executable, codex_exe=sys.executable)


@pytest.fixture
def build(cfg):
    def make(pol=None, names=("claude", "codex"), **kw):
        connectors = {n: Named(n, cfg) for n in names}
        return Router(connectors, pol or policy(), sleep=lambda s: None, rng=lambda: 0.0, **kw), connectors
    return make


def ask(function="", stage=None, **kw):
    return AskRequest(user="hello", ctx=RouteContext(tag=CallTag(function=function, stage=stage), **kw.pop("ctx", {})), **kw)


def test_default_order_is_claude_then_codex(build):
    router, _ = build()
    plan = router.plan(ask())
    assert plan.order == ("claude", "codex") and plan.skipped == ()
    assert plan.models == {"claude": "sonnet", "codex": "gpt-5.6-luna"}


def test_plan_starts_no_process_and_calls_no_model(build):
    router, connectors = build()
    router.plan(ask())
    assert all(c.calls == [] and c.usage().total == 0 for c in connectors.values())


def test_first_matching_rule_sets_the_order(build):
    pol = policy(rules=[{"match": {"function": "audit"}, "order": ["codex", "claude"]},
                        {"match": {"function": "au*"}, "order": ["claude"]}])
    router, _ = build(pol)
    assert router.plan(ask("audit")).order == ("codex", "claude")
    assert router.plan(ask("identity")).order == ("claude", "codex")


def test_rule_resolved_settings_ride_in_the_plan(build):
    pol = policy(rules=[{"match": {"purpose": "summary"}, "effort": "low", "timeout_s": 300}])
    router, _ = build(pol)
    plan = router.plan(AskRequest(user="x", ctx=RouteContext(tag=CallTag(purpose="summary"))))
    assert (plan.resolved.effort, plan.resolved.timeout_s, plan.resolved.rule_index) == ("low", 300, 0)


def test_avoid_providers_are_tried_last(build):
    router, _ = build()
    assert router.plan(ask(ctx={"avoid": ["claude"]})).order == ("codex", "claude")


def test_a_pinned_provider_goes_first_even_when_the_rule_left_it_out(build):
    pol = policy(rules=[{"match": {"function": "audit"}, "order": ["claude"]}])
    router, _ = build(pol)
    assert router.plan(ask("audit"), pinned="codex").order == ("codex", "claude")
    assert router.plan(ask(), pinned="codex").order == ("codex", "claude")


def test_a_pinned_provider_that_is_skipped_is_not_forced(build):
    router, connectors = build()
    connectors["codex"].auth["signed_in"] = False
    assert router.plan(ask(), pinned="codex").order == ("claude",)


def test_provider_missing_from_connectors(build):
    router, _ = build(names=("claude",))
    plan = router.plan(ask())
    assert plan.order == ("claude",) and plan.skipped == (("codex", "not configured"),)


def test_provider_disabled_in_the_policy(build):
    router, _ = build(policy(codex={"enabled": False}))
    assert router.plan(ask()).skipped == (("codex", "disabled in the routing policy"),)


def test_provider_absent_from_the_policy_is_refused_but_the_stub_is_not(cfg):
    pol = policy(order=("claude",))
    stub = StubConnector(cfg)
    router = Router({"claude": Named("claude", cfg), "stub": stub}, pol)
    assert router.plan(ask()).order == ("claude",)
    assert router.plan(ask(), pinned="stub").order == ("stub", "claude")
    only_stub = Router({"codex": Named("codex", cfg)}, parse_policy({**pol.model_dump(mode="json"), "providers": {"claude": {"model": "sonnet"}}}))
    with pytest.raises(NoProviderError) as e:
        only_stub.plan(ask())
    assert e.value.detail["skipped"] == [{"provider": "claude", "reason": "not configured"}]


def test_cli_missing_gives_the_install_hint(cfg):
    cfg2 = cfg.model_copy(update={"claude_exe": "/nonexistent/claude-cli"})
    router = Router({"claude": Named("claude", cfg2), "codex": Named("codex", cfg2.model_copy(update={"codex_exe": "/nonexistent/codex"}))}, policy())
    with pytest.raises(NoProviderError) as e:
        router.plan(ask())
    reasons = dict(map(tuple, ((s["provider"], s["reason"]) for s in e.value.detail["skipped"])))
    assert reasons["claude"] == "CLI not found on PATH (install it and run `claude` once)"
    assert reasons["codex"] == "CLI not found on PATH (install it and run `codex login`)"
    assert e.value.user_message() == ("No model is available: Claude: CLI not found on PATH (install it and run `claude` once); "
                                      "Codex: CLI not found on PATH (install it and run `codex login`)")


def test_signed_out_providers_say_how_to_sign_in(build):
    router, connectors = build()
    connectors["claude"].auth["signed_in"] = False
    connectors["codex"].auth["signed_in"] = False
    with pytest.raises(NoProviderError) as e:
        router.plan(ask())
    assert [s["reason"] for s in e.value.detail["skipped"]] == ["not signed in: run `claude auth login`",
                                                               "not signed in: use Sign in or run `codex login`"]


def test_an_api_key_login_is_refused_with_no_override(build):
    router, connectors = build()
    connectors["codex"].auth["billing"] = "api_key"
    plan = router.plan(ask())
    assert plan.order == ("claude",) and plan.skipped == (("codex", API_KEY_REFUSED),)


def test_an_unknown_sign_in_state_and_billing_are_allowed(build):
    router, connectors = build()
    connectors["claude"].auth.update(signed_in=None, billing="unknown")
    assert router.plan(ask()).order == ("claude", "codex")


def test_a_provider_in_cooldown_is_skipped_until_it_ends(cfg):
    now = [1000.0]
    health = HealthBook(clock=lambda: now[0])
    router = Router({n: Named(n, cfg) for n in ("claude", "codex")}, policy(), health=health, clock=lambda: now[0])
    health.failed("claude", QuotaError("limit", provider="claude", resets_at=1600.0))
    plan = router.plan(ask())
    assert plan.order == ("codex",) and plan.skipped[0][0] == "claude" and "usage limit reached, retry after" in plan.skipped[0][1]
    now[0] = 1601.0
    assert router.plan(ask()).order == ("claude", "codex")


def test_images_need_a_provider_that_takes_them(build, tmp_path):
    router, connectors = build()
    connectors["claude"].capabilities = Capabilities(native_schema=True, resume=True, images=False, partials=True, mcp=False)
    img = tmp_path / "a.png"
    img.write_bytes(b"x")
    plan = router.plan(ask(images=[str(img)]))
    assert plan.order == ("codex",) and plan.skipped == (("claude", "cannot take images"),)


def test_tools_need_a_provider_with_mcp(build):
    router, _ = build()
    with pytest.raises(NoProviderError) as e:                    # the stub has no MCP
        router.plan(ask(tools=("sutra",)))
    assert {s["reason"] for s in e.value.detail["skipped"]} == {"cannot use tools"}


def test_the_policy_tool_profile_counts_as_tools(build):
    router, _ = build(policy(tool_profile="sutra+github"))
    with pytest.raises(NoProviderError):
        router.plan(ask())


def test_nothing_usable_raises_no_provider_error_listing_each_reason(build):
    router, connectors = build()
    connectors["claude"].auth["signed_in"] = False
    router.policy.providers["codex"].enabled = False
    with pytest.raises(NoProviderError) as e:
        router.plan(ask())
    assert e.value.code == "no_model" and not e.value.fallback_ok
    assert e.value.user_message() == ("No model is available: Claude: not signed in: run `claude auth login`; "
                                      "Codex: disabled in the routing policy")


def test_the_router_never_falls_back_to_the_stub_on_its_own(cfg):
    router = Router({"claude": Named("claude", cfg), "stub": StubConnector(cfg)}, policy(order=("claude",)))
    router._connectors["claude"].auth["signed_in"] = False
    with pytest.raises(NoProviderError):
        router.plan(ask())


def test_an_unusable_policy_model_name_is_a_skip_reason(build):
    router, _ = build(policy(claude={"model": "bad model!"}))
    def refuse(requested):
        from sutra_app.connectors.errors import InvalidRequestError
        raise InvalidRequestError("'bad model!' is not a usable model name", provider="claude")
    router._connectors["claude"].resolve_model = refuse
    plan = router.plan(ask())
    assert plan.order == ("codex",) and plan.skipped == (("claude", "'bad model!' is not a usable model name"),)


def test_connector_setting_restricts_the_order(build):
    router, _ = build(connector="codex")
    assert router.plan(ask()).order == ("codex",)
    assert router.mode == "live"


def test_restriction_beats_the_rule_order(build):
    router, _ = build(policy(rules=[{"match": {"function": "audit"}, "order": ["claude"]}]), connector="codex")
    assert router.plan(ask("audit")).order == ("codex",)


def test_restricting_to_something_not_configured_fails_with_the_reason(build):
    router, _ = build(names=("claude",), connector="codex")
    with pytest.raises(NoProviderError) as e:
        router.plan(ask())
    assert e.value.detail["skipped"] == [{"provider": "codex", "reason": "not configured"}]


def test_offline_means_the_stub_only(cfg):
    router = Router({"claude": Named("claude", cfg), "stub": StubConnector(cfg)}, policy(), offline=True)
    assert router.plan(ask()).order == ("stub",)
    assert router.plan(ask(), pinned="claude").order == ("stub",)
    assert router.mode == "offline"
    assert router.status().mode == "offline"


def test_a_bad_connector_name_is_refused(cfg):
    with pytest.raises(ValueError):
        Router({}, policy(), connector="gemini")


def test_mode_from_env():
    assert mode_from_env({}) == ("auto", False)
    assert mode_from_env({"SUTRA_CONNECTOR": " Codex ", "SUTRA_OFFLINE": "1"}) == ("codex", True)
    assert mode_from_env({"SUTRA_OFFLINE": "0"}) == ("auto", False)
    with pytest.raises(ValueError, match="SUTRA_CONNECTOR"):
        mode_from_env({"SUTRA_CONNECTOR": "gemini"})


def test_health_probes_are_cached_between_plans(build):
    router, connectors = build()
    router.plan(ask())
    router.plan(ask())
    assert connectors["claude"].probes == 1


def test_a_failing_status_command_becomes_the_skip_reason(build):
    router, connectors = build()

    def broken():
        raise ConnectorError("claude status timed out", provider="claude")
    connectors["claude"].probe_auth = broken
    plan = router.plan(ask())
    assert plan.order == ("codex",) and plan.skipped == (("claude", "claude status timed out"),)


def test_status_lists_every_provider_without_a_model_call(build):
    router, connectors = build()
    st = router.status()
    assert [p.name for p in st.providers] == ["claude", "codex"]
    claude = st.providers[0]
    assert (claude.installed, claude.signed_in, claude.billing, claude.version) == (True, True, "subscription", "1.0")
    assert claude.health.state == "ok" and claude.today.calls == 0
    assert st.policy.source == "default" and st.policy.error is None and st.policy.version == 1
    assert all(c.calls == [] for c in connectors.values())


def test_status_reports_a_missing_cli_and_a_policy_error(cfg):
    cfg2 = cfg.model_copy(update={"claude_exe": "/nonexistent/claude"})
    router = Router({"claude": Named("claude", cfg2)}, policy(), policy_source="default", policy_error="policy.json: bad")
    st = router.status()
    assert st.providers[0].installed is False and st.providers[0].detail == "CLI not found on PATH"
    assert st.policy.error == "policy.json: bad"


def test_status_refresh_probes_again(build):
    router, connectors = build()
    router.status()
    router.status()
    assert connectors["claude"].probes == 1
    router.status(refresh=True)
    assert connectors["claude"].probes == 2
