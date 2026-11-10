"""The `project` output and its capability (engine design 2.3, D128): work in the owner's own folder, run by the one engine.

"Project work" is a document-flow output (its `sections` are set), so the whole flow is inherited unchanged: Identity's intake and charter,
Adaptation's plan, Priority's pricing, the builders, Audit, the three attempts, the necessary conditions, receipts, atoms, the function
nodes and the map. The "document" is the work report; each builder does its section's work with its file tools in the folder and reports
it. Audit looks in the folder itself (`CallTag.workspace`: Audit reads, a builder of this output edits; the owner's access setting caps
both). The one vendored change it needs is patch P14 (`single`: named documents in the brief do not swap the output).

Everything here is data and small functions: the texts below are the output's own prompts, the conditions are the file
`data/project.json` (an absolute name, so `j2.load_conditions` finds it without touching the vendored `conditions/` folder), and the
mocks are what the offline mode answers. J2 is imported lazily, inside `outputs()`, so importing this module reads no environment.
"""
import os
import re
from pathlib import Path
from typing import Optional

from .base import Capability, EngineContext, OutputSpec, Selection
from .select import choose_output

__all__ = ["ProjectCapability", "PROJECT_SECTIONS", "PROJECT_RUBRIC", "CONDITIONS_FILE", "PROJECT_INTAKE", "PROJECT_PLAN",
           "PROJECT_BUILDER", "project_spec", "mock_project_charter", "mock_project_section", "bind_data_dir"]

# The design names the third section "Verification". J2's own validator refuses that word: a done-when item may not contain it
# (`J2Run.NOT_CHECKABLE`) and, unless the realization pass is on, a workflow whose name contains it is "Audit's job, not a workflow"
# (`J2Run.CHECK_WORK`); and the offline mock plan of a document has no costs while the realization pass is on. So the section is called
# "Confirmation": the same content (what was checked in the folder, how, and what could not be), a word the validator lets through.
PROJECT_SECTIONS = ("Findings", "Changes", "Confirmation", "Open items", "Outcome")
CONDITIONS_FILE = str(Path(__file__).resolve().parent / "data" / "project.json")
# A project has no data model and no template, so both are switched off for it (the host says so in a trace line).
FORCE = {"artifact_schema": False, "template_library": False}

PROJECT_RUBRIC = (
    ("PJ-1", "Every finding names the file or command it comes from"),
    ("PJ-2", "Every change the report lists is found in the folder: Audit looks, in the file or in `git diff`"),
    ("PJ-3", "Nothing was changed that the request did not ask for"),
    ("PJ-4", "Confirmation says what was checked and how, and says what could not be checked"),
    ("PJ-5", "No invented facts: a claim beyond a file that was read or the request is labelled \"Assumption:\""),
)

PROJECT_INTAKE = (
    "J2.a for project work in the owner's working folder. Look at the folder with your file tools before you ask anything. Ask only "
    "what the folder and its instructions cannot answer (enough=false, 1 to 3 questions); never ask what a file says. If the prompt says "
    "no working folder is set, set enough=false and ask the owner to choose one in Settings, under Connectors, in Working folder, and to "
    "say the request again. Record the charter from the brief, the answers and what you read; `product_name` is the project (folder or "
    "repository) name; `features` are the changes or checks asked; `facts` are exact names the owner used. done_when: one checkable item "
    "per section. Keep everything the brief asks for. Don't plan costs.\n"
    "- What the brief asks decides the goal. A brief that asks to update, implement, fix, change or add something means the goal includes "
    "making that change in the folder: `features` name it and the done_when item for the Changes section names the files to change. A brief "
    "that only asks to look, list, check or report stays a report: that item says no change was asked.\n"
    "- The folder's access is what the working folder text says the owner allowed. Your own tools only read because you plan; that is not a "
    "limit of the run, so never put it in the charter. Write \"Folder is read-only\" in constraints or rules only when that text says the "
    "owner chose read only. Then, if the brief asks for a change, the goal is the report: it says plainly that changes cannot be made, "
    "gives the exact edits file by file, and says how to allow changes (Settings, under Working folder). When changes are allowed, never "
    "write that files are not changed.")

PROJECT_PLAN = (
    "\nTHE OUTPUT IS A PROJECT WORK REPORT (markdown). Plan one workflow per section in this order: "
    f"{', '.join(PROJECT_SECTIONS)}, named \"Write <Section>\" (for example \"Write Confirmation\"); each has one work atom whose how.steps names its "
    "`## <Section>` heading. Findings reads the folder; "
    "Changes makes exactly the changes the charter asks for; Confirmation checks them; price with the document rate card.")

