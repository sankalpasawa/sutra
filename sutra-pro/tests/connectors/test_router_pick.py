"""The router honours an agent's pick (D131, WP6): `Router.agent_pick(tag) -> Pick | None`.

What is proved: a pick makes its provider the first of the order and its model go through that provider's `resolve_model`; its effort is used for the
picked provider only (a fallback answers with the policy's); a pick that cannot run falls back by policy and the usage note says so; only an agent's own
calls (agent_turn, plan, judge, agent_chat) look at it, and the engine's reader is never asked for a call of a chat session; the pick is read once per
request, so a change applies from the agent's next call, never in the middle of one or of its retry; with no pick (or a broken reader) nothing changes.

A pick the caller resolved and put in `RouteContext.pick` (the owner's question to a function, D149) is used as it is, for a call that carries a session id
too: it decides before the session's own provider, it falls back with the same note, and it is ignored for a purpose outside the governed ones."""
from __future__ import annotations

import sys

import pytest

from sutra_app.connectors.claude import ClaudeConnector
from sutra_app.connectors.codex import CodexConnector
from sutra_app.connectors.models import AskRequest, AuthStatus, ConnectorConfig, JsonRequest, Pick, RouteContext
from sutra_app.connectors.policy import parse_policy
from sutra_app.connectors.router import PICK_PURPOSES, Plan, Router
from sutra_app.connectors.stub import StubConnector
from sutra_app.connectors.usage import MemoryUsageSink
from sutra_app.engine.port import CallTag


def policy(claude=None, codex=None, **defaults):
    base = {"order": ["claude", "codex"], "effort_json": "low", "effort_text": "high", "timeout_s": 900, "max_attempts": 2,
            "retry_delays_s": [2, 5], "repair_rounds": 2, "max_calls_per_request": 6, "fallback_on_invalid_json": False,
            "tool_profile": "none", "idle_timeout_s": 120}
    base.update(defaults)
    return parse_policy({"version": 1, "providers": {"claude": {"model": "sonnet", "max_concurrency": 4, **(claude or {})},
                                                     "codex": {"model": "gpt-5.6-luna", "max_concurrency": 2, **(codex or {})}},
                         "defaults": base, "rules": [], "rates": {}})


class Named(StubConnector):
    """A stub under the name claude or codex that remembers the model and effort of every call it is given."""

    def __init__(self, name, cfg, **kw):
        super().__init__(cfg, **kw)
        self.name = name
        self.signed_in = True
        self.got = []

    def resolve_model(self, requested):
        return requested or f"{self.name}-default"

    def probe_auth(self):
        return AuthStatus(provider=self.name, installed=True, signed_in=self.signed_in, billing="subscription", checked_at=self._clock())

    def call_text(self, prompt, **kw):
        self.got.append({"model": kw.get("model"), "effort": kw.get("effort")})
        return super().call_text(prompt, **kw)


class Rig:
    def __init__(self, tmp_path, pick=None, **kw):
        cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work", claude_exe=sys.executable, codex_exe=sys.executable)
        self.claude, self.codex = Named("claude", cfg), Named("codex", cfg)
        self.sink, self.events, self.asked = MemoryUsageSink(), [], []
        self.router = Router({"claude": self.claude, "codex": self.codex}, policy(), usage_sink=self.sink, sleep=lambda s: None, rng=lambda: 0.0,
                             events=lambda t, d: self.events.append((t, d)), **kw)
        self.current = pick
        self.router.agent_pick = self._reader

    def _reader(self, tag):
        self.asked.append(tag.function)
        return self.current(tag) if callable(self.current) else self.current

    def ask(self, function="identity", purpose="agent_turn", session_id=None, progress=None, pick=None):
        """One text call; the answer is the name of the provider that answered (the stubs all say `stub` in the turn, the usage row says who).
        `pick` is the pick the caller resolved and carries in the context (D149)."""
        self.router.ask(AskRequest(user="hello", kind="text",
                                   ctx=RouteContext(tag=CallTag(function=function, purpose=purpose), session_id=session_id, pick=pick)), progress)
        return self.row().provider

    def row(self):
        return self.sink.rows[-1]


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


