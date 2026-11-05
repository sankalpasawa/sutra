"""The offline demo's reply book (GAP-DEMO, D97): each stage reply validates against its reply class, decide, change and assign agree
with each other, a retry gets the same answer, the wiring gives the book to the offline router only, and the REAL ChatAgent over the
stub with the book handles three messages (a new team, the same topic, another topic)."""
import asyncio
from types import SimpleNamespace

import pytest
from orchestrator.test_chart_store import Env

from sutra_app.config import Settings
from sutra_app.connectors.factory import build_router
from sutra_app.connectors.models import ConnectorConfig
from sutra_app.connectors.orchestrator_port import AsyncConnector
from sutra_app.connectors.stub import ReplyBook, StubConnector
from sutra_app.library.gate import GATE
from sutra_app.library.replies import ReplyParser
from sutra_app.orchestrator.agent import demo, prompts
from sutra_app.orchestrator.agent.agent import ChatAgent, PlanRequest
from sutra_app.orchestrator.agent.demo import DemoBook, DemoStub, demo_book, topic_name
from sutra_app.orchestrator.models import ChangeContext
from sutra_app.orchestrator.wiring import build_services

CAFE = "A website for my cafe"
DIGEST_EMPTY = "Org chart revision 1. Root id: root."
CAFE_LINE = "website-cafe | Website Cafe | A website for my cafe | live: - | last: -"
SALES_LINE = "sales-leads | Sales Leads | Track leads and quotes | live: - | last: -"
DIGEST_TWO = "\n".join([DIGEST_EMPTY, CAFE_LINE, "  menu | Menu | The menu page", SALES_LINE])


# ---- prompts as the chat agent builds them -------------------------------------------------------------------------------------

def decide_prompt(message, digest=DIGEST_EMPTY):
    return prompts.render("decide", revision=1, digest=digest, conversation="(no earlier messages)", pending="(nothing)",
                          message=message, field_digest="F", schema="{}")


def change_prompt(message, digest=DIGEST_EMPTY, kind="add"):
    return prompts.render("change", revision=1, digest=digest, field_digest="F", message=message, decision="{}", kind=kind, schema="{}")


def assign_prompt(message, digest):
    return prompts.render("assign", digest=digest, field_digest="F", message=message, schema="{}")


RETRY = "\n\n" + prompts.render("retry", n=1, max=3, violations="- request: x: y", delta="nothing")


def answer(stage, prompt):
    """What the book says to `prompt` for `stage`, the way the stub does it (the prompt is visible to the reply)."""
    token = demo._PROMPT.set(prompt)
    try:
        found, reply = demo_book().lookup("chat_agent", stage)
        assert found
        return reply()
    finally:
        demo._PROMPT.reset(token)


def parse(family, obj, kind=None):
    model = ReplyParser().parse(family, obj, kind=kind).model
    GATE.check(family, model)
    return model


# ---- each reply validates ------------------------------------------------------------------------------------------------------

def test_decide_adds_a_team_when_the_chart_has_none():
    decision = parse("chat_turn", answer("decide", decide_prompt(CAFE)), "decide")
    assert (decision.intent, decision.change, decision.reuse_nodes, decision.assignments) == ("new_task", "add", [], [])


def test_decide_reuses_the_department_that_shares_a_word_with_its_goal():
    decision = parse("chat_turn", answer("decide", decide_prompt("Add a menu to the cafe page", DIGEST_TWO)), "decide")
    assert (decision.change, decision.reuse_nodes) == ("reuse", ["website-cafe"])
    assert [(d.ref, d.dept, d.scope) for d in decision.assignments] == [("a1", "website-cafe", None)]
    assert decision.assignments[0].brief == "Add a menu to the cafe page"


def test_decide_reuses_on_a_word_of_the_name_alone():
    decision = parse("chat_turn", answer("decide", decide_prompt("Quotes for sales", DIGEST_TWO)), "decide")
    assert decision.reuse_nodes == ["sales-leads"]


def test_decide_adds_when_no_word_is_shared_and_ignores_divisions_and_filler():
    decision = parse("chat_turn", answer("decide", decide_prompt("Plan the staff rota", DIGEST_TWO)), "decide")
    assert decision.change == "add"
    team = "\n".join([DIGEST_EMPTY, "sales-team | Sales Team | Sales", "  menu | Menu | The staff rota"])      # only a division mentions 'rota'
    assert parse("chat_turn", answer("decide", decide_prompt("A team for rota", team)), "decide").change == "add"


