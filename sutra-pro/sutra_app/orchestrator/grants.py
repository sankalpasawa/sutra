"""What a node may do: the tiers, the role table and the grant (multi-agent nodes, guardrails 3 and 4; D266 to D269). Pure code: no database, no file, no process, no model.

    grant = intersect("worker", StepRequest(id="a1", scope=("site/pricing/",)), output_spec, "edit")      # a frozen Grant
    resolution = resolve("worker", StepRequest(id="a1", wants=frozenset({4})), output_spec, "edit")       # the grant, what the owner could still allow, what is refused

A grant is the INTERSECTION of four things: the role table, the plan's step, the department's output spec and the owner's own folder access. It can only get smaller:

    * the role table says the most a role can ever hold (a reviewer never writes, the planner never touches the folder);
    * the step can only ask. What it asks for never adds a tier the table, the output and the owner's access do not already give. The one tier above the defaults
      that can be added is tier 4 (network), and only by an approval passed in (`approved`), for a worker, when the owner allowed changes;
    * the department's output spec says what the team's builders may do in the owner's folder (`read` or `edit`, as `engine/capabilities/workspace.py` decides);
    * the owner's access caps every grant: `none` (no working folder chosen), `read` (nothing above tier 1) or `edit`.

Tier 5 (spend beyond a node's own slice) is never part of a grant: a raise is a question to the owner each time (P25). Tier 6 (publish outside) is never granted, asked or stored:
`Grant` refuses to be built with it, so no code path can hold one. A `Grant` is frozen when the node spawns and cannot change; a stored one is read back through `Grant.from_json`,
which checks the same rules, so a row edited by hand cannot be wider than the table either.

Nothing here reads a connector, the router or the working folder: the owner's access and the output's level come in as plain values (`WorkFolder.grant()` and `output_spec(...)`
are read by the caller, in a later package). That is what keeps the Gatekeeper code and never a model.
"""
from __future__ import annotations

import dataclasses
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from sutra_app.config import NODE_DEFAULT_CAPS
from sutra_app.orchestrator.models import NodeCaps

__all__ = [
    "ROLES", "TIER_NAMES", "GRANTABLE_TIERS", "APPROVABLE_TIERS", "FOLDER_LEVELS", "OWNER_ACCESS", "TOOL_PROFILES", "COMMAND_LEVELS", "ROLE_TABLE", "RoleRule",
    "Grant", "GrantError", "StepRequest", "Ask", "Denial", "Resolution", "intersect", "resolve", "output_level_of", "normalize_scope", "scopes_overlap", "scope_width",
    "MAX_SCOPE_ENTRIES",
]

ROLES = ("planner", "worker", "reviewer")
TIER_NAMES = ("think", "read", "write files", "run commands", "network", "spend", "publish")
GRANTABLE_TIERS = (0, 1, 2, 3, 4)          # the tiers a grant can hold: 5 is a slice and a question, 6 is a wall
APPROVABLE_TIERS = frozenset({4})          # the one tier an approval can add to the defaults (tier 5 is asked per raise, tier 6 is never offered)
FOLDER_LEVELS = ("none", "read", "inspect", "edit")        # inspect = read plus the four git reads (Router.folder_for)
OWNER_ACCESS = ("none", "read", "edit")                    # no working folder chosen, read only, read and change (WorkFolder)
TOOL_PROFILES = ("none", "sutra", "sutra+github")          # connectors/tools/profiles.py: the read-only app tools, and those plus the GitHub reads
COMMAND_LEVELS = ("none", "git_reads", "sandboxed_builder")
MAX_SCOPE_ENTRIES = 50
_MAX_SCOPE_LENGTH = 400


class GrantError(ValueError):
    """A request or a stored grant the rules refuse. The message says why, in plain words; it never holds text a node wrote."""


def _rank(order: tuple[str, ...], value: str) -> int:
    return order.index(value)


def _least(order: tuple[str, ...], *values: str) -> str:
    return min(values, key=lambda value: order.index(value))


@dataclass(frozen=True)
class RoleRule:
    """The most one role can ever hold. Every part is a ceiling: the step, the output and the owner can only lower it."""

    tiers: frozenset[int]
    folder: str
    commands: str
    profile: str


