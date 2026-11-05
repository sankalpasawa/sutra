"""Declare and atom ids (WP E6, engine design 4.3a, function-nodes.md sections 2.3, 2.4 and 3): a `TurnInfo` and a `FunctionSpec`
become an `AtomDraft` before the work; ids count per (run, node) from 1 and every open attempt consumes a number."""
import pytest

from sutra_app.engine.fnodes.declare import (DeclareError, declare, declare_question, has_work_to_schedule, pick_template,
                                              predicted_work, spec_kind)
from sutra_app.engine.fnodes.ids import AtomIds, node_id_of, run_overhead_id
from sutra_app.engine.hooks import TurnInfo
from sutra_app.library.atom import BANAL_GOAL_RE, open_atom
from sutra_app.library.node import FunctionSpecs, load_function_specs
from sutra_app.library.types import ATOM_ID_RE, FUNCTIONS, IdError, atom_sid, function_atom_id, overhead_atom_id

SPECS: FunctionSpecs = load_function_specs()


def turn(function="identity", kind="intake", **fields) -> TurnInfo:
    base = dict(run_id="j2-run-1", dept_id="web", turn_no=1, function=function, kind=kind, step=1, step_label="J2.a Identity intake",
                cycle=1, task="the brief is in", context=[("charter", "none yet")])
    return TurnInfo(**{**base, **fields})


def draft(function="identity", kind="intake", **kw):
    return declare(turn(function, kind), SPECS.specs[function], **kw)


def names(d):
    return [c.template for c in d.verify.checks]


def spec_with(function, **changes):
    """A copy of one shipped spec with some fields changed, in a FunctionSpecs-free form (the declare functions take one spec)."""
    return SPECS.specs[function].evolve(**changes)


# ---- ids --------------------------------------------------------------------------------------------------------------

def test_ids_count_per_run_and_node_from_one():
    ids = AtomIds()
    assert [ids.next("j2-a", "web.identity") for _ in range(3)] == [function_atom_id(atom_sid("j2-a", "web.identity"), n) for n in (1, 2, 3)]
    assert ids.next("j2-a", "web.audit").endswith("-01")           # another node starts again
    assert ids.next("j2-b", "web.identity").endswith("-01")        # so does another run
    assert ids.last("j2-a", "web.identity") == 3 and ids.last("j2-z", "web.identity") == 0


def test_ids_come_from_the_library_and_match_the_atom_id_pattern():
    ids = AtomIds()
    atom_id = ids.next("j2-20261104-100004-7f3a", "sales.priority")
    assert ATOM_ID_RE.fullmatch(atom_id) and atom_id == f"a-{AtomIds.sid('j2-20261104-100004-7f3a', 'sales.priority')}-01"
    assert node_id_of("sales", "priority") == "sales.priority"
    assert run_overhead_id("j2-x") == overhead_atom_id("j2-x")


def test_a_bad_id_part_spends_no_number():
    ids = AtomIds()
    with pytest.raises(IdError):
        ids.next("", "web.identity")
    assert ids.last("", "web.identity") == 0
    with pytest.raises(IdError):
        node_id_of("Bad Dept", "identity")


# ---- the template -----------------------------------------------------------------------------------------------------

def test_template_by_function_and_kind_else_generic():
    assert pick_template(SPECS.specs["identity"], "audit").name == "audit"
    assert pick_template(SPECS.specs["priority"], "envelope").name == "envelope"
    assert pick_template(SPECS.specs["identity"], "resolve").name == "generic"
    assert pick_template(SPECS.specs["adaptation"], None).name == "generic"
    assert draft("adaptation", "dispute").goal == "The adaptation answers the hand-off dispute with a reply that follows its rules"


def test_the_price_turn_arrives_as_proposal():
    assert spec_kind("priority", "proposal") == "price" and spec_kind("identity", "proposal") == "proposal" and spec_kind("audit", None) is None
    d = draft("priority", "proposal")
    assert names(d) == ["reply-valid", "turn-posted", "price-kept", "within-budget"]
    assert d.verify.checks[0].args == ["priority", "price"]


def test_a_turn_without_a_kind_is_declared_as_a_turn():
    d = draft("adaptation", None)
    assert "hand-off turn" in d.goal and names(d) == ["turn-posted"]