def test_change_is_one_add_op_under_the_root_named_from_the_message():
    request = parse("chart_change_request", answer("change", change_prompt(CAFE, "Org chart revision 4. Root id: org.")))
    assert len(request.ops) == 1 and request.reuses == []
    node = request.ops[0].node
    assert (request.ops[0].op, node.kind, node.name, node.parent, node.ref) == ("add", "department", "Website Cafe", "org", "$team")
    assert node.purpose == CAFE and "Website Cafe" in request.reason


def test_a_long_multi_line_message_is_cut_to_the_goal_and_the_name():
    message = "Please build an online ordering website for my small neighbourhood coffee shop\nwith a menu and opening hours " * 3
    node = parse("chart_change_request", answer("change", change_prompt(message))).ops[0].node
    assert len(node.purpose) == 120 and node.purpose.endswith("…") and node.name == "Build Online Ordering Website"


@pytest.mark.parametrize("message, name", [
    ("A website for my cafe", "Website Cafe"),
    ("sales", "Sales Team"),
    ("the and of", "General Team"),
    ("Coffee Coffee beans roastery wholesale", "Coffee Beans Roastery Wholesale"),
])
def test_a_team_name_is_two_to_four_words(message, name):
    assert topic_name(message) == name


def test_assign_names_the_message_and_the_department_the_change_added():
    plan = parse("chat_turn", answer("assign", assign_prompt(CAFE, DIGEST_TWO)), "assignments")
    assert [(d.dept, d.title, d.brief) for d in plan.assignments] == [("website-cafe", CAFE, CAFE)]


def test_assign_prefers_the_team_named_like_the_topic_and_falls_back_to_the_newest():
    both = "\n".join([DIGEST_EMPTY, "web-old | Web | A website for my cafe", "web-topic | Website Cafe | A website for my cafe",
                      "web-new | Web | A website for my cafe"])
    assert parse("chat_turn", answer("assign", assign_prompt(CAFE, both)), "assignments").assignments[0].dept == "web-topic"
    newest = "\n".join([DIGEST_EMPTY, "web-old | Web | A website for my cafe", "web-new | Web | A website for my cafe"])
    assert parse("chat_turn", answer("assign", assign_prompt(CAFE, newest)), "assignments").assignments[0].dept == "web-new"
    other = "\n".join([DIGEST_EMPTY, SALES_LINE, "marketing | Marketing | Ads"])
    assert parse("chat_turn", answer("assign", assign_prompt("Something else entirely", other)), "assignments").assignments[0].dept == "marketing"


def test_assign_without_a_department_is_a_clear_error():
    with pytest.raises(ValueError, match="no department"):
        answer("assign", assign_prompt(CAFE, DIGEST_EMPTY))


def test_decide_change_and_assign_agree_on_a_new_team():
    name = parse("chart_change_request", answer("change", change_prompt(CAFE))).ops[0].node.name
    after = "\n".join([DIGEST_EMPTY, f"website-cafe | {name} | {CAFE} | live: - | last: -"])
    assert parse("chat_turn", answer("decide", decide_prompt(CAFE)), "decide").change == "add"
    assert parse("chat_turn", answer("assign", assign_prompt(CAFE, after)), "assignments").assignments[0].dept == "website-cafe"
    reused = parse("chat_turn", answer("decide", decide_prompt(CAFE, after)), "decide")
    assert reused.assignments[0].dept == reused.reuse_nodes[0] == "website-cafe"


@pytest.mark.parametrize("stage, build", [("decide", decide_prompt), ("change", change_prompt), ("assign", lambda m: assign_prompt(m, DIGEST_TWO))])
def test_a_retry_of_a_stage_gets_the_same_answer_as_the_stage(stage, build):
    assert answer(stage, build(CAFE) + RETRY) == answer(stage, build(CAFE))


def test_a_prompt_that_is_not_the_chat_agents_is_refused():
    with pytest.raises(ValueError, match="OWNER REQUEST"):
        answer("decide", "hello")


def test_the_book_has_exactly_the_three_stages_and_the_stub_it_asks_for():
    book = demo_book()
    assert isinstance(book, DemoBook) and len(book) == 3 and book.connector_class is DemoStub
    assert all(("chat_agent", stage) in book for stage in ("decide", "change", "assign"))
    assert issubclass(DemoStub, StubConnector)


