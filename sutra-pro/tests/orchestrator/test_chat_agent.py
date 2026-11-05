"""The chat agent (ORCH-7): reply classes, prompts, the keyword fallback, the code template lines and the staged calls with their
retries. `AgentEnv` builds the whole server side over a chart with two teams that have purposes; `test_turn_runner.py` and
`test_api_agent.py` import it and the reply builders."""
import json
import random
import time

import pytest
from factories_org import add_op, div_op, merge_op, move_op, rename_op
from orchestrator.test_chart_store import Env
from orchestrator.test_tasks import TEnv
from pydantic import ValidationError

from sutra_app.library.gate import GATE, GateError
from sutra_app.library.org_chart import apply_change
from sutra_app.library.registry import REGISTRY, is_transport_safe
from sutra_app.library.replies import ReplyInvalid, ReplyParser
from sutra_app.library.types import overhead_atom_id
from sutra_app.orchestrator.agent import planner, prompts
from sutra_app.orchestrator.agent.agent import ChartBusy, ChatAgent, PlanRequest, StageFailed, StaleChart, call_context
from sutra_app.orchestrator.agent.ports import (
    ConnectorFailure, ConnectorPort, failure_kind, hint, missing_cli, usable,
)
from sutra_app.orchestrator.agent.replies import (
    AssignmentDraft, AssignmentPlan, ChatDecision, dependency_order,
)
from sutra_app.orchestrator.models import Event
from sutra_app.orchestrator.testing.scripted import ScriptedConnector, ScriptExhausted


# ---- builders of scripted model replies ---------------------------------------------------------------------------------

def draft(ref="a1", dept="web", title="Cafe page", brief="Build the cafe landing page.", scope=None, depends_on=(), follows=None) -> dict:
    return {"ref": ref, "dept": dept, "scope": scope, "title": title, "brief": brief, "depends_on": list(depends_on), "follows": follows}


def decide(intent="new_task", change="reuse", reuse=("web",), why="web fits", assignments=None) -> dict:
    if assignments is None:
        assignments = [draft()] if intent == "new_task" and change in ("none", "reuse") else []
    return {"kind": "decide", "intent": intent, "change": change, "reuse_nodes": list(reuse), "why": why, "assignments": assignments}


def add_dept(ref, name, purpose="", parent="root") -> dict:
    return {"op": "add", "node": {"ref": ref, "kind": "department", "name": name, "purpose": purpose, "parent": parent}}


def add_div(ref, name, parent, purpose="") -> dict:
    return {"op": "add", "node": {"ref": ref, "kind": "division", "name": name, "purpose": purpose, "parent": parent}}


def change_reply(*ops, reason="a new team", reuses=()) -> dict:
    return {"reason": reason, "reuses": list(reuses), "ops": list(ops)}


def assignments(*drafts) -> dict:
    return {"kind": "assignments", "assignments": list(drafts)}


class AgentEnv(TEnv):
    """TEnv over a chart with Web (Menu) and Sales (Leads, Quotes), each with a purpose, plus an agent over a scripted connector."""

    def __init__(self, db, settings, clock, events, script=()) -> None:
        env = Env(db, settings, clock, events)
        env.apply(add_op("$web", "department", "Web", "root", "Websites, landing pages and menus"),
                  add_op("$sales", "department", "Sales", "root", "Leads, quotes and customers"))
        env.apply(div_op("$menu", "Menu", "web"), div_op("$leads", "Leads", "sales"), div_op("$quotes", "Quotes", "sales"))
        events.batches.clear()
        super().__init__(env, settings, clock)
        self.connector = ScriptedConnector(script)
        self.agent = ChatAgent(self.connector, env.chart, clock=clock)
        self.chart = env.chart

    def request(self, text="I need a landing page for my coffee shop.", mid=5, history=(), pending=()) -> PlanRequest:
        return PlanRequest(text=text, message_id=mid, history=history, pending=pending)

    def plan(self, request=None, **kw):
        return self.run(self.agent.plan(request or self.request(), **kw))

    def steps(self) -> list[str]:
        return [c.step for c in self.connector.calls]