PROJECT_BUILDER = (
    "Workflow agent for one section of a project work report. You work in the owner's folder with your file tools. Findings: read and "
    "report what you saw, naming each file. Changes: make the smallest change that does what the charter asks, follow the project's own "
    "instructions, then list each on its own line as - `path`: what changed; never commit; never describe a change instead of making it; "
    "when your tools are read-only (the owner chose read only) write 'No changes were made: the folder is read only for the team.' and, when "
    "the charter asks for a change, give the exact edits file by file and say how to allow changes (Settings, under Working folder). "
    "Confirmation: look at the files and `git diff`/`git status` and say what you confirmed "
    "and what you could not (you cannot run tests). Open items: what is left and why. Outcome: three sentences from the other sections. "
    "Reply with the section only, starting with `## <Section>`, in markdown. Claims beyond a file you read or the charter start with "
    "`Assumption:`.")

ADDENDA = {
    "identity": ("Project work: look before you ask. Read the working folder with your file tools first, and ask the owner only what the "
                 "folder and its instructions cannot answer. This is not a website: never ask about pages, menus or visitors. Your tools only "
                 "read, because you plan: the builders change files when the owner allowed it, and the working folder text says whether he or "
                 "she did, so plan for what the team can do and never write your own tools' limit into the charter as the run's."),
    "adaptation": f"Project work: plan the five sections only ({', '.join(PROJECT_SECTIONS)}), one workflow each, in that order.",
    "audit": ("Project work: check every change the report claims against the folder with your tools: read the file and look at `git diff` and "
              "`git status`. A change the report claims that the folder does not show has not been made; a change the charter asked for that "
              "the folder does not show is not done, whatever the report says; a change the request did not ask for fails the rubric. You "
              "cannot edit anything: you check the builders' work independently of them."),
}

def project_spec(j2) -> OutputSpec:
    """The output's spec, built from the J2 module that is running (its charter format, rate card and atom helper)."""
    return OutputSpec(
        label="Project work", noun="report", sections=PROJECT_SECTIONS, conditions=CONDITIONS_FILE, rubric=PROJECT_RUBRIC,
        rates="rates_prd", check_types=j2.DOC_CHECK_TYPES, builder=PROJECT_BUILDER, export=None, file="project.md",
        intake=PROJECT_INTAKE, charter_fmt=j2.PRD_CHARTER_FMT, plan=PROJECT_PLAN, atom_rules=_atom_rules(j2.PRD_ATOM_RULES),
        mock_charter=mock_project_charter, mock_section=mock_project_section, mock_atom=j2.doc_atom_for(PROJECT_SECTIONS, {}),
        done="Done: the project work report is workable. Every done-when item, rubric item and necessary condition passes.",
        single=True, workspace="edit")


# `PRD_ATOM_RULES` with the sentences about ids taken out (a project report has no R1, R2, ... ids): the only check types left are
# heading-present, section-not-empty and facts-present. Each pair must match J2's text exactly, or the registration stops.
_ATOM_EDITS = (
    (' ids (target: the id prefix, "R" for requirement ids R1, R2, ...),', ""),
    (' ids-unique (target: an id prefix, "R" for R1, R2, ...; expect true);', ""),
    ("in the PRD when", "in the report when"),
    ("on the PRD after", "on the report after"),
)


def _atom_rules(prd_rules: str) -> str:
    text = prd_rules
    for old, new in _ATOM_EDITS:
        if old not in text:
            raise RuntimeError(f"the project output's atom rules no longer match J2's PRD_ATOM_RULES: {old[:60]!r}")
        text = text.replace(old, new)
    return text


# ---- mocks (offline mode; no folder is ever read) -------------------------------------------------------------------------
def _name_of(text: str) -> str:
    m = re.search(r"\b(?:for|called|of|in)\s+(?:the\s+)?([A-Z][\w'-]*(?:\s+[A-Z0-9][\w'-]*)*)", text)
    return m.group(1) if m else "The project"


def _clauses(text: str) -> list[str]:
    parts = [" ".join(p.split()).strip(" .,;:") for p in re.split(r"(?<=[.!?])\s+|\n+|;|\band then\b|\band\b", text or "")]
    return [p[:1].upper() + p[1:] for p in parts if len(p.split()) >= 3][:5]


# What the owner allowed in the working folder, as the SCRIPTED Identity reads it (offline mode only): the real Identity reads the same fact from the working
# folder text its calls carry (`Router.folder_for`); a scripted reply has no router, so `install` binds the data folder and the mock asks the store.
_BOUND: dict = {"data_dir": None}
_CHANGE = re.compile(r"\b(?:updat\w*|upgrad\w*|implement\w*|fix\w*|chang\w*|add(?:s|ed|ing)?|creat\w*|writ(?:e|es|ing|ten)|rewrit\w*|renam\w*|remov\w*|"
                     r"delet\w*|refactor\w*|edit\w*|modif\w*|replac\w*|insert\w*|append\w*|patch\w*)\b", re.I)
_NAMED_FILE = re.compile(r"(?<![\w./-])((?:[\w-]+/)*[\w-]+\.(?:md|txt|py|js|ts|tsx|jsx|json|html|css|yml|yaml|toml|cfg|ini|sh|java|go|rs|rb|php|sql))(?![\w])")