ROLE_TABLE: Mapping[str, RoleRule] = {
    # the planner (the chat agent's staged call, inline in the server): thinks, and sees the chart and the plan data it is given; no folder, no tools, no commands
    "planner": RoleRule(frozenset({0, 1}), "none", "none", "none"),
    # a worker (an ordinary team run): reads, may change files in its scope, runs the git reads and J2's sandboxed builder tools, may ask for the GitHub reads
    "worker": RoleRule(frozenset({0, 1, 2, 3, 4}), "edit", "sandboxed_builder", "sutra+github"),
    # a reviewer: reads and runs the four git reads, never writes, never reaches the network
    "reviewer": RoleRule(frozenset({0, 1, 3}), "inspect", "git_reads", "sutra"),
}


# ---- write scopes -----------------------------------------------------------------------------------------------------------------

_GLOB = re.compile(r"[*?\[\]{}]")
_DRIVE = re.compile(r"^[A-Za-z]:")


def normalize_scope(entries: Iterable[Any]) -> tuple[str, ...]:
    """A write scope as a sorted tuple of plain relative paths, or `()` for the whole folder.

    Each entry is a path below the owner's working folder, written with `/` (a `\\` is read as one). An entry that is the folder itself (`.`, `./`) makes the scope the whole folder,
    which is what "no scope declared" means too, so it is not wider than the department's. Refused (GrantError): an absolute path or a drive, a `..` part, a part named `.git`
    (the repository's own state is never a team's to write), a wild-card, a control character, an empty or very long entry, and more than 50 entries. A path covered by another entry
    of the list is dropped (`site/` already holds `site/pricing/`)."""
    items = list(entries)
    if len(items) > MAX_SCOPE_ENTRIES:
        raise GrantError(f"a write scope names at most {MAX_SCOPE_ENTRIES} paths")
    cleaned: list[str] = []
    for item in items:
        if not isinstance(item, str):
            raise GrantError("a write scope is made of paths written as text")
        text = item.replace("\\", "/").strip()
        if not text or len(text) > _MAX_SCOPE_LENGTH:
            raise GrantError("a path of a write scope is empty or too long")
        if any(ord(char) < 32 or ord(char) == 127 for char in text):
            raise GrantError("a path of a write scope holds a control character")
        if text.startswith("/") or text.startswith("~") or _DRIVE.match(text):
            raise GrantError("a write scope names paths below the working folder, not absolute ones")
        if _GLOB.search(text):
            raise GrantError("a write scope names exact paths, with no wild-card")
        parts = [part for part in text.split("/") if part not in ("", ".")]
        if ".." in parts:
            raise GrantError("a write scope cannot leave the working folder")
        if any(part.lower() == ".git" for part in parts):
            raise GrantError("the .git folder is never part of a write scope")
        if not parts:
            return ()                                              # the folder itself: the whole folder
        cleaned.append("/".join(parts) + ("/" if text.endswith("/") else ""))
    unique = sorted(set(cleaned))
    kept = [path for path in unique if not any(other != path and _covers(other, path) for other in unique)]
    return tuple(kept)


def _covers(parent: str, child: str) -> bool:
    """`child` is `parent` or lies below it."""
    base = parent.rstrip("/")
    return child.rstrip("/") == base or child.startswith(base + "/")


def scopes_overlap(first: tuple[str, ...], second: tuple[str, ...]) -> bool:
    """Two write scopes (normalised) can change the same path. `()` is the whole folder, so it overlaps every scope, another whole folder included."""
    if not first or not second:
        return True
    return any(_covers(a, b) or _covers(b, a) for a in first for b in second)


def scope_width(scope: tuple[str, ...]) -> str:
    """`whole` (no scope: the whole folder), `one` (a single path) or `wide` (more than one path). A wide scope is one the plan gate asks about."""
    if not scope:
        return "whole"
    return "one" if len(scope) == 1 else "wide"


