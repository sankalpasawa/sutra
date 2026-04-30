#!/bin/bash
# validate-hook-paths.sh — pre-release CI guard.
#
# Reads marketplace/plugin/hooks/hooks.json and confirms every `command` path
# referenced (after expanding ${CLAUDE_PLUGIN_ROOT}) exists on disk inside the
# plugin tree AND is git-tracked. Catches the description-vs-source-tree drift
# class (v2.10.0 incident: hooks.json referenced inbox-display.sh, file existed
# in working tree but was never git add'd → installs from the published tarball
# saw `No such file or directory` on every SessionStart).
#
# Exit 0: every hook path exists + is tracked.
# Exit 1: at least one hook path missing or untracked. Prints the offenders.
#
# Run pre-commit, in tests/run-all.sh, and as a release-cut acceptance gate.
set -u

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
HOOKS_JSON="$PLUGIN_ROOT/hooks/hooks.json"

if [ ! -f "$HOOKS_JSON" ]; then
  echo "validate-hook-paths: FAIL — hooks.json missing at $HOOKS_JSON" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "validate-hook-paths: FAIL — python3 required" >&2
  exit 1
fi

# Extract every command path; drop ${CLAUDE_PLUGIN_ROOT} prefix; emit one path
# per line (relative to plugin root, which is where files live on disk).
PATHS=$(python3 - "$HOOKS_JSON" <<'PY'
import json, sys, re
h = json.load(open(sys.argv[1]))
out = []
for ev, blocks in h.get("hooks", {}).items():
    for b in blocks:
        for hk in b.get("hooks", []):
            cmd = hk.get("command", "")
            # only validate command-type entries that point at our tree
            if hk.get("type") != "command":
                continue
            if "${CLAUDE_PLUGIN_ROOT}" not in cmd:
                continue
            rel = cmd.replace("${CLAUDE_PLUGIN_ROOT}/", "").split()[0]
            out.append(rel)
for p in sorted(set(out)):
    print(p)
PY
)

if [ -z "$PATHS" ]; then
  echo "validate-hook-paths: FAIL — no \${CLAUDE_PLUGIN_ROOT} commands found in hooks.json" >&2
  exit 1
fi

MISSING_FS=()
UNTRACKED=()
TOTAL=0
OK=0

# Best-effort: detect git status only when run inside a git checkout.
GIT_OK=0
if (cd "$PLUGIN_ROOT" && git rev-parse --git-dir >/dev/null 2>&1); then
  GIT_OK=1
fi

while IFS= read -r rel; do
  TOTAL=$((TOTAL+1))
  abs="$PLUGIN_ROOT/$rel"
  if [ ! -f "$abs" ]; then
    MISSING_FS+=("$rel")
    continue
  fi
  if [ "$GIT_OK" = "1" ]; then
    if ! (cd "$PLUGIN_ROOT" && git ls-files --error-unmatch "$rel" >/dev/null 2>&1); then
      UNTRACKED+=("$rel")
      continue
    fi
  fi
  OK=$((OK+1))
done <<< "$PATHS"

echo "validate-hook-paths: $OK/$TOTAL hook paths exist and are git-tracked"
[ "$GIT_OK" = "0" ] && echo "  (note: not in a git checkout — only filesystem presence checked)"

if [ "${#MISSING_FS[@]}" -gt 0 ]; then
  echo "  MISSING ON DISK:" >&2
  for p in "${MISSING_FS[@]}"; do echo "    - $p" >&2; done
fi
if [ "${#UNTRACKED[@]}" -gt 0 ]; then
  echo "  UNTRACKED IN GIT (will not ship in plugin tarball):" >&2
  for p in "${UNTRACKED[@]}"; do echo "    - $p" >&2; done
fi

[ "${#MISSING_FS[@]}" -eq 0 ] && [ "${#UNTRACKED[@]}" -eq 0 ] && exit 0
exit 1
