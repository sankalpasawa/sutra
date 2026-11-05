"""Goal: the charter Identity writes and the questions it asks (library design section 5, S2-models-14).

    Question          one question to the Requester, with up to 4 options              (J2:4027)
    TbcAnswer         a fact the Requester cannot give yet, by done-when item NUMBER   (what Identity returns)
    ToBeConfirmed     the same fact as J2 stores it, by criterion TEXT                 (J2:4155 `_tbc`)
    GoalDraft         what Identity returns at J2.a (CHARTER_FMT / PRD_CHARTER_FMT)
      SiteGoalDraft   a website charter  (kind "site")
      DocGoalDraft    a document charter (kind "doc")
    SiteGoal, DocGoal the stored charter: the family "goal", the J2 file goal.json

The stored charter is the draft plus the keys code writes later (`charter_items`, `core_items`, `dropped_by_requester`,
`dropped_reasons`, `requester_answers`, `confirmed_facts`); the draft's `to_be_confirmed` (item numbers) becomes the
stored one (criterion texts). Bounds are design parameters. Where J2 wrote longer text than the design assumed, the bound
was raised (a done-when item of 454 characters was seen in 6 of 84 saved runs, so items may be 600).

J2's goal.json has no `kind` key: the caller of `Gate.check("goal", ...)` supplies it (`goal_kind` tells which).
"""
from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Final, Literal, NoReturn, Self

from pydantic import Field, StringConstraints, ValidationError, model_validator
from pydantic_core import InitErrorDetails

from .base import Record, Value
from .registry import record
from .types import JsonObject

__all__ = [
    "MAX_DONE_WHEN", "MAX_ITEM_CHARS", "Question", "TbcAnswer", "ToBeConfirmed", "UserGroup", "DroppedReason",
    "GoalDraft", "SiteGoalDraft", "DocGoalDraft", "SiteGoal", "DocGoal", "goal_kind",
]

MAX_DONE_WHEN: Final = 40          # done-when items in one charter
MAX_ITEM_CHARS: Final = 600        # one done-when item, and every copy of it (charter_items, to_be_confirmed, ...)

Problem = tuple[tuple[str | int, ...], str]       # (place inside the model, what is wrong)

Line = Annotated[str, StringConstraints(min_length=1, max_length=MAX_ITEM_CHARS)]       # a standard, a rule, a feature ...
Item = Annotated[str, StringConstraints(min_length=1, max_length=MAX_ITEM_CHARS)]       # one done-when item or a copy of it
Fact = Annotated[str, StringConstraints(min_length=1, max_length=300)]
Name = Annotated[str, StringConstraints(min_length=1, max_length=120)]
Label = Annotated[str, StringConstraints(max_length=120)]
Said = Annotated[str, StringConstraints(max_length=20_000)]           # the Requester's own words, kept whole
Count = Annotated[int, Field(ge=1)]


def _raise(title: str, problems: Sequence[Problem]) -> NoReturn:
    """Fail validation with one error for every problem, each at its own place (a model validator that raises a plain
    ValueError can report only one)."""
    raise ValidationError.from_exception_data(title, [
        InitErrorDetails(type="value_error", loc=loc, input=None, ctx={"error": ValueError(text)})
        for loc, text in problems])


# ---- the questions and the facts ----------------------------------------------------------------------------------

class Question(Value):
    """One question Identity puts to the Requester. J2 shows at most 3 options; the reply may carry 4 (J2:4027)."""

    question: Annotated[str, StringConstraints(min_length=1, max_length=400)]
    options: Annotated[list[Annotated[str, StringConstraints(min_length=1, max_length=300)]], Field(max_length=4)] = []


class TbcAnswer(Value):
    """A fact only the Requester can give and has said they cannot give yet, named by the NUMBER of the done-when item
    it blocks (what Identity returns; the number is a position in the charter)."""

    item: Count
    fact: Fact


class ToBeConfirmed(Value):
    """The stored form of the same fact, keyed by the criterion TEXT (numbers shift when items are dropped, J2:4155)."""

    criterion: Item
    fact: Fact


class UserGroup(Value):
    """A user group of a document charter, with what the group does (empty when the Requester did not say)."""

    name: Name
    actions: Annotated[list[Line], Field(max_length=20)] = []


class DroppedReason(Value):
    """Why a done-when item was left out: code writes it when the Requester (or the owner override) drops one."""

    criterion: Item
    reason: Annotated[str, StringConstraints(min_length=1, max_length=20_000)]


# ---- the draft: what Identity returns ------------------------------------------------------------------------------

