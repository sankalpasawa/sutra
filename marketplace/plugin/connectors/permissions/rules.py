"""Rule parsing: `Tool` and `Tool(specifier)`.

Grammar (design/04 §4.1):

    Tool                            every use of the tool
    Tool(*)                         identical to the bare name
    Tool(<repo>[:<qualifier>])      resource form
    Tool(<param>:<value>)           parameter form -- deny/ask ONLY

Disambiguating the two colon forms is deterministic, not heuristic: the
resource form's repo pattern always contains a `/` or is exactly `*`, because
a GitHub repository is always `owner/name`. A parameter name can be neither.

A rule that cannot be honoured is never silently dropped and never silently
widened: it is marked `ignored` with a `warning`, and the caller surfaces it at
startup. Claude Code does the same for `Bash(command:...)`.
"""
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class RuleKind(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


#: Fields already covered by the resource form. A rule may not name these in
#: parameter form, for the reason Claude ignores `Bash(command:rm *)`: the
#: parameter form is bypassable where the resource form is not.
PRIMARY_FIELDS = frozenset({
    "repository", "repo", "path", "branch", "base", "head", "ref", "connector_id",
})

_RULE_RE = re.compile(r"^\s*(?P<tool>[^()\s]+)\s*(?:\((?P<spec>.*)\))?\s*$", re.DOTALL)
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
#: An allow-list tool glob must be anchored by a glob-free provider segment,
#: mirroring Claude's `mcp__<server>__*` rule (the server segment must be literal).
_ANCHORED_GLOB_RE = re.compile(r"^[A-Za-z0-9_-]+\.")


@dataclass(frozen=True)
class Rule:
    """One parsed permission rule."""
    raw: str
    kind: RuleKind
    source: str = "unknown"

    tool_pattern: str = "*"
    #: None means the bare form: matches every use of the tool.
    repo_pattern: Optional[str] = None
    qualifier_pattern: Optional[str] = None
    param_name: Optional[str] = None
    param_value: Optional[str] = None

    ignored: bool = False
    warning: Optional[str] = None

    @property
    def is_bare(self) -> bool:
        """True when the rule names a tool with no specifier.

        A bare rule in `deny` removes the tool from the model's context.
        """
        return (
            self.repo_pattern is None
            and self.param_name is None
            and self.qualifier_pattern is None
        )

    @property
    def is_param_form(self) -> bool:
        return self.param_name is not None

    def __str__(self) -> str:
        return self.raw


def _ignored(raw, kind, source, warning) -> Rule:
    return Rule(raw=raw, kind=kind, source=source, ignored=True, warning=warning)


def parse_rule(raw: str, kind: RuleKind, source: str = "unknown") -> Rule:
    """Parse one rule string. Never raises: an unusable rule comes back ignored."""
    if not isinstance(raw, str) or not raw.strip():
        return _ignored(str(raw), kind, source, "empty rule")

    match = _RULE_RE.match(raw)
    if not match:
        return _ignored(raw, kind, source, "malformed rule; expected Tool or Tool(specifier)")

    tool = match.group("tool").strip()
    spec = match.group("spec")

    if not tool:
        return _ignored(raw, kind, source, "missing tool name")

    # --- tool-name globs -------------------------------------------------
    # deny/ask accept any glob in the tool position. allow accepts one only
    # after a literal, glob-free provider segment, so an allow rule always
    # names a provider you configured.
    if "*" in tool and kind is RuleKind.ALLOW:
        head = tool.split("*", 1)[0]
        if not _ANCHORED_GLOB_RE.match(head):
            return _ignored(
                raw, kind, source,
                "unanchored allow glob %r: an allow rule's provider segment must be "
                "literal (e.g. 'github.get_*')" % tool,
            )

    # --- bare form -------------------------------------------------------
    if spec is None:
        return Rule(raw=raw, kind=kind, source=source, tool_pattern=tool)

    spec = spec.strip()
    if spec in ("", "*"):
        # Tool(*) is documented as identical to the bare name.
        return Rule(raw=raw, kind=kind, source=source, tool_pattern=tool)

    # --- parameter form vs resource form ---------------------------------
    head, sep, tail = spec.partition(":")
    head = head.strip()
    is_param_form = bool(sep) and _IDENTIFIER_RE.match(head) and "/" not in head

    if is_param_form:
        if kind is RuleKind.ALLOW:
            return _ignored(
                raw, kind, source,
                "parameter-form rules are not accepted in allow: matching one parameter "
                "does not establish the call is safe overall. Use the resource form.",
            )
        if head in PRIMARY_FIELDS:
            return _ignored(
                raw, kind, source,
                "%r is a primary resource field and is not matchable in parameter form "
                "(it would be bypassable). Use the resource form, e.g. Tool(owner/name)."
                % head,
            )
        return Rule(
            raw=raw, kind=kind, source=source, tool_pattern=tool,
            param_name=head, param_value=tail.strip(),
        )

    # --- resource form: <repo>[:<qualifier>] -----------------------------
    repo = head
    qualifier = tail.strip() if sep else None
    if not repo:
        return _ignored(raw, kind, source, "empty repository pattern")
    if repo != "*" and "/" not in repo:
        return _ignored(
            raw, kind, source,
            "repository pattern %r must be 'owner/name' (wildcards allowed) or '*'" % repo,
        )
    if sep and not qualifier:
        return _ignored(raw, kind, source, "empty qualifier after ':'")

    return Rule(
        raw=raw, kind=kind, source=source, tool_pattern=tool,
        repo_pattern=repo, qualifier_pattern=qualifier,
    )


def parse_rules(raws, kind: RuleKind, source: str = "unknown") -> List[Rule]:
    """Parse a list of rule strings, preserving order (order is not significance)."""
    return [parse_rule(raw, kind, source) for raw in (raws or [])]
