"""The capability registry (engine design 2.1, D126): one engine that keeps gaining abilities, each inherited by every agent and every
output, with nothing routed in front of it.

    CAPABILITIES   the fixed tuple of capabilities; adding the next one is one module and one line here
    register(j2)   once per process, after J2 is imported and before `J2Run` exists: registers every capability's outputs as types with
                   `j2_types.register` (patch P18; idempotent; a name that already exists raises `CapabilityConflict`, so no capability can
                   replace another)
    install(ctx)   once per run process: each `install(ctx)`, then the tag and progress hooks go into `llm.TAG_HOOKS` / `llm.PROGRESS_HOOKS`,
                   which `llm.ask` runs for every call of every output
    addenda(fn, ctx)  every capability's system text for agent `fn`
    documents(output, run_dir)  every capability's Artifacts rows for the report of a run of `output`: the fallback of the Documents group,
                   whose row J2 now lists itself (D146, amended by D164)
    describe()     what `GET /api/engine/capabilities` answers: the registry is the only way the host, the API and the tests learn what
                   the engine can do

The package imports no J2 module: `register` is given the J2 module, so the API process, the stdlib adapter, the host and the tests all
see the same outputs.
"""
import importlib
import sys
from typing import Optional

from .. import llm
from .base import Capability, CapabilityConflict, EngineContext, OutputSpec, Selection, SPECS, output_spec
from .project import ProjectCapability
from .workspace import WorkspaceCapability

__all__ = ["CAPABILITIES", "Capability", "CapabilityConflict", "EngineContext", "OutputSpec", "Selection", "SPECS",
           "output_spec", "register", "install", "addenda", "documents", "describe", "capability_hooks", "select_output",
           "forced_settings"]


def _agent_capabilities() -> tuple:
    """The two capabilities of the agent sessions (picks and live view) when their module is there; they come last, in this order."""
    try:
        agents = importlib.import_module(f"{__name__}.agents")
    except ModuleNotFoundError as exc:
        if exc.name != f"{__name__}.agents":
            raise
        return ()
    return tuple(cls() for cls in (getattr(agents, name, None) for name in ("AgentPicksCapability", "AgentLiveCapability")) if cls)


CAPABILITIES: tuple = (WorkspaceCapability(), ProjectCapability(), *_agent_capabilities())


def _caps(capabilities) -> tuple:
    return CAPABILITIES if capabilities is None else tuple(capabilities)


def register(j2, capabilities=None) -> None:
    """Register every capability's outputs as types (`j2.j2_types.register`, patch P18), the entry beside its callables. All or nothing: a
    conflict raises before anything is registered. Registering the same capability twice is a no-op in effect (the same owner replaces its
    own entry); a name that is not ours (J2's own, a local type, another capability's) is a conflict."""
    types = j2.j2_types
    pending: dict[str, tuple[Capability, OutputSpec]] = {}
    for cap in _caps(capabilities):
        for name, spec in cap.outputs().items():
            if name in pending:
                raise CapabilityConflict(f"the output {name!r} is registered by both {pending[name][0].name!r} and {cap.name!r}")
            pending[name] = (cap, spec)
    known = set(types.names())
    for name, (cap, _spec) in pending.items():
        owner = (types.HOST.get(name) or {}).get("entry", {}).get("host")
        if name in known and owner != cap.name:
            raise CapabilityConflict(f"the output {name!r} (capability {cap.name!r}) already exists in the engine")
    for name, (cap, spec) in pending.items():
        try:
            types.register(spec.to_type_entry(cap.name), spec.extras())
        except ValueError as exc:
            raise CapabilityConflict(f"the output {name!r} (capability {cap.name!r}) was refused: {exc}") from None
        SPECS[name] = spec