def plan_of(rig, function="identity", purpose="agent_turn"):
    return rig.router.plan(AskRequest(user="x", kind="text", ctx=RouteContext(tag=CallTag(function=function, purpose=purpose))))


# ---- Plan -----------------------------------------------------------------------------------------------------------------------

def test_effort_for_is_the_picks_effort_for_the_picked_provider_only(rig):
    rig.current = Pick(provider="codex", model="gpt-5.6-luna", effort="medium")
    plan = plan_of(rig)
    assert isinstance(plan, Plan) and plan.pick == rig.current
    assert plan.effort_for("codex") == "medium" and plan.effort_for("claude") == plan.resolved.effort == "high"


def test_a_pick_with_no_effort_leaves_the_policys(rig):
    rig.current = Pick(provider="codex")
    plan = plan_of(rig)
    assert plan.effort_for("codex") == plan.resolved.effort and plan.models["codex"] == "gpt-5.6-luna"


def test_without_a_pick_the_plan_is_the_policys(rig):
    plan = plan_of(rig)
    assert plan.pick is None and plan.pick_miss is None and plan.order == ("claude", "codex") and plan.effort_for("claude") == plan.resolved.effort


# ---- the pick decides ---------------------------------------------------------------------------------------------------------------

def test_the_picked_provider_goes_first_with_its_model_and_effort(rig):
    rig.current = Pick(provider="codex", model="gpt-5.6-terra", effort="xhigh")
    plan = plan_of(rig)
    assert plan.order == ("codex", "claude") and plan.models == {"codex": "gpt-5.6-terra", "claude": "sonnet"}
    assert rig.ask() == "codex" and rig.codex.got == [{"model": "gpt-5.6-terra", "effort": "xhigh"}] and rig.claude.got == []
    assert rig.row().detail["note"] is None


def test_the_picks_model_goes_through_that_providers_resolve_model(tmp_path):
    seen = []

    class Resolving(Named):
        def resolve_model(self, requested):
            seen.append((self.name, requested))
            return f"{self.name}:{requested}"

    cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work", claude_exe=sys.executable, codex_exe=sys.executable)
    router = Router({"claude": Resolving("claude", cfg), "codex": Resolving("codex", cfg)}, policy())
    router.agent_pick = lambda tag: Pick(provider="claude", model="haiku", effort="low")
    plan = router.plan(AskRequest(user="x", kind="text", ctx=RouteContext(tag=CallTag(function="W-3"))))
    assert plan.models == {"claude": "claude:haiku", "codex": "codex:gpt-5.6-luna"}      # the pick's model for its provider, the policy's for the other
    assert ("codex", "haiku") not in seen


def test_the_run_wide_default_reaches_an_agent_with_none_of_its_own(rig):
    rig.current = lambda tag: Pick(provider="codex", model="m1", effort="low") if tag.function == "identity" else Pick(provider="claude", model="haiku")
    assert rig.ask("identity") == "codex" and rig.ask("W-2") == "claude"
    assert rig.claude.got[-1] == {"model": "haiku", "effort": "high"} and rig.asked == ["identity", "W-2"]


# ---- the effort stays with the picked provider --------------------------------------------------------------------------------------------

def test_a_fallback_answers_with_the_policys_effort_not_the_picks(rig):
    rig.current = Pick(provider="claude", model="haiku", effort="max")
    rig.claude.fail_next("quota")
    assert rig.ask() == "codex" and rig.claude.got == [{"model": "haiku", "effort": "max"}]
    assert rig.codex.got == [{"model": "gpt-5.6-luna", "effort": "high"}]
    assert rig.row().detail["note"] == "claude out of quota, answered by codex"


# ---- the pick cannot run --------------------------------------------------------------------------------------------------------------------

