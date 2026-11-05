"""artifact-schema/1: the SHAPE of every artifact the engine generates, as closed pydantic models (library design 9.3).

Port of J2's `j2_artifact_models.py` (baseline 33aeeda). The models say what fields an artifact's data has, their types,
which are required and which enums they allow, and nothing else. Every constraint (ids in order, references that point at
an id that exists, hex colours, plain CSS, page tags, anchors) is a rule in `rules.py`, written as data and run as its own
layer. The one presence rule that stays here is a website section's "html or head": which fields must be there is shape.

One model per thing a workflow writes, so each builder's schema stays small: a PRD section, an HLD section, an LLD
section, the design style guide, one website section. The document models (PRD, HLD, LLD) are the same fields assembled,
used for the cross-document rules and for rendering.

What differs from J2, and nothing else:
  * `Artifact` derives from `Value` (strict, frozen, closed): `required: "true"` is refused, nothing is coerced.
  * Every string and list has a bound (design rule 3). The bounds are generous, and the transport schema strips them, so
    every transport schema stays byte for byte J2's.
  * `Artifact.TRANSPORT_OPTIONAL` is J2's `OPTIONAL_FIELDS`, set once on the base class; every nested class inherits it.
  * The registry (`SECTION_MODELS`, `model_for`, registration) lives in `__init__.py`, the transport schema in
    `registry.py`, the renderers in `render.py`.

Class docstrings are left out of the models on purpose: pydantic copies a class docstring into the JSON Schema, and the
schema (and its sha) must stay J2's. Notes go in comments.
"""
from typing import Annotated, ClassVar, Literal, Optional, Self

from pydantic import Field, model_validator

from ..base import Value
from .rules import FIELD_TYPES as _FIELD_TYPES
from .rules import PRIORITIES as _PRIORITIES

__all__ = [
    "VERSION", "OPTIONAL_FIELDS", "FIELD_TYPES", "PRIORITIES", "Artifact", "UserGroup", "Goal", "Requirement",
    "SuccessMetric", "PRDProblem", "PRDUsers", "PRDGoals", "PRDRequirements", "PRDSuccessMetrics", "PRDOutOfScope",
    "PRD", "Page", "Component", "DataFlow", "Hosting", "Risk", "HLDPurpose", "HLDPages", "HLDComponents", "HLDDataFlow",
    "HLDHosting", "HLDRisks", "HLD", "LLDSection", "Element", "FormField", "FileEntry", "LLDSections", "LLDElements",
    "LLDFormFields", "LLDFiles", "LLDRules", "LLD", "Palette", "Fonts", "Spacing", "Buttons", "Design",
    "WebsiteSection",
]

VERSION = 1
# Field names that may be missing from a reply because the brief may not say anything about them. Everything else is
# required in the transport schema.
OPTIONAL_FIELDS = frozenset({
    "assumptions", "google_fonts_url", "notes", "window", "target", "validation", "page", "head", "anchor", "html",
    "selectors_used", "facts_used", "implements", "covers", "goals", "actions", "needs", "responsive_rules",
    "accessibility_rules", "out_of_scope", "risks", "data_flows", "files"})
# The enums are shape: the model allows these values and no others, and the transport schema carries them.
FIELD_TYPES = tuple(_FIELD_TYPES)
PRIORITIES = tuple(_PRIORITIES)

# ---- bounds (generous: a real artifact is far below them; the transport schema never shows them)
Id = Annotated[str, Field(max_length=40)]
Name = Annotated[str, Field(max_length=300)]
Text = Annotated[str, Field(max_length=4000)]
Css = Annotated[str, Field(max_length=2000)]
Url = Annotated[str, Field(max_length=500)]
Markup = Annotated[str, Field(max_length=200_000)]
Ids = Annotated[list[Id], Field(max_length=200)]
Lines = Annotated[list[Text], Field(max_length=200)]
Names = Annotated[list[Name], Field(max_length=500)]
Items = 300           # most objects in one list


class Artifact(Value):
    # Strict (no extra keys, no coercion), frozen; carries the template name the records show.
    TEMPLATE: ClassVar[str] = "artifact/1"
    SECTION: ClassVar[str] = ""
    TRANSPORT_OPTIONAL: ClassVar[frozenset[str]] = OPTIONAL_FIELDS

    @classmethod
    def template(cls) -> str:
        return cls.TEMPLATE + (f" · {cls.SECTION}" if cls.SECTION else "")


# ---------------------------------------------------------------- PRD/1
class UserGroup(Artifact):
    group: Name = Field(description="the name of this user group, as the charter names it")
    needs: Text = Field(default="", description="what this group needs from the product")
    actions: Lines = Field(default_factory=list, description="what this group does on the page; empty when this "
                                                             "group has no actions in this version")


