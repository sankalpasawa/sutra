#!/usr/bin/env python3
"""
mcp_trust_mode.py - MCP catastrophic-only auto-approve (v2.32+, ADR-003 amended)

BUILD-LAYER: L0 (fleet)
Charter: sutra/os/charters/PERMISSIONS.md Tier 1.7 (MCP Trust Mode)

v2.17 -> v2.32 amendment per founder direction 2026-05-04: align MCP posture
with Bash Trust Mode (v2.6.1 catastrophic-only). v2.17's read-verb allowlist
plus mutator-token prompt produced ~95% of MCP prompt friction with no
incremental safety vs the trusted-operator threat model. New rule:
auto-approve every MCP tool EXCEPT catastrophic verbs (delete/destroy/etc.),
bulk/mass mutators, and an explicit per-vendor catastrophe list.

Reads PermissionRequest JSON on stdin. Prints one JSON line:
  {"prompt": false, "category": "mcp-allowlist", "reason": "..."}    -> auto-allow
  {"prompt": true,  "category": "mcp-catastrophic-...", ...}         -> prompt

Catastrophic verb tokens (always prompt, vendor-agnostic):
  delete, destroy, drop, purge, wipe, truncate, eradicate, expunge,
  uninstall, deauthorize

Bulk/mass mutation patterns (always prompt):
  bulk_*, batch_modify, batch_delete, mass_*, apply_labels, bulk_label

Per-vendor explicit deny (true catastrophes that don't trip the verb rule):
  playwright: browser_run_code_unsafe, browser_evaluate  (JS execution)
  gmail:      _forward_                                  (data exfil)
  drive:      move_to_trash, _trash_                     (irreversible w/o restore)

Fail-safe-to-prompt: parse errors -> prompt=true.
"""
from __future__ import annotations

import json
import re
import sys
from typing import Tuple


CATASTROPHIC_VERBS = frozenset({
    "delete", "destroy", "drop", "purge", "wipe", "truncate",
    "eradicate", "expunge", "uninstall", "deauthorize",
})

BULK_PATTERNS = (
    "bulk_", "batch_modify", "batch_delete", "mass_",
    "apply_labels", "bulk_label",
)

# Per-vendor explicit catastrophes that don't reduce to a verb token.
# Keep TIGHT; routine create/update/send across all vendors auto-approves.
VENDOR_CATASTROPHIC: dict[str, list[str]] = {
    "playwright": [
        "browser_run_code_unsafe",
        "browser_evaluate",
    ],
    "gmail": [
        "_forward_",
    ],
    "drive": [
        "move_to_trash",
        "_trash_",
    ],
}


def _tokenize(name: str) -> list[str]:
    """Tokenize on `_`, `-`, and camelCase boundaries. Lowercase output."""
    parts = name.split("__")
    tail = parts[-1] if parts else name
    raw = re.split(
        r"[_\-]+|(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", tail)
    return [t.lower() for t in raw if t]


def _vendor_from_tool_name(tool_name: str) -> str:
    """Best-effort vendor extraction (telemetry + denylist routing)."""
    n = tool_name.lower()
    for marker, vendor in (
        ("slack", "slack"),
        ("gmail", "gmail"),
        ("drive", "drive"),
        ("calendar", "calendar"),
        ("apollo", "apollo"),
        ("atlassian", "atlassian"),
        ("hubspot", "hubspot"),
        ("read_ai", "read_ai"),
        ("playwright", "playwright"),
        ("context7", "context7"),
    ):
        if marker in n:
            return vendor
    return "unknown"


def classify(tool_name: str) -> Tuple[bool, str, str]:
    """
    Returns (prompt, category, reason).
    prompt=True  -> harness should prompt (do not auto-approve).
    prompt=False -> auto-approve.
    """
    if not tool_name.startswith("mcp__"):
        return (True, "mcp-not-applicable",
                f"tool_name does not start with mcp__: {tool_name}")

    vendor = _vendor_from_tool_name(tool_name)
    lower = tool_name.lower()

    # 1. Bulk / mass patterns (vendor-agnostic, highest precedence).
    for pat in BULK_PATTERNS:
        if pat in lower:
            return (True, f"mcp-catastrophic-bulk-{vendor}",
                    f"bulk/batch pattern '{pat}' in tool_name")

    # 2. Per-vendor explicit catastrophic denylist.
    for pat in VENDOR_CATASTROPHIC.get(vendor, []):
        if pat in tool_name:
            return (True, f"mcp-catastrophic-{vendor}",
                    f"vendor catastrophic pattern '{pat}'")

    # 3. Catastrophic verb tokens.
    tokens = _tokenize(tool_name)
    hits = [t for t in tokens if t in CATASTROPHIC_VERBS]
    if hits:
        return (True, f"mcp-catastrophic-verb-{vendor}",
                f"catastrophic verb token(s) {hits}")

    # 4. Auto-approve (default).
    return (False, "mcp-allowlist",
            f"non-catastrophic mcp tool (vendor={vendor})")


def main() -> int:
    raw = sys.stdin.read().strip()
    if not raw:
        print(json.dumps({"prompt": True, "category": "no-input",
                          "reason": "empty stdin"}))
        return 0
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(json.dumps({"prompt": True, "category": "malformed-input",
                          "reason": f"json parse error: {exc}"}))
        return 0
    tool_name = payload.get("tool_name") or payload.get("tool") or ""
    prompt, category, reason = classify(tool_name)
    print(json.dumps({"prompt": prompt, "category": category, "reason": reason}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