def test_a_pick_that_cannot_run_falls_back_by_policy_and_the_note_says_so(rig):
    rig.codex.signed_in = False
    rig.current = Pick(provider="codex", model="gpt-5.6-luna", effort="low")
    progress = []
    answered = rig.ask(progress=progress.append)
    note = "your choice for identity (codex) could not run: not signed in; claude answered"
    assert answered == "claude" and rig.claude.got == [{"model": "sonnet", "effort": "high"}]       # the policy's model and effort answer
    assert rig.row().detail["note"] == note and {"note": note} in progress
    event, = [d for t, d in rig.events if t == "connector.choice_unavailable"]
    assert event["agent"] == "identity" and event["wanted"] == "codex" and event["used"] == "claude" and "not signed in" in event["reason"]


def test_a_picked_model_the_provider_refuses_falls_back_too(tmp_path):
    class Strict(Named):
        def resolve_model(self, requested):
            if requested == "nonsense model":
                from sutra_app.connectors.errors import InvalidRequestError
                raise InvalidRequestError("'nonsense model' is not a usable model name", provider=self.name)
            return super().resolve_model(requested)

    cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work", claude_exe=sys.executable, codex_exe=sys.executable)
    sink = MemoryUsageSink()
    router = Router({"claude": Strict("claude", cfg), "codex": Strict("codex", cfg)}, policy(), usage_sink=sink)
    router.agent_pick = lambda tag: Pick(provider="codex", model="nonsense model")
    router.ask(AskRequest(user="x", kind="text", ctx=RouteContext(tag=CallTag(function="audit", purpose="judge"))))
    assert sink.rows[0].provider == "claude" and sink.rows[0].detail["note"].startswith("your choice for audit (codex) could not run:")


def test_when_the_pick_cannot_run_and_the_policys_own_choice_fails_the_request_fails_as_it_always_did(rig):
    rig.codex.signed_in = False
    rig.current = Pick(provider="codex")
    rig.claude.fail_next("quota")
    rig.codex.fail_next("quota")
    with pytest.raises(Exception):
        rig.ask()                                                        # claude (the policy's) runs out too, codex was not usable: nothing answers
    assert rig.row().ok is False


def test_a_pick_on_a_provider_this_app_is_limited_away_from_says_so(tmp_path):
    cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work", claude_exe=sys.executable, codex_exe=sys.executable)
    sink = MemoryUsageSink()
    router = Router({"claude": Named("claude", cfg)}, policy(), usage_sink=sink, connector="claude")
    router.agent_pick = lambda tag: Pick(provider="codex")
    router.ask(AskRequest(user="x", kind="text", ctx=RouteContext(tag=CallTag(function="identity"))))
    assert sink.rows[0].detail["note"] == "your choice for identity (codex) could not run: this app is set to use only claude; claude answered"


# ---- which calls look at it ----------------------------------------------------------------------------------------------------------------------

def test_the_purposes_an_agents_pick_governs():
    assert PICK_PURPOSES == ("agent_turn", "plan", "judge", "agent_chat")


@pytest.mark.parametrize("purpose,governed", [("agent_turn", True), ("plan", True), ("judge", True), ("agent_chat", True), ("summary", False),
                                              ("template", False), ("review", False), ("change", False), ("chat_plan", False), ("chat", False)])
def test_only_an_agents_own_calls_follow_the_pick(rig, purpose, governed):
    rig.current = Pick(provider="codex", model="gpt-5.6-terra", effort="low")
    assert (rig.ask(purpose=purpose) == "codex") is governed and bool(rig.asked) is governed


def test_a_call_of_a_chat_session_never_asks_for_a_pick(rig):
    rig.current = Pick(provider="codex")
    assert rig.ask(session_id="cs_1") == "claude" and rig.asked == []


def test_the_org_agents_json_call_is_not_governed(rig):
    rig.current = Pick(provider="codex")
    rig.router.call_json(JsonRequest(user="p", ctx=RouteContext(tag=CallTag(function="chat_agent", purpose="chat_plan"))))
    assert rig.row().provider == "claude" and rig.asked == []


