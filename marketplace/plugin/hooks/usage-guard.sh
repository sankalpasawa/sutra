#!/usr/bin/env bash
# usage-guard.sh — opt-in rate-limit guard (founder direction 2026-08-07).
#
# Event: PreToolUse (no matcher) — fires on EVERY tool call, but is DORMANT
# unless ~/.sutra-usage-guard/enabled exists (clients opt in on the fly with
# `sutra-usage on`; nothing is auto-deployed behavior-wise).
#
# Behavior (delegates all logic to bin/sutra-usage check):
#   >=70% utilization  -> stderr WARNING, once per 10 min, tool call allowed
#   >=80% utilization  -> exit 2 HARD BLOCK until founder says "continue"
#                         (Claude runs `sutra-usage continue`; override
#                         auto-expires when the breaching limit window resets)
#
# Deadlock guard: a Bash call whose entire command is a bare invocation of
# THIS plugin's own bin/sutra-usage (continue/status/on/off; no pipes, no
# redirection, nothing chained) is always allowed so the unblock path itself
# is never blocked. Path identity is checked by realpath, not by basename.
# Fail-open: missing helper, missing python, fetch/parse errors -> exit 0.
# Kill-switch: ~/.usage-guard-disabled (founder revoke only).
set -u
GUARD_DIR="${SUTRA_USAGE_GUARD_DIR:-$HOME/.sutra-usage-guard}"
[ -f "$GUARD_DIR/enabled" ] || exit 0
[ -f "$HOME/.usage-guard-disabled" ] && exit 0

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
BIN="${CLAUDE_PLUGIN_ROOT:-$(dirname "$HOOK_DIR")}/bin/sutra-usage"
[ -f "$BIN" ] || BIN="$(dirname "$HOOK_DIR")/bin/sutra-usage"
[ -f "$BIN" ] || exit 0

# Allow the unblock path through. Narrow by construction:
#   * argv is tokenized with shlex, so a pipe / semicolon / redirection /
#     command substitution leaves extra tokens and the match fails;
#   * the helper token must resolve (expanduser + realpath) to THIS plugin's
#     own bin/sutra-usage. A look-alike such as /tmp/sutra-usage does NOT
#     match (codex round-1 P1, 2026-08-28: the old regex accepted any path
#     whose basename happened to be sutra-usage);
#   * an optional leading interpreter token is dropped ONLY when it resolves
#     to a shell at a known absolute path. /tmp/bash <helper> continue does
#     NOT match (codex round-2 P1: basename-only matching let a fake bash
#     execute instead), and PATH is never consulted for it (round-3 P1);
#   * an unqualified `sutra-usage` is accepted only when PATH resolves it to
#     the same file.
# Any parse error yields no ALLOW, i.e. the exemption fails CLOSED.
# Accepted residual: $BIN lives in a user-writable plugin dir, so a caller who
# could already overwrite the helper before the block engaged is out of scope
# for this matcher (codex round-2 point 4).
payload="$(cat 2>/dev/null || true)"
if [ -n "$payload" ]; then
  allow="$(printf '%s' "$payload" | python3 -c '
import json, os, shlex, shutil, sys
VERBS = {"continue", "status", "on", "off"}

def resolve(tok):
    p = os.path.expanduser(tok)
    if os.sep not in p:
        p = shutil.which(p) or ""
    return os.path.realpath(p) if p else ""

try:
    target = os.path.realpath(sys.argv[1])
    if not target:
        raise SystemExit
    # Known absolute paths only. shutil.which("bash") is deliberately NOT
    # consulted: PATH is caller-influenced, so a fake bash earlier on PATH
    # would add itself to the trusted set (codex round-3 P1, 2026-08-28).
    trusted_bash = set()
    for c in ("/bin/bash", "/usr/bin/bash", "/usr/local/bin/bash",
              "/opt/homebrew/bin/bash", "/bin/sh", "/usr/bin/sh"):
        if os.path.exists(c):
            trusted_bash.add(os.path.realpath(c))
    d = json.load(sys.stdin)
    if d.get("tool_name") != "Bash":
        raise SystemExit
    parts = shlex.split(((d.get("tool_input") or {}).get("command") or "").strip())
    if len(parts) == 3:
        if resolve(parts[0]) not in trusted_bash:
            raise SystemExit
        parts = parts[1:]
    if len(parts) != 2 or parts[1] not in VERBS:
        raise SystemExit
    if resolve(parts[0]) == target:
        print("ALLOW")
except SystemExit:
    pass
except Exception:
    pass' "$BIN" 2>/dev/null || true)"
  [ "$allow" = "ALLOW" ] && exit 0
fi

out="$(bash "$BIN" check 2>/dev/null)"
rc=$?
case "$rc" in
  20) printf '%s\n' "$out" >&2; exit 2 ;;
  10) printf '%s\n' "$out" >&2; exit 0 ;;
  *)  exit 0 ;;
esac
