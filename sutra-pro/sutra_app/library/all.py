"""Import the whole Interface library, so that `REGISTRY` holds every family (library design section 2; work package L8).

    from sutra_app.library import all as library        # or: import sutra_app.library.all

The order is the dependency order of the design (section 17, risk 10): foundations, then the models, then `artifacts` before
`templates`, then `wire` (L9), then the catalogue `records` (which registers the payloads only it reads) and the schema router
`api`. `export` imports this module to find the registry, so `docs/schemas/` is exactly what is registered here.

This module does NOT freeze the registry at import. The orchestrator registers four more families of its own
(`orchestrator/records.py`, which the library must not import), and a registry frozen here would refuse them depending on
which module the process imported first. The process that builds the app calls `freeze()` once everything is imported.
"""
from . import (  # noqa: F401  (imported for what they register)
    artifacts, atom, base, chat, department, evaluation, functions, gate, goal, node, org_chart, records, registry, replies,
    templates, types, wire, workflow,
)
from . import api  # noqa: F401  (after records: the router checks with the catalogue's registry)
from .gate import GATE
from .registry import REGISTRY
from .types import Violation

__all__ = ["REGISTRY", "GATE", "verify", "freeze", "families"]


def families() -> list[str]:
    """Every registered family name, sorted (what `GET /api/schemas` lists)."""
    return REGISTRY.families()


def verify() -> list[Violation]:
    """The full-registry reference check: every FunctionSpec task kind answers with a registered reply family and kind, and
    every template check is a known name with the right argument count. `[]` means at least one spec was looked at (L1 made
    `verify_refs` raise when it has nothing to check). The specs and the arity function are bound by `node.py` and `atom.py`."""
    return REGISTRY.verify_refs()


def freeze() -> None:
    """Close the registry: later `register`, `register_payload` and `upgrade` raise `RegistryError("frozen")`. Call it once
    in the process that composes the app, after the orchestrator's records are imported."""
    REGISTRY.freeze()
