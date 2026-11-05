"""Goal (library design section 5): Question, the tbc facts, the two drafts and the stored charter (family "goal").

The charters below are J2's own: `mock_charter(<Brew Lab brief>)` and `mock_prd_charter` (the drafts), and the goal.json
that J2 33aeeda wrote for them in mock mode (the stored form: `core` gone, `charter_items` and `core_items` added)."""
import copy

import pytest
from pydantic import ValidationError

from sutra_app.library import goal as goal_module
from sutra_app.library.base import aliased_fields, unbounded_fields
from sutra_app.library.gate import GATE, GateError
from sutra_app.library.goal import (
    DocGoal, DocGoalDraft, DroppedReason, GoalDraft, Question, SiteGoal, SiteGoalDraft, TbcAnswer, ToBeConfirmed,
    UserGroup, goal_kind,
)
from sutra_app.library.registry import REGISTRY, is_transport_safe, transport_schema

ITEMS = ["The menu with prices is shown", "Opening hours are listed", "The address and a map link are shown",
         "Visitors can pre-order a coffee for pickup with a form", "A section about the beans and the farms they come from",
         "A loyalty-card explainer (buy 9, get the 10th free)", "Layout works on a phone"]
SITE_DRAFT = {   # J2 mock_charter(BREW_LAB), unchanged
    "statement": "A one-page website for Brew Lab where visitors find what they need and come in", "site_name": "Brew Lab",
    "audience": "Local customers, mostly on phones", "standards": ["Warm, modern feel", "Fast first screen on a phone"],
    "rules": ["Plain HTML/CSS/JS in one file", "No real customer data"], "done_when": ITEMS,
    "core": [True, True, True, True, False, False, False], "to_be_confirmed": [], "dropped_from_brief": [],
    "facts": ["Brew Lab"], "business_type": "cafe", "visitor_needs": ["Menu with prices", "Opening hours", "Where to find us"]}
BOUTIQUE_DRAFT = {   # J2 mock_charter(<Thread & Loom brief>), unchanged: no hours were given, so there are five items
    "statement": "A one-page website for Thread where visitors find what they need and come in", "site_name": "Thread",
    "audience": "Local customers, mostly on phones", "standards": ["Warm, modern feel", "Fast first screen on a phone"],
    "rules": ["Plain HTML/CSS/JS in one file", "No real customer data"],
    "done_when": ["Visitors can browse products by category", "Every product shows its id and price",
                  "Visitors can filter products by size and price",
                  "Every product has an order button that opens a WhatsApp link with the product id and price", "Layout works on a phone"],
    "core": [False, True, True, True, False], "to_be_confirmed": [], "dropped_from_brief": [], "facts": ["Thread"],
    "business_type": "boutique", "visitor_needs": ["Products shown by category", "Filter products by size and price", "Order on WhatsApp"]}
DOC_ITEMS = ["The Problem section states the problem QuickQueue solves", "The Users section says who the users are",
             "The Goals section lists the goals as G1, G2, ...", "The Requirements section lists every must-have feature as R1, R2, ...",
             "The Success metrics section gives a measurable metric for each goal", "The Out of scope section says what the product won't do"]
DOC_DRAFT = {    # J2 mock_prd_charter, unchanged: it already carries site_name, business_type and visitor_needs
    "statement": "A PRD for QuickQueue", "product_name": "QuickQueue", "site_name": "QuickQueue",
    "users": "patients at small clinics and the front-desk staff who manage the line",
    "audience": "patients at small clinics and the front-desk staff who manage the line",
    "user_groups": [{"name": "patients at small clinics", "actions": ["join the queue from a phone"]},
                    {"name": "front-desk staff who manage the line", "actions": []}],
    "problem": "patients wait 45 minutes on average in crowded waiting rooms", "features": [], "constraints": [],
    "success_measures": [], "facts": ["QuickQueue"], "standards": ["Every requirement testable"], "rules": ["No invented facts"],
    "done_when": DOC_ITEMS, "core": [True, False, False, True, True, False], "to_be_confirmed": [], "dropped_from_brief": [],
    "business_type": "prd", "visitor_needs": []}


