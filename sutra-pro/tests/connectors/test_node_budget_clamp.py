"""One builder call of a step is bounded by the dollars the step has left (D387): the router lowers the call's `--max-budget-usd` (the engine asks for $2 a call) to the node meter's remaining allowance,
which the host set at the step's start from the project's dollars and the owner's monthly limit (real limits file, real ledger); with nothing left no program is started."""
from __future__ import annotations

import os
import time

import pytest

from sutra_app.config import Settings
from sutra_app.connectors.claude import ClaudeConnector
from sutra_app.connectors.errors import EnvelopeExceededError
from sutra_app.connectors.models import ConnectorConfig
from sutra_app.connectors.node_tools import NodeRights
from sutra_app.connectors.policy import parse_policy
from sutra_app.connectors.router import Router
from sutra_app.engine.llm import NodeMeter
from sutra_app.engine.port import CallTag, CompletionRequest, ToolGrant
from sutra_app.orchestrator.db import Database
from sutra_app.orchestrator.limits import LIMITS_FILE, Limits, spend_status
from sutra_app.orchestrator.testing import EventCollector, FakeClock

TAG = CallTag(function="W-1", role="builder", node_id="nd_0123456789ab", node_role="worker")
POLICY = parse_policy({"version": 1, "providers": {"claude": {"model": "sonnet", "max_concurrency": 4}},
                       "defaults": {"order": ["claude"], "effort_json": "low", "effort_text": "high", "timeout_s": 900, "max_attempts": 2, "retry_delays_s": [2, 5], "repair_rounds": 2,
                                    "max_calls_per_request": 6, "fallback_on_invalid_json": False, "tool_profile": "none", "idle_timeout_s": 120}, "rules": [], "rates": {}})


def value(argv, flag):
    return argv[argv.index(flag) + 1]


@pytest.fixture
def month(tmp_path):
    """A real limits file and a real ledger: a $3 month with $2.60 spent, so a step has $0.40 left."""
    settings = Settings.load({}, data_dir=tmp_path / "data", token="t" * 24, env_file=tmp_path / "none.env", live_v1=False)
    clock = FakeClock()
    db = Database(settings.db_path, EventCollector(), clock=clock)
    db.migrate()
    limits = Limits(settings.data_dir / LIMITS_FILE, db, quotas=lambda: {}, clock=clock)
    now = time.time()
    limits.update(monthly_usd=3.0, now=now)
    with db.tx() as tx:
        tx.conn.execute("INSERT INTO usage_ledger(at, provider, purpose, usd) VALUES (?, 'claude', 'agent_turn', 2.6)", (int(now),))
    yield lambda: max(0.0, limits.monthly_limit() - spend_status(db.conn(), limits.monthly_limit(), now)["spent"])
    db.close()


def router_for(fake, tmp_path):
    router = Router({"claude": ClaudeConnector(ConnectorConfig(**fake.config_kwargs(tmp_path)))}, POLICY, sleep=lambda s: None)
    router.node_rights = NodeRights((0, 1), "none")
    return router


def grant(tmp_path):
    out = os.path.realpath(tmp_path / "run" / "out")
    os.makedirs(out)
    return ToolGrant(tools=("Read", "Write", "Edit"), allow=("Read", "Write", "Edit"), cwd=out, root=os.path.dirname(out), usd=2.0, log_chars=10)


def test_the_call_is_started_with_the_dollars_the_step_has_left(fake, tmp_path, month):
    fake.sequence("ok_plain").reply(text="built")
    left = month()
    assert round(left, 2) == 0.4
    meter = NodeMeter(max_usd=left)                                    # what the host gives the step at its start (the project's and the month's remainder)
    router = router_for(fake, tmp_path)
    try:
        router.complete(CompletionRequest(system="s", user="build", tag=TAG, run_tools=grant(tmp_path), allowance=meter.begin()))
        call, = fake.model_calls("claude")
    finally:
        router.close()
    assert float(value(call["argv"], "--max-budget-usd")) == pytest.approx(0.4, abs=0.001) and call["argv"].count("--max-budget-usd") == 1


def test_what_an_earlier_call_spent_comes_off(fake, tmp_path, month):
    fake.sequence("ok_plain").reply(text="built")
    meter = NodeMeter(max_usd=month())
    meter.begin()
    meter.charge(0.15)
    router = router_for(fake, tmp_path)
    try:
        router.complete(CompletionRequest(system="s", user="build", tag=TAG, run_tools=grant(tmp_path), allowance=meter.begin()))
        argv = fake.model_calls("claude")[0]["argv"]
    finally:
        router.close()
    assert float(value(argv, "--max-budget-usd")) == pytest.approx(0.25, abs=0.001)


def test_a_larger_allowance_leaves_the_engines_own_figure_and_an_ordinary_call_is_untouched(fake, tmp_path):
    fake.sequence("ok_plain").reply(text="built")
    router = router_for(fake, tmp_path)
    try:
        router.complete(CompletionRequest(system="s", user="build", tag=TAG, run_tools=grant(tmp_path), allowance=NodeMeter(max_usd=50.0).begin()))
        node_argv = fake.model_calls("claude")[-1]["argv"]
        os.makedirs(tmp_path / "run2" / "out")
        ordinary = ToolGrant(tools=("Read",), allow=("Read",), cwd=os.path.realpath(tmp_path / "run2" / "out"), root=os.path.realpath(tmp_path / "run2"), usd=2.0, log_chars=10)
        fake.sequence("ok_plain").reply(text="built")
        router.complete(CompletionRequest(system="s", user="build", tag=CallTag(function="W-1", role="builder"), run_tools=ordinary))
        plain_argv = fake.model_calls("claude")[-1]["argv"]
    finally:
        router.close()
    assert float(value(node_argv, "--max-budget-usd")) == 2.0 and float(value(plain_argv, "--max-budget-usd")) == 2.0


def test_with_nothing_left_no_program_is_started(fake, tmp_path):
    fake.sequence("ok_plain").reply(text="built")
    router = router_for(fake, tmp_path)
    try:
        meter = NodeMeter(max_usd=0.4)
        meter.begin()
        meter.charge(0.4)
        allowance = meter._allowance()                                 # the meter itself refuses the next call (NodeCapReached); a router given zero must too
        assert allowance.max_usd == 0.0
        with pytest.raises(EnvelopeExceededError, match="no dollars left"):
            router.complete(CompletionRequest(system="s", user="build", tag=TAG, run_tools=grant(tmp_path), allowance=allowance))
        assert not fake.model_calls("claude")
    finally:
        router.close()
