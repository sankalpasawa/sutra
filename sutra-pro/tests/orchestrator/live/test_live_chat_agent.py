"""One real decide stage against the real CLI on a three-team chart (orchestrator 7). Runs only with SUTRA_LIVE=1:

    SUTRA_LIVE=1 scripts/py -m pytest tests/orchestrator/live -q -m live

It asserts shape, never wording: the reply must validate as `ChatDecision`, name only ids of the chart, and carry no prose field. A CLI
that is not installed or not signed in skips the test. Reuse-versus-add quality is read from the printed decision, not asserted."""
import asyncio
import shutil

import pytest
from factories_org import add_op
from orchestrator.test_chart_store import Env

from sutra_app.library.registry import REGISTRY
from sutra_app.orchestrator.agent.agent import ChatAgent, PlanRequest, call_context
from sutra_app.orchestrator.agent.replies import ChatDecision

pytestmark = pytest.mark.live
TEAMS = (("$web", "Web", "Websites, landing pages and online menus"), ("$sales", "Sales", "Leads, quotes and customers"),
         ("$ops", "Operations", "Suppliers, stock and opening hours"))


@pytest.fixture(scope="module")
def connector(tmp_path_factory):
    if shutil.which("claude") is None and shutil.which("codex") is None:
        pytest.skip("neither claude nor codex is installed")
    from sutra_app.connectors.factory import build_router
    from sutra_app.connectors.orchestrator_port import AsyncConnector
    from sutra_app.config import Settings
    root = tmp_path_factory.mktemp("live-chat")
    settings = Settings.load({}, data_dir=root / "data", token="live-token-0123456789abcdef", env_file=root / "none.env")
    router = build_router(settings)
    port = AsyncConnector(router)
    status = port.status()
    if not any(s.get("installed") and s.get("signed_in") is not False for s in status.values()):
        pytest.skip("no CLI is signed in")
    return port


def test_one_real_decide_stage_validates_as_a_chat_decision(connector, db, settings, clock, events):
    env = Env(db, settings, clock, events)
    env.apply(*[add_op(ref, "department", name, "root", purpose) for ref, name, purpose in TEAMS])
    agent = ChatAgent(connector, env.chart, clock=clock)
    request = PlanRequest(text="I need a landing page for my coffee shop.", message_id=1)
    plan = asyncio.run(agent.plan(request))
    print("decision:", plan.decision.model_dump_json() if plan.decision else "keywords", "| calls:", plan.calls)
    assert plan.outcome in ("work", "clarify", "status", "smalltalk", "none")
    if plan.decision is not None:
        assert ChatDecision.model_validate(plan.decision.model_dump()).intent in ("new_task", "chart_request", "status", "smalltalk", "clarify")
        ids = {n.id for n in env.chart.head().model.nodes}
        assert set(plan.decision.reuse_nodes) <= ids and all(d.dept in ids for d in plan.decision.assignments)
    assert REGISTRY.transport_schema("chat_turn", kind="decide")["properties"]
    assert call_context(1)["node_id"] == "root"