def test_goal_names_the_turn_and_is_never_banal_or_empty():
    custom = spec_with("identity", atom_templates=[{**SPECS.specs["identity"].atom_templates[-1].model_dump(), "goal": "{task}"}])
    for task in ("done", "", "  fix  "):
        d = declare(turn(kind="anything", task=task), custom)
        assert d.goal and not BANAL_GOAL_RE.fullmatch(d.goal) and len(d.goal) <= 600
    assert declare(turn(kind="anything", task="Say it"), custom).goal == "Say it"          # a good goal is kept as it is
    long = declare(turn(kind="anything", task="x" * 900), custom)
    assert len(long.goal) == 600


def test_goal_text_is_filled_from_the_turn():
    template = SPECS.specs["identity"].atom_templates[-1].model_dump() | {"goal": "{function}/{kind}/{step_label}/{task}"}
    d = declare(turn(kind="limit"), spec_with("identity", atom_templates=[template]))
    assert d.goal == "identity/limit/J2.a Identity intake/the brief is in"


# ---- constraints, context, work, outputs ------------------------------------------------------------------------------

def test_constraints_are_the_first_twenty_may_not_without_a_check():
    custom = spec_with("audit", may_not=[f"rule {i}" for i in range(20)])
    d = declare(turn("audit", "audit"), custom)
    assert [c.text for c in d.constraints] == custom.may_not and all(c.check is None for c in d.constraints)
    assert [c.text for c in draft("audit", "audit").constraints] == SPECS.specs["audit"].may_not[:20]


def test_context_is_rendered_as_kind_colon_summary_and_bounded():
    pairs = [(f"k{i}", "s" * 300) for i in range(45)]
    d = declare(turn(context=pairs), SPECS.specs["identity"])
    assert len(d.context) == 40 and all(len(line) <= 200 for line in d.context) and d.context[0].startswith("k0: s")
    assert draft().context == ["charter: none yet"]
    assert declare(turn(context=[]), SPECS.specs["identity"]).context == []


def test_work_fields_outputs_and_touches():
    d = draft("priority", "price")
    assert (d.work.dispatch_kind, d.work.how_kind, d.work.agent, d.work.steps) == ("llm", "AI", "priority", "J2.a Identity intake")
    assert d.outputs == [SPECS.specs["priority"].yields] and d.touches == [] and d.model is None and d.effort is None
    bash = draft("priority", "envelope")
    assert (bash.work.dispatch_kind, bash.work.how_kind) == ("bash", "code")


def test_schedule_is_bash_only_when_nothing_is_registered_or_held():
    registered = [{"id": "W-1", "status": "registered"}]
    assert draft("coordination", "schedule", workflows=None).work.dispatch_kind == "bash"
    assert draft("coordination", "schedule", workflows=[{"id": "W-0", "status": "done"}]).work.dispatch_kind == "bash"
    assert draft("coordination", "schedule", workflows=registered).work.dispatch_kind == "llm"
    assert draft("coordination", "schedule", workflows=[{"id": "W-3", "status": "held"}]).work.dispatch_kind == "llm"
    assert has_work_to_schedule(registered) and not has_work_to_schedule(["junk", None])
    # the rule is about Coordination's schedule turn only
    assert draft("priority", "price", workflows=None).work.dispatch_kind == "llm"


def test_a_caller_can_ask_for_the_other_work_kind():
    assert draft("priority", "envelope", work="llm").work.dispatch_kind == "llm"
    assert predicted_work(SPECS.specs["coordination"], pick_template(SPECS.specs["coordination"], "schedule"), "schedule", None, "llm") == "llm"


# ---- verify -----------------------------------------------------------------------------------------------------------

def test_floor_checks_come_first_by_work_kind():
    assert names(draft("identity", "intake")) == ["reply-valid", "turn-posted", "charter-stamp", "audience-split"]
    assert names(draft("audit", "audit")) == ["reply-valid", "turn-posted", "finding-per-item", "pass-needs-proof", "code-measure-wins"]
    assert names(draft("priority", "envelope")) == ["turn-posted", "within-budget"]               # bash: turn-posted only
    assert names(draft("identity", "resolve")) == ["reply-valid", "turn-posted"]                  # generic kind with a reply family
    assert names(draft("identity", "limit")) == ["turn-posted"]                                    # no reply family and kind named
    assert names(draft("identity", "approval"))[0] == "reply-valid" and draft("identity", "approval").verify.checks[0].args == ["identity", "approval|approval_ask"]


