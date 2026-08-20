"""Connector permission engine — a faithful port of Claude Code's permission model.

Semantics verified against code.claude.com/docs/en/permissions on 2026-08-20.
Design of record: ../design/04-capabilities-agent.md

The three properties everything else depends on:

  1. Evaluation order is deny -> ask -> allow, first match wins, and rule
     SPECIFICITY DOES NOT REORDER. A broad deny beats a narrow allow.
  2. A bare tool name in `deny` removes the tool from the model's context.
  3. Hooks narrow, never widen. A hook that blocks wins over every allow rule;
     a hook that allows loses to any matching deny or ask rule.

Stdlib only, by design: this package must be importable from sutra-ui, whose
runtime dependencies are fastapi/uvicorn/websockets and whose test suite
refuses to import anything else.
"""
from .modes import Mode, Outcome
from .rules import Rule, RuleKind, parse_rule, parse_rules
from .tools import ToolDef, ToolRegistry, GITHUB_TOOLS
from .settings import PermissionSettings, SettingsSource, load_settings
from .engine import Decision, HookResult, PermissionEngine, ToolCall

__all__ = [
    "Mode", "Outcome",
    "Rule", "RuleKind", "parse_rule", "parse_rules",
    "ToolDef", "ToolRegistry", "GITHUB_TOOLS",
    "PermissionSettings", "SettingsSource", "load_settings",
    "Decision", "HookResult", "PermissionEngine", "ToolCall",
]