# ---- wiring ---------------------------------------------------------------------------------------------------------------------

def router_for(tmp_path, *, connector="auto", offline=True, replybook=None):
    settings = SimpleNamespace(data_dir=tmp_path, connector=connector, offline=offline)
    return build_router(settings, config=ConnectorConfig(data_dir=tmp_path), replybook=replybook)


def test_the_factory_gives_the_book_to_a_stub_only_router(tmp_path):
    book = demo_book()
    stub = router_for(tmp_path, replybook=book).connectors["stub"]
    assert type(stub) is DemoStub and stub.book is book
    plain = ReplyBook()
    assert type(router_for(tmp_path, connector="stub", offline=False, replybook=plain).connectors["stub"]) is StubConnector
    assert router_for(tmp_path).connectors["stub"].book is not book and type(router_for(tmp_path).connectors["stub"]) is StubConnector


def test_the_stub_answers_a_chat_agent_call_from_the_book(tmp_path):
    router = router_for(tmp_path, replybook=demo_book())
    reply = asyncio.run(AsyncConnector(router).call_json(decide_prompt(CAFE), schema=None, function="chat_agent", step="decide"))
    assert reply[0]["change"] == "add" and reply[2] == "stub"
    assert router.connectors["stub"].calls[-1].rule == "book"


def services_for(tmp_path, **changes):
    settings = Settings.load({}, data_dir=tmp_path / "data", token="t" * 24, env_file=tmp_path / "none.env", engine="fake", **changes)
    return build_services(settings)


def test_offline_services_use_the_demo_book_and_nothing_else_does(tmp_path):
    offline = services_for(tmp_path / "a", offline=True)
    assert type(offline.connector_router.connectors["stub"]) is DemoStub
    stub_only = services_for(tmp_path / "b", connector="stub")
    assert type(stub_only.connector_router.connectors["stub"]) is StubConnector and not stub_only.settings.offline


# ---- the real ChatAgent over the stub with the book -----------------------------------------------------------------------------

class Demo:
    """The chat agent over the offline stub, on a real chart; `say` plans one message and applies its change like the runner does."""

    def __init__(self, db, settings, clock, events, tmp_path) -> None:
        self.env = Env(db, settings, clock, events)
        self.router = router_for(tmp_path, replybook=demo_book())
        self.agent = ChatAgent(AsyncConnector(self.router), self.env.chart, clock=clock)
        self.n = 0

    def say(self, text):
        self.n += 1
        plan = asyncio.run(self.agent.plan(PlanRequest(text=text, message_id=self.n)))
        ctx = ChangeContext(session_id="cs_org", message_id=self.n, request_id=f"req-{self.n}", request_title=text)
        self.env.chart.apply(plan.change, actor="chat_agent", ctx=ctx)
        return plan

    def departments(self):
        return [(n.id, n.name, n.purpose) for n in self.env.head().nodes if n.kind == "department"]


def test_three_messages_make_reuse_and_add_teams(db, settings, clock, events, tmp_path):
    d = Demo(db, settings, clock, events, tmp_path)
    first = d.say(CAFE)
    assert (first.outcome, first.keywords, first.decision.change, first.change.model.kind) == ("work", False, "add", "add")
    assert d.departments() == [("website-cafe", "Website Cafe", CAFE)]
    assert [(x.dept, x.brief) for x in first.drafts] == [("website-cafe", CAFE)] and first.calls == 3

    second = d.say("Add a menu to the cafe page")
    assert (second.keywords, second.decision.change, second.change.model.kind, second.change.model.reuses) == (False, "reuse", "reuse", ["website-cafe"])
    assert [x.dept for x in second.drafts] == ["website-cafe"] and len(d.departments()) == 1 and second.calls == 1

    third = d.say("Track sales leads and quotes")
    assert (third.keywords, third.change.model.kind) == (False, "add") and [x.dept for x in third.drafts] == [third.added[0]]
    assert [name for _, name, _ in d.departments()] == ["Website Cafe", "Track Sales Leads Quotes"]

    stub = d.router.connectors["stub"]
    assert {c.rule for c in stub.calls} == {"book"} and [c.stage for c in stub.calls] == ["decide", "change", "assign", "decide", "decide", "change", "assign"]
    assert all(c.function == "chat_agent" for c in stub.calls)