def capability_hooks(ctx: EngineContext, capabilities=None) -> tuple[list, list]:
    """(tag hooks, progress hooks) for `llm`: closures over the context. A capability without its own `progress` adds no progress hook, so
    a process whose capabilities only tag calls does not ask the model port for partial text."""
    tags, progress = [], []
    for cap in _caps(capabilities):
        if type(cap).tag is not Capability.tag:
            def tag_hook(tag, cap=cap):
                return cap.tag(tag, ctx)
            tag_hook.capability = cap.name
            tags.append(tag_hook)
        if type(cap).progress is not Capability.progress:
            def progress_hook(tag, event, cap=cap):
                return cap.progress(tag, event)
            progress_hook.capability = cap.name
            progress.append(progress_hook)
    return tags, progress


def install(ctx: EngineContext, capabilities=None) -> None:
    """Per process: every `install(ctx)`, then the hooks. A second call (a test that runs two hosts in one process) replaces the hooks the
    first one put there instead of adding to them."""
    caps = _caps(capabilities)
    for cap in caps:
        cap.install(ctx)
    tags, progress = capability_hooks(ctx, caps)
    llm.TAG_HOOKS[:] = [h for h in llm.TAG_HOOKS if not hasattr(h, "capability")] + tags
    llm.PROGRESS_HOOKS[:] = [h for h in llm.PROGRESS_HOOKS if not hasattr(h, "capability")] + progress


def select_output(brief: str, ctx: EngineContext, capabilities=None) -> Selection:
    """The output for this brief: the first capability that votes, else none: the team's planner chooses (D165). `ctx.settings.output` is
    the choice the owner made (`auto` when they made none)."""
    for cap in _caps(capabilities):
        vote = cap.select(brief, ctx)
        if vote is not None:
            return vote
    return Selection(None, "planner", "the team's planner chooses")


def forced_settings(output: Optional[str], capabilities=None) -> dict:
    """The engine settings (`{field: value}`) fixed for a run of `output`. Asked before J2 is imported. The first capability to name a field
    wins, so no capability can undo another's."""
    fixed: dict = {}
    for cap in _caps(capabilities):
        for name, value in cap.force(output).items():
            fixed.setdefault(name, value)
    return fixed


def addenda(fn: str, ctx: EngineContext, capabilities=None) -> str:
    """Every capability's system text for agent `fn`, in registry order. A capability that fails adds nothing."""
    out = ""
    for cap in _caps(capabilities):
        try:
            text = cap.addendum(fn, ctx)
        except Exception as exc:  # noqa: BLE001
            print(f"addendum of capability {cap.name} failed: {type(exc).__name__}: {str(exc)[:300]}", file=sys.stderr)
            continue
        out += text if isinstance(text, str) else ""
    return out


def documents(output: Optional[str], run_dir, capabilities=None) -> list:
    """Every capability's Artifacts rows for the report of a run of `output` in `run_dir`, in registry order (D146): `[]` for J2's own
    types and for no type (no capability registered them), the report row for an output a capability added. The caller merges these with
    J2's own Documents rows by id, J2's row first (D164). A capability that fails adds nothing:
    the Artifacts pane is polled and must not break because one hook did."""
    rows: list = []
    for cap in _caps(capabilities):
        try:
            got = cap.documents(output, run_dir)
        except Exception as exc:  # noqa: BLE001
            print(f"documents of capability {cap.name} failed: {type(exc).__name__}: {str(exc)[:300]}", file=sys.stderr)
            continue
        rows += got if isinstance(got, list) else []
    return rows


def describe(capabilities=None) -> list:
    """`[{name, outputs: [{name, label, workspace, single}], settings: [...]}]` for every capability, in registry order."""
    rows = []
    for cap in _caps(capabilities):
        outs = []
        for name, spec in cap.outputs().items():
            data = {**spec.to_type_entry(cap.name), **spec.extras()} if isinstance(spec, OutputSpec) else dict(spec)
            outs.append({"name": name, "label": data.get("label", name), "workspace": data.get("workspace", "read"),
                         "single": bool(data.get("single", False))})
        rows.append({"name": cap.name, "outputs": outs, "settings": cap.settings()})
    return rows