def stored(draft: dict) -> dict:
    """What J2 does to a charter (J2:4109-4119): `core` is popped, charter_items and core_items are written."""
    out = {k: copy.deepcopy(v) for k, v in draft.items() if k != "core"}
    out["charter_items"] = list(draft["done_when"])
    out["core_items"] = [c for c, flag in zip(draft["done_when"], draft["core"]) if flag]
    return out


def problems(cls, data) -> list[tuple[str, str]]:
    with pytest.raises(ValidationError) as error:
        cls.model_validate(data)
    return [(".".join(str(p) for p in e["loc"]), e["type"]) for e in error.value.errors()]


def refused(family, data) -> list[tuple[str, str]]:
    with pytest.raises(GateError) as error:
        GATE.check(family, data)
    return [(v.path, v.code) for v in error.value.violations]


# ---- Question, TbcAnswer, ToBeConfirmed ---------------------------------------------------------------------------

def test_a_question_has_text_and_up_to_four_options():
    assert Question(question="What is the business called?").options == []
    assert len(Question(question="Which one?", options=["a", "b", "c", "d"]).options) == 4


@pytest.mark.parametrize("data, where, code", [
    ({"question": "Which?", "options": ["a", "b", "c", "d", "e"]}, "options", "too_long"),
    ({"question": ""}, "question", "string_too_short"),
    ({"question": "q" * 401}, "question", "string_too_long"),
    ({"question": "q", "options": ["o" * 301]}, "options.0", "string_too_long"),
    ({"question": "q", "options": [""]}, "options.0", "string_too_short"),
    ({"question": "q", "budget": [1]}, "budget", "extra_forbidden"),
])
def test_a_question_refuses(data, where, code):
    assert (where, code) in problems(Question, data)


def test_the_two_tbc_shapes_are_not_interchangeable():
    assert TbcAnswer(item=2, fact="the phone number").item == 2
    assert ToBeConfirmed(criterion=ITEMS[0], fact="prices").criterion == ITEMS[0]
    assert ("criterion", "missing") in problems(ToBeConfirmed, {"item": 1, "fact": "x"})
    assert ("item", "missing") in problems(TbcAnswer, {"criterion": ITEMS[0], "fact": "x"})
    assert ("item", "greater_than_equal") in problems(TbcAnswer, {"item": 0, "fact": "x"})
    assert ("item", "int_type") in problems(TbcAnswer, {"item": "1", "fact": "x"})


def test_a_user_group_and_a_dropped_reason():
    assert UserGroup(name="students").actions == []
    assert ("name", "string_too_short") in problems(UserGroup, {"name": ""})
    assert DroppedReason(criterion=ITEMS[1], reason="The Requester chose to leave it out").criterion == ITEMS[1]
    assert ("reason", "string_too_short") in problems(DroppedReason, {"criterion": ITEMS[1], "reason": ""})


# ---- the drafts ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("charter, name, items", [(SITE_DRAFT, "Brew Lab", 7), (BOUTIQUE_DRAFT, "Thread", 5)])
def test_j2s_mock_site_charter_is_a_site_draft(charter, name, items):
    draft = SiteGoalDraft.model_validate(charter)
    assert draft.kind == "site" and draft.site_name == name and len(draft.done_when) == items


def test_j2s_mock_prd_charter_is_a_doc_draft():
    draft = DocGoalDraft.model_validate(DOC_DRAFT)
    assert draft.kind == "doc" and draft.product_name == "QuickQueue" and draft.user_groups[1].actions == []


def test_core_is_empty_or_one_flag_per_item():
    assert SiteGoalDraft.model_validate({**SITE_DRAFT, "core": []}).core == []
    assert problems(SiteGoalDraft, {**SITE_DRAFT, "core": [True]}) == [("core", "value_error")]
    assert problems(SiteGoalDraft, {**SITE_DRAFT, "core": [True] * 8}) == [("core", "value_error")]


def test_done_when_needs_an_item_and_every_item_differs():
    assert ("done_when", "too_short") in problems(SiteGoalDraft, {**SITE_DRAFT, "done_when": [], "core": []})
    twice = {**SITE_DRAFT, "done_when": [ITEMS[0], ITEMS[1], ITEMS[0]], "core": []}
    assert problems(SiteGoalDraft, twice) == [("done_when.2", "value_error")]
    with pytest.raises(ValidationError, match="done_when item 3 repeats item 1"):
        SiteGoalDraft.model_validate(twice)