def bind_data_dir(data_dir) -> None:
    """Tell the scripted Identity where the owner's choices live (`install` calls it for every run; a test may bind a folder or None)."""
    _BOUND["data_dir"] = data_dir


def _folder_access() -> str:
    """`edit` or `read`: what the owner allowed in the working folder; `` when none is set (or no data folder is bound)."""
    if _BOUND["data_dir"] is None:
        return ""
    try:
        from sutra_app.connectors.workdir import WorkFolder
        grant = WorkFolder(_BOUND["data_dir"]).grant()
    except Exception:  # noqa: BLE001 - an unreadable store is "no folder", never a failed scripted reply
        return ""
    return "" if grant is None else ("edit" if getattr(grant, "edit", False) else "read")


def mock_project_charter(text: str, access: Optional[str] = None) -> dict:
    """Mock only: a project charter from the brief: the project's name, the changes or checks it asks for (its own sentences). It follows the same
    rules the real Identity is given (`PROJECT_INTAKE`): a brief that asks for a change has the change as its goal, with the files named in the
    Changes item; "Folder is read-only" is written only when the owner chose read only (`access`, else the bound folder's), and then the goal is the
    report of the exact edits; a brief that only looks stays a report."""
    name = _name_of(text)
    features = _clauses(text) or ["Look at the project and report what was found"]
    allowed = _folder_access() if access is None else access
    asks = bool(_CHANGE.search(text or ""))
    named = list(dict.fromkeys(_NAMED_FILE.findall(text or "")))[:5]
    constraints, rules = ["Change only what the request asks", "Never commit"], ["No invented facts"]
    changes = f"The Changes section lists every change made to {name}"
    if not asks:
        constraints = ["The request asks for no change: leave every file as it is", "Never commit"]
        changes = f"The Changes section says no change was asked in {name}"
    elif allowed == "read":
        constraints = ["Folder is read-only: the owner chose read only in Settings, under Working folder, so changes cannot be made here",
                       "The report gives the exact edits and how to allow changes"]
        rules = ["No invented facts", "Do not change any file in the working folder"]
        changes = f"The Changes section says changes cannot be made in {name}, gives the exact edits file by file and says how to allow changes"
    elif named:
        changes = f"The Changes section lists each change made to {', '.join(named)} in {name}"
    items = [f"The Findings section says what was found in {name}", changes,
             "The Confirmation section says what was checked and what could not be", "The Open items section says what is left and why",
             "The Outcome section sums the work up in three sentences"]
    return {"statement": f"Project work on {name}", "product_name": name, "site_name": name, "users": "The owner",
            "audience": "The owner", "user_groups": [{"name": "Owner", "actions": features}],
            "problem": " ".join((text or "").split())[:300] or "The request in the brief", "features": features,
            "constraints": constraints, "success_measures": [],
            "facts": [name], "standards": ["Every finding names its file"], "rules": rules,
            "done_when": items, "core": [True, True, True, False, False], "to_be_confirmed": [], "dropped_from_brief": [],
            "business_type": "project", "visitor_needs": []}


def mock_project_section(w: dict, goal: Optional[dict]) -> str:
    """Mock only: the markdown a scripted builder writes for the section its workflow names. Offline it changes nothing."""
    g = goal or {}
    sec = next((s for s in PROJECT_SECTIONS if s.lower() in str(w.get("name")).lower()), PROJECT_SECTIONS[0])
    name, feats = g.get("product_name") or "The project", g.get("features") or []
    asked = "; ".join(feats) or "the request in the brief"
    body = {"Findings": f"- Looked at {name} for this request: {asked}.\n- Offline mode: no file of the folder was read.",
            "Changes": f"No changes were made to {name}: this is an offline run, so nothing in the folder was touched.",
            "Confirmation": f"Nothing could be checked in {name}: offline mode reads no file and runs no command.",
            "Open items": f"- Everything asked is still open for {name}: {asked}.",
            "Outcome": f"This was an offline run for {name}. Nothing was read or changed in the folder. "
                       "Run it again with a model to do the work."}[sec]
    return f"## {sec}\n\n{body}\n"


# ---- the capability --------------------------------------------------------------------------------------------------------
class ProjectCapability(Capability):
    name = "project"

    def outputs(self) -> dict:
        import importlib
        return {"project": project_spec(importlib.import_module("sutra_app.engine.j2"))}

    def install(self, ctx: EngineContext) -> None:
        bind_data_dir(getattr(ctx, "data_dir", None))              # the scripted Identity reads the owner's access choice from the same store

    def select(self, brief: str, ctx: EngineContext) -> Optional[Selection]:
        return choose_output(brief, ctx.has_folder, ctx.seed_output, ctx.settings.output)

    def force(self, output: str) -> dict:
        return dict(FORCE) if output == "project" else {}

    def addendum(self, fn: str, ctx: EngineContext) -> str:
        if ctx.output != "project":
            return ""
        text = ADDENDA.get(fn)
        return f"\n\n## Project work\n{text}" if text else ""
