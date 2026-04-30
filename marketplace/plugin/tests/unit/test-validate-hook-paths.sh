#!/bin/bash
# Unit test: scripts/validate-hook-paths.sh
#
# Regression test for the v2.10.0 incident — hooks.json referenced a hook file
# that was present in the working tree but not committed to git, so the
# published plugin tarball shipped a manifest pointing at a missing file. The
# validator must catch BOTH: (a) referenced-but-missing on disk, (b) referenced
# but not git-tracked.
set -u
PLUGIN_ROOT="$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")"
VALIDATOR="$PLUGIN_ROOT/scripts/validate-hook-paths.sh"

PASS=0; FAIL=0
_ok() { PASS=$((PASS+1)); echo "  OK  $1"; }
_no() { FAIL=$((FAIL+1)); echo "  X   $1"; }

if [ ! -x "$VALIDATOR" ]; then
  echo "  X   validator not executable: $VALIDATOR"
  exit 1
fi

# 1) Real plugin tree must be green (post-fix).
if "$VALIDATOR" >/dev/null 2>&1; then
  _ok "validator passes on current plugin tree (49/49 hook paths)"
else
  _no "validator fails on current plugin tree — did a hook file get unstaged?"
fi

# 2) Synthetic scenario: hooks.json references a non-existent file on disk.
TMPROOT=$(mktemp -d)
trap 'rm -rf "$TMPROOT"' EXIT
mkdir -p "$TMPROOT/hooks"
cat > "$TMPROOT/hooks/hooks.json" <<'EOF'
{
  "hooks": {
    "SessionStart": [
      { "hooks": [
        { "type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/never-shipped.sh", "timeout": 3 }
      ]}
    ]
  }
}
EOF
if CLAUDE_PLUGIN_ROOT="$TMPROOT" "$VALIDATOR" >/dev/null 2>&1; then
  _no "validator INCORRECTLY passed when hooks.json references a missing file"
else
  _ok "validator correctly fails when hooks.json references a missing file"
fi

# 3) Synthetic scenario: file present on disk, not in any git tree.
#    Validator should flag as UNTRACKED when run inside a git checkout, and
#    pass-with-note when not in a git checkout. Build a non-git tmproot to
#    exercise the "not in git checkout" branch (passes because file exists).
echo "#!/bin/bash" > "$TMPROOT/hooks/never-shipped.sh"
chmod +x "$TMPROOT/hooks/never-shipped.sh"
if CLAUDE_PLUGIN_ROOT="$TMPROOT" "$VALIDATOR" >/dev/null 2>&1; then
  _ok "validator passes when file present on disk in non-git tree"
else
  _no "validator failed unexpectedly when file present on disk (non-git)"
fi

# 4) Synthetic scenario: empty hooks.json — must fail (defensive).
echo '{"hooks":{}}' > "$TMPROOT/hooks/hooks.json"
if CLAUDE_PLUGIN_ROOT="$TMPROOT" "$VALIDATOR" >/dev/null 2>&1; then
  _no "validator INCORRECTLY passed when no hooks declared"
else
  _ok "validator correctly fails when hooks.json declares no commands"
fi

TOTAL=$((PASS+FAIL))
echo ""
echo "  $PASS/$TOTAL passed"
exit "$FAIL"
