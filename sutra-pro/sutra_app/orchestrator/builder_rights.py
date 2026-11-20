"""What the builder tools of a step of a project may be, as a pure rule (D380, D386): no process, no file, no database, no connector. The Gatekeeper's grant line (`grants.py`) and the router's narrowing
(`connectors/node_tools.py`) both read it, so the words and the enforcement cannot drift apart.

    Read, Glob, Grep       always
    Write, Edit            only inside the step's own working folder
    a shell (Bash)         never in version 1, whatever the grant holds (tier 3 is the four git reads of the owner's folder, not a shell)
    WebSearch, WebFetch    never in version 1, whatever the grant holds (D386): tier 4 is "Read GitHub, read only" and it travels the separate tool-profile path, not the builder call

The table is the same for every step. `NodeRights` carries the grant's tiers and commands level to the router so that a router that was made for a node knows it is one (and narrows every builder call of
it, whatever its tag says), and so that a later, deliberate level has somewhere to be read; nothing in it opens a tool today. There is no shell level in the code: adding one is a decision, with its own
sandbox check, and not a string that a grant could happen to hold (D387, m8).
"""
from __future__ import annotations

from dataclasses import dataclass

__all__ = ["NodeRights", "READ_TOOLS", "WRITE_TOOLS", "NARROWEST", "allowed_tools", "words"]

READ_TOOLS = ("Read", "Glob", "Grep")
WRITE_TOOLS = ("Write", "Edit", "MultiEdit")


@dataclass(frozen=True)
class NodeRights:
    """The two parts of a frozen grant that decide the builder tools: its tiers and its commands level."""

    tiers: tuple[int, ...] = ()
    commands: str = "none"


NARROWEST = NodeRights()


def allowed_tools(rights: NodeRights) -> tuple[str, ...]:
    """The tool names a step may be offered, in a fixed order. The same for every step in version 1: `rights` is read by nobody yet, on purpose (see the top of the file)."""
    return (*READ_TOOLS, *WRITE_TOOLS)


def words(rights: NodeRights) -> str:
    """The short, plain part of the grant line that says what the builder tools of the step may do (at most 80 characters)."""
    return "reads; writes only in its own folder; no commands; no web"
