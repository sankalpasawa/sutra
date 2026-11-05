"""The seed FunctionSpecs (WP L10): `sutra_app/library/specs/function_specs.json` loads, every reference in it resolves
(`REGISTRY.verify_refs()` looks at a NON-EMPTY set), every template opens without refusal for a sample turn, and the data
is the table of docs/design/function-nodes.md section 3 (named checks, yields, work hints).

Importing `sutra_app.library.functions` is what registers the reply families the task kinds name; a program that
verifies the specs must import it (the engine and L8's `all.py` do)."""
import json
import re
import string
from pathlib import Path

import pytest

import sutra_app.library.functions  # noqa: F401  (registers the five reply families verify_refs resolves)
from sutra_app.engine.hooks import TurnInfo
from sutra_app.library.atom import (
    BANAL_GOAL_RE, CHECK_NAMES, REGISTRY_CHECKS, AtomDraft, Check, Constraint, Verify, Work, check_arity, open_atom, open_rules,
)
from sutra_app.library.node import (
    ALLOWED_GOAL_FIELDS, DEFAULT_SPECS_PATH, AtomTemplate, FunctionSpecs, load_function_specs, new_function_node,
    refresh_function_nodes,
)
from sutra_app.library.registry import REGISTRY, RegistryError
from sutra_app.library.types import FUNCTIONS

SPEC_FILE = Path(__file__).resolve().parents[2] / "sutra_app" / "library" / "specs" / "function_specs.json"
AGENT_DIR = Path(__file__).resolve().parents[2] / "sutra_app" / "engine" / "agents" / "j2"
SPECS = load_function_specs()
GENERIC_GOAL = "The {function} answers the hand-off {kind} with a reply that follows its rules"

# function-nodes.md section 3: (function, template name) -> (work hint, named checks as (name, args))
TABLE = {
    ("identity", "intake"): ("llm", [("charter-stamp", ()), ("audience-split", ())]),
    ("identity", "audit"): ("llm", [("workable", ()), ("audience-split", ())]),
    ("identity", "requester_answered"): ("llm", [("audience-split", ())]),
    ("identity", "approval"): ("llm", [("audience-split", ())]),
    ("identity", "ruling_budget"): ("llm", [("audience-split", ())]),
    ("identity", "answer"): ("manual", [("answer-recorded", ("{question_message_id}",))]),
    ("identity", "generic"): ("llm", []),
    ("adaptation", "propose"): ("llm", [("atom-rules", ()), ("judge-gate", ())]),
    ("adaptation", "respond"): ("llm", [("atom-rules", ())]),
    ("adaptation", "generic"): ("llm", []),
    ("priority", "price"): ("llm", [("price-kept", ()), ("within-budget", ())]),
    ("priority", "ruling"): ("llm", [("price-kept", ()), ("within-budget", ())]),
    ("priority", "envelope"): ("bash", [("within-budget", ())]),
    ("priority", "generic"): ("llm", []),
    ("coordination", "schedule"): ("llm", [("order-registered", ())]),
    ("coordination", "generic"): ("llm", []),
    ("audit", "audit"): ("llm", [("finding-per-item", ()), ("pass-needs-proof", ()), ("code-measure-wins", ())]),
    ("audit", "generic"): ("llm", []),
}
YIELDS = {"identity": "charter, rule, question", "adaptation": "proposal with its checks", "priority": "GRANT, COUNTER, REFUSE",
          "coordination": "rule, order, holds", "audit": "one finding per item"}
STAGES = {"identity": ["J2.a", "J2.d", "J2.h"], "adaptation": ["J2.b"], "priority": ["J2.c", "J2.f"], "coordination": ["J2.f"],
          "audit": ["J2.g"]}
TASK_KINDS = {
    "identity": ["intake", "stage_decision", "resolve", "approval", "audit", "requester_answered", "ruling_budget", "limit",
                 "send_confirm", "question"],
    "adaptation": ["propose", "respond", "dispute", "atom_failed", "change"],
    "priority": ["price", "dispute", "envelope", "ruling"],
    "coordination": ["schedule", "dispute"],
    "audit": ["audit", "dispute"],
}
REPLIES = {      # (function, kind) -> (reply family, reply kind); every other task kind names no reply
    ("identity", "intake"): ("identity", "intake"), ("identity", "resolve"): ("identity", "ruling"),
    ("identity", "approval"): ("identity", "approval|approval_ask"), ("identity", "audit"): ("identity", "done"),
    ("identity", "requester_answered"): ("identity", "heard"),
    ("adaptation", "propose"): ("adaptation", "propose"), ("adaptation", "respond"): ("adaptation", "respond"),
    ("adaptation", "atom_failed"): ("adaptation", "atom_verdict"),
    ("priority", "price"): ("priority", "price"), ("priority", "ruling"): ("priority", "price"),
    ("priority", "envelope"): ("priority", "envelope_check"), ("coordination", "schedule"): ("coordination", "schedule"),
    ("audit", "audit"): ("audit", "report"),
}


