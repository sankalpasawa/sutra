#!/usr/bin/env python3
"""
mcp_trust_mode.py — MCP tool auto-approve detector for ADR-003.

Mirrors the contract of `sh_trust_mode.py`: reads JSON on stdin (with the
PermissionRequest payload from Claude Code), prints a single JSON line:

  {"prompt": <bool>, "category": "<class>", "reason": "<text>"}

Decision logic:
  1. Mutator/send denylist check (per-vendor explicit string match) — if hit,
     prompt with category = "<vendor>-mutate".
  2. Read-verb allowlist regex — if matches, auto-approve with
     category = "mcp-read".
  3. Otherwise prompt with category = "mcp-unknown" (safe default).

ADR-003 §1. Codex R2 ADVISORY folded (regex tightening A1 + Gmail mutator
expansion A3). DIRECTIVE-ID 1777641500.

Usage:
  echo '{"tool_name":"mcp__claude_ai_Slack__slack_search_channels"}' \
    | python3 mcp_trust_mode.py
"""

from __future__ import annotations

import json
import re
import sys
from typing import Tuple

# ── Read-verb allowlist (codex A1 tightened, A1 expanded) ────────────────────
# Anchored regex: verb must appear as a clearly-bounded token, with at most
# one optional leading namespace prefix and at most one optional trailing
# single-token modifier. Drift-prone names like `get_or_create`, `read_write`,
# `fetch_and_delete`, `status_update` will NOT match (they would have an
# additional `_<verb>` chain that the regex rejects).

READ_VERBS = (
    "search", "list", "get", "read", "fetch", "query", "describe", "enrich",
    "match", "status", "info", "view", "metadata", "count", "index", "profile",
    "resolve", "open", "outline", "availability", "preview", "download",
)

_READ_VERB_SET = set(READ_VERBS)

# Mutator tokens — if any of these appear in the tokenized tool name, the tool
# is classified as mutating (prompt). Defense-in-depth against drift-prone
# names like `get_or_create`, `read_write`, `status_update`, `fetch_and_delete`.
MUTATOR_TOKENS = frozenset({
    "create", "update", "delete", "set", "add", "remove", "modify", "edit",
    "send", "forward", "respond", "submit", "publish", "unpublish",
    "label", "unlabel", "apply",
    "import", "copy", "move", "rename", "duplicate", "clone",
    "transition", "comment", "worklog", "approve", "reject",
    "archive", "unarchive", "restore",
    "revoke", "grant", "assign", "unassign", "invite", "kick", "ban",
    "schedule", "unschedule",
    "write", "upload", "ingest",
    "merge", "split",
    "fork", "init", "deploy",
    "kill", "terminate", "restart", "stop", "pause", "resume",
})


def _tokenize(name: str) -> list[str]:
    """Tokenize an MCP tool name on `_` AND camelCase boundaries. Lowercase."""
    # Strip mcp__<server>__ prefix if present.
    parts = name.split("__")
    tail = parts[-1] if parts else name
    # Split on snake_case + camelCase.
    raw = re.split(r"[_\-]+|(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", tail)
    return [t.lower() for t in raw if t]

# ── Mutator/send denylist (codex P1.2 expanded + A3 Gmail) ───────────────────
# Per-vendor explicit string match. Prompt-list ALWAYS overrides allowlist.
# Each entry is matched as a substring against the tool_name, except where
# noted with a leading "exact:" (full match required).

DENYLIST_PATTERNS: dict[str, list[str]] = {
    "slack": [
        "slack_send_message",
        "slack_send_message_draft",
        "slack_schedule_message",
        "slack_create_canvas",
        "slack_update_canvas",
    ],
    "gmail": [
        "create_draft",
        "update_draft",
        "_send_",
        "_forward_",
        "send_draft",
        "delete_thread",
        "delete_message",
        "archive_",
        "label_message",
        "label_thread",
        "unlabel_message",
        "unlabel_thread",
        "create_label",
        "apply_labels_",
        "batch_modify_",
        "bulk_label_",
    ],
    "drive": [
        "create_file",
        "copy_file",
        "batch_update_",
        "import_",
        "template-copy_",
        "duplicate-sheet_",
    ],
    "calendar": [
        "create_event",
        "update_event",
        "delete_event",
        "respond_to_event",
    ],
    "apollo": [
        "_create",          # apollo_*_create
        "_update",          # apollo_*_update
        "emailer_campaigns_",
        "organizations_bulk_enrich",
    ],
    "atlassian": [
        "createJiraIssue",
        "editJiraIssue",
        "transitionJiraIssue",
        "addCommentToJiraIssue",
        "addWorklogToJiraIssue",
        "createConfluencePage",
        "updateConfluencePage",
        "createConfluenceFooterComment",
        "createConfluenceInlineComment",
        "createIssueLink",
    ],
    "hubspot": [
        "manage_crm_objects",
        "submit_feedback",
    ],
    "playwright": [
        "browser_click",
        "browser_drag",
        "browser_drop",
        "browser_evaluate",
        "browser_fill_form",
        "browser_file_upload",
        "browser_handle_dialog",
        "browser_hover",
        "browser_navigate",
        "browser_navigate_back",
        "browser_press_key",
        "browser_resize",
        "browser_run_code_unsafe",
        "browser_select_option",
        "browser_tabs",
        "browser_type",
        "browser_wait_for",
        "browser_close",
    ],
}


