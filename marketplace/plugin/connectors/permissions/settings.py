"""Settings hierarchy.

Five sources, managed highest. Two different merge strategies, for a reason:

  RULES are unioned across every source. Because evaluation is deny-first and
  specificity never reorders, ADDING a rule can only ever narrow the outcome or
  leave it unchanged -- so union is the safe merge and no source can widen
  another's policy by being higher precedence.

  SCALARS take the highest-precedence source that sets them, with one
  deliberate exception: the lock keys (disableBypassPermissionsMode,
  disableAutoMode) are ORed across all sources. Claude Code documents that
  disableBypassPermissionsMode "works from any scope. A user can set it in
  their own settings to lock themselves out of bypass mode." A lock that a
  higher-precedence source could silently undo is not a lock.
"""
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .modes import Mode
from .rules import Rule, RuleKind, parse_rules

#: Highest precedence first.
SOURCE_ORDER = ("managed", "session", "local", "project", "user")

_DISABLE = "disable"


@dataclass
class SettingsSource:
    name: str
    data: Dict
    path: Optional[str] = None

    @property
    def precedence(self) -> int:
        try:
            return SOURCE_ORDER.index(self.name)
        except ValueError:
            return len(SOURCE_ORDER)

    @property
    def permissions(self) -> Dict:
        block = self.data.get("permissions")
        return block if isinstance(block, dict) else {}


@dataclass
class PermissionSettings:
    rules: List[Rule] = field(default_factory=list)
    default_mode: Mode = Mode.DEFAULT
    disable_bypass: bool = False
    disable_auto: bool = False
    allow_managed_rules_only: bool = False
    #: Rules that could not be honoured, for startup surfacing. Never silently dropped.
    warnings: List[str] = field(default_factory=list)

    def by_kind(self, kind: RuleKind) -> List[Rule]:
        return [r for r in self.rules if r.kind is kind and not r.ignored]

    def effective_mode(self, requested: Optional[Mode] = None) -> Mode:
        """Resolve the session mode, honouring the locks.

        A locked-out mode falls back to `default` rather than failing: the
        session still runs, it just runs with prompts.
        """
        mode = requested if requested is not None else self.default_mode
        if mode is Mode.BYPASS and self.disable_bypass:
            return Mode.DEFAULT
        if mode is Mode.AUTO and self.disable_auto:
            return Mode.DEFAULT
        return mode


def load_settings(sources: Sequence[SettingsSource]) -> PermissionSettings:
    ordered = sorted(sources, key=lambda s: s.precedence)

    managed_only = any(
        s.name == "managed" and s.permissions.get("allowManagedPermissionRulesOnly") is True
        for s in ordered
    )

    rules: List[Rule] = []
    warnings: List[str] = []
    for source in ordered:
        if managed_only and source.name != "managed":
            continue
        perms = source.permissions
        for kind, key in (
            (RuleKind.DENY, "deny"),
            (RuleKind.ASK, "ask"),
            (RuleKind.ALLOW, "allow"),
        ):
            for rule in parse_rules(perms.get(key), kind, source.name):
                rules.append(rule)
                if rule.ignored:
                    warnings.append(
                        "[%s] ignored %s rule %r: %s"
                        % (source.name, kind.value, rule.raw, rule.warning)
                    )

    default_mode = Mode.DEFAULT
    for source in ordered:                      # highest precedence first; first wins
        raw = source.permissions.get("defaultMode")
        if raw is None:
            continue
        try:
            default_mode = Mode.parse(raw)
        except ValueError as exc:
            warnings.append("[%s] %s" % (source.name, exc))
            continue
        break

    # Locks are ORed, never overridden.
    disable_bypass = any(
        s.permissions.get("disableBypassPermissionsMode") == _DISABLE for s in ordered
    )
    disable_auto = any(
        s.permissions.get("disableAutoMode") == _DISABLE for s in ordered
    )

    return PermissionSettings(
        rules=rules,
        default_mode=default_mode,
        disable_bypass=disable_bypass,
        disable_auto=disable_auto,
        allow_managed_rules_only=managed_only,
        warnings=warnings,
    )


def read_source(name: str, path: str) -> Optional[SettingsSource]:
    """Read one settings file. A missing file is not an error; a malformed one is.

    Malformed settings fail CLOSED at the call site: the caller surfaces the
    error rather than proceeding with a silently empty rule set, because an
    empty rule set reads as 'no policy' and no policy is the widest state.
    """
    if not path or not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("%s: expected a JSON object at the top level" % path)
    return SettingsSource(name=name, data=data, path=path)