def template_of(function: str, name: str) -> AtomTemplate:
    return next(t for t in SPECS.specs[function].atom_templates if t.name == name)


def all_check_refs():
    return [(fn, t.name, ref) for fn in FUNCTIONS for t in SPECS.specs[fn].atom_templates for ref in t.checks]


def turn(function: str, kind: str | None, **over) -> TurnInfo:
    base = dict(run_id="r-1", dept_id="sales", task_id="tsk_0123456789ab", turn_no=3, function=function, kind=kind, step=2,
                step_label="J2.b Adaptation proposes workflows", cycle=1, stage=None, task="the brief needs a charter",
                context=[("charter", "a menu site for a cafe"), ("chat", "the owner asked for a menu")])
    return TurnInfo(**{**base, **over})


def declare(spec, info: TurnInfo) -> AtomDraft:
    """A minimal stand-in for E6's declare: the template by kind else generic, the floors by work kind, constraints from
    may_not. It exists to prove the seed templates open; E6 owns the real one."""
    task_kind = next((k for k in spec.task_kinds if k.kind == info.kind), None)
    template = next((t for t in spec.atom_templates if t.name == info.kind), None) or next(
        t for t in spec.atom_templates if t.name == "generic")
    return build_draft(spec, template, task_kind, info)


def build_draft(spec, template: AtomTemplate, task_kind, info: TurnInfo) -> AtomDraft:
    goal = template.goal.format(function=info.function, kind=info.kind or "", step_label=info.step_label, task=info.task)
    checks = [Check(template=ref.name, args=[a.replace("{question_message_id}", "14") for a in ref.args], text=ref.name)
              for ref in template.checks]
    hint = template.work_hint
    if task_kind is not None and task_kind.reply_family and hint == "llm":
        checks.insert(0, Check(template="reply-valid", args=[task_kind.reply_family, task_kind.reply_kind], text="reply-valid"))
    if hint != "manual":
        checks.append(Check(template="turn-posted", text="turn-posted"))
    return AtomDraft(
        goal=goal, constraints=[Constraint(text=t) for t in spec.may_not[:20]], context=[f"{k}: {v}" for k, v in info.context],
        work=template.work.evolve(dispatch_kind=hint, steps=info.step_label), outputs=[spec.yields], verify=Verify(checks=checks))


# ---- the file and the five specs ------------------------------------------------------------------------------------

def test_the_default_path_is_the_shipped_file():
    assert DEFAULT_SPECS_PATH == SPEC_FILE
    assert SPEC_FILE.is_file() and SPEC_FILE.stat().st_size < 64 * 1024


def test_the_file_is_json_with_a_function_specs_kind_and_loads_to_five_specs():
    data = json.loads(SPEC_FILE.read_text(encoding="utf-8"))
    assert set(data) == {"kind", "specs"} and data["kind"] == "function_specs"
    assert isinstance(SPECS, FunctionSpecs) and list(SPECS.specs) == list(FUNCTIONS)
    assert all(spec.function == key for key, spec in SPECS.specs.items())


def test_every_spec_starts_at_version_one():
    assert {fn: spec.version for fn, spec in SPECS.specs.items()} == dict.fromkeys(FUNCTIONS, 1)


@pytest.mark.parametrize("function", FUNCTIONS)
def test_goal_is_the_j2_role_sentence_of_the_agent_file(function):
    front = AGENT_DIR.joinpath(f"{function}.md").read_text(encoding="utf-8").split("---")[1]
    role = re.search(r"^role: (.+)$", front, re.M).group(1)
    assert SPECS.specs[function].goal == role


@pytest.mark.parametrize("function", FUNCTIONS)
def test_reads_come_from_the_agent_file(function):
    front = AGENT_DIR.joinpath(f"{function}.md").read_text(encoding="utf-8").split("---")[1]
    line = re.search(r"^reads: (.+)$", front, re.M).group(1)
    reads = SPECS.specs[function].reads
    assert reads and all(item in line for item in reads)
    assert reads == [item for item in reads if item]