@pytest.fixture
def aenv(db, settings, clock, events):
    return AgentEnv(db, settings, clock, events)


def with_script(aenv: AgentEnv, *items) -> AgentEnv:
    aenv.connector.push(*items)
    return aenv


# ============================================ reply classes ==================================================================

def test_the_family_is_registered_with_two_kinds_and_transport_safe_schemas():
    assert set(REGISTRY.kinds("chat_turn")) == {"decide", "assignments"}
    for kind in ("decide", "assignments"):
        schema = REGISTRY.transport_schema("chat_turn", kind=kind)
        assert is_transport_safe(schema) == []
        assert "oneOf" not in json.dumps(schema) and "discriminator" not in json.dumps(schema)


def test_no_reply_class_has_a_prose_field():
    for cls in (ChatDecision, AssignmentPlan, AssignmentDraft):
        assert not {"reply", "say", "message", "text", "answer"} & set(cls.model_fields)


def test_a_decision_is_gated_and_closed():
    checked = GATE.check("chat_turn", decide())
    assert checked.kind == "decide" and checked.model.assignments[0].dept == "web"
    with pytest.raises(GateError):
        GATE.check("chat_turn", {**decide(), "reply": "Sure, I will do that"})


@pytest.mark.parametrize("fields, phrase", [
    (dict(intent="new_task", change="none", assignments=[]), "needs at least one assignment"),
    (dict(intent="new_task", change="reuse", reuse_nodes=[], assignments=[draft()]), "needs reuse_nodes"),
    (dict(intent="chart_request", change="none"), "chart_request means the change is add or rearrange"),
    (dict(intent="status", change="add"), "changes nothing"),
    (dict(intent="smalltalk", change="none", assignments=[draft()]), "carries no assignments"),
    (dict(intent="clarify", change="none", reuse_nodes=["a1x", "b1x", "c1x", "d1x"]), "at most 3 candidate"),
    (dict(intent="new_task", change="add", assignments=[draft()]), "left empty when the change is add"),
])
def test_decision_rules(fields, phrase):
    base = dict(intent="new_task", change="none", reuse_nodes=[], why="x", assignments=[])
    with pytest.raises(ValidationError) as info:
        ChatDecision(**{**base, **fields})
    assert phrase in str(info.value)


def test_decision_accepts_the_allowed_shapes():
    ChatDecision(intent="status", change="none", why="asks for progress")
    ChatDecision(intent="smalltalk", change="none", why="thanks")
    ChatDecision(intent="clarify", change="none", reuse_nodes=["web", "sales"], why="two teams could fit")
    ChatDecision(intent="chart_request", change="rearrange", why="owner asks to merge")
    ChatDecision(intent="new_task", change="add", why="no team fits")


def test_refs_must_be_unique_known_and_acyclic():
    with pytest.raises(ValidationError, match="used twice"):
        AssignmentPlan(assignments=[draft("a1"), draft("a1")])
    with pytest.raises(ValidationError, match="not one of the assignments"):
        AssignmentPlan(assignments=[draft("a1", depends_on=["a2"])])
    with pytest.raises(ValidationError, match="cannot depend on itself"):
        AssignmentPlan(assignments=[draft("a1", depends_on=["a1"])])
    with pytest.raises(ValidationError, match="in a circle"):
        AssignmentPlan(assignments=[draft("a1", depends_on=["a2"]), draft("a2", depends_on=["a1"])])
    with pytest.raises(ValidationError):
        AssignmentPlan(assignments=[])
    with pytest.raises(ValidationError):
        AssignmentDraft(**draft("a6"))


def test_to_task_workflow_orders_dependencies_first_and_passes_the_gate():
    plan = AssignmentPlan(assignments=[draft("a1", "web", depends_on=["a2"]), draft("a2", "sales", title="Quote")])
    workflow = plan.to_task_workflow("req-7")
    assert workflow.id == "req-7" and workflow.name == "Cafe page"
    assert [s.id for s in workflow.steps] == ["a2", "a1"] and workflow.steps[1].depends_on == ["a2"]
    assert GATE.check("workflow", workflow).kind == "task"
    assert [d.ref for d in dependency_order(plan.assignments)] == ["a2", "a1"]