def test_at_most_forty_done_when_items():
    forty = [f"item {n}" for n in range(40)]
    assert len(SiteGoalDraft.model_validate({**SITE_DRAFT, "done_when": forty, "core": []}).done_when) == 40
    assert ("done_when", "too_long") in problems(SiteGoalDraft, {**SITE_DRAFT, "done_when": forty + ["one more"], "core": []})


def test_a_tbc_fact_names_an_item_that_exists():
    ok = {**SITE_DRAFT, "to_be_confirmed": [{"item": 7, "fact": "the real prices"}]}
    assert SiteGoalDraft.model_validate(ok).to_be_confirmed[0].item == 7
    assert problems(SiteGoalDraft, {**SITE_DRAFT, "to_be_confirmed": [{"item": 8, "fact": "x"}]}) == [("to_be_confirmed.0.item", "value_error")]


def test_every_problem_of_a_draft_is_reported_at_its_own_place():
    bad = {**SITE_DRAFT, "core": [True], "done_when": [ITEMS[0], ITEMS[0]], "to_be_confirmed": [{"item": 3, "fact": "x"}]}
    assert sorted(problems(SiteGoalDraft, bad)) == [("core", "value_error"), ("done_when.1", "value_error"),
                                                    ("to_be_confirmed.0.item", "value_error")]


@pytest.mark.parametrize("change, where, code", [
    ({"site_name": ""}, "site_name", "string_too_short"),
    ({"site_name": "s" * 121}, "site_name", "string_too_long"),
    ({"statement": ""}, "statement", "string_too_short"),
    ({"statement": "s" * 601}, "statement", "string_too_long"),
    ({"standards": ["s"] * 31}, "standards", "too_long"),
    ({"rules": [""]}, "rules.0", "string_too_short"),
    ({"facts": ["f" * 301]}, "facts.0", "string_too_long"),
    ({"core": [1] * 7}, "core.0", "bool_type"),
    ({"colour": "red"}, "colour", "extra_forbidden"),
    ({"kind": "doc"}, "kind", "literal_error"),
])
def test_a_site_draft_refuses(change, where, code):
    assert (where, code) in problems(SiteGoalDraft, {**SITE_DRAFT, **change})


def test_a_doc_draft_needs_a_product_name_and_refuses_what_is_not_a_document_key():
    assert ("product_name", "missing") in problems(DocGoalDraft, {k: v for k, v in DOC_DRAFT.items() if k != "product_name"})
    assert ("kind", "literal_error") in problems(DocGoalDraft, {**DOC_DRAFT, "kind": "site"})
    assert ("user_groups.0.name", "string_too_short") in problems(DocGoalDraft, {**DOC_DRAFT, "user_groups": [{"name": ""}]})
    assert ("chain", "extra_forbidden") in problems(DocGoalDraft, {**DOC_DRAFT, "chain": {}})        # code writes it, never a model


def test_a_draft_can_leave_every_optional_list_out():
    bare = SiteGoalDraft(statement="s", site_name="n", done_when=["one"])
    assert (bare.standards, bare.core, bare.to_be_confirmed, bare.facts, bare.audience, bare.business_type) == ([], [], [], [], "", "")


def test_goal_draft_is_the_shared_base():
    assert issubclass(SiteGoalDraft, GoalDraft) and issubclass(DocGoalDraft, GoalDraft)
    assert ("done_when", "missing") in problems(GoalDraft, {"statement": "s"})


def test_a_done_when_item_may_have_600_characters_where_j2_wrote_454():
    long = "x" * 454
    assert SiteGoalDraft.model_validate({**SITE_DRAFT, "done_when": [long], "core": []}).done_when == [long]
    assert SiteGoalDraft.model_validate({**SITE_DRAFT, "done_when": ["y" * 600], "core": []})
    assert ("done_when.0", "string_too_long") in problems(SiteGoalDraft, {**SITE_DRAFT, "done_when": ["y" * 601], "core": []})