def test_identity_reads_leave_out_envelope_decisions_because_the_code_strips_them():
    identity = SPECS.specs["identity"]
    line = re.search(r"^reads: (.+)$", AGENT_DIR.joinpath("identity.md").read_text(encoding="utf-8"), re.M).group(1)
    assert "envelope decisions" in line and "envelope decisions" not in identity.reads
    assert not any(re.search(r"budget|cost|envelope|rate", item) for item in identity.reads)


@pytest.mark.parametrize("function", FUNCTIONS)
def test_standing_lines_are_set_and_bounded(function):
    spec = SPECS.specs[function]
    assert spec.role.startswith("J2.")
    assert spec.yields == YIELDS[function]
    assert spec.stages == STAGES[function]
    assert spec.writes and spec.reads
    assert 1 <= len(spec.may_not) <= 20


@pytest.mark.parametrize("function", FUNCTIONS)
def test_the_task_kinds_are_the_j2_dispatchers_cases(function):
    assert [k.kind for k in SPECS.specs[function].task_kinds] == TASK_KINDS[function]


def test_each_role_names_the_j2_stage_letters_the_function_acts_in():
    for function in FUNCTIONS:
        spec = SPECS.specs[function]
        letters = {stage.split(".")[1] for stage in spec.stages}
        assert {part.split()[0].split(".")[1] for part in spec.role.split(",") if part.strip().startswith("J2.")} <= letters
    assert SPECS.specs["priority"].role == "J2.c prices, checks run limits"      # J2.f is its envelope stage, in `stages`


def test_may_not_carries_the_agent_files_you_may_not_lists():
    expected = {
        "identity": ["invent a new goal or rule", "increase an envelope", "choose which workflow runs first"],
        "adaptation": ["grant your own resources", "schedule a run", "declare your result correct"],
        "priority": ["say which accepted workflow runs first", "grant undeclared or unlimited resources"],
        "coordination": ["increase an envelope", "modify the workflow steps", "mark a result correct"],
        "audit": ["design the workflow", "repair the result", "decide policy"],
    }
    for function, items in expected.items():
        assert all(item in SPECS.specs[function].may_not for item in items), function


# ---- references --------------------------------------------------------------------------------------------------

def test_verify_refs_with_the_bound_source_finds_nothing_wrong():
    assert REGISTRY.verify_refs() == []
    assert REGISTRY.verify_refs(SPECS) == []


def test_verify_refs_looks_at_a_non_empty_set_of_checks():
    seen: list[str] = []

    def spy(name: str):
        seen.append(name)
        return check_arity(name)

    assert REGISTRY.verify_refs(check_arity=spy) == []
    wanted = [ref.name for _, _, ref in all_check_refs()]
    assert len(wanted) == 20 and sorted(seen) == sorted(wanted)      # every CheckRef of the file was judged, none skipped


def test_verify_refs_looks_at_every_reply_reference_too():
    broken = json.loads(SPEC_FILE.read_text(encoding="utf-8"))
    broken["specs"]["priority"]["task_kinds"][0]["reply_kind"] = "pricing"
    broken["specs"]["audit"]["atom_templates"][0]["checks"][0]["args"] = ["unexpected"]
    broken["specs"]["identity"]["atom_templates"][5]["checks"][0]["args"] = []
    found = REGISTRY.verify_refs(FunctionSpecs.model_validate(broken))
    assert sorted((v.code, v.path) for v in found) == [
        ("bad_check_args", "audit.atom_templates.audit.checks.0.args"),
        ("bad_check_args", "identity.atom_templates.answer.checks.0.args"),
        ("unknown_reply_kind", "priority.task_kinds.price.reply_kind"),
    ]


def test_an_unbound_registry_would_refuse_instead_of_passing():
    with pytest.raises(RegistryError) as caught:
        REGISTRY.verify_refs({})
    assert caught.value.code == "specs_empty"


def test_every_check_name_is_a_check_template_with_a_matching_argument_count():
    for function, name, ref in all_check_refs():
        assert ref.name in CHECK_NAMES, (function, name)
        low, high = check_arity(ref.name)
        assert low <= len(ref.args) <= high, (function, name, ref.name)


def test_the_seed_names_only_registry_checks_and_the_floors_are_left_to_declare():
    names = {ref.name for _, _, ref in all_check_refs()}
    assert names <= set(REGISTRY_CHECKS)
    assert not names & {"reply-valid", "turn-posted"}
    assert names == set(REGISTRY_CHECKS) - {"reply-valid", "turn-posted"}      # all twelve other registry checks are used