def test_every_valid_plan_gives_a_workflow_the_gate_accepts():
    rng = random.Random(7)
    accepted = 0
    for _ in range(150):
        n = rng.randint(1, 5)
        refs = [f"a{i}" for i in range(1, n + 1)]
        drafts = [draft(ref, rng.choice(["web", "sales"]), depends_on=rng.sample(refs, rng.randint(0, min(2, n))), follows=None) for ref in refs]
        try:
            plan = AssignmentPlan(assignments=drafts)
        except ValidationError:
            continue
        accepted += 1
        assert GATE.check("workflow", plan.to_task_workflow("req-1")).family == "workflow"
    assert accepted > 30


# ============================================ prompts =========================================================================

def test_each_template_file_holds_exactly_its_placeholders():
    for name in prompts.TEMPLATES:
        assert prompts.fields_of(name) == prompts.PLACEHOLDERS[name]
    assert "banned" not in {p for fields in prompts.PLACEHOLDERS.values() for p in fields}


def test_render_refuses_a_missing_or_unknown_placeholder():
    with pytest.raises(prompts.PromptError, match="missing"):
        prompts.render("retry", n=1, max=3, violations="x")
    with pytest.raises(prompts.PromptError, match="unknown"):
        prompts.render("retry", n=1, max=3, violations="x", delta="y", extra="z")
    with pytest.raises(prompts.PromptError, match="no prompt template"):
        prompts.template("nope")


def test_the_templates_say_what_the_design_says():
    assert "REUSE a team" in prompts.template("decide") and "Prefer reuse" in prompts.template("decide")
    assert "ref such as $web" in prompts.template("change")
    assert "CHART AFTER THE CHANGE" in prompts.template("assign")
    assert "attempt {n} of {max}" in prompts.template("retry")
    for name in ("decide", "assign"):                                    # no reply sentence is asked for
        assert "reply" not in prompts.template(name).lower().replace("one json object", "")


def test_prompt_helpers():
    assert prompts.conversation([]) == "(no earlier messages)"
    text = prompts.conversation([("user", "hi there"), ("sutra", "Tell me what you need.")] * 10, limit=12)
    assert text.count("\n") == 11 and text.splitlines()[0].startswith(("Owner:", "Sutra:"))
    assert prompts.pending_lines([]).startswith("(nothing") and prompts.pending_lines(["chg-0004: x"]) == "chg-0004: x"
    assert prompts.changed_keys(None, {"a": 1}).startswith("nothing to compare")
    assert prompts.changed_keys({"a": 1, "b": 2}, {"a": 1, "b": 3, "c": 4}) == "b, c"
    assert prompts.changed_keys({"a": 1}, {"a": 1}).startswith("nothing")
    from sutra_app.library.types import violation
    assert prompts.violation_lines([violation("ops.0", "bad", "no good"), violation("", "x", "y")]) == "- ops.0: bad: no good\n- request: x: y"
    digest = prompts.field_digest(AssignmentDraft)
    assert digest.startswith("AssignmentDraft: ref, dept, scope") and "identity, adaptation, priority, coordination, audit" in digest


# ============================================ the connector port ==============================================================

def test_failure_kinds():
    class Quota(Exception):
        pass

    class Odd(Exception):
        kind = "auth"
    assert failure_kind(Odd()) == "auth" and failure_kind(TimeoutError()) == "timeout" and failure_kind(Quota()) == "quota"
    assert failure_kind(ConnectorFailure("bad_output")) == "bad_output" and failure_kind(KeyError("x")) is None
    with pytest.raises(ValueError):
        ConnectorFailure("exploded")


def test_status_helpers():
    ok = {"claude": {"installed": True, "signed_in": True}}
    assert usable(ok) and hint(ok) == "" and not missing_cli(ok)
    out = {"claude": {"installed": False}, "codex": {"installed": True, "signed_in": False}}
    assert not usable(out) and hint(out) == "Claude is not installed; Codex is signed out"
    assert missing_cli({"claude": {"installed": False}}) and not missing_cli(out) and hint({}) == "no connector is set up"
    assert isinstance(ScriptedConnector(), ConnectorPort)


