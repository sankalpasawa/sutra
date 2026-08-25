"""Outbound scrubbing + the tool-gating table (PLAN-100 S35).

Everything Shadow SENDS anywhere -- today that is session_say payloads --
passes through scrub() first. The gate table is the one place that states,
per shadow tool, what kind of action it is and what stands between a model
call and its effect; a test asserts every registered shadow tool has a row,
so adding a tool without deciding its gate fails CI.
"""
import re

_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]{16,}"),
]


def scrub(text):
    """Redact credential-shaped substrings. Returns (clean, n_redactions)."""
    n = 0
    for pat in _PATTERNS:
        text, k = pat.subn("[redacted]", text)
        n += k
    return text, n


# tool -> what it is and what gates it. "write-inert" appends to Shadow's own
# ledger only; "write-acting" reaches a live session and carries the full
# authorization chain.
TOOL_GATES = {
    "shadow_sessions_list": {"kind": "read", "gate": "flag+env, call-time re-check"},
    "shadow_session_read_tail": {"kind": "read", "gate": "flag+env, call-time re-check, bounded"},
    "shadow_app_state": {"kind": "read", "gate": "flag+env, call-time re-check, redacted snapshot"},
    "shadow_ledger_read": {"kind": "read", "gate": "flag+env, call-time re-check"},
    "shadow_ledger_append": {"kind": "write-inert", "gate": "flag+env, ledger-only, append-only"},
    "shadow_session_say": {"kind": "write-acting", "gate": "flag+env + mission_id + dedupe + scrub + app-side 403/404/400/409"},
    "shadow_verify": {"kind": "read", "gate": "flag+env, call-time re-check"},
    "shadow_mission_update": {"kind": "write-inert", "gate": "flag+env, missions ledger only, state enum"},
}