class Goal(Artifact):
    id: Id = Field(description="G1, G2, ... in order")
    statement: Text = Field(description="the goal in one line")


class Requirement(Artifact):
    id: Id = Field(description="R1, R2, ... in order")
    statement: Text = Field(description="what the product must do, naming the user group that does it")
    priority: Literal["must", "should", "could"] = Field(description="must, should or could")
    goals: Ids = Field(default_factory=list, description="the goal ids this requirement serves, e.g. [\"G1\"]")


class SuccessMetric(Artifact):
    goal: Id = Field(description="the goal id this metric measures, e.g. \"G1\"")
    metric: Text = Field(description="what is measured")
    target: Text = Field(default="", description="the number or state to reach")
    window: Text = Field(default="", description="the measurement window, e.g. \"in the first 30 days\"; write "
                                                 "\"measurement window not set\" when the brief doesn't say")


class PRDProblem(Artifact):
    TEMPLATE: ClassVar[str] = "PRD/1"
    SECTION: ClassVar[str] = "Problem"
    statement: Text = Field(description="the problem the product solves, in the charter's own words")
    assumptions: Lines = Field(default_factory=list, description="facts you had to assume, each one line")


class PRDUsers(Artifact):
    TEMPLATE: ClassVar[str] = "PRD/1"
    SECTION: ClassVar[str] = "Users"
    users: Annotated[list[UserGroup], Field(max_length=Items)] = Field(description="every user group the charter names")
    assumptions: Lines = Field(default_factory=list)


class PRDGoals(Artifact):
    TEMPLATE: ClassVar[str] = "PRD/1"
    SECTION: ClassVar[str] = "Goals"
    goals: Annotated[list[Goal], Field(max_length=Items)] = Field(description="the goals, G1, G2, ... in order")
    assumptions: Lines = Field(default_factory=list)


class PRDRequirements(Artifact):
    TEMPLATE: ClassVar[str] = "PRD/1"
    SECTION: ClassVar[str] = "Requirements"
    requirements: Annotated[list[Requirement], Field(max_length=Items)] = Field(
        description="the requirements, R1, R2, ... in order")
    assumptions: Lines = Field(default_factory=list)


class PRDSuccessMetrics(Artifact):
    TEMPLATE: ClassVar[str] = "PRD/1"
    SECTION: ClassVar[str] = "Success metrics"
    success_metrics: Annotated[list[SuccessMetric], Field(max_length=Items)] = Field(description="one metric per goal")
    assumptions: Lines = Field(default_factory=list)


class PRDOutOfScope(Artifact):
    TEMPLATE: ClassVar[str] = "PRD/1"
    SECTION: ClassVar[str] = "Out of scope"
    out_of_scope: Lines = Field(description="what the product will not do, one line each")
    assumptions: Lines = Field(default_factory=list)


class PRD(Artifact):
    TEMPLATE: ClassVar[str] = "PRD/1"
    problem: PRDProblem
    users: Annotated[list[UserGroup], Field(max_length=Items)] = Field(default_factory=list)
    goals: Annotated[list[Goal], Field(max_length=Items)] = Field(default_factory=list)
    requirements: Annotated[list[Requirement], Field(max_length=Items)] = Field(default_factory=list)
    success_metrics: Annotated[list[SuccessMetric], Field(max_length=Items)] = Field(default_factory=list)
    out_of_scope: Lines = Field(default_factory=list)
    assumptions: Lines = Field(default_factory=list)


# ---------------------------------------------------------------- HLD/1
class Page(Artifact):
    id: Id = Field(description="P1, P2, ... in order")
    name: Name = Field(description="the page name")
    purpose: Text = Field(description="what the page is for")
    implements: Ids = Field(default_factory=list, description="the PRD requirement ids this page carries")


class Component(Artifact):
    id: Id = Field(description="C1, C2, ... in order")
    name: Name = Field(description="the component name")
    responsibility: Text = Field(description="its one responsibility, in one line")
    covers: Ids = Field(default_factory=list, description="the PRD requirement ids it covers, e.g. [\"R1\"]")
    page: Id = Field(default="", description="the page id it sits on, e.g. \"P1\"")


class DataFlow(Artifact):
    from_: Name = Field(alias="from", description="where the data comes from")
    to: Name = Field(description="where it goes")
    data: Text = Field(description="what is sent")
    trigger: Text = Field(description="what starts it")


class Hosting(Artifact):
    kind: Text = Field(description="how it is hosted, e.g. \"one static file on a static host\"")
    notes: Text = Field(default="", description="how it is deployed and replaced")


