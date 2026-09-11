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

# §6 tenant: the generator now REFUSES to publish without one — an
# auto-committing public-Pages writer defaulting to "every tenant" is the worst
# possible place to forget the boundary. Same selector the per-turn resolve hook
# exports; validated as data, exactly like SITE_DIR and LABEL.
TENANT=$(sed -n 's/^TENANT=//p' "$CFG" 2>/dev/null | head -1 | tr -d '\r')
TENANT="${TENANT:-${PLACEMENT_TENANT:-T-local}}"
case "$TENANT" in
  ''|*'$'*|*'`'*|*';'*|*'|'*|*'&'*|*' '*) TENANT="T-local" ;;
esac

KIT="${SUTRA_NATIVE_HOME:-$HOME/.sutra-native/user-kit}"
[ -d "$KIT/domains" ] || exit 0
STATE="$REPO_ROOT/.claude"

NOW=$(date +%s)

# -- drift: full-content fingerprint (mtimes lie; content does not) ----------
FP=$( { cat "$KIT/domains/INDEX.jsonl" "$KIT"/domains/*.json \
            "$KIT"/charters/*.json ; } 2>/dev/null | shasum -a 256 2>/dev/null | cut -d' ' -f1)
[ -z "$FP" ] && exit 0
STAMP="$REPO_ROOT/$SITE_DIR/.registry-stamp"
[ "$(cat "$STAMP" 2>/dev/null)" = "$FP" ] && exit 0

GEN="${CLAUDE_PLUGIN_ROOT:-}/lib/domains_page.py"
[ -f "$GEN" ] || GEN="$REPO_ROOT/sutra/marketplace/plugin/lib/domains_page.py"
[ -f "$GEN" ] || exit 0
ERR="$STATE/domains-refresh.err"

# -- never-shrink guard (2.263.1; codex fold 2026-09-11) ---------------------
# Twice (bb66966, c991193) a machine whose registry held a FEW domains
# regenerated the public site over the 55-domain published export and broke
# the byte-pinned importer suite on the next desktop release. An unattended
# publisher must never shrink the public set: the cheap precheck here
# (registry rows vs published department pages) gates BOTH lanes; the full
# regen below additionally dry-runs into a temp dir and refuses if any
# published dref-*.html / C-*.html page would go missing.
SITE="$REPO_ROOT/$SITE_DIR"
N_KIT=$(grep -c . "$KIT/domains/INDEX.jsonl" 2>/dev/null)
case "$N_KIT" in ''|*[!0-9]*) N_KIT=0 ;; esac
N_SITE=$(ls "$SITE"/dref-*.html 2>/dev/null | grep -c .)
case "$N_SITE" in ''|*[!0-9]*) N_SITE=0 ;; esac
if [ "$N_KIT" -lt "$N_SITE" ]; then
  printf 'domains-site-refresh: refused - registry has %s domain rows but the published site has %s department pages; a partial registry never shrinks the public site (kit=%s)\n' \
    "$N_KIT" "$N_SITE" "$KIT" > "$ERR" 2>/dev/null
  exit 0
fi

# Published page basenames a regen must keep (dref = department, C = charter).
_published_pages() {
  ( cd "$SITE" 2>/dev/null && ls dref-*.html C-*.html 2>/dev/null ) | sort
}

# -- FAST LANE (founder 2026-08-01: data on the fly): push ONLY registry.json
# on drift, lightly coalesced (3 min, codex fold) — pages hydrate it on load.
# Full page regen keeps the 60-min debounce below. Freshness honesty: numbers
# show after GitHub Pages publishes the push (usually ~1 min, up to ~10).
FLAST=$(cat "$STATE/domains-fastlane-last" 2>/dev/null)
case "$FLAST" in ''|*[!0-9]*) FLAST=0 ;; esac
FSTAMP=$(cat "$STATE/domains-fastlane-fp" 2>/dev/null)
if [ "$FSTAMP" != "$FP" ] && [ $((NOW - FLAST)) -ge 180 ]; then
  if python3 - "$GEN" "$REPO_ROOT/$SITE_DIR" "$TENANT" >/dev/null 2>>"$ERR" <<'PYEOF'
import subprocess, sys
subprocess.run([sys.executable, sys.argv[1], sys.argv[2], "--export-registry",
                "--tenant", sys.argv[3]], check=True, timeout=60)
PYEOF
  then
    printf '%s\n' "$FP" > "$STATE/domains-fastlane-fp" 2>/dev/null
    printf '%s\n' "$NOW" > "$STATE/domains-fastlane-last" 2>/dev/null
    SREPO=$(git -C "$REPO_ROOT/$SITE_DIR" rev-parse --show-toplevel 2>/dev/null)
    if [ -n "$SREPO" ]; then
      export GIT_TERMINAL_PROMPT=0
      git -C "$SREPO" add -- "$REPO_ROOT/$SITE_DIR/registry.json" >/dev/null 2>&1
      if git -C "$SREPO" commit -q -m "chore(domains): fast-lane data refresh" >/dev/null 2>&1; then
        python3 - "$SREPO" >/dev/null 2>>"$ERR" <<'PYEOF'
import subprocess, sys
try:
    subprocess.run(["git", "-C", sys.argv[1], "push", "-q", "origin", "HEAD"], timeout=60)
except Exception:
    pass
PYEOF
        echo "domains-site-refresh: fast-lane data pushed (registry.json)" >&2
      fi
    fi
  fi
fi

# -- debounce for the FULL regen: bounds worst-case layout latency at ~60 min -
LAST=$(cat "$STATE/domains-refresh-last" 2>/dev/null)
case "$LAST" in ''|*[!0-9]*) LAST=0 ;; esac
[ $((NOW - LAST)) -lt 3600 ] && exit 0

# -- non-blocking lock: concurrent session skips silently --------------------
LOCK="$STATE/domains-refresh.lock"
mkdir "$LOCK" 2>/dev/null || exit 0
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

# -- regen (120s cap) into a TEMP dir first; stamp ONLY on success ------------
# Rendering beside the published site lets the guard compare page sets before
# a single public byte changes.
TMPSITE=$(mktemp -d -t domains-regen.XXXXXX 2>/dev/null) || exit 0
trap 'rmdir "$LOCK" 2>/dev/null; rm -rf "$TMPSITE" 2>/dev/null' EXIT
python3 - "$GEN" "$TMPSITE" "$LABEL" "$TENANT" >/dev/null 2>"$ERR" <<'PYEOF'
import subprocess, sys
gen, out, label, tenant = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
subprocess.run([sys.executable, gen, out, "--site", "--label", label,
                "--tenant", tenant], check=True, timeout=120)
PYEOF
[ $? -ne 0 ] && exit 0
MISSING=$(comm -23 <(_published_pages) <( ( cd "$TMPSITE" && ls dref-*.html C-*.html 2>/dev/null ) | sort ))
if [ -n "$MISSING" ]; then
  printf 'domains-site-refresh: refused - regenerating from %s would drop %s published page(s): %s\n' \
    "$KIT" "$(printf '%s\n' "$MISSING" | grep -c .)" "$(printf '%s' "$MISSING" | tr '\n' ' ')" > "$ERR" 2>/dev/null
  exit 0
fi
# Overlay, never replace: files the generator no longer emits stay published
# (the pre-2.263.1 behaviour - the generator wrote in place and deleted nothing).
cp -R "$TMPSITE/." "$SITE/" 2>>"$ERR" || exit 0
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