# ============================================ the scripted connector ==========================================================

def test_scripted_connector_pops_in_order_raises_and_runs_callables():
    async def go():
        calls = ScriptedConnector([{"a": 1}, lambda call: {"step": call.step}, ConnectorFailure("quota"), ValueError])
        assert await calls.call_json("p", step="x") == ({"a": 1}, 0.0, "stub")
        assert (await calls.call_json("p", step="decide"))[0] == {"step": "decide"}
        with pytest.raises(ConnectorFailure):
            await calls.call_json("p")
        with pytest.raises(ValueError):
            await calls.call_json("p")
        with pytest.raises(ScriptExhausted):
            await calls.call_json("p")
        assert len(calls.calls) == 5 and calls.remaining == 0
    import asyncio
    asyncio.run(go())


def test_scripted_connector_usage_sink_and_status():
    rows = []
    c = ScriptedConnector([{"a": 1}, ConnectorFailure("timeout")], sink=rows.append)
    import asyncio
    asyncio.run(c.call_json("p", context={"purpose": "chat_plan", "atom_id": "a-1234567890-01", "node_id": "root", "session_id": "cs_org"}))
    with pytest.raises(ConnectorFailure):
        asyncio.run(c.call_json("p"))
    assert c.records_usage and [r.ok for r in rows] == [True, False] and rows[0].atom_id == "a-1234567890-01" and rows[0].provider == "stub"
    assert c.status()["stub"]["signed_in"] is True
    c.set_status({"claude": {"installed": False}})
    assert not usable(c.status()) and not ScriptedConnector().records_usage


# ============================================ the keyword fallback and the words =============================================

def chart_of(aenv):
    return aenv.chart.head().model


def test_fallback_reuses_the_one_team_whose_words_fit(aenv):
    found = planner.fallback_plan("Please build a landing page for the cafe websites", chart_of(aenv))
    assert found.reuse.id == "web" and found.reuse.score >= 2


def test_fallback_needs_two_words_and_a_clear_winner(aenv):
    chart = chart_of(aenv)
    one_word = planner.fallback_plan("I want quotes please", chart)
    assert one_word.reuse is None and [c.id for c in one_word.candidates][0] == "sales"
    tie = planner.fallback_plan("leads quotes landing pages", chart)
    assert tie.reuse is None and len(tie.candidates) == 2
    nothing = planner.fallback_plan("xyzzy plugh", chart)
    assert nothing.reuse is None and {c.id for c in nothing.candidates} == {"web", "sales"}


def test_fallback_without_a_department_is_none(db, settings, clock, events):
    env = Env(db, settings, clock, events)
    assert planner.fallback_plan("anything at all", env.chart.head().model) is None


def test_candidates_named_first_then_by_overlap(aenv):
    chart = chart_of(aenv)
    found = planner.candidates(chart, "landing pages", ids=["quotes", "root", "nope"])
    assert [c.id for c in found] == ["quotes", "web", "sales"] and found[0].kind == "division"
    assert len(planner.candidates(chart, "x", limit=1)) == 1


def test_status_report_is_built_by_code(aenv):
    chart = chart_of(aenv)
    text = planner.status_report(chart, [planner.TaskLine("web", "Cafe page", "running"), planner.TaskLine("sales", "Old quote", "done")])
    assert text.splitlines() == [planner.STATUS_HEADER, '- Web: working on "Cafe page".', '- Sales: last finished "Old quote".']
    assert planner.status_report(chart, []).splitlines()[1:] == ["- Web: nothing yet.", "- Sales: nothing yet."]
    queued = planner.status_report(chart, [planner.TaskLine("web", "A", "done"), planner.TaskLine("web", "B", "waiting_user")])
    assert 'waiting for you on "B"' in queued


def test_the_greeting_is_the_chart_stores():
    from sutra_app.orchestrator.chart import GREETING
    assert planner.LINES["greeting"] == GREETING