class Risk(Artifact):
    risk: Text = Field(description="the risk, one line")
    mitigation: Text = Field(description="what is done about it")


class HLDPurpose(Artifact):
    TEMPLATE: ClassVar[str] = "HLD/1"
    SECTION: ClassVar[str] = "Purpose and scope"
    purpose: Text = Field(description="what this design covers and what it leaves out")
    assumptions: Lines = Field(default_factory=list)


class HLDPages(Artifact):
    TEMPLATE: ClassVar[str] = "HLD/1"
    SECTION: ClassVar[str] = "Pages"
    pages: Annotated[list[Page], Field(max_length=Items)] = Field(description="the pages, P1, P2, ... in order")
    assumptions: Lines = Field(default_factory=list)


class HLDComponents(Artifact):
    TEMPLATE: ClassVar[str] = "HLD/1"
    SECTION: ClassVar[str] = "Components"
    components: Annotated[list[Component], Field(max_length=Items)] = Field(
        description="the components, C1, C2, ... in order; each names the PRD requirement ids it covers")
    assumptions: Lines = Field(default_factory=list)


class HLDDataFlow(Artifact):
    TEMPLATE: ClassVar[str] = "HLD/1"
    SECTION: ClassVar[str] = "Data flow"
    data_flows: Annotated[list[DataFlow], Field(max_length=Items)] = Field(
        description="every flow the pages need, including each form")
    assumptions: Lines = Field(default_factory=list)


class HLDHosting(Artifact):
    TEMPLATE: ClassVar[str] = "HLD/1"
    SECTION: ClassVar[str] = "Hosting and deployment"
    hosting: Hosting
    assumptions: Lines = Field(default_factory=list)


class HLDRisks(Artifact):
    TEMPLATE: ClassVar[str] = "HLD/1"
    SECTION: ClassVar[str] = "Risks"
    risks: Annotated[list[Risk], Field(max_length=Items)] = Field(description="each risk with its mitigation")
    assumptions: Lines = Field(default_factory=list)


class HLD(Artifact):
    TEMPLATE: ClassVar[str] = "HLD/1"
    purpose: Text = ""
    pages: Annotated[list[Page], Field(max_length=Items)] = Field(default_factory=list)
    components: Annotated[list[Component], Field(max_length=Items)] = Field(default_factory=list)
    data_flows: Annotated[list[DataFlow], Field(max_length=Items)] = Field(default_factory=list)
    hosting: Optional[Hosting] = None
    risks: Annotated[list[Risk], Field(max_length=Items)] = Field(default_factory=list)
    assumptions: Lines = Field(default_factory=list)


# ---------------------------------------------------------------- LLD/1
class LLDSection(Artifact):
    id: Id = Field(description="S1, S2, ... in order")
    anchor: Id = Field(description="the id attribute on the page, with the #, e.g. \"#classes\"")
    page: Id = Field(default="", description="the page id, e.g. \"P1\"")
    implements: Ids = Field(default_factory=list, description="the HLD component ids this section implements")


class Element(Artifact):
    id: Id = Field(description="E1, E2, ... in order")
    section: Id = Field(description="the section id it sits in, e.g. \"S1\"")
    selector: Name = Field(description="its selector, e.g. \"#book-now\"")
    trigger: Name = Field(description="what the visitor does, e.g. \"click\"")
    behaviour: Text = Field(description="what happens then")


class FormField(Artifact):
    id: Id = Field(description="F1, F2, ... in order")
    form: Name = Field(description="the form's selector, e.g. \"#booking\"")
    name: Name = Field(description="the field name attribute")
    type: Literal["text", "email", "tel", "url", "number", "date", "time", "select", "textarea", "checkbox",
                  "radio", "password", "file"] = Field(description="one of " + ", ".join(FIELD_TYPES))
    required: bool = Field(description="true when the visitor must fill it in")
    section: Id = Field(default="", description="the section id the form sits in, e.g. \"S1\"")
    validation: Text = Field(default="", description="the validation rule in one line")


class FileEntry(Artifact):
    path: Name = Field(description="the file path, e.g. \"index.html\"")
    purpose: Text = Field(description="what it holds")


class LLDSections(Artifact):
    TEMPLATE: ClassVar[str] = "LLD/1"
    SECTION: ClassVar[str] = "Pages and sections"
    sections: Annotated[list[LLDSection], Field(max_length=Items)] = Field(
        description="the page sections, S1, S2, ... in order, each with its anchor and the HLD components it implements")
    assumptions: Lines = Field(default_factory=list)


