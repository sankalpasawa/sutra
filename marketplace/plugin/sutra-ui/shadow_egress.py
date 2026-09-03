"""Outbound scrubbing + the tool-gating table (PLAN-100 S35).

Everything Shadow SENDS anywhere -- today that is session_say payloads --
passes through scrub() first. The gate table is the one place that states,
per shadow tool, what kind of action it is and what stands between a model
call and its effect; a test asserts every registered shadow tool has a row,
so adding a tool without deciding its gate fails CI.
"""
import re

#: NAMED so an audit line can say WHICH shape matched without recording the
#: value that matched. Piece 6 of the provider-switch plan made that a hard
#: requirement: switch egress is silent by founder decision, so the only way a
#: scrubber miss is ever discoverable after the fact is a log that says "one
#: jwt was redacted here" -- and a log that recorded the token itself would be
#: a second copy of the secret, in plaintext, on disk.
#:
#: CREDENTIALS ONLY. The shell scrubber at bin/peer-review-payload-scrub.sh
#: (via lib/privacy-sanitize.sh) also rewrites $HOME and /tmp paths and redacts
#: email and phone, which is right for shipping a diff to an outside reviewer
#: and WRONG here: a provider-switch replay hands the receiving assistant a
#: record of work on real files, and it has to read those paths afterwards.
#: Normalising them would break the handover to protect nothing -- the paths
#: are already on the machine both providers run on.
_NAMED_PATTERNS = [
    ("openai-key", re.compile(r"sk-[A-Za-z0-9_-]{8,}")),
    ("github-token", re.compile(r"ghp_[A-Za-z0-9]{20,}")),
    ("github-pat", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("slack-token", re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}")),
    ("aws-key-id", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("bearer", re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]{16,}")),
    # --- added 2026-09-02 (provider-switch piece 6) -------------------------
    # Shapes the shell scrubber already covered and this one did not. A replay
    # carries whole tool_result bodies -- entire files, `env` output, config
    # dumps -- so the shapes that only appear in file CONTENT matter here in a
    # way they never did for a one-line Shadow message.
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
    ("pem-private-key", re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        re.DOTALL)),
    ("stripe-key", re.compile(r"(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}")),
    ("slack-webhook", re.compile(r"https://hooks\.slack\.com/services/[A-Za-z0-9/_-]{10,}")),
    ("discord-webhook", re.compile(r"https://discord(?:app)?\.com/api/webhooks/[0-9]+/[A-Za-z0-9_-]{10,}")),
    # A URI with inline credentials. The USERINFO is redacted, not the whole
    # URI: the host and database name are usually the point of the line, and
    # blanking them would hide a schema the receiving model needs.
    ("db-uri-credentials", re.compile(
        r"(?i)\b((?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://)"
        r"[^\s:@/]+:[^\s:@/]+@")),
    ("private-key-env", re.compile(
        r"(?i)\b((?:api[_-]?key|secret[_-]?key|access[_-]?token|password|passwd)"
        r"\s*[=:]\s*)['\"]?[A-Za-z0-9._\-/+]{12,}['\"]?")),
]

#: Patterns that keep a captured prefix (group 1) instead of vanishing whole.
#: Redacting `DATABASE_URL=postgres://u:p@host/db` down to "[redacted]" loses
#: the fact that a database URL was there at all, which is information the
#: receiving assistant needs and the secret is not.
_PREFIX_KEEPING = {"db-uri-credentials", "private-key-env"}

#: Back-compat: the original unnamed list, still exported because it was part
#: of this module's surface before the names existed.
_PATTERNS = [pat for _name, pat in _NAMED_PATTERNS]


def scrub_detail(text):
    """Redact credential-shaped substrings. Returns (clean, {name: count}).

    Only shapes that actually matched appear in the mapping, so an audit row
    stays short and a reader can tell "nothing matched" from "six shapes
    matched" at a glance.
    """
    counts = {}
    for name, pat in _NAMED_PATTERNS:
        repl = (r"\1[redacted]") if name in _PREFIX_KEEPING else "[redacted]"
        text, k = pat.subn(repl, text)
        if k:
            counts[name] = counts.get(name, 0) + k
    return text, counts


def scrub(text):
    """Redact credential-shaped substrings. Returns (clean, n_redactions).

    Kept at this exact arity: app.py:1718, sutra_mcp.py and mission_engine.py
    all unpack two values, and widening the tuple here would break Shadow's
    live say path. scrub_detail() is the richer form.
    """
    clean, counts = scrub_detail(text)
    return clean, sum(counts.values())


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


# ------------------------------------------------------------------ floors --
# The three confirm-first floors (PRD R8): no ledger row, template, or
# standing instruction can override these -- a say that trips one pauses its
# mission for an explicit founder yes. Patterns are deliberately broad:
# a false PAUSE costs a click; a false PASS costs a repo.
_FLOOR_PATTERNS = [
    ("d52_destructive_git",
     __import__("re").compile(
         r"(--force(-with-lease)?\b|reset\s+--hard|--no-verify"
         r"|push\s+.*--delete|filter-branch|update-ref\s+-d)")),
    ("d33_client_repo",
     __import__("re").compile(
         r"~/Claude/(?!asawa-holding)[A-Za-z][A-Za-z0-9_-]*")),
    ("irreversible_external_send",
     __import__("re").compile(
         r"(?i)\b(send (the )?(email|mail|invoice)|post (to|on) "
         r"(slack|twitter|x\.com|linkedin)|publish (the )?(site|release"
         r"|post)|charge (the )?(card|customer))\b")),
]


def floor_check(text):
    """Return the list of floor names the text trips (empty = clear)."""
    return [name for name, pat in _FLOOR_PATTERNS if pat.search(text or "")]
