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


# ---- the cap is read on every builder call, from the database, read-only (D409, R-2) ------------------------------------------------------------------

@pytest.fixture
def project_world(tmp_path):
    """A migrated database with a project of two steps, the owner's $3 month with $0.60 spent."""
    settings = Settings.load({}, data_dir=tmp_path / "data", token="t" * 24, env_file=tmp_path / "none.env", live_v1=False)
    clock = FakeClock()
    db = Database(settings.db_path, EventCollector(), clock=clock)
    db.migrate()
    limits = Limits(settings.data_dir / LIMITS_FILE, db, quotas=lambda: {}, clock=clock)
    now = int(time.time())
    limits.update(monthly_usd=3.0, now=now)
    with db.tx() as tx:
        tx.conn.execute("INSERT INTO usage_ledger(at, provider, purpose, usd) VALUES (?, 'claude', 'agent_turn', 0.6)", (now,))
        tx.conn.execute("INSERT INTO projects(id, title, status, created_at, budget_usd, caps_json) VALUES ('prj_0123456789ab', 'P', 'running', ?, 2.4, '{\"usd_from_month\": true}')", (now - 5,))
        for n, state in (("a", "running"), ("b", "planned")):
            tx.conn.execute("INSERT INTO agent_nodes(id, project_id, role, runtime, plan_ref, state, created_at) VALUES (?, 'prj_0123456789ab', 'worker', 'engine', ?, ?, ?)", (f"nd_{n * 12}", n, state, now))

    def set_state(state):
        with db.tx() as tx:
            tx.conn.execute("UPDATE agent_nodes SET state = ? WHERE plan_ref = 'b'", (state,))
    yield settings.data_dir, set_state
    db.close()


def test_the_reader_gives_the_project_and_month_remainder_divided_by_the_steps_that_run_now(project_world):
    from sutra_app.connectors.engine_port import live_cap_reader
    data_dir, set_state = project_world
    read = live_cap_reader(str(data_dir), "prj_0123456789ab")
    assert read() == pytest.approx(2.4), "alone: the project's 2.4 (the month has 2.4 left too)"
    set_state("running")
    assert read() == pytest.approx(1.2), "a sibling runs now: half, read again, not frozen"
    set_state("awaiting_approval")
    assert read() == pytest.approx(2.4), "held: no share"
    assert live_cap_reader(str(data_dir), "prj_ffffffffffff")() == pytest.approx(2.4), "a project the database does not know: the month alone"


def test_the_reader_never_raises_and_says_none_when_there_is_no_database(tmp_path):
    from sutra_app.connectors.engine_port import live_cap_reader
    assert live_cap_reader(str(tmp_path / "nothing"), "prj_0123456789ab")() is None


def test_a_builder_call_is_started_with_the_live_cap_when_it_is_lower_than_the_steps_own_remainder(fake, tmp_path, project_world):
    from sutra_app.connectors.engine_port import live_cap_reader
    data_dir, set_state = project_world
    fake.sequence("ok_plain").reply(text="built")
    router = router_for(fake, tmp_path)
    router.live_cap = live_cap_reader(str(data_dir), "prj_0123456789ab")
    set_state("running")
    try:
        router.complete(CompletionRequest(system="s", user="build", tag=TAG, run_tools=grant(tmp_path), allowance=NodeMeter(max_usd=50.0).begin()))
        argv = fake.model_calls("claude")[-1]["argv"]
    finally:
        router.close()
    assert float(value(argv, "--max-budget-usd")) == pytest.approx(1.2, abs=0.001), "min(engine $2, step remainder $50, live cap $1.2)"


def test_the_port_of_a_node_installs_the_reader_and_a_port_of_an_ordinary_run_does_not(fake, tmp_path, project_world):
    from sutra_app.connectors import engine_port
    from sutra_app.engine.port import PortSpec
    data_dir, _ = project_world
    node = engine_port.port_from_config(PortSpec(mock=False, connector="claude", run_id="j2-20261120-100000-aaaa", dept_id="web", data_dir=str(data_dir), node=True, project_id="prj_0123456789ab"),
                                        ConnectorConfig(**fake.config_kwargs(tmp_path)))
    ordinary = engine_port.port_from_config(PortSpec(mock=False, connector="claude", run_id="j2-20261120-100000-bbbb", dept_id="web", data_dir=str(data_dir)), ConnectorConfig(**fake.config_kwargs(tmp_path)))
    try:
        assert node.router.live_cap is not None and ordinary.router.live_cap is None
    finally:
        node.close()
        ordinary.close()
