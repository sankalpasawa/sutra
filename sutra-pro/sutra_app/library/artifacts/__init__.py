"""The artifact models, their rules as data and their renderers (library design section 9.3).

    models   the 19 section models and the PRD, HLD and LLD document models (port of J2's j2_artifact_models)
    rules    `RuleSpec`, the 12 rule functions, `RULES` as data, `run_rules` / `run_specs` (port of j2_rules)
    render   `render_section`, `style_from_design`, `normalise`, `errors_of`, `validate`

This module holds the registry of sections (`SECTION_MODELS`, `DOC_MODELS`, `SECTION_CONDITIONS`, `model_for`) and registers
every model as a payload `artifact.<kind>.<section-slug>` (19) and `artifact.<kind>` for the documents prd, hld, lld (3),
with each section's rules attached (`REGISTRY.rules(name)`). The design and website documents are their section models.
"""
import re
from typing import Optional

from ..registry import REGISTRY
from . import models, render, rules
from .models import (
    HLD, LLD, OPTIONAL_FIELDS, PRD, VERSION, Design, HLDComponents, HLDDataFlow, HLDHosting, HLDPages, HLDPurpose,
    HLDRisks, LLDElements, LLDFiles, LLDFormFields, LLDRules, LLDSections, PRDGoals, PRDOutOfScope, PRDProblem,
    PRDRequirements, PRDSuccessMetrics, PRDUsers, WebsiteSection,
)
from .render import errors_of, normalise, render_section, style_from_design, validate
from .rules import RULE_NAMES, RULES, RuleSpec, failures, rule_names, rules_count, rules_for, run_rules, run_specs

__all__ = [
    "models", "render", "rules", "VERSION", "OPTIONAL_FIELDS", "SECTION_MODELS", "DOC_MODELS", "SECTION_CONDITIONS",
    "model_for", "slug", "payload_name", "RuleSpec", "RULES", "RULE_NAMES", "rules_for", "rule_names", "rules_count",
    "run_rules", "run_specs", "failures", "render_section", "style_from_design", "normalise", "errors_of", "validate",
]

# One model per section a workflow writes, so a builder's schema is only its own part. The names are the section names of
# PRD_SECTIONS / HLD_SECTIONS / LLD_SECTIONS in the engine; the parity test fails if they ever disagree.
SECTION_MODELS = {
    "prd": {"Problem": PRDProblem, "Users": PRDUsers, "Goals": PRDGoals, "Requirements": PRDRequirements,
            "Success metrics": PRDSuccessMetrics, "Out of scope": PRDOutOfScope},
    "hld": {"Purpose and scope": HLDPurpose, "Pages": HLDPages, "Components": HLDComponents,
            "Data flow": HLDDataFlow, "Hosting and deployment": HLDHosting, "Risks": HLDRisks},
    "lld": {"Pages and sections": LLDSections, "Interactive elements": LLDElements, "Form fields": LLDFormFields,
            "File structure": LLDFiles, "Responsive and accessibility rules": LLDRules},
    "design": {"Style guide": Design},
    "website": {"Section": WebsiteSection},
}
DOC_MODELS = {"prd": PRD, "hld": HLD, "lld": LLD, "design": Design, "website": WebsiteSection}
# Which condition each section's rules come from, for the records (the conditions themselves stay in conditions/).
SECTION_CONDITIONS = {
    "prd": {"Problem": ["P1"], "Users": ["P1", "P7"], "Goals": ["P1", "P6"], "Requirements": ["P1", "P2"],
            "Success metrics": ["P1", "P6", "P8"], "Out of scope": ["P1"]},
    "hld": {"Purpose and scope": ["H1"], "Pages": ["H1"], "Components": ["H1", "H3", "H4"], "Data flow": ["H1"],
            "Hosting and deployment": ["H1"], "Risks": ["H1"]},
    "lld": {"Pages and sections": ["L1", "L2", "L5"], "Interactive elements": ["L1", "L2", "L3"],
            "Form fields": ["L1", "L2", "L4"], "File structure": ["L1"],
            "Responsive and accessibility rules": ["L1"]},
    "design": {"Style guide": []},
    "website": {"Section": ["N1", "N4", "N8"]},
}


def slug(text) -> str:
    """J2's `slug` (j2_template_lib): lowercase, runs of anything else become one "-", "template" for nothing."""
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-") or "template"


def payload_name(kind: str, section: Optional[str] = None) -> str:
    """The registry name of a section payload ("artifact.prd.problem") or, without `section`, of a document ("artifact.prd")."""
    return f"artifact.{kind}" if section is None else f"artifact.{kind}.{slug(section)}"


def model_for(kind, section):
    """The model one workflow writes, by output kind and section name (None when there is none)."""
    by = SECTION_MODELS.get(str(kind or ""), {})
    if section in by:
        return by[section]
    want = re.sub(r"[^a-z0-9]+", " ", str(section or "").lower()).strip()
    for name, m in by.items():
        if re.sub(r"[^a-z0-9]+", " ", name.lower()).strip() == want:
            return m
    return next(iter(by.values())) if kind in ("design", "website") else None


def _register() -> None:
    for kind, sections in SECTION_MODELS.items():              # prd 6, hld 6, lld 5, design 1, website 1 = 19
        for section, cls in sections.items():
            REGISTRY.register_payload(payload_name(kind, section), VERSION, cls, rules=RULES.get((kind, section), ()))
    for kind in ("prd", "hld", "lld"):                         # the three documents; design and website are their sections
        REGISTRY.register_payload(payload_name(kind), VERSION, DOC_MODELS[kind])


_register()
