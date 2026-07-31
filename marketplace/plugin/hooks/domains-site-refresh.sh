#!/bin/bash
# domains-site-refresh.sh — SOFT auto-refresh for the published domains site.
#
# Founder direction 2026-07-31: "make it automatic. Don't make it a hard look."
# Contract: this hook NEVER blocks a turn — exit 0 on every path, no matter
# what breaks. It is dormant fleet-wide until a repo opts in (D33: we never
# auto-push a client repo they didn't ask for).
#
# Flow (guards ordered cheapest-first; codex consult 2026-07-31 folds):
#   1. opt-in  .claude/domains-autopublish  (SITE_DIR=<repo-relative>, LABEL=)
#   2. debounce: >= 60 min since last successful refresh
#   3. drift:   sha256 over FULL registry content (INDEX + domains/*.json +
#               charters/*.json) vs the stamp shipped inside the site
#   4. lock:    non-blocking mkdir; a concurrent session just skips
#   5. regen:   domains_page.py --site, 120s hard cap; stamp written ONLY
#               after success (a failed run must not suppress retries)
#   6. publish: git add/commit/push in the repo that owns SITE_DIR —
#               push-only (never pull/rebase inside a hook), prompts off,
#               60s cap; failures swallowed, next drift retries
#
# Privacy: auto-publish means minted content reaches the public page within
# the hour. public_names_withheld must be set AT MINT TIME.
# Debug: last failure (if any) at .claude/domains-refresh.err — bounded,
# overwritten each attempt, cleared on success.

set +e

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
[ -z "$REPO_ROOT" ] && exit 0
CFG="$REPO_ROOT/.claude/domains-autopublish"
[ -f "$CFG" ] || exit 0

# Config is DATA, not shell (codex): strict KV parse + path/label validation.
SITE_DIR=$(sed -n 's/^SITE_DIR=//p' "$CFG" 2>/dev/null | head -1 | tr -d '\r')
LABEL=$(sed -n 's/^LABEL=//p' "$CFG" 2>/dev/null | head -1 | tr -d '\r')
[ -z "$SITE_DIR" ] && exit 0
case "$SITE_DIR" in
  /*|*..*|*'$'*|*'`'*|*';'*|*'|'*|*'&'*|*' '*) exit 0 ;;
esac
LABEL="${LABEL:-Domains}"
case "$LABEL" in *'$'*|*'`'*|*';'*|*'|'*|*'&'*) LABEL="Domains" ;; esac

KIT="${SUTRA_NATIVE_HOME:-$HOME/.sutra-native/user-kit}"
[ -d "$KIT/domains" ] || exit 0
STATE="$REPO_ROOT/.claude"

# -- debounce first: cheapest guard, bounds worst-case latency at ~60 min ----
NOW=$(date +%s)
LAST=$(cat "$STATE/domains-refresh-last" 2>/dev/null)
case "$LAST" in ''|*[!0-9]*) LAST=0 ;; esac
[ $((NOW - LAST)) -lt 3600 ] && exit 0

# -- drift: full-content fingerprint (mtimes lie; content does not) ----------
FP=$( { cat "$KIT/domains/INDEX.jsonl" "$KIT"/domains/*.json \
            "$KIT"/charters/*.json ; } 2>/dev/null | shasum -a 256 2>/dev/null | cut -d' ' -f1)
[ -z "$FP" ] && exit 0
STAMP="$REPO_ROOT/$SITE_DIR/.registry-stamp"
[ "$(cat "$STAMP" 2>/dev/null)" = "$FP" ] && exit 0

# -- non-blocking lock: concurrent session skips silently --------------------
LOCK="$STATE/domains-refresh.lock"
mkdir "$LOCK" 2>/dev/null || exit 0
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

# -- regen (120s cap); stamp ONLY on success ---------------------------------
GEN="${CLAUDE_PLUGIN_ROOT:-}/lib/domains_page.py"
[ -f "$GEN" ] || GEN="$REPO_ROOT/sutra/marketplace/plugin/lib/domains_page.py"
[ -f "$GEN" ] || exit 0
ERR="$STATE/domains-refresh.err"
python3 - "$GEN" "$REPO_ROOT/$SITE_DIR" "$LABEL" >/dev/null 2>"$ERR" <<'PYEOF'
import subprocess, sys
gen, out, label = sys.argv[1], sys.argv[2], sys.argv[3]
subprocess.run([sys.executable, gen, out, "--site", "--label", label],
               check=True, timeout=120)
PYEOF
[ $? -ne 0 ] && exit 0
printf '%s\n' "$FP" > "$STAMP" 2>/dev/null
printf '%s\n' "$NOW" > "$STATE/domains-refresh-last" 2>/dev/null
: > "$ERR" 2>/dev/null

# -- publish: push-only, prompts off, 60s cap --------------------------------
SREPO=$(git -C "$REPO_ROOT/$SITE_DIR" rev-parse --show-toplevel 2>/dev/null)
[ -z "$SREPO" ] && exit 0
export GIT_TERMINAL_PROMPT=0
git -C "$SREPO" add -A -- "$REPO_ROOT/$SITE_DIR" >/dev/null 2>&1
git -C "$SREPO" commit -q -m "chore(domains): auto-refresh from registry drift" >/dev/null 2>&1 || exit 0
python3 - "$SREPO" >/dev/null 2>>"$ERR" <<'PYEOF'
import subprocess, sys
try:
    subprocess.run(["git", "-C", sys.argv[1], "push", "-q", "origin", "HEAD"], timeout=60)
except Exception:
    pass
PYEOF
echo "domains-site-refresh: registry drift -> site regenerated + pushed" >&2
exit 0