def test_a_json_call_of_an_agent_follows_the_pick_too(rig):
    rig.current = Pick(provider="codex")
    rig.router.call_json(JsonRequest(user="p", ctx=RouteContext(tag=CallTag(function="identity", purpose="plan"))))
    assert rig.row().provider == "codex" and rig.asked == ["identity"]


# ---- a pick the caller resolved: RouteContext.pick (D149) -----------------------------------------------------------------------------------------

CODEX_PICK = Pick(provider="codex", model="gpt-5.6-terra", effort="xhigh")


def plan_with(rig, pick, function="audit", purpose="agent_chat", session_id="cs_1"):
    return rig.router.plan(AskRequest(user="x", kind="text", ctx=RouteContext(tag=CallTag(function=function, purpose=purpose), session_id=session_id, pick=pick)))


def test_the_context_pick_of_a_call_that_belongs_to_a_session_decides_with_its_model_and_effort(rig):
    assert rig.ask("audit", "agent_chat", session_id="cs_1", pick=CODEX_PICK) == "codex"
    assert rig.codex.got == [{"model": "gpt-5.6-terra", "effort": "xhigh"}] and rig.claude.got == []
    row = rig.row()
    assert (row.session_id, row.fn, row.purpose, row.detail["note"]) == ("cs_1", "audit", "agent_chat", None)
    assert rig.asked == []                                               # the engine's reader is for calls with no session: it was not asked


def test_the_plan_of_a_context_pick_holds_the_pick_and_its_effort_for_the_picked_provider_only(rig):
    plan = plan_with(rig, Pick(provider="codex", model="gpt-5.6-terra", effort="medium"))
    assert plan.order == ("codex", "claude") and plan.pick == Pick(provider="codex", model="gpt-5.6-terra", effort="medium")
    assert plan.models == {"codex": "gpt-5.6-terra", "claude": "sonnet"}
    assert plan.effort_for("codex") == "medium" and plan.effort_for("claude") == plan.resolved.effort


def test_the_context_pick_goes_before_the_sessions_own_provider_and_the_engines_reader(rig):
    rig.router.choice_source = lambda sid: "claude"                      # the session's own pill says claude
    rig.current = Pick(provider="claude", model="haiku")                 # and so does the engine's reader
    assert rig.ask("audit", "agent_chat", session_id="cs_1", pick=CODEX_PICK) == "codex"
    assert rig.asked == [] and rig.events == []                          # the session's choice was not overruled with a "pill could not run" event


def test_a_context_pick_that_cannot_run_falls_back_by_policy_with_the_usual_note_and_names_the_session(rig):
    rig.codex.signed_in = False
    progress = []
    answered = rig.ask("audit", "agent_chat", session_id="cs_1", progress=progress.append, pick=Pick(provider="codex", model="gpt-5.6-luna", effort="low"))
    note = "your choice for audit (codex) could not run: not signed in; claude answered"
    assert answered == "claude" and rig.claude.got == [{"model": "sonnet", "effort": "high"}]         # the policy's model and effort answer
    assert rig.row().detail["note"] == note and {"note": note} in progress
    event, = [d for t, d in rig.events if t == "connector.choice_unavailable"]
    assert (event["session_id"], event["agent"], event["wanted"], event["used"]) == ("cs_1", "audit", "codex", "claude")


def test_a_context_pick_the_policy_cannot_serve_either_fails_like_any_request(rig):
    rig.codex.signed_in = False
    rig.claude.fail_next("quota")
    with pytest.raises(Exception):
        rig.ask("audit", "agent_chat", session_id="cs_1", pick=Pick(provider="codex"))
    assert rig.row().ok is False and rig.row().session_id == "cs_1"


@pytest.mark.parametrize("purpose", ["summary", "template", "review", "change", "chat_plan", "chat"])
def test_a_context_pick_is_ignored_for_a_purpose_outside_the_governed_ones(rig, purpose):
    assert plan_with(rig, CODEX_PICK, purpose=purpose).pick is None
    assert rig.ask("audit", purpose, session_id="cs_1", pick=CODEX_PICK) == "claude" and rig.codex.got == []


