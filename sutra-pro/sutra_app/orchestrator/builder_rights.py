"""What the builder tools of a step of a project may be, as a pure rule (D380): no process, no file, no database, no connector. The Gatekeeper's grant line (`grants.py`) and the router's narrowing
(`connectors/node_tools.py`) both read it, so the words and the enforcement cannot drift apart.

    Read, Glob, Grep       always
    Write, Edit            only inside the step's own working folder
    a shell (Bash)         only with a shell level on the grant, which no grant holds in version 1 (tier 3 is the four git reads, not a shell)
    WebSearch, WebFetch    only with tier 4 (network)
"""
from __future__ import annotations

from dataclasses import dataclass

__all__ = ["NodeRights", "READ_TOOLS", "WRITE_TOOLS", "SHELL_TOOLS", "WEB_TOOLS", "SHELL_LEVELS", "NARROWEST", "allowed_tools", "words", "owner_words"]

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
