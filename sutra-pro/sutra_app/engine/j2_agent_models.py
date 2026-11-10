"""agent-views/1: the agent-readable form of every artifact a J2 run keeps, as Pydantic 2 models.

A human reads the rendered artifact (a guide's markdown, the PRD, the page, the audit chart). An agent reads a JSON
beside it, in one fixed shape per artifact kind, and always finds it in the same place (j2_artifacts.agent_view).
Every JSON carries, at the top, "schema" (this file's SCHEMA), "model" (the class below) and "valid": the real
result of validating the data against that class, never assumed. What a saved run did not record is written as
NOT_RECORDED, so an agent can tell "missing" from "empty".

Nothing here assumes a website: a run may deliver documents, guides, a page or any office deliverable. The models
for the PRD, HLD, LLD, the style guide and a website section stay in j2_artifact_models.py (artifact-schema/1);
this file adds the kinds that had no structured form: the guides a planning workflow writes, the run's own records
(charter, workflow plan, check receipts, necessary conditions) and the audits, treated as workflows.

Python 3.9: Optional/List/Dict, never "X | None".
"""
import re
from typing import Any, ClassVar, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA = "agent-views/1"
VERSION = 1
NOT_RECORDED = "not recorded"


class AgentModel(BaseModel):
    """Closed shapes: a key the model does not know is an error, so a JSON that drifts from its model reads invalid."""
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------------------------------- guides
class GuideSection(AgentModel):
    """One heading of a guide with the prose and the bullet points under it."""
    heading: str
    level: int = Field(ge=1, le=6, description="the markdown heading level")
    text: str = Field(default="", description="the paragraphs under the heading, joined with blank lines")
    points: List[str] = Field(default_factory=list, description="the bullet points under the heading, in order")


class Guide(AgentModel):
    """A guide the makers read (artifacts/*.md): its title, purpose, audience and sections. General enough for any
    deliverable; the subclasses only fix the kind."""
    KIND: ClassVar[str] = "guide"
    kind: str
    title: str
    purpose: str = Field(default=NOT_RECORDED, description="the first paragraph before any heading, else not recorded")
    audience: str = Field(default=NOT_RECORDED, description="who the guide is for, when the text says so")
    sections: List[GuideSection] = Field(default_factory=list)
    facts_used: List[str] = Field(default_factory=list, description="the charter facts the text repeats verbatim")
    source_file: str = Field(description="the markdown file this was read from, relative to the run")
    written_by: str = Field(default=NOT_RECORDED, description="the workflow id that wrote the file")
    words: int = Field(default=0, ge=0)


class ProductPlan(Guide):
    kind: Literal["product plan"] = "product plan"


class Architecture(Guide):
    kind: Literal["architecture"] = "architecture"


class DesignGuide(Guide):
    kind: Literal["design guide"] = "design guide"


class Copy(Guide):
    kind: Literal["copy"] = "copy"


class StreakRules(Guide):
    kind: Literal["streak rules"] = "streak rules"


class GenericGuide(Guide):
    kind: Literal["guide"] = "guide"


GUIDE_MODELS = {"product plan": ProductPlan, "architecture": Architecture, "design guide": DesignGuide, "copy": Copy,
                "streak rules": StreakRules, "guide": GenericGuide}
_GUIDE_WORDS = (("plan", ProductPlan), ("roadmap", ProductPlan), ("architect", Architecture), ("design", DesignGuide),
                ("style", DesignGuide), ("brand", DesignGuide), ("copy", Copy), ("content", Copy), ("tone", Copy),
                ("streak", StreakRules), ("rules", StreakRules))


def guide_model_for(filename):
    """The guide class a file name points at (artifacts/product_plan.md -> ProductPlan), else GenericGuide."""
    stem = re.sub(r"[^a-z]+", " ", str(filename or "").rsplit("/", 1)[-1].rsplit(".", 1)[0].lower())
    for word, cls in _GUIDE_WORDS:
        if word in stem:
            return cls
    return GenericGuide


# ---------------------------------------------------------------------------------------------------- run records
class Charter(AgentModel):
    """goal.json as the agent reads it: what was asked, for whom, the standards and rules, and the done-when list."""
    statement: str
    site_name: Optional[str] = None
    audience: str = NOT_RECORDED
    business_type: str = NOT_RECORDED
    standards: List[str] = Field(default_factory=list)
    rules: List[str] = Field(default_factory=list)
    done_when: List[str] = Field(default_factory=list)
    core_items: List[str] = Field(default_factory=list)
    to_be_confirmed: List[Any] = Field(default_factory=list)
    dropped_from_brief: List[Any] = Field(default_factory=list)
    facts: List[str] = Field(default_factory=list)
    visitor_needs: List[Any] = Field(default_factory=list)