def test_every_line_has_a_matching_pattern_and_no_free_prose_matches():
    for key, template in planner.LINES.items():
        values = {name: "X" for _, name, _, _ in __import__("string").Formatter().parse(template) if name}
        sentence = planner.line(key, **{k: ("Menu is busy with Cafe" if key == "busy" else v) for k, v in values.items()})
        assert planner.matches_template(sentence), key
    assert planner.matches_template("I moved Menu under Content. I set up a Content team.")
    assert not planner.matches_template("Sure! I will build you a lovely website right away.")
    assert not planner.matches_template("I set up a Web team and gave it your request. Also here is a joke.")
    with pytest.raises(ValueError):
        planner.line("reuse")
    assert planner.names_phrase(["A"]) == "A" and planner.names_phrase(["A", "B", "C"]) == "A, B and C" and planner.names_phrase([]) == ""


# ============================================ the agent: stage A =============================================================

def test_reuse_first_is_one_call(aenv):
    with_script(aenv, decide())
    plan = aenv.plan()
    assert aenv.steps() == ["decide"] and plan.outcome == "work" and not plan.keywords
    assert plan.change.model.kind == "reuse" and plan.change.model.reuses == ["web"] and plan.change.model.task_id == "req-5"
    assert [d.dept for d in plan.drafts] == ["web"] and plan.calls == 1


def test_prompt_carries_schema_digest_and_history_and_no_secret(aenv, monkeypatch):
    secret = "sk-live-0123456789abcdef"
    aenv.agent._redact = lambda text: text.replace(secret, "[redacted]")
    with_script(aenv, decide())
    aenv.plan(aenv.request(f"My key is {secret}. Build a page.", history=[("user", "hello"), ("sutra", "Tell me what you need.")],
                           pending=["chg-0009: Merge Leads into Quotes (waiting)"]))
    call = aenv.connector.calls[0]
    assert secret not in call.prompt and "[redacted]" in call.prompt
    assert "web | Web | Websites, landing pages and menus" in call.prompt and "Org chart revision" in call.prompt
    assert "Owner: hello" in call.prompt and "Sutra: Tell me what you need." in call.prompt and "chg-0009" in call.prompt
    assert json.dumps(REGISTRY.transport_schema("chat_turn", kind="decide"), sort_keys=True, separators=(",", ":")) in call.prompt
    assert call.schema == REGISTRY.transport_schema("chat_turn", kind="decide")
    assert "AssignmentDraft:" in call.prompt and call.function == "chat_agent" and call.step == "decide" and call.timeout == 120.0


def test_every_call_of_a_request_carries_the_overhead_key(aenv):
    with_script(aenv, decide(intent="new_task", change="add", reuse=()), change_reply(add_dept("$cafe", "Cafe", "Coffee shop menus")),
                assignments(draft("a1", "cafe")))
    aenv.plan(aenv.request(mid=9))
    assert aenv.steps() == ["decide", "change", "assign"]
    wanted = overhead_atom_id("req-9")
    assert call_context(9) == {"purpose": "chat_plan", "session_id": "cs_org", "node_id": "root", "atom_id": wanted}
    assert all(c.context == call_context(9) for c in aenv.connector.calls)


def test_status_smalltalk_and_clarify_make_no_change(aenv):
    with_script(aenv, decide("status", "none", reuse=()), decide("smalltalk", "none", reuse=()),
                decide("clarify", "none", reuse=("quotes", "web"), why="two fit"))
    assert aenv.plan().outcome == "status"
    assert aenv.plan().outcome == "smalltalk"
    clar = aenv.plan(aenv.request("do the thing"))
    assert clar.outcome == "clarify" and [c.id for c in clar.candidates] == ["quotes", "web", "sales"] and clar.change is None


def test_change_none_with_assignments_logs_a_reuse_of_their_teams(aenv):
    with_script(aenv, decide(change="none", reuse=(), assignments=[draft("a1", "web", scope="menu"), draft("a2", "sales", title="Quote")]))
    plan = aenv.plan()
    assert plan.change.model.kind == "reuse" and plan.change.model.reuses == ["web", "menu", "sales"]