def _vendor_from_tool_name(tool_name: str) -> str:
    """Extract vendor family from tool_name (best-effort, for telemetry)."""
    if "Slack" in tool_name:
        return "slack"
    if "Gmail" in tool_name:
        return "gmail"
    if "Drive" in tool_name or "drive" in tool_name.lower():
        return "drive"
    if "Calendar" in tool_name or "calendar" in tool_name.lower():
        return "calendar"
    if "Apollo" in tool_name or "apollo" in tool_name.lower():
        return "apollo"
    if "Atlassian" in tool_name or "atlassian" in tool_name.lower():
        return "atlassian"
    if "HubSpot" in tool_name or "hubspot" in tool_name.lower():
        return "hubspot"
    if "Read_ai" in tool_name or "read_ai" in tool_name.lower():
        return "read_ai"
    if "playwright" in tool_name.lower():
        return "playwright"
    if "context7" in tool_name.lower():
        return "context7"
    return "unknown"


def classify(tool_name: str) -> Tuple[bool, str, str]:
    """
    Returns (prompt: bool, category: str, reason: str).

    prompt=True  → harness should prompt the founder (do not auto-approve).
    prompt=False → auto-approve.
    """
    if not tool_name.startswith("mcp__"):
        # Not an MCP tool — outside this matcher's scope. Fall through to prompt.
        return (True, "mcp-not-applicable", f"tool_name does not start with mcp__: {tool_name}")

    vendor = _vendor_from_tool_name(tool_name)

    # Step 1 — denylist (highest precedence)
    patterns = DENYLIST_PATTERNS.get(vendor, [])
    for pat in patterns:
        if pat in tool_name:
            return (
                True,
                f"mcp-denylist-{vendor}",
                f"matched mutator/send pattern '{pat}' in tool_name",
            )

    # Step 2 — token-based classification (defense-in-depth + flexibility)
    tokens = _tokenize(tool_name)

    # 2a — any mutator token → prompt (catches status_update, get_or_create,
    # read_write, fetch_and_delete, slack_status_update, etc.)
    mutator_hits = [t for t in tokens if t in MUTATOR_TOKENS]
    if mutator_hits:
        return (
            True,
            f"mcp-mutator-token-{vendor}",
            f"mutator token(s) {mutator_hits} in tool name (vendor={vendor})",
        )

    # 2b — at least one read verb token → auto-approve (catches search/list/get
    # in any position: slack_search_channels, getJiraIssue,
    # apollo_organizations_enrich, etc.)
    read_hits = [t for t in tokens if t in _READ_VERB_SET]
    if read_hits:
        return (
            False,
            "mcp-allowlist",
            f"read verb token(s) {read_hits} in tool name (vendor={vendor})",
        )

    # Step 3 — fall through (safe default: prompt)
    return (
        True,
        "mcp-unknown",
        f"no read verb or mutator token found (vendor={vendor}, "
        f"tokens={tokens}); falling through to prompt",
    )


def main() -> int:
    raw = sys.stdin.read().strip()
    if not raw:
        # No input — treat as misconfiguration; safe default = prompt.
        out = {"prompt": True, "category": "no-input", "reason": "empty stdin"}
        print(json.dumps(out))
        return 0

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        out = {
            "prompt": True,
            "category": "malformed-input",
            "reason": f"json parse error: {exc}",
        }
        print(json.dumps(out))
        return 0  # fail-open per PERMISSIONS.md fail-open posture

    tool_name = (
        payload.get("tool_name")
        or payload.get("tool")
        or ""
    )

    prompt, category, reason = classify(tool_name)
    out = {"prompt": prompt, "category": category, "reason": reason}
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