def test_a_context_pick_outside_the_governed_purposes_leaves_the_sessions_own_provider_in_charge(rig):
    rig.router.choice_source = lambda sid: "codex"
    assert rig.ask("audit", "chat", session_id="cs_1", pick=Pick(provider="claude")) == "codex"       # the old path: the pill of the session


def test_a_context_pick_with_no_provider_is_default_and_the_session_or_the_policy_answers(rig):
    assert plan_with(rig, Pick()).pick is None
    assert rig.ask("audit", "agent_chat", session_id="cs_1", pick=Pick()) == "claude" and rig.row().detail["note"] is None
    rig.router.choice_source = lambda sid: "codex"                       # the session's own choice is then the one that counts, as before
    assert rig.ask("audit", "agent_chat", session_id="cs_1", pick=Pick(model="haiku")) == "codex" and rig.asked == []


def test_without_a_context_pick_a_session_call_is_what_it_always_was(rig):
    rig.current = Pick(provider="codex")                                 # the engine's reader would say codex ...
    assert rig.ask("audit", "agent_chat", session_id="cs_1") == "claude" and rig.asked == []      # ... but a call of a session never asks it
    rig.router.choice_source = lambda sid: "codex"
    assert rig.ask("audit", "agent_chat", session_id="cs_1") == "codex"


def test_a_context_pick_on_a_provider_this_app_is_limited_away_from_says_so(tmp_path):
    cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work", claude_exe=sys.executable, codex_exe=sys.executable)
    sink = MemoryUsageSink()
    router = Router({"claude": Named("claude", cfg)}, policy(), usage_sink=sink, connector="claude")
    router.ask(AskRequest(user="x", kind="text", ctx=RouteContext(tag=CallTag(function="audit", purpose="agent_chat"), session_id="cs_1",
                                                                   pick=Pick(provider="codex"))))
    assert sink.rows[0].detail["note"] == "your choice for audit (codex) could not run: this app is set to use only claude; claude answered"


# ---- a change applies at the agent's next call ----------------------------------------------------------------------------------------------

def test_a_change_applies_from_the_next_call(rig):
    rig.current = Pick(provider="codex", model="a", effort="low")
    first = rig.ask()
    rig.current = Pick(provider="claude", model="b", effort="max")
    second = rig.ask()
    rig.current = None
    third = rig.ask()
    assert [first, second, third] == ["codex", "claude", "claude"]
    assert rig.codex.got == [{"model": "a", "effort": "low"}] and rig.claude.got == [{"model": "b", "effort": "max"}, {"model": "sonnet", "effort": "high"}]


def test_the_pick_is_read_once_per_request_so_a_retry_keeps_it(rig):
    rig.current = lambda tag: Pick(provider="claude", model=f"m{len(rig.asked)}", effort="low")
    rig.claude.fail_next("overloaded")                                   # the first try fails and is retried after the policy's delay
    assert rig.ask() == "claude" and rig.asked == ["identity"]       # asked once, not once per try
    assert rig.claude.got == [{"model": "m1", "effort": "low"}, {"model": "m1", "effort": "low"}]


# ---- nothing changes without a pick ----------------------------------------------------------------------------------------------------------------

def test_a_reader_that_fails_or_answers_nothing_leaves_the_policy(rig, caplog):
    def boom(tag):
        raise RuntimeError("the file is gone")

    rig.current = boom
    assert rig.ask() == "claude"
    rig.current = lambda tag: "not a pick"
    assert rig.ask() == "claude"
    rig.current = Pick(provider="")                                      # "Default": nobody chose
    assert rig.ask() == "claude"
    assert rig.row().detail["note"] is None


def test_no_reader_at_all_is_the_old_router(tmp_path):
    rig = Rig(tmp_path)
    rig.router.agent_pick = None
    rig.current = Pick(provider="codex")
    assert rig.ask() == "claude" and rig.asked == []


# ---- the real CLIs: the flags the pick reaches ----------------------------------------------------------------------------------------------------