class GoalDraft(Value):
    """The charter as Identity writes it (CHARTER_FMT, J2:3544). Every list may be left out; `statement` and at least
    one done-when item may not."""

    statement: Annotated[str, StringConstraints(min_length=1, max_length=600)]
    audience: Annotated[str, StringConstraints(max_length=600)] = ""
    standards: Annotated[list[Annotated[str, StringConstraints(min_length=1, max_length=300)]], Field(max_length=30)] = []
    rules: Annotated[list[Annotated[str, StringConstraints(min_length=1, max_length=300)]], Field(max_length=30)] = []
    done_when: Annotated[list[Item], Field(min_length=1, max_length=MAX_DONE_WHEN)]
    core: Annotated[list[bool], Field(max_length=MAX_DONE_WHEN)] = []            # one flag per done-when item, or none
    to_be_confirmed: Annotated[list[TbcAnswer], Field(max_length=MAX_DONE_WHEN)] = []
    dropped_from_brief: Annotated[list[Line], Field(max_length=MAX_DONE_WHEN)] = []
    facts: Annotated[list[Fact], Field(max_length=60)] = []

    @model_validator(mode="after")
    def _charter_rules(self) -> Self:
        problems: list[Problem] = []
        wanted = len(self.done_when)
        if self.core and len(self.core) != wanted:
            problems.append((("core",), f"core has {len(self.core)} flags for {wanted} done_when items: one per item, or none"))
        first: dict[str, int] = {}
        for index, text in enumerate(self.done_when):
            if text in first:
                problems.append((("done_when", index), f"done_when item {index + 1} repeats item {first[text] + 1}: items must differ"))
            first.setdefault(text, index)
        for index, fact in enumerate(self.to_be_confirmed):
            if isinstance(fact, TbcAnswer) and fact.item > wanted:        # the stored form (criterion texts) has no number
                problems.append((("to_be_confirmed", index, "item"), f"item {fact.item} is past the {wanted} done_when items"))
        if problems:
            _raise(type(self).__name__, problems)
        return self


class SiteGoalDraft(GoalDraft):
    """A website charter."""

    kind: Literal["site"] = "site"
    site_name: Name
    business_type: Label = ""
    visitor_needs: Annotated[list[Line], Field(max_length=MAX_DONE_WHEN)] = []


class DocGoalDraft(GoalDraft):
    """A document charter (PRD, HLD, LLD): PRD_CHARTER_FMT, J2:2258. J2 sets `site_name`, `business_type` and
    `visitor_needs` on the charter of every output (J2:4099, and its mock PRD charter already carries them), so a draft
    may hold them; the model is not asked for them."""

    TRANSPORT_OPTIONAL = frozenset({"site_name", "business_type", "visitor_needs"})

    kind: Literal["doc"] = "doc"
    product_name: Name
    users: Annotated[str, StringConstraints(max_length=600)] = ""
    problem: Annotated[str, StringConstraints(max_length=1000)] = ""
    features: Annotated[list[Line], Field(max_length=MAX_DONE_WHEN)] = []
    constraints: Annotated[list[Line], Field(max_length=MAX_DONE_WHEN)] = []
    success_measures: Annotated[list[Line], Field(max_length=MAX_DONE_WHEN)] = []
    user_groups: Annotated[list[UserGroup], Field(max_length=20)] = []
    site_name: Label = ""
    business_type: Label = ""
    visitor_needs: Annotated[list[Line], Field(max_length=MAX_DONE_WHEN)] = []


# ---- the stored charter: the draft plus what code writes later -----------------------------------------------------

class _StoredCharter(Value):
    """The fields and rules the stored charter adds to a draft (J2:3781-3783, 4114-4119, 4448, 4479). It stands beside
    the draft in the bases of SiteGoal and DocGoal, so both are still drafts with more in them."""

    to_be_confirmed: Annotated[list[ToBeConfirmed], Field(max_length=MAX_DONE_WHEN)] = []       # texts, not numbers
    charter_items: Annotated[list[Item], Field(max_length=200)] = []          # every item the charter ever had; the number of an item is its place here
    core_items: Annotated[list[Item], Field(max_length=200)] = []
    dropped_by_requester: Annotated[list[Item], Field(max_length=200)] = []
    dropped_reasons: Annotated[list[DroppedReason], Field(max_length=200)] = []
    requester_answers: Annotated[list[Said], Field(max_length=100)] = []
    confirmed_facts: Annotated[list[ToBeConfirmed], Field(max_length=200)] = []

    @model_validator(mode="after")
    def _stored_rules(self) -> Self:
        problems: list[Problem] = []
        open_items = set(getattr(self, "done_when", ())) | set(self.dropped_by_requester)
        for index, fact in enumerate(self.to_be_confirmed):
            # an item the owner dropped by override stays listed (J2:3399 leaves to_be_confirmed alone)
            if fact.criterion not in open_items:
                problems.append((("to_be_confirmed", index, "criterion"), "a fact to be confirmed must belong to a done_when item"))
        ever = set(self.charter_items)
        for index, text in enumerate(self.dropped_by_requester):
            if text not in ever:
                problems.append((("dropped_by_requester", index), "an item dropped by the Requester must be one the charter once had (charter_items)"))
        if problems:
            _raise(type(self).__name__, problems)
        return self


@record
class SiteGoal(Record, _StoredCharter, SiteGoalDraft):
    """The stored website charter: goal.json of a website run."""

    FAMILY = "goal"
    kind: Literal["site"] = "site"


@record
class DocGoal(Record, _StoredCharter, DocGoalDraft):
    """The stored document charter. Besides the draft it carries, for an HLD or LLD, `chain`: the earlier documents'
    agent_output and their ids (`stage_goal`, J2:2184)."""

    FAMILY = "goal"
    kind: Literal["doc"] = "doc"
    chain: JsonObject = Field(default_factory=dict)


def goal_kind(charter: Mapping[str, Any]) -> Literal["site", "doc"]:
    """The kind of a charter as J2 writes it (no `kind` key): a charter that names a product is a document's, any other a
    website's. `Gate.check("goal", {**charter, "kind": goal_kind(charter)})` is how goal.json is checked."""
    return "doc" if isinstance(charter, Mapping) and "product_name" in charter else "site"