class Workflow(AgentModel):
    id: str
    name: str
    purpose: str = ""
    covers: List[Union[int, str]] = Field(default_factory=list)
    fixes: List[Union[int, str]] = Field(default_factory=list)
    outputs: List[str] = Field(default_factory=list)
    section: Optional[str] = None
    cycle: Optional[int] = None
    cost: Optional[float] = None
    charged: Optional[bool] = None
    calls_used: Optional[int] = None
    retries_used: Optional[int] = None
    dependencies: List[str] = Field(default_factory=list)
    completion_check: Optional[str] = None
    proposal_id: Optional[str] = None


class WorkflowPlan(AgentModel):
    workflows: List[Workflow]


class Receipt(AgentModel):
    """One check a workflow's atom ran (receipts.jsonl): what was checked, by what, and whether it passed."""
    atom: str = NOT_RECORDED
    check: str = NOT_RECORDED
    attempt: Optional[int] = None
    passed: Optional[bool] = None
    met: Optional[bool] = None
    by: Optional[str] = None
    kind: Optional[str] = None
    evidence: str = ""
    expect: Optional[Any] = None
    actual: Optional[Any] = None
    of: Optional[str] = None
    target: Optional[Any] = None
    t: Optional[str] = None


class Receipts(AgentModel):
    items: List[Receipt]


class Condition(AgentModel):
    id: str
    text: str
    check: Optional[str] = None
    met: bool
    evidence: str = ""


class Conditions(AgentModel):
    items: List[Condition]


# ---------------------------------------------------------------------------------------------------- audits
class AuditFinding(AgentModel):
    """One item the audit judged: the criterion, the verdict, how sure, how bad, and what it looked at."""
    id: Optional[str] = None
    item: Optional[Union[int, str]] = None
    criterion: str
    verdict: str
    note: str = ""
    severity: str = NOT_RECORDED
    confidence: Optional[Union[str, float]] = None
    passed: bool
    evidence: str = ""


class Evidence(AgentModel):
    kind: str = Field(description="screenshot | mechanical | conditions | lld | page | rubric")
    ref: str
    note: str = ""


class AuditResult(AgentModel):
    """One audit as a workflow of its own (audits.json entry): A-1, A-2, ... in time order, with the goal, the method
    and the evidence it used, and every finding."""
    id: str
    cycle: int
    version: int
    goal: str = NOT_RECORDED
    method: str = NOT_RECORDED
    findings: List[AuditFinding] = Field(default_factory=list)
    rubric: List[AuditFinding] = Field(default_factory=list)
    extra_issues: List[AuditFinding] = Field(default_factory=list)
    all_pass: Optional[bool] = None
    screenshot: Optional[str] = None
    mechanical: Dict[str, Any] = Field(default_factory=dict)
    conditions: List[Condition] = Field(default_factory=list)
    lld: Dict[str, Any] = Field(default_factory=dict)
    evidence: List[Evidence] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _audit_id(cls, v):
        if not re.fullmatch(r"A-\d+", v):
            raise ValueError("an audit id is A-<n>")
        return v


MODELS = {c.__name__: c for c in (ProductPlan, Architecture, DesignGuide, Copy, StreakRules, GenericGuide, Charter,
                                  WorkflowPlan, Receipts, Conditions, AuditResult)}


# ---------------------------------------------------------------------------------------------------- the envelope
def errors_of(e):
    try:
        return [f"{'.'.join(str(x) for x in err.get('loc', ()))}: {err.get('msg')}" for err in e.errors()]
    except Exception:      # noqa: BLE001 -- a non-Pydantic error reads the same to the agent
        return [str(e)]


def validate(model, data):
    """(object or None, [error lines]): the real result, Pydantic's own words."""
    try:
        return model.model_validate(data), []
    except Exception as e:      # noqa: BLE001
        return None, errors_of(e)


def envelope(model, data, source):
    """The JSON an agent reads: schema, model, the REAL validity, the errors when invalid, where the data came from, the data."""
    obj, errs = validate(model, data)
    return {"schema": SCHEMA, "model": model.__name__, "valid": obj is not None, "errors": errs,
            "source": source, "data": obj.model_dump() if obj is not None else data}