def value(argv, flag):
    return argv[argv.index(flag) + 1]


def real_router(fake, tmp_path):
    cfg = ConnectorConfig(**fake.config_kwargs(tmp_path))
    return Router({"claude": ClaudeConnector(cfg), "codex": CodexConnector(cfg)}, policy(), sleep=lambda s: None)


def test_the_picks_model_and_effort_reach_the_claude_argv_and_only_for_that_agent(fake, tmp_path):
    fake.sequence("ok_plain").reply(text="r")
    router = real_router(fake, tmp_path)
    router.agent_pick = lambda tag: Pick(provider="claude", model="haiku", effort="low") if tag.function == "W-3" else None
    try:
        for function in ("W-3", "identity"):
            router.ask(AskRequest(user="hello", kind="text", ctx=RouteContext(tag=CallTag(function=function))))
        picked, other = [c["argv"] for c in fake.model_calls("claude")]
        assert (value(picked, "--model"), value(picked, "--effort")) == ("haiku", "low")
        assert (value(other, "--model"), value(other, "--effort")) == ("sonnet", "high")
    finally:
        router.close()


def test_the_picks_effort_reaches_the_codex_argv(fake, tmp_path):
    fake.sequence("ok_plain", cli="codex").reply(text="r")
    router = real_router(fake, tmp_path)
    router.agent_pick = lambda tag: Pick(provider="codex", effort="medium")
    try:
        router.ask(AskRequest(user="hello", kind="text", ctx=RouteContext(tag=CallTag(function="identity"))))
        call, = fake.model_calls("codex")
        assert 'model_reasoning_effort="medium"' in call["argv"] and fake.model_calls("claude") == []
    finally:
        router.close()


def test_a_signed_out_pick_falls_back_with_the_note_on_the_real_connectors(fake, tmp_path):
    fake.auth(codex="signed_out")
    fake.sequence("ok_plain", cli="claude").reply(text="from claude")
    router = real_router(fake, tmp_path)
    sink = MemoryUsageSink()
    router.usage_sink = sink
    router.agent_pick = lambda tag: Pick(provider="codex", model="gpt-5.6-luna", effort="low")
    try:
        turn = router.ask(AskRequest(user="hello", kind="text", ctx=RouteContext(tag=CallTag(function="identity"))))
        assert turn.provider == "claude" and sink.rows[0].detail["note"].startswith("your choice for identity (codex) could not run: not signed in; claude answered")
        argv = fake.model_calls("claude")[0]["argv"]
        assert (value(argv, "--model"), value(argv, "--effort")) == ("sonnet", "high")
    finally:
        router.close()


def test_a_context_picks_model_and_effort_reach_the_claude_argv_of_a_call_that_belongs_to_a_session(fake, tmp_path):
    fake.sequence("ok_plain").reply(text="r")
    router = real_router(fake, tmp_path)
    try:
        router.ask(AskRequest(user="hello", kind="text", ctx=RouteContext(tag=CallTag(function="audit", purpose="agent_chat"), session_id="cs_1",
                                                                          pick=Pick(provider="claude", model="haiku", effort="low"))))
        argv = fake.model_calls("claude")[0]["argv"]
        assert (value(argv, "--model"), value(argv, "--effort")) == ("haiku", "low") and fake.model_calls("codex") == []
    finally:
        router.close()


def test_a_context_picks_effort_reaches_the_codex_argv_and_a_signed_out_pick_falls_back_on_the_real_connectors(fake, tmp_path):
    fake.sequence("ok_plain", cli="codex").reply(text="r")
    router = real_router(fake, tmp_path)
    try:
        router.ask(AskRequest(user="hello", kind="text", ctx=RouteContext(tag=CallTag(function="audit", purpose="agent_chat"), session_id="cs_1",
                                                                          pick=Pick(provider="codex", effort="medium"))))
        call, = fake.model_calls("codex")
        assert 'model_reasoning_effort="medium"' in call["argv"] and fake.model_calls("claude") == []
    finally:
        router.close()