@pytest.mark.parametrize("function,kind", sorted(REPLIES))
def test_a_task_kind_with_a_reply_names_a_registered_family_and_every_kind_alternative(function, kind):
    task_kind = next(k for k in SPECS.specs[function].task_kinds if k.kind == kind)
    assert (task_kind.reply_family, task_kind.reply_kind) == REPLIES[function, kind]
    for alternative in task_kind.reply_kind.split("|"):
        assert alternative in REGISTRY.kinds(task_kind.reply_family)


def test_the_task_kinds_without_a_reply_name_neither_family_nor_kind():
    for function in FUNCTIONS:
        for task_kind in SPECS.specs[function].task_kinds:
            if (function, task_kind.kind) not in REPLIES:
                assert (task_kind.reply_family, task_kind.reply_kind) == ("", "")


# ---- templates ---------------------------------------------------------------------------------------------------

def test_the_templates_are_the_table_of_the_design():
    got = {(fn, t.name): (t.work_hint, [(c.name, tuple(c.args)) for c in t.checks])
           for fn in FUNCTIONS for t in SPECS.specs[fn].atom_templates}
    assert got == TABLE


@pytest.mark.parametrize("function", FUNCTIONS)
def test_the_generic_template_exists_names_no_check_and_serves_any_kind(function):
    generic = template_of(function, "generic")
    assert generic.goal == GENERIC_GOAL and generic.checks == [] and generic.work_hint == "llm"
    assert sum(t.name == "generic" for t in SPECS.specs[function].atom_templates) == 1


def test_a_template_is_named_for_a_task_kind_of_its_function_or_is_the_owner_answer_or_generic():
    for function in FUNCTIONS:
        spec = SPECS.specs[function]
        kinds = {k.kind for k in spec.task_kinds}
        for template in spec.atom_templates:
            assert template.name in kinds | {"generic", "answer"}, (function, template.name)
    assert [t.name for t in SPECS.specs["identity"].atom_templates if t.name not in {k.kind for k in SPECS.specs["identity"].task_kinds}] == [
        "answer", "generic"]


def test_seed_work_hints_priority_envelope_bash_identity_answer_manual_coordination_schedule_llm():
    assert template_of("priority", "envelope").work_hint == "bash"
    assert template_of("identity", "answer").work_hint == "manual"
    assert template_of("coordination", "schedule").work_hint == "llm"
    others = {(fn, t.name): t.work_hint for fn in FUNCTIONS for t in SPECS.specs[fn].atom_templates}
    assert sorted(k for k, v in others.items() if v != "llm") == [("identity", "answer"), ("priority", "envelope")]


def test_a_template_work_agrees_with_its_hint_and_function():
    for function in FUNCTIONS:
        for template in SPECS.specs[function].atom_templates:
            work = template.work
            assert work.dispatch_kind == template.work_hint
            if template.work_hint == "manual":
                assert (work.agent, work.how_kind) == ("owner", "code")
            else:
                assert work.agent == function
                assert work.how_kind == ("AI" if template.work_hint == "llm" else "code")


def test_templates_touch_nothing_and_stay_inside_the_bounds():
    for function in FUNCTIONS:
        spec = SPECS.specs[function]
        assert len(spec.atom_templates) <= 10 and len(spec.task_kinds) <= 20
        for template in spec.atom_templates:
            assert template.touches == [] and len(template.checks) <= 6


def test_judge_gate_is_only_on_propose():
    holders = [(fn, t.name) for fn in FUNCTIONS for t in SPECS.specs[fn].atom_templates if any(c.name == "judge-gate" for c in t.checks)]
    assert holders == [("adaptation", "propose")]


# ---- goals -------------------------------------------------------------------------------------------------------

def test_every_goal_names_only_the_four_allowed_fields():
    for function in FUNCTIONS:
        for template in SPECS.specs[function].atom_templates:
            names = [f for _, f, _, _ in string.Formatter().parse(template.goal) if f is not None]
            assert set(names) <= set(ALLOWED_GOAL_FIELDS), (function, template.name)