def test_the_manual_atom_has_no_floor_checks():
    q = declare_question(turn(), SPECS.specs["identity"], 7, question="Which colour?", pause="questions")
    assert names(q) == ["answer-recorded"] and q.verify.checks[0].args == ["7"]
    assert (q.work.dispatch_kind, q.work.agent, q.work.how_kind) == ("manual", "owner", "code")
    assert q.goal == "The owner's answer to the first question is recorded"
    assert q.context == ["question: Which colour?", "pause: questions"] and q.outputs == [SPECS.specs["identity"].yields]


def test_manual_atom_without_text_names_the_message_and_without_a_template_uses_ours():
    q = declare_question(turn(), SPECS.specs["identity"], 12)
    assert q.context == ["question: message 12"]
    bare = spec_with("identity", atom_templates=[SPECS.specs["identity"].atom_templates[-1]])      # only `generic`
    fallback = declare_question(turn(), bare, 3)
    assert names(fallback) == ["answer-recorded"] and fallback.verify.checks[0].args == ["3"] and fallback.work.dispatch_kind == "manual"
    assert "answer" in fallback.goal


def test_each_check_carries_the_registry_sentence_as_text_and_relevance():
    for check in draft("identity", "intake").verify.checks:
        assert check.text and check.relevance == check.text and len(check.text) <= 300 and check.relevance_source == "declared"


def test_a_placeholder_needs_a_question_id_and_a_turn_must_match_its_spec():
    answer_spec = SPECS.specs["identity"]
    with pytest.raises(DeclareError, match="question message id"):
        declare(turn(kind="answer"), answer_spec)
    assert declare(turn(kind="answer"), answer_spec, question_id=9).verify.checks[-1].args == ["9"]
    with pytest.raises(DeclareError, match="spec is audit"):
        declare(turn("identity"), SPECS.specs["audit"])


def test_a_template_check_that_repeats_a_floor_is_not_added_twice():
    template = SPECS.specs["audit"].atom_templates[-1].model_dump() | {"name": "audit", "checks": [{"name": "turn-posted", "args": []},
                                                                                                  {"name": "pass-needs-proof", "args": []}]}
    d = declare(turn("audit", "audit"), spec_with("audit", atom_templates=[template, SPECS.specs["audit"].atom_templates[-1]]))
    assert names(d) == ["reply-valid", "turn-posted", "pass-needs-proof"]


def test_a_check_outside_the_registry_is_declared_without_text():
    template = SPECS.specs["audit"].atom_templates[-1].model_dump() | {"name": "audit", "checks": [{"name": "file-exists", "args": ["site/index.html"]}],
                                                                       "touches": ["site/"]}
    d = declare(turn("audit", "audit"), spec_with("audit", atom_templates=[template, SPECS.specs["audit"].atom_templates[-1]]))
    last = d.verify.checks[-1]
    assert (last.template, last.args, last.text, last.relevance) == ("file-exists", ["site/index.html"], "", None) and d.touches == ["site/"]


def test_every_production_template_opens_without_refusal():
    """Production templates never refuse (function-nodes.md 5.3): a refusal would be a template bug made visible."""
    seen = 0
    for function in FUNCTIONS:
        spec = SPECS.specs[function]
        for kind in [*(k.kind for k in spec.task_kinds), "proposal", "unheard-of", None]:
            for workflows in (None, [{"id": "W-1", "status": "registered"}]):
                d = declare(turn(function, kind), spec, workflows=workflows)
                tr = open_atom(d, id="a-abc-01", node_id=f"web.{function}", now=1)
                assert tr.outcome == "opened", (function, kind, tr.refusal)
                seen += 1
    q = declare_question(turn(), SPECS.specs["identity"], 4)
    assert open_atom(q, id="a-abc-02", node_id="web.identity", now=1).outcome == "opened" and seen > 40