def test_unknown_node_and_bad_assignment_are_retried_with_the_reasons(aenv):
    with_script(aenv, decide(reuse=("ghost",)), decide(change="reuse", reuse=("web",), assignments=[draft("a1", "ghost-team")]), decide())
    plan = aenv.plan()
    assert aenv.steps() == ["decide"] * 3 and plan.outcome == "work"
    second, third = aenv.connector.calls[1].prompt, aenv.connector.calls[2].prompt
    assert "Your last answer was rejected (attempt 1 of 3)." in second and "- reuse_nodes.0: unknown_node:" in second
    assert "Your last answer was rejected (attempt 2 of 3)." in third and "- assignments.0.dept: bad_assignment:" in third
    assert "Changed since your last try: reuse_nodes, assignments" in third


def test_bad_json_then_success_on_attempt_two(aenv):
    with_script(aenv, {"oops": True}, decide())
    plan = aenv.plan()
    assert aenv.steps() == ["decide", "decide"] and plan.outcome == "work" and not plan.keywords
    retry = aenv.connector.calls[1].prompt
    assert "Your last answer was rejected (attempt 1 of 3)." in retry and "- intent:" in retry
    assert retry.startswith(aenv.connector.calls[0].prompt)


def test_three_failures_give_the_keyword_fallback(aenv):
    with_script(aenv, {"x": 1}, {"x": 2}, {"x": 3})
    plan = aenv.plan(aenv.request("Build a landing page for the cafe websites"))
    assert aenv.steps() == ["decide"] * 3 and plan.keywords and plan.outcome == "work"
    assert plan.change.model.kind == "reuse" and plan.change.model.reason.endswith("(planned by keywords)")
    assert plan.drafts[0].dept == "web" and plan.drafts[0].brief == "Build a landing page for the cafe websites"


def test_fallback_without_a_clear_team_offers_a_choice(aenv):
    with_script(aenv, {"x": 1}, {"x": 2}, {"x": 3})
    plan = aenv.plan(aenv.request("xyzzy"))
    assert plan.outcome == "none" and plan.keywords and plan.change is None and len(plan.candidates) == 2


def test_timeouts_and_bad_output_count_as_attempts(aenv):
    with_script(aenv, ConnectorFailure("timeout"), ConnectorFailure("bad_output"), decide())
    plan = aenv.plan()
    assert aenv.steps() == ["decide"] * 3 and plan.outcome == "work"
    assert "- request: timeout:" in aenv.connector.calls[1].prompt and "- request: bad_output:" in aenv.connector.calls[2].prompt


@pytest.mark.parametrize("kind", ["unavailable", "auth", "quota"])
def test_unavailable_auth_and_quota_are_not_retried(aenv, kind):
    with_script(aenv, ConnectorFailure(kind), decide())
    with pytest.raises(ConnectorFailure) as info:
        aenv.plan()
    assert info.value.kind == kind and aenv.steps() == ["decide"]


def test_a_connector_error_with_a_kind_attribute_is_mapped(aenv):
    class Signed(Exception):
        kind = "auth"
        provider = "claude"
    with_script(aenv, Signed("not signed in"))
    with pytest.raises(ConnectorFailure) as info:
        aenv.plan()
    assert info.value.kind == "auth" and info.value.provider == "claude"


def test_a_bug_in_the_connector_is_not_swallowed(aenv):
    with_script(aenv, KeyError("bug"))
    with pytest.raises(KeyError):
        aenv.plan()


def test_the_call_cap_ends_the_request_with_the_fallback(aenv):
    aenv.agent.max_calls = 3
    bad = {"reason": "x", "reuses": [], "ops": []}                       # a change of kind reuse where add was decided
    with_script(aenv, decide(change="add", reuse=()), bad, bad, bad, bad)
    plan = aenv.plan(aenv.request("Websites and landing pages"))
    assert aenv.steps() == ["decide", "change", "change"] and plan.keywords and plan.calls == 3 and aenv.connector.remaining == 2


def test_no_department_and_a_failing_model_is_f1(db, settings, clock, events):
    env = Env(db, settings, clock, events)
    agent = ChatAgent(ScriptedConnector([{"x": 1}] * 3), env.chart)
    import asyncio
    with pytest.raises(ConnectorFailure) as info:
        asyncio.run(agent.plan(PlanRequest("hello", 1)))
    assert info.value.kind == "bad_output"


