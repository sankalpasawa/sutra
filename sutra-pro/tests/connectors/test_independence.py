"""Independent audit (GAP2 rules-notes): the checker is not the maker. The router sends Audit's calls to the other closed model than the one that
served the run's builders, when the policy says so, and says so when it could not.

Providers are `Named` stub connectors (no process). The tag is what J2's calls already carry: `W-<n>` for a builder, `audit` for Audit, and the
run id keeps one run's builders apart from another's. Off by default: the first test pins that a plan is then exactly what it was."""
from __future__ import annotations

import sys
import threading

import pytest

from sutra_app.connectors.independence import NOT_INDEPENDENT, RUNS_KEPT, Independence
from sutra_app.connectors.models import AskRequest, AuthStatus, ConnectorConfig, RouteContext
from sutra_app.connectors.policy import load_default_policy, parse_policy
from sutra_app.connectors.router import Router
from sutra_app.connectors.stub import StubConnector
from sutra_app.connectors.usage import MemoryUsageSink
from sutra_app.engine.port import CallTag


def policy(independent=False, order=("claude", "codex")):
    return parse_policy({"version": 1, "providers": {"claude": {"enabled": True, "model": "sonnet", "max_concurrency": 4},
                                                     "codex": {"enabled": True, "model": "gpt-5.6-luna", "max_concurrency": 2}},
                         "defaults": {"order": list(order), "independent_audit": independent}, "rules": [], "rates": {}})


class Named(StubConnector):
    def __init__(self, name, cfg, **kw):
        super().__init__(cfg, **kw)
        self.name = name
        self.signed_in = True

    def resolve_model(self, requested):
        return requested or "scripted"

    def probe_auth(self):
        return AuthStatus(provider=self.name, installed=True, signed_in=self.signed_in, billing="subscription", checked_at=self._clock())


class Rig:
    def __init__(self, tmp_path, pol):
        cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work", claude_exe=sys.executable, codex_exe=sys.executable)
        self.claude, self.codex = Named("claude", cfg), Named("codex", cfg)
        self.sink = MemoryUsageSink()
        self.router = Router({"claude": self.claude, "codex": self.codex}, pol, usage_sink=self.sink, sleep=lambda s: None, rng=lambda: 0.0)

    @staticmethod
    def request(function, run="run-1", **ctx):
        return AskRequest(user="hello", ctx=RouteContext(tag=CallTag(function=function, run_id=run), **ctx))

    def call(self, function, run="run-1", **ctx):
        progress = []
        self.router.ask(self.request(function, run, **ctx), progress.append)
        return self.sink.rows[-1], [p for p in progress if "note" in p]               # the streamed text is not what these tests are about


@pytest.fixture
def make(tmp_path):
    return lambda independent=True, order=("claude", "codex"): Rig(tmp_path, policy(independent, order))


# ---- off by default ------------------------------------------------------------------------------------------------------------------

def test_the_flag_is_off_by_default_and_a_plan_is_then_exactly_what_it_was(make):
    assert parse_policy({"version": 1, "providers": {"claude": {"model": "sonnet", "max_concurrency": 4}}, "defaults": {"order": ["claude"]},
                         "rules": [], "rates": {}}).defaults.independent_audit is False
    rig = make(independent=False)
    row, _ = rig.call("W-1")
    assert row.provider == "claude"                                              # a builder was served by claude ...
    assert rig.router.plan(rig.request("audit")).order == ("claude", "codex")    # ... and the audit's plan is the policy's order, untouched
    row, progress = rig.call("audit")
    assert row.provider == "claude" and row.detail["note"] is None and progress == []


def test_the_shipped_policy_file_leaves_it_off():
    assert load_default_policy().defaults.independent_audit is False


# ---- on --------------------------------------------------------------------------------------------------------------------------------

def test_claude_built_so_codex_audits(make):
    rig = make()
    rig.call("W-1")
    rig.call("W-2")
    assert rig.router.plan(rig.request("audit")).order == ("codex", "claude")
    row, progress = rig.call("audit")
    assert row.provider == "codex" and row.detail["note"] is None and progress == []            # independent: nothing to say
    assert len(rig.claude.calls) == 2 and len(rig.codex.calls) == 1


def test_codex_built_so_claude_audits(make):
    rig = make(order=("codex", "claude"))
    assert rig.call("W-1")[0].provider == "codex"
    assert rig.router.plan(rig.request("audit")).order == ("claude", "codex")
    assert rig.call("audit")[0].provider == "claude"


def test_the_audit_still_runs_and_says_so_when_the_other_model_is_unavailable(make):
    rig = make()
    rig.codex.signed_in = False                                                                  # codex is signed out: it is skipped
    rig.call("W-1")
    plan = rig.router.plan(rig.request("audit"))
    assert plan.order == ("claude",) and plan.skipped and plan.skipped[0][0] == "codex"
    row, progress = rig.call("audit")
    assert row.provider == "claude" and row.ok
    assert row.detail["note"] == NOT_INDEPENDENT and {"note": NOT_INDEPENDENT} in progress     # on the usage row and on J2's progress line


