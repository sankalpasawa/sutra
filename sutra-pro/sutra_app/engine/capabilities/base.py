"""What a capability is (engine design 2.1, D126): a small object the engine always runs. It can ADD outputs, call-tag fields, prompt
text, progress sinks and one setting; it can never replace what another one added or what the engine already has.

    Capability.outputs()    new output types, registered with `j2_types.register` by `capabilities.register` (a name that exists is a conflict)
    Capability.install(ctx) once per run process, after J2 is imported and before `J2Run` exists
    Capability.tag(tag, ctx)       extra `CallTag` fields for one call (`llm.ask` takes only the fields still empty on the tag)
    Capability.progress(tag, event) sees each progress event of a call
    Capability.addendum(fn, ctx)   system text for agent `fn` (`ctx.output` says which output is running)
    Capability.select(brief, ctx)  a vote on the output when the owner left it on `auto`
    Capability.force(output)       settings fixed for a run of one output (`{field: value}`)
    Capability.documents(output, run_dir)  the Artifacts rows for the report of an output this capability added (D146)

This module imports nothing of J2 and nothing of the host when it is imported: `OutputSpec.to_type_entry()` and `extras()` are the
places that turn a spec into what J2 reads, and `documents` imports J2's Artifacts module only when a report row is asked for.
"""
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:       # typing only: the settings module imports the names of the outputs from the package above this file
    from pathlib import Path

    from ..paths import DataPaths
    from ..port import CallTag
    from ..spec import EngineSettings, TaskSpec

__all__ = ["Capability", "CapabilityConflict", "OutputSpec", "EngineContext", "Selection", "SPECS", "output_spec", "WORKSPACE_LEVELS"]

WORKSPACE_LEVELS = ("read", "edit")


class CapabilityConflict(RuntimeError):
    """A capability tried to register an output that already exists (the engine's own or another capability's)."""


@dataclass(frozen=True)
class Selection:
    """The output the engine chose for a brief: `rule` is the row of the table that decided (`select.RULES`), `reason` the
    owner-readable clause that goes into `output.json` and, for project work, into the chat."""

    output: Optional[str]            # None: undecided, J2's planner chooses (D165)
    rule: str
    reason: str


@dataclass(frozen=True)
class OutputSpec:
    """A type a capability adds, in two parts (D164): the JSON-safe type entry J2's `j2_types` reads (`to_type_entry()`: it names its text
    files, which belong to the capability and may be absolute paths) and the keys J2 cannot read from data (`extras()`): `single` (named
    documents in the brief do not swap the output: patch P14), `workspace` (the most the builders of this output may do in the owner's
    folder), `deliver` (a run of this output leaves a file the owner reads: the host records what it delivered and what changed in the
    owner's folder in `deliverable.json` before `run.ended`, and the server posts it to the team's chat; D135) and the offline mocks.
    `force_off` settings are not here: `Capability.force` says them."""

    name: str
    label: str
    noun: str
    file: str
    sections: tuple = ()
    rubric: tuple = ()                  # ((id, text), ...)
    check_types: tuple = ()
    done: str = ""
    conditions: str = ""                # paths of the capability's own text files (absolute: `j2_types.load` joins them as they are)
    builder: str = ""
    intake: str = ""
    charter_format: str = ""
    atom_rules: str = ""
    template: str = ""
    tag: str = ""
    mock_charter: Optional[Callable] = None
    mock_section: Optional[Callable] = None
    mock_atom: Optional[Callable] = None
    single: bool = False
    workspace: str = "read"
    deliver: bool = False

    def __post_init__(self) -> None:
        if self.workspace not in WORKSPACE_LEVELS:
            raise ValueError(f"workspace is one of {', '.join(WORKSPACE_LEVELS)}, not {self.workspace!r}")

    def to_type_entry(self, owner: str) -> dict:
        """The JSON-safe `kind: "type"` entry of a document-form type that no planner lists (`deliverable: false`), owned by capability
        `owner`. Everything it leaves out comes from the `document` form of `types.json`. The cost block keeps the form's rate card and
        prices no item as a requirements section."""
        return {"name": self.name, "kind": "type", "label": self.label, "tag": self.tag or self.label.split()[0], "color": "--other",
                "form": "document", "file": self.file, "noun": self.noun, "export": None, "template": self.template,
                "rubric": [{"id": i, "text": t} for i, t in self.rubric], "check_types": list(self.check_types), "done": self.done,
                "conditions": self.conditions, "builder": self.builder, "intake": self.intake, "charter_format": self.charter_format,
                "atom_rules": self.atom_rules, "deliverable": False, "triggers": [], "groups": [], "depends_on": [],
                "cost": {"item_parts": [{"part": "doc_section", "words": ""}]}, "host": owner}

    def extras(self) -> dict:
        """What J2 reads from `output_def(name)` and cannot read from data: the flags and the offline mocks that are set."""
        out: dict = {"single": self.single, "workspace": self.workspace, "deliver": self.deliver}
        for key in ("mock_charter", "mock_section", "mock_atom"):
            if getattr(self, key) is not None:
                out[key] = getattr(self, key)
        return out