# ============================================ stage B and C ==================================================================

def test_add_flow_is_three_calls_and_the_agent_sets_the_change_fields(aenv):
    with_script(aenv, decide(intent="new_task", change="add", reuse=()),
                change_reply(add_dept("$cafe", "Cafe Menus", "Coffee shop menus and boards")), assignments(draft("a1", "cafe-menus")))
    plan = aenv.plan(aenv.request(mid=11))
    assert aenv.steps() == ["decide", "change", "assign"]
    model = plan.change.model
    assert (model.kind, model.task_id, model.base_revision, model.id) == ("add", "req-11", aenv.chart.head().model.revision, aenv.chart.next_change_id())
    assert plan.added == ["cafe-menus"] and plan.drafts[0].dept == "cafe-menus" and not plan.stage_c_pending
    change_prompt, assign_prompt = aenv.connector.calls[1].prompt, aenv.connector.calls[2].prompt
    assert "ref such as $web" in change_prompt and "YOUR DECISION" in change_prompt and "kind add" in change_prompt
    assert "NewNode:" in change_prompt and "AddOp:" in change_prompt
    assert "CHART AFTER THE CHANGE" in assign_prompt and "cafe-menus | Cafe Menus | Coffee shop menus and boards" in assign_prompt
    assert aenv.connector.calls[1].schema == REGISTRY.transport_schema("chart_change_request")


def test_stage_c_may_use_a_division_the_change_adds(aenv):
    with_script(aenv, decide(change="add", reuse=()), change_reply(add_div("$blog", "Blog", "web", "Posts")),
                assignments(draft("a1", "web", scope="blog")))
    plan = aenv.plan()
    assert plan.drafts[0].scope == "blog" and plan.added == ["blog"]


def test_stage_b_violations_are_all_listed_and_retried(aenv):
    bad = change_reply(add_dept("$w2", "Web Pages", "Websites, landing pages and menus"), {"op": "move", "node": "ghost", "to_parent": "web"})
    with_script(aenv, decide(change="add", reuse=()), bad, change_reply(add_dept("$cafe", "Cafe", "Coffee")), assignments(draft("a1", "cafe")))
    aenv.plan()
    retry = aenv.connector.calls[2].prompt
    assert "kind_mismatch" in retry                                    # the move makes it a rearrange, not an add
    assert aenv.steps() == ["decide", "change", "change", "assign"]


def test_reuse_candidate_is_retried(aenv):
    dup = change_reply(add_dept("$w", "Web", "Websites, landing pages and menus"))
    with_script(aenv, decide(change="add", reuse=()), dup, change_reply(add_dept("$cafe", "Cafe", "Coffee")), assignments(draft("a1", "cafe")))
    aenv.plan()
    assert "reuse_candidate" in aenv.connector.calls[2].prompt and "reuse it instead of adding another" in aenv.connector.calls[2].prompt


def test_stage_b_failing_three_times_falls_back_to_keywords(aenv):
    dup = change_reply(add_dept("$w", "Web", "Websites, landing pages and menus"))
    with_script(aenv, decide(change="add", reuse=()), dup, dup, dup)
    plan = aenv.plan(aenv.request("A landing page for websites"))
    assert aenv.steps() == ["decide", "change", "change", "change"] and plan.keywords and plan.change.model.kind == "reuse"


def test_a_busy_division_is_not_retried(aenv):
    aenv.new("sales", "Quotes work", scope_id="quotes")
    with_script(aenv, decide("chart_request", "rearrange", reuse=()), change_reply({"op": "move", "node": "quotes", "to_parent": "web"}))
    with pytest.raises(ChartBusy) as info:
        aenv.plan()
    assert "Quotes is busy with Quotes work" in info.value.violations[0].message and aenv.steps() == ["decide", "change"]