# ---- the request and the result ---------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class StepRequest:
    """What one plan step asks for. It can only ask: nothing in it adds a tier the rules do not give. There is no field for text: a step's words never reach this code.

    `wants`: tiers the step asks for beyond the defaults (only 4 can be given, by an approval; 5 and 6 are always refused). `scope`: the paths it wants to change (empty: no
    scope declared, the whole folder). `tool_profile`: the app tools it asks for."""

    id: str = ""
    wants: frozenset[int] = frozenset()
    scope: tuple[str, ...] = ()
    tool_profile: str = "none"

    def __post_init__(self) -> None:
        wants = frozenset(self.wants)
        if any(isinstance(tier, bool) or not isinstance(tier, int) or not 0 <= tier <= 6 for tier in wants):
            raise GrantError("a step asks for tiers from 0 to 6")
        if self.tool_profile not in TOOL_PROFILES:
            raise GrantError("a step asks for the tool profile none, sutra or sutra+github")
        object.__setattr__(self, "wants", wants)
        object.__setattr__(self, "scope", tuple(self.scope))


@dataclass(frozen=True)
class Ask:
    """A tier the step wants and the owner (or the Decide for me rule table) could still allow."""

    tier: int
    why: str


@dataclass(frozen=True)
class Denial:
    """A tier the step wants and nobody can allow, with the reason in plain words (an audit row `grant.denied`)."""

    tier: int
    why: str


def output_level_of(output: Any) -> str:
    """`read` or `edit`: the most the team's builders may do in the owner's folder. Takes the output spec itself (anything with a `workspace` attribute), the word, or None (no
    spec: `read`, as `workspace_for` answers for a builder with no spec). An unknown word is `read`: deny by default."""
    level = getattr(output, "workspace", output)
    return "edit" if level == "edit" else "read"


def _check_inputs(role: str, owner_access: str) -> None:
    if role not in ROLE_TABLE:
        raise GrantError(f"that is not a role: the roles are {', '.join(ROLES)}")
    if owner_access not in OWNER_ACCESS:
        raise GrantError("the owner's access is none, read or edit")


