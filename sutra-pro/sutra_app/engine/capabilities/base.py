"""What a capability is (engine design 2.1, D126): a small object the engine always runs. It can ADD outputs, call-tag fields, prompt
text, progress sinks and one setting; it can never replace what another one added or what the engine already has.

    Capability.outputs()    new output types, merged into `j2.OUTPUTS` by `capabilities.register` (a name that exists is a conflict)
    Capability.install(ctx) once per run process, after J2 is imported and before `J2Run` exists
    Capability.tag(tag, ctx)       extra `CallTag` fields for one call (`llm.ask` takes only the fields still empty on the tag)
    Capability.progress(tag, event) sees each progress event of a call
    Capability.addendum(fn, ctx)   system text for agent `fn` (`ctx.output` says which output is running)
    Capability.select(brief, ctx)  a vote on the output when the owner left it on `auto`

This module imports nothing of J2 and nothing of the host: `OutputSpec.to_j2()` is the one place that turns a spec into the dict J2 reads.
"""
from dataclasses import dataclass, field
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

    output: str
    rule: str
    reason: str


@dataclass(frozen=True)
class OutputSpec:
    """The keys of a `j2.OUTPUTS` entry, plus what the capabilities layer adds: `single` (named documents in the brief do not swap the
    output: patch P14), `workspace` (the most the builders of this output may do in the owner's folder) and `force_off` (engine settings
    that are switched off for a run of this output because the output has nothing for them)."""

    label: str
    noun: str
    sections: tuple = ()
    conditions: str = ""
    rubric: tuple = ()
    rates: str = "rates"
    check_types: tuple = ()
    builder: str = ""
    export: Optional[Callable] = None
    file: Optional[str] = None
    intake: Optional[str] = None
    charter_fmt: Optional[str] = None
    plan: Optional[str] = None
    atom_rules: Optional[str] = None
    mock_charter: Optional[Callable] = None
    mock_section: Optional[Callable] = None
    mock_atom: Optional[Callable] = None
    done: str = ""
    single: bool = False
    workspace: str = "read"
    force_off: tuple = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.workspace not in WORKSPACE_LEVELS:
            raise ValueError(f"workspace is one of {', '.join(WORKSPACE_LEVELS)}, not {self.workspace!r}")

    def to_j2(self) -> dict:
        """The `j2.OUTPUTS` entry: every key that is set (J2 reads the optional ones with `.get`)."""
        entry = {"label": self.label, "noun": self.noun, "sections": tuple(self.sections), "conditions": self.conditions,
                 "rubric": tuple(self.rubric), "rates": self.rates, "check_types": tuple(self.check_types), "builder": self.builder,
                 "export": self.export, "done": self.done}
        for key in ("file", "intake", "charter_fmt", "plan", "atom_rules", "mock_charter", "mock_section", "mock_atom"):
            value = getattr(self, key)
            if value is not None:
                entry[key] = value
        entry["single"] = self.single
        entry["workspace"] = self.workspace
        return entry


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
    def output(self) -> str:
        """The run's concrete output: the live run's, else the one the host chose (never `auto`)."""
        live = getattr(self.run, "output", None)
        if isinstance(live, str) and live:
            return live
        if self.selection is not None:
            return self.selection.output
        return self.settings.output if self.settings.output != "auto" else "website"


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

    def settings(self) -> list:
        """The one engine setting this capability has, if any: `[{"field": "workspace", "values": [...], "default": ...}]`."""
        return []