def test_a_chart_that_moved_is_stale_not_retried(aenv):
    def moved(call):
        aenv.apply_other = aenv.env.apply(add_op("$z", "department", "Zed", "root", "Zed things"))
        return change_reply(add_dept("$cafe", "Cafe", "Coffee"))
    with_script(aenv, decide(change="add", reuse=()), moved)
    with pytest.raises(StaleChart):
        aenv.plan()
    assert aenv.steps() == ["decide", "change"]


def test_a_merge_waits_for_approval_and_skips_stage_c(aenv):
    with_script(aenv, decide(change="rearrange", reuse=(), intent="new_task"), change_reply({"op": "merge", "into": "quotes", "sources": ["leads"]}))
    plan = aenv.plan()
    assert aenv.steps() == ["decide", "change"] and plan.stage_c_pending and plan.drafts == []
    assert aenv.chart.classify(plan.change) == "approve"


def test_a_chart_request_asks_for_no_assignments(aenv):
    with_script(aenv, decide("chart_request", "rearrange", reuse=()), change_reply({"op": "rename", "node": "menu", "name": "Menus", "purpose": None}))
    plan = aenv.plan()
    assert aenv.steps() == ["decide", "change"] and plan.drafts == [] and plan.change.model.kind == "rearrange" and not plan.stage_c_pending


def test_stage_c_bad_assignments_are_retried(aenv):
    with_script(aenv, decide(change="add", reuse=()), change_reply(add_dept("$cafe", "Cafe", "Coffee")), assignments(draft("a1", "web", scope="quotes")),
                assignments(draft("a1", "cafe")))
    plan = aenv.plan()
    assert "- assignments.0.scope: bad_assignment:" in aenv.connector.calls[3].prompt and plan.drafts[0].dept == "cafe"


def test_stage_c_follows_must_be_a_task_of_that_team(aenv):
    other = aenv.new("sales", "Quote request")
    with_script(aenv, decide(change="add", reuse=()), change_reply(add_dept("$cafe", "Cafe", "Coffee")),
                assignments(draft("a1", "cafe", follows=other.id)), assignments(draft("a1", "cafe")))
    aenv.plan()
    assert "bad_assignment" in aenv.connector.calls[3].prompt and f"{other.id!r} is not a task of" in aenv.connector.calls[3].prompt


# ============================================ resume and the owner's pick ====================================================

def test_resume_asks_only_stage_c_after_an_approval(aenv):
    decision = ChatDecision.model_validate(decide(change="rearrange", reuse=(), intent="new_task"))
    with_script(aenv, assignments(draft("a1", "sales", title="Quote")))
    plan = aenv.run(aenv.agent.resume(aenv.request(), decision))
    assert aenv.steps() == ["assign"] and plan.drafts[0].dept == "sales" and plan.change is None


def test_resume_keeps_a_decision_without_work(aenv):
    chart_only = ChatDecision.model_validate(decide("chart_request", "rearrange", reuse=()))
    assert aenv.run(aenv.agent.resume(aenv.request(), chart_only)).drafts == [] and aenv.connector.calls == []
    assert aenv.run(aenv.agent.resume(aenv.request(), None)).drafts == []


def test_resume_falls_back_to_keywords_when_stage_c_fails(aenv):
    decision = ChatDecision.model_validate(decide(change="rearrange", reuse=(), intent="new_task"))
    with_script(aenv, {"x": 1}, {"x": 2}, {"x": 3})
    plan = aenv.run(aenv.agent.resume(aenv.request("Quotes for leads and customers"), decision))
    assert plan.keywords and plan.drafts[0].dept == "sales" and plan.change is None


def test_choice_plan_builds_a_reuse_change_without_a_model_call(aenv):
    plan = aenv.run(aenv.agent.choice_plan(aenv.request("a very long request " * 100), "quotes"))
    assert aenv.connector.calls == [] and plan.change.model.reuses == ["quotes"] and "You picked the Quotes team" in plan.change.model.reason
    draft_ = plan.drafts[0]
    assert (draft_.dept, draft_.scope) == ("sales", "quotes") and len(draft_.brief) <= 2000 and len(draft_.title) <= 60
    with pytest.raises(Exception, match="not a team"):
        aenv.run(aenv.agent.choice_plan(aenv.request(), "root"))
