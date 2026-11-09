"""The capability registry (engine design 2.1, D126): one engine that keeps gaining abilities, each inherited by every agent and every
output, with nothing routed in front of it.

    CAPABILITIES   the fixed tuple of capabilities; adding the next one is one module and one line here
    register(j2)   once per process, after J2 is imported and before `J2Run` exists: merges every capability's outputs into `j2.OUTPUTS`
                   (idempotent; a name that already exists raises `CapabilityConflict`, so no capability can replace another)
    install(ctx)   once per run process: each `install(ctx)`, then the tag and progress hooks go into `llm.TAG_HOOKS` / `llm.PROGRESS_HOOKS`,
                   which `llm.ask` runs for every call of every output
    addenda(fn, ctx)  every capability's system text for agent `fn`
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
from .workspace import WorkspaceCapability

__all__ = ["CAPABILITIES", "Capability", "CapabilityConflict", "EngineContext", "OutputSpec", "Selection", "SPECS", "output_spec",
           "register", "install", "addenda", "describe", "capability_hooks"]


def _agent_capabilities() -> tuple:
    """The two capabilities of the agent sessions (picks and live view) when their module is there; they come last, in this order."""
    try:
        agents = importlib.import_module(f"{__name__}.agents")
    except ModuleNotFoundError as exc:
        if exc.name != f"{__name__}.agents":
            raise
        return ()
    return tuple(cls() for cls in (getattr(agents, name, None) for name in ("AgentPicksCapability", "AgentLiveCapability")) if cls)


CAPABILITIES: tuple = (WorkspaceCapability(), *_agent_capabilities())


def _caps(capabilities) -> tuple:
    return CAPABILITIES if capabilities is None else tuple(capabilities)


def register(j2, capabilities=None) -> None:
    """Merge every capability's outputs into `j2.OUTPUTS`. All or nothing: a conflict raises before anything is added. Registering the
    same capability twice is a no-op (the entry is marked with the capability's name); an entry that is not ours is a conflict."""
    pending: dict[str, tuple[Capability, dict, Optional[OutputSpec]]] = {}
    for cap in _caps(capabilities):
        for name, spec in cap.outputs().items():
            if name in pending:
                raise CapabilityConflict(f"the output {name!r} is registered by both {pending[name][0].name!r} and {cap.name!r}")
            entry = spec.to_j2() if isinstance(spec, OutputSpec) else dict(spec)
            pending[name] = (cap, {**entry, "capability": cap.name}, spec if isinstance(spec, OutputSpec) else None)
    for name, (cap, entry, _spec) in pending.items():
        have = j2.OUTPUTS.get(name)
        if have is not None and have.get("capability") != cap.name:
            raise CapabilityConflict(f"the output {name!r} (capability {cap.name!r}) already exists in the engine")
    for name, (cap, entry, spec) in pending.items():
        if name not in j2.OUTPUTS:
            j2.OUTPUTS[name] = entry
        if spec is not None:
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


def describe(capabilities=None) -> list:
    """`[{name, outputs: [{name, label, workspace, single}], settings: [...]}]` for every capability, in registry order."""
    rows = []
    for cap in _caps(capabilities):
        outs = []
        for name, spec in cap.outputs().items():
            data = spec.to_j2() if isinstance(spec, OutputSpec) else dict(spec)
            outs.append({"name": name, "label": data.get("label", name), "workspace": data.get("workspace", "read"),
                         "single": bool(data.get("single", False))})
        rows.append({"name": cap.name, "outputs": outs, "settings": cap.settings()})
    return rows