# ---- what goes to a model -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("cls", [Question, SiteGoalDraft, DocGoalDraft])
def test_the_model_facing_classes_have_a_transport_safe_schema(cls):
    assert is_transport_safe(transport_schema(cls)) == []


def test_a_model_is_not_asked_for_the_three_keys_code_sets_on_a_document_charter():
    schema = transport_schema(DocGoalDraft)
    assert {"site_name", "business_type", "visitor_needs"}.isdisjoint(schema["required"])
    assert {"statement", "product_name", "done_when", "kind"} <= set(schema["required"])


# ---- the stored charter -------------------------------------------------------------------------------------------

def test_a_stored_site_charter_passes_the_gate_as_site_goal():
    checked = GATE.check("goal", {**stored(SITE_DRAFT), "kind": "site"})
    assert isinstance(checked.model, SiteGoal) and checked.kind == "site" and checked.family == "goal"
    assert checked.model.core == [] and checked.model.core_items == ITEMS[:4]


def test_a_stored_document_charter_passes_the_gate_as_doc_goal():
    checked = GATE.check("goal", {**stored(DOC_DRAFT), "kind": "doc"})
    assert isinstance(checked.model, DocGoal) and checked.model.business_type == "prd" and checked.model.chain == {}


def test_an_hld_charter_carries_the_chain_of_earlier_documents():
    hld = {**stored(DOC_DRAFT), "kind": "doc", "business_type": "hld", "statement": "An HLD for QuickQueue",
           "chain": {"prd": {"kind": "prd", "requirements": [{"id": "R1", "text": "Join from a phone"}]},
                     "prd_ids": ["R1"], "hld_ids": []}}
    model = GATE.check("goal", hld).model
    assert model.chain["prd_ids"] == ["R1"] and model.chain["prd"]["requirements"][0]["id"] == "R1"
    assert ("chain", "dict_type") in problems(DocGoal, {**hld, "chain": ["R1"]})


def test_a_charter_after_a_leave_out_and_a_confirmed_fact_passes():
    left = stored(SITE_DRAFT)
    gone = [ITEMS[1], ITEMS[4]]
    left.update(done_when=[c for c in ITEMS if c not in gone], dropped_by_requester=gone,
                dropped_reasons=[{"criterion": c, "reason": "The Requester chose to leave it out (limit): 2"} for c in gone],
                confirmed_facts=[{"criterion": ITEMS[0], "fact": "1. Espresso 120, latte 180"}],
                requester_answers=["It's called Brew Lab", "x" * 5000])
    model = GATE.check("goal", {**left, "kind": "site"}).model
    assert model.dropped_by_requester == gone and model.confirmed_facts[0].fact.startswith("1. Espresso")


def test_a_fact_to_be_confirmed_belongs_to_a_done_when_item():
    ok = {**stored(SITE_DRAFT), "to_be_confirmed": [{"criterion": ITEMS[0], "fact": "the real prices"}]}
    assert GATE.check("goal", {**ok, "kind": "site"}).model.to_be_confirmed[0].criterion == ITEMS[0]
    bad = {**ok, "to_be_confirmed": [{"criterion": "A different item", "fact": "x"}]}
    assert refused("goal", {**bad, "kind": "site"}) == [("site.to_be_confirmed.0.criterion", "value_error")]


def test_an_item_the_owner_dropped_may_stay_in_to_be_confirmed():
    """J2's override `drop` leaves to_be_confirmed alone (J2:3399), so the fact outlives its item."""
    data = stored(SITE_DRAFT)
    data.update(done_when=ITEMS[1:], dropped_by_requester=[ITEMS[0]], dropped_reasons=[{"criterion": ITEMS[0], "reason": "Owner override"}],
                to_be_confirmed=[{"criterion": ITEMS[0], "fact": "the real prices"}])
    assert GATE.check("goal", {**data, "kind": "site"}).model.to_be_confirmed[0].criterion == ITEMS[0]


def test_a_dropped_item_must_be_one_the_charter_once_had():
    data = {**stored(SITE_DRAFT), "dropped_by_requester": ["Never an item"]}
    assert refused("goal", {**data, "kind": "site"}) == [("site.dropped_by_requester.0", "value_error")]
    assert refused("goal", {**stored(SITE_DRAFT), "charter_items": [], "dropped_by_requester": [ITEMS[0]], "kind": "site"}) \
        == [("site.dropped_by_requester.0", "value_error")]