class LLDElements(Artifact):
    TEMPLATE: ClassVar[str] = "LLD/1"
    SECTION: ClassVar[str] = "Interactive elements"
    elements: Annotated[list[Element], Field(max_length=Items)] = Field(
        description="every interactive element, E1, E2, ... in order")
    assumptions: Lines = Field(default_factory=list)


class LLDFormFields(Artifact):
    TEMPLATE: ClassVar[str] = "LLD/1"
    SECTION: ClassVar[str] = "Form fields"
    form_fields: Annotated[list[FormField], Field(max_length=Items)] = Field(
        description="every form field, F1, F2, ... in order")
    assumptions: Lines = Field(default_factory=list)


class LLDFiles(Artifact):
    TEMPLATE: ClassVar[str] = "LLD/1"
    SECTION: ClassVar[str] = "File structure"
    files: Annotated[list[FileEntry], Field(max_length=1000)] = Field(description="every file of the build")
    assumptions: Lines = Field(default_factory=list)


class LLDRules(Artifact):
    TEMPLATE: ClassVar[str] = "LLD/1"
    SECTION: ClassVar[str] = "Responsive and accessibility rules"
    responsive_rules: Lines = Field(default_factory=list, description="one rule per line")
    accessibility_rules: Lines = Field(default_factory=list, description="one rule per line")
    assumptions: Lines = Field(default_factory=list)


class LLD(Artifact):
    TEMPLATE: ClassVar[str] = "LLD/1"
    sections: Annotated[list[LLDSection], Field(max_length=Items)] = Field(default_factory=list)
    elements: Annotated[list[Element], Field(max_length=Items)] = Field(default_factory=list)
    form_fields: Annotated[list[FormField], Field(max_length=Items)] = Field(default_factory=list)
    files: Annotated[list[FileEntry], Field(max_length=1000)] = Field(default_factory=list)
    responsive_rules: Lines = Field(default_factory=list)
    accessibility_rules: Lines = Field(default_factory=list)
    assumptions: Lines = Field(default_factory=list)


# ---------------------------------------------------------------- Design/1 (the style guide, STYLE_FMT as a model)
class Palette(Artifact):
    primary: Css
    secondary: Css
    accent: Css
    background: Css
    surface: Css
    text: Css
    muted: Css


class Fonts(Artifact):
    heading: Css = Field(description="a css font-family")
    body: Css = Field(description="a css font-family")
    google_fonts_url: Optional[Url] = Field(default=None, description="a https://fonts.googleapis.com/ url, or null")


class Spacing(Artifact):
    unit: Css = Field(description="the base spacing, e.g. \"8px\"")
    section: Css = Field(description="the space between sections, e.g. \"64px\"")


class Buttons(Artifact):
    primary: Css = Field(description="css declarations for the primary button")
    secondary: Css = Field(description="css declarations for the secondary button")


class Design(Artifact):
    TEMPLATE: ClassVar[str] = "Design/1"
    SECTION: ClassVar[str] = "Style guide"
    palette: Palette
    fonts: Fonts
    spacing: Spacing
    radius: Css = Field(description="the corner radius, e.g. \"12px\"")
    buttons: Buttons
    card: Css = Field(description="css declarations for a card")
    notes: Text = Field(default="", description="one line: why this suits the business")


# ---------------------------------------------------------------- WebsiteSection/1
class WebsiteSection(Artifact):
    TEMPLATE: ClassVar[str] = "WebsiteSection/1"
    SECTION: ClassVar[str] = "Section"
    id: Id = Field(description="the section id of this workflow, as the task gives it")
    anchor: Id = Field(default="", description="the id attribute of the section element, with the #; \"\" when this "
                                                "workflow writes page-head tags only")
    implements: Ids = Field(default_factory=list, description="the LLD section ids this builds; empty when the run "
                                                              "has no LLD")
    html: Markup = Field(default="", description="the section's HTML only: no <html>, <head> or <body> tags; \"\" when "
                                                 "this workflow writes page-head tags only")
    head: Markup = Field(default="", description="page-head tags this section needs (meta, link, style or script "
                                                 "only); \"\" when it needs none")
    selectors_used: Names = Field(default_factory=list, description="the ids and classes you used")
    facts_used: Lines = Field(default_factory=list, description="the charter facts this section shows, copied exactly")

    @model_validator(mode="after")
    def _something(self) -> Self:
        # Shape, not a constraint: a section must carry one of the two fields. Everything else about the markup and the
        # anchor is a rule in rules.py (html_no_page_tags, anchor_selector, anchor_in_html).
        if not str(self.html).strip() and not str(self.head).strip():
            raise ValueError("a section must have html, or head tags when it writes only those")
        return self