SPECS: dict[str, OutputSpec] = {}        # the outputs the capabilities registered, by name (`register` fills it)


def output_spec(name: Optional[str]) -> Optional[OutputSpec]:
    return SPECS.get(str(name or ""))


@dataclass
class EngineContext:
    """What a capability may know about the run: the task, the settings the host resolved, the paths. `selection` is the output the
    host chose; `run` is the `J2Run` once it exists (the host sets it), so `output` can follow a run that changes its output."""

    task: "TaskSpec"
    settings: "EngineSettings"
    paths: "DataPaths"
    data_dir: "Path"
    selection: Optional[Selection] = None
    has_folder: bool = False
    seed_output: Optional[str] = None
    run: Any = None

    @property
    def output(self) -> Optional[str]:
        """The run's concrete output: the live run's, else the one the host chose; None while no type is chosen (never `auto`; D165)."""
        live = getattr(self.run, "output", None)
        if isinstance(live, str) and live:
            return live
        if self.selection is not None:
            return self.selection.output
        return self.settings.output if self.settings.output != "auto" else None


class Capability:
    """Subclass and override what you add. Every method has a harmless default, so a capability is as small as it needs to be."""

    name: str = ""

    def outputs(self) -> dict:
        return {}

    def install(self, ctx: EngineContext) -> None:
        return None

    def tag(self, tag: "CallTag", ctx: EngineContext) -> dict:
        return {}

    def progress(self, tag: "CallTag", event: dict) -> None:
        return None

    def addendum(self, fn: str, ctx: EngineContext) -> str:
        return ""

    def select(self, brief: str, ctx: EngineContext) -> Optional[Selection]:
        return None

    def force(self, output: str) -> dict:
        """Engine settings (field name: value) this capability fixes for a run of `output`, because the output cannot work, or has nothing to
        use, otherwise. Asked by the host BEFORE J2 is imported, so it cannot depend on the registered outputs."""
        return {}

    def settings(self) -> list:
        """The one engine setting this capability has, if any: `[{"field": "workspace", "values": [...], "default": ...}]`."""
        return []

    def documents(self, output: str, run_dir) -> list:
        """The Artifacts rows (the Documents group of `artifacts-groups/1`) for a run of `output` in `run_dir` (D146).

        J2's Documents group lists its own PRD, HLD and LLD, because the constant that names them (`TYPES_PATH`) holds no other type.
        An output a capability adds has a report file too (`OutputSpec.file`), so the capability that registered the output says
        what its row is, from the spec it already has: nothing of J2 is patched, and a future output with a report file shows
        up the same way with no code. Every capability inherits this: `[]` unless `output` is one of THIS capability's outputs, its
        spec names a `file`, and that file exists in the run folder. Otherwise one row of J2's own document shape (`id`, `kind`,
        `name`, `file`, `doc_file`, `maker`, `made_in`, `sections`, `nodes`, `versions`, `docs`, `ok`, `views`): `views` is
        `j2_artifacts.views(run_dir, row)`, so the three tabs (Summary, Agent-readable, Human-readable) work as they do for a PRD.
        A report is not a Map node, so `nodes` is empty and no Map link points at it."""
        spec = self.outputs().get(output) if output and run_dir else None
        if spec is None:
            return []
        get = (lambda key: getattr(spec, key, None)) if isinstance(spec, OutputSpec) else spec.get
        file = get("file")
        if not isinstance(file, str) or not file or not os.path.isfile(os.path.join(run_dir, file)):
            return []
        from .. import j2_artifacts          # J2's module is read when a row is built, never when the registry is imported
        label, noun = str(get("label") or output), str(get("noun") or "").strip()
        row = {"id": output, "kind": "document", "name": f"{label} {noun}".strip(), "file": file, "doc_file": file, "maker": None,
               "made_in": [], "sections": {}, "nodes": [],
               "versions": [{"workflow": None, "cycle": None, "purpose": "", "label": "current"}], "docs": [],
               "ok": os.path.getsize(os.path.join(run_dir, file)) > 0}
        row["views"] = j2_artifacts.views(run_dir, row)
        return [row]
