"""Replies a model reasonably gives that the closed models used to refuse (P033, D158): the project output's rubric ids, a text over
its cap, and the corrected checks of an atom verdict worded the way J2's prompt words them. Each fixture is the reply as it failed."""
import json

import pytest

pytest.importorskip("sutra_app.engine")

from sutra_app.engine import capabilities, j2, j2_types  # noqa: E402
from sutra_app.library.evaluation import ConditionResult, RubricResult  # noqa: E402
from sutra_app.library.functions import REPLY_CLASSES, RubricRow  # noqa: E402
from sutra_app.library.replies import ReplyInvalid, ReplyParser  # noqa: E402

PARSER = ReplyParser()
GOAL = {"statement": "S", "site_name": "N", "done_when": ["a", "b", "c"]}


def outputs() -> dict:
    """Every output type J2 knows, read from the data (types.json, the local types and what the capabilities register)."""
    capabilities.register(j2)
    return {name: j2.output_def(name) for name in j2_types.names()}


def report(rubric):
    return {"say": "x", "findings": [], "rubric": rubric, "next": "Identity"}


# ---- 1: the ids ------------------------------------------------------------------------------------------------------------
def test_the_project_rubric_ids_are_accepted_by_the_audit_reply():
    rows = [{"id": f"PJ-{n}", "verdict": "PASS", "evidence": "seen"} for n in range(1, 6)]
    assert [r.id for r in PARSER.parse("audit", report(rows), kind="report").model.rubric] == [f"PJ-{n}" for n in range(1, 6)]


def test_every_rubric_and_condition_id_the_application_registers_is_accepted():
    seen = 0
    for name, out in outputs().items():
        for rid, text in out["rubric"]:
            RubricRow(id=rid, verdict="PASS", evidence="e")
            RubricResult.model_validate({"id": rid, "verdict": "PASS", "note": "n", "pass": True})
            seen += 1
        for cond in j2.load_conditions(out["conditions"]):
            ConditionResult.model_validate({"id": cond["id"], "met": True, "evidence": "e"})
            seen += 1
    assert seen > 30 and "project" in outputs()


@pytest.mark.parametrize("bad", ["R1", "r-1", "R-", "R-1234", "RUBRIC-1", "PJ_1", ""])
def test_a_rubric_id_still_needs_its_shape(bad):
    with pytest.raises(ReplyInvalid):
        PARSER.parse("audit", report([{"id": bad, "verdict": "PASS", "evidence": "e"}]), kind="report")


def test_the_project_conditions_file_ids_are_the_ones_the_model_accepts():
    for cond in j2.load_conditions(outputs()["project"]["conditions"]):
        assert ConditionResult.model_validate({"id": cond["id"], "met": False, "evidence": "e"}).id == cond["id"]


# ---- 2: a text over its cap ----------------------------------------------------------------------------------------------
def intake(**over):
    return {"say": "", "enough": True, "next": "Adaptation", "goal": GOAL, **over}


def test_a_to_agents_of_700_characters_is_refused_as_before_and_cut_when_asked():
    reply = intake(to_agents="@Adaptation " + "x" * 688)
    with pytest.raises(ReplyInvalid):
        PARSER.parse("identity", reply, kind="intake")
    parsed = PARSER.parse("identity", reply, kind="intake", clip_text=True)
    assert len(parsed.model.to_agents) == 600 and parsed.model.to_agents.endswith("…")
    assert parsed.clipped == ["to_agents (700 > 600)"]


def test_texts_inside_the_charter_and_lists_are_cut_too_and_ids_never():
    goal = {**GOAL, "done_when": ["a" * 650, "b", "c"], "facts": ["f" * 301]}
    parsed = PARSER.parse("identity", intake(goal=goal, say="s" * 4100), kind="intake", clip_text=True)
    assert sorted(parsed.clipped) == ["goal.done_when.0 (650 > 600)", "goal.facts.0 (301 > 300)", "say (4100 > 4000)"]
    with pytest.raises(ReplyInvalid):          # an id has a pattern: it is never cut into another id
        PARSER.parse("coordination", {"say": "", "rule": "r", "order": ["W-" + "1" * 20], "next": "Priority"}, kind="schedule", clip_text=True)


def test_a_text_that_fits_is_left_alone_and_other_errors_still_refuse():
    assert PARSER.parse("identity", intake(to_agents="short"), kind="intake", clip_text=True).clipped == []
    with pytest.raises(ReplyInvalid):
        PARSER.parse("identity", intake(to_agents="y" * 700, next="Nobody"), kind="intake", clip_text=True)


def test_the_check_closes_recovered_for_a_cut_text():
    from sutra_app.engine.fnodes.checks import RECOVERED, CheckRunner
    from sutra_app.engine.fnodes.evidence import Evidence
    from sutra_app.engine.fnodes.registry import REGISTRY
    from sutra_app.engine.hooks import TurnInfo
    turn = TurnInfo(run_id="r", dept_id="web", task_id="t", turn_no=1, function="identity", kind="intake", step=1, step_label="", cycle=1,
                    stage="website", task="", context=[])
    ev = Evidence(turn=turn, reply=intake(to_agents="z" * 700), replies=[intake(to_agents="z" * 700)])
    out = REGISTRY.run("reply-valid", ev, ("identity", "intake"))
    assert out.ok and out.changed == ("to_agents (700 > 600)",)
    assert CheckRunner.words(out).startswith(RECOVERED + "text over its limit")


# ---- 3: the corrected checks of an atom verdict, as J2's prompt words them -----------------------------------------------------
def test_the_checks_of_the_prompts_example_pass_the_atom_verdict():
    example = j2.EXAMPLE_WORKFLOW["atoms"][0]["verification"]            # {text, type, target, expect}: what the prompt shows
    verdict = {"say": "@Coordination The check is wrong.", "verdict": "CHECK_WRONG", "atom": "W-1.a1",
               "verification": [{**c, "item": n} for n, c in enumerate(example, 1)]}
    model = PARSER.parse("adaptation", json.dumps(verdict), kind="atom_verdict").model
    assert [(c.template, c.args, c.expect) for c in model.verification] == [
        ("element-count", ["#contact"], 1), ("named-test", ["form-has-submit"], True)]


def test_the_librarys_own_check_shape_still_passes_the_atom_verdict():
    verdict = {"say": "s", "verdict": "CHECK_WRONG", "atom": "W-1.a1", "verification": [{"template": "element-count", "args": ["#a"], "expect": 2}]}
    assert PARSER.parse("adaptation", verdict, kind="atom_verdict").model.verification[0].args == ["#a"]


def test_every_reply_class_is_still_registered():
    assert len(REPLY_CLASSES) == 14