def test_the_stored_charter_keeps_texts_where_the_draft_has_numbers():
    draft_form = {**stored(SITE_DRAFT), "to_be_confirmed": [{"item": 1, "fact": "x"}]}
    assert ("to_be_confirmed.0.criterion", "missing") in problems(SiteGoal, {**draft_form, "kind": "site"})
    assert ("to_be_confirmed.0.item", "extra_forbidden") in problems(SiteGoal, {**draft_form, "kind": "site"})


def test_a_draft_is_a_stored_charter_without_the_code_written_keys():
    assert SiteGoal.model_validate({**SITE_DRAFT, "kind": "site"}).charter_items == []        # defaults, so a bare draft is also a goal
    assert issubclass(SiteGoal, SiteGoalDraft) and issubclass(DocGoal, DocGoalDraft)
    assert (SiteGoal.model_fields["kind"].default, DocGoal.model_fields["kind"].default) == ("site", "doc")


def test_the_stored_charter_is_closed_and_bounded():
    assert ("charter_ids", "extra_forbidden") in problems(SiteGoal, {**stored(SITE_DRAFT), "kind": "site", "charter_ids": []})
    assert ("open_inputs", "extra_forbidden") in problems(SiteGoal, {**stored(SITE_DRAFT), "kind": "site", "open_inputs": ["x"]})
    assert ("charter_items", "too_long") in problems(SiteGoal, {**stored(SITE_DRAFT), "kind": "site", "charter_items": ["i"] * 201})
    assert ("requester_answers.0", "string_too_long") in problems(SiteGoal, {**stored(SITE_DRAFT), "kind": "site", "requester_answers": ["a" * 20_001]})


def test_a_stored_charter_changes_only_through_evolve_which_checks_it_again():
    charter = SiteGoal.model_validate({**stored(SITE_DRAFT), "kind": "site"})
    assert charter.evolve(site_name="Brew Lab 2").site_name == "Brew Lab 2" and charter.site_name == "Brew Lab"
    with pytest.raises(ValidationError, match="repeats item 1"):
        charter.evolve(done_when=[ITEMS[0], ITEMS[0]])
    with pytest.raises(ValidationError, match="must belong to a done_when item"):
        charter.evolve(to_be_confirmed=[{"criterion": "A different item", "fact": "x"}])
    with pytest.raises(ValidationError):
        charter.statement = "changed"                                                          # frozen


def test_the_canonical_json_of_a_stored_charter_does_not_depend_on_key_order():
    data = {**stored(SITE_DRAFT), "kind": "site"}
    shuffled = dict(reversed(list(data.items())))
    assert GATE.check("goal", data).sha256 == GATE.check("goal", shuffled).sha256


def test_the_family_picks_the_class_by_kind():
    assert {k: c.__name__ for k, c in REGISTRY.kinds("goal").items()} == {"site": "SiteGoal", "doc": "DocGoal"}
    assert refused("goal", stored(SITE_DRAFT)) == [("", "union_tag_not_found")]                 # goal.json has no kind: the caller adds it
    assert refused("goal", {**stored(SITE_DRAFT), "kind": "page"}) == [("", "union_tag_invalid")]
    assert problems(SiteGoal, {**stored(SITE_DRAFT), "kind": "site", "schema_version": 2}) == [("", "value_error")]


def test_goal_kind_reads_a_charter_as_j2_writes_it():
    assert goal_kind(stored(SITE_DRAFT)) == "site"
    assert goal_kind(stored(DOC_DRAFT)) == "doc"
    assert goal_kind({}) == "site" and goal_kind(None) == "site"


def test_every_class_is_bounded_and_aliases_nothing():
    for cls in (Question, TbcAnswer, ToBeConfirmed, UserGroup, DroppedReason, GoalDraft, SiteGoalDraft, DocGoalDraft, SiteGoal, DocGoal):
        assert unbounded_fields(cls) == [], cls.__name__
        assert aliased_fields(cls) == [], cls.__name__


def test_the_module_lists_what_it_exports():
    assert all(hasattr(goal_module, name) for name in goal_module.__all__)
