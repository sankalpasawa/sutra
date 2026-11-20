"""What the builder tools of a step of a project may be (D380). Pure code: no process, no file, no database.

J2's builder asks for Claude's whole tool list in its own folder (`Read, Write, Edit, Glob, Grep, Bash, WebSearch, WebFetch`, `types.json`). For an ordinary run that is how it has always
been. A step of a project holds a GRANT, and the grant is the owner's word about what the step may do, so the host (the router, never the vendored engine) takes that list down to
what the grant allows before the call is planned:

    * Read, Glob and Grep: always (the model program keeps its reads inside its working folder);
    * Write and Edit: only inside the step's own working folder (the run's `out` folder), never anywhere else on the computer;
    * a shell (`Bash`): only with a shell level on the grant, which no grant holds in version 1. Tier 3 is the four git reads of the owner's folder, not a shell, and a shell is not
      confined to those, so tier 3 does not open it;
    * `WebSearch` and `WebFetch`: only with tier 4 (network), the one tier an approval can add.

A tool the list does not name is never allowed (deny by default). A step whose rights are not known (an older task file without them) gets the narrowest list, never the widest.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sutra_app.engine.port import ToolGrant

__all__ = ["NodeRights", "READ_TOOLS", "WRITE_TOOLS", "SHELL_TOOLS", "WEB_TOOLS", "SHELL_LEVELS", "NARROWEST", "allowed_tools", "narrow", "words", "owner_words"]

READ_TOOLS = ("Read", "Glob", "Grep")
WRITE_TOOLS = ("Write", "Edit", "MultiEdit")
SHELL_TOOLS = ("Bash", "BashOutput", "KillShell")
WEB_TOOLS = ("WebSearch", "WebFetch")
SHELL_LEVELS = frozenset({"sandboxed_builder"})          # a level of `commands` that opens the shell; `COMMAND_LEVELS` of a grant has none of it in version 1 (D380)
NETWORK_TIER = 4


@dataclass(frozen=True)
class NodeRights:
    """The two parts of a frozen grant that decide the builder tools: its tiers and its commands level."""

    tiers: tuple[int, ...] = ()
    commands: str = "none"

    @property
    def shell(self) -> bool:
        return self.commands in SHELL_LEVELS

    @property
    def web(self) -> bool:
        return NETWORK_TIER in self.tiers


NARROWEST = NodeRights()


def allowed_tools(rights: NodeRights) -> tuple[str, ...]:
    """The tool names a step with these rights may be offered, in a fixed order."""
    return (*READ_TOOLS, *WRITE_TOOLS, *(SHELL_TOOLS if rights.shell else ()), *(WEB_TOOLS if rights.web else ()))


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


def words(rights: NodeRights) -> str:
    """The short, plain part of the grant line that says what the builder tools of the step may do (at most 80 characters)."""
    parts = ["reads", "writes only in its own folder"]
    parts.append("runs commands" if rights.shell else "no commands")
    parts.append("web" if rights.web else "no web")
    return "; ".join(parts)


def owner_words(rights: NodeRights) -> str:
    """The same in the words the owner reads on the page (no tool names, no tiers)."""
    can = ["look at the files it is given", "write its own working files in a scratch space of its own"]
    if rights.web:
        can.append("search and read the web")
    cannot = ["run commands"] + ([] if rights.web else ["use the web"])
    return "This step can " + ", ".join(can[:-1]) + " and " + can[-1] + ". It cannot " + " or ".join(cannot) + "."
