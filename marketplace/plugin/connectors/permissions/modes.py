"""Permission modes and outcomes.

Six modes, mirroring Claude Code. `manual` is an accepted alias for `default`,
as it is in Claude Code v2.1.200+.
"""
from enum import Enum


class Outcome(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class Mode(str, Enum):
    #: Prompts on first use of each tool.
    DEFAULT = "default"
    #: Auto-accepts content writes in granted repositories. Destructive tools still prompt.
    ACCEPT_EDITS = "acceptEdits"
    #: Reads only. Every write is hard-denied ABOVE allow rules.
    PLAN = "plan"
    #: Auto-approves after a safety check.
    #: NOT parity with Claude's trained classifier -- see SafetyCheck in engine.py.
    AUTO = "auto"
    #: Auto-denies unless an allow rule pre-approves.
    #: requiresUserInteraction tools are denied even when allowed.
    DONT_ASK = "dontAsk"
    #: Skips prompts, EXCEPT the actions no mode auto-approves.
    BYPASS = "bypassPermissions"

    @classmethod
    def parse(cls, value):
        """Accept the canonical name or a documented alias. Unknown -> ValueError."""
        if isinstance(value, cls):
            return value
        text = str(value).strip()
        if text.lower() == "manual":
            return cls.DEFAULT
        for member in cls:
            if member.value == text:
                return member
        # Case-insensitive second pass: settings files are hand-edited.
        for member in cls:
            if member.value.lower() == text.lower():
                return member
        raise ValueError("unknown permission mode: %r" % (value,))


#: Modes in which a write is blocked outright, above allow rules (step 2).
HARD_BLOCK_WRITES = frozenset({Mode.PLAN})
