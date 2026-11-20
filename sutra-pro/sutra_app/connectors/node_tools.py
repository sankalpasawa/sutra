"""What the builder tools of a step of a project may be, enforced (D380): the router takes J2's tool list for a call of a node down to what the node's frozen grant allows. The rule itself is pure and lives in
`orchestrator/builder_rights.py` (the grant line reads it too); this module applies it to a `ToolGrant`.

J2's builder asks for Claude's whole tool list in its own folder. For an ordinary run that is how it has always been. A step of a project holds a GRANT, which is the owner's word about what the step may do, so
the host (the router, never the vendored engine) narrows the list before the call is planned. A tool the rule does not name is never allowed (deny by default). A step whose rights are not known gets the
narrowest list, never the widest.
"""
from __future__ import annotations

from pathlib import Path

from sutra_app.engine.port import ToolGrant
from sutra_app.orchestrator.builder_rights import (
    NARROWEST, READ_TOOLS, WRITE_TOOLS, NodeRights, allowed_tools, words,
)

__all__ = ["NodeRights", "READ_TOOLS", "WRITE_TOOLS", "NARROWEST", "allowed_tools", "narrow", "words"]


def _confined(cwd: str) -> list[str]:
    """Permission rules that let the file tools write only below `cwd`: the absolute form (`//` + the path from the root) and the one relative to the working folder."""
    posix = Path(cwd).as_posix()
    absolute = "/" + posix if posix.startswith("/") else "//" + posix
    return [f"Edit({absolute}/**)", "Edit(./**)"]


def narrow(grant: ToolGrant, rights: NodeRights) -> ToolGrant:
    """`grant` taken down to `rights`: only the tools that rights allow, the allow rules of the ones kept, and the file-writing tools allowed only inside the call's own folder."""
    allowed = set(allowed_tools(rights))
    tools = tuple(name for name in grant.tools if name in allowed) or READ_TOOLS
    writes = any(name in WRITE_TOOLS for name in tools)
    rules: list[str] = []
    for rule in grant.allow:
        base = rule.split("(", 1)[0].strip()
        if base in WRITE_TOOLS:
            continue                                   # replaced below by the rules that stay inside the folder
        if base in tools and rule not in rules:
            rules.append(rule)
    for name in tools:                                 # a tool the engine named without a rule still needs its plain rule
        if name not in WRITE_TOOLS and name not in rules and not any(r.split("(", 1)[0].strip() == name for r in rules):
            rules.append(name)
    if writes:
        rules.extend(_confined(grant.cwd))
    return grant.model_copy(update={"tools": tools, "allow": tuple(rules)})