def test_every_goal_is_non_banal_after_filling():
    for function in FUNCTIONS:
        spec = SPECS.specs[function]
        for template in spec.atom_templates:
            for kind in [None, "intake", "dispute", "x"]:
                info = turn(function, kind)
                goal = template.goal.format(function=function, kind=kind or "", step_label=info.step_label, task=info.task)
                assert goal.strip() and not BANAL_GOAL_RE.fullmatch(goal), (function, template.name)
                assert len(goal) <= 600 and len(goal.split()) >= 5


# ---- every template opens ----------------------------------------------------------------------------------------

def sample_kinds(function: str) -> list[str | None]:
    return [*TASK_KINDS[function], None, "unlisted_kind"]


@pytest.mark.parametrize("function", FUNCTIONS)
def test_every_task_kind_opens_without_refusal_for_a_sample_turn(function):
    spec = SPECS.specs[function]
    for kind in sample_kinds(function):
        draft = declare(spec, turn(function, kind))
        assert open_rules(draft) is None, (function, kind)
        moved = open_atom(draft, id="a-0123456789-01", node_id=f"sales.{function}", now=7)
        assert moved.outcome == "opened" and moved.atom.state == "open" and moved.refusal is None, (function, kind)


def test_the_owner_question_template_opens_a_manual_atom_with_the_answer_check_only():
    spec = SPECS.specs["identity"]
    template = template_of("identity", "answer")
    draft = build_draft(spec, template, None, turn("identity", "question"))
    assert [c.template for c in draft.verify.checks] == ["answer-recorded"] and draft.verify.checks[0].args == ["14"]
    assert draft.work.dispatch_kind == "manual"
    moved = open_atom(draft, id="a-0123456789-02", node_id="sales.identity", now=7)
    assert moved.outcome == "opened"


def test_a_template_with_no_check_and_no_floor_would_be_refused_so_generic_relies_on_the_floors():
    spec = SPECS.specs["audit"]
    bare = AtomDraft(goal=GENERIC_GOAL.format(function="audit", kind="dispute"), work=template_of("audit", "generic").work)
    assert open_rules(bare).code == "verify_missing"
    assert open_rules(declare(spec, turn("audit", "dispute"))) is None


def test_the_floor_checks_follow_the_work_kind_and_the_reply_the_task_kind_names():
    spec = SPECS.specs["priority"]
    names = lambda info: [c.template for c in declare(spec, info).verify.checks]      # noqa: E731
    assert names(turn("priority", "price")) == ["reply-valid", "price-kept", "within-budget", "turn-posted"]
    assert names(turn("priority", "envelope")) == ["within-budget", "turn-posted"]      # bash: no reply, no reply-valid
    assert names(turn("priority", "dispute")) == ["turn-posted"]                          # generic, no reply named
    reply = next(c for c in declare(spec, turn("priority", "price")).verify.checks if c.template == "reply-valid")
    assert reply.args == ["priority", "price"]


def test_unknown_kinds_fall_back_to_generic_and_keep_the_standing_constraints():
    spec = SPECS.specs["identity"]
    draft = declare(spec, turn("identity", "limit"))
    assert draft.goal == GENERIC_GOAL.format(function="identity", kind="limit")
    assert [c.text for c in draft.constraints] == spec.may_not[:20] and all(c.check is None for c in draft.constraints)
    assert draft.outputs == ["charter, rule, question"]


# ---- the nodes made from the specs -------------------------------------------------------------------------------

def test_new_function_nodes_take_goal_task_and_context_from_the_seed():
    for function in FUNCTIONS:
        spec = SPECS.specs[function]
        node = new_function_node("sales", function, SPECS, 5)
        assert (node.goal, node.task, node.context, node.spec_version) == (spec.goal, spec.role, spec.reads, 1)
        assert node.id == f"sales.{function}" and node.state == "idle"


def test_a_version_two_seed_refreshes_the_nodes_made_from_version_one():
    nodes = [new_function_node("sales", fn, SPECS, 5) for fn in FUNCTIONS]
    data = json.loads(SPEC_FILE.read_text(encoding="utf-8"))
    data["specs"]["audit"]["version"] = 2
    data["specs"]["audit"]["goal"] = "independent check, with evidence"
    newer = FunctionSpecs.model_validate(data)
    refreshed = refresh_function_nodes(newer, nodes)
    assert [n.id for n in refreshed] == ["sales.audit"] and refreshed[0].goal == "independent check, with evidence"
    assert refresh_function_nodes(SPECS, nodes) == []


def test_the_work_model_of_every_template_is_the_atom_work_class():
    assert all(isinstance(t.work, Work) for fn in FUNCTIONS for t in SPECS.specs[fn].atom_templates)