@dataclass(frozen=True)
class Grant:
    """The grant of one node, frozen at spawn (D267). Building one checks every rule below, so a wider grant than the role table cannot exist, tier 6 least of all.

    `tiers`: the tiers it holds, from 0 to 4. `folder`: none, read, inspect (read plus the four git reads) or edit. `scope`: the paths a writer may change (`()`: the whole folder;
    only a writer has one). `tool_profile` and `commands`: the app tools and the commands it may run. `caps`: its calls, dollars and time. `id` and `node_id` are put on when
    the node exists (`for_node`)."""

    role: str
    tiers: tuple[int, ...]
    folder: str = "none"
    scope: tuple[str, ...] = ()
    tool_profile: str = "none"
    commands: str = "none"
    caps: NodeCaps = field(default_factory=lambda: _default_caps())
    id: str = ""
    node_id: str = ""

    def __post_init__(self) -> None:
        rule = ROLE_TABLE.get(self.role)
        if rule is None:
            raise GrantError("a grant needs one of the roles planner, worker or reviewer")
        tiers = tuple(self.tiers)
        if any(isinstance(tier, bool) or not isinstance(tier, int) for tier in tiers):
            raise GrantError("a grant holds whole tiers")
        if any(tier in (5, 6) for tier in tiers):
            raise GrantError("a grant never holds tier 5 (spend beyond the slice) or tier 6 (publish outside)")
        if any(tier not in GRANTABLE_TIERS for tier in tiers) or list(tiers) != sorted(set(tiers)) or 0 not in tiers:
            raise GrantError("a grant holds tiers from 0 to 4, once each, in order, and always tier 0")
        if not set(tiers) <= rule.tiers:
            raise GrantError(f"a {self.role} cannot hold tier {sorted(set(tiers) - rule.tiers)[0]}")
        for name, value, order, ceiling in (("folder", self.folder, FOLDER_LEVELS, rule.folder), ("tool profile", self.tool_profile, TOOL_PROFILES, rule.profile),
                                            ("commands", self.commands, COMMAND_LEVELS, rule.commands)):
            if value not in order:
                raise GrantError(f"a grant has no such {name}")
            if _rank(order, value) > _rank(order, ceiling):
                raise GrantError(f"a {self.role} cannot have {name} {value}")
        scope = tuple(self.scope)
        if scope != normalize_scope(scope):
            raise GrantError("the write scope of a grant is in its plain form (normalize_scope)")
        has = set(tiers)
        if (2 in has) != (self.folder == "edit"):
            raise GrantError("tier 2 (write files) goes with the folder level edit, and only with it")
        if (3 in has) != (self.commands != "none"):
            raise GrantError("tier 3 (run commands) goes with a commands level, and only with it")
        if self.commands == "git_reads" and self.folder not in ("inspect", "edit"):
            raise GrantError("the git reads need a folder to run in")
        if self.commands == "sandboxed_builder" and self.folder != "edit":
            raise GrantError("the builder tools of a worker go with a folder it may change")
        if (4 in has) != (self.tool_profile == "sutra+github"):
            raise GrantError("tier 4 (network) goes with the tool profile sutra+github, and only with it")
        if scope and 2 not in has:
            raise GrantError("only a writer has a write scope")
        if 1 in has and self.role != "planner" and self.folder == "none" and self.tool_profile == "none":
            raise GrantError("tier 1 (read) needs a folder to read or the read-only app tools")
        if self.role != "planner" and 1 not in has and (self.folder != "none" or self.tool_profile != "none"):
            raise GrantError("a folder or a tool profile goes with tier 1")
        if self.role == "planner" and (self.folder != "none" or self.tool_profile != "none" or self.commands != "none"):
            raise GrantError("the planner has no folder, no tools and no commands")
        object.__setattr__(self, "tiers", tiers)
        object.__setattr__(self, "scope", scope)

    # ---- reading a grant -------------------------------------------------------------------------------------------------------

    def has(self, tier: int) -> bool:
        return tier in self.tiers

    @property
    def writer(self) -> bool:
        return 2 in self.tiers

    @property
    def scope_width(self) -> str:
        """`none` for a node that does not write; else `whole`, `one` or `wide` (see `scope_width`)."""
        return scope_width(self.scope) if self.writer else "none"

    @property
    def writes_alone(self) -> bool:
        """A writer that declared no scope holds the whole folder, so it runs alone among writers (D260)."""
        return self.writer and not self.scope

    def for_node(self, grant_id: str, node_id: str) -> "Grant":
        """The same grant with its ids put on (it is frozen: this is a new object)."""
        return dataclasses.replace(self, id=grant_id, node_id=node_id)

    def to_json(self) -> dict[str, Any]:
        return {"id": self.id, "node_id": self.node_id, "role": self.role, "tiers": list(self.tiers), "folder": self.folder, "scope": list(self.scope),
                "tool_profile": self.tool_profile, "commands": self.commands, "caps": self.caps.model_dump(mode="json")}

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "Grant":
        """A stored grant, checked by the same rules as a new one. Anything missing, unknown or wider than the role table is a GrantError."""
        if not isinstance(data, Mapping):
            raise GrantError("a stored grant is an object")
        known = {"id", "node_id", "role", "tiers", "folder", "scope", "tool_profile", "commands", "caps"}
        if set(data) - known:
            raise GrantError("a stored grant has a field a grant does not have")
        if "role" not in data or "tiers" not in data:
            raise GrantError("a stored grant names its role and its tiers")
        try:
            caps = NodeCaps.model_validate(data["caps"]) if "caps" in data else _default_caps()
            return cls(role=data["role"], tiers=tuple(data["tiers"]), folder=data.get("folder", "none"), scope=tuple(data.get("scope", ())),
                       tool_profile=data.get("tool_profile", "none"), commands=data.get("commands", "none"), caps=caps, id=str(data.get("id", "")),
                       node_id=str(data.get("node_id", "")))
        except (TypeError, ValueError) as exc:
            if isinstance(exc, GrantError):
                raise
            raise GrantError("a stored grant is not in the shape a grant has") from None


def _default_caps() -> NodeCaps:
    return NodeCaps(calls=int(NODE_DEFAULT_CAPS["node_calls"] or 60), usd=NODE_DEFAULT_CAPS["node_usd"], wall_s=int(NODE_DEFAULT_CAPS["node_wall_s"] or 1800))


@dataclass(frozen=True)
class Resolution:
    """The grant, and what is left over: what the owner could still allow (`asks`) and what nobody can (`denied`)."""

    grant: Grant
    asks: tuple[Ask, ...] = ()
    denied: tuple[Denial, ...] = ()


# ---- the intersection -------------------------------------------------------------------------------------------------------------