def test_a_note_already_on_the_call_keeps_its_words_and_gains_the_other(make):
    router = make().router
    assert router._independence_note(type("S", (), {"ctx": RouteContext(tag=CallTag(function="audit", run_id="r"))})(), "claude",
                                     "codex overloaded, answered by claude") == "codex overloaded, answered by claude"      # no builder known: unchanged
    router.independence.note(RouteContext(tag=CallTag(function="W-1", run_id="r")), "claude")
    state = type("S", (), {"ctx": RouteContext(tag=CallTag(function="audit", run_id="r"))})()
    assert router._independence_note(state, "claude", "codex overloaded, answered by claude") == f"codex overloaded, answered by claude; {NOT_INDEPENDENT}"
    assert router._independence_note(state, "codex", None) is None


def test_a_pinned_team_keeps_its_model_and_the_note_says_it_was_not_independent(make):
    rig = make()
    rig.router.choice_source = lambda sid: "claude" if sid == "cs_web" else None                 # the chat pill pins the team to claude
    rig.call("W-1", session_id="cs_web")
    plan = rig.router.plan(rig.request("audit", session_id="cs_web"))
    assert plan.order[0] == "claude"                                                             # the pin wins over the soft avoid
    row, _ = rig.call("audit", session_id="cs_web")
    assert row.provider == "claude" and row.detail["note"] == NOT_INDEPENDENT


def test_one_run_s_builders_never_steer_another_run_s_audit(make):
    rig = make()
    rig.call("W-1", run="run-1")
    assert rig.router.plan(rig.request("audit", run="run-2")).order == ("claude", "codex")
    assert rig.router.plan(rig.request("audit", run="run-1")).order == ("codex", "claude")
    assert rig.router.plan(rig.request("audit", run="")).order == ("claude", "codex")             # a call with no run id is never matched


def test_only_a_builder_s_call_counts_and_only_audit_is_steered(make):
    rig = make()
    for function in ("identity", "adaptation", "validator", "chat_agent", "audit"):
        rig.call(function)
    assert rig.router.independence.builders("run-1") == frozenset()                              # no builder has been served yet
    assert rig.router.plan(rig.request("audit")).order == ("claude", "codex")
    rig.call("W-3")
    for function in ("identity", "priority", "W-4"):
        assert rig.router.plan(rig.request(function)).order == ("claude", "codex")              # only Audit is steered


def test_a_model_that_was_skipped_is_not_remembered_as_a_maker(make):
    rig = make()
    rig.claude.signed_in = False
    row, _ = rig.call("W-1")
    assert row.provider == "codex"                                                               # claude was skipped; codex built it
    assert rig.router.independence.builders("run-1") == frozenset({"codex"})
    row, progress = rig.call("audit")                                                            # claude is still signed out: the audit falls back honestly
    assert row.provider == "codex" and row.ok and row.detail["note"] == NOT_INDEPENDENT and {"note": NOT_INDEPENDENT} in progress


# ---- the memory ------------------------------------------------------------------------------------------------------------------------

def ctx(function, run):
    return RouteContext(tag=CallTag(function=function, run_id=run))


def test_the_memory_keeps_only_closed_models_of_builders_with_a_run_id():
    book = Independence()
    book.note(ctx("W-1", "r"), "claude")
    book.note(ctx("W-2", "r"), "codex")
    book.note(ctx("W-3", "r"), "stub")                       # the stub is neither a maker nor a checker
    book.note(ctx("audit", "r"), "codex")                    # an audit's own call is not a maker
    book.note(ctx("W-4", ""), "claude")                      # no run id: nothing to attach it to
    assert book.builders("r") == frozenset({"claude", "codex"}) and book.avoid_for(ctx("audit", "r")) == ["claude", "codex"]
    assert book.builders("nope") == frozenset() and book.avoid_for(ctx("identity", "r")) == [] and book.avoid_for(ctx("audit", "")) == []
    assert book.avoid_for(object()) == []                    # a context without a tag is not an error


def test_the_memory_is_bounded_and_the_newest_runs_stay():
    book = Independence(runs_kept=3)
    for n in range(5):
        book.note(ctx("W-1", f"r{n}"), "claude")
    assert [bool(book.builders(f"r{n}")) for n in range(5)] == [False, False, True, True, True]
    book.note(ctx("W-2", "r2"), "codex")                     # touching a run keeps it
    book.note(ctx("W-1", "r5"), "claude")
    assert book.builders("r2") == frozenset({"claude", "codex"}) and not book.builders("r3")
    assert RUNS_KEPT >= 100


def test_the_memory_is_safe_across_threads():
    book = Independence(runs_kept=50)

    def work(offset):
        for n in range(200):
            book.note(ctx("W-1", f"r{(offset + n) % 80}"), "claude" if n % 2 else "codex")
            book.avoid_for(ctx("audit", f"r{n % 80}"))
    threads = [threading.Thread(target=work, args=(i,)) for i in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(book._built) <= 50


def test_the_flag_is_a_boolean_in_the_closed_policy():
    with pytest.raises(Exception):
        parse_policy({"version": 1, "providers": {"claude": {"model": "sonnet", "max_concurrency": 4}}, "defaults": {"order": ["claude"], "independent_audit": "maybe"},
                      "rules": [], "rates": {}})
    assert policy(True).defaults.independent_audit is True