def resolve(role: str, step: StepRequest | None, output: Any, owner_access: str, *, approved: Iterable[int] = (), caps: NodeCaps | None = None,
            grant_id: str = "", node_id: str = "") -> Resolution:
    """The grant of one node and what is left over. `output` is the department's output spec (or `read` / `edit`, or None), `owner_access` is `none`, `read` or `edit`.
    `approved` are tiers the owner (or a rule) allowed for this node; only tier 4 can be added by one. Raises GrantError for a role, an access or a scope that is not one."""
    _check_inputs(role, owner_access)
    step = step if step is not None else StepRequest()
    rule = ROLE_TABLE[role]
    level = output_level_of(output)
    allowed = frozenset(approved) & APPROVABLE_TIERS
    scope = normalize_scope(step.scope)                       # checked even for a node that cannot write: a plan with a bad path is a bad plan

    # folder: what the output lets the role do, capped by the role and by the owner (the owner's `edit` is also what lets the git reads run, as Router.folder_for decides)
    if role == "planner":
        folder = "none"
    else:
        wanted = ("edit" if level == "edit" else "read") if role == "worker" else ("inspect" if level == "edit" else "read")
        folder = _least(FOLDER_LEVELS, wanted, rule.folder, owner_access)
    commands = "none"
    if role == "worker" and folder == "edit":
        commands = "sandboxed_builder"
    elif role == "reviewer" and folder == "inspect":
        commands = "git_reads"

    # tools: what the step asks for, capped by the role; tier 4 only with an approval, for a worker, when the owner allowed changes
    profile = "none" if role == "planner" else _least(TOOL_PROFILES, "sutra" if step.tool_profile == "sutra+github" else step.tool_profile, rule.profile)
    asks: list[Ask] = []
    denied: list[Denial] = []
    if 4 in step.wants or step.tool_profile == "sutra+github":
        reason = _why_not_network(role, owner_access)
        if reason:
            denied.append(Denial(4, reason))
        elif 4 in allowed:
            profile = "sutra+github"                           # the profile that carries tier 4 is only ever given with an approval
        else:
            asks.append(Ask(4, "Read GitHub (read only), through your own GitHub login"))

    # the tiers follow from the pieces
    tiers = {0}
    if role == "planner" or folder != "none" or profile != "none":
        tiers.add(1)
    if folder == "edit":
        tiers.add(2)
    if commands != "none":
        tiers.add(3)
    if profile == "sutra+github":
        tiers.add(4)
    for tier in sorted(step.wants):
        if tier == 6:
            denied.append(Denial(6, "Publishing outside is never available to a node"))
        elif tier == 5:
            denied.append(Denial(5, "A node cannot raise its own budget: a raise is a question to you, each time"))
        elif tier in (2, 3) and tier not in tiers:
            denied.append(Denial(tier, _why_not(tier, role, level, owner_access)))
        elif tier == 1 and 1 not in tiers:
            denied.append(Denial(1, _why_not(1, role, level, owner_access)))
    grant = Grant(role=role, tiers=tuple(sorted(tiers)), folder=folder, scope=scope if 2 in tiers else (), tool_profile=profile, commands=commands,
                  caps=caps if caps is not None else _default_caps(), id=grant_id, node_id=node_id)
    return Resolution(grant, tuple(asks), tuple(denied))


def intersect(role: str, step: StepRequest | None, output: Any, owner_access: str, *, approved: Iterable[int] = (), caps: NodeCaps | None = None,
              grant_id: str = "", node_id: str = "") -> Grant:
    """The grant of one node: the role table, the step, the output spec and the owner's access, intersected (see the module text). Never wider than any one of them."""
    return resolve(role, step, output, owner_access, approved=approved, caps=caps, grant_id=grant_id, node_id=node_id).grant


def _why_not_network(role: str, owner_access: str) -> str:
    if role != "worker":
        return f"A {role} never reaches the network"
    if owner_access != "edit":
        return "The network is only open to a project when you allowed changes to the working folder"
    return ""


def _why_not(tier: int, role: str, level: str, owner_access: str) -> str:
    if role == "planner":
        return "The planner only thinks: it has no folder and no commands"
    if owner_access == "none":
        return "No working folder is chosen"
    if tier == 2:
        if role != "worker":
            return f"A {role} never changes files"
        if level != "edit":
            return "The team's output only reads the folder"
        return "The working folder is read only"
    if tier == 3:
        return "Commands need the working folder to allow changes" if owner_access != "edit" else "This role runs no commands here"
    return "Nothing to read here"
